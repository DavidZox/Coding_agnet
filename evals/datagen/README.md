# 隨機情境錄製產生器（`evals/datagen/`）

大量數據的穩定度測試用：隨機組合這台機器人在開發的六個套件的情境，產生跟 `ros2 bag record -a` 同格式的 MCAP，
**評分標準由注入的事件自動產生**（不用人工標註），直接套用數據分析的回歸評分（`evals/analysis_regression.py`）。

## 怎麼用

```bash
cd ~/Coding_agnet
docker start cah_analysis_test
PY=~/aiagent_venv_env/.venv/bin/python
python3 evals/datagen/generate.py --set s2 --seed 2 --n 60                     # → test_data/recordings/gen/s2/（60 份＋cases.json）
python3 evals/datagen/generate.py --set s3 --seed 3 --n 20 --require bridge    # 每一份都有 bridge（只測某個子系統時）
python3 evals/datagen/check_facts.py test_data/recordings/gen/s2/cases.json    # 程式那一層：分析程式量到的事實 vs 評分標準（不呼叫模型）
$PY evals/analysis_regression.py --run --runs 2 --model gemma4:26b --container cah_analysis_test \
    --cases-file test_data/recordings/gen/s2/cases.json --data-root /workspace/experiment_logs/gen/s2 \
    --out evals/results/analysis_gen_s2                                         # 有模型的回歸
$PY test_data/tools/stability.py evals/results/analysis_gen_s2/runs.json      # 產物穩定性
docker stop cah_analysis_test
```

- 同一個 seed、同一版程式每次產生一樣的數據（`--only 3,7` 只重產這幾份）。
- 評分標準的定義改了、數據沒變時，不用重寫 bag：`python3 evals/datagen/refresh_truth.py <cases.json>` 在主機上重跑模擬、只重算評分標準
  （重跑出來的情境跟原本不同的那一份不動——代表產生器的程式已經不是當時那一版）。
- 先跑 `check_facts.py`：快、結果固定；程式的事實對了，再跑有模型的回歸。它用的是分析程式本身（`mcap_analyzer --facts`、
  `rosout_parser`、`analysis_job.build_facts`），比對時間線該有的事件與 Topic 的類別。
- 一份 30～178 秒；60 份約 0.8 GB（`test_data/` 不進 git）。

## 評分標準怎麼來的

模擬時每注入一個事件，就登記「它在數據裡看得到的樣子」（`sim_core.Sim.expect_*`），錄製寫完之後依**分析程式的定義**換成時間與關鍵字
（`Sim._resolve`）——照定義看不到的不列，不然評分會冤枉分析程式：

| 事件 | 看得到的時間 | 關鍵字 |
|---|---|---|
| 狀態改變（`expect_value`） | 改變之後的第一則訊息（固定頻率的 Topic 不是改變的那一刻）；這個 Topic 的第一則而且在錄製開始 5 秒之後＝「第一則訊息」 | Topic、`→ 新的值` |
| 停止發布（`expect_stop`） | 最後一則（處理延遲讓最後一則晚於停止的時間也照實算）；離錄製結束太近的不列 | Topic、停止發布 |
| 開始發布（`expect_start`） | 第一則；錄製開始 5 秒內、之前有訊息的（那是恢復）不列 | Topic、開始發布 |
| 訊息中斷（`expect_gap`） | 那段時間附近最長的間隔的開頭；不到週期 3 倍、0.5 秒的不列 | Topic、訊息中斷 |
| Log（`expect_log`） | 那一則的時間；出現超過 3 次的只列第一次與最後一次（分析程式的時間線也只列這兩次） | 層級、代碼 |
| 類別（`expect_tags`） | — | 這個 Topic 該有／不該有的類別（例如狀態改變時才發布的 Topic 不該有「訊息中斷」）；開始發布的類別只在那次開始照定義看得到時才期望（`expect_start(tag=True)`） |
| 背景（`expect_background`） | — | 沒有注入事件也會有事件的 Topic（有底盤時 EKF 診斷的 Events in window 是整數計數，每秒在 299／300 之間跳，分析程式照整數狀態量）：穩定錄製的「沒有事件」不算它（`no_event.background`） |

