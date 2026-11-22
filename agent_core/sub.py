"""新架構的子工作階段（第 5 步；〈新架構討論紀錄〉第 4 節〈第 5 步〉）：沒有複合技能的領域、或中階沒有做完也沒有報告時（沒有適合的做法、
失敗、使用者取消），程式開一個子工作階段，用這個領域的工具照現在主對話的方式一步一步做（D2：不寫 SOP），做完由程式整理成報告交回主對話。

1. **自己的對話**（架構圖的「子工作階段隔離」、D7）：system prompt 是這個領域的說明、〈做法〉（SKILLS.md 的那一節，現在的做法）、能用的工具
   與長期記憶；第一則訊息是它的子目標、要回答的項目、前面的領域查到的、這個問題的分工（每個領域的子目標、主對話這一回合做過的）、
   使用者的原始問題（只用來對照名稱與數值），再交時加上一次的經過（第 5 步 5-3：高階分工，下一層只做自己的子目標）。試錯（載入規格、
   參數寫錯重下）只在這裡，存在 logs/sub_jobs/<編號>/job.json 的 messages；主對話只收到報告。
2. **每一步跟主對話走同一條路**（agent._run_tool_once）：先載入規格再執行、存檔 #編號、收據、狀態標記的同步（docker_open 換目標容器，主對話
   之後也看得到）；太長的工具回傳照舊提煉（錨點換成原始問題、子目標與這一步的目的）；卡住偵測照主對話的規則（turn_guard.RepeatTracker，
   卡住就收尾）。只能用這個領域的工具與共用的工具（DOMAIN.md），其他的回 [ERROR]（orchestrator.domain_gate 看 agent._sub_allowed）；
   提煉結尾的下一步建議、怎麼回存檔看也只寫它能用的（result_grep、result_view；設計筆記 2.47：以前叫它用 result_recall，全部被擋）。
   對話太長時，送給模型的那一份把舊的工具結果換成存檔編號（存著的對話不動）。
3. **確認關卡**：會改狀態的工具照舊先問使用者——子工作階段停下來（need_user），高階轉問（domain_pending），resume 接回同一步；拒絕就把
   [DENIED] 交給模型接著做；cancel（使用者取消）照做到的收尾。
4. **收尾**：模型回 action null 加 answers（每一項：答到／查不到／不屬於這個領域、回答或理由、出處＝這個子工作階段的工具結果 #編號，或收據裡的
   檔案:行號；查不到、不屬於的那一項另外選哪個領域查得到（system prompt 列的其他領域，或 none；第 5 步 5-4：schema 的欄位，高階照它列給
   主模型再分工）；每一項都不屬於這個領域＝這個子工作階段不屬於這個領域，高階照中階的處理排除、交回主模型重新分工），
   程式照 4-2 核對（answers.answer_problems：出處在自己的工具結果裡、數字與名稱在出處裡、查不到的寫原因），沒過的交回修一次；
   步數用完（SUB_STEPS_MAX）、卡住、使用者取消、模型沒有回覆也收尾，報告寫明做到哪裡。每一則不是用工具就是收尾：action null、answers
   也是空的（沒有動作也沒有回答）不算收尾，提醒一次（上一步之後只提醒一次，不算交回修）；寫到字串上限被截斷的回覆不執行、重問一次
   （第 5 步 5-1 的評測：26b 的第一則常沒有動作也沒有回答，被當成收尾、用掉交回修，有的一步都沒做就結束）。
5. **報告**（程式整理，report.md）：每一項的回答與出處（核對過的；沒過的標出來；檔案:行號 附那一行的原文；查不到、不屬於的寫查得到的領域）、
   每一步（工具、參數、結果、#編號、確認關卡的決定）；analysis_run 的事實報告原樣附在最後（第 5 步 G4：主對話照它核對回答，
   orchestrator._domain_outcome）。
   主對話照 4-2 依報告回答。
"""
import os
import time

