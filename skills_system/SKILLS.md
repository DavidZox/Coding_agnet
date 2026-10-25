# Agent Skills Index

> 輕量索引：`action.command` 填技能名稱取得該技能的規格文件（這一輪不執行），下一輪改填規格文件標明的腳本路徑（如 `scripts/cd_cmd.py`）、參數放 `args` 才會真正執行；文件裡 `EXECUTE: 路徑 參數` 的範例即 command 與 args。

> **共同回傳慣例**：成功以 `[PASS]` 開頭；失敗（含逾時）以 `[ERROR]` 開頭並附原因與下一步。各技能有自己的逾時上限（見規格），系統另有 600 秒總逾時。收到 `[ERROR]` 照訊息的下一步做（修正參數、先用它說的技能查、或問使用者），不要原樣重試。長的輸出分成 `## 章節`；提煉結果與 result_* 引用的行號都是存檔原文的行號（`result_view <編號> --from <行號>`）。

> **目標容器**：容器技能的 `<container_name>` 可省略＝Current Agent State 的 CURRENT_TARGET_CONTAINER（`docker_open` 選定／切換；成功操作過的容器會自動成為目標）。已有目標時直接用，不要再問使用者要看哪個容器。

> **ROS 2 Workspace 狀態**：`CURRENT_ROS2_WORKSPACE` 只適用於 `ROS2_WORKSPACE_CONTAINER` 所記錄的容器。ROS2_* 技能與數據技能會自動載入 /opt/ros、這個 Workspace 與執行中節點的 ROS_DOMAIN_ID；`docker_runcmd` 不會，容器裡的 ros2 指令要自己 source，或改用 `ROS2_workspace_env --command`。Workspace 路徑不知道時用 `ROS2_workspace_env --discover` 找，不要先問使用者。

> **ROS 2 數據解析的執行邊界**：數據技能（mcap_*、rosout_parser）由主機端呼叫，讀檔與 ROS 2 訊息反序列化在目標容器內執行（自動載入 /opt/ros 與 Workspace overlay；自訂訊息型別讀不到時先用 ROS2_workspace_env 確認 Workspace）。路徑以容器內路徑為準，主機路徑會依容器的 bind mount 自動換算。**數據**可以是實驗資料夾、bag 資料夾、切片資料夾、`.mcap`、實驗名稱或 `latest`；省略時用 CURRENT_ANALYSIS_DATA（成功操作過的數據會自動成為目前的數據）。

## ROS 2 數據解析（主要功能）
> 問題要同時看 Log 與好幾個 Topic（「發生了什麼、前後有哪些變化、什麼時候恢復」）用 analysis_run；只看一個 Topic、一個值、Log 的時間點，直接用下面對應的技能。
- [analysis_run](tools/analysis_run.md) — 數據分析（全部由程式做）：Log 去重＋量全部 Topic 的事實 → 事實報告（每個重要的時間點一則重點、各 Topic 的結果、時間線、Log 的對照；不判斷原因），依報告回答
- [mcap_recorder](tools/mcap_recorder.md) — 在目標容器內定時錄製 ROS 2 Topic（toolkit 格式：bag、rosout.log、terminal.log），錄完自動建立全域 Topic Metadata 索引
- [rosout_parser](tools/rosout_parser.md) — 錄製數據（MCAP）裡的 Log 智慧過濾：/rosout 重複的 Log 合併成唯一訊號（L#：層級、Node、次數、時間戳），找異常的時間點；主機上一般的文字 Log 用 search_text
- [mcap_analyzer](tools/mcap_analyzer.md) — 全域 Topic Metadata（時間範圍、每個 Topic 的型別、筆數、頻率、角色）；`--topic` 看每個 Key 的型別、維度與類別；`--key --preview` 看原始值
- [mcap_feature_measure](tools/mcap_feature_measure.md) — 量測 Key 的特徵：數值統計（極值、均值、標準差、斜率、尖峰）、向量分量、狀態跳轉、訊息中斷、字串裡的 JSON 欄位；`--where` 門檻條件（第一次是什麼時候、持續多久）
- [mcap_slicer](tools/mcap_slicer.md) — 依 Log 訊號（L#）或時間點前後各取幾秒，切出 toolkit 格式的 sliced_bag_*

