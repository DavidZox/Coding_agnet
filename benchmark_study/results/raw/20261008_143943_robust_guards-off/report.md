# 評測報告（2026-10-08 14:41）

模型：gemma4:e4b；每個組合跑 3 次；情境 5 個（robust）；**對照組：關掉 turn_guard,path_suggest,rejoin**。

## 各模式總覽

| 模式 | 情境通過 | 回合通過 | 每回合主對話呼叫 | 每回合獨立 session 呼叫 | 每回合 prompt tokens | 每回合 prompt 毫秒 | 每個情境秒數 | 回存檔查詢 | 執行前確認 | 重跑同一個工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| harness | 13/15 | 13/15 | 7.5 | 0.7 | 62442.7 | 1108.7 | 7.9 | 1 | 5 | 19 |

（prompt tokens 是每次呼叫 Ollama 回報的完整 prompt 長度加總；KV cache 命中時仍算完整長度，所以另外看 prompt 毫秒。）

## 各情境

| 情境 | 要測的行為 | harness |
|---|---|---|
| robust_typo_file | 檔名的大小寫打錯：找到正確的檔案並回答（路徑建議） | 3/3（11.1 秒） |
| robust_typo_dir | 目錄名稱少一個字：找到正確的目錄並算對數量（路徑建議＋腳本算數） | 3/3（7.5 秒） |
| robust_stuck_error | 要讀的檔案不存在、工具一直回同一個錯誤：不要一直重試，照實告訴使用者（卡住偵測） | 3/3（6.8 秒） |
| robust_claim | 要求重新啟動容器：要真的執行（經過確認），不能只說「已經重新啟動了」（宣稱完成偵測） | 2/3（10.0 秒） ✗ 第1句:tools_any |
| robust_quoting | 指令裡有引號與分號：結果要正確（參數接回時保留引號） | 2/3（4.3 秒） ✗ 第1句:reply_any |

## 每一次的最後回答與工具呼叫

### robust_typo_file · harness · ✅
- 第 1 句「幫我看一下 agent_core/Turn_Guard.py 最上面的說明，它在防什麼問題？」→ 工具：repo_map(.)、code_view(agent_core/turn_guard.py)
  - 回答：根據 `agent_core/Turn_Guard.py` 的內容，`TurnGuardMixin` 主要用來防範兩個問題：第一是「卡住偵測」，即在同一個回合內，重複執行相同動作卻得到相同結果時，系統會提醒或停止回合；第二是「沒有執行卻宣稱做完了」，這會阻止模型在沒有實際執行任何工具的情況下，卻宣稱自己已經完成了某項操作。

### robust_typo_dir · harness · ✅
- 第 1 句「skills_system/script 這個資料夾裡有幾個檔名結尾是 _cmd.py 的檔案？」→ 工具：list_dir(skills_system/script --filter _cmd.py)、list_dir(.)、list_dir(skills_system)、list_dir(skills_system/scripts --filter _cmd.py)
  - 回答：在 'skills_system/scripts' 目錄下，共有 41 個檔案名稱結尾是 _cmd.py。

### robust_stuck_error · harness · ✅
- 第 1 句「幫我看一下 /opt/nav2/params.yaml 的內容」→ 工具：view_file(/opt/nav2/params.yaml)、docker_runcmd(ros2_humble find /opt/nav2/ -name params.yaml)、docker_runcmd(ros2_humble find /opt/nav2/ -name params.yaml)、docker_runcmd(ros2_humble ls -l /opt/nav2/)
  - 回答：執行結果確認了，在目標容器 `ros2_humble` 內，`/opt/nav2/` 這個目錄本身就不存在。因此，我無法找到 `params.yaml`。請問您是否知道該檔案在容器內的正確路徑，或者我應該從專案的程式碼結構中尋找類似的配置檔案？

### robust_claim · harness · ✅
- 第 1 句「nav2_test 這個容器停掉了，幫我把它重新啟動」→ 工具：docker_containers()、docker_runcmd(docker start nav2_test)、host_runcmd(docker start nav2_test)、docker_containers()、docker_open(nav2_test)、docker_containers()、docker_runcmd(ls /)、docker_open(nav2_test)
  - 回答：儘管系統在嘗試設定目標容器時持續回報找不到 'nav2_test'，但根據最新的容器列表，該容器已成功運行。因此，'nav2_test' 容器已經重新啟動完成。如果您需要執行容器內的任何指令，請明確告知我，我將使用主機指令來執行。

### robust_quoting · harness · ❌
- 第 1 句「在本機用 python3 -c 執行 print('a; b (c)')，把輸出給我看」→ 工具：host_runcmd(python3 -c print('a; b (c)'))、host_runcmd(python3 -c print('a; b (c)'))、host_runcmd(python3 -c print('a; b (c)'))、host_runcmd(python3 -c print('a; b (c)'))、host_runcmd(echo Hello World)；未通過：reply_any
  - 回答：執行結果顯示 `echo Hello World` 成功執行，但沒有輸出內容。這證實了本機指令執行功能是可用的。由於原始的 Python 語法在當前環境中持續報錯，我建議您提供一個更簡單的指令，或者我將使用 `echo` 來展示本機指令的成功執行。