同一個 Topic 反覆切換時，分析程式的時間線只列前 5 次與最後 2 次：模擬登記「分析程式會算成變化事件的每一個時間」（`change_times`），
評分標準照同一個規則取捨。錄製工具的行為也照真的：rosbag2_recorder 自己的 Log；發布者在錄製中途才出現的 Topic（開機、
延遲建立的 publisher、`ros2 topic pub`），錄製工具要等發現了才訂閱，最前面的一兩則錄不到（`Stream.appears`）。

## 模擬了什麼（照六個套件的源碼、文件與 14 份實錄整理的目錄）

| 檔案 | 套件 | Topic 與 Log | 情境 |
|---|---|---|---|
| `sim_diag.py` | diagnostics_package | aggregator 10 Hz、MON 每收到一則 /diagnostics_agg 發一則 /system/safety_command、GATE 20 Hz 的 /cmd_vel 與狀態改變時的 /system/safety_gate_status、BBX、LCM；44 個診斷項目；Log 的格式、file、function、line 照源碼 | 指令、WARN／ERROR／閂鎖的故障、復位（先被拒絕再成功）、aggregator 凍結／結束、MON 結束、LCM 重啟、三個故障疊在一起、回報的節點停止（項目被移除） |
| `sim_base.py` | amr_base_hw | 底盤控制 62.5 Hz（/cmd_state、/wheel_rpm、/driver_state、/hardware_alarm、/base_state、/wheel_odom）、IMU 100 Hz、兩顆 SICK 15 Hz、/scan_merged、/scan、/rf2o_odom、EKF 的 /odom、/tf、/joint_states | 遙控、驅動器警報、USB 拔掉、馬達斷電、LiDAR 斷線（/rosout 沒有 Log）、IMU 拔掉（FATAL）、checksum 錯誤、推車模式、碰撞 |
| `sim_nav.py` | amr_base_sw | task_agent → GlobalPlanner → RouteExecutor → LocalNav → VelocityMux 的狀態 Topic（很多是字串或 JSON 字串）、Diagnostics 監看 | 任務完成、被擋放棄、暫時被擋、現場停止、定位跳動；監看的 Topic 斷訊或一直沒收到 |
| `sim_rmf.py` | fih_rmf_system | 每台機器人 10 Hz 的 robot_state（心跳）、registry 1 Hz 的 fleet_states 與每秒一張狀態表（佔 /rosout 六成）、派工的 authorize／confirm／handshake、speed_limit 20 Hz | 派工、心跳斷掉（離線、恢復）、授權逾時 |
| `sim_vslam.py` | VSLAM_package | 雙目影像（縮小成 32×18）、/run_slam 的 pose、keyframes、tracking_state（只在改變時發） | 追蹤丟失、相機中斷、重新初始化 |
| `sim_bridge.py` | fih_amr_bridge | 本地節點 tb1.bridge_local_node 的 Log（啟動、每 5 秒稽核的 WARN 與「已恢復」、停止）；Isaac Sim 的設定時 /odom、/scan、/scan_b、/imu、/joint_states_in、/clock、/isaac/initialpose 經 bridge 進本地 | 中途啟動（可以帶 ROBOT_NS 跟 .env 不同的 WARN）、同一台機器人跑了兩個 bridge、停止；Isaac Sim 中途才開／中途關掉（導航的 Diagnostics 等待初始化或斷訊） |

`sim_scenarios.py` 每一份挑 1～3 個子系統、每個子系統 0～2 個事件（時間不重疊、不靠近頭尾），一成是沒有事件的穩定錄製、一成多是
錄製中途才啟動；子系統之間照真的接法連動：導航的速度指令 → /cmd_vel_raw → GATE → /cmd_vel → 底盤；底盤的 LiDAR 斷線 → /scan 停 →
導航的 Diagnostics 監看到斷訊；沒有底盤時 bridge 可能是 Isaac Sim 的設定（模擬器要先開、導航才跑任務）。
問題一半用情境相關的（「為什麼安全閘一直鎖著？」），一半用一般的（「這 N 秒系統發生了什麼？」）。

## 檔案

