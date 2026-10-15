# Data Analysis Agent（ROS 2／MCAP 智慧診斷）

以本地 Ollama 模型（預設 `gemma4:e4b`）為核心的 **ROS 2 數據解析 agent**：錄製 MCAP 與 /rosout、把重複的 Log 去重成唯一訊號、建立全域 Topic Metadata，
再用 **Orchestrator → Workers → Synthesizer** 的多 agent 協同回答「這段數據發生了什麼、為什麼、什麼時候恢復」。
harness 本身（技能系統的索引＋按需載入的規格＋既有腳本、上下文管理、執行前關卡、記憶、Plan 模式、CLI 與 Web Console）跟原本一樣，
機器人維運的技能（容器、ROS 2、調度系統、ops_run）也都還在。決策模型只用本地模型。

> **2026-10-14 拆分**：這個資料夾原本同時有 coding 與非 coding 兩套 harness。coding 的部分（coding orchestrator、`code_*` 技能、Coding 面板、
> coding 評測、DevBench／SWE-bench）已經整個移到 **`/home/david/Coding_agent_harness`**（git clone，保留完整歷史）；這裡只留非 coding 的部分，
> 往數據解析 agent 發展。數據技能依 `diagnostics_package/toolkit` 的人工工具重寫（見下面〈數據技能〉）。

## 數據解析的多 agent 協同（`analysis_run`，2026-10-14 新增）

```
使用者 ─問題─▶ 主對話的 AI（analysis_run 技能）／/analyze 指令／📊 分析模式
                    │
                    ▼
0. 資料預備（程式，按需處理）
   rosout_parser：/rosout 去重成唯一訊號 L#（層級、Node、次數、每一次的時間戳）
   mcap_analyzer：全域 Topic Metadata（錄製時已建立的索引直接讀快取）
1. Orchestrator（一次模型呼叫）──同時看「去重後的 Log」與「全域 Topic Metadata」
   對齊問題 → 挑出相關的 Log 訊號（只填 L#，精確的時間窗由程式換算：前後各幾秒、重疊的合併）
   → 廣度優先分派：每個 worker 一個不同的 Topic（程式檢查：Topic 要存在、可分析、不重複、不派 Log）
2. Workers（每個一個乾淨的 session，可以平行）──只看自己的 Topic、時間窗與 Key 目錄，看不到 Log 字串
   自己決定量哪些 Key（mcap_feature_measure：數值統計、狀態跳轉、訊息中斷）→ Frontmatter Markdown 的局部報告
   （frontmatter 的數字由程式從量測結果填，模型只寫判斷與說明）
3. Synthesizer（一次模型呼叫）──Log 的宏觀視角＋全部局部報告 → 因果拼圖 → 根因診斷報告
   （結論、根因與信心、時間線、證據、尚未確認、建議；也是 Frontmatter Markdown）
```

| 資料類型 | 誰處理 | 怎麼處理 |
|---|---|---|
| String／Log（/rosout、自由文字） | **只有 Orchestrator** | rosout_parser 去重成唯一訊號；自由文字欄位 worker 不量測 |
| Scalar／Float／Vector（數值） | Worker（平行） | 極值、均值、變異數／標準差、斜率、尖峰（>2.5σ）、最大跳變；向量每個分量各自量 |
| UINT8／Enum／bool／列舉字串／代碼集合（狀態） | Worker（平行） | 狀態變遷偵測（時間、從哪個值到哪個值、集合增減、各狀態的時間占比） |
| DiagnosticArray 這類「訊息的序列」 | Worker | 依名稱展開（`status.level` 對每個 `status.name` 各一項），只列有變化的 |

產物都在 `logs/analysis_jobs/<編號>/`：`job.json`、`events.jsonl`（進度）、`log_digest.md`、`topic_metadata.md`、`plan.json`、
`workers/W<n>_<topic>.md`（局部報告）與 `.transcript.md`（worker 的完整對話）、`report.md`（最後的報告）。
回傳給主對話的是報告的重點（以 `[PASS] 📊 數據診斷報告` 開頭：不再交給摘要 session，並存成 `#編號`，之後可以 `result_recall`）。

