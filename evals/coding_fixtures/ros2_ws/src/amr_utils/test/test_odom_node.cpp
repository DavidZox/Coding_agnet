#include <gtest/gtest.h>

#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"

TEST(OdomNode, CanCreateNode) {
  rclcpp::init(0, nullptr);
  auto node = std::make_shared<rclcpp::Node>("test_odom_node");
  EXPECT_EQ(std::string(node->get_name()), "test_odom_node");
  rclcpp::shutdown();
}
