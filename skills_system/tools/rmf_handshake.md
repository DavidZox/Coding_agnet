---
type: Tool
title: 調度交握（診斷與手動觸發）
description: 看某台機器人跟 distribute 的授權交握狀況並自動判斷原因（離線、沒回應、回 no、完成訊號遺失）；必要時手動回 yes／no 或補發完成訊號（會先請使用者確認）。
version: 1.1.0
dependencies: ["調度系統 web_console", "manual_trigger（手動觸發時）", "ROS 2 容器（聽 topic 時）"]
---

# 用途
工作包「一直沒開始」「卡在授權」「停在某一站」時先用 `status`：它讀 web_console 的快照、在 ROS 2 容器裡聽 /{rid}/allocator_status 與
/{rid}/handshake_states 幾秒，依交握規則判斷原因並建議下一步。只有判斷清楚、使用者同意時才用 yes／no／fin 介入：
* 機器人**沒有回應**授權（TaskAgent 沒在跑）時**不要**手動回 yes——機器人不會真的去執行，工作包會卡住。
* 機器人已經到站、閒置，工作項還在等：多半是 task_exec_fin 遺失，`fin` 補發（task_id 省略＝它目前在等的工作項）；補發後用 `workpackage_status <工作包> --watch 20` 確認有往下走、跑完。

# 語法
`EXECUTE: scripts/rmf_handshake_cmd.py status <機器人或工作包> [--seconds N] [--container 容器]`（給工作包編號會自動換成它目前指派的機器人）
`EXECUTE: scripts/rmf_handshake_cmd.py yes|no <機器人> [<機器人> …]`　`EXECUTE: scripts/rmf_handshake_cmd.py fin <機器人> [<task_id>]`
* 位址：`--url`（web_console，預設 RMF_WEB_CONSOLE_URL）、`--trigger`（manual_trigger，預設 RMF_MANUAL_TRIGGER_URL）；環境的設定檔（例如 configs/rmf/fleet.yaml）有寫的話照用。
* `--container`：跑 ROS 2 的容器（預設目前的目標容器；都沒有時自動找：只有一個執行中的容器、或名稱含 rmf／ros／amr 的剛好一個）。

# 範例
`EXECUTE: scripts/rmf_handshake_cmd.py status WP_C3`　`EXECUTE: scripts/rmf_handshake_cmd.py status tb3 --container rmf_sim`　`EXECUTE: scripts/rmf_handshake_cmd.py fin tb2`

# 回傳
`[PASS] tb3 的交握狀況：` + distribute 的狀態、正在授權的任務、OverPending、工作包、聽到的訊息數 + `判斷：` 原因與建議。yes／no／fin 回報送出的結果。

# 異常
連不上 web_console／manual_trigger、名冊裡沒有這台機器人、找不到唯一的工作項：`[ERROR]` 說明原因。
