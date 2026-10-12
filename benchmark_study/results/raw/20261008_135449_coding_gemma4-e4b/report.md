# coding 評測：worker gemma4:e4b、規劃 gemma4:e4b

- 時間：2026-10-08 14:01；每個情境 1 次；通過 14/14

| 情境 | 通過 | job 狀態 | 平均秒數 | 平均模型呼叫 | 沒通過的條件 |
|---|---|---|---|---|---|
| feature_restock | 1/1 | done | 19 | 14 | — |
| rename_cross_file | 1/1 | done | 16 | 16 | — |
| feature_csv_export | 1/1 | done | 17 | 14 | — |
| bugfix_textstats | 1/1 | done | 26 | 26 | — |
| long_category_feature | 1/1 | done | 42 | 34 | — |
| new_module | 1/1 | done | 62 | 36 | — |
| cpp_perimeter | 1/1 | done | 35 | 44 | — |
| cpp_triangle | 1/1 | done | 35 | 38 | — |
| cpp_bugfix_total | 1/1 | done | 14 | 12 | — |
| c_ringbuf_api | 1/1 | done | 34 | 24 | — |
| c_bugfix_mean | 1/1 | done | 12 | 10 | — |
| ros2_cpp_compose | 1/1 | done | 36 | 21 | — |
| ros2_cpp_bugfix_angle | 1/1 | done | 16 | 12 | — |
| ros2_py_battery | 1/1 | done | 21 | 17 | — |

## 每一次

### feature_restock：✅（done，19.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python） 13 passed（0.1 秒）（整個專案）
  - 1. done（1 次、3 步）Inventory.remove() 增加庫存不足檢查；檔案 ['inventory/store.py']；驗證 python3 -m pytest -q tests/test_store.py
  - 2. done（1 次、3 步）新增 Inventory.restock_below 方法；檔案 ['inventory/store.py']；驗證 python3 -m pytest -q tests/test_store.py
  - 3. done（1 次、3 步）新增 restock_below 測試案例；檔案 ['tests/test_store.py']；驗證 python3 -m pytest -q tests/test_store.py

### rename_cross_file：✅（done，16.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true, "absent": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python） 10 passed（0.1 秒）（整個專案）
  - 1. done（1 次、5 步）重命名 Inventory.total_value() 為 total()；檔案 ['inventory/store.py']；驗證 python3 -m pytest -q tests/test_store.py
  - 2. done（1 次、3 步）更新 Inventory 類別中呼叫 total_value() 的地方；檔案 ['tests/test_store.py']；驗證 python3 -m pytest -q tests/test_store.py
  - 3. done（1 次、2 步）在 CLI 中新增 total 子指令並實作邏輯；檔案 ['inventory/cli.py']；驗證 python3 -m inventory.cli --file /tmp/inv.json total

### feature_csv_export：✅（done，17.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python） 11 passed（0.2 秒）（整個專案）
  - 1. done（1 次、2 步）新增 CSV 匯出函式到 storage.py；檔案 ['inventory/storage.py']；驗證 python3 -m pytest -q tests/test_storage.py
  - 2. done（1 次、3 步）在 CLI 中新增 export 子指令；檔案 ['inventory/cli.py']；驗證 python3 -m inventory.cli --file /tmp/inv.json export /tmp/out.csv
  - 3. done（1 次、3 步）新增 CSV 匯出功能測試；檔案 ['tests/test_storage.py']；驗證 python3 -m pytest -q tests/test_storage.py

