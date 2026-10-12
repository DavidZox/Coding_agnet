# artifacts：評測用的程式版本、模型與 Docker 映像

評測不直接跑專案目錄，而是跑凍結的副本（`~/cah_eval/<版本>/`），評測期間在專案目錄做的修改不會影響結果。這裡保存副本的快照與雜湊、
模型與映像的版本，讓結果可以對應到確切的版本。

## harness 的版本

| 檔案 | 版本 | agent 程式的雜湊 | 說明 |
|---|---|---|---|
| （`../../benchmark_study_2/artifacts/harness_snapshot_v4.2_eval.tar.gz`） | v4.2（第二次研究的最後版本，對照組） | 6436be794225c705 | 這次沒有改它的 agent 程式 |
| `harness_snapshot_v5_eval.tar.gz` | v5（這次的改版） | 703c9cc4b5f7d821 | 2026-10-10 14:29 凍結 |

**agent 程式的雜湊**：只算 agent 的行為會用到的檔案（`agent_core/`、`skills_system/`、`coding_agents/`、`ops_agents/`、`context_modes/`、
`web_app/`、`AGENT.md` 底下的 .py／.md／.html），不含評測程式（`evals/`）與文件。v5 新增了 `ops_agents/`；v4.2 沒有這個目錄，用同一個算法
算出來仍是 6436be794225c705（跟第二次研究一致）。

```bash
find agent_core skills_system coding_agents ops_agents context_modes web_app AGENT.md -type f \( -name "*.py" -o -name "*.md" -o -name "*.html" \) \
  -not -path "*/__pycache__/*" 2>/dev/null | sort | xargs sha256sum | sha256sum | cut -c1-16
```

**快照的內容**：凍結副本的全部檔案（含 `evals/` 的評測程式），不含 `logs/`、`evals/results/`（結果在 `../results/raw/`）、DevBench 的資料與
虛擬環境（兩個版本都用符號連結指向 `~/Coding_agent_harness/evals/devbench/` 的同一份）。兩個版本的 `Memory.md` 內容相同。

**評測程式（evals/）在兩個副本裡相同**：`evals/ops_suite/` 的 run.py 與 worker.py 在 v4.2 的第一次執行（26b、e4b 各一次，2026-10-10 11:26～12:07）
之後換成新版，兩個版本之後的執行都用新版。差別只在紀錄：(1) 模型呼叫數不再受 `agent.perf_calls` 只留 200 筆的限制（v4.2 那兩次沒有任何情境
超過 200 次呼叫，結果相同）；(2) 記下 v5 的 ops 計畫；(3) 加了 `--set holdout`。舊版保存在 `v4.2_ops_*_driver_before_sync.py`。

**計分程式**（`../datasets/`，兩個版本共用一份）在評測期間的修改：
- `small_projects/tools/score.py`：突變體改用建立時的節點／token 編號套用（以前只用行號＋描述，同一行有兩個相同的突變點時會套錯位置）；
  官方測試在計分程序裡抓不到的突變體標成 `unstable` 不計分（xlsx2csv 1 個）；TW 的測試結果分開記「失敗」與「跳過／預期失敗（xfail）」。
  這些都在小專案的正式執行開始之前改好。
- `ops_suite/scenarios.py`：回覆的同義說法補齊——「機器人沒有回應授權」（`NO_REPLY`，原本漏了「未收到任何授權回覆」）、「機器人回 no」（`REPLIED_NO`，原本漏了「回覆了「no」」「收到 10 則 no」）。`analysis/collect.py`
  用目前的情境定義重算所有紀錄的「回覆」類檢查（兩個版本一起），狀態類的檢查沿用評測當時的結果。
- `ops_suite/sandbox/sandbox.py`：每個情境開始前，除了刪掉容器，也刪掉 agent 拉下來的映像（例如 `docker run ubuntu` 拉的 ubuntu:latest）。
  從 v5 的第一次 26b 執行之後才生效；之前的執行裡，v4.2 的 dk_create_box 拉了 ubuntu:latest，之後的情境沙盒裡多一個映像（只有列出映像時看得到）。

## 模型（`ollama_models.json`）

評測專用的 Ollama（127.0.0.1:11435，預設設定、KEEP_ALIVE 30 分鐘；版本 0.34.4），兩個模型：

| 模型 | 參數 | 量化 | digest（前 12 碼） |
|---|---|---|---|
| gemma4:26b | 25.2B（MoE，每個 token 約用 4B） | Q4_K_M | 001e5dafc3c7 |
| gemma4:e4b | 7.5B（含 embedding；有效約 4B） | Q4_K_M | dc35e8d9c606 |

## Docker 映像（`docker_images.txt`）

沙盒的 DinD（`docker:27-dind`）與裡面的映像：`ros:jazzy-ros-base`（rmf_sim 的基底）、`ubuntu:24.04`（一般容器）、`cahtest/rmf_sim:jazzy`
（`../datasets/ops_suite/sandbox/rmf_sim/` 建出來的，標籤記著原始碼的雜湊，原始碼一改就重建）。
