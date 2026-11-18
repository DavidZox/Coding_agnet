"""result_list：列出工具結果存檔的索引（編號、時間、腳本、狀態、大小、當時的任務、摘要回答），先看這個再決定要 result_grep 哪一個。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _results_common import INDEX_NAME, current_session, list_result_files, results_dir
import _receipt_common as receipt  # noqa: E402

DEFAULT_N = 20
MAX_N = 100
USAGE = (f"用法: scripts/result_list_cmd.py [N] [--all]\n"
         f"  預設列目前 session 最近 {DEFAULT_N} 筆（新→舊）；--all 連同之前 session 的存檔一起列。")


def parse_args(argv):
    n, show_all = DEFAULT_N, False
    for a in argv:
        if a == "--all":
            show_all = True
        elif a.isdigit():
            n = max(1, min(MAX_N, int(a)))
        else:
            return None, None, f"[ERROR] 不認識的參數 {a!r}。\n{USAGE}"
    return n, show_all, None


def main(argv):
    n, show_all, err = parse_args(argv)
    if err:
        return receipt.fail(err, "args")
    d = results_dir()
    files = list_result_files(d)
    scope = "all" if show_all else "session"
    if not files:
        receipt.result("empty", counts={"total": 0, "all_sessions": 0, "shown": 0}, scope=scope)
        return f"[PASS] 目前沒有任何工具結果存檔（{d}）；執行過技能後才會有。"
    index = os.path.join(d, INDEX_NAME)
    lines = []
    if os.path.exists(index):
        with open(index, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.startswith("#")]
    sess = current_session()
    by_file = {}
    for ln in lines:
        parts = [p.strip() for p in ln.split(" | ")]
        if len(parts) >= 6:
            by_file[parts[5]] = ln
    chosen = [f for f in files if show_all or not sess or f[0] == sess]
    if not chosen:
        receipt.result("empty", counts={"total": 0, "all_sessions": len(files), "shown": 0}, scope=scope)
        return (f"[PASS] 目前 session 還沒有工具結果存檔（之前的 session 共 {len(files)} 筆，加 --all 可列出）。")
    in_scope = len(chosen)
    chosen = chosen[-n:][::-1]   # 新→舊
    receipt.result("pass", counts={"total": in_scope, "all_sessions": len(files), "shown": len(chosen)},
                   items=[{"id": rid, "session": sess_id, "script": stem, "file": fn} for sess_id, rid, stem, fn in chosen], scope=scope)
    head = (f"[PASS] 工具結果存檔：{'全部' if show_all or not sess else '目前 session'} 共 {len([f for f in files if show_all or not sess or f[0] == sess])} 筆"
            f"（全部 session {len(files)} 筆），列出最近 {len(chosen)} 筆（新→舊；依問題重新提煉用 result_recall <編號> \"<問題>\"、"
            f"找字串用 result_grep <編號> <關鍵字>、看原文用 result_view <編號>）：")
    out = [head]
    for sess_id, rid, stem, fn in chosen:
        ln = by_file.get(fn)
        if ln:
            out.append(ln)
        else:   # index.md 沒有這一行（寫入失敗、或手動放進來的檔）：大小是檔案的位元組數
            out.append(f"#{rid} | ? | {stem} | ? | {os.path.getsize(os.path.join(d, fn))} bytes | {fn} | 任務：？ | 回答：")
    return "\n".join(out)


if __name__ == "__main__":
    receipt.main(main, "result_list")
