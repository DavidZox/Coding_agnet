"""code_ast_reader：用 AST 讀一個 Python 檔的結構——模組說明、常數、類別（繼承）、函式／方法的完整簽名與第一行 docstring，
每個 def／class 附行號範圍（`行 120-180`），要看實作就用 view_file --from 120 --lines 61，不必讀全文。

簽名包含 / 前的位置參數、預設值、*args、* 之後的關鍵字參數、**kwargs、型別標註與回傳型別（以前只列一般參數）；常數包含
有型別標註的（`X: int = 5`）；太長的值截斷。逾時 15 秒。
收據（_receipt_common，欄位見規格的 receipt）：全部的 def／class（含 _ 開頭的私有項目、不受 MAX_ITEMS 限制）——名稱、所在的類別或函式、
種類、行號範圍；程式拿搜尋命中的行號就查得到它在哪個函式裡。

`--refs <名稱>`（新架構第 3 步，複合技能 py_usage 用）：改成列出這個名稱在檔案裡的每一處——定義（def、class）、呼叫、import、
指定（`x = …`、`self.x = …`、參數）、其他用到（當成值傳出去、讀屬性），每一處附行號與所在的函式。用 AST 分，所以註解與字串裡
提到的本來就不算；import 不是呼叫。收據的項目一處一筆（含檔案的路徑：中階可以再從這裡帶入行號）。
"""
import ast
import os
import re
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402
from _receipt_common import fail, main, result  # noqa: E402

TIMEOUT_SECONDS = 15
MAX_ITEMS = 400               # 最多列幾個 def／class
VALUE_CHARS = 80              # 常數的值最多幾個字
DEFAULT_CHARS = 40            # 參數預設值最多幾個字
REF_TEXT_CHARS = 160          # --refs 每一處附的原始碼最多幾個字
USAGE = (
    "用法: scripts/code_ast_reader_cmd.py <檔案.py> [--no-docstrings] [--private] [--refs <名稱>]\n"
    "  <檔案.py>：一個 Python 檔（相對或絕對路徑，可用 ~）\n"
    "  --no-docstrings：不印 docstring　--private：也列 _ 開頭的私有函式與方法\n"
    "  --refs <名稱>：改成列出這個名稱的每一處（定義、呼叫、import、指定、其他用到）與所在的函式"
)
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REF_KINDS = {"def": "定義", "call": "呼叫", "import": "import", "assign": "指定", "ref": "其他用到"}   # 收據的 kind（class 也算定義）


def parse_args(argv):
    """解析命令列參數 → (file_path, show_docstrings, show_private, refs, error)；refs 是 --refs 的名稱（沒給是 None）"""
    file_path, show_docstrings, show_private, refs, extra = None, True, False, None, []
    args = list(argv)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--no-docstrings":
            show_docstrings = False
        elif arg == "--private":
            show_private = True
        elif arg == "--refs" or arg.startswith("--refs="):
            if "=" in arg:
                refs = arg.split("=", 1)[1]
            elif i + 1 < len(args):
                refs, i = args[i + 1], i + 1
            else:
                return None, None, None, None, f"[ERROR] --refs 後面需要一個名稱。\n{USAGE}"
            if not _NAME.match(refs):
                return None, None, None, None, (f"[ERROR] --refs 的名稱要是一個 Python 的名稱（英文字母或底線開頭，只有英數字與底線；"
                                                f"`a.b` 只寫最後一段），收到「{refs}」。\n{USAGE}")
        elif arg.startswith("-"):
            return None, None, None, None, f"[ERROR] 不支援的選項 {arg}。下一步：照下面的用法改。\n{USAGE}"
        elif file_path is None:
            file_path = arg
        else:
            extra.append(arg)
        i += 1
    if extra:
        joined = pc.join_if_exists([file_path] + extra)
        if joined is None:
            return None, None, None, None, (f"[ERROR] 一次只能解析一個檔案（收到 {file_path}、{'、'.join(extra)}）。"
                                            f"下一步：分開執行。\n{USAGE}")
        file_path = joined
    if not file_path:
        return None, None, None, None, f"[ERROR] 沒有給要解析的檔案。下一步：給一個 .py 檔的路徑。\n{USAGE}"
    return file_path, show_docstrings, show_private, refs, None


