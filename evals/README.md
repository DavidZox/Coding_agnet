# 評測（evals）

評測依對象分成四組。每組都有一支**不用模型**的自我測試（假的 `ollama.chat` 照劇本回答，幾秒到一分鐘，改程式之後先跑）與**真模型**的評測。
每一次都在臨時目錄複製一份專案來跑，不碰正式的 `logs/` 與 `prompts/Memory.md`；結果寫到 `evals/results/`（已在 `.gitignore`）。

| 組 | 不用模型 | 真模型 | 測什麼 |
|---|---|---|---|
| `chat/` 主對話 | `selftest.py` | `run.py`（情境在 `scenarios.py`，`worker.py` 跑一個情境）、`perf_report.py`（KV cache 分析） | 選技能、兩階段揭露、大量回傳與回存檔查、執行前確認、記憶、程式把關、對數據技能的路由；兩種上下文模式比較 |
| `analysis/` 數據解析 | `selftest.py`（數據技能用錄下的真實輸出 `fixtures/`） | `regression.py`（評分標準 `regression_cases.json`；數據分析全部由程式做，不需要 Ollama）、`tools_live.py`（在真的容器裡跑數據技能） | 事實的整理、重點、報告、主對話回答的核對；回歸評分只評事實 |
| `datagen/` 隨機情境的錄製產生器 | `check_facts.py`（只驗程式那一層，需要容器） | 產生的錄製交給 `analysis/regression.py` | 六個開發中套件的模擬，評分標準由注入的事件自動產生（見 [`datagen/README.md`](datagen/README.md)） |
| `ops/` 多步驟維運 | `selftest.py` | `run.py`（情境在 `dataset/`，在 Docker-in-Docker 沙盒裡真的執行；`worker.py` 跑一個情境） | ops_plan／ops_run、file_ops、維運技能的確認關卡 |

改程式之後先跑三支不用模型的自我測試：

```bash
PY=~/aiagent_venv_env/.venv/bin/python     # 有 ollama 套件的 Python
$PY evals/chat/selftest.py && $PY evals/analysis/selftest.py && $PY evals/ops/selftest.py
```

## 主對話（`chat/`）

