"""源碼索引：把 ROS 2 工作區的源碼整理成數據診斷的線索（程式做，不呼叫模型）。

Log 只說「發生了什麼」，Topic 只有數字；Topic 之間的關係（誰發布、誰訂閱、在什麼時機發布）、Log 裡的代碼在什麼條件下成立，
寫在源碼裡。這個模組把源碼整理成三種線索，交給 Orchestrator、Worker、Synthesizer：
1. Log 的源碼位置：/rosout 的 file、function、line（錄製時就存在 MCAP 裡）對回源碼目錄的檔案、函式與那一行；
   那一行附近不是 Log 呼叫（或函式名稱對不上）＝源碼可能跟錄製時的版本不同，標出來。
2. Topic 之間的關係：create_publisher／create_subscription／計時器／服務／參數（Python 用 ast；C++ 遮掉註解、字串與前置
   處理指令之後配對大括號）；publish 在哪個函式、那個函式由哪個 callback（收到哪個 Topic、計時器、lifecycle）呼叫；
   每個函式寫入哪些成員變數。
3. 代碼的條件：Log 或狀態裡的代碼（NO_CMD_VEL_RAW、INIT…）在源碼的哪裡出現（字串、.msg 常數），外層的 if 條件，
   條件讀的成員變數由哪個 callback（哪個 Topic）或參數寫入。

範圍：有 package.xml 的套件；略過 build、install、log、test、文件與第三方（3rd、third_party…）。
哪些檔案有在執行：CMake 的 add_executable／add_library、install(PROGRAMS／DIRECTORY)、ament_python_install_package，
setup.py 的套件；沒有編譯的檔案（例如註解掉的 C++ 版節點）不列，避免同一個 Topic 出現兩個發布者。
launch 檔裡、套件不在工作區的節點列為外部節點。
快取：<cache_dir>/<根目錄的雜湊>.json；檔案大小與 mtime 沒變就沿用。"""
import ast
import bisect
import hashlib
import json
import os
import re
import time

INDEX_VERSION = 3   # 2：每個函式讀的成員變數（reads）；3：呼叫別的物件的方法（ocalls：core_.startInitBuffer()）
CODE_EXTS = {".py", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"}
SKIP_DIRS = {".git", ".svn", "build", "install", "log", "__pycache__", "node_modules", ".venv", "venv", "test", "tests",
             "testing", "3rd", "3rdparty", "third_party", "thirdparty", "external", "vendor", "doc", "docs", "dataset",
             "datasets", "spec_kit"}
MAX_FILE_BYTES = 400_000          # 比這大的多半是產生的或第三方的單一標頭檔：不解析
_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")                         # 代碼字串：INIT、NO_CMD_VEL_RAW
_CONST_IDENT = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")      # 常數名：REASON_NO_CMD_VEL_RAW
_IDENT_SKIP = re.compile(r"^(?:RCLCPP|RCUTILS|RCL|ROS|GTEST|EXPECT|ASSERT|TEST|DEFINE|INCLUDE|STD|UINT|INT)\w*")
_LOG_METHODS = {"debug", "info", "warn", "warning", "error", "fatal", "critical"}
_LIFECYCLE = {"on_configure", "on_activate", "on_deactivate", "on_cleanup", "on_shutdown", "on_error"}
_CPP_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "sizeof", "decltype", "static_assert", "alignof",
                 "noexcept", "throw", "new", "delete", "case", "do", "else", "try", "operator", "alignas", "typeid",
                 "static_cast", "dynamic_cast", "reinterpret_cast", "const_cast", "defined"}


# =====================================================================================================================
# Python
# =====================================================================================================================
def _unparse(node, n=200):
    if node is None:
        return None
    try:
        text = ast.unparse(node)
    except Exception:   # noqa: BLE001
        return None
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _self_member(node):
    """self.x → x；其他 → None。"""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return node.attr
    return None


def _is_logger(node):
    """self.get_logger()、node.get_logger()、logger、self._logger…"""
    if isinstance(node, ast.Call):
        f = node.func
        return (isinstance(f, ast.Attribute) and f.attr == "get_logger") or (isinstance(f, ast.Name) and f.id == "get_logger")
    name = node.attr if isinstance(node, ast.Attribute) else (node.id if isinstance(node, ast.Name) else "")
    return name.lower().lstrip("_") in ("logger", "log")


class _PyVisitor(ast.NodeVisitor):
    def __init__(self, out, lines):
        self.out, self.lines = out, lines
        self.cls, self.func, self.target = [], [], None
        self.consts = {}

    def qual(self):
        if not self.func:
            return None
        return ".".join(self.cls[-1:] + self.func)

    def _arg(self, call, i, kw):
        for k in call.keywords:
            if k.arg == kw:
                return k.value
        return call.args[i] if len(call.args) > i else None

    def _str(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.consts.get(node.id)
        m = _self_member(node)
        return self.consts.get("self." + m) if m else None

    def _cb(self, node):
        if node is None:
            return None
        m = _self_member(node)
        if m:
            return m
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Lambda):
            for sub in ast.walk(node.body):
                if isinstance(sub, ast.Call):
                    return _self_member(sub.func) or (sub.func.id if isinstance(sub.func, ast.Name) else None)
        if isinstance(node, ast.Call) and node.args:   # functools.partial(self.cb, …)
            return self._cb(node.args[0])
        return _unparse(node, 80)

    def visit_ClassDef(self, node):
        self.cls.append(node.name)
        self.generic_visit(node)
        self.cls.pop()

    def visit_FunctionDef(self, node):
        self.func.append(node.name)
        self.out["funcs"].append([self.qual(), node.name, self.cls[-1] if self.cls else None, node.lineno,
                                  node.end_lineno or node.lineno])
        self.generic_visit(node)
        self.func.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _record_targets(self, targets, value):
        q = self.qual()
        names = []
        for t in targets:
            for sub in ast.walk(t):
                m = _self_member(sub)
                if m:
                    names.append(("self", m))
                elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    names.append(("local", sub.id))
        for kind, nm in names:
            if kind == "self" and q:
                w = self.out["writes"].setdefault(q, [])
                if nm not in w:
                    w.append(nm)
            if kind == "local" and q and value is not None:
                self.out["assigns"].setdefault(q, {})[nm] = _unparse(value)
            if isinstance(value, ast.Constant) and isinstance(value.value, str):   # 常數：NAME = '/topic'、self.x = '/topic'
                self.consts[("self." + nm) if kind == "self" else nm] = value.value
        self.target = next((nm for k, nm in names if k == "self"), None) or next((nm for k, nm in names), None)

    def visit_Assign(self, node):
        self._record_targets(node.targets, node.value)
        self.visit(node.value)
        self.target = None

    def visit_AnnAssign(self, node):
        self._record_targets([node.target], node.value)
        if node.value is not None:
            self.visit(node.value)
        self.target = None

    def visit_AugAssign(self, node):
        self._record_targets([node.target], None)
        self.visit(node.value)
        self.target = None

    def _ctrl(self, start, end, header):
        self.out["ctrl"].append([start, end, header])

    def visit_If(self, node):
        line = self.lines[node.lineno - 1].lstrip() if node.lineno - 1 < len(self.lines) else ""
        kw = "elif" if line.startswith("elif") else "if"
        test = _unparse(node.test)
        self._ctrl(node.lineno, node.body[-1].end_lineno or node.lineno, f"{kw} {test}")
        orelse = node.orelse
        is_elif = (len(orelse) == 1 and isinstance(orelse[0], ast.If) and orelse[0].lineno - 1 < len(self.lines)
                   and self.lines[orelse[0].lineno - 1].lstrip().startswith("elif"))
        if orelse and not is_elif:
            self._ctrl(orelse[0].lineno, orelse[-1].end_lineno or orelse[0].lineno, f"else（{kw} {test} 不成立）")
        self.generic_visit(node)

    def visit_While(self, node):
        self._ctrl(node.lineno, node.body[-1].end_lineno or node.lineno, f"while {_unparse(node.test)}")
        self.generic_visit(node)

    def visit_For(self, node):
        self._ctrl(node.lineno, node.body[-1].end_lineno or node.lineno, f"for {_unparse(node.target)} in {_unparse(node.iter)}")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.body:
            self._ctrl(node.lineno, node.body[-1].end_lineno or node.lineno, f"except {_unparse(node.type) or ''}".strip())
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and _TOKEN.match(node.value):
            self.out["consts"].append([node.lineno, node.value])

    def visit_Attribute(self, node):
        if _CONST_IDENT.fullmatch(node.attr) and not _IDENT_SKIP.match(node.attr):
            self.out["idents"].append([node.lineno, node.attr])
        q = self.qual()
        if q and isinstance(node.ctx, ast.Load) and _self_member(node):
            r = self.out["reads"].setdefault(q, [])
            if node.attr not in r:
                r.append(node.attr)
        self.generic_visit(node)

    def visit_Name(self, node):
        if _CONST_IDENT.fullmatch(node.id) and not _IDENT_SKIP.match(node.id):
            self.out["idents"].append([node.lineno, node.id])

    def visit_Call(self, node):
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
        q, line = self.qual(), node.lineno
        if name in ("create_publisher", "create_lifecycle_publisher"):
            topic = self._arg(node, 1, "topic")
            self.out["pubs"].append({"topic": self._str(topic), "expr": _unparse(topic, 80), "type": _unparse(self._arg(node, 0, "msg_type"), 80),
                                     "var": self.target, "line": line, "func": q})
        elif name == "create_subscription":
            topic = self._arg(node, 1, "topic")
            self.out["subs"].append({"topic": self._str(topic), "expr": _unparse(topic, 80), "type": _unparse(self._arg(node, 0, "msg_type"), 80),
                                     "cb": self._cb(self._arg(node, 2, "callback")), "var": self.target, "line": line, "func": q})
        elif name in ("create_timer", "create_wall_timer"):
            self.out["timers"].append({"period": _unparse(self._arg(node, 0, "timer_period_sec"), 80),
                                       "cb": self._cb(self._arg(node, 1, "callback")), "var": self.target, "line": line, "func": q})
        elif name == "create_service":
            srv = self._arg(node, 1, "srv_name")
            self.out["srvs"].append({"name": self._str(srv), "expr": _unparse(srv, 80), "type": _unparse(self._arg(node, 0, "srv_type"), 80),
                                     "cb": self._cb(self._arg(node, 2, "callback")), "line": line, "func": q})
        elif name == "create_client":
            srv = self._arg(node, 1, "srv_name")
            self.out["clis"].append({"name": self._str(srv), "expr": _unparse(srv, 80), "type": _unparse(self._arg(node, 0, "srv_type"), 80),
                                     "line": line, "func": q})
        elif name and "declare" in name.lower() and "param" in name.lower():
            n0 = self._arg(node, 0, "name")
            if isinstance(n0, ast.Constant) and isinstance(n0.value, str):
                d = self._arg(node, 1, "value")
                self.out["params"].append({"name": n0.value, "default": _unparse(d, 80), "var": self.target, "line": line, "func": q})
        elif name == "publish" and isinstance(f, ast.Attribute):
            self.out["publish"].append([_self_member(f.value) or _unparse(f.value, 60), line, q])
        elif name in _LOG_METHODS and isinstance(f, ast.Attribute) and _is_logger(f.value):
            self.out["logs"].append([node.lineno, node.end_lineno or node.lineno])
        elif name == "__init__" and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Call):
            a0 = node.args[0] if node.args else self._arg(node, 99, "node_name")
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                self.out["nodes"].append([a0.value, self.cls[-1] if self.cls else None, line])
        elif name in ("Node", "LifecycleNode", "create_node"):
            a0 = node.args[0] if node.args else self._arg(node, 99, "node_name")
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                self.out["nodes"].append([a0.value, self.cls[-1] if self.cls else None, line])
        if q:
            callee = _self_member(f) or (f.id if isinstance(f, ast.Name) else None)
            if callee:
                c = self.out["calls"].setdefault(q, [])
                if callee not in c:
                    c.append(callee)
            elif isinstance(f, ast.Attribute):   # 別的物件的方法：self.core.start()、helper.update()
                c = self.out["ocalls"].setdefault(q, [])
                if f.attr not in c:
                    c.append(f.attr)
        self.generic_visit(node)


