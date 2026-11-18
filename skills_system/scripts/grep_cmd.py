"""search_text：在檔案「內部文字」裡搜關鍵字（包 GNU grep），命中依檔案分組、筆數由腳本算好。

以前的問題（2026-10 稽核）：額外的旗標原樣傳給 grep、用子字串判斷有沒有帶 -r／-i，`--exclude-dir=build` 讓 -r 消失
（grep: tree: Is a directory）；關鍵字是 BRE，`error|fail` 被當成字面 → 默默回「找不到」；一個沒有權限的目錄讓 grep exit 2，
已經找到的結果全部丟掉；沒有預設略過 build／install／log，在 ROS 2 Workspace 裡逾時；`grep session logs` 一次回 34,140 行、
單行 75,321 字；grep 的錯誤（Unmatched [）原文丟給模型、沒有下一步。

現在：關鍵字一律 `-E -e 關鍵字 --`（a|b 是同義詞；不是合法的正規表示式就改成照字面再搜一次並註明）；只接受少數幾個選項
（不認識的回 [ERROR]）；預設略過 _path_common.DEFAULT_EXCLUDES 的目錄（--all-dirs 取消）；沒有權限的路徑略過並計數；
每個檔案最多列 20 筆、總共 200 筆、單行 300 字，截掉的都寫明怎麼縮小；逾時保留已經找到的結果。
收據（_receipt_common，欄位見規格的 receipt）：每個檔案的筆數（全部）、命中的行（路徑、行號；最多 RECEIPT_LINES 行）。
--rank（新架構 3b）：好幾個字（a|b|c）時，命中太多、列不完的情況先列「同一行含最多個不同的字」的行（長文件照檔案順序會截掉後面的答案）；
檔案照它最多的那一行排，檔案裡照行號；收據的每一行多記 words（含幾個不同的字）。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path_common as pc  # noqa: E402
from _receipt_common import fail, main, result  # noqa: E402
from _results_common import numbered  # noqa: E402
from _shell_common import run_shell  # noqa: E402

TIMEOUT_SECONDS = 30
PER_FILE, TOTAL = 20, 200                 # 每個檔案最多列幾筆、總共最多列幾筆
PER_FILE_CTX, TOTAL_CTX = 10, 50          # 有 -C 前後行時
MAX_CONTEXT = 5
OTHER_FILES_SHOWN = 50                    # 「其他命中的檔案」最多列幾個
FILES_MODE_SHOWN = 200                    # -l 最多列幾個檔案
KEEP_LIMIT = 20000                        # 記憶體裡最多保留幾行（超過的檔案只計數）
RECEIPT_LINES = 20000                     # 收據最多記幾個命中的行號（每個檔案的筆數照樣全部算）
LINE_CHARS = 300
BLOCKED = ("/", "/proc", "/sys", "/dev")
USAGE = ('用法: scripts/grep_cmd.py "<關鍵字>" [路徑…] [選項]\n'
         '  關鍵字：不分大小寫；同義詞用 | 分隔（error|fail|timeout）；可用正規表示式（不合法時自動改成照字面搜尋）；'
         '以 - 開頭的關鍵字寫成 -e "<關鍵字>"。\n'
         '  路徑：檔案或目錄，可以給好幾個，預設 .（目前工作目錄）；不能是 /。\n'
         f'  選項：-w 整個字　-F 照字面　--case 分大小寫　-l 只列檔名與筆數　-C N 前後各 N 行（上限 {MAX_CONTEXT}）\n'
         '        --include "*.py" 只搜這種檔名（可重複）　--exclude-dir 名稱 多略過一個目錄　'
         '--all-dirs 連預設略過的 build、install、log、.git 等目錄也搜\n'
         '        --rank 好幾個字（a|b|c）時先列同一行含最多個不同的字的行')
_NOOP_SHORT = set("rRnHiIEPs")            # 舊習慣的 grep 旗標：本來就是這樣（遞迴、行號、不分大小寫、跳過二進位檔、延伸正規表示式）
_NOOP_LONG = {"--recursive", "--line-number", "--ignore-case", "--with-filename", "--extended-regexp", "--no-messages",
              "--binary-files=without-match", "--color=never"}
_REGEX_ERR = re.compile(r"Unmatched|Invalid|Trailing backslash|too big|malformed", re.I)


def _looks_like_path(a):
    return a in (".", "..") or a.startswith(("/", "./", "../", "~"))


def parse_args(argv):
    """回傳 (選項 dict, 錯誤)。"""
    o = {"pattern": None, "paths": [], "word": False, "fixed": False, "case": False, "files": False, "ctx": 0,
         "include": [], "exclude": [], "exclude_dir": [], "all_dirs": False, "rank": False, "notes": []}
    args = list(argv)
    i = 0

    def need_value(name):
        if i + 1 >= len(args):
            raise ValueError(f"[ERROR] {name} 後面需要值。\n{USAGE}")
        return args[i + 1]

    def set_ctx(v, name):
        if not str(v).isdigit():
            raise ValueError(f"[ERROR] {name} 後面要是行數（0～{MAX_CONTEXT}），收到「{v}」。\n{USAGE}")
        o["ctx"] = max(o["ctx"], min(MAX_CONTEXT, int(v)))
        if int(v) > MAX_CONTEXT:
            o["notes"].append(f"前後行數上限 {MAX_CONTEXT}，已改成 {MAX_CONTEXT}")

    try:
        while i < len(args):
            a = args[i]
            if a == "--":
                for rest in args[i + 1:]:
                    if o["pattern"] is None:
                        o["pattern"] = rest
                    else:
                        o["paths"].append(rest)
                break
            if a in ("-e", "--regexp") or a.startswith("--regexp="):
                o["pattern"] = a.split("=", 1)[1] if "=" in a else need_value(a)
                i += 1 if "=" in a else 2
                continue
            if a.startswith("--"):
                name, eq, val = a.partition("=")
                if a in _NOOP_LONG or name in ("--color", "--colour", "--perl-regexp", "--null"):
                    pass
                elif name in ("--include", "--exclude", "--exclude-dir"):
                    v = val if eq else need_value(name)
                    i += 0 if eq else 1
                    o[{"--include": "include", "--exclude": "exclude", "--exclude-dir": "exclude_dir"}[name]].append(v)
                elif name == "--context":
                    v = val if eq else need_value(name)
                    i += 0 if eq else 1
                    set_ctx(v, name)
                elif a == "--all-dirs":
                    o["all_dirs"] = True
                elif a == "--rank":
                    o["rank"] = True
                elif a in ("--case", "--case-sensitive", "--no-ignore-case"):
                    o["case"] = True
                elif a in ("--fixed-strings", "--fixed"):
                    o["fixed"] = True
                elif a in ("--word-regexp", "--word"):
                    o["word"] = True
                elif a in ("--files-with-matches", "--count", "--files"):
                    o["files"] = True
                elif o["pattern"] is None and i == 0 and args[1:] and all(os.path.exists(pc.expand(p)) for p in args[1:]):
                    o["pattern"] = a              # 要搜的文字本身以 -- 開頭（例如 "--timeout" .）
                    o["notes"].append(f"「{a}」不是選項，當成要搜的文字（以 - 開頭的關鍵字建議寫成 -e \"{a}\"）")
                else:
                    raise ValueError(f"[ERROR] 不支援的選項 {a}。下一步：拿掉這個選項（能用的選項見下面的用法）；要搜的字本身以 - 開頭時才寫成 -e \"{a}\"。\n{USAGE}")
                i += 1
                continue
            if a.startswith("-") and len(a) > 1 and not (o["pattern"] is None and i == 0 and _plain_word_after_dash(a, args)):
                j = 1
                while j < len(a):
                    c = a[j]
                    if c in _NOOP_SHORT:
                        pass
                    elif c == "w":
                        o["word"] = True
                    elif c == "F":
                        o["fixed"] = True
                    elif c in "lc":
                        o["files"] = True
                    elif c in "ABC":
                        rest = a[j + 1:]
                        if rest:
                            set_ctx(rest, f"-{c}")
                        else:
                            set_ctx(need_value(f"-{c}"), f"-{c}")
                            i += 1
                        break
                    elif c == "e":
                        rest = a[j + 1:]
                        o["pattern"] = rest if rest else need_value("-e")
                        i += 0 if rest else 1
                        break
                    else:
                        where = "" if len(a) == 2 else f"（在 {a} 裡）"
                        raise ValueError(f"[ERROR] 不支援的選項 -{c}{where}。下一步：拿掉這個選項（能用的選項見下面的用法）；"
                                         f"要搜的字本身以 - 開頭時才寫成 -e \"{a}\"。\n{USAGE}")
                    j += 1
                i += 1
                continue
            if o["pattern"] is None:
                o["pattern"] = a
                if a.startswith("-"):
                    o["notes"].append(f"「{a}」不是選項，當成要搜的文字")
            else:
                o["paths"].append(a)
            i += 1
    except ValueError as e:
        return None, str(e)
    return o, None


def _plain_word_after_dash(a, args):
    """第一個參數以 - 開頭、但不是我們認得的短旗標組合、後面的參數又都是存在的路徑 → 那是要搜的文字（例如 "-v1.2"）。"""
    body = a[1:]
    if all(c in _NOOP_SHORT | set("wFlc") for c in body):
        return False
    if re.fullmatch(r"[ABCe]\d*", body):
        return False
    return bool(args[1:]) and all(os.path.exists(pc.expand(p)) for p in args[1:])


def _alternatives(pattern):
    """關鍵字最外層的 | 分出的每一個字（括號、方括號裡的 | 與跳脫的 \\| 不算）。"""
    out, cur, depth, in_class, i = [], "", 0, False, 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\" and i + 1 < len(pattern):
            cur += pattern[i:i + 2]
            i += 2
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        elif c == "|" and depth == 0:
            out.append(cur)
            cur, i = "", i + 1
            continue
        cur += c
        i += 1
    return [x for x in out + [cur] if x]


def _scorer(o, pattern, fixed):
    """--rank：一行含幾個不同的字（照 grep 的規則：分不分大小寫、整個字）。不是 --rank、照字面搜或只有一個字時回 None（排序沒有作用）。"""
    alts = [] if fixed or not o["rank"] else _alternatives(pattern)
    if len(alts) < 2:
        return None
    flags = re.ASCII | (0 if o["case"] else re.I)      # grep 在 C locale：只有英文字母分大小寫，\w 只算英數字與底線
    rxs = []
    for a in alts:
        try:
            body = re.compile(a, flags).pattern
        except re.error:                                 # grep 認得、Python 不認得的寫法（[[:alpha:]]）：照字面
            body = re.escape(a)
        rxs.append(re.compile(rf"(?<!\w)(?:{body})(?!\w)" if o["word"] else body, flags))
    return lambda text: sum(1 for rx in rxs if rx.search(text))


class Collector:
    """grep -Z 的輸出逐行收進來：每個檔案的命中筆數（全部都算）、保留前幾筆（含前後行）。
    score（--rank）：每個命中的行含幾個不同的字，記進收據；要照它挑行時 per_file 給 KEEP_LIMIT（先全部留著，render 再挑）。"""

    def __init__(self, per_file, ctx, score=None):
        self.per_file, self.ctx, self.score = per_file, ctx, score
        self.files = {}
        self.kept = 0
        self.hit_lines = 0                    # 收據記了幾個命中的行號

    def on_line(self, raw):
        if raw == b"--":
            return
        nul = raw.find(b"\0")
        if nul < 0:
            return
        path = raw[:nul].decode("utf-8", errors="replace")
        m = re.match(rb"(\d+)([:-])", raw[nul + 1:])
        if not m:
            return
        ln, hit = int(m.group(1)), m.group(2) == b":"
        text = raw[nul + 1 + m.end():].decode("utf-8", errors="replace").rstrip("\r")
        f = self.files.get(path)
        if f is None:
            f = self.files[path] = {"hits": 0, "kept_hits": 0, "last_kept_hit": None, "lines": [], "hit_lines": [], "words": {}}
        if hit:
            f["hits"] += 1
            if self.hit_lines < RECEIPT_LINES:
                f["hit_lines"].append(ln)
                self.hit_lines += 1
                if self.score:
                    f["words"][ln] = self.score(text)
        if self.kept >= KEEP_LIMIT and not f["lines"]:      # 記憶體上限：之後的新檔案只計數（列在「其他命中的檔案」）
            return
        if hit and f["kept_hits"] < self.per_file:
            f["kept_hits"] += 1
            f["last_kept_hit"] = ln
            f["lines"].append((ln, True, text))
            self.kept += 1
        elif not hit and (f["kept_hits"] < self.per_file
                          or (f["last_kept_hit"] is not None and 0 < ln - f["last_kept_hit"] <= self.ctx)):
            f["lines"].append((ln, False, text))
            self.kept += 1


def _show_path(p):
    return p[2:] if p.startswith("./") else p


def _fix_pattern(p):
    """模型的 BRE 習慣：`a\\|b` → `a|b`；`\\d` → `[0-9]`（GNU grep -E 不認得 \\d，會當成字母 d）。"""
    return p.replace("\\|", "|").replace("\\d", "[0-9]").replace("\\D", "[^0-9]")


def _run(o, pattern, fixed, excludes, collector, timeout):
    cmd = ["grep", "-r", "-n", "-H", "-Z", "-I", "--color=never", "-D", "skip"]
    if not o["case"]:
        cmd.append("-i")
    cmd.append("-F" if fixed else "-E")
    if o["word"]:
        cmd.append("-w")
    if o["ctx"]:
        cmd.append(f"-C{o['ctx']}")
    cmd += [f"--include={g}" for g in o["include"]] + [f"--exclude={g}" for g in o["exclude"]]
    cmd += [f"--exclude-dir={d}" for d in excludes + o["exclude_dir"]]
    cmd += ["-e", pattern, "--"] + o["paths"]
    perm, other = [], []

    def on_err(raw):
        line = raw.decode("utf-8", errors="replace")
        if "warning:" in line:
            return
        (perm if "Permission denied" in line else other).append(line)

    env = dict(os.environ, LC_ALL="C")      # C locale：有編碼錯誤的 log 不會被當成二進位檔跳過，也比較快
    r = run_shell(cmd, timeout, env=env, on_stdout_line=collector.on_line, on_stderr_line=on_err)
    return r, perm, other


def _binary_note(paths):
    out = []
    for p in paths:
        ap = os.path.abspath(pc.expand(p))
        if os.path.isfile(ap):
            try:
                with open(ap, "rb") as f:
                    if b"\0" in f.read(8192):
                        out.append(p)
            except OSError:
                pass
    return out


def execute(argv):
    o, err = parse_args(argv)
    if err:
        return fail(err, "args")
    if o["pattern"] is None or o["pattern"] == "":
        return fail(f"[ERROR] 缺少要搜的關鍵字。下一步：第一個參數寫關鍵字、第二個寫路徑，例如 \"ERROR\" .\n{USAGE}", "args")
    if not o["paths"] and _looks_like_path(o["pattern"]) and os.path.isdir(pc.expand(o["pattern"])):
        return fail(f"[ERROR] 只給了路徑 {o['pattern']}，缺少要搜的關鍵字。下一步：寫成 \"<關鍵字>\" {o['pattern']}；"
                    f"要列目錄內容請用 list_dir、找檔名請用 find_file。\n{USAGE}", "args")
    if not o["paths"]:
        o["paths"] = ["."]
        o["notes"].append("沒有給路徑，搜目前工作目錄 .")
    resolved = []
    for idx, p in enumerate(o["paths"]):
        ap, perr = pc.resolve(p, "any")
        if perr:
            kind = perr.kind
            if idx == 0 and o["pattern"].lower() == "grep" and len(o["paths"]) >= 1:
                perr += ("\n（第一個參數是要搜的關鍵字：你寫的是「grep」。search_text 不用寫 grep 指令本身，"
                         "直接寫 \"<關鍵字>\" <路徑>）")
            return fail(perr, kind)
        if ap in BLOCKED:
            return fail(f"[ERROR] 不搜 {ap}（整個系統或虛擬檔案系統太大、會卡住）。下一步：指定具體的目錄，例如 . 或專案的 src。", "args")
        resolved.append(ap)
    o["paths"] = [p if not p.startswith(("~", "$")) else pc.expand(p) for p in o["paths"]]
    per_file, total_cap = (PER_FILE_CTX, TOTAL_CTX) if o["ctx"] else (PER_FILE, TOTAL)
    single_file = len(resolved) == 1 and os.path.isfile(resolved[0])
    if single_file:
        per_file = total_cap
    excludes = pc.excludes_for(o["paths"], o["all_dirs"])
    pattern = o["pattern"] if o["fixed"] else _fix_pattern(o["pattern"])
    score = _scorer(o, pattern, o["fixed"])
    collector = Collector(KEEP_LIMIT if score and not o["files"] else per_file, o["ctx"], score)
    r, perm, other = _run(o, pattern, o["fixed"], excludes, collector, TIMEOUT_SECONDS)
    fixed = o["fixed"]
    if r.spawn_error:
        return fail(f"[ERROR] search_text 沒辦法執行 grep：{r.spawn_error}。下一步：請使用者確認系統有安裝 grep。", "env")
    if not fixed and r.rc == 2 and not collector.files and any(_REGEX_ERR.search(x) for x in other):
        reason = next(x for x in other if _REGEX_ERR.search(x)).split(":", 1)[-1].strip()
        o["notes"].append(f"關鍵字不是合法的正規表示式（{reason}），已改成照字面搜尋")
        fixed = True
        collector = Collector(per_file, o["ctx"])               # 照字面：整串是一個字，--rank 沒有作用
        r, perm, other = _run(o, o["pattern"], True, excludes, collector, TIMEOUT_SECONDS)
    return render(o, collector, r, perm, other, excludes, per_file, total_cap, fixed, single_file)


def render(o, col, r, perm, other, excludes, per_file, total_cap, fixed, single_file):
    files = sorted(col.files.items(), key=lambda kv: _show_path(kv[0]))
    files = [(p, f) for p, f in files if f["hits"]]
    n_hits = sum(f["hits"] for _, f in files)
    where = "、".join(o["paths"])
    how = ("分大小寫" if o["case"] else "不分大小寫") + ("、照字面" if fixed else "") + ("、整個字" if o["word"] else "")
    kw = f"「{o['pattern']}」"
    tail_notes = []
    if perm:
        tail_notes.append(f"{len(perm)} 個路徑沒有權限（略過）")
    if other and not (r.rc == 2 and not files):
        tail_notes.append(f"{len(other)} 個讀取錯誤（略過；第一個：{pc.clip(other[0], 160)}）")
    searched_dirs = any(os.path.isdir(pc.expand(p)) for p in o["paths"])
    if excludes and searched_dirs:
        tail_notes.append(f"預設略過 {'／'.join(excludes[:4])} 等目錄（要一起搜加 --all-dirs）")
    if o["include"]:
        tail_notes.append(f"只搜檔名符合 {'、'.join(o['include'])} 的檔案")
    if o["rank"] and not col.score:
        tail_notes.append("--rank 要有好幾個字（a|b|c）才有作用：照檔案順序列")
    elif o["rank"] and o["files"]:
        tail_notes.append("-l 只列檔名，--rank 沒有作用")
    if r.rc == 2 and not files and other and not perm:
        msg = "；".join(pc.clip(x, 200) for x in other[:3])
        return fail(f"[ERROR] search_text 執行失敗（grep exit code 2）：{msg}。下一步：檢查關鍵字與路徑"
                    f"（關鍵字含特殊字元時加 -F 照字面搜尋）；路徑沒問題就把這個錯誤告訴使用者。\n{USAGE}", "args")
    notes = o["notes"] + tail_notes
    note_line = f"（{'；'.join(notes)}）" if notes else ""
    if r.timed_out and not files:
        return fail(f"[ERROR] 搜尋{kw}逾時（{TIMEOUT_SECONDS} 秒內沒有搜完，也還沒有找到任何一筆；搜尋 {where}）。"
                    f"下一步：縮小範圍——指定子目錄或檔案、加 --include \"*.py\" 只搜某種檔案、或換更精確的關鍵字。" + note_line, "timeout")
    _receipt(o, files, r, perm, other, excludes, fixed)
    if not files:
        out = [f"[PASS] 找不到符合{kw}的內容（0 筆；搜尋 {where}，{how}）"]
        hints = []
        binaries = _binary_note(o["paths"])
        if binaries:
            hints.append(f"{'、'.join(binaries)} 是二進位檔，search_text 不搜（影像用 image_inspect；mcap 用 mcap_analyzer／rosout_parser）")
        if not fixed and "|" not in o["pattern"]:
            hints.append("可以用 | 加同義詞再搜一次，例如 error|fail|exception")
        if excludes and searched_dirs:
            hints.append("可能在預設略過的目錄裡：加 --all-dirs 再搜")
        if note_line:
            out.append(note_line)
        if hints:
            out.append("（" + "；".join(hints) + "）")
        return "\n".join(out)
    if r.timed_out:
        head = (f"[PASS] 搜尋{kw}逾時（{TIMEOUT_SECONDS} 秒）沒有搜完：目前找到 {n_hits} 筆、{len(files)} 個檔案，不是全部"
                f"（搜尋 {where}，{how}）；要完整的結果請縮小範圍（指定子目錄、--include \"*.py\"）")
    else:
        head = f"[PASS] 搜尋{kw}：共 {n_hits} 筆命中，分布在 {len(files)} 個檔案（搜尋 {where}，{how}）"
    lines = []
    if o["files"]:
        shown = files[:FILES_MODE_SHOWN]
        head += "；只列檔名與筆數" + (f"，只列前 {len(shown)} 個檔案（依路徑排序）" if len(files) > len(shown) else "")
        lines.append(f"## 有命中的檔案（{len(files)} 項）")
        lines += [f"- {_show_path(p)}（{f['hits']} 筆）" for p, f in shown]
    else:
        shown_hits, others, clipped = 0, [], False
        for p, f, entries, take in (_ranked(col, files, per_file, total_cap, o["ctx"]) if col.score
                                    else _in_order(files, total_cap, o["ctx"])):
            if not take:
                others.append((p, f))
                continue
            shown_hits += take
            label = f"{f['hits']} 筆" + (f"，只列{'' if col.score else '前'} {take} 筆" if take < f["hits"] else "")
            lines.append(f"## {_show_path(p)}（{label}）")
            prev = None
            for ln, hit, text in entries:
                if o["ctx"] and prev is not None and ln > prev + 1:
                    lines.append("      …")
                if len(text) > LINE_CHARS:
                    clipped = True
                lines.append(numbered(ln, pc.clip(text, LINE_CHARS), ">" if (hit and o["ctx"]) else " "))
                prev = ln
        if col.score:
            head += "；先列同一行含最多個不同的字的行（--rank），檔案照它最多的那一行排、檔案裡照行號"
        if shown_hits < n_hits:
            first = " " if col.score else "前 "
            head += (f"；只列{first}{shown_hits} 筆（每個檔案最多 {per_file} 筆、總共最多 {total_cap} 筆）" if not single_file
                     else f"；只列{first}{shown_hits} 筆")
        if clipped:
            head += f"；單行超過 {LINE_CHARS} 字截斷"
        if others:
            lines.append(f"## 其他命中的檔案（{len(others)} 項，只列檔名與筆數）")
            lines += [f"- {_show_path(p)}（{f['hits']} 筆）" for p, f in others[:OTHER_FILES_SHOWN]]
            if len(others) > OTHER_FILES_SHOWN:
                lines.append(f"- …另外 {len(others) - OTHER_FILES_SHOWN} 個檔案沒有列出")
        if shown_hits < n_hits:
            if single_file:
                lines.append(f"（看其他筆：view_file {o['paths'][0]} --from <行號>，或換更精確的關鍵字）")
            else:
                lines.append("（要看其他筆：指定那個檔案再搜一次（單一檔案最多列 200 筆）、加 --include \"*.py\" 或換更精確的關鍵字；"
                             "只看哪些檔案有命中用 -l）")
    if note_line:
        lines.append(note_line)
    return "\n".join([head] + lines)


def _in_order(files, total_cap, ctx):
    """照檔案與行號：每個檔案 (路徑, 檔案, 要列的行（含前後行）, 列幾筆命中)；總共列滿了的檔案列 0 筆（放到「其他命中的檔案」）。"""
    budget = total_cap
    for p, f in files:
        hits_here = [x for x in f["lines"] if x[1]]
        if budget <= 0 or not hits_here:
            yield p, f, [], 0
            continue
        take = min(len(hits_here), budget)
        last_hit_ln = hits_here[take - 1][0]
        budget -= take
        yield p, f, [x for x in f["lines"] if x[0] <= last_hit_ln + ctx], take


def _ranked(col, files, per_file, total_cap, ctx):
    """--rank：命中的行照含幾個不同的字（多的先）、檔案、行號挑（每個檔案最多 per_file 筆、總共 total_cap 筆）；
    檔案照它挑到的最多字的那一行排，檔案裡照行號列（含前後行）。"""
    cands = sorted(((col.score(text), _show_path(p), ln, p) for p, f in files for ln, hit, text in f["lines"] if hit),
                   key=lambda c: (-c[0], c[1], c[2]))
    picked, best = {}, {}
    for score, _, ln, p in cands:
        if sum(len(v) for v in picked.values()) >= total_cap:
            break
        if len(picked.get(p, ())) < per_file:
            picked.setdefault(p, set()).add(ln)
            best[p] = max(best.get(p, 0), score)
    order = sorted(files, key=lambda pf: (pf[0] not in picked, -best.get(pf[0], 0), _show_path(pf[0])))
    for p, f in order:
        lines = picked.get(p, set())
        near = {x for ln in lines for x in range(ln - ctx, ln + ctx + 1)}      # 沒挑到的命中在前後行的範圍裡：當前後行列（不標 >）
        yield p, f, [(ln, ln in lines, text) for ln, _, text in f["lines"] if ln in near], len(lines)


def _receipt(o, files, r, perm, other, excludes, fixed):
    """收據：每個檔案的筆數（全部）、命中的行（路徑、行號）；逾時沒搜完或行號超過 RECEIPT_LINES 時 truncated。"""
    items = [dict({"path": os.path.abspath(p), "line": ln}, **({"words": f["words"][ln]} if ln in f["words"] else {}))
             for p, f in files for ln in f["hit_lines"]]
    complete = all(len(f["hit_lines"]) == f["hits"] for _, f in files)
    result("pass" if files else "empty", counts={"hits": sum(f["hits"] for _, f in files), "files": len(files)},
           items=items, truncated=r.timed_out or not complete,
           per_file={os.path.abspath(p): f["hits"] for p, f in files}, pattern=o["pattern"],
           paths=[os.path.abspath(pc.expand(p)) for p in o["paths"]],
           options={"word": o["word"], "fixed": fixed, "case": o["case"], "files_only": o["files"], "context": o["ctx"],
                    "include": o["include"], "exclude_dir": o["exclude_dir"], "all_dirs": o["all_dirs"], "rank": o["rank"]},
           excluded_dirs=list(excludes), skipped={"permission": len(perm), "read_errors": len(other)}, timed_out=r.timed_out)


if __name__ == "__main__":
    main(execute, "search_text")
