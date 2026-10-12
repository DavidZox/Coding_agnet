"""code_view：帶行號讀程式檔——整份、某一段（--from／--lines），或某個函式／類別（--symbol，Python 用 AST 找範圍）。

--symbol 的範圍：Python 用 AST，C／C++ 用 _cpp_common 的掃描器（有本體的定義優先於標頭裡的宣告）。
跟 view_file（cat_cmd.py）的差別：每行前面有行號（`  12| 內容`），可以只讀一段，長檔案預設只給開頭並說明還有多少行、
怎麼繼續讀；要修改檔案時，行號讓模型與使用者對得上「改的是哪裡」（寫入技能會自動剝掉被抄進去的行號前綴）。
"""
import ast
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc

WHOLE_MAX_LINES = 400      # 不超過這麼多行就整份顯示
DEFAULT_LINES = 250        # 長檔案預設顯示的行數
MAX_LINES = 600            # 一次最多顯示幾行
MAX_LINE_CHARS = 400
USAGE = ("用法: scripts/code_view_cmd.py <檔案> [--from 行號] [--lines 行數] [--symbol 名稱]\n"
         f"  不給範圍時：{WHOLE_MAX_LINES} 行以內整份顯示，更長的只顯示前 {DEFAULT_LINES} 行；--lines 上限 {MAX_LINES}；"
         "--symbol 只看某個函式或類別（Python 例如 load_config、Inventory.remove；C／C++ 例如 Circle::area、parse_shape）。")