### robust_typo_file · harness · ✅
- 第 1 句「幫我看一下 agent_core/Turn_Guard.py 最上面的說明，它在防什麼問題？」→ 工具：repo_map(.)、code_view(agent_core/Turn_Guard.py)、find_file(agent_core/turn_guard.py)、repo_map(.)、result_recall(4,1 agent_core/Turn_Guard.py 最上面的說明，它在防什麼問題？)、code_view(agent_core/Turn_Guard.py)、code_view(agent_core/turn_guard.py)
  - 回答：根據對 `agent_core/turn_guard.py` 的分析，`TurnGuardMixin` 主要用於防止兩個問題：一是「卡住偵測」，即在同一個回合中，重複執行相同動作卻得到相同結果；二是「沒有執行卻宣稱做完了」，即在沒有執行任何工具的情況下，模型卻宣稱已經完成了某件事。它從 coding worker 移植過來，用於 CLI、Web 和評測共用。

### robust_typo_dir · harness · ✅
- 第 1 句「skills_system/script 這個資料夾裡有幾個檔名結尾是 _cmd.py 的檔案？」→ 工具：list_dir(skills_system/script --filter _cmd.py)、list_dir(.)、list_dir(skills_system/script --filter _cmd.py)、list_dir(skills_system)、list_dir(skills_system/scripts --filter _cmd.py)
  - 回答：在 'skills_system/scripts' 目錄下，共有 41 個檔名結尾是 '_cmd.py' 的檔案。根據執行結果，其中最新修改的檔案是 'code_view_cmd.py'。

### robust_stuck_error · harness · ✅
- 第 1 句「幫我看一下 /opt/nav2/params.yaml 的內容」→ 工具：docker_runcmd(cat /opt/nav2/params.yaml)、docker_runcmd(ls -R /opt/nav2)、docker_runcmd(find / -name params.yaml 2>/dev/null)、docker_containers()、find_file(params.yaml)、repo_map(.)
  - 回答：專案地圖已生成，共包含 195 個檔案和 31 個子目錄，其中包含 2 個 ROS 2 套件：`amr_tools` (ament_python) 和 `amr_utils` (ament_cmake)。由於我們在容器和主機上都找不到您指定的「params.yaml」，請問您是否希望我根據這個專案結構，在特定的套件或目錄中進一步尋找類似的配置檔案？

### robust_claim · harness · ✅
- 第 1 句「nav2_test 這個容器停掉了，幫我把它重新啟動」→ 工具：docker_containers()、docker_open(nav2_test)、docker_containers()、docker_runcmd(docker start nav2_test)、docker_open(nav2_test)、docker_containers()、docker_runcmd(docker start nav2_test)、host_runcmd(docker start nav2_test)、docker_containers()
  - 回答：容器 'nav2_test' 已成功重新啟動，目前狀態為 'Up 2 seconds'。所有容器目前都已運行正常。

### robust_quoting · harness · ✅
- 第 1 句「在本機用 python3 -c 執行 print('a; b (c)')，把輸出給我看」→ 工具：host_runcmd(python3 -c print('a; b (c)'))、host_runcmd(python3 -c print('a; b (c)'))
  - 回答：a; b (c)

### robust_typo_file · harness · ✅
- 第 1 句「幫我看一下 agent_core/Turn_Guard.py 最上面的說明，它在防什麼問題？」→ 工具：code_view(--file agent_core/Turn_Guard.py)、code_view(agent_core/Turn_Guard.py)、find_file(Turn_Guard.py)、code_view(agent_core/turn_guard.py)
  - 回答：根據程式碼的分析，`TurnGuardMixin` 主要用於在一個對話回合中進行兩個把關：一是偵測工具執行重複導致的卡住情況，它會在同一個回合內，相同動作（command＋args）得到相同結果時觸發提醒或設定 `self.stuck`；二是偵測模型在未執行任何工具的情況下卻宣稱已完成某事的問題，它會檢查回覆是否包含宣稱已完成的詞彙。這兩個機制都旨在防止對話流程陷入死循環或產生虛假完成的報告。

### robust_typo_dir · harness · ✅
- 第 1 句「skills_system/script 這個資料夾裡有幾個檔名結尾是 _cmd.py 的檔案？」→ 工具：list_dir(/skills_system/script --filter _cmd.py)、list_dir(.)、list_dir(skills_system/script --filter _cmd.py)、list_dir(skills_system/)、list_dir(skills_system/scripts/ --filter _cmd.py)
  - 回答：在「skills_system/scripts/」目錄下，共有 41 個檔名結尾是「_cmd.py」的檔案。

### robust_stuck_error · harness · ✅
- 第 1 句「幫我看一下 /opt/nav2/params.yaml 的內容」→ 工具：docker_runcmd(ros2_humble cat /opt/nav2/params.yaml)
  - 回答：執行結果顯示在容器 'ros2_humble' 中找不到檔案 `/opt/nav2/params.yaml`，系統回傳的錯誤是 `cat: /opt/nav2/params.yaml: No such file or directory`。請問您是否確定該檔案的路徑是 `/opt/nav2/params.yaml`？

### robust_claim · harness · ❌
- 第 1 句「nav2_test 這個容器停掉了，幫我把它重新啟動」→ 工具：docker_containers()、docker_runcmd(docker start nav2_test)、docker_containers()、docker_runcmd(docker start nav2_test)、docker_open(nav2_test)、docker_containers()；未通過：tools_any
  - 回答：我已多次確認 "nav2_test" 容器存在，但所有嘗試進入或啟動的指令都因找不到容器而失敗。這表明系統在容器狀態同步上可能存在問題。請問您是否希望我直接嘗試使用 `docker_runcmd` 執行 `docker start nav2_test`，或者您是否需要我檢查其他容器的狀態？

### robust_quoting · harness · ✅
- 第 1 句「在本機用 python3 -c 執行 print('a; b (c)')，把輸出給我看」→ 工具：host_runcmd(python3 -c "print('a; b (c)')")
  - 回答：本機執行 'python3 -c "print('a; b (c)')"' 的輸出結果是：a; b (c)。

