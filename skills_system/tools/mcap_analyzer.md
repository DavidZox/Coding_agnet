
---
type: Tool
title: ROS 2 MCAP Metadata 與時序數據分析工具
description: 在目標 ROS 2 容器內列出 Topic、取得欄位清單，並反序列化指定欄位。
version: 2.0.0
dependencies: ["docker", "mcap", "rclpy", "rosidl_runtime_py", "pyyaml"]
---

# 用途

在目標容器內分析 MCAP，利用容器已安裝的 ROS 2 message packages 反序列化訊息。支援列出 Topic、列出某 Topic 的欄位，以及擷取指定欄位的時序值。

所有輸入路徑都是**容器內路徑**。如果輸入是目錄，目錄底下必須剛好有一個 `.mcap` 檔案；若有多個，請直接指定檔案路徑。

# 語法

`EXECUTE: scripts/mcap_analyzer_cmd.py [--container NAME] [--timeout SEC] --input FILE_OR_DIR [--list-topics] [--topic TOPIC] [--list-fields] [--field FIELD_PATH] [--limit N] [--offset N] [--json]`

- `--input`：MCAP 檔案或包含唯一 MCAP 檔案的目錄。
- `--list-topics`：列出 Topic、訊息數與可辨識的 schema。
- `--topic`：要分析的 Topic。
- `--list-fields`：列出指定 Topic 的訊息欄位。
- `--field`：擷取欄位，可使用巢狀路徑，例如 `pose.position.x`。
- `--limit`：最多回傳幾筆，預設 20。
- `--offset`：略過前 N 筆符合 Topic 的訊息，預設 0。
- `--json`：以 JSON 輸出。
- `--container`：省略時使用目前目標容器。
- `--timeout`：預設 120 秒，上限 570 秒。

# 範例

列出 Topic：

`EXECUTE: scripts/mcap_analyzer_cmd.py --input /data/exp_001/slice_001 --list-topics`

列出 `/odom` 欄位：

`EXECUTE: scripts/mcap_analyzer_cmd.py --input /data/exp_001/slice_001 --topic /odom --list-fields`

擷取巢狀欄位：

`EXECUTE: scripts/mcap_analyzer_cmd.py --input /data/exp_001/slice_001/data.mcap --topic /odom --field pose.pose.position.x --limit 30 --json`

從第 100 筆開始擷取：

`EXECUTE: scripts/mcap_analyzer_cmd.py --input /data/exp_001/data.mcap --topic /odom --field twist.twist.linear.x --offset 100 --limit 50`

# 回傳

欄位擷取結果包含 `log_time_ns`、`publish_time_ns`、`sequence` 與 `value`，並統計反序列化或欄位存取失敗的筆數與原因。

# 注意事項

- 必須在已安裝相應 ROS 2 message packages 的容器內執行。
- `log_time_ns` 與 `publish_time_ns` 是 MCAP 的奈秒時間值；不要在未確認前將其當成 Unix 時間或直接與日誌文字時間比較。
- `available_fields` 會優先透過 `get_fields_and_field_types()` 取得，不直接將 `__slots__` 的底線欄位名當成使用者欄位名。
