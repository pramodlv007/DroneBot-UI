"""
TurtleBot <-> Unified Robot Gateway bridge node.

Supersedes turtlebot_sender.py (see docs/audit.md). Subscribes to this
TurtleBot's /odom and /battery_state, normalizes them into the platform's
common RobotState JSON schema using the SAME coordinate_transformer module
the backend gateway uses (imported directly — see the sys.path shim below
— so there is exactly one implementation of the odom->mission_map frame
math, not two that could drift apart), and pushes state to the gateway
over a WebSocket client connection. Receives velocity commands back over
that same socket and publishes them to /cmd_vel, with its own local
stale-command watchdog as a second, independent layer of defense on top of
the gateway's SafetyManager (§15) — if the network to the gateway drops,
this node stops the robot on its own rather than coasting on the last
command forever.

Run standalone (no colcon build needed) for quick testing:
    python3 turtlebot_bridge_node.py --ros-args -p gateway_url:=ws://localhost:8000/ws/ingest?robot_id=turtlebot_01
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import threading
import time
from pathlib import Path

# --- single source of truth for coordinate math: import the backend's
# pure-stdlib coordinate_transformer module directly, rather than
# reimplementing the GPS/NED/odom frame conversions a second time here. ---
_BACKEND_APP_DIR = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_APP_DIR))

from app.coordinate_transformer import CoordinateTransformer  # noqa: E402

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import qos_profile_sensor_data  # noqa: E402
from nav_msgs.msg import Odometry  # noqa: E402
from sensor_msgs.msg import BatteryState  # noqa: E402
from geometry_msgs.msg import Twist  # noqa: E402

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None

COMMAND_TIMEOUT_S = 1.0
RECONNECT_BACKOFF_S = 2.0


def yaw_from_quaternion(q) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


class TurtleBotBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("turtlebot_bridge_node")

        self.declare_parameter("robot_id", "turtlebot_01")
        self.declare_parameter("gateway_ws_url", "ws://localhost:8000/ws/ingest")
        self.declare_parameter("odom_topic", "odom")
        self.declare_parameter("battery_topic", "battery_state")
        self.declare_parameter("cmd_vel_topic", "cmd_vel")
        # Compass heading (0=North, clockwise) the TurtleBot's +x (front) was
        # facing at odom-origin time. This replaces the legacy
        # TURTLEBOT_FACING_DEG blocker (see docs/audit.md) with a proper,
        # always-valid ROS2 parameter — default 0.0 (facing North) rather
        # than an unset value, with an explicit operator override expected
        # per-deployment via a launch argument or params file.
        self.declare_parameter("heading_deg_from_north", 0.0)
        self.declare_parameter("mission_origin_x_m", 0.0)
        self.declare_parameter("mission_origin_y_m", 0.0)

        self.robot_id = self.get_parameter("robot_id").value
        self.gateway_url = f"{self.get_parameter('gateway_ws_url').value}?robot_id={self.robot_id}"

        self._transformer = CoordinateTransformer()
        self._transformer.set_turtlebot_origin(
            heading_deg_from_north=self.get_parameter("heading_deg_from_north").value,
            mission_x_m=self.get_parameter("mission_origin_x_m").value,
            mission_y_m=self.get_parameter("mission_origin_y_m").value,
        )

        self._battery_pct: float | None = None
        self._last_command_time = 0.0
        self._linear_x = 0.0
        self._angular_z = 0.0

        self.cmd_vel_pub = self.create_publisher(Twist, self.get_parameter("cmd_vel_topic").value, 10)
        self.create_subscription(Odometry, self.get_parameter("odom_topic").value, self._on_odom, qos_profile_sensor_data)
        self.create_subscription(BatteryState, self.get_parameter("battery_topic").value, self._on_battery, qos_profile_sensor_data)
        self.create_timer(1.0 / 20.0, self._watchdog_tick)  # local safety watchdog, independent of the gateway

        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws = None
        self._ws_thread = threading.Thread(target=self._run_ws_client, daemon=True)
        self._ws_thread.start()

        self.get_logger().info(f"TurtleBot bridge started: robot_id={self.robot_id}, gateway={self.gateway_url}")

    # -- ROS2 callbacks --------------------------------------------------

    def _on_odom(self, msg: Odometry) -> None:
        if not getattr(self, "_odom_logged", False):
            self._odom_logged = True
            self.get_logger().info(f"Received first odometry packet! x={msg.pose.pose.position.x:.2f}, y={msg.pose.pose.position.y:.2f}")
        x, y, yaw = self._transformer.turtlebot_odom_to_mission(
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            yaw_from_quaternion(msg.pose.pose.orientation),
        )
        source_ts_ms = int(time.time() * 1000)

        state = {
            "robot_id": self.robot_id,
            "robot_type": "UGV",
            "protocol": "ROS2",
            "connected": True,
            "mode": "TRACKING" if (self._linear_x or self._angular_z) else "IDLE",
            "health": "NORMAL",
            "pose": {"x": x, "y": y, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": yaw},
            "velocity": {
                "linear_x": msg.twist.twist.linear.x,
                "linear_y": msg.twist.twist.linear.y,
                "angular_z": msg.twist.twist.angular.z,
            },
            "battery": {"percentage": self._battery_pct} if self._battery_pct is not None else None,
            "capabilities": [],
            "source_timestamp_ms": source_ts_ms,
            "received_timestamp_ms": source_ts_ms,
            "metadata": {},
        }
        self._send_state(state)

    def _on_battery(self, msg: BatteryState) -> None:
        if msg.percentage == msg.percentage:  # not NaN
            self._battery_pct = msg.percentage * 100.0 if msg.percentage <= 1.0 else msg.percentage

    def _watchdog_tick(self) -> None:
        if time.time() - self._last_command_time > COMMAND_TIMEOUT_S and (self._linear_x or self._angular_z):
            self.get_logger().warn("No command from gateway within timeout — stopping (local watchdog)")
            self._linear_x = 0.0
            self._angular_z = 0.0
            self.cmd_vel_pub.publish(Twist())

    # -- WebSocket client (runs in its own thread/event loop) -----------

    def _run_ws_client(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._ws_client_loop())

    async def _ws_client_loop(self) -> None:
        if websockets is None:
            self.get_logger().error("The 'websockets' package is required: pip install websockets")
            return
        while rclpy.ok():
            try:
                async with websockets.connect(self.gateway_url) as ws:
                    self._ws = ws
                    self.get_logger().info("Connected to gateway")
                    async for raw in ws:
                        self._handle_gateway_message(raw)
            except Exception as exc:
                self.get_logger().warn(f"Gateway connection lost/failed: {exc}; retrying in {RECONNECT_BACKOFF_S}s")
                self._ws = None
                await asyncio.sleep(RECONNECT_BACKOFF_S)

    def _handle_gateway_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if msg.get("type") != "command":
            return

        self._linear_x = float(msg.get("linear_x", 0.0))
        self._angular_z = float(msg.get("angular_z", 0.0))
        self._last_command_time = time.time()

        twist = Twist()
        twist.linear.x = self._linear_x
        twist.angular.z = self._angular_z
        self.cmd_vel_pub.publish(twist)

    def _send_state(self, state: dict) -> None:
        if self._ws is None or self._loop is None:
            return
        payload = json.dumps({"type": "state", "state": state})
        asyncio.run_coroutine_threadsafe(self._ws.send(payload), self._loop)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TurtleBotBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.cmd_vel_pub.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
