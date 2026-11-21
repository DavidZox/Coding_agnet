---
type: Tool
title: Python 名稱的每一處
description: 一個 Python 的名稱在範圍裡的每一處（AST：定義、呼叫、import、指定、其他用到），附檔案、行號與所在的函式；各檔案幾處、總共幾處由腳本算好。
version: 1.1.0
dependencies: []
parameters: [{"name": "name", "required": true, "ask": "要找哪一個 Python 的名稱（函式、方法、類別、變數）？"}, {"name": "path", "required": false, "default": ".", "fetch": "find_file <目錄名稱>"}]
receipt: {"counts": ["refs", "files", "defs", "calls", "imports", "assigns", "others", "scanned"], "items": ["name", "kind", "line", "scope", "text", "path", "qualname?", "in_class?", "decorator?", "end?"], "fields": ["per_file", "name", "paths", "kind", "exclude_dirs", "cpp_files", "syntax_errors", "timed_out"]}
narrow: {"paths": {"rule": "inside", "arg": "路徑"}}
---

# 用途
Python 程式裡的一個名稱（函式、方法、類別、變數）定義在哪、哪裡呼叫或用到、哪些檔案用了幾次：整個範圍一次查完。照語法分，註解與字串裡提到的、
名稱更長的相似名稱都不算，import 不算呼叫，數量比照字面搜尋準。只看 Python 檔；範圍裡的 Python 沒有、C/C++ 檔有這個名稱時，回覆會寫是哪幾份
（C/C++ 用 search_text 或 code_defs）。找一段文字（不是名稱）用 search_text；一個檔案的結構用 code_ast_reader。

# 語法
`EXECUTE: scripts/py_refs_cmd.py <名稱> [路徑…] [--exclude-dir <名稱>] [--include "<檔名寫法>"] [--kind <種類>]`
* 名稱：一個 Python 的名稱（`a.b` 只寫最後一段）。
* 路徑：目錄或檔案，可多個，預設 `.`，可用 `~`，不能是 `/`。預設略過 build、install、log、.git、node_modules、__pycache__、venv、.venv。
* `--exclude-dir 名稱`：多略過一個目錄（可重複）。`--include "test_*.py"`：只看這種檔名（可重複；預設全部的 Python 檔）。
* `--kind call`：只列這幾種（def 定義、call 呼叫、import、assign 指定、ref 其他用到；幾種用 `|` 分開：`def|call`）。不加就是全部。
* 最多列 400 處（數量照樣全部算）；最多看 5000 份檔案；逾時 30 秒。

# 範例
`EXECUTE: scripts/py_refs_cmd.py start_capture cam_driver`　`EXECUTE: scripts/py_refs_cmd.py CameraNode . --exclude-dir tests --kind "def|call"`

# 回傳
`[PASS] 「名稱」在 <路徑> 的 Python 程式裡出現 N 處、M 份檔案（AST）：定義 a、呼叫 b、import c、指定 d、其他用到 e`，每份檔案一節
`## 路徑（N 處：…）`，每一處一行（縮排）`  - 呼叫 行 45（在 類別.函式）：那一行的原始碼`（定義寫行號範圍，從 def／class 那一行算，
有裝飾器的另外寫「裝飾器在行 N」；模組層寫「模組層」）。
沒有：`[PASS] 範圍 … 的 Python 程式裡沒有「名稱」（AST；看了 K 份 Python 檔…）`，C/C++ 檔有的話列出來。

# 異常
* `[ERROR] 找不到路徑`：照「相近的路徑」修正。`不搜 /`：指定具體的目錄。
* `沒有給要找的名稱`、`名稱要是一個 Python 的名稱`：只寫名稱本身（不是句子、路徑或 `a.b`）；找一段文字用 search_text。
* `不支援的選項`、`… 後面需要值`、`--kind 要是…`：照語法改。`[ERROR] 搜尋逾時…`：縮小範圍。
