"""
ros2 launch heterogeneous_robot_bridge turtlebot_bridge.launch.py \
    robot_id:=turtlebot_01 \
    gateway_ws_url:=ws://192.168.1.50:8000/ws/ingest \
    heading_deg_from_north:=90.0 \
    odom_topic:=odom \
    battery_topic:=battery_state \
    cmd_vel_topic:=cmd_vel

Run this on the TurtleBot's companion computer (wherever ROS2 + this
TurtleBot's driver stack is installed). It does not need the FastAPI
backend's Python dependencies installed — only rclpy, the standard ROS2
message packages, and `websockets` (see package.xml/setup.py).

odom_topic/battery_topic/cmd_vel_topic default to the unnamespaced names
the node itself declares. If your bringup publishes odometry on a
namespaced or differently-named topic (e.g. "/turtlebot_01/odom"), you
MUST override odom_topic here — the node otherwise subscribes to the
wrong topic, receives nothing, and the gateway shows "connected" with no
telemetry even though the robot is actually moving and publishing just
fine under its real topic name. Check the real name first with:
    ros2 topic list | grep -i odom
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    robot_id = LaunchConfiguration("robot_id")
    gateway_ws_url = LaunchConfiguration("gateway_ws_url")
    heading_deg_from_north = LaunchConfiguration("heading_deg_from_north")
    odom_topic = LaunchConfiguration("odom_topic")
    battery_topic = LaunchConfiguration("battery_topic")
    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")

    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_id", default_value="turtlebot_01"),
            DeclareLaunchArgument("gateway_ws_url", default_value="ws://localhost:8000/ws/ingest"),
            DeclareLaunchArgument("heading_deg_from_north", default_value="0.0"),
            # These three must match the real topic names your bringup
            # publishes/subscribes on — see the module docstring above.
            DeclareLaunchArgument("odom_topic", default_value="odom"),
            DeclareLaunchArgument("battery_topic", default_value="battery_state"),
            DeclareLaunchArgument("cmd_vel_topic", default_value="cmd_vel"),
            Node(
                package="heterogeneous_robot_bridge",
                executable="turtlebot_bridge_node",
                name="turtlebot_bridge_node",
                output="screen",
                parameters=[
                    {
                        "robot_id": robot_id,
                        "gateway_ws_url": gateway_ws_url,
                        "heading_deg_from_north": heading_deg_from_north,
                        "odom_topic": odom_topic,
                        "battery_topic": battery_topic,
                        "cmd_vel_topic": cmd_vel_topic,
                    }
                ],
            ),
        ]
    )
