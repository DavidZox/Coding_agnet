| 情境組 | 版本 | 把關 | 上下文模式 | 模型 | 通過 | 通過率 [Wilson 95% CI] | 每個情境的主模型呼叫 | 連續重複的工具呼叫 | 撞到步數上限 | 卡住偵測停下 | 宣稱完成的提醒 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main | AI_agent_harness | guards-n/a | claude_code | gemma4:26b | 39/42 | 92.9% [81.0, 97.5] | 4.6 | 0 | 0 | 0 | 0 |
| main | AI_agent_harness | guards-n/a | claude_code | gemma4:e4b | 70/96 | 72.9% [63.3, 80.8] | 4.7 | 13 | 0 | 0 | 0 |
| main | AI_agent_harness | guards-n/a | harness | gemma4:26b | 39/42 | 92.9% [81.0, 97.5] | 3.8 | 1 | 0 | 0 | 0 |
| main | AI_agent_harness | guards-n/a | harness | gemma4:e4b | 83/84 | 98.8% [93.6, 99.8] | 4.1 | 5 | 0 | 0 | 0 |
| main | v0 | guards-n/a | harness | gemma4:e4b | 20/20 | 100.0% [83.9, 100.0] | 3.4 | 0 | 0 | 0 | 0 |
| main | v1 | guards-on | harness | gemma4:e4b | 14/14 | 100.0% [78.5, 100.0] | 3.5 | 0 | 0 | 0 | 0 |
| main | v4 | guards-on | harness | gemma4:e4b | 42/42 | 100.0% [91.6, 100.0] | 3.6 | 0 | 0 | 0 | 0 |
| main | v4.1 | guards-on | harness | gemma4:e4b | 27/28 | 96.4% [82.3, 99.4] | 3.5 | 0 | 0 | 0 | 0 |
| robust | v4 | guards-off | harness | gemma4:e4b | 13/15 | 86.7% [62.1, 96.3] | 7.5 | 5 | 0 | 0 | 0 |
| robust | v4 | guards-on | harness | gemma4:e4b | 11/15 | 73.3% [48.0, 89.1] | 5.3 | 0 | 0 | 1 | 0 |
| robust | v4.1 | v4 的規則（對照） | harness | gemma4:e4b | 37/50 | 74.0% [60.4, 84.1] | 5.8 | 2 | 0 | 1 | 0 |
| robust | v4.1 | v4.1 把關開啟 | harness | gemma4:e4b | 39/50 | 78.0% [64.8, 87.2] | 6.3 | 4 | 0 | 0 | 0 |
| robust | v4.1 | 把關全部關閉 | harness | gemma4:e4b | 37/50 | 74.0% [60.4, 84.1] | 7.1 | 20 | 0 | 0 | 0 |
