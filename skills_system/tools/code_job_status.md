---
type: Tool
title: 查 coding job 的進度
description: 查 coding job 的狀態：計畫每一項做到哪、改了哪些檔案、驗證結果、是不是在等使用者決定；list 列出最近的 job。
version: 1.0.0
dependencies: []
---

# 用途
使用者問「改好了嗎」「進度如何」「卡在哪」時用。狀態、完成項數、每一項的摘要與改過的檔案都由腳本整理好，直接引用；在等使用者核准或決定時，提醒使用者到 Coding 面板操作。報告的細節用 `result_recall <報告編號>`，看 diff 用 `code_diff --job <編號>`。

# 語法
`EXECUTE: scripts/code_job_status_cmd.py [編號|latest|list] [--log N]`

# 範例
`EXECUTE: scripts/code_job_status_cmd.py latest`　`EXECUTE: scripts/code_job_status_cmd.py list`　`EXECUTE: scripts/code_job_status_cmd.py 3 --log 10`

# 回傳
`[PASS] coding job #N：<狀態>（A/B 項完成）` + 任務、工作區、計畫各項（✅❌⏭️🔄⬜）、整體驗證、報告存檔編號。

# 異常
找不到 job：`[ERROR]` 並列出現有的編號。
