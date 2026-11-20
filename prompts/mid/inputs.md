新架構的中階（agent_core/mid.py）：交給模型的 user 訊息裡程式組的標籤（規則在 select.md、contract.md、judge.md）。
{名稱} 是程式填的值：question＝使用者的問題；goal＝這一層的子目標；domain＝領域的名稱；intro＝領域的說明（SKILLS.md 的開頭）；
skills＝每個複合技能一則（skill_entry）；name＝技能或參數的名稱；description＝技能的說明；when＝技能的〈什麼時候用〉；
answers＝技能答得了問題要的哪幾種（位置、數量、內容）；
title＝技能的標題；params＝每個參數一則（param_*）；desc＝參數的說明；kind＝參數的種類（type_* 的一則）；default＝預設值；
rejected＝沒有通過核對的參數（reject_* 的幾則）；quote＝模型抄的原文；value＝模型寫的值；missing＝原文裡找不到的那幾段字。
判斷節點（judge_*，agent_core/judge.py）：sources＝整理好的原文；source＝原文的編號（#數字）；what＝那份原文是什麼（judge_what_*）；
pattern＝搜尋的字；scope＝搜尋的範圍；hits＝命中幾筆；file＝檔案；start、end＝看的那一段；omitted＝省略了哪些行；picked＝之前挑出的行；
labels＝可以標的種類；branches＝每條路一則（judge_branch*）；id、say＝路的名稱與說明；params＝那條路要填的（judge_param_* 的幾則）；
where＝片段對到的那幾行；line＝行號；label＝挑的時候標的種類；text＝那一行的內容（程式從原文取）；words＝這個工作找過的字；branch＝選的路。
上一次的經過（previous*，4-2：同一個問題再交給這個領域時，程式從之前幾次的紀錄取）：count＝之前交了幾次；attempts＝每一次一則；n＝第幾次；
skill＝那一次的複合技能；params＝那一次的參數；status＝結果；note＝停下來的原因；searched＝那一次找過的字；items＝那一次要回答的項目。

<!-- @question -->
【使用者的問題】
{question}

<!-- @goal -->
【這一層的子目標】
{goal}

<!-- @select_question -->
【使用者的原始問題】（背景：裡面其他的事分給了別的領域或主對話；挑技能、判斷屬不屬於這個領域都只看上面的子目標）
{question}

<!-- @redispatch_goal -->
【這一層的子目標】（這是第 {n} 次交給這個領域：這次的參數只從這一段抄，quote 也只能是這一段裡的字；這一段沒提到的參數，quote 與 value 都留空，程式會沿用上一次的值）
{goal}

<!-- @redispatch_question -->
【使用者的原始問題】（背景，讓你知道整件事要做什麼；這次的參數不從這裡抄）
{question}

<!-- @domain -->
【領域】{domain}
{intro}

<!-- @skills -->
【複合技能】
{skills}

<!-- @skill_entry -->
- {name}：{description}
  答得了：{answers}
  什麼時候用：{when}

<!-- @skill -->
【選好的複合技能】{name}（{title}）：{description}

<!-- @params -->
【參數】
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

<!-- @rejected -->
【上一次沒有通過核對的參數：只重寫這幾個】
{rejected}

<!-- @previous -->
【上一次的經過】同一個問題之前交給這個領域 {count} 次，下面是每一次做了什麼、停在哪裡（程式從紀錄取）。照一樣的複合技能與參數再做一次，結果也會一樣：這次要從停下來的原因修正——換一個做得到的複合技能，或照原因改參數（例如範圍找不到就照原文重寫路徑、連在一起的幾個名稱分開寫、換成檔案裡會照樣出現的寫法）。
{attempts}

<!-- @previous_attempt -->
- 第 {n} 次：做法 {skill}；參數 {params}；結果：{status}{note}；找過的字：{searched}；那一次的項目：{items}

<!-- @reject_same -->
這次的參數跟第 {n} 次一模一樣（做法 {skill}；{params}），那一次的結果是「{status}」：照一樣的參數再跑一次結果也一樣。請照那一次停下來的原因改參數（每個參數重寫）；問題裡真的沒有別的寫法，就照原樣寫。

<!-- @reject_quote -->
- {name}：抄的原文「{quote}」不在問題或子目標裡（要一字不改地抄）

<!-- @reject_quote_goal -->
- {name}：抄的原文「{quote}」在原始問題裡、不在這一次的子目標裡（這次再交，參數只從子目標抄；子目標沒提到就留空，程式會沿用上一次的值）

