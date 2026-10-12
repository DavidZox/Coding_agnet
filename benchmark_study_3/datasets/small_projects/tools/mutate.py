"""產生 mutant（人為植入的小錯誤），給「寫測試」任務算 mutation score、給「修 bug」任務當植入的 bug。

只用標準庫，結果可重現（固定種子）：
- Python：用 ast 找變異點，一次只改一個地方，再用 ast.unparse 寫回整個檔案（格式會被正規化，註解會消失，
  但行為只差那一個地方）。運算子：比較（< ↔ <=、> ↔ >=、== ↔ !=、in ↔ not in、is ↔ is not）、算術（+ ↔ -、* ↔ /、// ↔ /、
  % → *）、布林（and ↔ or）、拿掉 not、常數（數字 n → n+1、0 ↔ 1、True ↔ False、非空字串 → ""）、return x → return None、
  if 條件取反、增量指派（+= ↔ -=）。
- C／C++：在 token 層級改（略過註解、字串、字元常數、前置處理指令）：比較（< ↔ <=、> ↔ >=、== ↔ !=）、算術（+ ↔ -、* ↔ /）、
  邏輯（&& ↔ ||）、++ ↔ --、+= ↔ -=、true ↔ false、整數常數（0 ↔ 1、n → n+1）、拿掉 !。為了避開樣板、指標、串流運算子，
  < > * 只改「兩邊都有空白」的；>> << -> 不改。編不過的 mutant 由呼叫端丟掉。

    python3 mutate.py list <檔案>            # 列出所有變異點
    python3 mutate.py apply <檔案> <編號>     # 印出第 N 個 mutant 的完整內容
"""
import ast
import copy
import random
import re
import sys

# ================================================================ Python
_CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
             ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
_BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult, ast.FloorDiv: ast.Div, ast.Mod: ast.Mult}
_SYM = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=", ast.In: "in", ast.NotIn: "not in",
        ast.Is: "is", ast.IsNot: "is not", ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%"}


def _docstring_nodes(tree):
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                skip.add(id(first.value))
    return skip


def py_points(src):
    """回傳變異點清單：[{"path": 節點在 ast.walk 裡的序號, "kind", "line", "desc"}]。"""
    tree = ast.parse(src)
    skip = _docstring_nodes(tree)
    points = []
    for idx, node in enumerate(ast.walk(tree)):
        line = getattr(node, "lineno", None)
        if isinstance(node, ast.Compare):
            for k, op in enumerate(node.ops):
                if type(op) in _CMP_SWAP:
                    points.append({"node": idx, "kind": "cmp", "sub": k, "line": line,
                                   "desc": f"{_SYM[type(op)]} → {_SYM[_CMP_SWAP[type(op)]]}"})
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN_SWAP:
            if isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                continue                      # 字串格式化（"%s" % x）不算算術
            points.append({"node": idx, "kind": "bin", "line": line, "desc": f"{_SYM[type(node.op)]} → {_SYM[_BIN_SWAP[type(node.op)]]}"})
        elif isinstance(node, ast.AugAssign) and type(node.op) in (ast.Add, ast.Sub):
            points.append({"node": idx, "kind": "aug", "line": line, "desc": f"{_SYM[type(node.op)]}= → {_SYM[_BIN_SWAP[type(node.op)]]}="})
        elif isinstance(node, ast.BoolOp):
            points.append({"node": idx, "kind": "bool", "line": line, "desc": "and ↔ or"})
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            points.append({"node": idx, "kind": "not", "line": line, "desc": "拿掉 not"})
        elif isinstance(node, ast.Constant) and id(node) not in skip:
            v = node.value
            if isinstance(v, bool):
                points.append({"node": idx, "kind": "const", "line": line, "desc": f"{v} → {not v}"})
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                points.append({"node": idx, "kind": "const", "line": line, "desc": f"{v} → {_num_mut(v)}"})
            elif isinstance(v, str) and v and len(v) <= 40 and line is not None:
                points.append({"node": idx, "kind": "const", "line": line, "desc": f"{v!r} → ''"})
        elif isinstance(node, ast.Return) and node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None):
            points.append({"node": idx, "kind": "ret", "line": line, "desc": "return … → return None"})
        elif isinstance(node, (ast.If, ast.While)) and not isinstance(node.test, ast.Constant):
            points.append({"node": idx, "kind": "neg", "line": line, "desc": "條件取反"})
    return points


