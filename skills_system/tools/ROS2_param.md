---
type: Tool
title: ROS 2 參數
description: 查詢 ROS 2 node 的參數（list／get，看執行中的實際值）；set 修改執行中的值（會先請使用者確認）。
version: 1.0.0
dependencies: ["docker", "ROS 2（容器內）"]
---

# 用途
問「某個 node 的參數現在是多少」時用這個——設定檔（yaml）寫的是啟動時的值，執行中的值可能被 launch 參數或之後的 set 改過，以這裡查到的為準。

# 語法
`EXECUTE: scripts/ROS2_param_cmd.py [容器名稱] list <node>`　`… get <node> <參數>`　`… set <node> <參數> <值>`
* 容器名稱省略＝目前的目標容器；node 名稱含命名空間（`/resource_allocator`，少了開頭的 / 會自動補）。

# 範例
`EXECUTE: scripts/ROS2_param_cmd.py rmf_sim get /resource_allocator authorize_timeout_sec`　`EXECUTE: scripts/ROS2_param_cmd.py list /resource_allocator`

# 回傳
`[PASS] /node 的 參數（執行中的值）：Double value is: 10.0`；list 列出參數名稱；set 回報設定成功。

# 異常
找不到 node（名稱或 ROS_DOMAIN_ID 不對）、沒有這個參數：`[ERROR]` 並建議先 list 或用 ROS2_node_list 確認。
