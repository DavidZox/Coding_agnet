# DevBench 實作任務：worker gemma4:26b、規劃 gemma4:26b

- 時間：2026-10-08 15:43；12 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。agent 看不到官方測試。

- **全部**（12 個 repo）：單元測試 28/116（24.1%）、驗收測試 14/51（27.5%）；每個 repo 通過率的平均：單元 30.8%、驗收 32.1%；依程式碼行數加權：單元 24.7%、驗收 24.9%
- **Python**（7 個 repo）：單元測試 11/57（19.3%）、驗收測試 5/24（20.8%）；每個 repo 通過率的平均：單元 27.6%、驗收 25.2%；依程式碼行數加權：單元 23.1%、驗收 20.5%
- **C++**（5 個 repo）：單元測試 17/59（28.8%）、驗收測試 9/27（33.3%）；每個 repo 通過率的平均：單元 35.4%、驗收 41.7%；依程式碼行數加權：單元 26.1%、驗收 28.7%

| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|
| readtime | python | 2/8 | 0/4 | done | 4/4 | 1.7 | 66 |
| particle-swarm-optimization | python | 5/5 | 1/1 | done | 3/3 | 0.5 | 22 |
| chakin | python | 0/1 | 0/1 | done | 5/5 | 13.8 | 46 |
| stocktrends | python | 1/7 | 0/2 | done | 4/4 | 1.5 | 32 |
| geotext | python | 1/4 | 1/5 | done | 3/3 | 1.8 | 41 |
| hone | python | 2/7 | 2/5 | done | 3/3 | 0.7 | 26 |
| lice | python | 0/25 | 1/6 | done | 5/5 | 1.4 | 39 |
| area_calculation | cpp | 3/3 | 3/3 | done | 6/6 | 1.5 | 66 |
| graph-cpp | cpp | 12/22 | 0/5 | done | 5/5 | 10.4 | 82 |
| logistic_system | cpp | 0/17 | 1/7 | partial | 6/7 | 3.2 | 73 |
| people_management | cpp | 2/9 | 1/7 | partial | 5/6 | 3.1 | 96 |
| xlsx2csv | cpp | 0/8 | 4/5 | partial | 9/10 | 4.4 | 127 |

參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%；GPT-4-Turbo-1106 驗收 6.9%、單元 6.8%；GPT-3.5-Turbo 驗收 4.2%、單元 4.3%；DeepSeek-Coder-33B-Instruct 驗收 4.4%、單元 5.5%；CodeLlama-34B-Instruct 驗收 0.6%、單元 0.5%

## 每個 repo

### readtime：單元 2/8、驗收 0/4（done，1.7 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.0 秒，在 /tmp/devbench_run_cuj6u6zx/workspace）：python3 examples/demo.py
  - 1. done（2 次、21 步）建立 readtime 套件基礎結構與 Result 類別；檔案 ['readtime/__init__.py', 'readtime/__about__.py', 'readtime/result.py']
  - 2. done（1 次、8 步）實作 readtime/utils.py 解析與計算邏輯；檔案 ['readtime/utils.py']
  - 3. done（1 次、6 步）實作 readtime/api.py 外部介面；檔案 ['readtime/api.py']
  - 4. done（1 次、11 步）修正整體驗證的失敗；檔案 ['readtime/__about__.py', 'readtime/__init__.py', 'readtime/api.py', 'readtime/result.py', 'readtime/utils.py']
- 單元測試輸出（尾巴）：
```
=========================== short test summary info ============================
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_empty - A...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_null - At...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm - Attribu...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_html - At...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_markdown
FAILED unit_tests/test_transitions.py::BaseTestCase::test_transitions - Asser...
6 failed, 2 passed in 0.04s
```
- 驗收測試輸出（尾巴）：
```

acceptance_tests/test_readtime.py:12: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_can_add - Assert...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_html - Assertion...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_markdown - Asser...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_plain_text - Ass...
4 failed in 0.04s
```

### particle-swarm-optimization：單元 5/5、驗收 1/1（done，0.5 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.0 秒，在 /tmp/devbench_run_9bnfiglu/workspace）：sh ./examples/demo.sh
  - 1. done（1 次、3 步）建立 pso 套件結構與 cost_functions.py；檔案 ['pso/__init__.py', 'pso/cost_functions.py']
  - 2. done（1 次、3 步）實作 pso_simple.py 中的 Particle 類別與 minimize 函式；檔案 ['pso/pso_simple.py']
  - 3. done（1 次、8 步）修正整體驗證的失敗；檔案 ['pso/__init__.py', 'pso/cost_functions.py', 'pso/pso_simple.py']
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

