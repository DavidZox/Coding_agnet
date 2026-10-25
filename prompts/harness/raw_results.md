claude_code 模式下工具回傳進主對話的字（agent_core/context_mode.py）：原文太長時中間省略的那一行（gap）、上下文超過水位時舊回傳換成的佔位
（cleared）。第一行的「（完整原文存檔 #N，約 X tokens）」留在程式裡：清除舊回傳時程式靠它找存檔編號。{名稱} 是程式填的值。

<!-- @gap -->
…（{where}省略，約 {omitted} tokens{contents}。上面看不到的內容不代表不存在：使用者問的東西不在頭尾時，先查存檔 #{rid} 再回答——找字串用 result_grep {rid} "<關鍵字>"、看這一段用 result_view {rid} --from {view_from} --lines 80、要依問題整理這一大份內容用 result_recall {rid} "<問題>"）…

<!-- @where_lines -->
中間第 {first}～{last} 行

<!-- @where_one_line -->
中間（單行過長）

<!-- @sections -->
；中間的章節：{sections}

<!-- @section_item -->
行 {n} {title}

<!-- @sections_more -->
…共 {count} 節

<!-- @cleared -->
這則舊的工具回傳（約 {tokens} tokens）已從上下文清除以節省空間；完整原文仍在存檔 #{rid}{what}。需要時用 result_view {rid}、result_grep {rid} "<關鍵字>" 或 result_recall {rid} "<問題>" 取回，不要重新執行同一個工具。

<!-- @cleared_what -->
（當時執行：{what}）
