新架構的高階（agent_core/orchestrator.py）：主模型「交給領域」之後，程式交回給主模型的文字（中階的報告、要問使用者、沒有適合的做法、
不屬於這個領域、取消），核對沒過的說明（[ERROR] 後面的部分），依報告回答時 answers 沒有通過核對的說明（answers_fix、why_*；
why_* 也用在使用者看到的「沒有通過核對」）。開頭的 [PASS] 🗺️／[ERROR] 由程式加。{名稱} 是程式填的值。

<!-- @report -->
{domain} 的報告（{status}；做法 {skill}）。決策圖：{url}
{report}

{items}
（依這份報告回答使用者：回答時（action 是 null）answers 照上面的編號一項一筆——status 寫 answered（報告寫了）或 not_found（報告沒寫到）；
text 寫回答，not_found 寫原因（照報告寫的說明、沒有做完的節點、判斷的經過）；refs 寫報告裡的出處（檔案:行號，或 #編號；這一回合自己執行過的
工具結果也算）。系統會照項目排好
給使用者，並附出處那一行的原文；reply 寫一句總結就好。不要自己補、也不要用常識猜；報告已經查過的不用再查一次。報告沒答到、又有別的範圍
或寫法可以找的，可以再交給領域一次，只帶沒答到的項目（系統會把這一次的經過一起交過去）；還要做別的動作時 answers 填 []。）

<!-- @items -->
這一回合要回答的項目（answers 照這個編號）：
{items}

<!-- @ask_waiting -->
{domain} 停下來要問使用者：{question}{candidates}。決策圖：{url}
系統已經直接問使用者，使用者回答之後會接著做完再交給你；這一輪不要做別的。

<!-- @ask_candidates -->
（候選：{candidates}）

<!-- @answered -->
使用者回答「{answer}」之後，{domain} 接著做完：

<!-- @cancelled -->
使用者沒有回答 {domain} 的問題（取消了），{domain} 沒有做完。決策圖：{url}
可以照實告訴使用者做到哪裡、還缺什麼資訊；要自己接著找，這一題可以照一般的方式，一步一步用這個領域的工具（先用技能名稱載入規格，再照規格執行）：
{tools}

<!-- @out_of_domain -->
{domain} 說這個問題不屬於它：{reason}。決策圖：{url}
這個問題不要再交給 {domain}：照一般的方式做——用其他技能，或一步一步用下面這些工具（先用技能名稱載入規格，再照規格執行），或照實回答使用者：
{tools}

<!-- @no_skill -->
{domain} 沒有適合的寫好的做法：{reason}。決策圖：{url}
這一題可以照一般的方式，一步一步用這個領域的工具（先用技能名稱載入規格，再照規格執行）：
{tools}

<!-- @failed -->
{domain} 沒有做完：{reason}。決策圖：{url}
這一題可以照一般的方式，一步一步用這個領域的工具（先用技能名稱載入規格，再照規格執行）：
{tools}

<!-- @history_line -->
{n}. {domain}（做法 {skill}）：{status}，決策圖 {url}

<!-- @tool_blocked -->
{tool} 是 {domain} 領域的工具，不直接用。下一步：在 action 填「交給領域」{"domain": "{domain}", "goal": …, "items": […]}，由 {domain} 照寫好的做法查；
報告說沒有適合的做法時，系統才會放行這個工具。

<!-- @err_unknown -->
沒有「{domain}」這個領域（有的領域：{names}）。下一步：交給列出的領域，或用 Available Skills 裡的技能。

<!-- @err_excluded -->
這個問題已經交給過 {domain}，它說不屬於它：{reason}。不要再交給 {domain}。這個問題交過的領域：
{history}
下一步：用 Available Skills 裡的其他技能做，或照實告訴使用者做了什麼、哪裡停下來（附上面的決策圖）。

<!-- @err_goal -->
交給 {domain} 時 goal 是空的。下一步：goal 寫這一層要找什麼、在哪個範圍（照使用者的原話）。

<!-- @err_items -->
要回答的項目有 {count} 項（要 1～{max} 項）。下一步：items 把使用者的問題拆成一項一項要回答的，每項一句話。

<!-- @err_same -->
這個問題已經用一樣的子目標與項目交給過 {domain}（結果：{status}），再交一次結果也一樣。下一步：照那一次的報告回答使用者；
報告沒答到的照實說沒找到與原因。

<!-- @err_item_tries -->
「{item}」這個問題已經交給 {domain} {n} 次（同一個項目最多 {max} 次）：
{history}
下一步：照這幾次的報告回答；報告沒答到的 status 寫 not_found，text 寫原因。

<!-- @err_lost -->
找不到 {domain} 那一次的工作紀錄，沒有辦法接著做。下一步：照實告訴使用者，請使用者再問一次。

<!-- @answers_fix -->
【系統核對】answers 有幾項沒有通過核對：
{problems}
請重寫 answers（每一項都要有一筆；只有上面這幾項要改）：答到的 refs 只寫報告或這一回合自己執行過的工具結果裡有的出處（檔案:行號，或 #編號），
text 裡的數字與名稱要是出處那幾行裡的；報告沒寫到的 status 寫 not_found，text 寫原因。

<!-- @answers_problem -->
- 第 {k} 項（{item}）：{why}

<!-- @answers_lead -->
- reply：{why}

<!-- @why_missing -->
沒有回答（answers 少了這一項）

<!-- @why_no_refs -->
答到的要附出處（refs）

<!-- @why_ref_unknown -->
出處 {ref} 不在這一回合的報告與工具結果裡

<!-- @why_ref_form -->
出處 {ref} 的寫法看不懂（寫成 檔案:行號，或 #編號）

<!-- @why_tokens -->
「{tokens}」在出處的那幾段裡找不到

<!-- @why_near -->
（那幾段裡相近的寫法：{near}）

<!-- @why_no_reason -->
查不到（not_found）要寫原因

<!-- @why_lead_refs -->
寫了報告裡沒有的出處 {refs}
