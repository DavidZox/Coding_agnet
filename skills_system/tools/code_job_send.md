---
type: Tool
title: 交給 coding orchestrator 修改程式
description: 要修改、新增、重構程式碼時用：把任務交給 coding orchestrator，它先探索專案、列出計畫，等使用者在畫面上核准後，派 worker 一項一項修改並驗證，最後產生報告（可暫停、停止、還原）。
version: 1.0.0
dependencies: []
---

# 用途
主對話不直接改檔案；所有「改程式」的請求（新增功能、修 bug、改名、重構、補測試）都用這個交出去。orchestrator 的流程：探索專案（`repo_map`）→ 規劃（拆成 work items，每項寫清楚要改的檔案與驗證方式）→ **使用者在 Coding 面板核准** → 每一項派一個 coding worker 修改，做完由程式驗證（語法、未定義名稱、跨檔 import、測試）→ 整體驗證 → 報告（存成 `#編號`，之後可以 `result_recall`）。改檔前都會備份，可以整個還原。

# 語法
`EXECUTE: scripts/code_job_send_cmd.py [--workspace 專案路徑] "<任務描述>"`
* 任務描述：照使用者的原話寫完整（要做什麼、改成怎樣、要不要測試），不要自己縮短。
* `--workspace`：專案根目錄；省略＝coding 工作區（`/code_ws` 設定的）或目前工作目錄。使用者提到某個專案路徑時一定要給。

# 範例
`EXECUTE: scripts/code_job_send_cmd.py --workspace /home/user/ws/inventory_app "在 Inventory 新增 restock_below(threshold, amount)，並加上測試"`

# 回傳
`[PASS] 已交給 coding orchestrator：job #N（工作區 …）…`。之後告訴使用者：計畫列好後要在畫面上核准才會開始改；進度用 `code_job_status`。

# 異常
工作區不存在、或是 `/`、家目錄這種整個系統的目錄：`[ERROR]`，請使用者給專案路徑。
