---
type: Tool
title: 帶行號讀程式檔
description: 帶行號讀檔：整份、某一段（--from／--lines），或某個函式／類別（--symbol，Python 與 C／C++）。
version: 1.0.0
dependencies: ["python3"]
---

# 用途
看程式碼的內容。跟 `view_file` 的差別：每行有行號（`  12| 內容`）、可以只讀一段，長檔案預設只顯示開頭並說明還有幾行、怎麼繼續讀。只想知道檔案有哪些函式用 `code_ast_reader` 或 `repo_map`，比讀全文省。

# 語法
`EXECUTE: scripts/code_view_cmd.py <file> [--from 行號] [--lines 行數] [--symbol 名稱]`
* 不給範圍：400 行以內整份，更長的只顯示前 250 行。`--lines` 上限 600。
* `--symbol`：只看某個函式或類別（例如 `load_config`、`Inventory.remove`、`Circle::area`；C／C++ 有本體的定義優先於宣告），找不到時列出檔案裡有的名稱。

# 範例
`EXECUTE: scripts/code_view_cmd.py agent_core/plan.py --symbol PlanMixin.plan_text`
`EXECUTE: scripts/code_view_cmd.py web_app/server.py --from 120 --lines 60`

# 回傳
`[PASS] <file>（共 N 行，Python）第 a～b 行[；之後還有 K 行（--from b+1 繼續）]：` + 帶行號的內容。

# 異常
檔案不存在（找檔名用 `find_file`）、是目錄、二進位檔、超過 5MB：`[ERROR]`。
