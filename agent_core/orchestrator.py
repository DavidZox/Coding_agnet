"""新架構的高階（Orchestrator；D10 第 4 步的 4-1，照 D1、D5 的高 1、4、D7、D9；〈新架構討論紀錄〉第 4 節〈第 4 步〉）。

主對話就是高階（D1），這個 mixin 給 SkillAgent：
1. **領域**（skills_system/DOMAIN.md）：〈領域〉每個領域一行，連到它的 SKILLS.md；〈共用的工具〉是每一層都直接用的（回顧存檔；
   列目錄、找檔案：只看有什麼、在哪裡，凍結的工具的事也要用）。
   主對話的 system prompt 多一節「領域」（domain_block），由程式從每個領域的 SKILLS.md 組：說明、不包含什麼、每個複合技能一句話
   （架構圖的入口技能）。領域的工具（共用的以外）從主對話的技能索引拿掉（skills_index_text），主模型直接叫的時候程式擋下來
   （domain_gate）。規格有問題的領域不列、它的工具也不擋（主對話照舊能用），問題放進通知。
2. **交給領域**（run_domain）：主模型在回覆的 action 填 {"domain", "goal", "items"}。程式核對：領域在 DOMAIN.md、這個問題沒有排除過、
   子目標不是空的、項目 1～DOMAIN_ITEMS_MAX 項、跟這一回合交過的不一樣（一樣的再交一次結果也一樣：不收斂）。核對過就執行中階
   （mid.Worker），結果存成 #編號 交回主模型（DOMAIN_RESULT_HEAD 開頭：程式整理好的，不再提煉）。
3. **問使用者**（D7）：中階停下來要問時，程式把問題與候選直接給使用者（domain_pending、domain_ask_text），使用者的回答由
   answer_domain 交給中階接回同一個工作（不合法就再問，不經過主模型）；cancel_domain 取消（中階結束成 cancelled）。
4. **第 3 級**（D5 高 1）：中階回「不屬於這個領域」時記下排除的領域，這個問題不能再交給它；再交時程式附這一回合做過的事（高 4）。
   中階沒有做完、也沒有報告時（不屬於這個領域、使用者取消、沒有適合的複合技能、失敗），這一回合回到主對話照現在的方式做：放行這個
   領域的工具（G7；過渡，第 5 步改成在子工作階段裡做）。
5. **依報告回答**（4-2，G4）：這一回合有領域的報告時，回覆的 schema 多 answers（domain_items 的每一項一筆：答到／查不到、回答、出處）。
   domain_reply_check 核對：每一項都有、答到的出處在報告裡（或這一回合自己執行過的工具結果）、回答裡的數字與名稱在出處那幾段裡
   （extract.missing_tokens）、查不到的寫了原因，
   回覆開頭寫的出處也要在報告裡；沒過的只把那幾項交回修一次。domain_render 照項目排使用者看到的回答，每一項附出處那一行的原文
   （從報告取，I.5），還是沒過的標「沒有通過核對」。
6. **帶著上一次的經過再交**（4-2，I）：同一個問題再交給同一個領域時（之前那幾次沒有做完，或這次的項目之前交過），程式把之前幾次的
   技能、參數、結果、原因、找過的字交給中階（mid.Worker.start 的 previous），中階從挑技能、合約重新規劃，一樣的做法由中階擋（repeated）。
   同一個項目最多交 DOMAIN_ITEM_TRIES 次（G5）。
"""
import difflib
import json
import os
import re

from . import mid, prompt_files
from .config import DOMAIN_INDEX_NAME, DOMAIN_ITEM_TRIES, DOMAIN_ITEMS_MAX, DOMAIN_QUOTE_LINES, DOMAIN_RESULT_HEAD, MID_JOBS_DIRNAME
from .extract import missing_tokens

