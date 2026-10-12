"""code_check：不執行程式的靜態檢查——語法、未定義的名稱、專案內的匯入對不對得上（跨檔一致性）。

小模型改程式最常見的錯：呼叫了不存在的函式、忘了 import、改了 A 檔的函式名稱卻沒改 B 檔的 import。這支腳本專抓這幾種：
- 語法：Python（compile）、JSON、TOML、YAML。
- 未定義的名稱（Python）：整個模組裡從來沒有被定義、匯入、指派過、也不是內建的名稱（只看整個模組，不分作用域——寧可漏抓也不誤報；
  模組有 `from x import *` 時跳過）。
- 專案內的匯入：`from 模組 import 名稱` 的模組是專案裡的檔案時，檢查那個檔案真的有定義這個名稱（或它是子模組）。
- 會污染其他測試的測試檔：在模組層級（import 時就執行）替換 sys.modules、或改掉專案模組／類別的屬性、patch(...).start()——
  pytest 在同一個程序跑所有測試，其他測試檔也會拿到假的東西。
- C／C++：用編譯器編譯一次（gcc／g++，輸出丟到 /dev/null，不留下檔案）——未宣告的名稱、型別不合、標頭與實作的簽名不一致、
  缺 #include、非 void 函式忘了 return（-Werror=return-type）都抓得到；有 compile_commands.json（CMake 的 -DCMAKE_EXPORT_COMPILE_COMMANDS=ON）就照它的參數，沒有就推測
  include 目錄（專案根目錄、include／src、放標頭的目錄）。改的是標頭時，編譯 #include 它的原始檔（沒有就單獨檢查標頭）。
  函式「有宣告沒實作」這種連結錯誤要等 code_test 建置時才看得到。
- 規格簽名（--spec 規格文件）：從規格文件的 API 行（UML 類別圖的「+name(參數)」、架構設計的「- name(參數): 說明」）抓出
  函式與方法的參數，跟這些檔案裡的定義比參數個數（有預設值的算可選；文件裡同一個名稱寫了好幾種就符合其中一種即可）。
  實測 e4b 照 DevBench 規格實作時，把規格的 update_velocity(pos_best_g) 寫成 update_velocity(self, pos_best_g, w, c1, c2)，
  官方測試直接 TypeError；程式碼本身沒有錯，只有對照規格才看得出來。coding job 的任務附了規格文件時，worker 的驗證會自動帶上。
有安裝 ruff 或 pyflakes 時另外附上它們的結果。不給路徑時：coding job 中檢查這個 job 改過的檔案，否則檢查目前目錄的所有
Python 與 C／C++ 檔。
"""
import ast
import builtins
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc
import _cpp_common as cp

MAX_ISSUES = 60
USAGE = ("用法: scripts/code_check_cmd.py [檔案或目錄 ...] [--spec 規格文件 ...]\n"
         "  不給檔案：coding job 改過的檔案，或目前目錄的所有 Python 與 C／C++ 檔；--spec：再對照規格文件裡的函式簽名（參數個數）")
_MODULE_DUNDERS = {"__name__", "__file__", "__doc__", "__package__", "__spec__", "__loader__", "__builtins__",
                   "__path__", "__annotations__", "__dict__", "__class__", "__qualname__", "__module__", "__debug__",
                   "__all__", "__version__", "__cached__"}
_BUILTINS = set(dir(builtins)) | _MODULE_DUNDERS


def bound_names(tree):
    """模組裡任何地方定義、指派、匯入過的名稱（不分作用域）。"""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names.add(node.rest)
        elif hasattr(ast, "TypeVar") and isinstance(node, getattr(ast, "TypeVar")):
            names.add(node.name)
    return names


def undefined_names(tree):
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
        return []
    bound = bound_names(tree) | _BUILTINS
    out, seen = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in bound and node.id not in seen:
            seen.add(node.id)
            out.append((node.lineno, f"未定義的名稱 '{node.id}'（沒有定義、匯入或指派過；是不是拼錯或忘了 import？）"))
    return out


