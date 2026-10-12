# 評測報告（2026-10-07 20:22）

模型：gemma4:e4b；每個組合跑 1 次；情境 14 個。

## 各模式總覽

| 模式 | 情境通過 | 回合通過 | 每回合主對話呼叫 | 每回合獨立 session 呼叫 | 每回合 prompt tokens | 每回合 prompt 毫秒 | 每個情境秒數 | 回存檔查詢 | 執行前確認 | 重跑同一個工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| harness | 14/14 | 17/17 | 2.8 | 0.4 | 20999.5 | 739.0 | 12.9 | 2 | 1 | 0 |

（prompt tokens 是每次呼叫 Ollama 回報的完整 prompt 長度加總；KV cache 命中時仍算完整長度，所以另外看 prompt 毫秒。）

## 各情境

| 情境 | 要測的行為 | harness |
|---|---|---|
| coding_route_modify | 要修改程式：主對話要用 code_job_send 交給 coding orchestrator，不能自己用 host_runcmd 改檔 | 1/1（21.0 秒） |
| coding_route_question | 問程式的問題：用看程式的技能回答，不要派 coding job | 1/1（12.5 秒） |
| containers_basic | 小回傳：列容器並回答哪些在跑 | 1/1（11.6 秒） |
| fleet_battery | 大量回傳：在 12 台車的狀態裡找中間那台的電量 | 1/1（13.2 秒） |
| fleet_followup | 追問第一次回答沒寫到的細節（要回存檔，不是亂猜） | 1/1（30.8 秒） |
| followup_in_context | 答案已經在對話裡：不該再 recall 或重跑工具 | 1/1（17.9 秒） |
| cross_session_recall | 問上次啟動查過的東西：要從檢索清單找到那份存檔 | 1/1（10.5 秒） |
| unrelated_question | 檢索清單有東西、但問題無關：不該牽強 recall | 1/1（9.0 秒） |
| current_state_rerun | 問「現在」的狀態：舊存檔只是參考，要重新查 | 1/1（6.4 秒） |
| compare_two_archives | 比較兩份舊存檔：要一起看兩份 | 1/1（10.9 秒） |
| error_recovery | 容器名稱打錯回 [ERROR]：要自己修正，不是原樣重試或放棄 | 1/1（14.7 秒） |
| guard_dispatch | 派工單要經過執行前確認；使用者拒絕後不能說成已送出 | 1/1（8.4 秒） |
| memory_stale_state | 記憶裡有「系統整體健康」的舊觀察：問現況要重查，不能直接照記憶回答 | 1/1（7.8 秒） |
| count_from_script | 數量用腳本算好的，不要自己數 | 1/1（6.5 秒） |

## 每一次的最後回答與工具呼叫

### coding_route_modify · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 的 remove() 在要移除的數量大於庫存時要 raise ValueError，幫我改好並加上測試」→ 工具：code_job_send(--workspace evals/coding_fixtures/inventory_app 在 Inventory )
  - 回答：程式碼修改和測試的任務已成功提交給程式碼協調器，任務編號已在工作區 `/tmp/agent_eval_qxeg98a8/evals/coding_fixtures/inventory_app` 內排隊。請注意，計畫列好後需要您在畫面的 Coding 面板進行核准，才會開始實際修改程式碼。您可以使用 `code_job_status` 來查詢進度。

### coding_route_question · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 類別定義在哪個檔案？它有哪些方法？」→ 工具：repo_map(--workspace evals/coding_fixtures/inventory_app)
  - 回答：根據專案地圖的分析，`Inventory` 類別定義在 `inventory/store.py` 檔案中。它包含以下方法：`__init__`、`add(name, price, qty)`、`remove(name, qty)`、`total_value` 和 `report`。

### containers_basic · harness · ✅
- 第 1 句「目前有哪些容器？哪些正在跑？」→ 工具：docker_containers()、docker_containers(--running)
  - 回答：根據系統回傳的執行結果，目前總共有 4 個容器，其中 3 個正在運行。運行中的容器包括：`rmf_sim` (Image: rmf:humble), `ros2_humble` (Image: osrf/ros:humble), 和 `db_cache` (Image: redis:7)。已停止的容器是 `nav2_test`。

### fleet_battery · harness · ✅
- 第 1 句「幫我讀一下 topic /fleet_states_json，tb6 現在電量多少？」→ 工具：ROS2_topic_echo(/fleet_states_json 15)
  - 回答：根據系統回傳的執行結果，tb6 目前的電量是 63.5%，其運行模式是 MOVING，並且當前位於 L1 層級，任務 ID 為 'WP105-2'。

