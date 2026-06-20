"""
Operator GUI — red/green status banner + live event log, driven by InterHuman AI.

A thin visual layer on top of OperatorMonitor (src/operator_monitor.py):

  - top banner turns RED   while a critical (BAD) signal is alerting (e.g. stress)
  - top banner turns GREEN when calm / no alert, GRAY while connecting
  - bottom panel streams the same real-time events you saw in the console
    (signal.detected / updated / ended, with probability + rationale)

It consumes the monitor's public, read-only interface only
(on_alert + on_event + active_alerts() + get_state()). It never touches the
robot and never modifies the cloned source — same decoupled contract.

Run:
  python src/operator_gui.py            # camera 0 (phone-as-webcam)
  python src/operator_gui.py 1          # explicit camera index
  INTERHUMAN_CAMERA=1 python src/operator_gui.py

Keys:  Esc = quit   |   F / F11 = toggle fullscreen
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import tkinter as tk
from collections import deque

sys.path.insert(0, os.path.dirname(__file__))
from operator_monitor import OperatorMonitor, DEFAULT_BAD_SIGNALS  # noqa: E402

# palette
RED = "#c0392b"
GREEN = "#1e8449"
GRAY = "#34495e"
LOGBG = "#1b2631"
FG = "#ffffff"
SUB = "#ecf0f1"


def decide(connected: bool, alerts: list[str]) -> tuple[str, str]:
    """Pure: map monitor state to (banner_color, big_text). Unit-testable."""
    if not connected:
        return GRAY, "…"
    if alerts:
        return RED, "⚠ " + "  ".join(s.upper() for s in alerts)
    return GREEN, "OK"


def format_event(evt: dict) -> tuple[str, str]:
    """Pure: (line, tag) for the log panel. tag in {bad, good, meta}."""
    t = evt.get("type", "?")
    d = evt.get("data") or {}
    ts = time.strftime("%H:%M:%S")
    sig = d.get("signal_type")
    bad = sig in DEFAULT_BAD_SIGNALS if sig else False

    if t in ("signal.detected", "signal.updated"):
        prob = d.get("probability", "?")
        rat = (d.get("rationale") or "").strip()
        arrow = "▲" if t == "signal.detected" else "≈"
        line = f"{ts}  {arrow} {sig} ({prob})"
        if rat:
            line += f" — {rat}"
        return line, ("bad" if bad else "good")
    if t == "signal.ended":
        return f"{ts}  ▽ {sig} ended", "meta"
    if t == "transcript.generated":
        txt = (d.get("text") or d.get("transcript") or "").strip()
        return f"{ts}  📝 “{txt}”", "meta"
    if t == "session.ready":
        return f"{ts}  • session ready", "meta"
    if t == "error":
        return f"{ts}  ! error: {d}", "bad"
    return f"{ts}  · {t}", "meta"


class OperatorGUI:
    def __init__(self, camera: int = 0, poll_ms: int = 300):
        self.poll_ms = poll_ms
        self._events: deque = deque(maxlen=500)   # thread-safe enough for append/popleft

        self.monitor = OperatorMonitor(camera=camera, on_event=self._enqueue)

        self.root = tk.Tk()
        self.root.title("Operator State — InterHuman")
        self.root.geometry("820x620")
        self.root.configure(bg=GRAY)

        # connection line
        self.conn = tk.Label(self.root, text="○ connecting", font=("Helvetica", 13),
                             fg=SUB, bg=GRAY, anchor="w")
        self.conn.pack(fill="x", padx=14, pady=(10, 0))

        # banner area (the red/green)
        self.banner = tk.Frame(self.root, bg=GRAY, height=240)
        self.banner.pack(fill="both", expand=True)
        self.banner.pack_propagate(False)

        self.big = tk.Label(self.banner, text="…", font=("Helvetica", 60, "bold"),
                           fg=FG, bg=GRAY)
        self.big.pack(expand=True)

        self.signals = tk.Label(self.banner, text="", font=("Helvetica", 16),
                               fg=SUB, bg=GRAY)
        self.signals.pack(pady=(0, 12))

        # live log panel
        tk.Label(self.root, text="EVENTI LIVE", font=("Helvetica", 11, "bold"),
                 fg=SUB, bg=LOGBG, anchor="w").pack(fill="x")
        logwrap = tk.Frame(self.root, bg=LOGBG)
        logwrap.pack(fill="both", expand=True)
        self.logbox = tk.Text(logwrap, height=12, bg=LOGBG, fg=SUB, bd=0,
                              font=("Menlo", 11), wrap="word",
                              state="disabled", padx=10, pady=6)
        sb = tk.Scrollbar(logwrap, command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.logbox.pack(side="left", fill="both", expand=True)
        self.logbox.tag_configure("bad", foreground="#ff6b6b")
        self.logbox.tag_configure("good", foreground="#51cf66")
        self.logbox.tag_configure("meta", foreground="#95a5a6")

        self._banner_widgets = (self.banner, self.big, self.signals, self.conn)
        self._fullscreen = False
        self.root.bind("<Escape>", lambda e: self._close())
        self.root.bind("f", lambda e: self._toggle_fullscreen())
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # fired from monitor background thread — just buffer, never touch tk here
    def _enqueue(self, evt: dict) -> None:
        self._events.append(evt)

    def _paint_banner(self, bg: str) -> None:
        self.root.configure(bg=bg)
        for w in self._banner_widgets:
            w.configure(bg=bg)

    def _drain_log(self) -> None:
        if not self._events:
            return
        self.logbox.configure(state="normal")
        while self._events:
            try:
                evt = self._events.popleft()
            except IndexError:
                break
            line, tag = format_event(evt)
            self.logbox.insert("end", line + "\n", tag)
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def _update(self) -> None:
        connected = self.monitor.is_connected
        alerts = self.monitor.active_alerts()
        state = self.monitor.get_state()

        bg, big = decide(connected, alerts)
        self._paint_banner(bg)
        self.big.configure(text=big)
        self.conn.configure(text="● connected" if connected else "○ connecting…")
        self.signals.configure(
            text="   ".join(f"{s}:{p}" for s, p in sorted(state.items()))
                 or "(nessun segnale)")

        self._drain_log()
        self.root.after(self.poll_ms, self._update)

    def _toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        self.root.attributes("-fullscreen", self._fullscreen)

    def _close(self) -> None:
        try:
            self.monitor.stop()
        finally:
            self.root.destroy()

    def run(self) -> None:
        if not self.monitor.start():
            self._paint_banner(GRAY)
            self.big.configure(text="NO MONITOR", font=("Helvetica", 36, "bold"))
            self.conn.configure(text="○ disattivato — controlla INTERHUMAN_API_KEY / websocket-client")
        self._update()
        self.root.mainloop()


def _resolve_camera() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else os.getenv("INTERHUMAN_CAMERA", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    OperatorGUI(camera=_resolve_camera()).run()