def module_file(root, module, level, current_file):
    """from <level 個點><module> import … → 專案裡對應的 .py（或套件的 __init__.py）；不是專案內的模組回 None。"""
    if level:
        base = os.path.dirname(current_file)
        for _ in range(level - 1):
            base = os.path.dirname(base)
        bases = [base]
    else:
        bases = [root, os.path.dirname(current_file)]
    for base in bases:
        rel = (module or "").replace(".", os.sep)
        cand = os.path.join(base, rel) if rel else base
        for p in (cand + ".py", os.path.join(cand, "__init__.py")):
            if os.path.isfile(p) and os.path.realpath(p).startswith(root):
                return os.path.realpath(p)
    return None


_TOP_CACHE = {}


def top_level_names(path):
    """一個模組在最外層定義、匯入或指派的名稱（給 from 這個模組 import 用）；有 __getattr__ 或 import * 時回 None（不檢查）。"""
    if path in _TOP_CACHE:
        return _TOP_CACHE[path]
    try:
        tree = ast.parse(cc.read_text(path))
    except (SyntaxError, OSError):
        _TOP_CACHE[path] = None
        return None
    names = set()

    def collect(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name):
                            names.add(n.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    if a.name == "*":
                        names.add("*")
                    names.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, (ast.If, ast.Try, ast.With)):
                for field in ("body", "orelse", "finalbody", "handlers"):
                    for sub in getattr(node, field, []) or []:
                        collect(sub.body if isinstance(sub, ast.ExceptHandler) else [sub])
    collect(tree.body)
    result = None if ("*" in names or "__getattr__" in names) else names
    _TOP_CACHE[path] = result
    return result


def import_issues(root, path, tree):
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        target = module_file(root, node.module, node.level, path)
        if not target:
            continue
        names = top_level_names(target)
        if names is None:
            continue
        pkg_dir = os.path.dirname(target) if target.endswith("__init__.py") else None
        for a in node.names:
            if a.name == "*" or a.name in names:
                continue
            if pkg_dir and (os.path.isfile(os.path.join(pkg_dir, a.name + ".py")) or os.path.isdir(os.path.join(pkg_dir, a.name))):
                continue
            mod = ("." * node.level) + (node.module or "")
            issues.append((node.lineno, f"from {mod} import {a.name}：{cc.rel_to_root(target)} 沒有定義 {a.name}"
                                        f"（名稱改了、還沒加、或拼錯？用 code_refs {a.name} 查）"))
    return issues


_TEST_FILE_RE = re.compile(r"(^test_.*|.*_test|^conftest)\.py$")


def _chain_root(node):
    """a.b.c、a.b[0]、a[x].y → 最左邊的名稱 a（不是這種形式回 None）。"""
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def test_pollution_issues(root, path, tree):
    """測試檔在模組層級（import 時就執行）替換 sys.modules，或改掉專案模組／類別的屬性：pytest 在同一個程序跑所有測試，
    這會讓其他測試檔也拿到假的東西（實測 e4b 在 test_cli.py 寫 sys.modules['inventory.storage'] = MagicMock()，
    test_storage.py 與 hidden 測試全部讀到空的庫存）。"""
    if not _TEST_FILE_RE.match(os.path.basename(path)):
        return []
    project = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and module_file(root, node.module, node.level, path):
            project |= {(a.asname or a.name) for a in node.names}
        elif isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if os.path.isdir(os.path.join(root, top)) or os.path.isfile(os.path.join(root, top + ".py")):
                    project.add((a.asname or a.name).split(".")[0])
    issues = []

    def visit(body):
        for node in body:
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if not isinstance(t, (ast.Attribute, ast.Subscript)):
                        continue
                    root_name = _chain_root(t)
                    text = ast.unparse(t)
                    if (root_name == "sys" and text.startswith("sys.modules")) or root_name in project:
                        issues.append((node.lineno, f"測試檔在模組層級替換了 {text}：pytest 會在同一個程序跑所有測試，其他測試檔也會拿到"
                                                    f"這個假的東西。直接用真的模組、類別與 tmp_path；真的要替換就在測試函式裡用 monkeypatch"
                                                    f"（測試結束會自動還原）"))
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) \
                    and node.value.func.attr == "start" and "patch" in ast.unparse(node.value.func.value):
                issues.append((node.lineno, "測試檔在模組層級 patch(...).start()（沒有還原，會影響其他測試檔）：改在測試函式裡用 monkeypatch"))
            elif isinstance(node, (ast.If, ast.Try)):
                visit(node.body)
                for h in getattr(node, "handlers", []):
                    visit(h.body)
                visit(getattr(node, "orelse", []) or [])
    visit(tree.body)
    return issues


