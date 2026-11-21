"""判斷節點的原文與核對（新架構第 3 步 3b；〈新架構討論紀錄〉第 4 節〈第 3 步 3b〉的 B）。流程在 agent_core/mid.py（Worker._judgment）。

- 原文（sources）：判斷節點依賴的節點，每個實例最後一次嘗試是一份（#編號）。行由程式照收據從檔案讀：search_text 命中的行與前後行
  （收據的 options.context）、view_file 看的那一段；每行有檔案、行號、內容、是不是命中的行（view_file 是 --around 的那一行）、
  含幾個不同的字（search_text --rank 的 words）。讀原文不靠解析工具給模型的文字（那份只列前幾筆，收據記全部）。
- 交給模型的原文（select、render）最多 MID_JUDGE_CHARS 字：先放含最多個不同的字的命中（前後行跟著它），放不下的寫明省略了幾行、
  在哪些檔案；照原文、檔案、行號排。
- 核對（check_line、check_params）：挑的行的片段要一字不改地在那份原文交給模型的某一行裡（比對時兩邊都不看格式：全形半形、
  Markdown 的 *、`、表格的 |、空白；模型抄的時候常拿掉這些）；片段可以是同一行裡照順序的幾段（用 | 或 … 分開：抄表格時跳過中間的格子）。
  整行內容由程式從原文填（以原文為準）；指定的原文沒有、這次的其他原文剛好一行有，以原文為準；片段對到好幾行（內容一樣的行）時用模型寫的
  行號選，行號要是對到的那幾行之一；對到之前的判斷挑過的行就是那一行（不算沒過）。分支的參數要在原文裡（搜尋的字原樣出現在這次的原文
  或之前挑過的行、檔案是原文裡的檔案、行號是那個檔案列出的行）。
"""
import re
import unicodedata

from . import prompt_files
from .config import MID_JUDGE_CHARS, MID_JUDGE_LINE_CHARS

READERS = ("search_text", "view_file")      # 判斷節點讀得懂的工具（照收據讀原文）
PARAM_TYPES = ("words", "path", "line")     # 分支的參數：搜尋的字（清單）、原文裡的檔案、那個檔案列出的行號
WORD = re.compile(r"^[\w./:@~-]+(?: [\w./:@~-]+)*$")   # 搜尋的一個字（或英文的詞組，中間一個空白）：沒有 |、括號與其他正規表示式的符號（. 在 grep 是任意字元，不影響找到）
_NUMBERED = re.compile(r"^\s*>?\s*\d+\s*→")   # 模型抄片段時連行號一起抄的「  754→」
_SPLIT = re.compile(r"[、,，;；\n]+")          # 搜尋的字用「、」分開（英文的詞組裡的空白不分）
_QUOTES = "\"'`「」『』“”‘’"
ROW_COST = 8                                # 一行除了內容之外的字（行號、→、換行）


def _i(key, /, **fields):
    """prompts/mid/inputs.md 的一則（交給判斷的原文與沒過核對的說明）。"""
    return prompt_files.load("mid/inputs.md", key, **fields)


def norm(s):
    return " ".join(str(s or "").split())


def plain(s):
    """比對片段用：全形半形統一（NFKC）、拿掉 Markdown 的 *、`、表格的 | 與空白（縮排、格子前後）。"""
    return re.sub(r"[\s*`|]+", "", unicodedata.normalize("NFKC", str(s or "")))


def _pieces(quote):
    """片段照 | 與 …（...）分成幾段（抄表格時跳過中間的格子、或省略中間的字），每一段比對用的寫法；空的段不算。"""
    return [k for k in (plain(x) for x in re.split(r"\||…|\.\.\.", unicodedata.normalize("NFKC", quote))) if k]


def _in_order(pieces, text):
    pos = 0
    for k in pieces:
        pos = text.find(k, pos)
        if pos < 0:
            return False
        pos += len(k)
    return True


def _file_lines(path, cache):
    """檔案的每一行（照 \\n 分，行號跟 grep 一樣）；讀不到回 None。"""
    if path not in cache:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            cache[path] = [ln.rstrip("\r") for ln in lines]
        except OSError:
            cache[path] = None
    return cache[path]


