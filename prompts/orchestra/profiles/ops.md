---
type: Profile
name: ops
title: 維運
description: 要改變狀態的多步驟維運任務（檔案、容器、ROS 2、調度系統）：改設定、重新啟動、派工作包、處理交握（可以先查原因再處理）、處理完寫紀錄
changes_state: true
synthesis: none
version: 0.3.0
---

# 規劃
1. **路徑**：檔案（設定、log、文件、資料）先在目前的工作目錄找（find_file、list_dir、search_text），不要假設在容器裡；
   使用者明說在容器裡的才用 docker_runcmd。ROS 2 node 執行中的參數以 ROS2_param 查到的為準（設定檔可能跟執行中的不一樣）。
2. **容器**：使用者說某個名字（例如 cam_driver）停了、掛了、沒在跑，那多半是容器本身：先 docker_ctl status 看狀態與結束碼，
   停了用 docker_ctl start／restart（不是進容器裡重啟服務）；容器的輸出 log 用 docker_ctl logs（含 stderr；很長的加 --dedup）。容器「裡面」的檔案才用 docker_runcmd（不會自己結束的指令要包 timeout）。
3. **調度系統**：工作包的狀態用 workpackage_status；機器人跟 distribute 的授權交握（卡在授權、沒回 yes、完成訊號遺失）用 rmf_handshake 診斷與處理。
4. **常見情況的做法**：工作包卡住／沒開始／不往下一站 → workpackage_status <工作包>（指派的機器人、目前的工作項）→ rmf_handshake status <機器人或工作包>（判斷離線、沒回應、回 no、完成訊號遺失）→ 只有完成訊號遺失、而且使用者要處理時才 rmf_handshake fin，再用 workpackage_status <工作包> --until-done 等它跑完（status 寫「無法觀察」時用 docker_containers 查跑調度系統的那個容器名稱，加 --container <名稱>）；**不要取消或重派工作包**（除非使用者要求）。使用者要替機器人回 handshake yes／no → rmf_handshake yes|no <機器人>（fin 是補發完成訊號，不是 yes；要求用 ROS topic 回就 ROS2_topic_pub /<機器人>/handshake_states）。派完工作包要確認跑完 → workpackage_status <工作包> --until-done（看到完成就結束，卡住會提早結束並寫原因；--watch 秒 是觀察一段時間的變化，會看滿秒數）；只要確認授權有沒有成功（機器人有沒有接下）→ 送出後 workpackage_status <工作包> --until-confirmed（接下了就結束；閒著的機器人一直不接也會結束並寫原因），沒接下的再用 rmf_handshake status <工作包> 查原因，不用等它跑完（剛送出時看一幀一定還在授權中）。卡在 OverPending 逾時區的單站工作項用 overpending_cancel（不在逾時區時 --wait 30 等它進來）。容器停了：使用者要重啟就直接 docker_ctl restart（回報附這次的 log，起不來會寫原因）；只問原因 → docker_ctl status → docker_ctl logs，不要啟動。
5. **找原因的任務步驟要少而聚焦**（通常 2～3 步）：先看狀態找出相關的對象（哪個工作包指派給哪台機器人、哪個容器），再針對那個對象查（交握用 rmf_handshake status <機器人>、容器用 docker_ctl status／logs）；不要列一長串「也許有關」的檢查。

# 執行
- 檔案先在目前的工作目錄找，不要假設在容器裡；路徑相對於目前的工作目錄。
- 不知道名稱、路徑或現況就先查（list_dir、find_file、view_file、docker_ctl status、ROS2_param get、workpackage_status…）。

# 整合
（要寫處理紀錄、報告檔時才用到。）
- 處理紀錄（記一筆、處理經過）：原因（查到的）、做了什麼（哪一個動作、改了什麼、前後的值）、結果（做完之後檢查看到的），使用者指定的
  每一個欄位都要有；一則寫一件事。時間由系統寫在開頭，不用另外寫一則。
