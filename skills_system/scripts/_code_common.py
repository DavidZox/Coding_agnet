"""程式開發技能（repo_map、code_* ）的共用層：工作區與路徑邊界、要略過的目錄、語言判斷、帶行號的顯示、
語法檢查、改檔前的備份、diff、指令的安全檢查、輸出截斷。

harness 以環境變數傳入（比照 _results_common 的 TOOL_RESULTS_DIR、_docker_common 的 TARGET_CONTAINER）：
- CODE_WORKSPACE：coding job 的工作區（專案根目錄）。有設定時，讀寫一律限制在它底下（路徑邊界）；沒設定時（主對話直接用）
  讀取不限制、寫入仍限制在目前工作目錄底下。
- CODE_BACKUP_DIR：coding job 的備份目錄。寫入技能第一次改某個檔案前，把原檔複製一份到 <備份>/files/<相對路徑>，並在
  <備份>/manifest.json 記下「原本存不存在」——job 的「還原全部變更」與 code_diff 都靠它。沒設定時不備份。
- CODE_ALLOW_INSTALL=1：code_run 放行 pip／npm 安裝類指令（預設擋，會改到環境也需要網路）。
- CODE_PYTHON：跑 Python 測試與程式用的直譯器（沒設定時：工作區的 .venv／venv → harness 自己的直譯器）。
- CODE_CPP_PREFIX：C／C++ 的函式庫安裝位置（冒號分隔，預設 ~/.local；gtest 裝在這裡），加進 CPATH、LIBRARY_PATH、
  CMAKE_PREFIX_PATH 等（見 toolchain_env）。

腳本由 harness 以 `python3 scripts/<name>_cmd.py` 執行，sys.path[0] 即為本目錄，各腳本直接 `import _code_common`；
agent_core 也會 import 這個模組（跟 _results_common 一樣），所以這裡只用標準庫。
"""
import difflib
import json
import os
import re
import shlex
import shutil
import sys
import time

# ---------------------------------------------------------------- 掃描範圍
# 不是程式碼、或是產生出來的目錄：repo_map／code_search／code_refs 一律略過（點開頭的目錄也略過：.git、.venv、.mypy_cache…）；
# 另外依專案的 .gitignore 略過目錄（見 iter_files）
SKIP_DIRS = {"__pycache__", "node_modules", "venv", "env", "dist", "build", "install", "log", "logs", "site-packages",
             "target", "htmlcov", "coverage"}
MAX_FILE_BYTES = 1024 * 1024        # 超過 1MB 的檔案不讀（多半是資料或產生出來的檔）

LANG_BY_EXT = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust",
    ".c": "C", ".h": "C/C++ 標頭", ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".c++": "C++", ".hpp": "C/C++ 標頭",
    ".hh": "C/C++ 標頭", ".hxx": "C/C++ 標頭", ".h++": "C/C++ 標頭", ".inl": "C/C++ 標頭", ".ipp": "C/C++ 標頭", ".tpp": "C/C++ 標頭",
    ".mk": "Makefile", ".cmake": "CMake",
    ".java": "Java", ".kt": "Kotlin", ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".sh": "Shell", ".bash": "Shell", ".md": "Markdown", ".rst": "reStructuredText", ".txt": "文字",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".ini": "INI", ".cfg": "INI",
    ".xml": "XML", ".launch": "XML", ".html": "HTML", ".css": "CSS", ".sql": "SQL", ".proto": "Protobuf",
    ".msg": "ROS 訊息", ".srv": "ROS 服務", ".action": "ROS action", ".urdf": "XML", ".xacro": "XML",
}
LANG_BY_NAME = {"CMakeLists.txt": "CMake", "Makefile": "Makefile", "makefile": "Makefile", "GNUmakefile": "Makefile",
                "Dockerfile": "Dockerfile",
                "package.xml": "XML", "setup.py": "Python", "requirements.txt": "文字"}
CODE_LANGS = {"Python", "JavaScript", "TypeScript", "Go", "Rust", "C", "C++", "C/C++ 標頭", "Java", "Kotlin", "C#",
              "Ruby", "PHP", "Swift", "Shell"}
FENCE_LANG = {"Python": "python", "JavaScript": "javascript", "TypeScript": "typescript", "Go": "go", "Rust": "rust",
              "C": "c", "C++": "cpp", "C/C++ 標頭": "cpp", "Java": "java", "Kotlin": "kotlin", "C#": "csharp",
              "Ruby": "ruby", "PHP": "php", "Swift": "swift", "Shell": "bash", "JSON": "json", "YAML": "yaml",
              "TOML": "toml", "Markdown": "markdown", "XML": "xml", "HTML": "html", "CSS": "css", "SQL": "sql",
              "CMake": "cmake", "Makefile": "makefile", "Dockerfile": "dockerfile"}


def language_of(path):
    name = os.path.basename(path)
    if name in LANG_BY_NAME:
        return LANG_BY_NAME[name]
    if re.match(r"^(?:GNU)?[Mm]akefile[._-]\w+$", name):     # makefile_test、Makefile.test
        return "Makefile"
    return LANG_BY_EXT.get(os.path.splitext(name)[1].lower(), "")


def fence_lang(path):
    return FENCE_LANG.get(language_of(path), "")


def skip_dir(name):
    return name.startswith(".") or name in SKIP_DIRS or name.endswith(".egg-info")


