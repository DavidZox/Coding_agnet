---
type: Tool
title: 建立容器環境
description: 以指定映像檔（可帶 tag）建立並在背景啟動容器，可指定名稱、指令、網路與環境變數；會先請使用者確認。
version: 3.0.0
dependencies: ["docker"]
---

# 用途
`docker run -d`：容器在背景常駐，確定在跑時成為目前的目標容器。會先請使用者確認。逾時 120 秒（要拉映像時較久）。
`docker run` 失敗或啟動後 2 秒內以非 0 結束時，附上 log 後移除這次建的容器（不留東西，可用同一個名稱重試）；結束碼 0（一次性的工作）保留。

# 語法
`EXECUTE: scripts/docker_est_cmd.py <映像檔[:tag]> [--name 名稱] [--cmd "指令"] [--network 網路] [-e 變數=值]...`
* 帶 tag 或路徑時一定要給 `--name`（英數字、`_ . -`，至少 2 個字）；沒帶時名稱＝映像檔名稱。先用 `docker_images` 確認映像檔存在。
* `--cmd` 省略＝一直跑著；含 `&& ; | $ source` 等 shell 語法時自動包成 `bash -lc "…"`（沒有 bash 用 `sh -c`）。
* 支援 `--network host`、`-e ROS_DOMAIN_ID=42`；`-v`、`-p`、`--gpus`、`--privileged`、`--rm`… 回 `[ERROR]`、不建任何東西；`-d`／`-it` 略過。

# 範例
`EXECUTE: scripts/docker_est_cmd.py ubuntu:24.04 --name scratch_box --cmd "sleep infinity"`
`EXECUTE: scripts/docker_est_cmd.py ros:jazzy-ros-base --name ros_box --network host -e ROS_DOMAIN_ID=42`

# 回傳
`[PASS] 容器 '<名稱>'（映像檔…，指令…，ID…）已在背景啟動，2 秒後確認還在跑；已設為目前的目標容器`，末行 `[TARGET_CONTAINER]`、`[CONTAINER_CWD]`。
跑完就結束（結束碼 0）：`[PASS] …容器停在 Exited、沒有設為目標容器`＋log。參數錯：`[ERROR]`，不會建立任何容器。

# 異常
* 同名容器已存在 → 訊息說它在跑（`docker_open`）還是停了（`docker_ctl start` 或換 `--name`）；不要刪除使用者沒交代的容器。
* 啟動就結束（非 0）→ 看附的 log 修正 `--cmd` 再建。映像檔不存在且拉不到 → `docker_images` 確認名稱。docker 不可用、逾時：回報使用者。
