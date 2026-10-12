# DevBench 實作任務：不用 harness 的對照組（gemma4:26b，一個檔案呼叫一次模型，沒有工具與測試回饋）

- 時間：2026-10-08 14:59；12 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。agent 看不到官方測試。

- **全部**（12 個 repo）：單元測試 5/116（4.3%）、驗收測試 9/51（17.6%）；每個 repo 通過率的平均：單元 8.3%、驗收 21.4%；依程式碼行數加權：單元 3.7%、驗收 21.9%
- **Python**（7 個 repo）：單元測試 5/57（8.8%）、驗收測試 4/24（16.7%）；每個 repo 通過率的平均：單元 14.3%、驗收 22.4%；依程式碼行數加權：單元 7.9%、驗收 16.1%
- **C++**（5 個 repo）：單元測試 0/59（0.0%）、驗收測試 5/27（18.5%）；每個 repo 通過率的平均：單元 0.0%、驗收 20.0%；依程式碼行數加權：單元 0.0%、驗收 26.9%

| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|
| readtime | python | 0/8 | 0/4 | bare | 0/0 | 0.1 | 4 |
| particle-swarm-optimization | python | 5/5 | 1/1 | bare | 0/0 | 0.1 | 3 |
| chakin | python | 0/1 | 0/1 | bare | 0/0 | 0.1 | 2 |
| stocktrends | python | 0/7 | 0/2 | bare | 0/0 | 0.2 | 2 |
| geotext | python | 0/4 | 0/5 | bare | 0/0 | 0.1 | 2 |
| hone | python | 0/7 | 2/5 | bare | 0/0 | 0.2 | 5 |
| lice | python | 0/25 | 1/6 | bare | 0/0 | 0.1 | 2 |
| area_calculation | cpp | 0/3 | 0/3 | bare | 0/0 | 0.1 | 9 |
| graph-cpp | cpp | 0/22 | 5/5 | bare | 0/0 | 0.3 | 6 |
| logistic_system | cpp | 0/17 | 0/7 | bare | 0/0 | 0.4 | 9 |
| people_management | cpp | 0/9 | 0/7 | bare | 0/0 | 0.4 | 8 |
| xlsx2csv | cpp | 0/8 | 0/5 | bare | 0/0 | 0.5 | 12 |

參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%；GPT-4-Turbo-1106 驗收 6.9%、單元 6.8%；GPT-3.5-Turbo 驗收 4.2%、單元 4.3%；DeepSeek-Coder-33B-Instruct 驗收 4.4%、單元 5.5%；CodeLlama-34B-Instruct 驗收 0.6%、單元 0.5%

## 每個 repo

### readtime：單元 0/8、驗收 0/4（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_empty - A...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_null - Ty...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_unsupported_format
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm - Attribu...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_html - At...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_markdown
FAILED unit_tests/test_transitions.py::BaseTestCase::test_transitions - Asser...
8 failed in 0.05s
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
chakin/downloader.py:3: in <module>
    import requests
E   ModuleNotFoundError: No module named 'requests'
=========================== short test summary info ============================
ERROR unit_tests/test_downloader.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.18s
```
- 驗收測試輸出（尾巴）：
```
    from .downloader import load_datasets, search, download
chakin/downloader.py:3: in <module>
    import requests
E   ModuleNotFoundError: No module named 'requests'
=========================== short test summary info ============================
ERROR acceptance_tests/acceptance_test.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.20s
```

### stocktrends：單元 0/7、驗收 0/2（bare，0.2 分鐘）
- 單元測試輸出（尾巴）：
```
FAILED unit_tests/test_instrument.py::test_validate_df - TypeError: Instrumen...
FAILED unit_tests/test_pnf.py::test_get_state - TypeError: PnF.__init__() mis...
FAILED unit_tests/test_pnf.py::test_roundit - TypeError: PnF.__init__() missi...
FAILED unit_tests/test_pnf.py::test_get_bar_ohlc_data_close - TypeError: PnF....
FAILED unit_tests/test_pnf.py::test_get_bar_ohlc_data_hl - TypeError: PnF.__i...
FAILED unit_tests/test_pnf.py::test_get_ohlc_data_close - TypeError: PnF.__in...
FAILED unit_tests/test_renko.py::test_Renko_box_periodic_close - TypeError: R...
7 failed in 0.17s
```
- 驗收測試輸出（尾巴）：
```
             ^^^^^^^^^^^^^
