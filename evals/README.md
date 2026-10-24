# 評測（evals）

評測依對象分成七組，外加每個階段結束時跑的總執行器（`phase_check.py`，見最後一節）。**不用模型**的自我測試（假的 `ollama.chat` 照劇本回答，或直接執行腳本，幾秒到一分多鐘）改程式之後先跑；**真模型／實機**的評測要 Ollama、容器或沙盒。
每一次都在臨時目錄複製一份專案來跑，不碰正式的 `logs/` 與 `prompts/Memory.md`（數據分析回歸例外：job 照常寫進正式的 `logs/analysis_jobs/`，評分從那裡讀）；結果寫到 `evals/results/`（已在 `.gitignore`）。

| 組 | 不用模型 | 真模型／實機 | 測什麼 |
|---|---|---|---|
| `chat/` 主對話 | `selftest.py`、`extract_selftest.py`（工具回傳的提煉與存檔回查） | `run.py`（情境在 `scenarios.py`，`worker.py` 跑一個情境）、`perf_report.py`（KV cache 分析） | 選技能、兩階段揭露、大量回傳與回存檔查、執行前確認、記憶、程式把關（卡住、說做了卻沒做、說要做卻沒動作）、模型設定、Web／CLI 的 `/workflow`、`task_run` 與 Plan 模式、對數據技能的路由；提煉的切段、核對、存檔、行號；兩種上下文模式比較 |
| `skills/` 技能腳本 | `selftest.py`（每一組一個 `<組>_test.py`：fs、containers、rmf、data） | —（主對話真的用技能看 `chat/`、`ops/`） | 每個技能直接執行：[PASS] 與每一種 [ERROR] 的寫法（原因與下一步）、截斷的說明、不讀標準輸入、逾時；需要容器的在沙盒裡跑，沒有就略過（規範：`doc/技能撰寫規範.md`） |
| `analysis/` 數據解析 | `selftest.py`（數據技能用錄下的真實輸出 `fixtures/`） | `regression.py`（回歸評分；數據分析全部由程式做，不需要 Ollama，要測試容器）、`tools_live.py`（在真的容器裡跑數據技能） | 事實的整理、重點、報告、主對話回答的核對；回歸評分只評事實 |
| `datagen/` 隨機情境的錄製產生器 | `check_facts.py`（只驗程式那一層，需要容器） | 產生的錄製交給 `analysis/regression.py` | 六個開發中套件的模擬，評分標準由注入的事件自動產生（見 [`datagen/README.md`](datagen/README.md)） |
| `ops/` 多步驟維運 | `selftest.py`（file_ops、維運技能的確認關卡） | `run.py`（情境在 `dataset/`，在 Docker-in-Docker 沙盒裡真的執行；`worker.py` 跑一個情境） | 主對話用技能、工作流、任務引擎做完維運任務；狀態、回覆、禁止動作由程式計分 |
| `task/` 任務引擎 | `selftest.py`（假模型、真的本機檔案技能） | —（真模型用 `ops/run.py`） | task_run 與 Plan 模式：規劃的程式檢查、先查再確認、worker 的權限、事實的核對、失敗後重排、工作流的步驟、存檔 |
| `integrity/` 評測的完整性 | `selftest.py` | — | 模型會讀的文字（prompt、技能說明、工作流、程式回給模型的字）沒有評測世界的名稱（從評測的來源自動取） |
| `extract/` 提煉 | —（不用模型的在 `chat/extract_selftest.py`） | `run.py`（情境在 `cases.py`：程式產生已知答案的長輸出；`worker.py` 跑一個情境） | 工具回傳的提煉與 result_recall：找到幾個、多列幾個、數量的說法、切幾段讀幾段、程式拿掉幾條 |
| `workflow/` 工作流 | `selftest.py`（規格驗證、跟 SKILLS.md 對得上、引號規則、推進、分支、【確認】、不用互動的入口、/make_skill） | `sandbox.py`（沙盒裡直接執行工作流，用維運情境計分；`sandbox_worker.py` 跑一個案例） | 程式照步驟推進、判斷點只填值與選分支、做完了沒由程式判斷 |

改程式之後先跑不用模型的自我測試：

