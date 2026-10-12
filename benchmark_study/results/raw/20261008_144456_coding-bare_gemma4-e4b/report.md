# 自建 coding 情境：不用 harness 的對照組（gemma4:e4b）

- 時間：2026-10-08 14:47；每個情境呼叫一次模型（任務＋專案全部檔案的內容），直接寫回它輸出的檔案；沒有工具、規劃、測試回饋與重試。檢查跟 run_coding_evals.py 一樣（hidden tests 驗收）。
- **通過 20/28**

| 情境 | 通過 | 檢查 | 寫了哪些檔案 | 秒數 |
|---|---|---|---|---|
| feature_restock | ❌ | {'all_tests': False, 'hidden_tests': True} | inventory/store.py、tests/test_store.py | 3.8 |
| feature_restock | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/store.py、tests/test_store.py | 3.6 |
| rename_cross_file | ✅ | {'all_tests': True, 'hidden_tests': True, 'absent': True} | inventory/models.py、inventory/store.py、inventory/cli.py、tests/test_store.py | 3.7 |
| rename_cross_file | ✅ | {'all_tests': True, 'hidden_tests': True, 'absent': True} | inventory/models.py、inventory/store.py、inventory/cli.py、tests/test_store.py | 3.4 |
| feature_csv_export | ❌ | {'all_tests': False, 'hidden_tests': True} | inventory/storage.py、inventory/cli.py、tests/test_storage.py | 4.1 |
| feature_csv_export | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/storage.py、inventory/cli.py、tests/test_storage.py | 3.9 |
| bugfix_textstats | ✅ | {'all_tests': True, 'unchanged': True} | textstats/stats.py | 1.1 |
| bugfix_textstats | ✅ | {'all_tests': True, 'unchanged': True} | textstats/stats.py | 0.9 |
| long_category_feature | ❌ | {'all_tests': False, 'hidden_tests': True} | inventory/models.py、inventory/store.py、inventory/storage.py、inventory/cli.py、tests/test_storage.py、tests/test_store.py | 8.3 |
| long_category_feature | ❌ | {'all_tests': False, 'hidden_tests': True} | inventory/models.py、inventory/store.py、inventory/storage.py、inventory/cli.py、tests/test_storage.py、tests/test_store.py | 7.7 |
| new_module | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/discount.py、tests/test_discount.py | 4.2 |
| new_module | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/discount.py、tests/test_discount.py | 3.6 |
| cpp_perimeter | ✅ | {'all_tests': True, 'hidden_tests': True} | include/geometry/shape.hpp、include/geometry/circle.hpp、include/geometry/rectangle.hpp、src/circle.cpp、src/rectangle.cpp、tests/test_shapes.cpp、tests/test_registry.cpp | 4.8 |
| cpp_perimeter | ✅ | {'all_tests': True, 'hidden_tests': True} | include/geometry/shape.hpp、include/geometry/circle.hpp、include/geometry/rectangle.hpp、src/circle.cpp、src/rectangle.cpp、tests/test_shapes.cpp、tests/test_registry.cpp | 4.5 |
| cpp_triangle | ❌ | {'all_tests': False, 'hidden_tests': False} | include/geometry/triangle.hpp、src/triangle.cpp、src/registry.cpp、tests/test_registry.cpp、tests/test_shapes.cpp | 8.5 |
| cpp_triangle | ✅ | {'all_tests': True, 'hidden_tests': True} | include/geometry/triangle.hpp、src/triangle.cpp、src/registry.cpp、tests/test_registry.cpp、tests/test_shapes.cpp | 7.6 |
| cpp_bugfix_total | ✅ | {'all_tests': True, 'hidden_tests': True} | src/registry.cpp、tests/test_registry.cpp | 3.2 |
| cpp_bugfix_total | ✅ | {'all_tests': True, 'hidden_tests': True} | src/registry.cpp、tests/test_registry.cpp | 3.1 |
| c_ringbuf_api | ✅ | {'all_tests': True, 'hidden_tests': True} | include/ringbuf.h、src/ringbuf.c、tests/test_ringbuf.cpp | 7.4 |
| c_ringbuf_api | ✅ | {'all_tests': True, 'hidden_tests': True} | include/ringbuf.h、src/ringbuf.c、tests/test_ringbuf.cpp | 6.8 |
| c_bugfix_mean | ✅ | {'all_tests': True, 'hidden_tests': True} | src/ringbuf.c、tests/test_ringbuf.cpp | 6.7 |
| c_bugfix_mean | ✅ | {'all_tests': True, 'hidden_tests': True} | src/ringbuf.c、tests/test_ringbuf.cpp | 5.6 |
| ros2_cpp_compose | ❌ | {'all_tests': False, 'hidden_tests': True} | src/amr_utils/include/amr_utils/odom_math.hpp、src/amr_utils/src/odom_math.cpp、src/amr_utils/test/test_odom_math.cpp | 7.2 |
| ros2_cpp_compose | ❌ | {'all_tests': False, 'hidden_tests': True} | src/amr_utils/include/amr_utils/odom_math.hpp、src/amr_utils/src/odom_math.cpp、src/amr_utils/test/test_odom_math.cpp | 7.8 |
| ros2_cpp_bugfix_angle | ✅ | {'all_tests': True, 'hidden_tests': True} | src/amr_utils/src/odom_math.cpp、src/amr_utils/test/test_odom_math.cpp | 4.5 |
| ros2_cpp_bugfix_angle | ✅ | {'all_tests': True, 'hidden_tests': True} | src/amr_utils/src/odom_math.cpp、src/amr_utils/test/test_odom_math.cpp | 3.9 |
| ros2_py_battery | ✅ | {'all_tests': True, 'hidden_tests': True, 'contains': True} | src/amr_tools/amr_tools/battery.py、src/amr_tools/amr_tools/battery_node.py、src/amr_tools/test/test_battery.py | 4.5 |
| ros2_py_battery | ❌ | {'all_tests': False, 'hidden_tests': True, 'contains': True} | src/amr_tools/amr_tools/battery.py、src/amr_tools/amr_tools/battery_node.py、src/amr_tools/test/test_battery.py | 4.7 |
