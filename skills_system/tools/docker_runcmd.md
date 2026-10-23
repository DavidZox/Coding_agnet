---
type: Tool
title: 容器內執行指令
description: 在指定容器（或目前的目標容器）內執行一行 shell 指令；看容器裡的目錄、檔案、程序都用它。
version: 2.0.0
dependencies: ["docker"]
---

# 用途
在容器內以 `bash -c` 執行（沒有 bash 用 sh）；list_dir／view_file 只看本機。唯讀的指令直接執行，其他的先請使用者確認。
* 目錄會保留：從 CURRENT_CONTAINER_DIRECTORY 開始（不在就從容器的預設目錄），指令裡的 `cd` 留到下一次。
* 不讀 ~/.bashrc：用 ros2 要自己加 `source /opt/ros/$ROS_DISTRO/setup.bash && `（ROS 的查詢優先用 ROS2_* 技能）。
* 不會自己結束的（`ros2 topic echo` 沒加 `--once`、`ros2 topic hz`、`tail -f`、`ros2 launch`、`top`）沒包 `timeout N` 就不執行，回替代做法。

# 語法
`EXECUTE: scripts/docker_runcmd_cmd.py [--timeout 秒] [container_name] "<command>"`
* `--timeout`：預設 120，範圍 1～570。`container_name`：省略＝目標容器；要指定時給完整名稱。
* `command`：一對雙引號包住整串（裡面用單引號）；`;`、`&&`、`&`（背景）都可以。

# 範例
`EXECUTE: scripts/docker_runcmd_cmd.py "ls -la /opt/ros"`　`EXECUTE: scripts/docker_runcmd_cmd.py --timeout 540 ros2_humble "cd /ws && colcon build"`
`EXECUTE: scripts/docker_runcmd_cmd.py "source /opt/ros/$ROS_DISTRO/setup.bash && timeout -s INT 10 ros2 topic hz /odom"`

# 回傳
`[PASS] 容器 '<名稱>' 內 `<command>` 執行完成（exit code 0；目錄 /a → /b）：` + 標準輸出；有 stderr 時 `## stderr`（最後 15 行）；太長只留頭尾並註明。
指令自己的 `timeout N` 時間到（exit code 124）也是 `[PASS]`。最後幾行是狀態標記（`[TARGET_CONTAINER]`、`[CONTAINER_CWD]`＋目錄）。

# 異常
* `[ERROR] … 失敗（exit code N）：原因` → 依 stderr 修正，不要原樣重送；grep 沒找到也回非 0（訊息會說）。
* 第一個參數不是容器也不像指令 → 附相近的容器名稱；整串是指令就用引號包住。
* 逾時（--timeout）→ 確定需要更久才加大；容器不存在／沒在跑／docker 不可用 → 訊息會說下一步。
