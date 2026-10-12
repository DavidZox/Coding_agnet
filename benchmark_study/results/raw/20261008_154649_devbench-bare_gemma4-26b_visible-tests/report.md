# DevBench 實作任務：不用 harness 的對照組（gemma4:26b，一個檔案呼叫一次模型，沒有工具與測試回饋）；官方測試的內容放在提示裡

- 時間：2026-10-08 15:50；12 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。**官方測試的內容放在提示裡（看得到、不能執行）**。

- **全部**（12 個 repo）：單元測試 43/116（37.1%）、驗收測試 16/51（31.4%）；每個 repo 通過率的平均：單元 32.5%、驗收 31.2%；依程式碼行數加權：單元 26.2%、驗收 32.8%
- **Python**（7 個 repo）：單元測試 27/57（47.4%）、驗收測試 10/24（41.7%）；每個 repo 通過率的平均：單元 30.5%、驗收 37.1%；依程式碼行數加權：單元 26.5%、驗收 35.3%
- **C++**（5 個 repo）：單元測試 16/59（27.1%）、驗收測試 6/27（22.2%）；每個 repo 通過率的平均：單元 35.3%、驗收 22.9%；依程式碼行數加權：單元 26.0%、驗收 30.6%

| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|
| readtime | python | 3/8 | 0/4 | bare | 0/0 | 0.3 | 4 |
| particle-swarm-optimization | python | 5/5 | 1/1 | bare | 0/0 | 0.1 | 3 |
| chakin | python | 0/1 | 0/1 | bare | 0/0 | 0.1 | 2 |
| stocktrends | python | 0/7 | 0/2 | bare | 0/0 | 0.6 | 2 |
| geotext | python | 0/4 | 1/5 | bare | 0/0 | 0.2 | 2 |
| hone | python | 0/7 | 2/5 | bare | 0/0 | 0.2 | 5 |
| lice | python | 19/25 | 6/6 | bare | 0/0 | 0.1 | 2 |
| area_calculation | cpp | 3/3 | 0/3 | bare | 0/0 | 0.2 | 9 |
| graph-cpp | cpp | 0/22 | 5/5 | bare | 0/0 | 0.3 | 6 |
| logistic_system | cpp | 13/17 | 1/7 | bare | 0/0 | 0.6 | 9 |
| people_management | cpp | 0/9 | 0/7 | bare | 0/0 | 0.4 | 8 |
| xlsx2csv | cpp | 0/8 | 0/5 | bare | 0/0 | 0.6 | 12 |

參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%；GPT-4-Turbo-1106 驗收 6.9%、單元 6.8%；GPT-3.5-Turbo 驗收 4.2%、單元 4.3%；DeepSeek-Coder-33B-Instruct 驗收 4.4%、單元 5.5%；CodeLlama-34B-Instruct 驗收 0.6%、單元 0.5%

## 每個 repo

### readtime：單元 3/8、驗收 0/4（bare，0.3 分鐘）
- 單元測試輸出（尾巴）：
```
readtime/utils.py:11: AttributeError
=========================== short test summary info ============================
FAILED unit_tests/test_check_data.py::BaseTestCase::test_invalid_format - Ass...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_null - As...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_unsupported_format
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_html - At...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_markdown
5 failed, 3 passed in 0.05s
```
- 驗收測試輸出（尾巴）：
```

acceptance_tests/test_readtime.py:12: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_can_add - Assert...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_html - Attribute...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_markdown - Attri...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_plain_text - Ass...
4 failed in 0.05s
```

### particle-swarm-optimization：單元 5/5、驗收 1/1（bare，0.1 分鐘）
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

### chakin：單元 0/1、驗收 0/1（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
    from .downloader import load_datasets, search, download
chakin/downloader.py:4: in <module>
    from progressbar2 import ProgressBar
E   ModuleNotFoundError: No module named 'progressbar2'
=========================== short test summary info ============================
ERROR unit_tests/test_downloader.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.17s
```
- 驗收測試輸出（尾巴）：
```
    from .downloader import load_datasets, search, download
chakin/downloader.py:4: in <module>
    from progressbar2 import ProgressBar
