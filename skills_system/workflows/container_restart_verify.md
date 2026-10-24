---
type: Workflow
title: 重新啟動容器並確認
description: 重新啟動一個一直在跑的服務容器、確認它是 Up；有給就在容器裡跑一個唯讀的指令確認設定、把經過寫進紀錄檔（跑完就結束的工作不適用）
version: 0.1.0
dependencies: ["docker_ctl", "docker_runcmd", "file_ops"]
changes_state: true
---

# 用途
「web_cache 被停掉了，重新啟動、確認設定還在、記一筆」這種：先看容器的狀態（結束碼的意思），重新啟動並確認是 Up；使用者要確認容器裡的
設定時，跑一個唯讀的指令看輸出；要留紀錄時把時間、做了什麼、確認結果寫進紀錄檔。

# 需要的資訊
* `{container}`：容器名稱（例：`web_cache`）
* `{check_command}`：起來之後在容器裡跑的唯讀指令（選填，例：`grep max_size /etc/web_cache.conf`）
* `{expect}`：上面那個指令的輸出要看到的字（選填，例：`512M`）
* `{note_file}`：紀錄要附加到哪個檔案（選填，例：`ops_notes/web_cache.md`）

# 步驟
1. 【執行】看容器目前的狀態：`EXECUTE: scripts/docker_ctl_cmd.py status {container}`　檢查：輸出有「[PASS]」
2. 【執行】重新啟動：`EXECUTE: scripts/docker_ctl_cmd.py restart {container}`　檢查：輸出有「Up」
3. 【執行】在容器裡確認設定：`EXECUTE: scripts/docker_runcmd_cmd.py {container} "{check_command}"`　檢查：輸出有「{expect}」
4. 【執行】寫紀錄（開頭的時間與容器由程式填；{note} 寫做了什麼、重新啟動前後的狀態、容器裡確認到的值，照前面的輸出寫）：`EXECUTE: scripts/file_ops_cmd.py append {note_file} --text "## {now} 重新啟動 {container}\n{note}"`　檢查：輸出有「[PASS]」
5. 【告知】回報：重新啟動前後的狀態（第 1、2 步）、容器裡確認到的值（第 3 步）、紀錄寫在哪裡

# 成功判準
* `EXECUTE: scripts/docker_ctl_cmd.py status {container}` 輸出有「Up」

# 異常與注意事項
* 重新啟動之後又停了（第 2 步沒有 Up）：工作流停下來；照第 2 步附的 log 回報原因，不要再重新啟動一次。
* check_command 只放唯讀的指令（cat、grep、ls）；要改容器裡的設定不屬於這個工作流。
* 只適用一直在跑的服務容器（重新啟動後要是 Up）；跑完就結束的工作（備份、批次）重新啟動後本來就會是 Exited，不要用這個工作流——直接 docker_ctl restart，看它回報的 log 有沒有正常跑完。
* 會改變狀態的是第 2 步（重新啟動）與第 4 步（附加紀錄）：開始執行時系統會請使用者確認一次。
