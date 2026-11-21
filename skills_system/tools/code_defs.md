---
type: Tool
title: 程式列舉
description: 一次列出範圍裡每份檔案的行數，與程式檔的類別、函式定義（Python 用 AST、C/C++ 照定義的寫法）；各檔案幾個、總共幾個由腳本算好。
version: 1.0.0
dependencies: []
parameters: [{"name": "path", "required": false, "default": ".", "fetch": "find_file <目錄名稱>"}]
receipt: {"counts": ["files", "lines", "classes", "functions"], "items": ["path", "line", "end", "kind", "name", "qualname"], "fields": ["per_file", "paths", "include", "exclude_dirs", "name", "kind", "timed_out"]}
narrow: {"paths": {"rule": "inside", "arg": "路徑"}, "include": {"rule": "added", "arg": "--include"}}
---

# 用途
要「全部」的時候用：範圍裡有幾份檔案、各幾行、最長的是哪幾份；有哪些類別、哪些函式或方法（名稱符合某種寫法的）、各幾個、總共幾個。
一次列完、數量由腳本算，不用一份一份看。找某個名稱在哪裡被用到用 py_refs（Python）或 search_text；看某一段程式用 view_file。
Python 照語法分（含巢狀與 `_` 開頭的；方法寫成 `類別.方法`）；C/C++ 照定義的寫法找有本體的類別與函式（`類別::方法`），只有宣告（`;` 結尾）的不列。

# 語法
`EXECUTE: scripts/code_defs_cmd.py [路徑…] [--include "<檔名寫法>"] [--exclude-dir <名稱>] [--name "<名稱的寫法>"] [--kind class|def] [--files] [--sort lines]`
* 路徑：目錄或檔案，可多個，預設 `.`，可用 `~`，不能是 `/`。預設略過 build、install、log、.git、node_modules、__pycache__、venv、.venv。
* `--include "*.md"`：只算這種檔名（可重複）。`--exclude-dir 名稱`：多略過一個目錄（可重複）。
* `--name "^test"`：只列名稱符合的定義（正規表示式、分大小寫：`^` 開頭、`$` 結尾）。`--kind class` 只列類別、`--kind def` 只列函式與方法。
* `--files`：每份檔案一行（行數與定義的數量），不列定義。`--sort lines`：照行數由多到少排。
* 最多列 300 份檔案、600 個定義（數量照樣全部算）；最多看 5000 份檔案；逾時 30 秒。

# 範例
`EXECUTE: scripts/code_defs_cmd.py docs --include "*.md" --files --sort lines`　`EXECUTE: scripts/code_defs_cmd.py cam_driver --kind class`
`EXECUTE: scripts/code_defs_cmd.py cam_driver/tests --include "test_*.py" --name "^test" --kind def`

# 回傳
`[PASS] 範圍 <路徑>：N 份檔案、共 L 行；定義：類別 C、函式／方法 F[（篩選）]`，每份檔案一節 `## 路徑（L 行；類別 c、函式 f）`、
每個定義一行（縮排）`  - class 名稱（行 a-b）`／`  - def 類別.方法（行 a-b）`（--files 時每份檔案一行 `- 路徑：L 行；…`）。列不下、沒有算的（二進位檔、
語法錯誤只算行數的）寫在最後一行。沒有符合的檔案：`[PASS] 範圍 … 裡沒有符合的檔案（0 份）`。

# 異常
* `[ERROR] 找不到路徑`：照「相近的路徑」修正。`不列 /`：指定具體的目錄。
* `不支援的選項`、`… 後面需要值`、`--kind 要是 class 或 def`、`--name 的寫法不是合法的正規表示式`：照語法改。
* `[ERROR] 列舉逾時…還沒有看完任何一份檔案`：縮小範圍、加 `--include`。
