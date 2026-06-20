# Operator Monitor — InterHuman AI (safety alerts only)

Real-time affect/sentiment monitoring of the **operator** while they teleoperate
the SO-101 with hand gestures. The webcam already frames the person; this module
streams short video clips to the [InterHuman AI](https://interhuman.ai) realtime
API, reads back affect signals (stress, confusion, frustration, …) and raises an
**alert** when a critical state hits `high` probability.

> **Read-only, decoupled, alert-only.** It never touches `robot_controller`,
> never modifies a joint command, never blocks the arm loop. The gesture control
> pipeline (`main.py` and the cloned `src/*.py`) is **left completely unchanged** —
> this lives entirely in `src/operator_monitor.py` plus these companion files.

---

## What it does

```
operator face (webcam)
        │  ~2 s self-contained mp4 mini-clips
        ▼
InterHuman AI realtime WebSocket   wss://api.interhuman.ai/v0/real-time/analyze
        │  signal.detected / signal.updated / signal.ended  (JSON events)
        ▼
OperatorMonitor   ── get_state() ──►  live {signal_type: high|medium|low}
        │
        └── BAD signal @ high ──►  on_alert(signal_type, probability, rationale)
                                   (default: ⚠️ log line)
```

**Signals (12):** agreement, confidence, confusion, disagreement, disengagement,
engagement, frustration, hesitation, interest, skepticism, stress, uncertainty.

**Critical (BAD) → trigger alert:** `stress, frustration, confusion, hesitation,
uncertainty, disengagement` — but only when `probability == high`.

The video carries audio; InterHuman runs ASR on it (`transcript.generated`), so
no separate text input is sent.

---

## Setup

Use **Python 3.12** (mediapipe doesn't run on 3.13). The project's Anaconda 3.12
already has `opencv`, `mediapipe`, `cyberwave`, `numpy`, `pyyaml`, `python-dotenv`.

```bash
# 1. install the one extra dependency
pip install -r requirements-monitor.txt          # websocket-client

# 2. add your API key to .env (additive, doesn't overwrite .env.example)
cat .env.monitor.example >> .env
#    then edit INTERHUMAN_API_KEY=...
```

---

## Run it (standalone, in parallel with the arm)

It runs as its **own process** next to `python src/main.py`. No flag, no change
to `main.py`:

```bash
# default camera 0
python src/operator_monitor.py

# explicit camera index (e.g. a second webcam pointed at the face)
python src/operator_monitor.py 1
```

You'll see live state and alerts on the console:

```
INFO | OperatorMonitor avviato (camera=0, chunk=2.0s)
INFO | InterHuman WS connesso: wss://api.interhuman.ai/v0/real-time/analyze
INFO | InterHuman session.ready (max_segment=33554432 bytes)
[●] 🟢 ENGAGEMENT(high)  🟢 CONFIDENCE(medium)
[●] 🔴 STRESS(high)
WARNING | ⚠️  OPERATOR ALERT: STRESS (high) — sustained tension in voice and brow
```

`●` = connected, `○` = reconnecting.

---

## Camera: one webcam or two?

- **Two webcams (recommended for clarity):** point a second cam at the face and
  pass its index — `python src/operator_monitor.py 1`. The hand-gesture cam in
  `main.py` is untouched.
- **One shared webcam:** the same frame contains face + hand. Run the monitor on
  camera `0` as well; OpenCV can usually open the same physical device from two
  processes on macOS, but if it can't, use two cameras. (A truly *shared single
  capture* would require feeding frames in-process, which means editing `main.py`
  — intentionally **not** done here. The class supports it via `push_frame()` /
  `camera=None` if you ever wire it in yourself.)

### Optional config (no source edits required)

`operator_monitor.py` reads an **optional** `operator_monitor:` section from
`config/so101.yaml` *read-only*. It is not there by default; add it yourself if
you want to override defaults:

```yaml
operator_monitor:
  camera: 0                # standalone: dedicated cam index
  chunk_seconds: 2.0       # mini-clip length sent per segment
  max_width: 640           # downscale before upload (bandwidth)
  alert_probability: high  # threshold that fires an alert
  bad_signals: [stress, frustration, confusion, hesitation, uncertainty, disengagement]
  synthesis_frequency:     # null | low | medium | high  (optional, signal-independent)
```

Env vars override the file: `INTERHUMAN_CAMERA`, `INTERHUMAN_CHUNK_SECONDS`.

---

## Interface contract

```python
from operator_monitor import OperatorMonitor

mon = OperatorMonitor(camera=1, on_alert=my_handler)   # api_key from INTERHUMAN_API_KEY
mon.start()                       # non-blocking, background threads
state = mon.get_state()           # {'stress': 'high', ...}  — read-only snapshot
alerts = mon.active_alerts()      # ['stress']  — BAD signals at threshold
mon.stop()
```

- `on_alert: Callable[[str, str, str], None]` → `(signal_type, probability, rationale)`
- **No reverse dependency on the robot.** Fully decoupled, one-way.
- Auto-reconnects with backoff if the Beta WebSocket drops.

---

## How to test

**1. Logic test, no camera / no network** (validates the event → state → alert
state machine):

```bash
python - <<'PY'
import sys; sys.path.insert(0, "src")
from operator_monitor import OperatorMonitor
fired = []
m = OperatorMonitor(api_key="x", on_alert=lambda *a: fired.append(a))
m._handle_event({"type":"signal.detected","data":{"signal_type":"stress","probability":"high","rationale":"r"}})
m._handle_event({"type":"signal.detected","data":{"signal_type":"engagement","probability":"high"}})
assert m.get_state() == {"stress":"high","engagement":"high"}
assert m.active_alerts() == ["stress"]            # only BAD@high
assert fired == [("stress","high","r")]           # alert fired once
m._handle_event({"type":"signal.detected","data":{"signal_type":"stress","probability":"high"}})
assert len(fired) == 1                              # de-duped, no spam
m._handle_event({"type":"signal.ended","data":{"signal_type":"stress"}})
assert "stress" not in m.get_state()               # cleared + re-armed
print("OK — state machine + alert dedupe verified")
PY
```

**2. Live test** — `pip install -r requirements-monitor.txt`, set
`INTERHUMAN_API_KEY`, run `python src/operator_monitor.py`, look into the camera
and act stressed/confused; watch `🔴` signals and the `⚠️ OPERATOR ALERT` line.

**3. Together with the arm** — two terminals:

```bash
# terminal 1 — arm (unchanged)
python src/main.py --mode dry_run --debug

# terminal 2 — operator monitor
python src/operator_monitor.py
```

---

## Notes / limits

- InterHuman realtime is **Beta** — event shapes may change; the receiver ignores
  unknown event types and malformed JSON instead of crashing.
- `probability` is bucketed (`high|medium|low`), not a 0–1 score.
- `INTERHUMAN_API_KEY` lives in `.env` only — never hardcode or commit it.
