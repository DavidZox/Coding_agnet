---
type: Tool
title: 數據分析（Orchestrator → Workers → Synthesizer）：事實報告
description: 要回答「這段數據發生了什麼、前後有哪些變化」這類需要同時看 Log 與好幾個 Topic 的問題時用：系統先去重 Log、讀 Topic Metadata，Orchestrator 分派 Topic，多個 worker 平行量整段數據，程式整理成事實報告（不判斷原因）。
version: 2.0.0
dependencies: []
---

# 用途
多 agent 協同的數據分析，一個動作完成，只要有 .mcap 就能用：
1. 資料預備（程式）：Log 去重成唯一訊號（每則附印出它的 檔名:行 函式，錄製時就在 MCAP 裡）、讀全域 Topic Metadata 索引。
2. Orchestrator：同時看去重後的 Log 與 Topic Metadata，對齊問題、挑出相關的 Log 訊號，把不同的 Topic 指派給不同的 worker。
3. Workers：每個 worker 只負責一個 Topic，自己決定量測哪些 Key（數值統計、狀態跳轉），量的是整段數據；只寫量到的現象，不看 Log 字串。
4. 事實（程式）：每個 Topic 的類別（沒有變化／狀態改變／數值切換／開始或停止發布／訊息中斷…）、事件與到最後的值；Topic 的事件與 Log 依時間排成時間線，前後 1 秒內的 Log 與變化互相對照（只寫時間差，不說誰造成誰），對不上的照實標出。
5. Synthesizer：把事實寫成摘要（不寫原因、不推測）。
6. Orchestrator 檢查：WARN 以上或相關的 Log 前後量到的 Topic 都沒有變化時，決定要不要補量還沒量的 Topic（最多補一輪）。

只讀不改，不用使用者確認；通常一分鐘以內。報告只有事實，沒有判斷原因（原因要對照源碼另外分析）。
一次最多分析 3 分鐘（180 秒）的數據：更長的先用 mcap_slicer（`--window +開始,+結束`）切出要看的那段，再用 `--data` 指定切片資料夾。
只要查一個值、看一個 Topic 的問題，直接用 mcap_feature_measure／rosout_parser 就好。

# 語法
`EXECUTE: scripts/analysis_run_cmd.py [--data 數據] [--topic TOPIC]... [--workers N] [--rounds N] "<問題>"`
* 問題：照使用者的原話；沒有具體問題時可以省略（預設：這段錄製期間發生了哪些狀態變化）。
* `--data`：實驗資料夾、bag、切片資料夾、實驗名稱或 `latest`；省略＝目前分析的數據。
* `--topic`：使用者指定一定要分析的 Topic（可以重複）。`--workers`：worker 上限（預設 6）。
* `--rounds N`：最多幾輪（1＝不補量、2＝可以補量一輪；省略＝照設定，預設 2）。

# 範例
`EXECUTE: scripts/analysis_run_cmd.py --data latest "底盤在錄製中途停下來的前後發生了什麼？什麼時候恢復？"`
`EXECUTE: scripts/analysis_run_cmd.py --data exp_20261014_084506 --topic /cmd_vel "速度指令有哪些變化"`

# 回傳
`[PASS] 📊 數據事實報告`：摘要、各 Topic 的結果（類別、發布、變化、到最後的值）、時間線的重點（Topic 的事件與 Log，附前後 1 秒內的對照）、前後量到的 Topic 都沒有變化的 Log、沒有分析的 Topic，以及完整報告的位置（logs/analysis_jobs/<編號>/report.md）。
依報告回答使用者：引用時間（+秒）、Log 編號與數值。報告沒有判斷原因：使用者問「為什麼」時，照事實說明發生了什麼與先後順序，並說明原因要對照源碼另外分析。
