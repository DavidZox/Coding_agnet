# 參考文獻

取得日期：2026-10-10。論文是 arXiv 上的公開版本（`papers/`，檔名後面是 arXiv 編號）；網頁存成 HTML 與 Chrome 印出的 PDF（`web/`）。
`research_notes/` 是開始評測前委派子代理做的兩份網路調查（英文原文）：資料集的比較、各基準的計分方式與已發表的數字、orchestrator 設計的證據。
這些副本只供內部參考與核對報告裡引用的數字；著作權屬於原作者，專案要公開時不要一起散布，改用下面的連結。

報告裡的編號 [n] 對應下表。

## 資料集與計分

| # | 文獻 | 用在 | 檔案 | 連結 |
|---|---|---|---|---|
| 1 | Li et al., *DevBench: A Comprehensive Benchmark for Software Development*（DevEval），2024 | TW／BF／FE 的 12 個專案 | `papers/DevBench_2403.08604.pdf` | https://arxiv.org/abs/2403.08604 |
| 2 | Wang et al., *MultiFileTest（原名 ProjectTest）: A Multi-File-Level LLM Unit Test Generation Benchmark and Impact of Error Fixing Mechanisms*，2025 | TW 的 6 個 ProjectTest 專案 | `papers/ProjectTest-MultiFileTest_2502.06556.pdf` | https://arxiv.org/abs/2502.06556 |
| 3 | Aider，*o1 tops aider's new polyglot leaderboard*（polyglot benchmark 的說明），2024-12-21；Exercism 練習題 | AP 20 題 | `web/aider_polyglot_blog.*` | https://aider.chat/2024/12/21/polyglot.html 、https://github.com/Aider-AI/polyglot-benchmark |
| 4 | Jain et al., *TestGenEval: A Real World Unit Test Generation and Test Completion Benchmark*，2024 | 寫測試用覆蓋率＋突變分數計分 | `papers/TestGenEval_2410.00752.pdf` | https://arxiv.org/abs/2410.00752 |
| 5 | Wang et al., *TESTEVAL: Benchmarking Large Language Models for Test Case Generation*，2024 | 覆蓋率在小模型上已接近天花板 | `papers/TestEval_2406.04531.pdf` | https://arxiv.org/abs/2406.04531 |
| 6 | Al-Ahmad et al., *Evaluating the effectiveness of class-level LLM-generated test suites in Python*，2026 | 同上（覆蓋率「接近天花板」、要看突變分數） | `papers/Class-level-LLM-test-suites_2609.24341.pdf` | https://arxiv.org/abs/2609.24341 |
| 7 | Yang et al., *SWE-smith: Scaling Data for Software Engineering Agents*，2025 | BF 植入 bug 的方法（只留讓既有測試失敗的突變） | `papers/SWE-smith_SWE-bench-Multilingual_2504.21798.pdf` | https://arxiv.org/abs/2504.21798 |

## 非編碼任務的評測

| # | 文獻 | 用在 | 檔案 | 連結 |
|---|---|---|---|---|
| 8 | Yao et al., *τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains*，2024 | 以最後的狀態計分、pass^k | `papers/tau-bench_2406.12045.pdf` | https://arxiv.org/abs/2406.12045 |
| 9 | Barres et al., *τ²-Bench: Evaluating Conversational Agents in a Dual-Control Environment*，2025 | 同上；Gemma 4 模型卡引用的 τ2 分數 | `papers/tau2-bench_2506.07982.pdf` | https://arxiv.org/abs/2506.07982 |
| 10 | Liu et al., *AgentBench: Evaluating LLMs as Agents*，ICLR 2024 | OS 類的殼層任務（重算答案的檢查腳本） | `papers/AgentBench_2308.03688.pdf` | https://arxiv.org/abs/2308.03688 |
| 11 | Yang et al., *InterCode: Standardizing and Benchmarking Interactive Coding with Execution Feedback*，NeurIPS 2023 | 檔案系統差異計分；「直接重試」勝過先規劃 | `papers/InterCode_2306.14898.pdf` | https://arxiv.org/abs/2306.14898 |
| 12 | Lu et al., *ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities*，2024 | 「地雷」（禁止動作）的計分方式 | `papers/ToolSandbox_2408.04682.pdf` | https://arxiv.org/abs/2408.04682 |
| 13 | Merrill et al., *Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks in Command Line Interfaces*，2026 | 以容器最後的狀態跑 pytest 計分 | `papers/Terminal-Bench_2601.11868.pdf` | https://arxiv.org/abs/2601.11868 |
| 14 | Rachwał et al.（Robotec.AI），*RAI: Flexible Agent Framework for Embodied AI*（rai_bench），2025 | ROS 2 任務的驗證器設計 | `papers/RAI-rai_bench_2505.07532.pdf` | https://arxiv.org/abs/2505.07532 |
| 15 | Bhat et al., *Benchmarking the Benchmarks: A Validity Audit of Tool-Calling Evaluation*，2026 | 只比對字串、要求唯一呼叫順序的檢查不可靠 → 這次以狀態為主、回覆用正規表示式 | `papers/Validity-Audit-Tool-Calling-Eval_2607.02577.pdf` | https://arxiv.org/abs/2607.02577 |
| 16 | Google，Gemma 4 模型卡（τ2：E4B 42.2、26B-A4B 68.2） | 模型的工具使用能力 | `web/gemma4_model_card.*` | https://ai.google.dev/gemma/docs/core/model_card_4 |

