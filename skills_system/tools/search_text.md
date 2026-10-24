---
type: Tool
title: 檔案內容搜尋
description: 在檔案「內部文字」裡搜關鍵字（a|b 同義詞、不分大小寫），命中依檔案分組、筆數由腳本算好。
version: 2.0.2
dependencies: ["grep"]
---

# 用途
找「哪些檔案、哪幾行含某段文字」（log 的錯誤碼、程式裡的參數名稱）。找檔名用 find_file，看整個檔案用 view_file。
預設略過 build、install、log、.git、node_modules、__pycache__、venv、.venv 目錄（名稱剛好是這些的目錄，例如 colcon 產生的 log／；`logs/` 這種名稱不同的照搜，指定的路徑本身在這些目錄裡也照搜），二進位檔不搜。Log 檔（.log）、設定檔都是文字，直接搜。

# 語法
`EXECUTE: scripts/grep_cmd.py "<關鍵字>" [路徑…] [選項]`
* 關鍵字：不分大小寫，同義詞用 `|`（`error|fail`），可用正規表示式（不合法時自動照字面搜）。以 `-` 開頭的寫 `-e "--timeout"`。
* 路徑：檔案或目錄，可多個，預設 `.`，可用 `~`，不能是 `/`。
* 選項只有：`-w` 整個字、`-F` 照字面、`--case` 分大小寫、`-l` 只列檔名與筆數、`-C N` 前後 N 行（上限 5）、`--include "*.py"`（可重複）、
  `--exclude-dir 名稱`、`--all-dirs` 連預設略過的目錄也搜。
* 每檔最多列 20 筆、總共 200 筆（-C 時 10／50；只搜一個檔案時 200），單行超過 300 字截斷；逾時 30 秒。

# 範例
`EXECUTE: scripts/grep_cmd.py "Traceback" logs`　`EXECUTE: scripts/grep_cmd.py "use_sim_time" ~/ws/src --include "*.yaml"`
`EXECUTE: scripts/grep_cmd.py "error|fail" logs/camera.log -C 2`

# 回傳
`[PASS] 搜尋「…」：共 N 筆命中，分布在 M 個檔案（…）[；只列前 K 筆]`，每個檔案一節 `## 路徑（N 筆）`、每行 `  行號→內容`
（-C 時命中行標 `>`），列不下的在 `## 其他命中的檔案`。最後一行寫略過了什麼（沒有權限的路徑、預設略過的目錄）與怎麼縮小。
找不到：`[PASS] 找不到符合「…」的內容（0 筆）`。逾時但有結果：`[PASS] … 逾時沒有搜完：目前找到 N 筆…不是全部`。

# 異常
* `[ERROR] 找不到路徑`：照相近的路徑修正。`不搜 /`：指定具體的目錄。
* `缺少要搜的關鍵字`／`只給了路徑`：寫成 `"<關鍵字>" <路徑>`。`不支援的選項`、`… 後面需要值`：只用上面的選項。
* `逾時…還沒有找到任何一筆`：縮小路徑、加 `--include`。`執行失敗（grep exit code 2）`、`沒辦法執行 grep`：照訊息修正，不行就告訴使用者。
