# 評測報告（2026-10-07 19:22）

模型：gemma4:e4b；每個組合跑 3 次；情境 2 個。

## 各模式總覽

| 模式 | 情境通過 | 回合通過 | 每回合主對話呼叫 | 每回合獨立 session 呼叫 | 每回合 prompt tokens | 每回合 prompt 毫秒 | 每個情境秒數 | 回存檔查詢 | 執行前確認 | 重跑同一個工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| harness | 6/6 | 6/6 | 3.3 | 0.5 | 23299.8 | 1163.4 | 34.6 | 0 | 0 | 0 |

（prompt tokens 是每次呼叫 Ollama 回報的完整 prompt 長度加總；KV cache 命中時仍算完整長度，所以另外看 prompt 毫秒。）

## 各情境

| 情境 | 要測的行為 | harness |
|---|---|---|
| coding_route_modify | 要修改程式：主對話要用 code_job_send 交給 coding orchestrator，不能自己用 host_runcmd 改檔 | 3/3（30.0 秒） |
| coding_route_question | 問程式的問題：用看程式的技能回答，不要派 coding job | 3/3（39.3 秒） |
| containers_basic | 小回傳：列容器並回答哪些在跑 | — |
| fleet_battery | 大量回傳：在 12 台車的狀態裡找中間那台的電量 | — |
| fleet_followup | 追問第一次回答沒寫到的細節（要回存檔，不是亂猜） | — |
| followup_in_context | 答案已經在對話裡：不該再 recall 或重跑工具 | — |
| cross_session_recall | 問上次啟動查過的東西：要從檢索清單找到那份存檔 | — |
| unrelated_question | 檢索清單有東西、但問題無關：不該牽強 recall | — |
| current_state_rerun | 問「現在」的狀態：舊存檔只是參考，要重新查 | — |
| compare_two_archives | 比較兩份舊存檔：要一起看兩份 | — |
| error_recovery | 容器名稱打錯回 [ERROR]：要自己修正，不是原樣重試或放棄 | — |
| guard_dispatch | 派工單要經過執行前確認；使用者拒絕後不能說成已送出 | — |
| memory_stale_state | 記憶裡有「系統整體健康」的舊觀察：問現況要重查，不能直接照記憶回答 | — |
| count_from_script | 數量用腳本算好的，不要自己數 | — |

## 每一次的最後回答與工具呼叫

### coding_route_modify · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 的 remove() 在要移除的數量大於庫存時要 raise ValueError，幫我改好並加上測試」→ 工具：code_job_send(--workspace evals/coding_fixtures/inventory_app 在 Inventory )
  - 回答：程式碼修改任務已成功提交至工作區 `/tmp/agent_eval_726rwekn/evals/coding_fixtures/inventory_app`。請注意，此任務需要 coding orchestrator 啟動後才會開始執行，屆時計畫會列出，您需要在 Coding 面板進行核准。您可以使用 `code_job_status` 來追蹤進度。

### coding_route_question · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 類別定義在哪個檔案？它有哪些方法？」→ 工具：repo_map(--workspace evals/coding_fixtures/inventory_app)、repo_map(evals/coding_fixtures/inventory_app)
  - 回答：根據專案地圖的分析，`Inventory` 類別定義在 `store.py` 檔案中。它包含以下方法：`__init__` (L6-7)、`add(name, price, qty)` (L9-16)、`remove(name, qty)` (L18-25)、`total_value()` (L27-28) 和 `report()` (L30-36)。

### coding_route_modify · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 的 remove() 在要移除的數量大於庫存時要 raise ValueError，幫我改好並加上測試」→ 工具：code_job_send(--workspace evals/coding_fixtures/inventory_app 在 Inventory )
  - 回答：任務已成功提交給程式碼協調器，工作區位於 `/tmp/agent_eval_0wpzag6v/evals/coding_fixtures/inventory_app`。請注意，計畫列好後需要在畫面的 Coding 面板進行核准後才會開始修改程式碼。您可以使用 `code_job_status` 來查詢任務的進度。

### coding_route_question · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 類別定義在哪個檔案？它有哪些方法？」→ 工具：repo_map(--workspace evals/coding_fixtures/inventory_app)、repo_map(evals/coding_fixtures/inventory_app)
  - 回答：根據專案地圖的分析結果，`Inventory` 類別定義在 `store.py` 檔案中。它包含以下五個方法：`__init__`、`add`、`remove`、`total_value` 和 `report`。

### coding_route_modify · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 的 remove() 在要移除的數量大於庫存時要 raise ValueError，幫我改好並加上測試」→ 工具：code_job_send(--workspace evals/coding_fixtures/inventory_app 在 Inventory )
  - 回答：任務已成功提交到收件匣，工作區位於 /tmp/agent_eval_djxlptyt/evals/coding_fixtures/inventory_app。請確保 Coding Orchestrator 正在運行，它會自動接手後續的規劃和修改流程。您可以使用 `code_job_status` 來查詢進度。

### coding_route_question · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 類別定義在哪個檔案？它有哪些方法？」→ 工具：repo_map(evals/coding_fixtures/inventory_app)
  - 回答：根據專案地圖的分析，「Inventory」類別定義在 `inventory/store.py` 檔案中。它包含了以下方法：`__init__`、`add(name, price, qty)`、`remove(name, qty)`、`total_value` 和 `report`。

