# DevBench 實作任務：worker gemma4:e4b、規劃 gemma4:e4b

- 時間：2026-10-07 23:47；3 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。

- **全部**（3 個 repo）：單元測試 8/16（50.0%）、驗收測試 1/8（12.5%）；每個 repo 通過率的平均：單元 66.7%、驗收 33.3%；依程式碼行數加權：單元 53.7%、驗收 27.4%
- **Python**（2 個 repo）：單元測試 5/13（38.5%）、驗收測試 1/5（20.0%）；每個 repo 通過率的平均：單元 50.0%、驗收 50.0%；依程式碼行數加權：單元 37.2%、驗收 37.2%
- **C++**（1 個 repo）：單元測試 3/3（100.0%）、驗收測試 0/3（0.0%）；每個 repo 通過率的平均：單元 100.0%、驗收 0.0%；依程式碼行數加權：單元 100.0%、驗收 0.0%

| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|
| area_calculation | cpp | 3/3 | 0/3 | partial | 8/11 | 9.2 | 183 |
| particle-swarm-optimization | python | 5/5 | 1/1 | done | 4/4 | 1.9 | 25 |
| readtime | python | 0/8 | 0/4 | done | 4/4 | 2.2 | 26 |

參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）：GPT-4-Turbo-0125 驗收 7.1%、單元 8.0%；GPT-4-Turbo-1106 驗收 6.9%、單元 6.8%；GPT-3.5-Turbo 驗收 4.2%、單元 4.3%；DeepSeek-Coder-33B-Instruct 驗收 4.4%、單元 5.5%；CodeLlama-34B-Instruct 驗收 0.6%、單元 0.5%

## 每個 repo

### area_calculation：單元 3/3、驗收 0/3（partial，9.2 分鐘）
- 整體驗證（agent 自己的）：[ERROR] 靜態檢查或建置沒有通過（建置：make）
  - 1. done（2 次、17 步）實作 Shape 基礎類別定義；檔案 ['include/Shape.h']
  - 2. done（1 次、5 步）實作 Shape 基礎類別實作；檔案 ['src/Shape.cpp']
  - 3. done（1 次、9 步）實作 Circle 類別定義與實作；檔案 ['include/Circle.hpp']
  - 4. done（1 次、8 步）實作 Rectangle 類別定義與實作；檔案 ['include/Rectangle.h']
  - 5. done（1 次、9 步）實作 Square 類別定義與實作；檔案 ['include/Square.hpp']
  - 6. done（1 次、10 步）實作 Rectangle 類別實作；檔案 ['src/Rectangle.cpp']
  - 7. done（1 次、10 步）實作 Circle 類別實作；檔案 ['src/Circle.cpp']
  - 8. skipped（2 次、11 步）實作 Square 類別實作；檔案 ['src/Square.cpp']
  - 9. done（1 次、3 步）實作 main.cpp 邏輯與 I/O；檔案 ['src/main.cpp']
  - 10. skipped（2 次、19 步）更新 Makefile 以支援所有檔案；檔案 ['makefile']
  - 11. failed（2 次、11 步）修正整體驗證的失敗；檔案 ['include/Circle.hpp', 'include/Rectangle.h', 'include/Shape.h', 'include/Square.hpp', 'makefile', 'src/Circle.cpp']
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
/usr/bin/ld: src/Shape.o:(.data.rel+0x20): undefined reference to `__gcov_merge_add'
/usr/bin/ld: src/Rectangle.o: in function `_sub_I_00100_0':
Rectangle.cpp:(.text+0x5a0): undefined reference to `__gcov_init'
/usr/bin/ld: src/Rectangle.o: in function `_sub_D_00100_1':
Rectangle.cpp:(.text+0x5af): undefined reference to `__gcov_exit'
/usr/bin/ld: src/Rectangle.o:(.data.rel+0x20): undefined reference to `__gcov_merge_add'
collect2: error: ld returned 1 exit status
make: *** [makefile:20: shape_calculator] Error 1
```

### particle-swarm-optimization：單元 5/5、驗收 1/1（done，1.9 分鐘）
- 整體驗證（agent 自己的）：[PASS] 檢查 3 個檔案（這個 coding job 改過的檔案；語法、未定義名稱、專案內匯入）：沒有發現問題
  - 1. done（1 次、4 步）實作成本函數：Sphere Function；檔案 ['pso/cost_functions.py']
  - 2. done（1 次、2 步）建立 PSO 套件結構；檔案 ['pso/__init__.py']
  - 3. done（1 次、6 步）實作 Particle 類別；檔案 ['pso/pso_simple.py']
  - 4. done（1 次、3 步）實作 PSO 核心 minimize 函式；檔案 ['pso/pso_simple.py']
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

### readtime：單元 0/8、驗收 0/4（done，2.2 分鐘）
- 整體驗證（agent 自己的）：[PASS] 檢查 4 個檔案（這個 coding job 改過的檔案；語法、未定義名稱、專案內匯入）：沒有發現問題
  - 1. done（1 次、3 步）實作 Result 類別結構與方法；檔案 ['readtime/result.py']
  - 2. done（1 次、2 步）建立 readtime 套件初始化檔案；檔案 ['readtime/__init__.py']
  - 3. done（1 次、5 步）實作 utils.py 的內容解析與計算邏輯；檔案 ['readtime/utils.py']
  - 4. done（1 次、5 步）實作 api.py 的介面函數；檔案 ['readtime/api.py']
- 單元測試輸出（尾巴）：
```
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_empty - T...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_plain_text_null - Ty...
FAILED unit_tests/test_check_data.py::BaseTestCase::test_unsupported_format
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm - TypeErr...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_html - Ty...
FAILED unit_tests/test_custom_wpm.py::BaseTestCase::test_custom_wpm_markdown
FAILED unit_tests/test_transitions.py::BaseTestCase::test_transitions - TypeE...
8 failed in 0.03s
```
- 驗收測試輸出（尾巴）：
```

acceptance_tests/test_readtime.py:11: TypeError
=========================== short test summary info ============================
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_can_add - TypeEr...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_html - TypeError...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_markdown - TypeE...
FAILED acceptance_tests/test_readtime.py::BaseTestCase::test_plain_text - Typ...
4 failed in 0.03s
```
