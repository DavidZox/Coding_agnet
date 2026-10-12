# DevBench 實作任務：worker gemma4:26b、規劃 gemma4:26b

- 時間：2026-10-08 18:43；12 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。**官方測試放在工作區、agent 可以跑**（DevBench 基準 agent 的設定）。

- **全部**（12 個 repo）：單元測試 86/116（74.1%）、驗收測試 21/51（41.2%）；每個 repo 通過率的平均：單元 66.3%、驗收 49.0%；依程式碼行數加權：單元 63.8%、驗收 40.7%
- **Python**（7 個 repo）：單元測試 40/57（70.2%）、驗收測試 10/24（41.7%）；每個 repo 通過率的平均：單元 62.9%、驗收 48.6%；依程式碼行數加權：單元 56.9%、驗收 42.2%
- **C++**（5 個 repo）：單元測試 46/59（78.0%）、驗收測試 11/27（40.7%）；每個 repo 通過率的平均：單元 71.0%、驗收 49.7%；依程式碼行數加權：單元 69.8%、驗收 39.5%

| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|
| readtime | python | 5/8 | 0/4 | partial | 1/4 | 9.5 | 144 |
| particle-swarm-optimization | python | 5/5 | 1/1 | done | 4/4 | 0.7 | 29 |
| chakin | python | 1/1 | 1/1 | done | 3/3 | 1.4 | 40 |
| stocktrends | python | 4/7 | 0/2 | partial | 1/5 | 19.3 | 186 |
| geotext | python | 1/4 | 2/5 | partial | 1/5 | 10.3 | 162 |
| hone | python | 0/7 | 0/5 | partial | 0/4 | 23.8 | 161 |
| lice | python | 24/25 | 6/6 | partial | 1/5 | 7.0 | 154 |
| area_calculation | cpp | 3/3 | 3/3 | partial | 3/6 | 4.0 | 113 |
| graph-cpp | cpp | 21/22 | 2/5 | partial | 4/6 | 14.4 | 154 |
| logistic_system | cpp | 17/17 | 1/7 | done | 5/5 | 4.4 | 74 |
| people_management | cpp | 2/9 | 1/7 | partial | 1/5 | 11.1 | 189 |
| xlsx2csv | cpp | 3/8 | 4/5 | partial | 7/11 | 11.8 | 228 |

參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%；GPT-4-Turbo-1106 驗收 6.9%、單元 6.8%；GPT-3.5-Turbo 驗收 4.2%、單元 4.3%；DeepSeek-Coder-33B-Instruct 驗收 4.4%、單元 5.5%；CodeLlama-34B-Instruct 驗收 0.6%、單元 0.5%

## 每個 repo

### readtime：單元 5/8、驗收 0/4（partial，9.5 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 7 failed、5 passed（0.1 秒）（整個專案）
  - 1. skipped（2 次、31 步）建立 readtime 套件基礎結構與 Result 類別；檔案 ['readtime/__init__.py', 'readtime/__about__.py', 'readtime/result.py']
  - 2. done（2 次、16 步）實作 readtime/utils.py 核心邏輯；檔案 ['readtime/utils.py']
  - 3. skipped（2 次、30 步）實作 readtime/api.py 介面；檔案 ['readtime/api.py']
  - 4. failed（2 次、29 步）修正整體驗證的失敗；檔案 ['readtime/__about__.py', 'readtime/__init__.py', 'readtime/api.py', 'readtime/result.py', 'readtime/utils.py', 'scripts/analyze_samples.py']
- 單元測試輸出（尾巴）：
```
E           AssertionError: 0 != 1

unit_tests/test_transitions.py:16: AssertionError
=========================== short test summary info ============================
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_empty - A...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm - Asserti...
FAILED unit_tests/test_transitions.py::BaseTestCase::test_transitions - Asser...
3 failed, 5 passed in 0.05s
```
- 驗收測試輸出（尾巴）：
```

acceptance_tests/test_readtime.py:12: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_can_add - Assert...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_html - Assertion...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_markdown - Asser...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_plain_text - Ass...
4 failed in 0.05s
```

