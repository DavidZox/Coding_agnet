"""file_ops：在本機做文件與目錄操作——建目錄、複製、移動、寫入／附加文字檔、取代檔案裡的一段文字。

會改變檔案，所以執行前一律由 harness 請使用者確認（config.GUARDED_SKILLS）。為了可以還原：覆寫、附加、取代、移動之前，
原本的檔案先備份到 harness 的 logs/file_backups/<時間>/（不在使用者的目錄留下 .bak）。不提供刪除：要刪檔請使用者自己決定。

路徑相對於目前的工作目錄（change_dir 切換的）；不能寫到系統目錄（/etc、/usr、/bin…）。
write／append 的內容用 --text 給（\\n 代表換行）；內容裡有引號也沒關係——腳本讀的是 action.args 的原文（HARNESS_RAW_ARGS）。
"""
import datetime
import os
import re
import shutil
import sys

USAGE = ("用法: scripts/file_ops_cmd.py <動作> …\n"
         "  mkdir <目錄>                         建立目錄（含上層）\n"
         "  copy <來源> <目的>                   複製檔案或整個目錄（目的已存在的檔案不覆蓋）\n"
         "  move <來源> <目的>                   移動或改名（目的是既有目錄時放進去）\n"
         "  write <檔案> --text \"內容\"           建立或覆寫文字檔（\\n 代表換行）\n"
         "  append <檔案> --text \"內容\"          在文字檔最後加上內容\n"
         "  replace <檔案> --old \"原文\" --new \"新的內容\"   取代檔案裡的一段文字（原文要剛好出現一次）")
_FORBIDDEN_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/dev", "/proc", "/sys", "/var/lib", "/opt/ros")
_ACTIONS = ("mkdir", "copy", "move", "write", "append", "replace")
HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "logs", "file_backups")


def _decode(text):
    """模型常把換行寫成 \\n、tab 寫成 \\t（JSON 字串裡多跳脫了一層）。"""
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')


def _raw_option(raw, name, stop=()):
    """從原文取出 --name 後面的內容：去掉外層一對引號；遇到 stop 裡的下一個選項就結束。"""
    m = re.search(rf"(?:^|\s){re.escape(name)}(?:\s+|=)", raw)
    if not m:
        return None
    rest = raw[m.end():]
    end = len(rest)
    for opt in stop:
        k = re.search(rf"\s{re.escape(opt)}(?:\s+|=)", rest)
        if k:
            end = min(end, k.start())
    val = rest[:end].strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        val = val[1:-1]
    return val


def _resolve(path):
    p = os.path.abspath(os.path.expanduser(path))
    if any(p == f or p.startswith(f + "/") for f in _FORBIDDEN_PREFIXES):
        return None, f"[ERROR] 不能在系統目錄操作：{p}"
    return p, None


