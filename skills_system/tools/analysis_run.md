---
type: Tool
title: 數據診斷（Orchestrator → Workers → Synthesizer）
description: 要回答「這段數據發生了什麼、為什麼」這類需要同時看 Log 與好幾個 Topic 的問題時用：系統先去重 Log、讀 Topic Metadata，Orchestrator 分派 Topic，多個 worker 平行量測，Synthesizer 寫根因診斷報告。
version: 1.0.0
dependencies: []
---

# 用途
多 agent 協同的數據診斷，一個動作完成：
1. 資料預備（程式）：Log 去重成唯一訊號、讀全域 Topic Metadata 索引；有設定源碼目錄（`/analysis_source`）時再整理源碼脈絡：Log 的源碼位置（/rosout 的 file:line）對回程式碼、這次在執行的節點的發布／訂閱關係（每個 Topic 依賴哪些輸入 Topic）、Log 裡的代碼在源碼的條件，交給 Orchestrator、Worker、Synthesizer。
2. Orchestrator：同時看去重後的 Log 與 Topic Metadata，對齊問題、挑出相關的 Log 訊號（系統換成精確的時間窗）、把不同的 Topic 指派給不同的 worker。
3. 動態時間切片（程式）：每個時間窗用 mcap_slicer 切一片（只含指派的 Topic，每個 Topic 再帶上時間窗之前的最後一則），worker 只讀切片——數據再長也只看關鍵的那幾段。整段數據（沒有相關訊號）不切。切片留在數據資料夾的 `analysis_slices/<job 編號>/`。
4. Workers：每個 worker 只負責一個 Topic，自己決定量測哪些 Key（數值統計、狀態跳轉），產出 Frontmatter Markdown 的局部報告；不看 Log 字串。
5. Synthesizer：把 Log 的時間線與各 Topic 的量測結果做因果拼圖，寫根因診斷報告（結論、根因、時間線、證據、尚未確認、建議）；程式再校正時間線、檢查沒錄到的輸入與背景條件。
只讀不改，不用使用者確認；通常一到幾分鐘。只要查一個值、看一個 Topic 的問題，直接用 mcap_feature_measure／rosout_parser 就好。

# 語法
`EXECUTE: scripts/analysis_run_cmd.py [--data 數據] [--topic TOPIC]... [--workers N] [--before 秒] [--after 秒] "<問題>"`
* 問題：照使用者的原話；沒有具體問題時可以省略（預設：這段錄製期間發生了什麼異常、根因是什麼）。
* `--data`：實驗資料夾、bag、切片資料夾、實驗名稱或 `latest`；省略＝目前分析的數據。
* `--topic`：使用者指定一定要分析的 Topic（可以重複）。`--workers`：worker 上限（預設 4）。`--before`／`--after`：時間窗預設秒數。
* `--source <源碼目錄>`／`--no-source`：這一次用（或不用）受測系統的源碼目錄（ROS 2 工作區的 src），省略＝照設定。

# 範例
`EXECUTE: scripts/analysis_run_cmd.py --data latest "底盤為什麼在錄製中途停下來？什麼時候恢復？"`
`EXECUTE: scripts/analysis_run_cmd.py --data exp_20261014_084506 --topic /cmd_vel "速度指令有沒有異常"`

# 回傳
`[PASS] 📊 數據診斷報告`：結論、根因與信心、時間線、證據、尚未確認、建議、每個 worker 的結果與完整報告的位置（logs/analysis_jobs/<編號>/report.md）。
依報告回答使用者：引用時間（+秒）、Log 編號與數值；尚未確認的照實說。
