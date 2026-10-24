---
type: Tool
title: 執行工作流（程式照步驟做）
description: 執行 SKILLS.md〈工作流〉列的多步驟流程：程式照規格一步一步做、跑檢查與成功判準，模型只在判斷點決定值；停在【確認】時 --continue 接著做。
version: 0.1.2
dependencies: ["skills_system/workflows/", "agent_core/workflow.py"]
---

# 用途
使用者的任務正好是某個工作流（例如「工作包卡住了，處理到跑完」「派工作包並確認跑完」）時用它，不要自己一個技能一個技能做：步驟、檢查、
「做完了沒」都由程式照規格判斷，比較穩。只有需要依前面結果決定的值（例如補發給哪一台機器人、處理紀錄的內容）才會問模型。
會改變狀態的步驟在開始時系統會請使用者確認一次（確認畫面列出是哪幾步），不用先問使用者。

# 語法
`EXECUTE: scripts/workflow_run_cmd.py <工作流名稱> 名稱=值 …`
* 名稱與需要的資訊照 SKILLS.md〈工作流〉那一行寫（選填的可以不給）；值有空白就用雙引號包住：`note_file="ops notes/a.md"`。
* `--continue`：工作流停在【確認】時接著做（系統會請使用者確認，不用先問）；`--cancel`：不做了；`--list`：列出全部的工作流與需要的資訊。

# 範例
`EXECUTE: scripts/workflow_run_cmd.py stuck_package_fix wp_id=WP_0815 note_file=notes/maintenance.md`
`EXECUTE: scripts/workflow_run_cmd.py --continue`　`EXECUTE: scripts/workflow_run_cmd.py --list`

# 回傳
第一行：`[PASS] 工作流 <名稱> 完成…`、`…依判斷提早結束：<分支>`（後面的步驟沒做，照結果回報）、`[PASS] ⏸️ 工作流 … 停在第 N 步【確認】…`、
`[PASS] … 成功判準沒過`、`[ERROR] … 在第 N 步沒有完成（原因）`。`## 步驟` 每一步一行：✅／⏭️ 略過／❌，執行的步驟附存檔 `#編號` 與輸出的
第一行，模型決定的值與分支的理由也列出；`## 成功判準` 是程式檢查的結果。回答使用者時照報告寫，要看某一步的完整輸出用 `result_recall <#編號> "<問題>"`。

# 異常
* 沒有這個工作流、參數不對（少了必填的、不認識的名稱）：[ERROR] 列出現有的工作流或需要的資訊；拿不到的值先問使用者，不要猜。
* 在某一步沒有完成：照那一步的輸出回報原因；要修正就照輸出寫的下一步做，不要整個工作流重跑（做過的步驟可能已經改變了狀態）。
* 規格有問題（步驟、腳本、分支寫錯）：[ERROR] 寫明哪裡要改；這次改用技能一步一步做，並告訴使用者規格要修正。
