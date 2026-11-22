"""本機路徑的共用層：list_dir（ls）、search_text（grep）、find_file、code_ast_reader、change_dir（cd）、view_file（cat）、
csv_query、file_ops、image_inspect 共用。只用標準庫。

1. resolve()：把模型給的路徑換成絕對路徑（`~`、`$HOME` 展開；相對路徑相對於目前的工作目錄＝harness 的 cwd），檢查存在、
   種類（目錄／檔案）與權限，錯誤訊息一律是「[ERROR] 原因。下一步：…」。
2. suggest()：路徑找不到時的「你是不是要找」。小模型最常見的錯是路徑差一點：大小寫、少一層目錄、拼錯一個字（launch／lauch）、
   把檔名當目錄。只回「不存在」時它常常換個更離譜的猜法、或一直重試同一個路徑（主對話的卡住偵測會在第三次停下來）；直接列出
   實際存在、最像的幾個路徑，下一步就對了。做法：從要找的路徑往上找到第一個存在的目錄，在那裡比對缺的那一段（不分大小寫、
   difflib 相似度）；另外在目前工作目錄底下（最多 4 層、最多看 5000 個項目）找同名的檔案或目錄。候選的清單是 near_paths()，
   找不到路徑的錯誤把它帶在 ToolError 的 near（收據記成 near：低階執行器的第 1 級照它判斷，好幾個候選時不替上一層選）。
3. DEFAULT_EXCLUDES：search_text、find_file 預設略過的目錄（ROS 2 Workspace 的 build／install／log、.git、虛擬環境…）。
4. newest_line()：「最新修改：A（時間）；其次：B、C」（list_dir、find_file 共用；數值由腳本算、模型照抄）。
5. harness_logs_dir()：技能要寫的檔案（file_ops 的備份、stt_engine 的辨識結果）一律放 harness 的 logs/，不寫進使用者的目錄。
6. 錯誤是 _receipt_common.ToolError（就是 str，另外帶收據用的種類）：找不到、種類不對、失效的連結＝args（換路徑就好），
   沒有權限＝env（換參數修不好）。
7. path_glob()、include_ok()：名稱的寫法含 / 時比對整個路徑（不分大小寫）。find_file 的名稱關鍵字與 search_text、code_defs、py_refs 的
   --include 用同一條規則；不含 / 的 --include 照舊只比對檔名。
"""
import difflib
import fnmatch
import os
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _receipt_common import ToolError  # noqa: E402

DEFAULT_EXCLUDES = ("build", "install", "log", ".git", "node_modules", "__pycache__", "venv", ".venv")
_SKIP = set(DEFAULT_EXCLUDES)
HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NOUN = {"dir": "目錄", "file": "檔案", "any": "路徑"}


def harness_logs_dir(*sub):
    """<harness>/logs/<sub>（不建立）。HARNESS_LOGS_DIR 只給測試用（evals/skills 在臨時目錄跑，不碰正式的 logs/）。"""
    root = (os.environ.get("HARNESS_LOGS_DIR") or "").strip() or os.path.join(HARNESS_ROOT, "logs")
    return os.path.join(root, *sub)


def expand(path):
    """`~`、`~user`、`$HOME`／`${HOME}` 展開（其他環境變數不展開：路徑裡的 $ 多半是檔名的一部分）。"""
    p = str(path).strip()
    home = os.path.expanduser("~")
    if p.startswith("$HOME") or p.startswith("${HOME}"):
        p = home + p[len("${HOME}") if p.startswith("${HOME}") else len("$HOME"):]
    return os.path.expanduser(p)


def _kind_ok(path, want):
    return want == "any" or (want == "dir" and os.path.isdir(path)) or (want == "file" and os.path.isfile(path))


def _show(path):
    cwd = os.getcwd()
    rel = os.path.relpath(path, cwd)
    return rel if not rel.startswith("..") else path


def display(path):
    """給模型看的路徑：在目前工作目錄底下就用相對路徑，否則絕對路徑。"""
    try:
        return _show(os.path.abspath(path))
    except ValueError:
        return path


