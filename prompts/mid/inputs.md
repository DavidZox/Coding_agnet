新架構的中階（agent_core/mid.py）：交給模型的 user 訊息裡程式組的標籤（規則在 select.md、contract.md）。
{名稱} 是程式填的值：question＝使用者的問題；goal＝這一層的子目標；domain＝領域的名稱；intro＝領域的說明（SKILLS.md 的開頭）；
skills＝每個複合技能一則（skill_entry）；name＝技能或參數的名稱；description＝技能的說明；when＝技能的〈什麼時候用〉；
answers＝技能答得了問題要的哪幾種（位置、數量、內容）；
title＝技能的標題；params＝每個參數一則（param_*）；desc＝參數的說明；kind＝參數的種類（type_* 的一則）；default＝預設值；
rejected＝沒有通過核對的參數（reject_* 的幾則）；quote＝模型抄的原文；value＝模型寫的值；missing＝原文裡找不到的那幾段字。

<!-- @question -->
【使用者的問題】
{question}

<!-- @goal -->
【這一層的子目標】
{goal}

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

<!-- @reject_quote -->
- {name}：抄的原文「{quote}」不在問題或子目標裡（要一字不改地抄）

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