def external_linter(paths):
    """有 ruff 或 pyflakes 就跑一次，回傳輸出（沒有就回 None）。"""
    py = [p for p in paths if p.endswith(".py")]
    if not py:
        return None
    for cmd in (["ruff", "check", "--quiet", "--select", "F", "--output-format", "concise"], ["pyflakes"]):
        if shutil.which(cmd[0]):
            try:
                r = subprocess.run(cmd + py, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
                return f"{cmd[0]}：" + ((r.stdout + r.stderr).strip() or "沒有發現問題")
            except (OSError, subprocess.SubprocessError):
                return None
    return None


# ---------------------------------------------------------------- C／C++
_CPP_COMPILE_TIMEOUT = 90


def check_cpp(root, paths):
    """回傳 (錯誤 list（每項是多行文字）, 警告 list, 實際編譯的檔案 list, 說明 list, 只做了結構檢查的檔案數)。
    colcon 工作區裡每個套件分開看（include 目錄、宣告的依賴、C++ 標準，見 cp.project_dir）。編譯失敗只是因為缺了宣告過的外部依賴
    的標頭（這台主機沒裝，例如沒有 ROS 2 時的 rclcpp）：那個檔案沒辦法用編譯器檢查，不算程式的錯誤（括號與結構在前面已經查過），
    說明裡講清楚缺了什麼、在哪裡才檢查得到——不然模型會去「修」本來就對的 #include。"""
    infos, dbs = {}, {}

    def info_of(rel):
        base = cp.project_dir(root, rel)
        if base not in infos:
            infos[base] = cp.detect(root, base)
            dbs[base] = dict(cp._load_compdb(os.path.join(root, base)), **dbs[""]) if base else dbs[""]
        return infos[base]

    dbs[""] = cp._load_compdb(root)
    rels = [os.path.relpath(p, root) for p in paths]
    targets = []
    for rel in rels:
        if cp.ext_of(rel) in cp.SOURCE_EXTS:
            targets.append(rel)
            continue
        info = info_of(rel)
        users = _includers(root, rel, info["sources"] + info["tests"])
        if not users:
            # 只被其他標頭 include 的片段（template 實作的 .hpp／.tpp、內部標頭）：單獨編譯會缺上下文，
            # 改編譯 include 那些標頭的原始檔；連那個也沒有就編譯上層的標頭
            parents = _includers(root, rel, [h for h in info["headers"] if h != rel])[:5]
            for ph in parents:
                users += [u for u in _includers(root, ph, info["sources"] + info["tests"]) if u not in users]
            users = users or parents[:1]
        targets += users[:3] or [rel]
    targets = list(dict.fromkeys(targets))[:40]
    for t in targets:
        info_of(t)
    compiler = "gcc" if all(cp.is_c_file(t, info_of(t)) for t in targets) else "g++"
    env = cc.toolchain_env(root)
    env["LC_MESSAGES"] = "C"
    if env.get("LC_ALL"):
        env["LC_ALL"] = "C.UTF-8"
    if not shutil.which(compiler, path=env.get("PATH")):
        return [], [], [], [f"（找不到 {compiler}，沒有做 C／C++ 的編譯檢查）"], 0

    def one(rel):
        base = cp.project_dir(root, rel)
        cmd, cwd = cp.syntax_command(root, rel, infos[base], dbs[base])
        cmd = cmd[:-1] + ["-Wall", "-Werror=return-type"] + cmd[-1:]    # 非 void 函式忘了 return：當成錯誤
        try:
            r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, errors="replace",
                               timeout=_CPP_COMPILE_TIMEOUT, stdin=subprocess.DEVNULL)
            return rel, cwd, r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return rel, cwd, None, f"{rel}: 編譯檢查逾時（超過 {_CPP_COMPILE_TIMEOUT} 秒）"
        except OSError as e:
            return rel, cwd, 127, f"{rel}: 無法執行 {cmd[0]}：{e}"

    with ThreadPoolExecutor(max_workers=max(1, min(8, os.cpu_count() or 2))) as ex:
        results = list(ex.map(one, targets))
    errors, warns, seen, partial = [], [], set(), []
    for rel, cwd, code, out in results:
        info = infos[cp.project_dir(root, rel)]
        ext = [h for h in cp.missing_headers(out) if cp.external_header(h, info)]
        d = cp.diagnostics(out, roots=[root, cwd], max_errors=8, with_warnings=True)
        blocks = [b for b in d["errors"] if not any(f"fatal error: {h}:" in b.split("\n", 1)[0] for h in ext)]
        if ext:
            partial.append((rel, ext, info))
            blocks += [f"{rel}:{ln}: 找不到 #include 的「{inc}」：專案裡沒有這個檔案（檔名或目錄拼錯、還沒建立）"
                       for ln, inc in cp.unresolved_project_includes(root, rel, info)]
        for block in blocks:
            key = block.split("\n", 1)[0]
            if key not in seen:
                seen.add(key)
                errors.append(block)
        if code not in (0, None) and not blocks and not ext:
            errors.append(f"{rel}: 編譯檢查失敗（exit {code}）：\n{cc.clip_middle(out.strip(), 1500)}")
        elif code is None:
            errors.append(out)
        for block in d["warnings"]:
            key = block.split("\n", 1)[0]
            if key not in seen:
                seen.add(key)
                warns.append(block)
    return errors, warns, targets, ([_partial_note(root, partial)] if partial else []), len(partial)


