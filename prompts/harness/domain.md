新架構的高階（agent_core/orchestrator.py）：主模型「分工」（交給領域）之後，程式交回給主模型的文字（每個領域的報告、子工作階段說別的領域
查得到的項目 routes、分工做完時依報告回答的說明 answer_hint、要問使用者、中階沒做完時接著一步一步做、不屬於這個領域、/clear 取消），
擋領域的工具與複合技能（tool_blocked、skill_blocked）、核對沒過的說明（[ERROR] 後面的部分），依報告回答時
answers 沒有通過核對的說明（answers_fix、why_*；why_* 也用在使用者看到的「沒有通過核對」與子工作階段收尾的核對）。開頭的 [PASS] 🗺️／[ERROR]
由程式加。交給下一層的文字（前面的領域查到的、這個問題的分工）在 harness/plan.md。{名稱} 是程式填的值。

<!-- @report -->
{domain} 的報告（{status}；做法 {skill}）。決策圖：{url}
{report}

<!-- @routes -->
子工作階段查不到、不屬於它、寫了哪個領域查得到的項目（系統從它們的回答取）：
{rows}
要再查就再分工一次：只帶這幾項，交給它寫的領域（系統會把這一次的經過一起交過去）。

<!-- @route -->
- {where}：{domain} 說要交給 {to} 查{state}

<!-- @route_where_n -->
第 {n} 項（{item}）

<!-- @route_where -->
「{item}」

<!-- @route_tried -->
（{to} 這一回合查過這一項：{status}）

<!-- @route_excluded -->
（{to} 這一回合說過不屬於它，不能再交給它）

<!-- @answer_hint -->
這一回合要回答的項目（answers 照這個編號）：
{items}
（依上面的報告回答使用者：回答時（action 是 null）answers 照上面的編號一項一筆——status 寫 answered（報告寫了）或 not_found（報告沒寫到）；
text 寫回答，not_found 寫原因（照報告寫的說明、沒有做完的節點、判斷的經過）；refs 寫報告裡的出處（檔案:行號，或 #編號；這一回合自己執行過的
工具結果也算）。系統會照項目排好給使用者，並附出處那一行的原文；reply 寫一句總結就好。不要自己補、也不要用常識猜；報告已經查過的不用再查一次。
報告沒答到、寫了還需要別的領域查的、或說不屬於那個領域的項目，可以再分工一次，只帶那幾項、交給查得到的領域（系統會把這一次的經過一起交過去）；
還要做別的動作（例如用 file_ops 把結果寫進檔案）時先做，answers 填 []。）

<!-- @ask_waiting -->
{domain} 停下來要問使用者：{question}{candidates}。決策圖：{url}
系統已經直接問使用者，使用者回答之後會接著做完（分工裡還沒做的也會接著做），再把報告一起交給你；這一輪不要做別的。

<!-- @ask_candidates -->
（候選：{candidates}）

<!-- @answered -->
使用者回答「{answer}」之後，{domain} 接著做完：

<!-- @cancelled -->
使用者取消了 {domain} 的問題，{domain} 沒有做完。決策圖：{url}
照實告訴使用者做到哪裡、還缺什麼資訊。

<!-- @out_of_domain -->
{domain} 說它的子目標不屬於它：{reason}。決策圖：{url}
這一回合不要再交給 {domain}：重新分工時交給別的領域，或用 Available Skills 裡的技能，或照實回答使用者。

<!-- @stepwise -->
{domain} 的中階沒有做完（{status}：{reason}；決策圖：{url}），系統接著在子工作階段裡用這個領域的工具一步一步做：

<!-- @retry -->
{domain} 的中階有報告、但沒有做完（{status}：{reason}；決策圖：{url}）。中階的報告照樣附上，可以照它回答：
{report}

系統接著帶著這份報告，在子工作階段裡換個做法再做一次：

<!-- @history_line -->
{n}. {domain}（做法 {skill}）：{status}，決策圖 {url}

<!-- @tool_blocked -->
{tool} 是 {domain} 領域的工具，不直接用。下一步：在 action 填「分工」{"domains": [{"domain": "{domain}", "goal": …, "items": […]}]}（要用的領域都列進去），
由 {domain} 照寫好的做法查；沒有寫好的做法時，系統會在子工作階段裡用這個領域的工具一步一步做，再把報告交給你。

<!-- @skill_blocked -->
{skill} 是 {domain} 領域寫好的做法（複合技能），由 {domain} 挑選、執行，不能直接用。下一步：在 action 填「分工」{"domains": [{"domain": "{domain}", "goal": …, "items": […]}]}（要用的領域都列進去），
由 {domain} 照寫好的做法查，再把報告交給你。

<!-- @err_plan_size -->
分工列了 {count} 個領域（要 1～{max} 個）。下一步：domains 列這個問題要用的領域，每個領域一項。

<!-- @err_plan_dup -->
分工裡 {domain} 出現了不只一次。下一步：同一個領域只列一項，它要做的寫在同一個子目標、要回答的都放進它的 items。

<!-- @err_plan_entry -->
分工的第 {k} 項（{domain}）：

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
