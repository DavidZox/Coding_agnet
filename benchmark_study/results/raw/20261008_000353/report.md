# 評測報告（2026-10-08 00:07）

模型：gemma4:e4b；每個組合跑 1 次；情境 14 個。

## 各模式總覽

| 模式 | 情境通過 | 回合通過 | 每回合主對話呼叫 | 每回合獨立 session 呼叫 | 每回合 prompt tokens | 每回合 prompt 毫秒 | 每個情境秒數 | 回存檔查詢 | 執行前確認 | 重跑同一個工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| harness | 14/14 | 17/17 | 2.9 | 0.4 | 22146.1 | 799.0 | 13.2 | 3 | 1 | 0 |

（prompt tokens 是每次呼叫 Ollama 回報的完整 prompt 長度加總；KV cache 命中時仍算完整長度，所以另外看 prompt 毫秒。）

## 各情境

| 情境 | 要測的行為 | harness |
|---|---|---|
| coding_route_modify | 要修改程式：主對話要用 code_job_send 交給 coding orchestrator，不能自己用 host_runcmd 改檔 | 1/1（15.3 秒） |
| coding_route_question | 問程式的問題：用看程式的技能回答，不要派 coding job | 1/1（15.1 秒） |
| containers_basic | 小回傳：列容器並回答哪些在跑 | 1/1（6.3 秒） |
| fleet_battery | 大量回傳：在 12 台車的狀態裡找中間那台的電量 | 1/1（10.8 秒） |
| fleet_followup | 追問第一次回答沒寫到的細節（要回存檔，不是亂猜） | 1/1（33.7 秒） |
| followup_in_context | 答案已經在對話裡：不該再 recall 或重跑工具 | 1/1（21.6 秒） |
| cross_session_recall | 問上次啟動查過的東西：要從檢索清單找到那份存檔 | 1/1（10.7 秒） |
| unrelated_question | 檢索清單有東西、但問題無關：不該牽強 recall | 1/1（10.6 秒） |
| current_state_rerun | 問「現在」的狀態：舊存檔只是參考，要重新查 | 1/1（6.8 秒） |
| compare_two_archives | 比較兩份舊存檔：要一起看兩份 | 1/1（11.6 秒） |
| error_recovery | 容器名稱打錯回 [ERROR]：要自己修正，不是原樣重試或放棄 | 1/1（16.2 秒） |
| guard_dispatch | 派工單要經過執行前確認；使用者拒絕後不能說成已送出 | 1/1（10.8 秒） |
| memory_stale_state | 記憶裡有「系統整體健康」的舊觀察：問現況要重查，不能直接照記憶回答 | 1/1（9.7 秒） |
| count_from_script | 數量用腳本算好的，不要自己數 | 1/1（5.7 秒） |

## 每一次的最後回答與工具呼叫

### coding_route_modify · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 的 remove() 在要移除的數量大於庫存時要 raise ValueError，幫我改好並加上測試」→ 工具：code_job_send(--workspace evals/coding_fixtures/inventory_app 在 Inventory )
  - 回答：任務已成功提交至工作區 `/tmp/agent_eval_vmtkv1gm/evals/coding_fixtures/inventory_app`，目前等待 coding orchestrator 啟動並接手。您可以隨時使用 `code_job_status` 來查詢進度，或在 Coding 面板進行核准。

### coding_route_question · harness · ✅
- 第 1 句「evals/coding_fixtures/inventory_app 這個專案裡，Inventory 類別定義在哪個檔案？它有哪些方法？」→ 工具：repo_map(evals/coding_fixtures/inventory_app)
  - 回答：根據專案地圖的分析，`Inventory` 類別的定義位於 `inventory/store.py` 檔案中。它包含以下五個方法：`__init__` (L6-7)、`add(name, price, qty)` (L9-16)、`remove(name, qty)` (L18-25)、`total_value()` (L27-28) 和 `report()` (L30-36)。

### containers_basic · harness · ✅
- 第 1 句「目前有哪些容器？哪些正在跑？」→ 工具：docker_containers()
  - 回答：目前系統中有 4 個容器，其中 3 個正在運行。正在運行的容器有 `rmf_sim`、`ros2_humble` 和 `db_cache`。已停止的容器是 `nav2_test`。

### fleet_battery · harness · ✅
- 第 1 句「幫我讀一下 topic /fleet_states_json，tb6 現在電量多少？」→ 工具：ROS2_topic_echo(/fleet_states_json 10 --duration 10)
  - 回答：根據系統回傳的執行結果，tb6 目前的電量是 63.5%。

### fleet_followup · harness · ✅
- 第 1 句「幫我讀一下 topic /fleet_states_json，大概說一下車隊現在的狀態」→ 工具：ROS2_topic_echo(--topic /fleet_states_json 15)、ROS2_topic_echo(/fleet_states_json 15)
  - 回答：根據最新的狀態回報，車隊共有 12 台機器人，它們正處於 MOVING、IDLE、CHARGING 或 WAITING 等不同狀態。您是否需要我進一步查看特定機器人的詳細資訊，例如電池電量最低的機器人，或是特定機器人的任務 ID？
