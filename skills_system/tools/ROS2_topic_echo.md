---
type: Tool
title: ROS2 話題內容（單筆或一段時間的量測）
description: 讀取指定 topic 的一筆訊息，或用 --duration 觀察一段時間：發布方式與中斷、每個欄位的變化（狀態跳轉的時間、數值統計、尖峰）、--where 門檻判斷（容器可省略＝目標容器）。
version: 2.0.1
dependencies: ["docker", "ros2"]
---

# 用途
在容器內直接訂閱 topic（型別自動查、QoS 依 publisher 自動配，只在狀態改變時才發布的 topic 也拿得到最後一則）。
- **問「現在」的值或狀態**（「amr_07 電量剩多少」「讀一下 /odom」）：**不加 `--duration`**，讀一筆就結束，印完整的 YAML（字串不截斷）。直接執行，不要先問使用者要觀察多久。
- **問「一段時間內」的變化**（「觀察 10 秒」「有沒有變化」「頻率多少」「什麼時候變成 RUNNING」）才加 `--duration 秒`：量測方式跟錄好的數據（mcap_feature_measure）一樣——
  發布方式（固定頻率／狀態改變時才發布／不定期）與中斷、每個欄位的變化（狀態跳轉的時間與前後的值、數值的極值與時間、平均、斜率、尖峰）、字串裡的 JSON 欄位
  （`data.mode`）、依名稱展開的項目（DiagnosticArray 的 `status.level[motor_left]`），最後附前後幾則原始訊息。使用者沒說秒數時用 10 秒。

# 語法
`EXECUTE: scripts/ROS2_topic_echo_cmd.py [container_name] <topic_name> [timeout_seconds] [--duration 秒] [--where 欄位<值]... [--raw N]`
* `container_name`：可省略＝目標容器。`topic_name` 以 `/` 開頭。
* `timeout_seconds`：單筆模式等第一則的上限，預設 15（1～570）；低頻 topic 加大。
* `--duration 秒`（2～300）：只有問一段時間內的變化才加；高頻 topic 縮短秒數。
* `--where 欄位<值`（可重複，要搭配 `--duration`）：「有沒有低於／超過、第一次是什麼時候、持續多久」由腳本算。運算子 `< <= > >= == !=`；欄位名稱同量測結果
  （`voltage`、`pose.pose.position.x`、`status.level[motor_left]`、`data.mode`）；`==` 可以比文字與 true／false；陣列（ranges）任一個元素符合就算。
* `--raw N`：附幾則原始訊息（前一半、後一半），預設 10、上限 100。

# 範例
`EXECUTE: scripts/ROS2_topic_echo_cmd.py /battery_state`（現在的值：讀一筆）
`EXECUTE: scripts/ROS2_topic_echo_cmd.py /odom --duration 10`（觀察 10 秒的變化）
`EXECUTE: scripts/ROS2_topic_echo_cmd.py /battery_state --duration 20 --where voltage<24`
`EXECUTE: scripts/ROS2_topic_echo_cmd.py ros_box /diagnostics 60`（讀一筆，低頻：最多等 60 秒）

# 回傳
單筆：`[PASS] <topic>（型別）的一筆訊息（等了 x 秒；publisher 數、QoS）：` + YAML。
一段時間：第一行 `[PASS] 觀察 '<topic>'（型別）N 秒：收到 M 則，<發布方式>…；有變化的欄位 a 個、固定不變 b 個`，接著 `## 訊息流`、`## 有變化的欄位`、
`## 固定不變`、`## 條件`（`條件 …：M 筆中 K 筆符合；第一筆符合 #k +秒（值）；前一筆 …；符合的時段…`）、`## 原始訊息`（`--- #序號 +秒`）。[+秒]＝距離開始觀察。
結論直接引用這些行，不要自己逐則比較。沒收到訊息也是 `[PASS]`，並寫原因（沒有 publisher、低頻、QoS 不相容）。

# 異常
* `ROS 圖上沒有 topic …`：附名稱相近的 topic；用 `ROS2_topic_list` 確認；只看得到 /rosout、/parameter_events 時用 `ROS2_domain_id` 確認 domain。
* `載入不到訊息型別`：自訂訊息，先用 `ROS2_workspace_env` 確認 Workspace 再觀察。
* `--where 找不到欄位`：訊息會列出可以用的名稱，照抄重送。
* 沒有目標容器、容器不存在、容器沒有 ROS 2：訊息會指出原因（docker_containers／docker_open 選容器）。
