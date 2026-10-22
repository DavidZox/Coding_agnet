---
type: Tool
title: 數據分析（Orchestrator → Workers → Synthesizer）：事實報告
description: 要回答「這段數據發生了什麼、前後有哪些變化」這類需要同時看 Log 與好幾個 Topic 的問題時用：程式去重 Log、量全部 Topic 的事實，Orchestrator 挑相關的 Log 與要說明的 Topic，worker 說明、Synthesizer 整理重點，成為事實報告（不判斷原因）。
version: 3.0.0
dependencies: []
---

# 用途
多 agent 協同的數據分析，一個動作完成，只要有 .mcap 就能用：
1. 資料預備與事實（程式）：Log 去重成唯一訊號 L#（每則附印出它的 檔名:行 函式，錄製時就在 MCAP 裡）；**量全部 Topic 的全部 Key**
   （發布方式、訊息中斷、開始／停止發布、狀態跳轉、數值切換、尖峰、到最後的值），整理成有編號的事實：T#＝Topic、E#＝事件；
   事件與 Log 依時間排成時間線，前後 1 秒內的互相對照（只寫時間差，不說誰造成誰），對不上的照實標出。
2. Orchestrator：同時看去重後的 Log 與全部 Topic 的事實，對齊問題、挑出相關的 Log 訊號，把有變化的 Topic 分派給 worker 說明。
3. Workers：每個 worker 說明一個 Topic（看那個 Topic 的事實與訊息定義的註解），一則一則、引用事件的編號；不看 Log 與問題。
4. Synthesizer：整段數據的重點，一則一則、引用編號（時間與引用的 Log 由程式補上）；不寫原因、不推測。
5. Orchestrator 檢查：相關的 Log 前後有變化、還沒有說明的 Topic，決定要不要補派 worker（最多補一輪）。
說明與重點都經過程式核對（編號、不寫原因、用詞跟引用的事件一致、時間對得上）。

只讀不改，不用使用者確認；通常一分鐘以內。報告只有事實，沒有判斷原因（原因要對照源碼另外分析）。
一次最多分析 3 分鐘（180 秒）的數據：更長的先用 mcap_slicer（`--window +開始,+結束`）切出要看的那段，再用 `--data` 指定切片資料夾。
只要查一個值、看一個 Topic 的問題，直接用 mcap_feature_measure／rosout_parser 就好。

# 語法
`EXECUTE: scripts/analysis_run_cmd.py [--data 數據] [--topic TOPIC]... [--workers N] [--rounds N] "<問題>"`
* 問題：照使用者的原話；沒有具體問題時可以省略（預設：這段錄製期間發生了哪些狀態變化）。
* `--data`：實驗資料夾、bag、切片資料夾、實驗名稱或 `latest`；省略＝目前分析的數據。
* `--topic`：使用者指定一定要說明的 Topic（可以重複）。`--workers`：worker 上限（預設 4；只影響有幾個 Topic 有 worker 的說明，事實是全部 Topic 都量）。
* `--rounds N`：最多幾輪（1＝不補派、2＝可以補派一輪；省略＝照設定，預設 2）。

# 範例
`EXECUTE: scripts/analysis_run_cmd.py --data latest "底盤在錄製中途停下來的前後發生了什麼？什麼時候恢復？"`
`EXECUTE: scripts/analysis_run_cmd.py --data exp_20261014_084506 --topic /cmd_vel "速度指令有哪些變化"`

# 回傳
`[PASS] 📊 數據事實報告`：程式的總覽、重點（一則一則；時間、引用的事件與 Log 的內容由程式列在每一則下面）、有變化的 Topic（類別、發布、變化、到最後的值）、
沒有變化的 Topic、重點沒有引用的時間線（事件與 Log，附前後 1 秒內的對照）、前後沒有任何 Topic 事件的 Log、沒有量的 Topic，以及完整報告的位置
（logs/analysis_jobs/<編號>/report.md）。
依報告回答使用者：引用時間（+秒）、編號（E#、L#、T#）與數值。報告沒有判斷原因：「前後 1 秒內」「同時」只是時間上的先後，不要寫成誰導致、
造成、觸發誰（系統會核對回答）；使用者問「為什麼」時，照事實說明發生了什麼與先後順序，並說明原因要對照源碼另外分析。
