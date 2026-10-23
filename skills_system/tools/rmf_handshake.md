---
type: Tool
title: 調度交握（診斷與手動觸發）
description: 看某台機器人（或某個工作包）跟 distribute 的授權交握並判斷原因（離線、沒回應、回 no、完成訊號遺失、在等忙碌的機器人）；必要時手動回 yes／no 或補發完成訊號（會先請使用者確認）。
version: 1.3.0
dependencies: ["fih_rmf_system web_console", "manual_trigger（yes／no／fin）", "ROS 2 容器＋fih_rmf_msgs（status 聽 topic）"]
---

# 用途
工作包「一直沒開始」「卡在授權」「停在某一站」時先用 `status`（唯讀）：讀快照、在 ROS 2 容器裡等訂閱配對上之後聽 /{rid}/allocator_status 與 /{rid}/handshake_states 幾秒（預設 4，`--seconds` 1～60）、聽完再讀一次快照，判斷原因並給下一步；給工作包 id 會換成它的機器人；聽不到時寫「無法觀察（原因）」。判斷清楚、使用者同意時才用 yes／no／fin：
* 機器人**沒有回應**授權時，除非使用者已經跟機器人端確認可以接、明確要你回 yes，**不要**自己手動回 yes（機器人不會真的去執行）。
* `yes`／`no` 是替機器人回應授權（handshake_states）；`fin` 是補發完成訊號（task_exec_fin）——兩回事，使用者說「回 yes」就用 `yes`。
* 完成訊號遺失（到站、閒置、工作項還在等）：`fin <機器人>`（task_id 省略＝它在等的工作項），再 `workpackage_status <工作包> --until-done` 等它跑完。

# 語法
`EXECUTE: scripts/rmf_handshake_cmd.py status <機器人或工作包> [--seconds N] [--container 容器]`
`EXECUTE: scripts/rmf_handshake_cmd.py yes|no <機器人> [<機器人> …]`　`EXECUTE: scripts/rmf_handshake_cmd.py fin <機器人> [<task_id 或工作包>]`
* `--seconds` 1～60（預設 4）。`--container`：預設目前的目標容器，沒有就找名稱含 rmf／ros／amr 的唯一容器。
* `--url`：web_console（預設 `RMF_WEB_CONSOLE_URL` 或 http://localhost:8020）；`--trigger`：manual_trigger（預設 `RMF_MANUAL_TRIGGER_URL` 或 http://localhost:8002，要另外 `ros2 run fih_rmf_system manual_trigger`）。
* yes／no／fin 會先核對名冊與工作項、送出後讀快照確認；快照讀不到時要加 `--no-check` 才送（使用者同意才用）。

# 範例
`EXECUTE: scripts/rmf_handshake_cmd.py status WP_C3`　`EXECUTE: scripts/rmf_handshake_cmd.py status tb3 --container rmf_sim --seconds 15`　`EXECUTE: scripts/rmf_handshake_cmd.py fin tb2`

# 回傳
`[PASS] tb3 的交握狀況：<判斷>` + `## 快照`、`## 聽 topic`（兩個 topic 各收到幾則、graph 上的發布者幾個、時間線 `+0.3s authorize、+0.3s 回 no…`、聽完的快照工作項換到哪裡）、`## 判斷`（原因與下一步）。發布者 0 個是證據：handshake_states 沒有發布者＝機器人端的 TaskAgent 多半沒在跑；allocator_status 沒有發布者＝聽的容器看不到 distribute（容器或 ROS_DOMAIN_ID 不對）。聽的期間工作項進了 OverPending 就寫「這幾秒剛好沒有授權」。yes／no／fin：送出的結果＋快照確認的效果。

# 異常
* 名冊沒有這台、也不是工作包（附相近的）：改用正確的 id，或問使用者。
* fin 找不到它在等的工作項、task_id 不是目前在等的、工作項還在 distribute、機器人還在 running：先 `status` 再決定，不要硬送。
* 看不到任何資料（快照讀不到也沒有容器可聽）：恢復 web_console，或加 `--container`。連不上 manual_trigger：它要另外啟動，回報使用者。
* 送出後 4 秒沒有效果：可能不在同一個 ROS_DOMAIN_ID，回報使用者，不要一直重送。
