"""工具回傳的提煉：程式切段 → 每段一個 worker 摘出跟問題有關的事實（附原文的行號）→ 整合成交給主對話的重點；每一步寫的名稱與數值由程式
核對是否真的在引用的原文裡，全部的中間產物存檔。summarize_tool_result（大量的工具回傳）與 result_recall（回存檔依問題重新提煉）共用。

1. 切段（_results_common.chunk_lines）：依原文的結構（章節、一筆一筆的紀錄、空行）切成每段不超過 EXTRACT_CHUNK_CHARS 字，每段附讀它要知道的
   前情（狀態列、所在的章節、表格的表頭）。全部放得進一段時不分工（direct）：一次呼叫直接寫結果，跟以前一樣只花一次模型呼叫。
2. Workers（merge）：每段一個乾淨的 session，只讀那一段（每行前面是原文的行號），摘出跟使用者的目標／問題有關的事實與錯誤，每條附行號。
   程式核對（missing_tokens）：每條寫的數字與名稱要在它引用的那幾行裡（前後 EVIDENCE_SPAN 行，加上縮排的上層——YAML、巢狀的輸出名稱常在
   上幾行）；對不上的不交給整合，記在存檔裡。段數超過 EXTRACT_MAX_CHUNKS 時依問題裡的名稱、數字出現在哪幾段挑著讀，沒讀的行號範圍由程式
   寫進「未涵蓋」——不會假裝讀過。
3. 整合（synthesizer）：拿各段核對過的事實＋那幾行的原文（程式附上）＋原文的開頭與大綱，寫成交給主對話的重點：回答、相關事實（附行號）、
   錯誤、未涵蓋、之後可能想知道的、檢索清單的描述、還需要的舊存檔。程式再核對一次：寫了原文沒有的名稱或數值 → 帶著問題請它修一次；
   還是對不上的事實拿掉，回答裡找不到的字由呼叫端標明。整合失敗（回覆不是 JSON）時改由程式把各段的事實排成清單，不丟掉 worker 的結果。
4. 存檔（JobStore，logs/extract_jobs/<編號>/）：job.json（切段、每段的結果與核對、整合、最後的重點）、calls.jsonl（每次模型呼叫的
   prompt 與原文回覆）、events.jsonl（進度）。"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from skills_system.scripts import _results_common as rc
from .config import (
    EXTRACT_CHUNK_CHARS,
    EXTRACT_EVIDENCE_CHARS,
    EXTRACT_JOBS_DIRNAME,
    EXTRACT_JOBS_KEEP,
    EXTRACT_MAX_CHUNKS,
    EXTRACT_PARALLEL,
    EXTRACT_SUMMARY_MAX_CHARS,
    EXTRACT_SUMMARY_MIN_CHARS,
    EXTRACT_SYNTH_PREDICT,
    EXTRACT_WORKER_FACTS,
    EXTRACT_WORKER_PREDICT,
    NUM_CTX,
    TOOL_USE_INDEX_HINT_TARGET,
)
from . import prompt_files
from .jobstore import JobStore
from .schemas import EXTRACT_WORKER_SCHEMA, TOOL_SUMMARY_SCHEMA

LINE_MAX_CHARS = 2000          # 交給模型的一行最多幾個字（更長的截斷並註明；只有一行的那一段放寬到整段的篇幅）
EVIDENCE_SPAN = 2              # 核對時引用的行前後各多看幾行（模型的行號常差一兩行）
EVIDENCE_LINES_PER_FACT = 6    # 交給整合的每條事實最多附幾行原文
EVIDENCE_CHILDREN = 12         # 引用的那一行底下縮排更深的下層，最多算幾行
PROGRESS_MARK = "📑"           # 進度訊息的開頭（Web 右欄的「⏳ 執行進度」；不能用 📊🧭🔧💭▶✅❌🧩，那幾個會切換數據分析面板）


def read_prompt(name, **fields):
    """prompts/extract/<name> 整份，{欄位} 換成值（prompt 裡有 JSON 的大括號，不用 str.format）。"""
    return prompt_files.load(f"extract/{name}", **fields)


def _x(key, /, **fields):
    """prompts/extract/inputs.md 的一則：交給 worker 與整合的 user 訊息裡程式組進去的標籤與說明。"""
    return prompt_files.load("extract/inputs.md", key, **fields)


# =====================================================================================================================
# 核對：一句話寫的數字與名稱，是否真的在引用的原文裡
# =====================================================================================================================
_REF_TEXT = re.compile(r"[（(]?\s*(?:#\d+\s*)?(?:行|第|lines?\b|L(?=\d))\s*[:：]?\s*\d+(?:\s*[-~～–,，、]\s*\d+)*\s*行?\s*[)）]?", re.I)
# 句子裡夾的行號（模型常把「(lines: 34)」「（行 40）」寫進句子）：行號另外有欄位、排版時另外附，句子裡的拿掉
_INLINE_REF = re.compile(r"\s*[（(]\s*(?:#\d+\s*)?(?:lines?|行|L)\s*[:：]?\s*\d+(?:\s*[-~～–,，、]\s*\d+)*\s*[)）]", re.I)
_NUM = re.compile(r"(?<![A-Za-z_\d.])\d+(?:\.\d+)?")
_ANY_NUM = re.compile(r"\d+(?:\.\d+)?")
_IDENT = re.compile(r"[A-Za-z_/~][A-Za-z0-9_/.\-:~]*")
_LINE_SPEC = re.compile(r"(\d+)(?:\s*[-~～–]\s*(\d+))?")
# 總數的寫法（共 7 台、總共有 12 個、合計 3 筆）：原文要有這個數字（不算名稱裡的，例如 amr_07 的 7）——實測 26b 列了 7 台卻寫「共有 6 台」
_COUNT = re.compile(r"(?:總共|共計|合計|一共|共)\s*(?:有\s*)?(\d+)\s*(?:台|個|筆|項|則|次|條|件|輛|位|段|行|種)")


def _num_values(text):
    out = set()
    for m in _ANY_NUM.finditer(text or ""):
        try:
            out.add(float(m.group()))
        except ValueError:
            continue
    return out


def missing_tokens(text, evidence, source, allowed="", counts=(), refs=()):
    """text 裡對不上的字（清單）：
    - 數字要在 evidence（引用的那幾行）裡，寫法不同但數值一樣也算（15.5＝15.50）；
    - 看起來像名稱的英數字要在 evidence 裡：含底線、斜線、點、冒號的（tb_1、/odom、rmf_sim、exp_5090），或字母加數字、而原文別的地方有
      同樣寫法的（引用的行沒有＝寫錯對象；原文有 tb1～tb12、寫了 tb13＝編出來的）。只有字母加數字、原文完全沒有這種寫法的（ROS2）是
      一般的詞，不核對；
    - allowed（使用者的問題、執行的指令）裡本來就有的字不核對（「電量低於 20%」的 20）；10 以下的整數不核對（序號、自己數的幾個）。
    - 總數（共 7 台、合計 3 筆）不管大小都核對，而且要是原文裡單獨出現的數字（原文沒有寫總數＝模型自己數的，數錯過）；counts 是程式
      自己數的數量（整合列了幾條核對過的事實），等於它也算有根據。
    行號的寫法（行 40、第 40 行、#12 行 40、lines: 40）先拿掉，不算數字；refs（這一條引用的行號）裡的數字也不算（模型常把行號寫進句子）。
    寧可漏掉也不誤擋（同 claims.py 的原則）。"""
    t = _REF_TEXT.sub(" ", str(text or ""))
    ev_low, src_low, ok_low = (evidence or "").lower(), (source or "").lower(), (allowed or "").lower()
    ev_nums, ok_nums = _num_values(evidence), _num_values(allowed)
    bad = []
    for m in _NUM.finditer(t):
        s = m.group()
        v = float(s)
        if (v.is_integer() and abs(v) < 10) or s in evidence or v in ev_nums or v in ok_nums or (v.is_integer() and int(v) in refs):
            continue
        bad.append(s)
    standalone = {float(x.group()) for x in _NUM.finditer(evidence or "")} | ok_nums | {float(c) for c in counts}
    for m in _COUNT.finditer(t):   # 總數：10 以下也核對，而且要是原文裡單獨出現的數字
        if float(m.group(1)) not in standalone:
            bad.append(f"共 {m.group(1)}")
    for m in _IDENT.finditer(t):
        w = m.group().rstrip(".:-~")
        if len(w) < 2 or not re.search(r"[A-Za-z0-9]", w):
            continue
        wl = w.lower()
        if wl in ev_low or wl in ok_low:
            continue
        if re.search(r"[_/.:]", w):
            bad.append(w)
        elif re.search(r"\d", w):
            pre = re.match(r"[A-Za-z]+", w)
            if wl in src_low or (pre and re.search(rf"(?<![a-z]){re.escape(pre.group().lower())}\d", src_low)):
                bad.append(w)
    return list(dict.fromkeys(bad))


def parse_lines(spec, n_lines):
    """「120」「120-125」「120、130」「行 120」→ 行號（1-based，限制在 1..n_lines，由小到大）；看不懂回空清單。"""
    out = set()
    for m in _LINE_SPEC.finditer(str(spec or "")):
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if b < a:
            a, b = b, a
        b = min(b, a + 5000)
        out.update(range(max(1, a), min(n_lines, b) + 1))
    return sorted(out)


def lines_text(nums):
    """[40, 41, 42, 50] → 「40-42、50」。"""
    out, start, prev = [], None, None
    for n in list(nums) + [None]:
        if start is None:
            start = prev = n
            continue
        if n is not None and n == prev + 1:
            prev = n
            continue
        out.append(f"{start}-{prev}" if prev != start else f"{start}")
        start = prev = n
    return "、".join(out)


def _indent(line):
    """行首的空白有幾個（YAML 清單的「- 」不算空白：「- name: tb6」是它下面「  battery: 41」的上層）。"""
    return len(line) - len(line.lstrip(" \t"))


def evidence_lines(lines, nums, span=EVIDENCE_SPAN):
    """引用的行（1-based）→ 核對用的行號：前後 span 行（不跨到別的紀錄：遇到一筆紀錄的開頭、表格的另一列、空行就停——不然 tb6 那一行
    前後兩行可能是 tb5、tb7 的值），加上縮排的上層（往上找縮排比較少的行，最多 4 層：巢狀的輸出名稱常在上面幾行）與縮排更深的下層
    （最多 EVIDENCE_CHILDREN 行：引用一筆紀錄的開頭時，它底下的欄位也算）。"""
    out = set()
    n = len(lines)
    starts = lambda k: rc.boundary_strength(lines, k - 1) >= 2   # 第 k 行（1-based）是另一筆紀錄的開頭
    for x in nums:
        if not 0 < x <= n:
            continue
        out.add(x)
        for k in range(x + 1, min(n, x + span) + 1):
            if starts(k):
                break
            out.add(k)
        for k in range(x - 1, max(1, x - span) - 1, -1):
            if starts(k + 1):
                break
            out.add(k)
        base = _indent(lines[x - 1])
        for k in range(x + 1, min(n, x + EVIDENCE_CHILDREN) + 1):   # 縮排更深的下層（引用「- name: tb6」那一行時，它下面的電量也算）
            if not lines[k - 1].strip() or _indent(lines[k - 1]) <= base:
                break
            out.add(k)
        i, level = x - 1, base
        for _ in range(4):
            if level <= 0:
                break
            j = i - 1
            while j >= 0 and (not lines[j].strip() or _indent(lines[j]) >= level):
                j -= 1
            if j < 0:
                break
            out.add(j + 1)
            i, level = j, _indent(lines[j])
    return sorted(out)


_STOP_BIGRAMS = set("什麼 哪些 哪個 目前 現在 一下 幫我 請問 是否 有沒 沒有 可以 告訴 看看 查一 一個 為什 怎麼 多少 這個 那個 之前 剛剛 結果 執行 系統 回傳".split())


def question_terms(text):
    """挑段落用的詞：問題裡的英數字名稱與數字（2 字以上）、中文的兩字詞（去掉「什麼」「目前」這類問句的字）。"""
    low = str(text or "").lower()
    terms = {w.rstrip(".:-") for w in re.findall(r"[a-z0-9_/.\-:]{2,}", low)}
    for seg in re.findall(r"[一-鿿]{2,}", str(text or "")):
        terms.update(seg[i:i + 2] for i in range(len(seg) - 1))
    return sorted(t for t in terms if len(t) >= 2 and t not in _STOP_BIGRAMS)


def parse_json(text):
    """模型的回覆 → dict；外面多了說明文字時取最外層的 {…}。不是 JSON 物件回 None。"""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", text or "", re.S)
        try:
            data = json.loads(m.group()) if m else None
        except ValueError:
            data = None
    return data if isinstance(data, dict) else None


def cited_items(value):
    """facts／errors → [{"text", "lines", "record"}]：模型可能給字串（舊的格式）或缺欄位的物件。"""
    out = []
    for x in value if isinstance(value, list) else ([value] if value else []):
        if isinstance(x, dict):
            text = _INLINE_REF.sub("", " ".join(str(x.get("text") or "").split())).strip()
            if text:
                out.append({"text": text, "lines": str(x.get("lines") or "").strip(), "record": str(x.get("record") or "").strip().lstrip("#")})
        elif str(x).strip():
            out.append({"text": _INLINE_REF.sub("", " ".join(str(x).split())).strip(), "lines": "", "record": ""})
    return out


def _cut(line, n=LINE_MAX_CHARS):
    return line if len(line) <= n else line[:n] + f"…（這一行共 {len(line)} 字，只列前 {n} 字）"


# =====================================================================================================================
# 一次提煉
# =====================================================================================================================
class Extraction:
    """一次提煉。sources＝[{"rid", "label", "lines", "background"}]（rid：存檔編號字串；lines：原文的每一行；background：這一份的背景，
    給 recall 用）；purpose＝錨點（使用者的目標＋這一步的目的，或 recall 的問題與背景）；catalog／allowed_ids＝工具使用檢索清單（給
    related_records）；question＝挑段落用的問題文字；allowed＝不核對的字（使用者的話、執行的指令）。run() 回傳結果 dict（見 run）。"""

    def __init__(self, agent, kind, sources, purpose, catalog="", allowed_ids=(), question="", allowed=""):
        self.agent = agent
        self.kind = kind
        self.sources = sources
        self.purpose = purpose
        self.catalog = catalog
        self.allowed_ids = set(allowed_ids)
        self.terms = question_terms(question)
        self.allowed = allowed or purpose
        self.store = JobStore(os.path.join(agent.script_dir, "logs", EXTRACT_JOBS_DIRNAME))
        self.lock = threading.Lock()
        self.texts = ["\n".join(s["lines"]) for s in sources]
        self.all_text = "\n".join(self.texts)
        self.jid = None

    # ---------------------------------------------------------------- 共用
    def note(self, text):
        """進度：印出、記進 events.jsonl、交給畫面（Web 執行工具時設的 progress_callback，推到右欄）。"""
        with self.lock:
            print(text)
            if self.jid:
                self.store.append(self.jid, "events.jsonl", {"text": text})
            cb = getattr(self.agent, "progress_callback", None)
            if cb:
                try:
                    cb(text)
                except Exception:   # noqa: BLE001  畫面的問題不能中斷提煉
                    pass

    def _call(self, role, system, user, schema, predict, chunk=None):
        """呼叫一次模型（perf.jsonl 的分類：direct 是 tool_summary／recall，其他加上角色），回傳 (data, raw, error)；每一次都記進 calls.jsonl。"""
        t0 = time.time()
        raw, err = "", None
        try:
            res = self.agent._timed_chat(
                self.kind if role == "direct" else f"{self.kind}_{role}", perf={"job": self.jid, "chunk": chunk},
                model=self.agent.summary_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                format=schema, options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": predict}, think=False)
            raw = (res["message"]["content"] or "").strip()
        except Exception as e:   # noqa: BLE001  一次呼叫失敗只影響這一段，記下來交給整合與呼叫端
            err = f"{type(e).__name__}: {e}"
        data = parse_json(raw) if raw else None
        if data is None and not err:
            err = "回覆不是 JSON" if raw else "沒有回覆"
        self.store.append(self.jid, "calls.jsonl", {"role": role, "chunk": chunk, "system": system, "user": user, "response": raw,
                                                    "error": err if data is None else None, "ms": round((time.time() - t0) * 1000)})
        return data, raw, (err if data is None else None)

    def _src_index(self, record):
        """record（存檔編號）→ 第幾份；只有一份或對不上時回 None。"""
        if len(self.sources) == 1:
            return 0
        r = str(record or "").strip().lstrip("#")
        for i, s in enumerate(self.sources):
            if str(s["rid"]) == r:
                return i
        return None

    def _ground(self, item, si=None, within=None):
        """一條事實或錯誤 → (核對過的 item 或 None, 對不上的字)。si＝哪一份（None：依 record 找，找不到就每一份都試）；within＝(開始, 結束)
        這一段的範圍（worker 的事實只能引用自己那一段附近的行）。沒寫行號、或行號不在範圍裡：在範圍（或整份）裡找出現那些字的行補上。"""
        cands = [si] if si is not None else ([self._src_index(item.get("record"))] if self._src_index(item.get("record")) is not None
                                             else list(range(len(self.sources))))
        best = None
        for i in cands:
            lines = self.sources[i]["lines"]
            nums = parse_lines(item.get("lines"), len(lines))
            if within:
                nums = [x for x in nums if within[0] - EVIDENCE_SPAN < x <= within[1] + EVIDENCE_SPAN]
            if nums:   # 寫了行號：只認那幾行（與上下層）。對不上＝寫錯對象或數值，不在別的地方幫它找
                ev = "\n".join(lines[x - 1] for x in evidence_lines(lines, nums))
                bad = missing_tokens(item["text"], ev, self.texts[i], self.allowed, refs=set(nums))
                if not bad:
                    return dict(item, src=i, nums=nums), []
            else:      # 沒寫行號：字都在這個範圍裡就收，補上出現那些字的行（最多 3 行；沒有可以核對的字就不附行號）
                lo, hi = within if within else (0, len(lines))
                bad = missing_tokens(item["text"], "\n".join(lines[lo:hi]), self.texts[i], self.allowed)
                if not bad:
                    toks = [w.lower() for w in re.findall(r"[A-Za-z0-9_/.\-:]{2,}", _REF_TEXT.sub(" ", item["text"]))]
                    hit = [k + 1 for k in range(lo, hi) if toks and any(w in lines[k].lower() for w in toks)][:3]
                    return dict(item, src=i, nums=hit), []
            if best is None or len(bad) < len(best):
                best = bad
        return None, best or []

    def _ground_all(self, items, si=None, within=None):
        kept, dropped = [], []
        for it in items:
            g, bad = self._ground(it, si, within)
            if g:
                kept.append(g)
            else:
                dropped.append({"text": it["text"], "lines": it.get("lines"), "record": it.get("record"), "missing": bad})
        return kept, dropped

    # ---------------------------------------------------------------- 主流程
    def run(self):
        """回傳 {"data": 整合的結果（facts／errors 已核對、附 src 與 nums）或 None, "structured": bool, "raw": 模型最後的原文,
        "mode": direct／merge, "job": 編號, "chunks": 段數, "read": 讀了幾段, "notes": 程式寫的未涵蓋（沒讀到、失敗的段落）,
        "answer_missing": 回答裡在原文找不到的字, "dropped": 拿掉的事實數, "fallback": 整合失敗、由程式排各段事實}。"""
        t0 = time.time()
        rids = "-".join(str(s["rid"]) for s in self.sources)[:40]
        self.jid = self.store.new_id(f"{self.kind}_{rids}")
        total = sum(len(t) + 1 for t in self.texts)
        self.max_chars = max(EXTRACT_SUMMARY_MIN_CHARS, min(EXTRACT_SUMMARY_MAX_CHARS, total // 4))
        self.chunks = []
        for si, s in enumerate(self.sources):
            spans = rc.chunk_lines(s["lines"], EXTRACT_CHUNK_CHARS) or [(0, 0)]
            for k, (a, b) in enumerate(spans, 1):
                self.chunks.append({"id": len(self.chunks) + 1, "src": si, "k": k, "of": len(spans), "start": a, "end": b,
                                    "chars": sum(len(x) + 1 for x in s["lines"][a:b])})
        self.job = {"id": self.jid, "kind": self.kind, "status": "working", "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "model": self.agent.summary_model, "purpose": self.purpose,
                    "sources": [{"rid": s["rid"], "label": s["label"], "lines": len(s["lines"]), "chars": len(t)}
                                for s, t in zip(self.sources, self.texts)],
                    "chunks": [{k: c[k] for k in ("id", "src", "start", "end", "chars")} for c in self.chunks],
                    "summary_max_chars": self.max_chars}
        self.store.save(self.job)
        try:
            out = self._direct() if total <= EXTRACT_CHUNK_CHARS else self._merge()
            self.job["status"] = "done"
        except Exception as e:
            self.job.update(status="failed", error=f"{type(e).__name__}: {e}")
            raise
        finally:
            self.job["seconds"] = round(time.time() - t0, 1)
            self.store.save(self.job)
            self.store.prune(EXTRACT_JOBS_KEEP)
        out["job"] = self.jid
        return out

    def _background(self):
        return "\n".join(f"#{s['rid']}：{s['background']}" for s in self.sources if s.get("background"))

    def _catalog_block(self):
        return _x("catalog", catalog=self.catalog) + "\n\n" if self.catalog else ""

    def _synth_system(self):
        return read_prompt("synthesizer.md", max_chars=self.max_chars, hint_target=TOOL_USE_INDEX_HINT_TARGET)

    # ---------------------------------------------------------------- 一次寫完（原文放得進一段）
    def _direct(self):
        self.job["mode"] = "direct"
        blocks = []
        for s, t in zip(self.sources, self.texts):
            body = "\n".join(rc.numbered(i + 1, _cut(x)) for i, x in enumerate(s["lines"]))
            if len(self.sources) == 1:
                blocks.append(_x("direct_single", count=len(s['lines']), body=body))
            else:
                blocks.append(_x("direct_multi_item", rid=s['rid'], label=s['label'], count=len(s['lines']), body=body))
        bg = self._background()
        user = (f"{self.purpose}\n\n{self._catalog_block()}" + (_x("direct_background", background=bg) + "\n\n" if bg and len(self.sources) > 1 else "")
                + (_x("direct_multi_header") + "\n" if len(self.sources) > 1 else "") + "\n\n".join(blocks))
        data, raw, err = self._call("direct", self._synth_system(), user, TOOL_SUMMARY_SCHEMA, EXTRACT_SYNTH_PREDICT)
        if data is None:
            self.job["synth"] = {"error": err}
            return self._failed(raw, err)
        return self._finish(data, raw, notes=[])

    def _failed(self, raw, err):
        """沒有可以用的結果：模型有回覆但不是 JSON → raw 交給呼叫端照實轉交；沒有回覆（連線失敗、逾時）→ error。"""
        return {"data": None, "structured": False, "raw": raw or "", "error": None if raw else err, "mode": self.job.get("mode"),
                "chunks": len(self.chunks), "read": 0, "notes": [], "answer_missing": [], "dropped": 0, "fallback": False}

    # ---------------------------------------------------------------- 分段：workers → 整合
    def _select(self):
        """要讀的段落：不超過 EXTRACT_MAX_CHUNKS 就全部；超過時每一份的第一段（狀態列與開頭）一定讀，再依問題的詞出現幾個挑（有出現的才算），
        還有名額就在其餘的段落裡平均分散地挑（不要全擠在開頭），讀到的範圍越廣越好。"""
        if len(self.chunks) <= EXTRACT_MAX_CHUNKS:
            return list(self.chunks), []
        def score(c):
            text = "\n".join(self.sources[c["src"]]["lines"][c["start"]:c["end"]]).lower()
            return sum(1 for t in self.terms if t in text)
        keep = {c["id"] for c in self.chunks if c["k"] == 1}
        for c in sorted((c for c in self.chunks if score(c) > 0), key=lambda c: (-score(c), c["id"])):
            if len(keep) >= EXTRACT_MAX_CHUNKS:
                break
            keep.add(c["id"])
        rest = [c for c in self.chunks if c["id"] not in keep]
        room = EXTRACT_MAX_CHUNKS - len(keep)
        if room > 0 and rest:
            step = len(rest) / room
            keep.update(rest[min(len(rest) - 1, int(step * (i + 0.5)))]["id"] for i in range(room))
        return [c for c in self.chunks if c["id"] in keep], [c for c in self.chunks if c["id"] not in keep]

    @staticmethod
    def _ranges(chunks):
        """段落 → 合併相鄰的行號範圍：「366～607、729～1208」。"""
        spans = []
        for c in sorted(chunks, key=lambda c: c["start"]):
            if spans and spans[-1][1] == c["start"]:
                spans[-1][1] = c["end"]
            else:
                spans.append([c["start"], c["end"]])
        return "、".join(f"{a + 1}～{b}" for a, b in spans)

    def _worker(self, c):
        s = self.sources[c["src"]]
        lines = s["lines"]
        a, b = c["start"], c["end"]
        limit = EXTRACT_CHUNK_CHARS if b - a == 1 else LINE_MAX_CHARS
        ctx = rc.chunk_context(lines, a)
        user = (f"{self.purpose}\n\n"
                + _x("worker_chunk", label=s["label"], count=len(lines), of=c["of"], k=c["k"], start=a + 1, end=b) + "\n"
                + (_x("worker_context", lines="\n".join(rc.numbered(j + 1, _cut(lines[j], 300)) for j in ctx)) + "\n" if ctx else "")
                + "\n" + _x("worker_body", lines="\n".join(rc.numbered(i + 1, _cut(lines[i], limit)) for i in range(a, b))))
        data, raw, err = self._call("worker", read_prompt("worker.md", max_facts=EXTRACT_WORKER_FACTS), user, EXTRACT_WORKER_SCHEMA,
                                    EXTRACT_WORKER_PREDICT, chunk=c["id"])
        if data is None:
            out = {"chunk": c["id"], "ok": False, "error": err}
        else:
            facts, dropped = self._ground_all(cited_items(data.get("facts")), c["src"], (a, b))
            errors, dropped_e = self._ground_all(cited_items(data.get("errors")), c["src"], (a, b))
            out = {"chunk": c["id"], "ok": True, "relevant": bool(data.get("relevant")) or bool(facts or errors),
                   "summary": " ".join(str(data.get("summary") or "").split()), "facts": facts, "errors": errors,
                   "dropped": dropped + dropped_e}
        self.note(f"{PROGRESS_MARK} 提煉：第 {c['id']}/{len(self.chunks)} 段（{'#' + str(s['rid']) + ' ' if len(self.sources) > 1 else ''}"
                  f"行 {a + 1}～{b}）" + (f"：{len(out['facts'])} 條事實" + (f"，程式拿掉 {len(out['dropped'])} 條對不上原文的" if out["dropped"] else "")
                                         if out["ok"] else f"：失敗（{out['error']}）"))
        return out

    def _merge(self):
        self.job["mode"] = "merge"
        selected, unread = self._select()
        size = sum(len(t) for t in self.texts)
        self.note(f"{PROGRESS_MARK} 提煉 {'、'.join('#' + str(s['rid']) for s in self.sources)}：原文 {size} 字，依結構切成 {len(self.chunks)} 段"
                  + (f"，依問題挑 {len(selected)} 段讀" if unread else "") + f"，每段一個 worker，最後整合")
        with ThreadPoolExecutor(max_workers=max(1, min(EXTRACT_PARALLEL, len(selected)))) as ex:
            results = list(ex.map(self._worker, selected))
        self.job["workers"] = results
        self.job["unread"] = [c["id"] for c in unread]
        notes = []
        for si, s in enumerate(self.sources):
            miss = [c for c in unread if c["src"] == si]
            if miss:
                notes.append(_x("note_unread", source="#" + str(s["rid"]) + " " if len(self.sources) > 1 else "", lines=self._ranges(miss),
                                count=len(miss), max=EXTRACT_MAX_CHUNKS))
        failed = [c for c, r in zip(selected, results) if not r["ok"]]
        if failed:
            notes.append(_x("note_failed", lines=self._ranges(failed)))
        self.note(f"{PROGRESS_MARK} 整合中：{sum(len(r.get('facts', [])) for r in results)} 條事實（{sum(1 for r in results if r.get('relevant'))} 段有相關內容）")
        data, raw, err = self._call("synth", self._synth_system(), self._merge_input(selected, results, notes), TOOL_SUMMARY_SCHEMA,
                                    EXTRACT_SYNTH_PREDICT)
        if data is None:
            self.job["synth"] = {"error": err}
            if not any(r["ok"] for r in results):   # 每一段與整合都失敗（多半是模型沒有回應）：照實回報
                return self._failed(raw, err or next((r["error"] for r in results if r.get("error")), None))
            return self._fallback(results, notes, raw or err or "")
        return self._finish(data, raw, notes)

    def _merge_input(self, selected, results, notes):
        parts = [self.purpose, ""]
        cat = self._catalog_block()
        if cat:
            parts.append(cat)
        budget = EXTRACT_EVIDENCE_CHARS
        shown = set()
        by_src = {}
        for c, r in zip(selected, results):
            by_src.setdefault(c["src"], []).append((c, r))
        for si, s in enumerate(self.sources):
            lines = s["lines"]
            n_chunks = sum(1 for c in self.chunks if c["src"] == si)
            head = _x("merge_source_head", rid=s["rid"], label=s["label"]) + "\n" if len(self.sources) > 1 else ""
            parts.append(_x("merge_source", head=head, label=s["label"], count=len(lines), chars=len(self.texts[si]), chunks=n_chunks)
                         + (_x("merge_background", background=s["background"]) if s.get("background") else ""))
            parts.append(_x("merge_opening", lines="\n".join(rc.numbered(i + 1, _cut(lines[i], 300)) for i in range(min(3, len(lines))))))
            ol = rc.outline(lines)
            if ol:
                parts.append(_x("merge_outline", lines="\n".join(_x("merge_outline_item", n=n, title=t, count=k) for n, t, k in ol)))
            parts.append(_x("merge_facts_header"))
            for c, r in by_src.get(si, []):
                title = _x("merge_chunk_title", k=c["k"], start=c["start"] + 1, end=c["end"])
                if not r["ok"]:
                    parts.append(_x("merge_chunk_failed", title=title))
                    continue
                if not (r["facts"] or r["errors"]):
                    parts.append(_x("merge_chunk_empty", title=title) + (_x("merge_chunk_empty_summary", summary=r["summary"]) if r["summary"] else ""))
                    continue
                parts.append(_x("merge_chunk_summary", title=title, summary=r["summary"] or _x("merge_no_summary")))
                for label, items in (("", r["facts"]), (_x("merge_error_label"), r["errors"])):
                    for it in items:
                        parts.append(_x("merge_fact", label=label, text=it["text"], lines=lines_text(it["nums"]) or _x("merge_unknown_lines")))
                        new = [x for x in evidence_lines(lines, it["nums"], span=0) if (si, x) not in shown][:EVIDENCE_LINES_PER_FACT]
                        text = "\n".join("      " + rc.numbered(x, _cut(lines[x - 1], 300)).lstrip() for x in new)
                        if new and budget - len(text) > 0:
                            parts.append(text)
                            budget -= len(text)
                            shown.update((si, x) for x in new)
        if notes:
            parts.append(_x("merge_notes", notes="\n".join(f"- {n}" for n in notes)))
        return "\n".join(parts)

    def _fallback(self, results, notes, raw):
        """整合失敗：各段核對過的事實由程式排成清單（不丟掉 worker 的結果），回答留空、由呼叫端說明。"""
        facts = [it for r in results if r["ok"] for it in r["facts"]]
        errors = [it for r in results if r["ok"] for it in r["errors"]]
        data = {"answer": "", "facts": facts, "errors": errors, "not_covered": "；".join(notes) or "無", "suggested_questions": [],
                "index_hint": "", "related_records": []}
        self.job["final"] = {k: v for k, v in data.items()}
        return {"data": data, "structured": True, "raw": raw, "mode": "merge", "chunks": len(self.chunks), "read": len(results),
                "notes": notes, "answer_missing": [], "dropped": 0, "fallback": True}

    # ---------------------------------------------------------------- 整合結果的核對（與一次修正）
    def _check(self, data):
        facts, dropped = self._ground_all(cited_items(data.get("facts")))
        errors, dropped_e = self._ground_all(cited_items(data.get("errors")))
        answer = " ".join(str(data.get("answer") or "").split())
        missing = missing_tokens(answer, self.all_text, self.all_text, self.allowed, counts={len(facts)})
        return facts, errors, dropped + dropped_e, answer, missing

    def _finish(self, data, raw, notes):
        facts, errors, dropped, answer, missing = self._check(data)
        repaired = False
        if missing or (dropped and len(dropped) * 2 >= len(cited_items(data.get("facts"))) + len(cited_items(data.get("errors")))):
            fixed, raw2 = self._repair(data, dropped, missing)
            if fixed is not None:
                f2, e2, d2, a2, m2 = self._check(fixed)
                if len(m2) + len(d2) <= len(missing) + len(dropped):
                    data, raw, facts, errors, dropped, answer, missing, repaired = fixed, raw2, f2, e2, d2, a2, m2, True
        out = dict(data)
        out.update(answer=answer, facts=facts, errors=errors)
        nc = " ".join(str(out.get("not_covered") or "").split())
        # 整合常會照抄程式的說明（措辭略改）：說明裡的第一個行號範圍已經出現在 not_covered 就不再補
        extra = [n for n in notes if n not in nc and not (re.search(r"\d+～\d+", n) and re.search(r"\d+～\d+", n).group() in nc)]
        if extra:
            out["not_covered"] = "；".join(([nc] if nc and nc.rstrip("。.") not in ("無", "沒有") else []) + extra)
        self.job["synth"] = {"repaired": repaired, "dropped": dropped, "answer_missing": missing}
        self.job["final"] = {k: (v if k not in ("facts", "errors") else [{"text": x["text"], "lines": lines_text(x["nums"]),
                                                                          "record": self.sources[x["src"]]["rid"]} for x in v])
                             for k, v in out.items()}
        return {"data": out, "structured": True, "raw": raw, "mode": self.job["mode"], "chunks": len(self.chunks),
                "read": len(self.job.get("workers") or [1]), "notes": notes, "answer_missing": missing, "dropped": len(dropped),
                "fallback": False}

    def _repair(self, data, dropped, missing):
        """帶著程式核對的問題請整合者修一次：只改對不上的地方（照原文改，或拿掉找不到根據的內容）。"""
        problems = []
        if missing:
            problems.append(_x("repair_answer_missing", tokens='」「'.join(missing)))
        for d in dropped[:8]:
            problems.append(_x("repair_fact_missing", text=d["text"], lines=d.get("lines") or _x("merge_unknown_lines"),
                               missing="」「".join(d["missing"]) or _x("repair_missing_default")))
        ev = []
        for d in dropped[:8]:
            si = self._src_index(d.get("record")) or 0
            lines = self.sources[si]["lines"]
            for x in evidence_lines(lines, parse_lines(d.get("lines"), len(lines)))[:EVIDENCE_LINES_PER_FACT]:
                ev.append(rc.numbered(x, _cut(lines[x - 1], 300)))
        user = (_x("repair_user", purpose=self.purpose, result=json.dumps(data, ensure_ascii=False), problems="\n".join(f"- {p}" for p in problems))
                + ("\n\n" + _x("repair_evidence", lines="\n".join(dict.fromkeys(ev))) if ev else "")
                + "\n\n" + _x("repair_tail"))
        fixed, raw, _ = self._call("repair", self._synth_system(), user, TOOL_SUMMARY_SCHEMA, EXTRACT_SYNTH_PREDICT)
        return fixed, raw
