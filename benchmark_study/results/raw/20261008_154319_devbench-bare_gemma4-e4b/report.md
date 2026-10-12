# DevBench 實作任務：不用 harness 的對照組（gemma4:e4b，一個檔案呼叫一次模型，沒有工具與測試回饋）

- 時間：2026-10-08 15:46；12 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。agent 看不到官方測試。

- **全部**（12 個 repo）：單元測試 1/116（0.9%）、驗收測試 7/51（13.7%）；每個 repo 通過率的平均：單元 1.2%、驗收 11.7%；依程式碼行數加權：單元 1.2%、驗收 16.9%
- **Python**（7 個 repo）：單元測試 1/57（1.8%）、驗收測試 2/24（8.3%）；每個 repo 通過率的平均：單元 2.0%、驗收 5.7%；依程式碼行數加權：單元 2.6%、驗收 5.2%
- **C++**（5 個 repo）：單元測試 0/59（0.0%）、驗收測試 5/27（18.5%）；每個 repo 通過率的平均：單元 0.0%、驗收 20.0%；依程式碼行數加權：單元 0.0%、驗收 26.9%

| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|
| readtime | python | 0/8 | 0/4 | bare | 0/0 | 0.2 | 4 |
| particle-swarm-optimization | python | 0/5 | 0/1 | bare | 0/0 | 0.1 | 3 |
| chakin | python | 0/1 | 0/1 | bare | 0/0 | 0.1 | 2 |
| stocktrends | python | 1/7 | 0/2 | bare | 0/0 | 0.1 | 2 |
| geotext | python | 0/4 | 0/5 | bare | 0/0 | 0.2 | 2 |
| hone | python | 0/7 | 2/5 | bare | 0/0 | 0.2 | 5 |
| lice | python | 0/25 | 0/6 | bare | 0/0 | 0.1 | 2 |
| area_calculation | cpp | 0/3 | 0/3 | bare | 0/0 | 0.2 | 9 |
| graph-cpp | cpp | 0/22 | 5/5 | bare | 0/0 | 0.4 | 6 |
| logistic_system | cpp | 0/17 | 0/7 | bare | 0/0 | 0.6 | 9 |
| people_management | cpp | 0/9 | 0/7 | bare | 0/0 | 0.9 | 8 |
| xlsx2csv | cpp | 0/8 | 0/5 | bare | 0/0 | 0.4 | 12 |

參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%；GPT-4-Turbo-1106 驗收 6.9%、單元 6.8%；GPT-3.5-Turbo 驗收 4.2%、單元 4.3%；DeepSeek-Coder-33B-Instruct 驗收 4.4%、單元 5.5%；CodeLlama-34B-Instruct 驗收 0.6%、單元 0.5%

## 每個 repo

### readtime：單元 0/8、驗收 0/4（bare，0.2 分鐘）
- 單元測試輸出（尾巴）：
```
    Result._add_operator_methods()
E   TypeError: Result._add_operator_methods() missing 1 required positional argument: 'self'
=========================== short test summary info ============================
ERROR unit_tests/test_check_data.py - TypeError: Result._add_operator_methods...
ERROR unit_tests/test_custom_wpm.py - TypeError: Result._add_operator_methods...
ERROR unit_tests/test_transitions.py - TypeError: Result._add_operator_method...
!!!!!!!!!!!!!!!!!!! Interrupted: 3 errors during collection !!!!!!!!!!!!!!!!!!!!
3 errors in 0.06s
```
- 驗收測試輸出（尾巴）：
```
    from .result import Result
readtime/result.py:79: in <module>
    Result._add_operator_methods()
E   TypeError: Result._add_operator_methods() missing 1 required positional argument: 'self'
=========================== short test summary info ============================
ERROR acceptance_tests/test_readtime.py - TypeError: Result._add_operator_met...
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.06s
```

### particle-swarm-optimization：單元 0/5、驗收 0/1（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
    def sphere(x: List[float]) -> float:
                  ^^^^
E   NameError: name 'List' is not defined
=========================== short test summary info ============================
ERROR unit_tests/test_cost_functions.py - NameError: name 'List' is not defined
ERROR unit_tests/test_pso_simple.py - NameError: name 'List' is not defined
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.04s
```
- 驗收測試輸出（尾巴）：
```
pso/cost_functions.py:1: in <module>
    def sphere(x: List[float]) -> float:
                  ^^^^
E   NameError: name 'List' is not defined
=========================== short test summary info ============================
ERROR acceptance_tests/test_pso.py - NameError: name 'List' is not defined
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.04s
```

### chakin：單元 0/1、驗收 0/1（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
    from .downloader import search, download, load_datasets
chakin/downloader.py:3: in <module>
    import requests
E   ModuleNotFoundError: No module named 'requests'
=========================== short test summary info ============================
ERROR unit_tests/test_downloader.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.17s
```
- 驗收測試輸出（尾巴）：
```
    from .downloader import search, download, load_datasets
chakin/downloader.py:3: in <module>
    import requests
E   ModuleNotFoundError: No module named 'requests'
=========================== short test summary info ============================
ERROR acceptance_tests/acceptance_test.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.20s
```

