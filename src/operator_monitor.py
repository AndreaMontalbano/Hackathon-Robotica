"""
Operator monitor — InterHuman AI realtime sentiment/affect analysis.

Read-only safety overlay for the SO-101 gesture teleoperation pipeline.

The webcam frames the operator's face while they teleoperate the arm with hand
gestures. This module streams ~2 s self-contained video mini-clips to the
InterHuman AI realtime WebSocket, receives `signal.*` events (12 affect
categories with high|medium|low probability), and keeps the live operator
state. When a *critical* (BAD) signal becomes active at `high` probability it
fires an alert — nothing else.

Design contract (one-way, decoupled):
  - NEVER imports or touches robot_controller / command_dispatcher.
  - NEVER influences arm movement. Gesture pipeline stays 100 % intact.
  - Output is alert + read-only state only.

Interface:
  OperatorMonitor.start() / .stop()
  OperatorMonitor.push_frame(frame_bgr)          # shared-camera mode
  OperatorMonitor.get_state() -> dict[str, str]  # {signal_type: probability}
  OperatorMonitor.on_alert: Callable[[str, str, str], None]   # (type, prob, rationale)

Camera modes:
  camera=None  → SHARED: monitor owns no capture; main loop feeds frames via
                 push_frame() (one webcam shared between face + hand).
  camera=<int> → DEDICATED: monitor opens its own cv2.VideoCapture(index)
                 (a second webcam pointed at the face).

InterHuman realtime spec (Beta — may change):
  wss://api.interhuman.ai/v0/real-time/analyze
  Auth: header `Authorization: Bearer <key>` (WS fallback: Sec-WebSocket-Protocol)
  SEND: binary self-contained video segments (<=32 MB; mp4/webm/mov/mkv/ts)
        optional JSON config frame {synthesis_frequency, synthesis_prompt}
  RECV (JSON, field `type`):
        session.ready | signal.detected | signal.updated | signal.ended
        synthesis.generated | transcript.generated | error | coverage.dropped
        signal.* data: {signal_type, start/end, probability, rationale}
        probability in {high, medium, low}; times = cumulative session seconds.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

# --- guarded heavy/optional imports ----------------------------------------
# Kept lazy so the pure alert/state logic stays importable & unit-testable
# without cv2 or websocket-client installed.
try:
    import cv2
    _CV2_OK = True
except ImportError:  # pragma: no cover
    cv2 = None
    _CV2_OK = False

try:
    import websocket  # websocket-client (sync API + threads)
    _WS_OK = True
except ImportError:  # pragma: no cover
    websocket = None
    _WS_OK = False


WS_URL = "wss://api.interhuman.ai/v0/real-time/analyze"

# The 12 InterHuman signal types
ALL_SIGNALS = (
    "agreement", "confidence", "confusion", "disagreement", "disengagement",
    "engagement", "frustration", "hesitation", "interest", "skepticism",
    "stress", "uncertainty",
)

# Critical states that raise a safety alert
DEFAULT_BAD_SIGNALS = frozenset({
    "stress", "frustration", "confusion", "hesitation",
    "uncertainty", "disengagement",
})

_MAX_SEGMENT_BYTES = 32 * 1024 * 1024  # 33554432 — server default, overwritten by session.ready


def _default_on_alert(signal_type: str, probability: str, rationale: str) -> None:
    msg = f"⚠️  OPERATOR ALERT: {signal_type.upper()} ({probability})"
    if rationale:
        msg += f" — {rationale}"
    logging.getLogger("operator_monitor").warning(msg)


class OperatorMonitor:
    """Streams operator video to InterHuman AI and surfaces affect alerts.

    Runs entirely in background threads; start()/stop() are non-blocking and
    the arm control loop is never blocked or coupled.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        ws_url: str = WS_URL,
        camera: Optional[int] = None,
        chunk_seconds: float = 2.0,
        max_width: int = 640,
        bad_signals: Iterable[str] = DEFAULT_BAD_SIGNALS,
        alert_probability: str = "high",
        on_alert: Optional[Callable[[str, str, str], None]] = None,
        on_event: Optional[Callable[[dict], None]] = None,
        synthesis_frequency: Optional[str] = None,
        synthesis_prompt: Optional[str] = None,
        reconnect: bool = True,
        max_backoff: float = 30.0,
        logger: Optional[logging.Logger] = None,
    ):
        self._api_key = api_key or os.getenv("INTERHUMAN_API_KEY")
        self._ws_url = ws_url
        self._camera = camera                       # None => shared, int => dedicated
        self._chunk_seconds = max(0.5, float(chunk_seconds))
        self._max_width = int(max_width) if max_width else 0
        self._bad = frozenset(s.lower() for s in bad_signals)
        self._alert_prob = alert_probability.lower()
        self.on_alert: Callable[[str, str, str], None] = on_alert or _default_on_alert
        # Optional firehose: called with the raw event dict for EVERY event
        # (session.ready, signal.*, transcript.*, error, ...). Read-only — for
        # live log panels / debugging. Never influences control.
        self.on_event: Optional[Callable[[dict], None]] = on_event
        self._synthesis_frequency = synthesis_frequency
        self._synthesis_prompt = synthesis_prompt
        self._reconnect = reconnect
        self._max_backoff = max_backoff
        self.log = logger or logging.getLogger("operator_monitor")

        # live state
        self._active: Dict[str, str] = {}           # signal_type -> probability
        self._alerted: set[str] = set()             # bad signals already alerted at threshold
        self._last_transcript: str = ""
        self._lock = threading.Lock()

        # shared-camera frame buffer: (timestamp, frame)
        self._buf: Deque[Tuple[float, "any"]] = deque(maxlen=600)

        # threads / lifecycle
        self._ws = None
        self._cap = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._supervisor: Optional[threading.Thread] = None
        self._receiver: Optional[threading.Thread] = None
        self._max_segment_bytes = _MAX_SEGMENT_BYTES
        self._chunks_sent = 0

    # ------------------------------------------------------------------ #
    #  PUBLIC API                                                         #
    # ------------------------------------------------------------------ #

    def start(self) -> bool:
        """Start background streaming. Non-blocking. Returns False if it cannot
        even attempt to run (missing deps / key) — caller should log & skip."""
        if not _WS_OK:
            self.log.warning("websocket-client non installato — monitor disattivato "
                             "(pip install websocket-client)")
            return False
        if not _CV2_OK:
            self.log.warning("cv2 non disponibile — monitor disattivato")
            return False
        if not self._api_key:
            self.log.warning("INTERHUMAN_API_KEY mancante nel .env — monitor disattivato")
            return False

        self._stop.clear()
        self._supervisor = threading.Thread(target=self._supervise, name="ih-supervisor",
                                             daemon=True)
        self._supervisor.start()
        self.log.info("OperatorMonitor avviato (camera=%s, chunk=%.1fs)",
                      "shared" if self._camera is None else self._camera,
                      self._chunk_seconds)
        return True

    def stop(self) -> None:
        self._stop.set()
        self._connected.clear()
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        for t in (self._receiver, self._supervisor):
            if t is not None and t.is_alive():
                t.join(timeout=2.0)
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self.log.info("OperatorMonitor fermato. Chunk inviati: %d", self._chunks_sent)

    def push_frame(self, frame_bgr) -> None:
        """Feed a webcam frame (shared-camera mode). No-op in dedicated mode."""
        if self._camera is not None or self._stop.is_set():
            return
        # store a copy so the main loop can keep mutating its frame
        self._buf.append((time.time(), frame_bgr.copy()))

    def get_state(self) -> Dict[str, str]:
        """Read-only snapshot of currently active signals -> probability."""
        with self._lock:
            return dict(self._active)

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def bad_signals(self) -> frozenset:
        return self._bad

    def active_alerts(self) -> List[str]:
        """Currently-active BAD signals at/above the alert threshold."""
        with self._lock:
            return [s for s, p in self._active.items()
                    if s in self._bad and p == self._alert_prob]

    @property
    def last_transcript(self) -> str:
        with self._lock:
            return self._last_transcript

    def format_state(self) -> str:
        """Compact human string, e.g. '🔴 STRESS(high)  🟢 ENGAGEMENT(high)'."""
        with self._lock:
            items = sorted(self._active.items())
        out = []
        for sig, prob in items:
            dot = "🔴" if sig in self._bad else "🟢"
            out.append(f"{dot} {sig.upper()}({prob})")
        return "  ".join(out)

    # ------------------------------------------------------------------ #
    #  EVENT HANDLING  (pure-ish — unit-testable without network)         #
    # ------------------------------------------------------------------ #

    def _handle_event(self, evt: dict) -> None:
        etype = evt.get("type")
        data = evt.get("data") or {}

        # firehose hook (live log panels / debug) — must never break handling
        if self.on_event is not None:
            try:
                self.on_event(evt)
            except Exception as e:
                self.log.debug("on_event callback raised: %s", e)

        if etype == "session.ready":
            self._max_segment_bytes = int(data.get("max_segment_size_bytes",
                                                    self._max_segment_bytes))
            self.log.info("InterHuman session.ready (max_segment=%d bytes)",
                          self._max_segment_bytes)
            return

        if etype in ("signal.detected", "signal.updated"):
            sig = data.get("signal_type")
            prob = (data.get("probability") or "").lower()
            if not sig:
                return
            with self._lock:
                self._active[sig] = prob
            self._maybe_alert(sig, prob, data.get("rationale", "") or "")
            return

        if etype == "signal.ended":
            sig = data.get("signal_type")
            if not sig:
                return
            with self._lock:
                self._active.pop(sig, None)
            self._alerted.discard(sig)
            return

        if etype == "transcript.generated":
            text = data.get("text") or data.get("transcript") or ""
            if text:
                with self._lock:
                    self._last_transcript = text
            return

        if etype == "error":
            self.log.warning("InterHuman error: %s", data)
            return

        if etype == "coverage.dropped":
            self.log.debug("InterHuman coverage.dropped: %s", data)
            return

        # synthesis.generated and anything else: ignore (we only care about signals)

    def _maybe_alert(self, sig: str, prob: str, rationale: str) -> None:
        if sig not in self._bad:
            return
        if prob == self._alert_prob:
            # de-dupe: fire once per escalation, re-arm only after it drops/ends
            if sig not in self._alerted:
                self._alerted.add(sig)
                try:
                    self.on_alert(sig, prob, rationale)
                except Exception as e:  # never let a bad callback kill the thread
                    self.log.error("on_alert callback raised: %s", e)
        else:
            # dropped below threshold — allow it to re-alert if it climbs again
            self._alerted.discard(sig)

    # ------------------------------------------------------------------ #
    #  CONNECTION SUPERVISOR  (reconnect loop)                            #
    # ------------------------------------------------------------------ #

    def _supervise(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._connect()
                backoff = 1.0  # reset after a clean connect
                self._sender_loop()  # blocks until disconnect / stop
            except Exception as e:
                if not self._stop.is_set():
                    self.log.warning("Monitor connessione persa: %s", e)
            finally:
                self._connected.clear()
                self._teardown_ws()

            if self._stop.is_set() or not self._reconnect:
                break
            self.log.info("Riconnessione monitor tra %.0fs...", backoff)
            self._stop.wait(backoff)
            backoff = min(self._max_backoff, backoff * 2)

    def _connect(self) -> None:
        header = [f"Authorization: Bearer {self._api_key}"]
        # Fallback per WS senza header custom: la key può viaggiare nel
        # Sec-WebSocket-Protocol (subprotocols=[f"bearer.{key}"]). Header preferito.
        self._ws = websocket.create_connection(
            self._ws_url,
            header=header,
            enable_multithread=True,
            timeout=30,
        )
        self._connected.set()
        self.log.info("InterHuman WS connesso: %s", self._ws_url)

        # optional config frame (synthesis only — does not affect signals)
        if self._synthesis_frequency or self._synthesis_prompt:
            cfg = {}
            if self._synthesis_frequency:
                cfg["synthesis_frequency"] = self._synthesis_frequency
            if self._synthesis_prompt:
                cfg["synthesis_prompt"] = self._synthesis_prompt
            try:
                self._ws.send(json.dumps(cfg))
            except Exception as e:
                self.log.debug("config frame non inviato: %s", e)

        # dedicated camera: open our own capture
        if self._camera is not None:
            self._cap = cv2.VideoCapture(self._camera)
            if not self._cap.isOpened():
                raise RuntimeError(f"camera dedicata {self._camera} non apribile")

        # receiver thread bound to this connection
        self._receiver = threading.Thread(target=self._receiver_loop,
                                           name="ih-receiver", daemon=True)
        self._receiver.start()

    def _teardown_ws(self) -> None:
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        self._ws = None
        if self._camera is not None and self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    # ------------------------------------------------------------------ #
    #  RECEIVER                                                           #
    # ------------------------------------------------------------------ #

    def _receiver_loop(self) -> None:
        ws = self._ws
        while not self._stop.is_set() and ws is not None:
            try:
                msg = ws.recv()
            except Exception:
                break
            if not msg:
                break
            if isinstance(msg, (bytes, bytearray)):
                continue  # server speaks JSON text; ignore stray binary
            try:
                evt = json.loads(msg)
            except (ValueError, TypeError):
                continue
            self._handle_event(evt)
        self._connected.clear()

    # ------------------------------------------------------------------ #
    #  SENDER                                                             #
    # ------------------------------------------------------------------ #

    def _sender_loop(self) -> None:
        while not self._stop.is_set() and self._connected.is_set():
            frames, fps = self._next_chunk()
            if not frames:
                continue
            data = self._encode_chunk(frames, fps)
            if not data:
                continue
            if len(data) > self._max_segment_bytes:
                self.log.warning("chunk %d byte > limite %d — scartato",
                                 len(data), self._max_segment_bytes)
                continue
            try:
                self._ws.send_binary(data)
                self._chunks_sent += 1
            except Exception as e:
                self.log.warning("send_binary fallita: %s", e)
                break  # supervisor will reconnect

    def _next_chunk(self) -> Tuple[List, float]:
        """Collect ~chunk_seconds of frames. Returns (frames, fps)."""
        if self._camera is None:
            # shared mode: wait the window, then drain whatever main pushed
            self._stop.wait(self._chunk_seconds)
            return self._drain_buffer()

        # dedicated mode: pull from our own capture
        frames: List = []
        t0 = time.time()
        while (time.time() - t0) < self._chunk_seconds and not self._stop.is_set():
            ok, fr = self._cap.read()
            if ok:
                frames.append(fr)
        elapsed = max(1e-3, time.time() - t0)
        fps = min(60.0, max(1.0, len(frames) / elapsed))
        return frames, fps

    def _drain_buffer(self) -> Tuple[List, float]:
        items: List[Tuple[float, "any"]] = []
        while self._buf:
            try:
                items.append(self._buf.popleft())
            except IndexError:
                break
        if len(items) < 2:
            return [], 1.0
        span = max(1e-3, items[-1][0] - items[0][0])
        fps = min(60.0, max(1.0, len(items) / span))
        return [f for _, f in items], fps

    def _encode_chunk(self, frames: List, fps: float) -> Optional[bytes]:
        if not frames:
            return None
        h, w = frames[0].shape[:2]
        scale = 1.0
        if self._max_width and w > self._max_width:
            scale = self._max_width / float(w)
            w, h = int(w * scale), int(h * scale)

        path = os.path.join(tempfile.gettempdir(),
                            f"ih_chunk_{threading.get_ident()}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(path, fourcc, float(fps), (w, h))
        if not vw.isOpened():
            self.log.debug("VideoWriter non apribile")
            return None
        try:
            for fr in frames:
                if scale != 1.0:
                    fr = cv2.resize(fr, (w, h))
                vw.write(fr)
        finally:
            vw.release()
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError:
            return None
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


def _load_yaml_section(path: str, section: str = "operator_monitor") -> dict:
    """Read an optional config section, READ-ONLY. Returns {} if absent."""
    try:
        import yaml
        with open(path) as fh:
            cfg = yaml.safe_load(fh) or {}
        return cfg.get(section, {}) or {}
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
#  Standalone runner:  python src/operator_monitor.py [camera_index]           #
#  Streams the operator's webcam to InterHuman and prints live state + alerts. #
#                                                                              #
#  Config priority:  CLI arg > env (INTERHUMAN_CAMERA / _CHUNK_SECONDS) >      #
#                    config/so101.yaml:operator_monitor (read-only) > defaults #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    here = os.path.dirname(__file__)
    cfg = _load_yaml_section(os.path.join(here, "..", "config", "so101.yaml"))

    # camera: standalone has no hand-loop feeding frames, so "same"/None becomes
    # a real dedicated index (default 0). Override via CLI arg or env.
    raw_cam = (sys.argv[1] if len(sys.argv) > 1
               else os.getenv("INTERHUMAN_CAMERA", cfg.get("camera", 0)))
    try:
        cam = int(raw_cam)
    except (TypeError, ValueError):
        cam = 0  # "same"/None -> 0 in standalone mode

    chunk = float(os.getenv("INTERHUMAN_CHUNK_SECONDS",
                            cfg.get("chunk_seconds", 2.0)))

    mon = OperatorMonitor(
        camera=cam,
        chunk_seconds=chunk,
        max_width=int(cfg.get("max_width", 640)),
        bad_signals=cfg.get("bad_signals", DEFAULT_BAD_SIGNALS),
        alert_probability=cfg.get("alert_probability", "high"),
        synthesis_frequency=cfg.get("synthesis_frequency") or None,
        synthesis_prompt=cfg.get("synthesis_prompt") or None,
    )
    if not mon.start():
        sys.exit(1)
    print(f"Streaming operatore (cam {cam}) → InterHuman. Ctrl-C per uscire.")
    try:
        while True:
            time.sleep(2.0)
            state = mon.format_state() or "(nessun segnale)"
            print(f"[{'●' if mon.is_connected else '○'}] {state}")
    except KeyboardInterrupt:
        pass
    finally:
        mon.stop()