# .gitignore 只拿來略過「目錄」：產生出來的、下載來的第三方程式、IDE 的建置目錄（cmake-build-debug、out、evals/results…）
# 不該進 repo_map／code_search／code_refs／code_check 與規劃的名稱索引，C／C++ 直接編譯時也不該把它們當成專案的原始檔。
# 單一檔案不因為 .gitignore 略過（*.log、本機設定檔可能正是要找的）。
def _gitignore_rules(base):
    """base/.gitignore → [(樣式, 種類, 是否為 ! 例外)]。種類 name：樣式沒有 /，比對任何深度的目錄名稱；path：樣式開頭或中間
    有 /，比對相對 base 的路徑；deep：**/ 開頭、後面還有 /（任何深度的這段路徑）。"""
    try:
        with open(os.path.join(base, ".gitignore"), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    rules = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        line = (line[1:] if negate else line).rstrip("/")
        if line.startswith(("\\#", "\\!")):
            line = line[1:]
        kind = "path" if "/" in line else "name"
        if line.startswith("**/"):
            line = line[3:]
            kind = "deep" if "/" in line else "name"
        line = line.lstrip("/")
        if line:
            rules.append((line, kind, negate))
    return rules


def _gitignored(full, chain):
    """目錄 full 是否被 .gitignore 排除。chain：[(.gitignore 所在目錄, 規則)]，外層在前；跟 git 一樣最後一條符合的規則算數。"""
    import fnmatch
    ignored, name = False, os.path.basename(full)
    for base, rules in chain:
        rel = os.path.relpath(full, base).replace(os.sep, "/")
        for pat, kind, negate in rules:
            if kind == "name":
                hit = fnmatch.fnmatchcase(name, pat)
            else:
                hit = fnmatch.fnmatchcase(rel, pat) or (kind == "deep" and fnmatch.fnmatchcase(rel, "*/" + pat))
            if hit:
                ignored = not negate
    return ignored


def _ancestor_gitignores(root):
    """root 上層的 .gitignore（外層在前）：只往上找到工作區／目前工作目錄、或 git 專案的根為止——在 evals 底下掃描時，
    專案根目錄 .gitignore 的 evals/results/ 也要算；工作區外面的路徑不往上找。"""
    stop, real = base_root(), os.path.realpath(root)
    if real == stop or not _inside(real, stop):
        return []
    chain, cur = [], os.path.dirname(real)
    while True:
        rules = _gitignore_rules(cur)
        if rules:
            chain.insert(0, (cur, rules))
        parent = os.path.dirname(cur)
        if cur == stop or parent == cur or os.path.exists(os.path.join(cur, ".git")):
            return chain
        cur = parent


def is_binary(path, probe=8192):
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(probe)
    except OSError:
        return True


def iter_files(root, exts=None, glob=None, max_files=5000):
    """遞迴列出 root 底下的文字檔（略過 SKIP_DIRS、點開頭的目錄、.gitignore 排除的目錄、二進位與超過 1MB 的檔案），依路徑排序。
    exts：只要這些副檔名；glob：fnmatch 樣式（比對檔名，例如 *.py、test_*）。回傳 (絕對路徑, 相對路徑) 的 list。
    root 本身就算被 .gitignore 排除也照樣掃（明確指定的路徑）。"""
    import fnmatch
    out = []
    root = os.path.abspath(root)
    if os.path.isfile(root):
        return [(root, os.path.basename(root))]
    rules = _gitignore_rules(root)
    chains = {root: _ancestor_gitignores(root) + ([(root, rules)] if rules else [])}
    for dirpath, dirnames, filenames in os.walk(root):
        chain, keep = chains.pop(dirpath, []), []
        for d in sorted(dirnames):
            full = os.path.join(dirpath, d)
            if skip_dir(d) or (chain and _gitignored(full, chain)):
                continue
            keep.append(d)
            rules = _gitignore_rules(full)
            chains[full] = chain + [(full, rules)] if rules else chain
        dirnames[:] = keep
        for fn in sorted(filenames):
            if exts and os.path.splitext(fn)[1].lower() not in exts:
                continue
            if glob and not (fnmatch.fnmatch(fn, glob) or fnmatch.fnmatch(os.path.relpath(os.path.join(dirpath, fn), root), glob)):
                continue
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > MAX_FILE_BYTES or is_binary(p):
                    continue
            except OSError:
                continue
            out.append((p, os.path.relpath(p, root)))
            if len(out) >= max_files:
                return out
    return out


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ---------------------------------------------------------------- 工作區與路徑邊界
def workspace_root():
    """coding job 的工作區（CODE_WORKSPACE）；沒設定回 None。"""
    ws = (os.environ.get("CODE_WORKSPACE") or "").strip()
    return os.path.realpath(os.path.expanduser(ws)) if ws else None


def base_root():
    """相對路徑的基準與寫入邊界：有工作區用工作區，否則用目前工作目錄（harness 以 cwd 傳入 AI 的工作目錄）。"""
    return workspace_root() or os.path.realpath(os.getcwd())


def _inside(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def resolve_path(path, for_write=False):
    """使用者／模型給的路徑 → (絕對路徑, 錯誤)。相對路徑以工作區（或目前工作目錄）為準。
    有工作區時讀寫都要在工作區內；沒有工作區時只限制寫入（在目前工作目錄內）。寫入一律不准碰 .git/。"""
    raw = str(path or "").strip().strip("\"'")
    if not raw:
        return None, "[ERROR] 沒有給檔案路徑。"
    p = os.path.expanduser(raw)
    if not os.path.isabs(p):
        p = os.path.join(base_root(), p)
    p = os.path.realpath(p)
    ws = workspace_root()
    limit = ws or (base_root() if for_write else None)
    if limit and not _inside(p, limit):
        what = "工作區" if ws else "目前工作目錄"
        return None, (f"[ERROR] 路徑 {raw} 在{what} {limit} 之外，" + ("不能寫入。" if for_write else "不能讀取。")
                      + "請用相對於專案根目錄的路徑。")
    if for_write and (f"{os.sep}.git{os.sep}" in p + os.sep):
        return None, f"[ERROR] 不能修改 .git 目錄裡的檔案：{raw}"
    return p, None


def rel_to_root(abs_path):
    root = base_root()
    try:
        rel = os.path.relpath(abs_path, root)
    except ValueError:
        return abs_path
    return abs_path if rel.startswith("..") else rel


# ---------------------------------------------------------------- 顯示
LINE_NO_RE = re.compile(r"^\s*\d+\s?[|│→] ?")


def numbered(lines, start=1):
    """帶行號的顯示：`  12| 內容`。模型會照抄行號，所以寫入技能會自動把這個前綴剝掉（strip_line_numbers）。"""
    width = max(4, len(str(start + len(lines))))
    return "\n".join(f"{i:>{width}}| {ln}" for i, ln in enumerate(lines, start))


def strip_line_numbers(text):
    """整段每一行（空行除外）都以 `數字|` 開頭時，把行號前綴剝掉：模型常把 code_view 的行號一起抄進 SEARCH 或新內容裡。"""
    lines = text.split("\n")
    body = [ln for ln in lines if ln.strip()]
    if not body or not all(LINE_NO_RE.match(ln) for ln in body):
        return text
    return "\n".join(LINE_NO_RE.sub("", ln, count=1) if ln.strip() else ln for ln in lines)


def clip_middle(text, max_chars, what="輸出"):
    """超過 max_chars 時保留頭 60%、尾 40%，中間註明省略多少字元。"""
    if len(text) <= max_chars:
        return text
    head, tail = int(max_chars * 0.6), int(max_chars * 0.4)
    return f"{text[:head]}\n…（{what}過長，中間省略 {len(text) - head - tail} 字元）…\n{text[-tail:]}"


# ---------------------------------------------------------------- 語法檢查
def _cpp():
    """_cpp_common（C／C++ 的掃描器）：agent_core 以套件 import 這個模組，腳本則是直接 import。"""
    try:
        from . import _cpp_common
    except ImportError:
        import _cpp_common
    return _cpp_common


def syntax_check(path, text):
    """依副檔名做語法檢查：Python（compile）、JSON、TOML、YAML（有 PyYAML 才查）、C／C++（括號與 #if／#endif 配對，
    不呼叫編譯器）。回傳 (ok, 訊息)；不支援的格式回 (True, "")。"""
    lang = language_of(path)
    try:
        if lang in ("C", "C++", "C/C++ 標頭"):
            ok, msg = _cpp().balance_check(text)
            return (True, f"{lang} 括號配對 OK") if ok else (False, f"{lang} 語法錯誤：{msg}")
        if lang == "Python":
            compile(text, path, "exec", dont_inherit=True)
            return True, "Python 語法 OK"
        if lang == "JSON":
            json.loads(text)
            return True, "JSON 格式 OK"
        if lang == "TOML":
            import tomllib
            tomllib.loads(text)
            return True, "TOML 格式 OK"
        if lang == "YAML":
            try:
                import yaml
            except ImportError:
                return True, ""
            list(yaml.safe_load_all(text))
            return True, "YAML 格式 OK"
    except SyntaxError as e:
        line = (e.text or "").rstrip("\n")
        return False, f"Python 語法錯誤：第 {e.lineno} 行：{e.msg}" + (f"\n    {line}" if line.strip() else "")
    except ValueError as e:   # JSONDecodeError、TOMLDecodeError 都是 ValueError
        return False, f"{lang} 格式錯誤：{e}"
    except Exception as e:     # yaml.YAMLError 等
        return False, f"{lang} 格式錯誤：{e}"
    return True, ""


# ---------------------------------------------------------------- 執行環境（測試、建置、程式共用）
_SYSTEM_BINS = {"/usr/bin", "/bin", "/usr/local/bin", "/usr/sbin", "/sbin"}


def project_python(root=None):
    """跑專案的 Python 測試與程式用的直譯器：CODE_PYTHON → 工作區的 .venv／venv／env → harness 自己的直譯器
    （harness 用 ~/aiagent_venv_env 的 python 執行，pytest 裝在那裡）→ PATH 上的 python3。"""
    explicit = (os.environ.get("CODE_PYTHON") or "").strip()
    if explicit:
        p = os.path.expanduser(explicit)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
        found = shutil.which(explicit)
        if found:
            return found
    root = root or base_root()
    for d in (".venv", "venv", "env"):
        p = os.path.join(root, d, "bin", "python")
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return sys.executable or shutil.which("python3") or "python3"


def cpp_prefixes():
    """C／C++ 函式庫的安裝位置（有 include 目錄的才算）：CODE_CPP_PREFIX（冒號分隔），沒設定用 ~/.local。"""
    raw = os.environ.get("CODE_CPP_PREFIX")
    cands = [x for x in (raw.split(os.pathsep) if raw and raw.strip() else ["~/.local"]) if x.strip()]
    out = []
    for c in cands:
        p = os.path.realpath(os.path.expanduser(c.strip()))
        if os.path.isdir(os.path.join(p, "include")) and p not in out:
            out.append(p)
    return out


def _prepend(env, key, values):
    cur = [x for x in (env.get(key) or "").split(os.pathsep) if x]
    new = [v for v in values if v and os.path.isdir(v)]
    if new:
        env[key] = os.pathsep.join(dict.fromkeys(new + cur))


def toolchain_env(root=None, base=None):
    """執行專案指令（測試、建置、程式）用的環境變數：
    - PATH 前面加上專案的 Python 所在目錄（工作區的虛擬環境）與 harness 直譯器所在目錄（pytest、cmake、ctest、ninja 裝在這裡），
      所以指令裡的 python3／pytest／cmake 用的是這些；系統目錄（/usr/bin…）不往前搬。
    - C／C++：cpp_prefixes() 的 include／lib 加進 CPATH、LIBRARY_PATH、LD_LIBRARY_PATH、CMAKE_PREFIX_PATH、PKG_CONFIG_PATH
      （gtest 裝在 ~/.local 時，g++ … -lgtest 與 CMake 的 find_package(GTest) 都找得到）。"""
    env = dict(os.environ if base is None else base)
    root = root or base_root()
    bins = [os.path.dirname(project_python(root))]
    if sys.executable:
        bins.append(os.path.dirname(sys.executable))     # 不 realpath：虛擬環境的 python 是 symlink，要留在 venv/bin
    _prepend(env, "PATH", [b for b in dict.fromkeys(bins) if b not in _SYSTEM_BINS])
    for pre in cpp_prefixes():
        libs = [os.path.join(pre, "lib"), os.path.join(pre, "lib64")]
        _prepend(env, "CPATH", [os.path.join(pre, "include")])
        _prepend(env, "LIBRARY_PATH", libs)
        _prepend(env, "LD_LIBRARY_PATH", libs)
        _prepend(env, "CMAKE_PREFIX_PATH", [pre])
        _prepend(env, "PKG_CONFIG_PATH", [os.path.join(x, "pkgconfig") for x in libs] + [os.path.join(pre, "share", "pkgconfig")])
    return env


# ---------------------------------------------------------------- 備份（coding job 的還原依據）
def backup_dir():
    d = (os.environ.get("CODE_BACKUP_DIR") or "").strip()
    return os.path.abspath(d) if d else None


def load_manifest(bdir=None):
    bdir = bdir or backup_dir()
    if not bdir:
        return {}
    try:
        with open(os.path.join(bdir, "manifest.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def backup_before_write(abs_path):
    """寫入前呼叫：這個 job 第一次碰這個檔案時，把原檔複製到 <備份>/files/<相對路徑>，manifest 記下原本存不存在。
    之後再改同一個檔案不再備份（保留的是 job 開始前的版本）。沒有 CODE_BACKUP_DIR 時什麼都不做。"""
    bdir = backup_dir()
    if not bdir:
        return
    rel = os.path.relpath(abs_path, base_root())
    manifest = load_manifest(bdir)
    if rel in manifest:
        return
    existed = os.path.exists(abs_path)
    if existed:
        dst = os.path.join(bdir, "files", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(abs_path, dst)
    os.makedirs(bdir, exist_ok=True)
    manifest[rel] = {"existed": existed, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    _write_json_atomic(os.path.join(bdir, "manifest.json"), manifest)


def original_text(rel, bdir=None):
    """job 開始前這個檔案的內容（沒有備份紀錄回 None；原本不存在回空字串）。"""
    bdir = bdir or backup_dir()
    entry = load_manifest(bdir).get(rel)
    if entry is None:
        return None
    if not entry.get("existed"):
        return ""
    try:
        return read_text(os.path.join(bdir, "files", rel))
    except OSError:
        return None


def detect_newline(path):
    """檔案原本的換行：有 CRLF 回 "\r\n"，否則 None（照系統預設的 \n）。讀檔時 Python 會把 CRLF 統一成 \n，
    寫回去時要換回原本的樣子，不然 Windows 來的檔案改一行，git 會顯示每一行都改了。"""
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError:
        return None
    return "\r\n" if b"\r\n" in head else None


def write_text(abs_path, text, newline=None):
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)


# ---------------------------------------------------------------- diff
def unified_diff(old, new, rel, context=3):
    """回傳 (diff 文字, 加了幾行, 刪了幾行)。"""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}", n=context, lineterm=""))
    added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
    return "\n".join(diff), added, removed


def changed_line_range(old, new):
    """新內容裡被改到的行範圍（1-based，含頭含尾）；沒有變化回 None。給「修改後的那一段」顯示用。"""
    sm = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    lo = hi = None
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        lo = j1 + 1 if lo is None else lo
        hi = max(j2, j1 + 1)
    return (lo, hi) if lo is not None else None


# ---------------------------------------------------------------- 指令安全檢查（code_run 與 coding job 的驗證指令共用）
# 這是啟發式的擋法（跟 guard.is_readonly_shell 同一種精神）：coding worker 在使用者核准的計畫裡自動執行，沒有人逐一按確認，
# 所以把「明顯會毀損、改到工作區以外、動到版本紀錄、需要網路或改環境」的指令擋掉；刪檔一律改用 code_write --delete（會先備份）。
_BLOCKED_HEADS = {
    "sudo": "不能用 sudo", "su": "不能切換使用者", "rm": "刪除檔案請用 code_write <檔案> --delete（會先備份、可還原）",
    "rmdir": "不能刪目錄", "shred": "不能毀損檔案", "dd": "不能用 dd", "mkfs": "不能格式化", "fdisk": "不能動分割區",
    "shutdown": "不能關機", "reboot": "不能重開機", "poweroff": "不能關機", "halt": "不能關機",
    "kill": "不能送訊號給程序", "killall": "不能送訊號給程序", "pkill": "不能送訊號給程序",
    "chown": "不能改擁有者", "chmod": "不能改權限（需要的話請使用者自己做）", "mount": "不能掛載", "umount": "不能卸載",
    "curl": "不能連網路", "wget": "不能連網路", "ssh": "不能連到其他機器", "scp": "不能連到其他機器", "rsync": "不能同步到其他位置",
    "apt": "不能安裝系統套件", "apt-get": "不能安裝系統套件", "dpkg": "不能安裝系統套件", "snap": "不能安裝系統套件",
    "systemctl": "不能操作系統服務", "service": "不能操作系統服務", "crontab": "不能改排程", "docker": "不能操作容器（請用容器技能）",
    "mv": "搬移檔案請改用 code_write 建新檔＋code_write --delete 刪舊檔（才有備份）",
    "eval": "不能用 eval", "exec": "不能用 exec", "nohup": "不能留背景程序", "setsid": "不能留背景程序",
}
_GIT_READONLY = {"status", "diff", "log", "show", "blame", "grep", "ls-files", "rev-parse", "branch", "describe", "shortlog"}
_INSTALL_RE = re.compile(r"\b(pip3?|python3?\s+-m\s+pip|conda|mamba|npm|yarn|pnpm|gem|cargo)\s+(install|uninstall|add|remove|update|upgrade)\b")
_SEPARATORS = {"&&", "||", ";", "|", "&", "|&", ";;", ";&"}


def _shell_segments(text):
    """把指令依 &&、||、;、|、& 切成好幾段，每段是 token list；引號裡的分隔符號不算（shlex 的標點模式）。"""
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    segs, cur = [], []
    for tok in lex:
        if tok in _SEPARATORS:
            if cur:
                segs.append(cur)
            cur = []
        elif tok in ("(", ")", "{", "}"):
            continue
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs


def check_command(command, root=None):
    """code_run 要執行的指令是否在允許範圍：回傳 None（可以）或 [ERROR] 開頭的說明（為什麼不行、該怎麼做）。"""
    text = str(command or "").strip()
    if not text:
        return "[ERROR] 沒有要執行的指令。"
    root = os.path.realpath(root or base_root())
    if re.search(r"(^|[^\w])sudo\b", text):
        return "[ERROR] 不允許：不能用 sudo。"
    if "`" in text or "$(" in text:
        return "[ERROR] 不允許：指令替換（反引號、$( )）看不出實際會執行什麼，請拆成明確的指令。"
    if not os.environ.get("CODE_ALLOW_INSTALL") and _INSTALL_RE.search(text):
        return ("[ERROR] 不允許：安裝／移除套件會改到環境（也需要網路）。缺套件時把需要的套件寫進報告，請使用者自己安裝"
                "（要放行請設定環境變數 CODE_ALLOW_INSTALL=1）。")
    # 寫到工作區以外的轉向（/dev/null 除外）
    for m in re.finditer(r"(?:\d?>>?|\btee\s+(?:-a\s+)?)\s*([^\s;&|]+)", text):
        target = m.group(1).strip("\"'")
        if target.startswith("&") or target == "/dev/null":
            continue
        tp = os.path.realpath(os.path.join(root, os.path.expanduser(target)))
        if not _inside(tp, root):
            return f"[ERROR] 不允許：輸出轉向到工作區以外（{target}）。"
    try:
        segments = _shell_segments(text)
    except ValueError:
        return f"[ERROR] 指令的引號不成對，看不懂：{text}"
    for toks in segments:
        while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):   # VAR=value 前綴
            toks = toks[1:]
        if not toks:
            continue
        head = os.path.basename(toks[0])
        if head in ("timeout", "time", "env", "nice"):
            rest = [t for t in toks[1:] if not t.startswith("-") and not re.match(r"^\d+[smhd]?$", t)
                    and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)]
            if not rest:
                continue
            head = os.path.basename(rest[0])
            toks = rest
        if head in _BLOCKED_HEADS:
            return f"[ERROR] 不允許：{head}——{_BLOCKED_HEADS[head]}。"
        if head == "git" and len(toks) > 1:
            sub = next((t for t in toks[1:] if not t.startswith("-")), "")
            if sub not in _GIT_READONLY:
                return f"[ERROR] 不允許：git {sub} 會改變版本紀錄或工作區；只能用 git {'／'.join(sorted(_GIT_READONLY))} 這些查詢指令。"
        if head == "cd" and len(toks) > 1:
            target = os.path.realpath(os.path.join(root, os.path.expanduser(toks[1])))
            if not _inside(target, root):
                return f"[ERROR] 不允許：cd 到工作區以外（{toks[1]}）。"
        if head == "find" and any(t in ("-delete", "-exec", "-execdir", "-ok") for t in toks):
            return "[ERROR] 不允許：find 不能帶 -delete／-exec。"
        if head in ("sed", "perl") and any(t == "-i" or t.startswith("-i") for t in toks[1:]):
            return "[ERROR] 不允許：原地改檔請用 code_edit（才有備份、語法檢查與 diff）。"
        if (head in ("make", "gmake", "ninja", "meson") and "install" in toks[1:]) or (head == "cmake" and "--install" in toks) \
                or head == "ldconfig":
            return "[ERROR] 不允許：install 會把檔案裝到工作區以外（系統目錄）；建置與測試不需要安裝，需要的話請使用者自己做。"
        if head == "cmake" and "-E" in toks and any(t in ("rm", "remove", "remove_directory", "rename") for t in toks):
            return "[ERROR] 不允許：刪除或搬移檔案請用 code_write（才有備份）。"
    return None


# ---------------------------------------------------------------- 測試輸出的摘要（數值由腳本算，模型照抄）
# pytest 的摘要行：「==== 4 failed, 3 passed in 0.12s ====」；-q 時沒有 = 框線：「8 passed in 0.01s」
_PYTEST_SUMMARY_RE = re.compile(
    r"^=*\s*((?:\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|warnings?|deselected|rerun)(?:, )?)+|no tests ran)"
    r"\s*(?:in [\d.]+s\b.*?)?\s*=*\s*$", re.M)
_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed|warnings?|deselected)")


_GTEST_PASSED_RE = re.compile(r"^\[  PASSED  \] (\d+) tests?\.", re.M)
_GTEST_FAILED_RE = re.compile(r"^\[  FAILED  \] (\d+) tests?, listed below", re.M)
_GTEST_SKIPPED_RE = re.compile(r"^\[  SKIPPED \] (\d+) tests?, listed below", re.M)
_CTEST_RE = re.compile(r"(\d+)% tests passed(?:, (\d+) tests? failed)? out of (\d+)")   # CTest 4：「100% tests passed out of 7」


def gtest_counts(output):
    """gtest 的「[  PASSED  ] N tests.」「[  FAILED  ] M tests, listed below」（好幾個測試程式時加總）；沒有摘要回空 dict。"""
    text = output or ""
    if not (_GTEST_PASSED_RE.search(text) or _GTEST_FAILED_RE.search(text)):
        return {}
    return {"passed": sum(int(x) for x in _GTEST_PASSED_RE.findall(text)),
            "failed": sum(int(x) for x in _GTEST_FAILED_RE.findall(text)),
            "skipped": sum(int(x) for x in _GTEST_SKIPPED_RE.findall(text))}


def ctest_counts(output):
    """ctest 的「83% tests passed, 1 tests failed out of 6」（最後一個）；沒有摘要回空 dict。"""
    m = None
    for m in _CTEST_RE.finditer(output or ""):
        pass
    if not m:
        return {}
    failed, total = int(m.group(2) or 0), int(m.group(3))
    return {"passed": total - failed, "failed": failed}


# 測試檔（含測試目錄裡的輔助檔、conftest）與建置／測試設定檔：「只寫測試」的工作只能改這些
TEST_PATH_RE = re.compile(r"(^|/)(tests?|unit_tests|testing|spec)/|(^|/)test_[^/]*$|_test\.[^/]+$|(^|/)conftest\.py$")
BUILD_FILE_RE = re.compile(r"(^|/)(CMakeLists\.txt|[Mm]akefile[^/]*|makefile_test|pytest\.ini|setup\.cfg|tox\.ini|\.coveragerc)$")


def is_test_path(rel):
    return bool(TEST_PATH_RE.search((rel or "").replace(os.sep, "/")))


def tests_without_assertions(path):
    """測試檔裡沒有任何斷言的測試名稱（只呼叫函式、什麼都沒檢查的測試，覆蓋率會算、卻抓不到 bug）。
    Python：test_* 函式／方法裡沒有 assert、沒有 pytest.raises／approx、沒有 self.assert*／mock 的 assert_*；
    C／C++：TEST／TEST_F／TEST_P 裡沒有 EXPECT_*／ASSERT_*（也接受 gmock 的 EXPECT_CALL、FAIL()、SUCCEED() 以外的寫法不算）。"""
    try:
        text = read_text(path)
    except OSError:
        return []
    if path.endswith(".py"):
        import ast
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        bare = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                ok = False
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assert):
                        ok = True
                    elif isinstance(sub, ast.Call):
                        f = sub.func
                        name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
                        if name.startswith(("assert", "fail")) or name in ("raises", "warns", "approx", "deprecated_call"):
                            ok = True
                    if ok:
                        break
                if not ok:
                    bare.append(node.name)
        return bare
    bare = []
    for m in re.finditer(r"\bTEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)", text):
        start = text.find("{", m.end())
        if start < 0:
            continue
        depth, i = 0, start
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[start:i]
        if not re.search(r"\b(EXPECT|ASSERT)_[A-Z_]+\s*\(|\bEXPECT_CALL\b|\bFAIL\s*\(", body):
            bare.append(f"{m.group(1)}.{m.group(2)}")
    return bare


