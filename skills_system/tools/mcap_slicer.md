---
type: Tool
title: MCAP 智慧時間切片（依 Log 訊號或時間點）
description: 依 rosout_parser 的 L#、指定時間點或明確的時間窗切出局部 MCAP（toolkit 格式的 sliced_bag_*，附 metadata.yaml 與欄位維度）；可以只切指定的 Topic、帶上時間窗之前的狀態。
version: 3.0.0
dependencies: ["docker", "mcap", "rclpy", "pyyaml"]
---

# 用途
把某個事件前後的數據切成獨立的小 bag，方便分享、用 Foxglove 看，或只分析那一段。
輸出（同 diagnostics_package/toolkit）：實驗資料夾底下 `sliced_bag_<序號>_<秒>_<奈秒>/`：`rosbag2.mcap`、`metadata.yaml`（每個 Topic 的 available_keys、頻率）、檔案級 Metadata `ai_slice_diagnostic_summary`（觸發的訊號、層級、Node、時間窗）、`topic_metadata.json`。
訊號的時間：bag 的 /rosout 用 MCAP log_time；rosout.log 用 Log 的 stamp。時間點不在數據範圍內時不切、回錯誤。

# 語法
`EXECUTE: scripts/mcap_slicer_cmd.py [數據] (--signal L# [--signal L#]... | --at 時間 [--at 時間]... | --window 開始,結束 [--window 開始,結束]...) [--before 5] [--after 5] [--all-occurrences] [--topics TOPIC...] [--with-state] [--out 資料夾]`
* `--signal`：rosout_parser 的編號；同一個訊號出現好幾次時預設只切第一次，`--all-occurrences` 每一次都切（最多 20 片）。
* `--at`：epoch 秒（如 1791967507.72）或 `+秒`（距離數據開頭，如 +15.5）。
* `--before`／`--after`：前後各取幾秒（預設各 5 秒，同 toolkit）。
* `--window 開始,結束`：明確的時間窗（epoch 秒或 `+秒`，例如 `+12,+30`）；不用 --before／--after。
* `--topics`：只切這些 Topic（省略＝全部）。`--with-state`：每個 Topic 另外帶上時間窗之前的最後一則（保留原本的時間戳），只在狀態改變時才發布的 Topic 才知道時間窗開始時的狀態。
* analysis_run 會自動用 `--window --topics --with-state` 替每個時間窗切片（放在 `analysis_slices/<job 編號>/`），不用另外叫。

# 範例
`EXECUTE: scripts/mcap_slicer_cmd.py latest --signal L28 --before 3 --after 10`
`EXECUTE: scripts/mcap_slicer_cmd.py exp_20261014_084506 --at +15.5`
`EXECUTE: scripts/mcap_slicer_cmd.py latest --window +140,+170 --topics /cmd_vel /system/safety_gate_status --with-state`

# 回傳
每一片的資料夾、觸發的訊號、時間窗與訊息數。切片資料夾本身也是數據，可以直接交給 mcap_analyzer／mcap_feature_measure／analysis_run。
