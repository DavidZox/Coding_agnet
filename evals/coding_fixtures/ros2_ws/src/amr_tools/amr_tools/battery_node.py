import rclpy
from rclpy.node import Node
from sensor_msgs.msg import BatteryState

from amr_tools.battery import percent


class BatteryMonitor(Node):

    def __init__(self):
        super().__init__('battery_monitor')
        self.sub = self.create_subscription(BatteryState, 'battery_state', self.on_battery, 10)

    def on_battery(self, msg):
        self.get_logger().info(f'battery {percent(msg.voltage):.1f}%')


def main(args=None):
    rclpy.init(args=args)
    node = BatteryMonitor()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
