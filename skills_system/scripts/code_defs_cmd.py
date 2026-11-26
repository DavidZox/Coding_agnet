"""code_defs：程式列舉——一個範圍（目錄或檔案，可以好幾個）裡每份檔案的行數，與程式檔裡的類別、函式定義（Python 用 AST；C／C++ 照
定義的寫法），各檔案幾個、總共幾個由程式算。要回答「有幾份檔案、各幾行、最長的是哪幾份」「範圍裡有哪些類別、哪些函式（名稱符合的）、
各幾個」時一次列完，不用一份一份看（repo_analysis 的工具，領域 session 用）。

- 範圍：預設略過 _path_common.DEFAULT_EXCLUDES 的目錄（build、install、log、.git…；指定的路徑本身在裡面的照算），--exclude-dir 多略過；
  --include 只算這種檔名（含 / 時比對整個路徑，同 search_text、find_file）；二進位檔不算（計數）。
- Python（.py、.pyw、.pyi、第一行是 python 的 #!）：code_ast_reader 的 _definitions（全部的 def／class，含巢狀與 _ 開頭的；方法的 qualname
  是 類別.方法）。語法錯誤的檔案只算行數，計數寫在最後一行。
- C／C++（.h、.hh、.hpp、.hxx、.c、.cc、.cpp、.cxx）：先把註解與字串換成空白（行號不變），class／struct 有本體的定義（前向宣告、enum class
  不算）；有本體的函式定義（名稱後面的括號配對之後接 `{`，或建構子的 `:` 初始化再接 `{`；if、for、while、switch、catch… 不算），在類別
  本體裡的、或寫成 `類別::名稱` 的是方法（qualname 是 類別::名稱）。只有宣告（`;` 結尾的原型）不列。
- --name（正規表示式，分大小寫；寫成萬用字元的樣子 `<字>*` 回 [ERROR]、附對應的正規表示式，_glob_name）、--kind（class／def）篩定義；--files 只列每份檔案的行數與定義的數量；--sort lines 照行數由多到少。
- --has（照字面、不分大小寫，`a|b` 是任一個）：只列名稱或所屬的那一層（qualname 的最後兩段 `類別::方法`、`類別.方法`，_tail；命名空間與更外層的
  不算）有這個字的定義，檔案只列有符合的定義的（其他幾份寫在最後）——用類別的名稱列出它的成員（標頭檔的類別、.cpp 寫成 `類別::方法` 的定義）；
  有骨架的技能 cpp_symbol 用它列有本體的定義（框架討論紀錄第 29 輪）。
收據（_receipt_common，欄位見規格的 receipt）：每一個定義一筆（路徑、行號、結束的行、種類、名稱、qualname；Python 有裝飾器的另記 decorator——
定義的行號從 def／class 那一行算），每份檔案的行數與數量（per_file）；用了 --has 時記篩選的字（has）。
"""
import os
import re
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402
from _receipt_common import fail, main, result  # noqa: E402
from code_ast_reader_cmd import _definitions, _is_python  # noqa: E402

TIMEOUT_SECONDS = 30
FILES_MAX = 5000            # 最多看幾份檔案（超過的不算，寫明）
SHOWN_FILES = 300           # 最多列幾份檔案
SHOWN_DEFS = 600            # 最多列幾個定義（每份檔案的數量照樣全部算）
PARSE_BYTES = 2_000_000     # 超過這麼大的程式檔只算行數
CPP_EXT = (".h", ".hh", ".hpp", ".hxx", ".c", ".cc", ".cpp", ".cxx")
BLOCKED = ("/", "/proc", "/sys", "/dev")
USAGE = ('用法: scripts/code_defs_cmd.py [路徑…] [--include "<檔名寫法>"] [--exclude-dir <名稱>] [--name "<名稱的寫法>"] '
         '[--has "<名稱>"] [--kind class|def] [--files] [--sort lines]\n'
         '  路徑：目錄或檔案，可以好幾個，預設 .（目前工作目錄）；不能是 /。\n'
         '  --include "*.py"：只算這種檔名（可重複；含 / 時比對整個路徑；不給就是全部的文字檔）　--exclude-dir 名稱：多略過一個目錄（可重複）\n'
         '  --name "^test"：只列名稱符合這個正規表示式的定義（分大小寫；^ 是開頭、$ 是結尾）　--kind class 只列類別、def 只列函式與方法\n'
         '  --has "<名稱>"：只列名稱或所屬的類別（類別::方法、類別.方法 的最後兩段）有這個字的定義（照字面、不分大小寫；a|b 是任一個），'
         '只列有符合的檔案\n'
         '  --files：只列每份檔案的行數與定義的數量　--sort lines：檔案照行數由多到少排（預設照路徑）')
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "sizeof", "alignof", "decltype", "static_assert", "new", "delete",
             "throw", "else", "do", "case", "operator", "defined", "typeid", "noexcept", "requires"}