def _short(text, n):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "…"


def _unparse(node, n=None):
    try:
        s = ast.unparse(node)
    except Exception:   # noqa: BLE001
        s = "…"
    return _short(s, n) if n else s


class CodeASTVisitor(ast.NodeVisitor):
    def __init__(self, show_docstrings=True, show_private=False):
        self.show_docstrings = show_docstrings
        self.show_private = show_private
        self.output = []
        self.indent_level = 0
        self.n_classes = self.n_funcs = self.n_hidden = 0
        self.items = 0
        self.truncated = False

    def _indent(self):
        return "  " * self.indent_level

    def _format_docstring(self, node):
        if not self.show_docstrings:
            return
        doc = ast.get_docstring(node)
        if doc:
            first_line = doc.strip().split("\n")[0]
            self.output.append(f'{self._indent()}  """{_short(first_line, 160)}"""')

    @staticmethod
    def _format_arg(arg, default=None):
        s = arg.arg
        if arg.annotation is not None:
            s += f": {_unparse(arg.annotation)}"
        if default is not None:
            s += (" = " if arg.annotation is not None else "=") + _unparse(default, DEFAULT_CHARS)
        return s

    def _format_signature(self, node):
        a = node.args
        parts = []
        positional = list(a.posonlyargs) + list(a.args)
        defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
        for k, arg in enumerate(positional):
            parts.append(self._format_arg(arg, defaults[k]))
            if a.posonlyargs and k == len(a.posonlyargs) - 1:
                parts.append("/")
        if a.vararg:
            parts.append("*" + self._format_arg(a.vararg))
        elif a.kwonlyargs:
            parts.append("*")
        for arg, default in zip(a.kwonlyargs, a.kw_defaults):
            parts.append(self._format_arg(arg, default))
        if a.kwarg:
            parts.append("**" + self._format_arg(a.kwarg))
        returns = f" -> {_unparse(node.returns)}" if node.returns else ""
        return f"({', '.join(parts)}){returns}"

    @staticmethod
    def _range(node):
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        end = getattr(node, "end_lineno", None) or node.lineno
        return f"行 {start}-{end}" if end != start else f"行 {start}"

    def _room(self):
        if self.items >= MAX_ITEMS:
            self.truncated = True
            return False
        self.items += 1
        return True

    def visit_Module(self, node):
        doc = ast.get_docstring(node)
        if self.show_docstrings and doc:
            self.output.append(f"模組說明：{_short(doc.strip().splitlines()[0], 200)}")
        constants = []
        for item in node.body:
            names = []
            if isinstance(item, ast.Assign):
                names = [t.id for t in item.targets if isinstance(t, ast.Name) and t.id.isupper()]
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id.isupper():
                names = [item.target.id]
            for name in names:
                if name.startswith("_") and not self.show_private:
                    self.n_hidden += 1
                    continue
                if isinstance(item, ast.Assign):
                    constants.append(f"- {name} = {_unparse(item.value, VALUE_CHARS)}（行 {item.lineno}）")
                else:
                    val = f" = {_unparse(item.value, VALUE_CHARS)}" if item.value is not None else ""
                    constants.append(f"- {name}: {_unparse(item.annotation)}{val}（行 {item.lineno}）")
        if constants:
            self.output.append(f"## 常數（{len(constants)} 項）")
            self.output += constants
        self.output.append("## 類別與函式")
        self._defs_header = len(self.output) - 1
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        if not self.show_private and node.name.startswith("_"):
            self.n_hidden += 1
            return
        if not self._room():
            return
        self.n_classes += 1
        bases = [_unparse(b) for b in node.bases] + [_unparse(k) for k in node.keywords]
        base_str = f"({', '.join(bases)})" if bases else ""
        for d in node.decorator_list:
            self.output.append(f"{self._indent()}@{_unparse(d, 120)}")
        self.output.append(f"{self._indent()}class {node.name}{base_str}:  {self._range(node)}")
        self._format_docstring(node)
        self.indent_level += 1
        self.generic_visit(node)
        self.indent_level -= 1

    def visit_FunctionDef(self, node):
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_func(node, is_async=True)

    def _visit_func(self, node, is_async=False):
        if not self.show_private and node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
            self.n_hidden += 1
            return
        if not self._room():
            return
        self.n_funcs += 1
        for d in node.decorator_list:
            self.output.append(f"{self._indent()}@{_unparse(d, 120)}")
        prefix = "async def" if is_async else "def"
        self.output.append(f"{self._indent()}{prefix} {node.name}{self._format_signature(node)}  {self._range(node)}")
        self._format_docstring(node)


