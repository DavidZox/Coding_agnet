---
type: Tool
title: ROS 2 MCAP 切片 Metadata 與局部數據解析工具
description: 讀取切片後的 Metadata 摘要與可用 Keys，支援精準鎖定 Topic 與欄位進行時序數據展開。
version: 1.1.0
dependencies: ["mcap", "rclpy", "yaml"]
---

# 用途
針對切片後的 MCAP 資料夾（`sliced_bag_*`），快速讀取 `metadata.yaml` 中的 AI 診斷註記、Topic 頻率與預先萃取好的可用欄位（`available_keys`）。支援讓 AI Agent 或使用者以編號清單鎖定特定 Topic 與 Key，精準提取並展開前幾筆時序數據。

# 語法
`EXECUTE: scripts/mcap_analyzer_cmd.py <sliced_bag_directory>`
* `<sliced_bag_directory>`：切片後的資料夾路徑（例如 `toolkit/experiment_logs/exp_xxx/sliced_bag_1_...`）。

# 範例
* 分析指定的切片資料夾：
  `EXECUTE: scripts/mcap_analyzer_cmd.py toolkit/experiment_logs/exp_20261013_120000/sliced_bag_1_1791873116_289`

# 回傳
* 成功：回傳區段統計摘要、檔案級 Metadata 註記、可用 Topic 與欄位 Keys 清單，以及指定欄位的時序數據展開結果。
* 失敗：`[ERROR] 原因`