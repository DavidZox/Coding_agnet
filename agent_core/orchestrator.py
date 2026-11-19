"""新架構的高階（Orchestrator；D10 第 4 步（4-1、4-2）與第 5 步，照 D1、D5 的高 1、4、D7、D9；〈新架構討論紀錄〉第 4 節〈第 4 步〉〈第 5 步〉）。

主對話就是高階（D1），這個 mixin 給 SkillAgent：
1. **領域**（skills_system/DOMAIN.md）：〈領域〉每個領域一行，連到它的 SKILLS.md；〈共用的工具〉是每一層都直接用的（回顧存檔；
   列目錄、找檔案：只看有什麼、在哪裡）。
   主對話的 system prompt 多一節「領域」（domain_block），由程式從每個領域的 SKILLS.md 組：說明、不包含什麼、每個複合技能一句話
   （架構圖的入口技能；沒有複合技能的領域寫明在子工作階段裡一步一步做）。領域的工具（共用的以外）從主對話的技能索引拿掉
   （skills_index_text），主模型直接叫的時候程式擋下來（domain_gate；子工作階段裡只能用那個領域的工具與共用的工具）。規格有問題的領域
   不列、它的工具也不擋（主對話照舊能用），問題放進通知。
2. **交給領域**（run_domain）：主模型在回覆的 action 填 {"domain", "goal", "items"}。程式核對：領域在 DOMAIN.md、這個問題沒有排除過、
   子目標不是空的、項目 1～DOMAIN_ITEMS_MAX 項、跟這一回合交過的不一樣（一樣的再交一次結果也一樣：不收斂）、同一個項目最多
   DOMAIN_ITEM_TRIES 次（G5）。核對過就執行：有複合技能的領域交給中階（mid.Worker），沒有的直接開子工作階段（sub.Session，第 5 步：
   照現在的方式一步一步做，試錯留在裡面）。結果存成 #編號 交回主模型（DOMAIN_RESULT_HEAD 開頭：程式整理好的，不再提煉）。
3. **問使用者**（D7）：中階或子工作階段停下來要問時，程式把問題與候選直接給使用者（domain_pending、domain_ask_text），使用者的回答由
   answer_domain 交給它接回同一個工作（不合法就再問，不經過主模型）；cancel_domain 取消。
4. **第 3 級**（D5 高 1）：中階回「不屬於這個領域」時記下排除的領域，這個問題不能再交給它；再交時程式附這一回合做過的事（高 4）。
   中階沒有做完、也沒有報告時（沒有適合的複合技能、失敗、使用者取消），程式接著開子工作階段，用這個領域的工具一步一步做，帶著中階
   停下來的原因（第 5 步 G3；取代 4-1 的放行：主對話不再直接用領域的工具）。
5. **依報告回答**（4-2，G4）：這一回合有領域的報告時，回覆的 schema 多 answers（domain_items 的每一項一筆：答到／查不到、回答、出處）。
   domain_reply_check 核對（answers.answer_problems）：每一項都有、答到的出處在報告裡（或這一回合自己執行過的工具結果）、回答裡的數字與
   名稱在出處那幾段裡、查不到的寫了原因，回覆開頭寫的出處也要在報告裡；沒過的只把那幾項交回修一次。domain_render 照項目排使用者看到的
   回答，每一項附出處那一行的原文（從報告取，I.5），還是沒過的標「沒有通過核對」。
6. **帶著上一次的經過再交**（4-2，I）：同一個問題再交給同一個領域時（之前那幾次沒有做完，或這次的項目之前交過），程式把之前幾次的
   做法、參數、結果、原因、找過的字交給中階或子工作階段（previous），中階從挑技能、合約重新規劃（合約只從新的子目標抄，第 5 步 G9），
   一樣的做法由中階擋（repeated）。
"""
import os
import re

from . import answers, mid, prompt_files, sub
from .config import (DOMAIN_INDEX_NAME, DOMAIN_ITEM_TRIES, DOMAIN_ITEMS_MAX, DOMAIN_QUOTE_LINES, DOMAIN_RESULT_HEAD, MID_JOBS_DIRNAME,
                     SUB_JOBS_DIRNAME)

_ENTRY = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(([^)]+)\)")
_INDEX_LINE = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(tools/[^)]+\)")
_YES = ("y", "yes", "是", "好", "同意", "可以", "1")
REPORTED = ("done", "dead_end", "circuit_break", "repeated")    # 中階有報告的結果（子工作階段做完一律有報告）


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


