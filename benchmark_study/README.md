# benchmark_study：評測資料、參考文獻與技術報告

這個資料夾收齊了 2026-10 對 Coding_agent_harness 做的評測：用到的資料集、參考文獻、原始結果、分析程式，以及兩份報告。
目的是回答「這個 harness 能不能擔任大多數 coding 與長任務 coding 的角色」，並且讓每個數字都能追到原始紀錄、重新算出來。

## 結論（詳見《評估報告》）

- **日常修改任務**（有測試的專案，Python／C／C++／ROS 2）：可以交給它，要審查改動——14 個情境 37/37 通過，同一個模型直接寫 71～82%。
- **長任務、只給規格**：還不行——官方單元測試 10～24%、驗收 22～35%；失敗有 83% 是介面跟規格／測試不一致。
- **長任務、有測試可以對照**：單元測試 72～74%，是 harness 最強的工作方式。
- **用數據集測試之後有沒有變好**：找到並修好了 8 類真的問題，但 DevBench 的總分沒有可信的進步（同一版本重跑就差 13.8 個百分點）；非 coding 的把關主要省下重複的呼叫，針對性的修正（v4.1）讓目標情境從 5/10 提高到 9/10。

## 先看哪個

| 檔案 | 給誰看 | 內容 |
|---|---|---|
| **`評估報告.md`**（`.pdf`） | 想知道結論的人 | 正式的評估報告：能力結論、各類任務可不可以交給它、風險與使用建議、改進路線圖、後續評測計畫、名詞解釋 |
| **`技術報告.md`**（`.pdf`） | 想看證據的人 | 論文格式的技術報告：研究問題、方法、全部的實驗結果與統計、效度威脅、參考文獻 |
| `results/tables/*.md` | 想看細節的人 | 每一個實驗、每個 repo、每個情境的結果表 |

`.html` 與 `.pdf` 是從 `.md` 產生的（`python3 analysis/build_reports.py`）；要改內容請改 `.md`。

## 資料夾內容

```
benchmark_study/
├── 評估報告.md / .html / .pdf      正式的評估報告
├── 技術報告.md / .html / .pdf      論文格式的技術報告
├── datasets/                       測試用到的資料
│   ├── devbench_subset/            DevBench 的 12 個 repo（規格、參考實作、官方測試；CC BY 4.0／Apache 2.0，見 SOURCE.md）
│   ├── custom_coding_scenarios/    自建的 14 個 coding 情境：範例專案、scenarios.json、hidden_tests/
│   ├── main_session_scenarios/     主對話（非 coding）的 14＋5 個情境（scenarios.json）
│   └── toolchain/                  GoogleTest 1.14.0、SQLite 3.53.4 的原始碼與安裝方式（INSTALL.md）
├── references/                     參考文獻：papers/（arXiv PDF）、web/（網頁的 HTML 與 PDF）、devbench_source/、README.md（清單與網址）
├── results/
│   ├── raw/                        每一次評測的原始紀錄（runs.jsonl、report.md、agent 寫出來的程式 workspaces/）
│   ├── INDEX.md                    每個原始紀錄目錄屬於哪個實驗、版本、條件
│   ├── tables/                     整理後的表格（*.csv）與報告用的表（*.md）
│   ├── figures/                    圖（SVG）
│   └── summary.json                analyze.py 算出來的全部統計
├── analysis/                       分析程式（只用 Python 標準庫）
│   ├── experiments.json            結果目錄 → 實驗、版本、條件
│   ├── collect.py                  raw → tables/*.csv
│   ├── analyze.py                  統計（Wilson 區間、以 repo 為單位的 bootstrap、配對比較、符號檢定）→ summary.json、tables/*.md
│   ├── figures.py                  summary.json → figures/*.svg
│   └── build_reports.py            *.md → *.html → *.pdf（需要 google-chrome）
└── artifacts/                      評測版本的程式碼快照與雜湊：v4（1ff704a72cdc0733，E1～E6）、v4.1（aa7126a221887d1e，E7）
```

## 重新算出全部的表與圖

```bash
cd ~/Coding_agent_harness
PY=~/aiagent_venv_env/.venv/bin/python
$PY benchmark_study/analysis/collect.py        # results/raw → results/tables/*.csv
$PY benchmark_study/analysis/analyze.py        # → results/summary.json、results/tables/*.md
$PY benchmark_study/analysis/figures.py        # → results/figures/*.svg
$PY benchmark_study/analysis/build_reports.py  # 報告的 .html 與 .pdf
```

## 重跑實驗

實驗本身用的是專案裡的評測程式（`evals/`），結果寫到 `evals/results/`，再複製到這裡的 `results/raw/`：

```bash
PY=~/aiagent_venv_env/.venv/bin/python
$PY evals/devbench/prepare.py --verify                       # DevBench：下載、建環境、用參考實作驗證計分（12 個全部通過）
$PY evals/devbench/run.py --model gemma4:26b                  # E1：harness，官方測試看不到（約 1.5 小時）
$PY evals/devbench/run.py --model gemma4:26b --visible-tests  # E3：harness，官方測試在工作區
$PY evals/devbench/bare.py --model gemma4:26b                 # E2：不用 harness 的對照組
$PY evals/devbench/bare.py --model gemma4:26b --visible-tests # E3：不用 harness，測試內容放在提示裡
$PY evals/run_coding_evals.py --model gemma4:26b              # E4：自建 14 個情境，harness
$PY evals/bare_coding_baseline.py --model gemma4:26b --runs 2 # E4：不用 harness
$PY evals/run_evals.py --modes harness --runs 3               # E5：主對話 14 個情境
$PY evals/run_evals.py --suite robust --modes harness --runs 10                      # E7：穩健性，v4.1 把關開啟
AGENT_TURN_GUARD_RULE=v4 AGENT_ABLATE=docker_hint $PY evals/run_evals.py --suite robust --modes harness --runs 10   # v4 的規則（對照）
AGENT_ABLATE=turn_guard,path_suggest,rejoin,docker_hint $PY evals/run_evals.py --suite robust --modes harness --runs 10   # 把關全部關閉
```

需要：Ollama 與 gemma4:e4b／gemma4:26b、g++、GoogleTest（見 `datasets/toolchain/INSTALL.md`）。結果會因為模型的隨機性而不同，請比較多次的平均與信賴區間，不要只看一次。
