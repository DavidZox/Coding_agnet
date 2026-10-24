---
type: Tool
title: ROS2 話題列表
description: 列出容器內目前的 topic（--types 附訊息型別），標頭算好總數與實際用的 ROS_DOMAIN_ID；--filter 關鍵字只列符合的並計數。
version: 1.6.1
dependencies: ["docker", "ros2"]
---

# 用途
在容器內執行 `ros2 topic list`（自動載入 ROS 2、已記錄的 Workspace，shell 沒設 domain 時沿用正在跑的節點的 ROS_DOMAIN_ID）。
兩個以上的命名空間時依命名空間分節（`## /amr_07（4 項）`）。要發布訊息（ROS2_topic_pub）前用 `--types` 查完整的型別。逾時 30 秒。

# 語法
`EXECUTE: scripts/ROS2_topic_list_cmd.py [container_name] [--types] [--filter 關鍵字]...`
* `container_name`：可省略＝目前的目標容器。`--types`：每行「topic [型別]」。
* `--filter 關鍵字`：只列名稱（或型別）含關鍵字的（不分大小寫，可重複），標頭給符合的數量；問「有幾個／哪些」時數量直接引用標頭。

# 範例
`EXECUTE: scripts/ROS2_topic_list_cmd.py`（用目標容器）　`EXECUTE: scripts/ROS2_topic_list_cmd.py --filter costmap`
`EXECUTE: scripts/ROS2_topic_list_cmd.py ros_box --types --filter camera`

# 回傳
`[PASS] 容器 '<名稱>' 的 topic：共 N 個[，其中含「關鍵字」的 M 個]；ROS_DOMAIN_ID X（來源）` + 清單。
只看到 /parameter_events、/rosout（每個系統都有）時第一行會明說「沒有任何節點自己的 topic」——不是正常的空系統。

# 異常
* 只有系統 topic → domain 可能不對或節點沒在跑 → `ROS2_domain_id`；`ROS2_node_list` 看有沒有節點。
* 名稱不是容器（例如把關鍵字當第一個參數）→ `[ERROR]` 附相近的容器，關鍵字要寫成 `--filter`。
* 沒有目標容器、容器沒在跑、找不到 ros2、逾時（DDS 問題）→ 訊息會說下一步。
