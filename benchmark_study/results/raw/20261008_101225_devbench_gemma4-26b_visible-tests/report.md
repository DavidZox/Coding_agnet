# DevBench 實作任務：worker gemma4:26b、規劃 gemma4:26b

- 時間：2026-10-08 11:45；12 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。**官方測試放在工作區、agent 可以跑**（DevBench 基準 agent 的設定）。

- **全部**（12 個 repo）：單元測試 84/116（72.4%）、驗收測試 18/51（35.3%）；每個 repo 通過率的平均：單元 67.7%、驗收 41.2%；依程式碼行數加權：單元 67.4%、驗收 36.7%
- **Python**（7 個 repo）：單元測試 36/57（63.2%）、驗收測試 11/24（45.8%）；每個 repo 通過率的平均：單元 62.0%、驗收 51.4%；依程式碼行數加權：單元 59.0%、驗收 44.8%
- **C++**（5 個 repo）：單元測試 48/59（81.4%）、驗收測試 7/27（25.9%）；每個 repo 通過率的平均：單元 75.8%、驗收 26.9%；依程式碼行數加權：單元 74.6%、驗收 29.8%

| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|
| readtime | python | 0/8 | 0/4 | partial | 2/4 | 11.2 | 110 |
| particle-swarm-optimization | python | 5/5 | 1/1 | done | 5/5 | 1.3 | 24 |
| chakin | python | 1/1 | 1/1 | done | 2/2 | 2.4 | 31 |
| stocktrends | python | 6/7 | 0/2 | partial | 1/5 | 19.6 | 174 |
| geotext | python | 2/4 | 2/5 | partial | 1/5 | 6.0 | 124 |
| hone | python | 1/7 | 1/5 | partial | 1/4 | 7.1 | 164 |
| lice | python | 21/25 | 6/6 | partial | 1/5 | 10.1 | 193 |
| area_calculation | cpp | 3/3 | 0/3 | partial | 3/6 | 2.2 | 103 |
| graph-cpp | cpp | 21/22 | 2/5 | partial | 4/6 | 8.8 | 151 |
| logistic_system | cpp | 17/17 | 1/7 | done | 8/8 | 3.3 | 97 |
| people_management | cpp | 3/9 | 0/7 | partial | 2/6 | 10.0 | 168 |
| xlsx2csv | cpp | 4/8 | 4/5 | partial | 3/8 | 10.4 | 235 |

參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%；GPT-4-Turbo-1106 驗收 6.9%、單元 6.8%；GPT-3.5-Turbo 驗收 4.2%、單元 4.3%；DeepSeek-Coder-33B-Instruct 驗收 4.4%、單元 5.5%；CodeLlama-34B-Instruct 驗收 0.6%、單元 0.5%

## 每個 repo

### readtime：單元 0/8、驗收 0/4（partial，11.2 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 6 failed、6 passed（0.2 秒）（整個專案）
  - 1. done（2 次、22 步）實作 Result 類別與基礎檔案；檔案 ['readtime/result.py', 'readtime/__init__.py', 'readtime/__about__.py']
  - 2. done（2 次、27 步）實作 utils.py 核心邏輯與解析；檔案 ['readtime/utils.py']
  - 3. skipped（2 次、6 步）實作 api.py 外部介面；檔案 ['readtime/api.py']
  - 4. failed（2 次、15 步）修正整體驗證的失敗；檔案 ['readtime/__about__.py', 'readtime/__init__.py', 'readtime/api.py', 'readtime/result.py', 'readtime/utils.py']
- 單元測試輸出（尾巴）：
```
    from readtime.api import of_text
E   ImportError: cannot import name 'of_text' from 'readtime.api' (/tmp/devbench_run_zu2hcg_9/workspace/readtime/api.py)
=========================== short test summary info ============================
ERROR unit_tests/test_check_data.py
ERROR unit_tests/test_custom_wpm.py
ERROR unit_tests/test_transitions.py
!!!!!!!!!!!!!!!!!!! Interrupted: 3 errors during collection !!!!!!!!!!!!!!!!!!!!
3 errors in 0.07s
```
- 驗收測試輸出（尾巴）：
```
    from readtime.api import of_text, of_markdown, of_html
readtime/__init__.py:1: in <module>
    from .api import of_text, of_html, of_markdown
E   ImportError: cannot import name 'of_text' from 'readtime.api' (/tmp/devbench_run_zu2hcg_9/workspace/readtime/api.py)
=========================== short test summary info ============================
ERROR acceptance_tests/test_readtime.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.07s
```

