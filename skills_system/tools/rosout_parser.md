
---
type: Tool
title: ROS 2 /rosout 系統日誌解析與事件檢視器
description: 在目標容器內解析 rosout.log，統計層級並保留事件來源行號。
version: 2.0.0
dependencies: ["docker", "python3"]
---

# 用途

在目標 Docker 容器內解析 `rosout.log`。每筆事件以來源檔案的 1-based 行號作為 `event_id`，讓後續分析可以追溯原始日誌位置。

工具會保留日誌中的時間文字，但不會自行推定該時間與 MCAP 的 `log_time` 使用同一個時鐘。

# 語法

`EXECUTE: scripts/rosout_parser_cmd.py [--container NAME] [--timeout SEC] [--level LEVEL]... [--limit N] [--json] INPUT`

- `INPUT`：容器內 `rosout.log` 的完整路徑，或包含該檔案的目錄。
- `--container`：省略時使用目前的目標容器。
- `--timeout`：預設 120 秒，上限 570 秒。
- `--level`：可重複指定 `DEBUG`、`INFO`、`WARN`、`ERROR`、`FATAL`。
- `--limit`：最多輸出事件數，預設 200。
- `--json`：輸出結構化 JSON。

# 範例

`EXECUTE: scripts/rosout_parser_cmd.py /data/exp_001/rosout.log`

只檢視錯誤事件：

`EXECUTE: scripts/rosout_parser_cmd.py --level ERROR --level FATAL --limit 100 /data/exp_001`

輸出 JSON 供後續程式使用：

`EXECUTE: scripts/rosout_parser_cmd.py --json /data/exp_001/rosout.log`

# 回傳欄位

JSON 輸出包含 `source`、`total_parsed_events`、`unparsed_nonempty_lines`、`level_counts` 與 `events`。每個事件保留：

- `event_id`、`source_line`
- `timestamp_text`、`timestamp_basis`
- `level`、`message`、`raw`

# 注意事項

- 若日誌是 YAML 區塊格式，逐行解析不一定能重建完整的 ROS 訊息；此時原始行會保留為 `UNKNOWN` 或列為未解析。
- `event_id` 是來源行號，不是時間戳，也不是 MCAP 訊息索引。
- 若要用事件時間進行 MCAP 切片，必須先驗證日誌時間與 MCAP 時間的基準、時區與單位。
