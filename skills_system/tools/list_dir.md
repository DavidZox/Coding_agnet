---
type: Tool
title: 查看目錄清單
description: 列出本機某一層目錄（不含子目錄）並算好數量與最新修改；可 --filter 關鍵字計數、--newest 依修改時間排序。
version: 1.5.0
dependencies: []
---

# 用途
列出本機某一層目錄（容器內的目錄用 docker_runcmd；要找子目錄裡的檔案用 find_file）。標頭由腳本算好「共 N 項（幾個檔案、幾個目錄）」，並附「最新修改：A（時間）；其次：B、C」。使用者問「有幾個 X」「哪個最新」時用 `--filter`／`--newest` 讓腳本算，直接引用，不要自己數或比時間。

# 語法
`EXECUTE: scripts/ls_cmd.py [path] [--filter 關鍵字] [--newest [N]]`
* `path`：一個目錄，預設目前工作目錄，可用 `~`。舊的 ls 旗標（`-la`）會忽略。
* `--filter 關鍵字`：只列名稱含關鍵字的（不分大小寫）。`--newest [N]`：依修改時間新→舊只列前 N 項（預設 5）。
* 最多列 200 行；逾時 5 秒。

# 範例
`EXECUTE: scripts/ls_cmd.py ~/ws/src`　`EXECUTE: scripts/ls_cmd.py launch --filter .launch.py`　`EXECUTE: scripts/ls_cmd.py logs --newest 3`

# 回傳
`[PASS] 目錄列表 (<path>)：共 N 項（F 個檔案、D 個目錄[，其中 L 個是連結]）[；名稱含「…」的 K 項][；只列前 200 行]`，接 `最新修改：…`，
再分 `## 目錄（N 項）`、`## 檔案（N 項）`（用 --newest 時是 `## 依修改時間新→舊（N 項）`）。每行「權限 大小(bytes) 修改時間 名稱」：目錄加 `/`，
連結寫成 `名稱@ → 指向的路徑`（指向目錄的連結算目錄）。截掉時最後一行說怎麼看其他的。

# 異常
* `[ERROR] 找不到目錄`：照「相近的路徑」修正；容器裡的路徑改用 docker_runcmd。
* `[ERROR] … 是檔案，不是目錄`：看內容用 view_file。`[ERROR] 一次只能列一個目錄`：分開執行，含空白的路徑加引號。
* `[ERROR] 沒有權限讀取目錄`：換有權限的目錄，或請使用者自己查看（不會用 sudo）。
* `[ERROR] 不認識的選項`／`--filter 後面需要關鍵字`：照語法改。`[ERROR] 逾時`、`無法讀取目錄`（裝置錯誤）：目錄太大或掛載裝置沒回應，改列子目錄或用 find_file。
* `[ERROR] … 是失效的連結`：改用連結指向的實際位置。