## 系統內建
- [list_dir](tools/list_dir.md) — 查看本機某一層目錄（不含子目錄）：目錄與檔案分開列，標頭算好數量與最新修改；`--filter 關鍵字` 計數、`--newest N` 找最新修改的
- [search_text](tools/search_text.md) — 在檔案「內部文字」裡搜關鍵字（`a|b` 同義詞、不分大小寫），依檔案分組並算好命中筆數；Log 檔、設定檔都能搜；預設略過 colcon 的 build／install／log 目錄與 .git（指定的路徑本身在裡面就照搜）
- [find_file](tools/find_file.md) — 依「名稱關鍵字」遞迴找檔案與目錄（`"*.launch.py"` 萬用字元、含 / 比對路徑），依目錄分組並算好數量；只看一層或找最新的用 list_dir --newest
- [code_ast_reader](tools/code_ast_reader.md) — 先看一個 Python 檔的結構（類別、函式完整簽名、docstring、每個 def 的行號範圍），再用 view_file --from 只讀需要的那段
- [change_dir](tools/change_dir.md) — 切換本機的工作目錄（之後的本機技能與相對路徑都以這裡為準；host_runcmd 指令裡的 cd 不會保留）
- [view_file](tools/view_file.md) — 看本機文字檔（每行附行號；--from／--lines 看一段、--tail 看最後幾行）；技能規格文件由 EXECUTE 自動載入，不用這個
- [host_runcmd](tools/host_runcmd.md) — 其他技能做不到的本機 shell 指令（不能互動、不保留背景程序；唯讀的直接執行，其他的會先請使用者確認）
- [csv_query](tools/csv_query.md) — 查 CSV／TSV 表格：欄位、篩選、整體或每一組的最大／最小／平均／筆數、排序（數字由腳本算好，可排成 Markdown 表格）；資料表的問題用這個，不要自己寫 python
- [file_ops](tools/file_ops.md) — 改本機的文件：建目錄、複製、移動／改名、寫入或附加文字檔、取代檔案裡的一段文字；改 YAML 設定檔的一個值用 set（`--after "name: amr_07"` 只改那一台的那一行）；會先請使用者確認；不提供刪除

## 工作流（多步驟，程式照步驟做）
> 使用者的任務正好是下面某一個時用 `workflow_run <名稱> 名稱=值 …`（值從使用者的話取得，拿不到的先問使用者），不要自己一個技能一個技能做：步驟、檢查、「做完了沒」由程式照規格判斷；會改變狀態的步驟開始時系統會請使用者確認一次，不用先問。停在【確認】時 `workflow_run --continue`。
- [workflow_run](tools/workflow_run.md) — 執行下面列的工作流；`--continue` 接著做、`--cancel` 不做了、`--list` 列出全部
  - `stuck_package_fix` — 工作包卡住、不往下一站：查原因；完成訊號遺失才補發、等它跑完、有給檔案就寫處理紀錄；其他原因只回報、不修改｜`workflow_run stuck_package_fix wp_id=<工作包> [note_file=<檔案>]`
  - `config_edit` — 改設定檔裡某一台機器人那一段的一個值（每台各一段的設定檔；設定只有一處、沒有分機器人的直接 `file_ops set <檔案> <名稱> <值>`）：只改那一段的那一行、改完確認；使用者要先備份（或使用者提到的文件規定要備份）時加 `backup=.bak`（另外留同目錄的備份），只說改值就不加｜`workflow_run config_edit file=<檔案> robot=<機器人> key=<設定名稱> value=<新的值> [backup=.bak] [block="<區塊開頭的字，預設 id: 機器人>"]`
  - `dispatch_and_confirm` — 派工作包給指定的機器人並等它跑完再回報｜`workflow_run dispatch_and_confirm robot=<機器人> stops=<站點1,站點2,…（照順序；「從 A 到 B」的 A 也要寫）> [wp_id=<編號>]`
  - `container_restart_verify` — 重新啟動一直在跑的服務容器並確認 Up（跑完就結束的備份、批次容器不適用，直接 docker_ctl restart）；可以在容器裡跑唯讀指令確認設定、寫紀錄｜`workflow_run container_restart_verify container=<容器> [check_command="<唯讀指令>"] [expect=<要看到的字>] [note_file=<檔案>]`
  - `reassign_package` — 工作包派不出去：是原本那台的問題才取消、用同樣的站點改派給指定的機器人並等它跑完｜`workflow_run reassign_package wp_id=<工作包> robot=<機器人>`

## 多步驟任務
- [task_run](tools/task_run.md) — 沒有對應的工作流、又是複雜的維運任務（4 步以上、跨檔案／容器／ROS 2／調度系統、或要改好幾個狀態）用這個：args 填使用者的原話；系統先規劃、先查清楚，要改變狀態的步驟系統會請使用者確認（不用先問），再一步一步執行並檢查，回報每一步的結果與核對過的事實

## 容器化環境
- [docker_containers](tools/docker_containers.md) — 列出目前所有容器（名稱、狀態、映像檔），可只看運行中或以關鍵字過濾；要進入容器前先用這個確認完整名稱
- [docker_images](tools/docker_images.md) — 列出本機所有映像檔（名稱、tag、大小），建立容器前先用這個確認映像檔存在
- [docker_est](tools/docker_est.md) — 用映像檔（可帶 tag）建立並啟動容器，可指定名稱（--name）、指令（--cmd）、--network、-e；會先請使用者確認
- [docker_open](tools/docker_open.md) — 進入指定名稱的 container 並設為目標容器（之後容器技能可省略名稱；要換容器再用一次）
- [docker_runcmd](tools/docker_runcmd.md) — 在容器裡執行一行 shell 指令（目錄會保留；不會自己結束的要包 timeout）；不是唯讀的會先確認
- [docker_ctl](tools/docker_ctl.md) — 容器本身的狀態、log（含 stderr；--since 接著看；行數多時整理成唯一訊號）、環境變數與設定，以及啟動／停止／重新啟動容器（會先請使用者確認）
- [ROS2_workspace_env](tools/ROS2_workspace_env.md) — 找出（--discover）或確認容器內的 ROS 2 Workspace 並記錄（ROS2_*、數據技能都會載入它）；可在載入後執行一行指令

