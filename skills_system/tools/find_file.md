---
type: Tool
title: 檔案名稱搜尋
description: 依「名稱關鍵字」遞迴找檔案與目錄；結果依目錄分組，標頭算好找到幾個並附最新修改。
version: 2.0.0
dependencies: ["find"]
---

# 用途
不知道檔案在哪一層時，從某個目錄往下找名稱（找檔案內容用 search_text；只看一層、找最新的用 list_dir --newest）。
預設略過 build、install、log、.git、node_modules、__pycache__、venv、.venv 目錄；沒有權限的目錄略過並計數。

# 語法
`EXECUTE: scripts/find_file_cmd.py "<名稱關鍵字>" [路徑] [--type f|d] [--all-dirs]`
* 名稱關鍵字（第一個參數）：名稱含這段文字（不分大小寫）；含 `*` `?` 時照萬用字元比對（`"*.launch.py"`）；含 `/` 時比對整個路徑（`"launch/nav"`）。
* 路徑（第二個參數）：從哪裡開始找，預設 `.`，可用 `~`；不能是 `/`。`--type f` 只找檔案、`d` 只找目錄；`--all-dirs` 連預設略過的目錄也找。
* 最多列 200 個（依路徑排序）；逾時 30 秒。

# 範例
`EXECUTE: scripts/find_file_cmd.py "Modelfile" .`　`EXECUTE: scripts/find_file_cmd.py "*.launch.py" ~/ws/src --type f`
`EXECUTE: scripts/find_file_cmd.py "nav2_params" ~/ws --all-dirs`

# 回傳
`[PASS] 找到 N 個名稱含「…」的項目（F 個檔案、D 個目錄；從 路徑 開始找）[；只列前 200 個]`，第二行 `最新修改：路徑（時間）；其次：…`，
之後每個目錄一節 `## 目錄（N 項）`、每行 `- 名稱`（目錄加 `/`）。最後一行是略過的東西與怎麼縮小。數字直接引用，不要自己數。
找不到：`[PASS] 找不到…（0 個）` 並建議下一步。逾時但有找到：`[PASS] … 逾時沒有找完：目前找到 N 個…不是全部`。

# 異常
* `[ERROR] 找不到搜尋的目錄`：照相近的路徑修正（不會改搜 .）。`[ERROR] … 是檔案，不是目錄`：路徑要給目錄。
* `[ERROR] 缺少名稱關鍵字`／`只給了路徑`：寫成 `"<關鍵字>" <路徑>`；只想列目錄用 list_dir。
* `[ERROR] 參數太多`：一次一個關鍵字，含空白的加引號。`不支援的選項`、`--type 要是 f 或 d`：照語法改。`不從 / 開始找`：給具體目錄。
* `[ERROR] 逾時…還沒有找到任何一個`：從子目錄開始、或用更精確的關鍵字。`沒辦法執行 find`：告訴使用者。
