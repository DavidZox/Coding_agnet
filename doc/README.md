# 文件導覽

| 文件 | 給誰看 | 內容 |
|---|---|---|
| [架構說明](架構說明.md) | 想看懂或修改程式的人 | `agent_core/`、`web_app/` 由哪幾個模組組成、其他資料夾（§4.3）、兩種上下文模式、一回合怎麼跑、工具回傳管線、執行前關卡、狀態與持久化、CLI／Web 對照、常數、「要改什麼看哪裡」、評測（§12）、工作流與 `--workflow` 入口（§14） |
| [架構說明 §13](架構說明.md#13-數據分析agent_coreanalysis_jobpy全部由程式做) | 想看懂或修改數據解析的人 | 全部由程式做的流程（事實 → 重要的時間點與重點 → 報告）、模組（含數據技能的共用層 `_ros2_data_common.py`）、主對話回答的核對、產物存在哪裡、常數、要改什麼看哪裡、報告的範例 |
| [設計筆記與已知限制](設計筆記與已知限制.md) | 想知道某個機制為什麼長這樣的人 | 每個機制的做法、理由與實測數據（數據解析在 2.15，工具回傳的提煉與技能的整理在 2.16，持續驗證在 2.17，工作流在 2.18，任務引擎與 Plan 模式在 2.19、2.8）；完整技能清單（§3，數據技能與 toolkit 的對照在 3.8）；驗證方法；已知限制（§6）；未來方向 |
| [技能撰寫規範](技能撰寫規範.md) | 寫技能、改技能的人 | 規格文件的格式；腳本輸出的結構（第一行、章節、截斷的說明、狀態標記放最後）；[ERROR] 要寫原因與下一步；可以自己用（不讀標準輸入、逾時、不留背景程序）；測試放 `evals/skills/` |
| [工作流撰寫規範](工作流撰寫規範.md) | 寫工作流、改工作流的人 | 工作流的格式（OKF type: Workflow）；四種步驟與程式怎麼推進（判斷點、分支、【確認】、成功判準）；寫得穩的訣竅（2026-10-23 實測）；怎麼測（`evals/workflow/`） |
| [待辦清單](待辦清單.md) | 要決定下一步做什麼的人 | 已記錄、還沒做的：架構整合剩下的階段（第 4 階段進行中、第 5～6 階段）、數據解析與技能的下一步 |
| [長期願景](長期願景.md) | 關心延伸方向的人 | AGV/AMR 車隊調度場景的構想（尚未實作）、實作心跳機制與定時任務時要注意的事 |
| [評測](../evals/README.md) | 改了程式或 prompt、想知道有沒有變好的人 | 主對話、技能腳本、數據解析、隨機情境產生器、多步驟維運、提煉、工作流各組，與每個階段結束時的 `phase_check.py`：怎麼跑、怎麼加情境、怎麼讀報表 |
| [隨機情境的錄製產生器](../evals/datagen/README.md) | 要做大量數據測試的人 | 六個開發中套件的模擬、評分標準怎麼產生、三組數據 |
| [test_data](../test_data/README.md)（只在本機） | 要跑實機回歸的人 | 這台錄的 14 份數據、正確答案、回歸工具 |
| [archive/root_cause_reference](archive/root_cause_reference/README.md) | 要做根因 agent 的人 | 第一～九輪的源碼脈絡與因果推論（只供閱讀，不會被執行） |

## 圖

圖的來源（`.puml`）在 `diagrams/`，產生的 PNG 在 `images/`。

| 圖 | 來源 | 內容 |
|---|---|---|
| ![架構](images/AI_agent_harness的說明.png) | `diagrams/AI_agent_harness的說明.puml` | 元件與資料流；`vision/`（框選／上傳 → 結構化提取 → `[vision result]`）與使用者介面、SkillAgent、技能與工作流、偽技能（result_recall、workflow_run、analysis_run、ops_plan／ops_run）、一次性 session（提煉、工作流的判斷點、ops 的規劃與 worker）、`logs/` 底下各種存檔、確認關卡的範圍 |
| ![一回合](images/AI_agent_harness的狀態轉移.png) | `diagrams/AI_agent_harness的狀態轉移.puml` | 一回合的狀態機；`/analyze`、`/workflow` 直接指定；確認關卡擋哪些；Dispatch 的偽技能；附圖時的視覺提取（1b），以及附圖分析在 prompt、壓縮、下一句話裡的位置 |
| ![工具回傳管線](images/AI_agent_harness的工具回傳管線.png) | `diagrams/AI_agent_harness的工具回傳管線.puml` | 原文存檔 → 規格文件、提煉過的、程式整理好的報告（數據分析、工作流）直接給原文 → 太長的提煉（程式切段 → 每段一個 worker → 整合，程式核對行號）→ 檢索清單 → result_recall；退路（`/summarize off`、提煉沒成功、重點不比原文短）；中段是附圖的影像分析（提取 → 存成 #編號 → 〔附圖分析〕進清單 → 併進訊息），同一套 recall |
| ![數據分析的流程](images/數據診斷的流程.png) | `diagrams/數據診斷的流程.puml` | 數據分析（事實報告）的完整流程（活動圖）：收到問題 → 資料預備與事實（超過 3 分鐘先切；字串裡的 JSON 展開成 Key；程式量全部 Topic 的全部 Key、整理成有編號的事實）→ 重點（程式照規則寫：每個重要的時間點一則）→ 報告 → 主對話依報告回答與程式的核對（之後的回合也核對）；藍＝程式、橘＝模型、綠＝程式核對，底部是程式做的與模型做的；第九輪的流程圖在 `archive/root_cause_reference/doc/` |

改完 `.puml` 後重新產生 PNG，一律用本機離線渲染（不要用線上的 PlantUML 伺服器：圖的內容會離開這台機器）。`~/tools/plantuml/` 放了 Temurin JRE 21 與
plantuml.jar（1.2026.8，從 Maven Central 下載）；這台機器沒有 Microsoft JhengHei，字型換成系統的 Noto Sans CJK TC 再渲染
（`.puml` 本身不改，照舊寫 JhengHei）：

```bash
cd doc && T=$(mktemp -d)
sed 's/"Microsoft JhengHei"/"Noto Sans CJK TC"/' diagrams/數據診斷的流程.puml > $T/數據診斷的流程.puml
~/tools/plantuml/jre/bin/java -Djava.awt.headless=true -DPLANTUML_LIMIT_SIZE=16384 -jar ~/tools/plantuml/plantuml.jar \
  -tpng -charset UTF-8 -failfast2 $T/數據診斷的流程.puml && cp $T/數據診斷的流程.png images/
```

有 Microsoft JhengHei 的機器（原作者的環境：`/home/david/Software_quality_checking_pipeline/tools` 有 PlantUML、字型與 fontconfig）：

```bash
cd doc
PH=/home/david/Software_quality_checking_pipeline/tools
FONTCONFIG_FILE=$PH/fontconfig/fonts.conf GRAPHVIZ_DOT=/usr/bin/dot \
  $PH/jre/bin/java -Djava.awt.headless=true -DPLANTUML_LIMIT_SIZE=16384 -jar $PH/plantuml.jar \
  -tpng -charset UTF-8 -failfast2 -o ../images diagrams/數據診斷的流程.puml
```

寫 `.puml` 時注意：字型沒有 emoji（📊 會變成方框，請用文字）、Noto Sans CJK 也沒有 ✗；同一行有兩個 `--`（例如 `--data --topic`）會被當成刪除線，要寫成 `~--`。