def _includers(root, rel, candidates):
    """candidates 裡 #include 了 rel（比對完整路徑或檔名）的檔案。"""
    base, out = os.path.basename(rel), []
    for src in candidates:
        try:
            incs = cp.includes_of(cc.read_text(os.path.join(root, src)))
        except OSError:
            continue
        if any(i == rel or os.path.basename(i) == base for i in incs):
            out.append(src)
    return out


def _partial_note(root, partial):
    """缺外部依賴、或缺建置時才產生的標頭，沒辦法用編譯器檢查的檔案 → 給模型看的說明（缺什麼、不是程式的錯、在哪裡才檢查得到）。"""
    heads = list(dict.fromkeys(h for _, ext, _ in partial for h in ext))
    kinds = {h: next((cp.missing_kind(h, i) for _, ext, i in partial if h in ext), None) for h in heads}
    ext = [h for h in heads if kinds[h] == "external"]
    gen = [h for h in heads if kinds[h] == "generated"]
    files = "、".join(r for r, _, _ in partial[:6]) + ("…" if len(partial) > 6 else "")
    ros = [i for _, _, i in partial if i.get("ros")]
    if ros:
        names = list(dict.fromkeys(i.get("name") or os.path.basename(i["base"] or root) for i in ros))
        how = f"在有 ROS 2 的環境（例如 ROS 2 的容器）建置：colcon build --packages-select {' '.join(names)}"
    else:
        how = "在裝好這些函式庫的環境建置，或把那裡產生的 compile_commands.json 放到專案目錄"

    def show(xs):
        return "、".join(xs[:5]) + ("…" if len(xs) > 5 else "")

    what = "；".join(x for x in (f"外部依賴的標頭 {show(ext)}" if ext else "", f"建置時才產生的標頭 {show(gen)}" if gen else "") if x)
    why = "、".join(x for x in (
        "外部依賴是 package.xml／CMakeLists.txt 宣告的，這台主機沒有安裝" + ("（沒有載入 ROS 2）" if ros and not cp.ros_sourced() else "")
        if ext else "",
        "產生的標頭（ROS 2 介面、建置檔產生的檔案）要建置之後才有" if gen else "") if x)
    return (f"⚠ {len(partial)} 個檔案沒辦法用編譯器檢查，只檢查了括號與結構：{files} 用到{what}——{why}，不是程式的錯誤，"
            f"不要為了這個改 #include。要完整檢查：{how}。")