_ENTRY = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(([^)]+)\)")
_INDEX_LINE = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(tools/[^)]+\)")
_REF = re.compile(r"[\w./-]*\w\.[A-Za-z][A-Za-z0-9]*:\d+")      # 回覆裡的出處：檔案:行號（副檔名是字母開頭，時間、IP 不算）
_CITE = re.compile(r"(" + _REF.pattern + r")(?:\s*[-~～]\s*(\d+))?")    # 出處：檔案:行號，可以是一段（a.py:31-35）
_ID = re.compile(r"#(\d+)")
_YES = ("y", "yes", "是", "好", "同意", "可以", "1")
REPORTED = ("done", "dead_end", "circuit_break", "repeated")    # 中階有報告的結果（照報告回答；沒有報告的這一回合放行領域的工具）


def _norm(text):
    return " ".join(str(text or "").split()).lower()


def _d(key, /, **fields):
    """prompts/harness/domain.md 的一則：交給領域的結果、核對沒過的說明。"""
    return prompt_files.load("harness/domain.md", key, **fields)


def load_registry(base_path, tools_dir):
    """DOMAIN.md → {"domains": {名稱: mid.load_domain 的結果}, "shared": [工具], "hidden": {工具: 領域}, "problems": [...]}。
    沒有 DOMAIN.md＝沒有領域（主對話照舊）；規格有問題的領域不列，它的工具也不擋。"""
    out = {"domains": {}, "shared": [], "hidden": {}, "problems": []}
    try:
        with open(os.path.join(base_path, DOMAIN_INDEX_NAME), encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError:
        return out
    section, names = None, []
    for ln in lines:
        if ln.startswith("## "):
            section = ln[3:].strip()
        elif (m := _ENTRY.match(ln)) and section in ("領域", "共用的工具"):
            (names if section == "領域" else out["shared"]).append(m.group(1))
    for name in names:
        d = mid.load_domain(base_path, tools_dir, name)
        if d["problems"]:
            out["problems"] += [f"{name}：{p}" for p in d["problems"]]
            continue
        out["domains"][name] = d
        for t in d["tools"]:
            if t not in out["shared"]:
                out["hidden"].setdefault(t, name)
    return out


def topology_url(jid):
    """中階的工作在 Web 決策圖的網址（正式的 logs/）。"""
    return f"/topology?src=logs&ref={MID_JOBS_DIRNAME}/{jid}"


class DomainMixin:

    # ---------------------------------------------------------------- 領域的清單
    def domain_registry(self):
        """load_registry 的結果；DOMAIN.md 與領域的檔案改了才重讀（system prompt 每一輪都會組）。"""
        sig = self._domain_signature()
        cache = getattr(self, "_domain_cache", None)
        if cache is None or cache[0] != sig:
            reg = load_registry(self.base_path, self.tools_dir)
            self._domain_cache = (sig, reg)
            if reg["problems"]:
                with self._compress_state_lock:
                    self._notices.append("⚠️ 領域的規格有問題，這些領域先不分派（主對話照舊用它們的工具）：" + "；".join(reg["problems"][:5]))
        return self._domain_cache[1]

    def _domain_signature(self):
        out = []
        for path in [os.path.join(self.base_path, DOMAIN_INDEX_NAME)] + [
                os.path.join(self.base_path, d) for d in sorted(os.listdir(self.base_path))
                if os.path.isfile(os.path.join(self.base_path, d, "SKILLS.md"))]:
            try:
                files = [path] if os.path.isfile(path) else [os.path.join(path, f) for f in sorted(os.listdir(path))]
                out += [(f, os.path.getmtime(f)) for f in files]
            except OSError:
                out.append((path, None))
        return tuple(out)

    def domain_names(self):
        return list(self.domain_registry()["domains"])

    def domain_block(self):
        """system prompt 的「領域」一節；沒有領域時是空的。"""
        reg = self.domain_registry()
        if not reg["domains"]:
            return ""
        entries = [prompt_files.load("harness/system_prompt.md", "domain_entry", title=d["title"], intro=d["intro"],
                                     skills="\n".join(f"- {s} — {desc}" for s, desc in d["catalog"].items()))
                   for d in reg["domains"].values()]
        return prompt_files.load("harness/system_prompt.md", "domains", domains="\n\n".join(entries), max=DOMAIN_ITEMS_MAX,
                                 tries=DOMAIN_ITEM_TRIES)

    def skills_index_text(self):
        """主對話的技能索引（SKILLS.md）拿掉領域的工具（共用的以外）：那些交給領域做。放行時另外在結果裡列（system prompt 不變）。"""
        with open(self.index_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
        hidden = self.domain_registry()["hidden"]
        return "\n".join(ln for ln in text.split("\n") if not ((m := _INDEX_LINE.match(ln)) and m.group(1) in hidden))

    def _index_lines(self, tools):
        with open(self.index_file, "r", encoding="utf-8") as f:
            lines = {m.group(1): ln for ln in f.read().split("\n") if (m := _INDEX_LINE.match(ln))}
        return "\n".join(lines.get(t, f"- {t}") for t in tools)

    # ---------------------------------------------------------------- 一回合的狀態
    def _reset_domain_turn(self):
        """使用者送出新的問題：這一回合交過的領域、排除的領域、放行的工具、報告歸零（回答中階的問題不算新的問題）。"""
        self._domain_turn = {"dispatches": [], "excluded": {}, "unlocked": set(), "reports": [], "reply_nudged": False,
                             "since": len(getattr(self, "trajectory", None) or [])}     # 這一回合的工具結果從軌跡的第幾筆開始

    def domain_gate(self, token):
        """主模型直接叫領域的工具（技能名稱或腳本）：這一回合沒有放行就回 [ERROR]（附下一步）；可以用回 None。"""
        reg = self.domain_registry()
        hidden = {t: d for t, d in reg["hidden"].items() if d not in self._domain_turn["unlocked"]}
        if not hidden:
            return None
        name = os.path.basename(token)
        name = name[:-3] if name.endswith(".md") else name
        skill = name if name in hidden else self._script_skill_map().get(self._normalize_script_name(name))
        if skill not in hidden:
            return None
        return "[ERROR] " + _d("tool_blocked", tool=skill, domain=hidden[skill])

    # ---------------------------------------------------------------- 交給領域
    def run_domain(self, action):
        """交給領域：核對 → 中階 → 結果（存成 #編號）。核對沒過回 [ERROR]（附下一步），不執行。"""
        reg, turn = self.domain_registry(), self._domain_turn
        name, goal, items = action["domain"], action.get("goal") or "", action.get("items") or []
        if name not in reg["domains"]:
            return "[ERROR] " + _d("err_unknown", domain=name, names="、".join(reg["domains"]) or "—")
        if name in turn["excluded"]:
            return "[ERROR] " + _d("err_excluded", domain=name, reason=turn["excluded"][name], history=self._domain_history())
        if not goal:
            return "[ERROR] " + _d("err_goal", domain=name)
        if not 1 <= len(items) <= DOMAIN_ITEMS_MAX:
            return "[ERROR] " + _d("err_items", count=len(items), max=DOMAIN_ITEMS_MAX)
        key = [name, goal, items]
        same = next((x for x in turn["dispatches"] if x["key"] == key), None)
        if same:
            return "[ERROR] " + _d("err_same", domain=name, status=mid.STATUS_TEXT.get(same["status"], same["status"] or "—"))
        mine = [x for x in turn["dispatches"] if x["domain"] == name]
        for it in items:                                   # G5：同一個項目最多交 DOMAIN_ITEM_TRIES 次
            tries = [x for x in mine if _norm(it) in {_norm(y) for y in x["items"]}]
            if len(tries) >= DOMAIN_ITEM_TRIES:
                return "[ERROR] " + _d("err_item_tries", item=it, domain=name, n=len(tries), max=DOMAIN_ITEM_TRIES,
                                       history=self._domain_history(tries))
        # 4-2 的 I：之前那幾次沒有做完、或這次的項目之前交過的，經過交給中階（從挑技能、合約重新規劃；一樣的做法由中階擋）
        mine_items = {_norm(y) for y in items}
        previous = [x for x in mine if x["job"] and (x["status"] != "done" or mine_items & {_norm(y) for y in x["items"]})]
        entry = {"key": key, "domain": name, "goal": goal, "items": items, "job": None, "status": None, "skill": None, "calls": [],
                 "n": len(mine) + 1, "previous": [x["job"] for x in previous], "params": {}, "note": "", "searched": [], "result_id": None}
        turn["dispatches"].append(entry)
        before = (self.current_cwd, self.container_cwd, self.target_container)
        info = [{"n": x["n"], "job": x["job"], "skill": x["skill"], "params": x["params"], "status": x["status"], "note": x["note"],
                 "searched": x["searched"], "items": x["items"]} for x in previous]
        job = mid.Worker(self, name).start(self.current_task or goal, goal, items=items, on_start=self._domain_started,
                                           previous=info, attempt=entry["n"])
        return self._domain_finish(entry, job, before)

    def _domain_started(self, jid):
        """中階的工作建好了：拓撲圖的連結先推給畫面（執行中就能看，4b ①）。"""
        text = f"🔗 決策圖：{topology_url(jid)}"
        print(text)
        cb = getattr(self, "progress_callback", None)
        if cb:
            try:
                cb(text)
            except Exception:   # noqa: BLE001  畫面的問題不能中斷執行
                pass

    def _domain_finish(self, entry, job, before, prefix=""):
        """中階的 job → 交回主模型的文字（存成 #編號）；要問使用者時設 domain_pending。"""
        text = DOMAIN_RESULT_HEAD + prefix + self._domain_outcome(entry, job)
        self.last_receipt = None
        self._record_trajectory(f"domain_{entry['domain']}", [entry["goal"]] + entry["items"], text, *before)
        entry["result_id"] = self.last_result_id
        return text

    def _domain_outcome(self, entry, job):
        name, st = entry["domain"], job["status"]
        calls = []                                    # 中階在領域裡用到的工具（每一版的圖的工具節點；從收據帶入的參數不列）
        for g in job.get("graphs") or []:
            for n in g["graph"]["nodes"]:
                c = {"tool": n.get("tool"), "args": [a for a in n.get("args") or [] if isinstance(a, str)]}
                if c["tool"] and c not in calls:
                    calls.append(c)
        url, note = topology_url(job["id"]), (job.get("result") or {}).get("note") or ""
        entry.update(job=job["id"], status=st, skill=job.get("skill"), calls=calls, note=note, searched=mid.searched(job),
                     params={k: v["value"] for k, v in (job.get("params") or {}).items()})
        if st == "need_user":
            need = job["need_user"]
            self.domain_pending = {"domain": name, "job": job["id"], "kind": need["kind"], "question": need.get("question") or "",
                                   "candidates": list(need.get("candidates") or []), "error": need.get("error"), "url": url, "entry": entry}
            cands = "；".join(self.domain_pending["candidates"])
            return _d("ask_waiting", domain=name, question=self.domain_pending["question"],
                      candidates=_d("ask_candidates", candidates=cands) if cands else "", url=url)
        self.domain_pending = None
        if st in REPORTED:
            report = (job.get("result") or {}).get("report") or ""
            self._domain_turn["reports"].append(report)
            items = "\n".join(f"{k}. {x}" for k, x in enumerate(self.domain_items(), 1))
            return _d("report", domain=name, status=mid.STATUS_TEXT[st], skill=job.get("skill") or "—", url=url, report=report,
                      items=_d("items", items=items))
        # 中階沒有做完、也沒有報告（不屬於這個領域、使用者取消、沒有適合的做法、失敗）：這一回合回到主對話照現在的方式做，
        # 放行這個領域的工具（G7；過渡，第 5 步改成在子工作階段裡做）。有報告的（做完、死路、熔斷）照舊擋：照報告回答。
        self._domain_turn["unlocked"].add(name)
        tools = self._index_lines([t for t, d in self.domain_registry()["hidden"].items() if d == name])
        if st == "out_of_domain":
            self._domain_turn["excluded"][name] = note or "—"
            return _d("out_of_domain", domain=name, reason=note or "—", url=url, tools=tools)
        if st == "cancelled":
            return _d("cancelled", domain=name, url=url, tools=tools)
        return _d("no_skill" if st == "no_skill" else "failed", domain=name, reason=note or "—", url=url, tools=tools)

    def _domain_history(self, entries=None):
        """這一回合交過的領域（高 4：能交的都交過了，寫做過的事）；entries＝只列這幾次。"""
        return "\n".join(_d("history_line", n=k, domain=x["domain"], skill=x["skill"] or "—",
                            status=mid.STATUS_TEXT.get(x["status"], x["status"] or "—"), url=topology_url(x["job"]) if x["job"] else "—")
                         for k, x in enumerate(self._domain_turn["dispatches"] if entries is None else entries, 1))

    # ---------------------------------------------------------------- 問使用者（程式轉、程式接回）
    def domain_ask_text(self):
        """給使用者看的：中階要問的問題、候選（編號）、上一次的回答為什麼不行。"""
        p = self.domain_pending
        if not p:
            return ""
        lines = [f"🗺️ {p['domain']} 要問你：{p['question']}"]
        if p.get("error"):
            lines.append(f"⚠️ 剛才的回答不能用：{p['error']}")
        if p["kind"] == "guard":
            lines.append("回答「是」照做，「否」不做；也可以取消。")
        elif p["candidates"]:
            lines += [f"  {k}. {c}" for k, c in enumerate(p["candidates"], 1)]
            lines.append("輸入編號選候選，或直接輸入你的回答；也可以取消。")
        else:
            lines.append("直接輸入你的回答；也可以取消。")
        lines.append(f"🔗 決策圖：{p['url']}")
        return "\n".join(lines)

    def answer_domain(self, text):
        """使用者回答中階的問題：交給中階接回同一個工作。還要再問（回答不合法、或下一個問題）回 None（domain_pending 已更新）；
        做完回交給主模型的文字。候選的編號換成候選本身。"""
        p = self.domain_pending
        if not p:
            return None
        text = (text or "").strip()
        if text.isdigit() and 1 <= int(text) <= len(p["candidates"]):
            text = p["candidates"][int(text) - 1]
        worker = mid.Worker(self, p["domain"])
        before = (self.current_cwd, self.container_cwd, self.target_container)
        if p["kind"] == "guard":
            job = worker.resume(p["job"], approve=text.lower() in _YES)
        else:
            job = worker.resume(p["job"], answer=text)
        if not job:
            self.domain_pending = None
            return "[ERROR] " + _d("err_lost", domain=p["domain"])
        if job["status"] == "need_user":
            self._domain_outcome(p["entry"], job)       # 更新 domain_pending（同一個問題附錯誤，或下一個問題）
            return None
        return self._domain_finish(p["entry"], job, before, prefix=_d("answered", domain=p["domain"], answer=text))

    def cancel_domain(self):
        """使用者取消中階的問題：中階結束成 cancelled，交回主模型的文字。"""
        p = self.domain_pending
        if not p:
            return None
        before = (self.current_cwd, self.container_cwd, self.target_container)
        job = mid.Worker(self, p["domain"]).cancel(p["job"])
        self.domain_pending = None
        if not job:
            return "[ERROR] " + _d("err_lost", domain=p["domain"])
        return self._domain_finish(p["entry"], job, before)

    # ---------------------------------------------------------------- 依報告回答（4-2：每一項的回答由程式核對、照項目排）
    def domain_items(self):
        """這一回合交給領域、有報告的項目（依報告回答時 answers 照這個編號；同樣的項目只列一次，照第一次出現的順序）。"""
        out, seen = [], set()
        for x in (getattr(self, "_domain_turn", None) or {}).get("dispatches") or []:
            if x["status"] in REPORTED:
                for it in x["items"]:
                    if _norm(it) not in seen:
                        seen.add(_norm(it))
                        out.append(it)
        return out

    def _turn_results(self):
        """這一回合自己執行過、有存檔的工具結果（交給領域的結果本身不算）：[(軌跡的紀錄, 存檔的路徑)]。依報告回答時它們也算出處
        （放行之後主對話自己查的、共用的工具：列目錄、找檔案）。"""
        recs = (getattr(self, "trajectory", None) or [])[self._domain_turn.get("since", 0):]
        return [(r, os.path.join(self.results_dir(), r["result_file"])) for r in recs
                if r.get("result_file") and not str(r.get("script") or "").startswith("domain_")]

    def _known_ids(self):
        turn = self._domain_turn
        return ({str(x["result_id"]) for x in turn["dispatches"] if x.get("result_id")}
                | {m for rep in turn["reports"] for m in _ID.findall(rep)} | {str(r["id"]) for r, _ in self._turn_results()})

    def _rows_from_results(self, path, first, last):
        """報告裡沒有的 檔案:行號：這一回合自己執行過的工具的收據裡有沒有（search_text 命中的行、view_file 看的那一段、code_ast_reader
        的定義與呼叫）→ (那幾行（程式從檔案讀，寫成 檔案:行號：內容）, 那幾份存檔的原文)。路徑的結尾一樣就算。"""
        rows, texts, cache = [], [], {}
        for _, archive in self._turn_results():
            receipt = _load_json(archive[:-3] + ".receipt.json")
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
                text = _line_of(p, n, cache)
                if text is not None:
                    rows.append(f"{_rel(p, self.current_cwd)}:{n}：{text}")
            if hits:
                texts.append(_read(archive))
        return rows, texts

    def _cited(self, ref):
        """一個出處 → (種類, 對到的行, 那幾段的文字, 行號)。種類：line（檔案:行號）、id（#編號）、unknown（報告與這一回合的工具結果都沒有）、
        form（寫法看不懂）。報告裡沒有的，再看這一回合自己執行過的工具（_turn_results：收據裡有的 檔案:行號、存檔的 #編號）。行號的出處要在報告的某一行（後面不能再接數字：a.py:4 不算 a.py:48），那幾段是那幾行所在的整節
        （## 到下一個 ##：核對數字與名稱時一起看，同一節的總數、範圍都算）；#編號 是報告裡出現的編號或交給領域的結果本身，
        那幾段是提到它的節，加上那份存檔的原文。"""
        reports = self._domain_turn["reports"]
        m = _CITE.search(ref)
        if m:
            base = m.group(1)
            path, line = base.rsplit(":", 1)
            last = int(m.group(2)) if m.group(2) and 0 <= int(m.group(2)) - int(line) <= 20 else int(line)
            rows, texts = self._rows_for(path, int(line), last, reports)       # 路徑的結尾一樣就算（報告寫完整路徑、回答只寫後面幾段）
            if not rows and "/" in path:                    # 目錄寫錯或省略了一段：檔名與行號在報告裡只對到一個檔案就算
                rows, texts = self._rows_for(os.path.basename(path), int(line), last, reports)
                if len({_REF.search(r).group().rsplit(":", 1)[0] for r in rows if _REF.search(r)}) != 1:
                    rows, texts = [], []
            if not rows:                                    # 報告裡沒有：這一回合自己執行過的工具（收據裡有這一行）
                rows, texts = self._rows_from_results(path, int(line), last)
            return ("line" if rows else "unknown"), rows, texts, list(range(int(line), last + 1))
        m = _ID.search(ref)
        if m:
            rid = m.group(1)
            if rid not in self._known_ids():
                return "unknown", [], [], []
            texts = [sec for rep in reports for sec in _sections(rep) if re.search(rf"#{rid}(?!\d)", sec)]
            if rid in {str(x["result_id"]) for x in self._domain_turn["dispatches"] if x.get("result_id")}:
                texts += reports
            path = self.result_file_path(rid)
            if path:
                texts.append(_read(path))
            return "id", [], texts, []
        return "form", [], [], []

    @staticmethod
    def _rows_for(path, first, last, reports):
        """報告裡寫到 path:行號（first～last）的行與它們所在的節。path 前面要是路徑的分隔或行首（a.py 不算 xa.py），行號後面不能再接數字。"""
        wants = [re.compile(r"(?<![\w.-])" + re.escape(f"{path}:{n}") + r"(?!\d)") for n in range(first, last + 1)]
        rows, texts = [], []
        for rep in reports:
            for sec in _sections(rep):
                hit = [ln.strip().lstrip("-").strip() for ln in sec.split("\n") if any(w.search(ln) for w in wants)]
                if hit:
                    rows += hit
                    texts.append(sec)
        return rows, texts

    def _answer_problems(self, parsed):
        """answers 的核對（G4 的步驟 7）→ {項目編號: [沒過的原因]}（0＝回覆的開頭）；全部過了是空的。"""
        items, turn = self.domain_items(), self._domain_turn
        answers = {a["item"]: a for a in parsed.get("answers") or [] if 1 <= a["item"] <= len(items)}
        allowed = "\n".join([self.current_task or ""] + items + [x["goal"] for x in turn["dispatches"]])
        source = "\n".join(turn["reports"])
        out = {}
        for k, item in enumerate(items, 1):
            a, why = answers.get(k), []
            if a is None:
                why.append(_d("why_missing"))
            elif a["status"] == "not_found":
                if not a["text"]:
                    why.append(_d("why_no_reason"))
            else:
                if not a["refs"]:
                    why.append(_d("why_no_refs"))
                evidence, lines = list(a["refs"]), []
                for ref in a["refs"]:
                    kind, _, texts, nums = self._cited(ref)
                    if kind == "form":
                        why.append(_d("why_ref_form", ref=ref))
                    elif kind == "unknown":
                        why.append(_d("why_ref_unknown", ref=ref))
                    evidence += texts
                    lines += nums
                if len(evidence) > len(a["refs"]):
                    text = "\n".join(evidence)
                    bad = missing_tokens(a["text"], text, source, allowed, refs=lines)
                    if bad:
                        near = _near(bad, text)
                        why.append(_d("why_tokens", tokens="、".join(bad)) + (_d("why_near", near="、".join(near)) if near else ""))
            if why:
                out[k] = why
        lead = [r for r in dict.fromkeys(_REF.findall(parsed.get("reply") or "")) if self._cited(r)[0] != "line"]
        if lead:
            out[0] = [_d("why_lead_refs", refs="、".join(lead))]
        return out

    def domain_reply_check(self, parsed):
        """這一回合有領域的報告、主模型回答了（沒有動作）：核對 answers（_answer_problems），沒過的只把那幾項交回修一次（回傳交回的文字）；
        修過一次還是沒過的不再交回，使用者看到的回答會標「沒有通過核對」（domain_render）。"""
        turn = self._domain_turn
        items = self.domain_items()
        if not items or turn["reply_nudged"] or not parsed or parsed.get("action") or not parsed.get("valid", True):
            return None
        problems = self._answer_problems(parsed)
        if not problems:
            return None
        turn["reply_nudged"] = True
        rows = [_d("answers_lead", why="；".join(w)) if k == 0 else _d("answers_problem", k=k, item=items[k - 1], why="；".join(w))
                for k, w in sorted(problems.items())]
        return _d("answers_fix", problems="\n".join(rows))

    def domain_render(self, parsed):
        """使用者看到的回答（G4 的步驟 10、I.5）：回覆的開頭，接著照項目排——每一項的回答與出處，答到的附出處那一行的原文（從報告取，
        最多 DOMAIN_QUOTE_LINES 行），查不到的寫原因，沒有通過核對的標出來附報告的 #編號；最後是決策圖的連結。這一回合沒有領域的報告、
        或還有動作時回 None（照模型的回覆）。"""
        items = self.domain_items()
        if not items or not parsed or parsed.get("action") or not parsed.get("valid", True):
            return None
        turn = self._domain_turn
        problems = self._answer_problems(parsed)
        answers = {a["item"]: a for a in parsed.get("answers") or [] if 1 <= a["item"] <= len(items)}
        ids = "、".join(f"#{x['result_id']}" for x in turn["dispatches"] if x["status"] in REPORTED and x.get("result_id")) or "—"
        out = [parsed["reply"]] if parsed.get("reply") else []
        if 0 in problems:
            out.append(f"⚠️ 回覆的開頭沒有通過核對：{'；'.join(problems[0])}")
        for k, item in enumerate(items, 1):
            a = answers.get(k)
            if a is None:
                out.append(f"{k}. {item}：（沒有回答）⚠️ 沒有通過核對，見報告 {ids}")
                continue
            if a["status"] == "not_found":
                out.append(f"{k}. {item}：查不到。{a['text']}")
            else:
                refs = list(dict.fromkeys(_ref_label(r) for r in a["refs"]))
                out.append(f"{k}. {item}：{a['text']}" + (f"（出處：{'、'.join(refs)}）" if refs else ""))
                quotes = []
                for ref in a["refs"]:
                    kind, rows, _, _ = self._cited(ref)
                    quotes += [r for r in rows[:1] if kind == "line" and r not in quotes]
                out += [f"   > {q}" for q in quotes[:DOMAIN_QUOTE_LINES]]
            if k in problems:
                out.append(f"   ⚠️ 沒有通過核對：{'；'.join(problems[k])}（報告：{ids}）")
        urls = list(dict.fromkeys(topology_url(x["job"]) for x in turn["dispatches"] if x["job"] and x["status"] in REPORTED))
        if urls:
            out.append("🔗 決策圖：" + "、".join(urls))
        return "\n".join(out)


_WORD = re.compile(r"[A-Za-z_][\w./-]*[\w]")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _line_of(path, n, cache):
    """檔案的第 n 行（去掉前後空白）；讀不到或沒有這一行回 None。"""
    if path not in cache:
        text = _read(path)
        cache[path] = text.split("\n") if text else None
    lines = cache[path]
    return lines[n - 1].strip() if lines and 1 <= n <= len(lines) else None


def _rel(path, cwd):
    cwd = os.path.abspath(cwd or ".")
    return os.path.relpath(path, cwd) if path.startswith(cwd.rstrip("/") + "/") else path


def _near(bad, evidence):
    """對不上的字在出處那幾段裡相近的寫法（拼錯一兩個字母的檔名、名稱）：交回修的時候附上，模型知道要改成什麼。"""
    words = sorted({x for w in _WORD.findall(evidence) for x in [w] + w.split("/") if x})   # 路徑也拆成每一段（回答常只寫檔名）
    out = []
    for w in bad:
        out += [x for x in difflib.get_close_matches(w, words, n=2, cutoff=0.8) if x != w and x not in out]
    return out[:4]


def _ref_label(ref):
    """顯示用的出處：只留 檔案:行號（一段的寫成 a.py:31-35）或 #編號（模型常把報告的整行抄進 refs）；看不懂的照原樣。"""
    m = _CITE.search(ref)
    if m:
        return m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
    m = _ID.search(ref)
    return f"#{m.group(1)}" if m else ref


def _sections(report):
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