### particle-swarm-optimization：單元 5/5、驗收 1/1（done，0.7 分鐘）
- 整體驗證（agent 自己的）：[PASS] 測試全部通過：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 6 passed（0.1 秒）（整個專案）
  - 1. done（1 次、2 步）建立 pso 套件結構與 __init__.py；檔案 ['pso/__init__.py']
  - 2. done（1 次、8 步）實作 cost_functions.py 中的 sphere 函數；檔案 ['pso/cost_functions.py']
  - 3. done（1 次、6 步）實作 pso_simple.py 中的 Particle 類別；檔案 ['pso/pso_simple.py']
  - 4. done（1 次、5 步）實作 pso_simple.py 中的 minimize 函式；檔案 ['pso/pso_simple.py']
- 單元測試輸出（尾巴）：
```
.....                                                                    [100%]
5 passed in 0.01s
```
- 驗收測試輸出（尾巴）：
```
.                                                                        [100%]
1 passed in 0.00s
```

### chakin：單元 1/1、驗收 1/1（done，1.4 分鐘）
- 整體驗證（agent 自己的）：[PASS] 測試全部通過：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 2 passed（0.9 秒）（整個專案）
  - 1. done（1 次、5 步）建立 chakin 套件結構與 datasets.csv；檔案 ['chakin/__init__.py', 'chakin/downloader.py', 'chakin/datasets.csv']
  - 2. done（1 次、18 步）實作 downloader.py 的核心邏輯；檔案 ['chakin/downloader.py']
  - 3. done（1 次、5 步）實作 chakin/__init__.py API 導出；檔案 ['chakin/__init__.py']
- 單元測試輸出（尾巴）：
```
.                                                                        [100%]
1 passed in 0.76s
```
- 驗收測試輸出（尾巴）：
```
.                                                                        [100%]
1 passed in 0.37s
```

### stocktrends：單元 4/7、驗收 0/2（partial，19.3 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 5 failed、4 passed（0.3 秒）（整個專案）
  - 1. done（1 次、4 步）建立 stocktrends 套件結構與 Instrument 基底類別；檔案 ['stocktrends/__init__.py', 'stocktrends/indicators.py']
  - 2. skipped（2 次、24 步）實作 Renko 指標類別；檔案 ['stocktrends/indicators.py']
  - 3. skipped（2 次、29 步）實作 LineBreak 指標類別；檔案 ['stocktrends/indicators.py']
  - 4. skipped（2 次、36 步）實作 PnF 指標類別；檔案 ['stocktrends/indicators.py']
  - 5. failed（2 次、28 步）修正整體驗證的失敗；檔案 ['stocktrends/__init__.py', 'stocktrends/indicators.py']
- 單元測試輸出（尾巴）：
```
E         Use -v to get more diff

unit_tests/test_renko.py:14: AssertionError
=========================== short test summary info ============================
FAILED unit_tests/test_pnf.py::test_get_bar_ohlc_data_hl - assert (37, 5) == ...
FAILED unit_tests/test_pnf.py::test_get_ohlc_data_close - assert (280, 6) == ...
FAILED unit_tests/test_renko.py::test_Renko_box_periodic_close - assert (131,...
3 failed, 4 passed in 0.19s
```
- 驗收測試輸出（尾巴）：
```
E        +    and   0      1.175\n1      4.850\n2     19.875\n3     26.475\n4     33.475\n       ...  \n71       NaN\n72       NaN\n73       NaN\n74       NaN\n75       NaN\nName: close, Length: 76, dtype: float64 = <ufunc 'absolute'>((0     142.775\n1     137.925\n2     118.050\n3     117.475\n4     151.525\n       ...   \n60    170.450\n61    157.950\n62    204.850\n63    205.200\n64    207.700\nName: close, Length: 65, dtype: float64 - 0     143.950\n1     142.775\n2     137.925\n3     143.950\n4     118.050\n       ...   \n71    187.950\n72    189.325\n73    204.850\n74    205.200\n75    207.700\nName: close, Length: 76, dtype: float64))
E        +      where <ufunc 'absolute'> = np.abs

acceptance_tests/test_indicators.py:42: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_indicators.py::test_renko - AssertionError: asse...
FAILED acceptance_tests/test_indicators.py::test_linebreak - AssertionError: ...
2 failed in 0.16s
```

### geotext：單元 1/4、驗收 2/5（partial，10.3 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 6 failed、3 passed（0.1 秒）（整個專案）
  - 1. done（1 次、2 步）建立 geotext 套件結構與 __init__.py；檔案 ['geotext/__init__.py']
  - 2. skipped（2 次、24 步）實作資料讀取工具函式與 build_index；檔案 ['geotext/geotext.py']
  - 3. skipped（2 次、28 步）實作 GeoText 類別核心邏輯；檔案 ['geotext/geotext.py']
  - 4. skipped（2 次、36 步）執行驗收測試以確保完整性；檔案 []
  - 5. failed（2 次、36 步）修正整體驗證的失敗；檔案 ['geotext/__init__.py', 'geotext/data_file/cities15000.txt', 'geotext/data_file/citypatches.txt', 'geotext/data_file/countryInfo.txt', 'geotext/data_file/nationalities.txt', 'geotext/geotext.py']
