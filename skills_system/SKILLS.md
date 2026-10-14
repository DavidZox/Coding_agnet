
# Agent Skills Index

> 輕量索引：`action.command` 填技能名稱取得該技能的規格文件（這一輪不執行），下一輪改填規格文件標明的腳本路徑（如 `scripts/cd_cmd.py`）、參數放 `args` 才會真正執行；文件裡 `EXECUTE: 路徑 參數` 的範例即 command 與 args。

> **共同回傳慣例**：成功以 `[PASS]` 開頭；失敗（含逾時）以 `[ERROR]` 開頭並附原因與建議。各技能有自己的逾時上限（見規格），系統另有 600 秒總逾時。收到 `[ERROR]` 請依訊息修正參數或回報使用者，不要原樣重試。

> **目標容器**：容器技能的 `<container_name>` 可省略＝Current Agent State 的 CURRENT_TARGET_CONTAINER（`docker_open` 選定／切換；成功操作過的容器會自動成為目標）。已有目標時直接用，不要再問使用者要看哪個容器。

> **ROS 2 Workspace 狀態**：`CURRENT_ROS2_WORKSPACE` 只適用於 `ROS2_WORKSPACE_CONTAINER` 所記錄的容器。只有當它與 `CURRENT_TARGET_CONTAINER` 相同時，才能將該路徑作為目前 Workspace 的候選值。執行前仍須確認 `install/setup.bash` 存在且可載入。每次獨立的 ROS 2 Shell 命令都必須自行載入環境。


> **ROS 2 資料分析執行邊界**：`mcap_recorder`、`rosout_parser`、`mcap_slicer`、`mcap_analyzer` 的入口腳本由主機端 Agent 呼叫，但實際操作資料與 ROS 2 訊息反序列化均在目標 Docker 容器內執行。四支腳本共用 `scripts/_docker_common.py` 的容器選擇、環境載入、逾時與錯誤回報機制。這些工具的輸入、輸出路徑都以容器內路徑解讀；要讓主機讀取輸出，請使用已掛載的共享目錄。

## 系統內建
- [list_dir](tools/list_dir.md) — 查看本機某一層目錄的清單（不含子目錄）；標頭算好數量與最新修改，`--filter 關鍵字` 計數、`--newest N` 找最新修改的檔案
- [search_text](tools/search_text.md) — 在檔案「內部文字」中過濾特定關鍵字，標頭算好命中筆數與檔案數
- [find_file](tools/find_file.md) — 依「檔案名稱關鍵字」遞迴搜尋整棵目錄樹，標頭算好找到幾個；要找某目錄裡最新修改的檔案請用 list_dir --newest
- [code_ast_reader](tools/code_ast_reader.md) — 透過 AST 解析單一 Python 檔的結構（類別、函式簽名、Docstring），無須讀取全文即可掌握架構
- [change_dir](tools/change_dir.md) — 切換當前工作目錄（注意：後端需維護 CWD 狀態）
- [view_file](tools/view_file.md) — 查看診斷報告或腳本內容（技能規格文件會由 EXECUTE 自動載入，不用這個）
- [host_runcmd](tools/host_runcmd.md) — 若要在本機環境直接執行 shell 指令時使用（會改變狀態的指令會先請使用者確認）
- [csv_query](tools/csv_query.md) — 查 CSV／TSV 表格：欄位、篩選、整體或每一組的最大／最小／平均／筆數、排序（數字由腳本算好，可排成 Markdown 表格）；資料表的問題用這個，不要自己寫 python
- [file_ops](tools/file_ops.md) — 改本機的文件：建目錄、複製、移動／改名、寫入或附加文字檔、取代檔案裡的一段文字（例如改設定檔的一個參數；會先請使用者確認）

## 多步驟維運任務
- [ops_run](tools/ops_run.md) — 複雜的維運任務（4 步以上、跨檔案／容器／ROS 2／調度系統、或要改好幾個狀態）用這個：args 填使用者的原話，系統先規劃、把整份計畫給使用者確認（只查詢的計畫不用確認），再一步一步執行並檢查

## 程式開發（Coding）
> 修改、新增、重構程式碼一律用 code_job_send 交給 coding orchestrator（它會探索、規劃、等使用者核准、派 worker 修改並驗證）；主對話只看、只查、只跑測試，不直接改檔案。

- [repo_map](tools/repo_map.md) — 專案地圖：目錄樹＋每個程式檔的類別與函式（含行號，Python 與 C／C++）＋測試指令、建置系統與 git 狀態，認識一個專案時先用
- [code_view](tools/code_view.md) — 帶行號讀程式檔：整份、某一段，或 --symbol 只看某個函式／類別（Python、C／C++）
- [code_search](tools/code_search.md) — 在整個專案的程式碼裡搜尋字串／正規表示式（略過 venv、build），附行號與前後文
- [code_refs](tools/code_refs.md) — 某個函式／類別／變數在哪裡定義、宣告、被誰匯入與使用（Python、C／C++），改名或改參數前列出要一起改的地方
- [code_check](tools/code_check.md) — 靜態檢查：Python 的語法、未定義的名稱、專案內 import；C／C++ 用 gcc／g++ 編譯檢查
- [code_test](tools/code_test.md) — 執行測試：Python 用 pytest、C／C++ 建置後跑 gtest；通過／失敗數由腳本算好、失敗與編譯錯誤附細節；`--coverage` 另外量覆蓋率（列出還沒測到的行）
- [code_diff](tools/code_diff.md) — 看某個 coding job（--job）或 git 工作區改了什麼
- [code_job_send](tools/code_job_send.md) — 要修改／新增／重構程式碼時用：交給 coding orchestrator 規劃，使用者核准後由 worker 修改並驗證
- [code_job_status](tools/code_job_status.md) — 查 coding job 的進度：每一項做到哪、改了哪些檔案、驗證結果、是否在等使用者
- [code_job_cancel](tools/code_job_cancel.md) — 停止 coding job（已改好的檔案保留，可在 Coding 面板還原）

