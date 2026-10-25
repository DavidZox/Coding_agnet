交給提煉（agent_core/extract.py）的「使用者想知道什麼」——放在 worker 與整合的 user 訊息最前面（agent_core/tool_summary.py）：
工具回傳的提煉＝使用者的目標＋這一步的目的（summary_purpose）；result_recall＝使用者現在的問題、決策 AI 要聚焦的點、每一份存檔的背景
（對話片段、附圖分析、工具輸出各有說明怎麼讀）。使用者的目標本身在 prompt.py 組（prompts/harness/anchor.md）。{名稱} 是程式填的值。

<!-- @step_tool -->
執行的工具：{action}

<!-- @step_thought -->
決策 AI 執行前的想法：{thought}

<!-- @step_reply -->
決策 AI 對使用者的說明：{reply}

<!-- @step_none -->
（沒有取得這一步的說明，請以使用者的目標為依據）

<!-- @summary_purpose -->
【使用者的目標】
{anchor}

【這一步的目的（決策 AI 為什麼執行這個工具）】
{step}

<!-- @recall_conversation_background -->
這份是過去被壓縮的對話原文（{command}），不是工具輸出——[user] 是使用者當時說的話、[assistant] 是 AI 當時的想法與回覆、[harness …] 是當時的工具回傳；回答時說明當時談了什麼、查到什麼、決定了什麼，使用者的原話與名稱、數值照抄

<!-- @recall_vision_background -->
這份是過去使用者附圖時系統的影像分析結果（{command}），不是工具輸出；原圖沒有保存，只能根據這份文字回答，文字裡沒有的寫進 not_covered（例如「當時的影像分析沒有提到…，需要的話請使用者重新附圖」），不要推測影像內容；當時使用者的說明：{task}

<!-- @recall_tool_background -->
當時的任務：{task}；執行的指令：{command}

<!-- @recall_kind_conversation -->
過去的對話片段

<!-- @recall_kind_vision -->
附圖分析

<!-- @recall_no_task -->
(沒有)

<!-- @recall_unknown_task -->
(未知)

<!-- @recall_label -->
{kind}（#{rid}，{ts}）

<!-- @recall_hint -->
；檢索清單對它的描述：{hint}

<!-- @recall_question -->
【使用者現在的問題】
{anchor}

<!-- @recall_focus -->
【決策 AI 要聚焦的點】
{focus}

<!-- @recall_background_one -->
【這份存檔的背景（不是現在要回答的問題）】

<!-- @recall_background_many -->
【這幾份存檔的背景（不是現在要回答的問題）】
