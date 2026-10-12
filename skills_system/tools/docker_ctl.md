---
type: Tool
title: 容器狀態與控制
description: 看容器本身的狀態、log、設定（環境變數、掛載、網路），以及啟動／停止／重新啟動容器（會先請使用者確認）。
version: 1.0.0
dependencies: ["docker"]
---

# 用途
操作的是容器本身（等同主機上的 `docker start／stop／restart／logs／inspect`），不是在容器裡面執行指令（那是 docker_runcmd）。
容器停了要找原因：先 `status` 看結束碼、再 `logs` 看最後的輸出；確認原因後、使用者要求時才 `start`／`restart`。
`start`／`stop`／`restart` 會改變狀態，執行前系統會請使用者確認；`status`／`logs`／`inspect`／`env` 是唯讀的。

# 語法
`EXECUTE: scripts/docker_ctl_cmd.py <status|logs|inspect|env|start|stop|restart> [容器名稱] [--tail N] [--grep 關鍵字]`
* 容器名稱可省略＝目前的目標容器；只寫部分名稱時，剛好對到一個容器才會用它（對到好幾個會列出來請你確認）。
* `logs`：預設最後 40 行；`--grep ERROR` 只看含關鍵字的行（會說有幾行、最後一行是什麼）。`env --grep ROS` 只看相關的環境變數。

# 範例
`EXECUTE: scripts/docker_ctl_cmd.py status nav2_test`　`EXECUTE: scripts/docker_ctl_cmd.py logs log_writer --grep ERROR`
`EXECUTE: scripts/docker_ctl_cmd.py env web_cache --grep CACHE`　`EXECUTE: scripts/docker_ctl_cmd.py restart db_backup`

# 回傳
`[PASS] <容器>：Up（執行中…）` 或 `Exited（結束碼 N，… 結束）`；start／stop／restart 回報「之前 → 之後」的狀態與最後幾行 log（一啟動就結束時看得到原因）。

# 異常
容器不存在、名稱對到好幾個、docker 沒有回應：`[ERROR]` 說明原因。使用者沒有同意（確認被拒）就不會執行，不要原樣重送。