### chakin：單元 0/1、驗收 0/1（done，13.8 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.4 秒，在 /tmp/devbench_run_xx_473mg/workspace）：python3 -c "import chakin; print(chakin.search('Arabic')); chakin.download(name='fastText(ar)', save_dir='./')"
  - 1. done（1 次、9 步）建立 chakin 套件基礎結構與 datasets.csv；檔案 ['chakin/__init__.py', 'chakin/datasets.csv']
  - 2. done（1 次、12 步）實作 chakin/downloader.py 核心功能；檔案 ['chakin/downloader.py']
  - 3. done（1 次、3 步）實作 chakin/__init__.py API 導出；檔案 ['chakin/__init__.py']
  - 4. done（1 次、3 步）實作 setup.py 與完整環境驗證；檔案 ['setup.py']
  - 5. done（1 次、4 步）修正整體驗證的失敗；檔案 ['chakin/__init__.py', 'chakin/datasets.csv', 'chakin/downloader.py', 'setup.py', 'verify_downloader.py']
- 單元測試輸出（尾巴）：
```
                "%s does not have the attribute %r" % (target, name)
            )
E           AttributeError: <module 'chakin.downloader' from '/tmp/devbench_run_xx_473mg/workspace/chakin/downloader.py'> does not have the attribute 'urlretrieve'

/usr/lib/python3.12/unittest/mock.py:1431: AttributeError
=========================== short test summary info ============================
FAILED unit_tests/test_downloader.py::TestDownloader::test_download_by_name
1 failed in 0.20s
```
- 驗收測試輸出（尾巴）：
```
                "%s does not have the attribute %r" % (target, name)
            )
E           AttributeError: <module 'chakin.downloader' from '/tmp/devbench_run_xx_473mg/workspace/chakin/downloader.py'> does not have the attribute 'urlretrieve'

/usr/lib/python3.12/unittest/mock.py:1431: AttributeError
=========================== short test summary info ============================
FAILED acceptance_tests/acceptance_test.py::TestDownloader::test_download_acceptance
1 failed in 0.20s
```

### stocktrends：單元 1/7、驗收 0/2（done，1.5 分鐘）
- 整體驗證（agent 自己的）：[PASS] 檢查 2 個檔案（這個 coding job 改過的檔案；語法、未定義名稱、專案內匯入）：沒有發現問題
  - 1. done（1 次、3 步）建立 stocktrends 套件結構與基礎 Instrument 類別；檔案 ['stocktrends/__init__.py', 'stocktrends/indicators.py']
  - 2. done（1 次、8 步）實作 Renko 指標邏輯；檔案 ['stocktrends/indicators.py']
  - 3. done（1 次、3 步）實作 LineBreak 指標邏輯；檔案 ['stocktrends/indicators.py']
  - 4. done（1 次、7 步）實作 PnF 指標邏輯；檔案 ['stocktrends/indicators.py']
- 單元測試輸出（尾巴）：
```
=========================== short test summary info ============================
FAILED unit_tests/test_pnf.py::test_get_state - AttributeError: 'PnF' object ...
FAILED unit_tests/test_pnf.py::test_roundit - TypeError: PnF.roundit() missin...
FAILED unit_tests/test_pnf.py::test_get_bar_ohlc_data_close - assert (47, 4) ...
FAILED unit_tests/test_pnf.py::test_get_bar_ohlc_data_hl - assert (47, 4) == ...
FAILED unit_tests/test_pnf.py::test_get_ohlc_data_close - assert (47, 4) == (...
FAILED unit_tests/test_renko.py::test_Renko_box_periodic_close - AttributeErr...
6 failed, 1 passed in 0.18s
```
- 驗收測試輸出（尾巴）：
```
                             ^^^^^^^^^^^^
E       TypeError: 'NoneType' object is not subscriptable

acceptance_tests/test_indicators.py:42: TypeError
=========================== short test summary info ============================
FAILED acceptance_tests/test_indicators.py::test_renko - AssertionError: asse...
FAILED acceptance_tests/test_indicators.py::test_linebreak - TypeError: 'None...
2 failed in 0.16s
```

### geotext：單元 1/4、驗收 1/5（done，1.8 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.0 秒，在 /tmp/devbench_run_qudasarj/workspace）：python3 examples/demo.py
  - 1. done（1 次、6 步）建立套件結構與 __init__.py；檔案 ['geotext/__init__.py', 'examples/demo.py', 'examples/demo.sh']
  - 2. done（1 次、4 步）實作 geotext.py 中的工具函式與索引建立；檔案 ['geotext/geotext.py']
  - 3. done（1 次、18 步）實作 GeoText 核心類別；檔案 ['geotext/geotext.py']
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

