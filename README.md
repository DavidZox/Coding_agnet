# Data Analysis Agent（ROS 2／MCAP 智慧診斷）

以本地 Ollama 模型（預設 `gemma4:e4b`）為核心的 **ROS 2 數據解析 agent**：錄製 MCAP 與 /rosout、把重複的 Log 去重成唯一訊號、
**由程式量完整段數據的全部 Topic 與全部 Key**，整理成有編號的事實，再用 **Orchestrator（挑相關的 Log、分派要說明的 Topic）→ Workers（說明）→
Synthesizer（重點）→ Orchestrator（檢查要不要補派）** 的多 agent 協同，把一段數據整理成**事實報告**：量到什麼、什麼時候、Log 說了什麼。
只要有 .mcap 就能用；不判斷原因（原因要對照源碼另外分析）。
harness 本身（技能系統的索引＋按需載入的規格＋既有腳本、上下文管理、執行前關卡、記憶、Plan 模式、CLI 與 Web Console）跟原本一樣，
機器人維運的技能（容器、ROS 2、調度系統、ops_run）也都還在。決策模型只用本地模型。

> **2026-10-14 拆分**：這個資料夾原本同時有 coding 與非 coding 兩套 harness。coding 的部分（coding orchestrator、`code_*` 技能、Coding 面板、
> coding 評測、DevBench／SWE-bench）已經整個移到 **`/home/david/Coding_agent_harness`**（git clone，保留完整歷史）；這裡只留非 coding 的部分，
> 往數據解析 agent 發展。數據技能依 `diagnostics_package/toolkit` 的人工工具重寫（見下面〈數據技能〉）。

## 數據解析的多 agent 協同（`analysis_run`）

只要有 .mcap 就能用：多個 agent 一起把一段數據整理成**事實報告**——量到什麼、什麼時候、Log 說了什麼。報告不判斷原因：
原因要對照源碼另外分析（第九輪以前的源碼脈絡與因果推論，留在 [`root_cause_reference/`](root_cause_reference/README.md) 給之後的根因 agent）。
一次最多分析 3 分鐘的數據；更長的先用 mcap_slicer 切出要看的那段（之後要分析更長的時間跨度，是多組各管一段、再往上整合）。

```
使用者 ─問題─▶ 主對話的 AI（analysis_run）／/analyze 指令／📊 分析模式
                    │  需要的話先錄：mcap_recorder；超過 3 分鐘的數據先用 mcap_slicer 切
                    ▼
① 資料預備與事實（程式）　 Log 去重成 L#；量全部 Topic 的全部 Key（mcap_analyzer --facts），整理成 T#＝Topic、E#＝事件、時間線與前後 1 秒的對照
② Orchestrator（模型）　　　理解問題、挑相關的 L#、把有變化的 Topic 分派給 worker 說明
③ Workers（模型）　　　　　每個 Topic 一次呼叫：看那個 Topic 的事實與訊息定義（.msg 的註解），一則一則說明（引用 E#／T#）
④ Synthesizer（模型）　　　整段數據的重點：程式給的每個重要時間點至少一則（引用 E#／L#／T#；時間、那一刻的事件與 Log 的內容由程式補上）
⑤ Orchestrator 檢查（模型）　相關的 Log 前後有變化、還沒有說明的 Topic，決定要不要補派（最多一輪）
⑥ 報告（程式組合）　　　　　report.md、主對話的 #編號；主對話依報告回答時，程式核對不把先後寫成因果；Web 面板看每一步
   程式核對（③④）：編號要存在、不寫原因與推測、「中斷／開始發布／停止發布」要引用那種事件、寫的時間對得上、太長 → 只交回有問題的那幾則
```

![數據分析的流程](doc/images/數據診斷的流程.png)

### 每一步的細節

圖的顏色：藍＝程式（量測、整理事實，不呼叫模型）、橘＝模型、綠＝程式核對。26b 在 RTX 5090 上：這台錄的 14 份（30～180 秒）一次約 9 秒、模型呼叫約 6 次；產生器的錄製（30～178 秒、最多 3 個子系統）約 8～13 秒、7 次。

**收到問題**：主對話的 AI 呼叫 `analysis_run`（偽技能，在本程式內執行），或 Web 的分析模式、`/analyze <問題>`。參數：`--data`（實驗資料夾、bag、
切片、實驗名稱、latest；省略＝目前的數據）、`--topic`（一定要說明的 Topic）、`--workers`、`--rounds`（1＝不補派）。問題省略＝這段錄製期間發生了哪些狀態變化。

