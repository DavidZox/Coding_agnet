# 原始紀錄的索引

`raw/<目錄>/` 是評測輸出（`evals/results/`）的副本：`runs.jsonl`（每一次的完整紀錄）、`report.md`（當時的報表）；DevBench 另有 `workspaces/<repo>/`（agent 寫出來的程式），SWE-bench 另有 `patches/<題目>.diff`（agent 的修改）與 `official_eval/<題目>/`（官方計分的紀錄：report.json、test_output.txt）。由 `analysis/collect.py` 產生。

| 目錄 | 基準 | 實驗 | 條件 | harness 版本 | 紀錄數 | 備註 |
|---|---|---|---|---|---|---|
| 20261009_022117_devbench_qwen2.5-coder-32b_plan-deepseek-r1-32b | DevBench |  | harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker | v4.1 | 12 |  |
| 20261009_041551_devbench_qwen2.5-coder-32b | DevBench |  | harness：Qwen2.5-Coder-32B | v4.1 | 12 |  |
| 20261009_053445_swebench_gemma4-26b | SWE-bench 子集 |  | harness：gemma4:26b | v4.1 | 21 | v4.1 跑到第 21 題後停掉：harness 的 C++ 大綱掃描器在 7 題的內附大型標頭上災難性回溯（見技術報告 5.x）。受影響的 7 題用修正後的 v4.1.1 重跑（目錄名稱含 _v411-affected）；這 7 題在 v4.1 的結果（4 題跑完、3 題沒跑完）另外列成「v4.1（C++ 掃描器 bug）」做修正前後的比較。其餘 17 題的程式路徑跟 v4.1.1 完全相同（沒有觸發的檔案），直接沿用。 |
| 20261009_132618_swebench-bare_qwen2.5-coder-32b | SWE-bench 子集 |  | 不用 harness：Qwen2.5-Coder-32B | v4.1 | 24 |  |
| 20261009_135925_swebench-bare_gemma4-26b | SWE-bench 子集 |  | 不用 harness：gemma4:26b | v4.1 | 24 |  |
| 20261009_140903_swebench_gemma4-26b_v411-affected | SWE-bench 子集 |  | harness：gemma4:26b | v4.1.1 | 7 | v411-affected |
| 20261009_150711_devbench_gemma4-26b | DevBench |  | harness：gemma4:26b | v4.1 | 12 |  |
| 20261009_160003_devbench-bare_qwen2.5-coder-32b | DevBench |  | 不用 harness：Qwen2.5-Coder-32B | v4.1 | 12 |  |
| 20261009_161224_devbench_qwen2.5-coder-32b_plan-deepseek-r1-32b | DevBench |  | harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker | v4.1 | 12 |  |
| 20261009_194309_swebench_qwen2.5-coder-32b_plan-deepseek-r1-32b | SWE-bench 子集 |  | harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker | v4.1.1 | 24 | R1 規劃（AGENT_CODING_THINK=1）＋Qwen worker，24 題全部用修正 C++ 掃描器之後的 v4.1.1。 |
| 20261010_000803_swebench_gemma4-26b_v42 | SWE-bench 子集 |  | harness：gemma4:26b（v4.2） | v4.2 | 24 | v42 |
| 20261010_014225_devbench_gemma4-26b | DevBench |  | harness：gemma4:26b（v4.2） | v4.2 | 12 |  |
| 20261010_023106_devbench_qwen2.5-coder-32b | DevBench |  | harness：Qwen2.5-Coder-32B（v4.2） | v4.2 | 12 |  |
