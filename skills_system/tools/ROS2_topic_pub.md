---
type: Tool
title: ROS 2 發布訊息
description: 對 ROS 2 topic 發布訊息（預設一次）；會影響正在跑的系統，執行前會請使用者確認。
version: 1.2.0
dependencies: ["docker", "ros2"]
---

# 用途
使用者明確要求「發一則訊息」時用（例如手動回交握、送一個指令）。型別用 `ROS2_topic_list --types` 查。調度系統的交握優先用 rmf_handshake。
發布前先看訂閱者：最多等 20 秒（`--times N` 再加 N 秒）配對，等不到就不發、說是「沒有訂閱者」還是「QoS 不相容」；訂閱端要求 TRANSIENT_LOCAL 時自動用 transient_local。整體逾時 60 秒。

# 語法
`EXECUTE: scripts/ROS2_topic_pub_cmd.py [容器名稱] <topic> <訊息型別> '<YAML 內容>' [--times N] [--qos 設定]`
* 型別寫完整（`std_msgs/msg/String`、`fih_rmf_msgs/msg/HandshakeState`）；內容是 YAML，用單引號包住（預設值寫 `'{}'`）。topic 少了開頭的 / 會自動補。
* `--times N`：每秒一次共 N 次，上限 30（超過回 `[ERROR]`、不發）。`--qos`：`transient_local`、`volatile`、`reliable`、`best_effort`、`sensor_data`（逗號合併）。

# 範例
`EXECUTE: scripts/ROS2_topic_pub_cmd.py rmf_sim /tb2/handshake_states fih_rmf_msgs/msg/HandshakeState '{is_authored: "yes"}'`

# 回傳
`[PASS] 已對 /topic（型別）發布 N 次（訂閱者 M 個；QoS…；容器…，ROS_DOMAIN_ID…）：內容`。

# 異常
* 不認得訊息型別 → `ROS2_topic_list --types` 看型別；自訂型別先 `ROS2_workspace_env` 確認 Workspace。內容跟欄位對不上 → 照提示看欄位。
* 沒有訂閱者 → 確認接收端 node 在跑、topic 名稱對；有訂閱者但型別跟你給的不同 → `[ERROR]` 寫出訂閱端的型別，改用那個型別的欄位重新發布；型別一樣卻配對不上 → 加 `--qos transient_local` 或 `--qos reliable` 重試。
* 第一個參數不是容器 → `[ERROR]` 附相近的容器。使用者拒絕確認就不會發布，不要原樣重送。
