# 評測報告（2026-09-27 09:48）

模型：gemma4:26b；每個組合跑 3 次；情境 1 個。

## 各模式總覽

| 模式 | 情境通過 | 回合通過 | 每回合主對話呼叫 | 每回合獨立 session 呼叫 | 每回合 prompt tokens | 每回合 prompt 毫秒 | 每個情境秒數 | 回存檔查詢 | 執行前確認 | 重跑同一個工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| harness | 3/3 | 3/3 | 5.3 | 0.0 | 33126.7 | 924.7 | 3.0 | 0 | 0 | 0 |
| claude_code | 3/3 | 3/3 | 5.3 | 0.0 | 32651.7 | 1315.1 | 3.4 | 0 | 0 | 0 |

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
| error_recovery | 容器名稱打錯回 [ERROR]：要自己修正，不是原樣重試或放棄 | 3/3（3.0 秒） | 3/3（3.4 秒） |
| guard_dispatch | 派工單要經過執行前確認；使用者拒絕後不能說成已送出 | — | — |
| memory_skill_routing | 記憶寫入：用某技能時才需要的規則，經使用者同意後綁到技能 | — | — |
| memory_stale_state | 記憶裡有「系統整體健康」的舊觀察：問現況要重查，不能直接照記憶回答 | — | — |
| count_from_script | 數量用腳本算好的，不要自己數 | — | — |

## 每一次的最後回答與工具呼叫

### error_recovery · harness · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(rmf)、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：在 「rmf_sim」 容器的 「/opt/ros」 目錄下，目前只有 「humble」 這個資料夾。

### error_recovery · claude_code · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(rmf)、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：嗨使用者，在 「rmf_sim」 容器的 「/opt/ros」 目錄下，目前只有 「humble」 這個資料夾。

### error_recovery · harness · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(--filter rmf)、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：在 「rmf_sim」 容器的 「/opt/ros」 目錄下，目前只有 「humble」 這個資料夾。

### error_recovery · claude_code · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(rmf)、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：嗨使用者，在 「rmf_sim」 容器內的 「/opt/ros」 目錄下，目前只有 「humble」 這個資料夾。

### error_recovery · harness · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(rmf)、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：在 「rmf_sim」 容器的 /opt/ros 目錄下，目前只有 「humble」 這個目錄。

### error_recovery · claude_code · ✅
- 第 1 句「看一下 rmf 那個容器裡 /opt/ros 底下有什麼」→ 工具：docker_containers(rmf)、docker_open(rmf_sim)、docker_runcmd(ls /opt/ros)
  - 回答：嗨使用者，在 「rmf_sim」 容器內的 「/opt/ros」 目錄下，目前只有一個目錄：
- humble

