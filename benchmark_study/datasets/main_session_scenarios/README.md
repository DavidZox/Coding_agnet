# 主對話（非 coding）的評測情境

`scenarios.json` 是 `evals/scenarios.py` 的情境定義匯出（使用者的話、每一句的檢查條件、開始前的狀態、用到的假工具）：

- `main_14`：機器人維運類的 14 個情境（容器、ROS 2 topic／node、調度系統的派工、工具回傳存檔與回查、記憶、coding 的路由）。外部世界（docker、ROS 2、調度系統）一律用假資料，結果才可重現；本機檔案類技能與存檔工具在臨時的專案副本裡真的執行。
- `robust_5`：穩健性情境（2026-10-08 新增）——檔名大小寫打錯、目錄名稱少一個字、要讀的檔案不存在、要求重新啟動容器（看會不會沒做就說做了）、指令裡有引號與分號。用來比較主對話的把關（卡住偵測、宣稱完成偵測、路徑建議、引號保留）開啟與關閉的差別（`AGENT_ABLATE=turn_guard,path_suggest,rejoin` 是對照組）。

假工具的內容（例如 12 台車的 fleet_states、容器清單）是程式產生的，在 `evals/scenarios.py`。跑法：`python3 evals/run_evals.py --modes harness --runs 3`、`python3 evals/run_evals.py --suite robust --modes harness --runs 3`。