| 檔案 | 在哪裡執行 | 內容 |
|---|---|---|
| `generate.py` | 主機 | 把模擬程式（連同分析程式的 `_ros2_data_common.py`：中斷、開始／停止發布的門檻照它）打包送進容器執行 |
| `sim_main.py` | 容器 | 寫 MCAP（`rosbag2_py.SequentialWriter`，storage mcap）、每份的 `truth.json`、整組的 `cases.json`；`fill()` 把 dict 轉成 ROS 訊息（byte 欄位、浮點欄位給整數時轉換） |
| `sim_core.py` | 兩邊 | 模擬核心：Signal（分段常數的值）、Alive（有在發布的時段）、Stream（固定頻率加抖動／明確的發布時間）、Sim（Log、評分標準、錄製工具）、Motion（速度積分成位置） |
| `sim_diag.py`、`sim_base.py`、`sim_nav.py`、`sim_rmf.py`、`sim_vslam.py`、`sim_bridge.py` | 兩邊 | 各套件的模擬 |
| `sim_scenarios.py` | 兩邊 | 隨機組合（`compose(seed, idx)`） |
| `check_facts.py` | 主機 | 程式那一層的驗證：時間線、類別、穩定錄製沒有事件（背景除外） |
| `refresh_truth.py` | 主機 | 只重算評分標準（數據不變） |

## 容器（`cah_analysis_test`）

ROS 2 Jazzy（`amr_base:latest`），`test_data/recordings` 掛載成 `/workspace/experiment_logs`。寫 MCAP 需要訊息型別，`/workspace/ws/src` 裡建了：

- `diagnostics_package`（原本就有，見 `test_data/README.md`）；
- `fih_rmf_msgs`（從 fih_rmf_system 複製）；
- `base_motor_controller`（只有介面：複製原本的 `msg/`、`srv/`，`package.xml` 與 `CMakeLists.txt` 只留 rosidl——寫錄製只需要訊息型別，
  不需要節點的程式）。

`colcon build`（容器裡、`/workspace/ws`）之後 `source /workspace/ws/install/setup.bash`；`generate.py --workspace` 可以換位置。
其他型別（nav_msgs、sensor_msgs、tf2_msgs、nav2_msgs、rosgraph_msgs…）是 Jazzy 本身就有的。

## 做過的組

| 組 | seed | 份數 | 說明 |
|---|---|---|---|
| `gen/s1` | 1 | 60 | 第一組（2026-10-22，加 bridge 之前：五個子系統；現在的程式重產不出同一組）。`check_facts.py`：60/60 份全對、時間線 365/365、類別（含沒有事件）221/221（穩定而且有底盤的 5 份後來補上背景） |
| `gen/s2` | 2 | 60 | 加了 fih_amr_bridge（含 Isaac Sim 的設定）之後的一般組合。`check_facts.py`：60/60 份全對、時間線 369/369、類別（含沒有事件）221/221 |
| `gen/s3` | 3 | 20 | `--require bridge`：每一份都有 bridge（中途啟動、.env 的 WARN、重複的 bridge、停止、Isaac Sim 中途開或關；4 份只有 Log）。`check_facts.py`：20/20、78/78、59/59 |

有模型的回歸（2026-10-22 第十一輪最終版，gemma4:26b，`evals/results/analysis_r11f_gen_s*/`）：s1 ×2、s2 ×1、s3 ×2 的時間線、類別、用詞、
時間有根據、重點涵蓋、沒有事件全部通過（s1：98/98、114/114、120/120、120/120、96/96、20/20）；程式產物與 Topic 的事件每份每次相同；一次約 8～13 秒。
各版本的比較與還在的問題見 `doc/設計筆記與已知限制.md` 2.18〈六〉。

加 bridge 改變了子系統的抽法：同一個 seed 用現在的程式產生的數據跟 s1 不同（s1 的數據與 cases.json 仍是一致的一組）。

## 限制

- **一個 domain**：真的系統裡 RMF 的 registry／distribute 在對外 domain、機器人的節點在本地 domain，錄在哪一邊看得到的不同；
  模擬把它們放在同一份錄製（bridge 的情境照本地 domain 的樣子）。
- **內容是簡化的**：感測器的數值是合成的（雜訊、碰撞的尖峰），影像是全黑的小圖；分析程式只量長度與元素平均，不影響事實。
- **JSON 字串的 Topic**（/robot_state、/amr_diagnostics…）分析程式當文字，只量訊息流；模擬也只登記它們的發布時間。
- 評分標準只列「照分析程式的定義看得到」的事件；分析程式的定義改了（例如中斷的門檻），要重產評分標準（`generate.py` 同一個 seed）。