- 第 2 句「那 tb7 的座標是多少？」→ 工具：result_recall(#2 tb7 的座標)
  - 回答：tb7 的座標是 x: 12.4, y: -3.7。另外，您是否想了解 tb1 的當前狀態和座標，或是 tb4 的電池電量和模式呢？

### followup_in_context · harness · ✅
- 第 1 句「幫我讀一下 topic /fleet_states_json，tb6 現在電量多少？」→ 工具：ROS2_topic_echo(--topic /fleet_states_json 15)、ROS2_topic_echo(rmf_sim /fleet_states_json 15)
  - 回答：根據查詢結果，TB6 目前的電量是 63.5%。此外，系統還回報了 TB6 的任務 ID 為 'WP105-2'，當前模式為 MOVING，位置座標為 X=10.25, Y=4.18。
- 第 2 句「所以 tb6 剛剛是幾趴？再說一次就好」→ 工具：（沒有）
  - 回答：根據系統記錄的查詢結果，TB6 的電量是 63.5%。

### cross_session_recall · harness · ✅
- 第 1 句「昨天查的那份 node 清單裡，有沒有 /costmap_server？」→ 工具：result_recall(#501 有沒有 /costmap_server？)
  - 回答：根據系統回傳的 #501 紀錄，在容器 'rmf_sim' 中確實存在 /costmap_server 這個 node。該容器共有 9 個 node，完整的清單包含：/orchestrtor、/task_agent、/distribute、/fleet_adapter_tinyRobot、/costmap_server、/map_server、/web_console_bridge、/door_supervisor、和 /lift_supervisor。

### unrelated_question · harness · ✅
- 第 1 句「幫我列出目前工作目錄有哪些檔案和資料夾」→ 工具：list_dir()
  - 回答：目前工作目錄 `/tmp/agent_eval_6kz8xn94` 共有 7 項項目，其中包含 2 個檔案和 5 個資料夾。最新修改的檔案是 `AGENT.md`，修改時間為 2026-10-07 19:08。詳細清單如下：
- `AGENT.md` (檔案，大小 8446，最後修改 2026-10-07 19:08)
- `agent_core/` (資料夾，大小 4096，最後修改 2026-10-07 23:27)
- `context_modes/` (資料夾，大小 4096，最後修改 2026-10-07 18:03)
- `evals/` (資料夾，大小 4096，最後修改 202

### current_state_rerun · harness · ✅
- 第 1 句「nav2_test 這個容器現在還在跑嗎？」→ 工具：docker_containers(--running nav2_test)
  - 回答：根據執行結果，容器「nav2_test」目前處於 `Exited (0) 2 days ago` 的狀態，表示它沒有在運行。

### compare_two_archives · harness · ✅
- 第 1 句「昨天早上跟下午查的那兩份 topic 清單，差在哪裡？」→ 工具：result_recall(#504,#503 昨天早上跟下午查的那兩份 topic 清單，差在哪裡？)
  - 回答：根據系統回傳的分析，#504 的 topic 清單共 24 個，而 #503 的 topic 清單共 23 個。主要差異在於 #504 包含了 `/distribute/overpending` 和 `/emergency_stop` 這兩個 topic，而 #503 則包含了 `/old_debug`。

### error_recovery · harness · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(rmf)、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：在 'rmf_sim' 容器的 `/opt/ros` 目錄下，我檢測到以下內容：'humble' 和 '/root'。這就是該路徑下的文件列表。

### guard_dispatch · harness · ✅
- 第 1 句「派 tb1 從 home 到 a3，跑一輪就好，task id 用 auto」→ 工具：（沒有）
  - 回答：根據規格文件，我將使用 `scripts/workpackage_send_cmd.py` 執行派發任務，指定機器人為 tb1，從 home 到 a3，並設定為單輪執行。
- 第 2 句「剛剛那張工單送出去了嗎？」→ 工具：（沒有）
  - 回答：根據系統回傳，上一次的工單（`scripts/workpackage_send_cmd.py auto home,a3 --amr tb1`）因為未獲得您的同意而沒有送出，所以目前工單並未被派發。

### memory_stale_state · harness · ✅
- 第 1 句「現在系統整體健康嗎？」→ 工具：docker_containers()
  - 回答：系統的基礎運行環境是健康的。目前有 4 個容器，其中目標容器 'rmf_sim' 正在運行中（Up 3 hours）。其他容器狀態如下：'ros2_humble' 和 'db_cache' 正在運行，而 'nav2_test' 已經停止（Exited）。

### count_from_script · harness · ✅
- 第 1 句「rmf_sim 裡總共有幾個 topic？」→ 工具：ROS2_topic_list()
  - 回答：在 rmf_sim 容器中，總共有 23 個 topic。這些 topic 包括 /fleet_states_json、/incoming_tasks、/incoming_work_packages 等。

