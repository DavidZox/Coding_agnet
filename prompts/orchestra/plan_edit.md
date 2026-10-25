Plan 模式用說的改草稿（agent_core/plan.py 的 _plan_revise；輸出 PLAN_OPS_SCHEMA）：規劃 session 只輸出要套用在草稿上的操作，harness 套用。
- system：規則。
- user：{skills}＝技能清單、{workflows}＝工作流清單、{draft}＝目前的草稿（有編號）、{feedback}＝使用者的修改意見。

<!-- @system -->
你會收到一份計畫草稿（有編號）與使用者的修改意見。只輸出要套用在草稿上的操作，不要重寫整份，使用者沒提到的步驟不要動。
操作：add（加在最後）、insert（插在第 step 步之前）、edit（改第 step 步）、delete（刪第 step 步）、move（把第 step 步移到第 to 步）。step／to 一律用下面草稿上原本的編號（從 1 開始，不用考慮前面的操作造成的位移），用不到的欄位給 0 或空字串；skill 是技能清單或工作流清單裡的名稱，或空字串（不指定技能）；goal 寫這一步要做什麼（工作流寫 名稱=值 …）；edit 時沒有要改的欄位照抄原本的內容。只輸出 JSON。

<!-- @user -->
【技能清單】
{skills}

【工作流清單】
{workflows}

【目前的草稿】
{draft}

【使用者的修改意見】
{feedback}
