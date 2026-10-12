# benchmark_study_3：小而有測試的專案、非編碼的維運任務，與 harness v5

第三次評測（2026-10-10～11）。前兩次的評測與報告在 [`../benchmark_study/`](../benchmark_study/README.md)、[`../benchmark_study_2/`](../benchmark_study_2/README.md)，這次沒有改動它們。

這次依使用者的方向回答三件事：

1. **編碼任務集中在小而有測試的專案**（一次改 5～10 個檔案、人會審查），特別是「幫我寫測試、確認覆蓋率有沒有涵蓋到」：有沒有適合的資料集？
   目前的 harness 做得如何？Python 與 C++ 都要能擔任。
2. **非編碼的任務**（目錄與文件、Docker、ROS 2、調度系統的交握）也要有像編碼一樣的 orchestrator 與 worker：有沒有適合的資料集？做得如何？
3. **以 gemma4 系列為主**（26b、e4b）優化 harness：改版 v5，並跟 v4.2 比較。

## 結論

<!-- conclusions -->

## 先看哪個

| 檔案 | 給誰看 | 內容 |
|---|---|---|
| **`評估報告.md`**（`.pdf`） | 想知道結論的人 | 結論、能力判定、使用建議（哪種任務用哪個模型、人要看哪裡）、路線圖（從小專案走向單一 agent 與多 agent、做成技能） |
| **`技術報告.md`**（`.pdf`） | 想看證據的人 | 論文格式：研究問題、資料集的建法、v5 的改動、方法、全部的結果與統計、效度威脅、參考文獻 |
| `results/tables/*.md` | 想看細節的人 | 每個條件、每個領域、每一題的結果表 |

## 資料夾內容

```
benchmark_study_3/
├── 評估報告.md / .html / .pdf
├── 技術報告.md / .html / .pdf
├── datasets/
│   ├── README.md               兩組資料集的說明、來源與授權
│   ├── small_projects/         小專案 62 題：tasks/（任務說明）、workspaces/（工作區範本）、mutants/（突變體）、fe_specs.json、tools/（建題與計分）
│   ├── ops_suite/              非編碼 50＋20 個情境：scenarios.py、scenarios_holdout.py、fs_world.py（檔案沙盒）、checks.py（計分）、
│   │                           reference.py（參考解法與「什麼都不做」的驗證）、sandbox/（DinD 沙盒與 rmf_sim 調度系統模擬）
│   └── source/                 上游資料集的 clone（Aider polyglot、ProjectTest）
├── references/                 參考文獻：papers/（arXiv PDF）、web/（網頁的 HTML 與 PDF）、research_notes/（評測前的兩份網路調查）、README.md（書目）
├── results/
│   ├── raw/<版本>/             每一次評測的原始紀錄（runs.jsonl、report.md、小專案的 patches/）
│   ├── tables/                 整理後的表格（*.csv）與報告用的表（*.md）
│   ├── figures/                圖（SVG）
│   └── summary.json            analyze.py 算出來的全部統計
├── analysis/                   分析程式（只用 Python 標準庫）：gather_raw.py → collect.py → analyze.py → figures.py → build_reports.py
└── artifacts/                  評測用的 harness 快照與雜湊（v5；v4.2 在第二次研究）、模型與 Docker 映像的版本（README.md 有說明）
```

## 重新算出全部的表與圖

```bash
cd ~/Coding_agent_harness
PY=~/aiagent_venv_env/.venv/bin/python
$PY benchmark_study_3/analysis/gather_raw.py     # ~/cah_eval/{v4.2,v5} 的正式評測結果 → results/raw（已經收好就不用跑）
$PY benchmark_study_3/analysis/collect.py        # results/raw → results/tables/ops_runs.csv、sp_runs.csv
$PY benchmark_study_3/analysis/analyze.py        # → results/summary.json、results/tables/*.md
$PY benchmark_study_3/analysis/figures.py        # → results/figures/*.svg
$PY benchmark_study_3/analysis/build_reports.py  # 報告的 .html 與 .pdf（需要 google-chrome）
```

## 重跑實驗

評測程式在專案的 `evals/`：`evals/small_projects/run.py`（小專案）與 `evals/ops_suite/run.py`（非編碼；`--set holdout` 跑保留組）。
非編碼評測需要 Docker（沙盒是 `docker:27-dind`，第一次會建 rmf_sim 的映像）；兩者都需要 Ollama 上的 gemma4:26b／e4b。

```bash
cd ~/cah_eval/v5        # 凍結的副本（或專案目錄）
OLLAMA_HOST=127.0.0.1:11435 ~/aiagent_venv_env/.venv/bin/python evals/ops_suite/run.py --model gemma4:26b --tag v5_r1
OLLAMA_HOST=127.0.0.1:11435 ~/aiagent_venv_env/.venv/bin/python evals/small_projects/run.py --model gemma4:26b --family tw --tag v5_r1
```

資料集本身的驗證：`python3 datasets/ops_suite/reference.py --set all`（參考解法 70/70）與 `--null`（什麼都不做 70/70 不及格）；
`python3 datasets/small_projects/tools/score.py verify`（參考實作 56/56）。
