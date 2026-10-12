# DevBench 實作任務：不用 harness 的對照組（qwen2.5-coder:32b，一個檔案呼叫一次模型，沒有工具與測試回饋）

- 時間：2026-10-09 16:12；12 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。agent 看不到官方測試。

- **全部**（12 個 repo）：單元測試 4/116（3.4%）、驗收測試 7/51（13.7%）；每個 repo 通過率的平均：單元 6.7%、驗收 18.3%；依程式碼行數加權：單元 2.9%、驗收 19.4%
- **Python**（7 個 repo）：單元測試 4/57（7.0%）、驗收測試 2/24（8.3%）；每個 repo 通過率的平均：單元 11.4%、驗收 17.1%；依程式碼行數加權：單元 6.3%、驗收 10.5%
- **C++**（5 個 repo）：單元測試 0/59（0.0%）、驗收測試 5/27（18.5%）；每個 repo 通過率的平均：單元 0.0%、驗收 20.0%；依程式碼行數加權：單元 0.0%、驗收 26.9%

| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|
| readtime | python | 0/8 | 0/4 | bare | 0/0 | 0.4 | 4 |
| particle-swarm-optimization | python | 4/5 | 1/1 | bare | 0/0 | 0.3 | 3 |
| chakin | python | 0/1 | 0/1 | bare | 0/0 | 0.2 | 2 |
| stocktrends | python | 0/7 | 0/2 | bare | 0/0 | 3.6 | 2 |
| geotext | python | 0/4 | 0/5 | bare | 0/0 | 0.4 | 2 |
| hone | python | 0/7 | 1/5 | bare | 0/0 | 0.5 | 5 |
| lice | python | 0/25 | 0/6 | bare | 0/0 | 0.5 | 2 |
| area_calculation | cpp | 0/3 | 0/3 | bare | 0/0 | 0.4 | 9 |
| graph-cpp | cpp | 0/22 | 5/5 | bare | 0/0 | 1.3 | 6 |
| logistic_system | cpp | 0/17 | 0/7 | bare | 0/0 | 1.9 | 9 |
| people_management | cpp | 0/9 | 0/7 | bare | 0/0 | 1.2 | 8 |
| xlsx2csv | cpp | 0/8 | 0/5 | bare | 0/0 | 1.6 | 12 |

參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%；GPT-4-Turbo-1106 驗收 6.9%、單元 6.8%；GPT-3.5-Turbo 驗收 4.2%、單元 4.3%；DeepSeek-Coder-33B-Instruct 驗收 4.4%、單元 5.5%；CodeLlama-34B-Instruct 驗收 0.6%、單元 0.5%

## 每個 repo

### readtime：單元 0/8、驗收 0/4（bare，0.4 分鐘）
- 單元測試輸出（尾巴）：
```
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_empty - U...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_null - At...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_unsupported_format
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm - Unbound...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_html - Ty...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_markdown
FAILED unit_tests/test_transitions.py::BaseTestCase::test_transitions - Unbou...
8 failed in 0.07s
```
- 驗收測試輸出（尾巴）：
```

readtime/utils.py:18: UnboundLocalError
=========================== short test summary info ============================
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_can_add - Unboun...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_html - TypeError...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_markdown - TypeE...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_plain_text - Unb...
4 failed in 0.08s
```

### particle-swarm-optimization：單元 4/5、驗收 1/1（bare，0.3 分鐘）
- 單元測試輸出（尾巴）：
```
>       for i in range(0, num_dimensions):
                          ^^^^^^^^^^^^^^
E       NameError: name 'num_dimensions' is not defined

pso/pso_simple.py:11: NameError
=========================== short test summary info ============================
FAILED unit_tests/test_pso_simple.py::TestPSO::test_evaluate - NameError: nam...
1 failed, 4 passed in 0.01s
```
- 驗收測試輸出（尾巴）：
```
.                                                                        [100%]
1 passed in 0.00s
```