```bash
PY=~/aiagent_venv_env/.venv/bin/python     # 有 ollama 套件的 Python
$PY evals/phase_check.py                   # 下面這幾組一次跑完、跟基準比（約 2 分鐘，見最後一節）
$PY evals/chat/selftest.py && $PY evals/chat/extract_selftest.py && $PY evals/analysis/selftest.py && $PY evals/ops/selftest.py \
  && $PY evals/task/selftest.py && $PY evals/workflow/selftest.py && $PY evals/integrity/selftest.py
$PY evals/skills/selftest.py               # 技能腳本（需要容器的情境沒有沙盒就略過）；只跑某幾組：selftest.py fs containers rmf data
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

結果在 `evals/results/<時間>[_<tag>]/`（已在 `.gitignore`）：

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
 "pseudo": {"analysis_run": "[PASS] 📊 ..."},      # 在 harness 裡執行的偽技能給固定的回傳（可省略）
 "guard": "deny",                                   # 執行前確認怎麼回答（預設 deny）
 "turns": [{"user": "使用者的話", "expect": {"tools_any": ["ROS2_topic_echo"], "reply_any": ["63.5"]}}]}
```

`expect` 可用的條件（全部成立才算這一句通過；情境的每一句都通過才算情境通過）：

| 條件 | 意思 |
|---|---|
| `reply_all`／`reply_any`／`reply_none` | 這一句回合裡模型所有的回答含有全部／任一／都不含這些字（不分大小寫） |
| `tools_all`／`tools_any`／`tools_none` | 這一句執行過全部／任一／都沒執行這些技能 |
| `args_any` | 工具呼叫的參數含有這些字之一（例如找到了正確的目錄） |
| `archive_lookup` | 有沒有用 `result_recall`／`result_grep`／`result_view`／`result_list` 回存檔查（True／False） |
| `archive_ids` | 回存檔查的參數裡包含這些編號 |
| `guard` | 有沒有觸發執行前確認 |
| `no_step_limit` | 沒有跑到 20 次的上限（True） |

### 讀報表要注意

- 次數少時差一兩次就是很大的百分比；結論請用 `--runs 5` 以上。
- 情境的問法本身也會影響結果（例如「讀一下 /fleet_states_json」會被當成檔案路徑）：沒通過時先看 `report.md` 裡那一次的工具呼叫與回答，分清楚是模式的差別、prompt 的問題，還是情境寫得不好。
- `prompt tokens` 是每次呼叫 Ollama 回報的完整 prompt 長度加總，KV cache 命中時仍算完整長度；要看 cache 效果看 `prompt 毫秒` 或 `chat/perf_report.py`。

### 穩健性情境（2026-10-08）

```bash
python3 evals/chat/run.py --suite robust --modes harness --runs 10     # 主對話的 5 個穩健性情境（檔名、目錄名稱打錯、一直回同一個錯誤、宣稱完成、引號）
AGENT_ABLATE=turn_guard,path_suggest,rejoin,docker_hint python3 evals/chat/run.py --suite robust --modes harness --runs 10   # 把關全部關掉的對照組
AGENT_TURN_GUARD_RULE=v4 AGENT_ABLATE=docker_hint python3 evals/chat/run.py --suite robust --modes harness --runs 10        # v4 的卡住規則（第三次就停）
```

把關開／關的對照（E6 消融實驗）的結果見〈設計筆記 2.12〉（完整的統計在 `~/Coding_agent_harness/benchmark_study/`）。

## 數據解析（`analysis/`、`datagen/`）

```bash
python3 evals/analysis/selftest.py          # 離線：數據技能用錄下的真實輸出（evals/analysis/fixtures/），主對話用假模型——11 組情境，幾秒鐘
docker start cah_analysis_test              # 測試容器（見 test_data/README.md）；用完 docker stop
python3 evals/analysis/tools_live.py --container cah_analysis_test \
    --data /workspace/experiment_logs/exp_5090_overheat [--record]   # 實機：五支數據技能（不需要 Ollama）
python3 evals/chat/run.py --modes harness --only analysis_route_diagnose,analysis_route_single_key,analysis_route_log   # 真模型：主對話的路由
python3 evals/analysis/regression.py --run --runs 2 --container cah_analysis_test --cases-file <cases.json> \
    [--data-root <容器內路徑>] --out evals/results/<名稱>   # 回歸評分（不呼叫模型，一份約 2 秒）
python3 evals/analysis/regression.py --score-file <runs.json> --out evals/results/<名稱>   # 只評分已經跑過的 job
python3 evals/phase_check.py --live --only analysis_regression   # 產生器 s1／s2／s3＋這台的實錄一次跑完，跟基準比
python3 evals/datagen/generate.py --set s2 --seed 2 --n 60      # 隨機情境的錄製＋評分標準（見 evals/datagen/README.md）
python3 evals/datagen/check_facts.py test_data/recordings/gen/s2/cases.json   # 產生的數據：只驗程式那一層（不呼叫模型）
```

