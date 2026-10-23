---
type: Tool
title: 刪除 OverPending 逾時區的工作項
description: 刪除卡在 distribute OverPending 逾時區的單站工作項；不在逾時區時可等它進來再刪，送出後確認全部佇列；會先請使用者確認。
version: 1.2.0
dependencies: ["fih_rmf_system web_console (port 8020)"]
---

# 用途
web_console `DELETE /api/overpending_tasks/{id}`。**OverPending 會來回**：工作項在 raw 等超過約 10 秒或授權逾時就進 OverPending，再約 10 秒回流 raw；distribute 只刪「此刻在 OverPending」的，DELETE 卻一律回 200。所以先看快照：此刻在逾時區才送；不在時回報所在佇列（加 `--wait 秒` 等它進來立刻刪）；送出後確認它從全部佇列消失。刪掉後所屬工作包會一直等這一站（要停整個工作包用 `workpackage_cancel`）。系統會先請使用者確認。

# 語法
`EXECUTE: scripts/overpending_cancel_cmd.py <工作項id> [--wait 秒] [--url 位址]`
* 工作項 id 形如 `<package>::<輪>::<站>::<run_id>-<序>`（`workpackage_status` 查）。`--wait` 1～300 秒；不加只看一幀。
* `--url`：web_console（預設環境變數 `RMF_WEB_CONSOLE_URL` 或 http://localhost:8020）；送出後確認最多讀 4 秒。

# 範例
`EXECUTE: scripts/overpending_cancel_cmd.py "WP001::0::1::3fa2b6c1-4"`　`EXECUTE: scripts/overpending_cancel_cmd.py "WP001::0::1::3fa2b6c1-4" --wait 30`

# 回傳
刪除：`[PASS] 已刪除 OverPending 工作項 …：快照確認它已不在 distribute 的任何佇列`。不在逾時區：`[PASS] 未刪除：… 目前在 raw …`（時序，不是錯誤）。

# 異常
* 「未刪除：在 raw／processing」：加 `--wait 30` 重做，或用 `workpackage_cancel` 取消整個工作包。
* 沒有刪到（DELETE 晚到一步：已回流 raw 或被機器人領走）：照訊息 `--wait 30` 重試。
* 找不到工作項（附相近的）、給的是工作包 id：用 `workpackage_status <工作包>` 查目前的工作項 id。
* 4 秒後仍在 OverPending：distribute 沒處理，回報使用者。連不上 web_console：回報使用者。