# ---------------------------------------------------------------- 規格簽名
_SPEC_LINE_RE = re.compile(r"^\s*(?:[-*+#~]\s*){0,2}(?:def\s+)?((?:[\w:<>*&]+\s+){0,3}?)([A-Za-z_~]\w*)\s*\(([^()]*)\)")
_SPEC_SKIP = set(dir(builtins)) | {"main", "if", "for", "while", "return", "sizeof", "printf", "assert", "TEST", "TEST_F"}


_TYPE_TOKENS = {"int", "double", "float", "bool", "str", "string", "list", "dict", "tuple", "set", "char", "void", "long", "short",
                "unsigned", "const", "std", "vector", "map", "object", "any", "none", "function", "callable", "auto", "size_t"}


def _doc_params(text, optional_names=()):
    """規格裡的參數 → (個數, 可選的個數, 有沒有 ...)；空的、void、self 不算。寫了「= 值」、或名稱在 optional_names（文件敘述說它
    有預設值）的算可選。"""
    parts = [x.strip() for x in cp._split_top(text) if x.strip()]
    parts = [x for x in parts if x not in ("void", "self", "cls")]
    var = any(x in ("...", "*args", "**kwargs") or x.startswith("*") for x in parts)
    parts = [x for x in parts if not (x in ("...",) or x.startswith("*"))]

    def optional(piece):
        if "=" in piece:
            return True
        names = [w.lower() for w in re.findall(r"[A-Za-z_]\w*", piece) if w.lower() not in _TYPE_TOKENS]
        return any(n in optional_names for n in names)

    return len(parts), sum(1 for x in parts if optional(x)), var


def _optional_names(text):
    """文件敘述裡說有預設值的參數名稱（「The default WPM rate is 265」「wpm is optional」→ wpm）。"""
    out = set()
    for m in re.finditer(r"\b(?:default(?:s)?|optional(?:ly)?)\b[^.\n]{0,40}|[^.\n]{0,40}\b(?:default(?:s)?|optional)\b", text, re.I):
        out |= {w.lower() for w in re.findall(r"[A-Za-z_]\w*", m.group(0))}
    return out - _TYPE_TOKENS - {"default", "defaults", "optional", "optionally", "the", "is", "a", "an", "of", "to", "if", "and",
                                 "or", "be", "will", "value", "rate", "it", "set", "by", "for", "in", "not", "use", "used"}


def spec_signatures(paths):
    """規格文件 → {名稱: [(最少參數, 最多參數, 文件:行, 原文)]}（只看 API 行，不看一般敘述；敘述只用來找有預設值的參數）。"""
    out = {}
    texts = {}
    for path in paths:
        try:
            texts[path] = cc.read_text(path)
        except OSError:
            continue
    optional_names = _optional_names("\n".join(texts.values()))
    for path, text in texts.items():
        lines = text.splitlines()
        fence = False
        for no, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                fence = not fence
                continue
            m = _SPEC_LINE_RE.match(line)
            if not m or fence and not line.lstrip().startswith(("def ", "+", "-")):
                continue
            name = m.group(2)
            if name in _SPEC_SKIP or "=" in m.group(1):
                continue
            n, opt, var = _doc_params(m.group(3), optional_names)
            out.setdefault(name, []).append((n - opt, None if var else n, f"{cc.rel_to_root(path)}:{no}",
                                             f"{name}({' '.join(m.group(3).split())})"))
    return out


