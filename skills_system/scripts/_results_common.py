"""工具結果存檔（logs/tool_results/）的共用層，給 result_list／result_grep／result_view 三個技能與 harness 的提煉（agent_core/extract.py）用。

harness（Agent_Runner._archive_tool_result）每次腳本執行都把完整原始輸出存成 <session>_<id>_<腳本>.md（key: value 檔頭 + 原文），
並在 index.md 記一行。這裡負責：找存檔目錄（環境變數 TOOL_RESULTS_DIR，預設 <harness>/logs/tool_results）、目前 session
（HARNESS_SESSION）、把「16／#16／latest／檔名」解析成檔案、讀檔頭（不用 PyYAML）、安全的逐行比對（長度上限＋時間預算，
防災難性回溯；路徑一律鎖在存檔目錄內），以及原文的結構（段落邊界、大綱、切段）。

行號一律是「原文的行號」（工具輸出的第 1 行＝行 1，不含存檔的檔頭）：result_view、result_grep、提煉結果引用的行號、claude_code 模式的
截斷說明都是同一套，寫成 `120→內容`（不用 L120：數據分析的報告裡 L# 是 Log 訊號的編號）。
存檔的種類（框架討論紀錄第 42 輪）：檔頭的 memory——action（會改狀態的動作，當時做了什麼的紀錄）、live（查執行中系統當下的狀態：工具規格寫了
`live: true`）、content（其他）；舊的存檔沒有這個欄位，照檔頭的技能判斷（memory_kind）。讀回時開頭寫那一份的事實（archive_facts）。
"""
import json
import os
import re
import time

INDEX_NAME = "index.md"
FILE_RE = re.compile(r"^(\d{8}_\d{6})_(\d{3,})_(.+)\.md$")
MAX_PATTERN_LEN = 200
TIME_BUDGET_SECONDS = 3.0
MAX_LINE_CHARS = 300          # 單行超過就截斷（高頻 topic 的 JSON 一行可能上千字）


def results_dir():
    d = (os.environ.get("TOOL_RESULTS_DIR") or "").strip()
    if not d:
        harness = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        d = os.path.join(harness, "logs", "tool_results")
    return d


def current_session():
    return (os.environ.get("HARNESS_SESSION") or "").strip()


def list_result_files(d=None):
    """[(session, id, stem, filename)]，依 session、id 排序（舊→新）。"""
    d = d or results_dir()
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        m = FILE_RE.match(fn)
        if m:
            out.append((m.group(1), int(m.group(2)), m.group(3), fn))
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def resolve_result(ref, d=None, session=None):
    """'16'／'#16'（優先目前 session 的 #16，沒有就取最新一個有 #16 的 session）、'latest'、或 result_list 列出的檔名。
    session：目前的 session（harness 在同一個 process 裡呼叫時直接給；腳本從環境變數 HARNESS_SESSION 讀）。
    回傳 (path, error)。路徑一定在存檔目錄內（只取 basename）。"""
    d = d or results_dir()
    session = session or current_session()
    files = list_result_files(d)
    if not files:
        return None, f"[ERROR] 目前沒有任何工具結果存檔（{d}）。要先執行過技能才有存檔。"
    ref = (ref or "").strip()
    if ref.lower() in ("", "latest", "last", "最新"):
        return os.path.join(d, files[-1][3]), None
    if ref.lstrip("#").isdigit():
        rid = int(ref.lstrip("#"))
        cands = [f for f in files if f[1] == rid]
        if not cands:
            return None, f"[ERROR] 找不到結果 #{rid}（用 result_list 看現有的編號）。"
        mine = [f for f in cands if f[0] == session]
        return os.path.join(d, (mine or cands)[-1][3]), None
    name = os.path.basename(ref)
    if name in {f[3] for f in files}:
        return os.path.join(d, name), None
    return None, f"[ERROR] 找不到結果 {ref!r}：請給編號（如 16）、latest，或 result_list 列出的檔名。"


def read_header(path, max_lines=40):
    """key: value 檔頭 → dict；回傳 (meta, body_start)：body_start 是原文第一行的 1-based 行號。"""
    meta, body_start = {}, 1
    with open(path, encoding="utf-8", errors="replace") as f:
        first = f.readline()
        if first.strip() != "---":
            return meta, 1
        for i, line in enumerate(f, 2):
            if line.strip() == "---":
                body_start = i + 1
                break
            if i > max_lines:
                break
            k, sep, v = line.partition(":")
            if sep:
                meta[k.strip()] = v.strip()
    return meta, body_start


_TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
_LIVE_LINE = re.compile(r"^live:\s*true\s*$")
_live = []