### chakin：單元 0/1、驗收 0/1（bare，0.2 分鐘）
- 單元測試輸出（尾巴）：
```
    from chakin.downloader import load_datasets, download
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
    from chakin.downloader import download, search
chakin/downloader.py:3: in <module>
    import requests
E   ModuleNotFoundError: No module named 'requests'
=========================== short test summary info ============================
ERROR acceptance_tests/acceptance_test.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.17s
```

### stocktrends：單元 0/7、驗收 0/2（bare，3.6 分鐘）
- 單元測試輸出（尾巴）：
```
E               ^
E   SyntaxError: unterminated string literal (detected at line 453)
=========================== short test summary info ============================
ERROR unit_tests/test_instrument.py
ERROR unit_tests/test_pnf.py
ERROR unit_tests/test_renko.py
!!!!!!!!!!!!!!!!!!! Interrupted: 3 errors during collection !!!!!!!!!!!!!!!!!!!!
3 errors in 0.27s
```
- 驗收測試輸出（尾巴）：
```
E     File "/tmp/devbench_bare_z12c1lu6/workspace/stocktrends/indicators.py", line 453
E       self.df['line
E               ^
E   SyntaxError: unterminated string literal (detected at line 453)
=========================== short test summary info ============================
ERROR acceptance_tests/test_indicators.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.19s
```

### geotext：單元 0/4、驗收 0/5（bare，0.4 分鐘）
- 單元測試輸出（尾巴）：
```

geotext/geotext.py:16: FileNotFoundError
=========================== short test summary info ============================
FAILED unit_tests/test_geotext.py::TestGeotext::test_cities - FileNotFoundErr...
FAILED unit_tests/test_geotext.py::TestGeotext::test_countries - FileNotFound...
FAILED unit_tests/test_geotext.py::TestGeotext::test_country_mentions - FileN...
FAILED unit_tests/test_geotext.py::TestGeotext::test_nationalities - FileNotF...
4 failed in 0.02s
```
- 驗收測試輸出（尾巴）：
```
geotext/geotext.py:16: FileNotFoundError
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_city_extraction
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_filter
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_country_mentions_count
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_data_loading
FAILED acceptance_tests/test_acceptance.py::TestGeoTextAcceptance::test_nationalities_extraction
5 failed in 0.02s
```

### hone：單元 0/7、驗收 1/5（bare，0.5 分鐘）
- 單元測試輸出（尾巴）：
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
unit_tests/test_hone.py:4: in <module>
    from hone.utils import test_utils
E   ImportError: cannot import name 'test_utils' from 'hone.utils' (unknown location)
=========================== short test summary info ============================
ERROR unit_tests/test_hone.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.04s
```
- 驗收測試輸出（尾巴）：
```