<!-- @reject_name -->
- {name}：「{value}」要是一個名稱（英文字母或底線開頭，只有英數字與底線），而且要出現在抄的原文「{quote}」裡

<!-- @reject_fragments -->
- {name}：值「{value}」裡的「{missing}」不在抄的原文「{quote}」裡（值要照原文寫，不要加原文沒有的字）

<!-- @reject_path -->
- {name}：路徑「{value}」裡的「{missing}」不是抄的原文「{quote}」裡的目錄或檔案名稱（每一段照原文的名稱寫、用 / 接起來，不含空白；原文沒有的目錄不要補）

<!-- @reject_missing -->
- {name}：必填，但沒有寫（問題或子目標裡有就一字不改地抄出原文再寫值；真的沒有才留空）

<!-- @reject_names -->
- {name}：「{missing}」不在抄的原文「{quote}」裡，或不是一個目錄的名稱（每個名稱要照原文寫，用「、」分開）

<!-- @type_words -->
搜尋的字（一個或幾個，用「、」分開）

<!-- @reject_words -->
- {name}：「{missing}」不在抄的原文「{quote}」裡，或不是一個名稱或短詞（每一個照原文一字不改地寫，空白也照原文；不要有括號；好幾個用「、」分開）

<!-- @judge_goal -->
【這個判斷要做的】
{goal}

<!-- @judge_sources -->
【原文】（程式照工具的收據從檔案讀的。每份開頭是原文的編號（#數字），## 後面是檔案，每行開頭是行號與 →，> 標的是搜尋命中的行（看某一行前後時是那一行））
{sources}

<!-- @judge_source -->
{source}（{what}）

<!-- @judge_what_search -->
搜「{pattern}」，範圍 {scope}，共 {hits} 筆

<!-- @judge_what_view -->
看 {file} 的第 {start}-{end} 行

<!-- @judge_omitted -->
（放不下、沒有列的行：{omitted}）

<!-- @judge_picked -->
【之前的判斷挑出的行】
{picked}

<!-- @judge_picked_line -->
- {file}:{line}（{label}）：{text}

<!-- @judge_searched -->
【已經找過的字】{words}

<!-- @judge_searched_before -->
【之前幾次交給這個領域時找過的字】{words}（那幾次沒有答到問題：要接著找的話，換別的字或別的範圍）

<!-- @judge_labels -->
【挑出的行可以標的種類】{labels}

<!-- @judge_branches -->
【看完之後選一條路】
{branches}

<!-- @judge_branch -->
- {id}：{say}

<!-- @judge_branch_params -->
- {id}：{say}（要填：{params}）

<!-- @judge_param_words -->
{name}＝搜尋的字（原文裡的名稱，可以好幾個）

<!-- @judge_param_path -->
{name}＝原文裡的一個檔案

<!-- @judge_param_line -->
{name}＝那個檔案在原文裡列出的一個行號

<!-- @judge_rejected -->
【上一次沒有通過核對的：只重寫這些】
{rejected}

<!-- @reject_source -->
- 來源 {source} 不是這次的原文（原文的編號有：{sources}）

<!-- @reject_empty_quote -->
- {source} 的 {file}：沒有抄片段（從那一行一字不改地複製一段）

<!-- @reject_line -->
- 片段「{quote}」不在 {source} 的 {file} 裡（要從那一行一字不改地複製，不要改寫或合併好幾行）

<!-- @reject_ambiguous -->
- 片段「{quote}」對到好幾行（{where}）：抄長一點，只對得到你要的那一行

<!-- @reject_param_empty -->
- {name}：選的路要填這個，但沒有填

<!-- @reject_param_words -->
- {name}：「{missing}」不在原文裡（搜尋的字要照原文一字不改地寫、原樣出現，不要有括號）；原文沒有要接著找的名稱就選別條路

<!-- @reject_param_searched -->
- 「{words}」都找過了（再找一次結果一樣）：選別條路——要看某一行前後就選看前後的那條，原文已經回答就選結束的那條，原文沒有寫就選沒有寫的那條

<!-- @reject_branch_ran -->
- {branch} 要加的節點都跑過了（結果一樣）：選別條路，或換一個檔案、行號

<!-- @reject_param_path -->
- {name}：「{value}」不是原文裡的檔案

<!-- @reject_param_line -->
- {name}：{file} 在原文裡沒有列第 {value} 行

