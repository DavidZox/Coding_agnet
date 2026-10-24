---
type: Workflow
title: 派工作包並確認跑完
description: 派一個工作包給指定的機器人（站點照順序），等它跑完（看到完成就結束，最多 300 秒），回報每一站的結果
version: 0.1.1
dependencies: ["workpackage_send", "workpackage_status"]
changes_state: true
---

# 用途
「派 tb1 從 home 到 a3 跑一趟，確認完成」這種：送出工作包、等它跑完再回報。等待用 workpackage_status --until-done，看到完成就結束，
不用猜要觀察幾秒；最多 300 秒，時間到還沒完成就照實回報現況。

# 需要的資訊
* `{robot}`：指派的機器人（例：`tb1`）
* `{stops}`：站點，照順序用逗號隔開；「從 A 到 B」的出發站 A 也要寫（例：「從 home 到 a3、再到 a7」→ `home,a3,a7`；名稱或語意名稱都可以）
* `{wp_id}`：工作包編號（選填，預設 `auto`＝自動產生）

# 步驟
1. 【執行】派工作包：`EXECUTE: scripts/workpackage_send_cmd.py {wp_id} {stops} --amr {robot}`　檢查：輸出有「已送出」
2. 【執行】等工作包跑完（編號照第 1 步送出的那一個）：`EXECUTE: scripts/workpackage_status_cmd.py {sent_id} --until-done`　檢查：輸出有「已完成」
3. 【告知】回報：工作包編號、路線、機器人、什麼時候完成（第 2 步）

# 成功判準
* 第 2 步的輸出有「已完成」

# 異常與注意事項
* 站點或機器人不對時第 1 步會停下來（workpackage_send 會核對拓譜圖與名冊）：照錯誤訊息裡相近的名稱問使用者。
* 300 秒內沒有完成時第 2 步會停下來：照輸出回報目前在第幾站，卡住了就改用 stuck_package_fix 查原因。
* 會改變狀態的是第 1 步（送出工作包）：開始執行時系統會請使用者確認一次。
