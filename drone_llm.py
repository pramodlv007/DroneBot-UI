from pymavlink import mavutil
import requests
import time
import json

PORT = "COM10"
BAUD = 57600

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3"

print("Connecting...")
master = mavutil.mavlink_connection(PORT, baud=BAUD)
master.wait_heartbeat()
print("Connected!")

latest = {}

def send_to_llm(data):
    prompt = f"""
You are analyzing drone telemetry.

Tell me:
- Is the drone stable?
- Any issues?
- Battery status?

Data:
{json.dumps(data, indent=2)}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    print("\nLLM RESPONSE:")
    print(response.json()["response"])


last_send = time.time()

while True:
    msg = master.recv_match(blocking=True)

    if not msg:
        continue

    t = msg.get_type()

    if t == "SYS_STATUS":
        latest["battery_voltage"] = msg.voltage_battery / 1000.0
        latest["battery_remaining"] = msg.battery_remaining

    elif t == "ATTITUDE":
        latest["roll"] = msg.roll
        latest["pitch"] = msg.pitch
        latest["yaw"] = msg.yaw

    elif t == "GLOBAL_POSITION_INT":
        latest["altitude"] = msg.relative_alt / 1000.0

    # Send every 5 seconds
    if time.time() - last_send > 5:
        print("\nTelemetry:", latest)
        send_to_llm(latest)
        last_send = time.time()