def _py_defs(tree):
    """Python：[(名稱, 行號, 最少參數, 最多參數或 None（*args）, 簽名文字)]；方法不算 self／cls，類別用 __init__ 的參數。"""
    out = []

    def sig(fn, method):
        a = fn.args
        pos = a.posonlyargs + a.args
        if method and pos and pos[0].arg in ("self", "cls") and not any(
                isinstance(d, ast.Name) and d.id == "staticmethod" for d in fn.decorator_list):
            pos = pos[1:]
        req = len(pos) - len(a.defaults) + sum(1 for k, d in zip(a.kwonlyargs, a.kw_defaults) if d is None)
        mx = None if a.vararg else len(pos) + len(a.kwonlyargs)
        names = [x.arg for x in pos] + (["*" + a.vararg.arg] if a.vararg else []) + [x.arg for x in a.kwonlyargs]
        return req, mx, ", ".join(names)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((node.name, node.lineno, *sig(node, False)))
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    r = sig(sub, True)
                    out.append((sub.name, sub.lineno, *r))
                    if sub.name == "__init__":
                        out.append((node.name, sub.lineno, *r))
    return out


def _cpp_defs(text):
    out = []
    for e in cp.scan(text):
        if e["kind"] not in ("function", "decl"):
            continue
        params = e.get("params") or ""
        n, opt, var = _doc_params(params)
        out.append((e["name"].split("::")[-1], e["line"], n - opt, None if var else n, params))
    return out


def spec_issues(paths, spec):
    issues = []
    if not spec:
        return issues
    for p in paths:
        lang = cc.language_of(p)
        try:
            text = cc.read_text(p)
        except OSError:
            continue
        if lang == "Python":
            try:
                defs = _py_defs(ast.parse(text))
            except SyntaxError:
                continue
        elif cp.is_c_family(p):
            defs = _cpp_defs(text)
        else:
            continue
        by_name = {}
        for name, line, req, mx, sigtext in defs:
            by_name.setdefault(name, []).append((line, req, mx, sigtext))
        for name, entries in by_name.items():
            docs = spec.get(name)
            if not docs:
                continue
            # 程式要接受規格允許的每一種呼叫（至少符合規格寫的其中一種）：必要參數不能比規格的最少參數多，
            # 也要收得下規格的最多參數
            ok = any(req <= dmin and (mx is None or (dmax is not None and dmax <= mx))
                     for _, req, mx, _ in entries for dmin, dmax, _, _ in docs)
            if ok:
                continue
            line, req, mx, sigtext = entries[0]
            d = docs[0]
            want = f"{d[0]}" if d[1] == d[0] else f"{d[0]}～{d[1] if d[1] is not None else '多'}"
            fix = ("規格沒有的參數改成有預設值或內部常數，不要多要求" if d[1] is not None and req > d[1] else
                   "文件說有預設值的參數要給預設值（照文件寫的值）" if req > d[0] else "參數不夠：照規格補上")
            issues.append(f"{cc.rel_to_root(p)}:{line}: 規格（{d[2]}）寫 {d[3]}（{want} 個參數），這裡定義成 {name}({sigtext})"
                          f"（必要參數 {req} 個{'' if mx is None else f'、最多 {mx} 個'}）：參數要照規格——{fix}")
    return issues


def _preexisting_structure_issue(path, rel):
    """coding job 裡（有備份）：這個檔案的括號／#if 問題在 job 開始前就有——job 沒改過它，或改之前的內容就已經不成對。"""
    bdir = cc.backup_dir()
    if not bdir:
        return False
    entry = cc.load_manifest(bdir).get(rel)
    if entry is None:
        return True
    if not entry.get("existed"):
        return False
    orig = cc.original_text(rel, bdir)
    return orig is not None and not cc.syntax_check(path, orig)[0]


def default_targets():
    bdir = cc.backup_dir()
    if bdir:
        rels = [rel for rel, e in cc.load_manifest(bdir).items()]
        paths = [os.path.join(cc.base_root(), r) for r in rels]
        return [p for p in paths if os.path.isfile(p)], "這個 coding job 改過的檔案"
    return [p for p, _ in cc.iter_files(cc.base_root(), exts={".py"} | cp.ALL_EXTS)], "目前目錄的所有 Python 與 C／C++ 檔"


_CHECK_LANGS = ("Python", "JSON", "TOML", "YAML", "C", "C++", "C/C++ 標頭")


