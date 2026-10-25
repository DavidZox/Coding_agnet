使用者用 /analyze、/workflow 直接指定時（不經過主模型選擇），harness 替使用者與 AI 放進主對話的那兩則訊息——之後的回合 AI 看得到
這是使用者指定的（agent_core/workflow_cmd.py；/analyze 在 agent_core/cli.py 與 web_app/flows.py，兩邊的 reply 原本就寫得不一樣，
照原樣各留一則）。還有數據分析報告最後一行的回答規則（agent_core/analysis_job.py；開頭的「（依這份報告回答使用者」是程式認的標記，
留在程式裡）。{名稱} 是程式填的值。

<!-- @workflow_user -->
（我用 /workflow 直接執行工作流：{args}。執行完照報告告訴我結果；停在【確認】或沒有完成時說明卡在哪裡、接下來可以怎麼做。）

<!-- @workflow_thought -->
使用者用 /workflow 直接指定要執行的工作流，照使用者給的參數執行

<!-- @workflow_reply -->
照你指定的執行工作流：{args}

<!-- @analyze_default_question -->
這段錄製期間發生了哪些狀態變化？

<!-- @analyze_thought -->
使用者要求數據分析，直接交給 analysis_run

<!-- @analyze_reply_cli -->
交給數據分析。

<!-- @analyze_reply_web -->
交給數據分析（程式量全部的事實、整理成事實報告）。

<!-- @analysis_answer_rules -->
：只陳述報告裡的事實——時間、數值、狀態、Log 的原文，可以引用編號。報告沒有判斷原因：「前後 1 秒內」「同時」只是時間上的先後，不要寫成誰導致、造成、觸發誰；使用者問「為什麼」時，照事實說明發生了什麼、先後順序，並說明原因要對照源碼另外分析；要細看某個 Topic、某一段時間或某則 Log，用數據技能（mcap_feature_measure、mcap_analyzer、rosout_parser、mcap_slicer）查）