def live_skills():
    """工具規格（skills_system/tools/<名稱>.md）的 frontmatter 寫了 `live: true` 的技能（查執行中系統當下的狀態）；讀一次就記住。"""
    if not _live:
        names = set()
        for fn in sorted(os.listdir(_TOOLS_DIR)) if os.path.isdir(_TOOLS_DIR) else []:
            if fn.endswith(".md"):
                try:
                    with open(os.path.join(_TOOLS_DIR, fn), encoding="utf-8") as f:
                        head = f.read(4000).split("\n---", 1)[0]
                except OSError:
                    continue
                if any(_LIVE_LINE.match(ln) for ln in head.split("\n")):
                    names.add(fn[:-3])
        _live.append(names)
    return _live[0]


def memory_kind(meta):
    """存檔的種類：檔頭的 memory（寫存檔時記的 action／live／content）；沒有的（舊的存檔）照檔頭的技能——規格寫了 live 的是 live，其他 content。"""
    kind = (meta.get("memory") or "").strip()
    if kind:
        return kind
    return "live" if (meta.get("skill") or "").strip() in live_skills() else "content"


def archive_time(meta):
    """檔頭的 ts（YYYY-MM-DD HH:MM:SS）→ 秒；寫錯、沒有的回 None。"""
    try:
        return time.mktime(time.strptime((meta.get("ts") or "").strip(), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, OverflowError):
        return None


def age_text(seconds):
    """經過的秒數 → 「剛剛」「N 分鐘前」「N 小時前」「N 天前」。"""
    if seconds < 90:
        return "剛剛"
    if seconds < 5400:
        return f"{round(seconds / 60)} 分鐘前"
    if seconds < 172800:
        return f"{round(seconds / 3600)} 小時前"
    return f"{round(seconds / 86400)} 天前"


def read_receipt(path):
    """存檔旁邊的收據（<存檔>.receipt.json）；沒有、讀不到的回 None。"""
    try:
        with open(path[:-3] + ".receipt.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def changed_files(receipt, since, limit=20):
    """收據裡讀過的檔案（絕對路徑，前 limit 個），修改時間比 since（存檔的時間，秒）晚的 → 寫成收據的 cwd 底下的相對路徑。"""
    if not isinstance(receipt, dict) or since is None:
        return []
    paths = [str(it["path"]) for it in receipt.get("items") or [] if isinstance(it, dict) and it.get("path")]
    paths += [str(p) for p in [receipt.get("path")] + list(receipt.get("per_file") or {}) if p]
    cwd = str(receipt.get("cwd") or "").rstrip("/")
    out = []
    for p in list(dict.fromkeys(x for x in paths if x.startswith("/")))[:limit]:
        try:
            if os.path.getmtime(p) > since + 1:
                out.append(p[len(cwd) + 1:] if cwd and p.startswith(cwd + "/") else p)
        except OSError:
            continue
    return out


def archive_facts(path, meta=None, now=None):
    """讀回存檔時開頭的一行事實（框架討論紀錄第 42 輪）：即時狀態寫什麼時候查的、多久以前；動作寫是當時做了什麼的紀錄；檔案內容在存檔之後
    收據裡的檔案改過的列出來；都不是回空字串。"""
    meta = meta if meta is not None else read_header(path)[0]
    rid, ts, skill = meta.get("id") or "?", meta.get("ts") or "?", meta.get("skill") or meta.get("script") or "?"
    when = archive_time(meta)
    age = age_text((now or time.time()) - when) if when else "時間不明"
    kind = memory_kind(meta)
    if kind == "live":
        return f"（#{rid} 是 {skill} 在 {ts}（{age}）查的即時狀態：是那時候的狀態，不一定是現在的；問現在的狀態要重新執行工具）"
    if kind == "action":
        return f"（#{rid} 是 {ts}（{age}）執行的動作 {skill} 的結果：是當時做了什麼的紀錄，不是現在的狀態）"
    changed = changed_files(read_receipt(path), when)
    if changed:
        return f"（#{rid} 存檔（{ts}）之後，這些檔案改過：{'、'.join(changed)}——存檔的內容可能跟現在的不一樣）"
    return ""


DERIVED_SCRIPTS = ("result_view_cmd.py", "result_grep_cmd.py", "result_recall_cmd.py")   # 看舊存檔的衍生輸出：照它讀的那幾份算


def stale_facts(path, first_id, d=None, session=None):
    """引用這一份存檔時要提醒的事實（框架討論紀錄第 42 輪的 D3）：這一回合之前存的（編號比 first_id 小）即時狀態、動作的紀錄、存檔之後改過的
    檔案（archive_facts）；看舊存檔的衍生輸出（result_view、result_grep、result_recall）照它讀的那幾份算（第一個參數寫的編號；latest、all 不算）。
    → [事實的句子]"""
    meta = read_header(path)[0]
    if (meta.get("script") or "") in DERIVED_SCRIPTS:
        tokens = (meta.get("command") or "").split()
        at = next((i for i, t in enumerate(tokens) if t.endswith(tuple(DERIVED_SCRIPTS))), None)
        first_arg = tokens[at + 1].strip("\"'") if at is not None and at + 1 < len(tokens) else ""
        out = []
        for ref in first_arg.split(","):
            if ref.lstrip("#").isdigit() and (first_id is None or int(ref.lstrip("#")) < first_id):
                src, err = resolve_result(ref.lstrip("#"), d, session=session)
                fact = archive_facts(src) if src and not err else ""
                if fact:
                    out.append(fact)
        return out
    rid = meta.get("id") or ""
    if first_id is not None and (not str(rid).isdigit() or int(rid) >= first_id):
        return []
    fact = archive_facts(path, meta)
    return [fact] if fact else []


def read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def read_body(path):
    """存檔 → (meta, 原文的每一行)：原文的第 1 行是 lines[0]（行號＝索引＋1）。"""
    meta, body_start = read_header(path)
    return meta, read_lines(path)[body_start - 1:]


def numbered(n, text, mark=" "):
    """一行原文的顯示：`  120→內容`（mark 是 result_grep 標命中行的 >）。"""
    return f"{mark}{n:>5}→{text}"


_NUMBERED = re.compile(r"^[ >]\s*(\d+)→")


def file_lines(lines, receipt):
    """工具輸出的每一行 → 那一行在檔案裡的位置：{輸出的行號（1 起算）: (路徑, 檔案的行號)}。view_file、search_text 每行前面的 `N→`
    （numbered）是檔案的行號；提煉、result_view 再加一層存檔的行號，兩個都寫成 `N→`，模型會搞混（設計筆記 2.47：檔案的第 49 行寫成存檔裡的
    第 149 行）。路徑照收據：收據只有一個檔案就是它；好幾個（search_text 一個檔案一節）就是上面最近一行寫到的那一個（不是 `N→` 的行，
    長的路徑先比）。寫成收據的 cwd 底下的相對路徑（跟工具輸出的寫法一樣）。沒有收據、收據沒有檔案的回空的。
    只認收據裡的絕對路徑：讀檔案的工具記的都是絕對路徑；result_grep 的 per_file 記的是存檔編號（"5"），它輸出的 `N→` 是那份存檔的行號，
    不是檔案的（4k ② 的階段驗證：被當成「檔案 5 的第 58 行」，交回修反而把回答改壞）。"""
    if not isinstance(receipt, dict):
        return {}
    cwd = str(receipt.get("cwd") or "").rstrip("/")
    paths = {str(it["path"]) for it in receipt.get("items") or [] if isinstance(it, dict) and it.get("path")}
    paths |= {str(p) for p in [receipt.get("path")] + list(receipt.get("per_file") or {}) if p}
    paths = {p for p in paths if p.startswith("/")}
    shown = sorted({p[len(cwd) + 1:] if cwd and p.startswith(cwd + "/") else p for p in paths}, key=len, reverse=True)
    out, cur = {}, (shown[0] if len(shown) == 1 else None)
    for i, line in enumerate(lines, 1):
        m = _NUMBERED.match(line)
        if m:
            if cur:
                out[i] = (cur, int(m.group(1)))
        elif len(shown) > 1:
            cur = next((p for p in shown if p in line), cur)
    return out


def describe(meta, fn):
    """'#16 semantic_map_cmd.py（2026-09-25 10:34，PASS）'"""
    m = FILE_RE.match(fn)
    rid = meta.get("id") or (m.group(2).lstrip("0") if m else "?")
    return f"#{rid} {meta.get('script') or fn}（{meta.get('ts') or '?'}，{meta.get('status') or '?'}）"


def compile_pattern(pattern):
    """安全的 regex：長度上限、不分大小寫；不是合法 regex 就當純文字比對。回傳 (regex, error)。"""
    pattern = (pattern or "").strip()
    if not pattern:
        return None, "[ERROR] 需要搜尋關鍵字（可用 | 分隔同義詞，例如 error|fail|timeout）。"
    if len(pattern) > MAX_PATTERN_LEN:
        return None, f"[ERROR] 關鍵字太長（{len(pattern)} > {MAX_PATTERN_LEN} 字元），請精簡。"
    try:
        return re.compile(pattern, re.IGNORECASE), None
    except re.error:
        return re.compile(re.escape(pattern), re.IGNORECASE), None


def search_lines(lines, regex, budget=TIME_BUDGET_SECONDS):
    """逐行比對、帶時間預算（模型或使用者給的正則可能災難性回溯）。回傳 (hit_indices 0-based, timed_out)。"""
    hits, t0 = [], time.monotonic()
    for i, ln in enumerate(lines):
        if regex.search(ln):
            hits.append(i)
        if (i & 127) == 0 and time.monotonic() - t0 > budget:
            return hits, True
    return hits, False


def clip(line):
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS] + "…"


# =====================================================================================================================
# 原文的結構：工具的輸出是一行一行的文字，大多有固定的寫法——第一行狀態列（[PASS]／[ERROR] 與算好的數量）、章節（`## 標題`、
# 「欄位變化（…）：」這種以全形冒號結尾的一行）、一筆一筆的紀錄（`--- #序號`、`- `、`▸`、`L12 `、表格的一列）。提煉時依這些邊界切段，
# 每一段附上讀它要知道的前情（狀態列、所在的章節、表格的表頭）；大綱給 claude_code 模式的截斷說明與整合的 session 看「中間有什麼」。
# =====================================================================================================================
_HEADING_RE = re.compile(r"^(#{1,4}\s+\S|【[^】]{1,40}】|={3,}\s*\S)")
_RECORD_RE = re.compile(r"^(---(\s.*)?$|\s{0,4}▸\s|[LETW]\d+\s|#\d+\s|\d+[.)]\s|[-*•]\s|>\s*\d+→)")
_TABLE_RE = re.compile(r"^\s*\|")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}")
_NUMBERED_RE = re.compile(r"^[>*\s]{0,3}\s*\d+→")   # view_file、result_view、result_grep 的「  120→內容」：判斷結構時看行號後面的內容


