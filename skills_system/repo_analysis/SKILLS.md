# repo_analysis：找檔案、讀文件與 log、分析程式

在工作目錄底下的檔案裡找答案：程式碼、文件、設定檔（yaml、xml、launch）與文字的 log 檔（.log、.txt 這種一行一則的紀錄）。找檔案、數數量、列出提到一段文字的行、讀文件、看程式的定義與呼叫；只讀檔案，不改任何東西。
不包含：正在跑的系統（容器、ROS 2 的 topic 與 node、調度系統、機器人現在的狀態）與錄製的數據（MCAP 錄製檔，和裡面的 /rosout 與 topic）——那些要問系統本身、用數據的工具，不是讀檔案。

## 複合技能
- [py_usage](py_usage.md) — 程式裡的一個名稱（函式、方法、類別、變數）定義在哪、哪裡呼叫或用到（在 .py 檔裡照語法找：每一處的檔案、行號與所在的函式，各檔案用了幾次、總共幾次）
- [count_in_scope](count_in_scope.md) — 數範圍裡（目錄、檔案名稱的寫法、不含的子目錄）一段文字出現在幾行（各檔案幾筆、總共幾筆），或名稱符合的檔案有幾個
- [find_lines](find_lines.md) — 在範圍裡（目錄或檔案、檔案名稱的寫法、不含的子目錄）的文字檔（log、設定檔、文件、程式碼）找一段文字，列出提到它的每一行與前後兩行（檔案、行號與內容由程式從檔案取），也算好每個檔案幾筆：答得了在哪幾行、那幾行寫了什麼（log 的時間與訊息、設定的值）
- [doc_lookup](doc_lookup.md) — 照指定的一份文件（規格書、手冊、說明）回答它寫了什麼：在文件裡搜問題提到的名稱，看原文挑出回答問題的那幾行（附檔案、行號）；文件提到別的編號或名稱時在同一份文件接著找
- [cpp_symbol](cpp_symbol.md) — C++ 程式（.h、.hpp、.cpp、.cc）裡的類別、函式、成員或設定：搜問題提到的名稱與前後幾行，看原文挑出定義、宣告、呼叫或設定的值（附檔案、行號）；原文提到的成員函式或型別接著找
- [config_trace](config_trace.md) — 一個參數、topic、節點或 launch 檔在 launch、設定檔（yaml、xml）與程式（.py、C++）裡怎麼接起來：誰設定、值多少、remap 成什麼、誰發布與訂閱、程式哪裡讀；一站一站接著找（附檔案、行號）

## 工具
- [search_text](../tools/search_text.md)
- [find_file](../tools/find_file.md)
- [list_dir](../tools/list_dir.md)
- [view_file](../tools/view_file.md)
- [code_ast_reader](../tools/code_ast_reader.md)
- [result_list](../tools/result_list.md)
- [result_grep](../tools/result_grep.md)
- [result_view](../tools/result_view.md)

## 公佈欄的工具
- [search_text](../tools/search_text.md)
- [find_file](../tools/find_file.md)
- [list_dir](../tools/list_dir.md)
- [view_file](../tools/view_file.md)
- [code_ast_reader](../tools/code_ast_reader.md)
- [code_defs](../tools/code_defs.md)
- [py_refs](../tools/py_refs.md)
