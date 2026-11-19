# DOMAIN：領域的清單（新架構的高階分流用）

> 每個領域一行，連到它的 `SKILLS.md`（領域的說明、不包含什麼、複合技能與工具都寫在那裡）。主對話的 system prompt 裡的「領域」一節
> 由程式從那裡組（`agent_core/orchestrator.py`），這份檔案不直接給模型讀。
> 主對話把這些領域的問題「交給領域」；領域的工具（下面〈共用的工具〉以外的）不給主對話直接用，中階說沒有適合的做法時才放行。

## 領域
- [repo_analysis](repo_analysis/SKILLS.md)

## 共用的工具
> 每一層都直接用：回顧存檔（追問時看之前的結果）。
- [result_list](tools/result_list.md)
- [result_grep](tools/result_grep.md)
- [result_view](tools/result_view.md)
