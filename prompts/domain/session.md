領域 session（agent_core/domain_session.py，docs/框架討論紀錄.md）看到的字：system prompt（system 與領域清單的一行 domain_entry）、
第一則訊息（first；每一項是使用者的原話；這一則之前的對話 context、context_archived、context_turn；上一次的經過 previous）、選了領域之後的技能清單（skills 與它的各段：skills_domain、skills_practice、skills_composites、
composite_entry、param_*、type_*、skills_tools、skills_shared、tool_entry）、選了技能之後的參數表單（form_composite、form_tool；沒過的交回重填
form_fix、工具的 args 寫法不對 form_fix_tool 與 reject_args_*、重填還是沒過 form_failed）、每一步的結果（step_head、composite_*（程式算的彙整
composite_totals）、output_head、result_id）、程式擋下的說明（err_*、not_my_tool）、
回報的核對沒過（answers_fix、why_ref_unknown；其他原因用 harness/domain.md 的 why_*）、回覆不是 JSON（retry、表單的 retry_form）、
寫到長度上限被截斷（cut）、對話太長時清掉的舊結果（cleared）、提煉時的「想知道什麼」（anchor；使用者前面的話 anchor_earlier）。
agent_core/composite.py 也用這份：合約沒過的說明（reject_*）、要領域 session 決定的事（need_*）、骨架裡有要確認的動作（guard_in_skill）。
{名稱} 是程式填的值。

<!-- @system -->
你是領域 session：主 session 把使用者的一件事交給你（【子目標】與【要回答的項目】，每一項是使用者的原話），你選領域、一次用一個技能查（或照使用者的要求做），看了結果再決定下一步，最後一項一項回報。你的對話只在這裡；做完由系統把你的回報與每一步整理成報告交回主 session。

## 每一輪只回一個 JSON：thought、state、domains、skill、answers、reply（state 是下面三種之一）
1. **domains（選領域）**：domains 從下面〈領域〉選要用的（可以好幾個）。系統把這些領域的技能清單交給你。第一輪一定是這個；清單裡沒有做得到的技能時可以再選（最多再選 {reselect} 次）。
2. **skill（用一個技能）**：skill 只寫技能清單裡的一個名稱。系統接著給你那個技能的參數表單，下一輪只填那張表單（有骨架的技能每個參數寫 quote 與 value；工具只寫 args）；系統核對、執行完把結果交給你（太長的結果會先整理成跟子目標有關的重點，每條附出處）。
   - 一次只用一個技能。同一個技能、同樣的參數不要再用（結果一樣）。收到 [ERROR] 或系統交回的說明，照它寫的改。
   - 最多用 {steps} 個技能。
3. **report（回報）**：answers 照【要回答的項目】的編號一項一筆——status 寫 answered（查到了）或 not_found（查不到）；text 寫回答，查不到寫原因（查了什麼、為什麼沒有）；refs 寫出處：結果開頭標的 #編號，或結果裡列的 檔案:行號。回答裡的數字、名稱照結果寫，不要自己估、不要用常識補。
- 用不到的欄位寫空的：domains、answers 寫 []，skill 寫 ""。
- thought 寫這一步為什麼這樣選（一到兩句）；reply 寫一句這一步在做什麼，回報時寫一句總結。thought 與 reply 裡不要用英文雙引號，引用名稱用「」。

## 怎麼做（極其重要）
1. 只做【子目標】、回答【要回答的項目】。每一項是使用者的原話，從【使用者的原始問題】切出來的：照它問的回答，一句話問了好幾件事就每一件都回答。項目的意思照原始問題的前後文與【前文】讀——「它」「這個」這種指代、沒寫主詞的追問，指的是前面說過的那個；【前文】只用來看指的是什麼，答案要用這次查到的結果。子目標與原始問題也用來對照名稱、路徑、數值。
2. 先用最能直接回答的技能；結果還不夠，就照結果裡的名稱、檔案、行號換一個技能或參數接著查（例如看某一行前後、接著找結果提到的名稱）。換一條路比同一條路再走一次有用。
3. 結果是 0 筆或不是要的：想想是範圍、字還是技能不對（例如名稱在別種檔案裡），換掉不對的那一個。
4. 查到能回答每一項就回報，不要多做沒被要求的事；試過幾條路還是查不到，就回報查不到的原因。
5. 問的是現在的狀態（還在不在跑、現在在哪、現在的值）：用技能重新查。存檔、記憶、對話裡的舊結果只是參考。
6. 使用者說「先不要改」「只要查」：只用查詢的技能。會改狀態的動作，系統會先問使用者。

