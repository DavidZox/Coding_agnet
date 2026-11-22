子工作階段直接叫的複合工具（建議 3，config.DOMAIN_SUB；agent_core/orchestrator.py 的 composite_doc、run_composite）：給模型的規格
（說明、〈什麼時候用〉、參數與執行的寫法；骨架、回退、判斷不給，程式照它們做）、參數的每一行、回傳的第一行與下一步。
參數的種類用 prompts/mid/inputs.md 的 type_*（合約也用同一份）。{名稱} 是程式填的值。

<!-- @doc -->
# {name}：{title}（複合工具）
{description}

## 什麼時候用
{when}

## 參數
{params}

## 執行
EXECUTE: scripts/{name}_cmd.py {usage}
- 程式照寫好的步驟查（搜尋、看檔案、分析程式），照收據整理成報告：每一處附 檔案:行號 與 #編號，數量由程式從收據算。回答照報告寫，出處寫報告裡的 檔案:行號 或這份結果的 #編號。
- 參數不對、路徑找不到、範圍太大時回 [ERROR]，附要改什麼與候選：改了參數再執行一次。

<!-- @param_required -->
- --{name}（{kind}，必填）：{desc}

<!-- @param_default -->
- --{name}（{kind}，可以不寫，預設 {default}）：{desc}

<!-- @param_optional -->
- --{name}（{kind}，可以不寫）：{desc}

<!-- @usage_required -->
--{name} <{kind}>

<!-- @usage_optional -->
[--{name} <{kind}>]

<!-- @head -->
複合工具 {name} 的報告：{status}

<!-- @err_args -->
複合工具 {name} 的參數有問題：{why}。下一步：照規格改參數再執行：EXECUTE: scripts/{name}_cmd.py {usage}

<!-- @err_params -->
複合工具 {name} 要改參數：{why}。下一步：照上面改參數再執行一次；這個工具用不上就用其他工具一步一步查。

<!-- @err_failed -->
複合工具 {name} 沒有做完：{status}{why}。下一步：用其他工具一步一步查。
