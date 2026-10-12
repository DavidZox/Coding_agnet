---
type: Tool
title: 查 CSV／TSV 表格
description: 查 CSV／TSV 表格：欄位與筆數、篩選、整體或每一組的最大／最小／平均／總和／筆數、排序；數字由腳本算好，可以排成 Markdown 表格。
version: 1.0.0
dependencies: []
---

# 用途
資料表（電量紀錄、匯出的 log、統計）的問題用這個，不要自己寫 python／awk。只讀檔、不改檔。
先不帶選項看一次（欄位名稱、型態、範圍、前 5 筆），再依問題加選項；欄位名稱照第一行的寫法（不分大小寫）。

# 語法
`EXECUTE: scripts/csv_query_cmd.py <檔案> [--where 欄位<運算子>值]... [--group 欄位] [--min 欄位|--max 欄位|--avg 欄位|--sum 欄位|--count] [--sort 欄位 [--desc]] [--head N] [--cols 欄位1,欄位2] [--markdown]`
* `--where`：運算子 `=` `!=` `<` `<=` `>` `>=` `~`（包含），可以重複（全部都要符合）。
* `--min／--max 欄位`：最小／最大的那一筆（整筆列出，看得到時間等其他欄位）；加 `--group 欄位` 就是每一組各一筆。
* `--avg／--sum 欄位`、`--count`：整體或每一組的平均、總和、筆數。`--sort`＋`--head`：排序後的前 N 筆。
* `--markdown`：結果排成 Markdown 表格（要寫進報告時用，再用 file_ops 寫入）。

# 範例
`EXECUTE: scripts/csv_query_cmd.py data/battery.csv`（先看欄位）
`EXECUTE: scripts/csv_query_cmd.py data/battery.csv --group robot --min battery --markdown`（每台機器人電量最低的那一筆）
`EXECUTE: scripts/csv_query_cmd.py data/battery.csv --max temperature`　`EXECUTE: scripts/csv_query_cmd.py data/battery.csv --where robot=tb3 --where battery<25 --count`

# 回傳
`[PASS] 檔案：N 筆、M 個欄位（…）` + 結果表格。同一組有好幾筆同樣的最小／最大值時，多一欄「同值筆數」。直接引用表格裡的數字與時間。

# 異常
欄位不存在：`[ERROR]` 並列出全部欄位，照列出的名稱再查一次。
