---
type: Workflow
title: 改設定檔的一個值
description: 改某台機器人（或某一段）的一個設定值：只改那一段的那一行（程式找、不靠抄原文）、改完確認，回報改了哪一行；照維運手冊要另外留 .bak 時給 backup
version: 0.3.0
dependencies: ["view_file", "file_ops"]
changes_state: true
---

# 用途
改設定檔裡某一台機器人（或某一個區塊）的一個值，例如「把 configs/robots.yaml 裡 tb4 的 battery_low 改成 18，其他不要動」。
程式在那一台的區塊裡找「名稱: 值」那一行、只換值（file_ops set），同樣的設定在別台不會被改到；改完讀回來確認。
維運手冊規定改之前先備份成同目錄的 .bak 時給 `backup=.bak`；沒有要求就不另外留（file_ops 本來就會把原檔備份到 logs/file_backups/）。

# 需要的資訊
* `{file}`：設定檔的路徑（例：`configs/robots.yaml`）
* `{robot}`：要改的那一台機器人或區塊的名稱（例：`tb4`）
* `{key}`：設定的名稱（例：`battery_low`）
* `{value}`：新的值（例：`18`）
* `{block}`：那一台在設定檔裡區塊開頭那一行的字（選填，預設 `id: {robot}`；設定檔用別的寫法時給，例：`name: {robot}`、`tb4:`）
* `{backup}`：另外留一份同目錄備份的副檔名（選填；使用者說照維運手冊、或要先備份時給 `.bak`）

# 步驟
1. 【執行】看設定檔目前的內容：`EXECUTE: scripts/cat_cmd.py {file}`　檢查：輸出有「[PASS]」
2. 【執行】先備份成同目錄的 {backup}（維運手冊的規定；沒給 backup 就略過）：`EXECUTE: scripts/file_ops_cmd.py copy {file} {file}{backup}`　檢查：輸出有「已複製」
3. 【執行】只改 {robot} 那一段的 {key}（程式在「{block}」開始的那一段裡找那一行，縮排與註解保留）：`EXECUTE: scripts/file_ops_cmd.py set {file} {key} {value} --after "{block}"`　檢查：輸出有「已修改」或「沒有修改」
4. 【執行】確認改好了：`EXECUTE: scripts/cat_cmd.py {file}`　檢查：輸出有「{key}: {value}」
5. 【告知】回報：改了哪一行（第 3 步的「原本」→「新的」）、其他沒有動、備份在哪裡（第 2 步，或 file_ops 自動備份的位置）

# 成功判準
* 第 4 步的輸出有「{key}: {value}」
* 第 2 步的輸出有「已複製」

# 異常與注意事項
* 第 3 步由程式找那一行（file_ops set），不經過模型：「{block}」那一段裡找不到 {key}、或設定檔的區塊不是用「id: <機器人>」開頭時會停下來，照錯誤訊息
  確認設定的名稱，或給 block。2026-10-23 第一版讓判斷點抄「要取代的原文」，e4b 只抄 `battery_low: 15`（tb4、tb5 都有），改了一次還是一樣。
* {file}{backup} 已經存在時第 2 步會停下來（file_ops 不覆蓋）：照實回報，問使用者要不要先把舊的備份改名，不要直接覆蓋。
* 使用者說「其他不要動」又沒有提手冊或備份時不要給 backup（會多出一個檔案）。
* 會改變狀態的是第 2 步（備份）與第 3 步（改值）：開始執行時系統會請使用者確認一次。
