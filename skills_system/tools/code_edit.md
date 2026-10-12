---
type: Tool
title: 修改檔案（coding worker 專用）
description: coding worker 修改既有檔案：args 只給檔案路徑，內容（整份檔案或 SEARCH/REPLACE 區塊）由系統另外請模型用一般文字輸出；主對話要改程式請用 code_job_send。
version: 1.0.0
dependencies: ["python3"]
---

# 用途
coding worker 改既有檔案用（主對話呼叫會被擋下，改用 `code_job_send`）。內容不放在 args：worker 決定改哪個檔案後，系統再請模型輸出內容——250 行以內的檔案輸出整份、更長的輸出 SEARCH/REPLACE 區塊——存成 payload 交給腳本。安全網：SEARCH 逐字→忽略行尾空白→忽略縮排依序比對、自動剝掉抄進來的行號；整份輸出裡有「其餘不變／...」或少了四成以上會拒絕；改完語法變壞會拒絕；改檔前備份原檔；只能改工作區內的檔案。

# 語法
`EXECUTE: scripts/code_edit_cmd.py <檔案> [--payload 內容檔] [--whole] [--dry-run]`

# 範例
`EXECUTE: scripts/code_edit_cmd.py inventory/store.py`（coding worker：只填路徑）

# 回傳
`[PASS] 已修改 <檔案>：+A −D 行（套用 N 個區塊）；Python 語法 OK` + diff + 修改後那一段（帶行號）。

# 異常
`[ERROR] <檔案> 沒有修改：…`（SEARCH 對不到時附最像的那一段、對到多處、省略、語法錯誤），照訊息修正後再改一次。