def parse_args(argv):
    opts = {"path": None, "start": None, "count": None, "symbol": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--from", "--lines"):
            if i + 1 >= len(argv) or not argv[i + 1].lstrip("L").isdigit():
                return None, f"[ERROR] {a} 後面需要數字。\n{USAGE}"
            n = int(argv[i + 1].lstrip("L"))
            if a == "--from":
                opts["start"] = max(1, n)
            else:
                opts["count"] = max(1, min(MAX_LINES, n))
            i += 2
            continue
        if a == "--symbol":
            if i + 1 >= len(argv):
                return None, f"[ERROR] --symbol 後面需要函式或類別名稱。\n{USAGE}"
            opts["symbol"] = argv[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            return None, f"[ERROR] 不認識的選項 {a}。\n{USAGE}"
        if opts["path"] is not None:
            return None, f"[ERROR] 一次只能看一個檔案（收到 {opts['path']} 與 {a}）。\n{USAGE}"
        opts["path"] = a
        i += 1
    if not opts["path"]:
        return None, f"[ERROR] 沒有給檔案路徑。\n{USAGE}"
    return opts, None


def find_symbol(text, symbol):
    """Python：名稱（或 類別.方法）→ (起始行含裝飾器, 結束行)；找不到回 (None, 可能的名稱 list)。"""
    tree = ast.parse(text)
    parts = symbol.split(".")
    candidates = []

    def walk(body, prefix):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{node.name}"
                candidates.append((name, node))
                if isinstance(node, ast.ClassDef):
                    walk(node.body, name + ".")

    walk(tree.body, "")
    exact = [n for name, n in candidates if name == symbol]
    if not exact and len(parts) == 1:
        exact = [n for name, n in candidates if name.split(".")[-1] == symbol]
    if not exact:
        return None, [name for name, _ in candidates]
    node = exact[0]
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return (start, node.end_lineno), [name for name, _ in candidates if name.split(".")[-1] == symbol.split(".")[-1]]


def _norm(name):
    return re.sub(r"\s+", "", re.sub(r"<[^<>]*>", "", name))


def find_cpp_symbol(text, symbol):
    """C／C++：名稱、類別::方法 或 類別.方法 → ((起始行, 結束行), 同名的 list)；找不到回 (None, 檔案裡的名稱 list)。
    有本體的定義優先於宣告（標頭裡的宣告、.cpp 裡的定義）。"""
    import _cpp_common as cp
    want = _norm(symbol.replace(".", "::"))
    ents = [e for e in cp.scan(text) if e["name"] and e["kind"] not in ("namespace",)]

    def full(e):
        owner = cp.owner_name(e["cls"]) if e["cls"] else ""
        return _norm(e["name"] if "::" in e["name"] or not owner else f"{owner}::{e['name']}")

    names = list(dict.fromkeys(full(e) for e in ents))
    exact = [e for e in ents if full(e) == want or full(e).endswith("::" + want)]
    if not exact and "::" not in want:
        exact = [e for e in ents if full(e).split("::")[-1] == want]
    if not exact:
        return None, names
    exact.sort(key=lambda e: (e["decl"], e["line"]))
    e = exact[0]
    return (e["line"], e["end"]), [full(x) for x in exact]


def main(argv):
    opts, err = parse_args(argv)
    if err:
        return err
    path, err = cc.resolve_path(opts["path"])
    if err:
        return err
    if not os.path.exists(path):
        import _path_common
        hint = _path_common.suggest(path, want="file")
        return (f"[ERROR] 檔案不存在：{opts['path']}（目前工作目錄 {cc.base_root()}）。"
                + (f"{hint}。" if hint else "找檔名用 find_file，看專案有哪些檔案用 repo_map。"))
    if os.path.isdir(path):
        return f"[ERROR] {opts['path']} 是目錄：看目錄用 list_dir 或 repo_map。"
    if cc.is_binary(path):
        return f"[ERROR] {opts['path']} 是二進位檔，不能用文字顯示。"
    if os.path.getsize(path) > 5 * cc.MAX_FILE_BYTES:
        return f"[ERROR] {opts['path']} 超過 5MB，不是一般的程式檔；請用 code_search 找要看的位置。"
    text = cc.read_text(path)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    total = len(lines)
    rel = cc.rel_to_root(path)
    lang = cc.language_of(path) or "文字"
    if total == 0:
        return f"[PASS] {rel}（空檔案，0 行）"

    note = ""
    if opts["symbol"]:
        if lang not in ("Python", "C", "C++", "C/C++ 標頭"):
            return f"[ERROR] --symbol 目前只支援 Python 與 C／C++ 檔；{rel} 請用 --from／--lines 指定範圍，或 code_search 找位置。"
        try:
            found, names = find_symbol(text, opts["symbol"]) if lang == "Python" else find_cpp_symbol(text, opts["symbol"])
        except SyntaxError as e:
            return f"[ERROR] {rel} 有語法錯誤（第 {e.lineno} 行：{e.msg}），沒辦法用 --symbol；改用 --from {max(1, (e.lineno or 1) - 10)} --lines 40 看那一段。"
        if found is None:
            want = opts["symbol"].split(".")[-1].lower()
            near = [n for n in names if want in n.lower()]
            near += [n for n in names if n not in near and difflib.get_close_matches(want, [n.split(".")[-1].lower()], n=1, cutoff=0.6)]
            near = near[:8]
            listed = "、".join(near or names[:12]) or "（這個檔案沒有函式或類別）"
            return f"[ERROR] {rel} 裡找不到 {opts['symbol']}。這個檔案有：{listed}"
        start, end = found
        if len(names) > 1:
            note = f"（有 {len(names)} 個同名的定義，顯示第一個；要指定請用 類別.方法）"
    else:
        start = opts["start"] or 1
        if start > total:
            return f"[ERROR] 起始行 {start} 超過檔案總行數 {total}。"
        if opts["count"]:
            end = min(total, start + opts["count"] - 1)
        elif opts["start"] is None and total <= WHOLE_MAX_LINES:
            end = total
        else:
            end = min(total, start + DEFAULT_LINES - 1)
    shown = [ln if len(ln) <= MAX_LINE_CHARS else ln[:MAX_LINE_CHARS] + "…（這一行太長，已截斷）" for ln in lines[start - 1:end]]
    rest = f"；之後還有 {total - end} 行（--from {end + 1} 繼續）" if end < total else ""
    head = (f"[PASS] {rel}（共 {total} 行，{lang}）" + ("整份" if start == 1 and end == total else f"第 {start}～{end} 行")
            + rest + note + "：")
    return head + "\n" + cc.numbered(shown, start)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_view 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
