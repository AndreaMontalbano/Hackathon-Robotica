#!/usr/bin/env python3
"""PROVA IK: carica la catena dall'URDF, dato un punto xyz calcola gli angoli
dei giunti _1.._5, verifica con la cinematica diretta l'errore, e (se OK) li
manda al twin SO-101 in SIMULAZIONE."""
import os, numpy as np
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

# carica la catena. Escludo dall'IK il giunto 6 (chela) -> lo controlla il pinch.
chain = Chain.from_urdf_file(str(HERE / "so101.urdf"), base_elements=["base"])
print("=== CATENA IK (link / attivo) ===")
for i, l in enumerate(chain.links):
    print(f"  [{i}] {l.name:20s} {'ATTIVO' if chain.active_links_mask[i] else 'fisso'}")

# punto target di prova in METRI (davanti e sopra la base)
target = [0.18, 0.00, 0.15]
ik = chain.inverse_kinematics(target)
print("\nAngoli IK (rad):", np.round(ik, 3))

fk = chain.forward_kinematics(ik)
pos = fk[:3, 3]
err = float(np.linalg.norm(pos - np.array(target)))
print(f"Chela arriva a: {np.round(pos,3)}  | target: {target}  | errore: {err*1000:.1f} mm")

# estrai gli angoli dei giunti attivi mappandoli ai nomi del link/joint
print("\n=== angoli per giunto ===")
active = [(l.name, ang) for l, ang, m in zip(chain.links, ik, chain.active_links_mask) if m]
for name, ang in active:
    print(f"  link '{name}': {np.degrees(ang):.1f} deg")

print("\n(se l'errore e' piccolo, l'IK funziona: prossimo step lo colleghiamo al twin)")
