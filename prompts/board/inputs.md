方向的實驗：公佈欄的 worker（agent_core/board.py）的 user 訊息裡程式組的部分——公佈欄（原始問題、子目標、項目與狀態、前面的領域查到的、
這個問題的分工、上一次的經過、核對過的事實、試過的步驟、還能走幾步）、提煉的錨點（look_purpose）、回答時的事實清單、回答沒有通過核對的說明
（answers_fix、answers_problem、why_*）。{名稱} 是程式填的值。

<!-- @question -->
【使用者的原始問題】
{question}

<!-- @goal -->
【你的子目標】
{goal}

<!-- @items -->
【要回答的項目】
{items}

<!-- @item_row -->
{n}. {item}（{state}）

<!-- @item_state_none -->
還沒有事實

<!-- @item_state_some -->
{count} 則事實

<!-- @facts -->
【公佈欄：核對過的事實】（程式核對過名稱與數值在原文裡，附出處）
{facts}

<!-- @facts_none -->
【公佈欄：核對過的事實】
（還沒有）

<!-- @facts_more -->
（另外還有 {count} 則比較早的事實沒有列）

<!-- @fact_row -->
F{id}（{where}第 {step} 步）：{text}（出處：{refs}）

<!-- @fact_item -->
第 {n} 項，

<!-- @steps -->
【試過的步驟】
{steps}

<!-- @steps_none -->
【試過的步驟】
（還沒有）

<!-- @step_row -->
第 {n} 步（{where}找：{look_for}）：{tool} {args} → {result}

<!-- @step_facts -->
；新的事實 {ids}

<!-- @step_no_facts -->
；沒有新的事實

<!-- @step_unread -->
；輸出太長，提煉只讀了 {read}/{chunks} 段，沒有讀：{where}

<!-- @unread_file -->
{file} 第 {start}～{end} 行

<!-- @unread_output -->
輸出的第 {start}～{end} 行

<!-- @view_more -->
；還有第 {start}～{end} 行沒有看（view_file {file} --from {start}）

<!-- @search_clipped -->
；文字只列了前面幾筆（每個檔案最多 20 筆、總共 200 筆），其他的看不到：縮小範圍、指定檔案或換更精確的字再搜

<!-- @step_repeat -->
跟第 {k} 步一樣（同樣的工具與參數），沒有執行

<!-- @left -->
【還能走】{left} 步

<!-- @previous -->
【上一次的經過】這個問題之前交給這個領域 {count} 次，都沒有做完或這次的項目之前查過：
{attempts}

<!-- @previous_attempt -->
- 第 {n} 次（{skill}）：{status}{note}；找過的字：{searched}；那一次的項目：{items}

<!-- @look_purpose -->
【使用者的原始問題】
{question}

【要回答的項目】
{items}

【這一步特別要找的】（{where}；原文裡回答其他項目的事實也要摘）
{look_for}

【這份輸出】{command}

<!-- @look_where_item -->
為第 {n} 項

<!-- @look_where_all -->
為好幾項

<!-- @look_where_auto -->
程式接著看上一步沒看完的部分，

<!-- @refs_only -->
（只算{kinds}）

<!-- @answer_facts -->
【公佈欄上的事實】（F 編號；回答時 facts 寫這些編號）
{facts}

<!-- @answers_fix -->
【系統核對】answers 有幾項沒有通過核對，照下面改（每一項都再寫一次）：
{problems}

<!-- @answers_problem -->
- 第 {k} 項（{item}）：{why}

<!-- @why_missing -->
沒有回答（answers 少了這一項）

<!-- @why_no_facts -->
答到的要在 facts 寫根據的事實編號

<!-- @why_fact_unknown -->
F{ids} 不在公佈欄上

<!-- @why_tokens -->
「{tokens}」在根據的事實裡找不到

<!-- @why_near -->
（事實裡相近的寫法：{near}）

<!-- @why_no_reason -->
查不到、不屬於這個領域要寫原因
