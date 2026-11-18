# repo_analysis：找檔案、讀文件、分析程式

在工作目錄底下的程式碼與文件裡找答案：找檔案、數數量、讀文件、看程式的定義與呼叫。只讀檔案，不改任何東西。
不包含：正在跑的系統（容器、ROS 2 的 topic 與 node、調度系統、機器人的狀態）與錄製的數據——那些要問系統本身，不是讀程式碼與文件。

## 複合技能
- [py_usage](py_usage.md) — 程式裡的一個名稱（函式、方法、類別、變數）定義在哪、哪裡呼叫或用到（在 .py 檔裡照語法找：每一處的檔案、行號與所在的函式，各檔案用了幾次、總共幾次）
- [count_in_scope](count_in_scope.md) — 數範圍裡（目錄、檔案名稱的寫法、不含的子目錄）一段文字出現在幾行（各檔案幾筆、總共幾筆），或名稱符合的檔案有幾個

## 工具
- [search_text](../tools/search_text.md)
- [find_file](../tools/find_file.md)
- [list_dir](../tools/list_dir.md)
- [view_file](../tools/view_file.md)
- [code_ast_reader](../tools/code_ast_reader.md)
- [result_list](../tools/result_list.md)
- [result_grep](../tools/result_grep.md)
- [result_view](../tools/result_view.md)
