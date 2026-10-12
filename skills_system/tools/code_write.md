---
type: Tool
title: 建立或刪除檔案（coding worker 專用）
description: coding worker 建立新檔（內容由系統另外請模型輸出），或 --delete 刪除檔案（先備份、可還原）；主對話要改程式請用 code_job_send。
version: 1.0.0
dependencies: ["python3"]
---

# 用途
coding worker 建立新檔案或刪檔用（主對話呼叫會被擋下，改用 `code_job_send`）。args 只給路徑，內容由系統另外請模型輸出整份檔案；父目錄自動建立；內容語法錯誤或有「...」省略時拒絕寫入。檔案已存在時不覆寫（改既有檔案用 `code_edit`）。

# 語法
`EXECUTE: scripts/code_write_cmd.py <檔案> [--payload 內容檔] [--overwrite]`　`EXECUTE: scripts/code_write_cmd.py <檔案> --delete`

# 範例
`EXECUTE: scripts/code_write_cmd.py inventory/discount.py`　`EXECUTE: scripts/code_write_cmd.py old_helper.py --delete`

# 回傳
`[PASS] 已建立 <檔案>（N 行，Python）；Python 語法 OK` + 結構大綱；`[PASS] 已刪除 <檔案>（原檔已備份…）`。

# 異常
檔案已存在、在工作區外、`.git/` 裡、內容語法錯誤：`[ERROR]` 並說明。