## 容器化環境
- [docker_containers](tools/docker_containers.md) — 列出目前所有容器（名稱、狀態、映像檔），可只看運行中或以關鍵字過濾；要進入容器前先用這個確認完整名稱
- [docker_images](tools/docker_images.md) — 列出本機所有映像檔（名稱、tag、大小），建立容器前先用這個確認映像檔存在
- [docker_est](tools/docker_est.md) — 用映像檔（可帶 tag）建立並啟動容器，可指定容器名稱（--name）與指令（--cmd）；會先請使用者確認
- [docker_open](tools/docker_open.md) — 進入指定名稱的 container 並設為目標容器（之後容器技能可省略名稱；要換容器再用一次）
- [docker_runcmd](tools/docker_runcmd.md) — 若要在容器內使用指令時使用
- [docker_ctl](tools/docker_ctl.md) — 容器本身的狀態、log、環境變數與設定，以及啟動／停止／重新啟動容器（會先請使用者確認）
- [ROS2_workspace_env](tools/ROS2_workspace_env.md) — 確認容器內的 ROS 2 Workspace，載入 install/setup.bash，並在同一個 Shell 執行命令；成功確認後由 Agent 狀態保存路徑


## 多模態資訊
- [stt_engine](tools/stt_engine.md) — 使用者需要進行語音輸入時使用
- [image_inspect](tools/image_inspect.md) — 對指定路徑的影像檔（截圖、相機快照）依提示詞做視覺模型分析，回傳文字描述

## ROS2套件
- [ROS2_domain_id](tools/ROS2_domain_id.md) — 在容器內查詢或修改 ROS_DOMAIN_ID 環境變數（可傳入 0-232 設定新 ID，省略傳參則為查詢）
- [ROS2_topic_list](tools/ROS2_topic_list.md) — 在容器內查詢 topic 列表，標頭算好總數；`--filter 關鍵字` 只列符合的並計數
- [ROS2_topic_echo](tools/ROS2_topic_echo.md) — 讀取指定 topic 的一筆訊息，或 --duration 擷取一段時間整理欄位變化與頻率；`--where 欄位<值` 由腳本做門檻判斷
- [ROS2_node_list](tools/ROS2_node_list.md) — 在容器內查詢 node 列表，標頭算好總數；`--filter 關鍵字` 只列符合的並計數
- [ROS2_node_info](tools/ROS2_node_info.md) — 指定 node 名稱進行 info 命令，獲得 node 詳細資訊
- [ROS2_param](tools/ROS2_param.md) — 查 node 的參數（執行中的實際值，以這個為準、不是設定檔）；set 會先請使用者確認
- [ROS2_topic_pub](tools/ROS2_topic_pub.md) — 對 topic 發布訊息（預設一次；會先請使用者確認）

## 調度系統
- [workpackage_send](tools/workpackage_send.md) — 對任務協調器 orchestrtor 發送多站點 work package（站點可用語意名稱；可設 N 輪或無限循環）
- [workpackage_status](tools/workpackage_status.md) — 查 work package 執行狀態：一幀快照，或 --watch 觀察一段時間並整理變化
- [workpackage_cancel](tools/workpackage_cancel.md) — 取消（刪除）一個 work package，orchestrtor 停止派下一站
- [overpending_cancel](tools/overpending_cancel.md) — 刪除卡在 distribute OverPending 逾時區的單站任務；不在逾時區時可等它進來再刪
- [semantic_map](tools/semantic_map.md) — 語義地圖：站點代號／語意名稱／說明／路段，對應目前機器人與工作包位置；也可只列站點或機器人
- [rmf_handshake](tools/rmf_handshake.md) — 某台機器人跟 distribute 的授權交握：診斷卡住的原因（離線、沒回應、回 no、完成訊號遺失）；必要時手動回 yes／no 或補發完成訊號（會先請使用者確認）

## 工具結果存檔
- [result_recall](tools/result_recall.md) — 追問任何存檔的內容時用（檢索清單裡的舊紀錄、或剛剛摘要沒寫到的細節）：檢索清單裡的舊紀錄、或剛剛摘要沒寫到的細節
- [result_grep](tools/result_grep.md) — 使用者要找某個字串／名稱出現在存檔哪幾行時用（a|b 同義詞、前後幾行）；一般追問用 result_recall
- [result_view](tools/result_view.md) — 讀某個存檔的第 N 行起 M 行，看 grep 命中處的整段原文
- [result_list](tools/result_list.md) — 檢索清單裡沒有相關的一筆、或要瀏覽更早／更多的存檔時，列出存檔索引（編號、腳本、任務、摘要回答） 

## ROS 2 診斷與分析管線 (Agent-Ready)
- [mcap_recorder](tools/mcap_recorder.md) — 在目標容器內錄製 ROS 2 Topic，輸出 MCAP、終端紀錄與 metadata；可選擇保存 /rosout
- [rosout_parser](tools/rosout_parser.md) — 在目標容器內解析 rosout.log，保留來源行號與事件層級；不自動推定與 MCAP 的時間基準一致
- [mcap_slicer](tools/mcap_slicer.md) — 依已確認的 MCAP log_time 奈秒時間戳進行時間切片，輸出切片 MCAP 與 Metadata
- [mcap_analyzer](tools/mcap_analyzer.md) — 在目標容器內列出 Topic／欄位，並以 rclpy.serialization 反序列化指定欄位的時序數據
