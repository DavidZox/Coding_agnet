# 原始紀錄的索引

`raw/<目錄>/` 是 `evals/results/` 的副本：`runs.jsonl`（每一次的完整紀錄）、`report.md`（當時的報表）、DevBench 另有 `workspaces/<repo>/`（agent 寫出來的程式）。由 `analysis/collect.py` 依 `analysis/experiments.json` 產生。

| 目錄 | 基準 | 實驗 | 版本 | 模型 | 條件 | 紀錄數 | 備註 |
|---|---|---|---|---|---|---|---|
| 20260927_022823 | 主對話 | E5 | AI_agent_harness | gemma4:e4b | guards-n/a | 84 | AI_agent_harness 時期：harness 與 claude_code 兩種上下文模式 × 3 |
| 20260927_023536_claude_code_raw6000 | 主對話 | E5 | AI_agent_harness | gemma4:e4b | guards-n/a | 12 |  |
| 20260927_093620 | 主對話 | E5 | AI_agent_harness | gemma4:e4b | guards-n/a | 78 |  |
| 20260927_094222 | 主對話 | E5 | AI_agent_harness | gemma4:26b | guards-n/a | 78 |  |
| 20260927_094820 | 主對話 | E5 | AI_agent_harness | gemma4:26b | guards-n/a | 6 |  |
| 20260927_094840 | 主對話 | E5 | AI_agent_harness | gemma4:e4b | guards-n/a | 6 |  |
| 20261007_190607_coding_gemma4-e4b | 自建 coding 情境 | E4 | v0 | gemma4:e4b | harness | 10 | 第一版，5 個 Python 情境 × 2 |
| 20261007_191853 | 主對話 | E5 | v0 | gemma4:e4b | guards-n/a | 6 | coding 路由的 2 個情境 |
| 20261007_194713_coding_gemma4-e4b | 自建 coding 情境 | E4 | v0 | gemma4:e4b | harness | 12 |  |
| 20261007_200504_coding_gemma4-26b | 自建 coding 情境 | E4 | v0 | gemma4:26b | harness | 12 |  |
| 20261007_201916 | 主對話 | E5 | v0 | gemma4:e4b | guards-n/a | 14 |  |
| 20261007_231301_coding_gemma4-e4b | 自建 coding 情境 | E4 | v1 | gemma4:e4b | harness | 5 | C／C++ 5 個 |
| 20261007_232611_devbench_gemma4-e4b | DevBench | trial | v1- | gemma4:e4b | harness | 1 | 試跑 1 個 repo |
| 20261007_233415_devbench_gemma4-e4b | DevBench | trial | v1- | gemma4:e4b | harness | 3 | 試跑 3 個 repo |
| 20261007_234826_coding_gemma4-e4b | 自建 coding 情境 | E4 | v1 | gemma4:e4b | harness | 6 | Python 回歸（換成真的 pytest 之後） |
| 20261008_000353 | 主對話 | E5 | v1 | gemma4:e4b | guards-on | 14 | 加入卡住偵測、宣稱完成偵測、路徑建議之後 |
| 20261008_000705_devbench_gemma4-26b | DevBench | E1 | v1 | gemma4:26b | harness | 12 |  |
| 20261008_023431_devbench_gemma4-e4b | DevBench | E1 | v1 | gemma4:e4b | harness | 12 |  |
| 20261008_054201_coding_gemma4-26b | 自建 coding 情境 | E4 | v1 | gemma4:26b | harness | 5 | C／C++ 5 個 |
| 20261008_054731_coding_gemma4-e4b | 自建 coding 情境 | E4 | v1 | gemma4:e4b | harness | 2 | rename_cross_file × 2 |
| 20261008_054925_coding_gemma4-26b | 自建 coding 情境 | E4 | v1 | gemma4:26b | harness | 6 | Python 6 個 |
| 20261008_055602_coding_gemma4-e4b | 自建 coding 情境 | E4 | v1 | gemma4:e4b | harness | 12 | Python 6 個 × 2 |
| 20261008_062246_devbench_gemma4-e4b | DevBench | E1 | v2 | gemma4:e4b | harness | 12 |  |
| 20261008_084341_devbench_gemma4-26b | DevBench | E1 | v2 | gemma4:26b | harness | 12 |  |
| 20261008_101225_devbench_gemma4-26b_visible-tests | DevBench | E3 | v2 | gemma4:26b | harness・官方測試看得到 | 12 |  |
| 20261008_114542_coding_gemma4-26b | 自建 coding 情境 | E4 | v2 | gemma4:26b | harness | 5 | C／C++ 5 個 |
| 20261008_114747_coding_gemma4-e4b | 自建 coding 情境 | E4 | v2 | gemma4:e4b | harness | 5 | C／C++ 5 個 |
| 20261008_131229_coding_gemma4-e4b | 自建 coding 情境 | E4 | v3 | gemma4:e4b | harness | 1 | 單一情境的快速檢查 |
| 20261008_134110_coding_gemma4-e4b | 自建 coding 情境 | E4 | v4- | gemma4:e4b | harness | 14 | 全部 14 個；ROS 2 情境第一次（套件內相對路徑的防呆之前） |
| 20261008_134756_coding_gemma4-26b | 自建 coding 情境 | E4 | v4- | gemma4:26b | harness | 3 | ROS 2 3 個 |
| 20261008_135449_coding_gemma4-e4b | 自建 coding 情境 | E4 | v4 | gemma4:e4b | harness | 14 | 全部 14 個 |
| 20261008_140127_coding_gemma4-e4b | 自建 coding 情境 | E4 | v4 | gemma4:e4b | harness | 6 | ROS 2 3 個 × 2 |
| 20261008_140610_coding_gemma4-26b | 自建 coding 情境 | E4 | v4 | gemma4:26b | harness | 3 | ROS 2 3 個 |
| 20261008_143819_robust_guards-on | 主對話 | E6 | v4 | gemma4:e4b | guards-on | 15 |  |
| 20261008_143943_robust_guards-off | 主對話 | E6 | v4 | gemma4:e4b | guards-off | 15 |  |
| 20261008_144150 | 主對話 | E5 | v4 | gemma4:e4b | guards-on | 42 |  |
| 20261008_144456_coding-bare_gemma4-e4b | 自建 coding 情境 | E4 | v4 | gemma4:e4b | bare | 28 |  |
| 20261008_144715_coding-bare_gemma4-26b | 自建 coding 情境 | E4 | v4 | gemma4:26b | bare | 28 |  |
| 20261008_144944_coding_gemma4-26b | 自建 coding 情境 | E4 | v4 | gemma4:26b | harness | 14 |  |
| 20261008_145629_devbench-bare_gemma4-26b | DevBench | E2 | v4 | gemma4:26b | bare | 12 |  |
| 20261008_145908_devbench_gemma4-26b | DevBench | E1 | v4 | gemma4:26b | harness | 12 |  |
| 20261008_154319_devbench-bare_gemma4-e4b | DevBench | E2 | v4 | gemma4:e4b | bare | 12 |  |
| 20261008_154649_devbench-bare_gemma4-26b_visible-tests | DevBench | E3 | v4 | gemma4:26b | bare・官方測試看得到 | 12 |  |
| 20261008_155035_devbench_gemma4-26b | DevBench | E1 | v4 | gemma4:26b | harness | 12 |  |
| 20261008_162522_devbench_gemma4-26b_visible-tests | DevBench | E3 | v4 | gemma4:26b | harness・官方測試看得到 | 12 |  |
| 20261008_195402_robust_v41-on | 主對話 | E7 | v4.1 | gemma4:e4b | v4.1 把關開啟 | 50 |  |
| 20261008_195951_robust_v4rule-on | 主對話 | E7 | v4.1 | gemma4:e4b | v4 的規則（對照） | 50 |  |
| 20261008_200509_robust_v41-off | 主對話 | E7 | v4.1 | gemma4:e4b | 把關全部關閉 | 50 |  |
| 20261008_201155_v41 | 主對話 | E7 | v4.1 | gemma4:e4b | guards-on | 28 |  |