**① 資料預備與事實（程式，不呼叫模型）**
- Topic Metadata：每個 Topic 的型別、筆數、頻率、起訖，每個 Key 的類別與維度，每個型別的訊息定義（MCAP 裡的 .msg，含註解）；錄製時建好的索引直接讀。
- Log 去重：/rosout 合併成唯一訊號 L#（層級、節點、次數、每一次的時間戳）；MCAP 裡每一則 Log 都帶 file、function、line，報告照列成
  「＠檔名:行 函式」（之後要做根因或改 code 就從這裡接）。略過 rosbag2 自己的 Log。
- **量全部 Topic**（`mcap_analyzer --facts`）：一次讀完整份數據，每個可以解碼的 Topic 量全部的 Key（數值、向量、狀態、鍵值、陣列；header 與
  共變異數除外）與訊息流，快取在 bag 資料夾的 `topic_facts.json`。不靠模型挑 Topic、挑 Key，同一份數據每次一樣。
  - 發布方式由時間與內容判斷：固定頻率／狀態改變時才發布／不定期／只有一兩則。**只有固定頻率的 Topic 判斷訊息中斷**（間隔超過週期 3 倍、
    ≥0.5 秒）與中途開始／停止發布；其他的列出每一則的時間，第一則在錄製開始 5 秒之後的列成事件「第一則訊息」。
  - 狀態跳轉、只有幾種值的數值（速度指令）的每一次切換、連續變化的數值的範圍、尖峰（跳出去又回來：跟前後 9 筆的中位數差超過殘差 MAD 的
    6 倍、又回到原來的水準、而且夠陡）。
- **有編號的事實**：T#＝每個 Topic 一列（類別、發布、變化、到最後的值、沒有變化的項目）；E#＝事件（同一則訊息裡一起改變的項目算一個事件，
  全部列出）；時間線＝事件＋Log（WARN 以上、規劃挑的、前後 1 秒內有事件的），每一列附前後 1 秒內的對照（只寫早或晚幾秒，不代表誰造成誰）；
  同時發生的變化（0.1 秒內）、前後沒有任何 Topic 事件的 Log、沒有量的 Topic（沒有訊息、無法解碼、ROS 2 框架的 Topic）、一句話的總覽。
- 數據超過 3 分鐘、或沒有可以分析的 Topic 就回 `[ERROR]`，說明要怎麼做。
- 產物：`topic_facts.json`、`topic_metadata.md`（全部 Topic 的事實）、`log_digest.md`。

**② Orchestrator：規劃（模型）**
- 看得到：問題、去重後的 Log（最多 60 個訊號，WARN 以上全部）、全部 Topic 的事實總表（T#、類別、發布、事件數）、限制（最多 4 個 worker）。
- 輸出：對問題的理解、相關的 L#、要說明的 Topic（名稱或 T#）與子任務。
- 程式檢查：L# 要存在、Topic 要在事實裡、不重複、不派 /rosout 與框架的 Topic、不超過上限；沒有變化的 Topic 不派（程式已經寫了「沒有變化」，
  不算問題）；有問題列出具體的問題交回修一次，還是沒有可用的指派由程式依「事件在相關的 Log 前後」的次數補指派。
- worker 上限只決定「誰來說明」：沒有派到的 Topic 照樣有完整的事實與事件。
- 產物：`plan.json`、`prompts/orchestrator.md`。

**③ Workers（每個 Topic 一次模型呼叫，同時 2 個）**
- 看得到：子任務（L# 由程式換成時間）、自己那個 Topic 的事實與事件（E#）、訊息定義（.msg 原文含註解，用來說明欄位與值的意思）。
- 看不到：Log、其他 Topic、使用者的問題與 Orchestrator 的理解（實測理解裡的推測會被 worker 照著寫成事實）。
- 輸出：1～5 則說明，每則 `{refs, text}`：refs 指到這個 Topic 的 E#／T#，text 一兩句話；時間不用寫，程式依 refs 補上。
- 程式核對每一則（跟 Synthesizer 同一套，見下面）；有問題只交回那幾則，通過的保留、修好的併進來；還是太長的截到完整的句子；還是不行的不列。
- 產物：`workers/W<n>_<topic>.md`（frontmatter 有說明、事件編號、沒通過的）、`prompts/worker_W<n>.md`。

**④ Synthesizer：重點（模型）**
- 看得到：程式整理的事實（有變化的 Topic 一行一個、時間線最多 60 列、規劃挑的 L#）、**重要的時間點清單**（M#：事件與 WARN 以上的 Log，
  1 秒內的算一個）、各 worker 的說明；看不到問題與 Orchestrator 的理解。