- 單元測試輸出（尾巴）：
```
E       AssertionError: OrderedDict() != {'PE': 1, 'IE': 1, 'RU': 2}

unit_tests/test_geotext.py:120: AssertionError
=========================== short test summary info ============================
FAILED unit_tests/test_geotext.py::TestGeotext::test_cities - AssertionError:...
FAILED unit_tests/test_geotext.py::TestGeotext::test_countries - AssertionErr...
FAILED unit_tests/test_geotext.py::TestGeotext::test_country_mentions - Asser...
3 failed, 1 passed in 0.01s
```
- 驗收測試輸出（尾巴）：
```
E       AssertionError: OrderedDict({'CN': 1}) != OrderedDict({'US': 2, 'CN': 1})

acceptance_tests/test_acceptance.py:23: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_city_extraction
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_filter
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_mentions_count
3 failed, 2 passed in 0.01s
```

### hone：單元 0/7、驗收 0/5（partial，23.8 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 逾時（300.0 秒）（整個專案）
  - 1. skipped（2 次、26 步）實作 CSV 與 JSON 工具類別；檔案 ['hone/utils/csv_utils.py', 'hone/utils/json_utils.py', 'hone/utils/__init__.py']
  - 2. skipped（2 次、24 步）實作 Hone 核心轉換邏輯；檔案 ['hone/hone.py']
  - 3. skipped（2 次、24 步）建立套件入口與 CLI 介面；檔案 ['hone/__init__.py', 'hone/__main__.py']
  - 4. failed（2 次、33 步）修正整體驗證的失敗；檔案 ['hone/__init__.py', 'hone/__main__.py', 'hone/hone.py', 'hone/utils/__init__.py', 'hone/utils/csv_utils.py', 'hone/utils/json_utils.py']
- 單元測試輸出（尾巴）：
```
（逾時：超過 600 秒）
```
- 驗收測試輸出（尾巴）：
```
（逾時：超過 600 秒）
```

### lice：單元 24/25、驗收 6/6（partial，7.0 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 1 failed、30 passed（0.2 秒）（整個專案）
  - 1. done（1 次、2 步）建立 lice 套件結構與 __init__.py；檔案 ['unit_tests/__init__.py']
  - 2. skipped（2 次、26 步）實作 core.py 基礎工具與 Context 類別；檔案 ['lice/core.py']
  - 3. skipped（2 次、36 步）實作模板讀取與變數處理邏輯；檔案 ['lice/core.py']
  - 4. skipped（2 次、12 步）實作語言格式化與 CLI main 函式；檔案 ['lice/core.py']
  - 5. failed（2 次、32 步）修正整體驗證的失敗；檔案 ['lice/__init__.py', 'lice/core.py']
- 單元測試輸出（尾巴）：
```
E           SystemExit: 1

lice/core.py:300: SystemExit
----------------------------- Captured stdout call -----------------------------
Error: path does not exist: /tmp/devbench_run_4faq_jam/workspace/nonexistent_path
=========================== short test summary info ============================
FAILED unit_tests/test_lice.py::TestMainFunction::test_template_path_not_exist
1 failed, 24 passed in 0.04s
```
- 驗收測試輸出（尾巴）：
```
......                                                                   [100%]
6 passed in 0.10s
```

### area_calculation：單元 3/3、驗收 3/3（partial，4.0 分鐘）
- 整體驗證（agent 自己的）：[PASS] 測試全部通過：gtest（make -f makefile_test test） 3 passed（1.3 秒）（整個專案）
  - 1. skipped（2 次、12 步）實作 Shape 基礎類別；檔案 ['include/Shape.h', 'src/Shape.cpp']
  - 2. skipped（2 次、10 步）實作 Circle 類別；檔案 ['include/Circle.hpp']
  - 3. skipped（2 次、14 步）實作 Rectangle 類別；檔案 ['include/Rectangle.h', 'src/Rectangle.cpp']
  - 4. done（1 次、3 步）實作 Square 類別；檔案 ['include/Square.hpp']
  - 5. done（2 次、36 步）實作 main.cpp 檔案處理邏輯；檔案 ['src/main.cpp']
  - 6. done（1 次、11 步）建立 Makefile 建置檔；檔案 ['makefile']
