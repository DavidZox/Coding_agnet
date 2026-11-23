---
type: Skill
title: 沿著 launch、設定檔、程式追一個名稱
description: 一個參數、topic、節點或 launch 檔在 launch、設定檔（yaml、xml）與程式（.py、C++）裡出現在哪：搜名稱與前後 2 行（同一行含最多個名稱的先列，附檔案、行號）；範圍裡沒有就看整個工作目錄。用一次查一站，下一站照結果裡的名稱再用
version: 1.0.0
answers: ["內容", "位置"]
topology: {"depends_on": [], "sub_skills": ["search_text", "view_file"]}
parameters: [{"name": "names", "type": "words", "required": true, "desc": "問題裡要追的名稱：參數、topic、節點、launch 檔或套件的名稱（照原文寫，好幾個用「、」分開）", "ask": "要追哪個參數、topic、節點或 launch 檔？"}, {"name": "path", "type": "path", "default": ".", "desc": "範圍：要追的套件或目錄（launch、設定檔與程式都要在裡面；原文寫的是某個 launch 檔或設定檔時，範圍寫它所在的套件，檔名寫進 names）", "fetch": {"tool": "find_file", "args": ["{value}", "."]}}, {"name": "exclude", "type": "names", "desc": "範圍裡不要的子目錄名稱（原文寫「不含 a、b」這種）"}]
---

# 什麼時候用
問題要跨好幾個檔案追：啟動時某個節點的參數實際是多少（launch 覆寫了程式的預設值）、某個 topic 從哪裡來又被誰用（remap、發布、訂閱）、
某個設定從哪個設定檔讀、值多少、沒寫時的預設值在哪裡。答案要把 launch、設定檔與程式接起來：用一次查一站，照結果裡的下一個名稱
（remap 成的 topic、讀它的程式、載入的設定檔）再用一次。
只問一個名稱定義或呼叫在哪用 py_usage、cpp_symbol；照一份文件回答用 doc_lookup。

# 骨架
```json
{"nodes": [
  {"id": "hits", "tool": "search_text", "args": ["{names}", "{path}", "--rank", "-C", "2", "--include", "*.py", "--include", "*.yaml", "--include", "*.yml", "--include", "*.xml", "--include", "*.launch", "--include", "*.cpp", "--include", "*.hpp", "--include", "*.h", {"if": "exclude", "args": ["--exclude-dir", "{exclude}"]}], "expect": ["pass", "empty"], "why": "在 launch、設定檔與程式裡找問題提到的名稱（同一行含最多個名稱的先列，附前後 2 行）"}
]}
```

# 回退
```json
[{"id": "outside_scope", "when": {"node": "hits", "status": "empty"},
  "change": {"add": [{"id": "wider", "tool": "search_text",
                      "args": ["{names}", ".", "-l", "--include", "*.py", "--include", "*.yaml", "--include", "*.yml", "--include", "*.xml",
                               "--include", "*.launch", "--include", "*.cpp", "--include", "*.hpp", "--include", "*.h"],
                      "expect": ["pass", "empty"], "report": "範圍外提到這些名稱的檔案", "why": "範圍裡沒有：看整個工作目錄有沒有"}]},
  "say": "範圍裡的 launch、設定檔與程式沒有這些名稱：在整個工作目錄找一次；回答寫明範圍裡沒有，範圍外有的話在哪些檔案"}]
```

# 策略與 SOP
1. 啟動時的值以 launch 與它載入的設定檔為準：launch 覆寫的值、remap 之後的名稱，跟程式裡的預設值不一樣時兩個都要寫。
2. 一站一站接：launch 的 remap → 那個節點的程式 → 它發布或讀取的名稱 → 下一個用到的節點；每一站附檔案與行號。要看 launch 裡一個節點的
   整段設定時用 view_file 看那一行前後。
3. 只用原文：沒找到的那一站就說沒找到，不要用名稱猜。