def tests_only_task(task):
    """任務只要求寫測試（補測試、量覆蓋率），沒有要求修改程式 → True。「不要修改正式程式」這類否定句先拿掉再判斷。"""
    text = re.sub(r"(不要|不用|不需要|別|勿|不可以|不能)[^，。；\n]{0,12}", "", task or "")
    wants_tests = re.search(r"(寫|補|新增|增加|產生|撰寫|加上|補上)[^，。；\n]{0,10}(單元)?測試|test ?cases?|覆蓋率|coverage", task or "", re.I)
    wants_code = re.search(r"(修正|修好|修復|修改|實作|重構|改成|改善|修 ?bug|\bfix\b)|(新增|增加|加入|加上|做)[^，。；\n]{0,15}"
                           r"(功能|指令|選項|api|介面|方法|函式|類別|欄位|參數)", text, re.I)
    return bool(wants_tests) and not wants_code


_ZERO_TESTS = [
    (re.compile(r"^Ran 0 tests in ", re.M), "一個測試都沒有跑（Ran 0 tests）"),
    (re.compile(r"collected 0 items(?! / )|\bno tests ran\b"), "pytest 沒有收集到任何測試"),
    (re.compile(r"\[=+\] (?:Running )?0 tests? from 0 test (?:suites|cases)"), "gtest 沒有任何測試"),
    (re.compile(r"^No tests were found!*", re.M), "ctest 沒有找到測試"),
    (re.compile(r"tests finished: 0 passed(?!.*\d+ failed)", re.S), "一個測試都沒有跑（tests finished: 0 passed）"),
]


