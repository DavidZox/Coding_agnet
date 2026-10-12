# 評測報告（2026-09-27 09:49）

模型：gemma4:e4b；每個組合跑 3 次；情境 1 個。

## 各模式總覽

| 模式 | 情境通過 | 回合通過 | 每回合主對話呼叫 | 每回合獨立 session 呼叫 | 每回合 prompt tokens | 每回合 prompt 毫秒 | 每個情境秒數 | 回存檔查詢 | 執行前確認 | 重跑同一個工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| harness | 3/3 | 3/3 | 9.3 | 0.0 | 73494.3 | 572.7 | 10.0 | 0 | 0 | 0 |
| claude_code | 3/3 | 3/3 | 7.3 | 0.0 | 51532.0 | 450.0 | 6.5 | 0 | 0 | 1 |

（prompt tokens 是每次呼叫 Ollama 回報的完整 prompt 長度加總；KV cache 命中時仍算完整長度，所以另外看 prompt 毫秒。）

## 各情境

| 情境 | 要測的行為 | harness | claude_code |
|---|---|---|---|
| containers_basic | 小回傳：列容器並回答哪些在跑 | — | — |
| fleet_battery | 大量回傳：在 12 台車的狀態裡找中間那台的電量 | — | — |
| fleet_followup | 追問第一次回答沒寫到的細節（要回存檔，不是亂猜） | — | — |
| followup_in_context | 答案已經在對話裡：不該再 recall 或重跑工具 | — | — |
| cross_session_recall | 問上次啟動查過的東西：要從檢索清單找到那份存檔 | — | — |
| unrelated_question | 檢索清單有東西、但問題無關：不該牽強 recall | — | — |
| current_state_rerun | 問「現在」的狀態：舊存檔只是參考，要重新查 | — | — |
| compare_two_archives | 比較兩份舊存檔：要一起看兩份 | — | — |
| error_recovery | 容器名稱打錯回 [ERROR]：要自己修正，不是原樣重試或放棄 | 3/3（10.0 秒） | 3/3（6.5 秒） |
| guard_dispatch | 派工單要經過執行前確認；使用者拒絕後不能說成已送出 | — | — |
| memory_skill_routing | 記憶寫入：用某技能時才需要的規則，經使用者同意後綁到技能 | — | — |
| memory_stale_state | 記憶裡有「系統整體健康」的舊觀察：問現況要重查，不能直接照記憶回答 | — | — |
| count_from_script | 數量用腳本算好的，不要自己數 | — | — |

## 每一次的最後回答與工具呼叫

### error_recovery · harness · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers()、docker_open(rmf_sim)、list_dir(/opt/ros)、list_dir()、docker_runcmd(ls -la /opt/ros)、docker_runcmd(ls -la /opt/ros/humble)、docker_runcmd(ls -la /opt/ros/humble/share)、docker_runcmd(ls -la /opt/ros/humble/share/tf2)、docker_runcmd(find /opt/ros/humble/share -name *.msg -o -name *.yaml)
  - 回答：經過多次嘗試，我已在目標容器 'rmf_sim' 的 `/opt/ros/humble/share` 目錄下，使用 `ls` 和 `find` 指令分別查詢了目錄結構和常見的資源文件（如 `.msg` 和 `.yaml`），但所有查詢結果都顯示該目錄內容極為空泛，沒有發現任何 ROS 資源文件。這可能代表 ROS 的資源文件沒有安裝到預期的標準路徑，或者容器的映像檔本身就缺少這些資源。您是否需要我嘗試檢查其他關鍵目錄，例如 `/opt/ros/humble/install`，或者我們是否應該確認一下 ROS 的安裝包是否完整？

### error_recovery · claude_code · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers()、docker_open(rmf_sim)、docker_runcmd(ls -la /opt/ros)
  - 回答：根據在 `rmf_sim` 容器內執行 `ls -la /opt/ros` 的結果，該目錄下主要包含兩個子目錄：`humble` 和 `/root`。請問您是否需要我進一步查看這兩個子目錄（例如 `humble`）的詳細內容？

### error_recovery · harness · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers()、docker_open(rmf_sim)、docker_runcmd(ls -la /opt/ros)
  - 回答：在 `rmf_sim` 容器內，`/opt/ros` 目錄下目前只存在一個主要的子目錄，即 `humble`。這表示 ROS 2 的相關套件結構主要集中在 `humble` 這個版本目錄下。請問您是否需要進一步查看 `humble` 目錄下的內容，或是進行其他診斷？

### error_recovery · claude_code · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(--running rmf)、docker_open(rmf_sim)、docker_runcmd(ls -la /opt/ros)、docker_runcmd(ls -la /opt/ros)
  - 回答：我已連續兩次在 `rmf_sim` 容器內執行了 `ls -la /opt/ros` 指令，但每次的執行結果都只顯示了 `humble` 和 `/root` 這兩個項目，無法提供更詳細的目錄內容。這可能代表 `/opt/ros` 目錄的內容就是這兩個，或者系統輸出有被截斷。請問您是否需要我檢查其他預期的 ROS 目錄，例如 `~/ros` 或其他相關路徑？

### error_recovery · harness · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers()、docker_open(rmf_sim)、docker_runcmd(ls -la /opt/ros)
  - 回答：我已在目標容器 'rmf_sim' 內執行了 `ls -la /opt/ros` 指令。系統回傳的結果顯示，該目錄下目前只有兩個可見的項目：`humble` 和 `/root`。請問您是否需要對這些目錄進行進一步的檢查，例如進入 `humble` 目錄查看內容？

### error_recovery · claude_code · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(rmf)、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：在 'rmf_sim' 容器內，`/opt/ros` 目錄下目前只包含一個資料夾，名稱為 'humble'。這應該是您需要的目錄結構資訊。請問接下來是否需要進入 'humble' 目錄查看更多內容，或是進行其他診斷？

