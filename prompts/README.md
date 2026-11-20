# prompts/：給模型的文字

harness 送給模型的字都在這裡：改字不用改程式，存檔之後下一次呼叫就生效（看修改時間重讀，不用重新啟動）。讀法在
`agent_core/prompt_files.py`；每個檔案給哪一種 session、誰組進 prompt，見〈[prompts 與流程的對應](../doc/images/prompts與流程的對應.png)〉圖
與〈[架構說明](../doc/架構說明.md)〉第 7 節。

## 每個檔案給誰

| 檔案 | 給誰 | 程式 |
|---|---|---|
| `AGENT.md` | 主對話的 system prompt（角色、跨領域的做法、執行協議、記憶協議、溝通風格；只屬於一個領域的做法在那個領域 `SKILLS.md` 的〈做法〉，只給它的子工作階段看，第 5 步 5-2） | `prompt.get_system_prompt` |
| `context_modes/harness.md`、`claude_code.md` | 主對話：目前上下文模式的規則（接在 AGENT.md 後面） | `context_mode.context_mode_rules` |
| `Memory.md` | 主對話：長期記憶——**資料，不是規則**：使用者要求時 `modify_memory` 寫入 | `prompt.load_long_term_memory` |
| `harness/system_prompt.md` | 主對話 system prompt 裡程式組的部分：各節的標題、長期記憶開頭的說明、接回舊摘要時的提醒、「領域」一節（分工的寫法：要用的領域一次列出、每個領域的子目標與要回報的項目、照順序做；依報告回答的 answers、再分工與次數的上限、Available Skills 列的你自己直接用、每個領域的說明） | `prompt.py`、`orchestrator.py` |
| `harness/domain.md` | 新架構的高階：分工（交給領域）之後程式交回主模型的文字（每個領域的報告、分工做完時這一回合要回答的項目與 answers 的寫法 `answer_hint`、要問使用者、中階沒做完時接著一步一步做 `stepwise`、不屬於這個領域、/clear 取消），核對沒過的說明（分工的領域數、同一個領域兩次、第幾項沒過、沒有的領域、排除過的、項目數、一樣的再交、同一個項目交太多次、直接叫領域的工具），answers 沒有通過核對的說明（`answers_fix`、`why_*`；`why_*` 也用在使用者看到的「沒有通過核對」與子工作階段收尾的核對） | `orchestrator.py`、`answers.py`、`sub.py` |
| `harness/plan.md` | 新架構的高階分工交給下一層的文字（第 5 步 5-3）：前面的領域查到的（子工作階段的第一則訊息裡一段、中階收到的問題後面接一段；子工作階段一項一項的回答、中階報告的前面）、這個問題的分工（每個領域的子目標、哪一項是它、做完了沒；主對話這一回合已經做過的） | `orchestrator.py` |
| `harness/tool_use_index.md` | system prompt 尾端的工具使用檢索清單（兩種模式各一則）、過去的對話片段、動態區的最新一筆 | `tool_use_index.py` |
| `harness/state_tail.md` | 動態區：目前狀態（工作目錄、容器、Workspace、目前的數據）、Objective | `prompt.build_state_tail`、`analysis_job.analysis_state_line` |
| `harness/tool_results.md` | 每一則工具結果的框架句、使用者捨棄結果的通知、沒有提煉時只給成功／失敗的那一則 | `protocol.tool_result_message`、`turn.py` |
| `harness/raw_results.md` | claude_code 模式：原文太長時中間省略的說明、清除舊回傳的佔位 | `context_mode.py` |
| `harness/skill_docs.md` | 用技能名稱當 action 時，規格前面那句「這一輪只是載入規格、下一輪要做什麼」 | `dispatch.py` |
| `harness/reminders.md` | 程式核對後的提醒：同樣的動作一直失敗、沒動作卻說做了或說要做、依數據報告回答時寫成因果或寫錯事實、空白回覆、寫到長度上限被截斷（`reply_cut`）；截斷的欄位後面接的說明（`cut_mark`） | `turn_guard.py`、`conversation.ask_ai`、`protocol.drop_cut` |
| `harness/followup.md` | 提煉結果最後的下一步建議（還要哪幾份存檔、沒讀到的段落、缺口、已經回答） | `tool_summary._followup_guidance` |
| `harness/extract_anchor.md` | 交給提煉的「使用者想知道什麼」：這一步的目的、recall 的問題與每份存檔的背景 | `tool_summary.py` |
| `harness/anchor.md` | 交給獨立 session 的「使用者的目標」（Objective、最新一句、任務線） | `prompt._build_task_anchor_text` |
| `harness/direct_commands.md` | `/analyze` 替使用者與 AI 放進主對話的訊息；數據分析報告最後的回答規則 | `cli.py`、`web_app/` |
| `harness/attachments.md` | Web：只附圖或只載入技能沒打字時的訊息、影像分析接在訊息後面的說明 | `web_app/flows.py`、`state.py` |
| `summary/rolling.md` | 滾動摘要 session | `compression._summary_prompts` |
| `extract/worker.md`、`synthesizer.md` | 工具回傳的提煉：分段的 worker、整合（規則） | `extract.py` |
| `extract/inputs.md` | 提煉的 user 訊息裡程式組的標籤、程式的說明、修一次的說明 | `extract.py` |
| `edg/fix.md` | 新架構的低階執行器：第 1 級修正（一個工具節點參數錯或逾時，只改字面參數；修不好就說修不好）的規則 | `edg.ModelFixer` |
| `edg/inputs.md` | 第 1 級修正的 user 訊息裡程式組的標籤（子目標、規格、參數、錯誤、逾時的縮小方式） | `edg.fix_message` |
| `mid/select.md` | 新架構的中階：挑複合技能（先寫理解、問題要的是位置／數量／內容，再選一個或說 none、out_of_domain）的規則 | `mid.Worker._select` |
| `mid/contract.md` | 中階的合約：照技能的參數從問題抽值，每個附一字不改的原文（程式核對）的規則 | `mid.Worker._contract_call` |
| `mid/judge.md` | 中階的判斷節點：看原文挑出回答問題的行（來源、檔案、行號、一字不改的片段、標籤），從技能列的路選一條、填那條路的值（程式核對）的規則 | `mid.Worker._judge` |
| `mid/inputs.md` | 中階的 user 訊息裡程式組的標籤（問題、挑技能時當背景的原始問題 `select_question`、領域、複合技能、參數與種類、沒過核對的參數；判斷的原文、之前挑出的行、找過的字、路與要填的值、沒過核對的片段；4-2：上一次的經過 `previous*`、參數跟之前一樣時重寫合約的原因 `reject_same`、判斷看的之前找過的字 `judge_searched_before`；第 5 步：再交時參數只從子目標抄 `redispatch_goal`、`redispatch_question`、`reject_quote_goal`） | `mid.py`、`judge.py` |
| `sub/session.md` | 新架構的子工作階段（第 5 步）：沒有複合技能的領域、或中階沒有做完也沒有報告時，用領域的工具一步一步做的模型看到的字——system prompt（領域的說明、〈做法〉、能用的工具、只做自己的子目標與「不屬於這個領域」、怎麼回覆與收尾——兩階段協議那幾行照抄 AGENT.md、長期記憶）、第一則訊息（子目標、要回答的項目、前面的領域查到的、這個問題的分工、原始問題（只用來對照名稱）、上一次的經過）、每份工具結果前面的 #編號、收尾的核對沒過時交回修（`answers_fix`、`why_ref_unknown`）、不是這個領域的工具、回覆不是 JSON、沒有動作也沒有回答（`empty_turn`）、寫到長度上限被截斷（`cut`）、對話太長時清掉的舊結果、提煉的錨點 | `sub.py`、`orchestrator.domain_gate` |
| `vision/extraction.md` | Web 附圖的影像提取（視覺模型的 system、純文字的退路、user 訊息） | `vision/extraction.py` |

