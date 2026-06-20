#!/usr/bin/env python3
"""Scarica URDF SO-101 + elenca i giunti (per mappare _1.._6) + controlla namespace motion."""
import os, json
from pathlib import Path

HERE = Path(__file__).parent
env_file = HERE / ".env"
for line in env_file.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
import certifi
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

from cyberwave import Cyberwave
cw = Cyberwave()
cw.affect("simulation")
TWIN = "7d98e176-7ee9-4c3e-84fb-b40e6c94b828"
arm = cw.twin(twin_id=TWIN)
print("asset_id:", arm.asset_id)

# --- namespace motion/commands/capabilities (ultima verifica per cartesiano nascosto) ---
for ns in ("motion", "commands"):
    o = getattr(arm, ns, None)
    print(f"arm.{ns} ->", [m for m in dir(o) if not m.startswith('_')] if o is not None else None)

# --- 1) GIUNTI dal modello cinematico ---
print("\n=== GIUNTI (dal get_raw) ===")
raw = cw.twins.get_raw(TWIN)
val = raw.get("value", raw) if isinstance(raw, dict) else raw
joints = val.get("joints") if isinstance(val, dict) else None
if joints:
    for j in joints:
        print(f"  {j.get('name')} | type={j.get('type')} | axis={j.get('axis')} "
              f"| parent={j.get('parent')} -> child={j.get('child')} | limit={j.get('limit')}")
else:
    print("  niente chiave 'joints'. chiavi disponibili:", list(val.keys()) if isinstance(val, dict) else type(val))

# --- 2) scarica URDF ---
print("\n=== URDF ===")
asset = None
for getter in (lambda: cw.assets.get(arm.asset_id),
               lambda: cw.assets.get_raw(arm.asset_id)):
    try:
        asset = getter(); break
    except Exception as e:
        print("  assets.get tentativo fallito:", e)

if asset is not None:
    uf = getattr(asset, "urdf_file", None)
    print("  urdf_file:", repr(uf)[:200])
    out = HERE / "so101.urdf"
    try:
        if isinstance(uf, str) and uf.startswith("http"):
            import requests
            r = requests.get(uf, verify=certifi.where(), timeout=30)
            out.write_bytes(r.content)
            print("  SCARICATO ->", out, f"({len(r.content)} byte)")
        elif callable(getattr(asset, "parse_file", None)):
            data = asset.parse_file()
            out.write_text(data if isinstance(data, str) else str(data))
            print("  SCRITTO via parse_file ->", out)
        else:
            print("  urdf_file non e' un URL diretto; tipo:", type(uf))
    except Exception as e:
        print("  download err:", e)
else:
    print("  asset non recuperato")
