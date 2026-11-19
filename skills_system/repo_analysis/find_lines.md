---
type: Skill
title: 範圍裡提到一段文字的行
description: 在範圍裡（目錄或檔案、檔案名稱的寫法、不含的子目錄）的文字檔（log、設定檔、文件、程式碼）找一段文字，列出提到它的每一行與前後兩行（檔案、行號與內容由程式從檔案取），也算好每個檔案幾筆：答得了在哪幾行、那幾行寫了什麼（log 的時間與訊息、設定的值）
version: 1.0.0
answers: ["位置", "內容", "數量"]
topology: {"depends_on": [], "sub_skills": ["search_text"]}
parameters: [{"name": "keyword", "type": "text", "required": true, "desc": "要找的那段文字（錯誤碼、訊息裡的字、設定的鍵；不分大小寫）", "ask": "要找哪一段文字（錯誤碼、訊息裡的字、設定的鍵）？"}, {"name": "files", "type": "glob", "desc": "只看哪些檔案：檔案名稱的寫法（例如 *.log、*.yaml）"}, {"name": "path", "type": "path", "default": ".", "desc": "範圍：目錄或一個檔案", "fetch": {"tool": "find_file", "args": ["{value}", "."]}}, {"name": "exclude", "type": "names", "desc": "範圍裡不要的子目錄名稱（原文寫「不含 a、b」這種）"}]
---

# 什麼時候用
要看範圍裡提到一段文字的那幾行：在哪個檔案第幾行、那一行與前後寫了什麼。例如 log 裡某個錯誤碼或訊息出現的時間與內容、設定檔裡某個鍵的值與它所在的那一段、
文件或程式裡某段字出現在哪裡。要找的是照字面的一段文字，答案就在提到它的那幾行裡。
只問有幾個、幾次（不用看那幾行寫什麼）用 count_in_scope；程式裡的一個名稱定義在哪、誰呼叫用 py_usage、cpp_symbol（照語法找，註解不算）；
要照一份文件讀懂它的規定用 doc_lookup；參數在 launch、設定檔與程式之間怎麼接起來用 config_trace。

# 骨架
```json
{"nodes": [
  {"id": "hits", "tool": "search_text",
   "args": ["{keyword}", "{path}", {"if": "files", "args": ["--include", "{files}"]}, {"if": "exclude", "args": ["--exclude-dir", "{exclude}"]}, "-C", "2"],
   "expect": ["pass", "empty"], "report": "提到這段文字的行", "lines": true, "why": "列出範圍裡提到這段文字的每一行與前後兩行"}
]}
```

# 回退
```json
[{"id": "search_timed_out", "when": {"node": "hits", "timed_out": true}, "change": {"ask": "path", "from": "hits"},
  "say": "範圍太大，搜尋逾時沒有搜完（列的行不是全部）：請指定比較小的範圍（下面是目前找到的各子目錄筆數）"}]
```

# 策略與 SOP
1. 範圍照原文：目錄或檔案、檔案名稱的寫法、不含的子目錄都要用上，不要搜整個目錄再自己挑。
2. 提到的行與前後兩行由程式照收據從檔案讀（檔案、行號與內容以檔案為準），每個檔案的筆數由程式從收據算；行太多、報告列不下時先拿掉前後行，
   還是列不下的寫明還有幾行、在哪個 #編號。
3. 一行有好幾次也只算一筆（數的是行）；0 筆就是範圍裡沒有一行提到，照實回答。
