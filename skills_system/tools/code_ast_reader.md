---
type: Tool
title: AST 程式碼結構化閱讀
description: 用 AST 讀一個 Python 檔的結構（常數、類別、函式的完整簽名、第一行 docstring、每個 def／class 的行號範圍），不必讀全文；--refs 列出一個名稱在檔案裡的每一處。
version: 2.2.0
dependencies: []
parameters: [{"name": "path", "required": true, "fetch": "find_file <檔名>.py"}]
receipt: {"counts": ["lines", "classes?", "functions?", "constants?", "refs?", "defs?", "calls?", "imports?", "assigns?", "others?"], "items": ["name", "qualname?", "kind", "async?", "line", "decorator?", "end?", "parent?", "private?", "scope?", "text?", "path?", "in_class?"], "fields": ["path", "constants?", "refs?"]}
---

# 用途
先看一個 `.py` 檔有哪些類別、函式與常數，再用 view_file `--from 行號 --lines 行數` 只讀需要的那一段。簽名含預設值、`/`、`*`、
關鍵字參數與型別標註。其他語言或設定檔用 view_file；找某個名稱在哪些檔案用 search_text。逾時 15 秒。
`--refs <名稱>` 改成列出這個名稱在檔案裡的每一處：定義、呼叫、import、指定、其他用到，各附行號與所在的函式（註解與字串裡提到的不算）。

# 語法
`EXECUTE: scripts/code_ast_reader_cmd.py <檔案.py> [--no-docstrings] [--private] [--refs <名稱>]`
* `<檔案.py>`：一個 Python 檔（或第一行是 python 的 `#!` 的腳本），可用 `~`。
* `--no-docstrings`：不印 docstring。`--private`：也列 `_` 開頭的函式、方法與常數（預設不列，標頭寫有幾個沒列）。
* `--refs <名稱>`：一個 Python 的名稱（`a.b` 只寫最後一段）。
* 最多列 400 個 def／class；常數的值超過 80 字截斷。

# 範例
`EXECUTE: scripts/code_ast_reader_cmd.py agent_core/dispatch.py`
`EXECUTE: scripts/code_ast_reader_cmd.py scripts/ls_cmd.py --private --no-docstrings`
`EXECUTE: scripts/code_ast_reader_cmd.py agent_core/dispatch.py --refs run_script`

# 回傳
`[PASS] <檔案> 的結構：共 N 行；C 個類別、F 個函式／方法[；K 個 _ 開頭的私有項目沒有列]`，`模組說明：…`，
`## 常數（N 項）`（`- NAME = 值（行 12）`），`## 類別與函式（N 項）`：`class Foo(Base):  行 10-80`、縮排的
`def bar(self, a, b=2, *, c=None) -> int  行 20-35`、下一行 `"""docstring 第一行"""`；行號從 def／class 那一行算，有裝飾器的
在上一行另外寫（`@staticmethod  行 19`）。
--refs：`[PASS] <檔案> 裡「名稱」出現 N 處（AST）：定義 a、呼叫 b、import c、指定 d、其他用到 e`，每一種一節，每行
`- 行 45（在 Foo.run）：那一行的原始碼`（定義寫行號範圍，有裝飾器的另外寫「裝飾器在行 N」）。沒有：`[PASS] <檔案> 裡沒有「名稱」`。

# 異常
* `[ERROR] 找不到檔案`：照相近的路徑修正；`沒有權限`、`無法讀取`：請使用者處理。`[ERROR] … 是目錄`：先用 find_file `"*.py"` 找檔案，再對單一檔案執行。
* `[ERROR] … 不是 Python 檔`：用 view_file。`[ERROR] … 有語法錯誤`：照提示用 view_file 看那幾行。
* `[ERROR] 一次只能解析一個檔案`／`不支援的選項`／`--refs 的名稱要是一個 Python 的名稱`：照語法改。`[ERROR] 解析…逾時`：用 search_text `"def |class "` 或 view_file --from。