E   ModuleNotFoundError: No module named 'progressbar2'
=========================== short test summary info ============================
ERROR acceptance_tests/acceptance_test.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.20s
```

### stocktrends：單元 0/7、驗收 0/2（bare，0.6 分鐘）
- 單元測試輸出（尾巴）：
```
E       ^
E   SyntaxError: invalid syntax
=========================== short test summary info ============================
ERROR unit_tests/test_instrument.py
ERROR unit_tests/test_pnf.py
ERROR unit_tests/test_renko.py
!!!!!!!!!!!!!!!!!!! Interrupted: 3 errors during collection !!!!!!!!!!!!!!!!!!!!
3 errors in 0.22s
```
- 驗收測試輸出（尾巴）：
```
E     File "/tmp/devbench_bare_us3kvngk/workspace/stocktrends/indicators.py", line 1
E       ```python
E       ^
E   SyntaxError: invalid syntax
=========================== short test summary info ============================
ERROR acceptance_tests/test_indicators.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.18s
```

### geotext：單元 0/4、驗收 1/5（bare，0.2 分鐘）
- 單元測試輸出（尾巴）：
```

unit_tests/test_geotext.py:104: AssertionError
=========================== short test summary info ============================
FAILED unit_tests/test_geotext.py::TestGeotext::test_cities - AssertionError:...
FAILED unit_tests/test_geotext.py::TestGeotext::test_countries - AssertionErr...
FAILED unit_tests/test_geotext.py::TestGeotext::test_country_mentions - Asser...
FAILED unit_tests/test_geotext.py::TestGeotext::test_nationalities - Assertio...
4 failed in 0.01s
```
- 驗收測試輸出（尾巴）：
```

acceptance_tests/test_acceptance.py:34: AssertionError
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_city_extraction
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_filter
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_mentions_count
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_nationalities_extraction
4 failed, 1 passed in 0.01s
```

### hone：單元 0/7、驗收 2/5（bare，0.2 分鐘）
- 單元測試輸出（尾巴）：
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
unit_tests/test_hone.py:4: in <module>
    from hone.utils import test_utils
E   ImportError: cannot import name 'test_utils' from 'hone.utils' (/tmp/devbench_bare_z___vbc0/workspace/hone/utils/__init__.py)
=========================== short test summary info ============================
ERROR unit_tests/test_hone.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.04s
```
- 驗收測試輸出（尾巴）：
```
E   {'some \'quoted"\' field"': 'no quotes', 'adopted_since': '2018', 'adopted': 'TRUE', 'birth': {'year': '2015', 'month': 'January', 'day': '18'}, 'weight (kg)': '3.1', 'age (years)': '3', 'name': 'Ciel'}
E   
E   Diff is 1823 characters long. Set self.maxDiff to None to see it.
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_data_integrity
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_nested_json_generation
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_quoted_field_handling
3 failed, 2 passed in 0.01s
```

### lice：單元 19/25、驗收 6/6（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
=========================== short test summary info ============================
FAILED unit_tests/test_lice.py::test_license - AttributeError: 'dict' object ...
FAILED unit_tests/test_lice.py::test_license_header - AttributeError: 'dict' ...
FAILED unit_tests/test_lice.py::TestMainFunction::test_list_languages_option
FAILED unit_tests/test_lice.py::TestMainFunction::test_list_template_vars - A...
FAILED unit_tests/test_lice.py::TestMainFunction::test_list_template_vars_with_custom_template
FAILED unit_tests/test_lice.py::TestMainFunction::test_output_to_file - Syste...
6 failed, 19 passed in 0.04s
```
- 驗收測試輸出（尾巴）：
```
......                                                                   [100%]
6 passed in 0.11s
```

### area_calculation：單元 3/3、驗收 0/3（bare，0.2 分鐘）
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
~Circle()
~Shape()
~Rectangle()
~Shape()
~Rectangle()
~Shape()
Processed input/3.txt and saved the output to outputs/3.txt
Mismatch found in file 1.txt
```

### graph-cpp：單元 0/22、驗收 5/5（bare，0.3 分鐘）
- 單元測試輸出（尾巴）：
```
      |                                                          ~~~~~~~~~~~~~^~~~~~~
