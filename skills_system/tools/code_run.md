---
type: Tool
title: 在專案目錄執行指令（coding worker 專用）
description: coding worker 在工作區執行指令（跑程式、建置、看版本、git 查詢），有安全檢查與逾時；主對話執行指令用 host_runcmd、跑測試用 code_test。
version: 2.0.0
dependencies: ["bash"]
---

# 用途
coding worker 跑程式確認行為（例如 `python3 -m inventory.cli --help`、`./build/geometry_cli /tmp/in.txt`）或建置（`cmake --build build`、`make`）。執行前的安全檢查會擋下：sudo、rm／mv（刪檔改用 `code_write --delete`）、chmod、網路（curl／wget）、安裝套件、`make install`／`cmake --install`、會改版本紀錄的 git、`sed -i`、寫到工作區以外的轉向、`$( )`。指令裡的 `python3`／`pytest`／`cmake` 用專案的虛擬環境或 harness 的 venv，gtest 的 include／lib 路徑已經設好。逾時會終止整個程序群組。

# 語法
`EXECUTE: scripts/code_run_cmd.py [--timeout 秒] "<指令>"`（預設 120 秒、上限 570）

# 範例
`EXECUTE: scripts/code_run_cmd.py "python3 -m inventory.cli --file /tmp/x.json report"`

# 回傳
`[PASS] 指令完成（exit 0，X 秒）：<指令>` + 輸出；非 0 結束：`[ERROR] 指令失敗（exit N）` + 輸出。測試指令（pytest、ctest、gtest）的通過／失敗數放在標頭；編譯錯誤與連結錯誤整理在輸出最前面（不會被長輸出截掉）。

# 異常
被安全檢查擋下：`[ERROR] 不允許：…——<該怎麼做>`。
