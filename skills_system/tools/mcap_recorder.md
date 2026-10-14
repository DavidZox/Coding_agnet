
---
type: Tool
title: ROS 2 MCAP 實驗數據錄製工具
description: 在目前目標 Docker 容器內錄製 ROS 2 Topic，並可另外保存 /rosout 輸出。
version: 2.0.0
dependencies: ["docker", "ros2", "mcap"]
---

# 用途

由主機端腳本選定目標容器，並在容器內執行 `ros2 bag record`。主機不需要安裝 ROS 2 或 `rclpy`。

所有路徑均以**容器內路徑**解讀。若希望主機端讀取錄製資料，請將輸出目錄放在已掛載到主機的共享目錄中。

# 語法

`EXECUTE: scripts/mcap_recorder_cmd.py [--container NAME] [--timeout SEC] (--topics TOPIC [TOPIC ...] | --all) --duration SEC --output-dir PATH [--rosout]`

- `--container`：容器名稱；省略時使用目前的目標容器。
- `--timeout`：Agent 工具的逾時秒數，預設 120，上限 570。
- `--topics`：明確指定一個或多個以 `/` 開頭的 Topic。
- `--all`：錄製可見的所有 Topic，與 `--topics` 互斥。
- `--duration`：有限錄製時間，必須大於 0。
- `--output-dir`：容器內的輸出目錄。若目錄已存在且非空，工具會拒絕覆寫。
- `--rosout`：額外將 `ros2 topic echo /rosout` 的輸出保存至 `rosout.log`。

# 範例

錄製特定 Topic 10 秒：

`EXECUTE: scripts/mcap_recorder_cmd.py --topics /cmd_vel /diagnostics --duration 10 --output-dir /data/exp_001`

錄製所有可見 Topic 30 秒，並保留 rosout：

`EXECUTE: scripts/mcap_recorder_cmd.py --all --duration 30 --output-dir /data/exp_002 --rosout`

指定容器並增加逾時：

`EXECUTE: scripts/mcap_recorder_cmd.py --container ros2_humble --timeout 180 --topics /odom --duration 60 --output-dir /data/exp_003`

# 輸出

- `bag_<UTC時間>/`：`ros2 bag record` 產生的 bag 資料。
- `terminal.log`：錄製程序的終端輸出。
- `recording_metadata.json`：錄製參數、執行時間與 MCAP 檔案清單。
- `rosout.log`：只有使用 `--rosout` 時才會產生。

# 回傳與異常

- 成功：`[PASS]` 與輸出目錄、MCAP 檔案數量。
- 失敗：`[ERROR]` 與錯誤原因。
- 若沒有產生任何 `.mcap`，即使錄製程序已結束也視為失敗。
- 逾時時依工具回報處理；不要在不確認容器內錄製程序狀態的情況下反覆重試。
