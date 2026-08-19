from setuptools import setup

package_name = "heterogeneous_robot_bridge"

setup(
    name=package_name,
    version="0.2.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", ["launch/turtlebot_bridge.launch.py"]),
    ],
    install_requires=["setuptools", "websockets"],
    zip_safe=True,
    maintainer="Pramod",
    maintainer_email="pramodlv2025@gmail.com",
    description="TurtleBot ROS2 <-> Unified Robot Gateway bridge node",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "turtlebot_bridge_node = heterogeneous_robot_bridge.turtlebot_bridge_node:main",
        ],
    },
)
