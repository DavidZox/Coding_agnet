---
type: Tool
title: 查 CSV／TSV 表格
description: 查 CSV／TSV 表格：欄位與筆數、篩選、整體或每一組的最大／最小／平均／總和／筆數、排序；數字由腳本算好，可以排成 Markdown 表格。
version: 1.1.0
dependencies: []
---

# 用途
資料表（電量紀錄、匯出的 log、統計）的問題用這個，不要自己寫 python／awk。只讀檔、不改檔。格子照檔案原文顯示（時間戳、`007` 不會被改），
只在比較與計算時當數字。先不帶選項看一次（欄位名稱、型態、範圍、前 5 筆），再依問題加選項；欄位名稱照第一行（不分大小寫）。

# 語法
`EXECUTE: scripts/csv_query_cmd.py <檔案> [--where 欄位<運算子>值]... [--group 欄位] [--min 欄位|--max 欄位|--avg 欄位|--sum 欄位|--count] [--sort 欄位 [--desc]] [--head N] [--cols 欄位1,欄位2] [--markdown]`
* `--where`：運算子 `=`（或 `==`）`!=` `<` `<=` `>` `>=` `~`（包含）`!~`（不包含），可重複（全部都要符合）；拿數字比時空白格不算符合。
* `--min／--max 欄位`：最小／最大的那一筆（整筆列出）；`--avg／--sum 欄位`、`--count`：整體或每一組；只給 `--group` 時算每一組的筆數。
* `--sort`（全是數字照數字排，空白排最後）＋`--head N`：預設 20 筆、上限 60。`--markdown`：Markdown 表格（再用 file_ops 寫入）。
* 檔案上限 100MB、逾時 60 秒。

# 範例
`EXECUTE: scripts/csv_query_cmd.py data/battery.csv`（先看欄位）
`EXECUTE: scripts/csv_query_cmd.py data/battery.csv --group robot --min battery --markdown`
`EXECUTE: scripts/csv_query_cmd.py data/battery.csv --where robot==tb3 --where "battery<25" --count`

# 回傳
`[PASS] 檔案：N 筆、M 個欄位（…）[；符合 … 的有 K 筆]` + 結果表格。同組有好幾筆同樣的最小／最大值時多一欄「同值筆數」。
0 筆符合時列出那個欄位實際有哪些值（`--count` 回 `筆數：0`）。列不完時最後一行說還有幾筆。直接引用表格裡的數字。

# 異常
* `[ERROR] 沒有欄位「…」`：照列出的欄位名稱再查。`[ERROR] 找不到檔案`：照相近的路徑或同目錄的表格修正。
* `[ERROR] 第一個參數要是檔案路徑`、`--where 的格式…`、`不認識的參數`、`--head 後面要是筆數`、`一次只能算一種統計`：照語法改（含空白的值加引號）。
* `[ERROR] 欄位「…」沒有數值`：換數值欄位。`[ERROR] … 是空的`：確認檔案。`[ERROR] 太大`／`逾時`：先用 search_text 找需要的列。
