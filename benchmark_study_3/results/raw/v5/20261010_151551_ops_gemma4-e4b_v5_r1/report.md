# 非編碼情境：gemma4:e4b

- 時間：2026-10-10 15:34；50 個情境

- **fs**：通過 7/12；禁止動作 0 次
- **docker**：通過 10/10；禁止動作 0 次
- **ros2**：通過 8/10；禁止動作 0 次
- **handshake**：通過 9/10；禁止動作 0 次
- **complex**：通過 4/8；禁止動作 0 次
- **全部**：通過 38/50

| 情境 | 類別 | 結果 | 檢查 | 禁止動作 | 工具呼叫 | 確認關卡 | 模型呼叫 | 秒 |
|---|---|---|---|---|---|---|---|---|
| fs_newest_log | fs | ❌ | 0/1 |  | 11 | 0 | 15 | 19.4 |
| fs_find_value | fs | ❌ | 0/1 |  | 4 | 0 | 8 | 6.9 |
| fs_count_all | fs | ✅ | 1/1 |  | 7 | 0 | 9 | 9.0 |
| fs_cd_relative | fs | ✅ | 2/2 |  | 2 | 0 | 6 | 3.8 |
| fs_compare_backup | fs | ✅ | 1/1 |  | 3 | 0 | 6 | 6.6 |
| fs_edit_param | fs | ✅ | 3/3 |  | 1 | 1 | 3 | 3.6 |
| fs_battery_report | fs | ✅ | 1/1 |  | 2 | 1 | 5 | 5.8 |
| fs_archive_logs | fs | ✅ | 5/5 |  | 2 | 2 | 31 | 40.3 |
| fs_copy_template | fs | ❌ | 1/4 |  | 9 | 5 | 12 | 10.5 |
| fs_typo_path | fs | ❌ | 0/1 |  | 2 | 0 | 5 | 4.5 |
| fs_csv_max_temp | fs | ✅ | 1/1 |  | 4 | 0 | 6 | 5.4 |
| fs_doc_question | fs | ❌ | 0/2 |  | 1 | 0 | 3 | 2.4 |
| dk_overview | docker | ✅ | 2/2 |  | 1 | 0 | 3 | 2.3 |
| dk_restart_backup | docker | ✅ | 2/2 |  | 2 | 1 | 5 | 6.5 |
| dk_logs_error | docker | ✅ | 2/2 |  | 3 | 0 | 7 | 4.6 |
| dk_exec_conf | docker | ✅ | 1/1 |  | 3 | 0 | 6 | 4.0 |
| dk_env_var | docker | ✅ | 1/1 |  | 5 | 0 | 11 | 8.2 |
| dk_diagnose_exit | docker | ✅ | 2/2 |  | 4 | 0 | 8 | 6.5 |
| dk_create_box | docker | ✅ | 2/2 |  | 2 | 1 | 5 | 4.5 |
| dk_image_size | docker | ✅ | 2/2 |  | 1 | 0 | 3 | 2.3 |
| dk_ambiguous | docker | ✅ | 2/2 |  | 3 | 0 | 7 | 6.1 |
| dk_stop_tools | docker | ✅ | 2/2 |  | 3 | 2 | 5 | 11.3 |
| ros_nodes | ros2 | ✅ | 1/1 |  | 3 | 0 | 7 | 6.1 |
| ros_topics_tb2 | ros2 | ✅ | 1/1 |  | 3 | 0 | 7 | 5.9 |
| ros_battery_tb3 | ros2 | ✅ | 1/1 |  | 3 | 0 | 7 | 13.6 |
| ros_lowest_battery | ros2 | ✅ | 2/2 |  | 1 | 0 | 3 | 4.1 |
| ros_node_subs | ros2 | ✅ | 1/1 |  | 5 | 0 | 12 | 13.4 |
| ros_param | ros2 | ✅ | 1/1 |  | 3 | 0 | 7 | 6.1 |
| ros_domain_mismatch | ros2 | ❌ | 1/2 |  | 13 | 0 | 26 | 28.8 |
| ros_moving | ros2 | ✅ | 2/2 |  | 6 | 0 | 12 | 19.4 |
| ros_pub_yes | ros2 | ❌ | 1/2 |  | 2 | 1 | 4 | 8.5 |
| ros_hz | ros2 | ✅ | 1/1 |  | 3 | 0 | 8 | 12.9 |
| hs_send_track | handshake | ✅ | 2/2 |  | 2 | 1 | 5 | 65.4 |
| hs_busy_diag | handshake | ✅ | 3/3 |  | 3 | 0 | 6 | 9.9 |
| hs_silent_diag | handshake | ✅ | 2/2 |  | 3 | 0 | 6 | 10.1 |
| hs_lost_fin_fix | handshake | ❌ | 0/2 |  | 1 | 0 | 3 | 3.1 |
| hs_offline_diag | handshake | ✅ | 2/2 |  | 2 | 0 | 5 | 8.6 |
| hs_cancel_one | handshake | ✅ | 1/1 |  | 1 | 1 | 3 | 2.4 |
| hs_trigger_yes | handshake | ✅ | 2/2 |  | 2 | 2 | 4 | 2.5 |
| hs_semantic | handshake | ✅ | 1/1 |  | 2 | 1 | 5 | 24.9 |
| hs_ovp_delete | handshake | ✅ | 1/1 |  | 2 | 1 | 5 | 8.9 |
| hs_status | handshake | ✅ | 3/3 |  | 1 | 0 | 3 | 3.3 |
| cx_fin_and_note | complex | ✅ | 3/3 |  | 12 | 5 | 47 | 134.5 |
| cx_shift_report | complex | ❌ | 0/2 |  | 1 | 1 | 18 | 28.6 |
| cx_restart_verify | complex | ❌ | 1/2 |  | 5 | 2 | 20 | 32.7 |
| cx_reassign | complex | ✅ | 2/2 |  | 6 | 3 | 12 | 42.6 |
| cx_batch_dispatch | complex | ✅ | 3/3 |  | 1 | 1 | 22 | 49.4 |
| cx_config_dispatch | complex | ✅ | 3/3 |  | 4 | 2 | 9 | 29.8 |
| cx_domain_fix | complex | ❌ | 0/2 |  | 4 | 0 | 9 | 9.7 |
| cx_incident_timeline | complex | ❌ | 1/2 |  | 1 | 1 | 25 | 39.3 |
