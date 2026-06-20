#!/usr/bin/env python3
"""GRU / PICK & PLACE — muovendo SOLO l'end-effector.
Dici DOVE prendere (PICK) e DOVE posare (PLACE): il braccio ci arriva con l'IK,
chiude la chela (prende), si sposta, apre (posa). Container non necessario.
Tutto in SIMULAZIONE. Guarda la dashboard (SIMULATE).
"""
import os, time, numpy as np
from pathlib import Path

# ============================================================
#  >>> DICI TU DOVE ANDARE  (coordinate in METRI: x avanti, y lato, z altezza)
PICK     = [0.18, -0.10, 0.10]   # dove "prende" il container
PLACE    = [0.16,  0.08, 0.10]   # dove lo "posa"
APPROACH = 0.07                  # quanto sopra avvicinarsi prima di scendere
HOME     = [0.18,  0.00, 0.18]   # posizione di partenza/riposo
GRIP_OPEN, GRIP_CLOSE = 1.2, 0.0 # apertura/chiusura chela (se invertiti li scambiamo)
# ============================================================

HERE = Path(__file__).parent
for line in (HERE / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

from ikpy.chain import Chain
from cyberwave import Cyberwave

mask = [False, True, True, True, True, True, False]
chain = Chain.from_urdf_file(str(HERE / "so101.urdf"), base_elements=["base"],
                             active_links_mask=mask)
cw = Cyberwave(); cw.affect("simulation")
arm = cw.twin(twin_id="7d98e176-7ee9-4c3e-84fb-b40e6c94b828")

def send(ik):
    arm.set_pose({f"_{j}": float(ik[j]) for j in range(1, 6)})

def glide(p_from, p_to, n, seed, label=""):
    """Sposta l'end-effector in linea retta da p_from a p_to in n passetti."""
    for k in range(1, n + 1):
        t = k / n
        p = [p_from[i] + (p_to[i] - p_from[i]) * t for i in range(3)]
        seed = chain.inverse_kinematics(p, initial_position=seed)
        send(seed); time.sleep(0.05)
    fk = chain.forward_kinematics(seed)
    err = np.linalg.norm(fk[:3, 3] - np.array(p_to)) * 1000
    print(f"  -> {label} {p_to}  (errore {err:.0f} mm)")
    return seed, list(p_to)

def grip(val, label):
    arm.set_pose({"_6": float(val)}); print(f"  -> chela {label}")
    time.sleep(0.7)

seed = np.zeros(len(chain.links))
pick_up  = [PICK[0],  PICK[1],  PICK[2]  + APPROACH]
place_up = [PLACE[0], PLACE[1], PLACE[2] + APPROACH]

print("GRU: pick & place (solo end-effector)")
seed, pos = glide(HOME,    HOME,     1,  seed, "home")
grip(GRIP_OPEN, "aperta")
seed, pos = glide(pos,     pick_up,  25, seed, "sopra il PICK")
seed, pos = glide(pos,     PICK,     15, seed, "scendo sul PICK")
grip(GRIP_CLOSE, "chiusa (preso!)")
seed, pos = glide(pos,     pick_up,  15, seed, "risalgo col carico")
seed, pos = glide(pos,     place_up, 30, seed, "sopra il PLACE")
seed, pos = glide(pos,     PLACE,    15, seed, "scendo sul PLACE")
grip(GRIP_OPEN, "aperta (posato!)")
seed, pos = glide(pos,     place_up, 15, seed, "risalgo")
seed, pos = glide(pos,     HOME,     25, seed, "torno a home")
print("FATTO: container spostato dal PICK al PLACE.")