def _empty_code():
    return {"funcs": [], "nodes": [], "pubs": [], "subs": [], "timers": [], "srvs": [], "clis": [], "params": [],
            "publish": [], "logs": [], "writes": {}, "reads": {}, "calls": {}, "ocalls": {}, "assigns": {}, "consts": [], "idents": [],
            "ctrl": []}


def parse_python(text):
    out = _empty_code()
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        out["error"] = "syntax"
        return out
    v = _PyVisitor(out, text.splitlines())
    for node in tree.body:   # 先收模組層的字串常數（create_subscription 用 TOPIC 常數時查得到）
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    v.consts[t.id] = node.value.value
    v.visit(tree)
    return out


# =====================================================================================================================
# C++
# =====================================================================================================================
_CPP_LEX = re.compile(
    r"(?P<pp>^[ \t]*\#(?:[^\n\\]|\\.)*)"
    r"|(?P<lc>//[^\n]*)"
    r"|(?P<bc>/\*.*?\*/)"
    r'|(?P<raw>R"(?P<d>[^()\\\s]{0,16})\((?P<rawv>.*?)\)(?P=d)")'
    r'|(?P<str>"(?:\\.|[^"\\\n])*")'
    r"|(?P<chr>'(?:\\.|[^'\\\n]){1,4}')",
    re.S | re.M)
_CTRL_RE = re.compile(r"^(?:else\s+if|if|for|while|switch|catch|do|try|else)\b|^case\b|^default\s*:")
_SCOPE_RE = re.compile(r"^(?:template\s*<[^{]*?>\s*)?(?:(?:inline|export)\s+)?(namespace|class|struct|union|enum(?:\s+class|\s+struct)?)"
                       r"\b(?:\s+\[\[[^\]]*\]\])?\s*([A-Za-z_][\w:]*)?")
_ACCESS_RE = re.compile(r"^(?:(?:public|private|protected|signals|slots|Q_SLOTS)\s*:\s*)+")
_FUNC_RE = re.compile(r"(~?[A-Za-z_]\w*(?:\s*::\s*~?[A-Za-z_]\w*)*)\s*\(")
_CPP_CALL = re.compile(r"\b(create_publisher|create_subscription|create_wall_timer|create_timer|create_service|create_client"
                       r"|declare_parameter)\b")
_UNESCAPE = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "0": "\0"}


def _mask_cpp(text):
    """註解、字串、字元、前置處理指令換成空白（換行保留，位置不變）→ (遮好的文字, [(位置, 字串內容)])。"""
    out, strings, pos = [], [], 0
    for m in _CPP_LEX.finditer(text):
        out.append(text[pos:m.start()])
        seg = m.group(0)
        out.append(re.sub(r"[^\n]", " ", seg))
        if m.group("str") is not None:
            strings.append((m.start(), re.sub(r"\\(.)", lambda x: _UNESCAPE.get(x.group(1), x.group(1)), seg[1:-1])))
        elif m.group("raw") is not None:
            strings.append((m.start(), m.group("rawv")))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out), strings


def _match_close(masked, i, open_ch="(", close_ch=")"):
    """masked[i] 是左括號：回傳配對的右括號位置（找不到回 -1）。"""
    depth = 0
    for j in range(i, len(masked)):
        c = masked[j]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return j
    return -1


