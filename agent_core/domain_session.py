"""領域 session（2026-11-23 框架，docs/框架討論紀錄.md）：主 session 交辦的任務（子目標、要回答的項目）在這裡做完，經過與結果交回主 session。

一個迴圈，每一輪模型回一個 JSON，state 是三種之一，由程式核對、照它接著做（F4）：
1. **domains**（選領域，可以多個）：要在 DOMAIN.md 的清單裡。程式載入這些領域的技能清單交給它——領域的〈做法〉、有骨架的技能（說明、
   什麼時候用、參數）、單步的工具（技能索引的那一行與〈語法〉的參數寫法）、共用的工具。第一輪一定是這個；重選最多 DOMAIN_RESELECT_MAX 次。
2. **skill**（用一個技能）：
   - 有骨架的技能（composite.py）：params 每個參數附一字不改的原文（F3），程式核對（composite.verify_param；原文＝問題、子目標、項目、
     前面每一步交給它的結果），沒過的交回改、不算一步；過了交給 composite.Runner 跑骨架與回退。缺參數、路徑有好幾個也交回它決定（附候選）。
   - 工具：args 照工具的〈語法〉寫，程式照技能名稱找腳本執行（agent._run_tool_once：跟主對話同一條路——確認關卡、存檔 #編號、收據、
     狀態標記的同步）；只能用選的領域的工具與共用的工具（orchestrator.domain_gate 看 agent._sub_allowed）。
   - 結果太長就分段提煉（turn._content_for_context；錨點是子目標與項目，事實附 檔案:行號），短的照原文；每份結果附 #編號。
   - 跟之前某一步一模一樣的技能＋參數不執行（附那一步的結果）；最多 DOMAIN_STEPS_MAX 步。
3. **report**（回報）：answers 照項目一項一筆（answered／not_found、回答、出處），程式核對（answers.answer_problems：出處是這個 session 的
   結果、數字與名稱在出處裡、查不到的寫原因），沒過的交回修一次；整理成報告交回主 session（F6）。
確認關卡：會改狀態的工具停下來（need_user），主 session 轉問使用者，resume 接回同一步；拒絕就把 [DENIED] 交給它接著做；cancel 照做到的收尾。
回覆不是 JSON 或空的重問一次；寫到字串上限被截斷的不執行、重問一次。對話太長時，送給模型的那一份把舊的結果換成存檔編號（存著的對話不動）。
存檔：logs/domain_jobs/<編號>/——job.json（每一步：選的領域、技能、參數與原文、核對、結果的 #編號）、calls.jsonl（每次模型呼叫）、
events.jsonl（進度）、report.md。
"""
import json
import os
import re
import time

from skills_system.scripts import _results_common
from . import answers, composite, prompt_files, skill_spec
from .config import (ANALYSIS_REPORT_HEAD, DOMAIN_JOBS_DIRNAME, DOMAIN_JOBS_KEEP, DOMAIN_MODEL, DOMAIN_QUOTE_LINES, DOMAIN_RESELECT_MAX,
                     DOMAIN_STEPS_MAX, DOMAIN_SYNTAX_LINES, DOMAIN_TURNS_MAX, NUM_CTX, REPLY_ARGS_CHARS, REPLY_THOUGHT_CHARS,
                     TOKEN_THRESHOLD, TOOL_SUMMARY_DEFAULT)
from .jobstore import JobStore
from .protocol import parse_answers, tool_result_message
from .schemas import DOMAIN_REPLY_CHARS, domain_session_schema
from .turn import _content_for_context

STATES = ("domains", "skill", "report")
STATUS_TEXT = {"running": "執行中", "need_user": "等使用者回答", "done": "做完", "stopped": "停下來（步數用完或卡住）",
               "cancelled": "使用者取消", "failed": "失敗（模型沒有回覆）"}
_KEEP_RESULTS = 3                           # 對話太長時，最新的這幾份結果不清
_SYNTAX = re.compile(r"`EXECUTE:\s*scripts/[\w.-]+\s*([^`]*)`")


