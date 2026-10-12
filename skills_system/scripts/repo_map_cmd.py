"""repo_map：專案地圖——整個專案的目錄樹、每個程式檔的結構大綱（類別、函式與行號範圍）、測試檔與建議的測試指令、git 狀態。

給「還不認識這個專案」的時候用（coding orchestrator 規劃前一定先跑一次）：數量、行數、測試框架都由腳本算好，模型照抄。
Python 用 AST 取大綱（class／def、參數、行號範圍）；C／C++ 用 _cpp_common 的掃描器（namespace、class／struct、方法的宣告與
定義、函式與行號範圍、gtest 的 TEST）；JavaScript／TypeScript／Go／Rust／Java 用正規表示式抓宣告。
C／C++ 專案另外列出建置系統（CMake／Makefile）與 C／C++ 測試怎麼跑（code_test 會建置後跑 gtest）。
輸出超過 --max-chars 時逐步降低細節：先拿掉方法、再拿掉所有大綱只留檔名與行數，最後只列前面的檔案並說明怎麼縮小範圍。
"""
import ast
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc
import _cpp_common as cp

DEFAULT_MAX_CHARS = 12000
USAGE = ("用法: scripts/repo_map_cmd.py [path] [--filter 關鍵字] [--no-outline] [--max-chars N]\n"
         "  path 預設目前工作目錄（coding job 時是工作區）；--filter 只列路徑含關鍵字的檔案；--no-outline 只列檔名與行數；"
         f"--max-chars 輸出上限（預設 {DEFAULT_MAX_CHARS}）。")

_TEST_FILE_RE = re.compile(r"(^test_.*\.py$|_test\.py$|\.test\.[jt]sx?$|\.spec\.[jt]sx?$|_test\.go$)")


def parse_args(argv):
    path, keyword, outline, max_chars = ".", None, True, DEFAULT_MAX_CHARS
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--filter" and i + 1 < len(argv):
            keyword = argv[i + 1].strip("*")
            i += 2
            continue
        if a == "--max-chars" and i + 1 < len(argv) and argv[i + 1].isdigit():
            max_chars = max(2000, int(argv[i + 1]))
            i += 2
            continue
        if a in ("--workspace", "--path") and i + 1 < len(argv):   # 模型常把 code_job_send 的 --workspace 帶過來：當成 path
            path = argv[i + 1]
            i += 2
            continue
        if a == "--no-outline":
            outline = False
            i += 1
            continue
        if a.startswith("--"):
            return None, f"[ERROR] 不認識的選項 {a}。\n{USAGE}"
        path = a
        i += 1
    return {"path": path, "keyword": keyword, "outline": outline, "max_chars": max_chars}, None


# ---------------------------------------------------------------- 大綱
def _args_text(node):
    a = node.args
    names = [x.arg for x in a.posonlyargs + a.args]
    if names and names[0] in ("self", "cls"):
        names = names[1:]
    if a.vararg:
        names.append("*" + a.vararg.arg)
    names += [x.arg for x in a.kwonlyargs]
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    text = ", ".join(names)
    return text if len(text) <= 60 else text[:57] + "…"


