#include <chrono>
#include <cmath>
#include <memory>

#include "geometry_msgs/msg/twist.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"

#include "amr_utils/odom_math.hpp"

class OdomNode : public rclcpp::Node {
 public:
  OdomNode() : Node("odom_node") {
    pub_ = create_publisher<nav_msgs::msg::Odometry>("odom", 10);
    sub_ = create_subscription<geometry_msgs::msg::Twist>(
        "cmd_vel", 10, [this](geometry_msgs::msg::Twist::SharedPtr msg) { cmd_ = *msg; });
    timer_ = create_wall_timer(std::chrono::milliseconds(20), [this]() { step(0.02); });
  }

 private:
  void step(double dt) {
    pose_ = amr_utils::integrate_diff_drive(pose_, cmd_.linear.x, cmd_.angular.z, dt);
    nav_msgs::msg::Odometry odom;
    odom.header.stamp = now();
    odom.header.frame_id = "odom";
    odom.child_frame_id = "base_link";
    odom.pose.pose.position.x = pose_.x;
    odom.pose.pose.position.y = pose_.y;
    odom.pose.pose.orientation.z = std::sin(pose_.theta / 2.0);
    odom.pose.pose.orientation.w = std::cos(pose_.theta / 2.0);
    pub_->publish(odom);
  }

  amr_utils::Pose2D pose_;
  geometry_msgs::msg::Twist cmd_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr pub_;
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<OdomNode>());
  rclcpp::shutdown();
  return 0;
}
