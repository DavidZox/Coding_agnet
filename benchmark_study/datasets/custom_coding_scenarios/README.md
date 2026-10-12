# 自建的 coding 情境（14 個）

`evals/coding_fixtures/` 的副本（範例專案）＋ `scenarios.json`（任務文字、檢查條件）＋ `hidden_tests/<情境>/`（agent 從頭到尾看不到、job 結束後才放進去的測試）。評測程式在 `evals/run_coding_evals.py`（harness）與 `evals/bare_coding_baseline.py`（不用 harness 的對照組）。

| 範例專案 | 語言與建置 | 情境 |
|---|---|---|
| `inventory_app/` | Python 套件＋CLI＋pytest | feature_restock、rename_cross_file、feature_csv_export、long_category_feature、new_module |
| `textstats_app/` | Python＋pytest（有 bug） | bugfix_textstats（不能改測試） |
| `geometry_cpp/` | C++17、CMake＋GoogleTest | cpp_perimeter、cpp_triangle、cpp_bugfix_total |
| `ringbuf_c/` | C、Makefile＋GoogleTest | c_ringbuf_api、c_bugfix_mean |
| `ros2_ws/` | ROS 2 colcon 工作區：ament_cmake（amr_utils）＋ament_python（amr_tools）；這台主機沒有 ROS 2 | ros2_cpp_compose、ros2_cpp_bugfix_angle、ros2_py_battery |

檢查（全部成立才算通過）：`all_tests`（整個專案的測試，含 hidden tests，真的 pytest／gtest）、`hidden_tests`、`unchanged`（不准改的檔案）、`absent`（改名後舊名稱不能再出現）、`contains`（測不到的部分，例如 rclpy 的 node 有沒有照任務改）。hidden tests 都用參考解法確認過「原本的專案會失敗、參考解法會通過」。

注意：這些情境是這個專案自己寫的，也被拿來找問題、改 prompt 與檢查規則，分數偏樂觀（見技術報告的「效度威脅」）。
