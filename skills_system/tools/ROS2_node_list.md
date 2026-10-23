---
type: Tool
title: ROS2 節點列表
description: 列出容器內運行中的 node，標頭算好總數與實際用的 ROS_DOMAIN_ID；--filter 關鍵字只列符合的並計數。
version: 1.6.0
dependencies: ["docker", "ros2"]
---

# 用途
在容器內執行 `ros2 node list`（自動載入 ROS 2、已記錄的 Workspace，shell 沒設 domain 時沿用正在跑的節點的 ROS_DOMAIN_ID）。兩個以上的命名空間時依命名空間分節。逾時 30 秒。

# 語法
`EXECUTE: scripts/ROS2_node_list_cmd.py [container_name] [--filter 關鍵字]...`
* `container_name`：可省略＝目前的目標容器。`--filter 關鍵字`：只列名稱含關鍵字的（不分大小寫，可重複），標頭給符合的數量，數量直接引用標頭。

# 範例
`EXECUTE: scripts/ROS2_node_list_cmd.py`（用目標容器）　`EXECUTE: scripts/ROS2_node_list_cmd.py --filter nav2`

# 回傳
`[PASS] 容器 '<名稱>' 的 node：共 N 個[，其中含「關鍵字」的 M 個]；ROS_DOMAIN_ID X（來源）` + 每行一個 node（含命名空間）。
一個 node 都沒有時第一行會明說可能的原因（domain 不對、節點沒在跑）。

# 異常
* 沒有 node → `ROS2_domain_id` 看節點在哪個 domain；`docker_ctl logs` 看節點有沒有啟動失敗。
* 名稱不是容器 → `[ERROR]` 附相近的容器；關鍵字要寫成 `--filter`。沒有目標容器、容器沒在跑、找不到 ros2、逾時 → 訊息會說下一步。
