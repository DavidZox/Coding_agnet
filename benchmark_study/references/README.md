# 參考資料

取得日期：2026-10-08。論文是 arXiv 上的 PDF；網頁另外存了 HTML（原始檔，離線開啟可能缺樣式）與用 Chrome 印出的 PDF（看起來跟網頁一樣）。
這些檔案是內部參考用的副本；如果這個專案要公開，請照各自的授權處理（arXiv 論文的預設授權不一定允許轉載，網頁著作權屬原作者）。

| # | 文獻 | 在報告裡用來說明 | 本地檔案 | 網址 |
|---|---|---|---|---|
| [1] | Li et al., *DevBench: A Comprehensive Benchmark for Software Development*（arXiv:2403.08604 v1，2024-03）；後來的版本改名為 *Prompting Large Language Models to Tackle the Full Software Development Lifecycle: A Case Study* | 本研究用的長任務基準（實作任務）、官方的評分方式 | `papers/DevBench_2403.08604v1.pdf`、`papers/DevBench_2403.08604.pdf`（最新版） | https://arxiv.org/abs/2403.08604 |
| [2] | open-compass/DevEval（DevBench 的程式與資料，commit `bb593c1f`），README 的實作任務結果表（GPT-4-Turbo-0125：驗收 7.1%、單元 8.0%） | 資料來源、授權（程式 Apache 2.0、資料 CC BY 4.0）、公開的參考分數 | `devbench_source/DevEval_README_bb593c1f.md`、`devbench_source/DevEval_LICENSE_bb593c1f`、`web/DevEval_github_page.html` | https://github.com/open-compass/DevEval |
| [3] | Jimenez et al., *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?*（ICLR 2024，arXiv:2310.06770） | 修 issue 型的基準；每題要 Docker 環境 | `papers/SWE-bench_2310.06770.pdf` | https://arxiv.org/abs/2310.06770 |
| [4] | Yang et al., *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering*（arXiv:2405.15793） | 「為模型設計的工具介面」（ACI）這個想法，跟本 harness 的技能設計相同 | `papers/SWE-agent_2405.15793.pdf` | https://arxiv.org/abs/2405.15793 |
| [5] | Qian et al., *ChatDev: Communicative Agents for Software Development*（arXiv:2307.07924） | DevBench 的基準 agent 是從 ChatDev 改的 | `papers/ChatDev_2307.07924.pdf` | https://arxiv.org/abs/2307.07924 |
| [6] | *NL2Repo-Bench: Towards Long-Horizon Repository Generation Evaluation of Coding Agents*（arXiv:2512.12730） | 長任務（只給需求文件、從空的工作區做出可安裝的 Python 函式庫）；最強的 agent 平均測試通過率也低於 40% | `papers/NL2Repo-Bench_2512.12730.pdf` | https://arxiv.org/abs/2512.12730 |
| [7] | Aider, *o1 tops aider's new polyglot leaderboard*（2024-12-21）：polyglot 基準＝Exercism 最難的 225 題，C++、Go、Java、JavaScript、Python、Rust | 建議的下一個基準（一般 coding 題、有 C++ 與 Python） | `web/aider_polyglot_benchmark_2024-12-21.html`、`.pdf` | https://aider.chat/2024/12/21/polyglot.html |
| [8] | Epoch AI, *How to run SWE-bench Verified in one hour on one machine*（2025-07-10）：最佳化後全部 2290 個 SWE-bench 映像 67 GiB、Verified 的 500 個 30 GiB | SWE-bench 的硬體與磁碟成本 | `web/epoch_ai_swebench_docker.html`、`.pdf` | https://epoch.ai/blog/swebench-docker |
| [9] | EvalScope 文件：SWE-bench Multilingual（300 題、42 個 repo、9 種語言，含 C／C++；每題一個 Docker 容器） | 建議的下一個基準（C／C++ 的修 issue 任務） | `web/evalscope_swe_bench_multilingual.html`、`.pdf` | https://evalscope.readthedocs.io/en/latest/benchmarks/swe_bench_multilingual_agentic.html |
