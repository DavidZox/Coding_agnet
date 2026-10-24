---
type: Workflow
title: 工作包卡住的處理
description: 工作包卡住、不往下一站：查狀態與交握找原因；完成訊號遺失就補發、等它跑完，有給檔案就寫處理紀錄；其他原因只回報、不修改
version: 0.1.1
dependencies: ["workpackage_status", "rmf_handshake", "file_ops"]
changes_state: true
---

# 用途
工作包停在某一站、一直沒有往下走時用。先查工作包的狀態與交握，判斷原因：只有「完成訊號遺失」（機器人已經到站、閒置，orchestrtor
還在等 task_exec_fin）才補發完成訊號、等工作包跑完；其他原因（機器人沒回應、一直回 no、離線）只回報原因與建議，不取消、不重派。

# 需要的資訊
* `{wp_id}`：卡住的工作包編號（例：`WP_0815`）
* `{note_file}`：處理紀錄要附加到哪個檔案（選填，例：`notes/maintenance.md`；沒給就不寫）

# 步驟
1. 【執行】查工作包的狀態：`EXECUTE: scripts/workpackage_status_cmd.py {wp_id}`　檢查：輸出有「[PASS]」
2. 【執行】查交握，判斷卡住的原因：`EXECUTE: scripts/rmf_handshake_cmd.py status {wp_id} --seconds 15`　檢查：輸出有「的交握狀況」或「已經 COMPLETED」
3. 【檢查】看第 2 步的判斷：「已經 COMPLETED」→ 結束；「完成訊號多半遺失了」→ 第 4 步；其他 → 結束
4. 【執行】補發完成訊號（機器人照第 2 步判斷的那一台）：`EXECUTE: scripts/rmf_handshake_cmd.py fin {robot}`　檢查：輸出有「已經由 manual_trigger 補發」
5. 【執行】等工作包跑完：`EXECUTE: scripts/workpackage_status_cmd.py {wp_id} --until-done`　檢查：輸出有「已完成」
6. 【執行】寫處理紀錄（開頭的時間、工作包、機器人由程式填；{note} 寫原因（第 2 步的判斷）、做了什麼（補發了哪一個工作項）、結果（第 5 步），照前面的輸出寫）：`EXECUTE: scripts/file_ops_cmd.py append {note_file} --text "## {now} 工作包 {wp_id}（機器人 {robot}）\n{note}"`　檢查：輸出有「[PASS]」
7. 【告知】回報：卡住的原因（第 2 步）、補發了哪一個工作項、工作包最後的狀態（第 5 步）、紀錄寫在哪裡

# 成功判準
* `EXECUTE: scripts/workpackage_status_cmd.py {wp_id}` 輸出有「COMPLETED」

# 異常與注意事項
* 第 3 步走到「其他 → 結束」時沒有修改任何東西：照第 2 步的判斷回報原因與建議（例如請機器人端確認 TaskAgent），不要取消或重派工作包。
* 補發被技能擋下（工作項還在 distribute、機器人還在 running）時工作流會停在第 4 步：照錯誤訊息回報，不要加 `--no-check` 硬送。
* 第 2 步聽交握 15 秒：授權逾時（10 秒）進 OverPending 冷卻（10 秒）的那段時間 distribute 不送授權，聽太短會碰上冷卻、判斷成「這幾秒剛好沒有授權」，分不出是沒回應還是一直回 no。
* 會改變狀態的是第 4 步（補發完成訊號）與第 6 步（附加處理紀錄）：開始執行時系統會請使用者確認一次。