hone/hone.py:38: TypeError
=========================== short test summary info ============================
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_comma_handling
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_data_integrity
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_nested_json_generation
FAILED acceptance_tests/test_acceptance.py::CSVtoJSONAcceptanceTests::test_quoted_field_handling
4 failed, 1 passed in 0.02s
```

### lice：單元 0/25、驗收 0/6（bare，0.5 分鐘）
- 單元測試輸出（尾巴）：
```
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
unit_tests/test_lice.py:9: in <module>
    from lice.core import (
E   ImportError: cannot import name 'valid_year' from 'lice.core' (/tmp/devbench_bare_fgk4sua2/workspace/lice/core.py)
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
6 failed in 0.10s
```

### area_calculation：單元 0/3、驗收 0/3（bare，0.4 分鐘）
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
g++ -std=c++17 -Wall -Wextra -O2 -c src/main.cpp -o src/main.o
Compilation failed.
src/main.cpp:3:10: fatal error: Circle.hpp: No such file or directory
    3 | #include "Circle.hpp"
      |          ^~~~~~~~~~~~
compilation terminated.
make: *** [makefile:14: src/main.o] Error 1
```

### graph-cpp：單元 0/22、驗收 5/5（bare，1.3 分鐘）
- 單元測試輸出（尾巴）：
```
mkdir -p obj
g++ -std=c++17 -Wall -g -fprofile-arcs -ftest-coverage -isystem /home/a111/Documents/googletest/googletest/include -c -o obj/test_al_graph.o unit_tests/test_al_graph.cpp
In file included from unit_tests/test_al_graph.cpp:3:
unit_tests/../include/al_graph.hpp:7:10: fatal error: queue.hpp: No such file or directory
    7 | #include <queue.hpp>
      |          ^~~~~~~~~~~
compilation terminated.
make: *** [makefile_test:31: obj/test_al_graph.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
Testing completed. Check the test_outputs directory for results.
make: *** No rule to make target 'clean'.  Stop.
make: *** No targets specified and no makefile found.  Stop.
acceptance_tests/test.sh: line 31: ./graph: No such file or directory
acceptance_tests/test.sh: line 31: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
acceptance_tests/test.sh: line 43: ./graph: No such file or directory
```

### logistic_system：單元 0/17、驗收 0/7（bare，1.9 分鐘）
- 單元測試輸出（尾巴）：
```
g++ -std=c++17 -Iinclude -fprofile-arcs -ftest-coverage -c -o src/account.o src/account.cpp
src/account.cpp: In function ‘std::ostream& operator<<(std::ostream&, const AccountNode&)’:
src/account.cpp:12:44: error: ‘setprecision’ is not a member of ‘std’
   12 |         << "Money: " << std::fixed << std::setprecision(2) << a.money << "\n"
      |                                            ^~~~~~~~~~~~
make: *** [makefile_test:27: src/account.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
Build failed
mkdir: cannot create directory ‘./data’: File exists
mkdir: cannot create directory ‘./outputs’: File exists
src/main.cpp:3:10: fatal error: logistics.h: No such file or directory
    3 | #include "logistics.h"
      |          ^~~~~~~~~~~~~
compilation terminated.
make: *** [makefile:21: src/main.o] Error 1
```

### people_management：單元 0/9、驗收 0/7（bare，1.2 分鐘）
- 單元測試輸出（尾巴）：
```
g++ -Wall -g -std=c++17 -fprofile-arcs -ftest-coverage -I include/ -c src/people_management.cpp -o src/people_management.o
src/people_management.cpp: In member function ‘bool PeopleManagement::execute_sql_from_file(const char*) const’:
src/people_management.cpp:41:33: error: variable ‘std::ifstream file’ has initializer but incomplete type
   41 |     std::ifstream file(file_name);
      |                                 ^
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

### xlsx2csv：單元 0/8、驗收 0/5（bare，1.6 分鐘）
- 單元測試輸出（尾巴）：
```
src/archive.cpp:64:29: error: request for member ‘emplace_back’ in ‘sheet_relations’, which is of non-class type ‘int’
   64 |             sheet_relations.emplace_back(name, static_cast<std::uint32_t>(std::stoi(sheetId)), rId);
      |                             ^~~~~~~~~~~~
src/archive.cpp: At global scope:
src/archive.cpp:114:19: error: definition of implicitly-declared ‘xlsx2csv::archive::~archive()’
  114 | archive::~archive() {
      |                   ^
make: *** [makefile_test:28: src/archive.o] Error 1
```
- 驗收測試輸出（尾巴）：
```
rm -f src/main.o src/workbook.o src/worksheet.o src/archive.o src/utils.o src/miniz.c src/tinyxml2.o src/main.cpp src/workbook.cpp src/worksheet.cpp src/archive.cpp src/utils.cpp src/miniz.o src/tinyxml2.cpp xlsx2csv
Build failed
mkdir: cannot create directory ‘./outputs’: File exists
mkdir: cannot create directory ‘./outputs/test001’: File exists
mkdir: cannot create directory ‘./outputs/test002’: File exists
mkdir: cannot create directory ‘./outputs/test003’: File exists
make: *** No rule to make target 'src/main.cpp', needed by 'src/main.o'.  Stop.
```
