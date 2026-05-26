import socket
import json
import time
from pymavlink import mavutil

# =========================
# SETTINGS
# =========================

PIXHAWK_CONNECTION = "COM10"   # Change to your telemetry COM port
PIXHAWK_BAUD = 57600

UDP_IP = "0.0.0.0"
UDP_PORT = 5005

FOLLOW_ALTITUDE_M = 3.0

ENABLE_DRONE_COMMANDS = False  # Keep False for first test
ARM_AND_TAKEOFF = False        # Keep False until safe


# =========================
# PIXHAWK CONNECTION
# =========================

def connect_pixhawk():
    print("Connecting to Pixhawk...")
    master = mavutil.mavlink_connection(
        PIXHAWK_CONNECTION,
        baud=PIXHAWK_BAUD
    )
    master.wait_heartbeat()
    print("Pixhawk connected")
    return master


def set_guided(master):
    print("Setting GUIDED mode...")
    master.set_mode_apm("GUIDED")
    time.sleep(2)


def arm_takeoff(master, altitude):
    print("Arming...")
    master.arducopter_arm()
    master.motors_armed_wait()

    print("Taking off...")
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,
        0, 0, 0, 0,
        0, 0,
        altitude
    )


def send_drone_target(master, x, y, alt):
    master.mav.set_position_target_local_ned_send(
        int(time.time() * 1000) & 0xFFFFFFFF,
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        0b110111111000,
        x,
        y,
        -alt,
        0, 0, 0,
        0, 0, 0,
        0,
        0
    )


# =========================
# UDP TURTLEBOT RECEIVER
# =========================

def setup_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    print(f"Listening for TurtleBot on UDP port {UDP_PORT}")
    return sock


# =========================
# MAIN
# =========================

def main():
    master = connect_pixhawk()
    sock = setup_udp()

    set_guided(master)

    if ARM_AND_TAKEOFF:
        arm_takeoff(master, FOLLOW_ALTITUDE_M)

    print("\nSystem ready.")
    print("Waiting for TurtleBot position...\n")

    last_position = None

    try:
        while True:
            data, addr = sock.recvfrom(1024)

            try:
                msg = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                print("Invalid data received")
                continue

            x = float(msg["x"])
            y = float(msg["y"])
            yaw = float(msg.get("yaw", 0.0))

            last_position = (x, y, yaw)

            print(f"TurtleBot connected from {addr[0]}")
            print(f"Position → X:{x:.2f}, Y:{y:.2f}, Yaw:{yaw:.2f}")

            # Send ACK back to TurtleBot
            sock.sendto(b"ACK_FROM_PC", addr)

            if ENABLE_DRONE_COMMANDS:
                send_drone_target(master, x, y, FOLLOW_ALTITUDE_M)
                print("Drone target updated")

            print("-" * 40)

    except KeyboardInterrupt:
        print("\nStopped.")

        if last_position:
            x, y, yaw = last_position
            print("Final TurtleBot Position:")
            print(f"X: {x:.2f}")
            print(f"Y: {y:.2f}")
            print(f"Yaw: {yaw:.2f}")


if __name__ == "__main__":
    main()