def zero_tests(output):
    """測試指令的輸出顯示「一個測試都沒跑到」→ 說明文字；否則 None。有任何通過或失敗的測試就不算。"""
    text = output or ""
    counts = summarize_test_counts(text)
    if counts and any(counts.get(k) for k in ("passed", "failed", "errors", "error")):
        return None
    for rx, why in _ZERO_TESTS:
        if rx.search(text):
            return why
    return None


def summarize_test_counts(output):
    """從測試輸出抓通過／失敗數：pytest（N passed, M failed）、unittest（Ran N tests）、ctest（x% tests passed…）、
    gtest（[  PASSED  ] N tests）。回傳 dict（沒抓到回空 dict）。ctest 有摘要時只用它（--output-on-failure 印出的 gtest 摘要不重複算）。"""
    ct = ctest_counts(output)
    if ct:
        return ct
    counts = {k: v for k, v in gtest_counts(output).items() if v}
    m = None
    for m in _PYTEST_SUMMARY_RE.finditer(output or ""):
        pass
    text = m.group(1) if m else ""
    for n, kind in _COUNT_RE.findall(text):
        kind = {"error": "errors", "warning": "warnings"}.get(kind, kind)
        counts[kind] = counts.get(kind, 0) + int(n)
    m2 = re.search(r"Ran (\d+) tests? in", output or "")   # unittest
    if not counts and m2:
        total = int(m2.group(1))
        fm = re.search(r"FAILED \((.*?)\)", output or "")
        failed = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", fm.group(1))) if fm else 0
        counts = {"passed": total - failed, "failed": failed} if total else {}
    return counts