- **`evals/analysis/selftest.py`** 測 harness 的程式把關：量測工具的特徵（發布方式由內容與時間判斷、只有固定頻率的才判斷中斷、尖峰不含雜訊與
  換了水準的地方、反覆切換只留頭尾、陣列只量長度）；事實的整理（T#／E# 每次一樣、同一則訊息的變化合成一個事件、時間線與前後 1 秒的對照、
  前後沒有任何變化的 Log、沒有量的 Topic）；報告（每個重要的時間點一則重點、那一刻全部的 Log 與事件、到最後跟開頭不同的值依 Topic 分組、
  指定的 Topic、不呼叫模型）；句子的意思（`agent_core/claims.py`：每一類誤擋都有放行與照樣擋的案例）；主對話依報告回答時把先後寫成因果
  或寫錯事實 → 提醒一次（之後的回合核對寫到報告的那幾行、`/clear` 之後不再對照）；dispatch、Web 的 `/analyze` 回合、CLI 的 `/analyze`（驅動真的 `cli.main()` 迴圈：
  `--data`、`--topic` 照原樣交給 analysis_run，跟 Web 同一套參數）；一次最多 3 分鐘、只有 Log 的錄製、
  拿掉的選項、設定檔只存改過的值；程式重新啟動時標成中斷；錄製的資料夾名稱。
  `evals/analysis/fixtures/` 是 `exp_5090_overheat` 錄下的 `mcap_analyzer --json`、`--facts --json`、`rosout_parser --json` 輸出；
  量測或輸出的格式改了就重錄一次（`SCAN_VERSION` 加一時一定要）。
- **`evals/analysis/tools_live.py`** 在真的容器裡跑：全域索引、Key 檢視、特徵量測（含寬鬆的時間寫法、不認識的參數、混了不存在的 Key 或「類別.Key」、
  `--where` 條件、JSON 字串的欄位當 Key）、原始值、錯誤處理、Log 去重、切片（`--signal`、`--window --topics --with-state`；寫到容器的 /tmp、
  測完刪掉；切片資料夾 `ros2 bag info` 讀得到）、`--record` 真的錄 6 秒。phase_check 用 `gen_s1_005` 與 `exp_5090_overheat` 兩份跑。
- **`evals/analysis/regression.py`**（回歸評分）：每份數據跑 N 次分析（job 照常寫進 `logs/analysis_jobs/<job>/`，評分只讀不改），依評分標準
  （`--cases-file`：預設 `evals/analysis/regression_cases.json` 是原作者的 6 份數據（`ros2_web_container`）；這台的 14 份用 `test_data/cases_5090.json`
  或 `test_data/tools/run_regression.py`，產生器的用 `test_data/recordings/gen/<組>/cases.json`）自動評分，只評事實：
  (a) 時間線有沒有該有的事件（時間±容許＋關鍵字）、(b) Topic 類別（該有、不該有的類別）、(c) 用詞（重點沒有原因、推測、這份數據不該有的
  說法）、(d) 時間有根據（重點寫的 +秒 對得上程式整理的事實）、(e) 重點涵蓋（標成 key 的事件，重點裡有沒有一則引用它）、沒有事件（steady：
  每個 Topic 都沒有事件）；另外列每份數據的平均秒數、同一份數據的事實有沒有不一致。報告全部由程式產生（2026-10-23 架構整合第 1 階段起，
  設計筆記 2.15〈九〉），(c)～(e) 檢查的是程式本身；以前模型寫說明與重點的 job 照樣評得了。評分標準沒有 (b)、(e) 的資料時那一欄是「—」；
  分析失敗的一次在適用的欄位都算沒過（不從分母裡消失）。全部由程式判，不需要人工標註。
  結果（`scorecard.md`、`scorecard.json`、`runs.json`）寫到 `--out`——請都給 `evals/results/…`：沒給時的預設是 `evals/analysis/results/analysis_<時間>/`，
  不在 `.gitignore`。第九輪以前的根因評分在 `doc/archive/root_cause_reference/evals/`。換機器時把 `test_data/recordings/` 複製到那台的數據根目錄（或 `--data-root`）。
