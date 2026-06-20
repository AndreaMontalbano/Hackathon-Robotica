#!/usr/bin/env python3
"""MANO -> BRACCIO (mirroring) — SIMULAZIONE.
La posizione della tua mano (webcam, MediaPipe) guida l'end-effector dell'SO-101;
i gesti FIST/OPEN aprono e chiudono la chela. L'IK fa il resto.

LANCIA con il venv 3.12:
    cd /Users/gianmorotti/cyberwave-mirroring
    source venv/bin/activate
    python hand_control.py
Premi 'q' nella finestra video per uscire. Tieni la dashboard su SIMULATE.
"""
import os, time, numpy as np
from pathlib import Path

HERE = Path(__file__).parent
for line in (HERE / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import cv2, mediapipe as mp
from ikpy.chain import Chain
from cyberwave import Cyberwave

# ---------- braccio + IK ----------
mask = [False, True, True, True, True, True, False]
chain = Chain.from_urdf_file(str(HERE / "so101.urdf"), base_elements=["base"],
                             active_links_mask=mask)
cw = Cyberwave(); cw.affect("simulation")
arm = cw.twin(twin_id="7d98e176-7ee9-4c3e-84fb-b40e6c94b828")

# ---------- spazio di lavoro raggiungibile (metri) ----------
EE_X = 0.16                    # profondita' fissa (avanti)
Y_MIN, Y_MAX = -0.10, 0.10    # sinistra <-> destra
Z_MIN, Z_MAX = 0.10, 0.24     # basso <-> alto
ALPHA = 0.35                  # smoothing (0=lento/stabile, 1=reattivo)

# ---------- gesti (dal vostro Gesture_recognition.py) ----------
def _dist(a, b):
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

def _finger_extended(lm, tip, pip, mcp):
    w = lm[0]
    return _dist(lm[tip], w) > _dist(lm[pip], w) > _dist(lm[mcp], w)

def grip_gesture(lm):
    idx = _finger_extended(lm, 8, 6, 5)
    mid = _finger_extended(lm, 12, 10, 9)
    rng = _finger_extended(lm, 16, 14, 13)
    pky = _finger_extended(lm, 20, 18, 17)
    if idx and mid and rng and pky:
        return "OPEN"
    if not idx and not mid and not rng and not pky:
        return "FIST"
    return None

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
cap = cv2.VideoCapture(0)

target = [EE_X, 0.0, 0.17]
seed = np.zeros(len(chain.links))
grip_val = 1.2                # chela aperta
last_send = 0.0

print("Muovi la mano davanti alla webcam. FIST=chiudi, OPEN=apri. 'q' per uscire.")
with mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7,
                    min_tracking_confidence=0.7) as hands:
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)                 # effetto specchio
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)
        label = "NO HAND"

        if res.multi_hand_landmarks:
            hlm = res.multi_hand_landmarks[0]
            mp_draw.draw_landmarks(frame, hlm, mp_hands.HAND_CONNECTIONS)
            lm = hlm.landmark
            palm = lm[9]                            # centro palmo (MCP medio)

            # posizione mano (0..1) -> bersaglio EE (metri)
            ty = Y_MIN + (1.0 - palm.x) * (Y_MAX - Y_MIN)   # destra schermo -> +y
            tz = Z_MIN + (1.0 - palm.y) * (Z_MAX - Z_MIN)   # mano in alto   -> +z
            # smoothing
            target[1] = (1 - ALPHA) * target[1] + ALPHA * ty
            target[2] = (1 - ALPHA) * target[2] + ALPHA * tz

            g = grip_gesture(lm)
            if g == "OPEN":
                grip_val = 1.2
            elif g == "FIST":
                grip_val = 0.0
            label = g or "MOVE"

        # IK + invio (max ~20 Hz)
        now = time.time()
        if now - last_send > 0.05:
            seed = chain.inverse_kinematics(target, initial_position=seed)
            fk = chain.forward_kinematics(seed)
            err = np.linalg.norm(fk[:3, 3] - np.array(target)) * 1000
            if err < 25:                            # invia solo pose valide
                pose = {f"_{j}": float(seed[j]) for j in range(1, 6)}
                pose["_6"] = float(grip_val)
                arm.set_pose(pose)
            last_send = now

        cv2.putText(frame, f"{label}  y={target[1]:+.2f} z={target[2]:.2f}",
                    (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.imshow("Hand -> Arm", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()
