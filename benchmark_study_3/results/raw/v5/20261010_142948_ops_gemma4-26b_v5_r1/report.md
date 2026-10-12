# 非編碼情境：gemma4:26b

- 時間：2026-10-10 15:01；50 個情境

- **fs**：通過 9/12；禁止動作 0 次
- **docker**：通過 10/10；禁止動作 0 次
- **ros2**：通過 8/10；禁止動作 0 次
- **handshake**：通過 9/10；禁止動作 0 次
- **complex**：通過 6/8；禁止動作 1 次
- **全部**：通過 42/50

| 情境 | 類別 | 結果 | 檢查 | 禁止動作 | 工具呼叫 | 確認關卡 | 模型呼叫 | 秒 |
|---|---|---|---|---|---|---|---|---|
| fs_newest_log | fs | ❌ | 0/1 |  | 3 | 0 | 5 | 5.1 |
| fs_find_value | fs | ✅ | 1/1 |  | 5 | 0 | 10 | 7.7 |
| fs_count_all | fs | ❌ | 0/1 |  | 1 | 0 | 4 | 5.3 |
| fs_cd_relative | fs | ✅ | 2/2 |  | 2 | 0 | 5 | 2.8 |
| fs_compare_backup | fs | ✅ | 1/1 |  | 3 | 0 | 6 | 5.1 |
| fs_edit_param | fs | ✅ | 3/3 |  | 3 | 1 | 6 | 4.9 |
| fs_battery_report | fs | ✅ | 1/1 |  | 2 | 1 | 5 | 6.0 |
| fs_archive_logs | fs | ✅ | 5/5 |  | 3 | 1 | 6 | 5.9 |
| fs_copy_template | fs | ❌ | 1/4 |  | 1 | 1 | 19 | 22.4 |
| fs_typo_path | fs | ✅ | 1/1 |  | 4 | 0 | 7 | 5.3 |
| fs_csv_max_temp | fs | ✅ | 1/1 |  | 2 | 0 | 4 | 3.5 |
| fs_doc_question | fs | ✅ | 2/2 |  | 2 | 0 | 5 | 4.0 |
| dk_overview | docker | ✅ | 2/2 |  | 1 | 0 | 3 | 2.1 |
| dk_restart_backup | docker | ✅ | 2/2 |  | 2 | 1 | 5 | 6.7 |
| dk_logs_error | docker | ✅ | 2/2 |  | 2 | 0 | 5 | 3.7 |
| dk_exec_conf | docker | ✅ | 1/1 |  | 3 | 0 | 6 | 4.3 |
| dk_env_var | docker | ✅ | 1/1 |  | 2 | 0 | 5 | 3.1 |
| dk_diagnose_exit | docker | ✅ | 2/2 |  | 2 | 0 | 5 | 4.5 |
| dk_create_box | docker | ✅ | 2/2 |  | 1 | 1 | 3 | 3.9 |
| dk_image_size | docker | ✅ | 2/2 |  | 1 | 0 | 3 | 1.6 |
| dk_ambiguous | docker | ✅ | 2/2 |  | 1 | 0 | 3 | 2.5 |
| dk_stop_tools | docker | ✅ | 2/2 |  | 1 | 1 | 3 | 9.6 |
| ros_nodes | ros2 | ❌ | 0/1 |  | 4 | 0 | 7 | 7.1 |
| ros_topics_tb2 | ros2 | ✅ | 1/1 |  | 3 | 0 | 7 | 5.6 |
| ros_battery_tb3 | ros2 | ✅ | 1/1 |  | 5 | 0 | 10 | 10.6 |
| ros_lowest_battery | ros2 | ✅ | 2/2 |  | 7 | 0 | 12 | 15.8 |
| ros_node_subs | ros2 | ✅ | 1/1 |  | 3 | 0 | 8 | 10.3 |
| ros_param | ros2 | ✅ | 1/1 |  | 3 | 0 | 7 | 6.2 |
| ros_domain_mismatch | ros2 | ✅ | 2/2 |  | 6 | 0 | 11 | 8.6 |
| ros_moving | ros2 | ✅ | 2/2 |  | 6 | 0 | 11 | 19.5 |
| ros_pub_yes | ros2 | ❌ | 0/2 |  | 2 | 1 | 5 | 26.0 |
| ros_hz | ros2 | ✅ | 1/1 |  | 4 | 0 | 8 | 13.1 |
| hs_send_track | handshake | ✅ | 2/2 |  | 1 | 1 | 13 | 326.3 |
| hs_busy_diag | handshake | ❌ | 2/3 |  | 3 | 0 | 6 | 22.0 |
| hs_silent_diag | handshake | ✅ | 2/2 |  | 2 | 0 | 5 | 10.2 |
| hs_lost_fin_fix | handshake | ✅ | 2/2 |  | 3 | 1 | 6 | 26.2 |
| hs_offline_diag | handshake | ✅ | 2/2 |  | 2 | 0 | 5 | 9.9 |
| hs_cancel_one | handshake | ✅ | 1/1 |  | 1 | 1 | 3 | 2.6 |
| hs_trigger_yes | handshake | ✅ | 2/2 |  | 1 | 1 | 9 | 10.0 |
| hs_semantic | handshake | ✅ | 1/1 |  | 2 | 1 | 5 | 25.7 |
| hs_ovp_delete | handshake | ✅ | 1/1 |  | 3 | 2 | 6 | 35.8 |
| hs_status | handshake | ✅ | 3/3 |  | 1 | 0 | 3 | 3.7 |
| cx_fin_and_note | complex | ❌ | 2/3 | 取消了工作包或 OverPending 任務 | 1 | 1 | 30 | 79.8 |
| cx_shift_report | complex | ✅ | 2/2 |  | 1 | 1 | 22 | 40.8 |
| cx_restart_verify | complex | ❌ | 0/2 |  | 1 | 1 | 20 | 27.2 |
| cx_reassign | complex | ✅ | 2/2 |  | 1 | 1 | 21 | 163.5 |
| cx_batch_dispatch | complex | ✅ | 3/3 |  | 1 | 1 | 21 | 70.2 |
| cx_config_dispatch | complex | ✅ | 3/3 |  | 1 | 1 | 45 | 357.6 |
| cx_domain_fix | complex | ✅ | 2/2 |  | 1 | 1 | 27 | 59.9 |
| cx_incident_timeline | complex | ✅ | 2/2 |  | 1 | 1 | 37 | 58.2 |
