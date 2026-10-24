"""file_ops：在本機做文件與目錄操作——建目錄、複製、移動、寫入／附加文字檔、取代檔案裡的一段文字。

會改變檔案，所以執行前一律由 harness 請使用者確認（config.GUARDED_SKILLS）。為了可以還原：覆寫、附加、取代之前，原本的檔案先備份到
harness 的 logs/file_backups/<時間>/（不在使用者的目錄留下 .bak）；移動不會毀掉任何東西（目的已存在就不做），不備份（以前會先把
整個來源複製一份，bag 資料夾要多佔一倍空間、可能超過 600 秒）。不提供刪除：要刪檔請使用者自己決定。

路徑相對於目前的工作目錄（change_dir 切換的）；不能寫到系統目錄（/etc、/usr、/bin…）。

內容的參數（--text、--old、--new）從 action.args 的原文（環境變數 HARNESS_RAW_ARGS）解析，順序不拘、內容裡有引號也沒關係：
值用引號包住時，取到「後面接著另一個選項、檔案路徑或結尾」的那個引號為止；沒有引號時取到下一個選項為止。
以前的解析 --new 一律取到字串結尾：`--new "a" --old "b"` 會把 `a" --old "b` 寫進檔案（2026-10 稽核：資料毀損）；
`write --text "hello" notes.md` 建出名為 --text 的檔案。跳脫：\\n 換行、\\t tab、\\" 引號、\\\\ 反斜線（字面的 \\n 寫成 \\\\n）；
內容裡已經有真正的換行時，只把 \\" 換成 "，其他照原樣寫入（那是程式碼裡的 \\n）。
"""
import datetime
import os
import re
import shlex
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402

USAGE = ("用法: scripts/file_ops_cmd.py <動作> …\n"
         "  mkdir <目錄>                         建立目錄（含上層）\n"
         "  copy <來源> <目的>                   複製檔案或整個目錄（目的已存在的檔案不覆蓋）\n"
         "  move <來源> <目的>                   移動或改名（目的是既有目錄時放進去；目的已存在不覆蓋）\n"
         "  write <檔案> --text \"內容\"           建立或覆寫文字檔（\\n 換行、\\t tab、\\\" 引號、\\\\ 反斜線）\n"
         "  append <檔案> --text \"內容\"          在文字檔最後加上內容\n"
         "  replace <檔案> --old \"原文\" --new \"新的內容\"   取代檔案裡的一段文字（原文要剛好出現一次）\n"
         "  set <檔案> <設定名稱> <新的值> [--after \"那一段開頭的字\"]   改設定檔（YAML 的「名稱: 值」）裡一個設定的值，只改那一行、\n"
         "                                       縮排與註解保留；給 --after 時只在含這幾個字的那一行開始的那一段裡找（例如 --after \"id: tb4\"）")
_FORBIDDEN_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/dev", "/proc", "/sys", "/var/lib", "/opt/ros")
_ACTIONS = ("mkdir", "copy", "move", "write", "append", "replace", "set")
_OPTIONS = ("--text", "--old", "--new", "--after")
_IGNORED_FLAGS = {"mkdir": {"-p", "--parents"}, "copy": {"-r", "-R", "-a", "--recursive"}, "move": set(), "write": set(),
                  "append": set(), "replace": set(), "set": set()}
MAX_EDIT_BYTES = 20 * 1024 * 1024
_OPT_RE = re.compile(r"(?:(?<=\s)|^)(--text|--old|--new|--after)(?==|\s|$)")
_AFTER_VALUE_RE = re.compile(r"^(\s*$|\s+(--text|--old|--new|--after)(=|\s|$)|\s+[^\s\"']+(\s+[^\s\"']+)*\s*$"
                             r"|\s+[^\s\"']+(\s+[^\s\"']+)*\s+(--text|--old|--new|--after)(=|\s|$))")
_NUMBERED_RE = re.compile(r"^\s*\d+→")


def backup_root():
    return pc.harness_logs_dir("file_backups")


