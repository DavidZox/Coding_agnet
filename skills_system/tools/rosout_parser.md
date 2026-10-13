---
type: Tool
title: ROS 2 /rosout 系統日誌解析與事件檢視器
description: 解析實驗記錄中的 rosout.log，依日誌等級（INFO, WARN, ERROR）過濾並列出帶時間戳的事件清單。
version: 1.1.0
dependencies: ["python3"]
---

# 用途
讀取實驗目錄下的 `rosout.log`，自動解析並統計各日誌層級（INFO、WARN、ERROR 等）的訊息筆數。支援讓 AI Agent 快速瀏覽異常事件時間戳與內容，作為後續時間切片（`mcap_slicer`）的基準依據。

# 語法
`EXECUTE: scripts/rosout_parser_cmd.py <experiment_dir>`
* `<experiment_dir>`：包含 `rosout.log` 的實驗資料夾路徑。

# 範例
* 解析並檢視實驗日誌：
  `EXECUTE: scripts/rosout_parser_cmd.py toolkit/experiment_logs/exp_20261013_120000`

# 回傳
* 成功：回傳各 Log Level 的統計總數，以及詳細的時間戳記、層級與訊息內容清單。
* 失敗：`[ERROR] 原因`