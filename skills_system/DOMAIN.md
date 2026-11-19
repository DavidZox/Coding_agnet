# DOMAIN：領域的清單（新架構的高階分流用）

> 每個領域一行，連到它的 `SKILLS.md`（領域的說明、不包含什麼、複合技能與工具都寫在那裡）。主對話的 system prompt 裡的「領域」一節
> 由程式從那裡組（`agent_core/orchestrator.py`），這份檔案不直接給模型讀。
> 主對話把這些領域的問題「交給領域」；領域的工具（下面〈共用的工具〉以外的）不給主對話直接用：有複合技能的領域由中階照寫好的做法做，
> 沒有複合技能、或中階沒有做完也沒有報告時（沒有適合的做法、失敗、使用者取消），在子工作階段裡用領域的工具一步一步做。

## 領域
- [repo_analysis](repo_analysis/SKILLS.md)

## 共用的工具
> 每一層都直接用：回顧存檔（追問時看之前的結果）；列目錄、找檔案（只看有什麼、在哪裡，不讀內容：凍結的工具的事——數據資料夾、
> 改設定檔前找檔案——主對話也要用）。讀內容的（搜文字、看檔案、分析程式）交給領域。
- [list_dir](tools/list_dir.md)
- [find_file](tools/find_file.md)
- [result_list](tools/result_list.md)
- [result_grep](tools/result_grep.md)
- [result_view](tools/result_view.md)