worker 的局部報告長這樣（frontmatter 由程式填，數字來自量測、不是模型抄的）：

```markdown
---
artifact: "worker_report"
topic: "/system/safety_command"
data_type: "state"
time_range: [1791967507.012, 1791967537.547]
analyzed_keys: ["primary_reaction", "winning_task", "winning_level"]
anomaly_detected: true
program_flags: ["W1 primary_reaction 狀態跳轉 1 次", "W1 winning_task 狀態跳轉 1 次"]
key_metrics: {"W1": {"_rate": {"messages": 301, "avg_hz": 10.0, "max_gap_sec": 0.101}, "primary_reaction": {"transitions": 1, "first": "INIT", "last": "NONE", "changes": ["INIT → NONE @1791967522.546327"]}}}
---

## 分析摘要
primary_reaction 從 INIT 轉向 NONE，發生在 +15.53s……
```

**幾個關鍵的設計**（細節與實測見〈[設計筆記 2.18](doc/設計筆記與已知限制.md)〉）：

- **時間戳由程式換算**：Orchestrator 只填訊號編號（L28），程式用去重後的時間戳算時間窗；worker 用 `--window W1` 這種編號（或不寫，系統帶入），不用抄 19 位數的時間。所有輸出的 `[+秒]` 都是「距離數據開頭」（Log、Topic、時間窗同一個基準）。
- **能由程式做的就不交給模型**：Log 去重、Key 的型別／維度／類別、統計數字、狀態跳轉、訊息中斷、異常指標、計畫的檢查（不存在的 L#／Topic、重複的 Topic 會具體列出、交回 Orchestrator 修一次，修不好由程式依關聯度補指派）。
- **worker 只能量自己的 Topic**：`--topic` 由系統固定、只准用量測技能；實測 e4b 常把動作的 JSON 寫進 `reply`，worker 的工具都是唯讀的量測，所以照做；一個 Key 都沒量時系統代選（狀態優先）。
- **「數據範圍」的程式檢查**：Log 說某個輸入沒有／逾時（`NO_CMD_VEL_RAW`、`IMU_TIMEOUT`…），數據裡卻沒有對得上的 Topic 時，程式保證報告把它列在「尚未確認」、信心最多 medium——小模型常拿名稱相近的輸出 Topic 當證據。

## 數據技能（依 `diagnostics_package/toolkit` 的人工工具重寫）

數據技能由主機端呼叫，讀檔與 ROS 2 反序列化在**目標容器內**執行（腳本連同共用模組 `_ros2_data_common.py` 經 stdin 打包送進容器，自動載入 /opt/ros 與 Workspace overlay；主機路徑依 bind mount 自動換成容器路徑）。
**數據**可以是實驗資料夾、bag 資料夾、切片資料夾、`.mcap`、實驗名稱或 `latest`；省略時用「目前分析的數據」（成功操作過的數據自動成為目前的數據，標題列顯示）。