def near_paths(path, want="any", limit=5):
    """相近的路徑：候選的清單（給模型看的寫法；找不到相近的回 []）。want：any／dir／file。
    評測的對照組用 AGENT_ABLATE=path_suggest 關掉（平常不要設）。"""
    if "path_suggest" in os.environ.get("AGENT_ABLATE", ""):
        return []
    try:
        target = os.path.abspath(expand(path))
    except (TypeError, ValueError):
        return []
    missing, cur = [], target
    while not os.path.exists(cur):
        parent = os.path.dirname(cur)
        if parent == cur:
            return []
        missing.insert(0, os.path.basename(cur))
        cur = parent
    out = []
    if missing and os.path.isdir(cur):
        try:
            entries = os.listdir(cur)
        except OSError:
            entries = []
        lower = {}
        for e in entries:
            lower.setdefault(e.lower(), e)
        want_name = missing[0].lower()
        names = [lower[want_name]] if want_name in lower else []
        names += [lower[m] for m in difflib.get_close_matches(want_name, list(lower), n=limit, cutoff=0.7) if lower[m] not in names]
        for name in names:
            full = os.path.join(cur, name, *missing[1:])
            if os.path.exists(full) and _kind_ok(full, want):
                out.append(_show(full))
            elif not missing[1:] and _kind_ok(os.path.join(cur, name), want):
                out.append(_show(os.path.join(cur, name)))
    base = (missing[-1] if missing else os.path.basename(target)).lower()
    if base and len(out) < limit:
        seen, root = 0, os.getcwd()
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            dirnames[:] = [d for d in dirnames if d not in _SKIP and not d.startswith(".")] if depth < 4 else []
            for name in dirnames + filenames:
                seen += 1
                full = os.path.join(dirpath, name)
                if name.lower() == base and _kind_ok(full, want) and _show(full) not in out:
                    out.append(_show(full))
            if seen > 5000 or len(out) >= limit:
                break
    return out[:limit]


def suggest(path, want="any", limit=5, near=None):
    """回傳一句「相近的路徑：…」（找不到相近的回空字串）；near 是已經算好的 near_paths。"""
    near = near_paths(path, want, limit) if near is None else near
    return ("相近的路徑：" + "、".join(near) + "（確認拼字與大小寫；不確定時先用 list_dir 看目錄內容）") if near else ""


def _nearest_existing(abs_path):
    cur = abs_path
    while not os.path.exists(cur):
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
    return cur


def _perm_text(path):
    try:
        st = os.stat(path)
    except OSError:
        return ""
    try:
        import pwd
        owner = pwd.getpwuid(st.st_uid).pw_name
    except (ImportError, KeyError):
        owner = str(st.st_uid)
    try:
        import getpass
        me = getpass.getuser()
    except Exception:   # noqa: BLE001
        me = str(os.getuid())
    return f"權限 {stat.filemode(st.st_mode)}、擁有者 {owner}，目前使用者 {me}"


def not_found(path, want="any", noun=None):
    """找不到路徑的 [ERROR]：原因（含展開後的路徑、目前工作目錄）＋相近的路徑或下一步。"""
    noun = noun or _NOUN.get(want, "路徑")
    abs_path = os.path.abspath(expand(path))
    shown = path if abs_path == os.path.abspath(path) and not str(path).startswith(("~", "$")) else f"{path}（展開為 {abs_path}）"
    msg = f"[ERROR] 找不到{noun}：{shown}（目前工作目錄 {os.getcwd()}）"
    near = near_paths(path, want)
    hint = suggest(path, want, near=near)
    if hint:
        msg += "\n" + hint
    else:
        parent = _nearest_existing(abs_path)
        base = os.path.basename(abs_path.rstrip("/")) or abs_path
        where = display(parent) if parent else "."
        msg += f"。下一步：用 list_dir {where} 看實際有哪些項目，或用 find_file {base} {where} 找正確的位置"
    container = (os.environ.get("TARGET_CONTAINER") or "").strip()
    if container and os.path.isabs(abs_path):
        msg += f"（如果這是容器 {container} 裡的路徑：本機技能看不到容器內，改用 docker_runcmd）"
    return ToolError(msg, "args", near=near)