def _split_args(masked, text, a, b):
    """masked[a:b] 是參數列（不含括號）：依最外層的逗號切開，回傳原文的每一段（字串保留）。"""
    parts, depth, start = [], 0, a
    for j in range(a, b):
        c = masked[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append((start, j))
            start = j + 1
    parts.append((start, b))
    return [(s, e, " ".join(text[s:e].split())) for s, e in parts if text[s:e].strip()]


def _cpp_str(arg):
    """參數是單一字串常值："/topic" → /topic；不是 → None。"""
    m = re.fullmatch(r'\s*(?:std::string\s*\(\s*)?"((?:\\.|[^"\\])*)"\s*\)?\s*', arg or "")
    return m.group(1) if m else None


def _cpp_cb(arg, masked_arg=""):
    """callback 參數 → 函式名稱：std::bind(&Class::method, …)、[this](…) { method(…); }、&Class::method、method。"""
    if not arg:
        return None
    m = re.search(r"std::bind\s*\(\s*&?\s*(?:[\w:]+::)?(\w+)", arg)
    if m:
        return m.group(1)
    if arg.lstrip().startswith("["):
        body = arg[arg.find("{") + 1:] if "{" in arg else ""
        for c in re.finditer(r"(?<![\w.:>])(?:this\s*->\s*)?([A-Za-z_]\w*)\s*\(", body):
            if c.group(1) not in _CPP_KEYWORDS:
                return c.group(1)
        return "lambda"
    m = re.fullmatch(r"\s*&?\s*(?:[\w:]+::)?(\w+)\s*", arg)
    return m.group(1) if m else " ".join(arg.split())[:80]


def _func_name(h):
    for m in _FUNC_RE.finditer(h):
        pre = h[:m.start()]
        if pre.count("(") != pre.count(")"):
            continue
        if re.search(r"(?<![<>!=])=(?!=)", pre):   # 前面有指定（auto x = …）：不是函式定義
            return None
        name = re.sub(r"\s+", "", m.group(1))
        if name.split("::")[-1] in _CPP_KEYWORDS:
            return None
        return name
    return None


def _classify(h):
    h = _ACCESS_RE.sub("", h).strip()
    if not h:
        return "block", None
    if _CTRL_RE.match(h):
        return "ctrl", None
    m = _SCOPE_RE.match(h)
    if m:
        kind = {"namespace": "namespace", "class": "class", "struct": "class", "union": "class"}.get(m.group(1), "enum")
        return kind, (m.group(2) or "").split("::")[-1] or None
    if h.startswith("extern"):
        return "namespace", None
    if h.endswith(("=", ",", "return")):
        return "init", None
    name = _func_name(h)
    return ("func", name) if name else ("block", None)


def parse_cpp(text):
    out = _empty_code()
    masked, strings = _mask_cpp(text)
    nl = [m.start() for m in re.finditer("\n", text)]

    def line_of(off):
        return bisect.bisect_right(nl, off - 1) + 1 if off > 0 else 1

    # ---- 大括號配對：函式、類別、控制區塊
    blocks, stack, paren, last = [], [], 0, 0
    for m in re.finditer(r"[{};()]", masked):
        c, i = m.group(), m.start()
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        elif c == ";":
            if paren == 0:
                last = i + 1
        elif c == "{":
            raw = masked[last:i]
            header = " ".join(raw.split())
            if paren > 0:
                kind, name = "lambda", None
            else:
                kind, name = _classify(header)
            hoff = last + (len(raw) - len(raw.lstrip()))
            parent = stack[-1] if stack else None
            cls = next((b["name"] for b in reversed(stack) if b["kind"] == "class"), None)
            hdr = _ACCESS_RE.sub("", header).strip()
            if kind == "ctrl" and re.match(r"^else\b(?!\s+if)", hdr) and parent is not None and parent.get("last_if"):
                hdr = f"else（{parent['last_if']} 不成立）"
            stack.append({"kind": kind, "name": name, "header": hdr, "off": i, "hoff": hoff if paren == 0 else i,
                          "cls": cls, "paren": paren})
            paren, last = 0, i + 1
        else:   # "}"
            if stack:
                b = stack.pop()
                b["end"] = i
                paren = b["paren"]
                blocks.append(b)
                if stack and b["kind"] == "ctrl":
                    if re.match(r"^(?:else\s+)?if\b", b["header"]):
                        stack[-1]["last_if"] = b["header"]
                    elif not b["header"].startswith("else"):
                        stack[-1].pop("last_if", None)
            last = i + 1
    funcs = []
    for b in blocks:
        if b["kind"] == "func" and b["name"]:
            parts = b["name"].split("::")
            short = parts[-1]
            cls = parts[-2] if len(parts) > 1 else b["cls"]
            qual = f"{cls}::{short}" if cls else short
            funcs.append([qual, short, cls, line_of(b["hoff"]), line_of(b["end"]), b["off"], b["end"]])
        elif b["kind"] == "ctrl":
            out["ctrl"].append([line_of(b["hoff"]), line_of(b["end"]), b["header"][:200]])
    funcs.sort(key=lambda f: f[5])
    out["funcs"] = [f[:5] for f in funcs]
    starts = [f[5] for f in funcs]

    def func_at(off):
        best = None
        k = bisect.bisect_right(starts, off)
        for f in funcs[:k]:
            if f[5] <= off <= f[6] and (best is None or f[5] >= best[5]):
                best = f
        return best

    def qual_at(off):
        f = func_at(off)
        return f[0] if f else None

    classes = [b for b in blocks if b["kind"] == "class" and b["name"]]

    def class_at(off):
        best = None
        for b in classes:
            if b["off"] <= off <= b["end"] and (best is None or b["off"] >= best["off"]):
                best = b
        return best["name"] if best else None

    def target_of(off):
        seg = masked[max(masked.rfind(";", 0, off), masked.rfind("{", 0, off), masked.rfind("}", 0, off)) + 1:off]
        m = re.search(r"([A-Za-z_]\w*)\s*=\s*(?:this\s*->\s*|[A-Za-z_]\w*\s*->\s*)?$", seg)
        return m.group(1) if m else None

    # ---- ROS 介面
    for m in _CPP_CALL.finditer(masked):
        name, j = m.group(1), m.end()
        while j < len(masked) and masked[j] in " \t\n":
            j += 1
        typ = None
        if j < len(masked) and masked[j] == "<":
            k = _match_close(masked, j, "<", ">")
            if k < 0:
                continue
            typ = " ".join(text[j + 1:k].split())
            j = k + 1
            while j < len(masked) and masked[j] in " \t\n":
                j += 1
        if j >= len(masked) or masked[j] != "(":
            continue
        k = _match_close(masked, j)
        if k < 0:
            continue
        args = _split_args(masked, text, j + 1, k)
        a = [x[2] for x in args]
        line, q = line_of(m.start()), qual_at(m.start())
        if name == "create_publisher":
            out["pubs"].append({"topic": _cpp_str(a[0]) if a else None, "expr": a[0] if a else None, "type": typ,
                                "var": target_of(m.start()), "line": line, "func": q})
        elif name == "create_subscription":
            out["subs"].append({"topic": _cpp_str(a[0]) if a else None, "expr": a[0] if a else None, "type": typ,
                                "cb": _cpp_cb(a[2]) if len(a) > 2 else None, "var": target_of(m.start()), "line": line, "func": q})
        elif name in ("create_wall_timer", "create_timer"):
            if name == "create_timer" and len(a) >= 4:   # rclcpp::create_timer(node, clock, period, callback)
                a = a[2:]
            out["timers"].append({"period": a[0] if a else None, "cb": _cpp_cb(a[1]) if len(a) > 1 else None,
                                  "var": target_of(m.start()), "line": line, "func": q})
        elif name == "create_service":
            out["srvs"].append({"name": _cpp_str(a[0]) if a else None, "expr": a[0] if a else None, "type": typ,
                                "cb": _cpp_cb(a[1]) if len(a) > 1 else None, "line": line, "func": q})
        elif name == "create_client":
            out["clis"].append({"name": _cpp_str(a[0]) if a else None, "expr": a[0] if a else None, "type": typ,
                                "line": line, "func": q})
        elif name == "declare_parameter" and a and _cpp_str(a[0]):
            out["params"].append({"name": _cpp_str(a[0]), "default": a[1] if len(a) > 1 else None,
                                  "var": target_of(m.start()), "line": line, "func": q})
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*(?:->|\.)\s*publish\s*\(", masked):
        out["publish"].append([m.group(1), line_of(m.start()), qual_at(m.start())])
    for m in re.finditer(r"\bRCLCPP_(?:DEBUG|INFO|WARN|ERROR|FATAL)\w*\s*\(", masked):
        k = _match_close(masked, m.end() - 1)
        out["logs"].append([line_of(m.start()), line_of(k if k > 0 else m.start())])
    for m in re.finditer(r"(?:\bNode|\bLifecycleNode|make_shared\s*<\s*rclcpp(?:_lifecycle)?::(?:Lifecycle)?Node\s*>|"
                         r"rclcpp::Node::make_shared)\s*\(\s*\"([^\"]+)\"", text):
        if masked[m.start()] != " ":   # 不在註解或字串裡
            out["nodes"].append([m.group(1), class_at(m.start()), line_of(m.start())])
    # ---- 每個函式寫入的成員變數、呼叫的函式
    for f in funcs:
        body = masked[f[5]:f[6]]
        w = []
        for m in re.finditer(r"(?<![\w.>:])(?:this\s*->\s*)?([A-Za-z_]\w*_)\s*(?:\[[^\]\n]*\])?\s*(?:[-+*/|&]?=)(?!=)", body):
            if m.group(1) not in w:
                w.append(m.group(1))
        for m in re.finditer(r"this\s*->\s*([A-Za-z_]\w*)\s*(?:[-+*/|&]?=)(?!=)", body):
            if m.group(1) not in w:
                w.append(m.group(1))
        if w:
            out["writes"][f[0]] = w
        r = []
        for m in re.finditer(r"(?<![\w.>:])(?:this\s*->\s*)?([A-Za-z_]\w*_)\b(?!\s*(?:\[[^\]\n]*\])?\s*(?:[-+*/|&]?=)(?!=))", body):
            if m.group(1) not in r:
                r.append(m.group(1))
        if r:
            out["reads"][f[0]] = r
        calls = []
        for m in re.finditer(r"(?<![\w.:>])(?:this\s*->\s*)?([A-Za-z_]\w*)\s*\(", body):
            if m.group(1) not in _CPP_KEYWORDS and m.group(1) not in calls:
                calls.append(m.group(1))
        if calls:
            out["calls"][f[0]] = calls
        oc = []
        for m in re.finditer(r"[\w\]\)]\s*(?:\.|->)\s*([A-Za-z_]\w*)\s*\(", body):
            if m.group(1) not in oc and m.group(1) not in ("c_str", "str", "size", "empty", "begin", "end", "push_back", "get"):
                oc.append(m.group(1))
        if oc:
            out["ocalls"][f[0]] = oc
        assigns = {}
        for m in re.finditer(r"(?:\bauto|\bconst\s+[\w:<>]+|[\w:<>]+)\s*&?\s+([a-z_]\w*)\s*=\s*([^;{}]+);", body):
            assigns[m.group(1)] = " ".join(text[f[5] + m.start(2):f[5] + m.end(2)].split())[:200]
        if assigns:
            out["assigns"][f[0]] = assigns
    for off, s in strings:
        if _TOKEN.match(s):
            out["consts"].append([line_of(off), s])
    for m in _CONST_IDENT.finditer(masked):
        if not _IDENT_SKIP.match(m.group(1)):
            out["idents"].append([line_of(m.start()), m.group(1)])
    return out


# =====================================================================================================================
# .msg、CMake、setup.py、launch
# =====================================================================================================================
def parse_msg(text):
    consts, comment, fields = [], [], 0
    for i, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            if not consts and not fields:
                comment.append(s.lstrip("#").strip())
            continue
        m = re.match(r"^([\w/]+(?:\[[^\]]*\])?)\s+([A-Za-z_]\w*)\s*=\s*(.+?)\s*$", s)
        if m:
            val = m.group(3)
            if not val.startswith(("'", '"')):
                val = val.split("#", 1)[0].strip()
            consts.append([i, m.group(2), val.strip().strip("'\"")])
        else:
            fields += 1
    return {"consts": consts, "comment": " ".join(c for c in comment if c)[:400]}


def parse_cmake(text):
    text = re.sub(r"(?m)#[^\n]*", "", text)
    proj = re.search(r"\bproject\s*\(\s*([\w-]+)", text, re.I)
    pname = proj.group(1) if proj else ""

    def words(s):
        return [w.replace("${PROJECT_NAME}", pname).strip('"') for w in s.split()]
    out = {"exes": {}, "libs": {}, "programs": [], "dirs": [], "pkgs": [], "has_targets": False}
    for m in re.finditer(r"\b(add_executable|ament_auto_add_executable|add_library|ament_auto_add_library)\s*\(([^)]*)\)", text, re.I):
        w = words(m.group(2))
        if not w:
            continue
        srcs = [x for x in w[1:] if re.search(r"\.(?:c|cc|cpp|cxx|h|hh|hpp|hxx)$", x)]
        out["has_targets"] = True
        (out["exes"] if "executable" in m.group(1).lower() else out["libs"])[w[0]] = srcs
    for m in re.finditer(r"\binstall\s*\(([^)]*)\)", text, re.I):
        w = words(m.group(1))
        if w and w[0].upper() in ("PROGRAMS", "FILES"):
            for x in w[1:]:
                if x.upper() == "DESTINATION":
                    break
                if x.endswith(".py"):
                    out["programs"].append(x)
        elif w and w[0].upper() == "DIRECTORY":
            for x in w[1:]:
                if x.upper() in ("DESTINATION", "FILES_MATCHING", "PATTERN"):
                    break
                out["dirs"].append(x.rstrip("/"))
    for m in re.finditer(r"\bament_python_install_package\s*\(\s*([\w${}]+)", text, re.I):
        out["pkgs"].append(m.group(1).replace("${PROJECT_NAME}", pname))
    if out["programs"] or out["pkgs"]:
        out["has_targets"] = True
    return out


def parse_setup_py(text):
    scripts = {}
    for m in re.finditer(r"['\"]\s*([\w.-]+)\s*=\s*([\w.]+)\s*:\s*(\w+)\s*['\"]", text):
        scripts[m.group(1)] = m.group(2).replace(".", "/") + ".py"
    return {"scripts": scripts}


def parse_launch(text, is_xml=False):
    nodes = []
    if is_xml:
        for m in re.finditer(r"<node\b([^>]*)>", text):
            attrs = dict(re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', m.group(1)))
            nodes.append({"package": attrs.get("pkg"), "executable": attrs.get("exec") or attrs.get("type"),
                          "name": attrs.get("name"), "namespace": attrs.get("namespace") or attrs.get("ns"),
                          "line": text.count("\n", 0, m.start()) + 1})
        return {"nodes": nodes}
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return {"nodes": nodes}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func.attr if isinstance(node.func, ast.Attribute) else (node.func.id if isinstance(node.func, ast.Name) else "")
            if fn in ("Node", "LifecycleNode", "ComposableNode"):
                kw = {k.arg: k.value.value for k in node.keywords
                      if isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)}
                if kw.get("package"):
                    nodes.append({"package": kw.get("package"), "executable": kw.get("executable") or kw.get("plugin"),
                                  "name": kw.get("name"), "namespace": kw.get("namespace"), "line": node.lineno})
    return {"nodes": nodes}


# =====================================================================================================================
# 索引
# =====================================================================================================================
def _norm_topic(t, node_name=None):
    """源碼裡的 Topic 名稱 → 數據裡的寫法：相對名稱加 /（預設 namespace）；~/x → /<節點>/x。"""
    if not t:
        return None
    if t.startswith("~/") and node_name:
        return f"/{node_name}/{t[2:]}"
    return t if t.startswith("/") else "/" + t


def _scan(root):
    """走訪源碼目錄：程式碼、.msg、CMakeLists.txt、setup.py、launch 檔，以及每個套件的根目錄（package.xml）。"""
    files, pkgs = [], {}
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
        if "package.xml" in names:
            try:
                with open(os.path.join(d, "package.xml"), encoding="utf-8", errors="replace") as f:
                    m = re.search(r"<name>\s*([^<\s]+)\s*</name>", f.read())
                pkgs[os.path.relpath(d, root)] = m.group(1) if m else os.path.basename(d)
            except OSError:
                pass
        for n in names:
            ext = os.path.splitext(n)[1]
            if (ext in CODE_EXTS or ext == ".msg" or n in ("CMakeLists.txt", "setup.py") or ".launch." in n
                    or n.endswith(".launch")):
                if n.startswith("test_") or re.search(r"_test\.(?:py|cpp|cc)$", n):
                    continue
                files.append(os.path.relpath(os.path.join(d, n), root))
    return files, pkgs


def _kind(rel):
    n = os.path.basename(rel)
    if n == "CMakeLists.txt":
        return "cmake"
    if n == "setup.py":
        return "setup"
    if ".launch." in n or n.endswith(".launch"):
        return "launch"
    ext = os.path.splitext(n)[1]
    if ext == ".msg":
        return "msg"
    return "py" if ext == ".py" else "cpp"


def _parse_file(path, kind):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return {"skipped": "too_large"}
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return {"skipped": "unreadable"}
    if kind == "py":
        return parse_python(text)
    if kind == "cpp":
        return parse_cpp(text)
    if kind == "msg":
        return parse_msg(text)
    if kind == "cmake":
        return parse_cmake(text)
    if kind == "setup":
        return parse_setup_py(text)
    return parse_launch(text, is_xml=not path.endswith(".py"))


def load(root, cache_dir=None):
    """建（或讀快取）一個源碼目錄的索引 → SourceIndex；目錄不存在回 None。"""
    root = os.path.realpath(os.path.expanduser(root or ""))
    if not root or not os.path.isdir(root):
        return None
    t0 = time.time()
    files, pkgs = _scan(root)
    cache_path = None
    cached = {}
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, hashlib.sha1(root.encode()).hexdigest()[:12] + ".json")
        try:
            with open(cache_path, encoding="utf-8") as f:
                c = json.load(f)
            if c.get("version") == INDEX_VERSION and c.get("root") == root:
                cached = c.get("files") or {}
        except (OSError, ValueError):
            pass
    out, parsed = {}, 0
    for rel in files:
        path = os.path.join(root, rel)
        try:
            st = os.stat(path)
        except OSError:
            continue
        sig = [st.st_size, int(st.st_mtime)]
        old = cached.get(rel)
        if old and old.get("sig") == sig:
            out[rel] = old
            continue
        kind = _kind(rel)
        out[rel] = {"sig": sig, "kind": kind, "data": _parse_file(path, kind)}
        parsed += 1
    if cache_path and (parsed or set(cached) != set(out)):
        tmp = cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": INDEX_VERSION, "root": root, "files": out}, f, ensure_ascii=False)
        os.replace(tmp, cache_path)
    return SourceIndex(root, out, pkgs, seconds=round(time.time() - t0, 2), parsed=parsed)


class SourceIndex:
    def __init__(self, root, files, pkgs, seconds=0.0, parsed=0):
        self.root, self.files, self.pkg_dirs = root, files, pkgs
        self.seconds, self.parsed = seconds, parsed
        self._lines = {}
        self.by_base = {}
        for rel in files:
            self.by_base.setdefault(os.path.basename(rel), []).append(rel)
        self.pkg_of = {}
        dirs = sorted(pkgs, key=len, reverse=True)
        for rel in files:
            d = os.path.dirname(rel)
            pd = next((p for p in dirs if p == "." or d == p or d.startswith(p + os.sep)), None)
            self.pkg_of[rel] = (pd, pkgs.get(pd)) if pd is not None else (None, None)
        self.packages = set(pkgs.values())
        self._built = self._compute_built()
        self.msg_consts = {}   # 常數值 → [(msg 型別, 常數名, 檔案, 行)]
        self.const_value = {}  # 常數名 → 值（REASON_NO_CMD_VEL_RAW → NO_CMD_VEL_RAW）
        for rel, f in files.items():
            if f["kind"] == "msg":
                pkg = self.pkg_of[rel][1] or "?"
                mtype = f"{pkg}/msg/{os.path.splitext(os.path.basename(rel))[0]}"
                for line, name, val in f["data"].get("consts") or []:
                    self.msg_consts.setdefault(val, []).append((mtype, name, rel, line))
                    self.const_value.setdefault(name, val)

    # ---- 哪些檔案有編譯／安裝
    def _compute_built(self):
        built, exes = set(), {}
        for pd, pname in self.pkg_dirs.items():
            base = "" if pd == "." else pd + os.sep
            cm = self.files.get(base + "CMakeLists.txt")
            sp = self.files.get(base + "setup.py")
            mine = [r for r in self.files if self.pkg_of[r][0] == pd]
            if cm and (cm["data"].get("has_targets")):
                d = cm["data"]
                for name, srcs in list(d.get("exes", {}).items()) + list(d.get("libs", {}).items()):
                    paths = [os.path.normpath(base + s) for s in srcs]
                    built.update(paths)
                    if name in d.get("exes", {}):
                        exes[(pname, name)] = paths
                for p in d.get("programs") or []:
                    path = os.path.normpath(base + p)
                    built.add(path)
                    exes[(pname, os.path.basename(p))] = [path]
                for dd in (d.get("dirs") or []) + (d.get("pkgs") or []):
                    pre = os.path.normpath(base + dd) + os.sep
                    built.update(r for r in mine if r.startswith(pre) and r.endswith(".py"))
                built.update(r for r in mine if os.path.splitext(r)[1] in (".h", ".hh", ".hpp", ".hxx"))
            else:   # ament_python 或判斷不了：整個套件都算
                built.update(mine)
            if sp:
                for exe, mod in (sp["data"].get("scripts") or {}).items():
                    exes[(pname, exe)] = [os.path.normpath(base + mod)]
        self.exes = exes
        return built

    def built(self, rel):
        return rel in self._built

    # ---- 檔案內容
    def lines(self, rel):
        if rel not in self._lines:
            try:
                with open(os.path.join(self.root, rel), encoding="utf-8", errors="replace") as f:
                    self._lines[rel] = f.read().splitlines()
            except OSError:
                self._lines[rel] = []
        return self._lines[rel]

    def line_text(self, rel, line):
        ls = self.lines(rel)
        return ls[line - 1].strip() if 0 < line <= len(ls) else ""

    def snippet(self, rel, start, end, mark=()):
        ls = self.lines(rel)
        start, end = max(1, start), min(len(ls), end)
        width = len(str(end))
        return "\n".join(f"{'▶' if i in mark else ' '}{i:>{width}}| {ls[i - 1].rstrip()}" for i in range(start, end + 1))

    def code(self, rel):
        f = self.files.get(rel) or {}
        return f.get("data") if f.get("kind") in ("py", "cpp") else None

    # ---- 查詢
    def resolve(self, path, function=None):
        """Log 的 file（建置時的絕對路徑、安裝後的路徑）→ 源碼目錄裡的相對路徑；對不到回 None。
        依「從尾端算起相同的路徑段數」挑，至少要兩段相同、或路徑裡有套件名稱、或函式名稱在那個檔案裡。"""
        if not path:
            return None
        parts = [p for p in path.replace("\\", "/").split("/") if p not in ("", ".")]
        cands = self.by_base.get(parts[-1] if parts else "", [])
        best, best_key = None, None
        for rel in cands:
            rp = rel.split(os.sep)
            n = 0
            while n < min(len(rp), len(parts)) and rp[-1 - n] == parts[-1 - n]:
                n += 1
            pkg = self.pkg_of[rel][1]
            key = (n, pkg in parts, self.built(rel))
            if best_key is None or key > best_key:
                best, best_key = rel, key
        if best is None:
            return None
        if best_key[0] >= 2 or best_key[1]:
            return best
        code = self.code(best) or {}
        if function and any(f[1] == function for f in code.get("funcs") or []):
            return best
        return None

    def func_at(self, rel, line):
        best = None
        for f in (self.code(rel) or {}).get("funcs") or []:
            if f[3] <= line <= f[4] and (best is None or f[3] >= best[3]):
                best = f
        return best

    def ctrl_at(self, rel, line, func=None):
        """line 外層最近的條件（if／elif／else／switch／case／for…）；C++ 沒有大括號的 if 看前一行。"""
        best = None
        for c in (self.code(rel) or {}).get("ctrl") or []:
            if c[0] <= line <= c[1] and (func is None or func[3] <= c[0]) and (best is None or c[0] >= best[0]):
                best = c
        if self.files[rel]["kind"] == "cpp":
            ls = self.lines(rel)
            for k in range(line - 1, max(0, line - 3), -1):
                prev = ls[k - 1].strip() if k - 1 < len(ls) else ""
                if not prev or prev.startswith("//"):
                    continue
                if re.match(r"^(?:\}\s*)?(?:else\s+)?if\s*\(", prev) and not prev.endswith(("{", ";")):
                    return [k, line, " ".join(prev.lstrip("} ").split())]
                break
        return best

    def branch_preview(self, rel, line):
        """line 是 if 那一行：回傳 (成立時的第一句, 不成立時的第一句或 None)；不是 if 回 None。只看縮排（Python）與大括號後的
        第一句（C++），給「代碼怎麼被用」看分支做什麼（例如只有 NO_CMD_VEL_RAW 時印 INFO、否則印 WARN）。"""
        ls = self.lines(rel)
        if not 0 < line <= len(ls) or not re.match(r"^\s*(?:\}\s*)?(?:el(?:se\s+)?)?if\b", ls[line - 1]):
            return None
        ind = len(ls[line - 1]) - len(ls[line - 1].lstrip())

        def first_stmt(k):
            while k < len(ls):
                t = ls[k].strip()
                if t and t not in ("{", "}") and not t.startswith(("#", "//")):
                    return t if len(ls[k]) - len(ls[k].lstrip()) > ind else None
                k += 1
            return None
        then = first_stmt(line)
        other = None
        for k in range(line, min(len(ls), line + 60)):
            t = ls[k]
            if not t.strip():
                continue
            k_ind = len(t) - len(t.lstrip())
            if k_ind < ind:
                break
            if k_ind == ind:
                if re.match(r"^\s*(?:\}\s*)?else\b", t) and not re.match(r"^\s*(?:\}\s*)?else\s+if\b", t):
                    other = first_stmt(k + 1) if not t.rstrip().endswith(("{", ":")) or True else None
                break
        return then, other

    def is_log_site(self, rel, line):
        for a, b in (self.code(rel) or {}).get("logs") or []:
            if a - 1 <= line <= b + 1:
                return True
        return False

    def callbacks(self, rel):
        """函式名稱 → 它是哪些介面的 callback：[("sub", topic)…("timer", 週期)…("srv", 名稱)]。"""
        code = self.code(rel) or {}
        out = {}
        node = (self.node_names(rel) or [None])[0]
        for s in code.get("subs") or []:
            if s.get("cb"):
                out.setdefault(s["cb"], []).append(("sub", _norm_topic(s.get("topic"), node) or s.get("expr")))
        for t in code.get("timers") or []:
            if t.get("cb"):
                out.setdefault(t["cb"], []).append(("timer", _with_params(t.get("period"), code.get("params"))))
        for s in code.get("srvs") or []:
            if s.get("cb"):
                out.setdefault(s["cb"], []).append(("srv", _norm_topic(s.get("name"), node) or s.get("expr")))
        return out

    def node_names(self, rel, cls=None):
        code = self.code(rel) or {}
        names = [n for n, c, _ in code.get("nodes") or [] if cls is None or c in (cls, None)]
        return list(dict.fromkeys(names))

    def entry_points(self, rel, func_short, depth=4):
        """func_short 在同一個檔案裡由哪些入口呼叫：callback（收到 Topic、計時器、服務）、lifecycle、建構子、main。
        回傳 [(種類, 說明, 經過的函式)]。"""
        code = self.code(rel) or {}
        cbs = self.callbacks(rel)
        callers = {}
        for q, cs in (code.get("calls") or {}).items():
            short = q.replace("::", ".").split(".")[-1]
            for c in cs:
                callers.setdefault(c, set()).add(short)
        out, seen, frontier = [], {func_short}, [(func_short, None)]
        for _ in range(depth):
            nxt = []
            for fn, via in frontier:
                if fn in cbs:
                    for kind, what in cbs[fn]:
                        out.append((kind, what, fn, via))
                if fn in _LIFECYCLE or fn == "__init__" or fn == "main" or fn in [n for n in self.class_names(rel)]:
                    out.append(("init" if fn not in _LIFECYCLE else "lifecycle", fn, fn, via))
                for c in sorted(callers.get(fn, ())):
                    if c not in seen:
                        seen.add(c)
                        nxt.append((c, via or fn if fn != func_short else c if via is None else via))
            frontier = nxt
            if not frontier:
                break
        return out

    def class_names(self, rel):
        return list(dict.fromkeys(f[2] for f in (self.code(rel) or {}).get("funcs") or [] if f[2]))

    def reads_closure(self, rel, func_short, depth=2):
        """函式讀的成員變數，加上它呼叫的同一個檔案裡的函式（往下 depth 層）讀的。"""
        code = self.code(rel) or {}
        by_short = {}
        for q in sorted(set(code.get("reads") or {}) | set(code.get("calls") or {})):
            by_short.setdefault(q.replace("::", ".").split(".")[-1], []).append(q)
        out, seen, frontier = [], set(), [func_short]
        for _ in range(depth + 1):
            nxt = []
            for fn in frontier:
                if fn in seen:
                    continue
                seen.add(fn)
                for q in by_short.get(fn, []):
                    out += [m for m in (code.get("reads") or {}).get(q, []) if m not in out]
                    nxt += [c for c in (code.get("calls") or {}).get(q, []) if c in by_short]
            frontier = nxt
        return out

    def short_body(self, rel, func_short, max_lines=3):
        """短函式（例如 _is_fresh）的內容一行：去掉 def／簽名與 docstring 後不超過 max_lines 行才回傳。"""
        code = self.code(rel) or {}
        fn = next((f for f in code.get("funcs") or [] if f[1] == func_short), None)
        if not fn:
            return None
        body = [ln.strip() for ln in self.lines(rel)[fn[3]:fn[4]] if ln.strip() and not ln.strip().startswith(("#", "//"))]
        if body and body[0].startswith(('"""', "'''")):
            q = body[0][:3]
            k = 0 if body[0].count(q) >= 2 and len(body[0]) > 3 else next((i for i, ln in enumerate(body[1:], 1) if q in ln), len(body))
            body = body[k + 1:]
        body = [ln for ln in body if ln not in ("{", "}")]
        if not body or len(body) > max_lines:
            return None
        return " ".join(body)

    def writers(self, rel, member):
        return [q.replace("::", ".").split(".")[-1] for q, ws in ((self.code(rel) or {}).get("writes") or {}).items() if member in ws]

    def param_of(self, rel, member):
        for p in (self.code(rel) or {}).get("params") or []:
            if p.get("var") == member:
                return p
        return None

    def token_sites(self, token, limit=6, prefer_files=(), prefer_pkgs=()):
        """代碼在源碼裡出現的地方：字串常值、.msg 常數（值等於代碼）的引用。回傳 ([{file, line, func, via, kind}], .msg 定義)。
        排序：這次在執行的節點的檔案 → 同一個套件（例如節點連結的核心 library）→ 其他有編譯的檔案；產生代碼的地方
        （append、=、return、push_back）排在使用的地方前面。有前面的就不列後面的。"""
        names = {name: (mtype, mrel, mline) for mtype, name, mrel, mline in self.msg_consts.get(token, [])}
        hits = []
        for rel, f in self.files.items():
            if f["kind"] not in ("py", "cpp"):
                continue
            d = f["data"]
            lines = set()
            for line, s in d.get("consts") or []:
                if s == token:
                    lines.add((line, None))
            for line, ident in d.get("idents") or []:
                if ident in names:
                    lines.add((line, ident))
            for line, via in sorted(lines):
                text = self.line_text(rel, line)
                if not self.func_at(rel, line):
                    continue   # 函式外（模組層的常數、集合的定義）不算產生或使用的地方；條件用到的常數另外列定義
                if re.search(r"\.append\(|push_back\(|emplace_back\(|\.add\(|\.insert\(", text):
                    kind, rank = "produce", 0      # 加進清單（reasons.append(…)）：最直接的「產生」
                elif re.search(r"(?<![=!<>])=(?!=)|\breturn\b", text):
                    kind, rank = "produce", 1
                else:
                    kind, rank = "use", 2
                tier = 0 if rel in prefer_files else 1 if self.pkg_of[rel][1] in prefer_pkgs else 2 if self.built(rel) else 3
                hits.append({"file": rel, "line": line, "via": via, "kind": kind, "rank": rank, "tier": tier})
        if any(h["tier"] <= 1 for h in hits):   # 有在執行的節點（或同一個套件，例如節點連結的核心 library）的，就不列其他套件的
            hits = [h for h in hits if h["tier"] <= 1]
        elif hits:
            best = min(h["tier"] for h in hits)
            hits = [h for h in hits if h["tier"] == best]
        hits.sort(key=lambda h: (h["rank"], h["tier"], h["file"], h["line"]))   # 產生代碼的地方優先（INIT：MON 核心設定它，GATE 只是比對）
        out = []
        for h in hits[:limit]:
            fn = self.func_at(h["file"], h["line"])
            h["func"] = fn[0] if fn else None
            h["code"] = self.line_text(h["file"], h["line"])[:200]
            out.append(h)
        defs = [{"msg": mtype, "const": name, "file": mrel, "line": mline} for name, (mtype, mrel, mline) in names.items()]
        return out, defs

    def const_def(self, rel, name):
        """模組／類別層的常數定義（條件裡用到的 PROTECTIVE_REASONS…）→ 「NAME = 值」一行（太長截短）；找不到回 None。"""
        ls = self.lines(rel)
        pat = re.compile(rf"^\s*(?:(?:static\s+)?(?:constexpr|const)\s+[\w:<>,\s]+?\s+)?{re.escape(name)}\b\s*(?:\[\])?\s*=")
        for i, ln in enumerate(ls, 1):
            if pat.match(ln) and not self.func_at(rel, i):
                text, j = ln.strip(), i
                depth = text.count("(") + text.count("{") + text.count("[") - text.count(")") - text.count("}") - text.count("]")
                while depth > 0 and j < len(ls) and j - i < 12:
                    nxt = ls[j].split("#", 1)[0].strip() if self.files[rel]["kind"] == "py" else ls[j].split("//", 1)[0].strip()
                    text += " " + nxt
                    depth += nxt.count("(") + nxt.count("{") + nxt.count("[") - nxt.count(")") - nxt.count("}") - nxt.count("]")
                    j += 1
                text = _short_qual(" ".join(text.split()))
                return (text if len(text) <= 300 else text[:299] + "…"), i
        return None

    def topic_decls(self, topic):
        """這個 Topic 在源碼裡的發布者與訂閱者（只看有編譯的檔案）。"""
        pubs, subs = [], []
        for rel, f in self.files.items():
            if f["kind"] not in ("py", "cpp") or not self.built(rel):
                continue
            d = f["data"]
            node = (self.node_names(rel) or [None])[0]
            for p in d.get("pubs") or []:
                if _norm_topic(p.get("topic"), node) == topic:
                    pubs.append(dict(p, file=rel))
            for s in d.get("subs") or []:
                if _norm_topic(s.get("topic"), node) == topic:
                    subs.append(dict(s, file=rel))
        return pubs, subs


# =====================================================================================================================
# 一次分析的源碼脈絡（job 用）
# =====================================================================================================================
_TOKEN_IN_TEXT = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{3,})(?![A-Za-z0-9_])")
_NOISE_TOKENS = {"INFO", "WARN", "ERROR", "FATAL", "DEBUG", "TRUE", "FALSE", "NULL", "NONE", "JSON", "YAML", "ROS", "MCAP",
                 "HZ", "ID", "OK"}


