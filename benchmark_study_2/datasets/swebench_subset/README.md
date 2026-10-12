# SWE-bench 子集：既有專案的 issue 修正（24 題）

DevBench 量的是「只給規格、從零寫出整個專案」。這個子集量的是另一種、日常更常見的工作：**在既有的真實專案裡，照 issue 修正問題**。
題目來自 SWE-bench 家族——目前評估 coding agent 最常用的基準，每一題都是 GitHub 上真實的 issue 與修正它的 PR：

- **Python 16 題**：SWE-bench Verified（500 題，OpenAI 與 SWE-bench 團隊人工確認過題目描述清楚、評分測試合理）。
- **C 4 題、C++ 4 題**：SWE-bench Multilingual（300 題、9 種語言，SWE-bench 團隊 2025 年發布，跟 Verified 同樣的收集與人工篩選方式）。

## 為什麼是 24 題、怎麼抽

規模跟第一次研究的 DevBench 子集（12 個 repo）相當：每一題只有「解決／沒解決」，題數抓兩倍。抽樣規則事先寫好、不看題目內容（`select_tasks.py`，種子 20261009）：

- Python：專案配額大致照 Verified 的分布（django 6、sympy 2、sphinx 2、matplotlib／scikit-learn／astropy／xarray／pytest 各 1，
  其他小專案合併 1——抽到 flask），難度配額照 Verified 的人工標註（<15 分鐘 39%、15 分鐘～1 小時 52%、1 小時以上 9% → 6／8／2）。
- C／C++：redis 2、jq 1、micropython 1（C）；fmt 3、nlohmann/json 1（C++）。Multilingual 沒有難度標註。

另一個現成的選擇是 SWE-bench Verified mini（50 題），但它只有 django 與 sphinx 兩個專案、也沒有 C／C++，所以沒有採用。

| 檔案 | 內容 |
|---|---|
| `instances.json` | 24 題的完整資料（issue、base_commit、官方映像、評分腳本、評分測試、參考解答）；評測程式用的是 `evals/swebench/instances.json`（同一份） |
| `instances.md` | 題目清單：語言、專案、難度、評分測試的數量 |
| `select_tasks.py` | 抽樣程式（重跑會得到一樣的結果） |
| `source/` | 原始資料集（Verified 500 題、Multilingual 300 題、Verified mini 50 題），見 `SOURCE.md` |

## agent 拿到什麼、看不到什麼

- **任務文字**：issue 的原文（`problem_statement`）＋固定的要求（改原始碼解決問題、不要為了通過測試改既有測試、評分用另外的測試）。
  跟 SWE-bench 的標準設定一樣，不給 `hints_text`。
- **工作區**：repo 停在 `base_commit`（issue 回報時的版本），環境已經裝好（官方映像裡的 `/testbed`）。
- **開發環境說明**（工作區根目錄的 `.coding_agent.md`，harness 會讀這個檔案，相當於開發者寫的 AGENTS.md）：這個專案怎麼建置、怎麼跑測試
  的通用格式，例如 django 用 `python tests/runtests.py <測試模組>`、redis 用 `make` 與 `./runtest --single unit/<測試>`。例子刻意避開評分用的測試；
  文字在 `evals/swebench/tasks.py` 的 `HINTS`。
- **看不到**：評分用的測試（`test_patch`、`FAIL_TO_PASS`、`PASS_TO_PASS`）與參考解答。

## 執行環境

每一題用官方的 Docker 映像當「已經裝好的開發環境」，harness 本身不用改（`evals/swebench/env.py`）：

1. 從映像起一個容器（`--network none`，不能連網路），主機上的工作區掛在容器裡同一個路徑；映像裡的 `/testbed` 複製到工作區，
   editable install 的路徑也改到工作區——容器裡 import、建置、跑測試用的就是工作區的檔案。
2. `python`、`pytest`、`make`、`cmake`、`gcc`、`tclsh`… 同名的包裝指令用 `docker exec` 在容器裡、同一個工作目錄執行；
   `CODE_PYTHON` 指向包裝目錄，harness 的 code_test／code_run／code_check 會把它放在 PATH 最前面，所以測試與建置在題目的環境裡執行，
   讀寫檔案照常在主機上。
3. 結束時工作區相對於 `base_commit` 的改動（agent 新寫的原始檔也算；建置產物、二進位檔、`.coding_agent.md` 不算）就是 patch。

## 計分

官方的 `swebench` 套件（5.0.2）：patch 套到題目映像的新容器 → 執行題目的評分腳本（先換上 `test_patch` 的測試，再跑測試）→ 官方的 log parser
判斷每個測試的結果。**resolved**＝`FAIL_TO_PASS` 全部通過（issue 修好了）**而且** `PASS_TO_PASS` 全部仍然通過（沒有弄壞別的）。
參考解答（gold patch）24 題全部 resolved，證明計分環境正確（`evaluate.py --gold`，紀錄在 `results/raw/gold_check/`）。其中 fmt-1683 第一次是 P2P 22/42——同時有 harness 與 3 個平行計分在跑時，評分腳本 `set -x` 的追蹤行跟測試輸出交錯，結束標記早於後面 20 個測試的結果，官方的 log parser 就把它們算成沒通過；單獨重跑是 42/42。所以每一組結果都用同一條規則找出「結束標記之後還有測試結果」的題目，在機器空閒時單獨重新計分（`evals/swebench/recheck.py`，重新計分的題目在結果表裡有標記）。

不用 harness 的對照組（`evals/swebench/bare.py`）：同一個模型、同一個 issue，用 BM25 關鍵字檢索找出相關的原始檔放進提示（SWE-bench 論文的
RAG 基準作法），模型一次寫出修改（SEARCH/REPLACE 區塊）——沒有工具、不能建置或跑測試、沒有重試。

## 重跑

```bash
PY=~/aiagent_venv_env/.venv/bin/python
~/swebench_venv/bin/pip install swebench==5.0.2           # 計分用（獨立的 venv）
$PY evals/swebench/evaluate.py --gold                      # 下載映像、用參考解答驗證計分（24 題都要 resolved）
$PY evals/swebench/run.py --model gemma4:26b               # harness
$PY evals/swebench/run.py --model qwen2.5-coder:32b --planner deepseek-r1:32b
$PY evals/swebench/bare.py --model gemma4:26b              # 不用 harness
```
