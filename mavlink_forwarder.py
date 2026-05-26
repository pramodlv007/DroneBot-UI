import socket
from pymavlink import mavutil

SERIAL_PORT = "COM10"
BAUD = 57600
TURTLEBOT_IP = "10.134.169.81"
TURTLEBOT_PORT = 14550

print(f"Connecting to Pixhawk on {SERIAL_PORT}...")
master = mavutil.mavlink_connection(SERIAL_PORT, baud=BAUD)
master.wait_heartbeat()
print("Pixhawk connected!")

# Request LOCAL_POSITION_NED (ID 32) at 10 Hz
master.mav.command_long_send(
    master.target_system,
    master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
    0, 32, 100000, 0, 0, 0, 0, 0
)

# Request ATTITUDE (ID 30) at 10 Hz
master.mav.command_long_send(
    master.target_system,
    master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
    0, 30, 100000, 0, 0, 0, 0, 0
)

# Request SYS_STATUS (ID 1) at 2 Hz
master.mav.command_long_send(
    master.target_system,
    master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
    0, 1, 500000, 0, 0, 0, 0, 0
)

print("Streams requested. Forwarding to TurtleBot...")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

count = 0
while True:
    msg = master.recv_match(blocking=True)
    if msg:
        sock.sendto(msg.get_msgbuf(), (TURTLEBOT_IP, TURTLEBOT_PORT))
        count += 1
        if count % 50 == 0:
            print(f"Forwarded {count} msgs | last: {msg.get_type()}")