from skills_system.scripts import _results_common
from . import answers, prompt_files
from .config import (ANALYSIS_REPORT_HEAD, DOMAIN_QUOTE_LINES, MID_JOBS_DIRNAME, NUM_CTX, SUB_JOBS_DIRNAME, SUB_JOBS_KEEP, SUB_MODEL,
                     SUB_STEPS_MAX, TOKEN_THRESHOLD, TOOL_SUMMARY_DEFAULT)
from .jobstore import JobStore
from .protocol import action_text, drop_cut, is_skill_doc_result, parse_agent_reply, tool_result_message
from .schemas import NO_ROUTE, agent_reply_schema
from .turn import _content_for_context
from .turn_guard import RepeatTracker

STATUS_TEXT = {"running": "執行中", "need_user": "等使用者回答", "done": "做完", "stopped": "停下來（步數用完或卡住）",
               "cancelled": "使用者取消", "failed": "失敗（模型沒有回覆）", "out_of_domain": "不屬於這個領域"}
STEP_SKILL = "一步一步（子工作階段）"      # 交給中階的上一次的經過、報告、主對話看到的「做法」
_KEEP_RESULTS = 3                           # 對話太長時，最新的這幾份工具結果不清


def _s(key, /, **fields):
    """prompts/sub/session.md 的一則。"""
    return prompt_files.load("sub/session.md", key, **fields)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _show_params(values):
    return "；".join(f"{k}＝{'、'.join(map(str, v)) if isinstance(v, list) else v}" for k, v in (values or {}).items()) or "—"


def searched(job):
    """子工作階段搜過的字（search_text 的第一個參數，| 分開的每一個）：高階交「上一次的經過」用。"""
    out = []
    for st in job.get("steps") or []:
        if st.get("tool") == "search_text" and not st.get("doc") and st.get("args"):
            for w in str(st["args"][0]).split("|"):
                w = w.strip()
                if w and w.lower() not in {x.lower() for x in out}:
                    out.append(w)
    return out


def analysis_reports(agent, job):
    """子工作階段裡 analysis_run 的事實報告：[(#編號, 原文)]（從存檔讀；第 5 步 G4：原樣附在報告裡，主對話的回答照它核對）。"""
    out = []
    for st in job.get("steps") or []:
        if st.get("tool") == "analysis_run" and not st.get("doc") and st.get("status") == "PASS" and st.get("result_id"):
            path = agent.result_file_path(st["result_id"])
            text = "\n".join(_results_common.read_body(path)[1]).strip() if path else ""
            if text.startswith(ANALYSIS_REPORT_HEAD):
                out.append((st["result_id"], text))
    return out


def calls(job):
    """子工作階段執行過的工具（不含載入規格、使用者沒有同意的）：評測的 worker 記成 via、高階記進交給領域的紀錄。"""
    return [{"tool": st["tool"], "script": st.get("script"), "args": st.get("args") or [], "status": st["status"], "head": st.get("head", "")}
            for st in job.get("steps") or [] if st.get("tool") and not st.get("doc") and st["status"] != "DENIED"]


