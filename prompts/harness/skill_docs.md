主對話用技能名稱當 action 時，系統回傳規格文件前面加的那句話（agent_core/dispatch.py）：這一輪只是載入規格、下一輪要做什麼。
兩階段流程裡最關鍵的一句——小模型載完規格容易停下來解釋或反問使用者，所以直接下達下一輪該做的事。{prefix}、{marker} 是程式認的標記
（[skill doc] 之類，留給程式填），{doc}＝規格文件本身；其他 {名稱} 是程式填的值。

<!-- @loaded_skill -->
{prefix} '{name}' 的規格文件（由系統提供）。這一輪只是載入規格、還沒有執行任何東西：{next}不要向使用者解釋規格內容，也不要詢問是否要執行。
{doc}

<!-- @run_next -->
下一輪請先把這個技能真正執行一次——action.command 填規格標明的實際腳本路徑（scripts/...）、args 填參數，執行完看到結果後才做使用者任務的下一步；

<!-- @args_not_run -->
你附的參數「{args}」也沒有被執行、狀態沒有改變。下一輪請先把這個技能真正執行一次：action.command 填規格標明的實際腳本路徑（scripts/...）、args 填同樣的參數，執行完看到結果後才做下一步；

<!-- @manual -->
{marker}
{prefix} '{name}' 的規格文件（使用者從選單手動載入，等同你以 action.command 填技能名稱後系統回傳的規格；{how}）：
{doc}

<!-- @manual_how -->
依此內容才可執行：action.command 填其中標明的實際腳本路徑、args 填參數
