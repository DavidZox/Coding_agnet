"""新架構的高階（Orchestrator；D10 第 4 步（4-1、4-2）與第 5 步，照 D1、D5 的高 1、4、D7、D9；〈新架構討論紀錄〉第 4 節〈第 4 步〉〈第 5 步〉）。

主對話就是高階（D1），這個 mixin 給 SkillAgent：
1. **領域**（skills_system/DOMAIN.md）：〈領域〉每個領域一行，連到它的 SKILLS.md；〈共用的工具〉是每一層都直接用的（回顧存檔；
   列目錄、找檔案：只看有什麼、在哪裡）。
   主對話的 system prompt 多一節「領域」（domain_block），由程式從每個領域的 SKILLS.md 組：說明、不包含什麼、每個複合技能一句話
   （架構圖的入口技能；沒有複合技能的領域寫明在子工作階段裡一步一步做）。領域的工具（共用的以外）從主對話的技能索引拿掉
   （skills_index_text），主模型直接叫的時候程式擋下來（domain_gate；複合技能的名稱也擋，回交給哪個領域（第 5 步 5-4）；子工作階段裡只能用
   那個領域的工具與共用的工具）。規格有問題的領域不列、它的工具也不擋（主對話照舊能用），問題放進通知。
2. **分工**（run_plan，第 5 步 5-3）：主模型在回覆的 action 填 {"domains": [{"domain", "goal", "items"}, …]}——要用的領域一次選出來，
   每個領域各自的子目標與項目（高階決定原始問題裡每個領域要回答什麼）。程式先核對每一項（_check_entry：領域在 DOMAIN.md、這個問題
   沒有排除過、子目標不是空的、項目 1～DOMAIN_ITEMS_MAX 項、跟這一回合交過的不一樣（一樣的再交一次結果也一樣：不收斂）、同一個項目
   最多 DOMAIN_ITEM_TRIES 次（G5）；一次最多 DOMAIN_PLAN_MAX 個領域、同一個領域只出現一次），全部過了才照順序執行：有複合技能的領域
   交給中階（mid.Worker），沒有的開子工作階段（sub.Session，第 5 步：照現在的方式一步一步做，試錯留在裡面）。後面的領域收到前面的領域
   查到的（_known_text，程式從報告取）；子工作階段另外收到這個問題的分工與主對話這一回合已經做過的（_division_text）：它只做自己的
   子目標，原始問題只用來對照名稱與數值。每個領域的結果各自存成 #編號，全部做完接在一起交回主模型（DOMAIN_RESULT_HEAD 開頭：程式
   整理好的，不再提煉；_plan_done）；中途要問使用者時分工停在 _domain_turn["plan"]，回答之後接著做剩下的。
   子工作階段查不到、不屬於的項目寫了哪個領域查得到時（回答的 domain 欄位，第 5 步 5-4），報告後面列「第 N 項：X 說要交給 Y 查」
   （_routes；Y 這一回合查過這一項、或說過不屬於它的附上），主模型照它再分工——分工還是主模型決定，程式不自己再交。
3. **問使用者**（D7）：中階或子工作階段停下來要問時，程式把問題與候選直接給使用者（domain_pending、domain_ask_text），使用者的回答由
   answer_domain 交給它接回同一個工作（不合法就再問，不經過主模型）；cancel_domain 取消。
4. **第 3 級**（D5 高 1）：中階回「不屬於這個領域」、或子工作階段每一項都回不屬於（5-3）時記下排除的領域，這個問題不能再交給它；
   分工裡其他的領域照樣做完，理由跟報告一起交回主模型重新分工；再交時程式附這一回合做過的事（高 4）。
   中階沒有做完、也沒有報告時（沒有適合的複合技能、失敗、使用者取消），程式接著開子工作階段，用這個領域的工具一步一步做，帶著中階
   停下來的原因（第 5 步 G3；取代 4-1 的放行：主對話不再直接用領域的工具）。
5. **依報告回答**（4-2，G4）：這一回合有領域的報告時，回覆的 schema 多 answers（domain_items 的每一項一筆：答到／查不到、回答、出處）。
   domain_reply_check 核對（answers.answer_problems）：每一項都有、答到的出處在報告裡（#編號要是交給領域的結果或這一回合執行過的
   工具結果，_known_ids）、回答裡的數字與
   名稱在出處那幾段裡、查不到的寫了原因，回覆開頭寫的出處也要在報告裡；沒過的只把那幾項交回修一次。domain_render 照項目排使用者看到的
   回答，每一項附出處那一行的原文（從報告取，I.5），還是沒過的標「沒有通過核對」。
6. **帶著上一次的經過再交**（4-2，I）：同一個問題再交給同一個領域時（之前那幾次沒有做完，或這次的項目之前交過），程式把之前幾次的
   做法、參數、結果、原因、找過的字交給中階或子工作階段（previous），中階從挑技能、合約重新規劃（合約只從新的子目標抄，第 5 步 G9），
   一樣的做法由中階擋（repeated）。
"""
import os
import re

