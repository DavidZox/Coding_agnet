# 根因分析的參考（第九輪版本，commit 62e0534）

2026-10-16 起，數據分析改成只做事實報告，只要有 .mcap 就能用。原本的源碼脈絡和因果推論從主流程拿掉。
這個資料夾保留第九輪的版本，給之後開發根因 agent 時參考。

這裡的程式只供閱讀，不會被執行或 import：裡面引用的模組（例如 `agent_core/source_index.py`）在主流程裡已經沒有了。
要實際跑第九輪的版本，另開一個 worktree：`git worktree add ../Coding_agnet_r9 62e0534`。

## 檔案

| 檔案 | 看什麼 |
|---|---|
| `agent_core/source_index.py` | 源碼索引：Python 用 AST、C++ 用掃描器；推出這次在執行的節點、每個 Topic 的發布者與訂閱者、Log 裡的代碼在源碼成立的條件（`JobSource`） |
| `agent_core/analysis_job.py` | 第九輪整條分析流程；跟根因有關的段落見下一節 |
| `agent_core/schemas.py` | `ANALYSIS_CAUSAL_SCHEMA`（因果推論的輸出）、`ANALYSIS_ASSIGN_SCHEMA`（規劃第二步）、`ANALYSIS_PLAN_SCHEMA_SOURCE` |
| `agent_core/config.py` | `ANALYSIS_SOURCE_*`、`ANALYSIS_PLAN_TWO_STEP`、`ANALYSIS_PROGRAM_HINTS`、`ANALYSIS_MAX_ROUNDS` |
| `analysis_agents/orchestrator_causal.md` | 因果推論那一步的 system prompt |
| `analysis_agents/`（其他三份） | 第九輪的規劃、worker、Synthesizer prompt |
| `evals/analysis_selftest.py` | 離線自我測試，含因果核對、源碼索引、觀測角度、到最後的值 |
| `evals/analysis_regression.py`、`analysis_regression_cases.json` | 根因版的評分：時間線、根因、錯誤說法、定性、上游 |
| `test_data/cases_5090.json`、`test_data/tools/make_cases.py` | 14 份測試數據的根因評分標準。只在本機：.gitignore 的 `test_data/` 也套用到這裡，不會進 git |
| `doc/數據診斷的流程_第九輪.puml` | 第九輪的流程圖（圖檔：`git show 62e0534:doc/數據診斷的流程.png > 流程.png`） |

## analysis_job.py 裡跟根因有關的部分

- **源碼脈絡**：`_analysis_source`、`_source_text`（依角色裁切的源碼段落）、`_source_doc`、`_signal_source`
- **規劃分兩步**：`_analysis_assign`、`_assign_user`；觀測角度：`_view_issue`
- **因果推論**：`_analysis_causal`、`_causal_user`（輸入）、`_causal_issues`（程式核對），以及交回兩次和「程式核對：未修正」標示
- **給判斷用的程式提示**：
  - `_coverage_gaps`：Log 提到、但沒錄到的輸入
  - `_background_codes`：背景條件
  - `_flow_block`、`_segment_notes`
  - `_end_states`：到最後的值、最後一次停止
- **用詞核對**：`_relies_on`、`_dismissed`、`_NOT_THE_CHANGE`、`_unlisted`
- **補分析只往上游**：`_upstream_of`
- **程式補時間窗**：`_coverage_signals`

## 學到的事

數字都是 gemma4:26b，每份數據跑 5 次。

1. **源碼解決了共用脈絡的問題，解決不了判斷的問題**（第四輪）。拿 /cmd_vel 當 /cmd_vel_raw 證據的情況從 15/20 降到 1/20；但沒有程式提示時，「這是正常運作」的定性是 0/10。
2. **整段源碼交給 Orchestrator 規劃，它反而漏挑指令開始的 Log**：20/20 降到 7/20（第五輪）。所以改成分兩步：先挑訊號，再帶源碼分派。
3. **推測一旦進到事實層，就會一路傳下去**（第七輪）。worker 的任務說明帶了 Orchestrator 的推測，worker 就照著寫「中斷」，跟量到的相反（32/40）。所以根因 agent 的輸入只能是事實報告，不能帶規劃時的假設。
4. **錯誤集中在「為什麼」**（第八輪，110 次）。交回修正有 27 次在因果推論那一步，worker 只有 4 次、Synthesizer 2 次、規劃 1 次；扣分的 11 個錯誤全部在因果推論。
5. **第九輪最好的結果**：源碼加程式提示 308/310，只給源碼 304/310。剩下的錯誤都是「為什麼」：
   - 把到最後仍維持的狀態，歸因到之後才發生的事件（motorhold，兩種設定各 2/5）
   - 沒有說系統的反應照不照設計
   - 拿背景條件當原因
6. **程式核對擋得住錯的出處和明顯的用詞，擋不住「為什麼」推錯**。後者只能一條條加片語規則，越補越多，這是改成只做事實報告的原因。

## 原本規劃的根因 agent

2026-10-16 已經同意，後來延後。

- **輸入**：使用者的問題、事實報告（加上事實的附錄）。不給 Orchestrator 規劃時的假設。
- **工具**：唯讀的源碼搜尋與讀取。
- **輸出**：
  - 因果鏈，每一環附事實的出處和源碼的「檔案:行」
  - 每個功能的行為是不是照設計
  - 根因，或者能確認到哪裡為止
  - 尚未確認的部分
- **什麼時候跑**：有源碼時自動接在數據分析後面。主對話先拿到事實報告，根因報告晚一點補上。
- **第一版不能自己要求再量數據**：缺的數據寫進尚未確認。
- **跟事實報告的接點**：
  - MCAP 裡每一則 Log 都帶 file、function、line，事實報告會列出來。
  - 對回源碼用 `SourceIndex.resolve`，參考 `JobSource.__init__` 裡建 `log_sites` 的那一段。

## 相關紀錄

- **設計紀錄**：`doc/設計筆記與已知限制.md` 的 §2.19～2.24，以及已知限制裡跟源碼、因果有關的條目（57～75 之間）。改文件時會搬到這個資料夾。
  - 第九輪原版可以直接看：`git show 62e0534:doc/設計筆記與已知限制.md`。
- **各輪的評分結果**：`evals/results/analysis_5090_*`。只在本機，不進 git。