- **產物穩定性與報告的時間**：`test_data/tools/stability.py <runs.json>`（同一份數據 N 次：程式產物、事件、重點是否每次相同）、
  `test_data/tools/fact_check.py <runs.json>`（報告裡的每個 +秒 對 ground truth，只用在這台錄的 14 份）；phase_check 的實錄組兩支都會跑。
- 這台錄的 14 份數據、ground truth 與評分標準在 `test_data/`（不進 git，見 `test_data/README.md`）。
- **大量數據的穩定度**：隨機情境的錄製產生器 `evals/datagen/`（六個套件的模擬，評分標準由注入的事件自動產生，見 `evals/datagen/README.md`）。

## 多步驟維運（`ops/`）

```bash
python3 evals/ops/selftest.py                                   # 離線：file_ops、維運技能的確認關卡（任務引擎在 evals/task/selftest.py）
python3 evals/ops/run.py --model gemma4:26b                     # 真模型：50 個情境（fs 12、docker 10、ros2 10、handshake 10、complex 8）
python3 evals/ops/run.py --set holdout --model gemma4:26b       # 20 個保留情境（開發時沒有看過）；--set all＝兩者 70 個（phase_check 用這個）
python3 evals/ops/run.py --only hs_lost_fin_fix --tag try1      # 只跑一個情境（--domain handshake,complex 只跑某幾類）
```

- 情境、沙盒與計分在 `ops/dataset/`（`scenarios.py`、`scenarios_holdout.py`、`checks.py`、`fs_world.py`、`sandbox/`）。
- 每個情境：沙盒重建（Docker-in-Docker 容器 `cah_ops_dind`，`127.0.0.1:23750`；裡面跑 `rmf_sim` 的機器人行為與預設工作包、新的檔案沙盒）
  → 記下開始時的狀態 → 在臨時的 harness 副本裡跑主對話（工具都真的執行；`DOCKER_HOST` 指到沙盒，碰不到主機上真的容器）→ 讀回最後的狀態
  → `checks.py` 計分（狀態＋回覆＋禁止動作）。第一次跑會建沙盒的映像檔；跑完沙盒容器留著，不用時 `docker stop cah_ops_dind`。
- 回覆裡的量測值用 `reply_num_any` 計分：數字加單位、在容許範圍內就算對（例如 2 Hz ±0.05、0.5 秒 ±0.02），技能量得比較精確
  （1.997 Hz）不會被當錯；目前只有 `ros_hz` 用。沙盒的 `rmf_sim` 2026-10-23 改得跟真系統一樣（訊息型別、distribute 的快照沒有電量、
  電量在 `/<機器人>/robot_state`），`sandbox.py` 依整個 `rmf_sim/` 目錄的內容判斷要不要重建映像檔。
- 結果在 `evals/results/<時間>_ops[_holdout|_all]_<模型>[_<tag>]/`：`runs.jsonl`、`report.md`，以及每個情境 harness 副本的 `logs/<情境>/`（`task_jobs/`：任務引擎每一版計畫、每一步與每一次模型呼叫；提煉的切段與模型呼叫、工具的完整原文、`perf.jsonl`——事後查得到每一步做了什麼）。
  `runs.jsonl` 每一回合的 `task_jobs` 記這一回合的任務（每一版計畫、每一步的狀態、worker 的工具呼叫與核對過的事實）。2026-10-10 建立這組評測時的報告與統計（基準的 `reference_v5`）在 `~/Coding_agent_harness/benchmark_study_3/`。

## 任務引擎（`task/`）

```bash
python3 evals/task/selftest.py      # 離線（約 10 秒）：假模型照劇本回答，worker 用真的本機檔案技能（view_file、file_ops、list_dir）
```

測 harness 的程式把關（模型能力用 `ops/run.py` 量）：規劃的程式檢查與修正（技能不存在、會改變狀態的標記、查詢的步驟不用檢查、
停著的容器排在啟動之前、使用者提到手冊卻沒有先讀、要寫檔卻沒列 file_ops）；做不了的計畫不執行；第一步就要改時確認關卡是整份計畫；**先查再確認**（開頭的查詢直接做 → 照事實重排 →
停下來 → harness 用 `take_task_continuation` 接著問）；worker 的權限（沒核准的 [DENIED]、這一步不能用的技能）與重試；**事實的核對**
（名稱與數值要在引用的 #編號 的輸出裡——這一步的、或這個任務前面各步的（讀回存檔），對不上的交回改一次、還是不行就拿掉）；失敗後重排（Plan 模式不重排）；工作流的步驟；Plan 模式的
草稿、指令、用說的改、核准後照計畫做；存檔與保留上限。CLI 與 Web 的回合（確認卡片、y/n）在 `chat/selftest.py`。