def _content(line):
    return _NUMBERED_RE.sub("", line, count=1)


def boundary_strength(lines, i):
    """在第 i 行（0-based）之前切開的合適程度：4 章節標題、3 一筆紀錄的開頭、2 空行之後／縮排結束／表格的一列、1 一般的行、
    0 縮排區塊的中間（YAML 的一則訊息、多行的紀錄）。附了行號的行（`  120→內容`）看行號後面的內容。"""
    if i <= 0 or i >= len(lines):
        return 4
    cur, prev = _content(lines[i]), _content(lines[i - 1])
    if not cur.strip():
        return 1
    if _HEADING_RE.match(cur) or (not cur[0].isspace() and cur.rstrip().endswith("：") and len(cur) <= 160):
        return 4
    if _TABLE_RE.match(cur):
        return 2 if _TABLE_RE.match(prev) else 3
    if _RECORD_RE.match(cur):
        return 3
    if not prev.strip():
        return 2
    if not cur[0].isspace() and prev[:1].isspace():
        return 2
    if cur[0].isspace():
        return 0
    return 1


def chunk_lines(lines, max_chars):
    """原文 → 段落 [(開始, 結束)]（0-based、不含結束）：每段不超過 max_chars 字（單行就超過的那一行自己一段）。切點選在這一段
    後 40% 裡最合適的邊界（boundary_strength），一樣合適的選後面的（每段盡量裝滿）。"""
    n, out, start = len(lines), [], 0
    while start < n:
        size, end = 0, start
        while end < n and size + len(lines[end]) + 1 <= max_chars:
            size += len(lines[end]) + 1
            end += 1
        if end >= n:
            out.append((start, n))
            break
        if end == start:
            out.append((start, start + 1))
            start += 1
            continue
        lo = start + max(1, int((end - start) * 0.6))
        cut = max(range(lo, end + 1), key=lambda i: (boundary_strength(lines, i), i))
        out.append((start, cut))
        start = cut
    return out


