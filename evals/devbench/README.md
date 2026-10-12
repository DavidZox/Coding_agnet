# DevBench 評測（實作任務，Python＋C++）

用公開的 benchmark 驗證 coding orchestrator 的「長任務」能力：每個 repo 從**規格文件**（PRD、UML 類別圖與循序圖、架構設計）寫出**整個專案**（2～11 個檔案、160～670 行），再用**官方的單元測試與驗收測試**計分——Python 用 pytest、C++ 用 GoogleTest 與官方的驗收腳本。agent 從頭到尾看不到官方測試。

- 來源：[DevBench](https://github.com/open-compass/DevEval)（Li et al., *DevBench: A Comprehensive Benchmark for Software Development*, [arXiv:2403.08604](https://arxiv.org/abs/2403.08604)）。資料以 **CC BY 4.0** 授權、程式碼 Apache 2.0；這裡不放資料本身，`prepare.py` 會從 GitHub 下載。
- 版本固定在 DevEval 的 commit `bb593c1f`（2024-05-30），每個檔案都用 git blob SHA-1 驗證，內容跟這個版本一模一樣（`repos.py`）。

## 為什麼選它、選哪些

長任務 coding 的 benchmark 大多太大（SWE-bench 系列要 Docker 映像、幾百 GB）、或只有 Python。DevBench 的實作任務剛好是「照規格從零做出一個多檔案專案」，有 Python 與 C／C++、測試是現成的 pytest／gtest、每個 repo 只有幾十 KB，在這台機器幾分鐘就能跑完一個。

| 選了 | 語言 | 單元測試 | 驗收測試 |
|---|---|---|---|
| readtime、particle-swarm-optimization、chakin、stocktrends、geotext、hone、lice | Python | 57 | 24 |
| area_calculation、graph-cpp、logistic_system、people_management、xlsx2csv | C++ | 59 | 27 |

沒選的：Hybrid_Images（參考實作的單元測試在這個環境本身就有 8 個失敗）、ArXiv_digest（驗收測試要連 arXiv 網站）、TextCNN（要 PyTorch 與實際訓練）；Java／JavaScript 的 repo 不在這個 harness 的範圍。

## 怎麼跑

```bash
cd ~/Coding_agent_harness
~/aiagent_venv_env/.venv/bin/python evals/devbench/prepare.py --verify      # 下載（約 7 MB）、建立 .venv、檢查 gtest、用參考實作驗證計分
~/aiagent_venv_env/.venv/bin/python evals/devbench/run.py                     # gemma4:e4b × 12 個 repo
~/aiagent_venv_env/.venv/bin/python evals/devbench/run.py --model gemma4:26b
~/aiagent_venv_env/.venv/bin/python evals/devbench/run.py --model gemma4:e4b --planner gemma4:26b --only readtime,area_calculation --keep
~/aiagent_venv_env/.venv/bin/python evals/devbench/run.py --model gemma4:26b --visible-tests   # 官方測試放在工作區（DevBench 基準 agent 的設定）
```

`prepare.py --verify` 的結果應該是 12 個 repo 全部 ✅（單元 116/116、驗收 51/51）——這表示環境（pytest、gtest、SQLite）與計分方式都對，之後 agent 的分數才有意義。

需要的工具：g++／gcc、make、GoogleTest、SQLite（people_management）。這台機器已經裝好（gtest 1.14 與 SQLite 裝在 `~/.local`，pytest、cmake、ninja 在 `~/aiagent_venv_env/.venv`）。其他機器缺的話：

```bash
sudo apt install -y build-essential libgtest-dev libsqlite3-dev cmake
```

不想用 sudo：googletest 從原始碼裝到 `~/.local`（`cmake -S googletest-1.14.0 -B build -DCMAKE_INSTALL_PREFIX=$HOME/.local && cmake --build build -j && cmake --install build`），harness 的 `code_test` 與這裡的計分都會自動找 `~/.local`（環境變數 `CODE_CPP_PREFIX` 可以改）。

## 流程（每個 repo）

1. 在臨時目錄複製一份 harness（`agent_core`、`skills_system`、`coding_agents`…），工作區只放規格文件與 `required_files`（資料檔、第三方程式庫、C++ 的 `makefile_test`）——跟 DevBench 實作任務給模型的一樣。
2. 送出 coding job（自動核准、某一項失敗就跳過）：任務文字列出規格文件的路徑，以及依 `code_file_DAG` 排好順序的「要寫的檔案」。任務提到的文件會整份附給規劃與每個 worker（`task_documents`），worker 的驗證會對照規格裡的函式簽名（`code_check --spec`）。Python 測試用 `.venv` 的直譯器（`CODE_PYTHON`）。
3. job 結束後：官方測試目錄換掉 agent 自己寫的同名目錄、`required_files` 換回原本的（agent 可能改過）、照 `setup_shell_script.sh` 建目錄，然後：
   - Python：`pytest <unit_tests>`、`pytest <acceptance_tests>`，數通過的測試；
   - C++：`make -B -f makefile_test test`（數 gtest 的 `[       OK ]`，跑到一半當掉時前面通過的也算）、`acceptance_tests/test.sh`（數通過的標記）或 people_management 的 pytest 驗收測試。
4. 結果寫到 `evals/results/<時間>_devbench_<模型>/`：`report.md`（彙整）、`runs.jsonl`（計畫、每一項的嘗試與步數、事件流、測試輸出）、`workspaces/<repo>/`（agent 寫的程式，可以直接看）。

## 跟 DevBench 基準 agent 的差別

DevBench 自己的基準 agent（DevEval 的 `agent_system/baseline`，ChatDev 改的）在實作階段開始時，`prepare_required_files` 會把**官方的單元與驗收測試目錄複製進工作區**，`--review execution` 時再把官方測試的執行結果回饋給模型；另外依架構設計的檔案樹先建立空檔案（所以 `__init__.py` 這類不在 DAG 裡的檔案一開始就存在）。這裡的預設比它嚴格：

| | 這裡（預設） | `--visible-tests` | DevBench 基準 agent |
|---|---|---|---|
| 官方測試 | agent 看不到，job 結束才放進去計分 | 放在工作區，agent 可以用 `code_test` 跑 | 放在工作區；execution 模式回饋測試結果 |
| 不在 DAG 裡的原始檔（`__init__.py`、makefile） | agent 照架構設計自己建立 | 同左 | 依檔案樹先建空檔 |
| 資料檔（不在 `required_files` 的，例如 geotext 的城市資料） | 不提供 | 不提供 | 不提供 |
| 計分 | 官方測試換回原本的版本再跑 | 同左（agent 改過測試也沒用） | 在工作區直接跑 |

預設模式量的是「只看規格能寫多準」（跟 hidden tests 的精神一樣）；`--visible-tests` 量的是「有現成測試時能修到多好」，比較接近平常在既有專案裡工作的情況。

## 分數怎麼看

- 主要指標：單元測試與驗收測試的**通過率**（DevBench 實作任務的指標）。報告同時列總數、每個 repo 通過率的平均、依程式碼行數加權的平均（論文用最後這個）。
- DevEval README 的實作任務結果（全部 22 個 repo、四種語言、依行數加權）：GPT-4-Turbo-0125 驗收 7.1%／單元 8.0%、GPT-3.5-Turbo 4.2%／4.3%、DeepSeek-Coder-33B 4.4%／5.5%。子集、agent、執行回饋都不一樣，**不能直接比**，只能當「這個任務有多難」的量級參考。
- 這個子集同時被拿來找 harness 的問題（例如規劃把範例指令抄進別的專案、驗證指令指向不存在的測試、簽名跟規格不符），改完重跑會偏樂觀；要比較模型或改動，請固定版本重跑全部 12 個。