def _num_mut(v):
    if v == 0:
        return 1
    if v == 1:
        return 0
    return v + 1


def py_apply(src, point):
    return py_apply_many(src, [point])


def py_apply_many(src, points):
    """同一個檔案一次套用多個變異點（節點序號都是對原始檔算的；ast.unparse 會重排格式，所以不能一個一個套）。"""
    tree = ast.parse(src)
    nodes = list(ast.walk(tree))
    for point in points:
        _py_mutate(tree, nodes[point["node"]], point)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def _py_mutate(tree, target, point):
    kind = point["kind"]
    if kind == "cmp":
        target.ops[point["sub"]] = _CMP_SWAP[type(target.ops[point["sub"]])]()
    elif kind == "bin":
        target.op = _BIN_SWAP[type(target.op)]()
    elif kind == "aug":
        target.op = _BIN_SWAP[type(target.op)]()
    elif kind == "bool":
        target.op = ast.Or() if isinstance(target.op, ast.And) else ast.And()
    elif kind == "not":
        parent = _parent_of(tree, target)
        _replace_child(parent, target, target.operand)
    elif kind == "const":
        v = target.value
        target.value = (not v) if isinstance(v, bool) else (_num_mut(v) if isinstance(v, (int, float)) else "")
    elif kind == "ret":
        target.value = ast.Constant(value=None)
    elif kind == "neg":
        target.test = ast.UnaryOp(op=ast.Not(), operand=target.test)


def _parent_of(tree, child):
    for node in ast.walk(tree):
        for field, value in ast.iter_fields(node):
            if value is child or (isinstance(value, list) and any(v is child for v in value)):
                return node
    return None


def _replace_child(parent, old, new):
    for field, value in ast.iter_fields(parent):
        if value is old:
            setattr(parent, field, new)
            return
        if isinstance(value, list):
            for i, v in enumerate(value):
                if v is old:
                    value[i] = new
                    return