acceptance_tests/test_acceptance.py:38: AttributeError
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_city_extraction
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_filter
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_mentions_count
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_data_loading
4 failed, 1 passed in 0.01s
```

### hone：單元 2/7、驗收 2/5（done，0.7 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.0 秒，在 /tmp/devbench_run_oh4fwmtl/workspace）：python3 -m hone data_file/small_cats_dataset/dataset.csv /tmp/out.json
  - 1. done（1 次、8 步）實作 CSV 與 JSON 工具模組；檔案 ['hone/utils/csv_utils.py', 'hone/utils/json_utils.py', 'hone/utils/__init__.py', 'hone/utils/test_utils.py']
  - 2. done（1 次、4 步）實作 Hone 核心轉換類別；檔案 ['hone/hone.py']
  - 3. done（1 次、4 步）建立套件入口與 CLI 介面；檔案 ['hone/__init__.py', 'hone/__main__.py']
- 單元測試輸出（尾巴）：
```
unit_tests/test_hone.py:19: AttributeError
=========================== short test summary info ============================
FAILED unit_tests/test_csv_utils.py::AcceptanceTestCSVtoJSON::test_full_conversion_quotes_test
FAILED unit_tests/test_hone.py::TestHone::test_get_schema - AttributeError: m...
FAILED unit_tests/test_hone.py::TestHone::test_nest_comma_csv - AttributeErro...
FAILED unit_tests/test_hone.py::TestHone::test_nest_quotes_csv - AttributeErr...
FAILED unit_tests/test_hone.py::TestHone::test_nest_small_csv - AttributeErro...
5 failed, 2 passed in 0.01s
```
- 驗收測試輸出（尾巴）：
```
E   {'some \'quoted"\' field"': 'no quotes', 'a[153 chars]mmy'}
E   
E   Diff is 1284 characters long. Set self.maxDiff to None to see it.
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_data_integrity
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_nested_json_generation
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_quoted_field_handling
3 failed, 2 passed in 0.01s
```

### lice：單元 0/25、驗收 1/6（done，1.4 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.0 秒；測試：4 passed，在 /tmp/devbench_run_y3gp7tvu/workspace）：python3 -m unittest discover -s ./lice/tests -p 'test_*.py'
  - 1. done（1 次、5 步）建立 lice 套件結構與 __init__.py；檔案 ['lice/__init__.py']
  - 2. done（1 次、4 步）實作 core.py 中的 Context 與基礎工具函式；檔案 ['lice/core.py']
  - 3. done（1 次、3 步）實作模板讀取與變數替換邏輯；檔案 ['lice/core.py']
  - 4. done（1 次、4 步）實作 core.py 的 CLI 介面與 main 函式；檔案 ['lice/core.py']
  - 5. done（1 次、12 步）修正整體驗證的失敗；檔案 ['lice/__init__.py', 'lice/core.py']
- 單元測試輸出（尾巴）：
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
unit_tests/test_lice.py:9: in <module>
    from lice.core import (
E   ImportError: cannot import name 'LICENSES' from 'lice.core' (/tmp/devbench_run_y3gp7tvu/workspace/lice/core.py)
=========================== short test summary info ============================
ERROR unit_tests/test_lice.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.05s
```
- 驗收測試輸出（尾巴）：
```
acceptance_tests/test_acceptance.py:21: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::test_default_license_generation
FAILED acceptance_tests/test_acceptance.py::test_license_with_organization - ...
FAILED acceptance_tests/test_acceptance.py::test_license_with_year - Assertio...
FAILED acceptance_tests/test_acceptance.py::test_license_with_project - Asser...
FAILED acceptance_tests/test_acceptance.py::test_license_with_output_file - A...
5 failed, 1 passed in 0.12s
```