## 多模態資訊
- [stt_engine](tools/stt_engine.md) — 把音檔轉成文字（--file，不需要有人在旁邊）；使用者要用說的時候也可以用麥克風錄音後辨識
- [image_inspect](tools/image_inspect.md) — 對指定路徑的影像檔（截圖、相機快照）依提示詞做視覺模型分析，回傳文字描述

## ROS2套件
- [ROS2_domain_id](tools/ROS2_domain_id.md) — 看 shell 與正在跑的節點各在哪個 ROS_DOMAIN_ID（topic／node 列表是空的時用）；set 寫進容器的 ~/.bashrc（會先請使用者確認）
- [ROS2_topic_list](tools/ROS2_topic_list.md) — 在容器內查詢 topic 列表（依命名空間分組、算好總數、寫明用的 domain）；`--filter 關鍵字` 只列符合的、`--types` 附型別
- [ROS2_topic_echo](tools/ROS2_topic_echo.md) — 問現在的值：讀指定 topic 的一筆訊息（直接讀，不用問要觀察多久）；問一段時間內的變化才加 `--duration`：發布方式與中斷、每個欄位的變化（同 mcap_feature_measure）、`--where 欄位<值` 門檻判斷
- [ROS2_node_list](tools/ROS2_node_list.md) — 在容器內查詢 node 列表（依命名空間分組、算好總數、寫明用的 domain）；`--filter 關鍵字` 只列符合的並計數
- [ROS2_node_info](tools/ROS2_node_info.md) — 指定 node 名稱看它的訂閱、發布、服務、動作（各節算好數量；找不到時列出相近的 node）
- [ROS2_param](tools/ROS2_param.md) — 查 node 的參數（執行中的實際值，以這個為準、不是設定檔）；set 會先請使用者確認
- [ROS2_topic_pub](tools/ROS2_topic_pub.md) — 對 topic 發布訊息（預設一次；會先看訂閱者與 QoS；會先請使用者確認）

## 調度系統
- [workpackage_send](tools/workpackage_send.md) — 對任務協調器 orchestrtor 發送多站點 work package（站點寫名稱、節點 id 或語意名稱；可設 N 輪或無限循環；送出前核對、送出後確認收到）
- [workpackage_status](tools/workpackage_status.md) — 查 work package 狀態：一幀快照；--watch 觀察一段時間、整理每個工作包／工作項／機器人的變化；--until-done 等指定的工作包跑完（看到完成就結束；看得出卡住——完成訊號遺失、閒著的機器人一直不接授權——就提早結束）；--until-confirmed 等目前這一站的授權有結果（只要確認授權時用）
- [workpackage_cancel](tools/workpackage_cancel.md) — 取消（刪除）一個 work package（先確認存在、送出後確認消失），orchestrtor 停止派下一站
- [overpending_cancel](tools/overpending_cancel.md) — 刪除卡在 OverPending 逾時區的單站工作項（id 含 ::）；不在逾時區時可 --wait 等它進來再刪
- [semantic_map](tools/semantic_map.md) — 語義地圖：站點（名稱／節點 id／語意名稱）、說明、路段，對應目前機器人與工作包；也可只列站點或機器人
- [rmf_handshake](tools/rmf_handshake.md) — 機器人或工作包的授權交握：診斷卡住的原因（離線、沒回應、回 no、完成訊號遺失、在等忙碌的機器人）；必要時手動回 yes／no 或補發完成訊號（會先請使用者確認）

## 工具結果存檔
- [result_recall](tools/result_recall.md) — 追問任何存檔的內容時用（檢索清單裡的舊紀錄、或剛剛的提煉沒寫到的細節）：帶編號＋使用者的話，系統讀完整原文依問題提煉（每條附原文的行號）
- [result_grep](tools/result_grep.md) — 使用者要找某個字串／名稱出現在存檔哪幾行時用（a|b 同義詞、前後幾行）；一般追問用 result_recall
- [result_view](tools/result_view.md) — 讀某個存檔的第 N 行起 M 行（行號＝提煉結果、result_grep 引用的行號），或 `--outline` 看原文有哪幾節
- [result_list](tools/result_list.md) — 檢索清單裡沒有相關的一筆、或要瀏覽更早／更多的存檔時，列出存檔索引（編號、腳本、任務、摘要回答）
