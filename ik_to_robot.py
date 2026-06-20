#!/usr/bin/env python3
"""IK -> ROBOT: per una serie di punti xyz calcola gli angoli (_1.._5) e li manda
al twin SO-101 in SIMULAZIONE. Guarda la dashboard: il braccio salta tra i punti."""
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

from ikpy.chain import Chain
from cyberwave import Cyberwave

# catena IK: giunto 6 (chela) escluso dal posizionamento
mask = [False, True, True, True, True, True, False]
chain = Chain.from_urdf_file(str(HERE / "so101.urdf"), base_elements=["base"],
                             active_links_mask=mask)

cw = Cyberwave(); cw.affect("simulation")
arm = cw.twin(twin_id="7d98e176-7ee9-4c3e-84fb-b40e6c94b828")

# punti di prova (metri) — la chela deve raggiungerli
targets = [
    [0.18, 0.00, 0.15],
    [0.18, 0.10, 0.15],
    [0.18, -0.10, 0.15],
    [0.15, 0.00, 0.25],
    [0.20, 0.00, 0.08],
    [0.18, 0.00, 0.15],
]

prev = np.zeros(len(chain.links))
for tgt in targets:
    ik = chain.inverse_kinematics(tgt, initial_position=prev)
    prev = ik
    fk = chain.forward_kinematics(ik)
    err = float(np.linalg.norm(fk[:3, 3] - np.array(tgt))) * 1000
    angles = {f"_{i}": float(ik[i]) for i in range(1, 6)}   # radianti
    deg = {k: round(np.degrees(v), 1) for k, v in angles.items()}
    print(f"target {tgt}  err={err:.1f}mm  ->  {deg}")
    arm.set_pose(angles)        # set_pose = spazio-giunti, radianti (degrees=False default)
    time.sleep(1.8)

print("FATTO. Il braccio dovrebbe aver toccato tutti i punti.")