def format_counts(counts):
    order = ["passed", "failed", "errors", "skipped", "xfailed", "xpassed", "deselected"]
    if counts.get("failed") or counts.get("errors"):        # 有失敗時失敗數放前面
        order = ["failed", "errors", "passed", "skipped", "xfailed", "xpassed", "deselected"]
    return "、".join(f"{counts[k]} {k}" for k in order if counts.get(k))


# ---------------------------------------------------------------- 編輯（code_edit／code_write 共用）
# 寫入技能的「內容」不經過 JSON 參數：harness 讓模型用一般文字輸出（``` 區塊或 SEARCH/REPLACE 區塊），存成 payload 檔再交給
# 腳本（--payload）。實測 gemma4:e4b 把程式碼放進 JSON 字串時，反斜線會少跳脫一層（'\\"' 變成 '\"'），3 次全錯；
# 同樣的程式碼放在 ``` 區塊裡 3 次全對。所以 payload 是模型的原始回覆，這裡負責把真正的內容拆出來。
_FENCE_RE = re.compile(r"^```[ \t]*([\w+.#-]*)[^\n]*\n(.*?)^```[ \t]*$", re.S | re.M)
_SR_RE = re.compile(r"^[ \t]*<{5,9}[ \t]*SEARCH[^\n]*\n(.*?)^[ \t]*={5,9}[ \t]*\n(.*?)^[ \t]*>{5,9}[ \t]*REPLACE[^\n]*$", re.S | re.M)
# 「其餘不變」這類偷懶的省略：出現在新增的行裡就拒絕寫入（不然原本的程式碼會被這一行取代掉）
_ELISION_RE = re.compile(
    r"^\s*(#|//|/\*|\*|--|<!--)?\s*(\.\.\.|…)?\s*\(?\s*("
    r"(rest|remainder) of (the )?(code|file|class|function|implementation)|existing code|unchanged|same as (before|above)|"
    r"other (methods|functions|code)|code omitted|omitted for brevity|(keep|kept) (as is|the same)|"
    r"其餘(不變|省略|同上|略)|其他(不變|省略|部分不變)|以下(省略|不變|略)|原本的程式碼|保持不變|省略\s*\.{0,3}|略\s*$"
    r")", re.I)