## 評測的完整性（`integrity/`）

```bash
python3 evals/integrity/selftest.py   # 離線（幾秒）
```

模型會讀的文字——`prompts/`（長期記憶除外）、`SKILLS.md`、技能規格、工作流、`agent_core/` 與技能腳本回給模型的字串（docstring 與註解不算）——
不能有評測世界獨有的名稱：機器人、工作包、站點與語意名稱、容器、映像、檔案沙盒的路徑、設定名稱、錯誤碼、數據的編號，**從評測的來源自動取**
（`ops/dataset/`、`chat/scenarios.py`、`workflow/sandbox.py`），新增情境不用改它；調度系統本身的協定名稱（distribute、threshold_recovery_sec…）
與 `/opt/ros` 不算。2026-10-24 加的：範例正好是評測的答案時（`file_ops` 的範例＝fs_edit_param、`mcap_slicer` 的 `--at +15.5`＝主對話評測要的 15.5），
評測量到的是會不會抄範例。

## 提煉（`extract/`）

```bash
python3 evals/extract/run.py --model gemma4:26b                  # 5 個情境 × 1 次，約 1 分鐘
python3 evals/extract/run.py --model gemma4:e4b --runs 3 --only fleet_80,recall_fleet_120
```

- 情境（`cases.py`，亂數種子固定，每次產生一樣的輸出——第 2 階段驗證用的就是這幾份）：`fleet_40`（7,416 字，一段就放得下，一次寫完）、
  `fleet_80`（小模型一次讀會漏、切 2 段）、`fleet_120`（22,124 字、切 3 段）——問「電量低於 40% 的車」，答案 7／21／30 台；
  `log_200k`（3,000 行約 20 萬字的 Log，planner 的 6 筆錯誤散在中段，切 26 段、依問題挑 8 段讀）；`recall_fleet_120`（同一份車隊輸出提煉一次後，
  用 result_recall 追問提煉沒寫到的「L2 樓層而且 IDLE 的車」，11 台）；`robot_heading`（2026-10-24 加：維運評測 ros_moving 那一次
  ROS2_topic_echo 的真實輸出 `fixtures/robot_state_moving.txt`，問「有在移動嗎？往哪裡走？」，要答出要去的站 a7——答案不在數值變化裡，
  那一次的提煉只寫了座標往哪個方向增加）。
- 評分：名稱和值在同一行才算找到（fleet），多列的名稱、回答裡「共 N 台」的數量要對；另外記模式（一次寫完／切段）、段數與讀了幾段、模型呼叫次數、
  程式核對拿掉幾條、整合有沒有修正、秒數。每一次的提煉存檔（`logs/extract_jobs/<編號>/`）留在結果目錄的 `logs/<情境>_<第幾次>/`。
- 2026-10-23 的基準：26b 全對（8～14 秒）；e4b 前四個全對，recall_fleet_120 9/11（worker 漏一台、整合時拿掉一台）。

## 工作流（`workflow/`）

```bash
python3 evals/workflow/selftest.py                               # 離線（假模型、假技能，幾秒鐘）
python3 evals/workflow/sandbox.py --model gemma4:26b              # 沙盒裡直接執行每一個工作流（不經過主對話），約 2 分鐘
python3 evals/workflow/sandbox.py --model gemma4:e4b --only wf_config_edit --runs 3
AGENT_WORKFLOWS=0 python3 evals/ops/run.py --only cx_fin_and_note --tag nowf     # 主對話「沒有工作流」的對照
```

- 離線：`skills_system/workflows/` 每一份都驗證得過（腳本存在、分支往後、dependencies 與 changes_state 一致）、跟 SKILLS.md〈工作流〉對得上；
  值放進命令的引號規則（file_ops 解析回來一字不差）；完成訊號遺失的整條路（程式選分支、判斷點只填機器人與紀錄、成功判準程式跑）、
  其他原因提早結束、選填略過、判斷點填不出值就停、[ERROR] 時改一次值、【確認】停下來與 `--continue`（接著做時前面步驟的輸出從存檔讀回原文）、比不出分支時交給模型、參數與確認關卡、
  dispatch 的接法、/make_skill 產生工作流。
