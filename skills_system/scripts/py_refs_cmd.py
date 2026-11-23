"""py_refs：Python 的一個名稱在一個範圍（目錄或檔案，可以好幾個）裡的每一處——用 AST 分成定義、呼叫、import、指定、其他用到，每一處附
檔案、行號與所在的函式；各檔案幾處、總共幾處由程式算。複合技能 py_usage 由程式做的部分（search_text 找出提到名稱的 .py，每個檔案
code_ast_reader --refs）做成一次執行的工具（repo_analysis 的工具，領域 session 用）。

- 範圍：預設略過 _path_common.DEFAULT_EXCLUDES 的目錄（指定的路徑本身在裡面的照算），--exclude-dir 多略過；只看 Python 檔（.py、.pyw、
  .pyi、第一行是 python 的 #!；--include 改成只看這種檔名，含 / 時比對整個路徑）。先照字面挑出有這個名稱（整個字）的檔案，再用 code_ast_reader 的 _RefVisitor 分
  每一處：註解與字串裡提到的、名稱更長的相似名稱不算；import 不算呼叫。語法錯誤的檔案不算，計數寫在最後一行。
- --kind 只列一種（def、call、import、assign、ref）。範圍裡的 Python 一處都沒有時，另外照字面看範圍裡的 C／C++ 檔有沒有這個名稱（寫在回覆裡）。
收據（_receipt_common，欄位見規格的 receipt）：每一處一筆（路徑、行號、種類、所在的函式、那一行的原始碼；定義另有 qualname、in_class、
結束的行、有裝飾器的另記 decorator——定義的行號與範圍從 def／class 那一行算），每個檔案的數量（per_file）。
"""
import ast
import os
import re
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402
from _receipt_common import fail, main, result  # noqa: E402
from code_ast_reader_cmd import REF_KINDS, _RefVisitor, _is_python  # noqa: E402

TIMEOUT_SECONDS = 30
FILES_MAX = 5000            # 最多看幾份檔案
SHOWN_REFS = 400            # 最多列幾處（每個檔案的數量照樣全部算）
CPP_EXT = (".h", ".hh", ".hpp", ".hxx", ".c", ".cc", ".cpp", ".cxx")
BLOCKED = ("/", "/proc", "/sys", "/dev")
KINDS = ("def", "call", "import", "assign", "ref")
USAGE = ('用法: scripts/py_refs_cmd.py <名稱> [路徑…] [--exclude-dir <名稱>] [--include "<檔名寫法>"] [--kind <種類>]\n'
         '  名稱：一個 Python 的名稱（函式、方法、類別、變數；a.b 只寫最後一段）\n'
         '  路徑：目錄或檔案，可以好幾個，預設 .（目前工作目錄）；不能是 /。\n'
         '  --exclude-dir 名稱：多略過一個目錄（可重複）　--include "test_*.py"：只看這種檔名（可重複，含 / 時比對整個路徑；預設全部的 Python 檔）\n'
         '  --kind call：只列這幾種（def 定義、call 呼叫、import、assign 指定、ref 其他用到；幾種用 | 分開：def|call）')
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_args(argv):
    """解析命令列參數 → (選項 dict, 錯誤)。"""
    o = {"name": None, "paths": [], "exclude_dir": [], "include": [], "kind": []}
    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--exclude-dir", "--include", "--kind"):
            if i + 1 >= len(args):
                return None, f"[ERROR] {a} 後面需要值。\n{USAGE}"
            v = args[i + 1]
            if a == "--exclude-dir":
                o["exclude_dir"] += [x.strip("/") for x in pc.split_globs(v)]
            elif a == "--include":
                o["include"] += pc.split_globs(v)               # "test_*.py|*_test.py" 拆成兩種（_path_common.split_globs）
            else:
                kinds = [k.strip() for k in re.split(r"[|,，、]", v) if k.strip()]
                bad = [k for k in kinds if k not in KINDS]
                if bad or not kinds:
                    return None, f"[ERROR] --kind 要是 {'、'.join(KINDS)}（幾種用 | 分開：def|call），收到「{v}」。\n{USAGE}"
                o["kind"] = list(dict.fromkeys(o["kind"] + kinds))
            i += 2
            continue
        if a.startswith("-") and a != "-":
            return None, f"[ERROR] 不支援的選項 {a}。下一步：照下面的用法改。\n{USAGE}"
        if o["name"] is None:
            o["name"] = a
        else:
            o["paths"].append(a)
        i += 1
    if not o["name"]:
        return None, f"[ERROR] 沒有給要找的名稱。下一步：寫成 <名稱> [路徑]。\n{USAGE}"
    if "." in o["name"] and _NAME.match(o["name"].rsplit(".", 1)[-1]):
        return None, (f"[ERROR] 名稱要是一個 Python 的名稱，收到「{o['name']}」。下一步：a.b 只寫最後一段"
                      f"（{o['name'].rsplit('.', 1)[-1]}）。\n{USAGE}")
    if not _NAME.match(o["name"]):
        return None, (f"[ERROR] 名稱要是一個 Python 的名稱（英文字母或底線開頭，只有英數字與底線），收到「{o['name']}」。"
                      f"下一步：只寫名稱本身，不要寫成句子或路徑；找一段文字用 search_text。\n{USAGE}")
    o["paths"] = o["paths"] or ["."]
    return o, None