## 領域
{domains}

## 長期記憶（使用者要記住的事）
{memory}

<!-- @domain_entry -->
- {name}（{title}）：{intro}

<!-- @first -->
【子目標】
{goal}

【要回答的項目】（使用者的原話；回報時 answers 照這個編號）
{items}

【使用者的原始問題】（要回答的項目是從這一則切出來的：項目的意思照這一則的前後文讀；也用來對照子目標裡的名稱、路徑、數值）
{question}
{context}{previous}
先選領域（state 寫 domains）。

<!-- @context -->

【前文】這一則之前的對話（系統照原文附上：使用者的話與當時的回覆）。只用來看項目裡的指代、沒寫的主詞指的是什麼；當時的回覆不一定是現在的狀態，答案要用這次查到的結果。
{turns}

<!-- @context_archived -->

【前文】這一則之前的對話（系統存成 #{rid}，太長的照子目標與項目整理過、每條附出處；原文用 result_view 看）。只用來看項目裡的指代、沒寫的主詞指的是什麼；當時的回覆不一定是現在的狀態，答案要用這次查到的結果。
{shown}

<!-- @context_turn -->
- 使用者：{user}
  當時的回覆：{reply}

<!-- @previous -->

【上一次的經過】同一個問題之前交辦過 {count} 次，下面是每一次用了哪些技能、結果如何（系統從紀錄取）。已經查過的不用再查；同樣的技能與參數不會有新的結果。
{attempts}

<!-- @previous_attempt -->
- 第 {n} 次：{steps}；結果：{status}{note}

<!-- @skills -->
【技能清單】你選的領域：{names}。下一輪 state 寫 skill，從下面選一個技能（只寫名稱；參數在再下一輪的表單填）。

{blocks}

<!-- @skills_domain -->
### {title}（{name}）
{practice}{composites}{tools}

<!-- @skills_practice -->
做法：
{practice}

<!-- @skills_composites -->
有骨架的技能（系統照寫好的步驟執行；選了之後在表單裡填下面的參數，每個附抄的原文）：
{entries}

<!-- @composite_entry -->
- {name}：{description}
  什麼時候用：{when}
  參數：
{params}

<!-- @param_required -->
  - {name}（{kind}，必填）：{desc}

<!-- @param_default -->
  - {name}（{kind}，沒有提到就用 {default}）：{desc}

<!-- @param_optional -->
  - {name}（{kind}，沒有提到就不用）：{desc}

<!-- @type_name -->
名稱

<!-- @type_text -->
文字

<!-- @type_path -->
路徑

<!-- @type_glob -->
檔案名稱的寫法

<!-- @type_names -->
名稱清單

<!-- @type_words -->
搜尋的字（一個或幾個，用「、」分開）

<!-- @skills_tools -->
工具（選了之後在表單裡照「args 的寫法」寫參數）：
{entries}

<!-- @skills_shared -->
### 共用的工具（每個領域都能用）
{entries}

<!-- @tool_entry -->
{line}
  args 的寫法：{syntax}

<!-- @syntax_none -->
（不用參數）