def _is_python(path):
    if path.endswith((".py", ".pyw", ".pyi")):
        return True
    try:
        with open(path, "rb") as f:
            first = f.readline(200)
        return first.startswith(b"#!") and b"python" in first
    except OSError:
        return False


def _timeout_handler(signum, frame):
    raise TimeoutError


def _definitions(tree):
    """全部的 def／class（含私有、巢狀）：名稱、qualname、種類（class／method／function）、行號範圍（start 含 decorator）、所在的類別或函式。"""
    out = []

    def walk(node, stack):
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, stack)
                continue
            is_class = isinstance(child, ast.ClassDef)
            parent = stack[-1] if stack else None
            out.append({"name": child.name, "qualname": ".".join([n for n, _ in stack] + [child.name]),
                        "kind": "class" if is_class else ("method" if parent and parent[1] == "class" else "function"),
                        "async": isinstance(child, ast.AsyncFunctionDef), "line": child.lineno,
                        "start": min([child.lineno] + [d.lineno for d in child.decorator_list]),
                        "end": getattr(child, "end_lineno", None) or child.lineno, "parent": parent[0] if parent else None,
                        "private": child.name.startswith("_") and not (child.name.startswith("__") and child.name.endswith("__"))})
            walk(child, stack + [(child.name, "class" if is_class else "function")])

    walk(tree, [])
    return out


def _constants(tree):
    out = []
    for item in tree.body:
        if isinstance(item, ast.Assign):
            out += [{"name": t.id, "line": item.lineno} for t in item.targets if isinstance(t, ast.Name) and t.id.isupper()]
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id.isupper():
            out.append({"name": item.target.id, "line": item.lineno})
    return out


def _load(file_path):
    """(絕對路徑, 原始碼, AST, 行數) 或 ([ERROR] 的文字,)：找檔案、確認是 Python、讀檔、解析。"""
    abs_path, err = pc.resolve(file_path, "file",
                               dir_hint=f"code_ast_reader 一次讀一個 .py 檔：先用 find_file \"*.py\" {file_path} 找出檔案，再對單一檔案執行")
    if err:
        return (fail(err),)
    if not _is_python(abs_path):
        return (fail(f"[ERROR] {file_path} 不是 Python 檔（副檔名不是 .py、第一行也不是 python 的 #!）。"
                     f"下一步：其他語言或設定檔用 view_file 看內容、search_text 找定義。", "args"),)
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            code = f.read()
    except OSError as e:
        return (fail(f"[ERROR] 無法讀取 {file_path}：{e}。下一步：確認路徑與權限。", "env"),)
    n_lines = code.count("\n") + (0 if code.endswith("\n") or not code else 1)
    try:
        tree = ast.parse(code, filename=file_path)
    except SyntaxError as se:
        text = (se.text or "").strip()
        return (fail(f"[ERROR] {file_path} 有語法錯誤，無法解析：第 {se.lineno} 行 {se.msg}" + (f"（{_short(text, 120)}）" if text else "")
                     + f"。下一步：用 view_file {file_path} --from {max(1, (se.lineno or 1) - 5)} --lines 15 看那一段；"
                       f"如果是 Python 2 的檔案，改用 search_text 找 def／class。", "args"),)
    return abs_path, code, tree, n_lines