- 單元測試輸出（尾巴）：
```
~Rectangle()
~Shape()
[       OK ] TestSquare.CalcArea (0 ms)
[----------] 1 test from TestSquare (0 ms total)

[----------] Global test environment tear-down
[==========] 3 tests from 3 test suites ran. (0 ms total)
[  PASSED  ] 3 tests.
```
- 驗收測試輸出（尾巴）：
```
g++ -std=c++17 -Wall -Wextra -Iinclude -c src/main.cpp -o src/main.o
g++ -std=c++17 -Wall -Wextra -Iinclude -o area_calculation src/Shape.o src/Rectangle.o src/main.o
Processed input/1.txt and saved the output to outputs/1.txt
Processed input/2.txt and saved the output to outputs/2.txt
Processed input/3.txt and saved the output to outputs/3.txt
File 1.txt matches
File 2.txt matches
File 3.txt matches
```

### graph-cpp：單元 21/22、驗收 2/5（partial，14.4 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：gtest（make -f makefile_test test） 1 failed、21 passed（2.1 秒）（整個專案）
  - 1. done（2 次、18 步）實作 Queue 類別；檔案 ['include/queue.hpp']
  - 2. done（1 次、3 步）實作 Stack 類別；檔案 ['include/stack.hpp']
  - 3. done（1 次、9 步）實作 AdjacencyMatrixGraph 類別；檔案 ['include/am_graph.hpp']
  - 4. skipped（2 次、29 步）實作 AdjacencyListGraph 類別；檔案 ['include/al_graph.hpp']
  - 5. done（2 次、28 步）實作 main 函式與 Makefile；檔案 ['src/main.cpp', 'makefile']
  - 6. failed（2 次、25 步）修正整體驗證的失敗；檔案 ['include/al_graph.hpp', 'include/am_graph.hpp', 'include/queue.hpp', 'include/stack.hpp', 'makefile', 'src/main.cpp']
- 單元測試輸出（尾巴）：
```
[----------] Global test environment tear-down
[==========] 22 tests from 4 test suites ran. (0 ms total)
[  PASSED  ] 21 tests.
[  FAILED  ] 1 test, listed below:
[  FAILED  ] GraphTest.TestDFSNoRecursionAdjacencyList

 1 FAILED TEST
make: *** [makefile_test:38: test] Error 1
```
- 驗收測試輸出（尾巴）：
```
g++ -std=c++17 -Wall -Iinclude -c src/main.cpp -o src/main.o
g++ -std=c++17 -Wall -Iinclude -o graph src/main.o
Test passed: Test Bad Input File passed
Test passed: Test Bad Input File passed
Test failed: Output for 'directed_graph.txt' doesn't match expected output
Test failed: Output for 'sample.txt' doesn't match expected output
Test failed: Output for 'undirected_graph.txt' doesn't match expected output
Testing completed. Check the test_outputs directory for results.
```

### logistic_system：單元 17/17、驗收 1/7（done，4.4 分鐘）
- 整體驗證（agent 自己的）：[PASS] 測試全部通過：gtest（make test） 17 passed（1.9 秒）（整個專案）
  - 1. done（1 次、8 步）實作 ExpressageNode 類別；檔案 ['include/expressage.h', 'src/expressage.cpp']
  - 2. done（1 次、11 步）實作 AccountNode 類別；檔案 ['include/account.h', 'src/account.cpp']
  - 3. done（2 次、23 步）實作 LogisticSys 核心邏輯；檔案 ['include/logistics.h', 'src/logistics.cpp']
  - 4. done（1 次、5 步）實作 main.cpp CLI 互動介面；檔案 ['src/main.cpp']
  - 5. done（1 次、4 步）建立 Makefile；檔案 ['makefile']
- 單元測試輸出（尾巴）：
```
[       OK ] LogisticSysTest.QueryAllExpressageTest (0 ms)
[ RUN      ] LogisticSysTest.QueryExpressageTest
[       OK ] LogisticSysTest.QueryExpressageTest (0 ms)
[----------] 11 tests from LogisticSysTest (1 ms total)

[----------] Global test environment tear-down
[==========] 17 tests from 3 test suites ran. (1 ms total)
[  PASSED  ] 17 tests.
```
- 驗收測試輸出（尾巴）：
```
Test 1: [FAILED].
Test 2: [FAILED].
Test 3: [FAILED].
Test 4: [FAILED].
Test 5: [FAILED].
Test 6: [FAILED].
mkdir: cannot create directory ‘./data’: File exists
mkdir: cannot create directory ‘./outputs’: File exists
```

