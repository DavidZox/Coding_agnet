---
type: Tool
title: ROS 2 MCAP 實驗數據錄製工具
description: 支援參數化或互動式的 ROS 2 實驗數據錄製，自動封裝 MCAP 並記錄 /rosout 系統日誌與終端輸出。
version: 1.1.0
dependencies: ["ros2", "mcap"]
---

# 用途
在指定的 ROS 2 系統中錄製指定的 Topic 或全部 Topic（`-a`），並同時建立獨立的系統 Log 檔（`rosout.log`）與終端輸出（`terminal.log`）。支援 AI Agent 非互動式參數呼叫或手動互動選單。逾時依設定而定。

# 語法
`EXECUTE: scripts/mcap_recorder_cmd.py [--topics TOPIC [TOPIC ...]] [--all] [--duration SECONDS] [--toolkit_dir PATH]`
* `--topics`：欲錄製的 Topic 清單，以空格分隔。
* `--all`：錄製系統中所有 Topic（相等於 `-a`）。
* `--duration`：定時錄製秒數；若設為 `0` 則持續錄製直到手動中斷。
* `--toolkit_dir`：工具箱根目錄路徑（選填）。

# 範例
* 定時錄製特定 Topic 10 秒：
  `EXECUTE: scripts/mcap_recorder_cmd.py --topics /cmd_vel /diagnostics --duration 10`
* 錄製所有 Topic 直到手動停止：
  `EXECUTE: scripts/mcap_recorder_cmd.py --all`

# 回傳
* 成功：`[PASS] 錄製結束！實驗資料已完整封裝於: <target_dir>`
* 失敗：`[ERROR] 原因`