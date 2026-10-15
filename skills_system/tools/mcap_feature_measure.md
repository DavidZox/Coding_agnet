---
type: Tool
title: Topic 特徵量測（數值統計、向量分量、狀態跳轉、訊息中斷）
description: 對一個 Topic 的一個或幾個 Key，在時間窗內量測特徵：數值的極值／均值／標準差／斜率／尖峰、向量每個分量、狀態跳轉的時間與前後值、訊息頻率與中斷。
version: 1.0.0
dependencies: ["docker", "mcap", "rclpy", "rosidl_runtime_py"]
---

# 用途
按需量測（移植自 toolkit 的 mcap_feature_measure.py）：
- 數值：筆數、min／max、mean、variance／std、趨勢斜率、尖峰（離均值 >2.5σ）、最大跳變；常數直接標出。
- 向量（vector [n]）：每個分量各自量；也可以只量一個分量（`linear.x`）。
- 狀態（uint8／bool／列舉字串／代碼集合，或相異值 ≤10 的整數）：狀態跳轉（時間、從哪個值到哪個值、集合增減）、各狀態的時間占比。
- 依名稱展開的 Key（DiagnosticArray 的 status.level、status.values）：每個名稱各自量，只列有變化的。
- 每個時間窗另外量訊息頻率與中斷（間隔超過正常週期 3 倍）。
文字與時間欄位不量測（Log 與自由文字由 rosout_parser 處理）。

# 語法
`EXECUTE: scripts/mcap_feature_measure_cmd.py [數據] --topic TOPIC --key KEY [--key KEY]... [--window 開始,結束]... [--around 時間 --before 秒 --after 秒] [--filter 名稱關鍵字]`
* Key 名稱用 `mcap_analyzer --topic <TOPIC>` 查。時間可以是 epoch 秒或 `+秒`（距離數據開頭）；不給時間窗＝整份數據。
* `--around <時間>`：以該時間為錨點，前後各取 --before／--after 秒（預設 5）。`--all-entries`：依名稱展開的 Key 連不變的項目也列。`--json`：結構化輸出。

# 範例
`EXECUTE: scripts/mcap_feature_measure_cmd.py --topic /cmd_vel --key linear --key angular`
`EXECUTE: scripts/mcap_feature_measure_cmd.py latest --topic /system/safety_gate_status --key mode --key stop_reasons --around +0.75 --before 2 --after 20`
`EXECUTE: scripts/mcap_feature_measure_cmd.py --topic /diagnostics_agg --key status.level --filter Battery --window +10,+40`

# 回傳
每個時間窗：訊息筆數／頻率／中斷，每個 Key 的特徵；最後一行「異常指標（程式判斷）」彙整尖峰、狀態跳轉與中斷。[+秒]＝距離數據開頭（跟 rosout_parser 同一個基準）。