- 輸出：重點一則一則，每則 `{refs, text}`：refs 指到 E#／L#／T#，text 寫這一刻的重點；**引用的事件的完整內容與每則 Log 由程式列在那一則下面**，
  模型不用逐項抄數值與 Log。**每個重要的時間點至少一則**：寫完程式核對漏掉的時間點，跟有問題的那幾則一起交回一次，還是漏的由程式補一則
  （標「程式列出」）；每個時間點其他的事件與 Log 掛在第一則引用到它的重點下面（那一刻的事實由程式列全）。則數上限跟著清單（時間點＋2，
  至少 8、最多 24）。
- 程式核對每一則：編號要存在；太長（寫到格式的上限 300 字＝失控、被截斷）；寫了原因、誰造成誰、推測（`_NOT_FACT_WORDS`，Log 原文本來就有的不算）；
  寫了「中斷」「開始發布」「停止發布」「恢復發布」，引用的事件裡卻沒有那種事件；寫了時間（+秒），引用的事實裡沒有這個時間。有問題只交回
  那幾則（`prompts/synthesizer_2.md`，修正版重寫的不收），太長的截到完整的句子，還是不行的不列（報告註明幾則、`summary_checks` 有原文）；
  一則都沒有通過時由程式依事實列出重點（一個時間點一則）。

**⑤ Orchestrator 檢查：要不要補派（模型；最多一輪，`--rounds 1`＝不補）**
- 候選：WARN 以上或規劃時挑的 Log，前後 1 秒內有事件、還沒有 worker 說明的 Topic；沒有候選就不問。
- 輸出：要補派的 Topic（最多 2 個），每一項寫它對應哪一則 Log。程式核對：Topic 要在候選裡、Log 要是它前後的那幾則；不符合的不補。
- 補派的 worker 說明完，回到 ④ 再寫一次重點；補派之前的報告留成 `report_r1.md`。

**⑥ 報告（程式組合）**：重點（程式的總覽＋重點，時間、引用的事件與 Log 的內容由程式補上）、各 Topic 的結果、Workers 的說明、時間線（附編號）、
同時發生的變化、前後沒有任何 Topic 事件的 Log、沒有量的 Topic、分析過程 → `report.md`（Frontmatter Markdown）。重點回到主對話
（以 `[PASS] 📊 數據事實報告` 開頭：不再交給摘要 session，存成 `#編號`，之後可以 `result_recall`），主對話的 AI 依報告回答；問「為什麼」時照事實
說明發生了什麼與先後順序，並說明原因要對照源碼。**主對話的回答也核對**：寫了報告裡沒有的因果動詞（導致、造成、觸發…）就提醒一次。

**報告長這樣**（exp_5090_lidar：LiDAR 斷線 4 秒，安全閘鎖住到錄完；26b，摘錄）：

```markdown
## 重點
**總覽（程式）**：6 個 Topic：有事件的 5 個（開始或停止發布 1、狀態改變 5）、只有數值連續變動的 0 個、沒有變化的 1 個、沒有量的 4 個；Log 8 個訊號（WARN 以上 5 個）

- **+16.50s**　/diagnostics 開始發布（E1）
  - E1 /diagnostics：開始發布（之前沒有訊息）
- **+16.53s**　同一時間 5 則 Log（ERROR 3、WARN 2）；安全閘進入 ESTOP_LATCHED，/system/safety_command 的 primary_reaction 變為 HARD_STOP，…（L16、L17、L18、L19、L20、E2、E3、E4、E5）
  - E2 /diagnostics_agg：status.level[/Sensors/Other Sensors]：0 → 2；status.level[/Sensors/Perception/LiDAR]：0 → 2；…
  - E4 /system/safety_command：primary_reaction：NONE → HARD_STOP；winning_level：0 → 2；winning_reason："" → LiDAR 數據中斷，視覺失明，採取硬煞停；…
  - E5 /system/safety_gate_status：mode：NORMAL → ESTOP_LATCHED；estop_latched：False → True；…
  - L16 ERROR system_health_monitor：event=MON_FAULT_RAISED code=0x04100101 severity=ERROR task="/Sensors/Other Sensors/sensor_lidar_front"
  - …
- **+20.51s～+20.53s**　同一時間 2 則 Log（INFO 2）；/diagnostics 的 sensor_lidar_front 狀態回到 OK，…（E6、L21、L22、E7、E8、E9）
  - …
- **整段**　到數據結束時 /system/safety_gate_status mode 仍是 ESTOP_LATCHED，/system/safety_command 的 primary_reaction 仍是 HARD_STOP（T2、T3、T4、T5）
- **整段**　/cmd_vel 整段沒有變化（T6）
```

