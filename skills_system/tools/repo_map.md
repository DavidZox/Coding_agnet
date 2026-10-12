---
type: Tool
title: 專案地圖
description: 整個專案的目錄樹、每個程式檔的結構大綱（類別、函式與行號範圍）、測試檔與建議的測試指令、C／C++ 的建置系統、git 狀態。
version: 1.0.0
dependencies: ["python3", "git（可選）"]
---

# 用途
第一次接觸一個專案、或要回答「這個專案的架構」「某個功能在哪個檔案」時先用它：檔案數、行數、語言、測試指令都由腳本算好，直接引用。Python 用 AST 取大綱（`class`／`def`、參數、`L起-迄` 行號）；C／C++ 用掃描器（namespace、class、方法的宣告與定義、函式、gtest 的 `TEST`，含行號範圍），並列出建置系統（CMake／Makefile）與 C／C++ 測試怎麼跑；JavaScript／TypeScript／Go／Rust／Java 用宣告比對。ROS 2 的 colcon 工作區另外列出每個套件與建置類型（ament_cmake／ament_python）。自動略過 `.git`、`__pycache__`、`node_modules`、`venv`、`build` 等目錄，以及 `.gitignore` 排除的目錄。輸出太長時會逐步省略細節並說明怎麼縮小範圍。

# 語法
`EXECUTE: scripts/repo_map_cmd.py [path] [--filter 關鍵字] [--no-outline] [--max-chars N]`
* `path`：專案目錄，預設目前工作目錄。`--filter`：只列路徑含關鍵字的檔案。`--no-outline`：只列檔名與行數。

# 範例
`EXECUTE: scripts/repo_map_cmd.py .`　`EXECUTE: scripts/repo_map_cmd.py ~/ws/src/my_pkg --filter launch`

# 回傳
`[PASS] 專案地圖 <path>：N 個檔案、M 個子目錄（Python 30、…）`，第二行是測試檔數量、建議的測試指令（C／C++ 專案是 `code_test`）、說明檔、git 狀態，C／C++ 專案再一行建置系統，ROS 2 工作區再一行套件清單，之後是目錄樹與大綱。

# 異常
路徑不存在或不是目錄：`[ERROR]`；看單一檔案的結構用 `code_ast_reader`，看內容用 `code_view`。