def _clip(text):
    return text if len(text) <= MID_JUDGE_LINE_CHARS else text[:MID_JUDGE_LINE_CHARS] + f"…（這一行共 {len(text)} 字，截斷）"


def rows(tool, receipt, cache):
    """一份收據 → 原文的行 [{"path", "line", "text", "hit", "words"}]（照檔案、行號；path 是收據的絕對路徑）。
    沒有結果（empty、error）或讀不到的檔案沒有行。"""
    out = []
    if not receipt or receipt.get("status") != "pass":
        return out
    if tool == "search_text":
        ctx = int((receipt.get("options") or {}).get("context") or 0)
        by_file = {}
        for it in receipt.get("items") or []:
            if it.get("path") and it.get("line"):
                by_file.setdefault(it["path"], {})[it["line"]] = it.get("words")
        for path in sorted(by_file):
            lines = _file_lines(path, cache)
            if lines is None:
                continue
            hits = by_file[path]
            want = sorted({x for ln in hits for x in range(max(1, ln - ctx), ln + ctx + 1) if x <= len(lines)})
            out += [{"path": path, "line": x, "text": _clip(lines[x - 1]), "hit": x in hits, "words": hits.get(x)} for x in want]
    elif tool == "view_file":
        around = receipt.get("around")
        for it in receipt.get("items") or []:
            lines = _file_lines(it.get("path") or "", cache)
            if lines is None or not it.get("from") or not it.get("to"):
                continue
            out += [{"path": it["path"], "line": x, "text": _clip(lines[x - 1]), "hit": x == around, "words": None}
                    for x in range(it["from"], min(it["to"], len(lines)) + 1)]
    return out


def select(sources, budget=MID_JUDGE_CHARS):
    """每一行標 shown（交給模型）：命中的行照含幾個不同的字（多的先）、原文與檔案的順序放，前後行跟著它的命中；
    view_file（看某一段）整段一起，從標 > 的那一行往外放。放到 budget 字為止。回傳 (放了幾個字, 省略的行 {原文: {檔案: 行數}})。"""
    blocks = []                                    # (排序的鍵, [行])
    for si, src in enumerate(sources):
        rs = src["rows"]
        for r in rs:
            r["shown"] = False
        if src["tool"] == "view_file":
            center = next((k for k, r in enumerate(rs) if r["hit"]), 0)
            order = sorted(range(len(rs)), key=lambda k: (abs(k - center), k))
            blocks.append(((0, si, 0), [rs[k] for k in order]))
            continue
        ctx = src.get("context", 0)
        by_file = {}
        for r in rs:
            by_file.setdefault(r["path"], []).append(r)
        pos = 0
        for path, frs in by_file.items():
            for r in frs:
                if not r["hit"]:
                    continue
                pos += 1
                near = [x for x in frs if abs(x["line"] - r["line"]) <= ctx]
                blocks.append(((-(r["words"] or 0), si, pos), [r] + [x for x in near if x is not r]))
    used = 0
    for _, block in sorted(blocks, key=lambda b: b[0]):
        for r in block:
            if r["shown"]:
                continue
            cost = len(r["text"]) + ROW_COST
            if used + cost > budget:
                if block[0]["shown"] or not r["hit"]:
                    continue                       # 前後行放不下就不放，命中的行照樣看下一段
                break
            r["shown"] = True
            used += cost
    omitted = {}
    for src in sources:
        for r in src["rows"]:
            if not r["shown"]:
                omitted.setdefault(src["id"], {}).setdefault(r["file"], 0)
                omitted[src["id"]][r["file"]] += 1
    return used, omitted


def render(sources):
    """交給模型的原文：每份原文一節，檔案一小節，每行 `>  754→內容`（> 是命中的行）。"""
    out = []
    for src in sources:
        shown = [r for r in src["rows"] if r["shown"]]
        if not shown:
            continue
        out.append(_i("judge_source", source=src["id"], what=src["what"]))
        cur = None
        for r in shown:
            if r["file"] != cur:
                cur = r["file"]
                out.append(f"## {cur}")
            out.append(f"{'>' if r['hit'] else ' '}{r['line']:>5}→{r['text']}")
    return "\n".join(out)


def shown_files(sources):
    return sorted({r["file"] for s in sources for r in s["rows"] if r["shown"]})