| 技能 | 對應的 toolkit 工具 | 做什麼 |
|---|---|---|
| `mcap_recorder` | `mcap_recorder.py`、`ros2_toolkit.sh` 選項 1 | 定時錄製（`-s mcap`；`--preset core`＝toolkit 的預設核心 Topic），`/rosout` 經 `rosout_formatter.py` 存成 `rosout.log`，同樣的 `exp_*/bag/` 結構；**錄完自動建立全域 Topic Metadata 索引** |
| `rosout_parser` | `rosout_parser.py`、`mcap_slicer.py` 步驟 1～3 | Log 智慧過濾：去重成唯一訊號 L#（只差在數字也算同一句），篩層級／Node／關鍵字；預設用 bag 裡的 /rosout（時間跟其他 Topic 同一個時鐘），沒有就用 `rosout.log`；略過 rosbag2 自己的 Log |
| `mcap_analyzer` | `mcap_analyzer.py`（Metadata 摘要、欄位維度、原始值預覽） | 全域索引（時間範圍、每個 Topic 的型別、筆數、頻率、起訖、角色），`--topic` 看每個 Key 的型別／維度／類別，`--key --preview` 看原始值；索引快取在 bag 資料夾的 `topic_metadata.json` |
| `mcap_feature_measure` | `mcap_feature_measure.py`（`compute_features`） | 按需量測 Key 的特徵（同 toolkit：尖峰 >2.5σ、整數相異值 ≤10 當狀態跳轉），加上最大跳變、訊息頻率與中斷、依名稱展開的序列 |
| `mcap_slicer` | `mcap_slicer.py` 步驟 4～5 | 依 L# 或時間點前後各取幾秒（預設 5 秒），輸出 toolkit 格式的 `sliced_bag_*`（`metadata.yaml` 的 available_keys、`ai_slice_diagnostic_summary`）——toolkit 的 `mcap_analyzer.py` 讀得懂 |
| `analysis_run` | （新增） | 上面的多 agent 數據診斷 |

改得跟 toolkit 不一樣的地方：全部非互動（agent 要用參數）、字串欄位分成「列舉」（相異值少 → 狀態）與「自由文字」（只給 Orchestrator）、
`builtin_interfaces/Time` 不再被誤判成狀態（toolkit 的型別判斷用子字串 `int`，`builtin_interfaces` 也會中）、空的序列不會變成假的項目、
時間窗與時間的寫法比較寬鬆（`+0.75s`、`0~30`、`10 to 20` 都認得）、不認識的參數照認得的做完並附說明。

## 怎麼用

```bash
python3 web_console.py      # Web：http://127.0.0.1:8765（只綁本機）
python3 Agent_Runner.py     # CLI（同樣有 /analyze 與 /analysis_* 指令）
```

1. **設定**：右欄「📊 數據分析」→ ⚙️ 設定：預設容器（數據技能都在容器內執行，例如 `ros2_web_container`）、數據根目錄（錄製位置，空白＝在容器的 /workspace 底下找 `experiment_logs`）、worker 上限、時間窗前後秒數。各角色的模型在標題列的 🧠（主對話、分析 Orchestrator／Worker／Synthesizer；沒有另外設定時跟著主對話）。
2. **數據**：跟 AI 說「錄 30 秒的核心 Topic」（mcap_recorder），或用現有的實驗資料夾（「看一下 exp_20261014_084506」）。
3. **問問題**：直接跟 AI 說（「底盤為什麼在錄製中途停下來？」，它會選 analysis_run；只問一個值或 Log 時直接用對應的技能），或 `/analyze <問題>`，或按輸入框旁的 **📊 分析** 進入分析模式。
4. **看結果**：左欄是 AI 依報告的回答；右欄的進度卡片即時顯示每一個階段；「📊 數據分析」面板列出 Orchestrator 的計畫（相關的 Log 訊號、時間窗、每個 worker 的 Topic）、每個 worker 的局部報告與完整對話、最後的報告。

| 數據分析指令 | 作用 |
|---|---|
| `/analyze [問題]` | 直接交給 analysis_run（問題省略＝找出異常與根因）；報告照一般工具結果進主對話，可以接著追問 |
| `/analysis`、`/analysis jobs` | 看最近一次的報告／列出最近的 job |
| `/analysis_data <數據>`、`/analysis_root <路徑>`、`/analysis_container <容器>` | 目前的數據、數據根目錄、預設容器（`-` 清除） |
| `/analysis_model <orchestrator\|worker\|synthesizer\|all> <模型>`、`/analysis_workers N` | 各角色的模型（`-` 跟著主對話）、worker 上限 |
| `/analysis_mode on\|off` | 📊 分析模式（同輸入框旁的按鈕） |

