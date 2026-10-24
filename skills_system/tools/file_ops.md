---
type: Tool
title: 文件與目錄操作
description: 在本機建目錄、複製、移動／改名、寫入或附加文字檔、取代檔案裡的一段文字；改 YAML 設定檔的一個值用 set；會先請使用者確認。
version: 2.1.2
dependencies: []
---

# 用途
「改」本機的文件（看用 view_file、找用 find_file／search_text）。執行前系統會請使用者確認；覆寫、附加、取代前原檔自動備份到
logs/file_backups/（移動不覆蓋任何東西，不備份）。沒有刪除。只改 UTF-8 文字檔。改 YAML 設定檔的一個值用 `set`：程式找「名稱: 值」那一行、
只換值（縮排、行尾註解保留）；同樣的設定出現在好幾台時加 `--after "name: amr_07"`，只在那一段裡找（不會改到別台）。其他改法用 `replace`，
`--old` 照檔案實際內容寫（先 view_file 看；**不要抄行號 `12→`**）。

# 語法
`EXECUTE: scripts/file_ops_cmd.py <動作> …`（路徑相對於工作目錄，可用 `~`；不能寫 /etc、/usr 等系統目錄）
* `mkdir <目錄>`；`copy <來源> <目的>`；`move <來源> <目的>`（目的是既有目錄時放進去）。目的已存在一律不覆蓋（複製一個檔案、目的已經一模一樣時回 [PASS]，不用再複製）。
* `write <檔案> --text "內容"` 建立或覆寫；`append <檔案> --text "內容"` 加在最後；
  `replace <檔案> --old "原文" --new "新的內容"`：原文要剛好出現一次（`--new ""` 是刪掉原文）。
* `set <檔案> <設定名稱> <新的值> [--after "那一段開頭的字"]`：`--after` 的那一段＝第一個含這幾個字的行，加上後面縮排比它深的行；
  不給 `--after` 時名稱在檔案裡要剛好出現一次。已經是那個值就不改（回 `沒有修改`）。
* 選項順序不拘，內容用雙引號包住（裡面有引號也可以）。跳脫：`\n` 換行、`\t` tab、`\"` 引號、`\\` 反斜線（字面的 `\n` 寫 `\\n`）；
  內容裡已經有真正的換行時只把 `\"` 換成 `"`，其他照原樣寫入。

# 範例
`EXECUTE: scripts/file_ops_cmd.py set config/camera.yaml exposure 20`
`EXECUTE: scripts/file_ops_cmd.py set config/amr_params.yaml max_accel 0.45 --after "name: amr_07"`
`EXECUTE: scripts/file_ops_cmd.py replace notes/maintenance.md --old "狀態：待處理" --new "狀態：已完成"`
`EXECUTE: scripts/file_ops_cmd.py write out/summary.md --text "# 統計\n| 站點 | 筆數 |\n|---|---|\n| p5 | 12 |"`
`EXECUTE: scripts/file_ops_cmd.py move records/2025-03 records/archive/`

# 回傳
`[PASS] 已建立目錄／已複製（N 個檔案）／已移動／已建立（N 行）／已覆寫／已附加／已修改 <檔案> 第 N 行附近：「原文」→「新的」`，
有備份時最後寫 `原本的檔案備份在 <路徑>`。

# 異常
* `出現 0 次`（列出相關的行）：照實際內容改 --old。`出現 N 次（第 a、b 行）`：--old 多帶前後文。`含有…行號`：去掉 `行號→`。
* `找不到來源／檔案`：照相近的路徑修正。`目的已經存在`：換名稱或問使用者。`已經是一個檔案`、`到它自己裡面`、`是目錄`：修正路徑。
* `需要 --text`／`需要 --old 與 --new`／`--old 是空的`／`出現了兩次`／`路徑太多`／`不認識的選項`／`第一個參數要是動作`：照語法改，內容一定加引號。
* `不能在系統目錄操作`、`沒有權限`、`不是 UTF-8 文字檔`、`是二進位檔`、`太大`、`… 失敗`（磁碟）：換路徑或請使用者處理。
