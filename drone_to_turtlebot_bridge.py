from openai.types.responses import web_search_tool
import os
import time
import math
import json
import threading
from dataclasses import dataclass

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

from pymavlink import mavutil


# ============================================================
# SETTINGS
# ============================================================

PIXHAWK_CONNECTION = "udp:0.0.0.0:14550"
PIXHAWK_BAUD = 57600

# Options:
#   "SIM"      - fake circular path, no hardware needed
#   "ATTITUDE" - Pixhawk handheld indoors: tilt forward=drive, rotate=turn
#   "LOCAL"    - Pixhawk indoors with optical flow sensor (EKF position)
#   "GPS"      - Pixhawk outdoors with GPS lock
DRONE_SOURCE = "GPS"

TURTLEBOT_ODOM_TOPIC = "/odom"
TURTLEBOT_CMD_TOPIC = "/cmd_vel"

CONTROL_RATE_HZ = 10

FOLLOW_DISTANCE_M = 0.0
MAX_LINEAR_SPEED = 0.22
MAX_ANGULAR_SPEED = 1.0

STOP_DISTANCE_M = 0.25

# Compass heading the TurtleBot FRONT is facing (degrees from North).
# 0=North, 90=East, 180=South, 270=West
# Check with a phone compass app, looking in the direction the bot faces.
# Set to None to auto-detect from Pixhawk compass.
# Auto-detect: place Pixhawk ON the TurtleBot (facing same direction)
# at startup, wait for "Heading locked" message, then pick it up and go.
TURTLEBOT_FACING_DEG = 

ENABLE_TURTLEBOT_MOTION = True
ENABLE_LLM_SUPERVISOR = False     # Optional slow supervisor

LLM_INTERVAL_SEC = 5.0
OPENAI_MODEL = "gpt-5.5"


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class DroneState:
    x: float = 0.0
    y: float = 0.0
    alt: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    compass_heading: float = -1.0   # VFR_HUD heading (0-360 deg from North)
    battery_v: float = 0.0
    gps_fix: int = 0
    last_update: float = 0.0


@dataclass
class TurtleState:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    last_update: float = 0.0


# ============================================================
# HELPERS
# ============================================================

def clamp(value, low, high):
    return max(low, min(high, value))


def yaw_from_quaternion(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def distance_2d(x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


# ============================================================
# MAVLINK DRONE READER
# ============================================================

class DroneReader(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.state = DroneState()
        self.running = True
        self.master = None

        self.home_lat = None
        self.home_lon = None

    def connect(self):
        print("Connecting to Pixhawk...")
        self.master = mavutil.mavlink_connection(
            PIXHAWK_CONNECTION,
            baud=PIXHAWK_BAUD
        )
        self.master.wait_heartbeat()
        print(f"Pixhawk connected (sys={self.master.target_system})")

        # Request LOCAL_POSITION_NED (ID 32) at 10 Hz
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            32,      # LOCAL_POSITION_NED
            100000,  # interval microseconds = 10 Hz
            0, 0, 0, 0, 0
        )
        # Request ATTITUDE (ID 30) at 10 Hz
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            30,      # ATTITUDE
            100000,
            0, 0, 0, 0, 0
        )
        # Request VFR_HUD (ID 74) at 2 Hz for compass heading
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            74,      # VFR_HUD
            500000,  # 2 Hz
            0, 0, 0, 0, 0
        )
        print("Data streams requested")

    def run(self):
        # Skip hardware connection entirely when simulating
        if DRONE_SOURCE != "SIM":
            self.connect()

        sim_start = time.time()

        while self.running:
            if DRONE_SOURCE == "SIM":
                t = time.time() - sim_start

                # Simulated drone path — radius 1.0m at 0.1 rad/s = 0.10 m/s
                # TurtleBot max is 0.18 m/s so it can actually follow this
                self.state.x = 1.0 * math.sin(0.1 * t)
                self.state.y = 1.0 * math.cos(0.1 * t)
                self.state.alt = 1.0
                self.state.last_update = time.time()

                time.sleep(0.05)
                continue

            msg = self.master.recv_match(blocking=False)

            if msg is None:
                time.sleep(0.01)
                continue

            msg_type = msg.get_type()

            if msg_type == "ATTITUDE":
                self.state.roll = msg.roll
                self.state.pitch = msg.pitch
                self.state.yaw = msg.yaw
                if DRONE_SOURCE == "ATTITUDE":
                    self.state.last_update = time.time()

            elif msg_type == "LOCAL_POSITION_NED" and DRONE_SOURCE == "LOCAL":
                # x=North, y=East in metres from where Pixhawk booted
                self.state.x = msg.x
                self.state.y = msg.y
                self.state.alt = -msg.z   # NED: z is negative upward
                self.state.last_update = time.time()

            elif msg_type == "GLOBAL_POSITION_INT" and DRONE_SOURCE == "GPS":
                lat = msg.lat / 1e7
                lon = msg.lon / 1e7
                alt = msg.relative_alt / 1000.0

                if self.home_lat is None:
                    self.home_lat = lat
                    self.home_lon = lon

                meters_per_deg_lat = 111_320.0
                meters_per_deg_lon = 111_320.0 * math.cos(math.radians(self.home_lat))

                self.state.x = (lat - self.home_lat) * meters_per_deg_lat
                self.state.y = (lon - self.home_lon) * meters_per_deg_lon
                self.state.alt = alt
                self.state.last_update = time.time()

            elif msg_type == "GPS_RAW_INT":
                self.state.gps_fix = msg.fix_type

            elif msg_type == "VFR_HUD":
                self.state.compass_heading = float(msg.heading)

            elif msg_type == "SYS_STATUS":
                self.state.battery_v = msg.voltage_battery / 1000.0


