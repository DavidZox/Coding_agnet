新架構的高階分工（agent_core/orchestrator.py 的 run_plan，第 5 步 5-3）交給下一層的文字：前面的領域查到的（_known_text：子工作階段的
第一則訊息裡一段、中階收到的問題後面接一段）、這個問題的分工（_division_text：子工作階段的第一則訊息裡一段）。{名稱} 是程式填的值。

<!-- @known -->

【前面的領域查到的】（系統從它們的報告取，可以直接用）
{rows}

<!-- @known_answer -->
- {domain}：{item}：{text}（出處：{refs}）

<!-- @known_not_found -->
- {domain}：{item}：查不到（{text}）

<!-- @known_out_of_domain -->
- {domain}：{item}：不屬於它（{text}）

<!-- @known_report -->
- {domain} 的報告（#{rid}，前面的部分）：
{text}

<!-- @division -->

【這個問題的分工】（主對話分好的；你只做標了「你」的那一項）
{rows}

<!-- @division_entry -->
{n}. {domain}：{goal}（{state}）

<!-- @division_main -->
- 主對話這一回合已經做的：{command} → {head}

<!-- @state_you -->
你

<!-- @state_done -->
做完了，結果在上面

<!-- @state_todo -->
之後由它做