<!-- @form_composite -->
【參數表單】{skill}（有骨架的技能）：這一輪只填這張表單——params 裡每個參數一欄，先寫 quote 再寫 value。
- quote：value 是從哪一段原文來的，一字不改地抄那一段（短短一段、要包含值）。原文可以是子目標、要回答的項目、使用者的原始問題，或前面結果裡寫的（例如結果列的路徑、名稱）；只抄內容，不要抄【】的標題。
- value：照參數的種類寫——名稱只寫名稱本身；路徑用原文裡的目錄或檔案名稱，一段一段用 / 接起來（原文沒有的上層目錄不要補）；檔案名稱的寫法用萬用字元寫（例如 *.<副檔名>，quote 抄原文裡說是哪種檔案的那幾個字）；名稱清單與搜尋的字照原文寫，好幾個用「、」分開。
- 沒提到的參數 quote 與 value 都寫 ""（系統用預設值，不用自己寫）。
參數：
{params}

<!-- @form_tool -->
【參數表單】{skill}（工具）：這一輪只填 args——一行參數，跟在指令列上打的一樣（不是 JSON）：照下面的寫法把 <…> 換成要的值，[…] 是可以不寫的部分（要用就只寫括號裡的字）；不含工具名稱與腳本路徑（含空白的參數用雙引號；不用參數就寫 ""）。
args 的寫法：{syntax}

<!-- @form_fix_tool -->
【系統】{skill} 的 args 沒有通過核對，沒有執行：{problem}。
這一輪只重填 args：一行參數，跟在指令列上打的一樣（不是 JSON）；<…> 換成要的值，[…] 是可以不寫的部分（要用就只寫括號裡的字，不寫括號）。
args 的寫法：{syntax}

<!-- @reject_args_json -->
args 寫成了 JSON

<!-- @reject_args_placeholder -->
args 照抄了寫法裡的 {marks}（沒有換成值）

<!-- @form_fix -->
【系統】{skill} 的參數沒有通過核對，沒有執行：
{problems}
這一輪只重填這幾個參數（quote 一字不改地從原文抄內容、不要抄【】的標題；value 照種類寫）：
{params}

<!-- @form_failed -->
【系統】{skill} 的參數重填之後還是沒有通過核對，沒有執行：
{problems}
換一個技能、從結果裡找到要的原文再選一次這個技能，或回報。

<!-- @step_head -->
【第 {n} 步的結果】{skill}（{how}）

<!-- @composite_status -->
技能的狀態：{status}{note}

<!-- @composite_switched -->
回退 {fallback}：{frm} 換成 {to}（照收據，程式換的）

<!-- @composite_fallback -->
回退：{say}

<!-- @composite_kept -->
系統只留原文裡的名稱：{name}「{given}」→ {value}（路徑的每一段是一個目錄或檔案的名稱，說明的字與萬用字元不寫進去）

<!-- @composite_of -->
系統照原文的「{of}」找到要讀的那一份：{name}「{given}」→ {value}（原文寫「<上層> 的 <名稱>」的，是上層底下檔名叫 <名稱> 的那一份）

<!-- @composite_filled -->
系統補的參數：{name}「{given}」→ {value}

<!-- @composite_need -->
要你決定：{question}{candidates}
（改了參數再用一次、換一個技能，或回報）

<!-- @composite_candidates -->
（候選：{candidates}）

<!-- @composite_totals -->
【程式照收據算的彙整】（存檔 #{rid}：回報時 refs 可以寫 #{rid}；數量照這裡寫，不要自己加）
{text}

<!-- @output_head -->
— {title}：{tool} {args} → {state}{rid}

<!-- @result_id -->
（存檔 #{rid}：回報時 refs 可以寫 #{rid}）

<!-- @err_first_domains -->
【系統】還沒選領域：這一輪 state 寫 domains，從〈領域〉選要用的。

<!-- @err_domains -->
【系統】domains 要從〈領域〉的名稱選：{names}。

<!-- @err_reselect -->
【系統】已經選過 {count} 次領域：從現在的技能清單選一個技能，或回報。

<!-- @err_skill -->
【系統】技能清單裡沒有「{skill}」，沒有執行。現在能用的：{names}。