unit_tests/../include/al_graph.hpp:87:34: error: ‘struct _vNode<int>’ has no member named ‘arcList’
   87 |                     _vexList[v]->arcList = new ArcNode(u, w, _vexList[v]->arcList);
      |                     ~~~~~~~~~~~~~^~~~~~~
unit_tests/../include/al_graph.hpp:87:75: error: ‘struct _vNode<int>’ has no member named ‘arcList’
   87 |                     _vexList[v]->arcList = new ArcNode(u, w, _vexList[v]->arcList);
      |                                                              ~~~~~~~~~~~~~^~~~~~~
make: *** [makefile_test:31: obj/test_al_graph.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
   87 |                     _vexList[v]->arcList = new ArcNode(u, w, _vexList[v]->arcList);
      |                                                              ~~~~~~~~~~~~~^~~~~~~
make: *** [makefile:14: src/main.o] Error 1
acceptance_tests/test.sh: line 31: ./graph: No such file or directory
acceptance_tests/test.sh: line 31: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
```

### logistic_system：單元 13/17、驗收 1/7（bare，0.6 分鐘）
- 單元測試輸出（尾巴）：
```
[  FAILED  ] 4 tests, listed below:
[  FAILED  ] AccountNodeTest.OutputOperatorTest
[  FAILED  ] LogisticSysTest.AddMoneyTest
[  FAILED  ] LogisticSysTest.QueryAllExpressageTest
[  FAILED  ] LogisticSysTest.QueryExpressageTest

 4 FAILED TESTS
make: *** [makefile_test:43: test] Error 1
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

### people_management：單元 0/9、驗收 0/7（bare，0.4 分鐘）
- 單元測試輸出（尾巴）：
```
/usr/include/c++/11/bits/basic_string.h:6212:5: note: candidate: ‘template<class _CharT, class _Traits, class _Alloc> std::__cxx11::basic_string<_CharT, _Traits, _Allocator> std::operator+(std::__cxx11::basic_string<_CharT, _Traits, _Allocator>&&, _CharT)’
 6212 |     operator+(basic_string<_CharT, _Traits, _Alloc>&& __lhs,
      |     ^~~~~~~~
/usr/include/c++/11/bits/basic_string.h:6212:5: note:   template argument deduction/substitution failed:
src/people_management.cpp:72:27: note:   deduced conflicting types for parameter ‘_CharT’ (‘char’ and ‘int’)
   72 |                           school_id + ", " + options.at("-type") + ");";
      |                           ^~~~~~~~~
make: *** [makefile_test:34: src/people_management.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
FAILED acceptance_tests/acceptance_testing.py::test_add_school - assert 127 == 0
FAILED acceptance_tests/acceptance_testing.py::test_add_person - assert 127 == 0
FAILED acceptance_tests/acceptance_testing.py::test_search_person - assert 12...
FAILED acceptance_tests/acceptance_testing.py::test_search_school - assert 12...
FAILED acceptance_tests/acceptance_testing.py::test_update_person - assert 12...
FAILED acceptance_tests/acceptance_testing.py::test_update_school - assert 12...
FAILED acceptance_tests/acceptance_testing.py::test_mentor - assert 127 == 0
7 failed in 0.03s
```

### xlsx2csv：單元 0/8、驗收 0/5（bare，0.6 分鐘）
- 單元測試輸出（尾巴）：
```
   35 |                 std::string path(file_stat.filename);
      |                                            ^~~~~~~~
      |                                            m_filename
src/archive.cpp:46:5: error: ‘mz_zip_archive_end’ was not declared in this scope; did you mean ‘mz_zip_archive’?
   46 |     mz_zip_archive_end(&zip_archive);
      |     ^~~~~~~~~~~~~~~~~~
      |     mz_zip_archive
make: *** [makefile_test:28: src/archive.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
   35 |                 std::string path(file_stat.filename);
      |                                            ^~~~~~~~
      |                                            m_filename
src/archive.cpp:46:5: error: ‘mz_zip_archive_end’ was not declared in this scope; did you mean ‘mz_zip_archive’?
   46 |     mz_zip_archive_end(&zip_archive);
      |     ^~~~~~~~~~~~~~~~~~
      |     mz_zip_archive
make: *** [makefile:30: src/archive.o] Error 1
```
