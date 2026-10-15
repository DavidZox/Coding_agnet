---
type: Tool
title: 全域 Topic Metadata 與 Key 檢視
description: 數據的全域索引（時間範圍、每個 Topic 的型別、筆數、頻率、角色與 Key）；看某個 Topic 每個 Key 的型別、維度與類別；預覽原始值。
version: 3.0.0
dependencies: ["docker", "mcap", "rclpy", "rosidl_runtime_py"]
---

# 用途
- 不帶 `--topic`：整份數據的索引（第一次建立後快取在 bag 資料夾的 topic_metadata.json，之後直接讀）。每個 Topic 的角色：
  可分析（有數值／狀態 Key）、Log（/rosout，用 rosout_parser）、只有文字、沒有訊息、無法解碼（自訂訊息要先用 ROS2_workspace_env 確認 Workspace）。
- `--topic`：每個 Key 的 ROS 型別、維度（scalar／vector [n]／matrix／set／map）、類別（數值／向量／狀態／鍵值／文字／時間）與抽樣看到的值。
  DiagnosticArray 這類訊息的序列會依名稱展開（status.level 對每個 status.name 各一項）。
- `--topic --key`：原始值預覽。

# 語法
`EXECUTE: scripts/mcap_analyzer_cmd.py [數據] [--topic TOPIC] [--key KEY --preview N] [--window 開始,結束] [--refresh]`
* 數據：實驗資料夾、bag、切片資料夾、.mcap、實驗名稱或 `latest`；省略＝目前分析的數據。
* `--window`：epoch 秒或 `+秒`，例如 `+10,+20`。`--refresh`：重建索引。`--json`：結構化輸出。

# 範例
`EXECUTE: scripts/mcap_analyzer_cmd.py latest`
`EXECUTE: scripts/mcap_analyzer_cmd.py --topic /system/safety_gate_status`
`EXECUTE: scripts/mcap_analyzer_cmd.py --topic /cmd_vel --key linear.x --preview 20 --window +10,+20`

# 回傳
索引：時間範圍、Topic 總表（型別｜訊息數｜頻率｜起訖｜角色｜Key 摘要）、切片的檔案級 Metadata。量測特徵用 mcap_feature_measure。
