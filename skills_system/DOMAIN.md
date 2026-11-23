# DOMAIN：領域的清單（交辦用）

> 每個領域一行，連到它的 `SKILLS.md`（領域的說明、不包含什麼、〈做法〉、有骨架的技能與工具都寫在那裡）。主 session 的 system prompt
> 的「交辦」一節與領域 session 的領域清單由程式從那裡組（`agent_core/orchestrator.py`、`agent_core/domain_session.py`），這份檔案不直接給模型讀。
> 主 session 把要用技能的事「交辦」給領域 session：它選領域、從那些領域的技能清單一次用一個技能做完；領域的工具（下面〈共用的工具〉以外的）
> 不給主 session 直接用。

## 領域
- [repo_analysis](repo_analysis/SKILLS.md)
- [robotics_infra](robotics_infra/SKILLS.md)
- [rmf_dispatch](rmf_dispatch/SKILLS.md)
- [data_analysis](data_analysis/SKILLS.md)
- [multimodal](multimodal/SKILLS.md)

## 共用的工具
> 每一層都直接用：回顧存檔（追問時看之前的結果）；列目錄、找檔案（只看有什麼、在哪裡，不讀內容：凍結的工具的事——數據資料夾、
> 改設定檔前找檔案——主對話也要用）。讀內容的（搜文字、看檔案、分析程式）交給領域。
- [list_dir](tools/list_dir.md)
- [find_file](tools/find_file.md)
- [result_list](tools/result_list.md)
- [result_grep](tools/result_grep.md)
- [result_view](tools/result_view.md)
