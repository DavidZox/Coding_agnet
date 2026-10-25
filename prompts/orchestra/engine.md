任務引擎給模型的字（agent_core/task_engine.py）：規劃與重排 session 的 user 訊息、程式檢查計畫發現的問題（交回規劃修）、worker 的 system 與
任務說明、worker 執行中的提醒、對照目標的兩個問題、事實核對交回改的說明、重試的原因。規劃與 worker 的通則在 planner.md、worker.md，
類型的知識在 profiles/<類型>.md；這裡是程式組進去的部分。{名稱} 是程式填的值，每一則上面的註記寫了是哪裡用的。
不在這裡的：task_run 回給主對話的報告與 [ERROR]、worker 的工具結果（[DENIED]／[ERROR]）、檢查的證據——那些是程式的輸出。

<!-- @issue_unknown_skills -->
第 {n} 步的技能 {skills} 不在技能清單裡（只能用清單裡的名稱）

<!-- @issue_no_workflow -->
第 {n} 步的工作流 {workflow} 不存在（只能用工作流清單裡的名稱，或改用技能）

<!-- @issue_workflow_confirm -->
第 {n} 步的工作流 {workflow} 有【確認】、會停下來等使用者，不能放進計畫：改用技能

<!-- @issue_workflow_args -->
第 {n} 步的工作流 {workflow}：{error}

<!-- @issue_workflow_in_goal -->
第 {n} 步的目標寫了工作流 {workflows}，但沒有填 workflow：要用工作流就填 workflow 與 workflow_args（skills 給空的），不用的話目標不要寫工作流的名稱

<!-- @issue_no_skills -->
第 {n} 步沒有列出要用的技能（或工作流）

<!-- @issue_write_needs_file_ops -->
第 {n} 步要寫進 {path}，skills 要列 file_ops（不然執行時不能寫）

<!-- @issue_unknown_check_skill -->
第 {n} 步的檢查技能「{skill}」不在技能清單裡

<!-- @issue_too_many_steps -->
步驟太多（{count} 步）：合併成最多 {max} 步

<!-- @issue_container_started_later -->
第 {n} 步要在 {container} 裡面做，但 {container} 現在沒有在跑（{status}），第 {later} 步才啟動它：把啟動排在前面

<!-- @issue_container_stopped -->
第 {n} 步要在 {container} 裡面做，但 {container} 現在沒有在跑（{status}）：容器停著時只能看狀態與 log（docker_ctl status／logs）；要進容器得先啟動（使用者要求才可以）

<!-- @issue_read_document_first -->
使用者提到「{doc}」：先排一步找到並讀那份文件（find_file／search_text／view_file），後面要改的步驟照文件寫的做（不要先假設文件的內容）

<!-- @issue_readonly_profile -->
第 {n} 步會改變狀態，但這一類任務（{title}）只查不改：拿掉這一步，或改成只查詢（要寫報告檔用 output，不用排一步）

<!-- @issue_expect_in_args -->
第 {n} 步的檢查要看到的「{expect}」就在檢查的參數（{args}）裡：輸出的開頭本來就會照列參數，一定找得到，看不出做完了沒。expect 改成做完之後輸出裡才會有的字（例如改好的值、寫進去的內容裡的關鍵字）

<!-- @issue_output_not_file -->
output 的 path「{path}」不是檔案的路徑：寫要建立或附加的檔案（相對於工作目錄，含副檔名，例如 notes/report.md）；不用寫檔就給空字串

<!-- @issue_output_exists -->
output 的 {path} 已經存在，mode 是 write 會整份換掉：使用者要加一筆（記一筆、附加）就用 append；確定要整份換掉才用 write

<!-- @issue_output_written_by_step -->
第 {n} 步要自己寫 {path}，但這個檔案已經寫在 output、系統最後會依核對過的事實寫：拿掉這一步（或改成只收集要寫進去的資料）；那一步是工作流、會自己寫這個檔的話，output 的 path 給空字串

