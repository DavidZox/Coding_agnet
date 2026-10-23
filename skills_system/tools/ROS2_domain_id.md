---
type: Tool
title: ROS 2 Domain ID 查詢與設定
description: 查看容器裡新開的 shell 與正在跑的 ROS 節點各在哪個 ROS_DOMAIN_ID（ROS2_* 看不到節點時用）；set 寫入 ~/.bashrc（會先請使用者確認）。
version: 2.0.0
dependencies: ["docker", "ros2"]
---

# 用途
ROS2_topic_list／ROS2_node_list 只看到 /rosout、/parameter_events 或沒有 node 時，先用它查：列出新開的 shell（含 ~/.bashrc 與 Workspace）、
容器的環境變數、~/.bashrc 的設定，以及正在跑的 ROS 程序各自的 domain，並算出 ROS2_* 技能實際會用哪一個、兩邊不同時怎麼辦。逾時 20 秒。

# 語法
`EXECUTE: scripts/ROS2_domain_id_cmd.py [container_name] [get]`　`EXECUTE: scripts/ROS2_domain_id_cmd.py [container_name] set <0-232>`
* `container_name` 可省略＝目前的目標容器。舊寫法 `[container_name] <N>` 等於 set。
* set 會改容器的 ~/.bashrc（只影響之後新開的 shell：ROS2_* 技能、終端機；docker_runcmd 的 bash -c 不讀 ~/.bashrc）；**正在跑的節點不會換 domain**，
  要換得重啟節點或容器（先問使用者）。寫入後開新的 shell 驗證，不對就還原。Linux 上建議 0～101。

# 範例
`EXECUTE: scripts/ROS2_domain_id_cmd.py`　`EXECUTE: scripts/ROS2_domain_id_cmd.py rmf_sim set 42`

# 回傳
`[PASS] 容器 '<名稱>' 的 ROS_DOMAIN_ID：新開的 shell＝X；正在跑的 ROS 節點都在 Y（N 個）；ROS2_* 技能會用 Z` + `## shell 的設定`、`## 正在跑的 ROS 程序`（pid、domain、指令）。
不一致時第一行有「注意：…下一步：…」。set：`[PASS] 已把…設成 N：寫入 ~/.bashrc…，新開的 shell 驗證是 N（原本 M）`。

# 異常
* 驗證不對（~/.bashrc 後面或 Workspace 又設了別的值）→ `[ERROR]` 並已還原、狀態沒變 → 照提示找是誰設的，告訴使用者。
* 沒有寫入權限 → `[ERROR]`、沒有改變。數字超出 0～232 → `[ERROR]`。容器沒有 bash／不存在／沒在跑 → 訊息會說下一步。
