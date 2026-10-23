---
type: Tool
title: 本機執行 Shell 指令
description: 在本機目前的工作目錄用 bash 執行一行指令（不能互動）；唯讀的指令直接執行，其他的會先請使用者確認。
version: 2.0.0
dependencies: ["bash"]
---

# 用途
其他技能做不到的本機操作（git、建置、套件檢查、docker 查詢、執行腳本）。看檔案、找檔案、改檔案優先用 view_file、
search_text、find_file、file_ops。**不能互動**：不讀標準輸入、沒有終端機，要密碼或確認的指令（sudo、沒加 -y 的 apt、
git 開編輯器）會直接失敗。指令裡的 `cd` 只在這一次有效（之後的目錄用 change_dir 切）。指令結束時背景程序（結尾的 `&`）會一起結束。

# 語法
`EXECUTE: scripts/host_runcmd_cmd.py [--timeout 秒] "<指令>" [--timeout 秒]`
* `指令`：用引號包住，多個用 `&&` 串接；原樣交給 `bash -c`。
* `--timeout`：放最前面或最後面，預設 120 秒、範圍 1～570；逾時會結束整個程序群組並回傳已經收到的輸出。
* 輸出（stdout 與 stderr 合在一起）太長時保留開頭約 12KB 與結尾約 28KB，中間寫省略了幾行；單行超過 2000 字截斷。

# 範例
`EXECUTE: scripts/host_runcmd_cmd.py "git status && git log -n 3 --oneline"`
`EXECUTE: scripts/host_runcmd_cmd.py "colcon build --packages-select nav_pkg 2>&1 | tail -40" --timeout 400`

# 回傳
成功：`[PASS] 指令執行完成（exit code 0，N 秒）：`指令``，接 `## 輸出（N 行）`。grep／diff／test／which 回 exit code 1 時是
`[PASS] … exit code 1 代表沒有找到符合的內容／有差異／條件不成立`（不是錯誤）。失敗：`[ERROR] 指令失敗（exit code N）：…。原因。下一步：…`
＋輸出。最後幾行的括號是附註（cd 沒有保留、背景程序已結束）。

# 異常
* `找不到指令`（127）：用 `which` 確認；沒裝就告訴使用者，不要自己用 sudo 安裝。`權限不足`：請使用者處理。
* `這個指令要互動輸入`：改用非互動參數（`-y`、`git commit -m`）；需要密碼的請使用者自己在終端機執行。
* `bash 語法錯誤`：檢查引號、括號。`程序被 SIGKILL 結束`：可能記憶體不足。
* `[ERROR] 指令逾時`：確實需要更久才加大 --timeout 重試一次；`tail -f`、`watch`、`ros2 topic echo` 這種不會結束的不要用它跑。
* `[ERROR] --timeout …`／`沒有給要執行的指令`：照語法改。`沒辦法啟動 bash`：告訴使用者。
