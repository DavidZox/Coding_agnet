
---
type: Tool
title: ROS 2 MCAP 時間切片與 Metadata 萃取工具
description: 在目標 ROS 2 容器內依 MCAP log_time 切片，並產生 Topic 統計與欄位 Metadata。
version: 2.0.0
dependencies: ["docker", "mcap", "pyyaml", "rclpy", "rosidl_runtime_py"]
---

# 用途

在目標容器內讀取來源 MCAP，依指定的 MCAP `log_time` 奈秒時間戳及前後秒數切出新的 MCAP，並輸出 `metadata.yaml` 與 `metadata.json`。

欄位清單透過容器內的 ROS 2 訊息型別嘗試取得。若自訂訊息型別未安裝或無法反序列化，切片本身仍可能成功，但相關 `available_keys` 可能為空。

# 語法

`EXECUTE: scripts/mcap_slicer_cmd.py [--container NAME] [--timeout SEC] --input FILE.mcap --output-dir NEW_DIR --timestamp-ns NS [--event-id ID] [--before SEC] [--after SEC]`

- `--input`：容器內現有的 `.mcap` 檔案；必須明確指定。
- `--output-dir`：新輸出目錄；若已存在則拒絕覆寫。
- `--timestamp-ns`：已確認時間基準的 MCAP `log_time` 奈秒值。
- `--event-id`：對應 `rosout_parser` 的來源行號，僅供追溯。
- `--before`、`--after`：切片中心點前後的秒數，預設各 5 秒。
- `--timeout`：預設 180 秒，上限 570 秒。

# 範例

`EXECUTE: scripts/mcap_slicer_cmd.py --input /data/exp_001/bag_001.mcap --output-dir /data/exp_001/slice_error_001 --timestamp-ns 1791873116289000000 --event-id 42 --before 5 --after 10`

# 輸出

- 切片後的 MCAP 檔案。
- `metadata.yaml`：切片範圍、來源事件 ID、訊息數與 Topic 統計。
- `metadata.json`：同內容的 JSON 版本，方便工具串接。

# 重要限制

- 不會自動把 `rosout` 的文字時間轉換成 MCAP `log_time`；請先確認兩者使用相同時間基準及單位。
- 輸入時間範圍內沒有訊息時，工具回報錯誤，不產生成功結果。
- 不會覆寫既有輸出目錄。
