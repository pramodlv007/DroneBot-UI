from pymavlink import mavutil
import json
import time

PORT = "COM10"
BAUD = 57600

print("Connecting...")
master = mavutil.mavlink_connection(PORT, baud=BAUD)
master.wait_heartbeat()
print("Connected!")

while True:
    msg = master.recv_match(blocking=True, timeout=2)

    if not msg:
        continue

    msg_type = msg.get_type()

    if msg_type in ["HEARTBEAT", "SYS_STATUS", "ATTITUDE", "GPS_RAW_INT", "GLOBAL_POSITION_INT"]:
        print(msg_type, msg.to_dict())

    time.sleep(0.1)