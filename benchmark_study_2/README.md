# benchmark_study_2：既有專案的評測、模型組合（DeepSeek-R1＋Qwen2.5-Coder）與 thinking 設定

第二次評測（2026-10-09）。第一次的評測與報告在 [`../benchmark_study/`](../benchmark_study/README.md)，這次沒有改動它們。

這次回答三件事：

1. **既有專案**：DevBench 量的是「只給規格、從零寫出整個專案」。在既有的真實專案裡照 issue 修正（SWE-bench 的 24 題子集，Python／C／C++），
   harness 行不行？
2. **換成「coding 很強」的模型**：DeepSeek-R1（32B 蒸餾版）規劃＋Qwen2.5-Coder-32B worker，在 DevBench 與 SWE-bench 子集上，跟 gemma4:26b 比如何？
   規劃者換成會思考的 R1 有沒有幫助（對照：Qwen 自己規劃）？
3. **規劃階段的 self-refine** 值不值得加進框架（文獻＋這次的數據）。

另外根據這次的發現改了 harness（v4.1.1、v4.2），並重測一次。

## 結論

1. **既有專案**：
   - 小而有測試的專案可行（第一次研究）。
   - 大型真實專案的 issue：harness 解決 7～8/24（29～33%），同一個模型直接寫 6/24（25%），沒有可信的差別。
   - harness 比較能找到該改的檔案（18/24 對 12/24），但改對的沒有比較多，自己的驗證也不可信。
2. **R1＋Qwen 沒有比較好**：
   - DevBench 明顯比 gemma4:26b 差（單元測試 3.0% 對 14.7%，p=0.016），每個 repo 慢 3.6 倍。
   - SWE-bench 差不多（8/24 對 7/24）。
   - 主因是 harness 的寫檔協議跟 Qwen 的習慣不合（11～16% 的呼叫在空轉）；R1 當規劃者也沒有幫助。
3. **thinking**：deepseek-r1:32b 關不掉；gemma4:26b 在簡單問答上開了沒有變準、慢很多。建議預設關閉，規劃可以試開。
4. **規劃的 self-refine**：做「用程式檢查計畫、把具體的問題交回規劃者改一次」，不做「請模型自己再想一次」。依使用者的指示，等測試結束後再實作。
5. **改版**：
   - v4.1.1 修正了 C++ 掃描器的災難性回溯。
   - v4.2 修正了大型檔案的修改視窗、測試指令與範圍、改動大小、空轉的提示。機制都有效：SEARCH 對不上少了 76%，每題時間減半。
   - 但分數沒有可信的變化（SWE-bench 仍是 7/24）。
   - v4.2 也暴露出下一個要修的問題：有的驗證一個測試都沒跑到，卻判定通過。
6. **Web Console**：主對話、Coding 規劃、Coding worker 可以分別設定模型與 thinking 開關。

詳細的數字與建議見兩份報告。

## 先看哪個

| 檔案 | 給誰看 | 內容 |
|---|---|---|
| **`評估報告.md`**（`.pdf`） | 想知道結論的人 | 結論、模型與 thinking 的使用建議、Gemini 建議的逐項檢查、self-refine 的評估、路線圖 |
| **`技術報告.md`**（`.pdf`） | 想看證據的人 | 論文格式：研究問題、方法、全部的結果與統計、效度威脅、參考文獻 |
| `results/tables/*.md` | 想看細節的人 | 每個條件、每個 repo、每一題的結果表 |

## 資料夾內容

