# 文件導覽

| 文件 | 給誰看 | 內容 |
|---|---|---|
| [架構說明](架構說明.md) | 想看懂或修改核心的人 | `agent_core/`、`web_app/` 由哪幾個模組組成、兩種上下文模式、一回合怎麼跑、工具回傳管線、執行前關卡、狀態與持久化、CLI／Web 對照、常數、「要改什麼看哪裡」、評測 |
| [設計筆記與已知限制](設計筆記與已知限制.md) | 想知道某個機制為什麼長這樣的人 | 每個機制的做法、理由與實測數據；完整技能清單；驗證方法；已知限制；未來方向（2026-09-26 從 README 移來） |
| [長期願景](長期願景.md) | 關心延伸方向的人 | AGV/AMR 車隊調度場景的構想（尚未實作） |
| [評測](../evals/README.md) | 改了 prompt、門檻或模式邏輯、想知道有沒有變好的人 | 同一組情境跑 harness／claude_code 兩種上下文模式：怎麼跑、情境清單、怎麼加情境、怎麼讀報表 |
| [架構說明 §13](架構說明.md#13-coding-orchestratoragent_corecoding_py) | 想看懂或修改 coding orchestrator 的人 | 規劃→核准→worker→驗證→報告的流程、模組、worker 的一步、狀態存在哪裡、常數、要改什麼看哪裡、C／C++ 與測試的執行環境（13.7）（設計理由與實測在設計筆記 2.12、2.13） |
| [DevBench 評測](../evals/devbench/README.md) | 想量長任務 coding 能力的人 | 公開 benchmark 的子集（Python 7、C++ 5 個 repo）：為什麼選它、怎麼準備與跑、分數怎麼看、授權 |

## 圖

| 圖 | 來源 | 內容 |
|---|---|---|
| ![架構](images/AI_agent_harness的說明.png) | `AI_agent_harness的說明.puml` | 元件與資料流；`vision/`（框選／上傳 → 結構化提取 → `[vision result]`）與使用者介面、SkillAgent、技能、存檔的關係 |
| ![一回合](images/AI_agent_harness的狀態轉移.png) | `AI_agent_harness的狀態轉移.puml` | 一回合的狀態機；附圖時的視覺提取（1b），以及附圖分析在 prompt、壓縮、下一句話裡的位置 |
| ![工具回傳管線](images/AI_agent_harness的工具回傳管線.png) | `AI_agent_harness的工具回傳管線.puml` | 原文存檔 → 摘要 → 檢索清單 → result_recall；中段是附圖的影像分析（提取 → 存成 #編號 → 〔附圖分析〕進清單 → 併進訊息），同一套 recall |
| ![coding](images/Coding_orchestrator的流程.png) | `Coding_orchestrator的流程.puml` | coding job 從任務到報告：探索、規劃（含 harness 的修正）、核准、worker（決定與內容通道）、驗證與重試、整體驗證與報告 |

改完 `.puml` 後重新產生 PNG（純標準庫，透過 PlantUML 官方伺服器，需要網路）：

```bash
python3 doc/流程圖產生器.py                 # 全部
python3 doc/流程圖產生器.py 某張圖.puml     # 只轉一張
```
