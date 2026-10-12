---
type: Tool
title: 停止 coding job
description: 停止一個 coding job：目前這一步做完就停，還沒做的項目不做；已經改好的檔案保留（可在 Coding 面板還原）。
version: 1.0.0
dependencies: []
---

# 用途
使用者要求停止、取消正在進行的 coding job 時用（會改變狀態，執行前系統會請使用者確認）。不會還原已經改好的檔案；要還原請使用者在 Coding 面板按「還原」或輸入 `/code revert <編號>`。

# 語法
`EXECUTE: scripts/code_job_cancel_cmd.py <編號|latest>`

# 範例
`EXECUTE: scripts/code_job_cancel_cmd.py latest`

# 回傳
`[PASS] 已要求停止 coding job #N…`。

# 異常
job 已經結束：`[ERROR]`（不用停止）。