def analyze_ast(file_path, show_docstrings=True, show_private=False):
    loaded = _load(file_path)
    if len(loaded) == 1:
        return loaded[0]
    abs_path, _, tree, n_lines = loaded
    visitor = CodeASTVisitor(show_docstrings=show_docstrings, show_private=show_private)
    visitor.visit(tree)
    defs, consts = _definitions(tree), _constants(tree)
    result("pass", counts={"lines": n_lines, "classes": sum(1 for d in defs if d["kind"] == "class"),
                           "functions": sum(1 for d in defs if d["kind"] != "class"), "constants": len(consts)},
           items=defs, path=abs_path, constants=consts)
    head = f"[PASS] {file_path} 的結構：共 {n_lines} 行；{visitor.n_classes} 個類別、{visitor.n_funcs} 個函式／方法"
    if visitor.n_hidden:
        head += f"；{visitor.n_hidden} 個 _ 開頭的私有項目沒有列（要看加 --private）"
    if visitor.truncated:
        head += f"；只列前 {MAX_ITEMS} 個（要找特定的函式用 search_text \"def 名稱\" {file_path}）"
    out = visitor.output
    hdr = getattr(visitor, "_defs_header", None)
    if hdr is not None:
        n_defs = visitor.n_classes + visitor.n_funcs
        out[hdr] = f"## 類別與函式（{n_defs} 項）"
        if not n_defs:
            out.append("（沒有類別或函式）")
    out.append(f"（看某個函式的實作：view_file {file_path} --from <開始行> --lines <行數>）")
    return "\n".join([head] + out)


class _RefVisitor(ast.NodeVisitor):
    """--refs：一個名稱在檔案裡的每一處（定義、呼叫、import、指定、其他用到）與所在的函式（最內層的 def／class 的 qualname，模組層是 None）。
    decorator、預設值、型別標註、基底類別屬於外面那一層；參數屬於那個函式。呼叫只算一次（被呼叫的名稱本身不再算成「其他用到」）。
    定義另外記 qualname、in_class（直接定義在哪個類別裡：方法；不是方法是 None）與行號範圍。"""

    def __init__(self, name, lines, path):
        self.name, self.lines, self.path = name, lines, path
        self.stack = []
        self.out = []

    def _scope(self):
        return ".".join(n for n, _ in self.stack) or None

    def _add(self, kind, node, scope=None, **extra):
        ln = node.lineno
        text = self.lines[ln - 1].strip() if 0 < ln <= len(self.lines) else ""
        self.out.append({"name": self.name, "kind": kind, "line": ln, "scope": scope if scope is not None else self._scope(),
                         "text": _short(text, REF_TEXT_CHARS), "path": self.path, **extra})

    def _visit_def(self, node, is_class):
        if node.name == self.name:
            outer = self._scope()
            self._add("class" if is_class else "def", node, qualname=".".join([n for n, _ in self.stack] + [node.name]),
                      in_class=self.stack[-1][0] if self.stack and self.stack[-1][1] else None,
                      start=min([node.lineno] + [d.lineno for d in node.decorator_list]),
                      end=getattr(node, "end_lineno", None) or node.lineno, scope=outer)
        for d in node.decorator_list:
            self.visit(d)
        if is_class:
            for b in list(node.bases) + list(node.keywords):
                self.visit(b)
        else:
            a = node.args
            for x in list(a.defaults) + [k for k in a.kw_defaults if k is not None]:
                self.visit(x)
            params = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs) + [p for p in (a.vararg, a.kwarg) if p]
            for p in params:
                if p.annotation is not None:
                    self.visit(p.annotation)
            if node.returns is not None:
                self.visit(node.returns)
        self.stack.append((node.name, is_class))
        if not is_class:
            for p in params:
                if p.arg == self.name:
                    self._add("assign", p)
        for child in node.body:
            self.visit(child)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self._visit_def(node, False)

    def visit_AsyncFunctionDef(self, node):
        self._visit_def(node, False)

    def visit_ClassDef(self, node):
        self._visit_def(node, True)

    def visit_Call(self, node):
        f = node.func
        if (isinstance(f, ast.Name) and f.id == self.name) or (isinstance(f, ast.Attribute) and f.attr == self.name):
            self._add("call", node)
            if isinstance(f, ast.Attribute):
                self.visit(f.value)
            for x in list(node.args) + list(node.keywords):
                self.visit(x)
            return
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id == self.name:
            self._add("ref" if isinstance(node.ctx, ast.Load) else "assign", node)

    def visit_Attribute(self, node):
        if node.attr == self.name:
            self._add("ref" if isinstance(node.ctx, ast.Load) else "assign", node)
        self.visit(node.value)

    def _visit_import(self, node, module=None):
        mods = (module or "").split(".")
        if any(a.name == self.name or a.name.split(".")[-1] == self.name or a.asname == self.name for a in node.names) \
                or self.name in mods:
            self._add("import", node)

    def visit_Import(self, node):
        self._visit_import(node)

    def visit_ImportFrom(self, node):
        self._visit_import(node, node.module)