### particle-swarm-optimization：單元 5/5、驗收 1/1（done，1.3 分鐘）
- 整體驗證（agent 自己的）：[PASS] 測試全部通過：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 6 passed（0.1 秒）（整個專案）
  - 1. done（1 次、2 步）建立 pso 套件結構與 __init__.py；檔案 ['pso/__init__.py']
  - 2. done（1 次、5 步）實作 cost_functions.py 中的 sphere 函數；檔案 ['pso/cost_functions.py']
  - 3. done（1 次、5 步）實作 pso_simple.py 中的 Particle 類別；檔案 ['pso/pso_simple.py']
  - 4. done（1 次、4 步）實作 pso_simple.py 中的 minimize 函式；檔案 ['pso/pso_simple.py']
  - 5. done（1 次、2 步）執行最終驗收測試；檔案 []
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

### chakin：單元 1/1、驗收 1/1（done，2.4 分鐘）
- 整體驗證（agent 自己的）：[PASS] 測試全部通過：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 2 passed（0.8 秒）（整個專案）
  - 1. done（1 次、2 步）建立 chakin/__init__.py 並匯出 API；檔案 ['chakin/__init__.py']
  - 2. done（1 次、18 步）實作 chakin/downloader.py 核心功能；檔案 ['chakin/downloader.py']
- 單元測試輸出（尾巴）：
```
.                                                                        [100%]
1 passed in 0.34s
```
- 驗收測試輸出（尾巴）：
```
.                                                                        [100%]
1 passed in 0.33s
```

### stocktrends：單元 6/7、驗收 0/2（partial，19.6 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 6 failed、3 passed（0.4 秒）（整個專案）
  - 1. done（1 次、7 步）建立 stocktrends 套件結構與 Instrument 基底類別；檔案 ['stocktrends/__init__.py', 'stocktrends/indicators.py']
  - 2. skipped（2 次、18 步）實作 Renko 指標類別；檔案 ['stocktrends/indicators.py']
  - 3. skipped（2 次、33 步）實作 LineBreak 指標類別；檔案 ['stocktrends/indicators.py']
  - 4. skipped（2 次、16 步）實作 PnF 指標類別；檔案 ['stocktrends/indicators.py']
  - 5. failed（2 次、36 步）修正整體驗證的失敗；檔案 ['stocktrends/__init__.py', 'stocktrends/indicators.py']
- 單元測試輸出（尾巴）：
```
E         
E         At index 0 diff: 79 != 84
E         Use -v to get more diff

unit_tests/test_renko.py:14: AssertionError
=========================== short test summary info ============================
FAILED unit_tests/test_renko.py::test_Renko_box_periodic_close - assert (79, ...
1 failed, 6 passed in 0.13s
```
- 驗收測試輸出（尾巴）：
```
E        +    and   0     81.25\n1       NaN\n2       NaN\n3       NaN\n4       NaN\n      ...  \n71      NaN\n72      NaN\n73      NaN\n74      NaN\n75      NaN\nName: close, Length: 76, dtype: float64 = <ufunc 'absolute'>((0    225.2\nName: close, dtype: float64 - 0     143.950\n1     142.775\n2     137.925\n3     143.950\n4     118.050\n       ...   \n71    187.950\n72    189.325\n73    204.850\n74    205.200\n75    207.700\nName: close, Length: 76, dtype: float64))
E        +      where <ufunc 'absolute'> = np.abs

acceptance_tests/test_indicators.py:42: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_indicators.py::test_renko - AssertionError: asse...
FAILED acceptance_tests/test_indicators.py::test_linebreak - AssertionError: ...
2 failed in 0.12s
```

### geotext：單元 2/4、驗收 2/5（partial，6.0 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 5 failed、4 passed（0.1 秒）（整個專案）
  - 1. done（1 次、2 步）建立 geotext 套件結構與 __init__.py；檔案 ['geotext/__init__.py']
  - 2. skipped（2 次、10 步）實作資料讀取與索引建立工具函式；檔案 ['geotext/geotext.py']
  - 3. skipped（2 次、12 步）實作 GeoText 類別提取邏輯；檔案 ['geotext/geotext.py']
  - 4. skipped（2 次、34 步）執行驗收測試以確保完整性；檔案 ['geotext/geotext.py']
  - 5. failed（2 次、36 步）修正整體驗證的失敗；檔案 ['geotext/__init__.py', 'geotext/data_file/cities15000.txt', 'geotext/data_file/countryInfo.txt', 'geotext/data_file/nationalities.txt', 'geotext/geotext.py']
