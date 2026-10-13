---
type: Tool
title: ROS 2 MCAP 智慧時間切片與 AI 特徵註記工具
description: 解析實驗 rosout.log 標記，依時間窗口切片 MCAP 檔案，並自動萃取可用 Keys 與統計特徵寫入 Metadata。
version: 1.1.0
dependencies: ["mcap", "yaml"]
---

# 用途
讀取實驗資料夾中的 `rosout.log` 與原始 MCAP 檔案，根據指定的日誌時間戳與前後緩衝區間進行高效切片。同時自動萃取每個 Topic 的訊息數量、平均頻率（`ai_features`）以及訊息結構可用欄位（`available_keys`），寫入 `metadata.yaml` 供 AI Agent 進行零反序列化推理。

# 語法
`EXECUTE: scripts/mcap_slicer_cmd.py <experiment_dir> <bag_name>`
* `<experiment_dir>`：包含 `rosout.log` 與 bag 資料夾的實驗目錄。
* `<bag_name>`：原始 bag 所在的子資料夾名稱（通常為 `bag`）。

# 範例
* 執行切片處理：
  `EXECUTE: scripts/mcap_slicer_cmd.py toolkit/experiment_logs/exp_20261013_120000 bag`

# 回傳
* 成功：`[PASS] 切片完成！共匯出 <count> 筆訊息，已自動萃取 Topic Keys 並寫入 Metadata。`
* 失敗：`[ERROR] 原因`