def _timeout_handler(signum, frame):
    raise TimeoutError


def _walk(roots, excludes):
    out, skipped = [], 0
    for root in roots:
        if os.path.isfile(root):
            out.append(root)
            continue
        for d, dirs, files in os.walk(root):
            keep = []
            for x in sorted(dirs):
                if x in excludes:
                    skipped += 1
                else:
                    keep.append(x)
            dirs[:] = keep
            out += [os.path.join(d, f) for f in sorted(files)]
    return list(dict.fromkeys(out)), skipped


def _read(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    return None if b"\0" in data[:8192] else data.decode("utf-8", errors="replace")


def execute(argv):
    o, err = parse_args(argv)
    if err:
        return fail(err, "args")
    roots = []
    for p in o["paths"]:
        if os.path.abspath(pc.expand(p)) in BLOCKED:
            return fail(f"[ERROR] 不搜 {p}：範圍太大。下一步：指定具體的目錄（例如專案或套件的目錄）。\n{USAGE}", "args")
        abs_path, perr = pc.resolve(p, "any")
        if perr:
            return fail(perr)
        roots.append(abs_path)
    excludes = set(pc.excludes_for(o["paths"])) | set(o["exclude_dir"])
    word = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(o['name'])}(?![A-Za-z0-9_])")
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
    refs, per_file, cpp_hits, scanned, syntax, timed_out, skipped_dirs, over = [], [], [], 0, [], False, 0, 0
    try:
        files, skipped_dirs = _walk(roots, excludes)
        over = max(0, len(files) - FILES_MAX)
        for path in files[:FILES_MAX]:
            is_py = pc.include_ok(path, o["include"]) if o["include"] else _is_python(path)   # 含 / 的比對整個路徑（同 search_text、find_file）
            if not is_py:
                if path.endswith(CPP_EXT):
                    text = _read(path)
                    if text and word.search(text):
                        cpp_hits.append(path)
                continue
            text = _read(path)
            if text is None:
                continue
            scanned += 1
            if not word.search(text):
                continue
            try:
                tree = ast.parse(text, filename=path)
            except (SyntaxError, ValueError):
                syntax.append(path)
                continue
            v = _RefVisitor(o["name"], text.split("\n"), path)
            v.visit(tree)
            got = sorted(v.out, key=lambda r: (r["line"], r["kind"]))
            if o["kind"]:
                got = [r for r in got if ("def" if r["kind"] in ("def", "class") else r["kind"]) in o["kind"]]
            if not got:
                continue
            refs += got
            row = {"path": path, "refs": len(got)}
            row.update({k: sum(1 for r in got if (r["kind"] in ("def", "class") if k == "def" else r["kind"] == k)) for k in KINDS})
            per_file.append(row)
    except TimeoutError:
        timed_out = True
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
    if timed_out and not scanned:
        return fail(f"[ERROR] 搜尋逾時（超過 {TIMEOUT_SECONDS} 秒）還沒有看完任何一份檔案。下一步：縮小範圍（更下層的目錄）。", "timeout")
    return _render(o, roots, refs, per_file, cpp_hits, scanned, syntax, timed_out, skipped_dirs, over, excludes)


