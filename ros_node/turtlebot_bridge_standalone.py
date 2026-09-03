#!/usr/bin/env python3
"""
TurtleBot Bridge — standalone, no colcon build required.

Run directly on the TurtleBot's Ubuntu machine:

    pip3 install websockets     # one-time
    python3 turtlebot_bridge_standalone.py \
        --robot-id turtlebot_01 \
        --gateway ws://192.168.0.X:8000/ws/ingest \
        --heading 0

Replace 192.168.0.X with your Windows PC's IP address.
"""

import argparse
import asyncio
import json
import math
import threading
import time

# ── Try to import ROS2 (rclpy) ──────────────────────────────────────────────
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import BatteryState
    from geometry_msgs.msg import Twist
    HAS_ROS = True
except ImportError:
    HAS_ROS = False
    print("[bridge] WARNING: rclpy not found — running in DEMO mode (fake odometry).")

# ── Try to import websockets ─────────────────────────────────────────────────
try:
    import websockets
    HAS_WS = True
except ImportError:
    HAS_WS = False
    print("[bridge] ERROR: 'websockets' package missing. Run:  pip3 install websockets")


# ── Coordinate math (inline — no backend dependency) ─────────────────────────

def yaw_from_quaternion(q) -> float:
    """Extract yaw (radians) from a ROS2 Quaternion object."""
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def odom_to_mission(x_odom: float, y_odom: float, yaw_odom: float,
                    heading_deg: float, origin_x: float, origin_y: float):
    """
    Rotate odometry frame into a flat ENU mission frame.
    heading_deg: compass heading (°, 0=North, +CW) the robot was facing at origin.
    """
    # rotation angle: heading_deg → ENU yaw (CCW from East)
    rot = math.radians(90.0 - heading_deg)
    x_m = origin_x + x_odom * math.cos(rot) - y_odom * math.sin(rot)
    y_m = origin_y + x_odom * math.sin(rot) + y_odom * math.cos(rot)
    yaw_m = yaw_odom + rot
    return x_m, y_m, yaw_m


# ── Main bridge node (ROS2 variant) ──────────────────────────────────────────