| 數據分析設定（環境變數） | 預設 | 說明 |
|---|---|---|
| `AGENT_ANALYSIS_ORCHESTRATOR_MODEL`／`_WORKER_MODEL`／`_SYNTHESIZER_MODEL` | 同主模型 | 各角色的模型（Web 的 🧠 設定會存檔，`logs/analysis_settings.json`） |
| `AGENT_ANALYSIS_THINK` | 關 | Orchestrator 與 Synthesizer 的 thinking（模型支援才送） |
| `AGENT_ANALYSIS_DATA_ROOT` | 自動尋找 | 數據根目錄 |
| `AGENT_ANALYSIS_MAX_WORKERS`／`AGENT_ANALYSIS_PARALLEL` | 4／2 | 最多派幾個 worker／同時跑幾個（同一個模型在 Ollama 只有一個 slot 時，模型呼叫仍會排隊） |
| `AGENT_ANALYSIS_WORKER_STEPS` | 6 | 一個 worker 最多幾個動作 |

## 實測（2026-10-14，這台筆電：RTX 5060 Laptop GPU 8 GB、Ollama；數據 `toolkit/experiment_logs/exp_20261014_084506`，52 秒、10 個 Topic、/rosout 31 則）

| 項目 | 結果 |
|---|---|
| `analysis_run`（e4b，問「安全閘為什麼一開始進入 PROTECTIVE_STOP、什麼時候恢復」） | 63～74 秒、模型呼叫 16～18 次、4 個 worker（safety_gate_status、safety_command、cmd_vel、diagnostics_toplevel_state）；時間線正確（+0.75s 進入保護停止、+15.53s primary_reaction INIT→NONE、+15.54s mode→NORMAL）；「尚未確認」列出 /cmd_vel_raw 不在數據裡 |
| Web 的完整流程（HTTP 照瀏覽器的方式、auto 模式、e4b） | 主模型自己選 analysis_run（先載規格再執行）、進度即時推到右欄、面板讀得到 job；追問直接用報告回答 |
| gemma4:26b | 這台 GPU 8 GB 放不下（18.7 GB，大部分在 CPU）：Orchestrator 一次約 2 分鐘，20 分鐘內做不完；worker 的交叉比對看得出比 e4b 好，要在 ≥24 GB 的機器上量 |
| 主對話的路由（`evals/run_evals.py` 的 3 個 analysis 情境，e4b、harness 模式） | 3/3：根因問題用 analysis_run、單一數值用 mcap_feature_measure、Log 問題用 rosout_parser，回答引用工具的數字 |
| 數據技能的實機測試（`evals/analysis_tools_live.py --record`） | 14/14（含真的錄 6 秒、切片、錯誤處理） |
| 離線自我測試 | `analysis_selftest.py` 8/8、`main_selftest.py` 12/12、`v5_selftest.py` 8/8 |
| toolkit 相容 | toolkit 的 `mcap_analyzer.py` 讀得懂 mcap_slicer 產生的切片（包括巢狀的 Key） |

**已知的限制**：e4b 的 Synthesizer 會把「輸出 Topic 是 0」當成「輸入缺失」的證據（Log 的 NO_CMD_VEL_RAW 指的是 /cmd_vel_raw，它不在這份數據裡）——程式檢查會把這種情況列進「尚未確認」並把信心壓到 medium，但推理文字本身仍可能這樣寫；
worker 的平行度受 Ollama 的 slot 限制；Topic Metadata 的 Key 分類是抽樣（每個 Topic 120 筆）判斷的。

## 運作方式（harness，跟原本一樣）


![架構圖](doc/images/AI_agent_harness的說明.png)

