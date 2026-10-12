# AMR 底盤的 ROS 2 工作區（評測用的縮小版）

colcon 工作區，兩個套件：

- `src/amr_utils`（ament_cmake）：里程計的數學（`include/amr_utils/odom_math.hpp`、`src/odom_math.cpp`，不依賴 ROS）與 `odom_node`（rclcpp：訂閱 `cmd_vel`、發布 `odom`）。測試：`test/test_odom_math.cpp`（gtest）、`test/test_odom_node.cpp`（需要 rclcpp）。
- `src/amr_tools`（ament_python）：電池電量的計算（`amr_tools/battery.py`，不依賴 ROS）與 `battery_node`（rclpy：訂閱 `battery_state`）。測試：`test/test_battery.py`（pytest）與 ROS 2 範本的 linter 測試。

建置與測試（在有 ROS 2 的環境）：

```bash
colcon build --symlink-install
colcon test && colcon test-result --verbose
```