class Session:
    """一個領域的子工作階段：start(問題, 子目標, 項目) → job（也存成 job.json）；停在確認關卡時 resume(編號, approve=…)，使用者不回答
    cancel(編號)。tools：這一次能用的工具（領域的工具加上共用的工具）；title、intro、practice：領域的標題、說明與〈做法〉（mid.load_domain）；
    others：其他領域 [(名稱, 標題, 說明的第一行)]（查不到、不屬於的那一項選哪個領域查得到，第 5 步 5-4）。"""

    def __init__(self, agent, domain, tools=(), title="", intro="", practice="", others=()):
        self.agent = agent
        self.domain = domain
        self.tools = list(dict.fromkeys(tools))
        self.title, self.intro, self.practice = title or domain, intro, practice
        self.others = [tuple(o) for o in others if o[0] != domain]
        self.store = JobStore(os.path.join(agent.script_dir, "logs", SUB_JOBS_DIRNAME))

    # ---------------------------------------------------------------- 進入點
    def start(self, question, goal, items, on_start=None, previous=None, attempt=1, known="", division=""):
        """previous：同一個問題之前交給這個領域的經過（[{"n", "job", "kind", "skill", "params", "status", "status_text", "note", "searched",
        "items"}]，高階取的；中階剛剛沒做完的那一次也在裡面）；attempt：這是第幾次；known、division：前面的領域查到的、這個問題的分工
        （高階組好的文字，orchestrator._known_text、_division_text）。"""
        jid = self.store.new_id()
        self.store.prune(SUB_JOBS_KEEP)
        previous = list(previous or [])
        job = {"id": jid, "kind": "sub", "status": "running", "created": _now(), "updated": _now(), "cwd": self.agent.current_cwd,
               "domain": self.domain, "question": question, "goal": (goal or question).strip(), "items": list(items or []),
               "attempt": attempt, "previous": previous, "known": known, "division": division, "tools": self.tools, "system": self._system(),
               "messages": [], "steps": [], "need_user": None, "asked": [], "nudged": False, "empty_at": None, "answers": [], "problems": {},
               "result": None}
        job["messages"].append({"role": "user", "content": self._first(job)})
        self.store.save(job)
        self._link(previous, jid, attempt)
        if on_start:
            on_start(jid)
        self._note(jid, f"🧩 子工作階段（{self.domain}）開始：{job['goal'][:80]}")
        return self._loop(job)

    def resume(self, jid, approve=None):
        """接回停在確認關卡的子工作階段：同意就照原本的動作執行，不同意就把 [DENIED] 交給模型接著做。"""
        job = self.store.load(jid)
        if not job or job["status"] != "need_user":
            return job
        need = job["need_user"]
        if job.get("asked"):
            job["asked"][-1].update(approve=bool(approve), answered=_now())
        job.update(status="running", need_user=None)
        parsed = {"thought": need.get("thought", ""), "reply": need.get("reply", ""), "action": need["action"]}
        if approve:
            stuck = self._step(job, parsed, approved=True, guarded=True)
        else:
            stuck = self._step(job, parsed, output=self.agent.guard_denied_text(need["guard"]), guarded=True)
        return self._finish(job, "stopped", note=stuck) if stuck else self._loop(job)

    def cancel(self, jid):
        """使用者不回答、取消確認關卡：照做到的收尾（報告寫明停在哪一步）。"""
        job = self.store.load(jid)
        if not job or job["status"] != "need_user":
            return job
        if job.get("asked"):
            job["asked"][-1].update(cancelled=True, answered=_now())
        return self._finish(job, "cancelled", note=f"要確認的是：{job['need_user'].get('command') or job['need_user']['question']}")

    # ---------------------------------------------------------------- 一步一步
    def _loop(self, job):
        while True:
            if len(job["steps"]) >= SUB_STEPS_MAX:
                return self._finish(job, "stopped", note=f"步數用完（最多 {SUB_STEPS_MAX} 步），照做到的收尾")
            parsed, raw = self._ask(job)
            if parsed is None:
                return self._finish(job, "failed", note="子工作階段的模型沒有回覆（或回覆不是 JSON）")
            job["messages"].append({"role": "assistant", "content": raw})
            if not parsed["action"] and not parsed["answers"] and job.get("empty_at") != len(job["steps"]):
                # 沒有動作也沒有回答：不是用工具、也不是收尾。提醒一次（上一步之後只一次），不算交回修
                job["empty_at"] = len(job["steps"])
                job["messages"].append({"role": "user", "content": _s("empty_turn")})
                job["updated"] = _now()
                self.store.save(job)
                self._note(job["id"], "🧩 沒有動作也沒有回答：提醒它用工具或收尾")
                continue
            if not parsed["action"]:
                problems = self._problems(job, parsed["answers"])
                if problems and not job["nudged"]:
                    job["nudged"] = True
                    rows = [prompt_files.load("harness/domain.md", "answers_problem", k=k, item=job["items"][k - 1], why="；".join(w))
                            for k, w in sorted(problems.items())]
                    job["messages"].append({"role": "user", "content": _s("answers_fix", problems="\n".join(rows))})
                    job["updated"] = _now()
                    self.store.save(job)
                    self._note(job["id"], f"🧩 回答有 {len(problems)} 項沒有通過核對，交回修一次")
                    continue
                given = [a for a in parsed["answers"] if 1 <= a["item"] <= len(job["items"])]
                if given and len({a["item"] for a in given}) == len(job["items"]) and all(a["status"] == "out_of_domain" for a in given):
                    return self._finish(job, "out_of_domain", note="；".join(dict.fromkeys(a["text"] for a in given if a["text"])) or "—",
                                        reply=parsed["reply"], answered=parsed["answers"], problems=problems)
                return self._finish(job, "done", reply=parsed["reply"], answered=parsed["answers"], problems=problems)
            guard = self.agent.guard_check(parsed)
            if guard:
                return self._wait(job, parsed, guard)
            stuck = self._step(job, parsed)
            if stuck:
                return self._finish(job, "stopped", note=stuck)

    def _step(self, job, parsed, approved=False, output=None, guarded=False):
        """執行一步（output 給了＝使用者沒有同意，不執行），結果接進子工作階段的對話、記一筆 steps；卡住時回傳說明。"""
        action = parsed["action"]
        payload = action_text(action).strip()
        parts = payload.split(maxsplit=1)
        token = os.path.basename(parts[0]) if parts else ""
        script = self.agent._normalize_script_name(token)
        tool = self.agent._script_skill_map().get(script) or (token[:-3] if token.endswith(".md") else token)
        denied = output is not None
        if not denied:
            output = self._execute(action, approved) or ""
        doc = is_skill_doc_result(output)
        rid = None if doc or denied else self.agent.last_result_id
        receipt = None if doc or denied else self.agent.last_receipt
        tracker = RepeatTracker()                 # 卡住偵測：照之前每一步重算（停在確認關卡、接回之後也接得上）
        for st in job["steps"]:
            tracker.note(st["action"], st["rep"])
        shown, times = tracker.note(payload, output)
        step = {"n": len(job["steps"]) + 1, "time": _now(), "thought": parsed.get("thought", ""), "reply": parsed.get("reply", ""),
                "action": payload, "tool": tool, "script": script, "doc": doc,
                "args": [] if doc else self.agent._parse_script_args(script, parts[1] if len(parts) > 1 else ""),
                "status": "DENIED" if denied else "ERROR" if output.lstrip().startswith("[ERROR]") else "PASS",
                "result_id": rid, "head": output.strip().splitlines()[0][:200] if output.strip() else "", "rep": output.strip()[:500],
                "receipt": {k: receipt.get(k) for k in ("status", "error_kind", "counts", "truncated")} if receipt else None,
                "guard": {"approve": not denied} if guarded else None}
        content = shown
        if not doc and not denied:
            content = _content_for_context(shown, self.agent.count_tokens(shown), self.agent, use_summary=TOOL_SUMMARY_DEFAULT,
                                           step={"thought": step["thought"], "reply": step["reply"], "action": action}, anchor=self._anchor(job),
                                           sub=True)
        step["summarized"] = content != shown
        if rid:
            content = _s("result_id", rid=rid) + "\n" + content
        job["steps"].append(step)
        job["messages"].append({"role": "user", "content": tool_result_message(content, action)})
        job["updated"] = _now()
        self.store.save(job)
        self._note(job["id"], f"🧩 第 {step['n']} 步：{payload[:100]} → {step['status']}" + (f"（#{rid}）" if rid else ""))
        if times:
            return f"同樣的動作 {times} 次都得到同樣的結果（{payload[:60]}），卡住了，照做到的收尾"
        return None

    def _execute(self, action, approved):
        if action.get("domains"):                   # 子工作階段的 schema 沒有這一種，保險
            return "[ERROR] " + _s("not_my_tool", tool="交給領域", domain=self.domain, tools="、".join(self.tools))
        self.agent._sub_allowed = {"domain": self.domain, "tools": set(self.tools)}
        try:
            return self.agent._run_tool_once({"action": action, "thought": "", "reply": "", "valid": True}, approved)
        finally:
            self.agent._sub_allowed = None

    def _ask(self, job):
        """模型一次 → (parsed, 原文)。不是 JSON 或是空的：附上那一則與提醒再問一次，兩次都不行回 (None, 原文)。寫到字串上限被截斷
        （parsed 的 cut）：不執行，只接提醒再問一次（不把那一大段截斷的回覆放進去）；還是被截斷就 protocol.drop_cut（截斷的動作不執行，
        存進對話的是不含截斷參數的 JSON）。每次呼叫記進 calls.jsonl（送出的最後一則與回覆；system prompt 在 job.json 的 system，
        前面的對話在 messages）。"""
        msgs = self._fit(job)
        schema = agent_reply_schema((), len(job["items"]), others=[o[0] for o in self.others])
        model = SUB_MODEL or self.agent.model
        raw = ""
        for attempt in range(2):
            t0, err = time.time(), None
            try:
                res = self.agent._timed_chat("sub_step", model=model, messages=msgs, format=schema,
                                             options={"temperature": 0.2, "num_ctx": NUM_CTX}, think=False)
                raw = (res["message"]["content"] or "").strip()
            except Exception as e:   # noqa: BLE001  模型呼叫失敗：當成沒有回覆
                raw, err = "", f"{type(e).__name__}: {e}"
            parsed = parse_agent_reply(raw)
            ok = parsed["valid"] and bool(parsed["action"] or parsed["reply"] or parsed["answers"])
            cut = parsed["cut"] if ok else []
            error = None if ok and not cut else err or ("寫到長度上限被截斷：" + "、".join(cut) if cut else "回覆不是 JSON 或是空的")
            self.store.append(job["id"], "calls.jsonl", {"role": "step", "step": len(job["steps"]) + 1, "model": model, "user": msgs[-1]["content"],
                                                         "response": raw, "error": error, "ms": round((time.time() - t0) * 1000)})
            if ok and not cut:
                return parsed, raw
            if cut and attempt:
                return drop_cut(parsed)
            msgs = msgs + ([{"role": "user", "content": _s("cut", fields="、".join(cut))}] if cut else
                           [{"role": "assistant", "content": raw}, {"role": "user", "content": _s("retry")}])
        return None, raw

    def _fit(self, job):
        """送給模型的對話：system prompt＋存著的對話，最後一則接上動態區（工作目錄、目標容器…）。超過硬水位時，舊的工具結果
        換成存檔編號（最新 _KEEP_RESULTS 份不動；存著的對話不改）。"""
        msgs = [{"role": "system", "content": job["system"]}] + [dict(m) for m in job["messages"]]
        msgs[-1]["content"] += "\n\n" + self.agent.build_state_tail()
        results = [i for i, m in enumerate(msgs) if m["role"] == "user" and m["content"].startswith("[tool result]")]
        size = sum(self.agent.count_tokens(m["content"]) for m in msgs)
        for k, i in enumerate(results[:-_KEEP_RESULTS] if len(results) > _KEEP_RESULTS else []):
            if size <= TOKEN_THRESHOLD:
                break
            st = job["steps"][k] if k < len(job["steps"]) else {}
            short = tool_result_message(_s("cleared", n=st.get("n", k + 1), rid=st.get("result_id") or "—", head=st.get("head", "")))
            size -= self.agent.count_tokens(msgs[i]["content"]) - self.agent.count_tokens(short)
            msgs[i] = {"role": "user", "content": short}
        return msgs

    def _wait(self, job, parsed, guard):
        need = {"kind": "guard", "question": self.agent.guard_prompt_text(guard), "command": guard.get("command", ""), "guard": guard,
                "action": parsed["action"], "thought": parsed.get("thought", ""), "reply": parsed.get("reply", ""), "candidates": []}
        job["asked"].append({"kind": "guard", "question": need["question"], "command": need["command"], "step": len(job["steps"]) + 1, "time": _now()})
        job.update(status="need_user", need_user=need, updated=_now())
        self.store.save(job)
        self._note(job["id"], f"🧩 要問使用者（確認關卡）：{need['command'][:100]}")
        return job

    # ---------------------------------------------------------------- 收尾：核對與報告
    def _archives(self, job):
        """這個子工作階段的工具結果：[(#編號, 存檔的路徑)]。"""
        out = []
        for st in job["steps"]:
            path = self.agent.result_file_path(st["result_id"]) if st.get("result_id") else None
            if path:
                out.append((st["result_id"], path))
        return out

    def _cited(self, job, ref, archives):
        """一個出處 → (種類, 對到的行, 那幾段的文字, 行號)：#編號 要是這個子工作階段的存檔；檔案:行號 要在它們的收據裡（那一行由程式從檔案讀）。"""
        m = answers.CITE.search(ref)
        if m:
            path, first, last = answers.span(m)
            rows, texts = answers.rows_from_archives([p for _, p in archives], path, first, last, job["cwd"])
            return ("line" if rows else "unknown"), rows, texts, list(range(first, last + 1))
        m = answers.ID.search(ref)
        if m:
            hit = [p for r, p in archives if str(r) == m.group(1)]
            return ("id", [], [answers.read(hit[0])], []) if hit else ("unknown", [], [], [])
        return "form", [], [], []

    def _problems(self, job, given):
        archives = self._archives(job)
        allowed = "\n".join([job["question"], job["goal"]] + job["items"])
        source = "\n".join(answers.read(p) for _, p in archives)
        return answers.answer_problems(job["items"], given, lambda ref: self._cited(job, ref, archives), allowed, source,
                                       unknown=lambda ref: _s("why_ref_unknown", ref=ref))

    def _finish(self, job, status, note="", reply="", answered=None, problems=None):
        problems = problems or {}
        job.update(status=status, need_user=None, updated=_now(), answers=answered or [], problems={str(k): v for k, v in problems.items()})
        report = self._report(job, note, reply, problems)
        self.store.write(job["id"], "report.md", report)
        job["result"] = {"status": status, "note": note, "report": report,
                         "sources": [st["result_id"] for st in job["steps"] if st.get("result_id")]}
        self.store.save(job)
        self._note(job["id"], f"🧩 子工作階段結束：{STATUS_TEXT[status]}" + (f"（{note[:100]}）" if note else ""))
        return job

    def _report(self, job, note, reply, problems):
        lines = [f"# 子工作階段的結果：{STATUS_TEXT[job['status']]}", f"- 問題：{job['question']}"]
        if job["goal"] != job["question"]:
            lines.append(f"- 子目標：{job['goal']}")
        lines += [f"- 要回答的項目 {k}：{x}" for k, x in enumerate(job["items"], 1)]
        if job["previous"]:
            lines.append(f"- 第 {job['attempt']} 次交給這個領域（之前：" + "；".join(
                f"第 {p.get('n')} 次 {p.get('skill') or '—'}：{p.get('status_text') or p.get('status') or '—'}" + (f"（{p['note']}）" if p.get("note") else "")
                for p in job["previous"]) + "）")
        lines.append(f"- 做法：{STEP_SKILL}，{len(job['steps'])} 步")
        if note:
            lines.append(f"- 說明：{note}")
        if reply:
            lines.append(f"- 總結：{reply}")
        lines += ["", "## 每一項的回答（子工作階段寫的；出處由程式核對）"]
        got = {a["item"]: a for a in job["answers"] if 1 <= a["item"] <= len(job["items"])}
        archives = self._archives(job)
        for k, item in enumerate(job["items"], 1):
            a = got.get(k)
            if a is None:
                lines.append(f"{k}. {item}：（沒有回答）")
            elif a["status"] in ("not_found", "out_of_domain"):
                lines.append(f"{k}. {item}：{'查不到' if a['status'] == 'not_found' else '不屬於這個領域'}。{a['text']}"
                             + (f"（查得到的領域：{a['domain']}）" if self._route(a) else ""))
            else:
                refs = list(dict.fromkeys(answers.ref_label(r) for r in a["refs"]))
                lines.append(f"{k}. {item}：{a['text']}" + (f"（出處：{'、'.join(refs)}）" if refs else ""))
                quotes = []
                for ref in a["refs"]:
                    kind, rows, _, _ = self._cited(job, ref, archives)
                    quotes += [r for r in rows[:1] if kind == "line" and r not in quotes]
                lines += [f"   > {q}" for q in quotes[:DOMAIN_QUOTE_LINES]]
            if k in problems:
                lines.append(f"   ⚠️ 沒有通過核對：{'；'.join(problems[k])}")
        lines += ["", "## 做了哪些步驟"]
        for st in job["steps"]:
            if st["doc"]:
                lines.append(f"{st['n']}. 載入 {st['tool']} 的規格")
            elif st["status"] == "DENIED":
                lines.append(f"{st['n']}. {st['action']} → 使用者沒有同意（確認關卡），沒有執行")
            else:
                lines.append(f"{st['n']}. {st['action']} → {st['head']}" + (f"（#{st['result_id']}）" if st.get("result_id") else "")
                             + ("（使用者同意）" if st.get("guard") else ""))
        if not job["steps"]:
            lines.append("（沒有執行任何工具）")
        for rid, text in analysis_reports(self.agent, job):      # G4：數據分析的報告原樣附上
            lines += ["", f"## 數據分析的報告（#{rid}，原樣）", text]
        return "\n".join(lines)

    # ---------------------------------------------------------------- 其他
    def _route(self, a):
        """一項回答寫的「哪個領域查得到」：其他領域的名稱才算（none、空的、不是其他領域的回空字串）。"""
        return a.get("domain") if a.get("status") != "answered" and a.get("domain") in {o[0] for o in self.others} else ""

    def _system(self):
        practice = _s("practice", practice=self.practice) if self.practice else ""
        others = "\n".join(_s("other_domain", title=t, intro=i) for _, t, i in self.others) or _s("no_other_domain")
        return _s("system", title=self.title, domain=self.domain, intro=self.intro or "—", practice=practice,
                  tools=self.agent._index_lines(self.tools), others=others, none=NO_ROUTE, steps=SUB_STEPS_MAX,
                  memory=self.agent.load_long_term_memory())

    def _first(self, job):
        items = "\n".join(f"{k}. {x}" for k, x in enumerate(job["items"], 1))
        prev = ""
        if job["previous"]:
            rows = [_s("previous_attempt", n=p.get("n"), skill=p.get("skill") or "—", params=_show_params(p.get("params")),
                       status=p.get("status_text") or p.get("status") or "—", note=f"（{p['note']}）" if p.get("note") else "",
                       searched="、".join(p.get("searched") or []) or "—", items="；".join(p.get("items") or []) or "—") for p in job["previous"]]
            prev = _s("previous", count=len({p.get("n") for p in job["previous"]}), attempts="\n".join(rows))
        return _s("first", question=job["question"], goal=job["goal"], items=items, known=job.get("known") or "",
                  division=job.get("division") or "", previous=prev)

    @staticmethod
    def _anchor(job):
        """提煉長輸出時的「使用者想知道什麼」：只放這一層的子目標與項目（5-3：原始問題裡其他的事分給了別的領域）。"""
        return _s("anchor", goal=job["goal"], items="；".join(job["items"]))

    def _link(self, previous, jid, attempt):
        """之前的工作（中階或子工作階段）記下這一次（決策圖從上一次連到下一次，4-2 的 I.4）。"""
        for p in previous:
            store = self.store if p.get("kind") == "sub" else JobStore(os.path.join(self.agent.script_dir, "logs", MID_JOBS_DIRNAME))
            pj = store.load(p.get("job")) if p.get("job") else None
            if pj:
                pj.setdefault("next", []).append({"job": jid, "n": attempt, "kind": "sub"})
                store.save(pj)

    def _note(self, jid, text):
        """進度：印出、記進 events.jsonl、交給畫面（progress_callback）。"""
        print(text)
        self.store.append(jid, "events.jsonl", {"text": text})
        cb = getattr(self.agent, "progress_callback", None)
        if cb:
            try:
                cb(text)
            except Exception:   # noqa: BLE001  畫面的問題不能中斷執行
                pass