### stocktrends：單元 1/7、驗收 0/2（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
=========================== short test summary info ============================
FAILED unit_tests/test_pnf.py::test_get_state - AttributeError: 'PnF' object ...
FAILED unit_tests/test_pnf.py::test_roundit - TypeError: PnF.roundit() missin...
FAILED unit_tests/test_pnf.py::test_get_bar_ohlc_data_close - assert (879, 15...
FAILED unit_tests/test_pnf.py::test_get_bar_ohlc_data_hl - assert (879, 15) =...
FAILED unit_tests/test_pnf.py::test_get_ohlc_data_close - assert (879, 15) ==...
FAILED unit_tests/test_renko.py::test_Renko_box_periodic_close - AttributeErr...
6 failed, 1 passed in 0.17s
```
- 驗收測試輸出（尾巴）：
```

acceptance_tests/test_indicators.py:42: AssertionError
----------------------------- Captured stdout call -----------------------------
Retrieving OHLC data for LineBreak with line number: 3
=========================== short test summary info ============================
FAILED acceptance_tests/test_indicators.py::test_renko - AssertionError: asse...
FAILED acceptance_tests/test_indicators.py::test_linebreak - AssertionError: ...
2 failed in 0.16s
```

### geotext：單元 0/4、驗收 0/5（bare，0.2 分鐘）
- 單元測試輸出（尾巴）：
```

geotext/geotext.py:167: AttributeError
=========================== short test summary info ============================
FAILED unit_tests/test_geotext.py::TestGeotext::test_cities - AttributeError:...
FAILED unit_tests/test_geotext.py::TestGeotext::test_countries - AttributeErr...
FAILED unit_tests/test_geotext.py::TestGeotext::test_country_mentions - Attri...
FAILED unit_tests/test_geotext.py::TestGeotext::test_nationalities - Attribut...
4 failed in 0.02s
```
- 驗收測試輸出（尾巴）：
```
geotext/geotext.py:167: AttributeError
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
E   ImportError: cannot import name 'test_utils' from 'hone.utils' (/tmp/devbench_bare_6kcok1_0/workspace/hone/utils/__init__.py)
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

### lice：單元 0/25、驗收 0/6（bare，0.1 分鐘）
- 單元測試輸出（尾巴）：
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
unit_tests/test_lice.py:9: in <module>
    from lice.core import (
E   ImportError: cannot import name 'LICENSES' from 'lice.core' (/tmp/devbench_bare_hwxu08s9/workspace/lice/core.py)
=========================== short test summary info ============================
ERROR unit_tests/test_lice.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.05s
```
- 驗收測試輸出（尾巴）：
```
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::test_default_license_generation
FAILED acceptance_tests/test_acceptance.py::test_specified_license_generation
FAILED acceptance_tests/test_acceptance.py::test_license_with_organization - ...
FAILED acceptance_tests/test_acceptance.py::test_license_with_year - Assertio...
FAILED acceptance_tests/test_acceptance.py::test_license_with_project - Asser...
FAILED acceptance_tests/test_acceptance.py::test_license_with_output_file - A...
6 failed in 0.11s
```

### area_calculation：單元 0/3、驗收 0/3（bare，0.2 分鐘）
- 單元測試輸出（尾巴）：
```
/usr/bin/ld: test_Circle.cpp:(.text+0x1eb): undefined reference to `Circle::~Circle()'
/usr/bin/ld: unit_tests/test_Square.o: in function `TestSquare_CalcArea_Test::TestBody()':
test_Square.cpp:(.text+0x3a): undefined reference to `Square::Square(double)'
/usr/bin/ld: test_Square.cpp:(.text+0x46): undefined reference to `Square::calcArea() const'
/usr/bin/ld: test_Square.cpp:(.text+0x176): undefined reference to `Square::~Square()'
/usr/bin/ld: test_Square.cpp:(.text+0x1f1): undefined reference to `Square::~Square()'
collect2: error: ld returned 1 exit status
make: *** [makefile_test:36: run_tests] Error 1
```
- 驗收測試輸出（尾巴）：
```
src/main.cpp:54:42: error: ‘make_unique’ is not a member of ‘std’
   54 |     std::unique_ptr<Shape> square = std::make_unique<Square>(sideLength);
      |                                          ^~~~~~~~~~~
src/main.cpp:54:42: note: ‘std::make_unique’ is defined in header ‘<memory>’; did you forget to ‘#include <memory>’?
src/main.cpp:54:60: error: expected primary-expression before ‘>’ token
   54 |     std::unique_ptr<Shape> square = std::make_unique<Square>(sideLength);
      |                                                            ^
make: *** [makefile:27: obj/main.o] Error 1
```

### graph-cpp：單元 0/22、驗收 5/5（bare，0.4 分鐘）
- 單元測試輸出（尾巴）：
```
unit_tests/../include/al_graph.hpp: In instantiation of ‘AdjacencyListGraph<VertexType>::~AdjacencyListGraph() [with VertexType = int]’:
/usr/include/c++/11/bits/unique_ptr.h:85:2:   required from ‘void std::default_delete<_Tp>::operator()(_Tp*) const [with _Tp = AdjacencyListGraph<int>]’
/usr/include/c++/11/bits/unique_ptr.h:361:17:   required from ‘std::unique_ptr<_Tp, _Dp>::~unique_ptr() [with _Tp = AdjacencyListGraph<int>; _Dp = std::default_delete<AdjacencyListGraph<int> >]’
unit_tests/test_al_graph.cpp:13:58:   required from here
unit_tests/../include/al_graph.hpp:51:22: error: cannot convert ‘__gnu_cxx::__alloc_traits<std::allocator<AdjacencyListGraph<int>::VNode*>, AdjacencyListGraph<int>::VNode*>::value_type’ {aka ‘AdjacencyListGraph<int>::VNode*’} to ‘AdjacencyListGraph<int>::ArcNode*’ in initialization
   51 |             ArcNode* currentArc = _adjList[i];
      |                      ^~~~~~~~~~
make: *** [makefile_test:31: obj/test_al_graph.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
  206 |             ArcNode* currentArc = _adjList[u_idx];
      |                      ^~~~~~~~~~
make: *** [makefile:21: obj/main.o] Error 1
acceptance_tests/test.sh: line 31: ./graph: No such file or directory
acceptance_tests/test.sh: line 31: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
```

### logistic_system：單元 0/17、驗收 0/7（bare，0.6 分鐘）
- 單元測試輸出（尾巴）：
```
include/account.h:43:20: error: expected ‘)’ before ‘,’ token
   43 |     AccountNode(_id, _pwd, _nm, _ph, _m, _ad, _t);
      |                ~   ^
      |                    )
src/account.cpp:10:25: error: expected constructor, destructor, or type conversion before ‘(’ token
   10 | AccountNode::AccountNode(_id, _pwd, _nm, _ph, _m, _ad, _t)
      |                         ^
make: *** [makefile_test:27: src/account.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
include/account.h:43:20: error: expected ‘)’ before ‘,’ token
   43 |     AccountNode(_id, _pwd, _nm, _ph, _m, _ad, _t);
      |                ~   ^
      |                    )
src/account.cpp:10:25: error: expected constructor, destructor, or type conversion before ‘(’ token
   10 | AccountNode::AccountNode(_id, _pwd, _nm, _ph, _m, _ad, _t)
      |                         ^
make: *** [makefile:24: obj/account.o] Error 1
```

### people_management：單元 0/9、驗收 0/7（bare，0.9 分鐘）
- 單元測試輸出（尾巴）：
```
/home/amr-base/.local/include/sqlite3.h:433:9: note:   initializing argument 3 of ‘int sqlite3_exec(sqlite3*, const char*, int (*)(void*, int, char**, char**), void*, char**)’
  433 |   int (*callback)(void*,int,char**,char**),  /* Callback function */
      |   ~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/people_management.cpp: In member function ‘int PeopleManagement::update(const string&, const std::map<std::__cxx11::basic_string<char>, std::__cxx11::basic_string<char> >&) const’:
src/people_management.cpp:337:9: warning: unused variable ‘bind_index’ [-Wunused-variable]
  337 |     int bind_index = 1;
      |         ^~~~~~~~~~
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
7 failed in 0.02s
```

### xlsx2csv：單元 0/8、驗收 0/5（bare，0.4 分鐘）
- 單元測試輸出（尾巴）：
```
g++ -std=c++17 -Iinclude -fprofile-arcs -ftest-coverage -c -o src/archive.o src/archive.cpp
src/archive.cpp:5:10: fatal error: zipstream.h: No such file or directory
    5 | #include <zipstream.h> // Assuming miniz provides zipstream functionality or similar
      |          ^~~~~~~~~~~~~
compilation terminated.
make: *** [makefile_test:28: src/archive.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
mkdir: cannot create directory ‘./outputs/test001’: File exists
mkdir: cannot create directory ‘./outputs/test002’: File exists
mkdir: cannot create directory ‘./outputs/test003’: File exists
src/archive.cpp:5:10: fatal error: zipstream.h: No such file or directory
    5 | #include <zipstream.h> // Assuming miniz provides zipstream functionality or similar
      |          ^~~~~~~~~~~~~
compilation terminated.
make: *** [makefile:30: obj/archive.o] Error 1
```