1. 使用者下指令，主 session 每輪回一個 JSON `{thought, reply, action}`，harness **只看 `action`**，`reply` 裡的文字不會被執行。
2. `action` 填技能名稱 → 回傳該技能的規格文件（這一輪不執行）；填規格標明的腳本路徑 → 才真的執行。沒有「技能名稱 → 腳本」的對照表，模型一定要先讀規格。會改變實體狀態的動作（派工單、取消任務、建容器、容器內非唯讀的指令）執行前一律由程式請使用者確認，任何模式都一樣。
3. 每次執行的完整原文都存成 `#編號` 並顯示給使用者。回傳怎麼進主對話看上下文模式：
   - **harness**（預設）：超過 500 tokens 時交給一次性的獨立 session，依使用者的問題擷取重點；主對話只收到重點與下一步建議。
   - **claude_code**：原文直接進上下文，超過 3000 tokens 保留頭尾並標明省略的行號與存檔編號；要不要回存檔查、用什麼查，由模型自己決定。
4. 大量回傳會在 `logs/tool_results/tools_use_index.md` 留下一句話描述（整句保存、不截斷），附在 system prompt 尾端；Web 附圖的影像分析也存成 `#編號` 記進這裡（標〔附圖分析〕）。使用者之後（包括下次啟動）追問舊資料時，模型執行 `result_recall <編號>`，讓獨立 session 回到原文重新提煉；問題要一起看幾份時，一次給多個編號。
5. system prompt 只放不常變的內容（KV cache 才能重用）；工作目錄、目標容器、核准的計畫這些常變的小東西，每次接在送出內容的最後面。
6. 上下文超過水位時，舊對話會融合成一份滾動摘要；使用者的原話由程式逐字保留，被壓掉的對話也存成 `#編號`，需要時可以取回。對話片段的描述只講那一段談了什麼、決定了什麼，列在 system prompt 的「過去的對話片段」一節，跟工具回傳分開列、保留上限也分開算（編號共用同一個序列，取回一樣用 `result_recall`）。claude_code 模式會先把舊的工具回傳清成「原文在存檔」的佔位，不夠才摘要。

![一回合的狀態機](doc/images/AI_agent_harness的狀態轉移.png)

![工具回傳管線](doc/images/AI_agent_harness的工具回傳管線.png)

每一步對應到哪個函式、狀態存在哪裡、要改某件事該看哪裡，見〈[架構說明](doc/架構說明.md)〉。

## 主對話的程式把關（2026-10-08，CLI、Web、評測共用）

- **卡住偵測**：同一個回合裡同樣的動作（技能＋參數）得到同樣的結果——第二次在工具回傳後面附「不要再重複、換個做法」，第三次加強提醒，第四次（或同一個錯誤第四次）停下這一回合、顯示 ⛔ 交回給你。
- **沒有執行卻宣稱做完**：這一回合一個工具都沒有執行，回覆卻說「已經重新啟動了／已建立…」，提醒 AI 一次（條件句、疑問句、否定句不算）。
- **路徑找不到時列出相近的路徑**：`view_file`、`list_dir`、`change_dir` 找不到時，列出大小寫或拼字最接近、或同名在別的目錄的路徑。
- **技能用錯時直接說該用哪個**：`docker_runcmd` 被拿來跑 `docker start／restart` 時，直接說明要用 `host_runcmd` 在主機上執行。

## 快速開始