def _render(o, roots, refs, per_file, cpp_hits, scanned, syntax, timed_out, skipped_dirs, over, excludes):
    scope = "、".join(pc.display(r) for r in roots)
    name = o["name"]
    totals = {k: sum(r[k] for r in per_file) for k in KINDS}
    counts = {"refs": len(refs), "files": len(per_file), "defs": totals["def"], "calls": totals["call"], "imports": totals["import"],
              "assigns": totals["assign"], "others": totals["ref"], "scanned": scanned}
    truncated = timed_out or over > 0
    result("pass" if refs else "empty", counts=counts, items=refs, truncated=truncated, per_file=per_file, name=name, paths=roots,
           kind=[REF_KINDS[k] for k in o["kind"]], exclude_dirs=sorted(excludes), cpp_files=cpp_hits[:20], syntax_errors=syntax[:20],
           timed_out=timed_out)
    only = f"（只算{'、'.join(REF_KINDS[k] for k in o['kind'])}）" if o["kind"] else ""
    tail = []
    if syntax:
        tail.append(f"{len(syntax)} 份語法錯誤的 Python 檔沒有算（{'、'.join(pc.display(p) for p in syntax[:3])}）")
    if over:
        tail.append(f"範圍裡的檔案超過 {FILES_MAX} 份，後面 {over} 份沒有看：縮小範圍")
    if timed_out:
        tail.append(f"逾時（{TIMEOUT_SECONDS} 秒）沒有看完：上面的數量不是全部，縮小範圍")
    if skipped_dirs:
        tail.append(f"略過了 {skipped_dirs} 個預設略過或指定略過的目錄（{'、'.join(sorted(excludes)[:8])}）")
    if not refs:
        msg = f"[PASS] 範圍 {scope} 的 Python 程式裡沒有「{name}」{only}（AST；看了 {scanned} 份 Python 檔，註解與字串裡提到的不算）。"
        if cpp_hits:
            msg += (f"範圍裡的 C／C++ 檔有這個名稱（照字面）：{'、'.join(pc.display(p) for p in cpp_hits[:5])}"
                    + (f" 等 {len(cpp_hits)} 份" if len(cpp_hits) > 5 else "") + "——用 search_text 或 code_defs 看那些檔案。")
        else:
            msg += "下一步：名稱可能拼錯或在範圍外：用 search_text 照字面找。"
        return msg + (f"\n（{'；'.join(tail)}）" if tail else "")
    head = (f"[PASS] 「{name}」在 {scope} 的 Python 程式裡出現 {len(refs)} 處、{len(per_file)} 份檔案（AST）{only}："
            + "、".join(f"{label} {totals[k]}" for k, label in REF_KINDS.items()))
    out, shown = [head], 0
    by_path = {}
    for r in refs:
        by_path.setdefault(r["path"], []).append(r)
    for row in per_file:
        parts = "、".join(f"{label} {row[k]}" for k, label in REF_KINDS.items() if row[k])
        out.append(f"## {pc.display(row['path'])}（{row['refs']} 處：{parts}）")
        for r in by_path[row["path"]]:
            if shown >= SHOWN_REFS:
                break
            shown += 1
            kind = "def" if r["kind"] in ("def", "class") else r["kind"]
            span = f"行 {r['line']}-{r['end']}" if kind == "def" and r.get("end") and r["end"] != r["line"] else f"行 {r['line']}"
            where = ("在 " + r["scope"] if r["scope"] else "模組層") + (f"；裝飾器在行 {r['decorator']}" if r.get("decorator") else "")
            out.append(f"  - {REF_KINDS[kind]} {span}（{where}）：{r['text']}")   # 縮排：提煉核對時上層的 ## 檔案 也算
    if len(refs) > SHOWN_REFS:
        tail.insert(0, f"只列前 {SHOWN_REFS} 處（共 {len(refs)} 處；數量照樣全部算）")
    out.append("（註解與字串裡提到的不算；import 不算呼叫" + ("；" + "；".join(tail) if tail else "") + "）")
    return "\n".join(out)


if __name__ == "__main__":
    main(execute, "py_refs")