_CLASS = re.compile(r"\b(class|struct)\s+((?:[A-Z_][A-Z0-9_]*\s+)*)([A-Za-z_]\w*)(\s*<[^<>;{}()]*>)?\s*(?:final\s*)?(?::(?!:)[^;{}()]*)?\{")
_CALLABLE = re.compile(r"(~?[A-Za-z_]\w*(?:\s*<[^<>;{}()]*>)?(?:\s*::\s*~?[A-Za-z_]\w*(?:\s*<[^<>;{}()]*>)?)*)\s*\(")
_AFTER = re.compile(r"\s*(?:(?:const|override|final|noexcept|volatile|mutable|&&?)\b\s*|noexcept\s*\([^()]*\)\s*|throw\s*\([^()]*\)\s*"
                    r"|->\s*[\w:<>,\s\*&]+?(?=[{;:=])|\[\[[^\]]*\]\]\s*)*")


_GLOB_STAR = re.compile(r"^\*|(?<!\\)[A-Za-z0-9_]\*")   # 萬用字元的 *：開頭，或接在英數字、底線後面（名稱裡不會有 *；\w* 這種跳脫的不算）


def _glob_name(v):
    """--name 寫成萬用字元的樣子（`<字>*`：正規表示式裡是「<字> 的最後一個字元重複任意次」，會多列）→ 對應的正規表示式；只有名稱的字、* 與 ?
    才換得出來，其他的回 ""；不是萬用字元的樣子回 None。單一迴圈的比較裡 26b 寫了 `<字>*`，多列了別的名稱（設計筆記 2.63）。"""
    if not _GLOB_STAR.search(v):
        return None
    core = v.strip("*")
    if not core or not re.fullmatch(r"[\w.:*?-]+", v):
        return ""
    rx = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in core)
    return ("" if v.startswith("*") else "^") + rx + ("" if v.endswith("*") else "$")


def parse_args(argv):
    """解析命令列參數 → (選項 dict, 錯誤)。"""
    o = {"paths": [], "include": [], "exclude_dir": [], "name": None, "has": [], "kind": None, "files": False, "sort": "path"}
    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--include", "--exclude-dir", "--name", "--has", "--kind", "--sort"):
            if i + 1 >= len(args):
                return None, f"[ERROR] {a} 後面需要值。\n{USAGE}"
            v = args[i + 1]
            if a == "--include":
                o["include"] += pc.split_globs(v)               # "*.h|*.cpp" 拆成兩種（_path_common.split_globs）
            elif a == "--exclude-dir":
                o["exclude_dir"] += [x.strip("/") for x in pc.split_globs(v)]
            elif a == "--name":
                rx = _glob_name(v)
                if rx is not None:
                    fix = f"寫成 --name \"{rx}\"" if rx else "改成正規表示式的寫法"
                    return None, (f"[ERROR] --name 是正規表示式，「{v}」是萬用字元的寫法（正規表示式的 * 是「前一個字元重複任意次」，不是任意字元）。"
                                  f"下一步：{fix}（^ 是開頭、$ 是結尾、.* 是任意字元）。\n{USAGE}")
                try:
                    re.compile(v)
                except re.error as e:
                    return None, f"[ERROR] --name 的寫法不是合法的正規表示式（{e}）：「{v}」。下一步：改成像 \"^test\" 這樣的寫法。\n{USAGE}"
                o["name"] = v
            elif a == "--has":
                words = [x.strip() for x in v.split("|") if x.strip()]
                if not words:
                    return None, f"[ERROR] --has 後面要寫名稱（好幾個用 | 分開），收到「{v}」。\n{USAGE}"
                o["has"] += words
            elif a == "--kind":
                if v not in ("class", "def"):
                    return None, f"[ERROR] --kind 要是 class（類別）或 def（函式與方法），收到「{v}」。\n{USAGE}"
                o["kind"] = v
            else:
                if v not in ("lines", "path"):
                    return None, f"[ERROR] --sort 要是 lines（照行數由多到少）或 path（照路徑），收到「{v}」。\n{USAGE}"
                o["sort"] = v
            i += 2
            continue
        if a == "--files":
            o["files"] = True
        elif a.startswith("-") and a != "-":
            return None, f"[ERROR] 不支援的選項 {a}。下一步：照下面的用法改。\n{USAGE}"
        else:
            o["paths"].append(a)
        i += 1
    o["paths"] = o["paths"] or ["."]
    return o, None


