---
type: Tool
title: 容器狀態與控制
description: 看容器本身的狀態、log（stdout＋stderr，可接著看新的）、設定（環境變數、掛載、網路），以及啟動／停止／重新啟動容器（會先請使用者確認）。
version: 2.0.2
dependencies: ["docker"]
---

# 用途
操作容器本身（主機上的 `docker start／stop／restart／logs／inspect`），不是在容器裡執行指令（那是 docker_runcmd）。使用者要啟動／重啟：直接 `start`／`restart`（會先請使用者確認），回報附這次啟動的 log、又停了會寫原因；只問容器停掉的原因：先 `status`
看結束碼的意思、再 `logs` 看最後的輸出，不要自己啟動。時間是主機本地時間（標時區）。
容器名稱省略＝目前的目標容器（只認完全相同的名稱）；有寫名稱時可以是唯一的部分名稱。

# 語法
`EXECUTE: scripts/docker_ctl_cmd.py <status|logs|inspect|env|start|stop|restart> [容器名稱] [選項]`
* `logs`：stdout 與 stderr 依時間合併（`2>` 標 stderr）。`--tail N` 預設 40、上限 2000；`--since`／`--until`：`10m`、`2h`、`14:05`、
  `2026-10-23T14:05:00` 或上次輸出最後的游標。超過 80 行或 `--dedup` 時整理成唯一訊號＋最後 30 行原文（`--raw` 不整理）；`--grep`（可重複）掃最後 5000 行。
* `env --grep ROS` 篩選；`inspect` 的環境變數只列前 40 個。`stop`／`restart` 等 10 秒後強制結束；`start`／`restart` 後等 2 秒回報。

# 範例
`EXECUTE: scripts/docker_ctl_cmd.py status cam_driver`　`EXECUTE: scripts/docker_ctl_cmd.py logs cam_driver --grep ERROR`
`EXECUTE: scripts/docker_ctl_cmd.py logs --since 10m --dedup`　`EXECUTE: scripts/docker_ctl_cmd.py restart cam_driver`

# 回傳
`[PASS] <容器>：Up（執行中…）` 或 `Exited（結束碼 N：意思；… 結束）`＋映像、指令、重新啟動政策、OOMKilled、健康檢查。logs 第一行有行數、
stdout／stderr 各幾行、狀態，最後一行「下次接著看新的：--since …」。start／restart 回報「之前 → 之後」與這次的 log；又停了會明說，不要直接再啟動。

# 異常
* 名稱對不到或好幾個、目標容器已不存在 → 列出現有的容器，改用完整名稱或 docker_open。log driver 讀不回、docker 沒回應 → `[ERROR]` 說原因。
* 不認得的選項 → `[ERROR]`＋用法。使用者拒絕確認就不會執行，不要原樣重送。