def _backup(path):
    if not os.path.exists(path):
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dst = os.path.join(BACKUP_ROOT, stamp, path.lstrip("/"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(path):
        shutil.copytree(path, dst)
    else:
        shutil.copy2(path, dst)
    return dst


def _rel(p):
    try:
        return os.path.relpath(p, os.getcwd())
    except ValueError:
        return p


def main(argv):
    raw = os.environ.get("HARNESS_RAW_ARGS") or ""
    if not argv or argv[0] not in _ACTIONS:
        return f"[ERROR] 第一個參數要是動作（{'／'.join(_ACTIONS)}）。\n{USAGE}"
    action = argv[0]
    if action == "mkdir":
        if len(argv) < 2:
            return f"[ERROR] mkdir 需要目錄路徑。\n{USAGE}"
        p, err = _resolve(argv[1])
        if err:
            return err
        existed = os.path.isdir(p)
        os.makedirs(p, exist_ok=True)
        return f"[PASS] {'目錄已經存在' if existed else '已建立目錄'}：{_rel(p)}"
    if action in ("copy", "move"):
        if len(argv) < 3:
            return f"[ERROR] {action} 需要來源與目的。\n{USAGE}"
        src, err = _resolve(argv[1])
        if err:
            return err
        dst, err = _resolve(argv[2])
        if err:
            return err
        if not os.path.exists(src):
            near = [f for f in os.listdir(os.path.dirname(src) or ".")
                    if os.path.basename(src).lower()[:4] in f.lower()][:5] if os.path.isdir(os.path.dirname(src) or ".") else []
            return f"[ERROR] 找不到來源：{_rel(src)}" + (f"（同一個目錄裡相近的：{'、'.join(near)}）" if near else "")
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src.rstrip("/")))
        if os.path.exists(dst) and action == "copy":
            return f"[ERROR] 目的已經存在：{_rel(dst)}（不覆蓋；要覆蓋請先跟使用者確認、改用別的名稱）"
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        if action == "copy":
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            n = sum(len(fs) for _, _, fs in os.walk(dst)) if os.path.isdir(dst) else 1
            return f"[PASS] 已複製 {_rel(src)} → {_rel(dst)}（{n} 個檔案）"
        if os.path.exists(dst):
            return f"[ERROR] 目的已經存在：{_rel(dst)}（不覆蓋）"
        bk = _backup(src)
        shutil.move(src, dst)
        return f"[PASS] 已移動 {_rel(src)} → {_rel(dst)}" + (f"（原本的位置備份在 {bk}）" if bk else "")
    if len(argv) < 2:
        return f"[ERROR] {action} 需要檔案路徑。\n{USAGE}"
    path, err = _resolve(argv[1])
    if err:
        return err
    if action in ("write", "append"):
        text = _raw_option(raw, "--text") if raw else None
        if text is None:
            if "--text" not in argv:
                return f"[ERROR] {action} 需要 --text \"內容\"。\n{USAGE}"
            text = argv[argv.index("--text") + 1] if argv.index("--text") + 1 < len(argv) else ""
        text = _decode(text)
        if action == "write" and os.path.isdir(path):
            return f"[ERROR] {_rel(path)} 是目錄，不是檔案。"
        bk = _backup(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a" if action == "append" else "w", encoding="utf-8") as f:
            if action == "append" and os.path.getsize(path) > 0 and not open(path, encoding="utf-8", errors="replace").read().endswith("\n"):
                f.write("\n")
            f.write(text if text.endswith("\n") else text + "\n")
        n = text.count("\n") + 1
        verb = "附加" if action == "append" else ("覆寫" if bk else "建立")
        return f"[PASS] 已{verb} {_rel(path)}（{n} 行）" + (f"；原本的檔案備份在 {bk}" if bk else "")
    if action == "replace":
        if not os.path.isfile(path):
            return f"[ERROR] 找不到檔案：{_rel(path)}"
        old = _raw_option(raw, "--old", stop=("--new",)) if raw else None
        new = _raw_option(raw, "--new") if raw else None
        if old is None or new is None:
            if "--old" not in argv or "--new" not in argv:
                return f"[ERROR] replace 需要 --old \"原文\" 與 --new \"新的內容\"。\n{USAGE}"
            old, new = argv[argv.index("--old") + 1], argv[argv.index("--new") + 1]
        old, new = _decode(old), _decode(new)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        n = content.count(old)
        if n != 1:
            hint = ""
            if n == 0:
                key = old.strip().split(":")[0].strip() if ":" in old else old.strip()[:20]
                lines = [f"{i + 1}: {ln}" for i, ln in enumerate(content.splitlines()) if key and key in ln][:5]
                hint = ("\n檔案裡相關的行：\n" + "\n".join(lines)) if lines else ""
            return f"[ERROR] {_rel(path)} 裡「{old[:80]}」出現 {n} 次（要剛好 1 次才取代；請照檔案的實際內容、加上前後文讓它唯一）{hint}"
        bk = _backup(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.replace(old, new, 1))
        line = content[:content.index(old)].count("\n") + 1
        return f"[PASS] 已修改 {_rel(path)} 第 {line} 行附近：「{old.strip()[:80]}」→「{new.strip()[:80]}」；原本的檔案備份在 {bk}"
    return f"[ERROR] 不認識的動作：{action}\n{USAGE}"


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] file_ops 未預期的例外：{e}")
