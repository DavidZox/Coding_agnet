---
type: Tool
title: 取消 work package
description: 刪除一個 work package（先確認存在、送出後確認從清單消失），orchestrtor 停止派下一站；會先請使用者確認。
version: 1.1.0
dependencies: ["fih_rmf_system web_console (port 8020)"]
---

# 用途
web_console `DELETE /api/work_packages/{id}`（不論 id 對不對都回 200）：先讀快照確認它在 orchestrtor 的清單（不在就不送），送出後讀快照確認它消失。只停止派下一站；已送到 distribute 或交給機器人的當前站可能仍會執行完（回報寫那一站此刻在哪）。工作項 id（含 `::`）不是工作包：只刪卡在 OverPending 的那一筆用 `overpending_cancel`。系統會先請使用者確認。

# 語法
`EXECUTE: scripts/workpackage_cancel_cmd.py <task_id> [--url 位址]`
* task_id 用 `workpackage_status` 查；一次一個。`--url`：web_console（預設環境變數 `RMF_WEB_CONSOLE_URL` 或 http://localhost:8020），確認最多讀 4 秒。

# 範例
`EXECUTE: scripts/workpackage_cancel_cmd.py WP001`

# 回傳
`[PASS] 已取消 work package <id>（取消前 …）：快照確認已從 orchestrtor 的清單移除` + 當前那一站的去向。失敗 `[ERROR] 原因。下一步：…`。

# 異常
* 清單裡沒有這個 id（附相近的 id，沒有送出）：用 `workpackage_status` 確認；取消過的就不在清單。使用者給的對不上就問使用者。
* 給的是工作項 id：照訊息改用工作包 id，或 `overpending_cancel`。
* orchestrtor 沒回報狀態、送出後 4 秒仍在清單：orchestrtor 可能沒在跑，回報使用者，不要一直重送。連不上 web_console：回報使用者。
