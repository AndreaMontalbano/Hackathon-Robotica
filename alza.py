#!/usr/bin/env python3
"""Il braccio si ALZA e basta — SIMULAZIONE. Guarda la dashboard (SIMULATE)."""
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

mask = [False, True, True, True, True, True, False]
chain = Chain.from_urdf_file(str(HERE / "so101.urdf"), base_elements=["base"],
                             active_links_mask=mask)
cw = Cyberwave(); cw.affect("simulation")
arm = cw.twin(twin_id="7d98e176-7ee9-4c3e-84fb-b40e6c94b828")

x, y = 0.14, 0.0          # tengo la chela davanti, fissa
seed = np.zeros(len(chain.links))

print("Alzo il braccio (z: 8 cm -> 28 cm)...")
for z in np.linspace(0.08, 0.28, 40):
    ik = chain.inverse_kinematics([x, y, float(z)], initial_position=seed)
    seed = ik
    arm.set_pose({f"_{j}": float(ik[j]) for j in range(1, 6)})
    time.sleep(0.08)

print("Fatto: braccio alzato.")
