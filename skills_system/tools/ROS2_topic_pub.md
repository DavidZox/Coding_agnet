---
type: Tool
title: ROS 2 發布訊息
description: 對 ROS 2 topic 發布訊息（預設一次）；會影響正在跑的系統，執行前會請使用者確認。
version: 1.0.0
dependencies: ["docker", "ROS 2（容器內）"]
---

# 用途
使用者明確要求「發一則訊息」時用（例如手動回交握、送一個指令）。不確定訊息型別時先用 ROS2_topic_list／ROS2_node_info 查。
調度系統的交握優先用 rmf_handshake（它會先判斷原因，也會走 manual_trigger）。

# 語法
`EXECUTE: scripts/ROS2_topic_pub_cmd.py [容器名稱] <topic> <訊息型別> '<YAML 內容>' [--times N]`
* 訊息型別寫完整（`std_msgs/msg/String`、`fih_rmf_msgs/msg/HandshakeState`）；內容是 YAML，用單引號包住。預設發一次，`--times N` 每秒一次共 N 次。

# 範例
`EXECUTE: scripts/ROS2_topic_pub_cmd.py rmf_sim /tb2/handshake_states fih_rmf_msgs/msg/HandshakeState '{is_authored: "yes"}'`

# 回傳
`[PASS] 已對 /topic（型別）發布 N 次：內容`。

# 異常
不認得訊息型別、內容跟型別對不上、沒有訂閱者一直等：`[ERROR]` 說明原因。