def analyze_refs(file_path, name):
    """--refs：這個名稱的每一處（AST），依種類分節；收據一處一筆。"""
    loaded = _load(file_path)
    if len(loaded) == 1:
        return loaded[0]
    abs_path, code, tree, n_lines = loaded
    v = _RefVisitor(name, code.split("\n"), abs_path)
    v.visit(tree)
    refs = sorted(v.out, key=lambda r: (r["line"], r["kind"]))
    by = {k: [r for r in refs if (r["kind"] in ("def", "class") if k == "def" else r["kind"] == k)] for k in REF_KINDS}
    counts = {"lines": n_lines, "refs": len(refs), "defs": len(by["def"]), "calls": len(by["call"]), "imports": len(by["import"]),
              "assigns": len(by["assign"]), "others": len(by["ref"])}
    result("pass" if refs else "empty", counts=counts, items=refs, path=abs_path, refs=name)
    if not refs:
        return (f"[PASS] {file_path} 裡沒有「{name}」（AST：定義、呼叫、import、指定、其他用到都是 0；註解與字串裡提到的不算）。"
                f"下一步：名稱可能拼錯，或在別的檔案：用 search_text \"{name}\" <目錄> -w --include \"*.py\" 找哪些檔案有。")
    head = (f"[PASS] {file_path} 裡「{name}」出現 {len(refs)} 處（AST）：" + "、".join(f"{label} {len(by[k])}" for k, label in REF_KINDS.items())
            + ("" if len(refs) <= MAX_ITEMS else f"；只列前 {MAX_ITEMS} 處"))
    out, shown = [head], 0
    for k, label in REF_KINDS.items():
        if not by[k]:
            continue
        out.append(f"## {label}（{len(by[k])}）")
        for r in by[k]:
            if shown >= MAX_ITEMS:
                break
            shown += 1
            where = f"在 {r['scope']}" if r["scope"] else "模組層"
            span = f"行 {r['start']}-{r['end']}" if k == "def" and r["end"] != r["start"] else f"行 {r['line']}"
            out.append(f"- {span}（{where}）：{r['text']}")
    out.append(f"（註解與字串裡提到的不算；import 不算呼叫。看前後：view_file {file_path} --from <行號> --lines <行數>）")
    return "\n".join(out)


def execute(argv):
    file_path, show_docstrings, show_private, refs, err = parse_args(argv)
    if err:
        return fail(err, "args")
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
    try:
        return analyze_refs(file_path, refs) if refs else analyze_ast(file_path, show_docstrings, show_private)
    except TimeoutError:
        return fail(f"[ERROR] 解析 {file_path} 逾時（超過 {TIMEOUT_SECONDS} 秒）：檔案可能非常大。"
                    f"下一步：用 search_text \"def |class \" {file_path} 列出定義，或用 view_file --from 看需要的那一段。", "timeout")
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)


if __name__ == "__main__":
    main(execute, "code_ast_reader")
