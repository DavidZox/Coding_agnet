"""find_file：依「名稱關鍵字」遞迴找檔案與目錄（包 GNU find），結果依路徑排序、依所在目錄分組，數量由腳本算好。

以前的問題（2026-10 稽核）：參數「是不是現存的目錄」決定誰是路徑——關鍵字剛好也是目錄名稱（launch .）就變成「缺少關鍵字」；
路徑不存在或寫 ~ 時被當成關鍵字、改搜 .，默默回 0 個；關鍵字含 / 時 -iname 永遠比不到；一個沒有權限的目錄讓 find exit 1，
找到的結果全部丟掉；逾時沒有下一步；結果不排序、沒有上限。

現在：第一個參數是關鍵字、第二個是路徑（只有「第一個明顯是路徑、第二個不是」時才對調並註明）；路徑不存在回 [ERROR] 與相近的路徑，
絕不改搜 .；關鍵字含 / 時比對整個路徑（-ipath）；含 * ? [ 時照萬用字元比對，否則是「名稱含關鍵字」；預設略過 build／install／log／.git
等目錄（--all-dirs 取消）；沒有權限的目錄略過並計數；逾時保留已經找到的部分。
"""
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402
from _shell_common import run_shell  # noqa: E402

TIMEOUT_SECONDS = 30
MAX_SHOWN = 200              # 最多列幾個
KEEP_LIMIT = 100000          # 最多保留幾個路徑來排序（超過的只計數）
NEWEST_STAT_LIMIT = 2000     # 結果超過這麼多個就不逐一 stat（避免拖慢），不給「最新修改」
BLOCKED = ("/", "/proc", "/sys", "/dev")
USAGE = ('用法: scripts/find_file_cmd.py "<名稱關鍵字>" [路徑] [--type f|d] [--all-dirs]\n'
         '  名稱關鍵字：名稱含這段文字（不分大小寫）；含 * ? 時照萬用字元比對（"*.launch.py"）；含 / 時比對整個路徑（"launch/nav"）。\n'
         '  路徑：從哪個目錄開始找（預設 .，可用 ~）；不能是 /。--type f 只找檔案、d 只找目錄；'
         '--all-dirs 連預設略過的 build、install、log、.git 等目錄也找。')


def _looks_like_path(a):
    return a in (".", "..") or a.startswith(("/", "./", "../", "~", "$HOME"))


def parse_args(argv):
    o = {"keyword": None, "path": None, "type": None, "all_dirs": False, "notes": []}
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--type", "-type"):
            if i + 1 >= len(argv) or argv[i + 1] not in ("f", "d"):
                return None, f"[ERROR] {a} 後面要是 f（只找檔案）或 d（只找目錄）。\n{USAGE}"
            o["type"] = argv[i + 1]
            i += 2
            continue
        if a.startswith("--type="):
            if a[7:] not in ("f", "d"):
                return None, f"[ERROR] --type 要是 f 或 d，收到「{a[7:]}」。\n{USAGE}"
            o["type"] = a[7:]
            i += 1
            continue
        if a == "--all-dirs":
            o["all_dirs"] = True
            i += 1
            continue
        if a in ("-name", "-iname", "--name"):          # find 的習慣：-name 後面是關鍵字
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            return None, f"[ERROR] 不支援的選項 {a}。下一步：照下面的用法改。\n{USAGE}"
        pos.append(a)
        i += 1
    if len(pos) == 3 and pos[0].lower() == "find":
        pos = pos[1:]
        o["notes"].append("第一個參數「find」是指令名稱，已略過")
    if not pos:
        return None, f"[ERROR] 缺少名稱關鍵字。下一步：寫成 \"<名稱關鍵字>\" [路徑]，例如 \"Modelfile\" .\n{USAGE}"
    if len(pos) > 2:
        joined = pc.join_if_exists(pos[1:])
        if joined is None:
            return None, (f"[ERROR] 參數太多（{'、'.join(pos)}）：只要「名稱關鍵字」與一個路徑。下一步：一次找一個關鍵字；"
                          f"含空白的關鍵字或路徑用引號包住。\n{USAGE}")
        pos = [pos[0], joined]
    if len(pos) == 1:
        if _looks_like_path(pos[0]) and os.path.isdir(pc.expand(pos[0])):
            return None, (f"[ERROR] 只給了路徑 {pos[0]}，缺少名稱關鍵字。下一步：寫成 \"<名稱關鍵字>\" {pos[0]}；"
                          f"要列出目錄內容或找最新修改的檔案請改用 list_dir（scripts/ls_cmd.py {pos[0]} --newest）。")
        o["keyword"], o["path"] = pos[0], "."
        o["notes"].append("沒有給路徑，從目前工作目錄 . 開始找")
        return o, None
    first, second = pos
    if _looks_like_path(first) and not _looks_like_path(second):
        first, second = second, first
        o["notes"].append(f"參數順序是「關鍵字 路徑」，已當成在 {second} 裡找「{first}」")
    o["keyword"], o["path"] = first, second
    return o, None


def _name_test(keyword):
    """→ (find 的比對參數, 說明)。"""
    has_glob = any(c in keyword for c in "*?[")
    if "/" in keyword:
        pat = keyword if has_glob else f"*{keyword.strip('/')}*"
        return ["-ipath", pat if pat.startswith("*") else f"*{pat}"], "路徑含"
    if has_glob:
        return ["-iname", keyword], "名稱符合"
    return ["-iname", f"*{keyword}*"], "名稱含"