def _s(key, /, **fields):
    """prompts/domain/session.md 的一則。"""
    return prompt_files.load("domain/session.md", key, **fields)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def parse_reply(raw):
    """模型回覆（JSON 字串）→ {"thought", "state", "domains", "skill", "params", "args", "answers", "reply", "cut"}；不是 JSON 物件回 None。
    state 不是三種之一時是空字串；cut：寫到字串上限（被截斷）的欄位。"""
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    state = str(data.get("state") or "").strip()
    domains = data.get("domains") if isinstance(data.get("domains"), list) else []
    params = data.get("params") if isinstance(data.get("params"), list) else []
    out = {"thought": str(data.get("thought") or "").strip(), "state": state if state in STATES else "",
           "domains": list(dict.fromkeys(str(x).strip() for x in domains if str(x).strip())),
           "skill": str(data.get("skill") or "").strip(),
           "params": [{"name": str(p.get("name") or "").strip(), "value": str(p.get("value") or ""), "quote": str(p.get("quote") or "")}
                      for p in params if isinstance(p, dict) and str(p.get("name") or "").strip()],
           "args": str(data.get("args") or "").strip(), "answers": parse_answers(data.get("answers")),
           "reply": str(data.get("reply") or "").strip()}
    caps = (("thought", REPLY_THOUGHT_CHARS), ("args", REPLY_ARGS_CHARS), ("reply", DOMAIN_REPLY_CHARS))
    out["cut"] = [k for k, n in caps if isinstance(data.get(k), str) and len(data[k]) >= n]
    return out


def analysis_reports(agent, job):
    """這個 session 裡 analysis_run 的事實報告：[(#編號, 原文)]（從存檔讀；原樣附在報告裡，主對話的回答照它核對）。"""
    out = []
    for st in job.get("steps") or []:
        if st.get("skill") == "analysis_run" and st.get("status") == "PASS" and st.get("result_ids"):
            path = agent.result_file_path(st["result_ids"][0])
            text = "\n".join(_results_common.read_body(path)[1]).strip() if path else ""
            if text.startswith(ANALYSIS_REPORT_HEAD):
                out.append((st["result_ids"][0], text))
    return out


def steps_text(job):
    """每一步的一行（主 session 再交辦時的「上一次的經過」、評測的紀錄）。"""
    return "；".join(f"{st['skill']}（{st['how']}）→ {st['status']}" for st in job.get("steps") or []) or "沒有用技能"


