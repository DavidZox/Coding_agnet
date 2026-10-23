"""list_dir：列出本機某一層目錄（純 Python，不包 ls）。

數值交給腳本算、不交給模型數：標頭給「共 N 項（檔案／目錄各幾個）」，永遠附一行「最新修改」；--filter 只列名稱含關鍵字的
項目並在標頭給數量；--newest N 依修改時間新→舊只列前 N 項。舊版的 ls 旗標（-la、-h）照樣接受但忽略。
輸出分「## 目錄（N 項）」「## 檔案（N 項）」兩節，每行：權限、大小（bytes）、修改時間、名稱（目錄加 /；連結加 @ 並寫指向哪裡）。
最多列 200 行（/usr/bin 有 1,481 個檔案），截掉時說怎麼縮小。逾時 5 秒（掛載裝置無回應時）。
"""
import os
import shlex
import signal
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402

TIMEOUT_SECONDS = 5
DEFAULT_NEWEST = 5
MAX_ROWS = 200
USAGE = ("用法: scripts/ls_cmd.py [path] [--filter 關鍵字] [--newest [N]]\n"
         "  path 預設目前工作目錄（可用 ~）；--filter 只列名稱含關鍵字的項目（不分大小寫）並在標頭計數；"
         f"--newest 依修改時間新→舊只列前 N 項（預設 {DEFAULT_NEWEST}）。最多列 {MAX_ROWS} 行。")


def parse_args(argv):
    """回傳 (path, keyword, newest, error)。argv 可以是 list 或整串字串。"""
    if isinstance(argv, str):
        argv = shlex.split(argv)
    keyword, newest, paths = None, None, []
    args = [a for a in argv if a != ""]   # 空字串參數（模型常寫 `. ""`）直接忽略
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--filter":
            if i + 1 >= len(args):
                return None, None, None, f"[ERROR] --filter 後面需要關鍵字。\n{USAGE}"
            keyword = args[i + 1].strip("*")   # 模型常寫成 glob（*.md）：--filter 是子字串比對，去掉星號即可
            i += 2
            continue
        if a == "--newest":
            newest = DEFAULT_NEWEST
            if i + 1 < len(args) and args[i + 1].isdigit():
                newest = max(1, int(args[i + 1]))
                i += 1
            i += 1
            continue
        if a.startswith("--"):
            return None, None, None, f"[ERROR] 不認識的選項 {a}。下一步：照下面的用法改。\n{USAGE}"
        if a.startswith("-") and len(a) > 1:
            i += 1          # 舊版 ls 旗標（-la、-h 等）：忽略
            continue
        paths.append(a)
        i += 1
    if len(paths) > 1:
        joined = pc.join_if_exists(paths)
        if joined is None:
            return None, None, None, (f"[ERROR] 一次只能列一個目錄（收到 {len(paths)} 個：{'、'.join(paths)}）。"
                                      f"下一步：分開執行，一次一個路徑；路徑含空白請用引號包住。\n{USAGE}")
        paths = [joined]
    return (paths[0] if paths else "."), keyword, newest, None


def scan(path):
    """回傳 (項目清單, 讀不到資訊的數量)。連結依指向的種類歸類（指向目錄的連結算目錄）。"""
    entries, unreadable = [], 0
    with os.scandir(path) as it:
        for e in it:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                unreadable += 1
                continue
            is_link = stat.S_ISLNK(st.st_mode)
            target, broken = None, False
            if is_link:
                try:
                    target = os.readlink(e.path)
                except OSError:
                    target = "?"
                broken = not os.path.exists(e.path)
            try:
                is_dir = e.is_dir(follow_symlinks=True)
            except OSError:
                is_dir = False
            entries.append({"name": e.name, "is_dir": is_dir, "is_link": is_link, "target": target, "broken": broken,
                            "size": st.st_size, "mtime": st.st_mtime, "mode": stat.filemode(st.st_mode)})
    return entries, unreadable


def _display_name(e):
    if e["is_link"]:
        return f"{e['name']}@ → {e['target']}" + ("/" if e["is_dir"] else "") + ("（連結失效）" if e["broken"] else "")
    return e["name"] + ("/" if e["is_dir"] else "")


def _short_name(e):
    return e["name"] + ("/" if e["is_dir"] else "@" if e["is_link"] else "")