def execute(argv):
    o, err = parse_args(argv)
    if err:
        return err
    root, perr = pc.resolve(o["path"], "dir", noun="搜尋的目錄",
                            file_hint=f"find_file 要從目錄開始找；看這個檔案的內容用 view_file {o['path']}")
    if perr:
        return perr
    if root in BLOCKED:
        return f"[ERROR] 不從 {root} 開始找（整個系統太大、會卡住）。下一步：指定具體的目錄，例如 . 、~ 或專案目錄。"
    shown_root = o["path"] if not o["path"].startswith(("~", "$")) else root
    excludes = pc.excludes_for([root], o["all_dirs"])
    test, how = _name_test(o["keyword"])
    cmd = ["find", shown_root]
    if excludes:
        cmd += ["(", "-type", "d", "("]
        for k, d in enumerate(excludes):
            cmd += (["-o"] if k else []) + ["-name", d]
        cmd += [")", ")", "-prune", "-o"]
    cmd += ["("] + test + (["-type", o["type"]] if o["type"] else []) + [")", "-print"]
    found, perm, other = [], [], []
    count = [0]

    def on_out(raw):
        p = raw.decode("utf-8", errors="replace")
        if os.path.abspath(p) == root:          # 起點自己符合時不算
            return
        count[0] += 1
        if len(found) < KEEP_LIMIT:
            found.append(p)

    def on_err(raw):
        line = raw.decode("utf-8", errors="replace")
        (perm if "Permission denied" in line else other).append(line)

    r = run_shell(cmd, TIMEOUT_SECONDS, on_stdout_line=on_out, on_stderr_line=on_err)
    if r.spawn_error:
        return f"[ERROR] find_file 沒辦法執行 find：{r.spawn_error}。下一步：請使用者確認系統有安裝 find（findutils）。"
    return render(o, root, shown_root, found, count[0], perm, other, r, how, excludes)


def _strip(p):
    return p[2:] if p.startswith("./") else p


def render(o, root, shown_root, found, total, perm, other, r, how, excludes):
    kw = f"「{o['keyword']}」"
    notes = list(o["notes"])
    if perm:
        notes.append(f"{len(perm)} 個目錄沒有權限（略過）")
    if other:
        notes.append(f"{len(other)} 個讀取錯誤（略過；第一個：{pc.clip(other[0], 160)}）")
    if excludes:
        notes.append(f"預設略過 {'／'.join(excludes[:4])} 等目錄（要一起找加 --all-dirs）")
    note_line = f"（{'；'.join(notes)}）" if notes else ""
    if r.timed_out and not found:
        return (f"[ERROR] 找{kw}逾時（{TIMEOUT_SECONDS} 秒內沒有找完，也還沒有找到任何一個；從 {shown_root} 開始）。"
                f"下一步：從比較小的子目錄開始找、或用更精確的關鍵字（例如加副檔名）。" + note_line)
    if not found:
        out = [f"[PASS] 找不到{how}{kw}的檔案或目錄（0 個，從 {shown_root} 開始找）"]
        hints = []
        if "/" not in o["keyword"] and "." in o["keyword"] and not any(c in o["keyword"] for c in "*?["):
            hints.append("關鍵字可以只寫名稱的一部分（例如去掉副檔名）")
        if excludes:
            hints.append("可能在預設略過的目錄裡：加 --all-dirs 再找")
        hints.append("要找檔案「內容」裡的文字請用 search_text")
        if note_line:
            out.append(note_line)
        out.append("（" + "；".join(hints) + "）")
        return "\n".join(out)
    items = []
    for p in found:
        try:
            st = os.lstat(p)
            is_dir = stat.S_ISDIR(st.st_mode)
        except OSError:
            st, is_dir = None, False
        items.append((_strip(p), is_dir, st))
    items.sort(key=lambda x: x[0])
    n_dirs = sum(1 for _, d, _ in items if d)
    counted = len(items)
    over = total - counted                    # 超過 KEEP_LIMIT 沒保留的
    kind = (f"{counted - n_dirs} 個檔案、{n_dirs} 個目錄" if not over
            else f"太多了，只保留先找到的 {counted} 個來排序，其中 {n_dirs} 個目錄")
    if r.timed_out:
        head = (f"[PASS] 找{kw}逾時（{TIMEOUT_SECONDS} 秒）沒有找完：目前找到 {total} 個（{kind}），不是全部"
                f"（從 {shown_root} 開始）；要完整的結果請從比較小的子目錄開始找")
    else:
        head = f"[PASS] 找到 {total} 個{how}{kw}的項目（{kind}；從 {shown_root} 開始找）"
    shown = items[:MAX_SHOWN]
    if total > len(shown):
        head += f"；只列前 {len(shown)} 個（依路徑排序）"
    lines = [head]
    if len(items) <= NEWEST_STAT_LIMIT:
        nl = pc.newest_line([(p, st.st_mtime) for p, d, st in items if st is not None and stat.S_ISREG(st.st_mode)])
        if nl:
            lines.append(nl)
    groups = {}
    for p, is_dir, _ in shown:
        d = os.path.dirname(p) or "."
        groups.setdefault(d, []).append(os.path.basename(p) + ("/" if is_dir else ""))
    for d in sorted(groups):
        names = groups[d]
        lines.append(f"## {d}（{len(names)} 項）")
        lines += [f"- {n}" for n in names]
    if total > len(shown):
        lines.append("（要縮小：用更精確的關鍵字（例如 \"*.launch.py\"）、從子目錄開始找、或 --type f 只找檔案）")
    if note_line:
        lines.append(note_line)
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        print(execute(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] find_file 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