E       TypeError: LineBreak.__init__() missing 1 required positional argument: 'line_number'

acceptance_tests/test_indicators.py:39: TypeError
=========================== short test summary info ============================
FAILED acceptance_tests/test_indicators.py::test_renko - TypeError: Renko.__i...
FAILED acceptance_tests/test_indicators.py::test_linebreak - TypeError: LineB...
2 failed in 0.16s
```

### geotext：單元 0/4、驗收 0/5（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```

geotext/geotext.py:93: FileNotFoundError
=========================== short test summary info ============================
FAILED unit_tests/test_geotext.py::TestGeotext::test_cities - FileNotFoundErr...
FAILED unit_tests/test_geotext.py::TestGeotext::test_countries - FileNotFound...
FAILED unit_tests/test_geotext.py::TestGeotext::test_country_mentions - FileN...
FAILED unit_tests/test_geotext.py::TestGeotext::test_nationalities - FileNotF...
4 failed in 0.02s
```
- 驗收測試輸出（尾巴）：
```
geotext/geotext.py:93: FileNotFoundError
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_city_extraction
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_filter
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_mentions_count
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_data_loading
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_nationalities_extraction
5 failed in 0.02s
```

### hone：單元 0/7、驗收 2/5（bare，0.2 分鐘）
- 單元測試輸出（尾巴）：
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
unit_tests/test_hone.py:4: in <module>
    from hone.utils import test_utils
E   ImportError: cannot import name 'test_utils' from 'hone.utils' (/tmp/devbench_bare_8z9gdc49/workspace/hone/utils/__init__.py)
=========================== short test summary info ============================
ERROR unit_tests/test_hone.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.04s
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

### lice：單元 0/25、驗收 1/6（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
unit_tests/test_lice.py:9: in <module>
    from lice.core import (
E   ImportError: cannot import name 'LICENSES' from 'lice.core' (/tmp/devbench_bare_g4_nphu2/workspace/lice/core.py)
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

### area_calculation：單元 0/3、驗收 0/3（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
/usr/bin/ld: test_Circle.cpp:(.text+0x170): undefined reference to `Circle::~Circle()'
/usr/bin/ld: test_Circle.cpp:(.text+0x1eb): undefined reference to `Circle::~Circle()'
/usr/bin/ld: unit_tests/test_Square.o: in function `TestSquare_CalcArea_Test::TestBody()':
test_Square.cpp:(.text+0x3a): undefined reference to `Square::Square(double)'
/usr/bin/ld: test_Square.cpp:(.text+0x176): undefined reference to `Square::~Square()'
/usr/bin/ld: test_Square.cpp:(.text+0x1f1): undefined reference to `Square::~Square()'
collect2: error: ld returned 1 exit status
make: *** [makefile_test:36: run_tests] Error 1
```
- 驗收測試輸出（尾巴）：
```
g++ -std=c++17 -Wall -Iinclude -o shape_app obj/Shape.o obj/Rectangle.o obj/main.o
Compilation failed.
/usr/bin/ld: obj/main.o: in function `std::_MakeUniq<Circle>::__single_object std::make_unique<Circle, double&>(double&)':
main.cpp:(.text._ZSt11make_uniqueI6CircleJRdEENSt9_MakeUniqIT_E15__single_objectEDpOT0_[_ZSt11make_uniqueI6CircleJRdEENSt9_MakeUniqIT_E15__single_objectEDpOT0_]+0x3e): undefined reference to `Circle::Circle(double)'
/usr/bin/ld: obj/main.o: in function `std::_MakeUniq<Square>::__single_object std::make_unique<Square, double&>(double&)':
main.cpp:(.text._ZSt11make_uniqueI6SquareJRdEENSt9_MakeUniqIT_E15__single_objectEDpOT0_[_ZSt11make_uniqueI6SquareJRdEENSt9_MakeUniqIT_E15__single_objectEDpOT0_]+0x3e): undefined reference to `Square::Square(double)'
collect2: error: ld returned 1 exit status
make: *** [makefile:19: shape_app] Error 1
```

