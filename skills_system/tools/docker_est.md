---
type: Tool
title: 建立容器環境
description: 以指定映像檔建立並啟動容器。
version: 2.0.0
dependencies: ["docker"]
---

# 用途
`docker run -d --name <容器名稱> <映像檔> <指令>` 讓容器在背景常駐（預設指令 `tail -f /dev/null`），建好後成為目前的目標容器。逾時 120 秒（需從 registry 拉取時較久）。
會改變狀態（建立容器），執行前系統會請使用者確認。

# 語法
`EXECUTE: scripts/docker_est_cmd.py <映像檔[:tag]> [--name 容器名稱] [--cmd "要執行的指令"]`
* 映像檔可以帶 tag（`ubuntu:24.04`、`ros:jazzy-ros-base`）；帶 tag 或路徑時一定要給 `--name`。沒帶 tag 又沒給 `--name` 時，容器名稱＝映像檔名稱。
* `--cmd` 省略＝`tail -f /dev/null`（一直跑著）；使用者指定了指令（例如 sleep infinity）就照寫。先用 `docker_images` 確認映像檔存在。

# 範例
`EXECUTE: scripts/docker_est_cmd.py ubuntu:24.04 --name scratch_box --cmd "sleep infinity"`　`EXECUTE: scripts/docker_est_cmd.py ros2_humble`

# 回傳
成功：`[PASS] 容器 '<名稱>'（映像檔 …，指令：…）已在背景啟動（ID: …），狀態：running；已設為目前的目標容器`（末行 `[TARGET_CONTAINER] <名稱>`）。
狀態不是 running 時會註明（指令執行完就結束了）。失敗：`[ERROR] ... 失敗（exit code N）: 原因`；參數不清楚時 `[ERROR]` 且不會建立任何容器。

# 異常
* 同名容器已存在：改用 `docker_open` 進入，或換一個名稱；不要刪除使用者沒有交代的容器。
* 映像檔不存在且無法拉取：用 `docker_images` 確認名稱。
* docker 不可用／daemon 未啟動／逾時：回報使用者。