def chunk_context(lines, start):
    """從第 start 行（0-based）開始的這一段，讀之前要知道的幾行：第一行（狀態列）、最近的章節標題、表格的表頭（這一段從表格中間開始時）。
    回傳 0-based 行號的清單（由小到大）。"""
    if start <= 0:
        return []
    ctx = {0}
    for j in range(start - 1, 0, -1):
        if lines[j].strip() and boundary_strength(lines, j) == 4:
            ctx.add(j)
            break
    if start < len(lines) and _TABLE_RE.match(lines[start]):
        j = start
        while j > 0 and _TABLE_RE.match(lines[j - 1]):
            j -= 1
        if j < start:
            ctx.add(j)
            if j + 1 < start and _TABLE_SEP_RE.match(lines[j + 1]):
                ctx.add(j + 1)
    return sorted(ctx)


def outline(lines, limit=30):
    """原文的大綱：每個章節標題 → (行號 1-based, 標題, 這一節有幾行)；沒有章節標題回空清單。超過 limit 個只留前 limit 個。"""
    heads = [i for i in range(1, len(lines)) if lines[i].strip() and boundary_strength(lines, i) == 4]
    out = []
    for k, i in enumerate(heads[:limit]):
        nxt = heads[k + 1] if k + 1 < len(heads) else len(lines)
        out.append((i + 1, clip(lines[i].strip()), nxt - i))
    return out
