---
type: Tool
title: 執行測試
description: 跑專案的測試——Python 用 pytest、C／C++ 建置後用 GoogleTest（CMake＋ctest、make test，或直接用 g++ 編譯）；通過／失敗數由腳本算好，失敗附細節、編譯失敗附整理過的錯誤。
version: 2.1.0
dependencies: ["python3", "pytest", "g++／gcc、GoogleTest（C／C++ 專案）", "cmake、ninja（CMake 專案）"]
---

# 用途
回答「測試有沒有過」、確認修改沒有弄壞東西。不給路徑時整個專案都跑：有 Python 測試（`test_*.py`／`*_test.py`）就跑 pytest，有 C／C++ 測試就建置後跑 gtest，兩種都有就兩種都跑。C／C++ 依序找：CMakeLists.txt 註冊了測試 → `cmake` 設定 `build/`、建置、`ctest`；Makefile（或 `makefile_test`）有 `test` 目標 → `make test`；只有測試原始檔（`test_*.cpp`、`tests/` 底下）→ 直接用 g++／gcc 編譯並連結 gtest。Python 用專案的虛擬環境（工作區的 `.venv`／`venv`，或 Coding 面板設定的 Python），沒有就用 harness 的 Python；那個 Python 沒有 pytest 時回報要怎麼安裝，不會改用別的方式。
ROS 2 的 colcon 工作區（`src/<套件>/package.xml`）每個套件分開跑：C++ 只編譯那個套件（include 目錄照套件的 `include/`），Python 在套件目錄跑 pytest。這台主機沒有 ROS 2 時，需要 rclcpp／rclpy／ament_flake8 等外部依賴的測試檔會跳過並說明（不是程式的錯誤），其他照跑。

# 語法
`EXECUTE: scripts/code_test_cmd.py [測試檔、目錄或 檔案::測試名稱 ...] [-k 關鍵字] [--lang python|cpp] [--coverage] [--timeout 秒]`
* 不給路徑＝整個專案；`--timeout` 預設 300 秒、上限 570；其他 pytest 選項（`-x`、`--maxfail=1`…）照傳給 pytest。
* `--coverage`：另外量覆蓋率——Python 用 coverage.py、C／C++ 用 `--coverage` 編譯＋gcovr，在專案的暫存副本裡量（工作區不會留下 .coverage、.gcda 或用 coverage 旗標編的 .o）。結果列出整體與每個檔案的行／分支覆蓋率，以及**還沒測到的行號**（＊＝只測到部分分支的行），補測試照著那幾行補。

# 範例
`EXECUTE: scripts/code_test_cmd.py`　`EXECUTE: scripts/code_test_cmd.py tests/test_store.py -k remove`
`EXECUTE: scripts/code_test_cmd.py tests/test_shapes.cpp::CircleTest.Area`　`EXECUTE: scripts/code_test_cmd.py src/my_pkg`
`EXECUTE: scripts/code_test_cmd.py unit_tests --coverage`（跑測試並量覆蓋率）

# 回傳
`[PASS] 測試全部通過：pytest（…） 12 passed；gtest（CMake＋ctest） 7 passed` 或 `[ERROR] 測試失敗：gtest（…） 1 failed、6 passed` + 失敗的細節（pytest 的 assert 實際值、gtest 的期望值與實際值、當掉的測試）；編譯失敗是 `編譯失敗（N 個錯誤）` + 每個錯誤的 `檔案:行號: error` 與那一行原始碼，連結錯誤（宣告了沒實作）另外列出。數字照抄。跳過缺外部依賴的測試時，摘要寫「（跳過 N 個缺外部依賴的測試檔）」；一個測試都跑不了時是 `[ERROR] 沒辦法在這台主機跑這些測試（缺外部依賴，不是程式的錯誤）`——不要為了這個改程式或安裝套件，照說明到有 ROS 2 的環境 `colcon test`。

# 異常
沒有收集到任何測試（測試路徑、名稱寫錯，或 `-k` 篩不到）、逾時、沒有 pytest／cmake／gtest：`[ERROR]` 並說明要使用者安裝什麼。一個測試都沒跑到**不算通過**。
`--coverage` 量不到時（這個 Python 沒有 coverage、沒有 gcovr／gcov）在覆蓋率那一段說明，測試結果照常回報。
