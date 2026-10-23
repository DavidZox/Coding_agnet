---
type: Tool
title: 列出容器
description: 列出主機上所有容器（名稱、狀態、映像檔），第一行算好總數與執行中、暫停、已停止的數量。
version: 1.3.0
dependencies: ["docker"]
---

# 用途
包裝 `docker ps -a`。進入容器或執行指令前先用它取得完整名稱；查到後用 `docker_open` 選定為目標容器，之後其他容器技能可省略名稱。
狀態依 docker 的 State 判斷：暫停（Paused）的不算執行中（不能執行指令）。逾時 15 秒。

# 語法
`EXECUTE: scripts/docker_containers_cmd.py [--running] [keyword]`
* `--running`：只列執行中（含暫停）的；預設含已停止的。`keyword`：過濾名稱（子字串、不分大小寫），最多一個。

# 範例
`EXECUTE: scripts/docker_containers_cmd.py`　`EXECUTE: scripts/docker_containers_cmd.py --running rmf`

# 回傳
`[PASS] 容器（含已停止）：共 N 個，運行中 M 個[、暫停 K 個、已停止 J 個…]` + 表格（NAME / STATUS / IMAGE / CONTAINER ID）。
沒有符合：`[PASS] 目前沒有任何…`（不是錯誤）。數量直接引用第一行，不要自己數。

# 異常
* docker 不可用／daemon 沒回應：`[ERROR]` 說明原因 → 回報使用者，不要原樣重試。
* Exited 的容器不能執行指令 → `docker_ctl status` 看原因，使用者要求才 `docker_ctl start`；Paused 的請使用者 unpause。
* 沒有目標容器、又有好幾個執行中的容器 → 請使用者指定，不要自己挑第一個。
