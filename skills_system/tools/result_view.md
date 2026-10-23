---
type: Tool
title: 讀工具結果存檔的一段原文或大綱
description: 讀某個工具結果存檔的第 N 行起 M 行（行號＝提煉結果、result_grep 引用的行號），或用 --outline 看原文有哪幾節、各在第幾行。
version: 2.0.0
dependencies: []
---

# 用途
提煉結果的每條事實附了原文的行號（「行 40-42」）、`result_grep` 給的是命中的行號；要看那幾行的完整原文、一則完整的訊息或一段錯誤堆疊時，用它從那一行讀一段。
不知道從哪裡看起：先 `--outline` 列出原文的章節與行號。不會重跑工具。

# 語法
`EXECUTE: scripts/result_view_cmd.py <編號|latest> [--from 行號] [--lines 行數] [--outline]`
* `--from`：原文的行號（工具輸出的第 1 行＝行 1），預設 1。`--lines`：行數，預設 80（上限 300）。
* `--outline`：只列大綱（每個章節標題的行號與行數）。

# 範例
`EXECUTE: scripts/result_view_cmd.py 16 --from 120 --lines 40`
`EXECUTE: scripts/result_view_cmd.py 16 --outline`

# 回傳
`[PASS] #編號 腳本（時間，狀態）｜指令｜原文共 N 行；顯示第 a～b 行` + `當時的任務：…` + 每行 `  行號→內容`；還沒到最後一行會提示 `--from` 的下一個行號。
`--outline`：每節一行 `- 行 n：標題（k 行）`；沒有章節標題的輸出會說明改用 `--from` 分段看。

# 異常
* 起始行超過總行數：`[ERROR]`，改小 `--from` 或先 `--outline`。
* 找不到編號：用 `result_list` 確認；檢索清單上有、檔案不在＝超過保留上限被清掉，照實告訴使用者。