def tokens_in(text):
    return [t for t in dict.fromkeys(_TOKEN_IN_TEXT.findall(text or "")) if t not in _NOISE_TOKENS]


def _with_params(expr, params):
    """計時器週期之類的運算式：用到參數就接上預設值（1.0 / self.output_rate_hz → …，output_rate_hz=20.0）。"""
    if not expr:
        return expr
    extra = [f"{p['name']}={p.get('default')}" for p in params or []
             if re.search(rf"\b(?:{re.escape(p['name'])}|{re.escape(p.get('var') or p['name'])})\b", expr)]
    return expr + (f"，{'、'.join(dict.fromkeys(extra))}" if extra else "")


def _when_text(eps):
    """入口 → 一句話：計時器 cb（週期）；收到 /a（cb）、/b（cb）；服務；lifecycle；啟動時。同一類併在一起。"""
    timers, subs, srvs, other = [], [], [], []
    for kind, what, fn, _via in eps:
        if kind == "sub":
            subs.append(f"{what}（{fn}）")
        elif kind == "timer":
            timers.append(f"計時器 {fn}（週期 {what}）")
        elif kind == "srv":
            srvs.append(f"服務 {what}（{fn}）")
        elif kind == "lifecycle":
            other.append(f"lifecycle {fn}")
        else:
            other.append("啟動時")
    parts = list(dict.fromkeys(timers))
    if subs:
        parts.append("收到 " + "、".join(dict.fromkeys(subs)))
    parts += list(dict.fromkeys(srvs)) + list(dict.fromkeys(other))
    return "；".join(parts)