- 單元測試輸出（尾巴）：
```
>       self.assertEqual(result, expected)
E       AssertionError: OrderedDict({'RU': 1}) != {'PE': 1, 'IE': 1, 'RU': 2}

unit_tests/test_geotext.py:120: AssertionError
=========================== short test summary info ============================
FAILED unit_tests/test_geotext.py::TestGeotext::test_cities - AssertionError:...
FAILED unit_tests/test_geotext.py::TestGeotext::test_country_mentions - Asser...
2 failed, 2 passed in 0.01s
```
- 驗收測試輸出（尾巴）：
```
E       AssertionError: OrderedDict() != OrderedDict({'US': 2, 'CN': 1})

acceptance_tests/test_acceptance.py:23: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_city_extraction
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_filter
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_mentions_count
3 failed, 2 passed in 0.01s
```

### hone：單元 1/7、驗收 1/5（partial，7.1 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 10 failed、2 passed（0.1 秒）（整個專案）
  - 1. skipped（2 次、33 步）實作 CSVUtils 與 JSONUtils 工具類別；檔案 ['hone/utils/csv_utils.py', 'hone/utils/json_utils.py', 'hone/utils/__init__.py']
  - 2. skipped（2 次、29 步）實作 Hone 核心轉換邏輯；檔案 ['hone/hone.py']
  - 3. done（2 次、26 步）建立套件入口與 CLI 介面；檔案 ['hone/__init__.py', 'hone/__main__.py']
  - 4. failed（2 次、23 步）修正整體驗證的失敗；檔案 ['hone/__init__.py', 'hone/__main__.py', 'hone/hone.py', 'hone/utils/__init__.py', 'hone/utils/csv_utils.py', 'hone/utils/json_utils.py']
- 單元測試輸出（尾巴）：
```
=========================== short test summary info ============================
FAILED unit_tests/test_csv_utils.py::AcceptanceTestCSVtoJSON::test_full_conversion_comma_test
FAILED unit_tests/test_csv_utils.py::AcceptanceTestCSVtoJSON::test_full_conversion_quotes_test
FAILED unit_tests/test_hone.py::TestHone::test_get_schema - AssertionError: {...
FAILED unit_tests/test_hone.py::TestHone::test_nest_comma_csv - AssertionErro...
FAILED unit_tests/test_hone.py::TestHone::test_nest_quotes_csv - AssertionErr...
FAILED unit_tests/test_hone.py::TestHone::test_nest_small_csv - AssertionErro...
6 failed, 1 passed in 0.02s
```
- 驗收測試輸出（尾巴）：
```
E   
E   Diff is 1284 characters long. Set self.maxDiff to None to see it.
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_comma_handling
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_data_integrity
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_nested_json_generation
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_quoted_field_handling
4 failed, 1 passed in 0.01s
```

### lice：單元 21/25、驗收 6/6（partial，10.1 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：pytest（~/Coding_agent_harness/evals/devbench/.venv/bin/python） 14 failed、17 passed（0.2 秒）（整個專案）
  - 1. done（1 次、2 步）建立 lice 套件結構與 __init__.py；檔案 ['unit_tests/__init__.py']
  - 2. skipped（2 次、36 步）實作 core.py 基礎工具函式；檔案 ['lice/core.py']
  - 3. skipped（2 次、27 步）實作模板讀取與變數替換邏輯；檔案 ['lice/core.py']
  - 4. skipped（2 次、24 步）實作授權格式化與 CLI main 函式；檔案 ['lice/core.py']
  - 5. failed（2 次、35 步）修正整體驗證的失敗；檔案 ['lice/__init__.py', 'lice/core.py', 'templates/template-LICENSES.AGPL3.txt', 'templates/template-LICENSES.APACHE.txt', 'templates/template-LICENSES.BSD2.txt', 'templates/template-LICENSES.BSD3.txt']
- 單元測試輸出（尾巴）：
```
----------------------------- Captured stderr call -----------------------------
Error: [Errno 2] No such file or directory: '/tmp/devbench_run_30xc7_ig/workspace/nonexistent_path'
=========================== short test summary info ============================
FAILED unit_tests/test_lice.py::TestFormatLicense::test_format_license_c_language
FAILED unit_tests/test_lice.py::TestMainFunction::test_list_template_vars - A...
FAILED unit_tests/test_lice.py::TestMainFunction::test_output_to_file - Syste...
FAILED unit_tests/test_lice.py::TestMainFunction::test_template_path_not_exist
4 failed, 21 passed in 0.04s
```
- 驗收測試輸出（尾巴）：
```
......                                                                   [100%]
6 passed in 0.11s
```

