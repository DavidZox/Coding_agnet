---
type: Skill
title: C++ 程式裡的名稱與設定
description: C++ 程式（.h、.hpp、.cpp、.cc）裡的類別、函式、成員或設定：搜問題提到的名稱與前後幾行，看原文挑出定義、宣告、呼叫或設定的值（附檔案、行號）；原文提到的成員函式或型別接著找
version: 1.0.0
answers: ["位置", "內容"]
topology: {"depends_on": [], "sub_skills": ["search_text", "view_file"]}
parameters: [{"name": "names", "type": "words", "required": true, "desc": "問題裡的 C++ 名稱：類別、函式、成員、型別、命名空間、節點或設定的名稱（照原文寫，好幾個用「、」分開）", "ask": "要查哪個類別、函式或設定的名稱？"}, {"name": "path", "type": "path", "default": ".", "desc": "範圍：套件或目錄", "fetch": {"tool": "find_file", "args": ["{value}", "."]}}, {"name": "exclude", "type": "names", "desc": "範圍裡不要的子目錄名稱（原文寫「不含 a、b」這種）"}]
---

# 什麼時候用
問題問 C++ 程式（寫明 C++、標頭檔、.cpp、.h，或問 C++ 套件裡的類別、成員函式、設定）：某個類別或函式宣告、定義在哪個檔案的第幾行，
哪個成員函式做某件事，某個設定或參數的預設值是多少、在哪裡設定。
要的是程式裡寫了什麼；Python 程式裡的名稱用 py_usage，照文件回答用 doc_lookup。

# 骨架
```json
{"nodes": [
  {"id": "hits", "tool": "search_text",
   "args": ["{names}", "{path}", "--rank", "-C", "2", "--include", "*.h", "--include", "*.hpp", "--include", "*.cpp", "--include", "*.cc",
            {"if": "exclude", "args": ["--exclude-dir", "{exclude}"]}],
   "expect": ["pass", "empty"], "why": "在 C++ 檔裡找問題提到的名稱（同一行含最多個名稱的先列，附前後 2 行）"},
  {"id": "read", "kind": "judgment", "depends_on": ["hits"],
   "goal": "從 C++ 檔裡搜到的行挑出回答問題的那幾行（定義、宣告、呼叫、設定的值）",
   "labels": ["定義", "宣告", "呼叫", "設定的值", "相關"],
   "branches": [
     {"id": "answered", "say": "挑出來的行回答了問題", "need_lines": true},
     {"id": "follow", "say": "這些行提到別的成員函式、型別或名稱，要接著找才回答得了", "params": [{"name": "more", "type": "words"}],
      "add": [{"id": "next", "tool": "search_text",
               "args": ["{more}", "{path}", "--rank", "-C", "2", "--include", "*.h", "--include", "*.hpp", "--include", "*.cpp", "--include", "*.cc",
                        {"if": "exclude", "args": ["--exclude-dir", "{exclude}"]}],
               "expect": ["pass", "empty"], "why": "在 C++ 檔裡找判斷要接著找的名稱"}]},
     {"id": "wider", "say": "要看某一行前後更多內容才看得懂（例如整個函式或建構子）",
      "params": [{"name": "file", "type": "path"}, {"name": "line", "type": "line"}],
      "add": [{"id": "around", "tool": "view_file", "args": ["{file}", "--around", "{line}", "-C", "25"], "why": "看判斷指定的那一行前後"}]},
     {"id": "not_found", "say": "看過的行都沒有寫這件事"}]}
]}
```

# 回退
```json
[{"id": "outside_scope", "when": {"node": "hits", "status": "empty"},
  "change": {"add": [{"id": "wider", "tool": "search_text",
                      "args": ["{names}", ".", "-l", "--include", "*.h", "--include", "*.hpp", "--include", "*.cpp", "--include", "*.cc"],
                      "expect": ["pass", "empty"], "report": "範圍外提到這些名稱的 C++ 檔", "why": "範圍裡沒有：看整個工作目錄有沒有"}]},
  "say": "範圍裡的 C++ 檔沒有這些名稱：在整個工作目錄找一次；回答寫明範圍裡沒有，範圍外有的話在哪些檔案"}]
```

# 策略與 SOP
1. 宣告在標頭檔（.h、.hpp），定義（實作）在 .cpp：問「定義在哪」要的是有函式本體的那一行，不是標頭檔的宣告。
2. 設定的預設值照程式裡寫的值（宣告參數、建構子、設定的結構）回答，附檔案與行號。
3. 只用原文：搜到的行看不出來就接著找或看前後，不要用名稱猜。
