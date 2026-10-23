---
type: Tool
title: 列出映像檔
description: 列出本機所有 Docker 映像檔（名稱、tag、大小），建立容器前確認映像檔存在。
version: 1.2.0
dependencies: ["docker"]
---

# 用途
包裝 `docker images`，列出 repository、tag、ID、大小、建立時間，並統計 `<none>` 懸空映像數。建立容器（`docker_est`）前先用它確認映像檔存在。逾時 15 秒。

# 語法
`EXECUTE: scripts/docker_images_cmd.py [keyword]`
* `keyword`：過濾 repository 或 tag（子字串、不分大小寫），最多一個。

# 範例
`EXECUTE: scripts/docker_images_cmd.py`　`EXECUTE: scripts/docker_images_cmd.py ros`

# 回傳
`[PASS] 本機映像檔：共 N 個…` + 表格（REPOSITORY / TAG / IMAGE ID / SIZE / CREATED）。沒有符合：`[PASS] 本機目前沒有任何映像檔…`（不是錯誤）。

# 異常
* docker 不可用／daemon 沒回應：`[ERROR]` 說明原因 → 回報使用者，不要原樣重試。
* `<none>` 懸空映像無法用名稱啟動。`docker_est` 用「REPOSITORY:TAG」（例如 `ubuntu:24.04`）；帶 tag 或路徑時要給 `--name`。