from . import answers, mid, prompt_files, sub
from .config import (DOMAIN_INDEX_NAME, DOMAIN_ITEM_TRIES, DOMAIN_ITEMS_MAX, DOMAIN_KNOWN_CHARS, DOMAIN_PLAN_MAX, DOMAIN_QUOTE_LINES,
                     DOMAIN_RESULT_HEAD, MID_JOBS_DIRNAME, SUB_JOBS_DIRNAME)

_ENTRY = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(([^)]+)\)")
_INDEX_LINE = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(tools/[^)]+\)")
_YES = ("y", "yes", "是", "好", "同意", "可以", "1")
REPORTED = ("done", "dead_end", "circuit_break", "repeated")    # 中階有報告的結果（子工作階段做完一律有報告）


def _d(key, /, **fields):
    """prompts/harness/domain.md 的一則：交給領域的結果、核對沒過的說明。"""
    return prompt_files.load("harness/domain.md", key, **fields)


def _p(key, /, **fields):
    """prompts/harness/plan.md 的一則：分工交給下一層的文字（前面的領域查到的、這個問題的分工）。"""
    return prompt_files.load("harness/plan.md", key, **fields)


def load_registry(base_path, tools_dir):
    """DOMAIN.md → {"domains": {名稱: mid.load_domain 的結果}, "shared": [工具], "hidden": {工具: 領域}, "skills": {複合技能: 領域},
    "problems": [...]}。沒有 DOMAIN.md＝沒有領域（主對話照舊）；規格有問題的領域不列，它的工具也不擋。"""
    out = {"domains": {}, "shared": [], "hidden": {}, "skills": {}, "problems": []}
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
        for sk in d["skills"]:
            out["skills"].setdefault(sk, name)
    return out


def topology_url(jid, kind="mid"):
    """中階或子工作階段的工作在 Web 決策圖的網址（正式的 logs/）。"""
    return f"/topology?src=logs&ref={SUB_JOBS_DIRNAME if kind == 'sub' else MID_JOBS_DIRNAME}/{jid}"


