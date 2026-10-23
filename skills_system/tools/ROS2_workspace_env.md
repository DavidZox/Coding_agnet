---
type: Tool
title: 確認並載入 ROS 2 Workspace
description: 找出（--discover）或確認容器裡的 ROS 2 Workspace 並記錄（之後 ROS 2 技能自動載入）；也可在載入後的同一個 shell 執行一個指令。
version: 2.0.0
dependencies: ["docker", "ros2"]
---

# 用途
確認成功後系統記錄 CURRENT_ROS2_WORKSPACE（綁這個容器），之後 ROS2_*、數據技能自動載入它（自訂訊息型別才讀得到）。
不知道路徑先 `--discover`，從結果挑（有 src、套件多的）；挑不出來才問使用者。不會建置或修改 Workspace。

# 語法
`EXECUTE: scripts/ROS2_workspace_env_cmd.py --workspace <路徑> [--command "指令"] [--container 名稱] [--timeout 秒]`
`EXECUTE: scripts/ROS2_workspace_env_cmd.py --discover [--container 名稱]`
* `--workspace`：容器內絕對路徑，根目錄或 install 都可以（`/ws`、`/ws/install`）；都沒給＝`--discover`（/ 底下 5 層，最多 30 個）。
* `--command`：載入後在同一個 shell 執行（不是唯讀的會先請使用者確認）；沒給 `--workspace` 時用已記錄的。`--timeout` 預設 30，上限 570。

# 範例
`EXECUTE: scripts/ROS2_workspace_env_cmd.py --discover`
`EXECUTE: scripts/ROS2_workspace_env_cmd.py --workspace /workspaces/amr_base --command "ros2 interface show fih_rmf_msgs/msg/HandshakeState"`

# 回傳
`[PASS] 已確認容器 '…' 的 ROS 2 Workspace：<路徑>（ROS_DISTRO、套件、有沒有 src；ROS_DOMAIN_ID）`，末行 `[ROS2_WORKSPACE] {…}`（狀態標記）。
`--command` 接著是指令的輸出與 `## stderr`；指令失敗是 `[ERROR]`，但 Workspace 仍會記錄。`--discover`：`## Workspace（N 項）`。

# 異常
* 目錄不存在、沒有 install/setup.bash → `[ERROR]` 附目錄內容 → `--discover`；都沒有再問使用者。
* 參數錯 → `[ERROR]`＋用法。不會自己結束的 `--command`（`ros2 topic echo` 沒加 `--once`）不執行。指令失敗依 stderr 修正。
