---
type: Tool
title: 靜態檢查程式碼
description: 不執行程式的檢查：Python 的語法、未定義的名稱、專案內的 import 對不對得上；C／C++ 用 gcc／g++ 編譯檢查（未宣告的名稱、型別、簽名不一致、忘了 return）。
version: 2.0.0
dependencies: ["python3", "g++／gcc（C／C++）"]
---

# 用途
改完程式後確認沒有改壞：Python 語法、呼叫了沒定義的函式或忘了 import、`from 模組 import 名稱` 的名稱在那個專案檔案裡不存在（改了 A 檔的名稱卻沒改 B 檔）；C／C++ 用編譯器編譯一次（輸出丟掉，不留檔案；有 `compile_commands.json` 就照它的參數），改的是標頭時編譯 `#include` 它的原始檔；JSON／TOML／YAML 的格式。`--spec 規格文件` 再對照文件 API 行（`+name(…)`、`- name(…): …`）的參數個數（敘述說有預設值的參數算可選）——照規格實作時，簽名跟規格不符（多要求參數、該有預設值卻沒有）會列出來。測試檔在模組層級替換 `sys.modules` 或專案模組／類別的屬性（會污染同一次 pytest 的其他測試）也會列出來。coding worker 每一項做完都會自動跑一次。「有宣告沒實作」這種連結錯誤要等 `code_test` 建置時才看得到。ROS 2 的 colcon 工作區裡，每個檔案的 include 目錄與依賴照它所屬的套件；缺的標頭是 package.xml／CMakeLists.txt 宣告的外部依賴（這台主機沒有 ROS 2 時的 rclcpp 之類）時，那個檔案只檢查括號與結構、最後附說明，不算問題（不要為了這個改 #include）；專案自己的 #include 寫錯照樣列出。

# 語法
`EXECUTE: scripts/code_check_cmd.py [檔案或目錄 ...] [--spec 規格文件 ...]`
* 不給：coding job 中檢查這個 job 改過的檔案，否則檢查目前目錄的所有 Python 與 C／C++ 檔。

# 範例
`EXECUTE: scripts/code_check_cmd.py inventory`　`EXECUTE: scripts/code_check_cmd.py src/circle.cpp include/geometry/circle.hpp`

# 回傳
沒有問題：`[PASS] 檢查 N 個檔案（…）：沒有發現問題`；有問題：`[ERROR] … 發現 K 個問題` + 每個問題 `檔案:行號: 問題`（C／C++ 附那一行原始碼）。編譯器的警告另外列出，不影響通過。

# 異常
Python 未定義名稱的判斷不分作用域（寧可漏抓也不誤報）；模組用了 `from x import *` 時不檢查那個模組的名稱。