class DomainSession:
    """start(問題, 子目標, 項目) → job（也存成 job.json）；停在確認關卡時 resume(編號, approve=…)，使用者取消 cancel(編號)。
    registry：orchestrator.load_registry 的結果。fixer：有骨架的技能交給低階的第 1 級修正（None＝預設的模型）。"""

    def __init__(self, agent, registry, fixer=None):
        self.agent = agent
        self.reg = registry
        self.fixer = fixer
        self.store = JobStore(os.path.join(agent.script_dir, "logs", DOMAIN_JOBS_DIRNAME))

    # ---------------------------------------------------------------- 進入點
    def start(self, question, goal, items, previous=None, attempt=1):
        """previous：同一個問題之前交辦的經過（[{"n", "job", "status_text", "note", "steps"}]，orchestrator 從這一回合的紀錄取）。"""
        jid = self.store.new_id()
        self.store.prune(DOMAIN_JOBS_KEEP)
        job = {"id": jid, "kind": "domain", "status": "running", "created": _now(), "updated": _now(), "cwd": self.agent.current_cwd,
               "question": question, "goal": (goal or question).strip(), "items": list(items or []), "attempt": attempt,
               "previous": list(previous or []), "domains": [], "picks": [], "messages": [], "steps": [], "turns": 0,
               "blocked": [], "sources": "", "need_user": None, "asked": [], "nudged": False, "answers": [], "problems": {}, "result": None}
        job["system"] = self._system()
        job["messages"].append({"role": "user", "content": self._first(job)})
        job["sources"] = "\n".join([job["question"], job["goal"]] + job["items"])
        self.store.save(job)
        self._note(jid, f"🧭 領域 session 開始：{job['goal'][:80]}")
        return self._loop(job)

    def resume(self, jid, approve=None):
        """接回停在確認關卡的那一步：同意就照原本的動作執行，不同意就把 [DENIED] 交給模型接著做。"""
        job = self.store.load(jid)
        if not job or job["status"] != "need_user":
            return job
        need = job["need_user"]
        if job.get("asked"):
            job["asked"][-1].update(approve=bool(approve), answered=_now())
        job.update(status="running", need_user=None)
        pending = need["pending"]
        if approve:
            self._tool(job, pending, approved=True, guarded=True)
        else:
            self._tool(job, pending, output=self.agent.guard_denied_text(need["guard"]), guarded=True)
        return self._loop(job)

    def cancel(self, jid):
        """使用者取消確認關卡：照做到的收尾（報告寫明停在哪一步）。"""
        job = self.store.load(jid)
        if not job or job["status"] != "need_user":
            return job
        if job.get("asked"):
            job["asked"][-1].update(cancelled=True, answered=_now())
        return self._finish(job, "cancelled", note=f"要確認的是：{job['need_user'].get('command') or job['need_user']['question']}")

    # ---------------------------------------------------------------- 迴圈
    def _loop(self, job):
        while True:
            if len(job["steps"]) >= DOMAIN_STEPS_MAX:
                return self._finish(job, "stopped", note=f"技能用了 {DOMAIN_STEPS_MAX} 次（上限），照做到的收尾")
            if job["turns"] >= DOMAIN_TURNS_MAX:
                return self._finish(job, "stopped", note=f"回了 {DOMAIN_TURNS_MAX} 輪還沒有回報（上限），照做到的收尾")
            parsed, raw = self._ask(job)
            if parsed is None:
                return self._finish(job, "failed", note="領域 session 的模型沒有回覆（或回覆不是 JSON）")
            job["turns"] += 1
            job["messages"].append({"role": "assistant", "content": raw})
            state = parsed["state"]
            if not job["domains"] and state != "domains":
                self._tell(job, _s("err_first_domains"), "還沒選領域")
                continue
            if state == "domains":
                self._domains(job, parsed)
                continue
            if state == "report":
                done = self._report_state(job, parsed)
                if done:
                    return done
                continue
            if self._skill(job, parsed):
                return job                          # 停在確認關卡

    def _tell(self, job, text, short):
        """程式交給模型的一則（擋下、交回改的說明）。"""
        job["messages"].append({"role": "user", "content": text})
        job["blocked"].append({"turn": job["turns"], "time": _now(), "why": short})
        job["updated"] = _now()
        self.store.save(job)
        self._note(job["id"], f"🧭 {short}")

    # ---------------------------------------------------------------- domains：選領域
    def _domains(self, job, parsed):
        names = [d for d in parsed["domains"] if d in self.reg["domains"]]
        if not names:
            return self._tell(job, _s("err_domains", names="、".join(self.reg["domains"])), "選的領域不在清單裡")
        if len(job["picks"]) > DOMAIN_RESELECT_MAX:
            return self._tell(job, _s("err_reselect", count=len(job["picks"])), "重選領域超過上限")
        job["domains"] = names
        job["picks"].append({"turn": job["turns"], "time": _now(), "domains": names, "thought": parsed["thought"]})
        job["messages"].append({"role": "user", "content": self._skills_text(job)})
        job["updated"] = _now()
        self.store.save(job)
        self._note(job["id"], f"🧭 選領域：{'、'.join(names)}（{parsed['thought'][:60]}）")
        return None

    def _available(self, job):
        """選的領域能用的：({有骨架的技能: (領域, 規格)}, [工具（領域的加上共用的）])。"""
        skills, tools = {}, []
        for name in job["domains"]:
            d = self.reg["domains"][name]
            for sk, spec in d["skills"].items():
                skills.setdefault(sk, (name, spec))
            tools += [t for t in d["tools"] if t not in tools]
        tools += [t for t in self.reg["shared"] if t not in tools]
        return skills, tools

    # ---------------------------------------------------------------- skill：用一個技能
    def _skill(self, job, parsed):
        """執行一個技能；停在確認關卡回 True。"""
        skills, tools = self._available(job)
        name = parsed["skill"]
        if name in skills:
            domain, spec = skills[name]
            if parsed["args"].strip() and not parsed["params"]:
                self._tell(job, _s("err_composite_args", skill=name, names="、".join(p["name"] for p in spec["parameters"])),
                           f"{name} 有骨架，參數寫在 args")
                return False
            params, problems = self._contract(job, spec, parsed["params"])
            if problems:
                self._tell(job, _s("err_params", skill=name, problems="\n".join(problems)), f"{name} 的參數沒有通過核對")
                return False
            how = composite.param_sig({k: v["value"] for k, v in params.items()})
            if self._same(job, name, how):
                return False
            self._composite(job, parsed, self.reg["domains"][domain], name, params, how)
            return False
        if name in tools:
            if parsed["params"] and not parsed["args"]:
                self._tell(job, _s("err_args", skill=name), f"{name} 是工具，參數寫在 params")
                return False
            args = self._own_args(name, parsed["args"])
            if self._same(job, name, " ".join(args.split())):
                return False
            pending = {"skill": name, "args": args, "thought": parsed["thought"], "reply": parsed["reply"]}
            guard = self.agent.guard_check({"action": self._action(name, args)})
            if guard:
                self._wait(job, pending, guard)
                return True
            self._tool(job, pending)
            return False
        self._tell(job, _s("err_skill", skill=name or "（空的）", names="、".join(list(skills) + tools)), f"技能清單裡沒有「{name}」")
        return False

    def _own_args(self, tool, args):
        """工具的參數：開頭照抄了工具名稱或腳本路徑的（「find_file x .」「scripts/ls_cmd.py .」）拿掉那一段，其他照原樣。"""
        head, _, rest = args.strip().partition(" ")
        script = self._script_of(tool) or ""
        if head in (tool, f"{tool}.md") or (script and os.path.basename(head) == script):
            return rest.strip()
        return args

    def _same(self, job, skill, how):
        """跟之前某一步一模一樣：不執行，交給模型那一步的結果（回 True）。"""
        prev = next((st for st in job["steps"] if st["skill"] == skill and st["sig"] == how), None)
        if prev:
            self._tell(job, _s("err_same", n=prev["n"], skill=skill, how=prev["how"], head=prev["head"] or "—"), f"跟第 {prev['n']} 步一樣，沒有執行")
        return bool(prev)

    def _contract(self, job, spec, given):
        """有骨架的技能的參數 → ({名稱: {"value", "quote", "source"}}, [沒過的說明])。原文要在這個 session 給模型看過的字裡。"""
        params, problems = {}, []
        cells = {p["name"]: p for p in given}
        known = {p["name"] for p in spec["parameters"]}
        problems += [_s("reject_unknown", name=n, names="、".join(sorted(known))) for n in cells if n not in known]
        for p in spec["parameters"]:
            cell = cells.get(p["name"])
            if cell is None:
                continue
            value, why = composite.verify_param(p, cell["quote"], cell["value"], job["sources"])
            if why:
                problems.append(why)
            elif value is not None:
                params[p["name"]] = {"value": value, "quote": composite._unquote(cell["quote"]), "source": "contract"}
        return params, problems

    def _composite(self, job, parsed, domain, name, params, how):
        res = composite.Runner(self.agent, fixer=self.fixer, note=lambda t: self._note(job["id"], t)).run(domain, name, params)
        lines = [_s("composite_status", status=composite.STATUS_TEXT[res["status"]], note=f"（{res['note']}）" if res["note"] else "")]
        for sw in res["switched"]:
            lines.append(_s("composite_switched", fallback=sw["fallback"], frm=sw["from"], to=sw["to"]))
        for fb in res["fallbacks"]:
            if fb.get("result") == "replanned":
                lines.append(_s("composite_fallback", say=fb["say"]))
        for a in res["auto_filled"]:
            lines.append(_s("composite_filled", name=a["param"], given=a["given"], value=a["value"]))
        if res["need"]:
            cands = "；".join(res["need"].get("candidates") or [])
            lines.append(_s("composite_need", question=res["need"]["question"], candidates=_s("composite_candidates", candidates=cands) if cands else ""))
        parts, rids, summarized = ["\n".join(lines)], [], False
        for o in res["outputs"]:
            title = o["report"] or o["why"] or o["node"]
            head = _s("output_head", title=title, tool=o["tool"], args=" ".join(o["args"]), state=o["state"],
                      rid=f"（#{o['result_id']}）" if o["result_id"] else "")
            if not o["result_id"]:
                parts.append(head + (f"\n{o['reason']}" if o["reason"] else ""))
                continue
            rids.append(o["result_id"])
            content, cut = self._shown(job, o["result_id"], {"thought": parsed["thought"], "reply": parsed["reply"],
                                                            "action": self._action(o["tool"], " ".join(o["args"]))})
            summarized = summarized or cut
            parts.append(head + "\n" + content)
        step = {"skill": name, "kind": "composite", "params": params, "args": "", "how": how, "sig": how, "thought": parsed["thought"],
                "reply": parsed["reply"], "status": res["status"], "result_ids": rids, "head": composite.STATUS_TEXT[res["status"]],
                "summarized": summarized,
                "composite": dict({k: res[k] for k in ("skill", "switched", "fallbacks", "auto_filled", "need", "note", "edg_jobs")},
                                  outputs=[{k: o[k] for k in ("node", "tool", "args", "state", "result_id")} for o in res["outputs"]])}
        self._record(job, step, "\n\n".join(parts))

    def _shown(self, job, rid, step):
        """一份存檔 → (交給模型的文字, 有沒有提煉)：門檻內原文，太長的提煉（錨點是子目標與項目；照收據把行號對到檔案）；開頭寫存檔編號。"""
        path = self.agent.result_file_path(rid)
        text = "\n".join(_results_common.read_body(path)[1]) if path else ""
        self.agent.last_result_id, self.agent.last_result_file = rid, os.path.basename(path) if path else None
        content = _content_for_context(text, self.agent.count_tokens(text), self.agent, use_summary=TOOL_SUMMARY_DEFAULT, step=step,
                                       anchor=self._anchor(job), sub=True)
        return _s("result_id", rid=rid) + "\n" + content, content != text

    def _action(self, tool, args):
        script = self._script_of(tool)
        return {"command": f"scripts/{script}" if script else tool, "args": args}

    def _script_of(self, tool):
        try:
            with open(os.path.join(self.agent.tools_dir, f"{tool}.md"), encoding="utf-8") as f:
                return skill_spec.script(f.read(), tool)
        except OSError:
            return None

    def _tool(self, job, pending, approved=False, output=None, guarded=False):
        """執行一個工具（output 給了＝使用者沒有同意，不執行）；結果接進對話、記一步。"""
        action = self._action(pending["skill"], pending["args"])
        denied = output is not None
        if not denied:
            _, tools = self._available(job)
            self.agent._sub_allowed = {"domain": "、".join(job["domains"]), "tools": set(tools)}
            try:
                output = self.agent._run_tool_once({"action": action, "thought": "", "reply": "", "valid": True}, approved) or ""
            finally:
                self.agent._sub_allowed = None
        rid = None if denied else self.agent.last_result_id
        status = "DENIED" if denied else "ERROR" if output.lstrip().startswith("[ERROR]") else "PASS"
        content = output
        if not denied:
            content = _content_for_context(output, self.agent.count_tokens(output), self.agent, use_summary=TOOL_SUMMARY_DEFAULT,
                                           step={"thought": pending["thought"], "reply": pending["reply"], "action": action},
                                           anchor=self._anchor(job), sub=True)
        summarized = content != output
        if rid:
            content = _s("result_id", rid=rid) + "\n" + content
        how = " ".join(pending["args"].split())
        step = {"skill": pending["skill"], "kind": "tool", "params": {}, "args": pending["args"], "how": how or "—", "sig": how,
                "thought": pending["thought"], "reply": pending["reply"], "status": status, "result_ids": [rid] if rid else [],
                "head": output.strip().splitlines()[0][:200] if output.strip() else "", "summarized": summarized,
                "guard": {"approve": not denied} if guarded else None}
        self._record(job, step, content)

    def _record(self, job, step, content):
        step.update(n=len(job["steps"]) + 1, time=_now())
        shown = _s("step_head", n=step["n"], skill=step["skill"], how=step["how"]) + "\n" + content
        job["steps"].append(step)
        job["sources"] += "\n" + shown
        job["messages"].append({"role": "user", "content": tool_result_message(shown, self._action(step["skill"], step["args"]))})
        job["updated"] = _now()
        self.store.save(job)
        self._note(job["id"], f"🧭 第 {step['n']} 步：{step['skill']}（{step['how'][:80]}）→ {step['status']}"
                   + (f"（{'、'.join('#' + str(r) for r in step['result_ids'])}）" if step["result_ids"] else ""))

    def _wait(self, job, pending, guard):
        need = {"kind": "guard", "question": self.agent.guard_prompt_text(guard), "command": guard.get("command", ""), "guard": guard,
                "pending": pending, "candidates": []}
        job["asked"].append({"kind": "guard", "question": need["question"], "command": need["command"], "step": len(job["steps"]) + 1, "time": _now()})
        job.update(status="need_user", need_user=need, updated=_now())
        self.store.save(job)
        self._note(job["id"], f"🧭 要問使用者（確認關卡）：{need['command'][:100]}")

    # ---------------------------------------------------------------- report：回報
    def _report_state(self, job, parsed):
        """回報：核對沒過的交回修一次（回 None）；過了或修過一次的收尾（回 job）。"""
        if not parsed["answers"]:
            self._tell(job, _s("err_empty_report"), "回報沒有寫 answers")
            return None
        problems = self._problems(job, parsed["answers"])
        if problems and not job["nudged"]:
            job["nudged"] = True
            rows = [prompt_files.load("harness/domain.md", "answers_problem", k=k, item=job["items"][k - 1], why="；".join(w))
                    for k, w in sorted(problems.items())]
            self._tell(job, _s("answers_fix", problems="\n".join(rows)), f"回報有 {len(problems)} 項沒有通過核對，交回修一次")
            return None
        return self._finish(job, "done", reply=parsed["reply"], answered=parsed["answers"], problems=problems)

    def _archives(self, job):
        """這個 session 的結果：[(#編號, 存檔的路徑)]。"""
        out = []
        for st in job["steps"]:
            for rid in st.get("result_ids") or []:
                path = self.agent.result_file_path(rid)
                if path:
                    out.append((rid, path))
        return out

    def _cited(self, job, ref, archives):
        """一個出處 → (種類, 對到的行, 那幾段的文字, 行號)：#編號 要是這個 session 的存檔；檔案:行號 要在它們的收據裡（那一行由程式從檔案讀）。"""
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
        job["result"] = {"status": status, "note": note, "report": report, "sources": [r for r, _ in self._archives(job)]}
        self.store.save(job)
        self._note(job["id"], f"🧭 領域 session 結束：{STATUS_TEXT[status]}" + (f"（{note[:100]}）" if note else ""))
        return job

    def _report(self, job, note, reply, problems):
        lines = [f"# 領域 session 的結果：{STATUS_TEXT[job['status']]}", f"- 問題：{job['question']}"]
        if job["goal"] != job["question"]:
            lines.append(f"- 子目標：{job['goal']}")
        lines += [f"- 要回答的項目 {k}：{x}" for k, x in enumerate(job["items"], 1)]
        if job["previous"]:
            lines.append(f"- 第 {job['attempt']} 次交辦（之前：" + "；".join(f"第 {p.get('n')} 次 {p.get('status_text') or '—'}" for p in job["previous"]) + "）")
        lines.append(f"- 領域：{'、'.join(job['domains']) or '（沒有選）'}；用了 {len(job['steps'])} 個技能")
        if note:
            lines.append(f"- 說明：{note}")
        if reply:
            lines.append(f"- 總結：{reply}")
        lines += ["", "## 每一項的回答（領域 session 寫的；出處由程式核對）"]
        got = {a["item"]: a for a in job["answers"] if 1 <= a["item"] <= len(job["items"])}
        archives = self._archives(job)
        for k, item in enumerate(job["items"], 1):
            a = got.get(k)
            if a is None:
                lines.append(f"{k}. {item}：（沒有回答）")
            elif a["status"] == "not_found":
                lines.append(f"{k}. {item}：查不到。{a['text']}")
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
            rids = "、".join(f"#{r}" for r in st["result_ids"])
            if st["status"] == "DENIED":
                lines.append(f"{st['n']}. {st['skill']}（{st['how']}）→ 使用者沒有同意（確認關卡），沒有執行")
            else:
                lines.append(f"{st['n']}. {st['skill']}（{st['how']}）→ {st['head']}" + (f"（{rids}）" if rids else "")
                             + ("（使用者同意）" if st.get("guard") else ""))
        if not job["steps"]:
            lines.append("（沒有用任何技能）")
        for rid, text in analysis_reports(self.agent, job):      # 數據分析的報告原樣附上（主對話照它核對回答）
            lines += ["", f"## 數據分析的報告（#{rid}，原樣）", text]
        return "\n".join(lines)

    # ---------------------------------------------------------------- 模型
    def _ask(self, job):
        """模型一次 → (parsed, 原文)。不是 JSON、state 不是三種之一：附上那一則與提醒再問一次；寫到字串上限被截斷：不執行，接提醒再問一次。
        兩次都不行回 (None, 原文)。每次呼叫記進 calls.jsonl（送出的最後一則與回覆）。"""
        msgs = self._fit(job)
        schema = domain_session_schema(list(self.reg["domains"]), len(job["items"]))
        model = DOMAIN_MODEL or self.agent.model
        raw = ""
        for attempt in range(2):
            t0, err = time.time(), None
            try:
                res = self.agent._timed_chat("domain_step", model=model, messages=msgs, format=schema,
                                             options={"temperature": 0.2, "num_ctx": NUM_CTX}, think=False)
                raw = (res["message"]["content"] or "").strip()
            except Exception as e:   # noqa: BLE001  模型呼叫失敗：當成沒有回覆
                raw, err = "", f"{type(e).__name__}: {e}"
            parsed = parse_reply(raw)
            ok = parsed is not None and bool(parsed["state"])
            cut = parsed["cut"] if ok else []
            error = None if ok and not cut else err or ("寫到長度上限被截斷：" + "、".join(cut) if cut else "回覆不是 JSON、是空的，或 state 不是三種之一")
            self.store.append(job["id"], "calls.jsonl", {"turn": job["turns"] + 1, "model": model, "user": msgs[-1]["content"],
                                                         "response": raw, "error": error, "ms": round((time.time() - t0) * 1000)})
            if ok and not cut:
                return parsed, raw
            msgs = msgs + ([{"role": "user", "content": _s("cut", fields="、".join(cut))}] if cut else
                           [{"role": "assistant", "content": raw}, {"role": "user", "content": _s("retry")}])
        return None, raw

    def _fit(self, job):
        """送給模型的對話：system prompt＋存著的對話，最後一則接上動態區（工作目錄、目標容器…）。超過硬水位時，舊的結果換成存檔編號
        （最新 _KEEP_RESULTS 份不動；存著的對話不改）。"""
        msgs = [{"role": "system", "content": job["system"]}] + [dict(m) for m in job["messages"]]
        msgs[-1]["content"] += "\n\n" + self.agent.build_state_tail()
        results = [i for i, m in enumerate(msgs) if m["role"] == "user" and m["content"].startswith("[tool result]")]
        size = sum(self.agent.count_tokens(m["content"]) for m in msgs)
        for k, i in enumerate(results[:-_KEEP_RESULTS] if len(results) > _KEEP_RESULTS else []):
            if size <= TOKEN_THRESHOLD:
                break
            st = job["steps"][k] if k < len(job["steps"]) else {}
            short = tool_result_message(_s("cleared", n=st.get("n", k + 1), rid="、".join(map(str, st.get("result_ids") or [])) or "—",
                                           head=st.get("head", "")))
            size -= self.agent.count_tokens(msgs[i]["content"]) - self.agent.count_tokens(short)
            msgs[i] = {"role": "user", "content": short}
        return msgs

    # ---------------------------------------------------------------- 給模型看的字
    def _system(self):
        rows = [_s("domain_entry", name=n, title=d["title"], intro=" ".join(d["intro"].split())) for n, d in self.reg["domains"].items()]
        return _s("system", domains="\n".join(rows) or "—", reselect=DOMAIN_RESELECT_MAX, steps=DOMAIN_STEPS_MAX,
                  memory=self.agent.load_long_term_memory())

    def _first(self, job):
        items = "\n".join(f"{k}. {x}" for k, x in enumerate(job["items"], 1))
        prev = ""
        if job["previous"]:
            rows = [_s("previous_attempt", n=p.get("n"), steps=p.get("steps") or "—", status=p.get("status_text") or "—",
                       note=f"（{p['note']}）" if p.get("note") else "") for p in job["previous"]]
            prev = _s("previous", count=len(job["previous"]), attempts="\n".join(rows))
        return _s("first", goal=job["goal"], items=items, question=job["question"], previous=prev)

    def _skills_text(self, job):
        """選了領域之後交給模型的技能清單：每個領域的〈做法〉、有骨架的技能（說明、什麼時候用、參數）、工具（索引的那一行與〈語法〉）；
        最後是共用的工具（選的領域沒有列的）。"""
        kinds = {"name": _s("type_name"), "text": _s("type_text"), "path": _s("type_path"), "glob": _s("type_glob"),
                 "names": _s("type_names"), "words": _s("type_words")}
        blocks, listed = [], set()
        for name in job["domains"]:
            d = self.reg["domains"][name]
            entries = []
            for sk, spec in d["skills"].items():
                rows = []
                for p in spec["parameters"]:
                    common = {"name": p["name"], "kind": kinds[p["type"]], "desc": p["desc"]}
                    if p.get("required"):
                        rows.append(_s("param_required", **common))
                    elif "default" in p:
                        rows.append(_s("param_default", default=p["default"], **common))
                    else:
                        rows.append(_s("param_optional", **common))
                entries.append(_s("composite_entry", name=sk, description=spec["meta"]["description"],
                                  when=" ".join(spec["sections"].get("什麼時候用", "").split()) or "—", params="\n".join(rows) or "  —"))
            tools = [t for t in d["tools"] if t not in listed]
            listed |= set(tools)
            blocks.append(_s("skills_domain", name=name, title=d["title"],
                             practice=_s("skills_practice", practice=d["practice"]) + "\n" if d.get("practice") else "",
                             composites=_s("skills_composites", entries="\n".join(entries)) + "\n" if entries else "",
                             tools=_s("skills_tools", entries=self._tool_entries(tools)) if tools else ""))
        shared = [t for t in self.reg["shared"] if t not in listed]
        if shared:
            blocks.append(_s("skills_shared", entries=self._tool_entries(shared)))
        return _s("skills", names="、".join(job["domains"]), blocks="\n\n".join(blocks))

    def _tool_entries(self, tools):
        """工具的那幾行：技能索引的說明（agent._index_lines，那一節的說明跟著工具走）加上規格〈語法〉裡 args 的寫法（_syntax：只留參數的部分）。"""
        out = []
        for ln in self.agent._index_lines(tools).split("\n"):
            m = re.match(r"^- \[([A-Za-z0-9_]+)\]", ln)
            if not m:
                out.append(ln)
                continue
            out.append(_s("tool_entry", line=ln, syntax=self._syntax(m.group(1))))
        return "\n".join(out)

    def _syntax(self, tool):
        """規格的〈語法〉：每一個 `EXECUTE: scripts/x.py <參數>` 只留參數的部分（就是 args 要寫的），最多 DOMAIN_SYNTAX_LINES 行。"""
        try:
            with open(os.path.join(self.agent.tools_dir, f"{tool}.md"), encoding="utf-8") as f:
                body = skill_spec.sections(f.read()).get("語法", "")
        except OSError:
            body = ""
        rows = [f"`{m.group(1).strip()}`" if m.group(1).strip() else _s("syntax_none") for m in _SYNTAX.finditer(body)]
        return "　".join(dict.fromkeys(rows[:DOMAIN_SYNTAX_LINES])) or "—"

    @staticmethod
    def _anchor(job):
        """提煉長輸出時的「想知道什麼」：這一件事的子目標與項目。"""
        return _s("anchor", goal=job["goal"], items="；".join(job["items"]))

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
