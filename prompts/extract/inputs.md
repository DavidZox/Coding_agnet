提煉（agent_core/extract.py）交給 worker 與整合的 user 訊息裡，程式組進去的標籤與說明：worker（放得進一段時讀全部；好幾份加起來放得進一段時
合成一段一起讀，worker_together）、整合、修一次。
worker 與整合的規則在 worker.md、merger.md；最前面的「使用者想知道什麼」在 tool_summary 組（prompts/harness/extract_anchor.md）。
{名稱} 是程式填的值。不在這裡的：交給主對話的提煉結果（回答、事實、未涵蓋的排版）——那是程式的輸出。

<!-- @note_unread -->
{source}原文第 {lines} 行這次沒有讀（共 {count} 段；段數超過 {max}，依問題挑了最相關的段落）

<!-- @note_failed -->
{source}原文第 {lines} 行提煉失敗，沒有讀到

<!-- @repair_answer_missing -->
answer 裡的「{tokens}」在原文找不到（數值、名稱要照抄原文；原文沒有的不要寫，或改寫成原文的寫法）。

<!-- @repair_answer_line -->
answer 寫的「{written}」是每一行最前面的存檔行號，不是檔案的行號：那一行在檔案裡是 {at}。寫檔案的位置要用檔案的行號。

<!-- @merge_source -->
{head}【這份輸出】{label}：原文共 {count} 行（{chars} 字），依結構切成 {chunks} 段，每段由一個 worker 讀

<!-- @merge_source_together -->
{head}【這份輸出】{label}：原文共 {count} 行（{chars} 字）；{n} 份加起來不長，由一個 worker 一起讀

<!-- @catalog -->
【過去的工具使用檢索清單（只用來填 related_records；不是這份原始輸出的內容，不可寫進 answer／facts）】
{catalog}

<!-- @worker_chunk -->
【這一段】{label}：原文共 {count} 行，依結構切成 {of} 段，你讀第 {k}/{of} 段（第 {start}～{end} 行）。

<!-- @worker_whole -->
【這份輸出】{label}：原文共 {count} 行，不長，你讀全部（第 1～{count} 行）。

<!-- @worker_together -->
【這幾份輸出】{count} 份存檔一起問、加起來不長，你一起讀全部。每一份前面有「===== 存檔 #編號 =====」，行號是那一份原文的行號。
每條事實與錯誤的 `record` 填它出自哪一份的編號；一條裡的名稱與數值只能出自那一份（程式照那一份核對）。問題要比較這幾份時，只列有差異的
（只在其中一份出現的名稱、幾份不一樣的數值），各自寫成那一份的事實（例如「<名稱> 只在 #<編號> 出現」）；幾份都有、都一樣的不用一條一條列。
比較的結論由整合寫。

<!-- @worker_together_item -->
===== 存檔 #{rid}（{label}；共 {count} 行）=====
{lines}

<!-- @worker_context -->
【前情（讀這一段要知道的幾行，不是這一段的內容）】
{lines}

<!-- @worker_body -->
【這一段的原文】
{lines}

<!-- @merge_source_head -->
===== 存檔 #{rid}（{label}）=====

<!-- @merge_background -->
；背景：{background}

<!-- @merge_opening -->
【原文的開頭】
{lines}

<!-- @merge_outline -->
【大綱（章節標題的行號）】
{lines}

<!-- @merge_outline_item -->
  行 {n}：{title}（{count} 行）

<!-- @merge_facts_header -->
【各段提煉的事實（程式核對過：名稱與數值都在引用的行裡；每條下面是那幾行的原文）】

<!-- @merge_chunk_title -->
第 {k} 段（行 {start}～{end}）

<!-- @merge_together_title -->
一個 worker 一起讀（{ranges}）

<!-- @merge_chunk_failed -->
{title}：提煉失敗，沒有讀到

<!-- @merge_chunk_empty -->
{title}：沒有跟問題有關的內容

<!-- @merge_chunk_empty_summary -->
（{summary}）

<!-- @merge_chunk_summary -->
{title}：{summary}

<!-- @merge_no_summary -->
（沒有寫總結）

<!-- @merge_fact -->
- {label}{text}（行 {lines}）

<!-- @merge_fact_record -->
- {label}{text}（#{rid} 行 {lines}）

<!-- @merge_error_label -->
錯誤／異常：

<!-- @merge_unknown_lines -->
？

<!-- @merge_notes -->
【程式的說明（寫進 not_covered）】
{notes}

<!-- @repair_user -->
{purpose}

【你剛才寫的結果】
{result}

【程式核對的問題】
{problems}

<!-- @repair_tail -->
只改有問題的地方：照原文改正，或拿掉找不到根據的內容；其他照原樣輸出。輸出同樣格式的 JSON。