**需要**：已在執行的 [Ollama](https://ollama.com/)（先 `ollama pull gemma4:e4b`）、Python 3.10+ 與 `pip install ollama`。附圖功能需要 `Pillow`；容器、ROS2 與數據技能需要宿主機的 `docker` CLI，數據技能另外需要一個有 ROS 2、`python3-mcap`（`pip install mcap`）與 PyYAML 的容器（要讀自訂訊息型別時容器裡要有建好的 Workspace）；調度系統技能需要 fih_rmf_system 的 web_console（:8020），離線時可用 `skills_system/scripts/mock_server.py` 代替。

```bash
python3 web_console.py      # Web：http://127.0.0.1:8765（只綁本機）
python3 Agent_Runner.py     # CLI
```

Web 左欄是對話，右欄是系統與工具回傳（另一個分頁是「📊 數據分析」面板）：每次工具回傳有兩張卡，一張是完整原文（附 `#編號`，可點開），一張是「AI 實際收到的內容」。輸入框打 `/` 會跳出指令與技能選單，旁邊有附圖（📷）、Plan 模式（📝）與 📊 分析模式按鈕；標題列顯示目前的目標容器、ROS 2 Workspace 與目前分析的數據。

| 常用指令 | 作用 |
|---|---|
| `/auto on` | 工具結果自動加入、連續執行到做完（Web 最多 25 輪） |
| `/hybrid on` | 每次問要不要加入，不論選哪個都繼續推論（預設的 manual 也會問，但選「不加入」就結束） |
| `/plan on` | 下一個任務先由 AI 列步驟草稿，核准（y）後才執行；草稿由系統保存，AI 只會改你提到的那幾條 |
| `/plan add`、`/plan edit N`、`/plan del N`、`/plan move N M`、`/plan show` | 直接改計畫草稿（不經過 AI）；沒開 `/plan on` 也能自己一條條列 |
| `/plan_exec_guard on` | 計畫執行中：計畫外、會改變狀態的技能不執行，AI 停下來會自動提醒繼續，連續失敗 3 次退出計畫（預設關＝沒有限制） |
| `/context_mode harness`、`/context_mode claude_code` | 切換上下文模式（差別見〈[架構說明 1.1](doc/架構說明.md#11-兩種上下文模式context_mode-harnessclaude_code)〉） |
| `/guard on`、`/guard off` | 執行前確認的開關（預設開；關閉只限這次執行） |
| `/skill <名稱>`、`/skills` | 手動載入某技能的規格／列出所有技能 |
| `/summarize off` | 大量回傳只給成功／失敗，不摘要 |
| `/make_skill <名稱>`、`/trajectory` | 把做對的對話整理成流程技能的規格（步驟只呼叫既有技能，不產生腳本）／查看操作軌跡 |
| `/compress`、`/clear` | 手動壓縮上下文／清空對話 |
| `/analyze [問題]`、`/analysis_help` | 數據診斷（見上面〈怎麼用〉）／數據分析的全部指令 |
| `/menu`（Web） | 列出全部指令 |

| 常用設定（環境變數） | 預設 | 說明 |
|---|---|---|
| `WEB_CONSOLE_MODEL` | `gemma4:e4b` | Web 用的主模型（CLI 寫在 `main()`）；在標題列 🧠 設定過之後以畫面上的設定為準（`logs/model_settings.json`） |
| `AGENT_MAIN_THINK` | 關 | 主對話的 thinking 模式（Web：🧠 或 `/think main on`；數據分析的角色用 `/think orchestrator on` 這類） |
| `WEB_CONSOLE_HOST`／`WEB_CONSOLE_PORT` | `127.0.0.1`／`8765` | Web 綁定位址 |
| `AGENT_NUM_CTX` | `32768` | context 上限；記憶體小的設備可調低 |
| `AGENT_CONTEXT_MODE` | `harness` | 啟動時的上下文模式（`harness`／`claude_code`） |
| `AGENT_GUARDED_SKILLS` | 派工單、取消、刪逾時任務、建容器、容器內指令 | 執行前要確認的技能（逗號分隔） |
| `AGENT_SUMMARY_MODEL` | 同主模型 | 獨立 session 用的模型（沒設定時跟著主對話的模型，在 🧠 換主模型時一起換） |
| `RMF_WEB_CONSOLE_URL` | `http://localhost:8020` | 調度系統的位址 |
| `VISION_MODEL` | `gemma4:e4b` | 附圖分析用的模型 |

其他門檻與保留上限見〈[架構說明 §10](doc/架構說明.md#10-常數與環境變數)〉。

## 技能一覽

| 分類 | 技能 |
|---|---|
| ROS 2 數據解析 | `analysis_run`（多 agent 數據診斷）、`mcap_recorder`、`rosout_parser`、`mcap_analyzer`、`mcap_feature_measure`、`mcap_slicer` |
| 檔案系統 | `list_dir`、`search_text`、`find_file`、`change_dir`、`view_file`、`code_ast_reader`、`host_runcmd`、`file_ops`、`csv_query` |
| 容器 | `docker_containers`、`docker_images`、`docker_est`、`docker_open`、`docker_runcmd`、`docker_ctl`、`ROS2_workspace_env` |
| ROS2（容器內） | `ROS2_domain_id`、`ROS2_topic_list`、`ROS2_topic_echo`、`ROS2_node_list`、`ROS2_node_info`、`ROS2_param`、`ROS2_topic_pub` |
| 調度系統 | `workpackage_send`、`workpackage_status`、`workpackage_cancel`、`overpending_cancel`、`semantic_map`、`rmf_handshake` |
| 多步驟維運任務（v5） | `ops_run`（規劃 → 確認整份計畫 → 每一步派 worker、程式檢查） |
| 多模態 | `stt_engine`、`image_inspect` |
| 工具結果存檔 | `result_recall`、`result_grep`、`result_view`、`result_list` |
| 記憶 | `modify_memory` |

索引在 [`skills_system/SKILLS.md`](skills_system/SKILLS.md)，每個技能的規格在 `skills_system/tools/<name>.md`；各技能的參數與重點見〈[設計筆記 §3](doc/設計筆記與已知限制.md#3-技能清單全部功能)〉。

## 目錄結構

```
Coding_agnet/            （資料夾名稱沿用；內容是數據解析 agent）
├── Agent_Runner.py     # CLI 入口（幾行，實作在 agent_core/）
├── web_console.py      # Web 入口（幾行，實作在 web_app/）
├── agent_core/         # 核心：SkillAgent（由各 mixin 組成）、回覆協議、常數、CLI——唯一的核心邏輯來源；
│                       #   analysis_job.py＝數據解析的 Orchestrator／Workers／Synthesizer，ops_job.py＝多步驟維運任務
├── web_app/            # Web 介面（純標準庫）：狀態、回合流程、slash 指令、HTTP、static/index.html；analysis.py＝📊 數據分析面板的後端
├── AGENT.md            # system prompt 主體：角色、JSON 回覆格式、執行協議、安全原則、記憶協議
├── analysis_agents/    # 數據解析三個角色的 system prompt（orchestrator.md、worker.md、synthesizer.md，可以直接改）
├── ops_agents/         # 多步驟維運任務的規劃與 worker 的 system prompt
├── context_modes/      # 兩種上下文模式各自的規則（harness.md、claude_code.md），接在 AGENT.md 後面
├── Memory.md           # 全域長期記憶（每輪常駐）
├── skills_system/
│   ├── SKILLS.md       # 技能索引（常駐 system prompt）
│   ├── tools/          # 各技能的規格文件（按需載入）
│   └── scripts/        # 各技能實際執行的腳本與共用模組（_ros2_data_common.py＝數據技能的共用層：送進容器執行、Log 去重、Metadata、特徵量測）
├── vision/             # 多模態影像 library（擷取、推論、前端框選）
├── subagent/           # 獨立的框選截圖 → 視覺推論小工具
├── evals/              # 評測：主對話（run_evals.py、scenarios.py、main_selftest.py）、數據解析（analysis_selftest.py、analysis_tools_live.py、
│                       #   analysis_fixtures/）、多步驟維運（v5_selftest.py、ops_suite/）
├── AI_agent_harness_geema4_26b/  # 舊版（沒有 coding 的）harness 副本，預設 gemma4:26b，保留參考
├── doc/                # 架構說明、設計筆記、圖（.puml 與產生器）
└── logs/               # 執行時產生：工具回傳存檔、檢索清單、軌跡、摘要歸檔、模型呼叫耗時、analysis_jobs/、ops_jobs/（.gitignore）
```

## 未來規劃的注意事項

接下來的方向是**數據解析**與**執行設計好的技能與固定技能組**，而不是 coding 那種開放式任務：調度系統上的人機交握，以及引入心跳機制後的定時狀況回報、定期執行某些技能。心跳機制的起因是：未來會有來自不同地方的 VLM 語意資訊（例如各處攝影機的影像分析結果），需要 AI agent 分析、彙整之後才能回報，所以不是單純的定時腳本。設計時要注意：

- **模型選擇要在目標設備上量過再決定**：在 RTX 5090 上 gemma4:26b 兩種上下文模式都比 e4b 好、甚至略快（〈[設計筆記 2.11](doc/設計筆記與已知限制.md)〉與 `evals/results/`），但 26b 在弱設備上的主要代價是**讀 prompt**，不是產出：這次讀 prompt 就慢了 3 倍，而 system prompt 常駐約 5～8K tokens。另外 26b 模型本身 18 GB、e4b 9.6 GB，裝得下是前提。在目標設備上用 `evals/run_evals.py --model …` 與 `evals/perf_report.py` 實際量過才準；設備較弱時，e4b 搭配 harness 模式的時間與推論成本優勢比較大。
- **定時任務不一定要經過模型**：「定期執行某些技能」的步驟如果是固定的，排程直接執行腳本最穩、最省（`/make_skill` 產生的流程技能要由模型照步驟做，適合有人在場、要確認的流程；固定的多步驟要不經過模型，就寫成一支腳本）。模型只負責解讀結果、判斷異常、彙整多個來源（包括 VLM 的語意資訊）、寫報告，推論成本和出錯機會都會少很多。
- **心跳機制要注意上下文會越積越多**：長時間定時執行，每次都接在同一段對話後面，上下文會一直變長、壓縮一直觸發。建議每次心跳開一個乾淨的 session，只帶上次的結論（加上這次收到的 VLM 資訊與技能結果）。
- **無人值守時，執行前確認怎麼辦**：定時執行沒有人按「同意」。要事先決定：定時任務只准唯讀技能，或者給一份事先核准過的白名單。這一點現在的設計還沒處理（`guard.py` 目前一律要人確認）。
- **人機交握的時間限制**：現場等回應通常有時限，要把每個動作的延遲算進去。harness 模式大量回傳時會多一次獨立 session，在弱設備上可能要好幾秒。

## 文件

- 〈[架構說明](doc/架構說明.md)〉：`agent_core/` 與 `web_app/` 的完整解析，含每個模組負責什麼（先從第 0 節「工具回傳什麼時候會被摘要」看起）
- 〈[設計筆記與已知限制](doc/設計筆記與已知限制.md)〉：各機制的理由與實測數據、完整技能清單、驗證方法、已知限制、未來方向
- 〈[長期願景](doc/長期願景.md)〉：AGV/AMR 車隊調度場景的構想（尚未實作）
- 〈[評測](evals/README.md)〉：怎麼跑、情境清單、怎麼加情境、怎麼讀報表
- 〈[benchmark_study](benchmark_study/README.md)〉：2026-10 的完整評測——《評估報告》（結論、使用建議、改進路線圖）、《技術報告》（方法、全部結果與統計）、用到的資料集、參考文獻（論文 PDF）、原始紀錄與分析程式
- 〈[benchmark_study_3](benchmark_study_3/README.md)〉：第三次評測（2026-10-10）——小而有測試的專案（寫測試＋覆蓋率、修多個 bug、補回跨檔功能、Aider polyglot，Python／C++ 62 題）與非編碼的維運任務（目錄與文件、Docker、ROS 2、調度交握、複合任務：50 個情境＋20 個保留情境，在隔離的 Docker-in-Docker 沙盒裡真的執行）；v5 的改動：覆蓋率、只寫測試的工作、回歸檢查、非編碼的 orchestrator（ops_run）與維運技能
- 第二次評測 benchmark_study_2（SWE-bench，coding）隨 coding agent 移到 `/home/david/Coding_agent_harness/benchmark_study_2/`；benchmark_study 與 benchmark_study_3 是拆分前的評測，內容同時有 coding 與非 coding 的部分，保留為歷史紀錄。
- 圖的來源在 `doc/*.puml`，用 `python3 doc/流程圖產生器.py` 重新產生
