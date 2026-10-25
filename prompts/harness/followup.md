提煉結果（summarize_tool_result、result_recall）最後給主對話的下一步建議（agent_core/tool_summary.py 的 _followup_guidance）：
獨立 session 看過完整原文與檢索清單之後的判斷，依序挑一則接在「完整原始輸出已存成…」（base）或「不要再對…重複」（recalled_base）後面。
claude_code 模式（cc_*）只陳述原文在哪、哪裡沒涵蓋，下一步由模型自己決定。{名稱} 是程式填的值。

<!-- @no_ids -->
你看不到原始輸出：需要其他資訊時，換更精確的參數重新執行工具，不要憑空補上。

<!-- @view -->
要看某一條事實的原文：result_view {id} --from <行號> --lines 30。

<!-- @failed -->
提煉沒有成功（獨立 session 的回覆不是預期的格式），上面是它的原文，可能不完整：需要細節時用 result_recall {id} "<使用者的問題>" 再提煉一次，或用 result_view／result_grep 自己看存檔 {label} 的原文；不要憑空補上。

<!-- @cc_where -->
原文在存檔 {label}。

<!-- @cc_related -->
獨立 session 認為這個問題可能還需要之前的存檔（{reasons}）。

<!-- @cc_gap -->
「未涵蓋」的部分原文裡沒有，或這次沒讀到。

<!-- @cc_next -->
接下來怎麼做由你決定：看某一段用 result_view、找某個字串用 result_grep、換個問題再 result_recall，或直接回答。

<!-- @recalled_base -->
不要再對 {label} 重複同一個問題的 recall。{view}

<!-- @base -->
完整原始輸出已存成 #{id}：之後使用者追問這份輸出裡上面沒寫到的內容時，執行 result_recall {id} "<使用者的話>" 回原文提煉（只有要找某個字串出現在哪幾行才用 result_grep），不要重新執行同一個工具。{view}

<!-- @fallback -->
整合沒有成功，上面的事實是各段直接摘出的：據此回答，不要補上沒列的內容。

<!-- @need_more -->
獨立 session 判斷這個問題還需要之前的存檔 {records} 一起看才答得完整：下一輪直接執行 result_recall {combo} "<使用者的話>"（逗號隔開的幾份原文交給同一次提煉一起整合），拿到後再回答，不要先問使用者、也不要重跑當時的工具。

<!-- @unread -->
有些段落這次沒有讀到（見「未涵蓋」）：上面已經回答的就直接回答；使用者要的正好在沒讀到的那幾行時，用更具體的問題 result_recall {id} "<問題>"（會依問題重新挑段落），或 result_view 看那幾行。

<!-- @gap_ask -->
上面的缺口原文裡沒有：下一輪用 reply 自然地問使用者一句話（不要條列、不要照抄），不要自己選一個方向去執行，除非使用者這句話已經對應到其中一個方向。

<!-- @answered -->
上面已經回答了使用者的問題：直接據此回答或做任務的下一步，不需要再 recall；後面列的方向只是額外可能有興趣的，順口提一句或略過都可以。

<!-- @cc_related_item -->
#{id}：{reason}

<!-- @cc_no_reason -->
（未給理由）
