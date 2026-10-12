"""路徑找不到時的「你是不是要找」：view_file（cat）、list_dir（ls）、change_dir（cd）共用。

小模型最常見的錯是路徑差一點：大小寫、少一層目錄、拼錯一個字（launch／lauch）、把檔名當目錄。只回「不存在」時它常常換個
更離譜的猜法、或一直重試同一個路徑（主對話的卡住偵測會在第三次停下來）；直接列出實際存在、最像的幾個路徑，下一步就對了。
做法：從要找的路徑往上找到第一個存在的目錄，在那裡比對缺的那一段（不分大小寫、difflib 相似度）；另外在目前工作目錄底下
（最多 4 層、最多看 5000 個項目）找同名的檔案或目錄。只用標準庫。
"""
import difflib
import os

_SKIP = {"__pycache__", "node_modules", "venv", ".venv", ".git", "build", "install", "log"}


def _kind_ok(path, want):
    return want == "any" or (want == "dir" and os.path.isdir(path)) or (want == "file" and os.path.isfile(path))


def _show(path):
    cwd = os.getcwd()
    rel = os.path.relpath(path, cwd)
    return rel if not rel.startswith("..") else path


def suggest(path, want="any", limit=5):
    """回傳一句「相近的路徑：…」（找不到相近的回空字串）。want：any／dir／file。
    評測的對照組用 AGENT_ABLATE=path_suggest 關掉（平常不要設）。"""
    if "path_suggest" in os.environ.get("AGENT_ABLATE", ""):
        return ""
    try:
        target = os.path.abspath(os.path.expanduser(path))
    except (TypeError, ValueError):
        return ""
    missing, cur = [], target
    while not os.path.exists(cur):
        parent = os.path.dirname(cur)
        if parent == cur:
            return ""
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
    if not out:
        return ""
    return "相近的路徑：" + "、".join(out[:limit]) + "（確認拼字與大小寫；不確定時先用 list_dir 看目錄內容）"
