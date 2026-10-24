---
type: Tool
title: 數據分析：事實報告（全部由程式做）
description: 要回答「這段數據發生了什麼、前後有哪些變化」這類需要同時看 Log 與好幾個 Topic 的問題時用：程式去重 Log、量全部 Topic 的事實、照規則寫重點，成為有編號的事實報告（不判斷原因）；依報告回答。
version: 4.0.1
dependencies: []
---

# 用途
一個動作完成、全部由程式做（不呼叫模型），只要有 .mcap 就能用：
1. Log 去重成唯一訊號 L#（每則附印出它的 檔名:行 函式，錄製時就在 MCAP 裡）。
2. **量全部 Topic 的全部 Key**（發布方式、訊息中斷、開始／停止發布、狀態跳轉、數值切換、尖峰、到最後的值），整理成有編號的事實：
   T#＝Topic、E#＝事件；事件與 Log 依時間排成時間線，前後 1 秒內的互相對照（只寫時間差，不說誰造成誰），對不上的照實標出。
3. 重點：每個重要的時間點（事件與 WARN 以上的 Log，1 秒內的算一個）一則，那一刻全部的 Log 與事件列在下面；另有到最後跟開頭不同的值、
   只有數值連續變動的 Topic、整段沒有變化的 Topic。

只讀不改，不用使用者確認；通常幾秒鐘。報告只有事實，沒有判斷原因（原因要對照源碼另外分析）。你依報告回答使用者的問題；
要細看某個 Topic、某一段時間、某則 Log，再用 mcap_feature_measure、mcap_analyzer、rosout_parser、mcap_slicer。
一次最多分析 3 分鐘（180 秒）的數據：更長的先用 mcap_slicer（`--window +開始,+結束`）切出要看的那段，再用 `--data` 指定切片資料夾。
只要查一個值、看一個 Topic 的問題，直接用 mcap_feature_measure／rosout_parser 就好。

# 語法
`EXECUTE: scripts/analysis_run_cmd.py [--data 數據] [--topic TOPIC]... "<問題>"`
* 問題：照使用者的原話（記在報告裡）；沒有具體問題時可以省略（預設：這段錄製期間發生了哪些狀態變化）。
* `--data`：實驗資料夾、bag、切片資料夾、實驗名稱或 `latest`；省略＝目前分析的數據。
* `--topic`：使用者特別問到的 Topic（可以重複）：它的事實完整列在報告最前面。

# 範例
`EXECUTE: scripts/analysis_run_cmd.py --data latest "底盤在錄製中途停下來的前後發生了什麼？什麼時候恢復？"`
`EXECUTE: scripts/analysis_run_cmd.py --data exp_20250301_101500 --topic /battery_state "電壓有哪些變化"`

# 回傳
`[PASS] 📊 數據事實報告`：總覽、指定的 Topic、重點（一則一則；時間、引用的 Log 與事件的內容列在每一則下面）、有變化的 Topic（類別、發布、變化、
到最後的值）、沒有變化的 Topic、重點沒有引用的時間線（附前後 1 秒內的對照）、前後沒有任何 Topic 事件的 Log、沒有量的 Topic，以及完整報告的
位置（logs/analysis_jobs/<編號>/report.md）。
依報告回答使用者：引用時間（+秒）、編號（E#、L#、T#）與數值。報告沒有判斷原因：「前後 1 秒內」「同時」只是時間上的先後，不要寫成誰導致、
造成、觸發誰（系統會核對回答，寫的變化與值也要跟報告的事實一致）；使用者問「為什麼」時，照事實說明發生了什麼與先後順序，並說明原因要對照源碼另外分析。

# 異常
* 數據超過 3 分鐘：回 `[ERROR]`，先用 mcap_slicer 切。
* Topic 都無法解碼：回 `[ERROR]`，先用 ROS2_workspace_env 確認 Workspace（自訂訊息要有建好、載入的套件）。
* `--workers`、`--rounds`、`--source`、`--before` 這些舊選項已經拿掉：回 `[ERROR]` 說明，不要再用。