def _find(rows, file, quote):
    """片段對到的行：先找指定的檔案，那個檔案沒有就找全部；整段對不到時，照 | 與 … 分開的每一段照順序都在同一行也算。"""
    key, pieces = plain(quote), _pieces(quote)
    if not key:
        return []
    for match in (lambda t: key in t, lambda t: len(pieces) > 1 and _in_order(pieces, t)):
        found = [r for r in rows if r["file"] == file and match(plain(r["text"]))]
        found = found or [r for r in rows if match(plain(r["text"]))]
        if found:
            return found
    return []


def check_line(item, sources, picked=()):
    """模型挑的一行 → (核對過的行, None) 或 (None, 交回修的說明)。片段照原樣找，找不到再去掉外面的引號找；指定的原文沒有就找這次的
    其他原文，再沒有就找之前的判斷挑過的行（picked）；剛好一行就是它（行號寫錯也以原文為準），好幾行時用模型寫的行號選。"""
    sid = str(item.get("source") or "").strip()
    sid = sid if sid.startswith("#") else f"#{sid}"
    src = next((s for s in sources if s["id"] == sid), None)
    file = str(item.get("file") or "")
    quote = norm(_NUMBERED.sub("", str(item.get("quote") or "")))
    if src is None:
        return None, _i("reject_source", source=sid, sources="、".join(s["id"] for s in sources))
    if not quote:
        return None, _i("reject_empty_quote", source=sid, file=file)
    def look(rows):
        return _find(rows, file, quote) or _find(rows, file, quote.strip(_QUOTES))
    others = [r for s in sources if s is not src for r in s["rows"] if r["shown"]]
    found = look([r for r in src["rows"] if r["shown"]]) or look(others) or look(list(picked))
    try:
        line = int(item.get("line") or 0)
    except (TypeError, ValueError):
        line = 0
    if len(found) > 1:
        found = [r for r in found if r["line"] == line] or found
    if len(found) == 1:
        r = found[0]
        rid = next((s["id"] for s in sources if any(x is r for x in s["rows"])), r.get("source", sid))
        return {"source": rid, "path": r["path"], "file": r["file"], "line": r["line"], "text": r["text"],
                "label": str(item.get("label") or ""), "quote": quote}, None
    if found:
        where = "、".join(f"{r['file']}:{r['line']}" for r in found[:8])
        return None, _i("reject_ambiguous", quote=quote, where=where)
    return None, _i("reject_line", quote=quote, source=sid, file=file)


def words_of(value):
    """搜尋的字：清單或用「、」分開的一串 → 去掉引號、空的與重複的（中間的空白合成一個）。"""
    raw = value if isinstance(value, list) else _SPLIT.split(str(value or ""))
    out = []
    for x in raw:
        w = norm(x).strip(_QUOTES).strip()
        if w and w not in out:
            out.append(w)
    return out


def check_params(branch, params, sources, picked=()):
    """分支的參數 → ({名稱: 值}, [交回修的說明])。搜尋的字要原樣在原文交給模型的行或之前的判斷挑過的行（picked）裡；
    檔案是這次原文的檔案；行號是那個檔案列出的行。"""
    shown = [r for s in sources for r in s["rows"] if r["shown"]]
    out, bad = {}, []
    for p in branch.get("params") or []:
        name, v = p["name"], (params or {}).get(p["name"])
        if p["type"] == "words":
            items = words_of(v)
            miss = [w for w in items if not WORD.match(w) or w.startswith("-") or not any(w in r["text"] for r in shown + list(picked))]
            if not items:
                bad.append(_i("reject_param_empty", name=name))
            elif miss:
                bad.append(_i("reject_param_words", name=name, missing="、".join(miss)))
            else:
                out[name] = items
        elif p["type"] == "path":
            files = {r["file"] for r in shown}
            if str(v or "") in files:
                out[name] = str(v)
            else:
                bad.append(_i("reject_param_path", name=name, value=str(v or "")))
        else:
            file = next((out.get(q["name"]) for q in branch.get("params") or [] if q["type"] == "path"), None)
            lines = {r["line"] for r in shown if r["file"] == file}
            try:
                n = int(str(v).strip())
            except ValueError:
                n = None
            if n in lines:
                out[name] = n
            else:
                bad.append(_i("reject_param_line", name=name, value=str(v), file=file or "（檔案沒有通過核對）"))
    return out, bad