### area_calculation：單元 3/3、驗收 0/3（partial，2.2 分鐘）
- 整體驗證（agent 自己的）：[PASS] 測試全部通過：gtest（make -f makefile_test test） 3 passed（1.2 秒）（整個專案）
  - 1. skipped（2 次、10 步）實作 Shape 基礎類別；檔案 ['include/Shape.h', 'src/Shape.cpp']
  - 2. skipped（2 次、9 步）實作 Circle 衍生類別；檔案 ['include/Circle.hpp']
  - 3. done（2 次、15 步）實作 Rectangle 衍生類別；檔案 ['include/Rectangle.h', 'src/Rectangle.cpp']
  - 4. done（1 次、3 步）實作 Square 衍生類別；檔案 ['include/Square.hpp']
  - 5. skipped（2 次、36 步）實作 main.cpp 檔案讀寫邏輯；檔案 ['src/main.cpp']
  - 6. done（1 次、4 步）建立 Makefile；檔案 ['makefile']
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
g++ -std=c++17 -Wall -Iinclude -c src/main.cpp -o src/main.o
g++ -std=c++17 -Wall -Iinclude -c src/Rectangle.cpp -o src/Rectangle.o
g++ -std=c++17 -Wall -Iinclude -c src/Shape.cpp -o src/Shape.o
g++ -std=c++17 -Wall -Iinclude -o area_calculation src/main.o src/Rectangle.o src/Shape.o
Processed input/1.txt and saved the output to outputs/1.txt
Processed input/2.txt and saved the output to outputs/2.txt
Processed input/3.txt and saved the output to outputs/3.txt
Mismatch found in file 1.txt
```

### graph-cpp：單元 21/22、驗收 2/5（partial，8.8 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 找不到測試路徑：&&（相對於 /tmp/devbench_run_bw8rb85d/workspace）。測試檔還沒建立的話，先建立再跑；看有哪些測試用 repo_map。
  - 1. done（1 次、15 步）實作 Queue 類別；檔案 ['include/queue.hpp']
  - 2. done（1 次、4 步）實作 Stack 類別；檔案 ['include/stack.hpp']
  - 3. done（1 次、7 步）實作 AdjacencyMatrixGraph 類別；檔案 ['include/am_graph.hpp']
  - 4. skipped（2 次、36 步）實作 AdjacencyListGraph 類別；檔案 ['include/al_graph.hpp']
  - 5. skipped（2 次、30 步）實作 main 函式與 Makefile；檔案 ['src/main.cpp', 'makefile']
  - 6. done（1 次、18 步）修正整體驗證的失敗；檔案 ['include/al_graph.hpp', 'include/am_graph.hpp', 'include/queue.hpp', 'include/stack.hpp', 'makefile', 'src/main.cpp']
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
g++ -std=c++17 -Wall -Wextra -Iinclude -c src/main.cpp -o src/main.o
g++ -std=c++17 -Wall -Wextra -Iinclude -o graph src/main.o
Test passed: Test Bad Input File passed
Test passed: Test Bad Input File passed
Test failed: Output for 'directed_graph.txt' doesn't match expected output
Test failed: Output for 'sample.txt' doesn't match expected output
Test failed: Output for 'undirected_graph.txt' doesn't match expected output
Testing completed. Check the test_outputs directory for results.
```

### logistic_system：單元 17/17、驗收 1/7（done，3.3 分鐘）
- 整體驗證（agent 自己的）：[PASS] 測試全部通過：gtest（make -f makefile_test test） 17 passed（1.7 秒）（整個專案）
  - 1. done（2 次、11 步）實作 AccountNode 類別標頭檔；檔案 ['include/account.h']
  - 2. done（1 次、5 步）實作 AccountNode 類別實作檔；檔案 ['src/account.cpp', 'include/account.h']
  - 3. done（2 次、20 步）實作 ExpressageNode 類別標頭檔；檔案 ['include/expressage.h']
  - 4. done（1 次、3 步）實作 ExpressageNode 類別實作檔；檔案 ['src/expressage.cpp', 'include/expressage.h']
  - 5. done（1 次、2 步）實作 LogisticSys 類別標頭檔；檔案 ['include/logistics.h']
  - 6. done（1 次、16 步）實作 LogisticSys 核心邏輯；檔案 ['src/logistics.cpp', 'include/logistics.h', 'include/account.h', 'include/expressage.h']
  - 7. done（1 次、2 步）實作 main 進入點與 CLI 介面；檔案 ['src/main.cpp', 'include/logistics.h']
  - 8. done（1 次、11 步）建立 Makefile；檔案 ['makefile']
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

