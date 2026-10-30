---
type: Workflow
title: 檢查 ROS2 與 MQTT 通訊
description: 切換至指定容器發送 ROS 2 訊息，並檢查 MQTT Broker 日誌確認是否有 PUBLISH 紀錄。
version: 0.1.0
dependencies: ["docker_open", "ROS2_topic_pub", "docker_ctl"]
changes_state: false
source: make_skill 2026-10-31 06:36（依對話與工具回傳整理；步驟呼叫既有技能，由 workflow_run 照步驟執行；可直接編輯）
---

# 用途
驗證 ROS 2 Topic 訊息是否能成功透過 MQTT Broker 轉發，用於檢查 ROS 2 與 MQTT 之間的通訊橋接是否正常。

# 使用者的要求（必須遵守）
* 必須先切換至 fms_hub 容器執行發送動作，接著檢查 mqtt-broker 容器的 log。（第 1 步）——使用者說：「請幫我到fms_hub發送ros2 topic pub --once /fms/command_to_send std_msgs/msg/String "{data: 'Hello FMS MQTT'}"後再到mqtt-broker看一下log」
* 檢查 mqtt-broker log 時，必須判斷是否包含 'PUBLISH' 字串，若有則判定為成功。（第 3 步）——使用者說：「只要有看到收到PUBLISH就是成功了」

# 需要的資訊
* `{target_container}`：要執行 ROS 2 發送指令的容器名稱（例：`fms_hub`）
* `{topic_name}`：要發布的 ROS 2 topic 名稱（例：`/fms/command_to_send`）
* `{msg_type}`：ROS 2 訊息型別（例：`std_msgs/msg/String`）
* `{msg_content}`：要發布的 YAML 格式訊息內容（例：`{data: 'Hello FMS MQTT'}`）
* `{broker_container}`：要檢查 log 的 MQTT Broker 容器名稱（例：`mqtt-broker`）

# 步驟
1. 【執行】切換到指定的 ROS 2 容器中。：`EXECUTE: scripts/docker_open_cmd.py {target_container}`
2. 【執行】在容器內發布一次指定的 ROS 2 訊息。：`EXECUTE: scripts/ROS2_topic_pub_cmd.py {target_container} {topic_name} {msg_type} '{msg_content}' --times 1`
3. 【執行】檢查 MQTT Broker 容器的日誌，搜尋是否包含 'PUBLISH' 字樣。：`EXECUTE: scripts/docker_ctl_cmd.py logs --tail 10 {broker_container} `
4. 【檢查】看第 3 步：「輸出裡會出現的字」PUBLISH → 告知使用者通訊成功；「其他」→ 告知使用者通訊失敗，未發現 PUBLISH 紀錄
5. 【告知】告知使用者驗證結果（成功或失敗）以及在 log 中看到的具體內容。

# 成功判準
* 第 3 步的輸出包含 'PUBLISH' 字樣。

# 異常與注意事項
* 第 1 步失敗時：停止執行並告知使用者無法連線至目標容器
* 第 2 步失敗時：若發布失敗，告知使用者訊息未送出，無法進行後續檢查
* 第 3 步失敗時：若無法讀取 log，告知使用者檢查 broker 容器狀態
* 如果 topic 沒帶斜線，腳本會自動補上，但建議使用者輸入完整路徑。
* 若 broker 容器未啟動，第 3 步會失敗。
* 會改變系統狀態的步驟（docker_open、ROS2_topic_pub、docker_ctl）：開始執行時系統會請使用者確認一次。
* 各步驟的參數規則與其他異常見底層技能的規格：docker_open、ROS2_topic_pub、docker_ctl。
