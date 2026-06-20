"""
Robot controller — Cyberwave SDK v0.5.1 per SO-101.

Flusso reale (da ispezione SDK + test live):
  1. Cyberwave(api_key, source_type='sim', environment_id=ENV_UUID)
  2. client.affect('simulation')
  3. twin = client.twin(twin_id=TWIN_UUID, environment_id=ENV_UUID)
  4. _start_simulation() via REST → cattura simulation_id
  5. twin.subscribe_joints(cb)  ← stabilisce connessione MQTT
  6. client.mqtt.publish(topic, envelope_json)  ← invia comandi joint

Joint IDs reali SO-101: _1 _2 _3 _4 _5 _6
Topic comandi: cyberwave/twin/{twin_uuid}/command
Envelope: {source_type, command, simulation_id, data:{positions,names}, timestamp}
"""

import os, time, json, math, logging
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

try:
    from cyberwave.client import Cyberwave
    from cyberwave import SOURCE_TYPE_SIM, SOURCE_TYPE_EDGE
    CYBERWAVE_AVAILABLE = True
except ImportError:
    CYBERWAVE_AVAILABLE = False
    logger.warning("cyberwave SDK non trovato — DRY RUN attivo")

JOINT_IDS   = ["_1", "_2", "_3", "_4", "_5", "_6"]
HOME_ANGLES = [0.0, 0.0, 90.0, 0.0, 0.0, 50.0]

_SIM_LIFETIME = 55.0   # rinnova 5s prima dei 60s di scadenza


def _api_request(method: str, path: str, api_key: str, body: dict = None):
    """Helper REST generico — restituisce dict parsed o None."""
    import urllib.request, urllib.error
    url  = f"https://api.cyberwave.com/api/v1{path}"
    data = json.dumps(body or {}).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode()
        logger.warning(f"REST {method} {path}: {e.code} — {body_txt[:200]}")
        return None


def _start_simulation(api_key: str, env_id: str) -> Optional[str]:
    """Avvia simulazione MuJoCo via REST, restituisce simulation_id o None."""
    RUNNING_STATES = {"loading", "running", "pending"}

    # Controlla se c'è già una simulazione attiva (non completed)
    active = _api_request("GET", f"/environments/{env_id}/simulations", api_key)
    sims   = (active or {}).get("active_simulations", [])
    for s in sims:
        status = s.get("status", "")
        if status in RUNNING_STATES:
            sid = s.get("simulation_id") or s.get("id") or "unknown"
            logger.info(f"Simulazione già attiva: {sid}  status={status}")
            return sid
        elif status == "completed":
            logger.info("Simulazione precedente completata — avvio nuova")

    result = _api_request("POST", f"/environments/{env_id}/simulations", api_key, {})
    if result is None:
        return None

    sim    = result.get("simulation", result)
    sid    = sim.get("simulation_id") or sim.get("id")
    status = sim.get("status", "?")
    logger.info(f"Simulazione avviata: id={sid}  status={status}  env={env_id[:8]}...")
    return sid