### people_management：單元 3/9、驗收 0/7（partial，10.0 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：gtest（make -f makefile_test test） 7 failed、2 passed（4.9 秒）（整個專案）
  - 1. done（1 次、3 步）實作 include/common.h 與 include/utils.h；檔案 ['include/common.h', 'include/utils.h']
  - 2. skipped（2 次、25 步）實作 include/people_management.h 與 src/utils.cpp；檔案 ['include/people_management.h', 'src/utils.cpp']
  - 3. skipped（2 次、36 步）實作 src/people_management.cpp；檔案 ['src/people_management.cpp']
  - 4. skipped（2 次、22 步）實作 src/main.cpp；檔案 ['src/main.cpp']
  - 5. done（1 次、9 步）實作 Makefile；檔案 ['makefile']
  - 6. failed（2 次、25 步）修正整體驗證的失敗；檔案 ['include/common.h', 'include/people_management.h', 'include/utils.h', 'makefile', 'src/main.cpp', 'src/people_management.cpp']
- 單元測試輸出（尾巴）：
```
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
rm: cannot remove 'database.sqlite3': No such file or directory
Mentor lookup error: near ";": syntax error
rm: cannot remove 'database.sqlite3': No such file or directory
make: *** [makefile_test:37: test] Error 1
```
- 驗收測試輸出（尾巴）：
```
FAILED acceptance_tests/acceptance_testing.py::test_add_school - sqlite3.Oper...
FAILED acceptance_tests/acceptance_testing.py::test_add_person - sqlite3.Oper...
FAILED acceptance_tests/acceptance_testing.py::test_search_person - Assertion...
FAILED acceptance_tests/acceptance_testing.py::test_search_school - Assertion...
FAILED acceptance_tests/acceptance_testing.py::test_update_person - assert 4 ...
FAILED acceptance_tests/acceptance_testing.py::test_update_school - assert 4 ...
FAILED acceptance_tests/acceptance_testing.py::test_mentor - sqlite3.Operatio...
7 failed in 3.23s
```

### xlsx2csv：單元 4/8、驗收 4/5（partial，10.4 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 測試失敗：gtest（make -f makefile_test test） 5 failed、3 passed（2.8 秒）（整個專案）
  - 1. done（1 次、14 步）定義基礎類型與工具函式標頭檔；檔案 ['include/types.h', 'include/utils.h']
  - 2. skipped（2 次、16 步）實作工具函式；檔案 ['src/utils.cpp']
  - 3. skipped（2 次、32 步）實作 Archive 類別；檔案 ['include/archive.h', 'src/archive.cpp']
  - 4. done（2 次、35 步）實作 Worksheet 類別；檔案 ['include/worksheet.h', 'src/worksheet.cpp']
  - 5. skipped（2 次、21 步）實作 Workbook 類別；檔案 ['include/workbook.h', 'src/workbook.cpp']
  - 6. done（1 次、4 步）實作 main 進入點與 CLI；檔案 ['src/main.cpp']
  - 7. skipped（2 次、18 步）建立 Makefile；檔案 ['makefile']
  - 8. failed（2 次、31 步）修正整體驗證的失敗；檔案 ['include/archive.h', 'include/types.h', 'include/utils.h', 'include/workbook.h', 'include/worksheet.h', 'makefile']
- 單元測試輸出（尾巴）：
```
[  FAILED  ] WorkbookTest.GetSharedString
[  FAILED  ] WorkbookTest.WriteToCSV

 4 FAILED TESTS
src/miniz.c:3185:9: note: ‘#pragma message: Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.’
 3185 | #pragma message("Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.")
      |         ^~~~~~~
make: *** [makefile_test:52: test] Error 1
```
- 驗收測試輸出（尾巴）：
```
      |                     ^~~
src/miniz.c:3185:9: note: ‘#pragma message: Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.’
 3185 | #pragma message("Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.")
      |         ^~~~~~~
Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]
diff: ../expected_outputs/test001: No such file or directory
diff: ../expected_outputs/test002: No such file or directory
diff: ../expected_outputs/test003: No such file or directory
```