def is_framework_topic(topic):
    """ROS 2 框架或錄製工具自己的 Topic：源碼脈絡不列。"""
    t = str(topic or "")
    return (t in ("/rosout", "/rosout_agg", "/parameter_events", "/clock", "/events/write_split")
            or t.endswith(("/transition_event", "/_action/status", "/_action/feedback")))


def _is_recorder(node):
    return bool(re.match(r"^(rosbag2(_\w+)?|ros2_bag\w*)$", str(node or "").strip("/").split("/")[-1]))


def _short_qual(text):
    """SafetyGateStatus.REASON_X → REASON_X（條件、常數定義裡重複的型別前綴拿掉，縮短）。"""
    return re.sub(r"\b[A-Za-z_]\w*(?:\.|::)(?=[A-Z][A-Z0-9_]{2,}\b)", "", text or "")


def value_tokens(message):
    """Log 訊息裡「值」的代碼（reasons=[A,B]、mode=X）；event=名稱 的事件名稱不算（Log 位置已經說明是哪個函式印的）。"""
    events = set(re.findall(r"\bevent=([A-Z][A-Z0-9_]+)", message or ""))
    return [t for t in tokens_in(message) if t not in events]


class JobSource:
    """一次分析用到的源碼脈絡：依數據裡的 Topic 與 Log 訊號，從索引挑出這次在執行的節點、Topic 之間的關係、Log 的源碼位置
    與代碼的條件。在執行的節點＝Log 印出的節點、數據裡有 /<節點>/transition_event 的 lifecycle 節點，再加上同一個 launch 檔
    一起啟動的節點；同一個節點名稱有好幾個實作時，用 Log 的源碼位置（其次 launch 的執行檔）決定是哪一個。工作區裡其他也用到
    同一個 Topic（例如 /cmd_vel）的節點不列——這次沒有在執行。"""

    def __init__(self, idx, topics, signals, msg_defs=None):
        """topics：{Topic: {"type", "count"}}（數據裡的全部 Topic）；signals：rosout_parser 的訊號（有 sources）。"""
        self.idx, self.topics = idx, topics
        self.signals = [s for s in signals or [] if not _is_recorder(s.get("node"))]
        self.msg_defs = msg_defs or {}
        self.log_sites, self.unresolved, self.confirmed = {}, [], set()
        for s in self.signals:
            for src in s.get("sources") or []:
                line = int(src.get("line") or 0)
                rel = idx.resolve(src.get("file"), src.get("function"))
                if not rel:
                    self.unresolved.append({"id": s["id"], "file": src.get("file")})
                    continue
                fn = idx.func_at(rel, line)
                ok_line, ok_func = idx.is_log_site(rel, line), bool(fn) and fn[1] == src.get("function")
                note = None
                if not ok_line or not ok_func:
                    bits = (["那一行附近不是 Log 呼叫"] if not ok_line else []) + \
                           ([f"那一行在 {fn[1] if fn else '函式外'}、Log 寫 {src.get('function')}"] if not ok_func else [])
                    note = "、".join(bits) + "——源碼可能跟錄製時的版本不同"
                self.log_sites.setdefault(s["id"], {"file": rel, "line": line, "func": fn[1] if fn else src.get("function"),
                                                    "ok": not note, "note": note, "node": s.get("node")})
                if not note:
                    self.confirmed.add(rel)
        self.running, self.impl, self.launched, self.ambiguous = self._running()
        self.nodes = self._nodes()
        self.prefer_files = {c["file"] for c in self.nodes} | self.confirmed
        self.prefer_pkgs = {c["pkg"] for c in self.nodes if c["pkg"]}

    # ---- 這次在執行的節點
    def _running(self):
        idx = self.idx
        declared = {}
        for rel, f in idx.files.items():
            if f["kind"] in ("py", "cpp") and idx.built(rel):
                for n in idx.node_names(rel):
                    declared.setdefault(n, []).append(rel)
        names = set()
        for s in self.signals:
            n = str(s.get("node") or "").strip("/").split("/")[-1].split(".")[-1]
            if n:
                names.add(n)
        for t in self.topics:
            parts = t.strip("/").split("/")
            if len(parts) >= 2 and (parts[-1] == "transition_event" or parts[0] in declared):
                names.add(parts[0])
        launched = {}
        for rel, f in idx.files.items():
            if f["kind"] != "launch":
                continue
            ns = f["data"].get("nodes") or []
            if any(n.get("name") in names for n in ns):
                for n in ns:
                    if n.get("name"):
                        launched.setdefault(n["name"], dict(n, launch=rel))
        names |= set(launched)
        for t, info in self.topics.items():   # 數據裡有訊息、源碼裡只有一個節點會發布的 Topic
            if info.get("count"):
                pubs, _ = idx.topic_decls(t)
                cand = {n for p in pubs for n in idx.node_names(p["file"])}
                if len(cand) == 1:
                    names |= cand
        impl, ambiguous = {}, []
        for n in sorted(names):
            cands = declared.get(n, [])
            conf = [r for r in cands if r in self.confirmed]
            if conf:
                impl[n] = conf[0]
                continue
            ln = launched.get(n)
            if ln:
                exe_files = idx.exes.get((ln.get("package"), ln.get("executable"))) or []
                pick = [r for r in cands if r in exe_files] or [r for r in exe_files if r in idx.files and idx.code(r)]
                if pick:
                    impl[n] = pick[0]
                    continue
                if ln.get("package") not in idx.packages:
                    continue
            if len(cands) == 1:
                impl[n] = cands[0]
            elif cands:
                ambiguous.append((n, cands))
        return names, impl, launched, ambiguous

    def _nodes(self):
        idx, out = self.idx, []
        for name, rel in sorted(self.impl.items(), key=lambda x: x[1]):
            code = idx.code(rel) or {}
            card = {"file": rel, "name": name, "pkg": idx.pkg_of[rel][1], "lang": "Python" if idx.files[rel]["kind"] == "py" else "C++",
                    "subs": [], "pubs": [], "timers": [], "srvs": [], "params": []}
            writes = code.get("writes") or {}
            for s in code.get("subs") or []:
                cbq = next((q for q in writes if q.replace("::", ".").split(".")[-1] == s.get("cb")), None)
                card["subs"].append({"topic": _norm_topic(s.get("topic"), name) or s.get("expr"), "type": s.get("type"),
                                     "cb": s.get("cb"), "line": s["line"], "writes": writes.get(cbq, [])[:6] if cbq else []})
            pubvars = {}
            for p in code.get("pubs") or []:
                t = _norm_topic(p.get("topic"), name) or p.get("expr")
                pubvars.setdefault(p.get("var"), t)
                card["pubs"].append({"topic": t, "type": p.get("type"), "var": p.get("var"), "line": p["line"], "sites": []})
            for var, line, q in code.get("publish") or []:
                pub = next((p for p in card["pubs"] if p["topic"] == pubvars.get(var)), None)
                if pub is None or not q:
                    continue
                short = q.replace("::", ".").split(".")[-1]
                if not any(x["func"] == short for x in pub["sites"]):
                    eps = idx.entry_points(rel, short)
                    pub["sites"].append({"line": line, "func": short, "when": _when_text(eps),
                                         "inputs": self._topic_inputs(rel, short, eps)})
            card["timers"] = [{"period": _with_params(t.get("period"), code.get("params")), "cb": t.get("cb"), "line": t["line"]}
                              for t in code.get("timers") or []]
            card["srvs"] = [{"name": _norm_topic(s.get("name"), name) or s.get("expr"), "cb": s.get("cb"), "line": s["line"]}
                            for s in code.get("srvs") or []]
            card["params"] = [{"name": p["name"], "default": p.get("default"), "var": p.get("var")} for p in code.get("params") or []]
            out.append(card)
        return out

    def _topic_inputs(self, rel, func_short, eps):
        """發布的函式依賴哪些輸入 Topic：觸發它的訂閱（收到哪個 Topic 時呼叫），加上它（與它呼叫的函式）讀的成員變數
        是由哪些訂閱的 callback 寫入的。"""
        idx = self.idx
        cbs = idx.callbacks(rel)   # Topic 名稱已經依節點正規化
        out = [what for kind, what, _fn, _via in eps if kind == "sub" and what]
        for m in idx.reads_closure(rel, func_short):
            for w in idx.writers(rel, m):
                out += [x for k, x in cbs.get(w, []) if k == "sub" and x]
        return list(dict.fromkeys(out))

    def topic_source_line(self, topic, compact=False):
        """每個 Topic 的源碼一行：誰發布、什麼時候、依賴哪些輸入 Topic、誰訂閱。compact：發布的時機只寫一種
        （有計時器寫計時器的週期，否則寫收到哪個 Topic 時），不列函式名稱。
        ROS 2 框架自己的 Topic（/rosout、/parameter_events、lifecycle 的 transition_event…）回空字串。"""
        if is_framework_topic(topic):
            return ""
        pubs = [(c, p) for c in self.nodes for p in c["pubs"] if p["topic"] == topic]
        subs = [(c, x) for c in self.nodes for x in c["subs"] if x["topic"] == topic]
        parts = []
        for c, p in pubs[:2]:
            site = p["sites"][0] if p["sites"] else None
            if compact:
                timer = next((t for t in c["timers"] if site and t["cb"] in site["when"]), None)
                trig = (f"計時器，週期 {timer['period']}" if timer else
                        f"收到 {site['inputs'][0]} 時" if site and site.get("inputs") and "收到" in site["when"] else "")
                txt = f"{c['name']} 發布" + (f"（{trig}）" if trig else "")
            else:
                txt = f"{c['name']} 發布" + (f"（{site['func']} ← {site['when']}）" if site and site["when"] else
                                              f"（{site['func']}）" if site else "")
            ins = []
            for x in p["sites"][:2]:
                ins += [t for t in x.get("inputs") or [] if t != topic]
            if ins:
                txt += "；依賴的輸入：" + "、".join(f"{t}{self.data_mark(t)}" for t in dict.fromkeys(ins))
            parts.append(txt)
        if not pubs:
            parts.append("在執行的節點的源碼裡沒有發布者" + ("（可能是外部套件的節點）" if self.external_nodes() else ""))
        if subs:
            parts.append("訂閱者：" + "、".join(f"{c['name']}（{x['cb']}）" for c, x in subs))
        return "源碼：" + "；".join(parts)

    def missing_inputs(self):
        """在執行的節點會訂閱、但數據裡沒有（或沒有訊息）的 Topic → [(Topic, [節點.callback…])]。"""
        out = {}
        for c in self.nodes:
            for x in c["subs"]:
                if self.data_mark(x["topic"]):
                    out.setdefault(x["topic"], []).append(f"{c['name']}.{x['cb']}")
        return sorted(out.items())

    def external_nodes(self):
        return [n for n in self.launched.values() if n.get("package") and n["package"] not in self.idx.packages]

    def data_mark(self, topic):
        info = self.topics.get(topic)
        if info is None:
            return "（✗數據裡沒有）"
        if not info.get("count"):
            return "（✗沒有訊息）"
        return ""

    # ---- 代碼的條件
    def token_info(self, token, limit=2):
        idx = self.idx
        sites, defs = idx.token_sites(token, limit=limit * 3, prefer_files=self.prefer_files, prefer_pkgs=self.prefer_pkgs)
        out = []
        for h in sites[:limit]:
            rel, line = h["file"], h["line"]
            fn = idx.func_at(rel, line)
            cond = idx.ctrl_at(rel, line, fn)
            item = {"file": rel, "line": line, "func": fn[1] if fn else None, "code": _short_qual(h["code"]), "kind": h["kind"],
                    "cond": _short_qual(cond[2]) if cond else None, "cond_line": cond[0] if cond else None,
                    "inputs": self._inputs(rel, fn, cond[2]) if cond else []}
            br = idx.branch_preview(rel, line) if h["kind"] == "use" else None
            if br and br[0]:   # 代碼在 if 的條件裡：兩個分支各做什麼
                item["branches"] = [_short_qual(br[0]), _short_qual(br[1]) if br[1] else None]
            out.append(item)
        return {"token": token, "sites": out, "defs": defs[:2]}

    def _inputs(self, rel, fn, cond):
        """條件讀的東西 → 從哪裡來：成員變數（self.x、x_、this->x；區域變數往回找一次指定）由哪個 callback（收到哪個 Topic）
        或參數寫入；模組／類別層的常數（PROTECTIVE_REASONS…）列出定義。"""
        idx = self.idx
        code = idx.code(rel) or {}
        members = re.findall(r"self\.(\w+)", cond) + re.findall(r"(?<![\w.>])(\w+_)\b", cond) + re.findall(r"this->(\w+)", cond)
        consts = [c for c in re.findall(r"(?<![\w.])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b", cond)]
        if fn:
            assigns = (code.get("assigns") or {}).get(fn[0]) or {}
            for local in re.findall(r"(?<![\w.])([a-z_]\w*)(?![\w(])", cond):
                rhs = assigns.get(local)
                if rhs:
                    members += re.findall(r"self\.(\w+)", rhs) + re.findall(r"(?<![\w.>])(\w+_)\b", rhs)
        cbs = idx.callbacks(rel)
        out = []
        for call in dict.fromkeys(re.findall(r"(?:self\.|this->)?([A-Za-z_]\w*)\s*\(", cond)):
            body = idx.short_body(rel, call)
            if body:
                out.append(f"{call}：`{body}`")
        log_tokens = set(self.signal_tokens())
        for c in dict.fromkeys(consts):
            d = idx.const_def(rel, c)
            if d:
                text = f"{_short_qual(d[0])}（第 {d[1]} 行）"
                rhs = d[0].split("=", 1)[1] if "=" in d[0] else ""
                names = re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", rhs)
                members = {idx.const_value.get(x, x) for x in names}
                family = {x.split("_")[0] for x in names if x in idx.const_value}   # 成員是 REASON_* 常數：只對照同一類的代碼

                def same_family(t):
                    return any(name.split("_")[0] in family for _m, name, _r, _l in idx.msg_consts.get(t, []))
                inside = sorted(t for t in log_tokens if t in members)
                outside = sorted(t for t in log_tokens if t not in members and same_family(t))
                if inside or outside:   # Log 裡出現的代碼哪些在這個集合裡（源碼與 Log 對照的事實，不是結論）
                    text += (f"；這份 Log 的代碼在 {c} 裡：{'、'.join(inside) or '（沒有）'}"
                             + (f"，不在 {c} 裡：{'、'.join(outside)}" if outside else ""))
                out.append(text)
        for m in dict.fromkeys(members):
            p = idx.param_of(rel, m)
            if p:
                out.append(f"{m} ← 參數 {p['name']}（預設 {p.get('default')}）")
                continue
            ws = [w for w in idx.writers(rel, m) if w != "__init__" and w not in _LIFECYCLE]
            if not ws:
                continue
            desc = []
            for w in ws[:3]:
                kinds = cbs.get(w) or []
                if kinds:
                    desc.append(f"{w}（" + "、".join(f"收到 {x}{self.data_mark(x)}" if k == "sub" else f"計時器 {x}" if k == "timer"
                                                     else f"服務 {x}" for k, x in kinds) + "）")
                else:
                    eps = [e for e in idx.entry_points(rel, w) if e[2] != w or e[0] != "init"]
                    callers = [] if eps else self._cross_callers(rel, w)
                    desc.append(w + (f"（← {_when_text(eps)}）" if eps else f"（← {'、'.join(callers)}）" if callers else ""))
            out.append(f"{m} ← " + "、".join(desc))
        return out[:6]

    def _cross_callers(self, rel, func_short, limit=3):
        """別的檔案（這次在執行的節點）裡呼叫 func_short 的函式與它的入口：核心 library 的函式由節點的 callback 呼叫時，
        例如 startInitBuffer ← system_health_monitor_node.cpp 的 on_activate。"""
        idx, out = self.idx, []
        for f in sorted(self.prefer_files):
            if f == rel:
                continue
            code = idx.code(f) or {}
            for q in sorted(set(code.get("calls") or {}) | set(code.get("ocalls") or {})):
                cs = ((code.get("calls") or {}).get(q) or []) + ((code.get("ocalls") or {}).get(q) or [])
                if func_short in cs:
                    short = q.replace("::", ".").split(".")[-1]
                    when = _when_text(idx.entry_points(f, short))
                    out.append(f"{os.path.basename(f)} 的 {short}" + (f"（{when}）" if when else ""))
        return list(dict.fromkeys(out))[:limit]

    # ---- 文字
    def node_lines(self, only=None, show_params=True, compact=False):
        """節點卡。compact：只列檔案、計時器、服務、參數（發布／訂閱已經寫在每個 Topic 的源碼一行）。"""
        rows = []
        for c in self.nodes:
            if only is not None and c["name"] not in only:
                continue
            rows.append(f"- {c['name']}｜{c['file']}（{c['lang']}）")
            if c["subs"] and not compact:
                rows.append("  訂閱：" + "；".join(f"{s['topic']}{self.data_mark(s['topic'])} → {s['cb']}"
                                                  + (f"（寫入 {'、'.join(s['writes'])}）" if s["writes"] else "") for s in c["subs"]))
            if c["pubs"] and not compact:
                parts = []
                for p in c["pubs"]:
                    how = "；".join(x["func"] + (f" ← {x['when']}" if x["when"] else "") for x in p["sites"][:2]) \
                        or "（源碼裡沒有找到 publish 呼叫）"
                    parts.append(f"{p['topic']}{self.data_mark(p['topic'])}：{how}")
                rows.append("  發布：" + "；".join(parts))
            if c["timers"]:
                rows.append("  計時器：" + "；".join(f"{t['cb']}（週期 {t['period']}）" for t in c["timers"]))
            if c["srvs"]:
                rows.append("  服務：" + "；".join(f"{s['name']} → {s['cb']}" for s in c["srvs"]))
            if show_params and c["params"]:
                rows.append("  參數：" + "、".join(f"{p['name']}={p['default']}" for p in c["params"][:8]))
        return rows

    def orphan_lines(self):
        rows = []
        published = {p["topic"] for c in self.nodes for p in c["pubs"]}
        no_pub = [t for t, info in sorted(self.topics.items()) if t not in published and info.get("count") and not is_framework_topic(t)]
        ext = self.external_nodes()
        if no_pub:
            rows.append(f"- 數據裡有、在執行的節點的源碼裡沒有發布者的 Topic：{'、'.join(no_pub)}"
                        + ("（可能是外部套件的節點發布的）" if ext else ""))
        if ext:
            rows.append("- 源碼不在工作區的節點（同一個 launch 檔啟動）：" + "、".join(
                f"{n.get('name') or n.get('executable')}（{n['package']} 套件）" for n in ext))
        for n, cands in self.ambiguous:
            rows.append(f"- {n} 有 {len(cands)} 個實作（{'、'.join(cands[:3])}），這份數據看不出是哪一個，沒有列出")
        return rows

    def log_lines(self, ids=None):
        rows, groups = [], {}
        for sid, s in self.log_sites.items():
            if ids is not None and sid not in ids:
                continue
            groups.setdefault((s["file"], s["func"], s["note"]), []).append((sid, s["line"]))
        for (rel, func, note), items in groups.items():
            ids_text = "、".join(f"{sid}" for sid, _ in items[:6]) + (f" 等 {len(items)} 個" if len(items) > 6 else "")
            lines = "/".join(dict.fromkeys(str(ln) for _, ln in items))
            rows.append(f"- {ids_text}：{os.path.basename(rel)}:{lines} {func}" + (f"（{note}）" if note else ""))
        return rows

    def token_lines(self, tokens, limit=10, per_token=2):
        rows, n = [], 0
        for tok in tokens:
            if n >= limit:
                break
            info = self.token_info(tok, limit=per_token)
            if not info["sites"]:
                continue
            n += 1
            for site in info["sites"]:
                where = f"{os.path.basename(site['file'])}:{site['line']} {site['func'] or ''}".rstrip()
                txt = f"- {tok}（{where}）：`{site['code']}`"
                if site["cond"] and site["cond"] != site["code"]:
                    txt += f"；條件 `{site['cond']}`（第 {site['cond_line']} 行）"
                if site.get("branches"):
                    txt += f"；成立時 `{site['branches'][0]}`" + (f"、否則 `{site['branches'][1]}`" if site["branches"][1] else "")
                if site["inputs"]:
                    txt += "；" + "；".join(site["inputs"])
                rows.append(txt)
        return rows

    def msg_comment(self, mtype, n=200):
        out = []
        for ln in (self.msg_defs.get(mtype) or "").splitlines():
            s = ln.strip()
            if not s:
                if out:
                    break
                continue
            if not s.startswith("#"):
                break
            out.append(s.lstrip("#").strip())
        text = " ".join(x for x in out if x)
        return text if len(text) <= n else text[: n - 1] + "…"

    def function_code(self, rel, func_short, mark=(), max_lines=40):
        code = self.idx.code(rel) or {}
        fn = next((f for f in code.get("funcs") or [] if f[1] == func_short), None)
        if not fn:
            return None
        a, b = fn[3], fn[4]
        if b - a + 1 <= max_lines:
            return self.idx.snippet(rel, a, b, mark)
        marks = [m for m in mark if a <= m <= b]
        c = (min(marks) + max(marks)) // 2 if marks else a + max_lines // 2
        a2 = max(a + 1, c - max_lines // 2)
        b2 = min(b, a2 + max_lines - 1)
        return (self.idx.snippet(rel, a, a) + "\n     …\n" + self.idx.snippet(rel, a2, b2, mark)
                + ("\n     …" if b2 < b else ""))

    def signal_tokens(self, ids=None, warn_only=False):
        toks = []
        for s in self.signals:
            if ids is not None and s["id"] not in ids:
                continue
            if warn_only and s.get("level") not in ("WARN", "ERROR", "FATAL"):
                continue
            toks += value_tokens(s.get("message"))
        return list(dict.fromkeys(toks))

    def summary(self):
        return {"root": self.idx.root, "files": len(self.idx.files), "index_seconds": self.idx.seconds,
                "running": sorted(self.running), "nodes": {c["name"]: c["file"] for c in self.nodes},
                "log_sites": self.log_sites, "unresolved": self.unresolved[:10],
                "external": [n.get("name") for n in self.external_nodes()], "ambiguous": [n for n, _ in self.ambiguous]}
