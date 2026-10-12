---
type: Tool
title: 文件與目錄操作
description: 在本機建目錄、複製、移動／改名、寫入或附加文字檔、取代檔案裡的一段文字（例如改設定檔的一個參數）；會先請使用者確認。
version: 1.0.0
dependencies: []
---

# 用途
需要「改」本機的文件時用（看用 view_file、找用 find_file／search_text）。會改變檔案，執行前系統會請使用者確認；
覆寫、附加、取代、移動之前原本的檔案會自動備份到 harness 的 logs/file_backups/（不在使用者的目錄留下 .bak）。沒有刪除功能。
改設定檔只改要改的那一行：用 `replace`，`--old` 照檔案的實際內容寫（先用 view_file 看），不要整份重寫。

# 語法
`EXECUTE: scripts/file_ops_cmd.py <動作> …`（路徑相對於目前的工作目錄）
* `mkdir <目錄>`；`copy <來源> <目的>`（目錄整個複製，目的已存在就不覆蓋）；`move <來源> <目的>`（目的是既有目錄時放進去）
* `write <檔案> --text "內容"`：建立或覆寫（`\n` 代表換行，可以寫多行，例如 Markdown 表格）；`append <檔案> --text "內容"`：加在最後
* `replace <檔案> --old "原文" --new "新的內容"`：原文要剛好出現一次

# 範例
`EXECUTE: scripts/file_ops_cmd.py replace configs/nav/nav_params.yaml --old "max_vel_x: 0.5" --new "max_vel_x: 0.3"`
`EXECUTE: scripts/file_ops_cmd.py write reports/battery.md --text "# 電量\n| 機器人 | 最低 |\n|---|---|\n| tb1 | 21.1 |"`
`EXECUTE: scripts/file_ops_cmd.py move logs/2026-09-28 logs/archive/`　`EXECUTE: scripts/file_ops_cmd.py copy templates/mission_template missions/patrol_b`

# 回傳
`[PASS] 已修改／建立／覆寫／附加／複製／移動 …`（附備份的位置）。

# 異常
找不到來源、目的已經存在、原文出現 0 次或好幾次（會列出檔案裡相關的行）、系統目錄：`[ERROR]` 說明原因，照著修正參數再試。
