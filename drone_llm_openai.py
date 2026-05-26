from pymavlink import mavutil
from openai import OpenAI
from dotenv import load_dotenv
import time
import json
import math
import socket

load_dotenv()

PORT = "COM10"
BAUD = 57600

# IP of the TurtleBot on the network (update if it changes)
TURTLEBOT_IP = "10.134.169.81"
TURTLEBOT_CMD_PORT = 5006        # Dedicated port: PC → TurtleBot commands

# Minimum yaw change (radians) to classify as a turn (~15 degrees)
YAW_CHANGE_THRESHOLD = 0.2618

client = OpenAI()
MODEL = "gpt-4o-mini"

print("Connecting to Pixhawk...")
master = mavutil.mavlink_connection(PORT, baud=BAUD)
master.wait_heartbeat()
print("Connected!")

latest = {}
prev_yaw = None
changes_log = []

cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def send_command_to_turtlebot(command):
    payload = json.dumps(command).encode()
    cmd_sock.sendto(payload, (TURTLEBOT_IP, TURTLEBOT_CMD_PORT))
    print(f"[→ TURTLEBOT] Sent: {command['type']} | yaw_delta={command.get('yaw_delta_deg')}°")


def detect_turn(telemetry, telemetry_time):
    global prev_yaw, changes_log

    current_yaw = telemetry.get("yaw")
    if current_yaw is None:
        return

    if prev_yaw is None:
        prev_yaw = current_yaw
        return

    # Normalize to [-pi, pi] to handle yaw wraparound
    delta = math.atan2(
        math.sin(current_yaw - prev_yaw),
        math.cos(current_yaw - prev_yaw)
    )

    if abs(delta) >= YAW_CHANGE_THRESHOLD:
        turn_type = "RIGHT_TURN" if delta > 0 else "LEFT_TURN"

        change = {
            "type": turn_type,
            "yaw_delta_deg": round(math.degrees(delta), 2),
            "telemetry_timestamp": round(telemetry_time, 3),
            "telemetry_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(telemetry_time)) + " UTC",
            "altitude_m": telemetry.get("altitude"),
            "lat": telemetry.get("lat"),
            "lon": telemetry.get("lon"),
        }

        changes_log.append(change)
        print(f"\n[CHANGE DETECTED] {turn_type} | delta={change['yaw_delta_deg']}° | {change['telemetry_iso']}")
        send_command_to_turtlebot(change)

    prev_yaw = current_yaw


def send_to_llm(data, telemetry_time):
    prompt = f"""Drone telemetry data:
{json.dumps(data, indent=2)}

Reply in ONE short line. Use plain keywords only, no explanation.
Format: <stability>. <battery>. <any issue or "No issues">.
Examples: "Stable. Battery 82%. No issues." or "Unstable. Battery 12%. Low battery."
"""

    ts_str = time.strftime("%H:%M:%S", time.gmtime(telemetry_time))
    ms_str = f"{int((telemetry_time % 1) * 1000):03d}"
    print(f"\n[TIMING] Telemetry at: {ts_str}.{ms_str} UTC")

    llm_start = time.time()

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        max_tokens=40,
    )

    print("[LLM] ", end="", flush=True)
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)

    llm_end = time.time()
    llm_latency = llm_end - llm_start
    total_delay = llm_end - telemetry_time

    print(f"\n[TIMING] LLM: {llm_latency:.2f}s | Total: {total_delay:.2f}s")


last_send = time.time()

print("Pipeline running. Waiting for telemetry...\n")

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
        latest["lat"] = msg.lat / 1e7
        latest["lon"] = msg.lon / 1e7

    if time.time() - last_send > 5:
        telemetry_time = time.time()

        print("\n" + "=" * 50)
        print("Telemetry:", latest)

        detect_turn(latest, telemetry_time)
        send_to_llm(latest, telemetry_time)

        last_send = time.time()
