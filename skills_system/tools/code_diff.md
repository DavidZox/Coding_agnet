---
type: Tool
title: 看程式改了什麼
description: 看某個 coding job 改了哪些檔案、每個檔案的 diff（跟 job 開始前的備份比）；沒有 job 時看 git 工作區的變更。
version: 1.0.0
dependencies: ["git（可選）"]
---

# 用途
回答「剛剛改了什麼」「那個檔案改成怎樣」。coding job 改檔前都會備份原檔，所以就算專案沒有 git 也看得到差異；新增與刪除的檔案也會列出。

# 語法
`EXECUTE: scripts/code_diff_cmd.py [檔案] [--stat] [--job <編號|latest>]`
* `--job`：看某個 coding job 的變更（主對話用這個）；`--stat`：只列每個檔案加減幾行；給檔案只看那一個。

# 範例
`EXECUTE: scripts/code_diff_cmd.py --job latest --stat`　`EXECUTE: scripts/code_diff_cmd.py inventory/store.py --job 3`

# 回傳
`[PASS] coding job #N 的變更（工作區 …）：K 個檔案（+A −D）` + 每個檔案的加減行數 + unified diff。

# 異常
找不到 job、或不在 job 裡又不是 git 專案：`[ERROR]` 並說明。