### bugfix_textstats：✅（done，25.5 秒）
- 檢查：{"all_tests": true, "unchanged": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python） 7 passed（0.1 秒）（整個專案）
  - 1. done（1 次、3 步）修正 words 函式以正確處理標點符號；檔案 ['textstats/stats.py']；驗證 python3 -m pytest -q tests/test_stats.py
  - 2. done（1 次、4 步）修正 average_word_length 函式邏輯；檔案 ['textstats/stats.py']；驗證 python3 -m pytest -q tests/test_stats.py
  - 3. done（1 次、5 步）修正 top_words 函式排序邏輯；檔案 ['textstats/stats.py']；驗證 python3 -m pytest -q tests/test_stats.py
  - 4. done（1 次、3 步）修正 word_count 函式邏輯；檔案 ['textstats/stats.py']；驗證 python3 -m pytest -q tests/test_stats.py
  - 5. done（1 次、4 步）更新 report.py 以使用修正後的統計函式；檔案 ['textstats/report.py']；驗證 python3 -m pytest -q tests/test_report.py

### long_category_feature：✅（done，42.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python） 22 passed（0.2 秒）（整個專案）
  - 1. done（1 次、2 步）Item 模型新增 category 欄位；檔案 ['inventory/models.py']；驗證 python3 -m pytest -q tests/test_store.py
  - 2. done（1 次、4 步）Inventory.add 處理 category 與測試；檔案 ['inventory/store.py', 'tests/test_store.py']；驗證 python3 -m pytest -q tests/test_store.py
  - 3. done（1 次、3 步）Inventory 新增 by_category() 方法；檔案 ['inventory/store.py', 'tests/test_store.py']；驗證 python3 -m pytest -q tests/test_store.py
  - 4. done（1 次、3 步）Storage 存檔/讀檔處理 category；檔案 ['inventory/storage.py', 'tests/test_storage.py']；驗證 python3 -m pytest -q tests/test_storage.py
  - 5. done（1 次、3 步）CLI: add 子指令新增 --category；檔案 ['inventory/cli.py', 'tests/test_store.py']；驗證 python3 -m inventory.cli --file /tmp/inv.json add apple 1.5 4 --category fruit
  - 6. done（1 次、3 步）CLI: 新增 categories 子指令；檔案 ['inventory/cli.py', 'tests/test_store.py']；驗證 python3 -m inventory.cli --file /tmp/inv.json categories
  - 7. done（1 次、2 步）測試：新增 category 相關邏輯；檔案 ['tests/test_store.py']；驗證 python3 -m pytest -q tests/test_store.py

### new_module：✅（done，61.5 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python） 19 passed（0.1 秒）（整個專案）
  - 1. done（1 次、4 步）新增 discount.py 實現 apply_discount；檔案 ['inventory/discount.py']；驗證 —
  - 2. done（2 次、10 步）新增 discount.py 實現 discounted_total；檔案 ['inventory/discount.py']；驗證 —
  - 3. done（1 次、8 步）新增測試文件並實作折扣功能測試；檔案 ['tests/test_discount.py']；驗證 python3 -m pytest -q tests/test_discount.py

### cpp_perimeter：✅（done，35.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：gtest（CMake＋ctest） 14 passed（0.6 秒）（整個專案）
  - 1. done（1 次、9 步）Shape 介面新增 perimeter() 純虛擬方法；檔案 ['include/geometry/shape.hpp']；驗證 code_test
  - 2. done（1 次、6 步）Circle 實作 perimeter() 方法；檔案 ['include/geometry/circle.hpp', 'src/circle.cpp']；驗證 code_test
  - 3. done（1 次、6 步）Rectangle 實作 perimeter() 方法；檔案 ['include/geometry/rectangle.hpp', 'src/rectangle.cpp']；驗證 code_test
  - 4. done（1 次、3 步）新增 Circle 周長測試案例；檔案 ['tests/test_shapes.cpp']；驗證 code_test
  - 5. done（1 次、3 步）新增 Rectangle 周長測試案例；檔案 ['tests/test_shapes.cpp']；驗證 code_test

### cpp_triangle：✅（done，35.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：gtest（CMake＋ctest） 12 passed（0.6 秒）（整個專案）
  - 1. done（1 次、4 步）新增 Triangle 類別定義；檔案 ['include/geometry/triangle.hpp']；驗證 code_test
  - 2. done（2 次、8 步）實作 Triangle 類別邏輯；檔案 ['src/triangle.cpp']；驗證 code_test
  - 3. done（1 次、9 步）更新 Registry 支援 Triangle 解析；檔案 ['src/registry.cpp']；驗證 code_test
  - 4. done（1 次、3 步）新增 Triangle 相關 GTest 測試；檔案 ['tests/test_shapes.cpp']；驗證 code_test

### cpp_bugfix_total：✅（done，14.5 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：gtest（CMake＋ctest） 12 passed（0.6 秒）（整個專案）
  - 1. done（1 次、4 步）修正 total_area 邏輯；檔案 ['src/registry.cpp']；驗證 code_test
  - 2. done（1 次、3 步）新增總面積計算測試；檔案 ['tests/test_registry.cpp']；驗證 code_test

### c_ringbuf_api：✅（done，34.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：gtest（make test） 10 passed（0.5 秒）（整個專案）
  - 1. done（1 次、3 步）新增 rb_peek_oldest 宣告與實作；檔案 ['include/ringbuf.h', 'src/ringbuf.c']；驗證 code_test
  - 2. done（1 次、6 步）新增 rb_clear 宣告與實作；檔案 ['include/ringbuf.h', 'src/ringbuf.c']；驗證 code_test
  - 3. done（1 次、3 步）新增 rb_peek_oldest 測試案例；檔案 ['tests/test_ringbuf.cpp']；驗證 code_test
  - 4. done（1 次、3 步）新增 rb_clear 測試案例；檔案 ['tests/test_ringbuf.cpp']；驗證 code_test

### c_bugfix_mean：✅（done，12.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：gtest（make test） 7 passed（0.4 秒）（整個專案）
  - 1. done（1 次、3 步）修正 rb_mean 計算邏輯；檔案 ['src/ringbuf.c']；驗證 code_test
  - 2. done（1 次、3 步）新增繞回後平均值測試案例；檔案 ['tests/test_ringbuf.cpp']；驗證 code_test

### ros2_cpp_compose：✅（done，36.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python）：src/amr_tools 3 passed（跳過 3 個缺外部依賴的測試檔）；gtest（g++ 直接編譯）：src/amr_utils 13 passed（跳過 1 個缺外部依賴的測試檔）（0.6 秒）（整個專案）
  - 1. done（1 次、7 步）在 odom_math.hpp 宣告 Pose2D compose 函式；檔案 ['src/amr_utils/include/amr_utils/odom_math.hpp']；驗證 code_test src/amr_utils
  - 2. done（1 次、3 步）在 odom_math.cpp 實作 Pose2D compose 函式；檔案 ['src/amr_utils/src/odom_math.cpp']；驗證 code_test src/amr_utils
  - 3. done（1 次、3 步）在 test_odom_math.cpp 新增 compose 函式測試；檔案 ['src/amr_utils/test/test_odom_math.cpp']；驗證 code_test src/amr_utils

### ros2_cpp_bugfix_angle：✅（done，15.5 秒）
- 檢查：{"all_tests": true, "hidden_tests": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python）：src/amr_tools 3 passed（跳過 3 個缺外部依賴的測試檔）；gtest（g++ 直接編譯）：src/amr_utils 8 passed（跳過 1 個缺外部依賴的測試檔）（0.6 秒）（整個專案）
  - 1. done（1 次、4 步）修正 normalize_angle 函式邏輯；檔案 ['src/amr_utils/src/odom_math.cpp']；驗證 code_test src/amr_utils
  - 2. done（1 次、3 步）新增負角度歸一化測試案例；檔案 ['src/amr_utils/test/test_odom_math.cpp']；驗證 code_test src/amr_utils

### ros2_py_battery：✅（done，21.0 秒）
- 檢查：{"all_tests": true, "hidden_tests": true, "contains": true}；測試：[PASS] 測試全部通過：pytest（~/aiagent_venv_env/.venv/bin/python）：src/amr_tools 11 passed（跳過 3 個缺外部依賴的測試檔）；gtest（g++ 直接編譯）：src/amr_utils 4 passed（跳過 1 個缺外部依賴的測試檔）（0.6 秒）（整個專案）
  - 1. done（1 次、5 步）Battery: 新增 is_low 檢查函式；檔案 ['src/amr_tools/amr_tools/battery.py']；驗證 python3 -m pytest -q src/amr_tools/test/test_battery.py
  - 2. done（1 次、3 步）BatteryNode: 實作低電量警告邏輯；檔案 ['src/amr_tools/amr_tools/battery_node.py']；驗證 python3 -m pytest -q src/amr_tools/test/test_battery.py
  - 3. done（1 次、2 步）Test: 新增 is_low 相關測試案例；檔案 ['src/amr_tools/test/test_battery.py']；驗證 python3 -m pytest -q src/amr_tools/test/test_battery.py
