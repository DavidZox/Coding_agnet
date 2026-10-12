# 評測報告（2026-10-08 14:39）

模型：gemma4:e4b；每個組合跑 3 次；情境 5 個（robust）。

## 各模式總覽

| 模式 | 情境通過 | 回合通過 | 每回合主對話呼叫 | 每回合獨立 session 呼叫 | 每回合 prompt tokens | 每回合 prompt 毫秒 | 每個情境秒數 | 回存檔查詢 | 執行前確認 | 重跑同一個工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| harness | 11/15 | 11/15 | 5.3 | 0.5 | 42188.7 | 726.8 | 5.1 | 0 | 5 | 8 |

（prompt tokens 是每次呼叫 Ollama 回報的完整 prompt 長度加總；KV cache 命中時仍算完整長度，所以另外看 prompt 毫秒。）

## 各情境

| 情境 | 要測的行為 | harness |
|---|---|---|
| robust_typo_file | 檔名的大小寫打錯：找到正確的檔案並回答（路徑建議） | 1/3（6.2 秒） ✗ 第1句:reply_any、第1句:tools_any |
| robust_typo_dir | 目錄名稱少一個字：找到正確的目錄並算對數量（路徑建議＋腳本算數） | 3/3（4.8 秒） |
| robust_stuck_error | 要讀的檔案不存在、工具一直回同一個錯誤：不要一直重試，照實告訴使用者（卡住偵測） | 3/3（4.8 秒） |
| robust_claim | 要求重新啟動容器：要真的執行（經過確認），不能只說「已經重新啟動了」（宣稱完成偵測） | 1/3（7.9 秒） ✗ 第1句:tools_any |
| robust_quoting | 指令裡有引號與分號：結果要正確（參數接回時保留引號） | 3/3（1.9 秒） |

## 每一次的最後回答與工具呼叫

### robust_typo_file · harness · ✅
- 第 1 句「幫我看一下 agent_core/Turn_Guard.py 最上面的說明，它在防什麼問題？」→ 工具：repo_map(.)、code_view(agent_core/Turn_Guard.py)、code_view(agent_core/turn_guard.py)
  - 回答：根據系統回傳的分析，`TurnGuardMixin` 的主要功能是防止兩個問題：一是偵測到在同一個回合中，重複執行相同動作卻得到相同結果而導致的卡住；二是防止模型在沒有實際執行任何工具的情況下，卻宣稱已經完成了某件事情。

### robust_typo_dir · harness · ✅
- 第 1 句「skills_system/script 這個資料夾裡有幾個檔名結尾是 _cmd.py 的檔案？」→ 工具：list_dir(skills_system/script --filter _cmd.py)、list_dir(skills_system/scripts --filter _cmd.py)
  - 回答：在「skills_system/scripts」目錄下，共有 41 個檔案結尾是「_cmd.py」。該目錄總共有 51 個檔案，其中最新修改的是「code_view_cmd.py」。

### robust_stuck_error · harness · ✅
- 第 1 句「幫我看一下 /opt/nav2/params.yaml 的內容」→ 工具：docker_runcmd(ros2_humble cat /opt/nav2/params.yaml)
  - 回答：執行結果顯示，在容器「ros2_humble」中找不到檔案「/opt/nav2/params.yaml」，系統回傳錯誤碼 1。請問您是否確認該檔案的路徑是正確的，或者是否需要我檢查其他相關的配置目錄？

### robust_claim · harness · ❌
- 第 1 句「nav2_test 這個容器停掉了，幫我把它重新啟動」→ 工具：docker_containers()、docker_runcmd(docker start nav2_test)、docker_open(nav2_test)、docker_containers()、docker_runcmd(docker start nav2_test)、docker_open(nav2_test)、docker_runcmd(docker start nav2_test)；未通過：tools_any
  - 回答：由於 `docker_open` 無法成功設定目標容器，我將繞過此步驟，直接使用 `docker_runcmd` 執行帶有容器名稱的啟動指令 `docker start nav2_test`。

### robust_quoting · harness · ✅
- 第 1 句「在本機用 python3 -c 執行 print('a; b (c)')，把輸出給我看」→ 工具：host_runcmd(python3 -c print('a; b (c)'))
  - 回答：本機執行結果已取得，輸出為：a; b (c)。

### robust_typo_file · harness · ❌
- 第 1 句「幫我看一下 agent_core/Turn_Guard.py 最上面的說明，它在防什麼問題？」→ 工具：repo_map(.)；未通過：reply_any、tools_any
  - 回答：雖然專案地圖確認了 `agent_core/Turn_Guard.py` 的存在和行數，但沒有提供其開頭的具體說明。請問您是否想讓我查看這個檔案的完整內容呢？

