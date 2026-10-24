---
type: Workflow
title: 工作包改派給別台
description: 工作包派不出去時查原因；是原本那台機器人的問題（一直回 no、沒回應、離線）才取消它、用同樣的站點改派給指定的機器人並等它跑完
version: 0.1.1
dependencies: ["workpackage_status", "rmf_handshake", "workpackage_cancel", "workpackage_send"]
changes_state: true
---

# 用途
「WP_0815 卡在授權，是 amr_07 的問題就取消、改給 amr_12」這種：先查工作包與交握，確定是原本那台機器人的問題才改派；
不是機器人的問題（例如站點、distribute）就只回報原因，不取消。

# 需要的資訊
* `{wp_id}`：派不出去的工作包編號（例：`WP_0815`）
* `{robot}`：改派給哪一台（例：`amr_12`）

# 步驟
1. 【執行】看工作包的路線與指派：`EXECUTE: scripts/workpackage_status_cmd.py {wp_id}`　檢查：輸出有「[PASS]」
2. 【執行】查交握，判斷原因：`EXECUTE: scripts/rmf_handshake_cmd.py status {wp_id} --seconds 15`　檢查：輸出有「的交握狀況」
3. 【檢查】看第 2 步，是不是原本那台機器人的問題：「對授權一直回 no」或「沒有回應授權」或「離線」→ 第 4 步；其他 → 結束
4. 【執行】取消原本的工作包：`EXECUTE: scripts/workpackage_cancel_cmd.py {wp_id}`　檢查：輸出有「[PASS]」
5. 【執行】用同樣的站點改派給 {robot}（站點照第 1 步的路線，用站點代號、照順序逗號隔開）：`EXECUTE: scripts/workpackage_send_cmd.py auto {stops} --amr {robot}`　檢查：輸出有「已送出」
6. 【執行】等新的工作包跑完（編號照第 5 步送出的那一個）：`EXECUTE: scripts/workpackage_status_cmd.py {new_id} --until-done`　檢查：輸出有「已完成」
7. 【告知】回報：原因（第 2 步）、取消了哪一個、新的工作包編號與結果（第 6 步）

# 成功判準
* 第 4 步的輸出有「[PASS]」
* 第 6 步的輸出有「已完成」

# 異常與注意事項
* 第 3 步走到「其他 → 結束」時沒有取消任何東西：照第 2 步的判斷回報原因與建議。
* 已經 confirm 給原本那台、它正在做的那一站，取消之後還是會做完（取消只讓 orchestrtor 不再派下一站）：回報時說明。
* 第 2 步聽交握 15 秒：授權逾時（10 秒）進 OverPending 冷卻（10 秒）的那段時間 distribute 不送授權，聽太短會碰上冷卻、判斷成「這幾秒剛好沒有授權」，分不出是沒回應還是一直回 no。
* 會改變狀態的是第 4 步（取消）與第 5 步（送出新的工作包）：開始執行時系統會請使用者確認一次。
