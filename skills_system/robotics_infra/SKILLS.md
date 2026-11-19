# robotics_infra：容器與 ROS 2

正在跑的系統：容器的狀態、log、設定與啟停，容器裡的 ROS 2 topic、node、參數（現在的值、發布訊息）。
不包含：工作目錄裡的檔案（程式碼、設定檔、文字的 log 檔：repo_analysis）、錄製的數據（MCAP：data_analysis）、調度系統的工作包與機器人的授權交握（rmf_dispatch）。

## 做法
- 容器技能直接用 CURRENT_TARGET_CONTAINER，**不要再問使用者要看哪個容器**；未設定時先 docker_containers 查、docker_open 選定；換容器用 docker_open。
- **常見情況的做法**（照順序做，查到原因就回報；使用者沒要求的處理不要做）：
  - 容器停了：使用者要你啟動／重啟（「重開一次」「把它開起來」）時，直接 `docker_ctl restart <容器>`（系統會請使用者確認，不用先問、不用先看 log），回報會附這次啟動的 log，起不來的原因照它寫；只問停掉的原因時，`docker_ctl status` 看結束碼 → `docker_ctl logs` 看最後的錯誤（含 stderr；很長的會整理成唯一訊號），回報原因，不要自己啟動。
  - ROS 2 的 topic／node 列表是空的或只有系統的 topic：`ROS2_domain_id` 看 shell 跟正在跑的節點各在哪個 domain；自訂訊息讀不到、Workspace 路徑不知道：`ROS2_workspace_env --discover`（不要先問使用者）。

## 複合技能
（還沒有：交給這個領域的問題，在子工作階段裡用下面的工具一步一步做）

## 工具
- [docker_containers](../tools/docker_containers.md)
- [docker_images](../tools/docker_images.md)
- [docker_est](../tools/docker_est.md)
- [docker_open](../tools/docker_open.md)
- [docker_runcmd](../tools/docker_runcmd.md)
- [docker_ctl](../tools/docker_ctl.md)
- [ROS2_workspace_env](../tools/ROS2_workspace_env.md)
- [ROS2_domain_id](../tools/ROS2_domain_id.md)
- [ROS2_topic_list](../tools/ROS2_topic_list.md)
- [ROS2_topic_echo](../tools/ROS2_topic_echo.md)
- [ROS2_node_list](../tools/ROS2_node_list.md)
- [ROS2_node_info](../tools/ROS2_node_info.md)
- [ROS2_param](../tools/ROS2_param.md)
- [ROS2_topic_pub](../tools/ROS2_topic_pub.md)
