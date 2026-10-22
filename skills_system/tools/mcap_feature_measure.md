---
type: Tool
title: Topic 特徵量測（數值統計、向量分量、狀態跳轉、訊息中斷）
description: 對一個 Topic 的一個或幾個 Key，在時間窗內量測特徵：數值的極值／均值／標準差／斜率／尖峰、向量每個分量、狀態跳轉的時間與前後值、發布方式與訊息中斷。
version: 2.0.0
dependencies: ["docker", "mcap", "rclpy", "rosidl_runtime_py"]
---

# 用途
按需量測（移植自 toolkit 的 mcap_feature_measure.py）：
- 數值：筆數、min／max（與時間）、mean、variance／std、趨勢斜率、最大跳變、尖峰（單獨幾筆跳出去又回來：跟前後 9 筆的中位數差超過殘差典型值的 6 倍、又回到原來的水準、而且夠陡——雜訊、斜坡換成定值、平滑的山頂都不算）；只有幾種值的（速度指令 0／0.1）列每次切換；常數直接標出。
- 向量（vector [n]）：每個分量各自量；也可以只量一個分量（`linear.x`）。
- 狀態（uint8／bool／列舉字串／代碼集合，或相異值 ≤10 的整數）：狀態跳轉（時間、從哪個值到哪個值、集合增減）、各狀態的時間占比。
- 依名稱展開的 Key（DiagnosticArray 的 status.level、status.values）：每個名稱各自量，只列有變化的。
- 每個時間窗另外量訊息流：發布方式（固定頻率／狀態改變時才發布／不定期，由時間與內容判斷）、第一筆與最後一筆的時間。只有固定頻率的 Topic 判斷中斷（間隔超過週期 3 倍、且 ≥0.5 秒）與「中途才開始發布」／「中途停止發布」（頭尾沒有訊息超過週期 10 倍、且 ≥1 秒）；其他發布方式列出每一則的時間（隔很久沒有訊息＝狀態沒變，不是中斷）。
- 狀態 Key：時間窗開頭的狀態沿用時間窗之前的最後一則（只在狀態改變時才發布的 Topic 才不會少算跳轉）；時間窗內沒有新訊息時列出那一則的值。
文字與時間欄位不量測（Log 與自由文字由 rosout_parser 處理）。

# 語法
`EXECUTE: scripts/mcap_feature_measure_cmd.py [數據] --topic TOPIC --key KEY [--key KEY]... [--window 開始,結束]... [--around 時間 --before 秒 --after 秒] [--filter 名稱關鍵字]`
* Key 名稱用 `mcap_analyzer --topic <TOPIC>` 查（state、numeric 這些是 Key 的類別，不是 Key）。好幾個 `--key` 裡有不存在的：認得的照量，最後一行說明略過哪些；全部都不存在才回 [ERROR] 並列出可以量測的 Key。時間可以是 epoch 秒或 `+秒`（距離數據開頭）；不給時間窗＝整份數據。
* `--around <時間>`：以該時間為錨點，前後各取 --before／--after 秒（預設 5）。`--all-entries`：依名稱展開的 Key 連不變的項目也列。`--json`：結構化輸出。

# 範例
`EXECUTE: scripts/mcap_feature_measure_cmd.py --topic /cmd_vel --key linear --key angular`
`EXECUTE: scripts/mcap_feature_measure_cmd.py latest --topic /system/safety_gate_status --key mode --key stop_reasons --around +0.75 --before 2 --after 20`
`EXECUTE: scripts/mcap_feature_measure_cmd.py --topic /diagnostics_agg --key status.level --filter Battery --window +10,+40`

# 回傳
每個時間窗：訊息筆數（第一筆、最後一筆）、發布方式、中斷／中途開始或停止發布（固定頻率的）或每一則的時間（其他的），每個 Key 的特徵；最後兩行：「程式判斷的異常（訊息中斷）」只列訊息中斷；「量到的變化（事實，不代表異常）」彙整尖峰、狀態跳轉、數值切換、中途開始／停止發布。`--json` 的 `anomalies` 是前者、`flags` 是全部。[+秒]＝距離數據開頭（跟 rosout_parser 同一個基準）。
