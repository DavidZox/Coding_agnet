# prompts/：給模型的文字

harness 送給模型的字都在這裡：改字不用改程式，存檔之後下一次呼叫就生效（看修改時間重讀，不用重新啟動）。讀法在
`agent_core/prompt_files.py`；每個檔案給哪一種 session、誰組進 prompt，見〈[prompts 與流程的對應](../doc/images/prompts與流程的對應.png)〉圖
與〈[架構說明](../doc/架構說明.md)〉第 7 節。

## 每個檔案給誰

| 檔案 | 給誰 | 程式 |
|---|---|---|
| `AGENT.md` | 主對話的 system prompt（角色、做法、執行協議、記憶協議、溝通風格） | `prompt.get_system_prompt` |
| `context_modes/harness.md`、`claude_code.md` | 主對話：目前上下文模式的規則（接在 AGENT.md 後面） | `context_mode.context_mode_rules` |
| `Memory.md` | 主對話：長期記憶——**資料，不是規則**：使用者要求時 `modify_memory` 寫入 | `prompt.load_long_term_memory` |
| `harness/system_prompt.md` | 主對話 system prompt 裡程式組的部分：各節的標題、長期記憶開頭的說明、接回舊摘要時的提醒 | `prompt.py` |
| `harness/tool_use_index.md` | system prompt 尾端的工具使用檢索清單（兩種模式各一則）、過去的對話片段、動態區的最新一筆 | `tool_use_index.py` |
| `harness/state_tail.md` | 動態區：目前狀態（工作目錄、容器、Workspace、目前的數據）、Objective | `prompt.build_state_tail`、`analysis_job.analysis_state_line` |
| `harness/tool_results.md` | 每一則工具結果的框架句、使用者捨棄結果的通知、沒有提煉時只給成功／失敗的那一則 | `protocol.tool_result_message`、`turn.py` |
| `harness/raw_results.md` | claude_code 模式：原文太長時中間省略的說明、清除舊回傳的佔位 | `context_mode.py` |
| `harness/skill_docs.md` | 用技能（或工作流）名稱當 action 時，規格前面那句「這一輪只是載入規格、下一輪要做什麼」 | `dispatch.py` |
| `harness/reminders.md` | 程式核對後的提醒：同樣的動作一直失敗、沒動作卻說做了或說要做、依數據報告回答時寫成因果或寫錯事實、空白回覆 | `turn_guard.py`、`conversation.ask_ai` |
| `harness/followup.md` | 提煉結果最後的下一步建議（還要哪幾份存檔、沒讀到的段落、缺口、已經回答） | `tool_summary._followup_guidance` |
| `harness/extract_anchor.md` | 交給提煉的「使用者想知道什麼」：這一步的目的、recall 的問題與每份存檔的背景 | `tool_summary.py` |
| `harness/anchor.md` | 交給獨立 session 的「使用者的目標」（Objective、最新一句、任務線） | `prompt._build_task_anchor_text` |
| `harness/direct_commands.md` | `/analyze`、`/workflow` 替使用者與 AI 放進主對話的訊息；數據分析報告最後的回答規則 | `workflow_cmd.py`、`cli.py`、`web_app/` |
| `harness/attachments.md` | Web：只附圖或只載入技能沒打字時的訊息、影像分析接在訊息後面的說明 | `web_app/flows.py`、`state.py` |
| `summary/rolling.md` | 滾動摘要 session | `compression._summary_prompts` |
| `extract/worker.md`、`synthesizer.md` | 工具回傳的提煉：分段的 worker、整合（規則） | `extract.py` |
| `extract/inputs.md` | 提煉的 user 訊息裡程式組的標籤、程式的說明、修一次的說明 | `extract.py` |
| `orchestra/planner.md`、`worker.md` | 任務引擎：規劃、每一步的 worker（通則） | `task_engine.py` |
| `orchestra/profiles/<類型>.md` | 任務的類型（第一個是 ops 維運）：「# 規劃」給規劃、「# 執行」給 worker | `task_engine.parse_profile` |
| `orchestra/engine.md` | 任務引擎組進去的部分：規劃與重排的 user 訊息、程式檢查計畫的問題、worker 的說明與提醒、對照目標的兩個問題、事實核對交回改、重試的原因 | `task_engine.py` |
| `orchestra/plan_edit.md` | Plan 模式用說的改草稿（只輸出要套用的操作） | `plan._plan_revise` |
| `workflow/fill.md`、`check.md`、`inputs.md` | 工作流的判斷點：填值、選分支（規則）；user 訊息的標籤與選項 | `workflow.py` |
| `make_skill/draft.md` | `/make_skill` 草擬工作流 | `make_skill._make_skill_prompts` |
| `vision/extraction.md` | Web 附圖的影像提取（視覺模型的 system、純文字的退路、user 訊息） | `vision/extraction.py` |

## 範本的寫法

- **一個檔案好幾則**：每一則用一行 `<!-- @名稱 -->` 開頭，到下一個 `<!-- @… -->` 或檔尾為止；那一則最後的換行不算（每則之間空幾行都一樣），
  開頭要空一行就在標記下面空一行。第一個標記之前的文字是給人看的說明，不會送給模型。整個檔案就是一則的（AGENT.md、worker.md…）照原樣讀。
- **`{名稱}`** 是程式填的值，每個檔案開頭的說明寫了各是什麼。只換程式給的名稱，其他大括號（JSON 的例子、給模型看的 `{名稱}` 寫法）照原樣。
  改字時不要改 `{名稱}`，也不要拿掉一則：`evals/integrity/selftest.py` 會檢查程式用到的每一則都在、程式填的名稱範本裡都有、沒有沒人用的一則。
- 有的開頭有空白（`harness/tool_use_index.md` 的兩則清單每行前面 12 個空白）：那是原本寫在程式碼裡時的縮排，模型收到的就是這樣，照留。

## 不在這裡的（留在程式裡）

- **程式的輸出**：工具與技能的結果（`[PASS]`／`[ERROR]`／`[DENIED]` 與下一步，照〈技能撰寫規範〉）、任務引擎與工作流與數據分析的報告、
  提煉結果的排版、檢查的證據——這些是程式算出來的結果，不是給模型的指示。
- **程式認的標記**：`[tool result]`、`【系統回傳】`、`[vision result]`、`[skill loaded]`、`📘 已載入技能`、`（完整原文存檔 #N，…）`、
  `（依這份報告回答使用者`——程式靠它們辨認訊息（壓縮、清除、核對），範本裡用 `{prefix}`、`{marker}` 這種名稱由程式填。
- 給使用者看的字（畫面上的提示、確認關卡的說明）、比對用的詞表（正規表示式）。

## 改了之後

改到這裡的字＝改到模型會讀的文字：跑對應的真模型評測跟基準比（`CLAUDE.md`〈每一次修改的測試〉第 3 條；主對話 `evals/chat/run.py`、
任務引擎與維運 `evals/ops/run.py`、工作流 `evals/workflow/sandbox.py`）；範例不要用評測世界的名稱（`evals/integrity/selftest.py` 會擋）。
