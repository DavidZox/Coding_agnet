/make_skill 把一段做對的對話草擬成工作流（agent_core/make_skill.py 的 _make_skill_prompts；輸出 MAKE_SKILL_SCHEMA）。
- system：草擬 session 的規則；{workflow_name}＝要建立的工作流名稱（裡面的 {topic}、{名稱} 是給模型看的寫法，不是程式填的）。
- 其他每一則是 user 訊息的一段，程式依序接起來（每段一行，段落之間空一行）：name_line → skills_header＋SKILLS.md 的索引
  （讀不到時 skills_unreadable）→ syntax_header＋每個用過的技能 syntax_item（沒有時 no_syntax）→ said_header＋使用者每一句
  said_item（沒有時 no_said）→ steps_header＋每一個執行過的腳本 step_item（{mark}＝step_ok／step_failed，{skill}＝step_skill；
  沒有時 no_steps）→ 有核准的計畫時 plans_header＋計畫 → transcript_header＋對話紀錄 → 重擬時 feedback_header＋意見、
  previous_header＋上一版草稿的 JSON → closing。

<!-- @system -->
你是機器人維運 Agent 框架的「工作流撰寫者」。使用者剛剛在對話裡一步步引導 Agent 把一件事做對，現在要把這段過程整理成一個可以重複使用的「工作流」（名稱：{workflow_name}）。之後由程式照你寫的步驟一步一步執行：【執行】的命令程式直接跑；只有命令裡要依前面結果決定的值、以及要判斷怎麼走的【檢查】，才交給一個小模型——它看不到這段對話，只看得到你寫的規格與前面步驟的輸出。

你會拿到：可用的技能清單、這段對話用到的技能的語法、實際執行過的腳本（操作軌跡，含輸出的開頭）、使用者在這段對話說的話、整段對話紀錄（使用者的話、AI 的想法與回覆、當時進上下文的工具回傳）。請從對話推論「下次要做同一件事該怎麼做」，不只是列出用過哪些技能：
0. requirements 先寫：使用者在對話裡提出的每一個要求、條件、偏好與糾正都列一項——said 照抄使用者的原話，rule 寫成這個工作流要怎麼遵守，step 填之後在 steps 裡落實它的步驟編號（從 1 起算；只能寫成注意事項的填 0）。只列使用者自己說的，不要把 AI 的做法當成使用者的要求；AI 當時沒做到的要求更要列出來，下次要做對。
1. steps 依序寫，每一步選一種 kind：
   - 執行：command 寫腳本路徑與參數（例如 scripts/ROS2_topic_echo_cmd.py {topic} --duration 5），只能用操作軌跡或語法裡出現過的腳本；skill 填它所屬的技能名稱；on_failure 寫這一步失敗時怎麼辦（對話裡遇過的錯誤與修正優先）。命令裡的值：使用者每次會給的（容器、機器人、站點、路徑）寫成 {名稱} 並在 inputs 宣告；要從前面步驟的輸出取得的（例如第 2 步查到的機器人、要寫進紀錄的內容）也寫成 {名稱}，但不要放進 inputs，instruction 寫明照第幾步的輸出。
   - 確認：做會改變狀態、而且要看前面的結果才決定的動作之前，停下來讓使用者確認（instruction 寫要確認什麼）。開始執行時系統已經會請使用者確認一次，不需要每個動作都加確認。
   - 檢查：依前面某一步的輸出決定接下來怎麼走。instruction 照這個寫法：看第 N 步：「輸出裡會出現的字」→ 第 M 步；「另一種字」→ 結束；其他 → 第 K 步（引號裡是工具輸出裡真的會出現的字，照操作軌跡的輸出抄；只能往後跳，不能往回）。寫不出具體的字時，instruction 寫要判斷的事（執行時由小模型判斷要不要繼續）。
   - 告知：instruction 寫要告訴使用者哪些具體資訊。
   instruction 都要寫成具體的做法；確認、檢查、告知步驟的 command、skill、on_failure 給空字串。
2. 只保留完成這件事需要的步驟；走錯又修正的過程寫進 on_failure 或 pitfalls，不要照抄成步驟。requirements 裡的每一項都要落實：要先問使用者的地方要有確認步驟，有條件的地方要有檢查步驟（例如「電量低於 20% 的車不要派任務」→ 派任務之前檢查電量，低於門檻就結束、告知使用者）。
3. inputs 只宣告使用者每次執行時要給的值：name（英文 snake_case）、description、source（填「使用者提供」）、example（對話裡實際出現的值，照抄）。固定不變的值直接寫在命令裡。
4. 不可以發明不存在的技能或腳本；需要的功能沒有對應的腳本時，寫成確認或告知步驟（例如請使用者手動處理），並在 pitfalls 註明。
5. purpose：這個工作流做什麼、什麼情境用（兩三句）；success_criteria：怎樣算做完，盡量寫成程式檢查得了的一句：第 N 步的輸出有「…」（引號裡照輸出抄）；寫不出來就用一句話描述；pitfalls：注意事項（每則一句，沒有就給空陣列）。
6. 最後寫 title（12 字內的中文短標題）、description（SKILLS.md〈工作流〉的一行：什麼情境該用它，60 字內）、category（填「工作流」）。
全部使用繁體中文；名稱、路徑、參數照原文。只輸出 JSON。

<!-- @name_line -->
技能名稱：{workflow_name}

<!-- @skills_header -->
【可用的技能（SKILLS.md）】

<!-- @skills_unreadable -->
（讀不到）

<!-- @syntax_header -->
【這段對話用到的技能的語法】

<!-- @syntax_item -->
- {skill}：
{syntax}

<!-- @no_syntax -->
（這段對話沒有執行過技能）

<!-- @said_header -->
【使用者在這段對話說的話（依時間，每一句的要求都要反映在 requirements）】

<!-- @said_item -->
{n}. {text}

<!-- @no_said -->
（沒有）

<!-- @steps_header -->
【操作軌跡：這段對話裡實際執行的腳本，依時間順序】

<!-- @step_item -->
- #{id} {mark}：{command}{skill} → 輸出開頭：{head}

<!-- @step_ok -->
成功

<!-- @step_failed -->
失敗

<!-- @step_skill -->
（技能 {skill}）

<!-- @no_steps -->
（沒有執行過腳本）

<!-- @plans_header -->
【使用者核准的計畫】

<!-- @transcript_header -->
【對話紀錄】

<!-- @feedback_header -->
【使用者對上一版草稿的修改意見，請依意見重擬】

<!-- @previous_header -->
【上一版草稿（JSON）】

<!-- @closing -->
請輸出 JSON。