_ELLIPSIS_ONLY_RE = re.compile(r"^\s*(#|//)?\s*(\.\.\.|…)\s*$")


def read_payload(path=None):
    """payload 檔（--payload 路徑）的內容；--payload - 才讀 stdin（不主動讀 stdin：harness 執行腳本時 stdin 不一定是終端機，
    讀了會一直等）。沒有給回 None。"""
    if path == "-":
        import sys
        data = sys.stdin.read()
        return data if data.strip() else None
    if path:
        return read_text(path)
    return None


def extract_fenced(text):
    """模型回覆裡的程式碼：有 ``` 區塊就取最長的那一個（說明文字裡偶爾夾小區塊），沒有就整段（去掉頭尾空行）。
    回傳 (內容, 有沒有找到區塊)。"""
    blocks = [m.group(2) for m in _FENCE_RE.finditer(text or "")]
    if blocks:
        body = max(blocks, key=len)
        return body[:-1] if body.endswith("\n") else body, True
    t = (text or "").strip("\n")
    if t.startswith("```"):   # 只有開頭沒有結尾（輸出被截斷）
        t = t.split("\n", 1)[1] if "\n" in t else ""
    return t, False


def parse_search_replace(text):
    """SEARCH/REPLACE 區塊 → [(old, new)]（已剝掉被抄進來的行號）。區塊可以被包在 ``` 裡。"""
    blocks = []
    for m in _SR_RE.finditer(text or ""):
        old, new = m.group(1), m.group(2)
        old = old[:-1] if old.endswith("\n") else old
        new = new[:-1] if new.endswith("\n") else new
        blocks.append((strip_line_numbers(old), strip_line_numbers(new)))
    return blocks