# ============================================================
# OPTIONAL LLM SUPERVISOR
# ============================================================

class LLMSupervisor(threading.Thread):
    def __init__(self, drone_reader, turtle_getter):
        super().__init__(daemon=True)
        self.drone_reader = drone_reader
        self.turtle_getter = turtle_getter
        self.running = True

    def run(self):
        if not ENABLE_LLM_SUPERVISOR:
            return

        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        except Exception as e:
            print("LLM disabled:", e)
            return

        while self.running:
            drone = self.drone_reader.state
            turtle = self.turtle_getter()

            telemetry = {
                "drone": drone.__dict__,
                "turtlebot": turtle.__dict__,
                "tracking_error_m": distance_2d(
                    drone.x, drone.y, turtle.x, turtle.y
                )
            }

            prompt = f"""
You are a robotics mission supervisor.
Do not give direct motor commands.
Analyze this drone-following-turtlebot mission state.
Return strict JSON with:
status: normal | warning | critical
issues: list
recommended_action: continue | slow_down | stop_turtlebot | pause_mission

Telemetry:
{json.dumps(telemetry, indent=2)}
"""

            try:
                response = client.responses.create(
                    model=OPENAI_MODEL,
                    input=prompt
                )

                print("\n========== LLM SUPERVISOR ==========")
                print(response.output_text)
                print("====================================\n")

            except Exception as e:
                print("LLM error:", e)

            time.sleep(LLM_INTERVAL_SEC)


# ============================================================
# ROS2 TURTLEBOT CONTROLLER
# ============================================================

