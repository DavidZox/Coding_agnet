> 非編碼任務的資料集與 orchestrator 設計調查：2026-10-10 開始這次評測前，委派給研究用的子代理做的網路調查（原文是英文，照原樣保存；報告裡引用的數字以原始論文為準，標 UNVERIFIED 的是調查時沒能確認的）。

**Benchmarks for a non-coding local agent: research results (checked 2026-10-10).** No project files were changed. I took licenses from each repo's LICENSE file. UNVERIFIED means I could not confirm it.

**Bottom line:** No existing suite covers Docker ops, ROS 2 ops or a dispatch handshake with state-based checks, so those parts must be custom-built. The best things to borrow are the BFCL file-system scenarios, the τ²-bench scoring, AgentBench-OS-style shell tasks and the rai_bench validator pattern for ROS 2.

### 1. Shell / file ops
| Benchmark | Tasks, environment, scoring | Offline | Open-model numbers |
|---|---|---|---|
| AgentBench-OS, ICLR'24 [2308.03688](https://arxiv.org/abs/2308.03688), [Apache-2.0](https://github.com/THUDM/AgentBench) | 26 dev / 144 test tasks. Ubuntu Docker image plus init scripts. Scored by exact match, or by check scripts that recompute the answer inside the container. E.g. "How many hidden files are in /home?", "count users in ≥2 groups" | Yes, after the image is built | Vicuna-13B 10.4, Llama-2-13B 4.2, CodeLlama-34B 2.8 (GPT-4 42.4) |
| InterCode-Bash, NeurIPS'23 [2306.14898](https://arxiv.org/abs/2306.14898), [MIT](https://github.com/princeton-nlp/intercode) | 200 tasks derived from NL2Bash, on 4 prepared file systems. Reward combines file-system diff, md5 of changed files and stdout similarity; 1.0 only if all match. E.g. "Set permissions of…" | Yes | Vicuna-13B 16.0 single-turn / 24.5 try-again; StarChat-16B 17.7 / 23.7 |
| BFCL v3/v4 multi-turn, ICML'25 ([PMLR](https://proceedings.mlr.press/v267/patil25a.html); arXiv id UNVERIFIED), [Apache-2.0](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard) | 800 entries: 200 each of base, missing function, missing parameter and long context. 50 of the 200 base entries use a simulated file system, GorillaFileSystem (cd, ls, find, grep, mv, cp, rm…). After every turn it compares the API objects' state with the gold state. It also checks that the gold calls are a subset of the calls made. E.g. "Move 'final_report.pdf' … to 'temp' … create the directory" | Yes. `--skip-server-setup` accepts any OpenAI-compatible server; whether it maps cleanly to an Ollama model is UNVERIFIED | Multi-turn overall ([leaderboard CSV](https://raw.githubusercontent.com/ShishirPatil/gorilla/gh-pages/data_multi_turn.csv)): Qwen3-8B 41.8, Qwen3-14B 34.8, Qwen3-32B 47.9, Qwen3-30B-A3B 30.0, xLAM-2-8b 70.0, Gemma-3-27b 10.8, Gemma-3-12b 5.8. No Gemma 4 entry |
| Terminal-Bench 1.0 (80 tasks) / 2.0 (89 tasks), [2601.11868](https://arxiv.org/abs/2601.11868), [Harbor](https://github.com/harbor-framework/harbor) Apache-2.0 | Each task has a Dockerfile, pytest tests on the final container state, and a reference solution | Partial; some tasks need network | TB2: GPT-OSS-20B 3.1–3.4%. Best open model is Kimi-K2-Thinking at 35.7%. TB3 and TB4 (2026) are harder still |
| MCPMark [2509.24002](https://arxiv.org/abs/2509.24002), [Apache-2.0](https://github.com/eval-sys/mcpmark) | 30 filesystem tasks (of 127), each with a prepared directory tree and a verify.py script | Yes | Models ≤100B not tested; GPT-5-medium 57.5% on filesystem |

NL2Bash ([1802.08979](https://arxiv.org/abs/1802.08979)) and NL2SH-ALFA ([2502.06858](https://arxiv.org/abs/2502.06858), 600 command pairs checked by execution) are static datasets, useful only as prompt sources. There is no LLM benchmark called "ShellBench"; that name belongs to a shell-speed tool.

### 2. Docker / DevOps
I found no benchmark for routine container ops (ps/run/exec/logs). The existing ones test environment setup:
- **EnvBench** [2503.14443](https://arxiv.org/abs/2503.14443) ([MIT](https://github.com/JetBrains-Research/EnvBench)): 994 repos, checked by import/compile. The best baseline set up 6.7% of Python and 29.5% of JVM repos.
- **Similar setup benchmarks:** Installamatic [2412.06294](https://arxiv.org/abs/2412.06294), ExecutionAgent [2412.10133](https://arxiv.org/abs/2412.10133) and SetupBench [2507.09063](https://arxiv.org/abs/2507.09063) (93 tasks).
- **DevOps-Gym**, ICLR'26 [2601.20882](https://arxiv.org/abs/2601.20882): 704 Java/Go tasks in Docker, including 34 monitoring tasks with injected faults. Qwen3-Coder-30B scored 20.4% on build and 5.9% on monitoring. Whether the code is released is UNVERIFIED.
- **FDE-Bench** [2609.27571](https://arxiv.org/abs/2609.27571) (Sep 2026): 136 Dockerfile/Compose/K8s tasks.
  - Scored by checks in sequence: build, then readiness, then behavior, then conformance.
  - Each run uses a fresh Docker-in-Docker sandbox.
- **Not a fit:** OpsEval [2310.07637](https://arxiv.org/abs/2310.07637) is multiple-choice only. AIOpsLab [2501.06706](https://arxiv.org/abs/2501.06706) and ITBench [2502.05352](https://arxiv.org/abs/2502.05352) need Kubernetes.

### 3. ROS 2
- **ROSA** (NASA JPL, [2410.06472](https://arxiv.org/abs/2410.06472), [Apache-2.0](https://github.com/nasa-jpl/rosa)): supports ROS1 and ROS2 Humble–Jazzy.
  - Tools: ros2_node_list/info, topic_list/info/echo, service_list/info/call, param_list/get/set, ros2_doctor and roslog_list, each with blacklists.
  - It has no task set and no quantitative evaluation. Ollama support is UNVERIFIED. It is a good reference for which tools to expose.
- **rai_bench** (Robotec.AI, [2505.07532](https://arxiv.org/abs/2505.07532), [Apache-2.0](https://github.com/RobotecAI/rai)): a tool-calling benchmark with mocked ROS 2 tools. **This is the best one to reuse.**
  - About 30 task classes: topics, services, images, get/set params, spawn entity, custom messages/services, manipulation.
  - Each task runs with brief or descriptive prompts, 0/2/5 examples, and an allowance of extra tool calls.
  - Scoring checks tool arguments and message fields, either in strict order, in any order, or "any one of".
  - Its docs list Ollama as a backend. It needs a ROS 2 environment. I found no published results (UNVERIFIED).
- **ROS-LLM** [2406.19741](https://arxiv.org/abs/2406.19741) (ROS1, real robot, license UNVERIFIED) and [ROSGPT](https://github.com/aniskoubaa/rosgpt) (CC BY-NC) have no reusable eval set.

No reusable ROS 2 ops task set with state checks exists.

### 4. Stateful APIs and protocol following
- **τ-bench** [2406.12045](https://arxiv.org/abs/2406.12045) ([MIT](https://github.com/sierra-research/tau-bench)): retail 115 and airline 50 tasks.
  - A policy document sets rules such as "obtain explicit user confirmation (yes)" before any write.
  - Reward = (final database equals the gold state) × (required information appears in the answer).
  - pass^k means all k runs of a task succeed.
- **τ²-bench** [2506.07982](https://arxiv.org/abs/2506.07982) ([MIT](https://github.com/sierra-research/tau2-bench); the repo now calls itself τ³): adds a telecom domain (114 tasks) where agent and user both act on shared state.
  - Reward is the product of: a database check (replay the gold actions, then compare hashes), environment assertions, required strings in replies, action matching, and natural-language assertions.
  - It uses LiteLLM, so local models work. A custom domain is just a policy, tools, a database and tasks.
  - With gpt-4.1/o4-mini on telecom, success drops about 18–25% when the agent must guide a user, and is near 0 beyond 7 actions.
  - The Gemma 4 [model card](https://ai.google.dev/gemma/docs/core/model_card_4) reports τ2 averaged over 3 domains: **E4B 42.2, 26B-A4B 68.2**.
- **AppWorld**, ACL'24 [2407.18901](https://arxiv.org/abs/2407.18901) ([Apache-2.0](https://github.com/StonyBrookNLP/appworld)): 750 tasks over 457 APIs.
  - Unit tests check the database state, including that nothing else was changed by mistake. Runs offline.
  - Task completion on the normal test set: DeepSeek-Coder-33B 7.1, Llama-3-70B 20.8.
- **ToolSandbox** [2408.04682](https://arxiv.org/abs/2408.04682) ([Apple license](https://github.com/apple/ToolSandbox)): 1,032 scenarios with hidden preconditions, e.g. cellular must be on before sending an SMS.
  - Milestones are steps that must happen, in a set order. Minefields are actions that must not happen; hitting any one scores 0.
  - The user simulator is a GPT model; offline use is UNVERIFIED.
  - Average similarity score: Hermes-2-Pro-7B 31.4, Mistral-7B 29.8.
- **API-Bank** [2304.08244](https://arxiv.org/abs/2304.08244) and **NESTFUL** [2409.03797](https://arxiv.org/abs/2409.03797) mostly score by matching calls, so they fit poorly.

Best model for a handshake with a stateful service: τ²'s structure, plus ToolSandbox milestones/minefields, plus BFCL's per-turn state checks.

Caution: an audit [2607.02577](https://arxiv.org/abs/2607.02577) found automated scorers disagreed with humans on 18.5% of tasks across BFCL v4, τ² and two MCP benchmarks. Causes were brittle state matching, requiring one exact call sequence, and substring checks.

### 5. Evidence on orchestrator/worker designs
- **ADaPT**, NAACL'24 Findings [2311.05772](https://arxiv.org/abs/2311.05772) ([MIT](https://github.com/archiki/ADaPT)): the executor tries first, and the task is broken down only if it fails.
  - Gains of up to +28, +27 and +33 points on ALFWorld, WebShop and TextCraft.
  - A fixed plan-then-execute approach lost to ReAct on WebShop (17 vs 32).
  - LLaMA-2-70B as executor with a GPT-3.5 planner gained +22.9 points.
- **InterCode-Bash** (GPT-3.5): simple retry 46.5 > Plan-and-Solve 28.0 > ReAct 20.5.
- **ReWOO** [2305.18323](https://arxiv.org/abs/2305.18323): planner/worker/solver split, 5× fewer tokens, planner distilled into a 7B model.
- **α-UMi** [2401.07324](https://arxiv.org/abs/2401.07324): fine-tuned 7B/13B models split into planner, caller and summarizer beat a single model.
- **TinyAgent** [2409.00608](https://arxiv.org/abs/2409.00608): fine-tuned 1.1B/7B models with a planner and tool retrieval matched GPT-4-Turbo on 16 functions.
- **Routine** [2507.14447](https://arxiv.org/abs/2507.14447): giving the model explicit step-by-step routines raised Qwen3-14B from 32.6% to 83.3%.
- **Scaling agent systems** [2512.08296](https://arxiv.org/abs/2512.08296) (frontier models only):
  - Multi-agent versus single agent ranged from +80.8% on tasks that split cleanly to −70% on sequential planning.
  - Tool-heavy tasks paid a coordination cost.
  - Without central verification, errors spread more.
- **MAST** [2503.13657](https://arxiv.org/abs/2503.13657): verification failures are one of three main failure classes.
- **TaskBench** [2311.18760](https://arxiv.org/abs/2311.18760): small models are much worse at breaking tasks down.
- **Magentic-One** [2411.04468](https://arxiv.org/abs/2411.04468): replans from a progress log when stuck.

### 6. Turning workflows into skills
- **Voyager** [2305.16291](https://arxiv.org/abs/2305.16291) ([MIT](https://github.com/MineDojo/Voyager)): stores code skills indexed by description. A skill is saved only after it runs and a GPT-4 check confirms success.
- **AWM** [2409.07429](https://arxiv.org/abs/2409.07429) ([Apache-2.0](https://github.com/zorazrw/agent-workflow-memory)): stores text workflows with placeholders, built only from runs an LLM judged successful. WebArena rose from 23.5% to 35.5%.
- **ASI** [2504.06821](https://arxiv.org/abs/2504.06821) ([CC-BY-SA-4.0](https://github.com/zorazrw/agent-skill-induction)): stores skills as Python functions.
  - A skill is saved only if re-running the task with it succeeds and the skill is actually used.
  - +23.5% success over an agent without skills, and +11.3% over text-based skills.
- **SkillWeaver** [2504.07079](https://arxiv.org/abs/2504.07079) ([MIT](https://github.com/OSU-NLP-Group/SkillWeaver)): skills are tested with generated tests and stored with usage logs. A stronger model's skills improved a weaker model by up to 54.3% (relative).
- **SkillsBench** [2602.12670](https://arxiv.org/abs/2602.12670): curated skills added +16.6 points, and skills with at most 3 modules worked best. Skills the agent wrote for itself before solving cost 8 to 11.5 points.
- **Playbook transfer** [2608.05778](https://arxiv.org/abs/2608.05778): a playbook that helped Qwen2.5-7B at temperature 0 hurt it at temperature 0.3.

### (a) Recommended suite: about 60 tasks, offline, one host
1. **Dispatch handshake (14 tasks).**
   - Build a FastAPI mock with an explicit state machine: CREATED → OFFERED → ACCEPTED → EXECUTING → REPORTED/FAILED. Simulate robots with scripts, not an LLM.
   - Cover: robot rejects, timeout, robot offline, missing parameter (the agent must ask), and illegal transitions.
   - Scoring:
     - From τ-bench: compare the final database with the gold state (ignore IDs and timestamps), times required fields in the report.
     - From ToolSandbox: milestones for the handshake order, and minefields for executing before accept, double dispatch, or touching other robots.
     - From AppWorld: checks that nothing else was changed.
     - From BFCL: state checks after every turn.
     - Report pass^4.
2. **Files and directories (16 tasks).**
   - Port 8 BFCL file-system scenarios: build each starting tree on disk, run the user's own skills, and compare the final tree with BFCL's gold state.
   - Add 8 AgentBench-OS / InterCode-style tasks on a prepared tree that mirrors the user's documents.
   - Also run BFCL's own harness once, to compare against the Qwen3/Gemma-3 numbers above.
3. **ROS 2 (12 tasks).**
   - 6 rai_bench-style tasks on mocked tools.
   - 6 live tasks in a ros:humble or ros:jazzy container running fixed nodes (talker, turtlesim, a parameter node, a counter service), checked with the ros2 CLI.
   - Keep ROS traffic away from the production robots: use an unused ROS_DOMAIN_ID and a bridge network. Also set ROS_LOCALHOST_ONLY=1 (Humble) or ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST (Jazzy).
4. **Docker (12 tasks).**
   - Run everything in a separate Docker-in-Docker daemon, as FDE-Bench does. Preload images with `docker save` / `docker load`.
   - Skills see only that daemon's DOCKER_HOST, never the host socket, so production containers are untouched.
   - Check results with `docker inspect`, labels and logs. Minefields: prune, `rm -f`, or touching anything outside the sandbox.
5. **Combined tasks (6 tasks).** E.g. find a mission file → start a container → verify a topic → dispatch → report. These are the main comparison of orchestrator mode against a single agent.

Package each task Harbor-style (instruction, environment, tests, reference solution); the reference solution must score 1.0. Report success, pass^k, milestone progress, minefield hits, tool-call count and wall time.

### (b) Design lessons for adding orchestrator/worker mode with small local models
1. **Break tasks down only when needed.**
   - Let the worker try first; bring in the planner only after a failure or stall.
   - Rigid plan-first approaches lost to adaptive loops (WebShop 17 vs 32; Bash 28 vs 46.5). Multi-agent splits cost up to 70% on sequential tasks.
   - Run in parallel only steps that just read and are independent.
2. **Have the planner output a short structured routine**: step, skill, arguments, expected result.
   - Keep each worker step to 5 tool calls or fewer, from a small set of tools. τ² success is near 0 beyond 7 actions, and explicit routines took Qwen3-14B from 32.6% to 83.3%.
   - Use gemma4 26B-A4B to plan and verify, and E4B only for narrow steps (τ2 68.2 vs 42.2).
3. **Have the orchestrator verify centrally after each step** using read-only checks: `docker inspect`, `ros2 param get`, `GET /tasks/{id}`. Enforce the handshake order in the dispatch API or skill code, not in the prompt (MAST; scaling study).
4. **Pass a compact state summary between agents, not full transcripts.** ReWOO used 5× fewer tokens this way.
5. **Save a skill only from a success that was verified and then re-run with the skill** (as in ASI and Voyager).
   - Store it as a parameterized script plus a short SKILL.md.
   - Re-test every skill on both gemma4 sizes, at the temperature you will deploy with.
   - Skills the model wrote for itself without verification cost 8 to 11.5 points (SkillsBench).