class BridgeNode(Node if HAS_ROS else object):  # type: ignore[misc]
    def __init__(self, args: argparse.Namespace) -> None:
        if HAS_ROS:
            super().__init__("turtlebot_bridge")

        self.robot_id = args.robot_id
        self.gateway_url = f"{args.gateway}?robot_id={self.robot_id}"
        self.heading_deg = args.heading
        self.origin_x = args.origin_x
        self.origin_y = args.origin_y

        self._battery_pct: float | None = None
        self._last_cmd_t = 0.0
        self._lin_x = 0.0
        self._ang_z = 0.0
        self._ws = None
        self._loop: asyncio.AbstractEventLoop | None = None

        if HAS_ROS:
            self.cmd_vel_pub = self.create_publisher(Twist, args.cmd_vel_topic, 10)
            self.create_subscription(Odometry, args.odom_topic, self._on_odom, qos_profile_sensor_data)
            self.create_subscription(BatteryState, args.battery_topic, self._on_battery, qos_profile_sensor_data)
            self.create_timer(0.05, self._watchdog_tick)  # 20 Hz safety watchdog
            self.get_logger().info(
                f"[bridge] robot_id={self.robot_id}  gateway={self.gateway_url}")

        # WebSocket client runs in its own thread+event-loop
        ws_thread = threading.Thread(target=self._run_ws, daemon=True)
        ws_thread.start()

    # ── ROS callbacks ──────────────────────────────────────────────────────

    def _on_odom(self, msg: "Odometry") -> None:  # type: ignore[name-defined]
        if not getattr(self, "_odom_logged", False):
            self._odom_logged = True
            if HAS_ROS:
                self.get_logger().info(f"[bridge] Received first odometry packet! x={msg.pose.pose.position.x:.2f}, y={msg.pose.pose.position.y:.2f}")
        x, y, yaw = odom_to_mission(
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            yaw_from_quaternion(msg.pose.pose.orientation),
            self.heading_deg, self.origin_x, self.origin_y,
        )
        self._push_state(
            x=x, y=y, yaw=yaw,
            lin_x=msg.twist.twist.linear.x,
            lin_y=msg.twist.twist.linear.y,
            ang_z=msg.twist.twist.angular.z,
        )

    def _on_battery(self, msg: "BatteryState") -> None:  # type: ignore[name-defined]
        pct = msg.percentage
        if pct == pct:  # not NaN
            self._battery_pct = pct * 100.0 if pct <= 1.0 else pct

    def _watchdog_tick(self) -> None:
        """Stop robot if gateway goes silent for more than 1 s."""
        if time.time() - self._last_cmd_t > 1.0 and (self._lin_x or self._ang_z):
            if HAS_ROS:
                self.get_logger().warn("[bridge] watchdog — stopping robot")
                self.cmd_vel_pub.publish(Twist())
            self._lin_x = 0.0
            self._ang_z = 0.0

    # ── State sender ───────────────────────────────────────────────────────

    def _push_state(self, *, x, y, yaw, lin_x, lin_y, ang_z) -> None:
        ts = int(time.time() * 1000)
        state = {
            "robot_id": self.robot_id,
            "robot_type": "UGV",
            "protocol": "ROS2",
            "connected": True,
            "mode": "MOVING" if (lin_x or ang_z) else "IDLE",
            "health": "NORMAL",
            "pose": {"x": x, "y": y, "z": 0.0,
                     "roll": 0.0, "pitch": 0.0, "yaw": yaw},
            "gps": None,
            "velocity": {"linear_x": lin_x, "linear_y": lin_y, "linear_z": 0.0,
                         "angular_x": 0.0, "angular_y": 0.0, "angular_z": ang_z},
            "battery": {"voltage": None, "current": None,
                        "percentage": self._battery_pct},
            "capabilities": ["POSITION", "ODOMETRY", "BATTERY",
                              "LINEAR_VELOCITY_CONTROL", "ANGULAR_VELOCITY_CONTROL"],
            "source_timestamp_ms": ts,
            "received_timestamp_ms": ts,
            "metadata": {"heading_deg_from_north": self.heading_deg},
        }
        payload = json.dumps({"type": "state", "state": state})
        if self._ws is not None and self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._ws.send(payload), self._loop)

    # ── Gateway command handler ────────────────────────────────────────────

    def _handle_cmd(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if msg.get("type") != "command":
            return
        self._lin_x = float(msg.get("linear_x", 0.0))
        self._ang_z = float(msg.get("angular_z", 0.0))
        self._last_cmd_t = time.time()
        if HAS_ROS:
            t = Twist()
            t.linear.x = self._lin_x
            t.angular.z = self._ang_z
            self.cmd_vel_pub.publish(t)

    # ── WebSocket event loop (background thread) ───────────────────────────

    def _run_ws(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._ws_loop())

    async def _ws_loop(self) -> None:
        if not HAS_WS:
            return
        while True:
            try:
                print(f"[bridge] Connecting to {self.gateway_url} …")
                async with websockets.connect(self.gateway_url) as ws:
                    self._ws = ws
                    print("[bridge] ✓ Connected to gateway")
                    async for raw in ws:
                        self._handle_cmd(raw)
            except Exception as exc:
                print(f"[bridge] Connection lost: {exc} — retry in 2 s")
                self._ws = None
                await asyncio.sleep(2.0)


# ── Demo mode: push fake odometry when ROS2 is unavailable ───────────────────

async def _demo_loop(node: BridgeNode) -> None:
    t = 0.0
    while True:
        x = math.cos(t * 0.1) * 0.5
        y = math.sin(t * 0.1) * 0.5
        node._push_state(x=x, y=y, yaw=t * 0.1,
                         lin_x=0.1, lin_y=0.0, ang_z=0.05)
        t += 0.1
        await asyncio.sleep(0.1)


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TurtleBot → Gateway bridge (standalone)")
    parser.add_argument("--robot-id", default="turtlebot_01", help="Robot ID in robots.yaml")
    parser.add_argument("--gateway", default="ws://localhost:8000/ws/ingest",
                        help="Gateway WebSocket ingest URL (replace localhost with your PC IP)")
    parser.add_argument("--heading", type=float, default=0.0,
                        help="Compass heading (°, 0=North, CW) robot faced at odometry origin")
    parser.add_argument("--origin-x", type=float, default=0.0, help="Mission-frame X offset (m)")
    parser.add_argument("--origin-y", type=float, default=0.0, help="Mission-frame Y offset (m)")
    parser.add_argument("--odom-topic", default="odom")
    parser.add_argument("--battery-topic", default="battery_state")
    parser.add_argument("--cmd-vel-topic", default="cmd_vel")
    args = parser.parse_args()

    if HAS_ROS:
        rclpy.init()
        node = BridgeNode(args)
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        finally:
            if HAS_ROS:
                node.cmd_vel_pub.publish(Twist())
            node.destroy_node()
            rclpy.shutdown()
    else:
        # No ROS2 — push demo data so you can verify gateway connectivity
        print("[bridge] No ROS2 — running demo loop. Press Ctrl+C to stop.")
        node = BridgeNode(args)
        asyncio.run(_demo_loop(node))


if __name__ == "__main__":
    main()