class DroneToTurtleBotNode(Node):
    def __init__(self, drone_reader):
        super().__init__("drone_to_turtlebot_bridge")

        self.drone_reader = drone_reader
        self.turtle = TurtleState()

        self.cmd_pub = self.create_publisher(
            Twist,
            TURTLEBOT_CMD_TOPIC,
            10
        )

        self.odom_sub = self.create_subscription(
            Odometry,
            TURTLEBOT_ODOM_TOPIC,
            self.odom_callback,
            10
        )

        self.timer = self.create_timer(
            1.0 / CONTROL_RATE_HZ,
            self.control_loop
        )

        self.get_logger().info("Drone → TurtleBot bridge started")

    def get_turtle_state(self):
        return self.turtle

    def odom_callback(self, msg):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y

        # Lock the drone SIM origin to wherever the TurtleBot starts
        if not hasattr(self, 'turtle_home'):
            self.turtle_home = (x, y)
            self.get_logger().info(f"Home set: X:{x:.2f} Y:{y:.2f}")

        self.turtle.x = x
        self.turtle.y = y
        self.turtle.yaw = yaw_from_quaternion(msg.pose.pose.orientation)
        self.turtle.last_update = time.time()

    def stop_turtlebot(self):
        self.cmd_pub.publish(Twist())

    def control_loop(self):
        drone = self.drone_reader.state
        turtle = self.turtle

        now = time.time()

        if now - turtle.last_update > 2.0:
            self.get_logger().warn("No TurtleBot odom received")
            self.stop_turtlebot()
            return

        if now - drone.last_update > 2.0:
            self.get_logger().warn("No drone telemetry received")
            self.stop_turtlebot()
            return

        cmd = Twist()

        if DRONE_SOURCE == "ATTITUDE":
            # Tilt Pixhawk forward (negative pitch) → drive forward
            # Rotate Pixhawk (yaw) → turn
            # Dead zone of 0.05 rad (~3 deg) to avoid drift
            pitch = drone.pitch
            yaw_rate = drone.yaw  # used as heading reference

            linear = clamp(-pitch * 0.6, -MAX_LINEAR_SPEED, MAX_LINEAR_SPEED)
            if abs(linear) < 0.02:
                linear = 0.0

            # Yaw error between Pixhawk heading and TurtleBot heading
            angle_error = yaw_rate - turtle.yaw
            while angle_error > math.pi:
                angle_error -= 2.0 * math.pi
            while angle_error < -math.pi:
                angle_error += 2.0 * math.pi
            angular = clamp(1.5 * angle_error, -MAX_ANGULAR_SPEED, MAX_ANGULAR_SPEED)

            if ENABLE_TURTLEBOT_MOTION:
                cmd.linear.x = linear
                cmd.angular.z = angular
                self.cmd_pub.publish(cmd)
            else:
                self.stop_turtlebot()

            print(
                f"Pitch:{drone.pitch:.2f} Yaw:{drone.yaw:.2f} | "
                f"cmd_v:{cmd.linear.x:.2f} cmd_w:{cmd.angular.z:.2f}"
            )

        else:
            # ── GPS / LOCAL position tracking ────────────────────
            #
            # GPS frame:  x = North,   y = East   (left-handed)
            # Odom frame: x = Forward, y = Left   (right-handed)
            #
            # Conversion needs a REFLECTION, not a rotation:
            #   odom_x =  gps_x * cos(H) + gps_y * sin(H)
            #   odom_y =  gps_x * sin(H) - gps_y * cos(H)
            # where H = compass heading the TurtleBot faces.
            # ─────────────────────────────────────────────────────
            home = getattr(self, 'turtle_home', (0.0, 0.0))

            # ── Determine H (TurtleBot heading) once ─────────────
            if not hasattr(self, '_heading_rad'):
                if TURTLEBOT_FACING_DEG is not None:
                    # User specified the heading manually
                    self._heading_rad = math.radians(TURTLEBOT_FACING_DEG)
                    print(f"[FRAME] Using configured heading: "
                          f"{TURTLEBOT_FACING_DEG}° from North")
                else:
                    # Auto-detect from Pixhawk compass.
                    # Pixhawk must be ON the TurtleBot, facing same
                    # direction as the bot's front.
                    if drone.compass_heading >= 0:
                        self._heading_rad = math.radians(
                            drone.compass_heading)
                        print(f"[FRAME] Heading from Pixhawk compass: "
                              f"{drone.compass_heading:.0f}° from North")
                        print(f"[FRAME] >>> Pick up the Pixhawk and walk! <<<")
                    else:
                        self.stop_turtlebot()
                        print("Waiting for Pixhawk compass (VFR_HUD)...")
                        return

                # Wait for drone to actually move before tracking
                self._tracking_active = False

            # Don't start tracking until drone has moved away
            if not getattr(self, '_tracking_active', False):
                gps_dist = math.sqrt(drone.x**2 + drone.y**2)
                if gps_dist > 0.5:
                    self._tracking_active = True
                    print(f"[TRACK] Drone moved {gps_dist:.2f}m — tracking!")
                else:
                    self.stop_turtlebot()
                    print(f"Waiting for drone to move... Dist:{gps_dist:.2f}")
                    return

            # ── Convert drone GPS position → odom frame ──────────
            H = self._heading_rad
            cosH = math.cos(H)
            sinH = math.sin(H)
            target_x = drone.x * cosH + drone.y * sinH + home[0]
            target_y = drone.x * sinH - drone.y * cosH + home[1]

            dx = target_x - turtle.x
            dy = target_y - turtle.y
            distance = math.sqrt(dx * dx + dy * dy)

            # ── Heading to target in odom frame ──────────────────
            target_angle = math.atan2(dy, dx)
            angle_error = target_angle - turtle.yaw
            while angle_error > math.pi:
                angle_error -= 2.0 * math.pi
            while angle_error < -math.pi:
                angle_error += 2.0 * math.pi

            # ── Go-to-point controller ───────────────────────────
            if distance > STOP_DISTANCE_M:
                angular = clamp(2.5 * angle_error,
                                -MAX_ANGULAR_SPEED, MAX_ANGULAR_SPEED)
                alignment = max(0.0, math.cos(angle_error))
                linear = MAX_LINEAR_SPEED * alignment
                cmd.linear.x = linear
                cmd.angular.z = angular

            if ENABLE_TURTLEBOT_MOTION:
                self.cmd_pub.publish(cmd)
            else:
                self.stop_turtlebot()

            print(
                f"Drone X:{drone.x:.2f} Y:{drone.y:.2f} | "
                f"Turtle X:{turtle.x:.2f} Y:{turtle.y:.2f} | "
                f"Dist:{distance:.2f} | "
                f"HeadErr:{math.degrees(angle_error):.0f}° | "
                f"v:{cmd.linear.x:.2f} w:{cmd.angular.z:.2f}"
            )


# ============================================================
# MAIN
# ============================================================

def main():
    print("==========================================")
    print(" Drone → TurtleBot Bridge")
    print("==========================================")
    print(f"Drone source: {DRONE_SOURCE}")
    print(f"TurtleBot motion enabled: {ENABLE_TURTLEBOT_MOTION}")
    if TURTLEBOT_FACING_DEG is not None:
        print(f"TurtleBot heading: {TURTLEBOT_FACING_DEG}° (manual)")
    else:
        print("TurtleBot heading: AUTO (from Pixhawk compass)")
        print("  → Place Pixhawk ON TurtleBot facing same direction")
        print("  → Wait for 'Heading locked' then pick up and walk")
    print("==========================================")

    drone_reader = DroneReader()
    drone_reader.start()

    rclpy.init()

    node = DroneToTurtleBotNode(drone_reader)

    llm = LLMSupervisor(drone_reader, node.get_turtle_state)
    llm.start()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        print("Stopping...")

    finally:
        node.stop_turtlebot()
        drone_reader.running = False
        llm.running = False
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
