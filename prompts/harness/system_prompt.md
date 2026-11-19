主對話的 system prompt 裡程式組進去的部分（agent_core/prompt.py 的 get_system_prompt，依序：AGENT.md → 上下文模式的規則 → 長期記憶 →
滾動摘要 → 使用者說過的話 → 過去的對話片段 → 技能索引 → 工具使用檢索清單）：各節的標題、長期記憶開頭的說明、接回舊摘要時的提醒。
AGENT.md、context_modes/、Memory.md 本身各是一個檔案；清單在 tool_use_index.md。{名稱} 是程式填的值。

<!-- @memory_none -->
No long-term memory.

<!-- @memory_guide -->
（每條開頭的 [月-日 時:分] 是寫入時間。規則、偏好、做法一律遵守；描述某個時間點狀態或觀察的條目（例如「系統整體健康」「資源不足」）只代表當時：使用者問現在的狀態時，先執行會實際查詢系統的技能（例如 docker_containers、ROS2_topic_list、workpackage_status）再回答，不要當成現況。）

<!-- @summary_none -->
No history summary yet.

<!-- @user_words_header -->
## 使用者說過的話（已被壓縮的對話裡使用者的原話，程式逐字保留，舊→新）

<!-- @user_words_more -->
（更早還有 {count} 則沒有列出，原文在「過去的對話片段」的存檔裡）

<!-- @summary_carried -->
（這份摘要是之前的對話留下的（{source}），不是這次啟動後的對話：裡面的進度、狀態與未完成事項可能已經過時——技能以下面的 Available Skills 為準，系統狀態以重新查詢為準；使用者沒有提起就不要主動接續裡面的未完成事項。）

<!-- @memory_dropped -->
（另有 {count} 條較舊的記憶超過載入上限，沒有載入。）

<!-- @context_mode -->
## Context Mode：{mode}

<!-- @context_mode_rules -->
## Context Mode：{mode}
{rules}

<!-- @memory -->
## Long Term Memory
{memory}

<!-- @summary -->
## Recent Compressed History Summary
{summary}

<!-- @skills -->
## Available Skills (SKILLS.md)
{skills}

<!-- @domains -->
## Domains（領域：交給領域處理的問題）
下面的領域有寫好的做法（複合技能），由系統照做法執行、整理成報告交給你。問題屬於某個領域時，action 填「交給領域」：
`{"domain": "<領域名稱>", "goal": "<這一層的子目標>", "items": ["<要回答的項目>", …]}`
- goal：照使用者的原話寫要找什麼、在哪個範圍（對話裡提過的名稱、路徑、#編號可以帶進來）；不要寫成步驟，也不要寫工具的參數。
- items：把使用者的問題拆成一項一項要回答的（1～{max} 項，每項一句話，例如「定義在哪個檔案」「各被呼叫幾次」）。
- 領域的工具不在下面的 Available Skills：不要自己叫（系統會擋）；報告說沒有適合的做法時，系統才會放行並列出能用的工具。
- 打招呼、問你能做什麼、答案已經在對話裡的，直接回答，不用交給領域。

{domains}

<!-- @domain_entry -->
### {title}
{intro}
寫好的做法：
{skills}