<!-- @issue_output_dropped -->
第 {n} 步會自己寫 {path}：系統不另外寫報告（同一個檔不寫兩次）

<!-- @issue_output_needs_steps -->
要寫 {path}，但沒有收集資料的步驟：先排查詢的步驟，系統最後依查到的事實寫

<!-- @plan_user -->
【技能清單】
{skills}

【工作流清單】（整件事或其中一段正好是其中一個時，那一步寫 workflow）
{workflows}

【目前狀態】
{ENV}

【任務】
{task}

（計畫的每個欄位都用繁體中文寫）

<!-- @env_time -->
現在時間：{now}

<!-- @env_cwd -->
工作目錄：{cwd}（{count} 項：{entries}）

<!-- @env_target -->
目標容器：{target}

<!-- @env_target_none -->
（未設定）

<!-- @env_containers -->
容器（名稱：狀態）：{containers}

<!-- @env_containers_more -->
；…共 {count} 個

<!-- @env_containers_unknown -->
容器：查不到（{why}）

<!-- @plan_fix -->
{plan}

【上一版計畫】
{previous}

【程式檢查發現的問題：修正後輸出完整的計畫】
{issues}

<!-- @replan_user -->
【技能清單】
{skills}

【工作流清單】
{workflows}

【目前狀態】
{ENV}

【任務】
{task}

【已經做完的步驟與查到的事實】
{done}

【原本剩下的步驟】
{rest}

【為什麼重排】{why}

【報告檔】{output}

只排還沒做的部分（已經查到的不要再查一次）：照上面查到的事實決定要改什麼、怎麼改；不需要再改變任何狀態時，只排確認或整理的步驟，或 items 給空的。（計畫的每個欄位都用繁體中文寫）

<!-- @replan_output -->
{path}（{mode}；系統最後依核對過的事實寫，不用排寫檔的步驟；output 照原本的寫）

<!-- @replan_output_none -->
（沒有；使用者要寫成檔案時才填 output）

<!-- @replan_rest_item -->
- {title}：{goal}

<!-- @replan_rest_none -->
（沒有）

<!-- @facts_step -->
第 {n} 步「{title}」{status}：{summary}

<!-- @facts_item -->
  - {text}（#{ref}）

<!-- @facts_check -->
  - 檢查：{evidence}

<!-- @facts_none -->
（還沒有）

<!-- @wf_catalog_item -->
- {name}：{description}
  workflow_args：
{inputs}

<!-- @wf_catalog_input -->
    {name}=…{optional}：{description}

<!-- @wf_catalog_optional -->
（選填）

<!-- @wf_catalog_no_inputs -->
    （不用）

<!-- @wf_catalog_none -->
（沒有）

<!-- @check_error_ask -->
【使用者的任務】{task}
【這一步】第 {n} 步：{title}
目標：{goal}
【worker 的回報】{report}
【這一步實際執行的動作與結果（系統紀錄）】
{actions}
【做完之後系統的檢查】{skill} {args}（要看到「{expect}」）→ 出錯了：
{output}

檢查出錯，程式沒辦法用它確認。依實際執行的動作與檢查的輸出（不是 worker 說的）判斷這一步的目標做到了沒有：
- 沒做到：檢查的錯誤表示目標要的結果不存在、沒有改成（例如要寫的檔案找不到、要建立或送出的東西不在清單裡），或執行的動作裡沒有做到目標的那一個（例如只建了目錄、沒有寫檔；只查了、沒有改）。
- 做到了：執行的動作已經做到目標（成功的輸出看得到），檢查出錯是因為檢查本身寫錯（參數的順序、選項、名稱或編號不對）、環境裡沒有它要用的指令，或目標本來就會讓它查不到（例如刪除之後查不到）。
goal_met 填 true／false；summary 寫判斷的根據：哪一個動作的輸出、檢查的錯誤代表什麼。

<!-- @check_error_system -->
你核對任務裡的一步做到了沒有：只依系統記下的動作、輸出與檢查判斷，照實回答。

