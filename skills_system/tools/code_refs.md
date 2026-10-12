---
type: Tool
title: 找定義與使用處
description: 某個函式、類別、方法或變數在整個專案的定義、宣告、匯入與使用處（Python 用 AST、C／C++ 用掃描器，不會把註解或字串算進來）；跨檔修改前用它列出要一起改的地方。
version: 1.0.0
dependencies: ["python3"]
---

# 用途
改名、改參數、改回傳值之前，先列出「哪些地方要一起改」；也用來回答「這個函式被誰呼叫」。Python 檔用 AST 分成定義（def／class／指派）、匯入（`from … import 名稱`）、使用（讀取、`物件.名稱`、`名稱=` 關鍵字參數）；C／C++ 分成定義（class、有本體的函式與方法、typedef、#define）、宣告（標頭的原型、類別裡的方法宣告）、使用；其他檔案用完整識別字的文字比對另外列出。

# 語法
`EXECUTE: scripts/code_refs_cmd.py <名稱> [path]`
* 名稱：`load_config`、`Inventory`、`Inventory.remove`、`Circle::area`（類別.方法／類別::方法 時，定義只認那個類別裡的）。

# 範例
`EXECUTE: scripts/code_refs_cmd.py tidy_hint agent_core`

# 回傳
`[PASS] code_refs「名稱」：定義 N 處、[宣告 D 處、]匯入 M 處、使用 K 處，共 F 個檔案`，之後依「定義／宣告／匯入／使用／其他檔案」列出 `檔案 L行號: 那一行`。

# 異常
不是合法的識別字：`[ERROR]`。找不到是 `[PASS]` 並提示改用 `code_search`。
