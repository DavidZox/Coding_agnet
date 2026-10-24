# Data Analysis Agent（ROS 2／MCAP 數據解析與維運助理）

以本地 Ollama 模型（預設 `gemma4:e4b`）為核心的機器人助理，有 CLI 與 Web 兩種介面；決策模型只用本地模型（離線的工廠環境）。

- **數據解析**（`analysis_run`）：把一段 ROS 2 錄製（.mcap 與 /rosout）整理成**事實報告**——量到什麼、什麼時候、Log 說了什麼。
  報告全部由程式產生（事實不會錯），AI 依報告回答、討論，要細看時自己用數據技能；只要有 .mcap 就能用；不判斷原因（原因要對照源碼另外分析）。
- **機器人維運**：檔案系統、Docker 容器、容器內的 ROS 2、fih_rmf_system 的調度系統；會重複做的流程寫成**工作流**（`workflow_run`：
  程式照步驟做、模型只在判斷點出手、做完了沒由程式判斷，例如工作包卡住的處理、改設定、派工並確認跑完），其他複雜的任務用 `ops_run`
  先規劃、確認整份計畫，再一步一步做。
- **視覺**：Web 附圖（框選螢幕或上傳）、`image_inspect` 技能、獨立的框選小工具。

核心想法是**模型不寫程式、只挑技能**：可用的能力是一份技能索引，加上按需載入的規格與既有腳本；會改變實體狀態的動作（派工單、
建容器、容器內非唯讀的指令…）執行前一律由程式請使用者確認。

## 快速開始