同一組情境分別用 **harness** 與 **claude_code** 兩種上下文模式跑（模式的差別見〈[架構說明 1.1](../doc/架構說明.md#11-兩種上下文模式context_mode-harnessclaude_code)〉），比較成功率、模型呼叫次數、token 與時間。改了 `prompts/AGENT.md`、`prompts/context_modes/`、門檻或切換邏輯之後重跑一次，跟上一次的報表比，才知道是變好還是變壞；4B 模型對 prompt 很敏感，改一條規則可能讓另一個行為退化。

### 怎麼跑

```bash
python3 evals/chat/run.py                  # 兩種模式 × 全部情境 × 1 次
python3 evals/chat/run.py --runs 5         # 每個組合跑 5 次（temperature 0.2 仍有隨機性，要比較請用 ≥5 次）
python3 evals/chat/run.py --modes claude_code --only fleet_battery,fleet_followup
python3 evals/chat/run.py --fake           # 假模型：幾秒鐘，只驗證評測流程本身能跑
python3 evals/chat/perf_report.py evals/results/<時間>/runs.jsonl   # 這次評測的 KV cache 分析
python3 evals/chat/perf_report.py                # 平常使用 CLI／Web 累積的 logs/perf.jsonl
```

需要本機 Ollama 與 `gemma4:e4b`（`--model` 可換）。評測期間不要同時開 CLI／Web：同一個模型只有一個 slot，會互相排隊、也會互相洗掉 KV cache，時間數字就不準了。

結果在 `evals/results/<時間>/`（已在 `.gitignore`）：

- `report.md`：各模式總覽、各情境的通過次數與沒通過的條件、每一次的最後回答與工具呼叫。
- `runs.jsonl`：每一次的完整紀錄，含每一步的 thought／reply／action、每個工具呼叫、每次模型呼叫的 token 與毫秒。

### 怎麼運作

- 每一次都在臨時目錄複製一份專案（`agent_core`、`skills_system`、`prompts`、`evals`），在副本裡跑，**不會動到正式的 `logs/` 與 `prompts/Memory.md`**。
- 外部世界（docker、ROS2、調度系統）一律用 `chat/scenarios.py` 裡的假輸出，結果可重現；存檔工具（`result_*`）、`modify_memory`、本機檔案類技能（ls、cat、grep、find、cd）在副本裡真的執行。沒準備假資料的腳本會回 `[ERROR]`。
- 流程比照 CLI 的 auto 模式：工具結果自動加入、連續執行到模型不再下 action，每一句使用者訊息最多 20 次模型回覆。執行前確認（派工單等）依情境的 `guard` 自動回答 approve／deny。

### 情境

| 情境 | 要測的行為 |
|---|---|
| analysis_route_diagnose | 問「為什麼、什麼時候恢復」：要用 analysis_run（程式整理的事實報告），依報告回答（analysis_run 用固定的報告代替） |
| analysis_route_single_key | 只問一個 Topic 的一個數值：直接用 mcap_feature_measure，不派 analysis_run |
| analysis_route_log | 問 Log 裡有哪些警告：用 rosout_parser，不派 analysis_run |
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

### 加一個情境

在 `chat/scenarios.py` 的 `SCENARIOS` 加一個 dict：

```python
{"id": "my_case", "desc": "要測的行為",
 "state": {"target_container": "rmf_sim"},          # 開始前的狀態（可省略）
 "seeds": [SOME_ARCHIVE],                           # 預先放好的舊存檔（可省略）
 "memory": "...",                                   # 取代 prompts/Memory.md（可省略）
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

### 讀報表要注意

- 次數少時差一兩次就是很大的百分比；結論請用 `--runs 5` 以上。
- 情境的問法本身也會影響結果（例如「讀一下 /fleet_states_json」會被當成檔案路徑）：沒通過時先看 `report.md` 裡那一次的工具呼叫與回答，分清楚是模式的差別、prompt 的問題，還是情境寫得不好。
- `prompt tokens` 是每次呼叫 Ollama 回報的完整 prompt 長度加總，KV cache 命中時仍算完整長度；要看 cache 效果看 `prompt 毫秒` 或 `chat/perf_report.py`。

### 穩健性情境（2026-10-08）

```bash
python3 evals/chat/run.py --suite robust --modes harness --runs 10     # 主對話的 5 個穩健性情境（路徑打錯、一直回同一個錯誤、宣稱完成、引號、docker 的誤用）
AGENT_ABLATE=turn_guard,path_suggest,rejoin,docker_hint python3 evals/chat/run.py --suite robust --modes harness --runs 10   # 把關全部關掉的對照組
AGENT_TURN_GUARD_RULE=v4 AGENT_ABLATE=docker_hint python3 evals/chat/run.py --suite robust --modes harness --runs 10        # v4 的卡住規則（第三次就停）
```

把關開／關的對照（E6 消融實驗）的結果見〈設計筆記 2.12〉（完整的統計在 `~/Coding_agent_harness/benchmark_study/`）。

## 數據解析（`analysis/`、`datagen/`）

```bash
python3 evals/analysis/selftest.py          # 離線：數據技能用錄下的真實輸出（evals/analysis/fixtures/），主對話用假模型——10 組情境，約半分鐘
python3 evals/analysis/tools_live.py --container ros2_web_container \
    --data /workspace/app/diagnostics_package/toolkit/experiment_logs/exp_20261014_084506 [--record]   # 實機：五支數據技能（不需要 Ollama）
python3 evals/chat/run.py --modes harness --only analysis_route_diagnose,analysis_route_single_key,analysis_route_log   # 真模型：主對話的路由
python3 evals/analysis/regression.py --run --runs 2 [--cases-file <cases.json>] [--data-root <容器內路徑>]   # 回歸評分（不呼叫模型，一份約 2 秒）
python3 evals/analysis/regression.py --score-file <runs.json>   # 只評分已經跑過的 job
python3 evals/datagen/generate.py --set s2 --seed 2 --n 60      # 隨機情境的錄製＋評分標準（見 evals/datagen/README.md）
python3 evals/datagen/check_facts.py test_data/recordings/gen/s2/cases.json   # 產生的數據：只驗程式那一層（不呼叫模型）
```

- **`evals/analysis/selftest.py`** 測 harness 的程式把關：量測工具的特徵（發布方式由內容與時間判斷、只有固定頻率的才判斷中斷、尖峰不含雜訊與
  換了水準的地方、反覆切換只留頭尾、陣列只量長度）；事實的整理（T#／E# 每次一樣、同一則訊息的變化合成一個事件、時間線與前後 1 秒的對照、
  前後沒有任何變化的 Log、沒有量的 Topic）；報告（每個重要的時間點一則重點、那一刻全部的 Log 與事件、到最後跟開頭不同的值依 Topic 分組、
  指定的 Topic、不呼叫模型）；句子的意思（`agent_core/claims.py`：每一類誤擋都有放行與照樣擋的案例）；主對話依報告回答時把先後寫成因果
  或寫錯事實 → 提醒一次（之後的回合核對寫到報告的那幾行、`/clear` 之後不再對照）；dispatch 與 Web 的回合；一次最多 3 分鐘、只有 Log 的錄製、
  拿掉的選項、設定檔只存改過的值；程式重新啟動時標成中斷；錄製的資料夾名稱。
  `evals/analysis/fixtures/` 是 `exp_5090_overheat` 錄下的 `mcap_analyzer --json`、`--facts --json`、`rosout_parser --json` 輸出；
  量測或輸出的格式改了就重錄一次（`SCAN_VERSION` 加一時一定要）。
- **`evals/analysis/tools_live.py`** 在真的容器裡跑：全域索引、Key 檢視、特徵量測（含寬鬆的時間寫法、不認識的參數、混了不存在的 Key 或「類別.Key」）、原始值、錯誤處理、Log 去重、
  切片（寫到容器的 /tmp、測完刪掉；切片資料夾 `ros2 bag info` 讀得到）、`--record` 真的錄 6 秒。
- **`evals/analysis/regression.py`**（回歸評分，另一個方法——原本的產物照舊產生、照舊保留，評分只讀 `logs/analysis_jobs/<job>/` 不改）：
  每份數據各跑 N 次，依評分標準（`--cases-file`；預設 `evals/analysis/regression_cases.json`，這台的 14 份數據用 `test_data/cases_5090.json`
  ——或經 `test_data/tools/run_regression.py`——，產生器的用 `test_data/recordings/gen/<組>/cases.json`）自動評分，只評事實：
  (a) 時間線有沒有該有的事件（時間±容許＋關鍵字）、(b) Topic 類別（該有、不該有的類別）、(c) 用詞（重點沒有原因、推測、這份數據不該有的
  說法）、(d) 時間有根據（重點寫的 +秒 對得上程式整理的事實）、(e) 重點涵蓋（標成 key 的事件，重點裡有沒有一則引用它）、沒有事件（steady：
  每個 Topic 都沒有事件）；另外列每份數據的平均秒數、同一份數據的事實與重點有沒有不一致。2026-10-23 起報告全部由程式產生，(c)～(e) 檢查的是
  程式本身；2026-10-22 以前的 job（模型寫說明與重點）照樣評得了。評分標準沒有 (b)、(e) 的資料時那一欄是「—」；分析失敗的一次在適用的欄位都算沒過（不從分母裡消失）。
  全部由程式判，不需要人工標註。
  結果在 `evals/results/analysis_<時間>/scorecard.md`（`--out` 可以指定）。第九輪以前的根因評分在 `doc/archive/root_cause_reference/evals/`。
  換機器時把 `test_data/recordings/` 複製到那台的數據根目錄（或 `--data-root`）。
- **三個版本的比較**（`evals/analysis/ablation.py`，2026-10-22～23）：只有程式／只呼叫一次模型／三個角色，讀者只看報告答題（261／261／257 題）；
  比完決定報告全部由程式產生，工具已經拿掉，結果在 `evals/results/ablation_r12d/`、設計筆記 2.15〈七〉。
- **產物穩定性與報告的時間**：`test_data/tools/stability.py <runs.json>`（同一份數據 N 次：程式產物、事件、重點是否每次相同；以前的 job
  另有計畫、worker、重點的交回與救回）、`test_data/tools/fact_check.py <runs.json>`（報告裡的每個 +秒 對 ground truth，只用在這台錄的 14 份）。
- **實機事件測試**（2026-10-15）的錄製、ground truth、每次分析與對照結果在 `test_data/`（見 `test_data/README.md`）。
- **大量數據的穩定度**：隨機情境的錄製產生器 `evals/datagen/`（六個套件的模擬，評分標準由注入的事件自動產生，見 `evals/datagen/README.md`）。

## 多步驟維運（`ops/`）

```bash
python3 evals/ops/selftest.py                                   # 離線：規劃檢查、確認關卡、[DENIED]、重試、file_ops、維運技能的確認關卡（8 項）
python3 evals/ops/run.py --model gemma4:26b                     # 真模型：50 個情境（fs 12、docker 10、ros2 10、handshake 10、complex 8）
python3 evals/ops/run.py --set holdout --model gemma4:26b       # 20 個保留情境（開發時沒有看過）
python3 evals/ops/run.py --only hs_lost_fin_fix --tag try1      # 只跑一個情境
```

- 情境、沙盒與計分在 `ops/dataset/`（`scenarios.py`、`scenarios_holdout.py`、`checks.py`、`fs_world.py`、`sandbox/`）。
- 每個情境：沙盒重建（Docker-in-Docker 容器 `cah_ops_dind`，`127.0.0.1:23750`；裡面跑 `rmf_sim` 的機器人行為與預設工作包、新的檔案沙盒）
  → 記下開始時的狀態 → 在臨時的 harness 副本裡跑主對話（工具都真的執行；`DOCKER_HOST` 指到沙盒，碰不到主機上真的容器）→ 讀回最後的狀態
  → `checks.py` 計分（狀態＋回覆＋禁止動作）。第一次跑會建沙盒的映像檔；跑完沙盒容器留著，不用時 `docker stop cah_ops_dind`。
- 結果在 `evals/results/<時間>_ops_<模型>[_<tag>]/`：`runs.jsonl`、`report.md`。2026-10-10 建立這組評測時的報告與統計在 `~/Coding_agent_harness/benchmark_study_3/`。
