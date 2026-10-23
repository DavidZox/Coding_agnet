"""view_file：看本機文字檔的內容，每行前面是行號（`  120→內容`，跟 result_view／result_grep 同一套寫法）。

預設從第 1 行列到最後，最多 2000 行、60000 字（再多交給提煉也讀不完）；截掉時第一行就寫「看後面用 --from N」。
--from N --lines M 看中間一段（code_ast_reader 給的「行 120-180」、search_text 給的行號可以直接接著看），--tail N 看最後 N 行（log）。
大檔案逐行讀、不整份載入（以前超過 1MB 就拒絕）；二進位檔（有 NUL 位元組）不印亂碼，回 [ERROR] 並指向該用的技能。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402
from _results_common import numbered  # noqa: E402

MAX_LINES = 2000
MAX_CHARS = 60000
LINE_CHARS = 2000            # 單行超過就截斷（minified JSON）
READ_LINE_BYTES = 1 << 20    # 一行最多讀進記憶體 1MB
COUNT_BUDGET_SECONDS = 10    # 算總行數的時間上限（好幾 GB 的檔案）
USAGE = ("用法: scripts/cat_cmd.py <檔案> [--from N] [--lines M] | [--tail N]\n"
         f"  預設從第 1 行列到最後（最多 {MAX_LINES} 行、{MAX_CHARS} 字）；--from N 從第 N 行開始、--lines M 列 M 行（上限 {MAX_LINES}）；"
         "--tail N 只看最後 N 行。\n  每行開頭的「行號→」是顯示用的，不是檔案的內容。")
_BINARY_HINTS = [
    ((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"), "影像檔：用 image_inspect 看內容"),
    ((".mcap", ".db3", ".bag"), "ROS 2 bag：Topic 與數據用 mcap_analyzer／mcap_feature_measure，Log 用 rosout_parser"),
    ((".pdf",), "PDF：沒有讀 PDF 的技能，請使用者轉成文字檔，或用 host_runcmd 的 pdftotext（有安裝的話）"),
    ((".zip", ".tar", ".gz", ".tgz", ".xz", ".bz2", ".7z", ".zst"), "壓縮檔：用 host_runcmd 看清單（tar -tf、unzip -l），解開後再看裡面的文字檔"),
    ((".xlsx", ".xls", ".docx", ".pptx"), "Office 檔：請使用者另存成 CSV／文字檔（表格用 csv_query）"),
    ((".sqlite", ".sqlite3", ".db"), "資料庫檔：用 host_runcmd 的 sqlite3（有安裝的話）查詢"),
    ((".pyc", ".so", ".o", ".a", ".bin", ".exe", ".pt", ".onnx", ".engine"), "編譯過的二進位檔：看原始碼或文件"),
]


def parse_args(argv):
    o = {"path": None, "from": None, "lines": None, "tail": None}
    pos, i = [], 0
    args = [a for a in argv if a != ""]
    while i < len(args):
        a = args[i]
        key = {"--from": "from", "--lines": "lines", "--head": "lines", "--tail": "tail"}.get(a)
        if a == "-n" and i + 1 < len(args) and args[i + 1].isdigit() and len(args) > 2:
            key = "lines"                       # head -n 50 的習慣
        if key:
            if i + 1 >= len(args) or not args[i + 1].isdigit() or int(args[i + 1]) < 1:
                return None, f"[ERROR] {a} 後面要是正整數（行號或行數）。\n{USAGE}"
            o[key] = int(args[i + 1])
            i += 2
            continue
        if a in ("-n", "--number", "-A", "-v"):   # cat -n：本來就有行號
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            return None, f"[ERROR] 不認識的選項 {a}。下一步：照下面的用法改。\n{USAGE}"
        pos.append(a)
        i += 1
    if not pos:
        return None, f"[ERROR] 沒有給要看的檔案。下一步：給檔案路徑，例如 scripts/cat_cmd.py config.yaml。\n{USAGE}"
    if len(pos) > 1:
        joined = pc.join_if_exists(pos)
        if joined is None:
            return None, (f"[ERROR] 一次只能看一個檔案（收到 {len(pos)} 個：{'、'.join(pos)}）。下一步：分開執行；"
                          f"路徑含空白請用引號包住。\n{USAGE}")
        pos = [joined]
    if o["tail"] and (o["from"] or o["lines"]):
        return None, f"[ERROR] --tail 不能跟 --from／--lines 一起用。下一步：看最後幾行用 --tail N，看中間一段用 --from N --lines M。\n{USAGE}"
    o["path"] = pos[0]
    return o, None


def _binary_hint(path):
    low = path.lower()
    for exts, hint in _BINARY_HINTS:
        if low.endswith(exts):
            return hint
    return "如果是某種程式的資料檔，請使用者說明用什麼工具開"


def _iter_lines(f):
    """二進位逐行讀：(這一行的開頭 bytes, 這一行是否太長被截斷, 這一行實際的 bytes 數)。"""
    while True:
        raw = f.readline(READ_LINE_BYTES)
        if not raw:
            return
        if raw.endswith(b"\n") or len(raw) < READ_LINE_BYTES:
            yield raw, False, len(raw)
            continue
        size = len(raw)
        while True:                              # 太長的一行：剩下的只算長度
            more = f.readline(READ_LINE_BYTES)
            size += len(more)
            if not more or more.endswith(b"\n"):
                break
        yield raw, True, size


def _decode(raw, enc):
    text = raw.decode(enc, errors="replace")
    return text.rstrip("\n").rstrip("\r")


def _count_rest(f, t0):
    """從目前位置往後還有幾行（最後一行沒有換行也算）；超過時間上限回 None。"""
    n, last = 0, b"\n"
    while True:
        block = f.read(1 << 20)
        if not block:
            return n + (0 if last == b"\n" else 1)
        n += block.count(b"\n")
        last = block[-1:]
        if time.monotonic() - t0 > COUNT_BUDGET_SECONDS:
            return None


def _tail(path, n, enc):
    """最後 n 行：從檔尾往回讀。回傳 (行的 list, 總行數或 None)。"""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        pos, buf = size, b""
        while pos > 0 and buf.count(b"\n") <= n:
            step = min(1 << 16, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
            if len(buf) > 64 * 1024 * 1024:
                break
        lines = buf.split(b"\n")
        if lines and lines[-1] == b"":
            lines.pop()
        lines = lines[-n:]
        f.seek(0)
        total = _count_rest(f, time.monotonic())
    return [_decode(x, enc) for x in lines], total


def execute(argv):
    o, err = parse_args(argv)
    if err:
        return err
    path = o["path"]
    abs_path, err = pc.resolve(path, "file", dir_hint=f"看目錄內容用 list_dir {path}；找檔名用 find_file <關鍵字> {path}")
    if err:
        return err
    if not os.path.isfile(abs_path):
        return (f"[ERROR] {path} 不是一般檔案（裝置、socket 或 FIFO），讀取可能永遠等不到結束，已拒絕。"
                f"下一步：確認路徑；要看裝置或程序的狀態請用 host_runcmd 的對應指令。")
    shown = path if not path.startswith(("~", "$")) else abs_path
    size = os.path.getsize(abs_path)
    if size == 0:
        return f"[PASS] 檔案內容 ({shown})：空檔案（0 bytes）"
    with open(abs_path, "rb") as f:
        head = f.read(8192)
    enc = "utf-8"
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        enc = "utf-16"
    elif head.startswith(b"\xef\xbb\xbf"):
        enc = "utf-8-sig"
    elif b"\0" in head:
        return (f"[ERROR] {shown} 是二進位檔（{size} bytes，含 NUL 位元組），view_file 只讀文字檔。下一步：{_binary_hint(abs_path)}。")
    if enc == "utf-16":
        return _render_utf16(o, abs_path, shown)
    if o["tail"]:
        lines, total = _tail(abs_path, o["tail"], enc)
        if total is None:
            return (f"[ERROR] {shown} 太大（{size} bytes），{COUNT_BUDGET_SECONDS} 秒內算不完行數。"
                    f"下一步：用 search_text 找關鍵字，或用 --from N --lines M 看開頭的部分。")
        start = total - len(lines) + 1
        return _render(shown, lines, start, total, size, cut_reason=None, clipped=_clip_all(lines), tail=True)
    start = o["from"] or 1
    asked = o["lines"]
    limit = min(asked or MAX_LINES, MAX_LINES)
    out, chars, consumed, clipped, stop = [], 0, 0, False, None
    t0 = time.monotonic()
    with open(abs_path, "rb") as f:
        for raw, too_long, real in _iter_lines(f):
            consumed += 1
            if consumed < start:
                continue
            text = _decode(raw, enc)
            if too_long or len(text) > LINE_CHARS:
                full = f"{real} bytes" if too_long else f"{len(text)} 字"
                text = text[:LINE_CHARS] + f"…（這一行共 {full}，截斷）"
                clipped = True
            if out and chars + len(text) > MAX_CHARS:
                stop = "chars"                   # 這一行讀了但沒有顯示
                break
            out.append(text)
            chars += len(text) + 1
            if len(out) >= limit:
                stop = "lines"
                break
        if consumed < start:
            return f"[ERROR] {shown} 只有 {consumed} 行，--from {start} 超過了。下一步：--from 1～{consumed}；看最後幾行用 --tail 50。"
        rest = _count_rest(f, t0)
    total = None if rest is None else consumed + rest
    end = start + len(out) - 1
    cut_reason = None
    if stop == "chars":
        cut_reason = f"{MAX_CHARS} 字"
    elif stop == "lines" and (asked is None or asked > MAX_LINES) and (total is None or end < total):
        cut_reason = f"{MAX_LINES} 行"
    return _render(shown, out, start, total, size, cut_reason, clipped, tail=False)


def _clip_all(lines):
    clipped = False
    for k, t in enumerate(lines):
        if len(t) > LINE_CHARS:
            lines[k] = t[:LINE_CHARS] + f"…（這一行共 {len(t)} 字，截斷）"
            clipped = True
    return clipped


def _render(shown, lines, start, total, size, cut_reason, clipped, tail):
    end = start + len(lines) - 1
    tot = f"共 {total} 行" if total is not None else f"{size} bytes（總行數太多沒有算完）"
    head = f"[PASS] 檔案內容 ({shown})：{tot}，顯示第 {start}-{end} 行" if lines else f"[PASS] 檔案內容 ({shown})：{tot}"
    more = total is None or end < total
    if cut_reason:
        head += f"（上限 {cut_reason}）"
    if more and not tail:
        head += f"；看後面用 --from {end + 1}"
    if tail and start > 1:
        head += f"；前面的用 --from 1 或 --from <行號> 看"
    if clipped:
        head += f"；單行超過 {LINE_CHARS} 字截斷"
    body = [numbered(start + k, t) for k, t in enumerate(lines)]
    foot = []
    if more and not tail:
        left = f"還有 {total - end} 行" if total is not None else "後面還有"
        foot.append(f"（{left}沒有顯示：用 --from {end + 1} 接著看，或用 search_text \"<關鍵字>\" {shown} 找特定的行）")
    return "\n".join([head] + body + foot)


def _render_utf16(o, abs_path, shown):
    size = os.path.getsize(abs_path)
    if size > 50 * 1024 * 1024:
        return f"[ERROR] {shown} 是 UTF-16 編碼、{size} bytes，太大。下一步：請使用者轉成 UTF-8，或用 search_text 找關鍵字。"
    with open(abs_path, encoding="utf-16", errors="replace") as f:
        all_lines = f.read().splitlines()
    total = len(all_lines)
    if o["tail"]:
        lines = all_lines[-o["tail"]:]
        start = total - len(lines) + 1
        return _render(shown, lines, start, total, size, None, _clip_all(lines), tail=True)
    start = o["from"] or 1
    if start > total:
        return f"[ERROR] {shown} 只有 {total} 行，--from {start} 超過了。下一步：--from 1～{total}；看最後幾行用 --tail 50。"
    limit = min(o["lines"] or MAX_LINES, MAX_LINES)
    lines = all_lines[start - 1:start - 1 + limit]
    cut = f"{MAX_LINES} 行" if o["lines"] is None and start - 1 + limit < total else None
    return _render(shown, lines, start, total, size, cut, _clip_all(lines), tail=False)


if __name__ == "__main__":
    try:
        print(execute(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] view_file 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
