---
type: Tool
title: 選定目標容器（進入並驗證連線）
description: 找出容器真實名稱、確認它在跑並驗證連線，設為之後容器技能預設使用的目標容器。
version: 1.4.1
dependencies: ["docker"]
---

# 用途
比對名稱（完全相同 > 不分大小寫相同 > 唯一的部分名稱），確認容器在跑，再以 `docker exec` 取得容器內目錄與使用者。成功後這個容器成為**目前的目標容器**
（CURRENT_TARGET_CONTAINER），容器內目錄成為 CURRENT_CONTAINER_DIRECTORY（docker_runcmd 從這裡開始）：之後 `docker_runcmd`、`ROS2_*`、`docker_ctl` 可省略容器名稱。
要換容器就再用一次。多個容器都符合時不猜。逾時 15 秒。

# 語法
`EXECUTE: scripts/docker_open_cmd.py <container_name>`（可為部分名稱、不分大小寫；只接受一個）

# 範例
`EXECUTE: scripts/docker_open_cmd.py ros_box`

# 回傳
`[PASS] 已成功連線至 '<真實名稱>'，並設為目前的目標容器：執行中，映像…；容器內目錄…，使用者…`，最後幾行是系統狀態標記
`[TARGET_CONTAINER] <名稱>`、`[CONTAINER_CWD]` 與目錄。失敗：`[ERROR] 原因。下一步：…`。

# 異常
* 找不到 → 訊息附相近的名稱與現有容器（太多只列前 15 個；完整清單用 `docker_containers`）。多個符合 → 改用完整名稱，不確定就問使用者。
* 容器沒有在跑 → `docker_ctl status` 看原因，使用者同意後 `docker_ctl start`，再 docker_open。被暫停 → 請使用者 unpause。
* docker 不可用、逾時：回報使用者。