def _timeout_handler(signum, frame):
    raise TimeoutError


# ---------------------------------------------------------------- 檔案
def _walk(roots, excludes, include):
    """(檔案的絕對路徑清單, 略過的目錄數)：照路徑排序；目錄照預設與指定的略過，檔名照 include（含 / 的比對整個路徑，_path_common.include_ok）。"""
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
            for f in sorted(files):
                if not pc.include_ok(os.path.join(d, f), include):
                    continue
                out.append(os.path.join(d, f))
    return list(dict.fromkeys(out)), skipped


def _read(path):
    """(文字, None) 或 (None, 原因)：二進位檔（前 8KB 有 NUL）、讀不到的不算。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return None, f"讀不到（{e.strerror or e}）"
    if b"\0" in data[:8192]:
        return None, "二進位檔"
    return data.decode("utf-8", errors="replace"), None


def _count_lines(text):
    return text.count("\n") + (0 if text.endswith("\n") or not text else 1)


# ---------------------------------------------------------------- Python
def _py_defs(text, path):
    import ast
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError):
        return None
    return [{"line": d["line"], "end": d["end"], "kind": d["kind"], "name": d["name"], "qualname": d["qualname"],
             **({"decorator": d["decorator"]} if d.get("decorator") else {})} for d in _definitions(tree)]


# ---------------------------------------------------------------- C／C++
def _strip_cpp(text):
    """註解、字串與字元常數換成空白（換行留著：行號不變）。"""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:j]))
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(c + "".join(ch if ch == "\n" else " " for ch in text[i + 1:j - 1]) + (c if j - 1 > i else ""))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)[:n]


def _match(text, i, open_ch, close_ch):
    """text[i] 是 open_ch：配對的 close_ch 的位置；配不到回 -1。"""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == open_ch:
            depth += 1
        elif text[j] == close_ch:
            depth -= 1
            if depth == 0:
                return j
    return -1


def _cpp_defs(text):
    """C／C++ 的類別與有本體的函式定義（照寫法，不是完整的語法分析）。"""
    s = _strip_cpp(text)
    line_at = lambda pos: s.count("\n", 0, pos) + 1          # noqa: E731
    out, classes = [], []
    for m in _CLASS.finditer(s):
        if re.search(r"\benum\s*$", s[max(0, m.start() - 12):m.start()]):
            continue
        body = m.end() - 1
        end = _match(s, body, "{", "}")
        classes.append((body, end if end > 0 else len(s), m.group(3)))
        out.append({"line": line_at(m.start(3)), "end": line_at(end) if end > 0 else line_at(body), "kind": "class", "name": m.group(3),
                    "qualname": m.group(3), "_pos": m.start()})
    pos = 0
    while True:
        m = _CALLABLE.search(s, pos)
        if not m:
            break
        pos = m.end()
        full = re.sub(r"\s+", "", m.group(1))
        name = re.sub(r"<.*>$", "", full.split("::")[-1]).lstrip("~")
        if name in _KEYWORDS or full.split("::")[0] in _KEYWORDS or re.search(r"(?:\.|->)\s*$", s[max(0, m.start() - 3):m.start()]):
            continue
        close = _match(s, m.end() - 1, "(", ")")
        if close < 0:
            continue
        k = _AFTER.match(s, close + 1).end()
        if s[k:k + 1] == ":" and s[k:k + 2] != "::":            # 建構子的初始化：x_(a), y_{b} 之後才是本體
            k = _init_list_end(s, k + 1)
            if k < 0:
                continue
        if s[k:k + 1] != "{":
            continue
        end = _match(s, k, "{", "}")
        owner = next((c for c in classes if c[0] < m.start() < c[1]), None)
        qual = re.sub(r"<[^<>]*>", "", full if "::" in full else (f"{owner[2]}::{full}" if owner else full))
        out.append({"line": line_at(m.start()), "end": line_at(end) if end > 0 else line_at(k),
                    "kind": "method" if ("::" in full or owner) else "function", "name": name, "qualname": qual, "_pos": m.start()})
        if end > 0:
            pos = end + 1                                      # 函式的本體裡不會再有定義（lambda、區域類別不列）
    out.sort(key=lambda d: d["_pos"])
    for d in out:
        d.pop("_pos")
    return out


_INIT = re.compile(r"\s*[A-Za-z_][\w:]*(?:\s*<[^<>;{}()]*>)?\s*([({])")


def _init_list_end(s, j):
    """建構子初始化（`: a_(x), b_{y}`）之後的位置（接著應該是本體的 {）；寫法對不上回 -1。"""
    while True:
        m = _INIT.match(s, j)
        if not m:
            return -1
        close = _match(s, m.end(1) - 1, m.group(1), ")" if m.group(1) == "(" else "}")
        if close < 0:
            return -1
        j = close + 1
        comma = re.match(r"\s*,", s[j:])
        if not comma:
            return j + len(s[j:]) - len(s[j:].lstrip())
        j += comma.end()


# ---------------------------------------------------------------- 主流程
def _show(path):
    return pc.display(path)


def _tail(qualname):
    """qualname 的最後兩段——所屬的那一層與名稱（`ns::Cls::m` → `Cls::m`、`Cls.m` → `Cls.m`）；--has 比對這一段，命名空間與更外層的不算
    （比對整個 qualname 時，命名空間的字會把那個命名空間裡的定義全部列出來）。"""
    return "".join(re.split(r"(::|\.)", qualname)[-3:])


def execute(argv):
    o, err = parse_args(argv)
    if err:
        return fail(err, "args")
    roots = []
    for p in o["paths"]:
        if os.path.abspath(pc.expand(p)) in BLOCKED:
            return fail(f"[ERROR] 不列 {p}：範圍太大。下一步：指定具體的目錄（例如專案或套件的目錄）。\n{USAGE}", "args")
        abs_path, perr = pc.resolve(p, "any")
        if perr:
            return fail(perr)
        roots.append(abs_path)
    excludes = set(pc.excludes_for(o["paths"])) | set(o["exclude_dir"])
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
    timed_out = False
    per_file, items, notes = [], [], {"binary": 0, "unreadable": 0, "syntax": 0, "big": 0}
    try:
        files, skipped_dirs = _walk(roots, excludes, o["include"])
        over = max(0, len(files) - FILES_MAX)
        name_re = re.compile(o["name"]) if o["name"] else None
        has_re = re.compile("|".join(re.escape(w) for w in o["has"]), re.I) if o["has"] else None
        for path in files[:FILES_MAX]:
            text, why = _read(path)
            if text is None:
                notes["binary" if why == "二進位檔" else "unreadable"] += 1
                continue
            defs = []
            is_py = _is_python(path)
            if (is_py or path.endswith(CPP_EXT)) and len(text) > PARSE_BYTES:
                notes["big"] += 1
            elif is_py:
                got = _py_defs(text, path)
                if got is None:
                    notes["syntax"] += 1
                defs = got or []
            elif path.endswith(CPP_EXT):
                defs = _cpp_defs(text)
            if name_re:
                defs = [d for d in defs if name_re.search(d["name"])]
            if has_re:
                defs = [d for d in defs if has_re.search(_tail(d["qualname"]))]
            if o["kind"] == "class":
                defs = [d for d in defs if d["kind"] == "class"]
            elif o["kind"] == "def":
                defs = [d for d in defs if d["kind"] != "class"]
            row = {"path": path, "lines": _count_lines(text), "classes": sum(1 for d in defs if d["kind"] == "class"),
                   "functions": sum(1 for d in defs if d["kind"] != "class")}
            per_file.append(row)
            items += [dict(d, path=path) for d in defs]
    except TimeoutError:
        timed_out = True
        over, skipped_dirs = 0, 0
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
    if timed_out and not per_file:
        return fail(f"[ERROR] 列舉逾時（超過 {TIMEOUT_SECONDS} 秒）還沒有看完任何一份檔案。下一步：縮小範圍（更下層的目錄）或加 --include。",
                    "timeout")
    return _render(o, roots, per_file, items, notes, over, skipped_dirs if not timed_out else 0, excludes, timed_out)


def _render(o, roots, per_file, items, notes, over, skipped_dirs, excludes, timed_out):
    scope = "、".join(_show(r) for r in roots)
    n_lines = sum(r["lines"] for r in per_file)
    n_cls, n_fn = sum(r["classes"] for r in per_file), sum(r["functions"] for r in per_file)
    filt = []
    if o["include"]:
        names, paths = [g for g in o["include"] if "/" not in g], [g for g in o["include"] if "/" in g]
        filt += ([f"檔名 {'、'.join(names)}"] if names else []) + ([f"路徑符合 {'、'.join(paths)}"] if paths else [])
    if o["name"]:
        filt.append(f"名稱符合「{o['name']}」")
    if o["has"]:
        filt.append(f"名稱或所屬的類別有「{'、'.join(o['has'])}」")
    if o["kind"]:
        filt.append("只算類別" if o["kind"] == "class" else "只算函式與方法")
    rows = sorted(per_file, key=lambda r: (-r["lines"], r["path"])) if o["sort"] == "lines" else per_file
    if o["has"] and not o["files"]:            # --has：只列有符合的定義的檔案（其他的寫在最後）
        rows = [r for r in rows if r["classes"] or r["functions"]]
    hidden = len(per_file) - len(rows)
    truncated = len(rows) > SHOWN_FILES or over > 0 or timed_out
    result("pass" if per_file else "empty",
           counts={"files": len(per_file), "lines": n_lines, "classes": n_cls, "functions": n_fn},
           items=items, truncated=truncated or len(items) > 1000, per_file=per_file, paths=roots, include=o["include"],
           exclude_dirs=sorted(excludes), name=o["name"], kind=o["kind"], timed_out=timed_out, **({"has": o["has"]} if o["has"] else {}))
    if not per_file:
        return (f"[PASS] 範圍 {scope} 裡沒有符合的檔案（0 份" + (f"；{'、'.join(filt)}" if filt else "") + "）。"
                f"下一步：確認路徑與 --include 的寫法（例如 \"*.py\"、\"test_*.py\"），或用 find_file 找檔案在哪裡。")
    head = f"[PASS] 範圍 {scope}：{len(per_file)} 份檔案、共 {n_lines} 行"
    head += f"；定義：類別 {n_cls}、函式／方法 {n_fn}" + (f"（{'、'.join(filt)}）" if filt else "")
    if o["sort"] == "lines":
        head += "；檔案照行數由多到少"
    out = [head]
    shown_defs = 0
    by_path = {}
    for it in items:
        by_path.setdefault(it["path"], []).append(it)
    for r in rows[:SHOWN_FILES]:
        counts = f"{r['lines']} 行" + (f"；類別 {r['classes']}、函式 {r['functions']}" if r["classes"] or r["functions"] else "")
        if o["files"]:
            out.append(f"- {_show(r['path'])}：{counts}")
            continue
        out.append(f"## {_show(r['path'])}（{counts}）")
        for d in by_path.get(r["path"], []):
            if shown_defs >= SHOWN_DEFS:
                break
            shown_defs += 1
            span = (f"行 {d['line']}-{d['end']}" if d["end"] and d["end"] != d["line"] else f"行 {d['line']}") \
                + (f"；裝飾器在行 {d['decorator']}" if d.get("decorator") else "")
            out.append(f"  - {'class' if d['kind'] == 'class' else 'def'} {d['qualname']}（{span}）")   # 縮排：提煉核對時上層的 ## 檔案 也算
    tail = []
    if len(rows) > SHOWN_FILES:
        tail.append(f"只列前 {SHOWN_FILES} 份檔案（共 {len(rows)} 份；數量照樣全部算）")
    if hidden:
        tail.append(f"其他 {hidden} 份檔案沒有符合的定義，不列")
    if shown_defs >= SHOWN_DEFS and len(items) > SHOWN_DEFS:
        tail.append(f"定義只列前 {SHOWN_DEFS} 個（共 {len(items)} 個；縮小範圍、加 --name 或 --kind 看其他的）")
    if over:
        tail.append(f"範圍裡的檔案超過 {FILES_MAX} 份，後面 {over} 份沒有算：縮小範圍或加 --include")
    if timed_out:
        tail.append(f"逾時（{TIMEOUT_SECONDS} 秒）沒有看完：上面的數量不是全部，縮小範圍或加 --include")
    skipped = [f"{v} 份{k}" for k, v in (("二進位檔", notes["binary"]), ("讀不到的", notes["unreadable"]),
                                        ("語法錯誤只算行數的 Python 檔", notes["syntax"]), ("太大只算行數的程式檔", notes["big"])) if v]
    if skipped:
        tail.append("沒有算的：" + "、".join(skipped))
    if skipped_dirs:
        tail.append(f"略過了 {skipped_dirs} 個預設略過或指定略過的目錄（{'、'.join(sorted(excludes)[:8])}）")
    if tail:
        out.append("（" + "；".join(tail) + "）")
    return "\n".join(out)


if __name__ == "__main__":
    main(execute, "code_defs")
