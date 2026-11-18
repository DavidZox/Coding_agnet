"""code_ast_reader：用 AST 讀一個 Python 檔的結構——模組說明、常數、類別（繼承）、函式／方法的完整簽名與第一行 docstring，
每個 def／class 附行號範圍（`行 120-180`），要看實作就用 view_file --from 120 --lines 61，不必讀全文。

簽名包含 / 前的位置參數、預設值、*args、* 之後的關鍵字參數、**kwargs、型別標註與回傳型別（以前只列一般參數）；常數包含
有型別標註的（`X: int = 5`）；太長的值截斷。逾時 15 秒。
收據（_receipt_common，欄位見規格的 receipt）：全部的 def／class（含 _ 開頭的私有項目、不受 MAX_ITEMS 限制）——名稱、所在的類別或函式、
種類、行號範圍；程式拿搜尋命中的行號就查得到它在哪個函式裡。
"""
import ast
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402
from _receipt_common import fail, main, result  # noqa: E402

TIMEOUT_SECONDS = 15
MAX_ITEMS = 400               # 最多列幾個 def／class
VALUE_CHARS = 80              # 常數的值最多幾個字
DEFAULT_CHARS = 40            # 參數預設值最多幾個字
USAGE = (
    "用法: scripts/code_ast_reader_cmd.py <檔案.py> [--no-docstrings] [--private]\n"
    "  <檔案.py>：一個 Python 檔（相對或絕對路徑，可用 ~）\n"
    "  --no-docstrings：不印 docstring　--private：也列 _ 開頭的私有函式與方法"
)


def parse_cli(argv):
    """解析命令列參數 → (file_path, show_docstrings, show_private, error)"""
    file_path, show_docstrings, show_private, extra = None, True, False, []
    for arg in argv:
        if arg == "--no-docstrings":
            show_docstrings = False
        elif arg == "--private":
            show_private = True
        elif arg.startswith("-"):
            return None, None, None, f"[ERROR] 不支援的選項 {arg}。下一步：照下面的用法改。\n{USAGE}"
        elif file_path is None:
            file_path = arg
        else:
            extra.append(arg)
    if extra:
        joined = pc.join_if_exists([file_path] + extra)
        if joined is None:
            return None, None, None, (f"[ERROR] 一次只能解析一個檔案（收到 {file_path}、{'、'.join(extra)}）。"
                                      f"下一步：分開執行。\n{USAGE}")
        file_path = joined
    if not file_path:
        return None, None, None, f"[ERROR] 沒有給要解析的檔案。下一步：給一個 .py 檔的路徑。\n{USAGE}"
    return file_path, show_docstrings, show_private, None


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


def analyze_ast(file_path, show_docstrings=True, show_private=False):
    abs_path, err = pc.resolve(file_path, "file",
                               dir_hint=f"code_ast_reader 一次讀一個 .py 檔：先用 find_file \"*.py\" {file_path} 找出檔案，再對單一檔案執行")
    if err:
        return fail(err)
    if not _is_python(abs_path):
        return fail(f"[ERROR] {file_path} 不是 Python 檔（副檔名不是 .py、第一行也不是 python 的 #!）。"
                    f"下一步：其他語言或設定檔用 view_file 看內容、search_text 找定義。", "args")
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            code = f.read()
    except OSError as e:
        return fail(f"[ERROR] 無法讀取 {file_path}：{e}。下一步：確認路徑與權限。", "env")
    n_lines = code.count("\n") + (0 if code.endswith("\n") or not code else 1)
    try:
        tree = ast.parse(code, filename=file_path)
    except SyntaxError as se:
        text = (se.text or "").strip()
        return fail(f"[ERROR] {file_path} 有語法錯誤，無法解析：第 {se.lineno} 行 {se.msg}" + (f"（{_short(text, 120)}）" if text else "")
                    + f"。下一步：用 view_file {file_path} --from {max(1, (se.lineno or 1) - 5)} --lines 15 看那一段；"
                      f"如果是 Python 2 的檔案，改用 search_text 找 def／class。", "args")
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


def execute(argv):
    file_path, show_docstrings, show_private, err = parse_cli(argv)
    if err:
        return fail(err, "args")
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
    try:
        return analyze_ast(file_path, show_docstrings, show_private)
    except TimeoutError:
        return fail(f"[ERROR] 解析 {file_path} 逾時（超過 {TIMEOUT_SECONDS} 秒）：檔案可能非常大。"
                    f"下一步：用 search_text \"def |class \" {file_path} 列出定義，或用 view_file --from 看需要的那一段。", "timeout")
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)


if __name__ == "__main__":
    main(execute, "code_ast_reader")