def find_elisions(lines):
    """新增的行裡看起來是「其餘不變／...」的省略行（回傳 [(序號, 行)]）。"""
    hits = []
    for i, ln in enumerate(lines):
        if _ELISION_RE.match(ln) or _ELLIPSIS_ONLY_RE.match(ln):
            hits.append((i, ln))
    return hits


def _indent_of(line):
    return line[:len(line) - len(line.lstrip(" \t"))]


def _reindent(lines, old_indent, new_indent):
    """把 lines 的縮排從 old_indent 換成 new_indent（只換開頭相同的部分；空行不動）。"""
    out = []
    for ln in lines:
        if not ln.strip():
            out.append(ln)
        elif ln.startswith(old_indent):
            out.append(new_indent + ln[len(old_indent):])
        else:
            out.append(new_indent + ln.lstrip(" \t") if not old_indent else ln)
    return out


def _windows(content_lines, old_lines, key):
    """content 裡跟 old 逐行（依 key 正規化後）相同的位置（起始索引 list）。"""
    want = [key(x) for x in old_lines]
    n = len(want)
    if n == 0:
        return []
    keys = [key(x) for x in content_lines]
    return [i for i in range(len(keys) - n + 1) if keys[i:i + n] == want]


def apply_block(content, old, new):
    """套用一個 SEARCH/REPLACE。回傳 (新內容, 比對方式, 錯誤)。比對方式：exact／trailing_ws／indent／append。
    依序試：逐字 → 忽略行尾空白 → 忽略縮排（找到後把 REPLACE 的縮排平移到檔案實際的縮排）。對到多個位置就報錯（要多帶幾行）。"""
    if not old.strip():
        if content and not content.endswith("\n"):
            content += "\n"
        return content + new + ("\n" if new and not new.endswith("\n") else ""), "append", None
    count = content.count(old)
    if count == 1:
        return content.replace(old, new, 1), "exact", None
    lines = content.split("\n")
    old_lines = old.split("\n")
    while old_lines and not old_lines[0].strip():      # SEARCH 頭尾的空行不算
        old_lines = old_lines[1:]
    while old_lines and not old_lines[-1].strip():
        old_lines = old_lines[:-1]
    new_lines = new.split("\n")
    if count > 1:
        starts = _windows(lines, old_lines, lambda x: x)
        where = "、".join(f"第 {s + 1} 行" for s in starts[:6])
        return None, None, (f"SEARCH 的內容在檔案裡出現 {count} 次（{where}），不知道要改哪一個：請在 SEARCH 多帶幾行上下文，"
                            f"讓它只對到一個位置。")
    for mode, key in (("trailing_ws", lambda x: x.rstrip()), ("indent", lambda x: x.strip())):
        starts = _windows(lines, old_lines, key)
        if len(starts) > 1:
            where = "、".join(f"第 {s + 1} 行" for s in starts[:6])
            return None, None, f"SEARCH 的內容（忽略空白後）在檔案裡出現 {len(starts)} 次（{where}）：請多帶幾行上下文。"
        if len(starts) == 1:
            s = starts[0]
            seg = lines[s:s + len(old_lines)]
            repl = new_lines
            if mode == "indent":
                first_old = next((x for x in old_lines if x.strip()), "")
                first_file = next((x for x in seg if x.strip()), "")
                repl = _reindent(new_lines, _indent_of(first_old), _indent_of(first_file))
            return "\n".join(lines[:s] + repl + lines[s + len(old_lines):]), mode, None
    return None, None, _closest_hint(lines, old_lines)


