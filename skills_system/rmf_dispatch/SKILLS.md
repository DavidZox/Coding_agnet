# rmf_dispatch：調度系統

調度系統的工作包、站點與機器人：派送工作包、看狀態、取消、授權交握（替機器人回 yes／no、補發完成訊號），語義地圖上的站點與機器人。
不包含：容器本身的狀態、log 與啟停，ROS 2 的 node 與參數（robotics_infra）；工作目錄裡的檔案（repo_analysis）。

## 做法
- **常見情況的做法**（照順序做，查到原因就回報；使用者沒要求的處理不要做）：
  - 工作包卡住／沒開始／不往下一站：`workpackage_status <工作包>`（看指派的機器人、目前的工作項）→ `rmf_handshake status <機器人或工作包>`（它會判斷：離線、沒回應、回 no、完成訊號遺失；寫「無法觀察」時用 docker_containers 查跑調度系統的那個容器名稱，加 `--container <名稱>` 再看一次）→ 判斷是「完成訊號遺失」、使用者又要你處理（「幫我處理」「讓它跑完」）時，直接 `rmf_handshake fin <機器人>`（系統會請使用者確認，不用先問），補發後用 `workpackage_status <工作包> --until-done` 等它跑完（看到完成就結束，不用猜秒數）（補發被拒時照訊息回報，不要加 `--no-check` 硬送）；其他情況、或使用者只要查原因時，回報原因與建議，不要取消或重派（除非使用者要求）。
  - 使用者明確要你替機器人回 handshake yes／no（「對 amr_07、amr_12 各回一次 yes」）：直接 `rmf_handshake yes <機器人> [<機器人> …]`（或 `no`；走 manual_trigger，系統會請使用者確認，不用先問），回報輸出裡 distribute 有沒有 confirm；要求「用 ROS topic 回」時用 `ROS2_topic_pub` 發 `/<機器人>/handshake_states`（`fih_rmf_msgs/msg/HandshakeState`，`is_authored: yes`）。`fin` 是補發完成訊號（task_exec_fin），不是回 yes。

## 複合技能
（還沒有：領域 session 直接用下面的工具）

## 工具
- [workpackage_send](../tools/workpackage_send.md)
- [workpackage_status](../tools/workpackage_status.md)
- [workpackage_cancel](../tools/workpackage_cancel.md)
- [overpending_cancel](../tools/overpending_cancel.md)
- [semantic_map](../tools/semantic_map.md)
- [rmf_handshake](../tools/rmf_handshake.md)
- [docker_containers](../tools/docker_containers.md)
- [docker_open](../tools/docker_open.md)
- [ROS2_workspace_env](../tools/ROS2_workspace_env.md)
- [ROS2_topic_pub](../tools/ROS2_topic_pub.md)