| 編號 | Topic | 類別 | 發布 | 變化 | 到最後 |
|---|---|---|---|---|---|
| T1 | /diagnostics | 開始或停止發布、狀態改變 | 118 則，固定頻率（週期 0.2003 秒）；+16.50s 才開始發布 | status.level[sensor_lidar_front]：2 → 0（+20.51s）；… | status.level[sensor_lidar_front]＝0（開頭 2）；… |
| T5 | /system/safety_gate_status | 狀態改變 | 只有：2 則（+0.00s、+16.53s） | mode：NORMAL → ESTOP_LATCHED（+16.53s）；estop_latched：False → True（+16.53s）；… | mode＝ESTOP_LATCHED（開頭 NORMAL）；estop_latched＝True（開頭 False）；… |

| 編號 | 時間 | 來源 | 事件 | 前後 1 秒內 |
|---|---|---|---|---|
| L16 | +16.53s | L16 ERROR system_health_monitor | event=MON_FAULT_RAISED code=0x04100101 … ＠system_health_monitor_node.cpp:165 logEvent | E2 /diagnostics_agg（同時）、E3 /diagnostics_toplevel_state（同時）…共 5 個 |
| E5 | +16.53s | T5 /system/safety_gate_status | mode：NORMAL → ESTOP_LATCHED；estop_latched：False → True；… | L16（同時）、L17（同時）、L18（同時）…共 5 個 |

**程式做的與模型做的**

| 誰 | 做什麼 |
|---|---|
| 程式（不呼叫模型） | Log 去重、時間換算、量全部 Topic 的全部 Key、事實的整理（編號、類別、事件、到最後的值、時間線、時間上的對照、同時發生）、說明與重點的時間、重點引用的事件與 Log 的內容、計畫與補派的檢查、子任務的 L# 換成時間、報告組合 |
| 程式核對（只交回有問題的那幾則） | worker 的說明與 Synthesizer 的重點：編號要存在、不寫原因與推測（同一張詞表）、用詞跟引用的事件一致（沒有引用中斷就不能寫中斷）、寫的時間對得上、一則不能寫到上限；主對話依報告的回答不寫因果 |
| 模型 | Orchestrator：理解問題、挑 Log、挑要說明的 Topic、決定要不要補派；Worker：說明一個 Topic 的事實（可以用訊息定義的註解）；Synthesizer：挑重點、寫成文字 |

**設定與開關**（預設值）：最多 2 輪（可以補派一輪；⚙️ 設定或 `AGENT_ANALYSIS_ROUNDS`）、worker 上限 4／同時 2、
一次最多 180 秒（`AGENT_ANALYSIS_MAX_SECONDS`）；各角色的模型沒另外設定時跟著主對話。設定檔（`logs/analysis_settings.json`）只存跟預設不同的值。

每一步留下什麼（`logs/analysis_jobs/<編號>/`）：

| 步驟 | 誰做 | 產物 |
|---|---|---|
| ① 資料預備與事實 | 程式 | `topic_facts.json`（全部 Topic 的量測）、`topic_metadata.md`（全部 Topic 的事實總表）、`log_digest.md`（去重後的 Log，每則附 ＠檔名:行 函式；rosbag2 自己的 Log 也列出並標明） |
| ② Orchestrator | 模型＋程式檢查 | `plan.json`（對問題的理解、相關訊號、每個 worker 的 Topic 與子任務；沒有派的 `skipped`、補派的 `followups`） |
| ③ Workers | 模型＋程式核對 | `workers/W<n>_<topic>.md`（說明；frontmatter 有 tid、類別、事件編號、notes、交回過的 `issues`、沒通過的 `dropped`、補派的 `round` 與 `signal`） |
| ④ 重點 | 模型＋程式核對 | `job.json` 的 `report`（重點、各 Topic 的結果、時間線…）、`summary_checks`（交回過的、救回的、沒通過的）；`prompts/synthesizer.md`（_2＝修正那一次） |
| ⑤ 檢查 | 模型＋程式檢查 | `job.json` 的 `checks`（候選、有沒有問、補派了什麼、程式檢查）；`report_r1.md`（補派之前的報告）；`prompts/orchestrator_check.md` |
| ⑥ 報告 | 程式 | `report.md` |
| 全程 | 程式 | `job.json`（狀態、計畫、事實、每個 worker 的說明、報告）、`events.jsonl`（進度，Web 的卡片與面板讀它）、`prompts/<角色>.md`（交給模型的完整輸入，對照與重播用） |

