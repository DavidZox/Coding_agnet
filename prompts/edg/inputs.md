低階執行器（agent_core/edg.py）的第 1 級修正：交給模型的 user 訊息裡程式組的標籤（規則在 fix.md）。
{名稱} 是程式填的值：goal＝子目標；why＝這個節點要做什麼（排圖時寫的，沒寫就不放這一則）；tool＝工具名稱；spec＝工具的規格
（給模型看的那一份）；args＝這一次的參數（JSON 陣列）；kind＝錯誤的種類（下面 kind_* 的一則）；error＝錯誤的原文；
rules＝逾時時可以用的縮小方式（下面 narrow_* 的幾則）；arg＝參數的名稱。

<!-- @goal -->
【子目標】
{goal}

<!-- @why -->
【這一步要做什麼】
{why}

<!-- @tool -->
【工具】{tool}
【工具的規格】
{spec}

<!-- @args -->
【這一次的參數（JSON 陣列）】
{args}

<!-- @error_pre -->
【錯誤：{kind}；執行前的參數檢查沒過，還沒有執行】
{error}

<!-- @error_run -->
【錯誤：{kind}；執行之後腳本回報的】
{error}

<!-- @kind_args -->
參數錯

<!-- @kind_timeout -->
逾時，還沒有任何結果

<!-- @narrow -->
【逾時時可以用的縮小方式（只能動這些，其他參數不變）】
{rules}

<!-- @narrow_inside -->
- {arg}：換成原本路徑裡面的子目錄或檔案

<!-- @narrow_added -->
- {arg}：多加一項（原本的都留著）
