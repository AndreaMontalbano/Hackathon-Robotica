"""
Test connessione Cyberwave — verifica API key, twin, joint names e movimento.
Run: python demo/test_connection.py
"""

import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

api_key    = os.getenv("CYBERWAVE_API_KEY")
robot_name = os.getenv("CYBERWAVE_ROBOT_NAME", "so101-mirror")

print("=" * 55)
print("  Cyberwave Connection Test")
print("=" * 55)
print(f"\n[1] API Key:    {'✓ (' + api_key[:8] + '...)' if api_key else '✗ MANCANTE'}")
print(f"[2] Robot name: {robot_name}")

if not api_key:
    print("\nERRORE: aggiungi CYBERWAVE_API_KEY al .env")
    sys.exit(1)

# Import SDK
try:
    from cyberwave.client import Cyberwave
    from cyberwave import SOURCE_TYPE_SIM
    print(f"\n[3] SDK: ✓")
except ImportError as e:
    print(f"\n[3] SDK: ✗ {e}")
    sys.exit(1)

# Connessione client
print(f"\n[4] Creazione client (source_type=sim)...")
try:
    client = Cyberwave(api_key=api_key, source_type=SOURCE_TYPE_SIM)
    print(f"    ✓ Client OK")
except Exception as e:
    print(f"    ✗ {e}")
    sys.exit(1)

# Recupero twin
print(f"\n[5] Connessione twin '{robot_name}'...")
try:
    twin = client.twin(asset_key=robot_name)
    print(f"    ✓ Twin OK")
    print(f"    name: {twin.name}")
    print(f"    uuid: {twin.uuid}")
except Exception as e:
    print(f"    ✗ {e}")
    print(f"\n    → Devi creare il twin su cyberwave.com:")
    print(f"      Dashboard → Add Robot → cerca 'the-robot-studio/so101'")
    print(f"      Dagli il nome '{robot_name}'")
    client.disconnect()
    sys.exit(1)

# Joint names
print(f"\n[6] Joint controllabili...")
try:
    joints = twin.get_controllable_joint_names()
    print(f"    ✓ {joints}")
except Exception as e:
    print(f"    ⚠ {e}")

# Feedback loop
print(f"\n[7] Feedback joint (subscribe)...")
received = []
def on_joints(data):
    received.append(data)
    if len(received) == 1:
        print(f"    ✓ Primo dato ricevuto: {data}")
try:
    twin.subscribe_joints(on_joints)
    time.sleep(1.0)
    if not received:
        print(f"    ⚠ Nessun dato in 1s — normale se il robot è fermo")
except Exception as e:
    print(f"    ⚠ {e}")

# Test movimento J1
print(f"\n[8] Movimento test (J1 → 15°)...")
try:
    twin.publish_command("set_joint", {"joint": "1", "value": 15.0})
    print(f"    ✓ Comando inviato — guarda il twin nel dashboard")
    time.sleep(1.5)
    twin.publish_command("set_joint", {"joint": "1", "value": 0.0})
    print(f"    ✓ Ritorno a 0°")
except Exception as e:
    print(f"    ✗ publish_command fallito: {e}")
    print(f"    → Provo formato alternativo...")
    try:
        twin.publish_command("set_joint", {{"1": 15.0}})
        print(f"    ✓ Formato alternativo OK")
    except Exception as e2:
        print(f"    ✗ Anche alternativo fallito: {e2}")
        print(f"    → Chiedi nel Discord qual è il comando corretto per muovere i joint")

print("\n" + "=" * 55)
print("  Fine test. Controlla ✓ e ✗ sopra.")
print("=" * 55)

client.disconnect()
