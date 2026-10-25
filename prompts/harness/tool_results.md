主對話收到工具結果時程式包上的字：每一則工具結果的框架句（agent_core/protocol.py 的 tool_result_message，前面的【系統回傳】是程式認的
標記，留在程式裡）、使用者沒把結果加入時的通知、harness 模式沒有提煉時只給成功／失敗的那一則（agent_core/turn.py）。{名稱} 是程式填的值。

<!-- @frame -->
以下是系統執行{what}的結果，由系統自動產生、不是使用者提供的（使用者也看到同一份）。回覆時稱「執行結果」或「系統回傳」，不要感謝使用者、不要說「您提供的」。

<!-- @frame_action -->
你上一輪 action（{label}）

<!-- @frame_action_plain -->
你上一輪 action

<!-- @frame_tail -->
（以上為系統回傳，不是使用者提供的）

<!-- @discarded -->
工具已執行完畢，但使用者選擇不把結果加入上下文（結果只有使用者看到）。請依此繼續，不要重複執行同一個指令。

<!-- @reduced -->
指令已{status}執行（原始輸出約 {tokens} tokens，超過門檻 {threshold}，且獨立摘要 session 未啟用或失敗，內容未加入上下文）。完整內容已顯示給使用者；你看不到它。{recall}，不要憑空補上結果。

<!-- @reduced_failed -->
失敗

<!-- @reduced_ok -->
成功

<!-- @reduced_recall -->
完整原始輸出已存成結果檔 #{rid}：需要內容時由你自己執行 result_recall {rid} "<使用者的問題>"（交給獨立 session 依問題提煉）、或 result_view {rid} --outline 看有哪幾節再 --from <行號> 看那一段（不要叫使用者去看），不要重新執行同一個工具

<!-- @reduced_no_recall -->
需要內容時請換更精確的參數重新執行工具