<!-- @err_same -->
【系統】這跟第 {n} 步一模一樣（{skill}：{how}），結果也會一樣，沒有執行。那一步的結果：{head}。換一個技能或參數，或回報。

<!-- @err_empty_report -->
【系統】state 是 report，但 answers 是空的：照【要回答的項目】一項一筆寫（查不到的 status 寫 not_found、text 寫原因）。

<!-- @reject_no_quote -->
- {name}：值「{value}」沒有抄原文：quote 寫提到它的那一段原文（一字不改）；原文沒提到這個參數就 quote 與 value 都寫 ""

<!-- @reject_quote -->
- {name}：抄的原文「{quote}」不在子目標、要回答的項目、使用者的原始問題或前面的結果裡（要一字不改地抄內容，不含【】的標題）

<!-- @reject_name -->
- {name}：「{value}」要是一個名稱（英文字母或底線開頭，只有英數字與底線），而且要出現在抄的原文「{quote}」裡

<!-- @reject_fragments -->
- {name}：值「{value}」裡的「{missing}」不在抄的原文「{quote}」裡（值要照原文寫，不要加原文沒有的字）

<!-- @reject_path -->
- {name}：路徑「{value}」裡的「{missing}」不是抄的原文「{quote}」裡的目錄或檔案名稱（每一段照原文的名稱寫、用 / 接起來，不含空白；原文沒有的目錄不要補）

<!-- @reject_names -->
- {name}：「{missing}」不在抄的原文「{quote}」裡，或不是一個目錄的名稱（每個名稱要照原文寫，用「、」分開）

<!-- @reject_words -->
- {name}：「{missing}」不在抄的原文「{quote}」裡，或不是一個名稱或短詞（每一個照原文一字不改地寫，空白也照原文；不要有括號；好幾個用「、」分開）

<!-- @need_missing -->
參數 {name}（{desc}）是必填，還沒有寫：從原文找到它再用一次。

<!-- @need_none -->
工作目錄底下找不到「{value}」（參數 {name}）：先用找檔案的工具找到完整的路徑，或換一個範圍。

<!-- @need_many -->
「{value}」（參數 {name}）有好幾個：照候選寫完整的路徑再用一次。

<!-- @need_any -->
參數 {names} 至少要寫一個。

<!-- @guard_in_skill -->
技能裡有要使用者確認的動作，沒有執行（{text}）

<!-- @not_my_tool -->
{tool} 不在你選的領域的技能清單裡，這裡不能用。可以用的：{tools}。

<!-- @answers_fix -->
【系統核對】answers 有幾項沒有通過核對：
{problems}
請重寫 answers（每一項都要有一筆；只有上面這幾項要改）：答到的 refs 只寫這個 session 的結果裡有的出處（#編號，或結果列出的 檔案:行號），text 裡的數字與名稱要是出處裡的；查不到的 status 寫 not_found，text 寫原因。還要查的話可以先用技能（state 寫 skill），最後再回報。

<!-- @why_ref_unknown -->
出處 {ref} 不在這個 session 的結果裡

<!-- @retry -->
【系統提醒】上一次的回覆不是規定的 JSON（或是空的、state 不是 domains／skill／report）。請只回一個 JSON：thought、state、domains、skill、answers、reply。

<!-- @retry_form -->
【系統提醒】上一次的回覆不是表單的 JSON（或是空的）。請只回一個 JSON：thought 與表單的欄位。

<!-- @cut -->
【系統提醒】上一次的回覆裡 {fields} 寫到長度上限被截斷了（多半是同一段字一直重複），沒有執行。請重新回覆：thought 一到兩句；args 只寫這一步需要的參數。

<!-- @cleared -->
（第 {n} 步的結果已經從這裡清掉（對話太長）；原文在存檔 #{rid}，要再看用 result_view 或 result_grep。第一行：{head}）

<!-- @anchor -->
這一件事的子目標：{goal}
要回答的項目：{items}

<!-- @anchor_earlier -->

使用者前面說的（項目裡的指代照這幾句）：{words}
