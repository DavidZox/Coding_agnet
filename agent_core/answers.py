"""依報告回答的核對（4-2，agent_core/orchestrator.py）與子工作階段收尾的核對（第 5 步，agent_core/sub.py）共用的部分：
出處的寫法（檔案:行號、#編號）、照收據從檔案讀那幾行、answers 每一項的核對（answer_problems）、相近的寫法、顯示用的出處。
兩邊只差「出處要在哪裡」：主對話的出處在這一回合的報告與自己執行過的工具結果，子工作階段的出處在它自己執行過的工具結果（cited 由呼叫的一方給）。"""
import difflib
import json
import os
import re

from . import prompt_files
from .extract import missing_tokens

REF = re.compile(r"[\w./-]*\w\.[A-Za-z][A-Za-z0-9]*:\d+")      # 出處：檔案:行號（副檔名是字母開頭，時間、IP 不算）
CITE = re.compile(r"(" + REF.pattern + r")(?:\s*[-~～]\s*(\d+))?")    # 出處：檔案:行號，可以是一段（a.py:31-35）
ID = re.compile(r"#(\d+)")
_WORD = re.compile(r"[A-Za-z_][\w./-]*[\w]")


def why(key, /, **fields):
    """prompts/harness/domain.md 的一則：answers 沒有通過核對的原因（why_*）與交回修的寫法。"""
    return prompt_files.load("harness/domain.md", key, **fields)


def norm(text):
    return " ".join(str(text or "").split()).lower()


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def line_of(path, n, cache):
    """檔案的第 n 行（去掉前後空白）；讀不到或沒有這一行回 None。"""
    if path not in cache:
        text = read(path)
        cache[path] = text.split("\n") if text else None
    lines = cache[path]
    return lines[n - 1].strip() if lines and 1 <= n <= len(lines) else None


def rel(path, cwd):
    cwd = os.path.abspath(cwd or ".")
    return os.path.relpath(path, cwd) if path.startswith(cwd.rstrip("/") + "/") else path


def near(bad, evidence):
    """對不上的字在出處那幾段裡相近的寫法（拼錯一兩個字母的檔名、名稱）：交回修的時候附上，模型知道要改成什麼。"""
    words = sorted({x for w in _WORD.findall(evidence) for x in [w] + w.split("/") if x})   # 路徑也拆成每一段（回答常只寫檔名）
    out = []
    for w in bad:
        out += [x for x in difflib.get_close_matches(w, words, n=2, cutoff=0.8) if x != w and x not in out]
    return out[:4]


def ref_label(ref):
    """顯示用的出處：只留 檔案:行號（一段的寫成 a.py:31-35）或 #編號（模型常把報告的整行抄進 refs）；看不懂的照原樣。"""
    m = CITE.search(ref)
    if m:
        return m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
    m = ID.search(ref)
    return f"#{m.group(1)}" if m else ref


def sections(report):
    """報告切成節：開頭（問題、子目標、參數）與每一個 ## 到下一個 ##。"""
    out, cur = [], []
    for ln in report.split("\n"):
        if ln.startswith("## ") and cur:
            out.append("\n".join(cur))
            cur = []
        cur.append(ln)
    if cur:
        out.append("\n".join(cur))
    return out


def span(match):
    """CITE 的一筆 → (路徑, 第一行, 最後一行)：一段最多 20 行，寫反了或太長的當成只有第一行。"""
    path, line = match.group(1).rsplit(":", 1)
    first = int(line)
    last = int(match.group(2)) if match.group(2) and 0 <= int(match.group(2)) - first <= 20 else first
    return path, first, last


def rows_from_archives(archives, path, first, last, cwd):
    """這幾份存檔（工具結果的 .md）的收據裡有沒有 path:first～last（search_text 命中的行、view_file 看的那一段、code_ast_reader 的定義與
    呼叫）→ (那幾行（程式從檔案讀，寫成 檔案:行號：內容）, 那幾份存檔的原文)。路徑的結尾一樣就算。"""
    rows, texts, cache = [], [], {}
    for archive in archives:
        receipt = load_json(archive[:-3] + ".receipt.json")
        hits = []
        for it in (receipt or {}).get("items") or []:
            p = str(it.get("path") or "")
            if not (p == path or p.endswith("/" + path)):
                continue
            if isinstance(it.get("line"), int) and first <= it["line"] <= last:
                hits.append((p, it["line"]))
            elif isinstance(it.get("from"), int) and isinstance(it.get("to"), int):
                hits += [(p, n) for n in range(max(first, it["from"]), min(last, it["to"]) + 1)]
        for p, n in dict.fromkeys(hits):
            text = line_of(p, n, cache)
            if text is not None:
                rows.append(f"{rel(p, cwd)}:{n}：{text}")
        if hits:
            texts.append(read(archive))
    return rows, texts


def answer_problems(items, answers, cited, allowed, source, unknown=None):
    """answers 每一項的核對（G4 的步驟 7）→ {項目編號: [沒過的原因]}；全部過了是空的。
    items：要回答的項目；answers：parse 過的每一項 {item, status, text, refs}；cited(ref) → (種類, 對到的行, 那幾段的文字, 行號)，
    種類是 line／id／unknown（不在該在的地方）／form（寫法看不懂）；allowed：本來就有的字（問題、項目、子目標），不核對；
    source：全部的原文（名稱的寫法看它）；unknown(ref)：出處不在該在的地方時的說法（子工作階段換成自己的，預設是 why_ref_unknown）。"""
    got = {a["item"]: a for a in answers or [] if 1 <= a["item"] <= len(items)}
    out = {}
    for k, _item in enumerate(items, 1):
        a, bad_why = got.get(k), []
        if a is None:
            bad_why.append(why("why_missing"))
        elif a["status"] == "not_found":
            if not a["text"]:
                bad_why.append(why("why_no_reason"))
        else:
            if not a["refs"]:
                bad_why.append(why("why_no_refs"))
            evidence, lines = list(a["refs"]), []
            for ref in a["refs"]:
                kind, _, texts, nums = cited(ref)
                if kind == "form":
                    bad_why.append(why("why_ref_form", ref=ref))
                elif kind == "unknown":
                    bad_why.append(unknown(ref) if unknown else why("why_ref_unknown", ref=ref))
                evidence += texts
                lines += nums
            if len(evidence) > len(a["refs"]):
                text = "\n".join(evidence)
                bad = missing_tokens(a["text"], text, source, allowed, refs=lines)
                if bad:
                    close = near(bad, text)
                    bad_why.append(why("why_tokens", tokens="、".join(bad)) + (why("why_near", near="、".join(close)) if close else ""))
        if bad_why:
            out[k] = bad_why
    return out