| 資料類型 | 誰處理 | 怎麼處理 |
|---|---|---|
| String／Log（/rosout、自由文字） | 程式去重、**Orchestrator 看** | rosout_parser 去重成唯一訊號；自由文字欄位（含 JSON 字串）只量訊息流 |
| Scalar／Float／Vector（數值） | 程式量、Worker 說明 | 極值與時間、均值、標準差、尖峰（跳出去又回來）；只有幾種值的（速度指令 0／0.1）列每次切換；向量每個分量各自量；陣列量長度與元素平均 |
| UINT8／Enum／bool／列舉字串／代碼集合（狀態） | 程式量、Worker 說明 | 狀態跳轉（時間、從哪個值到哪個值、集合增減、各狀態的時間占比）；同一則訊息裡一起改變的項目合成一個事件 |
| DiagnosticArray 這類「訊息的序列」 | 程式量、Worker 說明 | 依名稱展開（`status.level` 對每個 `status.name` 各一項），只列有變化的，沒變的記數量與值 |

worker 的說明長這樣（同一份數據的 W1 /diagnostics；frontmatter 由程式填，時間由程式依編號補上；節錄）：

```markdown
---
artifact: "worker_notes"
topic: "/diagnostics"
tid: "T1"
message_type: "diagnostic_msgs/msg/DiagnosticArray"
tags: ["開始或停止發布", "狀態改變"]
events: ["E1", "E6"]
notes: [{"refs": ["E1"], "text": "這個 Topic 從 +16.50s 開始發布", "t": 16.504, "time": "+16.50s"}, …]
---

## 說明
- **+16.50s**　這個 Topic 從 +16.50s 開始發布（E1）
- **+20.51s**　sensor_lidar_front 的 status.level 從 2 變成 0，status.message 從 LiDAR disconnected 變成 OK，且 error_code 從 0x04100101 變成 0x00000000（E6）
- **整段**　這個 Topic 為固定頻率發布，到數據結束時 sensor_lidar_front 的 status.level 為 0，status.message 為 OK（T1）
```

**幾個關鍵的設計**（理由與實測見〈[設計筆記 2.18](doc/設計筆記與已知限制.md)〉）：
- **事實由程式量全部，模型只「選」和「說明」**：時間、數值、跳轉、開始／停止、到最後的值、時間上的對照，全部從量測結果直接算；
  哪個 Topic、哪個 Key 都量，worker 上限只決定誰來說明——第十輪 worker 上限 4 時時間線缺的全是沒派到的 Topic，第十一輪起不會了。
- **一則一則、有編號的輸出，不靠文字的長度**：說明與重點都是 `{refs, text}`，時間與引用的事件、Log 的內容由程式補（模型不用逐項抄數值）；一則寫到上限只影響那一則
  （截到完整的句子），不會像一整段摘要被截斷在半句。重點的則數上限跟著事實的多寡（重要的時間點各一則）。交回修正只交回有問題的那幾則，
  通過的由程式保留。
- **用詞跟引用的事件綁在一起**：寫「中斷」「開始發布」「停止發布」要引用那種事件——整段持續發布的 Topic 寫成開始與停止，引用的編號裡沒有
  start／stop 就擋得下。發布方式由時間與內容判斷，只在狀態改變時才發布的 Topic 不會被算成訊息中斷。
- **推測不進事實那一層**：worker 不給問題與 Orchestrator 的理解；說明與重點用同一張詞表核對；主對話依報告的回答也核對因果動詞。
- **對照只看時間**：Log 與 Topic 的事件前後 1 秒內就列在一起，對不上的照實標出，不硬對齊。
- **回歸評分只評事實**：`evals/analysis_regression.py` 用錄好的數據與自動產生的評分標準評分（時間線該有的事件、Topic 類別、用詞、時間有沒有根據、
  重點有沒有引用關鍵的事件），不需要人工標註；大量數據用隨機情境的錄製產生器（`evals/datagen/`，六個套件的模擬，評分標準由注入的事件產生）。

## 數據技能（依 `diagnostics_package/toolkit` 的人工工具重寫）

數據技能由主機端呼叫，讀檔與 ROS 2 反序列化在**目標容器內**執行（腳本連同共用模組 `_ros2_data_common.py` 經 stdin 打包送進容器，自動載入 /opt/ros 與 Workspace overlay；主機路徑依 bind mount 自動換成容器路徑）。
**數據**可以是實驗資料夾、bag 資料夾、切片資料夾、`.mcap`、實驗名稱或 `latest`；省略時用「目前分析的數據」（成功操作過的數據自動成為目前的數據，標題列顯示）。

