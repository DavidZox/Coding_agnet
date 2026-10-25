---
type: Tool
title: 查 work package 執行狀態（一幀或一段時間）
description: 讀 web_console 快照看 work package、distribute 佇列、機器人與事件；--watch 觀察一段時間，整理每個工作包／工作項／機器人的狀態變遷；--until-done 等指定的工作包跑完（看到完成就結束，看得出卡住就提早結束）；--until-confirmed 等目前這一站的授權有結果。
version: 1.4.0
dependencies: ["fih_rmf_system web_console (port 8020)"]
---

# 用途
WebSocket `/api/ws` 一幀快照：`## work package`（每個一行：狀態、第幾站、目前工作項在 distribute 的哪裡、機器人或 ⏳；RUNNING 全列，已完成的太多時寫「另有 N 個」）、`## distribute 佇列`、`## 機器人`、`## 最近事件`。task_id 可以是工作包或工作項（含 `::`）。**一幀只是瞬間**：問「一段時間／持續／有沒有在動／變化」用 `--watch 秒`：每個工作包（站點／輪次／機器人）、工作項（raw／OverPending／processing→機器人／離開 distribute）、機器人（ONLINE／顯示／自報狀態）的每次變遷（從什麼到什麼、+秒）、次數與時間占比，結束時的狀態在前，太多次只列頭尾。**等它跑完**（派完工作包、補發完成訊號之後要確認完成）用 `<工作包> --until-done`：看到 COMPLETED 或從清單消失就結束，不用猜要看幾秒；看得出它不會自己往下走（完成訊號遺失、閒著的機器人一直不接授權）就提早結束，寫原因與下一步；`--watch 秒` 是觀察一段時間的變化，會看滿秒數。**只要確認授權有沒有成功**（派完工作包、機器人有沒有接下）用 `<工作包> --until-confirmed`：confirm 給機器人就成功、閒著的機器人一直不接就失敗（寫原因），不用等整個工作包跑完；剛送出時工作項一定還在授權中，看一幀看不出成不成功。

# 語法
`EXECUTE: scripts/workpackage_status_cmd.py [task_id] [--watch 秒] [--until-done | --until-confirmed] [--url 位址]`
* `--watch` 1～300 秒（不加＝一幀）。帶 task_id：只看它、它的工作項與相關機器人。
* `--until-done`、`--until-confirmed`：要帶工作包編號（不是工作項），只能選一個；最多等 `--watch` 的秒數，沒給就 300 秒。
* `--url`：web_console（預設環境變數 `RMF_WEB_CONSOLE_URL` 或 http://localhost:8020）；連線＋第一幀 6 秒內沒來算失敗。

# 範例
`EXECUTE: scripts/workpackage_status_cmd.py`　`EXECUTE: scripts/workpackage_status_cmd.py WP001`　`EXECUTE: scripts/workpackage_status_cmd.py WP001 --watch 30`　`EXECUTE: scripts/workpackage_status_cmd.py WP001 --until-done`　`EXECUTE: scripts/workpackage_status_cmd.py WP001 --until-confirmed`

# 回傳
一幀：`[PASS] 目前狀態：work package N 個（RUNNING a、COMPLETED b）…` + 各節。`--watch`：`[PASS] 觀察 N 秒（收到 M 幀…）` + `## 結束時` + 各類變化（`--- #n` 一個對象）+ 期間新增的事件；中途斷線時第一行是 `⚠️ 只觀察到 N 秒就中斷`。`--until-done`：第一行 `[PASS] WP001 已完成：COMPLETED（共 1 輪），在 +8.0s 看到完成就結束觀察…`；時間到還沒完成是 `…WP001 還沒完成：結束時 <狀態>`，第二行是下一步；看得出卡住是 `[PASS] WP001 沒有進展，提早結束觀察（+16.0s…）：<原因>`，第二行是下一步（完成訊號遺失 → `rmf_handshake fin`；閒著的機器人一直不接授權 → `rmf_handshake status <機器人> --seconds 15`）；`--until-confirmed`：`[PASS] WP001 授權成功：工作項 … 已經 confirm 給 <機器人>…`、`[PASS] WP001 授權沒有成功，提早結束觀察…：<原因>`（第二行是下一步）、時間到是 `…WP001 的授權還沒有結果`（機器人在忙）；被刪除是 `…從 orchestrtor 的清單消失（被刪除），沒有跑完`。其餘各節同 `--watch`。

# 異常
* 找不到 id（`[ERROR]`，附相近的 id）：確認 id；取消過的工作包會從清單消失。`⏳ 等待機器人` 不是錯誤。
* `--until-done`／`--until-confirmed` 沒帶工作包、帶了工作項、兩個一起用、第一幀就沒有這個工作包、`--until-done` 遇到無限循環的工作包（不會完成）：立刻回 `[ERROR]`，照下一步做。
* 連不上 web_console、握手或快照逾時：回報使用者（或用 `--url` 指到正確位址）。觀察中斷：照第二行再跑一次。
* 下一步的技能：刪 OverPending 的工作項 `overpending_cancel`；取消工作包 `workpackage_cancel`；卡住的原因 `rmf_handshake status`。
