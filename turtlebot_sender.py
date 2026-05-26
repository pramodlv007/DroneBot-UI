import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry

import socket
import json
import threading

PC_IP = "10.215.31.111"
PC_PORT = 5005

CMD_LISTEN_PORT = 5006  # Port to receive drone turn commands from PC

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def command_listener():
    """Background thread: receives turn commands from drone (via PC) and logs them.

    To make the robot physically turn, publish a Twist to /cmd_vel here,
    or send a Nav2 waypoint goal.
    """
    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cmd_sock.bind(("0.0.0.0", CMD_LISTEN_PORT))
    print(f"[CMD LISTENER] Ready on port {CMD_LISTEN_PORT}")

    while True:
        try:
            data, _ = cmd_sock.recvfrom(4096)
            cmd = json.loads(data.decode("utf-8"))
            cmd_type = cmd.get("type", "UNKNOWN")

            print(f"\n{'='*50}")
            print(f"[COMMAND FROM DRONE] {cmd_type}")
            print(f"  Timestamp  : {cmd.get('telemetry_iso', 'N/A')}")
            print(f"  Yaw delta  : {cmd.get('yaw_delta_deg', 0):.1f} deg")
            print(f"  Altitude   : {cmd.get('altitude_m', 'N/A')} m")
            print(f"  Drone lat  : {cmd.get('lat', 'N/A')}")
            print(f"  Drone lon  : {cmd.get('lon', 'N/A')}")
            print(f"  Raw unix ts: {cmd.get('telemetry_timestamp', 'N/A')}")
            print(f"{'='*50}")

            # TODO: Uncomment and adapt once ROS2 cmd_vel publishing is wired up
            # from geometry_msgs.msg import Twist
            # twist = Twist()
            # if cmd_type == "LEFT_TURN":
            #     twist.angular.z = 0.5   # positive = counter-clockwise (left)
            # elif cmd_type == "RIGHT_TURN":
            #     twist.angular.z = -0.5  # negative = clockwise (right)
            # cmd_vel_pub.publish(twist)

        except Exception as e:
            print(f"[CMD LISTENER] Error: {e}")


class TurtleBotSender(Node):

    def __init__(self):
        super().__init__('turtlebot_udp_sender')

        self.subscription = self.create_subscription(
            Odometry,
            '/odom',
            self.listener_callback,
            10
        )

        t = threading.Thread(target=command_listener, daemon=True)
        t.start()

        self.get_logger().info("Sending TurtleBot position via UDP")
        self.get_logger().info(f"Listening for drone commands on port {CMD_LISTEN_PORT}")

    def listener_callback(self, msg):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y

        data = {
            "x": x,
            "y": y,
            "yaw": 0.0
        }

        sock.sendto(json.dumps(data).encode(), (PC_IP, PC_PORT))

        print(f"Sent → X:{x:.2f}, Y:{y:.2f}")


def main(args=None):
    rclpy.init(args=args)

    node = TurtleBotSender()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
