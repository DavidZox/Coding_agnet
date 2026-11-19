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
5. **依報告回答**（4-1）：回覆裡寫的出處（檔案:行號）要在這一回合的報告裡，對不上的提醒一次（domain_reply_check）。每一項的結構化
   回答與核對、帶著上一次的經過再交給領域是 4-2。
"""
import os
import re

from . import mid, prompt_files
from .config import DOMAIN_INDEX_NAME, DOMAIN_ITEMS_MAX, DOMAIN_RESULT_HEAD, MID_JOBS_DIRNAME

_ENTRY = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(([^)]+)\)")
_INDEX_LINE = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(tools/[^)]+\)")
_REF = re.compile(r"[\w./-]*\w\.[A-Za-z][A-Za-z0-9]*:\d+")      # 回覆裡的出處：檔案:行號（副檔名是字母開頭，時間、IP 不算）
_YES = ("y", "yes", "是", "好", "同意", "可以", "1")


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
        return prompt_files.load("harness/system_prompt.md", "domains", domains="\n\n".join(entries), max=DOMAIN_ITEMS_MAX)

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
        self._domain_turn = {"dispatches": [], "excluded": {}, "unlocked": set(), "reports": [], "reply_nudged": False}

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
        entry = {"key": key, "domain": name, "goal": goal, "items": items, "job": None, "status": None, "skill": None, "calls": []}
        turn["dispatches"].append(entry)
        before = (self.current_cwd, self.container_cwd, self.target_container)
        job = mid.Worker(self, name).start(self.current_task or goal, goal, items=items, on_start=self._domain_started)
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
        return text

    def _domain_outcome(self, entry, job):
        name, st = entry["domain"], job["status"]
        calls = []                                    # 中階在領域裡用到的工具（每一版的圖的工具節點；從收據帶入的參數不列）
        for g in job.get("graphs") or []:
            for n in g["graph"]["nodes"]:
                c = {"tool": n.get("tool"), "args": [a for a in n.get("args") or [] if isinstance(a, str)]}
                if c["tool"] and c not in calls:
                    calls.append(c)
        entry.update(job=job["id"], status=st, skill=job.get("skill"), calls=calls)
        url, note = topology_url(job["id"]), (job.get("result") or {}).get("note") or ""
        if st == "need_user":
            need = job["need_user"]
            self.domain_pending = {"domain": name, "job": job["id"], "kind": need["kind"], "question": need.get("question") or "",
                                   "candidates": list(need.get("candidates") or []), "error": need.get("error"), "url": url, "entry": entry}
            cands = "；".join(self.domain_pending["candidates"])
            return _d("ask_waiting", domain=name, question=self.domain_pending["question"],
                      candidates=_d("ask_candidates", candidates=cands) if cands else "", url=url)
        self.domain_pending = None
        if st in ("done", "dead_end", "circuit_break"):
            report = (job.get("result") or {}).get("report") or ""
            self._domain_turn["reports"].append(report)
            return _d("report", domain=name, status=mid.STATUS_TEXT[st], skill=job.get("skill") or "—", url=url, report=report)
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

    def _domain_history(self):
        """這一回合交過的領域（高 4：能交的都交過了，寫做過的事）。"""
        return "\n".join(_d("history_line", n=k, domain=x["domain"], skill=x["skill"] or "—",
                            status=mid.STATUS_TEXT.get(x["status"], x["status"] or "—"), url=topology_url(x["job"]) if x["job"] else "—")
                         for k, x in enumerate(self._domain_turn["dispatches"], 1))

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

    # ---------------------------------------------------------------- 依報告回答（4-1：出處要在報告裡）
    def domain_reply_check(self, parsed):
        """這一回合有領域的報告、主模型回答了（沒有動作）：回覆裡的出處（檔案:行號）都要在報告裡；對不上的提醒一次（回傳提醒的文字）。"""
        turn = self._domain_turn
        if not turn["reports"] or turn["reply_nudged"] or not parsed or parsed.get("action") or not parsed.get("valid", True):
            return None
        refs = list(dict.fromkeys(_REF.findall(parsed.get("reply") or "")))
        missing = [r for r in refs if not any(r in rep for rep in turn["reports"])]
        if not missing:
            return None
        turn["reply_nudged"] = True
        return _d("reply_refs", refs="、".join(missing))