def python_outline(text):
    """[(層級, 文字)]：class 名稱(基底) L起-迄、def 名稱(參數) L起-迄；方法在層級 1。"""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [(0, f"⚠️ 語法錯誤：第 {e.lineno} 行 {e.msg}")]
    out = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            bases = bases if len(bases) <= 50 else bases[:47] + "…"
            out.append((0, f"class {node.name}{f'({bases})' if bases else ''} L{node.lineno}-{node.end_lineno}"))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append((1, f"def {sub.name}({_args_text(sub)}) L{sub.lineno}-{sub.end_lineno}"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            out.append((0, f"{prefix} {node.name}({_args_text(node)}) L{node.lineno}-{node.end_lineno}"))
        elif isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            out.append((0, f"if __name__ == '__main__' L{node.lineno}-{node.end_lineno}"))
    return out


_REGEX_OUTLINES = {
    "JavaScript": [r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)", r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\(",
                   r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>"],
    "Go": [r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", r"^type\s+(\w+)\s+(?:struct|interface)"],
    "Rust": [r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)", r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+(\w+)",
             r"^\s*impl(?:<[^>]*>)?\s+([\w:<>, ]+?)\s*\{"],
    "C++": [r"^\s*(?:class|struct)\s+(\w+)\s*(?::[^{;]*)?\{", r"^[\w:<>\*&\s,]+?\s+[\*&]?([\w:~]+)\s*\([^;{]*\)\s*(?:const\s*)?(?:override\s*)?\{?\s*$"],
    "Java": [r"^\s*(?:public|private|protected)?\s*(?:abstract\s+|final\s+)?(?:class|interface|enum)\s+(\w+)",
             r"^\s*(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ]+\s+(\w+)\s*\("],
}
_REGEX_OUTLINES["TypeScript"] = _REGEX_OUTLINES["JavaScript"] + [r"^\s*(?:export\s+)?(?:interface|type)\s+(\w+)"]
_REGEX_OUTLINES["C"] = _REGEX_OUTLINES["C++"]
_REGEX_OUTLINES["C/C++ 標頭"] = _REGEX_OUTLINES["C++"]
_REGEX_OUTLINES["Kotlin"] = [r"^\s*(?:data\s+|open\s+|abstract\s+)?class\s+(\w+)", r"^\s*(?:private\s+|public\s+)?fun\s+(\w+)"]
_C_KEYWORDS = {"if", "for", "while", "switch", "return", "else", "do", "sizeof", "catch"}


def regex_outline(text, lang):
    pats = [re.compile(p) for p in _REGEX_OUTLINES.get(lang, [])]
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        for p in pats:
            m = p.match(line)
            if m and m.group(1) not in _C_KEYWORDS:
                out.append((0, f"{line.strip()[:70]} L{no}"))
                break
        if len(out) >= 40:
            out.append((0, "…（宣告太多，只列前 40 個；用 code_view 或 code_search 看細節）"))
            break
    return out


def outline_for(path, text, lang):
    if lang == "Python":
        return python_outline(text)
    if lang in ("C", "C++", "C/C++ 標頭"):
        return cp.outline(text)
    return regex_outline(text, lang)


# ---------------------------------------------------------------- 專案資訊
def git_info(root):
    try:
        top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if top.returncode != 0:
            return None
        branch = subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5)
        status = subprocess.run(["git", "--no-optional-locks", "-C", root, "status", "--porcelain"], capture_output=True, text=True, timeout=8)
        dirty = [ln for ln in status.stdout.splitlines() if ln.strip()]
        return f"git：{branch.stdout.strip() or '?'} 分支，{len(dirty)} 個檔案有未提交的變更" if status.returncode == 0 else "git：有版本控制"
    except (OSError, subprocess.SubprocessError):
        return None


def detect_tests(root, files, cpp_info=None):
    """回傳 (測試檔相對路徑 list, 建議的測試指令或 None)。C／C++ 的測試由 code_test 建置後執行（指令就是 code_test）。"""
    tests = [rel for _, rel in files if _TEST_FILE_RE.search(os.path.basename(rel)) or cp.is_test_source(rel)
             or (rel.endswith(".py") and rel.split(os.sep)[0] in ("tests", "test") and os.path.basename(rel) != "__init__.py")]
    names = {rel for _, rel in files}
    py = any(t.endswith(".py") for t in tests) or "pytest.ini" in names or "conftest.py" in names
    cpp = bool(cpp_info and ((cpp_info["cmake"] and cpp_info["cmake"]["tests"]) or cpp_info["make"] or cpp_info["tests"]))
    cmd = None
    if cpp or (tests and "package.xml" in {os.path.basename(n) for n in names}):    # ROS 套件：code_test 每個套件分開跑
        cmd = "code_test"
    elif cpp:
        cmd = "code_test"
    elif py and "tests/runtests.py" in names:
        # 自己有測試程式的大型 Python 專案（SWE-bench 評測，2026-10-09）：django 的測試不能用 pytest 跑（環境裡也沒有 pytest），
        # 要跑哪些測試用模組名稱指定（例如 python3 tests/runtests.py utils_tests.test_text）
        cmd = "python3 tests/runtests.py <測試模組>"
    elif py and "bin/test" in names and os.path.isdir(os.path.join(root, "sympy")):
        cmd = "python3 bin/test <測試檔>"     # sympy 自己的測試程式（環境裡通常沒有 pytest）
    elif py:
        cmd = "python3 -m pytest -q"
    elif "package.json" in names:
        cmd = "npm test"
    elif "go.mod" in names:
        cmd = "go test ./..."
    elif "Cargo.toml" in names:
        cmd = "cargo test"
    return tests, cmd


def render(root, files, keyword, outline, max_chars):
    langs = {}
    for _, rel in files:
        lang = cc.language_of(rel) or "其他"
        langs[lang] = langs.get(lang, 0) + 1
    cpp_info = cp.detect(root) if any(cp.is_c_family(rel) for _, rel in files) else None
    tests, test_cmd = detect_tests(root, files, cpp_info)
    shown = [(p, rel) for p, rel in files if not keyword or keyword.lower() in rel.lower()]
    dirs = {os.path.dirname(rel) for _, rel in files if os.path.dirname(rel)}
    lang_text = "、".join(f"{k} {v}" for k, v in sorted(langs.items(), key=lambda kv: -kv[1])[:6])
    head = [f"[PASS] 專案地圖 {root}：{len(files)} 個檔案、{len(dirs)} 個子目錄（{lang_text or '沒有可讀的文字檔'}）"
            + (f"；路徑含「{keyword}」的 {len(shown)} 個" if keyword else "")]
    info = []
    if tests:
        info.append(f"測試檔 {len(tests)} 個" + (f"；建議的測試指令：{test_cmd}" if test_cmd else ""))
    else:
        info.append("沒有找到測試檔" + (f"（建議的測試指令：{test_cmd}）" if test_cmd else ""))
    readmes = [rel for _, rel in files if os.path.basename(rel).lower().startswith("readme") and os.sep not in rel]
    if readmes:
        info.append(f"說明檔：{', '.join(readmes)}")
    g = git_info(root)
    if g:
        info.append(g)
    head.append("；".join(info))
    if cpp_info:
        build = cp.describe(cpp_info)
        if build:
            head.append(f"C／C++（{cpp_info['lang']}{'、' + cpp_info['std'] if cpp_info.get('std') else ''}）：{build}")
    pkgs = cp.ros_packages(root, [rel for _, rel in files])
    if pkgs and not (len(pkgs) == 1 and pkgs[0][0] == "."):
        listed = "、".join(f"{d}（{n}，{t}）" for d, n, t in pkgs[:12]) + (f"…等 {len(pkgs)} 個" if len(pkgs) > 12 else "")
        head.append(f"ROS 2 colcon 工作區，{len(pkgs)} 個套件：{listed}。code_test 每個套件分開跑（C／C++ 用套件自己的 include 目錄"
                    "編譯 gtest、Python 在套件目錄跑 pytest）；驗證指令請指定套件，例如 code_test " + pkgs[0][0]
                    + ("" if cp.ros_sourced() else "。這台主機沒有載入 ROS 2：用到 rclcpp 的 C／C++ 檔只能做結構檢查，需要 rclcpp／rclpy 的測試會跳過並說明"))
    elif pkgs and not cp.ros_sourced():
        head.append(f"ROS 2 套件（{pkgs[0][1]}，{pkgs[0][2]}）。這台主機沒有載入 ROS 2：用到 rclcpp 的 C／C++ 檔只能做結構檢查，"
                    "需要 rclcpp／rclpy 的測試會跳過並說明")

    entries = []
    for p, rel in shown:
        try:
            text = cc.read_text(p)
        except OSError:
            continue
        lang = cc.language_of(rel)
        n_lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        outl = outline_for(p, text, lang) if outline and lang in cc.CODE_LANGS else []
        entries.append((rel, n_lines, outl))

    def build(level):
        """level 0：完整大綱；1：只留最外層（拿掉方法）；2：只有檔名與行數。"""
        lines, last_dir = [], None
        for rel, n_lines, outl in entries:
            d = os.path.dirname(rel)
            if d != last_dir:
                if d:
                    lines.append(f"{d}/")
                last_dir = d
            indent = "  " if d else ""
            lines.append(f"{indent}{os.path.basename(rel)}（{n_lines} 行）")
            if level < 2:
                for depth, txt in outl:
                    if depth and level >= 1:
                        continue
                    lines.append(f"{indent}  {'  ' * depth}{txt}")
        return lines

    body, note = None, ""
    for level, why in ((0, ""), (1, "（輸出較長，已省略類別裡的方法；要看某個檔案的完整結構用 code_ast_reader 或 code_view）"),
                       (2, "（輸出較長，只列檔名與行數；要看結構請用 --filter 縮小範圍，或 code_ast_reader 看單一檔案）")):
        body = build(level)
        if len("\n".join(head + body)) <= max_chars:
            note = why
            break
    else:
        kept, used = [], len("\n".join(head))
        for ln in body:
            if used + len(ln) + 1 > max_chars - 200:
                break
            kept.append(ln)
            used += len(ln) + 1
        note = (f"（檔案太多，只列出前 {sum(1 for ln in kept if '行）' in ln)} 個；請用 --filter 關鍵字 或指定子目錄縮小範圍）")
        body = kept
    return "\n".join(head + ([note] if note else []) + body)


def main(argv):
    opts, err = parse_args(argv)
    if err:
        return err
    root, err = cc.resolve_path(opts["path"])
    if err:
        return err
    if not os.path.exists(root):
        return f"[ERROR] {opts['path']} 不存在（目前工作目錄 {os.getcwd()}）。"
    if not os.path.isdir(root):
        return f"[ERROR] {opts['path']} 不是目錄（看單一檔案請用 code_view 或 code_ast_reader）。"
    files = cc.iter_files(root)
    if not files:
        return f"[PASS] 專案地圖 {root}：沒有可讀的文字檔（略過了 .git、__pycache__、node_modules、venv、build 等目錄）。"
    return render(root, files, opts["keyword"], opts["outline"], opts["max_chars"])


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] repo_map 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