def resolve(path, want="any", noun=None, dir_hint=None, file_hint=None):
    """模型給的路徑 → (絕對路徑, None) 或 (None, "[ERROR] …")。want：any／dir／file。
    檢查：存在（不存在時列相近的路徑）、種類（want=dir 卻是檔案時附 file_hint，反之附 dir_hint）、權限（目錄要能讀與進入、檔案要能讀）。"""
    if path is None or not str(path).strip():
        return None, ToolError(f"[ERROR] 沒有給{noun or _NOUN.get(want, '路徑')}。", "args")
    noun = noun or _NOUN.get(want, "路徑")
    abs_path = os.path.abspath(expand(path))
    if not os.path.exists(abs_path):
        if os.path.islink(abs_path):
            return None, ToolError(f"[ERROR] {path} 是失效的連結（指向 {os.readlink(abs_path)}，那個路徑不存在）。"
                                   f"下一步：用 list_dir {display(os.path.dirname(abs_path))} 確認，或改用連結指向的實際位置", "args")
        return None, not_found(path, want, noun)
    if want == "dir" and not os.path.isdir(abs_path):
        return None, ToolError(f"[ERROR] {path} 是檔案，不是目錄。下一步：" + (file_hint or "看檔案內容用 view_file；要列它所在的目錄用 list_dir "
                                                                        + display(os.path.dirname(abs_path))), "args")
    if want == "file" and os.path.isdir(abs_path):
        return None, ToolError(f"[ERROR] {path} 是目錄，不是檔案。下一步："
                               + (dir_hint or f"看目錄內容用 list_dir {path}；找檔名用 find_file <關鍵字> {path}"), "args")
    mode = os.R_OK | (os.X_OK if os.path.isdir(abs_path) else 0)
    if not os.access(abs_path, mode):
        return None, ToolError(f"[ERROR] 沒有權限讀取{noun}：{path}（{_perm_text(abs_path)}）。"
                               f"下一步：改用有權限的路徑；一定要看這裡的內容就請使用者自己處理權限（技能不會用 sudo）", "env")
    return abs_path, None


def split_globs(value):
    """--include、--exclude、--exclude-dir 一次一種寫法；模型常把幾種寫在一起、用 | 分開（"*.cpp|*.hpp"：檔名的寫法裡 | 是字面，
    一份都對不到）→ 拆成幾個；沒有 | 照原樣。"""
    parts = [p.strip() for p in str(value).split("|") if p.strip()]
    return parts if len(parts) > 1 else [value]


def path_glob(value):
    """名稱的寫法含 / 時比對整個路徑 → fnmatch／find -ipath 的寫法：前面補 *（哪一層都可以），沒有萬用字元的是「路徑含這一段」，
    開頭的 ./ 拿掉；不含 / 的回 None（只比對名稱）。待辦 4l ②：以前 --include 原樣交給 grep、只比對檔名，「<目錄>/*.py」一份都對不到，
    同一個值給 find_file 卻照路徑找得到。"""
    if "/" not in value:
        return None
    value = value[2:] if value.startswith("./") else value
    pat = value if any(c in value for c in "*?[") else f"*{value.strip('/')}*"
    return pat if pat.startswith("*") else f"*{pat}"


def include_ok(path, globs):
    """path 符合 --include 的其中一種寫法（沒有寫法都算）：不含 / 的比對檔名（同 grep 的 --include，分大小寫），含 / 的照 path_glob 比對
    整個路徑（絕對路徑，不分大小寫，同 find_file 的 -ipath）。"""
    if not globs:
        return True
    base, full = os.path.basename(path), os.path.abspath(path).lower()
    return any(fnmatch.fnmatchcase(full, pat.lower()) if (pat := path_glob(g)) else fnmatch.fnmatchcase(base, g) for g in globs)


def join_if_exists(parts):
    """模型忘了用引號包含空白的路徑（`My Documents` 被拆成兩個參數）：接起來存在就回傳接起來的路徑，否則 None。"""
    if len(parts) > 1:
        joined = " ".join(parts)
        if os.path.exists(expand(joined)):
            return joined
    return None


def fmt_time(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def newest_line(items, limit=3):
    """items：[(顯示名稱, 修改時間)]（呼叫端決定範圍：通常只算檔案，沒有檔案才算目錄）→
    「最新修改：A（時間）；其次：B（時間）、C（時間）」；空的回 None。"""
    ranked = sorted(items, key=lambda x: x[1], reverse=True)[:limit]
    if not ranked:
        return None
    line = f"最新修改：{ranked[0][0]}（{fmt_time(ranked[0][1])}）"
    if len(ranked) > 1:
        line += "；其次：" + "、".join(f"{n}（{fmt_time(t)}）" for n, t in ranked[1:])
    return line


def excludes_for(paths, include_all=False):
    """search_text／find_file 預設略過的目錄名稱；使用者明確指定的路徑本身在這些目錄裡（例如搜 ws/log）就不略過那個名稱。"""
    if include_all:
        return []
    named = set()
    for p in paths:
        named.update(part for part in os.path.abspath(expand(p)).split(os.sep) if part)
    return [d for d in DEFAULT_EXCLUDES if d not in named]


def clip(line, n=300):
    """單行太長就截斷並註明原本的長度。"""
    return line if len(line) <= n else f"{line[:n]}…（這一行共 {len(line)} 字，截斷）"
