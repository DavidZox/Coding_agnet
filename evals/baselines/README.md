# 持續驗證的基準

> 寫給：每個階段結束時要確認「框架沒有變差」的人。`evals/phase_check.py` 跑完會拿這裡的數字逐項比；結果目錄（`evals/results/`）不進版控，
> 基準要跟著程式一起 commit，換了機器也比得了。

| 檔案 | 內容 | 目前的來源 |
|---|---|---|
| `offline.json` | 各組自我測試的通過數（`skills`、`chat_selftest`、`extract_selftest`、`ops_selftest`、`analysis_selftest`、`repo_selftest`、`integrity`；凍結的工具另有 `skills_sandbox`、`containers_sandbox`、`data_live`、`tools_live:<數據>`） | 拿掉任務引擎與 Plan 模式之後（2026-11-18）：`chat_selftest` 17、`ops_selftest` 3（沙盒 daemon 怎麼起）、`integrity` 8（`task_selftest` 刪掉）；其他的是之前的（`skills` 100、`skills_sandbox` 27 是待辦 20、23 之後的） |
| `ops_gemma4-26b.json` | 維運評測（沙盒裡真的執行，77 個情境：檔案與調查 23 個每個階段跑、凍結的工具 54 個 `--tools` 才跑）：`current.per` 每個情境的次數、通過、禁止動作、秒數中位數、**每一次的結果**（`results`，照跑的順序，1＝過）與是哪一次更新的（`since`）；總分由 `results` 算（名稱開頭 `ho_`＝保留、`inv_`＝調查與報告、其他＝主要），所以只跑一部分也能跟同一組情境比。比對只用 `current`，其他的 key 是之前的基準、只當參考（`todo25`、`todo20_23`、`phase4`、`phase4_start`、`phase3`、`reference_v5`，那些還是舊的格式） | 第 5 階段的三次完整跑（2026-10-25，`*_p5_r1～r3`）：主要 48／48／47、保留 18／20／19、調查與報告 5／5／5，禁止動作 0；收尾時從這三次的 `runs.jsonl` 補上 `results`（算回來的總分跟原本記的一樣） |
| `chat_gemma4-e4b.json` | 主對話評測（假的外部世界、真模型）11 個情境，每個情境的次數與通過 | 第 4 階段結束的一次（×3：33/33；第 4 階段開始也是 33/33，第 2 階段兩次 32/33、33/33）。第 5 階段結束的一次 32/33（followup_in_context 一次，沒用到任務引擎），沒有拿來更新 |
| `extract.json` | 提煉評測（`evals/extract/`）每個模型、每個情境：找到幾個、多列幾個、數量的說法對不對、秒數 | 第 2 階段 commit 之後各跑一次（26b 全對；e4b 的 recall_fleet_120 是 9/11：worker 漏一台、整合時拿掉一台——兩個條件一起篩對小模型難）；robot_heading 2026-10-24 加（26b 4/4；e4b 這一次 1/1，另外三次只過 1 次——小模型常漏掉要去的站，沒過時先看是不是這個）。第 4 階段沒有改提煉，結束時的一次 26b 全對、e4b fleet_40 6/7（一次讀完漏了 amr_24）、recall_fleet_120 10/11，沒有拿來更新；第 5 階段結束時一樣（26b 全對、e4b fleet_40 6/7、recall_fleet_120 10/11），沒有更新 |
| `analysis.json` | 數據分析回歸（不呼叫模型）：產生器 s1／s2／s3、這台的實錄，每份數據每個評分項目過了幾次；實錄另有產物穩定性、沒有根據的時間 | 第 2 階段（`analysis_p2_*`）；第 3、第 4 階段的 `--live` 結果跟它一樣（全部項目都過、實錄的產物每次相同 14/14、沒有根據的時間 0/1070） |

## 怎麼比

- 自我測試：有沒過的就是 ❌；通過數比基準少（測試被拿掉、或環境少了東西而略過）列成要注意。
- 維運：只跑一次時，基準裡大多會過（≥ 3/4）的情境這次沒過才列；跑好幾次時，通過率比基準低超過 1/3 才列（模型有隨機性，單次的差別多半是波動）。
  另外列：有禁止動作的、秒數中位數超過基準的 2 倍而且多 30 秒以上的（2026-10-23 的 `--watch 300` 就是這樣被看到的）、總分低於基準裡**同一組情境**
  每一次的最低分的（每一組分開比：主要、保留、調查與報告）。秒數會受同一台機器上的其他負載影響（例如 Isaac Sim 佔著 GPU），變慢先看 `perf`。
- 主對話：通過率比基準低超過 1/3 的情境。
- 提煉：找到的比基準少、多列的比基準多、回答說的數量不對。
- 數據分析回歸：每份數據的每個評分項目，通過次數的比例比基準低就列。

## 什麼時候更新

階段 commit 之後、確認要注意的項目都看過（是波動或已經處理），用那一次（或那幾次）的結果更新：

```bash
python3 evals/phase_check.py --save-baseline evals/results/<時間>_phase_check [其他的結果目錄…] --label "第 N 階段（<commit>）"
```

維運最好用 3 次以上的結果一起更新（`--save-baseline` 給好幾個 `_ops_` 目錄會合成一份）；只換這次有跑的情境，沒跑的情境的基準不動
（只跑檔案與調查時，凍結的工具那 54 個照舊）。

只更新其中幾項時加 `--only`，其他的基準不動：名稱是 summary.md 第一欄括號裡的 key（`skills`、`chat_selftest`、`chat`、`ops`、`ops_tools`…），
有冒號的取冒號前面（`tools_live`、`analysis`、`extract`；跑的時候數據分析回歸叫 `analysis_regression`，這裡是 `analysis`）。

要留下整份舊的維運基準當參考，先在 json 裡把 `current` 複製成另一個 key（`phase4_start`、`phase4` 就是這樣留的）。

最近的更新：第 5 階段（2026-10-25）更新了維運（三次完整跑，多了調查與報告一組；之前的 `current` 複製成 `todo25`）與 `task_selftest`（18）；主對話、提煉、數據分析沒有更新（結果見上表）。收尾（2026-11-17）：拿掉工作流引擎，`workflow.json` 與 `offline.json` 的 `workflow_selftest` 刪掉；`offline.json` 更新 `chat_selftest`、`task_selftest`、`integrity`；維運的 `current` 補上每一次的結果、拿掉 `totals`（設計筆記 2.25）；收尾的真模型評測（主對話 33/33、維運的檔案與調查每個情境都跟基準一樣）沒有更新真模型的基準。拿掉任務引擎與 Plan 模式（2026-11-18）：`offline.json` 的 `task_selftest` 刪掉，更新 `chat_selftest`（17）、`ops_selftest`（3）、`integrity`（8，範本的檢查改成每個模組各自核對）；真模型的基準沒有更新（之後的基準以新架構為主，設計筆記 2.26）。同一天加了 `repo_selftest`（7，真實專案評測的自我測試）；真實專案評測的
真模型結果不存基準（現在的版本只量一次當對照，新架構每一版跑 3 次之後才存，設計筆記 2.27）。收據（D10 第 1 步）：`skills` 108（多了
`receipt` 一組 8 項）、`chat_selftest` 18（`t_receipts`）。
