主 session 這一側的交辦（agent_core/orchestrator.py）：主模型「交辦」之後，程式交回主模型的文字（交辦的報告 report、停在確認關卡 ask_waiting、
使用者回答之後接著做完 answered、取消 cancelled、依報告回答的說明 answer_hint），擋領域的工具與有骨架的技能（tool_blocked、skill_blocked）、
交辦沒過核對的說明（err_*，原話不在使用者說過的話裡 err_quote，有一段沒放進任何一欄 err_cover、問句只放進背景或限制 err_cover_asked；[ERROR] 後面的部分；背景與限制不是原話的由程式拿掉、不交回）、
依報告回答時 answers 沒有通過核對的說明（answers_fix、answers_problem、answers_lead、why_*，漏了報告的編號與數字 why_dropped，
回答的文字寫了存檔的 #編號 why_archive_id；
why_* 也用在使用者看到的「沒有通過核對」與領域 session 回報的核對，agent_core/answers.py）。開頭的 [PASS] 🗺️／[ERROR] 由程式加。{名稱} 是程式填的值。

<!-- @report -->
交辦的報告（{status}）：
{report}

<!-- @answer_hint -->
這一回合要回答的項目（answers 照這個編號）：
{items}
（依上面的報告回答使用者：回答時（action 是 null）answers 照上面的編號一項一筆——status 寫 answered（報告寫了）或 not_found（報告沒寫到）；
text 寫回答，not_found 寫原因（照報告寫的說明）；refs 寫報告裡的出處（檔案:行號，或 #編號；這一回合自己執行過的工具結果也算）。
系統會照項目排好給使用者，並附出處那一行的原文；reply 寫一句總結就好。不要自己補、也不要用常識猜；報告已經查過的不用再查一次。
報告沒答到的項目，可以再交辦一次，只帶那幾項（系統會把這一次的經過一起交過去）；
還要做別的動作（例如用 file_ops 把結果寫進檔案）時先做，answers 填 []。）

<!-- @ask_waiting -->
領域 session 停在確認關卡：{question}
系統已經直接問使用者，使用者回答之後會接著做完，再把報告交給你；這一輪不要做別的。

<!-- @answered -->
使用者回答「{answer}」之後，領域 session 接著做完：

<!-- @cancelled -->
使用者取消了確認，領域 session 照做到的收尾。照實告訴使用者做到哪裡、還缺什麼。

<!-- @history_line -->
{n}. {goal}：{status}

<!-- @tool_blocked -->
{tool} 是「{domain}」領域的工具，不直接用。下一步：在 action 填「交辦」{"task": {"goal": …, "items": […]}}，由領域 session 選領域與技能做完，再把報告交給你。

<!-- @skill_blocked -->
{skill} 是「{domain}」領域有骨架的技能，由領域 session 選用，不能直接用。下一步：在 action 填「交辦」{"task": {"goal": …, "items": […]}}，再把報告交給你。

<!-- @domain_named -->
{name} 是領域的名稱，不是技能，不能直接用：你不用指定領域，交辦之後由領域 session 選領域與技能。下一步：在 action 填「交辦」{"task": {"goal": …, "items": [{"quote": …}]}}（goal 照使用者的原話寫要找什麼、做什麼；每一項一字不改地抄使用者的原話），領域 session 做完會把報告交給你。

<!-- @err_no_domain -->
沒有可以交辦的領域（DOMAIN.md 沒有列，或領域的規格有問題）。下一步：用 Available Skills 裡的技能，或照實回答使用者。

<!-- @err_goal -->
交辦的 goal 是空的。下一步：goal 照使用者的原話寫這一件事要找什麼、要做什麼。

<!-- @err_items -->
交辦的 items 有 {count} 項（要 1～{max} 項）。下一步：每一項寫 quote：一字不改地抄使用者的原話裡、這一項在問的那一段。

<!-- @err_cover -->
使用者最新這一則的{questions}沒有放進交辦的任何一欄（每一句都要有歸屬，一句裡用「、」接的每一段都要抄到）。下一步：問的、要你做的抄進 items；使用者說明的現況、前提抄進 background；使用者要求的做法、不能做的事抄進 constraints——quote 都一字不改地抄那一句（用「、」接的幾段抄在同一筆就好；接著前面問的、有「它」的也照抄，領域 session 會照前後文讀）。

<!-- @err_cover_asked -->
{questions}是問句，只放進了 background 或 constraints：問的要回答，抄進 items（同一句也可以留在 background 或 constraints）。

<!-- @err_quote -->
交辦的第 {k} 項「{quote}」不在使用者說過的話裡。下一步：quote 一字不改地抄使用者的原話裡、這一項在問的那一段（之前幾則訊息裡的也可以），不要改寫、不要補字。

<!-- @err_same -->
這一回合第 {n} 次交辦的子目標與項目跟這次一模一樣（那一次：{status}），再交一次結果也一樣。下一步：照報告回答；還要查的話，只帶報告沒答到的項目、子目標寫清楚還缺什麼。

<!-- @err_item_tries -->
「{item}」這一回合已經交辦 {n} 次（最多 {max} 次）：
{history}
下一步：照報告回答（查不到的寫原因），不要再交辦這一項。

<!-- @err_lost -->
找不到等使用者回答的那個領域 session（紀錄不見了）。下一步：照實告訴使用者，需要的話重新交辦。

<!-- @answers_fix -->
【系統核對】answers 有幾項沒有通過核對：
{problems}
請重寫 answers（每一項都要有一筆；只有上面這幾項要改）：答到的 refs 只寫報告或這一回合自己執行過的工具結果裡有的出處（檔案:行號，或 #編號），
text 裡的數字與名稱要是出處那幾行裡的，報告這一項寫的編號與數字照寫；報告沒寫到的 status 寫 not_found，text 寫原因。

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

<!-- @why_archive_id -->
text 寫了存檔的編號「{ids}」：#編號是系統的存檔編號，只寫在 refs；text 寫內容（要引用規格書、文件的編號就照原文寫那個編號）

<!-- @why_dropped -->
報告裡這一項寫了「{tokens}」，回答裡沒有（照報告寫上）