**需要**：已在執行的 [Ollama](https://ollama.com/)（先 `ollama pull gemma4:e4b`）、Python 3.10+ 與 `pip install ollama`；附圖需要 `Pillow`。
容器、ROS 2 與數據技能需要宿主機的 `docker` CLI；數據技能另外需要一個有 ROS 2、`python3-mcap`（`pip install mcap`）與 PyYAML 的容器
（要讀自訂訊息型別時，容器裡要有建好的 Workspace）。調度系統技能需要 fih_rmf_system 的 web_console（:8020），離線時可以用
`skills_system/scripts/mock_server.py` 代替。

```bash
python3 web_console.py      # Web：http://127.0.0.1:8765（只綁本機）
python3 Agent_Runner.py     # CLI
python3 Agent_Runner.py --workflow <名稱> 名稱=值 … [--yes]   # 不用互動執行一次工作流（排程、之後的心跳用；結束碼見架構說明 14.1）
python3 -m vision.sniper    # 獨立的「截圖 → 框選 → 視覺推論」小工具：http://127.0.0.1:8766
```

Web 左欄是對話，右欄是系統與工具回傳（另一個分頁是「📊 數據分析」面板）：每次工具回傳有兩張卡，一張是完整原文（附 `#編號`），一張是
「AI 實際收到的內容」。輸入框打 `/` 會跳出指令與技能選單，旁邊有附圖（📷）、Plan 模式（📝）與 📊 分析模式按鈕；標題列顯示目前的
目標容器、ROS 2 Workspace 與目前分析的數據，🧠 設定主對話的模型。

| 常用指令 | 作用 |
|---|---|
| `/auto on`、`/hybrid on` | 工具結果自動加入、連續執行到做完（Web 最多 25 輪）／每次問要不要加入 |
| `/plan on` | 下一個任務先由 AI 列步驟草稿，核准（y）後才執行；`/plan add`、`/plan edit N`… 直接改草稿 |
| `/analyze [問題]`、`/analysis_help` | 數據分析（見下面）／數據分析的全部指令 |
| `/workflow`、`/workflow show <名稱>`、`/workflow <名稱> 名稱=值 …` | 列出工作流／看步驟／直接執行（不經過 AI 選擇；會改變狀態的步驟照常請你確認，報告進對話、AI 依報告回答）；停在【確認】時 `/workflow --continue`／`--cancel` |
| `/context_mode harness`、`/context_mode claude_code` | 切換上下文模式（見〈[架構說明 1.1](doc/架構說明.md#11-兩種上下文模式context_mode-harnessclaude_code)〉） |
| `/guard on`、`/guard off` | 執行前確認的開關（預設開；關閉只限這次執行） |
| `/skill <名稱>`、`/skills`、`/make_skill <名稱>` | 手動載入某技能的規格／列出所有技能／把做對的對話整理成工作流 |
| `/compress`、`/clear`、`/menu` | 手動壓縮上下文／清空對話／列出全部指令 |

常用的環境變數：`WEB_CONSOLE_MODEL`（Web 的主模型，預設 `gemma4:e4b`；在 🧠 設定過之後以畫面上的為準）、`AGENT_NUM_CTX`（context
上限，預設 32768）、`AGENT_CONTEXT_MODE`、`RMF_WEB_CONSOLE_URL`（預設 `http://localhost:8020`）、`VISION_MODEL`。全部的常數與環境變數見
〈[架構說明 §10](doc/架構說明.md#10-常數與環境變數)〉。

## 數據解析（`analysis_run`）

**怎麼用**
1. **設定**：右欄「📊 數據分析」→ ⚙️ 設定：預設容器（數據技能都在容器內執行）、數據根目錄（空白＝在容器的 /workspace 底下找
   `experiment_logs`）。
2. **數據**：跟 AI 說「錄 30 秒的核心 Topic」（mcap_recorder），或用現有的實驗資料夾（「看一下 exp_20261014_084506」）。一次最多分析
   3 分鐘，更長的先用 mcap_slicer 切出要看的那段。
3. **問問題**：直接跟 AI 說（「底盤在錄製中途停下來的前後發生了什麼？」，它會選 analysis_run；只問一個值或 Log 時直接用對應的技能），
   或 `/analyze <問題>`，或按 **📊 分析** 進入分析模式。
4. **看結果**：左欄是 AI 依報告的回答（可以接著追問、要它細看某個 Topic 或某段時間）；「📊 數據分析」面板有去重後的 Log、全部 Topic 的事實
   與事實報告。

| 數據分析指令 | 作用 |
|---|---|
| `/analyze [--data 數據] [--topic T] [問題]` | 直接交給 analysis_run（問題省略＝這段錄製期間發生了哪些狀態變化）；報告進主對話，可以接著追問（CLI 與 Web 一樣） |
| `/analysis`、`/analysis jobs` | 看最近一次的報告／列出最近的 job |
| `/analysis_data`、`/analysis_root`、`/analysis_container` | 目前的數據、數據根目錄、預設容器（`-` 清除） |

**怎麼運作**

```
① 事實（程式）　　Log 去重成 L#；量全部 Topic 的全部 Key，整理成 T#＝Topic、E#＝事件、時間線與前後 1 秒的對照
② 重點（程式）　　每個重要的時間點一則（那一刻全部的 Log 與事件），加上到最後跟開頭不同的值、沒有變化的 Topic
③ 報告（程式）　　report.md、主對話的 #編號；一次約 2 秒，不呼叫模型，同一份數據每次一樣
④ 主對話（模型）　依報告回答、討論，要細看時用數據技能；程式核對回答不把先後寫成因果、寫的變化與值跟事實一致（追問的回合也核對）
```

![數據分析的流程](doc/images/數據診斷的流程.png)

| 誰 | 做什麼 |
|---|---|
| 程式（不呼叫模型） | Log 去重、量全部 Topic 的全部 Key、事實的整理（編號、類別、事件、到最後的值、時間線、時間上的對照、同時發生）、重要的時間點與重點、報告組合 |
| 程式核對 | 主對話依報告的回答不寫因果、寫的變化與值（從 A 變成 B、到最後的值、沒有變化、回到初始）跟事實對得上；執行報告的那一回合核對整個回答，之後的回合核對寫到報告的那幾行 |
| 模型 | 主對話：理解問題、依報告回答與討論、用數據技能細看某個 Topic、某段時間或某則 Log |

細節：每一步做什麼、產物存在哪裡、報告的範例見〈[架構說明 §13](doc/架構說明.md#13-數據分析agent_coreanalysis_jobpy全部由程式做)〉；
設計理由與實測（為什麼全部由程式做：三個版本的比較）見〈[設計筆記 2.15](doc/設計筆記與已知限制.md)〉。**已知的限制**：一次最多分析
3 分鐘；時間上的對照不代表誰造成誰；主對話的回答只核對寫得出主詞的說法（Key 或 Topic 名稱：從 A 變成 B、到最後的值、沒有變化、
回到初始），中文主詞的說法不核對；字串裡的 JSON 要抽樣八成以上是 JSON 物件才展開成 Key（其他的字串只量訊息流）；固定頻率的 Topic
頻率中途改變不會列成事件。完整的在〈設計筆記〉第 6 節。

## harness 怎麼運作

![架構圖](doc/images/AI_agent_harness的說明.png)

1. 主 session 每輪回一個 JSON `{thought, reply, action}`，harness **只看 `action`**，`reply` 裡的文字不會被執行。
2. `action` 填技能名稱 → 回傳該技能的規格文件（這一輪不執行）；填規格標明的腳本路徑 → 才真的執行。
3. 每次執行的完整原文都存成 `#編號`。回傳怎麼進主對話看上下文模式：**harness**（預設）超過 500 tokens 時交給獨立 session 依問題提煉——
   長的輸出由程式依結構切段、每段一個 worker、再整合，每條事實附原文的行號、由程式核對，全部的中間產物存在 `logs/extract_jobs/`；
   **claude_code** 原文直接進上下文，太大保留頭尾並標明存檔編號與中間有哪幾節。使用者之後追問舊資料時，模型用 `result_recall <編號>` 回到原文重新提煉。
4. system prompt 只放不常變的內容（KV cache 才能重用）；工作目錄、目標容器、核准的計畫這些常變的小東西，每次接在送出內容的最後面。
5. 上下文超過水位時，舊對話融合成一份滾動摘要；使用者的原話由程式逐字保留，被壓掉的對話也存成 `#編號`。
6. 主對話的程式把關（`turn_guard.py`）：同樣的動作一直得到同樣的結果時提醒、第四次停下；沒有執行卻宣稱做完時提醒一次；依數據分析的
   報告回答時把先後寫成因果、或寫錯事實時提醒一次。

每一步對應到哪個函式、狀態存在哪裡、要改某件事該看哪裡，見〈[架構說明](doc/架構說明.md)〉。

## 技能一覽

| 分類 | 技能 |
|---|---|
| ROS 2 數據解析 | `analysis_run`（程式整理的事實報告）、`mcap_recorder`、`rosout_parser`、`mcap_analyzer`、`mcap_feature_measure`、`mcap_slicer` |
| 檔案系統 | `list_dir`、`search_text`、`find_file`、`change_dir`、`view_file`、`code_ast_reader`、`host_runcmd`、`file_ops`、`csv_query` |
| 容器 | `docker_containers`、`docker_images`、`docker_est`、`docker_open`、`docker_runcmd`、`docker_ctl`、`ROS2_workspace_env` |
| ROS 2（容器內） | `ROS2_domain_id`、`ROS2_topic_list`、`ROS2_topic_echo`、`ROS2_node_list`、`ROS2_node_info`、`ROS2_param`、`ROS2_topic_pub` |
| 調度系統 | `workpackage_send`、`workpackage_status`、`workpackage_cancel`、`overpending_cancel`、`semantic_map`、`rmf_handshake` |
| 工作流（`skills_system/workflows/`） | `workflow_run`：`stuck_package_fix`、`config_edit`、`dispatch_and_confirm`、`container_restart_verify`、`reassign_package` |
| 多步驟維運任務 | `ops_run`（規劃 → 確認整份計畫 → 每一步派 worker、程式檢查） |
| 多模態 | `stt_engine`、`image_inspect` |
| 工具結果存檔 | `result_recall`、`result_grep`、`result_view`、`result_list` |
| 記憶 | `modify_memory`（用法寫在 `prompts/AGENT.md` 的記憶協議，不列在索引） |

索引在 [`skills_system/SKILLS.md`](skills_system/SKILLS.md)，每個技能的規格在 `skills_system/tools/<name>.md`、工作流在 `skills_system/workflows/<名稱>.md`；各技能的參數與重點見
〈[設計筆記 §3](doc/設計筆記與已知限制.md#3-技能清單全部功能)〉。

## 評測

| 對象 | 不用模型（改程式之後先跑） | 真模型或真的容器 |
|---|---|---|
| 主對話 | `evals/chat/selftest.py` | `evals/chat/run.py`（兩種上下文模式 × 情境） |
| 技能腳本 | `evals/skills/selftest.py`（需要容器的在沙盒裡跑，沒有就略過） | — |
| 數據解析 | `evals/analysis/selftest.py`、`evals/datagen/check_facts.py` | `evals/analysis/regression.py`（這台的實錄與隨機情境產生器 `evals/datagen/` 的錄製；不呼叫模型，要容器）、`evals/analysis/tools_live.py` |
| 多步驟維運 | `evals/ops/selftest.py` | `evals/ops/run.py`（Docker-in-Docker 沙盒裡真的執行） |
| 工作流 | `evals/workflow/selftest.py` | `evals/workflow/sandbox.py`（沙盒裡直接執行工作流） |
| 提煉 | `evals/chat/extract_selftest.py` | `evals/extract/run.py`（已知答案的長輸出） |
| 每個階段結束 | `evals/phase_check.py`（離線） | `evals/phase_check.py --live --model`（跟 `evals/baselines/` 逐項比） |

怎麼跑、情境清單、怎麼讀報表見〈[評測](evals/README.md)〉。

## 目錄結構

```
Coding_agnet/            （資料夾名稱沿用；原本的 coding agent 已移到 ~/Coding_agent_harness）
├── Agent_Runner.py      CLI 入口（實作在 agent_core/cli.py；--workflow 是不用互動的入口）
├── web_console.py       Web 入口（實作在 web_app/）
├── agent_core/          核心：SkillAgent（由各 mixin 組成）、回覆協議、常數；analysis_job.py＝數據解析、extract.py＝工具回傳的提煉、
│                        workflow*.py＝工作流、ops_job.py＝多步驟維運
├── web_app/             Web 介面（純標準庫）：回合流程、slash 指令、HTTP、static/index.html；analysis.py＝📊 面板的後端
├── prompts/             給模型的文字（可以直接改）
│   ├── AGENT.md         主對話的 system prompt
│   ├── Memory.md        長期記憶（modify_memory 寫入，每輪常駐）
│   ├── context_modes/   兩種上下文模式的規則
│   ├── extract/         工具回傳的提煉：worker 與整合
│   ├── ops/             多步驟維運的規劃與 worker
│   └── workflow/        工作流的判斷點（填值、選分支）
├── skills_system/       技能：SKILLS.md（索引）、tools/（規格）、scripts/（腳本與共用模組）、workflows/（工作流）
├── vision/              視覺模態：擷取、推論、提取、Web 的框選（web/）、sniper.py（獨立的框選小工具）
├── evals/               評測：chat/、skills/、analysis/、datagen/、ops/、workflow/、extract/、phase_check.py、baselines/；
│                        results/（.gitignore）
├── doc/                 文件；diagrams/（.puml 與產生器）、images/（圖）、archive/（第一～九輪的根因版本，只供閱讀）
├── test_data/           實機錄製、正確答案、回歸工具（只在本機，.gitignore）
└── logs/                執行時產生：工具回傳存檔、檢索清單、軌跡、摘要、extract_jobs/、analysis_jobs/、workflow_jobs/、ops_jobs/
                         （.gitignore）
```

## 文件

- 〈[架構說明](doc/架構說明.md)〉：每個模組負責什麼、一回合怎麼跑、狀態存在哪裡、要改某件事該看哪裡；數據解析在 §13、工作流在 §14
- 〈[設計筆記與已知限制](doc/設計筆記與已知限制.md)〉：各機制的理由與實測數據、完整技能清單、已知限制、未來方向
- 〈[技能撰寫規範](doc/技能撰寫規範.md)〉、〈[工作流撰寫規範](doc/工作流撰寫規範.md)〉：新增或修改技能腳本與工作流的規則與怎麼測
- 〈[待辦清單](doc/待辦清單.md)〉：已記錄、還沒做的——架構整合剩下的階段（第 4～6 階段）與數據解析、技能的下一步
- 〈[長期願景](doc/長期願景.md)〉：AGV/AMR 車隊調度場景的構想、心跳機制與定時任務要注意的事
- 〈[評測](evals/README.md)〉、〈[隨機情境的錄製產生器](evals/datagen/README.md)〉
- 圖的來源在 `doc/diagrams/`，怎麼重新產生見〈[文件導覽](doc/README.md)〉