### area_calculation：單元 3/3、驗收 3/3（done，1.5 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.0 秒，在 /tmp/devbench_run_jket1udj/workspace）：make && ./area_calculation inputs/1.txt /tmp/out.txt && diff /tmp/out.txt expected_outputs/1.txt
  - 1. done（1 次、3 步）實作 Shape 基底類別；檔案 ['include/Shape.h', 'src/Shape.cpp']
  - 2. done（1 次、4 步）實作 Circle 類別；檔案 ['include/Circle.hpp']
  - 3. done（1 次、5 步）實作 Rectangle 類別；檔案 ['include/Rectangle.h', 'src/Rectangle.cpp']
  - 4. done（1 次、4 步）實作 Square 類別；檔案 ['include/Square.hpp']
  - 5. done（2 次、27 步）實作 main.cpp 檔案處理邏輯；檔案 ['src/main.cpp']
  - 6. done（1 次、5 步）建立 Makefile；檔案 ['makefile']
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
g++ -std=c++17 -Wall -Wextra -Iinclude -c src/Rectangle.cpp -o src/Rectangle.o
g++ -std=c++17 -Wall -Wextra -Iinclude -o area_calculation src/main.o src/Shape.o src/Rectangle.o
Processed input/1.txt and saved the output to outputs/1.txt
Processed input/2.txt and saved the output to outputs/2.txt
Processed input/3.txt and saved the output to outputs/3.txt
File 1.txt matches
File 2.txt matches
File 3.txt matches
```

### graph-cpp：單元 12/22、驗收 0/5（done，10.4 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.3 秒，在 /tmp/devbench_run_6jarf2o1/workspace）：make && ./graph file inputs/sample.txt /tmp/sample_out.txt
  - 1. done（1 次、4 步）實作 Queue 與 Stack 類別；檔案 ['include/queue.hpp', 'include/stack.hpp']
  - 2. done（1 次、3 步）實作 Adjacency Matrix Graph 類別；檔案 ['include/am_graph.hpp']
  - 3. done（2 次、27 步）實作 Adjacency List Graph 類別；檔案 ['include/al_graph.hpp']
  - 4. done（1 次、10 步）實作 main.cpp 與 CLI 邏輯；檔案 ['src/main.cpp']
  - 5. done（1 次、4 步）撰寫 Makefile；檔案 ['makefile']
- 單元測試輸出（尾巴）：
```
[  FAILED  ] MatrixGraphTest.LocateVexTest
[  FAILED  ] QueueTest.FrontThrowsWhenEmpty
[  FAILED  ] QueueTest.PopThrowsWhenEmpty
[  FAILED  ] StackTest.TopThrowsWhenEmpty
[  FAILED  ] StackTest.PopThrowsWhenEmpty

10 FAILED TESTS
make: *** [makefile_test:38: test] Error 1
```
- 驗收測試輸出（尾巴）：
```
rm -rf obj graph
mkdir -p obj
g++ -std=c++17 -Wall -Wextra -Iinclude -c src/main.cpp -o obj/main.o
g++ -std=c++17 -Wall -Wextra -Iinclude -o graph obj/main.o
Test failed: Output for 'directed_graph.txt' doesn't match expected output
Test failed: Output for 'sample.txt' doesn't match expected output
Test failed: Output for 'undirected_graph.txt' doesn't match expected output
Testing completed. Check the test_outputs directory for results.
```

### logistic_system：單元 0/17、驗收 1/7（partial，3.2 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 指令失敗（exit 2，0.0 秒）：make && ./<TARGET_NAME>
  - 1. done（1 次、4 步）實作 AccountNode 標頭檔與實作；檔案 ['include/account.h', 'src/account.cpp']
  - 2. done（1 次、4 步）實作 ExpressageNode 標頭檔與實作；檔案 ['include/expressage.h', 'src/expressage.cpp']
  - 3. done（1 次、2 步）實作 LogisticSys 標頭檔；檔案 ['include/logistics.h']
  - 4. done（1 次、9 步）實作 LogisticSys 核心邏輯；檔案 ['src/logistics.cpp']
  - 5. done（1 次、11 步）實作 main.cpp 與 CLI 互動邏輯；檔案 ['src/main.cpp']
  - 6. done（1 次、4 步）建立 makefile；檔案 ['makefile']
  - 7. failed（2 次、20 步）修正整體驗證的失敗；檔案 ['include/account.h', 'include/expressage.h', 'include/logistics.h', 'makefile', 'src/account.cpp', 'src/expressage.cpp']
- 單元測試輸出（尾巴）：
```
      |   ^~~~~~~~~~~~~~~~~~~
/home/amr-base/.local/include/gtest/gtest.h:1869:3: note: in expansion of macro ‘EXPECT_PRED_FORMAT2’
 1869 |   EXPECT_PRED_FORMAT2(::testing::internal::EqHelper::Compare, val1, val2)
      |   ^~~~~~~~~~~~~~~~~~~
unit_tests/test_account.cpp:23:5: note: in expansion of macro ‘EXPECT_EQ’
   23 |     EXPECT_EQ(account.type, authority::user);
      |     ^~~~~~~~~