- 離線也測 `/workflow`（`agent_core/workflow_cmd.py`）：列出、看步驟；不用互動的入口沒給 `--yes` 不執行會改變狀態的、結束碼
  （完成／提早結束 0、沒有完成 1、停在【確認】2、要核准 3、沒有執行 4）、`--continue`、命令列參數；報告不交給提煉（程式整理好的報告直接進主對話）；
  `Agent_Runner.py --workflow` 真的當成一個行程跑（`OLLAMA_HOST` 指到沒有服務的位址，證明不需要模型）。
  Web 與 CLI 的 `/workflow`（確認卡片／y、n，核准才改、拒絕不改，報告完整進主對話）在 `chat/selftest.py` 的 `t_workflow_web`、`t_workflow_cli`。
- 沙盒：`CASES` 每一個案例用一個維運情境的世界與檢查（回覆＝工作流的報告），另外核對工作流結束的狀態（完成／提早結束）；
  `checks_only` 只算跟這個工作流有關的檢查（禁止動作照樣全部算）。執行走不用互動的入口（`workflow_cmd.run_headless … yes`＝
  `Agent_Runner.py --workflow … --yes`，之後心跳定期跑工作流的同一條路）。結果在 `evals/results/<時間>_workflow_sandbox_<模型>[_<tag>]/`，
  每一次的 job（判斷點的模型呼叫）在 `logs/<案例>_<第幾次>/`。phase_check 的 `--model` 會跑 26b、e4b 各 2 次（`workflow`）。

## 持續驗證：每個階段結束時（`phase_check.py`）

```bash
python3 evals/phase_check.py                  # 離線（約 1～2 分鐘）：六組自我測試
python3 evals/phase_check.py --live           # 再加上要容器／沙盒、不呼叫模型的（約 15 分鐘）：調度技能接沙盒、容器技能接開發用沙盒、
                                              #   數據技能接測試容器、數據技能實機、數據分析回歸（產生器 s1／s2／s3、實錄 ×2）
python3 evals/phase_check.py --live --model   # 再加上真模型（約 1 小時）：提煉（26b、e4b）、主對話（e4b 11 個情境 ×3）、
                                              #   工作流沙盒（26b、e4b 各 7 個案例 ×2）、維運（26b 70 個）
python3 evals/phase_check.py --model --only ops,extract     # 只跑某幾項（名稱見下面）；--no-offline 不跑離線的
python3 evals/phase_check.py --compare <結果目錄…>          # 不跑，只拿已經跑好的結果跟基準比
python3 evals/phase_check.py --save-baseline <結果目錄…> --label "第 N 階段（<commit>）" [--only <項目>]   # 階段 commit 之後更新基準
```

- `--only` 的名稱：離線 `skills`、`chat_selftest`、`extract_selftest`、`ops_selftest`、`task_selftest`、`analysis_selftest`、`workflow_selftest`、`integrity`；
  `--live` 的 `skills_sandbox`、`containers_sandbox`、`data_live`、`tools_live`、`analysis_regression`；`--model` 的 `extract`、`chat`、`workflow`、`ops`。
  `--save-baseline` 的 `--only` 用 summary.md 第一欄括號裡的名稱，有冒號的取冒號前面（`analysis`、`tools_live`、`extract`、`workflow`），見 [`baselines/README.md`](baselines/README.md)。
- 跟 `evals/baselines/` 逐項比（怎麼比、什麼時候更新見 [`baselines/README.md`](baselines/README.md)），結果在
  `evals/results/<時間>_phase_check/summary.md`：每一項一行（結果、基準、判定 ✅／⚠️／❌），要注意的逐項列出——沒過的測試、比基準差的情境、
  禁止動作、變慢超過 2 倍的情境。
- 容器與沙盒用完就關（`cah_ops_dind`、`cah_dev_dind`、`cah_analysis_test`）；`logs/analysis_settings.json` 測試前後比對，有變就還原。
- 近期加進來的案例：第 2 階段——提煉的真模型評測（〈提煉〉一節）、交握 status 連續幾次的判斷（`skills/rmf_test.py` 的 `t_sandbox_status_stable`）、
  數據技能的「不是錄製數據」判斷不擋任何一份真的錄製（`skills/data_test.py` 的 `t_not_recording_real_data`）、維運評測的 `logs/<情境>/`
  （每一步的紀錄）；第 3 階段——工作流的自我測試（`workflow_selftest`）與沙盒測試（`workflow:<模型>`）；第 4 階段——評測的完整性（`integrity`）、
  任務引擎與 Plan 模式（`task_selftest`；CLI／Web 的回合在 `chat_selftest`）、數據分析的存檔只留最近幾次（`analysis_selftest`）。