<!-- @check_error_action -->
- {skill} {args} → {head}

<!-- @check_error_no_actions -->
（沒有執行任何技能）

<!-- @retry_check_error -->
你回報完成了，但做完之後的檢查：{evidence}。先查清楚現在的狀態：沒做好就修正；確定已經完成、是檢查的條件不適用，就照實回報並說明。

<!-- @retry_check_miss -->
你回報完成了，但做完之後的檢查沒有通過：{evidence}。先查清楚現在的狀態：沒做好就修正；確定已經完成、是檢查的條件不適用，就照實回報並說明。

<!-- @replan_why_surveyed -->
查詢的步驟做完了

<!-- @replan_why_finding -->
第 {n} 步「{title}」做完了，查到的狀況：{summary}

<!-- @replan_why_failed -->
第 {n} 步「{title}」沒有完成：{summary}

<!-- @continue_plan_thought -->
使用者在 Plan 模式核准了計畫，交給任務引擎照計畫做

<!-- @continue_plan_reply -->
照核准的計畫執行。

<!-- @continue_survey_thought -->
任務引擎查完、重排了要改的步驟，等使用者確認

<!-- @continue_survey_reply -->
查完了，接下來要改變狀態的步驟請你確認。

<!-- @worker_truncated -->
[系統] 你的回覆太長被截斷，不是完整的 JSON，這一輪沒有執行。請縮短：thought 一兩句、reply 寫重點，一次只做一個動作。

<!-- @worker_no_tool_yet -->
[系統] 你還沒有用任何技能。這一步的目標要實際查詢或操作才知道結果：action 填技能的腳本路徑去做，做完再回報。

<!-- @worker_still_working -->
[系統] 你寫「{said}」，但這一輪沒有動作（action 是 null），系統會當成這一步做完了。還要查就把 action 填上去做；這一步的目標已經做完，就回報結果（reply 寫查到的、facts 列出關鍵事實），不要寫還要做什麼。

<!-- @worker_wrapup -->
[系統] 已經用完 {max_steps} 輪，不能再用技能了。依上面的執行結果判斷：這一步的目標做完了沒有？done 填 true／false；summary 寫做了什麼、看到的關鍵事實；facts 列出關鍵事實（路徑、名稱、數值、修改前→後），ref 填出處的工具結果編號。

<!-- @goal_check_ask -->
[系統] 你回報這一步沒有完成。對照這一步的目標判斷做到了沒有：
目標：{goal}
- 做到了：目標要查的查到了、要確認的確認清楚了（結果是有問題——卡住、被拒、離線、沒成功、設定不對——也是做到了；問題還在、修不了，不算沒做到：修好問題不在這一步的目標裡，除非目標寫了要修好）；要改的改好了。
- 沒做到：要查的查不到（找不到對象、技能一直錯誤）、要改的沒改成（技能被擋、檢查不過）、目標要等的結果沒有發生（例如要等它跑完，它卻卡住了）。
goal_met 填 true／false；summary 照實寫這一步最後的結果：做了什麼、現在是什麼狀態（問題還在就寫問題是什麼，不要寫「沒有完成」）。

<!-- @facts_bad_ref -->
出處 #{ref} 不是這個任務執行過的工具結果（這一步的是 {mine}；前面各步的是 {before}）

<!-- @facts_not_found -->
「{tokens}」在 #{ref} 的輸出裡找不到

<!-- @facts_fix_head -->
[系統] 你列的事實有幾條在引用的工具輸出裡找不到（系統核對名稱與數值）：

<!-- @facts_fix_item -->
- 「{text}」（#{ref}）：{problem}

<!-- @facts_fix_tail -->
照輸出的原文改正（或換成正確的出處），找不到根據的就拿掉；facts 輸出完整的清單，summary 照改正後的寫。

<!-- @worker_profile_header -->
## 這一類任務（{title}）