def _quote(rows, ref):
    """使用者看到的出處原文：報告裡寫到這個 檔案:行號 的行，先挑以它開頭的那一行（報告附的原文；子工作階段的報告裡回答那一行也寫了出處，
    排在原文前面），沒有就用第一行。"""
    label = answers.ref_label(ref)
    rows = [r.lstrip("> ").strip() for r in rows]
    return next((r for r in rows if r.startswith(label)), rows[0] if rows else None)


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
                                 tries=DOMAIN_ITEM_TRIES, plan=DOMAIN_PLAN_MAX)

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
        self._domain_turn = {"dispatches": [], "excluded": {}, "reports": [], "reply_nudged": False, "plan": None, "spans": [],
                             "since": len(getattr(self, "trajectory", None) or [])}     # 這一回合的工具結果從軌跡的第幾筆開始

    def _tool_of(self, token):
        """技能名稱、規格（.md）或腳本 → 技能名稱；不是任何技能回 None。"""
        name = os.path.basename(token)
        name = name[:-3] if name.endswith(".md") else name
        if os.path.exists(os.path.join(self.tools_dir, f"{name}.md")):
            return name
        return self._script_skill_map().get(self._normalize_script_name(name))

    def domain_gate(self, token):
        """主模型直接叫領域的工具（技能名稱或腳本）回 [ERROR]（附下一步）；叫領域的複合技能的名稱（或寫成腳本的 <名稱>_cmd.py）也一樣
        （複合技能由中階執行，不是工具；第 5 步 5-4：以前落到「沒有這個技能（已經移除的名稱）」，沒有說要交給哪個領域）。子工作階段裡
        （agent._sub_allowed）只能用那個領域的工具與共用的工具。可以用回 None（不是任何技能的照舊交給後面的檢查）。"""
        skill = self._tool_of(token)
        reg = self.domain_registry()
        name = os.path.basename(token)
        name = name[:-3] if name.endswith(".md") else name[:-len("_cmd.py")] if name.endswith("_cmd.py") else name
        composite = reg["skills"].get(name) if skill is None else None
        allowed = getattr(self, "_sub_allowed", None)
        if allowed is not None:
            if (skill is None and composite is None) or skill in allowed["tools"]:
                return None
            return "[ERROR] " + prompt_files.load("sub/session.md", "not_my_tool", tool=skill or name, domain=allowed["domain"],
                                                  tools="、".join(sorted(allowed["tools"])))
        if composite:
            return "[ERROR] " + _d("skill_blocked", skill=name, domain=composite)
        if skill not in reg["hidden"]:
            return None
        return "[ERROR] " + _d("tool_blocked", tool=skill, domain=reg["hidden"][skill])

    # ---------------------------------------------------------------- 分工（交給領域）
    def run_plan(self, action):
        """分工（第 5 步 5-3）：核對每一項 → 照順序交給中階或子工作階段（後面的領域收到前面的領域查到的）→ 報告一起交回（每個領域的
        結果各自存成 #編號）。核對沒過回 [ERROR]（附下一步），一項都不執行。"""
        entries = action.get("domains") or []
        if not 1 <= len(entries) <= DOMAIN_PLAN_MAX:
            return "[ERROR] " + _d("err_plan_size", count=len(entries), max=DOMAIN_PLAN_MAX)
        names = [e["domain"] for e in entries]
        dup = next((n for n in names if names.count(n) > 1), None)
        if dup:
            return "[ERROR] " + _d("err_plan_dup", domain=dup)
        for k, e in enumerate(entries, 1):
            why = self._check_entry(e)
            if why:
                return "[ERROR] " + (_d("err_plan_entry", k=k, domain=e["domain"]) if len(entries) > 1 else "") + why
        turn = self._domain_turn
        start = len(getattr(self, "trajectory", None) or [])
        turn["plan"] = {"entries": entries, "next": 0, "texts": [], "first": len(turn["dispatches"])}
        turn["spans"].append([start, None])             # 分工執行期間的軌跡（中階、子工作階段的工具）：不算主對話自己做的
        return self._plan_run()

    def _check_entry(self, e):
        """分工的一項的核對：領域在 DOMAIN.md、這個問題沒有排除過、子目標不是空的、項目 1～DOMAIN_ITEMS_MAX 項、跟這一回合交過的不一樣
        （一樣的再交一次結果也一樣：不收斂）、同一個項目最多 DOMAIN_ITEM_TRIES 次（G5）。過了回 None，沒過回說明（不含 [ERROR]）。"""
        reg, turn = self.domain_registry(), self._domain_turn
        name, goal, items = e["domain"], e.get("goal") or "", e.get("items") or []
        if name not in reg["domains"]:
            return _d("err_unknown", domain=name, names="、".join(reg["domains"]) or "—")
        if name in turn["excluded"]:
            return _d("err_excluded", domain=name, reason=turn["excluded"][name], history=self._domain_history())
        if not goal:
            return _d("err_goal", domain=name)
        if not 1 <= len(items) <= DOMAIN_ITEMS_MAX:
            return _d("err_items", count=len(items), max=DOMAIN_ITEMS_MAX)
        same = next((x for x in turn["dispatches"] if x["key"] == [name, goal, items]), None)
        if same:
            return _d("err_same", domain=name, status=_status_text(same["kind"], same["status"]))
        mine = [x for x in turn["dispatches"] if x["domain"] == name]
        for it in items:                                   # G5：同一個項目最多交 DOMAIN_ITEM_TRIES 次
            tries = [x for x in mine if answers.norm(it) in {answers.norm(y) for y in x["items"]}]
            if len(tries) >= DOMAIN_ITEM_TRIES:
                return _d("err_item_tries", item=it, domain=name, n=len(tries), max=DOMAIN_ITEM_TRIES, history=self._domain_history(tries))
        return None

    def _plan_run(self):
        """做分工的下一項；全部做完回所有的報告。"""
        plan = self._domain_turn["plan"]
        if plan["next"] >= len(plan["entries"]):
            return self._plan_done()
        job, entry, before = self._start_entry(plan, plan["next"])
        return self._plan_next(self._domain_finish(entry, job, before))

    def _plan_next(self, text):
        """分工的一項有了結果：停下來要問使用者就回等回答的說明（分工留在 _domain_turn["plan"]，回答之後 answer_domain 接著做）；
        做完了記下它的報告、接著做下一項。"""
        plan = self._domain_turn.get("plan")
        if self.domain_pending or not plan:
            return DOMAIN_RESULT_HEAD + text
        plan["texts"].append(text)
        plan["next"] += 1
        return self._plan_run()

    def _plan_done(self):
        """分工做完：每個領域的結果接在一起，接著是子工作階段說別的領域查得到的項目（_routes，有的時候），最後是依報告回答的說明與
        這一回合要回答的項目（有報告時）。"""
        turn = self._domain_turn
        plan, turn["plan"] = turn["plan"], None
        turn["spans"][-1][1] = len(getattr(self, "trajectory", None) or [])
        items = self.domain_items()
        routes = self._routes(turn["dispatches"][plan["first"]:], items)
        hint = [_d("answer_hint", items="\n".join(f"{k}. {x}" for k, x in enumerate(items, 1)))] if items else []
        return DOMAIN_RESULT_HEAD + "\n\n".join(plan["texts"] + ([routes] if routes else []) + hint)

    def _routes(self, done, items):
        """這次分工裡子工作階段查不到、不屬於、寫了哪個領域查得到的項目（回答的 domain 欄位，第 5 步 5-4）→ 給主模型的一段；沒有回空字串。
        項目在這一回合要回答的項目（items）裡的寫第幾項（每一項都不屬於的子工作階段沒有報告，項目不在裡面，只寫項目）；那個領域這一回合
        已經查過這一項、或說過不屬於它的，程式附上（再交之前就看得到）。"""
        reg, turn = self.domain_registry(), self._domain_turn
        keys = [answers.norm(x) for x in items]
        rows = []
        for x in done:
            if x.get("kind") != "sub":                # 中階的報告沒有一項一項的回答
                continue
            for a in x.get("answers") or []:
                to = a.get("domain") or ""
                if a["status"] == "answered" or to == x["domain"] or to not in reg["domains"] or not 1 <= a["item"] <= len(x["items"]):
                    continue
                item = x["items"][a["item"] - 1]
                key = answers.norm(item)
                where = _d("route_where_n", n=keys.index(key) + 1, item=item) if key in keys else _d("route_where", item=item)
                tried = [y for y in turn["dispatches"] if y["domain"] == to and key in {answers.norm(i) for i in y["items"]}]
                state = (_d("route_excluded", to=to) if to in turn["excluded"] else
                         _d("route_tried", to=to, status=_status_text(tried[-1]["kind"], tried[-1]["status"])) if tried else "")
                rows.append(_d("route", where=where, domain=x["domain"], to=to, state=state))
        return _d("routes", rows="\n".join(dict.fromkeys(rows))) if rows else ""

    def _start_entry(self, plan, k):
        """分工的第 k 項（從 0 算）：記一筆交給領域的紀錄，交給中階（有複合技能）或子工作階段（沒有）。中階收到的問題後面接前面的領域
        查到的（合約可以從那裡抄參數）；子工作階段另外收到這個問題的分工。回傳 (job, 紀錄, 開始時的工作目錄與目標容器)。"""
        reg, turn = self.domain_registry(), self._domain_turn
        e = plan["entries"][k]
        name, goal, items = e["domain"], e["goal"], e["items"]
        mine = [x for x in turn["dispatches"] if x["domain"] == name]
        # 4-2 的 I：之前那幾次沒有做完、或這次的項目之前交過的，經過交下去（中階從挑技能、合約重新規劃；子工作階段從停下來的地方接著做）
        mine_items = {answers.norm(y) for y in items}
        previous = [x for x in mine if x["job"] and (x["status"] != "done" or mine_items & {answers.norm(y) for y in x["items"]})]
        context = {"known": self._known_text(), "division": self._division_text(plan, k)}
        entry = {"key": [name, goal, items], "domain": name, "goal": goal, "items": items, "kind": None, "job": None, "status": None,
                 "skill": None, "calls": [], "n": len(mine) + 1, "previous": [x["job"] for x in previous],
                 "previous_info": [i for x in previous for i in self._attempt_infos(x)], "params": {}, "note": "", "searched": [],
                 "result_id": None, "mid": None, "answers": [], "context": context}
        turn["dispatches"].append(entry)
        before = (self.current_cwd, self.container_cwd, self.target_container)
        question = self.current_task or goal
        if reg["domains"][name]["skills"]:
            job = mid.Worker(self, name).start(question + ("\n\n" + context["known"] if context["known"] else ""), goal, items=items,
                                               on_start=self._domain_started, previous=entry["previous_info"], attempt=entry["n"])
        else:                                              # 沒有複合技能的領域：直接開子工作階段（第 5 步）
            job = self._sub_start(name, entry)
        return job, entry, before

    def _sub_start(self, name, entry, previous=None):
        """開這個領域的子工作階段（分工的一項，或中階沒做完時接著做；previous 不給就用這一次的上一次的經過）。"""
        return self._sub(name).start(self.current_task or entry["goal"], entry["goal"], entry["items"],
                                     on_start=lambda jid: self._domain_started(jid, "sub"),
                                     previous=entry["previous_info"] if previous is None else previous, attempt=entry["n"],
                                     known=entry["context"]["known"], division=entry["context"]["division"])

    def _known_text(self):
        """這一回合前面的領域查到的（交給後面的領域，程式從報告取）：子工作階段一項一項的回答；中階的報告沒有一項一項的回答，取報告的
        前面 DOMAIN_KNOWN_CHARS 字（全文在 #編號）。沒有回空字串。"""
        rows = []
        for x in self._domain_turn["dispatches"]:
            if not x.get("job") or not self._reported(x):
                continue
            if x["kind"] == "sub":
                for a in x.get("answers") or []:
                    if 1 <= a["item"] <= len(x["items"]):
                        item = x["items"][a["item"] - 1]
                        if a["status"] == "answered":
                            rows.append(_p("known_answer", domain=x["domain"], item=item, text=a["text"],
                                           refs="、".join(answers.ref_label(r) for r in a["refs"]) or "—"))
                        else:
                            rows.append(_p("known_not_found" if a["status"] == "not_found" else "known_out_of_domain",
                                           domain=x["domain"], item=item, text=a["text"]))
            elif x.get("report"):
                body = x["report"].split("\n", 1)[-1].strip()
                rows.append(_p("known_report", domain=x["domain"], rid=x.get("result_id") or "—",
                               text=body[:DOMAIN_KNOWN_CHARS] + ("…" if len(body) > DOMAIN_KNOWN_CHARS else "")))
        return _p("known", rows="\n".join(rows)) if rows else ""

    def _division_text(self, plan, k):
        """這個問題的分工（給子工作階段：每個領域的子目標、哪一項是它、做完了沒），加上主對話這一回合已經做過的（工具與結果的第一行）。"""
        rows = [_p("division_entry", n=i + 1, domain=e["domain"], goal=e["goal"],
                   state=_p("state_you" if i == k else "state_done" if i < k else "state_todo"))
                for i, e in enumerate(plan["entries"])]
        rows += [_p("division_main", command=str(r.get("command") or r.get("script") or "—").removeprefix("EXECUTE: "),
                    head=(str(r.get("output_head") or "").strip().splitlines() or ["—"])[0][:160]) for r in self._main_calls()]
        return _p("division", rows="\n".join(rows))

    def _main_calls(self):
        """主對話這一回合自己執行過的工具（軌跡；分工執行期間的——中階、子工作階段的工具——不算，交給領域的結果本身也不算）。"""
        traj, turn = getattr(self, "trajectory", None) or [], self._domain_turn
        spans = [(a, len(traj) if b is None else b) for a, b in turn["spans"]]
        return [r for i, r in enumerate(traj) if i >= turn["since"] and r.get("kind") == "exec"
                and not str(r.get("script") or "").startswith("domain_") and not any(a <= i < b for a, b in spans)]

    @staticmethod
    def _attempt_info(x):
        """交給領域的一次 → 「上一次的經過」的一筆（程式從這一回合的紀錄取，交給中階或子工作階段）。"""
        return {"n": x["n"], "job": x["job"], "kind": x["kind"], "skill": x["skill"], "params": x["params"], "status": x["status"],
                "status_text": _status_text(x["kind"], x["status"]), "note": x["note"], "searched": x["searched"], "items": x["items"]}

    def _attempt_infos(self, x):
        """交給領域的一次 → 上一次的經過（中階沒做完、接著開了子工作階段的，兩筆都給：中階的參數與停下來的原因、子工作階段做到的）。"""
        m = x.get("mid")
        head = [{"n": x["n"], "job": m["job"], "kind": "mid", "skill": m["skill"], "params": m["params"], "status": m["status"],
                 "status_text": _status_text("mid", m["status"]), "note": m["note"], "searched": [], "items": x["items"]}] if m else []
        return head + [self._attempt_info(x)]

    def _sub(self, name):
        """這個領域的子工作階段：能用領域的工具加上共用的工具；其他領域的標題與說明的第一行（查不到、不屬於的那一項選哪個領域查得到）。"""
        reg = self.domain_registry()
        d = reg["domains"][name]
        others = [(n, o["title"], (o["intro"].split("\n") or [""])[0]) for n, o in reg["domains"].items() if n != name]
        return sub.Session(self, name, tools=d["tools"] + reg["shared"], title=d["title"], intro=d["intro"], practice=d.get("practice", ""),
                           others=others)

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
        """中階或子工作階段的 job → 這個領域的結果（存成 #編號；分工的報告接在一起交回主模型，_plan_done）；要問使用者時設 domain_pending。"""
        text = prefix + self._domain_outcome(entry, job, follow)
        self.last_receipt = None
        self._record_trajectory(f"domain_{entry['domain']}", [entry["goal"]] + entry["items"], DOMAIN_RESULT_HEAD + text, *before)
        entry["result_id"] = self.last_result_id
        return text

    def _reported(self, x):
        """這一次交給領域有沒有報告（照報告回答）：子工作階段結束了都有（每一項都不屬於這個領域的除外）；中階是做完、死路、熔斷、跟之前一樣。"""
        if x.get("kind") == "sub":
            return x["status"] not in (None, "running", "need_user", "out_of_domain")
        return x["status"] in REPORTED

    def _domain_outcome(self, entry, job, follow=True):
        name, st = entry["domain"], job["status"]
        kind = "sub" if job.get("kind") == "sub" else "mid"
        url, note = topology_url(job["id"], kind), (job.get("result") or {}).get("note") or ""
        if kind == "sub":
            entry.update(kind="sub", job=job["id"], status=st, skill=sub.STEP_SKILL, calls=sub.calls(job), note=note,
                         searched=sub.searched(job), params={}, answers=list(job.get("answers") or []))
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
            entry["report"] = report
            return _d("report", domain=name, status=_status_text(kind, st), skill=entry["skill"] or "—", url=url, report=report)
        if st == "out_of_domain":                     # 中階挑技能時、或子工作階段每一項都說不屬於這個領域（5-3）
            self._domain_turn["excluded"][name] = note or "—"
            return _d("out_of_domain", domain=name, reason=note or "—", url=url)
        if not follow or kind == "sub":               # /clear 取消：照實記下，不再接著做（子工作階段結束了都有報告，不會到這裡）
            return _d("cancelled", domain=name, url=url)
        # 中階沒有做完、也沒有報告（沒有適合的做法、失敗、使用者取消）：接著開子工作階段，用這個領域的工具一步一步做（第 5 步 G3，
        # 取代 4-1 的放行）。中階這一次也算進上一次的經過（停下來的原因交給子工作階段）。
        entry["mid"] = {"job": job["id"], "status": st, "skill": job.get("skill"), "params": dict(entry["params"]), "note": note,
                        "calls": entry["calls"]}
        follow_job = self._sub_start(name, entry, previous=entry["previous_info"] + [self._attempt_info(entry)])
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
            self._plan_drop()
            return "[ERROR] " + _d("err_lost", domain=p["domain"])
        if job["status"] == "need_user":
            self._domain_outcome(p["entry"], job)       # 更新 domain_pending（同一個問題附錯誤，或下一個問題）
            return None
        return self._plan_next(self._domain_finish(p["entry"], job, before, prefix=_d("answered", domain=p["domain"], answer=text)))

    def cancel_domain(self, follow=True):
        """使用者取消中階或子工作階段的問題：結束成「使用者取消」，接著做分工裡還沒做的，交回主模型的文字。中階取消之後照舊接著開
        子工作階段一步一步做（follow；/clear 不接著做，分工裡還沒做的也不做）。"""
        p = self.domain_pending
        if not p:
            return None
        before = (self.current_cwd, self.container_cwd, self.target_container)
        job = (self._sub(p["domain"]) if p.get("worker") == "sub" else mid.Worker(self, p["domain"])).cancel(p["job"])
        self.domain_pending = None
        if not job:
            self._plan_drop()
            return "[ERROR] " + _d("err_lost", domain=p["domain"])
        text = self._domain_finish(p["entry"], job, before, follow=follow)
        if not follow:
            self._plan_drop()
            return DOMAIN_RESULT_HEAD + text
        return self._plan_next(text)

    def _plan_drop(self):
        """分工不再接著做（/clear、找不到工作紀錄）：分工執行期間的軌跡到這裡為止。"""
        turn = self._domain_turn
        if turn.get("plan"):
            turn["plan"] = None
            turn["spans"][-1][1] = len(getattr(self, "trajectory", None) or [])

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
        """依報告回答時能當出處的 #編號：交給領域的結果本身、這一回合執行過的工具結果（子工作階段與中階執行的也在軌跡裡）。報告文字裡
        出現、但不是這些的不算（第 5 步 5-3：子工作階段引用之前的存檔，自己的核對標了沒過，主對話以前因為報告裡寫了那個編號就收）。"""
        turn = self._domain_turn
        return {str(x["result_id"]) for x in turn["dispatches"] if x.get("result_id")} | {str(r["id"]) for r, _ in self._turn_results()}

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
                    q = _quote(rows, ref) if kind == "line" else None
                    if q and q not in quotes:
                        quotes.append(q)
                out += [f"   > {q}" for q in quotes[:DOMAIN_QUOTE_LINES]]
            if k in problems:
                out.append(f"   ⚠️ 沒有通過核對：{'；'.join(problems[k])}（報告：{ids}）")
        urls = list(dict.fromkeys(topology_url(x["job"], x["kind"]) for x in turn["dispatches"] if x["job"] and self._reported(x)))
        if urls:
            out.append("🔗 決策圖：" + "、".join(urls))
        return "\n".join(out)
