---
type: Tool
title: 切換工作目錄
description: 切換本機的工作目錄（之後的本機技能都在這裡執行、相對路徑相對於這裡）。
version: 2.0.0
dependencies: []
---

# 用途
接下來好幾個操作都在同一個目錄（專案、Workspace）時先切過去，之後的路徑就能寫相對路徑。只改 harness 的狀態，不需要確認。
host_runcmd 指令裡的 `cd` 只在那一次有效，要切換一律用這個。容器裡的目錄不能用它（用 docker_runcmd）。

# 語法
`EXECUTE: scripts/cd_cmd.py <目錄>`
* `目錄`：絕對路徑、相對於目前工作目錄的路徑、或 `~` 開頭；不給就切到家目錄。一次一個，含空白的加引號。
* 切換前檢查：存在、是目錄、目前使用者能讀取並進入。

# 範例
`EXECUTE: scripts/cd_cmd.py ~/fih_humanoid_amr/amr_base`　`EXECUTE: scripts/cd_cmd.py ../logs`

# 回傳
`[PASS] 已切換工作目錄: <絕對路徑>（裡面有 N 項）`，最後一行 `[CWD_CHANGED] <絕對路徑>`（系統據此更新工作目錄）。
失敗時工作目錄不變。

# 異常
* `[ERROR] 找不到目錄`：照「相近的路徑」修正，或先用 list_dir 看上一層；需要新目錄時用 file_ops mkdir（會請使用者確認）。
* `[ERROR] … 是檔案，不是目錄`：改切到訊息寫的所在目錄。
* `[ERROR] 沒有權限進入目錄`（例如 /root）：換有權限的目錄；那裡的內容請使用者自己查看（不會用 sudo）。
* `[ERROR] 一次只能切換到一個目錄`／`沒有選項`／`不支援 cd -`：只給一個路徑。
