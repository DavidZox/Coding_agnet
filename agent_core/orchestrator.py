"""主 session 這一側的交辦（2026-11-23 框架，docs/框架討論紀錄.md）：SkillAgent 的 mixin。

1. **領域**（skills_system/DOMAIN.md）：〈領域〉每個領域一行，連到它的 SKILLS.md（說明、不包含什麼、〈做法〉、有骨架的技能、工具）；
   〈共用的工具〉主 session 與領域 session 都直接用（回顧存檔；列目錄、找檔案：只看有什麼、在哪裡）。
   主 session 的 system prompt 多一節「交辦」（domain_block）：怎麼交辦，與每個領域一行（標題、說明的第一句），讓主模型知道哪些事要交辦。
   領域的工具（共用的以外）從主 session 的技能索引拿掉（skills_index_text），主模型直接叫的時候程式擋下來（domain_gate；有骨架的技能的
   名稱也擋）；領域 session 裡只能用它選的領域的工具與共用的工具（agent._sub_allowed）。規格有問題的領域不列、它的工具也不擋，問題放進通知。
2. **交辦**（run_task，F1）：主模型在 action 填 {"task": {"goal", "background", "constraints", "items"}}——子目標、使用者說明的背景、要求的
   限制與要回答的項目，不指定領域；每一筆 {quote}：一字不改地抄使用者的原話（這段對話裡使用者說過的任何一則，_user_words；框架討論紀錄
   第 6 輪的 B、第 27 輪：關鍵資訊由程式原樣帶著走，領域 session 照原話判斷項目的意思；背景與限制是第 32 輪的 U1，只用來理解）。程式核對
   （子目標不是空的、項目 1～DOMAIN_ITEMS_MAX 項、每一筆原話在使用者說過的話裡、最新這一則的每一段都有放進一欄而問句在項目裡、
   跟這一回合交辦過的不一樣、同一個項目最多 DOMAIN_ITEM_TRIES 次），交給領域 session
   （agent_core/domain_session.py：選領域、一次一個技能、太長就提煉、決定回報或再選）。同一個問題再交辦時，之前幾次的經過（每一步的技能
   與結果）一起交下去。結果存成 #編號，報告交回主模型（DOMAIN_RESULT_HEAD 開頭：程式整理好的，不再提煉），後面接依報告回答的說明。
3. **問使用者**：領域 session 停在確認關卡時，程式把問題直接給使用者（domain_pending、domain_ask_text），answer_domain 接回同一步、
   cancel_domain 取消（照做到的收尾）。
4. **依報告回答**（F6）：這一回合有交辦的報告時，回覆的 schema 多 answers（domain_items 的每一項一筆：答到／查不到、回答、出處）。
   domain_reply_check 核對（answers.answer_problems）：每一項都有、答到的出處在報告裡（#編號要是交辦的結果或這一回合執行過的工具結果，
   _known_ids）、回答裡的數字與名稱在出處那幾段裡、查不到的寫了原因，回覆開頭寫的出處也要在報告裡；報告裡這一項的回答寫的編號與數字，
   回答裡也要有（answers.dropped：漏了報告的編號，B）；沒過的只把那幾項交回修一次。
   domain_render 照項目排使用者看到的回答，每一項附出處那一行的原文（從報告取），還是沒過的標「沒有通過核對」。
"""
import os
import re

from . import answers, composite, domain_session, prompt_files
from .protocol import answers_text, parse_agent_reply
from .config import DOMAIN_INDEX_NAME, DOMAIN_ITEM_TRIES, DOMAIN_ITEMS_MAX, DOMAIN_QUOTE_LINES, DOMAIN_RESULT_HEAD

_ENTRY = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(([^)]+)\)")
_INDEX_LINE = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(tools/[^)]+\)")
_YES = ("y", "yes", "是", "好", "同意", "可以", "1")


def _d(key, /, **fields):
    """prompts/harness/domain.md 的一則：交辦的結果、核對沒過的說明。"""
    return prompt_files.load("harness/domain.md", key, **fields)


_SENTENCE_END = re.compile(r"[？。！]|[?!](?=\s|$)")   # 一句的結尾：「？」「。」「！」，或「?」「!」後面是空白或結尾（a?b 這種寫法裡的不算）