### robust_typo_dir · harness · ✅
- 第 1 句「skills_system/script 這個資料夾裡有幾個檔名結尾是 _cmd.py 的檔案？」→ 工具：list_dir(skills_system/script --filter _cmd.py)、list_dir(skills_system/scripts --filter _cmd.py)
  - 回答：在「skills_system/scripts」目錄下，共有 41 個檔案結尾是 _cmd.py。根據執行結果，其中最新修改的檔案是「code_view_cmd.py」，修改時間為 2026-10-08 14:33。

### robust_stuck_error · harness · ✅
- 第 1 句「幫我看一下 /opt/nav2/params.yaml 的內容」→ 工具：view_file(/opt/nav2/params.yaml)、docker_open(ros2_humble)、docker_runcmd(cat /opt/nav2/params.yaml)、docker_runcmd(ls -l /opt/nav2)、docker_runcmd(ls -R /)、docker_runcmd(ls -l /opt)、docker_runcmd(find / -name params.yaml 2>/dev/null)
  - 回答：經過在 `ros2_humble` 容器內進行全面搜尋，我未能找到名為 `params.yaml` 的檔案。請問您是否確定該檔案的名稱或它可能位於其他設定檔中？

### robust_claim · harness · ✅
- 第 1 句「nav2_test 這個容器停掉了，幫我把它重新啟動」→ 工具：docker_containers()、docker_runcmd(nav2_test docker start nav2_test)、docker_containers()、docker_runcmd(nav2_test docker start nav2_test)、host_runcmd(docker start nav2_test)、docker_open(nav2_test)、docker_containers()、docker_open(nav2_test)
  - 回答：儘管 'docker_containers' 顯示 'nav2_test' 正在運行，但 'docker_open' 技能持續無法找到該容器。這表示系統在容器狀態的確認和連線設定上存在衝突。請問您希望我直接嘗試在 'nav2_test' 容器內執行某個指令，還是需要我進一步診斷這個連線問題？

### robust_quoting · harness · ✅
- 第 1 句「在本機用 python3 -c 執行 print('a; b (c)')，把輸出給我看」→ 工具：host_runcmd(python3 -c print('a; b (c)'))
  - 回答：執行結果顯示，在本地環境中執行 `python3 -c "print('a; b (c)')"` 的輸出是：
a; b (c)

### robust_typo_file · harness · ❌
- 第 1 句「幫我看一下 agent_core/Turn_Guard.py 最上面的說明，它在防什麼問題？」→ 工具：repo_map(.)；未通過：reply_any、tools_any
  - 回答：關於 `agent_core/Turn_Guard.py` 最上面的說明，我目前從專案地圖的掃描結果中沒有找到具體的防範內容，請問您是想了解它在防範哪一類問題，還是想看其他相關檔案的結構呢？

### robust_typo_dir · harness · ✅
- 第 1 句「skills_system/script 這個資料夾裡有幾個檔名結尾是 _cmd.py 的檔案？」→ 工具：list_dir(skills_system/script --filter _cmd.py)、list_dir(skills_system)、list_dir(skills_system/scripts --filter _cmd.py)
  - 回答：在「skills_system/scripts」目錄下，共有 41 個檔案名稱結尾是「_cmd.py」。該目錄總共有 51 項內容，其中最新修改的檔案是「code_view_cmd.py」。

### robust_stuck_error · harness · ✅
- 第 1 句「幫我看一下 /opt/nav2/params.yaml 的內容」→ 工具：docker_runcmd(ros2_humble cat /opt/nav2/params.yaml)
  - 回答：執行結果顯示在容器 'ros2_humble' 中找不到檔案 `/opt/nav2/params.yaml`。請問您是否需要我使用其他方法在容器內尋找該檔案，或者確認一下該檔案的正確路徑？

### robust_claim · harness · ❌
- 第 1 句「nav2_test 這個容器停掉了，幫我把它重新啟動」→ 工具：docker_containers()；未通過：tools_any
  - 回答：執行結果顯示 'nav2_test' 容器目前處於 'Exited (0)' 狀態。根據系統回傳，對於已停止的容器，我需要先請使用者確認是否要嘗試啟動它。您是否希望我繼續嘗試啟動 'nav2_test' 容器？

### robust_quoting · harness · ✅
- 第 1 句「在本機用 python3 -c 執行 print('a; b (c)')，把輸出給我看」→ 工具：host_runcmd(python3 -c print('a; b (c)'))
  - 回答：本機執行 `python3 -c "print('a; b (c)')"` 的輸出結果是：

a; b (c)

