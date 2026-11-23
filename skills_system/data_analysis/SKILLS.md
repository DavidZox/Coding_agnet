# data_analysis：錄製的數據

錄製的 ROS 2 數據（MCAP 與裡面的 /rosout、topic）：錄、看有什麼、Log、量測、切片，以及要同時看 Log 與好幾個 Topic 的數據分析（程式整理的事實報告）。
不包含：正在跑的系統（容器、現在的 topic 與參數：robotics_infra）、工作目錄裡的文字 log 檔與程式碼（repo_analysis）、調度系統（rmf_dispatch）。

## 做法
- **數據在哪裡**：數據技能都在目標容器內讀檔；「數據」可以是實驗資料夾、bag 資料夾、切片資料夾、`.mcap`、實驗名稱（相對於數據根目錄）或 `latest`（最新的實驗），主機路徑會自動換成容器內路徑。使用者沒指定時用 Current Agent State 的 CURRENT_ANALYSIS_DATA；兩者都沒有時用 `latest`，或問使用者要哪一份。
- **依問題選技能**（一兩步做得完的直接用對應的技能）：
  - 錄數據：`mcap_recorder`（一定要有時長；使用者沒說錄多久、錄哪些 Topic 才先問）：「全部／所有 Topic」用 `--all`、「核心 Topic」用 `--preset core`、點名的用 `--topics`；資料夾名稱用 `--name`。
  - 數據裡有什麼、有哪些 Topic／Key：`mcap_analyzer`（`--topic` 看某個 Topic 的 Key）。
  - Log、錯誤訊息、事件發生的時間點：`rosout_parser`（重複的 Log 已合併成唯一訊號 L#）。
  - 某個 Topic／Key 的數值範圍、尖峰、狀態有沒有跳轉、有沒有中斷、什麼時候第一次低於／超過某個值：`mcap_feature_measure`（`--where 欄位<值`；Key 名稱不知道就先 `mcap_analyzer --topic`）。
  - 事件前後的數據切出來（給別人看、用 Foxglove 看、只分析其中一段）：`mcap_slicer --signal L#` 或 `--window +開始,+結束`。
  - **「發生了什麼、前後有哪些變化、什麼時候恢復」這種要同時看 Log 與好幾個 Topic 的問題**：用 `analysis_run`，args＝`--data <數據>` 加上使用者的原話（用雙引號）。它只讀不改，不用先問使用者要不要執行；系統會自動去重 Log、量全部 Topic 的事實，由程式整理成有編號的事實報告（重點、各 Topic 的結果、時間線）。依報告回答；要細看某個 Topic、某一段時間或某則 Log，再用下面對應的數據技能。一次最多 3 分鐘的數據，更長的先用 `mcap_slicer --window` 切出要看的那段，再對切片執行。
- **回答數據問題**：引用工具算好的數字、時間（+秒＝距離數據開頭）與編號（L#＝Log、E#＝事件、T#＝Topic），不要自己估算。analysis_run 的報告只有事實（量到什麼、什麼時候、Log 的原文），沒有判斷原因：照報告的事實回答；使用者問「為什麼」時，說明發生了什麼、先後順序，並說明原因要對照源碼另外分析，不要自己推因果、也不要說成已證實。
- 時間的寫法：epoch 秒（1791967507.72）或 `+秒`（距離數據開頭，例如 `+15.5`）；時間窗 `--window +10,+20`。

## 複合技能
（還沒有：領域 session 直接用下面的工具）

## 工具
- [analysis_run](../tools/analysis_run.md)
- [mcap_recorder](../tools/mcap_recorder.md)
- [rosout_parser](../tools/rosout_parser.md)
- [mcap_analyzer](../tools/mcap_analyzer.md)
- [mcap_feature_measure](../tools/mcap_feature_measure.md)
- [mcap_slicer](../tools/mcap_slicer.md)
- [docker_containers](../tools/docker_containers.md)
- [docker_open](../tools/docker_open.md)
- [ROS2_workspace_env](../tools/ROS2_workspace_env.md)
