工作流的判斷點（agent_core/workflow.py 的 WorkflowRun.fill_values、do_check）交給模型的 user 訊息：規則在 fill.md、check.md，
這裡是程式組進去的標籤、選項與前面各步的輸出。{名稱} 是程式填的值。不在這裡的：工作流的報告與 [ERROR]（程式的輸出）。

<!-- @fill_user -->
【工作流】{title}（{name}）：{purpose}

【整份步驟】
{outline}

【這一步】第 {n} 步：{step}
命令：scripts/{script} {args}
要你決定的值：{names}

{context}

<!-- @context_output -->
【第 {n} 步的輸出】{title}（{command}；存檔 #{rid}）
{output}

<!-- @context_inputs -->
【需要的資訊】{inputs}

<!-- @context_no_inputs -->
（沒有）

<!-- @fill_retry -->
【上一次用你給的值執行，技能回報錯誤】
{error}
依錯誤訊息改正這幾個值（照抄輸出裡的寫法）。

<!-- @check_user -->
【工作流】{title}

【整份步驟】
{outline}

【這一步要判斷的事】第 {n} 步：{step}

【選項】
{options}

{context}

<!-- @check_option_branch -->
「{when}」→ {target}

<!-- @check_target_end -->
結束

<!-- @check_target_step -->
第 {to} 步

<!-- @check_option_continue -->
繼續做下一步

<!-- @check_option_stop -->
結束（不再做下去）
