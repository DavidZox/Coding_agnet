# artifacts：評測用的程式版本、模型與 Docker 映像

評測不直接跑專案目錄，而是跑凍結的副本（`~/cah_eval/<版本>/`），評測期間在專案目錄做的修改不會影響結果。這裡保存每一份副本的快照與雜湊，以及模型與映像的 digest，讓結果可以對應到確切的版本。

## harness 的版本

| 檔案 | 版本 | agent 程式的雜湊 | 用在 |
|---|---|---|---|
| `harness_snapshot_v4.1_eval.tar.gz` | v4.1（第一次研究的最後版本） | 5b37b79521737866 | E8 DevBench 全部；E9 SWE-bench gemma4:26b 沒有觸發 C++ 掃描器 bug 的 17 題；兩個「不用 harness」的對照組 |
| `harness_snapshot_v4.1.1_eval.tar.gz` | v4.1.1＝v4.1＋C++ 掃描器的一行修正 | ed861606750f20b1 | E9 SWE-bench：gemma4:26b 受影響的 7 題、R1＋Qwen 全部 24 題 |
| `harness_snapshot_v4.2_eval.tar.gz` | v4.2＝v4.1.1＋既有專案的四個修正＋每個角色的模型與 thinking 開關 | 6436be794225c705 | E10 |

**agent 程式的雜湊**：只算 agent 的行為會用到的檔案（`agent_core/`、`skills_system/`、`coding_agents/`、`context_modes/`、`web_app/`、`AGENT.md` 底下的 .py／.md／.html），不含評測程式（`evals/`）與文件。算法：

```bash
find agent_core skills_system coding_agents context_modes web_app AGENT.md -type f \( -name "*.py" -o -name "*.md" -o -name "*.html" \) \
  -not -path "*/__pycache__/*" | sort | xargs sha256sum | sha256sum | cut -c1-16
```

v4.1 的雜湊跟第一次研究的 v4.1 快照（`../../benchmark_study/artifacts/harness_snapshot_v4.1_20261008_1954.tar.gz`）用同樣的算法算出來完全相同。第一次研究的雜湊（aa7126a221887d1e）用的是另一種算法（範圍較大），所以數字不同。

**快照的內容**：凍結副本的全部檔案（含 `evals/` 的評測程式），不含 `logs/`、`evals/results/`（結果在 `../results/raw/`）、DevBench 的資料與虛擬環境（由 `evals/devbench/prepare.py` 產生）。

**評測程式在評測期間的修改**（agent 程式都沒有變）：

- `evals/swebench/bare.py`：第一次執行的解析器太嚴格，跑了 2 題後停掉（`_aborted`），改成沿用前一個區塊的路徑、比對方式跟 harness 的 code_edit 一樣，整組重跑。
- `evals/swebench/run.py`：加上 `salvage_job`——job 程序被逾時結束時，從 job 的 state.json／events.jsonl 撈回已經做的事（紀錄裡標 `"salvaged": true`）。只影響紀錄的完整度，不影響 patch 與計分。

快照裡的評測程式是最後的版本。

## 模型（`ollama_models.json`）

四個模型都是 Ollama 預設的 Q4_K_M 量化；digest 可以用 `ollama show --modelfile <模型>` 或 `curl 127.0.0.1:11434/api/tags` 核對。

| 模型 | 參數 | 架構 |
|---|---|---|
| gemma4:26b | 25.2B（MoE，每個 token 約用 4B） | gemma4 |
| qwen2.5-coder:32b（Qwen2.5-Coder-32B-Instruct） | 32.8B（dense） | qwen2 |
| deepseek-r1:32b（DeepSeek-R1-Distill-Qwen-32B） | 32.8B（dense） | qwen2 |
| gemma4:e4b | 7.5B | gemma4（只用在主對話的 thinking 實測） |

評測用的 Ollama：`OLLAMA_HOST=127.0.0.1:11435 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve`（技術報告 4.4 節）。

## SWE-bench 的 Docker 映像（`docker_images.txt`）

24 題各一個官方的評測映像（`swebench/sweb.eval.x86_64.<題目>:latest`），欄位：映像名稱、digest、ID、大小（共用的層只算一次，實際佔磁碟約 25 GB）。agent 執行時用它當開發環境，官方計分也用它。