class RobotController:
    def __init__(self, robot_name: str = "", mode: str = "simulation"):
        self.robot_name     = robot_name or os.getenv("CYBERWAVE_ROBOT_NAME", "so101-mirror")
        self.mode           = mode
        self._client        = None
        self._twin          = None
        self._twin_uuid     = ""
        self._env_id        = ""
        self._simulation_id: Optional[str] = None
        self._sim_start     = 0.0
        self._actual:  Dict[str, float] = {k: 0.0 for k in JOINT_IDS}
        self._commands_sent = 0

    # ------------------------------------------------------------------ #
    #  CONNECT                                                             #
    # ------------------------------------------------------------------ #

    def connect(self):
        if self.mode == "dry_run" or not CYBERWAVE_AVAILABLE:
            self.mode = "dry_run"
            logger.info("DRY RUN — comandi a console")
            return

        api_key = os.getenv("CYBERWAVE_API_KEY")
        env_id  = os.getenv("CYBERWAVE_ENVIRONMENT_ID")
        twin_id = os.getenv("CYBERWAVE_TWIN_ID")

        if not all([api_key, env_id, twin_id]):
            logger.error("Credenziali mancanti nel .env — dry_run")
            self.mode = "dry_run"; return

        self._env_id    = env_id
        self._twin_uuid = twin_id

        logger.info(f"Connessione a env={env_id[:8]}...  twin={twin_id[:8]}...")

        try:
            source       = SOURCE_TYPE_SIM if self.mode == "simulation" else SOURCE_TYPE_EDGE
            self._client = Cyberwave(api_key=api_key, source_type=source, environment_id=env_id)
            # affect() deve combaciare con source_type: 'simulation' per la sim,
            # 'live' per il robot reale. Un mismatch confonde i publisher MQTT.
            self._client.affect("simulation" if self.mode == "simulation" else "live")

            self._twin = self._client.twin(twin_id=twin_id, environment_id=env_id)
            logger.info(f"Twin '{self._twin.name}' (uuid={getattr(self._twin,'uuid','?')[:8]}...) connesso")

            # PERF FIX: il SDK rifà un fetch REST dell'asset (~46KB) a OGNI
            # joints.get()/set() per leggere lo schema joint. A 30fps il
            # controllo diventa inutilizzabile (~6s per comando). Avvolgiamo
            # assets.get() con una cache: lo schema è immutabile nella sessione.
            self._install_asset_cache()

            if self.mode == "simulation":
                self._simulation_id = _start_simulation(api_key, env_id)
                self._sim_start     = time.time()
                if self._simulation_id:
                    logger.info(f"Simulation ID: {self._simulation_id}")
                    self._wait_for_simulation_running(api_key, env_id, timeout=40.0)
                else:
                    logger.warning("Simulazione non avviata — provo comunque MQTT")

            # JointsHandle si auto-connette all'MQTT al primo get/set
            try:
                self._twin.joints.get(timeout=3.0)
            except Exception:
                pass
            logger.info("MQTT connesso. Pronti. ✓")
            logger.info(f"  env:   {env_id}")
            logger.info(f"  twin:  {twin_id}")
            logger.info(f"  sim:   {self._simulation_id}")

        except Exception as e:
            logger.error(f"Connessione fallita: {e}")
            self.mode   = "dry_run"
            self._client = self._twin = None

    def _install_asset_cache(self):
        """Memoizza client.assets.get() — lo schema asset non cambia durante la
        sessione, quindi evitiamo di rifare il fetch REST a ogni comando joint."""
        try:
            assets_mgr = self._client.assets
            original   = assets_mgr.get
            cache: Dict[str, object] = {}

            def cached_get(asset_id, *a, **kw):
                if asset_id not in cache:
                    cache[asset_id] = original(asset_id, *a, **kw)
                return cache[asset_id]

            assets_mgr.get = cached_get
            # Pre-warm: popola la cache subito con l'asset del nostro twin
            aid = getattr(self._twin, "asset_id", None)
            if aid:
                cached_get(aid)
            logger.info("Cache schema asset attiva (no refetch per comando)")
        except Exception as e:
            logger.warning(f"Impossibile installare cache asset: {e}")

    def _wait_for_simulation_running(self, api_key: str, env_id: str, timeout: float = 20.0):
        """Polling finché status diventa 'running' (max timeout secondi)."""
        deadline = time.time() + timeout
        last_status = None
        while time.time() < deadline:
            result = _api_request("GET", f"/environments/{env_id}/simulations", api_key)
            sims   = (result or {}).get("active_simulations", [])
            # Cerca la nostra simulazione o qualsiasi non-completed
            for s in sims:
                sid    = s.get("simulation_id") or s.get("id")
                status = s.get("status", "?")
                if sid == self._simulation_id or status in ("loading", "running"):
                    if status != last_status:
                        logger.info(f"Simulazione {sid[:8]}...: {status}")
                        last_status = status
                    if status == "running":
                        logger.info("Simulazione RUNNING ✓")
                        return
            time.sleep(1.0)
        logger.warning("Timeout attesa simulazione — continuo comunque (potrebbe funzionare uguale)")

    # ------------------------------------------------------------------ #
    #  FEEDBACK                                                            #
    # ------------------------------------------------------------------ #

    def _on_joint_update(self, data: Dict):
        try:
            if not getattr(self, "_fmt_logged", False):
                logger.info(f"[FEEDBACK RAW] {data}")
                self._fmt_logged = True
            # Il feedback MuJoCo ha i joint dentro data["positions"] (dict)
            positions = data.get("positions", data)
            if isinstance(positions, dict):
                for k, v in positions.items():
                    if k in self._actual:
                        self._actual[k] = float(v)
            else:
                # Fallback: prova top-level
                for k, v in data.items():
                    if k in self._actual:
                        self._actual[k] = float(v)
        except Exception as e:
            logger.debug(f"_on_joint_update: {e}")

    # ------------------------------------------------------------------ #
    #  SIMULATION RENEWAL                                                  #
    # ------------------------------------------------------------------ #

    def _renew_simulation(self):
        if self.mode != "simulation":
            return
        if time.time() - self._sim_start < _SIM_LIFETIME:
            return
        api_key = os.getenv("CYBERWAVE_API_KEY")
        logger.info("Rinnovo simulazione...")
        new_id = _start_simulation(api_key, self._env_id)
        if new_id:
            self._simulation_id = new_id
            self._sim_start     = time.time()
            logger.info(f"Simulazione rinnovata: {new_id}")
            # Il server resetta le connessioni MQTT al cambio di stato sim
            # Forza la riconnessione tramite joints.get() che usa attach_topic_listener
            time.sleep(2.0)
            try:
                self._twin.joints.get(timeout=5.0)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  SEND JOINTS (ACT)                                                   #
    # ------------------------------------------------------------------ #

    def send_joints(self, angles: Dict[str, float]):
        if self.mode == "dry_run":
            out = "  ".join(f"{k}:{v:+.1f}°" for k, v in angles.items())
            print(f"[DRY RUN] {out}", flush=True)
            return

        self._renew_simulation()

        try:
            # SDK JointsHandle.set() — usa il canale corretto "joint_update"
            # e converte automaticamente gradi → radianti
            self._twin.joints.set(angles, degrees=True)
            self._commands_sent += 1
            if self._commands_sent <= 3 or self._commands_sent % 20 == 0:
                out = "  ".join(f"{k}:{v:+.1f}°" for k, v in angles.items())
                logger.debug(f"[ACT #{self._commands_sent}] {out}")
        except Exception as e:
            logger.error(f"send_joints: {e}")

    # ------------------------------------------------------------------ #
    #  PERCEIVE / UTILITY                                                  #
    # ------------------------------------------------------------------ #

    def get_state(self) -> Optional[Dict[str, float]]:
        if self.mode == "dry_run":
            return None
        try:
            # JointsHandle.get() restituisce posizioni in radianti — convertiamo in gradi
            rad = self._twin.joints.get()
            return {k: math.degrees(v) for k, v in rad.items()}
        except Exception:
            return self._actual.copy()

    def home(self):
        self.send_joints(dict(zip(JOINT_IDS, HOME_ANGLES)))
        time.sleep(1.0)

    def disconnect(self):
        try:
            if self._twin and self.mode != "dry_run":
                self.home()
            if self._client:
                self._client.disconnect()
        except Exception:
            pass
        logger.info(f"Disconnesso. Comandi totali inviati: {self._commands_sent}")
