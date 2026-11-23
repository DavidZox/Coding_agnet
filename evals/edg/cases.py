"""第 1 級修正的真模型評測的題目（evals/edg/run.py；故意製造錯誤，參數錯觸發第 1 級）。

每一題是一張只有一個工具節點的決策圖，參數故意錯一個地方（都是實際會犯的錯：選項寫錯、關鍵字含空白沒包成一個、路徑打錯字、
行號超過檔案、一次給兩個目錄、只給路徑沒給關鍵字）。工作目錄是真實專案評測的快照（amr_base/src，唯讀）。
- want＝fixed：修正之後要跑成功，收據的欄位要對（receipt：欄位 → 值；endswith 比路徑的結尾，endswith_all 是清單裡每一個路徑；
  不分大小寫的寫 ci）。範圍也要對：搜尋、找檔案的起點跟子目標一樣（修正不能把範圍放大）。
- want＝not_fixable：改參數修不好（要換工具、要使用者決定），修正要說 fixable=false、不重跑。
保留組（set＝holdout）不拿來調 prompts/edg/ 的字（同真實專案評測）。
"""

CASES = [
    {"id": "find_type_word", "set": "main", "goal": "在 amr_base_sw 找名稱含 DockDecision 的檔案（只要檔案，不要目錄）",
     "node": {"tool": "find_file", "args": ["--type", "file", "DockDecision", "amr_base_sw"]},
     "want": "fixed", "receipt": {"type": "f", "keyword": "DockDecision", "root": {"endswith": "/amr_base_sw"}}},
    {"id": "search_bad_option", "set": "main", "goal": "在 amr_base_sw/docs 搜 PRE_DOCK_ALIGN 出現在哪幾行",
     "node": {"tool": "search_text", "args": ["-o", "PRE_DOCK_ALIGN", "amr_base_sw/docs"]},
     "want": "fixed", "receipt": {"pattern": {"ci": "PRE_DOCK_ALIGN"}, "paths": {"endswith_all": "/amr_base_sw/docs"}}},
    {"id": "search_split_keyword", "set": "main", "goal": "在 amr_base_hw 搜「emergency stop」這個詞出現在哪裡",
     "node": {"tool": "search_text", "args": ["emergency", "stop", "amr_base_hw"]},
     "want": "fixed", "receipt": {"pattern": {"ci": "emergency stop"}, "paths": {"endswith_all": "/amr_base_hw"}}},
    {"id": "view_typo_path", "set": "main", "goal": "看 amr_base_sw 裡 RMF 整合報告的開頭",
     "node": {"tool": "view_file", "args": ["amr_base_sw/RMF_Integration_Reprot.md", "--lines", "40"]},
     "want": "fixed", "receipt": {"path": {"endswith": "amr_base_sw/RMF_Integration_Report.md"}}},
    {"id": "view_from_beyond", "set": "main", "goal": "看 hw_bringup 的 package.xml 最後面寫了什麼",
     "node": {"tool": "view_file", "args": ["amr_base_hw/hw_bringup/package.xml", "--from", "5000"]},
     "want": "fixed", "receipt": {"path": {"endswith": "amr_base_hw/hw_bringup/package.xml"}}},
    {"id": "list_two_dirs", "set": "main", "goal": "列出 amr_base_hw 底下有哪些套件",
     "node": {"tool": "list_dir", "args": ["amr_base_hw", "amr_base_sw"]},
     "want": "fixed", "receipt": {"path": {"endswith": "/amr_base_hw"}}},
    {"id": "ast_not_python", "set": "main", "goal": "看 CLaserOdometry2DNode.cpp 定義了哪些函式",
     "node": {"tool": "code_ast_reader", "args": ["amr_base_hw/rf2o_laser_odometry/src/CLaserOdometry2DNode.cpp"]},
     "want": "not_fixable"},
    {"id": "find_only_path", "set": "main", "goal": "在 amr_base_hw 裡找名稱含 hw_bringup 的檔案或目錄",
     "node": {"tool": "find_file", "args": ["./amr_base_hw"]},
     "want": "fixed", "receipt": {"keyword": "hw_bringup", "root": {"endswith": "/amr_base_hw"}}},
    {"id": "search_only_path_unknown", "set": "main", "goal": "在 amr_base_sw/config 搜使用者要的那個參數（使用者還沒說是哪一個）",
     "node": {"tool": "search_text", "args": ["./amr_base_sw/config"]},
     "want": "not_fixable"},
    {"id": "ho_view_lines_zero", "set": "holdout", "goal": "看 hw_bringup 的 package.xml 開頭幾行",
     "node": {"tool": "view_file", "args": ["amr_base_hw/hw_bringup/package.xml", "--lines", "0"]},
     "want": "fixed", "receipt": {"path": {"endswith": "amr_base_hw/hw_bringup/package.xml"}}},
    {"id": "ho_find_only_path_unknown", "set": "holdout", "goal": "在 amr_base_sw/config 找使用者說的那個設定檔（使用者還沒說檔名）",
     "node": {"tool": "find_file", "args": ["./amr_base_sw/config"]},
     "want": "not_fixable"},
]

BY_ID = {c["id"]: c for c in CASES}
assert len(BY_ID) == len(CASES)


def receipt_ok(receipt, want):
    """收據的欄位跟題目要的一樣：(True, "") 或 (False, 哪一個欄位不對)。"""
    for field, exp in (want or {}).items():
        got = (receipt or {}).get(field)
        if isinstance(exp, dict) and "endswith" in exp:
            ok = isinstance(got, str) and got.endswith(exp["endswith"])
        elif isinstance(exp, dict) and "endswith_all" in exp:
            ok = isinstance(got, list) and bool(got) and all(isinstance(g, str) and g.endswith(exp["endswith_all"]) for g in got)
        elif isinstance(exp, dict) and "ci" in exp:
            ok = isinstance(got, str) and got.lower() == exp["ci"].lower()
        else:
            ok = got == exp
        if not ok:
            return False, f"收據的 {field} 是 {got!r}，要的是 {exp!r}"
    return True, ""