make: *** [<builtin>: unit_tests/test_account.o] Error 1
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

### people_management：單元 2/9、驗收 1/7（partial，3.1 分鐘）
- 整體驗證（agent 自己的）：[PASS] 指令完成（exit 0，0.0 秒，在 /tmp/devbench_run_b9gfmsww/workspace）：make
  - 1. skipped（2 次、24 步）實作 include/common.h 與 include/utils.h；檔案 ['include/common.h', 'include/utils.h']
  - 2. done（1 次、7 步）實作 src/utils.cpp；檔案 ['src/utils.cpp']
  - 3. done（1 次、2 步）實作 include/people_management.h；檔案 ['include/people_management.h']
  - 4. done（1 次、12 步）實作 src/people_management.cpp；檔案 ['src/people_management.cpp']
  - 5. done（1 次、11 步）實作 src/main.cpp；檔案 ['src/main.cpp']
  - 6. done（1 次、11 步）實作 makefile；檔案 ['makefile']
- 單元測試輸出（尾巴）：
```
SQL error: no such table: person
rm: cannot remove 'database.sqlite3': No such file or directory
SQL error in sql/people.sql: table people already exists
SQL error in sql/school.sql: table school already exists
SQL error in sql/mentorship.sql: table mentorship already exists
SQL error: near ";": syntax error
rm: cannot remove 'database.sqlite3': No such file or directory
make: *** [makefile_test:37: test] Error 1
```
- 驗收測試輸出（尾巴）：
```
=========================== short test summary info ============================
FAILED acceptance_tests/acceptance_testing.py::test_add_school - sqlite3.Oper...
FAILED acceptance_tests/acceptance_testing.py::test_add_person - sqlite3.Oper...
FAILED acceptance_tests/acceptance_testing.py::test_search_person - assert 5 ...
FAILED acceptance_tests/acceptance_testing.py::test_update_person - assert 5 ...
FAILED acceptance_tests/acceptance_testing.py::test_update_school - assert 4 ...
FAILED acceptance_tests/acceptance_testing.py::test_mentor - sqlite3.Operatio...
6 failed, 1 passed in 0.38s
```

### xlsx2csv：單元 0/8、驗收 4/5（partial，4.4 分鐘）
- 整體驗證（agent 自己的）：[PASS] 靜態檢查與建置都通過（建置：make -B）
  - 1. done（1 次、3 步）實作基礎類型與工具函式標頭檔；檔案 ['include/types.h', 'include/utils.h']
  - 2. done（1 次、3 步）實作工具函式實作；檔案 ['src/utils.cpp']
  - 3. done（1 次、2 步）實作 Archive 類別標頭檔；檔案 ['include/archive.h']
  - 4. done（2 次、28 步）實作 Archive 類別實作；檔案 ['src/archive.cpp']
  - 5. done（1 次、3 步）實作 Worksheet 類別標頭檔；檔案 ['include/worksheet.h']
  - 6. done（1 次、4 步）實作 Workbook 類別標頭檔；檔案 ['include/workbook.h']
  - 7. done（1 次、4 步）實作 Worksheet 類別實作；檔案 ['src/worksheet.cpp']
  - 8. done（1 次、7 步）實作 Workbook 類別實作；檔案 ['src/workbook.cpp']
  - 9. skipped（2 次、31 步）實作 Makefile；檔案 ['makefile']
  - 10. done（1 次、5 步）實作 main.cpp；檔案 ['src/main.cpp']
- 單元測試輸出（尾巴）：
```
      |         ^~~~~~~
unit_tests/test_utils.cpp:5:17: error: ‘my_xlsx’ has not been declared
    5 | using namespace my_xlsx::xlsx_reader;
      |                 ^~~~~~~
unit_tests/test_utils.cpp:5:26: error: ‘xlsx_reader’ is not a namespace-name
    5 | using namespace my_xlsx::xlsx_reader;
      |                          ^~~~~~~~~~~
make: *** [<builtin>: unit_tests/test_utils.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
      | ^~~~~~~~~
src/miniz.c:3185:9: note: ‘#pragma message: Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.’
 3185 | #pragma message("Using fopen, ftello, fseeko, stat() etc. path for file I/O - this path may not support large files.")
      |         ^~~~~~~
Error: Please check the usage: ./xlsx2csv [xlsx filename] [output file path]
diff: ../expected_outputs/test001: No such file or directory
diff: ../expected_outputs/test002: No such file or directory
diff: ../expected_outputs/test003: No such file or directory
```
