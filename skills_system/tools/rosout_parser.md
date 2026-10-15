---
type: Tool
title: Log 智慧過濾（rosout 去重成唯一訊號）
description: 把 /rosout 重複出現的 Log 合併成唯一訊號（L#：層級、Node、次數、每一次的時間戳），看全局、找異常的時間點。
version: 3.0.0
dependencies: ["docker", "rclpy", "mcap"]
---

# 用途
解析數據裡的 Log（預設用 bag 裡的 /rosout：最完整、時間跟其他 Topic 同一個時鐘；沒有就用實驗資料夾的 rosout.log），
同一個 Node、同一層級、同一句話（只差在數字也算同一句）合成一個**唯一訊號**，依第一次出現的時間編號 L1、L2…。
編號在篩選之前就編好，`mcap_slicer --signal L#` 與 `analysis_run` 用同一套編號。預設略過錄製工具 rosbag2 自己的 Log。

# 語法
`EXECUTE: scripts/rosout_parser_cmd.py [數據] [--level WARN] [--level ERROR] [--node 關鍵字] [--grep 關鍵字] [--top N] [--events]`
* 數據：實驗資料夾、bag 資料夾、切片資料夾、.mcap、rosout.log、實驗名稱或 `latest`；省略＝目前分析的數據。
* `--level` 可以重複；`--node`、`--grep` 不分大小寫；`--top` 預設 60。
* `--events`：不合併，逐則列出（每則標它屬於哪個 L#）。`--exact`：逐字比對才算同一句。`--all-nodes`：連 rosbag2 的 Log 也列。
* `--source bag|log`：指定 Log 來源（預設 auto）。`--json`：結構化輸出。

# 範例
`EXECUTE: scripts/rosout_parser_cmd.py latest`
`EXECUTE: scripts/rosout_parser_cmd.py exp_20261014_084506 --level WARN --level ERROR`

# 回傳
標頭算好：幾則 Log → 幾個唯一訊號、各層級的數量、來源與時間基準。每一行：`L# 層級 ×次數 首次[+秒] ～ 末次 Node：訊息`（[+秒]＝距離數據開頭）。
要看某個訊號前後的數據：`mcap_feature_measure --around <秒>` 或 `mcap_slicer --signal L#`。