## 範本的寫法

- **一個檔案好幾則**：每一則用一行 `<!-- @名稱 -->` 開頭，到下一個 `<!-- @… -->` 或檔尾為止；那一則最後的換行不算（每則之間空幾行都一樣），
  開頭要空一行就在標記下面空一行。第一個標記之前的文字是給人看的說明，不會送給模型。整個檔案就是一則的（AGENT.md、worker.md…）照原樣讀。
- **`{名稱}`** 是程式填的值，每個檔案開頭的說明寫了各是什麼。只換程式給的名稱，其他大括號（JSON 的例子、給模型看的 `{名稱}` 寫法）照原樣。
  改字時不要改 `{名稱}`，也不要拿掉一則：`evals/integrity/selftest.py` 會檢查程式用到的每一則都在、程式填的名稱範本裡都有、沒有沒人用的一則。
- 有的開頭有空白（`harness/tool_use_index.md` 的兩則清單每行前面 12 個空白）：那是原本寫在程式碼裡時的縮排，模型收到的就是這樣，照留。

## 不在這裡的（留在程式裡）

- **程式的輸出**：工具與技能的結果（`[PASS]`／`[ERROR]`／`[DENIED]` 與下一步，照〈技能撰寫規範〉）、數據分析的報告、
  提煉結果的排版、檢查的證據——這些是程式算出來的結果，不是給模型的指示。
- **程式認的標記**：`[tool result]`、`【系統回傳】`、`[vision result]`、`[skill loaded]`、`📘 已載入技能`、`（完整原文存檔 #N，…）`、
  `（依這份報告回答使用者`——程式靠它們辨認訊息（壓縮、清除、核對），範本裡用 `{prefix}`、`{marker}` 這種名稱由程式填。
- 給使用者看的字（畫面上的提示、確認關卡的說明）、比對用的詞表（正規表示式）。

## 改了之後

改到這裡的字＝改到模型會讀的文字：跑對應的真模型評測跟基準比（`CLAUDE.md`〈每一次修改的測試〉第 3 條；主對話 `evals/chat/run.py`、
維運 `evals/ops/run.py`、提煉 `evals/extract/run.py`、低階執行器的修正 `evals/edg/run.py`、中階 `evals/mid/run.py`、交給領域與子工作階段 `evals/repo/run.py`）；範例不要用評測世界的名稱（`evals/integrity/selftest.py` 會擋）。
