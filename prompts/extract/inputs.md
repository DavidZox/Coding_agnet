提煉（agent_core/extract.py）交給 worker 與整合的 user 訊息裡，程式組進去的標籤與說明：一次讀完、分段 worker、整合、修一次。
worker 與整合的規則在 worker.md、synthesizer.md；最前面的「使用者想知道什麼」在 tool_summary 組（prompts/harness/extract_anchor.md）。
{名稱} 是程式填的值。不在這裡的：交給主對話的提煉結果（回答、事實、未涵蓋的排版）——那是程式的輸出。

<!-- @direct_single -->
【工具的完整原始輸出（共 {count} 行；每一行前面是原文的行號）】
{body}

<!-- @direct_multi_item -->
===== 存檔 #{rid}（{label}；共 {count} 行）=====
{body}

<!-- @note_unread -->
{source}原文第 {lines} 行這次沒有讀（共 {count} 段；段數超過 {max}，依問題挑了最相關的段落）

<!-- @note_failed -->
原文第 {lines} 行提煉失敗，沒有讀到

<!-- @repair_answer_missing -->
answer 裡的「{tokens}」在原文找不到（數值、名稱要照抄原文；原文沒有的不要寫，或改寫成原文的寫法）。

<!-- @repair_fact_missing -->
事實「{text}」（行 {lines}）的「{missing}」不在引用的那幾行。

<!-- @merge_source -->
{head}【這份輸出】{label}：原文共 {count} 行（{chars} 字），依結構切成 {chunks} 段，由 worker 各讀一段

<!-- @catalog -->
【過去的工具使用檢索清單（只用來填 related_records；不是這份原始輸出的內容，不可寫進 answer／facts）】
{catalog}

<!-- @direct_background -->
【存檔的背景（不是現在要回答的問題）】
{background}

<!-- @direct_multi_header -->
【這幾份存檔的完整原文（facts 的 record 填存檔編號）】

<!-- @worker_chunk -->
【這一段】{label}：原文共 {count} 行，依結構切成 {of} 段，你讀第 {k}/{of} 段（第 {start}～{end} 行）。

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

<!-- @repair_evidence -->
【那幾條事實引用的原文】
{lines}

<!-- @repair_tail -->
只改有問題的地方：照原文改正，或拿掉找不到根據的內容；其他照原樣輸出。輸出同樣格式的 JSON。

<!-- @repair_missing_default -->
內容