### graph-cpp：單元 0/22、驗收 5/5（bare，0.3 分鐘）
- 單元測試輸出（尾巴）：
```
      |                                                       ~~~~~~~~~~~~^~~~
unit_tests/../include/al_graph.hpp:71:29: error: ‘__gnu_cxx::__alloc_traits<std::allocator<_vNode<int> >, _vNode<int> >::value_type’ {aka ‘struct _vNode<int>’} has no member named ‘head’
   71 |                 _vexList[v].head = new ArcNode(u, weight, _vexList[v].head);
      |                 ~~~~~~~~~~~~^~~~
unit_tests/../include/al_graph.hpp:71:71: error: ‘__gnu_cxx::__alloc_traits<std::allocator<_vNode<int> >, _vNode<int> >::value_type’ {aka ‘struct _vNode<int>’} has no member named ‘head’
   71 |                 _vexList[v].head = new ArcNode(u, weight, _vexList[v].head);
      |                                                           ~~~~~~~~~~~~^~~~
make: *** [makefile_test:31: obj/test_al_graph.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
   71 |                 _vexList[v].head = new ArcNode(u, weight, _vexList[v].head);
      |                                                           ~~~~~~~~~~~~^~~~
make: *** [makefile:19: obj/main.o] Error 1
acceptance_tests/test.sh: line 31: ./graph: No such file or directory
acceptance_tests/test.sh: line 31: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
```

### logistic_system：單元 0/17、驗收 0/7（bare，0.4 分鐘）
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
      |                     ~~^~~~~~~~~~~~~~~~
acceptance_tests/test.sh: line 37: ./logistics: No such file or directory
acceptance_tests/test.sh: line 37: ./logistics: No such file or directory
acceptance_tests/test.sh: line 37: ./logistics: No such file or directory
acceptance_tests/test.sh: line 37: ./logistics: No such file or directory
acceptance_tests/test.sh: line 37: ./logistics: No such file or directory
acceptance_tests/test.sh: line 37: ./logistics: No such file or directory
acceptance_tests/test.sh: line 37: ./logistics: No such file or directory
```

### people_management：單元 0/9、驗收 0/7（bare，0.4 分鐘）
- 單元測試輸出（尾巴）：
```
g++ -Wall -g -std=c++17 -fprofile-arcs -ftest-coverage -I include/ -c src/people_management.cpp -o src/people_management.o
src/people_management.cpp: In member function ‘bool PeopleManagement::check_database(const char*) const’:
src/people_management.cpp:22:29: error: request for member ‘c_str’ in ‘db_name’, which is of non-class type ‘const char*’
   22 |     std::ifstream f(db_name.c_str());
      |                             ^~~~~
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

### xlsx2csv：單元 0/8、驗收 0/5（bare，0.5 分鐘）
- 單元測試輸出（尾巴）：
```
src/archive.cpp:48:85: error: ‘struct mz_zip_archive_file_stat’ has no member named ‘uncompressed_size’
   48 |             persistent_data.emplace_back(reinterpret_cast<char*>(buffer), file_stat.uncompressed_size);
      |                                                                                     ^~~~~~~~~~~~~~~~~
src/archive.cpp:54:5: error: ‘mz_zip_archive_end’ was not declared in this scope; did you mean ‘mz_zip_archive’?
   54 |     mz_zip_archive_end(&zip_archive);
      |     ^~~~~~~~~~~~~~~~~~
      |     mz_zip_archive
make: *** [makefile_test:28: src/archive.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
mkdir: cannot create directory ‘./outputs/test002’: File exists
mkdir: cannot create directory ‘./outputs/test003’: File exists
In file included from include/workbook.h:9,
                 from src/main.cpp:4:
include/archive.h:7:24: error: missing terminating > character
    7 | #include <unordered_map
      |                        ^
make: *** [makefile:30: src/main.o] Error 1
```
