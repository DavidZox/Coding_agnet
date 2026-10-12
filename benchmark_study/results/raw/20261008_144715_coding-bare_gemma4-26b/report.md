# 自建 coding 情境：不用 harness 的對照組（gemma4:26b）

- 時間：2026-10-08 14:49；每個情境呼叫一次模型（任務＋專案全部檔案的內容），直接寫回它輸出的檔案；沒有工具、規劃、測試回饋與重試。檢查跟 run_coding_evals.py 一樣（hidden tests 驗收）。
- **通過 23/28**

| 情境 | 通過 | 檢查 | 寫了哪些檔案 | 秒數 |
|---|---|---|---|---|
| feature_restock | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/store.py、tests/test_store.py | 9.8 |
| feature_restock | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/store.py、tests/test_store.py | 4.0 |
| rename_cross_file | ✅ | {'all_tests': True, 'hidden_tests': True, 'absent': True} | inventory/cli.py、inventory/store.py、tests/test_store.py | 4.3 |
| rename_cross_file | ✅ | {'all_tests': True, 'hidden_tests': True, 'absent': True} | inventory/cli.py、inventory/store.py、tests/test_store.py | 4.1 |
| feature_csv_export | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/storage.py、inventory/cli.py、tests/test_storage.py | 4.5 |
| feature_csv_export | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/storage.py、inventory/cli.py、tests/test_storage.py | 4.1 |
| bugfix_textstats | ✅ | {'all_tests': True, 'unchanged': True} | textstats/stats.py、textstats/report.py | 2.5 |
| bugfix_textstats | ✅ | {'all_tests': True, 'unchanged': True} | textstats/stats.py、textstats/report.py | 2.4 |
| long_category_feature | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/models.py、inventory/store.py、inventory/storage.py、inventory/cli.py、tests/test_store.py、tests/test_storage.py | 7.7 |
| long_category_feature | ✅ | {'all_tests': True, 'hidden_tests': True} | inventory/models.py、inventory/store.py、inventory/storage.py、inventory/cli.py、tests/test_storage.py、tests/test_store.py | 8.0 |
| new_module | ❌ | {'all_tests': False, 'hidden_tests': True} | inventory/__init__.py、inventory/discount.py、tests/test_discount.py | 3.4 |
| new_module | ❌ | {'all_tests': False, 'hidden_tests': True} | inventory/__init__.py、inventory/discount.py、tests/test_discount.py | 2.8 |
| cpp_perimeter | ✅ | {'all_tests': True, 'hidden_tests': True} | include/geometry/circle.hpp、include/geometry/rectangle.hpp、include/geometry/shape.hpp、src/circle.cpp、src/rectangle.cpp、tests/test_shapes.cpp | 5.0 |
| cpp_perimeter | ✅ | {'all_tests': True, 'hidden_tests': True} | include/geometry/circle.hpp、include/geometry/rectangle.hpp、include/geometry/shape.hpp、src/circle.cpp、src/rectangle.cpp、tests/test_shapes.cpp | 4.6 |
| cpp_triangle | ✅ | {'all_tests': True, 'hidden_tests': True} | include/geometry/triangle.hpp、src/triangle.cpp、src/registry.cpp、tests/test_registry.cpp、tests/test_shapes.cpp | 7.4 |
| cpp_triangle | ✅ | {'all_tests': True, 'hidden_tests': True} | include/geometry/triangle.hpp、src/triangle.cpp、src/registry.cpp、tests/test_registry.cpp、tests/test_shapes.cpp | 7.0 |
| cpp_bugfix_total | ❌ | {'all_tests': False, 'hidden_tests': False} | src/registry.cpp、tests/test_registry.cpp | 4.4 |
| cpp_bugfix_total | ❌ | {'all_tests': False, 'hidden_tests': False} | src/registry.cpp、tests/test_registry.cpp | 3.9 |
| c_ringbuf_api | ✅ | {'all_tests': True, 'hidden_tests': True} | include/ringbuf.h、src/ringbuf.c、tests/test_ringbuf.cpp | 7.5 |
| c_ringbuf_api | ✅ | {'all_tests': True, 'hidden_tests': True} | include/ringbuf.h、src/ringbuf.c、tests/test_ringbuf.cpp | 7.2 |
| c_bugfix_mean | ✅ | {'all_tests': True, 'hidden_tests': True} | src/ringbuf.c、tests/test_ringbuf.cpp | 5.4 |
| c_bugfix_mean | ✅ | {'all_tests': True, 'hidden_tests': True} | src/ringbuf.c、tests/test_ringbuf.cpp | 5.0 |
| ros2_cpp_compose | ✅ | {'all_tests': True, 'hidden_tests': True} | src/amr_utils/include/amr_utils/odom_math.hpp、src/amr_utils/src/odom_math.cpp、src/amr_utils/test/test_odom_math.cpp | 7.6 |
| ros2_cpp_compose | ✅ | {'all_tests': True, 'hidden_tests': True} | src/amr_utils/include/amr_utils/odom_math.hpp、src/amr_utils/src/odom_math.cpp、src/amr_utils/test/test_odom_math.cpp | 7.1 |
| ros2_cpp_bugfix_angle | ✅ | {'all_tests': True, 'hidden_tests': True} | src/amr_utils/src/odom_math.cpp、src/amr_utils/test/test_odom_math.cpp | 5.2 |
| ros2_cpp_bugfix_angle | ✅ | {'all_tests': True, 'hidden_tests': True} | src/amr_utils/src/odom_math.cpp、src/amr_utils/test/test_odom_math.cpp | 4.3 |
| ros2_py_battery | ❌ | {'all_tests': False, 'hidden_tests': True, 'contains': True} | src/amr_tools/amr_tools/battery.py、src/amr_tools/amr_tools/battery_node.py、src/amr_tools/test/test_battery.py | 5.0 |
| ros2_py_battery | ✅ | {'all_tests': True, 'hidden_tests': True, 'contains': True} | src/amr_tools/amr_tools/battery.py、src/amr_tools/amr_tools/battery_node.py、src/amr_tools/test/test_battery.py | 4.4 |
