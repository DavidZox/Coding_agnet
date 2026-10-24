---
type: Tool
title: 查看檔案內容
description: 看本機文字檔（設定檔、log、腳本）的內容，每行附行號；可 --from／--lines 看一段、--tail 看最後幾行。
version: 2.0.1
dependencies: []
---

# 用途
讀本機的文字檔。技能規格文件不用它（`action.command` 填技能名稱就會載入）；容器裡的檔案用 docker_runcmd。
大檔案（log）先用 search_text 找行號，或 `--tail` 看最後幾行，再用 `--from` 看那一段。

# 語法
`EXECUTE: scripts/cat_cmd.py <檔案> [--from N] [--lines M] | [--tail N]`
* `檔案`：一個，可用 `~`。預設從第 1 行列到最後，最多 2000 行、60000 字；單行超過 2000 字截斷。
* `--from N`：從第 N 行開始；`--lines M`：列 M 行（上限 2000）；`--tail N`：只看最後 N 行（不能跟 --from 一起用）。

# 範例
`EXECUTE: scripts/cat_cmd.py config/camera.yaml`　`EXECUTE: scripts/cat_cmd.py agent_core/dispatch.py --from 120 --lines 60`
`EXECUTE: scripts/cat_cmd.py logs/camera.log --tail 50`

# 回傳
`[PASS] 檔案內容 (<路徑>)：共 N 行，顯示第 a-b 行[（上限 2000 行）][；看後面用 --from b+1]`，之後每行 `  行號→內容`。
**行號與 → 是顯示用的，不是檔案內容**：用 file_ops 改檔時 --old 只寫 → 後面的文字。沒顯示完時最後一行寫還有幾行、怎麼接著看。
空檔案：`[PASS] … 空檔案（0 bytes）`。

# 異常
* `[ERROR] 找不到檔案`：照「相近的路徑」修正；找檔名用 find_file。`[ERROR] … 是目錄`：用 list_dir。
* `[ERROR] … 是二進位檔`：照訊息改用對的技能（影像 image_inspect、bag 用 mcap_analyzer／rosout_parser）。
* `[ERROR] 沒有權限讀取`：請使用者處理（不會用 sudo）。`[ERROR] 不是一般檔案`（裝置、FIFO）：不要讀。
* `[ERROR] 只有 N 行，--from 超過了`：改 --from 或用 --tail。`沒有給要看的檔案`／`一次只能看一個`／`不認識的選項`／`--from 後面要是正整數`／`--tail 不能跟 --from 一起用`：照語法改。
* `[ERROR] … 太大`：用 search_text 找關鍵字，或 --from 看開頭。