| 技能 | 對應的 toolkit 工具 | 做什麼 |
|---|---|---|
| `mcap_recorder` | `mcap_recorder.py`、`ros2_toolkit.sh` 選項 1 | 定時錄製（`-s mcap`；`--preset core`＝toolkit 的預設核心 Topic），`/rosout` 經 `rosout_formatter.py` 存成 `rosout.log`，同樣的 `exp_*/bag/` 結構；**錄完自動建立全域 Topic Metadata 索引** |
| `rosout_parser` | `rosout_parser.py`、`mcap_slicer.py` 步驟 1～3 | Log 智慧過濾：去重成唯一訊號 L#（只差在數字也算同一句），篩層級／Node／關鍵字；預設用 bag 裡的 /rosout（時間跟其他 Topic 同一個時鐘），沒有就用 `rosout.log`；略過 rosbag2 自己的 Log |
| `mcap_analyzer` | `mcap_analyzer.py`（Metadata 摘要、欄位維度、原始值預覽） | 全域索引（時間範圍、每個 Topic 的型別、筆數、頻率、起訖、角色），`--topic` 看每個 Key 的型別／維度／類別，`--key --preview` 看原始值；`--facts` 量全部 Topic 的全部 Key（analysis_run 的事實）；索引與事實快取在 bag 資料夾的 `topic_metadata.json`、`topic_facts.json` |
| `mcap_feature_measure` | `mcap_feature_measure.py`（`compute_features`） | 按需量測 Key 的特徵（整數相異值 ≤10 當狀態跳轉，同 toolkit），加上最大跳變、只有幾種值的數值的每次切換、尖峰（跳出去又回來，不含雜訊）、發布方式（只有固定頻率的判斷中斷）、依名稱展開的序列 |
| `mcap_slicer` | `mcap_slicer.py` 步驟 4～5 | 依 L# 或時間點前後各取幾秒（預設 5 秒），或明確的時間窗（`--window`），可以只切指定的 Topic（`--topics`）、帶上時間窗之前的狀態（`--with-state`）；輸出 toolkit 格式的 `sliced_bag_*`（`metadata.yaml` 的 available_keys、`ai_slice_diagnostic_summary`）——toolkit 的 `mcap_analyzer.py` 讀得懂；`metadata.yaml` 是 rosbag2 的格式，`ros2 bag info／play <切片資料夾>` 也讀得到；超過 3 分鐘的數據先用它切出要看的那段，再交給 analysis_run |
| `analysis_run` | （新增） | 上面的多 agent 數據分析（事實報告） |

改得跟 toolkit 不一樣的地方：全部非互動（agent 要用參數）、字串欄位分成「列舉」（相異值少 → 狀態）與「自由文字」（只給 Orchestrator）、
`builtin_interfaces/Time` 不再被誤判成狀態（toolkit 的型別判斷用子字串 `int`，`builtin_interfaces` 也會中）、空的序列不會變成假的項目、
時間窗與時間的寫法比較寬鬆（`+0.75s`、`0~30`、`10 to 20` 都認得）、不認識的參數照認得的做完並附說明。

## 怎麼用

```bash
python3 web_console.py      # Web：http://127.0.0.1:8765（只綁本機）
python3 Agent_Runner.py     # CLI（同樣有 /analyze 與 /analysis_* 指令）
```

1. **設定**：右欄「📊 數據分析」→ ⚙️ 設定：預設容器（數據技能都在容器內執行，例如 `ros2_web_container`）、數據根目錄（錄製位置，空白＝在容器的 /workspace 底下找 `experiment_logs`）、worker 上限、最多幾輪（可以補派一輪）。各角色的模型在標題列的 🧠（主對話、分析 Orchestrator／Worker／Synthesizer；沒有另外設定時跟著主對話）。
2. **數據**：跟 AI 說「錄 30 秒的核心 Topic」（mcap_recorder），或用現有的實驗資料夾（「看一下 exp_20261014_084506」）。
3. **問問題**：直接跟 AI 說（「底盤在錄製中途停下來的前後發生了什麼？」，它會選 analysis_run；只問一個值或 Log 時直接用對應的技能），或 `/analyze <問題>`，或按輸入框旁的 **📊 分析** 進入分析模式。數據超過 3 分鐘時，先用 mcap_slicer 切出要看的那段（例如跟 AI 說「切出 +60 到 +200 秒」）。
4. **看結果**：左欄是 AI 依報告的回答；右欄的進度卡片即時顯示每一個階段；「📊 數據分析」面板列出 Orchestrator 的計畫（相關的 Log 訊號、每個 worker 的 Topic、補派）、每個 worker 的說明（沒通過核對的則數）、最後的事實報告。

