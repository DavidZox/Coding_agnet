---
type: Tool
title: 搜尋程式碼
description: 在整個專案的程式碼裡搜尋字串或正規表示式，依檔案分組、附行號與前後文；自動略過 .git、venv、build 等目錄。
version: 1.0.0
dependencies: ["python3"]
---

# 用途
找某段程式碼、錯誤訊息、設定值出現在哪裡。跟 `search_text` 的差別：自動略過不是原始碼的目錄與二進位檔、可以 `--glob` 只搜某類檔案、`--context` 帶前後文、`--word` 只比對完整識別字；大小寫採 smart case（關鍵字有大寫才區分）。命中數與檔案數由腳本算好。要找某個函式「在哪裡定義、被誰呼叫」用 `code_refs` 比較準。

# 語法
`EXECUTE: scripts/code_search_cmd.py "<關鍵字或正規表示式>" [path] [--glob "*.py"] [--context N] [--word] [--case] [--max N]`

# 範例
`EXECUTE: scripts/code_search_cmd.py "def load_config" .`
`EXECUTE: scripts/code_search_cmd.py "timeout" src --glob "*.py" --context 2`

# 回傳
`[PASS] 搜尋「…」：共 N 處命中，分布在 M 個檔案（…）`、各檔命中數，之後每個檔案一組 `L行號: 內容`。0 處命中也是 `[PASS]`。

# 異常
路徑不存在、或要搜整個 `/`：`[ERROR]`。逾時 8 秒只回傳搜到的部分並註明。
