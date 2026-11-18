---
type: Skill
title: Python 的名稱用在哪裡
description: 程式裡的一個名稱（函式、方法、類別、變數）定義在哪、哪裡呼叫或用到（在 .py 檔裡照語法找：每一處的檔案、行號與所在的函式，各檔案用了幾次、總共幾次）
version: 1.0.0
answers: ["位置", "數量"]
topology: {"depends_on": [], "sub_skills": ["search_text", "code_ast_reader"]}
parameters: [{"name": "name", "type": "name", "required": true, "desc": "問題問到的那個名稱本身：要找它定義在哪、被誰用到的那一個（問題寫「誰呼叫 X」「哪些檔案用了 X」就是 X；只寫名稱，不要寫成句子）", "ask": "要查哪一個函式、類別或變數？"}, {"name": "path", "type": "path", "default": ".", "desc": "範圍：套件、目錄或檔案", "fetch": {"tool": "find_file", "args": ["{value}", "."]}}, {"name": "exclude", "type": "names", "desc": "範圍裡不要的子目錄名稱（原文寫「不含 a、b」這種）"}]
---

# 什麼時候用
問題提到程式裡的一個名稱（函式、方法、類別、變數這種識別字），要知道它定義在哪、哪些地方呼叫或用到它、有沒有人用、改它會影響哪裡。
也用來數：哪些檔案用了它、各幾次、總共幾次——呼叫一個函式或方法（不管問題說的是呼叫、建立還是宣告）就是用到這個名稱。
它在 .py 檔裡照語法分：註解、字串與名稱更長的相似名稱不會算進去，數量比照字面搜尋準；範圍裡的 Python 程式沒有這個名稱時，報告會寫明。
問題寫明是 C++ 或其他語言（或問標頭檔、.cpp）才不用這個；沒寫是哪種語言就用這個，不要從名稱的樣子猜語言。

# 骨架
```json
{"nodes": [
  {"id": "hits", "tool": "search_text", "args": ["{name}", "{path}", "-w", "--include", "*.py", {"if": "exclude", "args": ["--exclude-dir", "{exclude}"]}],
   "expect": ["pass", "empty"], "complete": true, "why": "找出提到這個名稱的 .py 檔（整個字）"},
  {"id": "refs", "tool": "code_ast_reader", "args": [{"from": "hits", "field": "path"}, "--refs", "{name}"], "depends_on": ["hits"],
   "expect": ["pass", "empty"], "complete": true, "report": "名稱的每一處",
   "why": "每個檔案用 AST 分出定義、呼叫、import 與所在的函式（只在註解或字串裡提到的檔案是 0 處）"}
]}
```

# 回退
```json
[{"id": "outside_scope", "when": {"node": "hits", "status": "empty"},
  "change": {"add": [{"id": "wider", "tool": "search_text", "args": ["{name}", ".", "-w", "--include", "*.py"], "expect": ["pass", "empty"],
                      "report": "範圍外提到這個名稱的檔案", "why": "範圍裡沒有：看整個工作目錄有沒有"}]},
  "say": "範圍裡找不到這個名稱：在整個工作目錄找一次；回答寫明範圍裡沒有，範圍外有的話在哪裡"},
 {"id": "too_many_lines", "when": {"node": "hits", "truncated": true}, "change": {"ask": "path", "from": "hits"},
  "say": "提到這個名稱的地方太多，一次看不完：請指定比較小的範圍（下面是各子目錄的筆數）"},
 {"id": "too_many_files", "when": {"node": "refs", "capped": true}, "change": {"ask": "path", "from": "hits"},
  "say": "提到這個名稱的檔案太多，一次看不完：請指定比較小的範圍（下面是各子目錄的筆數）"}]
```

# 策略與 SOP
1. 先找程式裡的名稱，不要先讀文件或規格書：要的是程式的定義與呼叫。
2. 每個檔案用 AST 分出定義、呼叫、import 與其他用到；import 不是呼叫，註解與字串裡提到的也不是。
3. 數量由程式從收據算；每一處附檔案、行號與所在的函式。