| 數據分析指令 | 作用 |
|---|---|
| `/analyze [問題]` | 直接交給 analysis_run（問題省略＝這段錄製期間發生了哪些狀態變化）；報告照一般工具結果進主對話，可以接著追問 |
| `/analysis`、`/analysis jobs` | 看最近一次的報告／列出最近的 job |
| `/analysis_data <數據>`、`/analysis_root <路徑>`、`/analysis_container <容器>` | 目前的數據、數據根目錄、預設容器（`-` 清除） |
| `/analysis_model <orchestrator\|worker\|synthesizer\|all> <模型>`、`/analysis_workers N` | 各角色的模型（`-` 跟著主對話）、worker 上限 |
| `/analysis_mode on\|off` | 📊 分析模式（同輸入框旁的按鈕） |

| 數據分析設定（環境變數） | 預設 | 說明 |
|---|---|---|
| `AGENT_ANALYSIS_ORCHESTRATOR_MODEL`／`_WORKER_MODEL`／`_SYNTHESIZER_MODEL` | 同主模型 | 各角色的模型（Web 的 🧠 設定會存檔，`logs/analysis_settings.json`） |
| `AGENT_ANALYSIS_THINK` | 關 | Orchestrator 與 Synthesizer 的 thinking（模型支援才送） |
| `AGENT_ANALYSIS_DATA_ROOT` | 自動尋找 | 數據根目錄 |
| `AGENT_ANALYSIS_MAX_WORKERS`／`AGENT_ANALYSIS_PARALLEL` | 4／2 | 最多派幾個 worker 說明／同時跑幾個（事實不受上限影響；同一個模型在 Ollama 只有一個 slot 時，模型呼叫仍會排隊） |
| `AGENT_ANALYSIS_ROUNDS` | 2 | 最多幾輪（1＝不補派、2＝可以補派一輪；Web：⚙️ 設定） |
| `AGENT_ANALYSIS_MAX_SECONDS` | 180 | 一次最多分析幾秒的數據（以整秒算；更長的先用 mcap_slicer 切） |
| （設定檔）`<角色>_ctx` | 同 `AGENT_NUM_CTX` | 各角色的上下文長度（`logs/analysis_settings.json`，只存跟預設不同的值；8 GB 顯卡上換大一點的模型時調小，見設計筆記限制 54） |

## 實測

第一～九輪（2026-10-14～16，包括源碼脈絡、Orchestrator 分兩步、因果推論、根因的評分）每一輪的做法與數據在
[`root_cause_reference/設計筆記_第1到9輪.md`](root_cause_reference/設計筆記_第1到9輪.md)；這裡只留跟現在的做法有關的。