def _closest_hint(lines, old_lines):
    """SEARCH 對不到時，找檔案裡最像的一段，連行號一起給模型看（讓它照實際內容重寫 SEARCH）。"""
    n = max(1, len(old_lines))
    target = "\n".join(x.strip() for x in old_lines)
    best, best_i = 0.0, None
    first = old_lines[0].strip() if old_lines else ""
    cands = [i for i, ln in enumerate(lines) if first and difflib.SequenceMatcher(None, ln.strip(), first).ratio() > 0.6] or \
        list(range(0, max(1, len(lines) - n + 1)))
    for i in cands[:400]:
        seg = "\n".join(x.strip() for x in lines[i:i + n])
        r = difflib.SequenceMatcher(None, seg, target, autojunk=False).ratio()
        if r > best:
            best, best_i = r, i
    msg = "SEARCH 的內容在檔案裡找不到（逐字、忽略行尾空白、忽略縮排都對不到）。"
    if best_i is not None and best >= 0.5:
        lo, hi = best_i, min(len(lines), best_i + n + 2)
        msg += (f"檔案裡最像的是第 {lo + 1}～{hi} 行（相似度 {best:.0%}），SEARCH 要逐字照抄這裡的實際內容（不要帶行號）：\n"
                + numbered(lines[lo:hi], lo + 1))
    else:
        msg += "請先用 code_view 看檔案目前的內容，再照實際內容重寫 SEARCH。"
    return msg


def edit_report(rel, old, new, path_for_lang=None, max_diff_chars=3000, region_lines=60):
    """寫入成功後給模型與使用者看的內容：diff（有上限）＋修改後的那一段（帶行號）。回傳 (文字, 加, 刪)。"""
    diff, added, removed = unified_diff(old, new, rel)
    parts = []
    if diff:
        parts.append("變更（diff）：\n" + clip_middle(diff, max_diff_chars, "diff"))
    rng = changed_line_range(old, new)
    if rng:
        new_lines = new.split("\n")
        lo, hi = max(1, rng[0] - 3), min(len(new_lines), rng[1] + 3)
        if hi - lo + 1 > region_lines:
            hi = lo + region_lines - 1
        parts.append(f"修改後的第 {lo}～{hi} 行：\n" + numbered(new_lines[lo - 1:hi], lo))
    return "\n".join(parts), added, removed