def newest_line(entries):
    """「最新修改：A（時間）；其次：B（時間）、C（時間）」——以列出的項目為範圍，優先只算檔案，沒有檔案才算目錄。"""
    files = [e for e in entries if not e["is_dir"]] or list(entries)
    return pc.newest_line([(_short_name(e), e["mtime"]) for e in files])


def _row(e):
    return f"{e['mode']} {e['size']:>10} {pc.fmt_time(e['mtime'])} {_display_name(e)}"


def render(path, entries, keyword=None, newest=None, unreadable=0):
    total = len(entries)
    n_dirs = sum(1 for e in entries if e["is_dir"])
    n_links = sum(1 for e in entries if e["is_link"])
    head = (f"[PASS] 目錄列表 ({path})：共 {total} 項（{total - n_dirs} 個檔案、{n_dirs} 個目錄"
            + (f"，其中 {n_links} 個是連結" if n_links else "") + "）")
    shown = entries
    if keyword:
        kw = keyword.lower()
        shown = [e for e in entries if kw in e["name"].lower()]
        head += f"；名稱含「{keyword}」的 {len(shown)} 項"
    tail = []
    if unreadable:
        tail.append(f"（另有 {unreadable} 項讀不到資訊，沒有列出）")
    if not shown:
        # 實測模型會用 list_dir --filter 在根目錄數「專案裡」的檔案，0 項就回報 0：明說這裡只看一層、指路 find_file
        return "\n".join([head, (f"（{path} 這一層沒有名稱含「{keyword}」的項目。注意：list_dir 不看子目錄，如果使用者問的是整個專案或所有子目錄，"
                                 f"這個 0 不能當答案，請改用 scripts/find_file_cmd.py {keyword} {path} 遞迴搜尋後再回答）"
                                 if keyword else "（空目錄）")] + tail)
    lines = []
    nl = newest_line(shown)
    if newest:
        ranked = sorted(shown, key=lambda e: e["mtime"], reverse=True)[:min(newest, MAX_ROWS)]
        head += f"；依修改時間新→舊只列前 {len(ranked)} 項"
        lines.append(f"## 依修改時間新→舊（{len(ranked)} 項）")
        lines += [_row(e) for e in ranked]
    else:
        dirs = sorted((e for e in shown if e["is_dir"]), key=lambda e: e["name"].lower())
        files = sorted((e for e in shown if not e["is_dir"]), key=lambda e: e["name"].lower())
        budget = MAX_ROWS
        cut = False
        for title, group in (("目錄", dirs), ("檔案", files)):
            if not group:
                continue
            take = group[:max(0, budget)]
            budget -= len(take)
            if len(take) < len(group):
                cut = True
            lines.append(f"## {title}（{len(group)} 項" + (f"，只列前 {len(take)} 項" if len(take) < len(group) else "") + "）")
            lines += [_row(e) for e in take]
        if cut:
            head += f"；只列前 {MAX_ROWS} 行（目錄在前，依名稱排序）"
            tail.append("（要看其他的：--filter 關鍵字 只列名稱含關鍵字的、--newest N 只列最新修改的 N 項，或改列子目錄）")
    return "\n".join([head] + ([nl] if nl else []) + lines + tail)


def _timeout_handler(signum, frame):
    raise TimeoutError


def execute(argv):
    path, keyword, newest, err = parse_args(argv)
    if err:
        return err
    abs_path, err = pc.resolve(path, "dir", file_hint=f"看檔案內容請用 view_file {path}")
    if err:
        return err
    shown_path = path if not path.startswith(("~", "$")) else abs_path
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(TIMEOUT_SECONDS)
    try:
        entries, unreadable = scan(abs_path)
    except TimeoutError:
        return (f"[ERROR] 目錄列表逾時（超過 {TIMEOUT_SECONDS} 秒）：目錄可能非常大，或在無回應的網路／掛載裝置上。"
                f"下一步：改列較小的子目錄，或用 find_file 依名稱找。")
    except PermissionError:
        return f"[ERROR] 沒有權限讀取目錄 {path}。下一步：改用有權限的目錄；一定要看這裡的內容就請使用者自己處理權限（技能不會用 sudo）。"
    except OSError as e:
        return f"[ERROR] 無法讀取目錄 {path}：{e}。下一步：確認路徑與裝置狀態，或改列別的目錄。"
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
    return render(shown_path, entries, keyword, newest, unreadable)


if __name__ == "__main__":
    try:
        print(execute(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] list_dir 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