| 項目 | 結果 |
|---|---|
| 程式量全部 Topic、一則一則有編號的說明（2026-10-22 第十一輪，RTX 5090、全部角色 gemma4:26b；這台錄的 14 份數據，每份 3 次） | **時間線 39/39、用詞 42/42、時間有根據 42/42、沒有事件 3/3**；報告裡的時間對真實事件 0/2127 沒有根據（重點 0/222、worker 的說明 0/300、程式整理的 0/1605）；程式產物與 Topic 的事件每次相同 14/14；worker 143 個 0 失敗；重點 42 次只交回 1 次、0 則截短或丟掉。一次約 9 秒、模型呼叫約 6 次（第十輪 20 秒、19 次）。細節：〈設計筆記 2.18 六〉、`evals/results/analysis_r11c_real/` |
| 隨機情境產生器（`evals/datagen/`：diagnostics_package、amr_base_hw、amr_base_sw、fih_rmf_system、VSLAM_package、fih_amr_bridge 的模擬；評分標準由注入的事件產生） | 三組 ×1～2 次（最終版）：s1（60 份，加 bridge 之前的五個子系統）×2 時間線 98/98、類別 114/114、用詞 120/120、時間有根據 120/120、**重點涵蓋 96/96**、**沒有事件 20/20**；s2（60 份，含 bridge 與 Isaac Sim 的設定）×1 時間線 53/53、類別 53/53、用詞 60/60、時間有根據 60/60、重點涵蓋 50/50、沒有事件 4/4；s3（20 份，每一份都有 bridge，含只有 Log 的錄製）×2 全部通過（28/28、26/26、40/40、40/40、28/28、8/8）。程式產物與 Topic 的事件每份每次都相同；worker 827 個 0 失敗；一次約 8～13 秒。程式那一層（`evals/datagen/check_facts.py`，不呼叫模型）：三組全對（時間線 365/365、369/369、78/78）。細節：〈設計筆記 2.18 五、六〉、`evals/datagen/README.md` |
| 第十一輪的四版（同一套數據） | 實錄：重點交回 18 → 9 → 1 → 0 次、截短 18 → 9 → 0 → 0 則；s1：重點涵蓋 82/96 → 87/96 → 96/96、沒有事件 10/20 → 20/20（產生器的評分標準補上背景）；s3：只有 Log 的錄製第一版一律回錯誤（時間線 22/28），最終版照樣出報告（28/28）。每一版改了什麼見〈設計筆記 2.18 四、六〉 |
| Web 的完整流程（HTTP 照瀏覽器的方式、auto 模式） | `/analyze --data exp_5090_lidar LiDAR 斷線的前後發生了什麼？安全閘最後是什麼狀態？`：分析的是指定的數據（11 秒、模型呼叫 7 次）；第一個回答照報告列出事實與編號，沒有因果的說法（第十輪這裡寫了「LiDAR 錯誤觸發了…導致…」）；追問「安全閘為什麼一直鎖著？是什麼造成的？」時照事實說明先後順序、指出報告沒有說明鎖定的邏輯，建議對照 safety_gate、system_health_monitor 的源碼（2026-10-22，26b，8799 埠，設定先備份、測完還原） |
| 主對話的路由（`evals/run_evals.py` 的 3 個 analysis 情境，e4b、harness 模式） | 3/3：發生了什麼的問題用 analysis_run、單一數值用 mcap_feature_measure、Log 問題用 rosout_parser，回答引用工具的數字（2026-10-22，報告換成新格式之後重跑） |
| 數據技能的實機測試（`evals/analysis_tools_live.py`） | exp_5090_overheat 21/21、調度系統的實錄 real_rmf_20261015 14/14（含 `--facts` 的文字與 JSON、切片、`ros2 bag info` 讀切片資料夾、讀切片＝讀原本的數據、混了不存在的 Key、錯誤處理；2026-10-22）；`--record` 真的錄 6 秒的那一項在 2026-10-14 跑過 |
| 離線自我測試 | `analysis_selftest.py` 13/13、`main_selftest.py` 13/13、`v5_selftest.py` 8/8 |
| toolkit 相容 | toolkit 的 `mcap_analyzer.py` 讀得懂 mcap_slicer 產生的切片（包括巢狀的 Key）；切片的 `metadata.yaml` 是 rosbag2 的格式，`ros2 bag info／play <切片資料夾>` 也讀得到 |
| 8 GB 筆電（RTX 5060 Laptop，2026-10-14） | e4b 可以跑（第一版一次 60～75 秒）；gemma4:26b 放不下（18.7 GB，大部分在 CPU），要在顯示記憶體 ≥24 GB 的機器上用 |

**已知的限制**：一次最多分析 3 分鐘；時間上的對照不代表誰造成誰；模型寫的文字（重點、說明）的數值不核對（正確的內容由程式列在重點下面）；
JSON 字串的 Topic 只量訊息流、不量內容；固定頻率的 Topic 頻率中途改變不會列成事件；worker 的平行度受 Ollama 的 slot 限制；
Topic Metadata 的 Key 分類是抽樣（每個 Topic 120 筆）判斷的；隨機情境產生器是照源碼與文件模擬的，實機的時序與雜訊會不一樣。完整的在〈設計筆記〉第 6 節。

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
- **沒有執行卻宣稱做完**：這一回合一個工具都沒有執行，回覆卻說「已經重新啟動了／已建立…」，提醒 AI 一次（條件句、疑問句、否定句不算；只認子句開頭或「我／我們」後面的說法——「指令已停止發布」這種有主詞的句子是在描述數據或系統的狀態）。
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
| `/analyze [問題]`、`/analysis_help` | 數據分析（見上面〈怎麼用〉）／數據分析的全部指令 |
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
| ROS 2 數據解析 | `analysis_run`（多 agent 數據分析，事實報告）、`mcap_recorder`、`rosout_parser`、`mcap_analyzer`、`mcap_feature_measure`、`mcap_slicer` |
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
│                       #   analysis_job.py＝數據解析（事實、Orchestrator／Workers／Synthesizer、核對），ops_job.py＝多步驟維運任務
├── web_app/            # Web 介面（純標準庫）：狀態、回合流程、slash 指令、HTTP、static/index.html；analysis.py＝📊 數據分析面板的後端
├── AGENT.md            # system prompt 主體：角色、JSON 回覆格式、執行協議、安全原則、記憶協議
├── analysis_agents/    # 數據解析各角色的 system prompt（orchestrator.md、orchestrator_check.md、worker.md、synthesizer.md，可以直接改）
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
│                       #   analysis_regression.py、analysis_fixtures/、datagen/＝隨機情境的錄製產生器）、多步驟維運（v5_selftest.py、ops_suite/）
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