## orchestrator 與技能的設計

| # | 文獻 | 用在 | 檔案 | 連結 |
|---|---|---|---|---|
| 17 | Prasad et al., *ADaPT: As-Needed Decomposition and Planning with Language Models*，NAACL 2024 Findings | 只在需要時拆解；固定「先規劃再照做」輸給邊做邊調整 | `papers/ADaPT_2311.05772.pdf` | https://arxiv.org/abs/2311.05772 |
| 18 | Xu et al., *ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models*，2023 | 規劃者／執行者分開、只傳精簡的結果 | `papers/ReWOO_2305.18323.pdf` | https://arxiv.org/abs/2305.18323 |
| 19 | Cemri et al., *Why Do Multi-Agent LLM Systems Fail?*（MAST），2025 | 驗證不足是主要的失敗類別 → 程式集中驗證 | `papers/MAST-Why-Multi-Agent-Fail_2503.13657.pdf` | https://arxiv.org/abs/2503.13657 |
| 20 | Kim et al., *Towards a Science of Scaling Agent Systems*，2025 | 多 agent 在可拆解的任務 +80.8%、在循序規劃 −70% | `papers/Scaling-Agent-Systems_2512.08296.pdf` | https://arxiv.org/abs/2512.08296 |
| 21 | Zeng et al., *Routine: A Structural Planning Framework for LLM Agent System in Enterprise*，2025 | 明確的步驟（routine）讓 Qwen3-14B 從 32.6% 到 83.3% → 「常見情況的做法」 | `papers/Routine_2507.14447.pdf` | https://arxiv.org/abs/2507.14447 |
| 22 | Shen et al., *TaskBench: Benchmarking Large Language Models for Task Automation*，2023 | 小模型的任務拆解明顯較差 | `papers/TaskBench_2311.18760.pdf` | https://arxiv.org/abs/2311.18760 |
| 23 | Fourney et al., *Magentic-One: A Generalist Multi-Agent System for Solving Complex Tasks*，2024 | 卡住時依進度紀錄重新規劃 | `papers/Magentic-One_2411.04468.pdf` | https://arxiv.org/abs/2411.04468 |
| 24 | Wang et al., *Voyager: An Open-Ended Embodied Agent with Large Language Models*，2023 | 技能只在驗證成功後才存 | `papers/Voyager_2305.16291.pdf` | https://arxiv.org/abs/2305.16291 |
| 25 | Wang et al., *Agent Workflow Memory*，2024 | 從成功的執行整理出可重用的流程 | `papers/Agent-Workflow-Memory_2409.07429.pdf` | https://arxiv.org/abs/2409.07429 |
| 26 | Zheng et al., *SkillWeaver: Web Agents can Self-Improve by Discovering and Honing Skills*，2025 | 技能附測試、強模型的技能能幫弱模型 | `papers/SkillWeaver_2504.07079.pdf` | https://arxiv.org/abs/2504.07079 |
| 27 | Li et al., *SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks*，2026 | 整理過的技能 +16.6 分；模型自己沒驗證就寫的技能 −8～−11.5 分 | `papers/SkillsBench_2602.12670.pdf` | https://arxiv.org/abs/2602.12670 |

前兩次研究引用過的文獻（Self-Refine、LLM-Modulo、SWE-bench 等）見 `../../benchmark_study_2/references/README.md`。
