"""
ros2 launch heterogeneous_robot_bridge turtlebot_bridge.launch.py \
    robot_id:=turtlebot_01 \
    gateway_ws_url:=ws://192.168.1.50:8000/ws/ingest \
    heading_deg_from_north:=90.0

Run this on the TurtleBot's companion computer (wherever ROS2 + this
TurtleBot's driver stack is installed). It does not need the FastAPI
backend's Python dependencies installed — only rclpy, the standard ROS2
message packages, and `websockets` (see package.xml/setup.py).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    robot_id = LaunchConfiguration("robot_id")
    gateway_ws_url = LaunchConfiguration("gateway_ws_url")
    heading_deg_from_north = LaunchConfiguration("heading_deg_from_north")

    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_id", default_value="turtlebot_01"),
            DeclareLaunchArgument("gateway_ws_url", default_value="ws://localhost:8000/ws/ingest"),
            DeclareLaunchArgument("heading_deg_from_north", default_value="0.0"),
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
                    }
                ],
            ),
        ]
    )