# ================================================================ C／C++
_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<string>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
  | (?P<num>\b\d+\.\d*(?:[eE][+-]?\d+)?[fFlL]?\b|\b\d+(?:[uUlL]+)?\b)
  | (?P<ident>[A-Za-z_]\w*)
  | (?P<op>->|\+\+|--|<<=|>>=|<<|>>|<=|>=|==|!=|&&|\|\||\+=|-=|\*=|/=|%=|&=|\|=|\^=|::|[-+*/%<>=!&|^~?:;,.(){}\[\]#])
  | (?P<other>.)
""", re.S | re.X)

_C_SWAP = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "==": "!=", "!=": "==", "+": "-", "-": "+", "*": "/", "/": "*",
           "&&": "||", "||": "&&", "++": "--", "--": "++", "+=": "-=", "-=": "+=", "true": "false", "false": "true"}
_SPACED_ONLY = {"<", ">", "*", "+", "-", "/"}      # 兩邊都要有空白才改（避開樣板、指標、一元運算子）


def c_tokens(src):
    toks, pos = [], 0
    for m in _TOKEN_RE.finditer(src):
        kind = m.lastgroup
        toks.append((kind, m.group(), m.start()))
    return toks


def c_points(src):
    toks = c_tokens(src)
    points = []
    line_starts = [0] + [i + 1 for i, ch in enumerate(src) if ch == "\n"]

    def line_of(pos):
        lo, hi = 0, len(line_starts)
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid
        return lo + 1

    pre_lines = set()
    for i, ls in enumerate(line_starts):
        rest = src[ls:src.find("\n", ls) if src.find("\n", ls) >= 0 else len(src)].lstrip()
        if rest.startswith("#"):
            pre_lines.add(i + 1)
    for k, (kind, text, pos) in enumerate(toks):
        line = line_of(pos)
        if line in pre_lines:
            continue
        prev_ws = k > 0 and toks[k - 1][0] == "ws"
        next_ws = k + 1 < len(toks) and toks[k + 1][0] == "ws"
        if kind == "op" and text in _C_SWAP:
            if text in _SPACED_ONLY and not (prev_ws and next_ws):
                continue
            if text in ("<", ">") and _looks_template(toks, k):
                continue
            points.append({"tok": k, "line": line, "desc": f"{text} → {_C_SWAP[text]}", "new": _C_SWAP[text]})
        elif kind == "ident" and text in ("true", "false"):
            points.append({"tok": k, "line": line, "desc": f"{text} → {_C_SWAP[text]}", "new": _C_SWAP[text]})
        elif kind == "num" and "." not in text and not _in_index_decl(toks, k):
            digits = re.match(r"\d+", text).group()
            val = int(digits)
            new = "1" if val == 0 else ("0" if val == 1 else str(val + 1))
            points.append({"tok": k, "line": line, "desc": f"{digits} → {new}", "new": new + text[len(digits):]})
        elif kind == "op" and text == "!" and k + 1 < len(toks) and toks[k + 1][1] != "=":
            points.append({"tok": k, "line": line, "desc": "拿掉 !", "new": ""})
    return points


def _looks_template(toks, k):
    """< 或 > 前後是型別名稱（std::vector < int >）之類的就跳過：前一個非空白 token 是識別字、後一個是識別字或 ::，
    而且同一行還有對應的 > 或 <。粗略判斷，編不過的 mutant 呼叫端會丟掉。"""
    def neighbor(step):
        j = k + step
        while 0 <= j < len(toks) and toks[j][0] == "ws":
            j += step
        return toks[j] if 0 <= j < len(toks) else ("", "", 0)
    prev, nxt = neighbor(-1), neighbor(1)
    return prev[1] in ("vector", "map", "set", "list", "pair", "array", "unique_ptr", "shared_ptr", "optional", "template",
                       "function", "queue", "stack", "deque", "unordered_map", "unordered_set") or nxt[1] in ("typename", "class")


def _in_index_decl(toks, k):
    """陣列宣告的大小（int a[10]）與 #include 之類的不改；這裡只排除前一個 token 是 [ 而後一個是 ] 的情況中、緊接在型別宣告後的。"""
    return False


def c_apply(src, point):
    toks = c_tokens(src)
    kind, text, pos = toks[point["tok"]]
    return src[:pos] + point["new"] + src[pos + len(text):]


# ================================================================ 共用
def points_for(path, src):
    return py_points(src) if path.endswith(".py") else c_points(src)


def apply_for(path, src, point):
    return py_apply(src, point) if path.endswith(".py") else c_apply(src, point)


def sample(points_by_file, limit, seed=20261010):
    """各檔案輪流抽，總數不超過 limit（同一行最多 2 個）。回傳 [(檔案, point)]。"""
    rng = random.Random(seed)
    pools = {}
    for f, pts in points_by_file.items():
        per_line = {}
        kept = []
        for p in pts:
            if per_line.get(p["line"], 0) < 2:
                per_line[p["line"]] = per_line.get(p["line"], 0) + 1
                kept.append(p)
        rng.shuffle(kept)
        pools[f] = kept
    out = []
    while len(out) < limit and any(pools.values()):
        for f in sorted(pools):
            if pools[f] and len(out) < limit:
                out.append((f, pools[f].pop()))
    return out


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    with open(path, encoding="utf-8") as f:
        src = f.read()
    pts = points_for(path, src)
    if cmd == "list":
        for i, p in enumerate(pts):
            print(f"{i:4d}  第 {p['line']} 行  {p['desc']}")
    elif cmd == "apply":
        sys.stdout.write(apply_for(path, src, pts[int(sys.argv[3])]))


if __name__ == "__main__":
    main()
