
---
type: Tool
title: 載入 ROS 2 Workspace 環境
description: 確認 Docker 容器內的 ROS 2 Workspace，載入 install/setup.bash，並可在同一個 Shell 執行命令。
version: 1.0.0
dependencies: ["docker"]
---

# 用途

確認目前目標容器中的 ROS 2 Workspace 路徑，載入該 Workspace 的
`install/setup.bash`，並確保後續命令在同一個 Bash Shell 執行。

成功確認後，Agent 會記錄：

- `CURRENT_ROS2_WORKSPACE`：Workspace 在容器內的絕對路徑。
- `ROS2_WORKSPACE_CONTAINER`：這個 Workspace 所屬的容器。

Workspace 狀態與容器綁定。切換目標容器後，不可直接沿用其他容器的路徑。

# 前置條件

1. 需要先有明確的 `CURRENT_TARGET_CONTAINER`；尚未設定時，先使用
   `docker_containers` 查詢，再以 `docker_open` 選定容器。
2. 如果沒有已確認的 Workspace 路徑，向使用者詢問容器內的 Workspace
   根目錄。不可自行猜測路徑。
3. Workspace 必須包含 `install/setup.bash`。
4. 已記錄的路徑仍須在實際執行時重新驗證，不能只憑狀態宣稱環境有效。

# 語法

`EXECUTE: scripts/ROS2_workspace_env_cmd.py --workspace <絕對路徑>`

可選參數：

- `--container <容器名稱>`：指定完整的 Docker 容器名稱；省略時使用
  目前的目標容器。
- `--timeout <秒數>`：預設 30 秒，範圍 1～570 秒。
- `--command "<命令>"`：載入 Workspace 後，在同一個 Shell 執行命令。

# 範例

載入已確認的 Workspace：

`EXECUTE: scripts/ROS2_workspace_env_cmd.py --workspace /workspace/my_robot`

載入環境並檢查 ROS 2 套件：

`EXECUTE: scripts/ROS2_workspace_env_cmd.py --workspace /workspace/my_robot --command "ros2 pkg list"`

指定容器：

`EXECUTE: scripts/ROS2_workspace_env_cmd.py --container ros2_humble --workspace /workspace/my_robot`

# 回傳

成功時回傳 `[PASS]`、Workspace 路徑與 ROS_DISTRO 資訊，並在末尾附加
系統狀態標記 `[ROS2_WORKSPACE]`。

只有命令成功完成才會輸出 Workspace 狀態標記。

失敗時回傳 `[ERROR]` 與原因，不得將失敗路徑寫入 Agent 狀態。

# 使用規則

- 後續 ROS 2 分析任務應優先讀取 `CURRENT_ROS2_WORKSPACE`。
- 若該狀態尚未設定，或不屬於目前的 `CURRENT_TARGET_CONTAINER`，
  必須先確認 Workspace 路徑。
- 每支獨立執行的 ROS 2 分析命令都要在同一次 Shell 中載入環境；
  不可假設先前工具執行的 `source` 會保留。
- 不修改或自動建立 Workspace；此技能只負責載入環境及執行指定命令。
