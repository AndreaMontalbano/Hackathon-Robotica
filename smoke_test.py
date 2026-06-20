#!/usr/bin/env python3
"""SMOKE TEST — prende l'SO-101 GIA' ESISTENTE nel Default Environment e lo muove (SIMULATE)."""
import os, time
from pathlib import Path

env_file = Path(__file__).parent / ".env"
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

ENV_SLUG = os.environ.get("CYBERWAVE_ENVIRONMENT_ID", "")

# 1) risolvi l'environment dallo slug della URL
env_uuid = None
try:
    for e in cw.environments.list():
        s, n, u = getattr(e, "slug", None), getattr(e, "name", None), getattr(e, "uuid", None)
        print("ENV:", u, "|", s, "|", n)
        if (s and (ENV_SLUG == s or ENV_SLUG.endswith(str(s)))) or n == "Default Environment":
            env_uuid = u
except Exception as ex:
    print("environments.list err:", ex)
print("-> env_uuid:", env_uuid)

# 2) prendi il twin esistente nell'environment
candidates = []
ns = getattr(cw, "twins", None)
if ns is not None:
    print("cw.twins ->", [m for m in dir(ns) if not m.startswith("_")])
    for kw in ({"environment_id": env_uuid}, {}):
        try:
            candidates = list(ns.list(**kw)); break
        except Exception as ex:
            print(f"twins.list({kw}) err:", ex)
for t in candidates:
    print("TWIN:", getattr(t, "uuid", None), "|", getattr(t, "slug", None), "|", getattr(t, "name", None))

target = None
for t in candidates:
    blob = ((getattr(t, "name", "") or "") + (getattr(t, "slug", "") or "")).lower()
    if "101" in blob or "so" in blob:
        target = t; break
if target is None and candidates:
    target = candidates[0]

arm = None
if target is not None:
    arm = cw.twin(twin_id=getattr(target, "uuid", None) or getattr(target, "slug", None))
    print("USO twin:", getattr(target, "name", None))
else:
    for key in ("the-robot-studio/so101", "the-robot-studio/so-101"):
        try:
            arm = cw.twin(key, environment_id=env_uuid); print("creato da asset", key); break
        except Exception as ex:
            print("asset", key, "err:", ex)

if arm is None:
    raise SystemExit("Twin non trovato — l'output sopra mi serve per capire l'API")

print("Giunti:", arm.joints.list())
print("Muovo il giunto base _1... guarda la dashboard (SIMULATE)")
for d in list(range(0, 46, 5)) + list(range(45, -1, -5)):
    arm.joints.set("_1", d, degrees=True); time.sleep(0.2)
print("FATTO. Se si e' mosso, siamo collegati.")