def decode_escapes(text, quote='"'):
    """\\n → 換行、\\t → tab、\\" → "、\\\\ → \\（一次掃過，\\\\n 是字面的 \\n）。內容裡已經有真正的換行時只換 \\"（其他是程式碼裡的跳脫）。"""
    if "\n" in text:
        return text.replace("\\" + quote, quote) if quote else text
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt == "r" and text[i + 2:i + 4] == "\\n":
                out.append("\n")
                i += 4
                continue
            elif nxt in "\\\"'":
                out.append(nxt)
            else:
                out.append(c + nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _escaped(raw, j):
    k, n = j - 1, 0
    while k >= 0 and raw[k] == "\\":
        n += 1
        k -= 1
    return n % 2 == 1


def _value_at(raw, i):
    """raw[i:] 是一個選項的值 → (值（已處理跳脫）, 值結束的位置)。"""
    if i < len(raw) and raw[i] == "=":
        i += 1
    while i < len(raw) and raw[i] in " \t":
        i += 1
    if i < len(raw) and raw[i] in "\"'":
        q = raw[i]
        j = i + 1
        while True:
            j = raw.find(q, j)
            if j < 0:
                break
            if not _escaped(raw, j) and _AFTER_VALUE_RE.match(raw[j + 1:]):
                return decode_escapes(raw[i + 1:j], q), j + 1
            j += 1
        # 引號不成對：取到下一個選項為止，去掉開頭的引號
        m = _OPT_RE.search(raw, i + 1)
        end = m.start() if m else len(raw)
        return decode_escapes(raw[i + 1:end].rstrip().rstrip(q), q), end
    m = _OPT_RE.search(raw, i)
    end = m.start() if m else len(raw)
    return decode_escapes(raw[i:end].strip(), None), end


def parse_raw(raw):
    """原文 → (位置參數, {選項: 值}, 錯誤)。"""
    opts, rest, pos = {}, [], 0
    while True:
        m = _OPT_RE.search(raw, pos)
        if not m:
            rest.append(raw[pos:])
            break
        rest.append(raw[pos:m.start()])
        name = m.group(1)
        if name in opts:
            return None, None, f"[ERROR] {name} 出現了兩次。下一步：每個選項只給一次（內容裡要寫 {name} 這幾個字時，整段內容用引號包住）。"
        opts[name], pos = _value_at(raw, m.end())
    text = " ".join(rest)
    try:
        positional = shlex.split(text)
    except ValueError:
        positional = [t.strip("\"'") for t in text.split()]
    return positional, opts, None


def parse_argv(argv):
    """沒有原文時（直接執行腳本）：選項的值是下一個參數。"""
    positional, opts, i = [], {}, 0
    while i < len(argv):
        a = argv[i]
        name, eq, val = a.partition("=")
        if name in _OPTIONS:
            if eq:
                opts[name] = decode_escapes(val)
                i += 1
            else:
                opts[name] = decode_escapes(argv[i + 1]) if i + 1 < len(argv) else ""
                i += 2
            continue
        positional.append(a)
        i += 1
    return positional, opts, None


def _first_word(raw):
    s = raw.strip()
    return s.split(None, 1)[0].strip("\"'") if s else ""


def _resolve(path):
    if path.startswith("-"):
        return None, (f"[ERROR] 「{path}」不是路徑（不認識的選項）。下一步：照用法寫，內容用 --text／--old／--new 給，"
                      f"路徑不要以 - 開頭。\n{USAGE}")
    p = os.path.abspath(pc.expand(path))
    if any(p == f or p.startswith(f + "/") for f in _FORBIDDEN_PREFIXES):
        return None, f"[ERROR] 不能在系統目錄操作：{p}。下一步：改寫到工作目錄底下或使用者的家目錄；系統設定請使用者自己改。"
    return p, None


def _backup(path):
    if not os.path.isfile(path):
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dst = os.path.join(backup_root(), stamp, path.lstrip("/"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(path, dst)
    return dst


def _rel(p):
    try:
        rel = os.path.relpath(p, os.getcwd())
    except ValueError:
        return p
    return rel if not rel.startswith("..") else p


def _perm_error(e, what):
    return (f"[ERROR] 沒有權限{what}：{e.filename or ''}（{e.strerror}）。下一步：改用有權限的路徑（例如工作目錄底下）；"
            f"一定要改這裡就請使用者自己處理權限（技能不會用 sudo）。")


def _read_text(path, what):
    """讀 UTF-8 文字檔（保留 \\r\\n）→ (內容, 錯誤)。"""
    size = os.path.getsize(path)
    if size > MAX_EDIT_BYTES:
        return None, f"[ERROR] {_rel(path)} 太大（{size} bytes，上限 {MAX_EDIT_BYTES}），file_ops 不{what}這麼大的檔案。下一步：請使用者自己處理。"
    with open(path, "rb") as f:
        data = f.read()
    if b"\0" in data[:8192]:
        return None, f"[ERROR] {_rel(path)} 是二進位檔，file_ops 只{what}文字檔。下一步：確認路徑；二進位檔請使用者自己處理。"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError as e:
        line = data[:e.start].count(b"\n") + 1
        return None, (f"[ERROR] {_rel(path)} 不是 UTF-8 文字檔（第 {line} 行附近有無法解碼的位元組），"
                      f"file_ops 只{what} UTF-8 的文字檔。下一步：請使用者確認檔案的編碼，或另存成 UTF-8 再改。")


def _numbered_check(name, text):
    lines = text.splitlines()
    if lines and sum(1 for ln in lines if _NUMBERED_RE.match(ln)) >= max(1, len(lines) // 2):
        return (f"[ERROR] {name} 的內容含有 view_file 顯示用的行號（像「  12→」），那不是檔案的內容。"
                f"下一步：去掉每一行開頭的「行號→」，只寫檔案裡實際的文字再執行。")
    return None


def _need_paths(action, positional, n):
    ignored = _IGNORED_FLAGS.get(action, set())
    paths = [p for p in positional[1:] if p not in ignored]
    flags = [p for p in paths if p.startswith("-") and len(p) > 1]
    if flags:
        return None, (f"[ERROR] {action} 不認識的選項 {'、'.join(flags)}（路徑不能以 - 開頭）。下一步：照下面的用法改；"
                      f"內容只用 --text／--old／--new 給。\n{USAGE}")
    if len(paths) < n:
        what = {"mkdir": "目錄路徑", "copy": "來源與目的", "move": "來源與目的"}.get(action, "檔案路徑")
        quote = ("（--text／--old／--new 的內容要用引號包住，沒有引號時會一直取到下一個選項，後面的路徑也被當成內容）"
                 if action in ("write", "append", "replace") else "")
        return None, f"[ERROR] {action} 需要{what}{quote}。下一步：照下面的用法補上。\n{USAGE}"
    if len(paths) > n:
        joined = pc.join_if_exists(paths) if n == 1 else None
        if joined:
            return [joined], None
        return None, (f"[ERROR] {action} 的路徑太多（收到 {'、'.join(paths)}）。下一步：路徑含空白請用引號包住；"
                      f"內容要用 --text／--old／--new 給。\n{USAGE}")
    return paths, None


def main(argv):
    raw = os.environ.get("HARNESS_RAW_ARGS") or ""
    if raw.strip() and argv and _first_word(raw) == argv[0]:
        positional, opts, err = parse_raw(raw)
    else:
        positional, opts, err = parse_argv(argv)
    if err:
        return err
    if not positional or positional[0] not in _ACTIONS:
        got = positional[0] if positional else "（沒有）"
        extra = "；file_ops 不提供刪除，要刪檔請使用者自己決定" if got in ("delete", "rm", "remove", "del") else ""
        return f"[ERROR] 第一個參數要是動作（{'／'.join(_ACTIONS)}），收到「{got}」{extra}。\n{USAGE}"
    action = positional[0]
    allowed = {"write": {"--text"}, "append": {"--text"}, "replace": {"--old", "--new"}, "set": {"--after"}}.get(action, set())
    stray = [o for o in opts if o not in allowed]
    if stray:
        return f"[ERROR] {action} 不用 {'、'.join(stray)}。下一步：照下面的用法改。\n{USAGE}"
    try:
        if action == "mkdir":
            return _mkdir(positional)
        if action in ("copy", "move"):
            return _copy_move(action, positional)
        if action == "set":
            return _set(positional, opts)
        return _edit(action, positional, opts)
    except PermissionError as e:
        return _perm_error(e, {"mkdir": "建立目錄", "copy": "複製", "move": "移動"}.get(action, "寫入檔案"))
    except OSError as e:
        return f"[ERROR] {action} 失敗：{e}。下一步：確認路徑與磁碟空間；看不出原因就把錯誤告訴使用者。"


def _mkdir(positional):
    paths, err = _need_paths("mkdir", positional, 1)
    if err:
        return err
    p, err = _resolve(paths[0])
    if err:
        return err
    if os.path.isfile(p):
        return f"[ERROR] {_rel(p)} 已經是一個檔案，不能建成目錄。下一步：換一個名稱，或用 list_dir {_rel(os.path.dirname(p)) or '.'} 確認。"
    existed = os.path.isdir(p)
    os.makedirs(p, exist_ok=True)
    return f"[PASS] {'目錄已經存在' if existed else '已建立目錄'}：{_rel(p)}"


def _copy_move(action, positional):
    paths, err = _need_paths(action, positional, 2)
    if err:
        return err
    src, err = _resolve(paths[0])
    if err:
        return err
    dst, err = _resolve(paths[1])
    if err:
        return err
    if not os.path.lexists(src):
        return pc.not_found(paths[0], "any", "來源")
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src.rstrip("/")))
    if os.path.lexists(dst):
        return f"[ERROR] 目的已經存在：{_rel(dst)}（不覆蓋）。下一步：換一個目的名稱；要覆蓋請先跟使用者確認、由使用者處理。"
    if os.path.isdir(src) and (dst + "/").startswith(src.rstrip("/") + "/"):
        return f"[ERROR] 不能把目錄 {_rel(src)} {('複製' if action == 'copy' else '移動')}到它自己裡面（{_rel(dst)}）。下一步：換一個目的。"
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    if action == "copy":
        if os.path.isdir(src):
            shutil.copytree(src, dst, symlinks=True)
            n = sum(len(fs) for _, _, fs in os.walk(dst))
        else:
            shutil.copy2(src, dst)
            n = 1
        return f"[PASS] 已複製 {_rel(src)} → {_rel(dst)}（{n} 個檔案）"
    shutil.move(src, dst)
    return f"[PASS] 已移動 {_rel(src)} → {_rel(dst)}（移動不會覆蓋任何東西，沒有另外備份）"


def _edit(action, positional, opts):
    paths, err = _need_paths(action, positional, 1)
    if err:
        return err
    path, err = _resolve(paths[0])
    if err:
        return err
    if os.path.isdir(path):
        return f"[ERROR] {_rel(path)} 是目錄，不是檔案。下一步：給目錄裡的檔案路徑。"
    if action in ("write", "append"):
        if "--text" not in opts:
            return f"[ERROR] {action} 需要 --text \"內容\"。下一步：照下面的用法補上。\n{USAGE}"
        text = opts["--text"]
        err = _numbered_check("--text", text)
        if err:
            return err
        old = ""
        if action == "append" and os.path.exists(path):
            old, err = _read_text(path, "附加")
            if err:
                return err
        bk = _backup(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        body = text if text.endswith("\n") else text + "\n"
        with open(path, "a" if action == "append" else "w", encoding="utf-8", newline="") as f:
            if action == "append" and old and not old.endswith("\n"):
                f.write("\n")
            f.write(body)
        n = body.count("\n")
        verb = "附加" if action == "append" else ("覆寫" if bk else "建立")
        return f"[PASS] 已{verb} {_rel(path)}（{n} 行）" + (f"；原本的檔案備份在 {bk}" if bk else "")
    # replace
    if "--old" not in opts or "--new" not in opts:
        return f"[ERROR] replace 需要 --old \"原文\" 與 --new \"新的內容\"。下一步：兩個都要給（--new \"\" 代表刪掉原文）。\n{USAGE}"
    old, new = opts["--old"], opts["--new"]
    if not old:
        return f"[ERROR] --old 是空的。下一步：照檔案的實際內容寫要被取代的那一段（先用 view_file 看）。\n{USAGE}"
    for name, val in (("--old", old), ("--new", new)):
        err = _numbered_check(name, val)
        if err:
            return err
    if not os.path.isfile(path):
        return pc.not_found(paths[0], "file", "檔案")
    content, err = _read_text(path, "修改")
    if err:
        return err
    if "\r\n" in content and "\n" in old and "\r\n" not in old:      # Windows 換行的檔案
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    if old == new:
        return f"[PASS] 沒有修改 {_rel(path)}：--old 與 --new 一樣。"
    n = content.count(old)
    if n != 1:
        if n == 0:
            key = old.strip().split(":")[0].strip() if ":" in old else old.strip()[:20]
            lines = [f"{i + 1}: {ln}" for i, ln in enumerate(content.splitlines()) if key and key in ln][:5]
            hint = ("\n檔案裡相關的行：\n" + "\n".join(lines)) if lines else ""
            return (f"[ERROR] {_rel(path)} 裡「{old[:80]}」出現 0 次（要剛好 1 次才取代）。下一步：用 view_file {_rel(path)} 看實際的內容，"
                    f"--old 照檔案裡的寫法（空白、引號、縮排都要一樣）{hint}")
        where, idx = [], -1
        while True:
            idx = content.find(old, idx + 1)
            if idx < 0:
                break
            where.append(content[:idx].count("\n") + 1)
        shown = "、".join(str(x) for x in where[:20]) + ("…" if len(where) > 20 else "")
        return (f"[ERROR] {_rel(path)} 裡「{old[:80]}」出現 {n} 次（第 {shown} 行），要剛好 1 次才取代。"
                f"下一步：--old 多帶前後文（例如連同上一行一起寫）讓它只對到要改的那一處。")
    bk = _backup(path)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content.replace(old, new, 1))
    line = content[:content.index(old)].count("\n") + 1
    return f"[PASS] 已修改 {_rel(path)} 第 {line} 行附近：「{old.strip()[:80]}」→「{new.strip()[:80]}」；原本的檔案備份在 {bk}"

def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _set(positional, opts):
    """set <檔案> <名稱> <值> [--after 錨點]：YAML 設定檔裡「名稱: 值」那一行換成新的值（縮排、清單的 -、行尾註解保留）。給 --after 時只在
    第一個含錨點的行開始的那一段裡找（之後縮排比它深的行；碰到縮排一樣或更淺的就是下一段）——同樣的設定出現在好幾台時不會改到別台；
    不給時名稱在檔案裡要剛好出現一次。找不到、出現好幾次都不改，回 [ERROR] 與下一步。"""
    args = positional[1:]
    if len(args) != 3:
        return (f"[ERROR] set 需要三個參數：檔案、設定名稱、新的值（收到 {len(args)} 個：{'、'.join(args) or '沒有'}）。下一步：值有空白就用引號包住，"
                f"例如 set configs/robots.yaml battery_low 18 --after \"id: tb4\"。\n{USAGE}")
    path_arg, key, value = args
    path, err = _resolve(path_arg)
    if err:
        return err
    if not os.path.isfile(path):
        return pc.not_found(path_arg, "file", "檔案")
    content, err = _read_text(path, "修改")
    if err:
        return err
    lines = content.split("\n")
    start, end, anchor = 0, len(lines), opts.get("--after", "").strip()
    where = "檔案"
    if anchor:
        idx = next((i for i, ln in enumerate(lines) if anchor in ln), None)
        if idx is None:
            last = anchor.split()[-1]
            near = [f"{i + 1}: {ln.strip()}" for i, ln in enumerate(lines) if last and last in ln][:5]
            return (f"[ERROR] {_rel(path)} 裡沒有含「{anchor}」的行，沒有修改。下一步：用 view_file {_rel(path)} 看那一段開頭實際的寫法"
                    + ("；相關的行：" + "；".join(near) if near else "") + "。")
        ind = _indent(lines[idx])
        end = next((j for j in range(idx + 1, len(lines)) if lines[j].strip() and _indent(lines[j]) <= ind), len(lines))
        start, where = idx, f"「{anchor}」那一段（第 {idx + 1}～{end} 行）"
    pat = re.compile(rf"^(?P<pre>\s*(?:-\s+)?){re.escape(key)}(?P<sep>\s*:\s*)(?P<val>.*?)(?P<post>\s+#.*)?(?P<cr>\r?)$")
    hits = [i for i in range(start, end) if pat.match(lines[i])]
    if not hits:
        near = [f"{i + 1}: {lines[i].strip()}" for i in range(start, end) if key.split("_")[0] in lines[i]][:5]
        return (f"[ERROR] {where}找不到「{key}: …」這一行，沒有修改。下一步：用 view_file {_rel(path)} 確認設定的名稱"
                + ("；相關的行：" + "；".join(near) if near else "") + (f"；不在那一段的話換 --after" if anchor else "") + "。")
    if len(hits) > 1:
        shown = "、".join(str(i + 1) for i in hits[:20])
        return (f"[ERROR] {where}有 {len(hits)} 行「{key}: …」（第 {shown} 行），沒有修改。下一步：加 --after \"<那一段開頭的字>\""
                f"（例如那一台的 id 那一行）只在那一段裡找。")
    i = hits[0]
    m = pat.match(lines[i])
    if m.group("val").strip() == value.strip():
        return f"[PASS] 沒有修改 {_rel(path)}：第 {i + 1} 行已經是「{lines[i].strip()}」。"
    old_line = lines[i]
    lines[i] = f"{m.group('pre')}{key}{m.group('sep')}{value}{m.group('post') or ''}{m.group('cr')}"
    bk = _backup(path)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))
    return (f"[PASS] 已修改 {_rel(path)} 第 {i + 1} 行" + (f"（在「{anchor}」那一段）" if anchor else "") + f"：「{old_line.strip()}」→「{lines[i].strip()}」"
            f"；原本的檔案備份在 {bk}")

if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] file_ops 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
