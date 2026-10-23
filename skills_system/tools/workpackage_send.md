---
type: Tool
title: 發送 work package（任務協調器）
description: 對 orchestrtor 發送多站點 work package（站點寫名稱、節點 id 或語意名稱；可設 N 輪或無限循環）；送出前核對、送出後確認收到；會先請使用者確認。
version: 1.2.0
dependencies: ["fih_rmf_system web_console (port 8020)", "或 ROS 2 容器內的 ros2 CLI＋fih_rmf_msgs（--ros2）"]
---

# 用途
web_console `POST /api/send_tasks` → orchestrtor 逐站派給 distribute。送出前核對：站點對到拓譜圖（名稱 → 節點 id（純數字只當 id）→ 語意名稱）、task_id 沒有重複（orchestrtor 會默默忽略重複的 id）、`--amr` 在機器人名冊；送出後讀快照確認 orchestrtor 收到。系統會先請使用者確認（`--dry-run` 不用）。查狀態 `workpackage_status`、取消 `workpackage_cancel`、看站點 `semantic_map`。

# 語法
`EXECUTE: scripts/workpackage_send_cmd.py <task_id|auto> <站點1,站點2,...> [--amr 機器人] [--type regular|charge|park] [--level normal|middle|emergency] [--weight 整數] [--loop [輪數]] [--desc 描述1,描述2] [--dry-run] [--ros2 [容器]] [--no-check] [--url 位址]`
* task_id：英數字、-、_（不能有空白、/、::）；`auto` 自動產生。預設：`--amr` 空＝distribute 挑、regular、normal、`--weight 0`＝自動。
* **循環**：「無限循環／一直跑」→ `--loop` 不接數字；「N 輪」→ `--loop N`；沒提就不加（一輪）。選項的值不能以 `--` 開頭。
* `--url`：web_console（預設環境變數 `RMF_WEB_CONSOLE_URL` 或 http://localhost:8020）。`--ros2 [容器]`：web_console 沒在跑時在容器內發布 `fih_rmf_msgs/msg/WorkPackage`（逾時 30 秒）。`--no-check`：拿不到拓譜圖／快照／名冊時照原樣送（使用者同意才用）。

# 範例
`EXECUTE: scripts/workpackage_send_cmd.py WP001 home,加工線通道-6,a7 --amr tb1`（一輪）　`EXECUTE: scripts/workpackage_send_cmd.py 巡邏 home,a3 --amr tb1 --loop`（無限）

# 回傳
`[PASS] work package「id」已送出：N 站，循環：…，機器人：…；orchestrtor 已收到（…）` + `stops:`（送出的值、節點 id、語意名稱）+ 參數。`--dry-run`：同樣的核對＋要送的 payload。

# 異常
* 站點對不到／對到多站（列候選）：用 `semantic_map --stations` 查，或問使用者是哪一站。
* id 已在清單：換 id 或 `auto`；一定要同 id 先 `workpackage_cancel`。名冊沒有這台：改用名冊上的 id（`semantic_map --robots`）。
* 拿不到拓譜圖／快照、orchestrtor 沒回報、連不上：回報使用者，不要原樣重試；web_console 沒在跑才考慮 `--ros2`＋`--no-check`。HTTP 503 等 5 秒重試一次；422 依訊息修正。
* 收下了但清單裡看不到：`workpackage_status <id>` 再確認，不要重送。參數錯：照訊息修正。沒有機器人可承接時停在當前站（⏳），不是錯誤。
