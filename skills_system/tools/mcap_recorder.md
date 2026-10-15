---
type: Tool
title: ROS 2 實驗數據錄製（MCAP＋rosout.log＋Topic Metadata 索引）
description: 在目標容器內定時錄製 ROS 2 Topic，產生 toolkit 格式的實驗資料夾，錄完自動建立全域 Topic Metadata 索引。
version: 3.0.0
dependencies: ["docker", "ros2", "rosbag2-storage-mcap", "mcap"]
---

# 用途
在目標容器內執行 `ros2 bag record -s mcap`，同時把 `/rosout` 經 rosout_formatter 存成一行一則的 `rosout.log`；錄完建立全域 Topic Metadata 索引（之後的分析直接讀，不用再掃）。
輸出（同 diagnostics_package/toolkit）：`<數據根目錄>/exp_YYYYmmdd_HHMMSS/` 底下 `bag/`（mcap、metadata.yaml、topic_metadata.json）、`rosout.log`、`terminal.log`、`recording_info.json`。
錄完的實驗會成為「目前分析的數據」（之後的數據技能可以省略路徑）。

# 語法
`EXECUTE: scripts/mcap_recorder_cmd.py (--topics TOPIC... | --preset core | --all) --duration 秒 [--out-root 數據根目錄] [--name 名稱] [--no-rosout]`
* 錄哪些 Topic（三選一，照使用者的說法）：
  - 使用者說「全部」「所有 Topic」→ `--all`（錄得到的 Topic 全部錄，診斷時最完整）。
  - 使用者說「核心 Topic」→ `--preset core`＝toolkit 的預設核心組合（/sensor_scan /cmd_vel /cmd_vel_raw /diagnostics /diagnostics_agg /system/safety_command /tf /tf_static）。
  - 使用者點名 Topic → `--topics /a /b`。
* `--duration`：一定要定時（1～480 秒）。
* `--name`：實驗資料夾的名稱（建在數據根目錄底下；省略＝`exp_年月日_時分秒`）。使用者說「資料夾名稱用 X」「命名為 X」→ `--name X`。
* `--out-root`：換數據根目錄（絕對路徑）。省略＝系統設定的數據根目錄；沒設定時在容器的 /workspace 底下找 `experiment_logs`。主機路徑會自動換成容器內路徑。資料夾名稱不要放這裡。
* 預設會加錄 /rosout；`--no-rosout` 不錄 Log。

# 範例
`EXECUTE: scripts/mcap_recorder_cmd.py --all --duration 30`（全部 Topic）
`EXECUTE: scripts/mcap_recorder_cmd.py --preset core --duration 30`（核心 Topic）
`EXECUTE: scripts/mcap_recorder_cmd.py --all --duration 40 --name exp_event_test`（全部 Topic，資料夾名稱 exp_event_test）
`EXECUTE: scripts/mcap_recorder_cmd.py --topics /cmd_vel /odom /battery_state --duration 20 --name exp_battery_test`

# 回傳
`[PASS] 錄製完成`、資料夾、每個 Topic 錄到幾則、沒有錄到訊息的 Topic（錄製期間沒有 publisher）、索引位置。
`[ERROR]`：時長不合法、資料夾已存在、沒有產生 mcap（附 terminal.log 最後幾行）。