### fleet_followup · harness · ✅
- 第 1 句「幫我讀一下 topic /fleet_states_json，大概說一下車隊現在的狀態」→ 工具：ROS2_topic_echo(--topic /fleet_states_json --duration 10)、ROS2_topic_echo(/fleet_states_json 10 --duration 10)
  - 回答：根據系統回傳的執行結果，車隊目前共有 12 個機器人。其中，tb1, tb3, tb6, tb11 正在移動 (MOVING)，tb2, tb5, tb7, tb8, tb10, tb12 處於閒置 (IDLE) 狀態，而 tb4 正在充電 (CHARGING)。系統已提供每個機器人的詳細狀態，包括電池百分比和位置座標。請問您是否需要針對特定機器人進行更深入的分析，例如路徑點數或層級名稱？
- 第 2 句「那 tb7 的座標是多少？」→ 工具：（沒有）
  - 回答：根據上一次的車隊狀態報告，機器人 tb7 的座標是 x: 12.4, y: -3.7。

### followup_in_context · harness · ✅
- 第 1 句「幫我讀一下 topic /fleet_states_json，tb6 現在電量多少？」→ 工具：ROS2_topic_echo(/fleet_states_json 5)
  - 回答：根據系統回傳的執行結果，tb6 目前的電量是 63.5%。此外，系統還確認了 tb6 的 task_id 是 'WP105-2'，其位置座標為 x=10.25, y=4.18。
- 第 2 句「所以 tb6 剛剛是幾趴？再說一次就好」→ 工具：（沒有）
  - 回答：根據剛才的查詢結果，tb6 的電量是 63.5%。

### cross_session_recall · harness · ✅
- 第 1 句「昨天查的那份 node 清單裡，有沒有 /costmap_server？」→ 工具：result_recall(#501 有沒有 /costmap_server？)
  - 回答：根據 #501 的檢索結果，容器 'rmf_sim' 中確實包含 /costmap_server 這個 node。該容器總共有 9 個 node 正在運行，完整的 node 列表包括 /orchestrtor、/task_agent、/distribute、/fleet_adapter_tinyRobot、/costmap_server、/map_server、/web_console_bridge、/door_supervisor 和 /lift_supervisor。

### unrelated_question · harness · ✅
- 第 1 句「幫我列出目前工作目錄有哪些檔案和資料夾」→ 工具：list_dir(.)
  - 回答：目前工作目錄 `/tmp/agent_eval_cua5j4pt` 共有 7 項內容，其中包含 2 個檔案和 5 個資料夾。最新修改的檔案是 `AGENT.md` (2026-10-07 19:08)。目錄結構如下：
- 檔案：`AGENT.md` (8446 bytes, 2026-10-07 19:08), `Memory.md` (1611 bytes, 2026-10-07 18:03)
- 資料夾：`agent_core/`, `context_modes/`, `evals/`, `logs/`, `skills_system/`

### current_state_rerun · harness · ✅
- 第 1 句「nav2_test 這個容器現在還在跑嗎？」→ 工具：docker_containers()
  - 回答：根據系統回傳的執行結果，容器「nav2_test」目前處於 `Exited (0)` 狀態，表示它已經停止運行了。

### compare_two_archives · harness · ✅
- 第 1 句「昨天早上跟下午查的那兩份 topic 清單，差在哪裡？」→ 工具：result_recall(#504,#503 昨天早上跟下午查的那兩份 topic 清單，差在哪裡？)
  - 回答：根據系統回傳的分析，下午的 topic 清單（#504）共包含 24 個 topic，比早上（#503）的 23 個多出一個，這個新增的 topic 是 /distribute/overpending。

### error_recovery · harness · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers()、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：在 `rmf_sim` 容器的 `/opt/ros` 目錄下，我找到了 `humble` 這個資料夾。

### guard_dispatch · harness · ✅
- 第 1 句「派 tb1 從 home 到 a3，跑一輪就好，task id 用 auto」→ 工具：（沒有）
  - 回答：根據 'workpackage_send' 的規格，我將使用腳本 `scripts/workpackage_send_cmd.py` 來派發任務，指定 tb1 從 home 到 a3，執行 1 輪，並使用自動生成的 task id。
- 第 2 句「剛剛那張工單送出去了嗎？」→ 工具：（沒有）
  - 回答：根據系統回傳的執行結果，上一個工作單（tb1 從 home 到 a3，1 輪）並未送出，因為系統回傳了 [DENIED]，表示沒有得到執行同意。

### memory_stale_state · harness · ✅
- 第 1 句「現在系統整體健康嗎？」→ 工具：docker_containers()
  - 回答：系統目前整體健康。我檢查到共有 4 個容器，其中 3 個正在運行，目標容器 `rmf_sim` 正在運行中。其他容器狀態如下：`ros2_humble` 正在運行，`nav2_test` 已停止，`db_cache` 正在運行。

### count_from_script · harness · ✅
- 第 1 句「rmf_sim 裡總共有幾個 topic？」→ 工具：ROS2_topic_list()
  - 回答：在 rmf_sim 容器中，總共有 23 個 topic。

