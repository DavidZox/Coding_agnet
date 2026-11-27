---
type: Skill
title: ROS 節點的參數與預設值
description: ROS 節點（C++ 或 Python）在程式裡宣告了哪些參數、各自的預設值：在節點所在的套件或目錄的原始碼裡，列出宣告參數的每一行（預設值寫在那一行；附檔案、行號）
version: 1.0.0
answers: ["內容", "位置"]
topology: {"depends_on": [], "sub_skills": ["search_text", "view_file"]}
parameters: [{"name": "node", "type": "path", "required": true, "desc": "節點所在的套件或目錄：原文寫的節點、套件名稱或路徑（前面有套件或目錄的寫成 a/X）", "ask": "要查哪個節點（或套件）的參數？", "fetch": {"tool": "find_file", "args": ["{value}", "."]}}, {"name": "exclude", "type": "names", "desc": "範圍裡不要的子目錄名稱（原文寫「不含 a、b」這種）"}]
---

# 什麼時候用
問題問某個 ROS 節點（或套件裡的節點）在程式裡有哪些參數、參數的預設值是多少：節點宣告了哪些參數、某個參數沒設定時用什麼值。
答案在節點的原始碼（C++ 或 Python）裡宣告參數的地方。launch 檔或設定檔（yaml）把參數覆寫成多少、某個值從哪個設定檔讀，用 config_trace；
只問 C++ 的類別、函式定義在哪用 cpp_symbol，Python 的名稱用 py_usage。

# 骨架
```json
{"nodes": [
  {"id": "decl", "tool": "search_text", "args": ["declare_parameter|param<|\\.param\\(|get_param\\(", "{node}", "--include", "*.cpp", "--include", "*.cc", "--include", "*.cxx", "--include", "*.hpp", "--include", "*.h", "--include", "*.py", {"if": "exclude", "args": ["--exclude-dir", "{exclude}"]}], "expect": ["pass", "empty"], "report": "程式裡宣告參數的地方", "why": "節點的參數在原始碼裡宣告的那一行（預設值寫在那一行）"}
]}
```

# 回退
```json
[{"id": "no_decl", "when": {"node": "decl", "status": "empty"}, "change": {"ask": "node", "from": "decl"},
  "say": "這個目錄的原始碼沒有宣告參數的地方：節點的程式是不是在別的套件或目錄？還是參數只寫在設定檔或 launch 檔（那要用 config_trace）？"}]
```

# 策略與 SOP
1. 先確定節點的原始碼在哪個套件或目錄（原文寫的節點或套件名稱）；同一個名稱有好幾個目錄時照原文前面寫的套件或目錄選。
2. 每一個參數照宣告那一行寫名稱與預設值；一行看不完整（預設值寫在下一行、或用變數）就看那一行前後（view_file）。
3. 只用原文：程式裡沒寫預設值的照實說沒寫，不要用常識或設定檔的值補；問的是設定檔覆寫成多少再用 config_trace。
