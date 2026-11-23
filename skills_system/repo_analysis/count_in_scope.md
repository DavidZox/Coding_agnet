---
type: Skill
title: 範圍裡的數量
description: 數範圍裡（目錄、檔案名稱的寫法、不含的子目錄）一段文字出現在幾行（各檔案幾筆、總共幾筆），或名稱符合的檔案有幾個
version: 1.0.0
answers: ["數量"]
topology: {"depends_on": [], "sub_skills": ["search_text", "find_file"]}
parameters: [{"name": "keyword", "type": "text", "desc": "要數的那段文字（錯誤碼、一段寫法；不分大小寫）"}, {"name": "files", "type": "glob", "desc": "只算哪些檔案：檔案名稱的寫法（例如 *.log、test_*.py）"}, {"name": "path", "type": "path", "default": ".", "desc": "範圍：目錄", "fetch": {"tool": "find_file", "args": ["{value}", "."]}}, {"name": "exclude", "type": "names", "desc": "範圍裡不要的子目錄名稱（原文寫「不含 a、b」這種）"}]
---

# 什麼時候用
問「範圍裡有幾個、幾次」，要數的是一段文字（log 的錯誤碼、設定檔的鍵、文件裡的字詞）出現在幾行，或名稱符合的檔案有幾個。
只數，不讀內容：問文件或程式「寫了什麼、會怎樣」的不用這個。
要數的是程式裡的一個名稱（函式、方法、類別、變數）用了幾次，用 py_usage：照字面數會把註解與名稱更長的相似名稱也算進去。

# 骨架
```json
{"nodes": [
  {"id": "files", "if": "files", "tool": "find_file", "args": ["{files}", "{path}", "--type", "f"], "expect": ["pass", "empty"],
   "complete": true, "report": "名稱符合的檔案", "why": "數範圍裡名稱符合的檔案"},
  {"id": "hits", "if": "keyword", "tool": "search_text",
   "args": ["{keyword}", "{path}", {"if": "files", "args": ["--include", "{files}"]}, {"if": "exclude", "args": ["--exclude-dir", "{exclude}"]}, "-l"],
   "expect": ["pass", "empty"], "report": "每個檔案的筆數", "why": "數範圍裡每個檔案有幾行提到這段文字"}
]}
```

# 回退
```json
[{"id": "search_timed_out", "when": {"node": "hits", "timed_out": true}, "change": {"ask": "path", "from": "hits"},
  "say": "範圍太大，搜尋逾時沒有搜完（數字不是全部）：請指定比較小的範圍（下面是目前找到的各子目錄筆數）"}]
```

# 策略與 SOP
1. 範圍照原文：目錄、檔案名稱的寫法、不含的子目錄都要用上，不要搜整個目錄再自己扣。
2. 數量是腳本算好的（search_text 列每個檔案的筆數與總數、find_file 列符合的檔案），不要照抄別的範圍的總數。
3. 一行有好幾次也只算一筆（數的是行）；要的是 Python 名稱的呼叫次數時改用 py_usage。
