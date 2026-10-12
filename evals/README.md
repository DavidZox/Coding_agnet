# 評測（evals）

同一組情境分別用 **harness** 與 **claude_code** 兩種上下文模式跑（模式的差別見〈[架構說明 1.1](../doc/架構說明.md#11-兩種上下文模式context_mode-harnessclaude_code)〉），比較成功率、模型呼叫次數、token 與時間。改了 `AGENT.md`、`context_modes/`、門檻或切換邏輯之後重跑一次，跟上一次的報表比，才知道是變好還是變壞；4B 模型對 prompt 很敏感，改一條規則可能讓另一個行為退化。

## 怎麼跑

```bash
python3 evals/run_evals.py                  # 兩種模式 × 全部情境 × 1 次
python3 evals/run_evals.py --runs 5         # 每個組合跑 5 次（temperature 0.2 仍有隨機性，要比較請用 ≥5 次）
python3 evals/run_evals.py --modes claude_code --only fleet_battery,fleet_followup
python3 evals/run_evals.py --fake           # 假模型：幾秒鐘，只驗證評測流程本身能跑
python3 evals/perf_report.py evals/results/<時間>/runs.jsonl   # 這次評測的 KV cache 分析
python3 evals/perf_report.py                # 平常使用 CLI／Web 累積的 logs/perf.jsonl
```

需要本機 Ollama 與 `gemma4:e4b`（`--model` 可換）。評測期間不要同時開 CLI／Web：同一個模型只有一個 slot，會互相排隊、也會互相洗掉 KV cache，時間數字就不準了。

結果在 `evals/results/<時間>/`（已在 `.gitignore`）：

- `report.md`：各模式總覽、各情境的通過次數與沒通過的條件、每一次的最後回答與工具呼叫。
- `runs.jsonl`：每一次的完整紀錄，含每一步的 thought／reply／action、每個工具呼叫、每次模型呼叫的 token 與毫秒。

## 怎麼運作

- 每一次都在臨時目錄複製一份專案（`agent_core`、`skills_system`、`context_modes`、`evals`、`AGENT.md`、`Memory.md`），在副本裡跑，**不會動到正式的 `logs/` 與 `Memory.md`**。
- 外部世界（docker、ROS2、調度系統）一律用 `scenarios.py` 裡的假輸出，結果可重現；存檔工具（`result_*`）、`modify_memory`、本機檔案類技能（ls、cat、grep、find、cd）在副本裡真的執行。沒準備假資料的腳本會回 `[ERROR]`。
- 流程比照 CLI 的 auto 模式：工具結果自動加入、連續執行到模型不再下 action，每一句使用者訊息最多 20 次模型回覆。執行前確認（派工單等）依情境的 `guard` 自動回答 approve／deny。

## 情境

| 情境 | 要測的行為 |
|---|---|
| containers_basic | 小回傳：列容器並回答哪些在跑 |
| fleet_battery | 大量回傳：12 台車的狀態裡找中間那台的電量 |
| fleet_followup | 追問第一次回答沒寫到的細節（要回存檔，不是亂猜） |
| followup_in_context | 答案已經在對話裡：不該再 recall 或重跑工具 |
| cross_session_recall | 問上次啟動查過的東西：要從檢索清單找到那份存檔 |
| unrelated_question | 檢索清單有東西、但問題無關：不該牽強 recall |
| current_state_rerun | 問「現在」的狀態：舊存檔只是參考，要重新查 |
| compare_two_archives | 比較兩份舊存檔：要一起看兩份 |
| error_recovery | 容器名稱打錯回 `[ERROR]`：要自己修正 |
| guard_dispatch | 派工單要經過執行前確認；使用者拒絕後不能說成已送出 |
| memory_stale_state | 記憶裡有「系統整體健康」的舊觀察：問現況要重查 |
| count_from_script | 數量用腳本算好的，不要自己數 |

## 加一個情境

在 `scenarios.py` 的 `SCENARIOS` 加一個 dict：

```python
{"id": "my_case", "desc": "要測的行為",
 "state": {"target_container": "rmf_sim"},          # 開始前的狀態（可省略）
 "seeds": [SOME_ARCHIVE],                           # 預先放好的舊存檔（可省略）
 "memory": "...",                                   # 取代 Memory.md（可省略）
 "fixtures": {"ROS2_topic_echo_cmd.py": lambda args, agent: "[PASS] ..."},   # 這個情境專用的假輸出（可省略）
 "guard": "deny",                                   # 執行前確認怎麼回答（預設 deny）
 "turns": [{"user": "使用者的話", "expect": {"tools_any": ["ROS2_topic_echo"], "reply_any": ["63.5"]}}]}
```

`expect` 可用的條件（全部成立才算這一句通過；情境的每一句都通過才算情境通過）：

| 條件 | 意思 |
|---|---|
| `reply_all`／`reply_any`／`reply_none` | 這一句回合裡模型所有的回答含有全部／任一／都不含這些字（不分大小寫） |
| `tools_all`／`tools_any`／`tools_none` | 這一句執行過全部／任一／都沒執行這些技能 |
| `archive_lookup` | 有沒有用 `result_recall`／`result_grep`／`result_view`／`result_list` 回存檔查（True／False） |
| `archive_ids` | 回存檔查的參數裡包含這些編號 |
| `guard` | 有沒有觸發執行前確認 |

## 讀報表要注意

- 次數少時差一兩次就是很大的百分比；結論請用 `--runs 5` 以上。
- 情境的問法本身也會影響結果（例如「讀一下 /fleet_states_json」會被當成檔案路徑）：沒通過時先看 `report.md` 裡那一次的工具呼叫與回答，分清楚是模式的差別、prompt 的問題，還是情境寫得不好。
- `prompt tokens` 是每次呼叫 Ollama 回報的完整 prompt 長度加總，KV cache 命中時仍算完整長度；要看 cache 效果看 `prompt 毫秒` 或 `perf_report.py`。

---

## Coding orchestrator 的評測（`run_coding_evals.py`）

改了 `agent_core/coding_*.py`、`_code_common.py`／`_cpp_common.py` 或程式技能腳本之後，先跑**離線自我測試**（假模型照劇本回答，不需要 Ollama）：

```bash
python3 evals/coding_selftest.py     # 12 個情境：規劃的修正、核准與修改計畫、worker 的內容通道、驗證與重試、停下來問、停止、重新啟動後接著做、
                                     # 技能腳本的各種保證（真的 pytest、.gitignore）、C／C++（真的 gtest：CMake、make、直接編譯；編譯錯誤、截斷的修改）、
                                     # 任務清單列出的檔案（計畫補項、worker 不能新建清單外的檔案）、整體驗證的修正變差就還原、
                                     # ROS 2 colcon 工作區（沒有 ROS 2：套件的 include、外部依賴與產生的標頭不算錯、-iquote、跨檔的命名空間、
                                     # 套件分開跑 gtest／pytest；job 的驗證跑不了時以靜態檢查為準、套件裡的相對路徑補成完整路徑）
python3 evals/main_selftest.py       # 主對話：卡住偵測、沒執行卻宣稱做完、相近路徑建議、兩階段揭露（驅動 Web 的回合迴圈）
python3 evals/web_ui_test.py         # Web 介面：無頭 Chrome 實際操作設定、送出、核准、diff、還原（需要 google-chrome）
```

測試一律用**真的 pytest 與 GoogleTest**（2026-10-08 起；原本沒有 pytest 時用的內建 runner 已移除）。這台機器的 pytest、cmake、ninja 裝在 `~/aiagent_venv_env/.venv`，GoogleTest 1.14 與 SQLite 裝在 `~/.local`（不需要 sudo，`code_test` 會自動找）。其他機器：`~/aiagent_venv_env/.venv/bin/pip install pytest cmake ninja`，GoogleTest 用 `sudo apt install -y libgtest-dev` 或從原始碼裝到 `~/.local`（見 `devbench/README.md`）。

它們測的是 harness 的流程與保證，不是模型的能力；模型的能力用下面的 `run_coding_evals.py` 與 `devbench/` 量。

同一組程式開發任務用指定的模型跑完整的 coding job（探索 → 規劃 → 自動核准 → worker 修改與驗證 → 整體驗證），結束後用 **hidden tests**（job 結束後才放進工作區、agent 從頭到尾看不到的測試）驗收：agent 自己寫的測試可能寫錯或寫得太鬆，不能拿來當唯一的標準。

```bash
python3 evals/run_coding_evals.py                                   # gemma4:e4b × 全部情境 × 1 次
python3 evals/run_coding_evals.py --model gemma4:26b --runs 2
python3 evals/run_coding_evals.py --model gemma4:e4b --planner gemma4:26b   # 規劃用 26b、worker 用 e4b
python3 evals/run_coding_evals.py --only rename_cross_file --keep    # --keep 保留臨時目錄（看 worker 的完整紀錄）
python3 evals/run_coding_evals.py --lang cpp                         # 只跑 C／C++ 的情境
```

每一次都在臨時目錄複製一份專案＋ fixture（`evals/coding_fixtures/<名稱>/`）當工作區，不碰正式的 `logs/`。結果在 `evals/results/<時間>_coding_<模型>/`：`report.md`（彙整表、每一項的嘗試次數與步數）、`runs.jsonl`（完整紀錄：事件流、diff、測試輸出）。

| 情境 | fixture | 要測的能力 |
|---|---|---|
| `feature_restock` | inventory_app | 同一個類別新增方法＋修改既有方法的行為＋測試 |
| `rename_cross_file` | inventory_app | 跨檔改名：方法改名、程式與測試裡所有使用處一起改＋CLI 新子指令 |
| `feature_csv_export` | inventory_app | 多檔功能：storage 新函式＋CLI 新子指令（照使用範例）＋測試 |
| `bugfix_textstats` | textstats_app | 除錯：測試失敗，找出 bug 修正程式，不能改測試 |
| `new_module` | inventory_app | 照規格建立新模組、使用既有類別、寫測試 |
| `long_category_feature` | inventory_app | 較長的跨檔功能：資料結構→商業邏輯→儲存（相容舊檔）→CLI→測試，5 個檔案 |
| `cpp_perimeter` | geometry_cpp（CMake＋gtest） | C++ 跨檔：介面加純虛擬方法、兩個子類別的標頭與實作、gtest 測試 |
| `cpp_triangle` | geometry_cpp | C++ 新類別：新標頭＋新實作＋解析器支援＋gtest 測試 |
| `cpp_bugfix_total` | geometry_cpp | C++ 除錯：從症狀（CLI 印出的總面積不對）找出 bug、修正、加回歸測試 |
| `c_ringbuf_api` | ringbuf_c（Makefile＋gtest） | C 新增 API：標頭宣告＋實作＋gtest（C++）測試 |
| `c_bugfix_mean` | ringbuf_c | C 除錯：環形緩衝區繞回後平均算錯 |
| `ros2_cpp_compose` | ros2_ws（colcon 工作區：ament_cmake 的 amr_utils＋ament_python 的 amr_tools；這台主機沒有 ROS 2） | ROS 2 C++ 套件：標頭＋實作新增函式（位姿合成）、gtest 測試；需要 rclcpp 的檔案只能檢查結構、測試跳過 |
| `ros2_cpp_bugfix_angle` | ros2_ws | ROS 2 C++ 除錯：從症狀（里程計的 theta 跑出範圍）找出角度正規化的 bug、修正、加回歸測試 |
| `ros2_py_battery` | ros2_ws | ROS 2 Python 套件：純 Python 模組新增函式＋改 rclpy 的 node（測不到，用 `contains` 檢查）＋pytest 測試；各套件的 linter 測試需要 ament_flake8，會跳過 |

檢查條件：`all_tests`（整個專案的測試，含 hidden tests；C／C++ 是建置後跑 gtest；ROS 2 工作區是每個套件分開跑，需要 ROS 2 的測試跳過）、`hidden_tests`、`unchanged`（不准改的檔案）、`absent`（改名後舊名稱不能再出現）、`contains`（改完的檔案要符合的正規表示式，給測不到的部分，例如 rclpy 的 node）。加情境：在 `coding_scenarios.py` 的 `SCENARIOS` 加一個 dict（fixture、task、hidden_tests…），hidden tests 先用一份參考解法確認「原本的 fixture 會失敗、參考解法會通過」。C／C++ 的 fixture 用 glob 收集測試檔（CMake 的 `file(GLOB … CONFIGURE_DEPENDS tests/*.cpp)`、Makefile 的 `$(wildcard tests/*.cpp)`），hidden test 放進 `tests/` 就會被建置。ROS 2 的 hidden test 放在套件的 `test/`，`code_test` 直接用 g++ 編譯（沒有 ROS 2 時不用 ament 的 CMake）。

### 「不用 harness」的對照組與穩健性情境（2026-10-08）

```bash
python3 evals/bare_coding_baseline.py --model gemma4:26b --runs 2      # 自建 14 個情境：同一個模型一次輸出要改的檔案，沒有工具與測試回饋
python3 evals/devbench/bare.py --model gemma4:26b                       # DevBench：一個檔案呼叫一次模型（--visible-tests：測試內容放進提示）
python3 evals/run_evals.py --suite robust --modes harness --runs 10     # 主對話的 5 個穩健性情境（路徑打錯、一直回同一個錯誤、宣稱完成、引號、docker 的誤用）
AGENT_ABLATE=turn_guard,path_suggest,rejoin,docker_hint python3 evals/run_evals.py --suite robust --modes harness --runs 10   # 把關全部關掉的對照組
AGENT_TURN_GUARD_RULE=v4 AGENT_ABLATE=docker_hint python3 evals/run_evals.py --suite robust --modes harness --runs 10        # v4 的卡住規則（第三次就停）
```

對照組回答的是「harness 比直接用同一個模型多做到多少」；結果與統計分析（信賴區間、配對比較）在 [`benchmark_study/`](../benchmark_study/README.md)，用 `benchmark_study/analysis/` 的程式從這裡的 `results/` 重新算。

## 公開 benchmark：DevBench（`devbench/`）

長任務的能力用 [DevBench](https://github.com/open-compass/DevEval) 的實作任務量：12 個 repo（Python 7、C++ 5），每個從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元與驗收測試計分（pytest、GoogleTest）。

```bash
python3 evals/devbench/prepare.py --verify       # 下載固定版本、建立 .venv、檢查 gtest、參考實作應該 116/116、51/51
python3 evals/devbench/run.py --model gemma4:26b
```

細節（選擇的理由、流程、分數怎麼看、授權）見 [`devbench/README.md`](devbench/README.md)。

主對話會不會把「改程式」交給 orchestrator、問程式問題會不會用看程式的技能，在原本的 `run_evals.py` 裡：`coding_route_modify`、`coding_route_question`。

## 公開 benchmark：SWE-bench 子集（`swebench/`，既有專案，2026-10-09）

DevBench 量的是「只給規格、從零寫」。日常更常見的是**在既有的專案裡照 issue 修正**：SWE-bench Verified（Python）16 題＋SWE-bench Multilingual
（C 4 題、C++ 4 題），共 24 題（抽樣與協定見 [`benchmark_study_2/datasets/swebench_subset/`](../benchmark_study_2/datasets/swebench_subset/README.md)）。

```bash
~/swebench_venv/bin/pip install swebench                  # 官方的計分套件（獨立的 venv，不裝進 harness 的環境）
python3 evals/swebench/evaluate.py --gold                 # 下載 24 個官方 Docker 映像（約 11 GB）、用參考解答驗證計分
python3 evals/swebench/run.py --model gemma4:26b          # harness（規劃與 worker 可以分開：--planner deepseek-r1:32b）
python3 evals/swebench/bare.py --model gemma4:26b         # 不用 harness：BM25 檢索相關檔案＋一次寫出修改
```

- `env.py`：每一題用官方映像起一個容器（不能連網路），工作區掛在容器裡同一個路徑；`python`／`pytest`／`make`／`cmake`／`gcc` 等同名的包裝指令
  用 `docker exec` 在容器裡執行，`CODE_PYTHON` 指向包裝目錄——harness 的測試、建置與編譯檢查就跑在題目的環境裡，harness 本身不用改。
- `tasks.py`：任務文字（issue 原文＋固定的要求）與工作區的開發環境說明（`.coding_agent.md`：怎麼建置、怎麼跑測試的通用格式）。
- `evaluate.py`：呼叫官方 swebench 套件計分（resolved＝評分用的 FAIL_TO_PASS 全部通過、PASS_TO_PASS 仍然全部通過）。
- 結果在 `evals/results/<時間>_swebench_<模型>/`：report.md、runs.jsonl、patches/<題目>.diff；分析與報告在 [`benchmark_study_2/`](../benchmark_study_2/README.md)。

