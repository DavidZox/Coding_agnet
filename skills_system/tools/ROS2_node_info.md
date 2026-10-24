---
type: Tool
title: ROS2 節點資訊
description: 查詢指定 node 的訂閱、發布、服務、Action（標頭算好每一類的數量；容器可省略＝目標容器）。
version: 1.5.1
dependencies: ["docker", "ros2"]
---

# 用途
在容器內執行 `ros2 node info <node>`（自動載入 ROS 2 與已記錄的 Workspace、沿用節點的 ROS_DOMAIN_ID）。每個 node 都有的參數服務
（describe_parameters…set_parameters_atomically、get_type_description）不列出、標頭註明個數。逾時 30 秒。

# 語法
`EXECUTE: scripts/ROS2_node_info_cmd.py [container_name] <node_name>`
* `node_name` 含命名空間（`/nav_node`；少了開頭的 / 會自動補）。兩個參數時第一個一定是容器名稱。一次查一個 node。

# 範例
`EXECUTE: scripts/ROS2_node_info_cmd.py /camera_node`（用目標容器）　`EXECUTE: scripts/ROS2_node_info_cmd.py ros_box /map_server`

# 回傳
`[PASS] 節點 /x（容器 '<名稱>'，ROS_DOMAIN_ID N）：訂閱 a、發布 b、服務 c、服務客戶端 d、Action 伺服器 e、Action 客戶端 f` + 有項目的各節
（`## 訂閱（Subscribers，a 項）`，每行「topic: 型別」）。

# 異常
* 找不到 node → `[ERROR]` 附相近的名稱與目前所有的 node → 用正確的名稱重試，不要猜；一個 node 都沒有 → `ROS2_domain_id`。
* 第一個參數不是容器 → `[ERROR]` 附相近的容器。沒有目標容器、容器沒在跑、找不到 ros2、逾時 → 訊息會說下一步。