<!-- @knowledge_header -->
## 領域知識（取自「{title}」類型：在哪裡找、用哪個技能查；這一類任務只照其中查詢的做法，不做會改變狀態的事）

<!-- @worker_specs_header -->
## 這一步的技能規格

<!-- @worker_others_header -->
## 其他可以用的技能（查詢用；action.command 填技能名稱會拿到規格）

<!-- @brief_mine -->
　← 你負責這一步

<!-- @brief_later -->
（之後別人負責，不要做）

<!-- @brief_status -->
（{status}）

<!-- @brief_perm_write -->
這一步可以改變狀態（使用者已經核准），可以用來改變狀態的技能：{skills}

<!-- @brief_perm_read -->
這一步只查詢，不能改變任何狀態

<!-- @brief_task -->
【使用者的任務】{task}

<!-- @brief_plan -->
【整份計畫】
{overview}

<!-- @brief_step -->
【你負責的這一步】第 {n} 步：{title}
目標：{goal}
{permission}

<!-- @brief_check -->
【做完之後系統會檢查】{skill} {args}，輸出要有「{expect}」

<!-- @brief_before -->
【前面各步的結果與事實】（#編號是那一次工具輸出的存檔）
{facts}

<!-- @brief_retry -->
【上一次做這一步沒有成功】{failure}
先查清楚現在的狀態再做，不要重複同樣的做法。

<!-- @brief_env -->
【目前狀態】
{env}

<!-- @profile_pick_system -->
你替任務選一個類型：只看使用者的任務要做什麼，從清單裡選最符合的一個，照實回答。

<!-- @profile_pick_user -->
【任務的類型】
{profiles}

【任務】
{task}

profile 填一個類型的名稱；reason 一句話寫為什麼（使用者要改變狀態、只要查原因、還是要整理成一份報告）。

<!-- @profile_pick_item -->
- {name}（{title}）：{description}

<!-- @synth_user -->
【使用者的任務】{task}

【要整理成】{goal}

【規劃時說要回報的重點】{focus}

【現在時間】{now}

【各步驟做了什麼、查到的】（#編號是那一次工具輸出的存檔；你寫的每一則都要附它根據的 #編號）
{steps}

<!-- @synth_goal_findings -->
回答使用者的問題：結論、根據、還不確定的（不會寫進檔案，交給主對話回答使用者）

<!-- @synth_goal_report -->
一份報告，內容照使用者要的（不寫進檔案，交給主對話給使用者）

<!-- @synth_goal_file -->
一份報告，系統會{mode} {path}：內容照使用者要的

<!-- @synth_mode_write -->
寫成

<!-- @synth_mode_append -->
附加到（檔案原本的內容保留，這一段接在最後）

<!-- @synth_focus_none -->
（沒有寫）

<!-- @synth_step -->
第 {n} 步「{title}」{status}：{summary}

<!-- @synth_action -->
  - 執行：{skill} {args} → {head}（#{rid}）

<!-- @synth_no_ref -->
沒有附出處（refs 要填它根據的工具輸出 #編號）

<!-- @synth_bad_ref -->
出處 {refs} 不是這個任務的工具輸出（這個任務的是 {rids}）

<!-- @synth_unreadable -->
出處 {refs} 的輸出讀不到（存檔不在了）：換一個出處

<!-- @synth_not_found -->
「{tokens}」在 {refs} 的輸出裡找不到

<!-- @synth_fix -->
[系統] 你寫的有幾則核對不過（系統核對每一則的出處，與名稱、數值在引用的輸出裡找得到）：
{items}

照引用的輸出原文改正那幾則（或換成正確的出處；一則寫了好幾份輸出的內容就把出處都附上），找不到根據的 text 給空字串（拿掉）。fixes 只列上面這幾則，n 照上面的編號。

<!-- @synth_fix_item -->
- 第 {n} 則「{text}」（{refs}）：{problem}

<!-- @synth_fix_line -->
    引用的輸出裡相關的一行：{line}
