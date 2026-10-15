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
| analysis_route_diagnose | 問「為什麼、什麼時候恢復」：要用 analysis_run（多 agent 數據診斷），依報告回答（analysis_run 用固定的報告代替） |
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

## 數據解析的評測（2026-10-14）

```bash
python3 evals/analysis_selftest.py          # 離線：假模型照劇本回答、數據技能用錄下的真實輸出（analysis_fixtures/）——7 個情境，幾秒
python3 evals/analysis_tools_live.py --container ros2_web_container \
    --data /workspace/app/diagnostics_package/toolkit/experiment_logs/exp_20261014_084506 [--record]   # 實機：五支數據技能（不需要 Ollama）
python3 evals/run_evals.py --modes harness --only analysis_route_diagnose,analysis_route_single_key,analysis_route_log   # 真模型：主對話的路由
```

- **`analysis_selftest.py`** 測 harness 的程式把關：Orchestrator 的計畫檢查與修正（不存在的 L#／Topic、Log Topic、重複的 Topic）、補指派、
  時間窗（前後秒數、合併、限制在數據範圍內）、worker 的規則（reply 裡的動作、`--topic` 固定、只准量測技能、第三次相同的量測擋下、系統代選 Key）、
  局部報告的 Frontmatter 數字來自程式、Synthesizer 壞掉的退路、dispatch 與 Web 的回合。`analysis_fixtures/` 是從 `exp_20261014_084506`
  錄下的 `mcap_analyzer --json`、`rosout_parser --json`、`mcap_feature_measure` 輸出；換了 Key 的分類或輸出格式時重錄一次（指令見 `analysis_tools_live.py` 的說明）。
- **`analysis_tools_live.py`** 在真的容器裡跑：全域索引、Key 檢視、特徵量測（含寬鬆的時間寫法與不認識的參數）、原始值、錯誤處理、Log 去重、
  切片（寫到容器的 /tmp、測完刪掉）、`--record` 真的錄 6 秒。
- **報告的品質**（根因對不對）目前只能人工看：`/analyze <問題>` 跑一次，看 `logs/analysis_jobs/<編號>/report.md` 與各 worker 的局部報告；
  建「已知根因」的錄製當評測資料是待辦（`doc/待辦清單.md`）。

多步驟維運任務（ops_run）的離線自我測試是 `v5_selftest.py`；真模型、在 Docker-in-Docker 沙盒裡真的執行的維運情境在 `ops_suite/`
（資料集與結果見 `benchmark_study_3/`）。coding 的評測（`run_coding_evals.py`、`coding_selftest.py`、`web_ui_test.py`、DevBench、SWE-bench）
在 2026-10-14 隨 coding agent 移到 `/home/david/Coding_agent_harness/evals/`。

### 穩健性情境（2026-10-08）

```bash
python3 evals/run_evals.py --suite robust --modes harness --runs 10     # 主對話的 5 個穩健性情境（路徑打錯、一直回同一個錯誤、宣稱完成、引號、docker 的誤用）
AGENT_ABLATE=turn_guard,path_suggest,rejoin,docker_hint python3 evals/run_evals.py --suite robust --modes harness --runs 10   # 把關全部關掉的對照組
AGENT_TURN_GUARD_RULE=v4 AGENT_ABLATE=docker_hint python3 evals/run_evals.py --suite robust --modes harness --runs 10        # v4 的卡住規則（第三次就停）
```

把關開／關的對照（E6 消融實驗）與統計分析在 [`benchmark_study/`](../benchmark_study/README.md)。