def ask_parts(text):
    """使用者這一則裡每一段要交辦的話（框架討論紀錄第 31 輪）→ [(開始, 結束, 顯示的寫法, 是不是問句)]：照句尾分句，最後沒有句尾的那一段也算；
    一句裡用「、」接的每一段各算一段（「發布到哪個 topic、頻率多少、會不會發 TF？」是三段）。結束是那一段最後一個字的下一個位置；句子的最後一段
    顯示時附上句尾；那一句是「？」「?」結尾的，每一段都是問句（第 32 輪：問的要放進項目）。沒有字的不算。"""
    out, start = [], 0
    for stop, nxt in [(m.start(), m.end()) for m in _SENTENCE_END.finditer(text)] + [(len(text), len(text))]:
        pieces = text[start:stop].split("、")
        asked = text[stop:nxt] in ("？", "?")
        pos = start
        for k, piece in enumerate(pieces):
            body = piece.strip()
            if body:
                s = pos + len(piece) - len(piece.lstrip())
                out.append((s, s + len(body), body + (text[stop:nxt] if k == len(pieces) - 1 else ""), asked))
            pos += len(piece) + 1
        start = nxt
    return out


def load_registry(base_path, tools_dir):
    """DOMAIN.md → {"domains": {名稱: composite.load_domain 的結果}, "shared": [工具], "hidden": {工具: 領域}, "skills": {有骨架的技能: 領域},
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
        d = composite.load_domain(base_path, tools_dir, name)
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


def _quote(rows, ref):
    """使用者看到的出處原文：報告裡寫到這個 檔案:行號 的行，先挑以它開頭的那一行（報告附的原文），沒有就用第一行。"""
    label = answers.ref_label(ref)
    rows = [r.lstrip("> ").strip() for r in rows]
    return next((r for r in rows if r.startswith(label)), rows[0] if rows else None)


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
                    self._notices.append("⚠️ 領域的規格有問題，這些領域先不交辦（主對話照舊用它們的工具）：" + "；".join(reg["problems"][:5]))
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
        """system prompt 的「交辦」一節；沒有領域時是空的。"""
        reg = self.domain_registry()
        if not reg["domains"]:
            return ""
        rows = [prompt_files.load("harness/system_prompt.md", "task_domain", title=composite.domain_label(d), intro=(d["intro"].split("\n") or [""])[0])
                for d in reg["domains"].values()]
        return prompt_files.load("harness/system_prompt.md", "tasks", domains="\n".join(rows), max=DOMAIN_ITEMS_MAX, tries=DOMAIN_ITEM_TRIES)

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
        """主 session 的技能索引（SKILLS.md）拿掉領域的工具（共用的以外）：那些交辦給領域 session。一節的工具全部拿掉時，整節
        （標題與說明，例如目標容器、ROS 2 Workspace）都不列。"""
        hidden = self.domain_registry()["hidden"]
        out = []
        for k, block in enumerate(self._index_blocks()):
            tools = [m.group(1) for ln in block if (m := _INDEX_LINE.match(ln))]
            if k and tools and all(t in hidden for t in tools):
                continue
            out += [ln for ln in block if not ((m := _INDEX_LINE.match(ln)) and m.group(1) in hidden)]
        return "\n".join(out)

    def _index_lines(self, tools):
        """技能索引裡這幾個工具的那一行（領域 session 的技能清單，照 tools 的順序）。工具所在的那一節有說明（> 開頭的，例如目標容器、
        ROS 2 Workspace）時，放在那一節第一個工具的前面：說明跟著工具走。"""
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
            out.append(rows.get(t, f"- [{t}](tools/{t}.md)"))
        return "\n".join(out)

    # ---------------------------------------------------------------- 一回合的狀態
    def _reset_domain_turn(self):
        """使用者送出新的問題：這一回合交辦過的、報告歸零（回答確認關卡不算新的問題）。"""
        self._domain_turn = {"tasks": [], "reports": [], "reply_nudged": False, "cover_asked": False,
                             "since": len(getattr(self, "trajectory", None) or [])}     # 這一回合的工具結果從軌跡的第幾筆開始

    def _tool_of(self, token):
        """技能名稱、規格（.md）或腳本 → 技能名稱；不是任何技能回 None。"""
        name = os.path.basename(token)
        name = name[:-3] if name.endswith(".md") else name
        if os.path.exists(os.path.join(self.tools_dir, f"{name}.md")):
            return name
        return self._script_skill_map().get(self._normalize_script_name(name))

    def domain_gate(self, token):
        """主模型直接叫領域的工具（技能名稱或腳本）回 [ERROR]（附下一步）；叫有骨架的技能的名稱（或寫成腳本的 <名稱>_cmd.py）也一樣；
        寫的是領域的名稱，說明要交辦（domain_named）。說明裡的領域寫它做什麼、不寫識別名稱（composite.domain_label）。
        領域 session 裡（agent._sub_allowed）只能用它選的領域的工具與共用的工具。可以用回 None（不是任何技能的照舊交給後面的檢查）。"""
        skill = self._tool_of(token)
        reg = self.domain_registry()
        name = os.path.basename(token)
        name = name[:-3] if name.endswith(".md") else name[:-len("_cmd.py")] if name.endswith("_cmd.py") else name
        composite_of = reg["skills"].get(name) if skill is None else None
        allowed = getattr(self, "_sub_allowed", None)
        if allowed is not None:
            if (skill is None and composite_of is None) or skill in allowed["tools"]:
                return None
            return "[ERROR] " + prompt_files.load("domain/session.md", "not_my_tool", tool=skill or name, tools="、".join(sorted(allowed["tools"])))
        if skill is None and name in reg["domains"]:      # 主 session 把領域的名稱當技能叫（e4b；設計筆記 2.64）：寫明要交辦
            return "[ERROR] " + _d("domain_named", name=name)
        if composite_of:
            return "[ERROR] " + _d("skill_blocked", skill=name, domain=composite.domain_label(reg["domains"][composite_of]))
        if skill not in reg["hidden"]:
            return None
        return "[ERROR] " + _d("tool_blocked", tool=skill, domain=composite.domain_label(reg["domains"][reg["hidden"][skill]]))

    # ---------------------------------------------------------------- 交辦
    def run_task(self, action):
        """交辦（F1）：核對 → 交給領域 session → 報告存成 #編號交回（後面接依報告回答的說明）；停在確認關卡時回等回答的說明。
        核對沒過回 [ERROR]（附下一步），不執行。"""
        task = action.get("task") or {}
        goal = task.get("goal") or ""
        items = [x["quote"] for x in task.get("items") or []]       # 每一項是使用者的原話（框架討論紀錄第 27 輪）
        background = [x["quote"] for x in task.get("background") or []]     # 背景與限制也是原話、只用來理解（第 32 輪的 U1）
        constraints = [x["quote"] for x in task.get("constraints") or []]
        why = self._check_task(goal, items, background, constraints)
        if why:
            return "[ERROR] " + why
        turn = self._domain_turn
        entry = {"key": [goal, items], "goal": goal, "items": items, "background": background, "constraints": constraints,
                 "n": len(turn["tasks"]) + 1, "job": None, "status": None, "steps": "", "note": "", "report": "", "result_id": None,
                 "answered": [], "previous": self._previous()}
        turn["tasks"].append(entry)
        before = (self.current_cwd, self.container_cwd, self.target_container)
        job = domain_session.DomainSession(self, self.domain_registry()).start(self.current_task or goal, goal, items,
                                                                               previous=entry["previous"], attempt=entry["n"],
                                                                               earlier=self._earlier_turns(),
                                                                               background=background, constraints=constraints)
        return self._task_finish(entry, job, before)

    def _check_task(self, goal, items, background=(), constraints=()):
        """交辦的核對：有領域、子目標不是空的、項目 1～DOMAIN_ITEMS_MAX 項、每一項與每一則背景、限制（使用者的原話）一字不改地在使用者說過的話裡
        （_user_words）、一輪的第一次交辦要把最新這一則的每一句、一句裡用「、」接的每一段放進項目、背景或限制，問句（「？」結尾的那一句）的每一段
        要在項目裡（_uncovered；交回一次，交回過照收——框架討論紀錄第 28、31、32 輪）、跟這一回合交辦過的不一樣（一樣的再交一次結果也一樣）、
        同一個項目最多 DOMAIN_ITEM_TRIES 次。過了回 None，沒過回說明（不含 [ERROR]）。"""
        turn = self._domain_turn
        if not self.domain_registry()["domains"]:
            return _d("err_no_domain")
        if not goal:
            return _d("err_goal")
        if not 1 <= len(items) <= DOMAIN_ITEMS_MAX:
            return _d("err_items", count=len(items), max=DOMAIN_ITEMS_MAX)
        said = self._user_words()
        for k, it in enumerate(items, 1):
            if not composite._unquote(it) or composite._unquote(it) not in said:
                return _d("err_quote", k=k, quote=it or "（空的）")
        for field, quotes in ((_d("field_background"), background), (_d("field_constraints"), constraints)):
            for k, it in enumerate(quotes, 1):
                if not composite._unquote(it) or composite._unquote(it) not in said:
                    return _d("err_quote_context", field=field, k=k, quote=it or "（空的）")
        if not turn["tasks"] and not turn["cover_asked"]:
            missing = self._uncovered(list(items) + list(background) + list(constraints))
            asked = [p for p in self._uncovered(items, asked_only=True) if p not in missing]
            if missing or asked:
                turn["cover_asked"] = True
                return "\n".join(([_d("err_cover", questions="、".join(f"「{q}」" for q in missing))] if missing else [])
                                 + ([_d("err_cover_asked", questions="、".join(f"「{q}」" for q in asked))] if asked else []))
        same = next((x for x in turn["tasks"] if x["key"] == [goal, items]), None)
        if same:
            return _d("err_same", n=same["n"], status=domain_session.STATUS_TEXT.get(same["status"], same["status"] or "—"))
        for it in items:
            tries = [x for x in turn["tasks"] if answers.norm(it) in {answers.norm(y) for y in x["items"]}]
            if len(tries) >= DOMAIN_ITEM_TRIES:
                return _d("err_item_tries", item=it, n=len(tries), max=DOMAIN_ITEM_TRIES, history=self._task_history(tries))
        return None

    def _uncovered(self, quotes, asked_only=False):
        """最新這一則裡，沒有跟這幾則原話任何一則重疊的那幾段（ask_parts：每一句、一句裡用「、」接的每一段；照 _user_words 的方式正規化空白）；
        asked_only：只看問句（「？」結尾的那一句）的那幾段。"""
        text = composite._norm(self.current_task or "")
        spans = []
        for it in quotes:
            q = composite._unquote(it)
            at = text.find(q) if q else -1
            while at >= 0:
                spans.append((at, at + len(q)))
                at = text.find(q, at + 1)
        return [shown for s, e, shown, asked in ask_parts(text)
                if (asked or not asked_only) and not any(a < e and b > s for a, b in spans)]

    def _earlier_turns(self):
        """【前文】的來源（框架討論紀錄第 28 輪）：任務線上這一則之前的使用者的話（最多 TASK_HISTORY_KEEP − 1 則），各附那一回合最後的回覆
        （reply 與 answers；不含 thought、工具結果）→ [{"user", "reply"}]。程式從 messages 取：使用者的訊息以那一句開頭（後面可能接了技能規格
        或影像分析）；那一回合被壓縮掉了的只有使用者的話。/clear 之後沒有。"""
        now = self.current_task or ""
        earlier = [t for t in (self.task_history or [])[:-1] if t and t != now]
        if not earlier:
            return []
        msgs = list(self.messages)

        def said(i, t):
            m = msgs[i]
            return m.get("role") == "user" and str(m.get("content") or "").strip().startswith(t.strip())

        end = max((i for i in range(len(msgs)) if said(i, now)), default=len(msgs))
        out = []
        for t in earlier:
            start = max((i for i in range(end) if said(i, t)), default=None)
            reply = ""
            if start is not None:
                stop = next((i for i in range(start + 1, end) if any(said(i, u) for u in earlier)), end)
                last = next((msgs[i] for i in range(stop - 1, start, -1) if msgs[i].get("role") == "assistant"), None)
                parsed = parse_agent_reply(last["content"]) if last else {"valid": False}
                if parsed["valid"]:
                    reply = "\n".join(x for x in (parsed["reply"], answers_text(parsed["answers"])) if x)
            out.append({"user": t, "reply": reply})
        return out

    def _user_words(self):
        """交辦的原話要在這裡：這段對話裡使用者說過的每一則（set_current_task 記的 _user_said，加上這一則），空白正規化之後接在一起。"""
        said = [x["text"] for x in getattr(self, "_user_said", None) or []] + [self.current_task or ""]
        return "\n".join(composite._norm(x) for x in said)

    def _previous(self):
        """這一回合之前的交辦 → 領域 session 的「上一次的經過」（每一次的步驟、結果、原因；程式從紀錄取）。"""
        return [{"n": x["n"], "job": x["job"], "status_text": domain_session.STATUS_TEXT.get(x["status"], x["status"] or "—"),
                 "note": x["note"], "steps": x["steps"]} for x in self._domain_turn["tasks"] if x["job"]]

    def _task_history(self, entries):
        return "\n".join(_d("history_line", n=x["n"], goal=x["goal"], status=domain_session.STATUS_TEXT.get(x["status"], x["status"] or "—"))
                         for x in entries)

    def _task_finish(self, entry, job, before, prefix=""):
        """領域 session 的 job → 交回主模型的文字（存成 #編號）；停在確認關卡時設 domain_pending、回等回答的說明。"""
        entry.update(job=job["id"], status=job["status"], steps=domain_session.steps_text(job), note=(job.get("result") or {}).get("note") or "",
                     answered=domain_session.answered_items(job))
        if job["status"] == "need_user":
            need = job["need_user"]
            self.domain_pending = {"job": job["id"], "kind": need["kind"], "question": need.get("question") or "", "entry": entry, "before": before}
            return _d("ask_waiting", question=self.domain_pending["question"])
        self.domain_pending = None
        report = (job.get("result") or {}).get("report") or ""
        analysis = domain_session.analysis_reports(self, job)
        if analysis:                # 領域 session 裡執行的數據分析（原樣附在報告裡），主對話的回答照它核對（analysis_reply_check）
            self.note_analysis_report(analysis[-1][1])
        self._domain_turn["reports"].append(report)
        entry["report"] = report
        text = prefix + _d("report", status=domain_session.STATUS_TEXT.get(job["status"], job["status"]), report=report)
        self.last_receipt = None
        self._record_trajectory("domain_task", [entry["goal"]] + entry["items"], DOMAIN_RESULT_HEAD + text, *before)
        entry["result_id"] = self.last_result_id
        items = self.domain_items()
        hint = _d("answer_hint", items="\n".join(f"{k}. {x}" for k, x in enumerate(items, 1))) if items else ""
        return DOMAIN_RESULT_HEAD + text + ("\n\n" + hint if hint else "")

    # ---------------------------------------------------------------- 問使用者（程式轉、程式接回）
    def domain_ask_text(self):
        """給使用者看的：領域 session 停在確認關卡要問的事。"""
        p = self.domain_pending
        if not p:
            return ""
        return "\n".join([f"🗺️ 要確認：{p['question']}", "回答「是」照做，「否」不做；也可以取消。"])

    def answer_domain(self, text):
        """使用者回答確認關卡：交給領域 session 接回同一步。還要再問（下一個確認關卡）回 None（domain_pending 已更新）；做完回交給主模型的文字。"""
        p = self.domain_pending
        if not p:
            return None
        text = (text or "").strip()
        job = domain_session.DomainSession(self, self.domain_registry()).resume(p["job"], approve=text.lower() in _YES)
        if not job:
            self.domain_pending = None
            return "[ERROR] " + _d("err_lost")
        out = self._task_finish(p["entry"], job, p["before"], prefix=_d("answered", answer=text))
        return None if job["status"] == "need_user" else out

    def cancel_domain(self, follow=True):
        """使用者取消確認關卡：領域 session 照做到的收尾，交回主模型的文字（follow＝False 是 /clear：只照實記下）。"""
        p = self.domain_pending
        if not p:
            return None
        job = domain_session.DomainSession(self, self.domain_registry()).cancel(p["job"])
        self.domain_pending = None
        if not job:
            return "[ERROR] " + _d("err_lost")
        text = self._task_finish(p["entry"], job, p["before"])
        return text if follow else DOMAIN_RESULT_HEAD + _d("cancelled")

    # ---------------------------------------------------------------- 依報告回答（每一項的回答由程式核對、照項目排）
    def domain_items(self):
        """這一回合交辦、有報告的項目（依報告回答時 answers 照這個編號；同樣的項目只列一次，照第一次出現的順序）。"""
        out, seen = [], set()
        for x in (getattr(self, "_domain_turn", None) or {}).get("tasks") or []:
            if x.get("report"):
                for it in x["items"]:
                    if answers.norm(it) not in seen:
                        seen.add(answers.norm(it))
                        out.append(it)
        return out

    def _turn_results(self):
        """這一回合執行過、有存檔的工具結果（交辦的結果本身不算；領域 session 的工具結果也在軌跡裡）：[(軌跡的紀錄, 存檔的路徑)]。"""
        recs = (getattr(self, "trajectory", None) or [])[self._domain_turn.get("since", 0):]
        return [(r, os.path.join(self.results_dir(), r["result_file"])) for r in recs
                if r.get("result_file") and not str(r.get("script") or "").startswith("domain_")]

    def _known_ids(self):
        """依報告回答時能當出處的 #編號：交辦的結果本身、這一回合執行過的工具結果。報告文字裡出現、但不是這些的不算。"""
        turn = self._domain_turn
        return {str(x["result_id"]) for x in turn["tasks"] if x.get("result_id")} | {str(r["id"]) for r, _ in self._turn_results()}

    def _cited(self, ref):
        """一個出處 → (種類, 對到的行, 那幾段的文字, 行號)。種類：line（檔案:行號）、id（#編號）、unknown（報告與這一回合的工具結果都沒有）、
        form（寫法看不懂）。報告裡沒有的，再看這一回合執行過的工具（收據裡有的 檔案:行號、存檔的 #編號）。行號的出處要在報告的某一行
        （後面不能再接數字：a.py:4 不算 a.py:48），那幾段是那幾行所在的整節；#編號 是報告裡出現的編號或交辦的結果本身，那幾段是提到它的節，
        加上那份存檔的原文。"""
        reports = self._domain_turn["reports"]
        m = answers.CITE.search(ref)
        if m:
            path, first, last = answers.span(m)
            rows, texts = self._rows_for(path, first, last, reports)       # 路徑的結尾一樣就算（報告寫完整路徑、回答只寫後面幾段）
            if not rows and "/" in path:                    # 目錄寫錯或省略了一段：檔名與行號在報告裡只對到一個檔案就算
                rows, texts = self._rows_for(os.path.basename(path), first, last, reports)
                if len({answers.REF.search(r).group().rsplit(":", 1)[0] for r in rows if answers.REF.search(r)}) != 1:
                    rows, texts = [], []
            if not rows:                                    # 報告裡沒有：這一回合執行過的工具（收據裡有這一行）
                rows, texts = answers.rows_from_archives([a for _, a in self._turn_results()], path, first, last, self.current_cwd)
            return ("line" if rows else "unknown"), rows, texts, list(range(first, last + 1))
        m = answers.ID.search(ref)
        if m:
            rid = m.group(1)
            if rid not in self._known_ids():
                return "unknown", [], [], []
            texts = [sec for rep in reports for sec in answers.sections(rep) if re.search(rf"#{rid}(?!\d)", sec)]
            if rid in {str(x["result_id"]) for x in self._domain_turn["tasks"] if x.get("result_id")}:
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
        """answers 的核對 → {項目編號: [沒過的原因]}（0＝回覆的開頭）；全部過了是空的。答到的照 answers.answer_problems；另外報告裡這一項的
        回答（領域 session 寫的、過了它的核對）寫的編號與數字，回答裡要有（answers.dropped；同一個項目交辦好幾次的看最後一次）。"""
        items, turn = self.domain_items(), self._domain_turn
        allowed = "\n".join([self.current_task or ""] + items + [x["goal"] for x in turn["tasks"]])
        out = answers.answer_problems(items, parsed.get("answers"), self._cited, allowed, "\n".join(turn["reports"]))
        reported = {answers.norm(it): text for x in turn["tasks"] for it, text in x.get("answered") or []}
        given = {a["item"]: a for a in parsed.get("answers") or [] if 1 <= a["item"] <= len(items)}
        for k, it in enumerate(items, 1):
            a, text = given.get(k), reported.get(answers.norm(it))
            lost = answers.dropped(text, " ".join([a["text"]] + list(a["refs"])), allowed) if a and text else []
            if lost:
                out.setdefault(k, []).append(_d("why_dropped", tokens="、".join(lost)))
        lead = [r for r in dict.fromkeys(answers.REF.findall(parsed.get("reply") or "")) if self._cited(r)[0] != "line"]
        if lead:
            out[0] = [_d("why_lead_refs", refs="、".join(lead))]
        return out

    def domain_reply_check(self, parsed):
        """這一回合有交辦的報告、主模型回答了（沒有動作）：核對 answers（_answer_problems），沒過的只把那幾項交回修一次（回傳交回的文字）；
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
        """使用者看到的回答：回覆的開頭，接著照項目排——每一項的回答與出處，答到的附出處那一行的原文（從報告取，最多 DOMAIN_QUOTE_LINES 行），
        查不到的寫原因，沒有通過核對的標出來附報告的 #編號。這一回合沒有交辦的報告、或還有動作時回 None（照模型的回覆）。"""
        items = self.domain_items()
        if not items or not parsed or parsed.get("action") or not parsed.get("valid", True):
            return None
        turn = self._domain_turn
        problems = self._answer_problems(parsed)
        given = {a["item"]: a for a in parsed.get("answers") or [] if 1 <= a["item"] <= len(items)}
        ids = "、".join(f"#{x['result_id']}" for x in turn["tasks"] if x.get("report") and x.get("result_id")) or "—"
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
        return "\n".join(out)