```
benchmark_study_2/
├── 評估報告.md / .html / .pdf
├── 技術報告.md / .html / .pdf
├── datasets/
│   ├── swebench_subset/        SWE-bench 子集 24 題：instances.json、抽樣程式、原始資料集、來源與授權（SOURCE.md）、評測協定（README.md）
│   └── devbench_subset/        指向第一次研究的 DevBench 資料（同一份 12 個 repo）
├── references/                 參考文獻：papers/（arXiv PDF）、web/（網頁的 HTML 與 PDF）、README.md（書目與連結）
├── results/
│   ├── raw/                    每一次評測的原始紀錄（runs.jsonl、report.md、DevBench 的 workspaces/、SWE-bench 的 patches/ 與官方計分紀錄）
│   ├── INDEX.md                每個原始紀錄目錄屬於哪個實驗、條件
│   ├── tables/                 整理後的表格（*.csv）與報告用的表（*.md）
│   ├── figures/                圖（SVG）
│   └── summary.json            analyze.py 算出來的全部統計
├── analysis/                   分析程式（只用 Python 標準庫）：gather_raw.py → collect.py → analyze.py → figures.py → build_reports.py；
│                               experiments.json（需要補充說明或排除的結果目錄）、think_probe.py（thinking 的實測）
└── artifacts/                  評測用的 harness 快照與雜湊（v4.1、v4.1.1、v4.2）、模型的 digest、Docker 映像的 digest（README.md 有說明）
```

## 重新算出全部的表與圖

```bash
cd ~/Coding_agent_harness
PY=~/aiagent_venv_env/.venv/bin/python
$PY benchmark_study_2/analysis/gather_raw.py     # ~/cah_eval 的評測結果與官方計分紀錄 → results/raw（已經收好就不用跑）
$PY benchmark_study_2/analysis/collect.py        # results/raw（＋第一次研究的 gemma 結果）→ results/tables/*.csv
$PY benchmark_study_2/analysis/analyze.py        # → results/summary.json、results/tables/*.md
$PY benchmark_study_2/analysis/figures.py        # → results/figures/*.svg
$PY benchmark_study_2/analysis/build_reports.py  # 報告的 .html 與 .pdf（需要 google-chrome）
```

## 重跑實驗

評測程式在專案的 `evals/`：`evals/devbench/`（從規格從零寫）與 `evals/swebench/`（既有專案，這次新增）。

```bash
PY=~/aiagent_venv_env/.venv/bin/python
# 32B 模型＋Isaac Sim 同時在跑時，用 KV cache q8_0 的 Ollama 才放得進 GPU（見技術報告 4.4）
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve &
export OLLAMA_HOST=127.0.0.1:11435
# E8：DevBench
AGENT_CODING_THINK=1 $PY evals/devbench/run.py --model qwen2.5-coder:32b --planner deepseek-r1:32b --timeout 7200
$PY evals/devbench/run.py --model qwen2.5-coder:32b --timeout 7200
$PY evals/devbench/run.py --model gemma4:26b --timeout 7200
$PY evals/devbench/bare.py --model qwen2.5-coder:32b
# E9：SWE-bench 子集（先 pip install swebench 到 ~/swebench_venv；第一次會下載約 11 GB 的映像）
$PY evals/swebench/evaluate.py --gold
$PY evals/swebench/run.py --model gemma4:26b
AGENT_CODING_THINK=1 $PY evals/swebench/run.py --model qwen2.5-coder:32b --planner deepseek-r1:32b
$PY evals/swebench/bare.py --model gemma4:26b
$PY evals/swebench/bare.py --model qwen2.5-coder:32b
$PY evals/swebench/recheck.py --rescore <結果目錄>   # 檢查計分紀錄有沒有被輸出交錯弄亂（技術報告 5.1）
# E10：v4.2（目前的專案目錄就是 v4.2）
$PY evals/swebench/run.py --model gemma4:26b --tag v42
$PY evals/devbench/run.py --model gemma4:26b --timeout 7200
$PY evals/devbench/run.py --model qwen2.5-coder:32b --timeout 7200
```

評測時跑的是凍結的副本（`~/cah_eval/<版本>/`，`artifacts/` 有快照），`run.py` 的結果寫在副本的 `evals/results/`，再由 `gather_raw.py` 收進 `results/raw/`。
