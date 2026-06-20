"""
Diagnostic — times each step of the Cyberwave live (real robot) connection
so we can see exactly which call blocks. Run:

    python demo/diag_live.py
"""

import os, sys, time, logging
from dotenv import load_dotenv

# Verbose SDK logging so we see MQTT broker host/port and every step
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

load_dotenv()

API_KEY = os.getenv("CYBERWAVE_API_KEY")
ENV_ID  = os.getenv("CYBERWAVE_ENVIRONMENT_ID")
TWIN_ID = os.getenv("CYBERWAVE_TWIN_ID")

print(f"\n=== CONFIG ===")
print(f"  api_key:  {API_KEY[:12]}...{API_KEY[-6:] if API_KEY else None}")
print(f"  env_id:   {ENV_ID}")
print(f"  twin_id:  {TWIN_ID}\n")


def step(name, fn):
    print(f"\n>>> {name} ...", flush=True)
    t0 = time.time()
    try:
        result = fn()
        print(f"<<< {name} OK in {time.time()-t0:.2f}s", flush=True)
        return result
    except Exception as e:
        print(f"!!! {name} FAILED in {time.time()-t0:.2f}s: {type(e).__name__}: {e}", flush=True)
        return None


from cyberwave.client import Cyberwave
from cyberwave import SOURCE_TYPE_EDGE

client = step("1. Cyberwave(constructor, source_type=edge)",
              lambda: Cyberwave(api_key=API_KEY, source_type=SOURCE_TYPE_EDGE, environment_id=ENV_ID))
if client is None:
    sys.exit(1)

step("2. affect('live')", lambda: client.affect("live"))

twin = step("3. client.twin(twin_id=...)  [REST fetch]",
            lambda: client.twin(twin_id=TWIN_ID, environment_id=ENV_ID))
if twin is None:
    print("\nTwin fetch failed — check twin_id / env_id / network.")
    sys.exit(1)

print(f"\n  Twin name: {getattr(twin, 'name', '?')}")
print(f"  Twin uuid: {getattr(twin, 'uuid', '?')}")

# This is the call that hangs in main.py — joints.get triggers MQTT connect
step("4. twin.joints.list()  [controllable joints, REST]",
     lambda: twin.joints.list())

step("5. twin.joints.get(timeout=3.0)  [MQTT connect + first read]",
     lambda: twin.joints.get(timeout=3.0))

step("6. twin.joints.set({'_1': 0.0}, degrees=True)  [publish a command]",
     lambda: twin.joints.set({"_1": 0.0}, degrees=True))

print("\n=== DONE. All steps attempted. ===")
print("Note which step number blocked or failed.\n")
client.disconnect()
