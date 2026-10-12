"""code_search：在整個專案的程式碼裡搜尋字串或正規表示式，結果依檔案分組、附行號與前後文。

跟 search_text（grep_cmd.py）的差別：自動略過 .git、__pycache__、node_modules、venv、build 等不是原始碼的目錄與二進位檔；
可以用 --glob 只搜某類檔案、--context 帶前後幾行、--word 只比對完整的識別字；大小寫採 smart case（關鍵字有大寫才區分大小寫）。
命中數與檔案數由腳本算好，直接引用。純 Python 實作，不依賴 grep／rg；逐行比對有時間預算（防災難性回溯）。
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc

DEFAULT_MAX_HITS = 80
MAX_OUTPUT_CHARS = 12000
TIME_BUDGET_SECONDS = 8.0
MAX_LINE_CHARS = 240
USAGE = ("用法: scripts/code_search_cmd.py \"<關鍵字或正規表示式>\" [路徑] [--glob \"*.py\"] [--context N] [--word] [--case] [--max N]\n"
         f"  路徑預設目前工作目錄（coding job 時是工作區）；--context 前後各帶 N 行（預設 0、上限 5）；--word 只比對完整識別字；"
         f"--case 區分大小寫（預設：關鍵字有大寫才區分）；--max 最多列幾處（預設 {DEFAULT_MAX_HITS}）。")


def parse_args(argv):
    opts = {"pattern": None, "path": ".", "glob": None, "context": 0, "word": False, "case": None, "max": DEFAULT_MAX_HITS}
    positional = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--glob", "--context", "--max", "-C", "-g"):
            if i + 1 >= len(argv):
                return None, f"[ERROR] {a} 後面需要值。\n{USAGE}"
            v = argv[i + 1]
            if a in ("--glob", "-g"):
                opts["glob"] = v
            elif not v.isdigit():
                return None, f"[ERROR] {a} 後面需要數字。\n{USAGE}"
            elif a in ("--context", "-C"):
                opts["context"] = min(5, int(v))
            else:
                opts["max"] = max(1, min(300, int(v)))
            i += 2
            continue
        if a in ("--word", "-w"):
            opts["word"] = True
        elif a in ("--case", "-s"):
            opts["case"] = True
        elif a in ("-i", "--ignore-case"):
            opts["case"] = False
        elif a.startswith("-") and len(a) > 1 and not positional:
            return None, f"[ERROR] 不認識的選項 {a}（關鍵字以 - 開頭時請放在引號裡、並放在最前面）。\n{USAGE}"
        else:
            positional.append(a)
        i += 1
    if not positional:
        return None, f"[ERROR] 沒有給搜尋的關鍵字。\n{USAGE}"
    opts["pattern"] = positional[0]
    if len(positional) > 1:
        opts["path"] = positional[1]
    if len(positional) > 2:
        return None, f"[ERROR] 參數太多：{' '.join(positional[2:])}（含空白的關鍵字請用引號包住）。\n{USAGE}"
    return opts, None


def compile_pattern(pattern, word, case):
    if case is None:
        case = any(c.isupper() for c in pattern)
    flags = 0 if case else re.IGNORECASE
    try:
        body = pattern
        re.compile(body)
        literal = False
    except re.error:
        body = re.escape(pattern)
        literal = True
    if word:
        body = rf"(?<![A-Za-z0-9_]){body}(?![A-Za-z0-9_])"
    return re.compile(body, flags), literal, case


def main(argv):
    opts, err = parse_args(argv)
    if err:
        return err
    root, err = cc.resolve_path(opts["path"])
    if err:
        return err
    if not os.path.exists(root):
        return f"[ERROR] 搜尋路徑不存在：{opts['path']}（目前工作目錄 {cc.base_root()}）。"
    if os.path.realpath(root) == "/":
        return "[ERROR] 安全邊界阻斷：不能搜尋整個根目錄 /，請指定專案目錄。"
    if len(opts["pattern"]) > 300:
        return "[ERROR] 關鍵字太長（超過 300 字元），請精簡。"
    regex, literal, case = compile_pattern(opts["pattern"], opts["word"], opts["case"])
    files = cc.iter_files(root, glob=opts["glob"])
    hits, files_hit, t0, timed_out = [], {}, time.monotonic(), False
    total_hits = 0
    for path, rel in files:
        try:
            lines = cc.read_text(path).split("\n")
        except OSError:
            continue
        rel_show = cc.rel_to_root(path)
        for i, ln in enumerate(lines):
            if regex.search(ln):
                total_hits += 1
                files_hit[rel_show] = files_hit.get(rel_show, 0) + 1
                if len(hits) < opts["max"]:
                    hits.append((rel_show, i, lines))
            if (i & 255) == 0 and time.monotonic() - t0 > TIME_BUDGET_SECONDS:
                timed_out = True
                break
        if timed_out:
            break
    scope = f"搜尋 {cc.rel_to_root(root) if root != cc.base_root() else '.'}，{len(files)} 個檔案" + (f"，只看 {opts['glob']}" if opts["glob"] else "")
    flags = ("、當作純文字比對" if literal else "") + ("、區分大小寫" if case else "、不分大小寫") + ("、完整識別字" if opts["word"] else "")
    if total_hits == 0:
        return (f"[PASS] 搜尋「{opts['pattern']}」：0 處命中（{scope}{flags}）。"
                + ("\n（搜尋逾時，只搜了一部分檔案；請縮小路徑或用 --glob）" if timed_out else "")
                + "\n要找檔名用 find_file；要找某個函式在哪裡被定義、被誰呼叫用 code_refs。")
    head = [f"[PASS] 搜尋「{opts['pattern']}」：共 {total_hits} 處命中，分布在 {len(files_hit)} 個檔案（{scope}{flags}）"]
    if len(files_hit) > 1:
        top = sorted(files_hit.items(), key=lambda kv: -kv[1])[:8]
        head.append("各檔命中數：" + "、".join(f"{f}（{n}）" for f, n in top) + ("…" if len(files_hit) > 8 else ""))
    if total_hits > len(hits):
        head.append(f"（只列前 {len(hits)} 處；用 --glob、更精確的關鍵字或 --max 調整）")
    if timed_out:
        head.append("（搜尋逾時，只搜了一部分檔案；請縮小路徑或用 --glob）")
    out, last_file, last_line = [], None, -10
    ctx = opts["context"]
    for rel, i, lines in hits:
        if rel != last_file:
            out.append(f"{rel}")
            last_file, last_line = rel, -10
        lo, hi = max(0, i - ctx), min(len(lines) - 1, i + ctx)
        if ctx and lo > last_line + 1 and last_line >= 0:
            out.append("    …")
        for j in range(max(lo, last_line + 1), hi + 1):
            text = lines[j] if len(lines[j]) <= MAX_LINE_CHARS else lines[j][:MAX_LINE_CHARS] + "…"
            out.append(f"  L{j + 1}{':' if j == i or regex.search(lines[j]) else '-'} {text}")
        last_line = hi
    text = "\n".join(head + out)
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + "\n…（輸出達上限，請縮小範圍）"
    return text


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_search 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