def main(argv):
    if any(a in ("-h", "--help") for a in argv):
        return USAGE
    root = cc.base_root()
    spec_paths, rest, i = [], [], 0
    while i < len(argv):
        if argv[i] == "--spec" and i + 1 < len(argv):
            p, err = cc.resolve_path(argv[i + 1])
            if err:
                return err
            if not os.path.isfile(p):
                return f"[ERROR] 找不到規格文件：{argv[i + 1]}"
            spec_paths.append(p)
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    argv = rest
    if argv:
        paths = []
        for a in argv:
            p, err = cc.resolve_path(a)
            if err:
                return err
            if not os.path.exists(p):
                return f"[ERROR] 找不到 {a}。"
            paths += [x for x, _ in cc.iter_files(p)] if os.path.isdir(p) else [p]
        scope = "、".join(argv)
    else:
        paths, scope = default_targets()
    checkable = [p for p in paths if cc.language_of(p) in _CHECK_LANGS]
    if not checkable:
        return f"[PASS] 沒有可以檢查的檔案（{scope}；支援 Python、C／C++、JSON、TOML、YAML）。"
    issues, cpp_ok, pre_notes = [], [], []
    for p in checkable:
        rel = cc.rel_to_root(p)
        try:
            text = cc.read_text(p)
        except OSError as e:
            issues.append(f"{rel}: 讀不到：{e}")
            continue
        ok, msg = cc.syntax_check(p, text)
        if not ok and cp.is_c_family(p) and _preexisting_structure_issue(p, rel):
            # 例如命名空間在標頭打開、在 .cpp 關閉（rf2o 就是這樣）：單一檔案的括號不成對，但合起來編譯得過；
            # 不是這次的修改造成的，不要讓 worker 去「修」——照常交給編譯器（標頭會編譯 include 它的原始檔）
            pre_notes.append(f"{rel}: {msg}——job 開始前就是這樣（不是這次的修改造成的），照常用編譯器檢查")
            ok = True
        if not ok:
            issues.append(f"{rel}: {msg}")
            continue
        if cp.is_c_family(p):
            cpp_ok.append(p)
            continue
        if cc.language_of(p) != "Python":
            continue
        tree = ast.parse(text)
        for ln, m in sorted(undefined_names(tree) + import_issues(root, p, tree) + test_pollution_issues(root, p, tree)):
            issues.append(f"{rel}:{ln}: {m}")
    spec = spec_signatures(spec_paths)
    issues += spec_issues(checkable, spec)
    warns, notes, kinds = [], list(pre_notes), "語法、未定義名稱、專案內匯入" + (f"、對照規格的 {sum(len(v) for v in spec.values())} 個簽名" if spec else "")
    if cpp_ok:
        t0 = time.time()
        errs, warns, compiled, cpp_notes, n_partial = check_cpp(root, cpp_ok)
        issues += errs
        notes += cpp_notes
        if compiled:
            kinds += f"；C／C++ 用編譯器檢查了 {len(compiled)} 個檔案（{time.time() - t0:.1f} 秒）"
            if n_partial:
                kinds += f"，其中 {n_partial} 個缺外部依賴的標頭、只檢查了結構（見最後的說明）"
    linter = external_linter(checkable)
    tail = "".join(f"\n{x}" for x in [linter] + notes if x)
    if warns:
        tail += f"\n編譯器的警告（不影響通過，{len(warns)} 個）：\n" + "\n".join(warns[:5])
    what = f"檢查 {len(checkable)} 個檔案（{scope}；{kinds}）"
    if not issues:
        return f"[PASS] {what}：沒有發現問題" + tail
    shown = issues[:MAX_ISSUES] + ([f"…還有 {len(issues) - MAX_ISSUES} 個問題沒有列出"] if len(issues) > MAX_ISSUES else [])
    files = len({i.split(":")[0] for i in issues})
    return f"[ERROR] {what}：發現 {len(issues)} 個問題（{files} 個檔案）\n" + "\n".join(shown) + tail


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_check 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