def topology_url(jid, kind="mid"):
    """中階或子工作階段的工作在 Web 決策圖的網址（正式的 logs/）。"""
    return f"/topology?src=logs&ref={SUB_JOBS_DIRNAME if kind == 'sub' else MID_JOBS_DIRNAME}/{jid}"


def _status_text(kind, status):
    return (sub.STATUS_TEXT if kind == "sub" else mid.STATUS_TEXT).get(status, status or "—")


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
                                     skills="\n".join(f"- {s} — {desc}" for s, desc in d["catalog"].items())
                                     or prompt_files.load("harness/system_prompt.md", "domain_no_skill"))
                   for d in reg["domains"].values()]
        return prompt_files.load("harness/system_prompt.md", "domains", domains="\n\n".join(entries), max=DOMAIN_ITEMS_MAX,
                                 tries=DOMAIN_ITEM_TRIES)

    def _index_blocks(self):
        """技能索引（SKILLS.md）→ [[一節的每一行]]：第一塊是第一個 ## 之前的開頭，之後每一塊從 ## 標題開始（標題、> 開頭的說明、工具）。"""
        with open(self.index_file, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        blocks = [[]]
        for ln in lines:
            if ln.startswith("## "):
                blocks.append([])
            blocks[-1].append(ln)
        return blocks

    def skills_index_text(self):
        """主對話的技能索引（SKILLS.md）拿掉領域的工具（共用的以外）：那些交給領域做（system prompt 不變）。一節的工具全部拿掉時，整節
        （標題與說明，例如目標容器、ROS 2 Workspace）都不列：主對話用不到（第 5 步 5-2，凍結的工具交給領域）。"""
        hidden = self.domain_registry()["hidden"]
        out = []
        for k, block in enumerate(self._index_blocks()):
            tools = [m.group(1) for ln in block if (m := _INDEX_LINE.match(ln))]
            if k and tools and all(t in hidden for t in tools):
                continue
            out += [ln for ln in block if not ((m := _INDEX_LINE.match(ln)) and m.group(1) in hidden)]
        return "\n".join(out)

    def _index_lines(self, tools):
        """技能索引裡這幾個工具的那一行（子工作階段的 system prompt 列能用的工具，照 tools 的順序）。工具所在的那一節有說明（> 開頭的，
        例如目標容器、ROS 2 Workspace）時，放在那一節第一個工具的前面：說明跟著工具走（第 5 步 5-2，凍結的工具交給子工作階段）。"""
        rows, where, notes = {}, {}, {}
        for k, block in enumerate(self._index_blocks()):
            notes[k] = [ln for ln in block if ln.startswith(">")] if k else []
            for ln in block:
                if (m := _INDEX_LINE.match(ln)):
                    rows[m.group(1)], where[m.group(1)] = ln, k
        out, shown = [], set()
        for t in tools:
            k = where.get(t)
            if k is not None and k not in shown:
                shown.add(k)
                out += notes[k]
            out.append(rows.get(t, f"- {t}"))
        return "\n".join(out)

    # ---------------------------------------------------------------- 一回合的狀態
    def _reset_domain_turn(self):
        """使用者送出新的問題：這一回合交過的領域、排除的領域、報告歸零（回答中階的問題不算新的問題）。"""
        self._domain_turn = {"dispatches": [], "excluded": {}, "reports": [], "reply_nudged": False,
                             "since": len(getattr(self, "trajectory", None) or [])}     # 這一回合的工具結果從軌跡的第幾筆開始

    def _tool_of(self, token):
        """技能名稱、規格（.md）或腳本 → 技能名稱；不是任何技能回 None。"""
        name = os.path.basename(token)
        name = name[:-3] if name.endswith(".md") else name
        if os.path.exists(os.path.join(self.tools_dir, f"{name}.md")):
            return name
        return self._script_skill_map().get(self._normalize_script_name(name))

    def domain_gate(self, token):
        """主模型直接叫領域的工具（技能名稱或腳本）回 [ERROR]（附下一步）；子工作階段裡（agent._sub_allowed）只能用那個領域的工具與
        共用的工具。可以用回 None（不是任何技能的照舊交給後面的檢查）。"""
        skill = self._tool_of(token)
        allowed = getattr(self, "_sub_allowed", None)
        if allowed is not None:
            if skill is None or skill in allowed["tools"]:
                return None
            return "[ERROR] " + prompt_files.load("sub/session.md", "not_my_tool", tool=skill, domain=allowed["domain"],
                                                  tools="、".join(sorted(allowed["tools"])))
        hidden = self.domain_registry()["hidden"]
        if skill not in hidden:
            return None
        return "[ERROR] " + _d("tool_blocked", tool=skill, domain=hidden[skill])

    # ---------------------------------------------------------------- 交給領域
    def run_domain(self, action):
        """交給領域：核對 → 中階或子工作階段 → 結果（存成 #編號）。核對沒過回 [ERROR]（附下一步），不執行。"""
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
            return "[ERROR] " + _d("err_same", domain=name, status=_status_text(same["kind"], same["status"]))
        mine = [x for x in turn["dispatches"] if x["domain"] == name]
        for it in items:                                   # G5：同一個項目最多交 DOMAIN_ITEM_TRIES 次
            tries = [x for x in mine if answers.norm(it) in {answers.norm(y) for y in x["items"]}]
            if len(tries) >= DOMAIN_ITEM_TRIES:
                return "[ERROR] " + _d("err_item_tries", item=it, domain=name, n=len(tries), max=DOMAIN_ITEM_TRIES,
                                       history=self._domain_history(tries))
        # 4-2 的 I：之前那幾次沒有做完、或這次的項目之前交過的，經過交下去（中階從挑技能、合約重新規劃；子工作階段從停下來的地方接著做）
        mine_items = {answers.norm(y) for y in items}
        previous = [x for x in mine if x["job"] and (x["status"] != "done" or mine_items & {answers.norm(y) for y in x["items"]})]
        entry = {"key": key, "domain": name, "goal": goal, "items": items, "kind": None, "job": None, "status": None, "skill": None,
                 "calls": [], "n": len(mine) + 1, "previous": [x["job"] for x in previous],
                 "previous_info": [i for x in previous for i in self._attempt_infos(x)], "params": {}, "note": "", "searched": [],
                 "result_id": None, "mid": None}
        turn["dispatches"].append(entry)
        before = (self.current_cwd, self.container_cwd, self.target_container)
        if reg["domains"][name]["skills"]:
            job = mid.Worker(self, name).start(self.current_task or goal, goal, items=items, on_start=self._domain_started,
                                               previous=entry["previous_info"], attempt=entry["n"])
        else:                                              # 沒有複合技能的領域：直接開子工作階段（第 5 步）
            job = self._sub(name).start(self.current_task or goal, goal, items, on_start=lambda jid: self._domain_started(jid, "sub"),
                                        previous=entry["previous_info"], attempt=entry["n"])
        return self._domain_finish(entry, job, before)

    @staticmethod
    def _attempt_info(x):
        """交給領域的一次 → 「上一次的經過」的一筆（程式從這一回合的紀錄取，交給中階或子工作階段）。"""
        return {"n": x["n"], "job": x["job"], "kind": x["kind"], "skill": x["skill"], "params": x["params"], "status": x["status"],
                "status_text": _status_text(x["kind"], x["status"]), "note": x["note"], "searched": x["searched"], "items": x["items"]}

    def _attempt_infos(self, x):
        """交給領域的一次 → 上一次的經過（中階沒做完、接著開了子工作階段的，兩筆都給：中階停下來的原因與子工作階段做到的）。"""
        m = x.get("mid")
        head = [{"n": x["n"], "job": m["job"], "kind": "mid", "skill": m["skill"], "params": {}, "status": m["status"],
                 "status_text": _status_text("mid", m["status"]), "note": m["note"], "searched": [], "items": x["items"]}] if m else []
        return head + [self._attempt_info(x)]

    def _sub(self, name):
        """這個領域的子工作階段：能用領域的工具加上共用的工具。"""
        reg = self.domain_registry()
        d = reg["domains"][name]
        return sub.Session(self, name, tools=d["tools"] + reg["shared"], title=d["title"], intro=d["intro"], practice=d.get("practice", ""))

    def _domain_started(self, jid, kind="mid"):
        """中階或子工作階段的工作建好了：決策圖的連結先推給畫面（執行中就能看，4b ①）。"""
        text = f"🔗 決策圖：{topology_url(jid, kind)}"
        print(text)
        cb = getattr(self, "progress_callback", None)
        if cb:
            try:
                cb(text)
            except Exception:   # noqa: BLE001  畫面的問題不能中斷執行
                pass

    def _domain_finish(self, entry, job, before, prefix="", follow=True):
        """中階或子工作階段的 job → 交回主模型的文字（存成 #編號）；要問使用者時設 domain_pending。"""
        text = DOMAIN_RESULT_HEAD + prefix + self._domain_outcome(entry, job, follow)
        self.last_receipt = None
        self._record_trajectory(f"domain_{entry['domain']}", [entry["goal"]] + entry["items"], text, *before)
        entry["result_id"] = self.last_result_id
        return text

    def _reported(self, x):
        """這一次交給領域有沒有報告（照報告回答）：子工作階段結束了一律有；中階是做完、死路、熔斷、跟之前一樣。"""
        if x.get("kind") == "sub":
            return x["status"] not in (None, "running", "need_user")
        return x["status"] in REPORTED

    def _domain_outcome(self, entry, job, follow=True):
        name, st = entry["domain"], job["status"]
        kind = "sub" if job.get("kind") == "sub" else "mid"
        url, note = topology_url(job["id"], kind), (job.get("result") or {}).get("note") or ""
        if kind == "sub":
            entry.update(kind="sub", job=job["id"], status=st, skill=sub.STEP_SKILL, calls=sub.calls(job), note=note,
                         searched=sub.searched(job), params={})
        else:
            calls = []                                # 中階在領域裡用到的工具（每一版的圖的工具節點；從收據帶入的參數不列）
            for g in job.get("graphs") or []:
                for n in g["graph"]["nodes"]:
                    c = {"tool": n.get("tool"), "args": [a for a in n.get("args") or [] if isinstance(a, str)]}
                    if c["tool"] and c not in calls:
                        calls.append(c)
            entry.update(kind="mid", job=job["id"], status=st, skill=job.get("skill"), calls=calls, note=note, searched=mid.searched(job),
                         params={k: v["value"] for k, v in (job.get("params") or {}).items()})
        if st == "need_user":
            need = job["need_user"]
            self.domain_pending = {"domain": name, "job": job["id"], "worker": kind, "kind": need["kind"], "question": need.get("question") or "",
                                   "candidates": list(need.get("candidates") or []), "error": need.get("error"), "guard": need.get("guard"),
                                   "url": url, "entry": entry}
            cands = "；".join(self.domain_pending["candidates"])
            return _d("ask_waiting", domain=name, question=self.domain_pending["question"],
                      candidates=_d("ask_candidates", candidates=cands) if cands else "", url=url)
        self.domain_pending = None
        if self._reported(entry):
            report = (job.get("result") or {}).get("report") or ""
            analysis = sub.analysis_reports(self, job) if kind == "sub" else []
            if analysis:                # G4：子工作階段裡執行的數據分析（原樣附在報告裡），主對話的回答照它核對（analysis_reply_check）
                self.note_analysis_report(analysis[-1][1])
            self._domain_turn["reports"].append(report)
            items = "\n".join(f"{k}. {x}" for k, x in enumerate(self.domain_items(), 1))
            return _d("report", domain=name, status=_status_text(kind, st), skill=entry["skill"] or "—", url=url, report=report,
                      items=_d("items", items=items))
        if st == "out_of_domain":
            self._domain_turn["excluded"][name] = note or "—"
            return _d("out_of_domain", domain=name, reason=note or "—", url=url)
        if not follow or kind == "sub":               # /clear 取消：照實記下，不再接著做（子工作階段結束了一律有報告，不會到這裡）
            return _d("cancelled", domain=name, url=url)
        # 中階沒有做完、也沒有報告（沒有適合的做法、失敗、使用者取消）：接著開子工作階段，用這個領域的工具一步一步做（第 5 步 G3，
        # 取代 4-1 的放行）。中階這一次也算進上一次的經過（停下來的原因交給子工作階段）。
        entry["mid"] = {"job": job["id"], "status": st, "skill": job.get("skill"), "note": note, "calls": entry["calls"]}
        prev = entry["previous_info"] + [self._attempt_info(entry)]
        follow_job = self._sub(name).start(self.current_task or entry["goal"], entry["goal"], entry["items"],
                                           on_start=lambda jid: self._domain_started(jid, "sub"), previous=prev, attempt=entry["n"])
        return _d("stepwise", domain=name, status=_status_text("mid", st), reason=note or "—", url=url) + "\n" + self._domain_outcome(entry, follow_job)

    def _domain_history(self, entries=None):
        """這一回合交過的領域（高 4：能交的都交過了，寫做過的事）；entries＝只列這幾次。"""
        return "\n".join(_d("history_line", n=k, domain=x["domain"], skill=x["skill"] or "—", status=_status_text(x["kind"], x["status"]),
                            url=topology_url(x["job"], x["kind"]) if x["job"] else "—")
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
        """使用者回答中階或子工作階段的問題：交給它接回同一個工作。還要再問（回答不合法、或下一個問題）回 None（domain_pending 已更新）；
        做完回交給主模型的文字。候選的編號換成候選本身。"""
        p = self.domain_pending
        if not p:
            return None
        text = (text or "").strip()
        if text.isdigit() and 1 <= int(text) <= len(p["candidates"]):
            text = p["candidates"][int(text) - 1]
        before = (self.current_cwd, self.container_cwd, self.target_container)
        if p.get("worker") == "sub":
            job = self._sub(p["domain"]).resume(p["job"], approve=text.lower() in _YES)
        elif p["kind"] == "guard":
            job = mid.Worker(self, p["domain"]).resume(p["job"], approve=text.lower() in _YES)
        else:
            job = mid.Worker(self, p["domain"]).resume(p["job"], answer=text)
        if not job:
            self.domain_pending = None
            return "[ERROR] " + _d("err_lost", domain=p["domain"])
        if job["status"] == "need_user":
            self._domain_outcome(p["entry"], job)       # 更新 domain_pending（同一個問題附錯誤，或下一個問題）
            return None
        return self._domain_finish(p["entry"], job, before, prefix=_d("answered", domain=p["domain"], answer=text))

    def cancel_domain(self, follow=True):
        """使用者取消中階或子工作階段的問題：結束成「使用者取消」，交回主模型的文字。中階取消之後照舊接著開子工作階段一步一步做
        （follow；/clear 不接著做）。"""
        p = self.domain_pending
        if not p:
            return None
        before = (self.current_cwd, self.container_cwd, self.target_container)
        job = (self._sub(p["domain"]) if p.get("worker") == "sub" else mid.Worker(self, p["domain"])).cancel(p["job"])
        self.domain_pending = None
        if not job:
            return "[ERROR] " + _d("err_lost", domain=p["domain"])
        return self._domain_finish(p["entry"], job, before, follow=follow)

    # ---------------------------------------------------------------- 依報告回答（4-2：每一項的回答由程式核對、照項目排）
    def domain_items(self):
        """這一回合交給領域、有報告的項目（依報告回答時 answers 照這個編號；同樣的項目只列一次，照第一次出現的順序）。"""
        out, seen = [], set()
        for x in (getattr(self, "_domain_turn", None) or {}).get("dispatches") or []:
            if self._reported(x):
                for it in x["items"]:
                    if answers.norm(it) not in seen:
                        seen.add(answers.norm(it))
                        out.append(it)
        return out

    def _turn_results(self):
        """這一回合自己執行過、有存檔的工具結果（交給領域的結果本身不算；子工作階段的工具結果也在軌跡裡）：[(軌跡的紀錄, 存檔的路徑)]。
        依報告回答時它們也算出處（共用的工具：列目錄、找檔案）。"""
        recs = (getattr(self, "trajectory", None) or [])[self._domain_turn.get("since", 0):]
        return [(r, os.path.join(self.results_dir(), r["result_file"])) for r in recs
                if r.get("result_file") and not str(r.get("script") or "").startswith("domain_")]

    def _known_ids(self):
        turn = self._domain_turn
        return ({str(x["result_id"]) for x in turn["dispatches"] if x.get("result_id")}
                | {m for rep in turn["reports"] for m in answers.ID.findall(rep)} | {str(r["id"]) for r, _ in self._turn_results()})

    def _cited(self, ref):
        """一個出處 → (種類, 對到的行, 那幾段的文字, 行號)。種類：line（檔案:行號）、id（#編號）、unknown（報告與這一回合的工具結果都沒有）、
        form（寫法看不懂）。報告裡沒有的，再看這一回合自己執行過的工具（_turn_results：收據裡有的 檔案:行號、存檔的 #編號）。行號的出處要在
        報告的某一行（後面不能再接數字：a.py:4 不算 a.py:48），那幾段是那幾行所在的整節（## 到下一個 ##：核對數字與名稱時一起看，同一節的
        總數、範圍都算）；#編號 是報告裡出現的編號或交給領域的結果本身，那幾段是提到它的節，加上那份存檔的原文。"""
        reports = self._domain_turn["reports"]
        m = answers.CITE.search(ref)
        if m:
            path, first, last = answers.span(m)
            rows, texts = self._rows_for(path, first, last, reports)       # 路徑的結尾一樣就算（報告寫完整路徑、回答只寫後面幾段）
            if not rows and "/" in path:                    # 目錄寫錯或省略了一段：檔名與行號在報告裡只對到一個檔案就算
                rows, texts = self._rows_for(os.path.basename(path), first, last, reports)
                if len({answers.REF.search(r).group().rsplit(":", 1)[0] for r in rows if answers.REF.search(r)}) != 1:
                    rows, texts = [], []
            if not rows:                                    # 報告裡沒有：這一回合自己執行過的工具（收據裡有這一行）
                rows, texts = answers.rows_from_archives([a for _, a in self._turn_results()], path, first, last, self.current_cwd)
            return ("line" if rows else "unknown"), rows, texts, list(range(first, last + 1))
        m = answers.ID.search(ref)
        if m:
            rid = m.group(1)
            if rid not in self._known_ids():
                return "unknown", [], [], []
            texts = [sec for rep in reports for sec in answers.sections(rep) if re.search(rf"#{rid}(?!\d)", sec)]
            if rid in {str(x["result_id"]) for x in self._domain_turn["dispatches"] if x.get("result_id")}:
                texts += reports
            path = self.result_file_path(rid)
            if path:
                texts.append(answers.read(path))
            return "id", [], texts, []
        return "form", [], [], []

    @staticmethod
    def _rows_for(path, first, last, reports):
        """報告裡寫到 path:行號（first～last）的行與它們所在的節。path 前面要是路徑的分隔或行首（a.py 不算 xa.py），行號後面不能再接數字。"""
        wants = [re.compile(r"(?<![\w.-])" + re.escape(f"{path}:{n}") + r"(?!\d)") for n in range(first, last + 1)]
        rows, texts = [], []
        for rep in reports:
            for sec in answers.sections(rep):
                hit = [ln.strip().lstrip("-").strip() for ln in sec.split("\n") if any(w.search(ln) for w in wants)]
                if hit:
                    rows += hit
                    texts.append(sec)
        return rows, texts

    def _answer_problems(self, parsed):
        """answers 的核對（G4 的步驟 7）→ {項目編號: [沒過的原因]}（0＝回覆的開頭）；全部過了是空的。"""
        items, turn = self.domain_items(), self._domain_turn
        allowed = "\n".join([self.current_task or ""] + items + [x["goal"] for x in turn["dispatches"]])
        out = answers.answer_problems(items, parsed.get("answers"), self._cited, allowed, "\n".join(turn["reports"]))
        lead = [r for r in dict.fromkeys(answers.REF.findall(parsed.get("reply") or "")) if self._cited(r)[0] != "line"]
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
        given = {a["item"]: a for a in parsed.get("answers") or [] if 1 <= a["item"] <= len(items)}
        ids = "、".join(f"#{x['result_id']}" for x in turn["dispatches"] if self._reported(x) and x.get("result_id")) or "—"
        out = [parsed["reply"]] if parsed.get("reply") else []
        if 0 in problems:
            out.append(f"⚠️ 回覆的開頭沒有通過核對：{'；'.join(problems[0])}")
        for k, item in enumerate(items, 1):
            a = given.get(k)
            if a is None:
                out.append(f"{k}. {item}：（沒有回答）⚠️ 沒有通過核對，見報告 {ids}")
                continue
            if a["status"] == "not_found":
                out.append(f"{k}. {item}：查不到。{a['text']}")
            else:
                refs = list(dict.fromkeys(answers.ref_label(r) for r in a["refs"]))
                out.append(f"{k}. {item}：{a['text']}" + (f"（出處：{'、'.join(refs)}）" if refs else ""))
                quotes = []
                for ref in a["refs"]:
                    kind, rows, _, _ = self._cited(ref)
                    quotes += [r for r in rows[:1] if kind == "line" and r not in quotes]
                out += [f"   > {q}" for q in quotes[:DOMAIN_QUOTE_LINES]]
            if k in problems:
                out.append(f"   ⚠️ 沒有通過核對：{'；'.join(problems[k])}（報告：{ids}）")
        urls = list(dict.fromkeys(topology_url(x["job"], x["kind"]) for x in turn["dispatches"] if x["job"] and self._reported(x)))
        if urls:
            out.append("🔗 決策圖：" + "、".join(urls))
        return "\n".join(out)
