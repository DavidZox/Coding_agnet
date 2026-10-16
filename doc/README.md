# 文件導覽

| 文件 | 給誰看 | 內容 |
|---|---|---|
| [架構說明](架構說明.md) | 想看懂或修改核心的人 | `agent_core/`、`web_app/` 由哪幾個模組組成、兩種上下文模式、一回合怎麼跑、工具回傳管線、執行前關卡、狀態與持久化、CLI／Web 對照、常數、「要改什麼看哪裡」、評測 |
| [設計筆記與已知限制](設計筆記與已知限制.md) | 想知道某個機制為什麼長這樣的人 | 每個機制的做法、理由與實測數據；完整技能清單；驗證方法；已知限制；未來方向（2026-09-26 從 README 移來） |
| [長期願景](長期願景.md) | 關心延伸方向的人 | AGV/AMR 車隊調度場景的構想（尚未實作） |
| [評測](../evals/README.md) | 改了 prompt、門檻或模式邏輯、想知道有沒有變好的人 | 同一組情境跑 harness／claude_code 兩種上下文模式：怎麼跑、情境清單、怎麼加情境、怎麼讀報表；數據解析的離線自我測試與實機測試 |
| [架構說明 §13](架構說明.md#13-數據解析的多-agent-協同agent_coreanalysis_jobpy) | 想看懂或修改數據解析的人 | Orchestrator → Workers → Synthesizer 的流程、模組（含數據技能的共用層 `_ros2_data_common.py`）、worker 的一步、產物存在哪裡、常數、要改什麼看哪裡（設計理由與實測在設計筆記 2.18） |
| [待辦清單](待辦清單.md) | 要決定下一步做什麼的人 | 數據解析 agent 的下一步建議（coding 的待辦在 Coding_agent_harness） |

## 圖

| 圖 | 來源 | 內容 |
|---|---|---|
| ![架構](images/AI_agent_harness的說明.png) | `AI_agent_harness的說明.puml` | 元件與資料流；`vision/`（框選／上傳 → 結構化提取 → `[vision result]`）與使用者介面、SkillAgent、技能、存檔的關係 |
| ![一回合](images/AI_agent_harness的狀態轉移.png) | `AI_agent_harness的狀態轉移.puml` | 一回合的狀態機；附圖時的視覺提取（1b），以及附圖分析在 prompt、壓縮、下一句話裡的位置 |
| ![工具回傳管線](images/AI_agent_harness的工具回傳管線.png) | `AI_agent_harness的工具回傳管線.puml` | 原文存檔 → 摘要 → 檢索清單 → result_recall；中段是附圖的影像分析（提取 → 存成 #編號 → 〔附圖分析〕進清單 → 併進訊息），同一套 recall |
| ![數據診斷的流程](images/數據診斷的流程.png) | `數據診斷的流程.puml` | 數據診斷的完整流程（活動圖，2026-10-16 改寫）：收到問題 → 資料預備（含源碼脈絡）→ Orchestrator 第一步挑訊號、第二步帶源碼分派（觀測角度跟源碼核對）→ 時間窗與切片 → Workers（每一步的程式檢查與量測）→ Synthesizer ⇄ 補推理鏈（最多 2 輪）→ 報告；藍＝程式、橘＝模型、綠＝程式檢查與更正，底部是程式輔助的三類（文字版的說明在 README〈圖的說明〉） |

改完 `.puml` 後重新產生 PNG。建議用本機離線渲染（不把圖的內容送到外部服務）：這台機器有 Java、Graphviz（`dot`）與
`/home/david/Software_quality_checking_pipeline/tools`（PlantUML 與 Microsoft JhengHei 字型）：

```bash
cd doc
PH=/home/david/Software_quality_checking_pipeline/tools
FONTCONFIG_FILE=$PH/fontconfig/fonts.conf GRAPHVIZ_DOT=/usr/bin/dot \
  $PH/jre/bin/java -Djava.awt.headless=true -DPLANTUML_LIMIT_SIZE=16384 -jar $PH/plantuml.jar \
  -tpng -charset UTF-8 -failfast2 -o images 數據診斷的流程.puml
```

沒有 Microsoft JhengHei 的機器（例如 amr-base 這台）：`~/tools/plantuml/` 放了 Temurin JRE 21 與 plantuml.jar（1.2026.8，從 Maven Central 下載），
字型換成系統的 Noto Sans CJK TC 再渲染（`.puml` 本身不改，照舊寫 JhengHei）：

```bash
cd doc && T=$(mktemp -d)
sed 's/"Microsoft JhengHei"/"Noto Sans CJK TC"/' 數據診斷的流程.puml > $T/數據診斷的流程.puml
~/tools/plantuml/jre/bin/java -Djava.awt.headless=true -DPLANTUML_LIMIT_SIZE=16384 -jar ~/tools/plantuml/plantuml.jar \
  -tpng -charset UTF-8 -failfast2 $T/數據診斷的流程.puml && cp $T/數據診斷的流程.png images/
```

寫 `.puml` 時注意：字型沒有 emoji（📊 會變成方框，請用文字）、Noto Sans CJK 也沒有 ✗；同一行有兩個 `--`（例如 `--window --topics`）會被當成刪除線，要寫成 `~--`。

`流程圖產生器.py` 是另一種做法：純標準庫，把 `.puml` 的內容送到 PlantUML 官方伺服器（plantuml.com）渲染，需要網路；圖的內容會離開這台機器：

```bash
python3 doc/流程圖產生器.py                 # 全部
python3 doc/流程圖產生器.py 某張圖.puml     # 只轉一張
```
