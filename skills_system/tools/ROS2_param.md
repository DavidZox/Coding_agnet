---
type: Tool
title: ROS 2 參數
description: 查詢 ROS 2 node 的參數（list／get，看執行中的實際值）；set 修改執行中的值（會先請使用者確認）。
version: 1.1.1
dependencies: ["docker", "ros2"]
---

# 用途
問「某個 node 的參數現在是多少」時用——設定檔（yaml）寫的是啟動時的值，執行中的值可能被 launch 參數或之後的 set 改過，以這裡查到的為準。
set 之後會再讀一次、回報實際的值；只影響執行中的 node，重啟後回到設定檔的值。逾時 40 秒。

# 語法
`EXECUTE: scripts/ROS2_param_cmd.py [容器名稱] list <node>`　`… get <node> <參數>`　`… set <node> <參數> <值>`
* 容器名稱省略＝目前的目標容器；node 名稱含命名空間（少了開頭的 / 會自動補）。
* set 的值照參數原本的型別寫：小數 `10.0`（不是 `10`）、整數 `10`、`true`／`false`、字串。

# 範例
`EXECUTE: scripts/ROS2_param_cmd.py ros_box get /camera_node exposure`　`EXECUTE: scripts/ROS2_param_cmd.py list /camera_node`

# 回傳
get：`[PASS] /node 的 參數（執行中的值；容器…，ROS_DOMAIN_ID N）：10.0（Double）`。list：`[PASS] /node 有 N 個參數` + 每行一個（超過 20 個依前綴分節）。
set：`[PASS] 已設定 … = 值；再讀一次的值：…`。

# 異常
* 找不到 node／沒有這個參數 → `[ERROR]` 附相近的名稱與現有的 node／參數 → 用正確的名稱重試，不要猜。
* set 失敗 → `[ERROR]` 附原因、目前的值與下一步：型別不對（照型別改寫值）、唯讀參數（只能改設定檔後重啟，先問使用者）、沒有宣告（名稱錯）。
* 逾時（node 沒回應或 DDS 探索不到）→ `ROS2_node_list`／`ROS2_domain_id` 確認。