### people_management：單元 2/9、驗收 1/7（partial，11.1 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：gtest（make -f makefile_test test） 7 failed、2 passed（5.5 秒）（整個專案）
  - 1. done（1 次、3 步）實作 include/common.h 與 include/utils.h；檔案 ['include/common.h', 'include/utils.h']
  - 2. skipped（2 次、29 步）實作 include/people_management.h 與 src/utils.cpp；檔案 ['include/people_management.h', 'src/utils.cpp']
  - 3. skipped（2 次、36 步）實作 src/people_management.cpp (核心邏輯)；檔案 ['src/people_management.cpp']
  - 4. skipped（2 次、36 步）實作 src/main.cpp 與 makefile；檔案 ['src/main.cpp', 'makefile']
  - 5. failed（2 次、32 步）修正整體驗證的失敗；檔案 ['include/common.h', 'include/people_management.h', 'include/utils.h', 'makefile', 'src/main.cpp', 'src/people_management.cpp']
- 單元測試輸出（尾巴）：
```
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
make: *** [makefile_test:37: test] Error 1
```
- 驗收測試輸出（尾巴）：
```
=========================== short test summary info ============================
FAILED acceptance_tests/acceptance_testing.py::test_add_school - sqlite3.Oper...
FAILED acceptance_tests/acceptance_testing.py::test_add_person - sqlite3.Oper...
FAILED acceptance_tests/acceptance_testing.py::test_search_person - Assertion...
FAILED acceptance_tests/acceptance_testing.py::test_update_person - assert 4 ...
FAILED acceptance_tests/acceptance_testing.py::test_update_school - assert 4 ...
FAILED acceptance_tests/acceptance_testing.py::test_mentor - sqlite3.Operatio...
6 failed, 1 passed in 0.34s
```

### xlsx2csv：單元 3/8、驗收 4/5（partial，11.8 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：gtest（make -f makefile_test test） 5 failed、3 passed（3.8 秒）（整個專案）
  - 1. done（1 次、2 步）實作基礎類型與工具函式標頭檔；檔案 ['include/types.h', 'include/utils.h']
  - 2. done（1 次、11 步）實作工具函式實作；檔案 ['src/utils.cpp']
  - 3. done（1 次、8 步）實作 Archive 類別標頭檔；檔案 ['include/archive.h']
  - 4. skipped（2 次、36 步）實作 Archive 類別實作；檔案 ['src/archive.cpp']
  - 5. done（1 次、2 步）實作 Worksheet 類別標頭檔；檔案 ['include/worksheet.h']
  - 6. done（2 次、14 步）實作 Workbook 類別標頭檔；檔案 ['include/workbook.h']
  - 7. done（1 次、7 步）實作 Worksheet 類別實作；檔案 ['src/worksheet.cpp']
  - 8. skipped（2 次、33 步）實作 Workbook 類別實作；檔案 ['src/workbook.cpp']
  - 9. skipped（2 次、23 步）實作 Makefile；檔案 ['makefile']
  - 10. done（1 次、3 步）實作 main.cpp；檔案 ['src/main.cpp']
  - 11. failed（2 次、30 步）修正整體驗證的失敗；檔案 ['include/archive.h', 'include/types.h', 'include/utils.h', 'include/workbook.h', 'include/worksheet.h', 'makefile']
- 單元測試輸出（尾巴）：
```
[  FAILED  ] WorkbookTest.GetSharedString
[  FAILED  ] WorkbookTest.WriteToCSV

 5 FAILED TESTS
src/miniz.c:3185:9: note: ‘#pragma message: Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.’
 3185 | #pragma message("Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.")
      |         ^~~~~~~
make: *** [makefile_test:52: test] Error 1
```
- 驗收測試輸出（尾巴）：
```
mkdir: cannot create directory ‘./outputs/test003’: File exists
src/miniz.c:3185:9: note: ‘#pragma message: Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.’
 3185 | #pragma message("Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.")
      |         ^~~~~~~
Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]
diff: ../expected_outputs/test001: No such file or directory
diff: ../expected_outputs/test002: No such file or directory
diff: ../expected_outputs/test003: No such file or directory
```
