"""方向的實驗：公佈欄的 worker（〈新架構討論紀錄〉第 5 節〈步驟 0 的結果與接下來的做法〉，2026-11-20 定案）。設定 AGENT_DOMAIN_BOARD 列的領域
（第一輪只有 repo_analysis）不交給中階，交給這裡；同一份題目新舊各跑一次比較，結束留下比較好的那一個。

步驟 0 看到現在剩下的錯大多在「看」的方法（合約照問題裡的字填、判斷節點只看到一小段、要列出全部時一份一份看），不在交接；所以公佈欄（邊規劃邊做的
狀態）跟「怎麼看」一起改：
1. **公佈欄**（程式維護，存在 job 裡）：使用者的原始問題、子目標、每一項與它的事實有幾則、前面的領域查到的、這個問題的分工、上一次的經過、
   核對過的事實（F 編號；提煉的附 檔案:行號 與 #編號，程式的附 #編號；哪一步得到的）、試過的每一步（工具、參數、收據的摘要、[ERROR]、
   有沒有新的事實）、還能走幾步。
2. **一步怎麼走**：
   - 規劃（模型一次，schema）：讀公佈欄，回下一步（工具與參數、為第幾項、要在輸出裡找什麼）或「可以回答了」。工具少而固定（領域 SKILLS.md 的
     〈公佈欄的工具〉），用法由程式從規格的〈語法〉填進說明，不用先載入規格。
   - 執行：交給低階（agent_core/edg.py）——這一步是決策圖上的一個新節點，圖一步一步長（edg.replan：跑過的不重跑；參數檢查、收據、
     第 1 級修正照舊）。跟之前一樣的工具與參數由程式擋下、不執行（連續 BOARD_REPEATS_MAX 次就當成卡住）；最多 BOARD_STEPS_MAX 步。
   - 看：成功的輸出交給提煉（extract.Extraction.facts_only：照結構切段、每段一次，錨點是原始問題、項目與這一步要找的），每一則事實照提煉的
     核對（名稱與數值在引用的那幾行，含 4j ①），輸出的行號換成 檔案:行號（照輸出的寫法：`## 檔案`、`120→`、`行 120`），寫進公佈欄；
     程式算好的數量（search_text 每個檔案的筆數、find_file、code_defs、py_refs）另外記成一則程式的事實。0 筆、[ERROR] 只記在試過的步驟。
3. **回答**（模型一次，schema）：每一項照公佈欄的事實回答（答到、查不到、不屬於這個領域；根據的事實編號）；程式核對（答到的要有事實、事實在
   公佈欄上、回答裡的名稱與數值在那幾則事實裡），沒過的交回修一次。交回主對話的是每一項的回答與它的事實（報告：每一項、公佈欄的事實與
   檔案:行號 那一行的原文、每一步），主對話照 4-2 依報告回答。

每一次存在 logs/board_jobs/<編號>/：job.json（公佈欄、每一步、回答與核對）、report.md、events.jsonl、calls.jsonl（規劃與回答的模型呼叫）；
低階的執行在 logs/edg_jobs/<edg_job>/，提煉在 logs/extract_jobs/。
"""
import json
import os
import re
import shlex
import time

from skills_system.scripts import _results_common as rc
from . import answers, edg, extract, prompt_files, skill_spec
from .config import (BOARD_ANSWER_PREDICT, BOARD_FACT_CHARS, BOARD_FACTS_SHOWN, BOARD_JOBS_DIRNAME, BOARD_JOBS_KEEP, BOARD_LOOK_FACTS,
                     BOARD_LOOK_PREDICT, BOARD_MODEL, BOARD_PLAN_PREDICT, BOARD_REPEATS_MAX, BOARD_STEPS_MAX, BOARD_VIEW_PAGES, DOMAIN_ANSWER_CHARS,
                     DOMAIN_QUOTE_LINES, DOMAIN_REFS_MAX, EDG_JOBS_DIRNAME, MID_JOBS_DIRNAME, NUM_CTX, SUB_JOBS_DIRNAME)
from .jobstore import JobStore
from .schemas import board_answer_schema, board_look_schema, board_plan_schema

STATUS_TEXT = {"running": "執行中", "done": "做完", "stopped": "停下來（步數用完或卡住），照公佈欄的事實回答",
               "failed": "失敗（模型沒有回覆）", "out_of_domain": "不屬於這個領域"}
STEP_SKILL = "公佈欄（一次決定一步）"
PROGRAM_FACT_TOOLS = ("search_text", "find_file", "code_defs", "py_refs")   # 收據的數量另外記成程式的事實
SUMMARY_FILES = 12            # 程式的事實與步驟的摘要最多列幾個檔案
SEARCH_PER_FILE, SEARCH_TOTAL = 20, 200   # search_text 的文字每個檔案、總共最多列幾筆（skills_system/scripts/grep_cmd.py；超過時摘要寫明只列了前面的）
ERROR_CHARS = 400             # 試過的步驟裡 [ERROR] 最多附幾個字
_DESC = re.compile(r"^description:\s*(.+)$", re.M)
_HEAD_PATH = re.compile(r"^## (.+?)（")
_NUMBERED = re.compile(r"^[ >]\s*(\d+)→")
_OWN_NUMBER = re.compile(r"^[ >]\s*\d+→")    # 工具自己加的行號（view_file、search_text 的 `  120→`）：交給提煉前拿掉，模型只看到一種行號
_AT_LINE = re.compile(r"行 (\d+)")


def _b(key, /, **fields):
    """prompts/board/inputs.md 的一則。"""
    return prompt_files.load("board/inputs.md", key, **fields)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _cmd(tool, args):
    return f"{tool} {shlex.join(args)}".strip()


def tool_usage(tools_dir, tool):
    """給規劃看的一個工具：名稱、規格的 description 與〈語法〉（程式從規格取，規劃不用先載入規格）。"""
    spec = edg.load_spec(tools_dir, tool)
    if not spec:
        return f"### {tool}"
    m = _DESC.search(spec["text"])
    syntax = skill_spec.sections(spec["text"]).get("語法", "")
    return f"### {tool}：{m.group(1).strip() if m else ''}\n{syntax}".strip()


def searched(job):
    """這份工作 search_text 搜過的字（第一個參數，| 分開的每一個）：高階交「上一次的經過」用。"""
    out = []
    for st in job.get("steps") or []:
        if st.get("tool") == "search_text" and st.get("args") and st.get("status") != "REPEAT":
            for w in str(st["args"][0]).split("|"):
                w = w.strip()
                if w and w.lower() not in {x.lower() for x in out}:
                    out.append(w)
    return out


def calls(job):
    """執行過的工具（擋下的重複不算）：評測的 worker 記成 via、高階記進交給領域的紀錄。"""
    return [{"tool": st["tool"], "script": None, "args": st.get("ran_args") or st["args"], "status": "ERROR" if st["status"] == "ERROR" else "PASS",
             "head": st.get("head", "")} for st in job.get("steps") or [] if st["status"] != "REPEAT"]


class BoardModel:
    """一次模型呼叫：caller(role, system, user, schema, predict, log) → dict 或 None（沒有回覆、不是 JSON）；每次呼叫交給 log 記進 calls.jsonl。"""

    def __init__(self, agent):
        self.agent = agent

    def __call__(self, role, system, user, schema, predict, log):
        model = BOARD_MODEL or self.agent.model
        t0, raw, err = time.time(), "", None
        try:
            res = self.agent._timed_chat(f"board_{role}", model=model,
                                         messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                         format=schema, options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": predict}, think=False)
            raw = (res["message"]["content"] or "").strip()
        except Exception as e:   # noqa: BLE001  模型呼叫失敗：這一次當成沒有回覆
            err = f"{type(e).__name__}: {e}"
        try:
            data = json.loads(raw) if raw else None
        except ValueError:
            data = None
        if not isinstance(data, dict) and not err:
            err = "回覆不是 JSON" if raw else "沒有回覆"
        log({"role": role, "model": model, "system": system, "user": user, "response": raw,
             "error": err if not isinstance(data, dict) else None, "ms": round((time.time() - t0) * 1000)})
        return data if isinstance(data, dict) else None


class Worker:
    """一個領域的公佈欄 worker：start(問題, 子目標, 項目, …) → job（dict，也存成 job.json）。tools：〈公佈欄的工具〉；model 預設是 BoardModel
    （自我測試換成假的）；fixer 交給低階（第 1 級修正的模型，None＝預設）。只讀，不會停下來問使用者。"""

    def __init__(self, agent, domain, tools, title="", intro="", model=None, fixer=None):
        self.agent = agent
        self.domain = domain
        self.tools = list(dict.fromkeys(tools))
        self.title, self.intro = title or domain, intro
        self.store = JobStore(os.path.join(agent.script_dir, "logs", BOARD_JOBS_DIRNAME))
        self.model = model if model is not None else BoardModel(agent)
        self.fixer = fixer
        self._lines = {}

    # ---------------------------------------------------------------- 進入點
    def start(self, question, goal, items, on_start=None, previous=None, attempt=1, known="", division=""):
        """previous、attempt、known、division 跟子工作階段一樣（orchestrator 組好的上一次的經過、前面的領域查到的、這個問題的分工）。"""
        jid = self.store.new_id()
        self.store.prune(BOARD_JOBS_KEEP)
        job = {"id": jid, "kind": "board", "status": "running", "created": _now(), "updated": _now(), "cwd": self.agent.current_cwd,
               "domain": self.domain, "question": question, "goal": (goal or question).strip(), "items": list(items or []), "attempt": attempt,
               "previous": list(previous or []), "known": known, "division": division, "tools": self.tools,
               "graph": {"goal": (goal or question).strip()[:300], "nodes": []}, "edg_job": None, "steps": [], "facts": [], "plans": [],
               "stop": "", "answers": [], "problems": {}, "result": None}
        self.store.save(job)
        self._link(job["previous"], jid, attempt)
        if on_start:
            on_start(jid)
        self._note(jid, f"📌 公佈欄（{self.domain}）開始：{job['goal'][:80]}")
        repeats = 0
        while True:
            if len(job["steps"]) >= BOARD_STEPS_MAX:
                job["stop"] = f"步數用完（最多 {BOARD_STEPS_MAX} 步），照公佈欄的事實回答"
                break
            plan = self._plan(job)
            if plan is None:
                job["stop"] = "規劃的模型沒有回覆（或回覆不是 JSON），照公佈欄的事實回答"
                break
            if plan["next"] == "answer" or plan["tool"] == "none":
                break
            step = self._step(job, plan)
            pages = 1
            while step.get("more_from") and pages < BOARD_VIEW_PAGES and len(job["steps"]) < BOARD_STEPS_MAX:   # 整份的檔案沒看完：程式接著看
                pages += 1
                step = self._step(job, dict(plan, args=[step["ran_args"][0], "--from", str(step["more_from"])], auto=True))
            repeats = repeats + 1 if step["status"] == "REPEAT" else 0
            if repeats >= BOARD_REPEATS_MAX:
                job["stop"] = f"連續 {repeats} 次排出跑過的工具與參數（卡住），照公佈欄的事實回答"
                break
        return self._answer(job)

    # ---------------------------------------------------------------- 規劃
    def _plan(self, job):
        system = prompt_files.load("board/plan.md", title=self.title, domain=self.domain, intro=self.intro or "—",
                                   tools="\n\n".join(tool_usage(self.agent.tools_dir, t) for t in self.tools), steps=BOARD_STEPS_MAX)
        schema = board_plan_schema(self.tools, len(job["items"]))
        user = self._board_text(job)
        out = None
        for _ in range(2):
            out = self.model("plan", system, user, schema, BOARD_PLAN_PREDICT, self._log(job["id"], step=len(job["steps"]) + 1))
            if out:
                break
        if not out:
            return None
        n = len(job["items"])
        item = out.get("item") if isinstance(out.get("item"), int) and 0 <= out.get("item") <= n else 0
        tool = str(out.get("tool") or "none")
        plan = {"step": len(job["steps"]) + 1, "understanding": str(out.get("understanding") or "")[:500],
                "next": "answer" if out.get("next") == "answer" else "tool", "item": item, "look_for": str(out.get("look_for") or "")[:200],
                "tool": tool if tool in self.tools else "none", "args": _split_include([str(a) for a in out.get("args") or [] if str(a) != ""])}
        job["plans"].append(plan)
        self.store.save(job)
        return plan

    # ---------------------------------------------------------------- 一步：低階執行、看
    def _step(self, job, plan):
        n = len(job["steps"]) + 1
        step = {"n": n, "time": _now(), "item": plan["item"], "look_for": plan["look_for"], "understanding": plan["understanding"],
                "tool": plan["tool"], "args": plan["args"], "node": f"s{n}", "status": None, "result_id": None, "head": "", "summary": "",
                "facts": [], "dropped": 0, "extract_job": None, "auto": bool(plan.get("auto"))}
        same = next((s for s in job["steps"] if s["status"] != "REPEAT" and s["tool"] == step["tool"]
                     and (s["args"] == step["args"] or s.get("ran_args") == step["args"])), None)
        if same:
            step.update(status="REPEAT", same=same["n"], head=_b("step_repeat", k=same["n"]))
            return self._done_step(job, step)
        node = {"id": step["node"], "tool": step["tool"], "args": step["args"], "expect": ["pass", "empty"], "why": step["look_for"] or "—"}
        job["graph"]["nodes"].append(node)
        ex = edg.Executor(self.agent, fixer=self.fixer)
        ej = ex.replan(job["edg_job"], job["graph"]) if job["edg_job"] else ex.start(job["graph"])
        job["edg_job"] = ej["id"]
        st = (ej.get("nodes") or {}).get(node["id"]) or {}
        inst = (st.get("instances") or [{}])[0]
        rec = (inst.get("attempts") or [None])[-1]
        if ej["status"] == "invalid" or st.get("state") == "need_user" or not rec:
            job["graph"]["nodes"].remove(node)        # 沒有執行的節點拿掉，下一步的圖才過得了檢查
            why = ("；".join(ej.get("problems") or []) if ej["status"] == "invalid" else
                   "這一步要使用者確認（唯讀的工作不做會改狀態的事）" if st.get("state") == "need_user" else st.get("reason") or "沒有執行")
            step.update(status="ERROR", head=f"[ERROR] {why}"[:ERROR_CHARS])
            return self._done_step(job, step)
        fix = inst.get("fix") or {}
        step["ran_args"] = rec.get("args") or step["args"]
        if fix.get("accepted"):
            step["fixed"] = {"args": fix.get("args"), "reason": fix.get("reason", "")}
        status = rec.get("status")
        step["result_id"] = rec.get("result_id")
        receipt = self._receipt(ej["id"], rec)
        if status == "error":
            text = str(rec.get("text") or rec.get("head") or "")
            step.update(status="ERROR", head=" ".join(text.split())[:ERROR_CHARS])
            return self._done_step(job, step)
        lines = self._output(step["result_id"])
        step.update(status="PASS" if status == "pass" else "EMPTY", head=(lines[0] if lines else rec.get("head") or "")[:300],
                    summary=self._summary(job, step["tool"], receipt, rec))
        if step["status"] == "EMPTY":
            step["head"] = " ".join(" ".join(lines[:3]).split())[:ERROR_CHARS]
            return self._done_step(job, step)
        c = receipt.get("counts") or {}
        whole = step["auto"] or not ({"--from", "--lines", "--tail", "--around"} & set(step.get("ran_args") or step["args"]))
        if step["tool"] == "view_file" and whole and isinstance(c.get("to"), int) and isinstance(c.get("total_lines"), int) and c["to"] < c["total_lines"]:
            step["more_from"] = c["to"] + 1             # 要整份、輸出沒看完：start() 的迴圈接著看下一段
        if step["tool"] in PROGRAM_FACT_TOOLS and step["summary"]:
            self._add_fact(job, step, step["summary"], [f"#{step['result_id']}"], [], "程式")
        self._look(job, step, lines, receipt)
        return self._done_step(job, step)

    def _done_step(self, job, step):
        job["steps"].append(step)
        job["updated"] = _now()
        self.store.save(job)
        new = f"，新的事實 {'、'.join(f'F{i}' for i in step['facts'])}" if step["facts"] else ""
        self._note(job["id"], f"📌 第 {step['n']} 步：{_cmd(step['tool'], step['args'])[:100]} → {step['status']}"
                              + (f"（#{step['result_id']}）" if step.get("result_id") else "") + new)
        return step

    def _receipt(self, eid, rec):
        rel = rec.get("receipt_file")
        if not rel:
            return {}
        try:
            with open(JobStore(os.path.join(self.agent.script_dir, "logs", EDG_JOBS_DIRNAME)).path(eid, rel), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _output(self, rid):
        """工具結果的原文（存檔的每一行，第 1 行是 lines[0]）。"""
        path = self.agent.result_file_path(rid) if rid else None
        if not path:
            return []
        lines = rc.read_body(path)[1]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        return lines

    def _rel(self, job, path):
        return answers.rel(path, job["cwd"])

    def _summary(self, job, tool, receipt, rec):
        """收據的摘要（程式算的數量；試過的步驟與程式的事實用）。"""
        c = receipt.get("counts") or rec.get("counts") or {}
        cut = "（結果不完整）" if receipt.get("truncated") or rec.get("truncated") else ""
        if tool == "search_text":
            per = sorted((receipt.get("per_file") or {}).items(), key=lambda kv: (-kv[1], kv[0]))
            files = "、".join(f"{self._rel(job, p)} {k} 筆" for p, k in per[:SUMMARY_FILES]) + ("…" if len(per) > SUMMARY_FILES else "")
            clipped = _b("search_clipped") if per and (len(per) > 1 and per[0][1] > SEARCH_PER_FILE or c.get("hits", 0) > SEARCH_TOTAL) else ""
            return (f"search_text「{receipt.get('pattern', '')}」共 {c.get('hits', 0)} 筆、{c.get('files', 0)} 個檔案" + (f"：{files}" if files else "")
                    + cut + clipped)
        if tool == "find_file":
            names = [self._rel(job, i["path"]) for i in receipt.get("items") or [] if i.get("path")]
            return (f"find_file「{receipt.get('keyword', '')}」找到 {c.get('total', 0)} 個（檔案 {c.get('files', 0)}、目錄 {c.get('dirs', 0)}）"
                    + (f"：{'、'.join(names[:SUMMARY_FILES])}" + ("…" if len(names) > SUMMARY_FILES else "") if names else "") + cut)
        if tool == "code_defs":
            per = receipt.get("per_file") or []
            files = "、".join(f"{self._rel(job, r['path'])} {r['lines']} 行" + (f"（類別 {r['classes']}、函式 {r['functions']}）"
                                                                                if r["classes"] or r["functions"] else "")
                             for r in per[:SUMMARY_FILES]) + ("…" if len(per) > SUMMARY_FILES else "")
            return (f"code_defs：{c.get('files', 0)} 份檔案、共 {c.get('lines', 0)} 行；類別 {c.get('classes', 0)}、函式／方法 {c.get('functions', 0)}"
                    + (f"：{files}" if files else "") + cut)
        if tool == "py_refs":
            per = receipt.get("per_file") or []
            only = _b("refs_only", kinds="、".join(receipt["kind"])) if receipt.get("kind") else ""
            files = "、".join(f"{self._rel(job, r['path'])} {r['refs']} 處（呼叫 {r['call']}、定義 {r['def']}）" for r in per[:SUMMARY_FILES])
            return (f"py_refs「{receipt.get('name', '')}」{only}{c.get('refs', 0)} 處、{c.get('files', 0)} 份檔案：定義 {c.get('defs', 0)}、"
                    f"呼叫 {c.get('calls', 0)}、import {c.get('imports', 0)}、指定 {c.get('assigns', 0)}、其他用到 {c.get('others', 0)}"
                    + (f"；{files}" + ("…" if len(per) > SUMMARY_FILES else "") if files else "") + cut)
        if tool == "view_file" and receipt.get("path"):
            rel, to, total = self._rel(job, receipt["path"]), c.get("to"), c.get("total_lines")
            more = (_b("view_more", start=to + 1, end=total, file=rel) if isinstance(to, int) and isinstance(total, int) and to < total else "")
            return f"{rel} 第 {c.get('from', '?')}～{to if to is not None else '?'} 行（共 {total if total is not None else '?'} 行）" + more
        if tool == "list_dir":
            return f"共 {c.get('total', 0)} 項（檔案 {c.get('files', 0)}、目錄 {c.get('dirs', 0)}）"
        if tool == "code_ast_reader" and receipt.get("path"):
            if receipt.get("refs"):
                return f"{self._rel(job, receipt['path'])} 裡「{receipt['refs']}」{c.get('refs', 0)} 處（定義 {c.get('defs', 0)}、呼叫 {c.get('calls', 0)}）"
            return f"{self._rel(job, receipt['path'])}：類別 {c.get('classes', 0)}、函式 {c.get('functions', 0)}（共 {c.get('lines', 0)} 行）"
        return ""

    def _look(self, job, step, lines, receipt):
        """成功的輸出用問題提煉成事實（每一則照提煉的核對），輸出的行號換成 檔案:行號，寫進公佈欄。"""
        if not lines:
            return
        rid, cmd = step["result_id"], _cmd(step["tool"], step.get("ran_args") or step["args"])
        where = _b("look_where_item", n=step["item"]) if step["item"] else _b("look_where_all")
        purpose = _b("look_purpose", question=job["question"], items=self._items_text(job), where=where, look_for=step["look_for"] or "—",
                     command=f"{cmd}（#{rid}）")
        allowed = "\n".join([job["question"], job["goal"]] + job["items"] + [cmd])
        # 提煉看到的每一行前面是輸出的行號；工具自己的行號（檔案的行號）留著的話一行有兩個數字，模型常寫成檔案的行號（差一行就對到表格的
        # 另一列、事實被核對拿掉）。輸出的行號由程式換成 檔案:行號（_locations 照原本的輸出）。
        look_lines = [_OWN_NUMBER.sub("", ln, count=1) for ln in lines]
        ex = extract.Extraction(self.agent, "board_look", [{"rid": str(rid), "label": step["tool"], "lines": look_lines}], purpose,
                                question=f"{job['question']} {step['look_for']}", allowed=allowed)
        try:
            out = ex.facts_only(prompt_files.load("board/look.md", max_facts=BOARD_LOOK_FACTS),
                                board_look_schema(BOARD_LOOK_FACTS, BOARD_FACT_CHARS), BOARD_LOOK_PREDICT)
        except Exception as e:   # noqa: BLE001  提煉失敗：這一步沒有新的事實（試過的步驟照記）
            step["look_error"] = f"{type(e).__name__}: {e}"
            return
        locs = _locations(lines, receipt, job["cwd"])
        step.update(extract_job=out["job"], dropped=len(out["dropped"]), chunks=out["chunks"], read=out["read"], unread=out["unread"],
                    look_failed=out["failed"], unread_where=self._unread_where(job, ex, locs))
        for f in out["facts"]:
            places = list(dict.fromkeys(locs[x] for x in f["nums"] if x in locs))
            refs = [f"{self._rel(job, p)}:{ln}" for p, ln in places] + [f"#{rid}"]
            rows = []
            for p, ln in places[:DOMAIN_QUOTE_LINES]:
                text = answers.line_of(p, ln, self._lines)
                if text is not None:
                    rows.append(f"{self._rel(job, p)}:{ln}：{text[:300]}")
            self._add_fact(job, step, f["text"], refs, rows, "提煉", lines_cited=f["nums"])

    def _unread_where(self, job, ex, locs):
        """提煉沒有讀的段落 → 給規劃看的位置：對得到檔案的行號就寫 檔案 第 a～b 行，對不到寫輸出的第 a～b 行。"""
        out = []
        for c in [c for c in ex.chunks if c["id"] in set(ex.job.get("unread") or [])]:
            inside = [locs[x] for x in range(c["start"] + 1, c["end"] + 1) if x in locs]
            if inside:
                out.append(_b("unread_file", file=self._rel(job, inside[0][0]), start=inside[0][1], end=inside[-1][1]))
            else:
                out.append(_b("unread_output", start=c["start"] + 1, end=c["end"]))
        return "、".join(out)

    def _add_fact(self, job, step, text, refs, rows, source, lines_cited=()):
        same = next((x for x in job["facts"] if x["text"] == text and x["refs"][:-1] == refs[:-1]), None)
        if same:
            return
        fid = len(job["facts"]) + 1
        job["facts"].append({"id": fid, "item": step["item"], "step": step["n"], "source": source, "text": text, "refs": refs, "rows": rows,
                             "rid": step["result_id"], "lines": list(lines_cited)})
        step["facts"].append(fid)

    # ---------------------------------------------------------------- 公佈欄（給規劃看的文字）
    def _items_text(self, job, counts=None):
        rows = []
        for k, it in enumerate(job["items"], 1):
            if counts is None:
                rows.append(f"{k}. {it}")
            else:
                c = counts.get(k, 0)
                rows.append(_b("item_row", n=k, item=it, state=_b("item_state_some", count=c) if c else _b("item_state_none")))
        return "\n".join(rows)

    def _fact_row(self, f):
        where = _b("fact_item", n=f["item"]) if f["item"] else ""
        return _b("fact_row", id=f["id"], where=where, step=f["step"], text=f["text"], refs="、".join(f["refs"]) or "—")

    def _steps_text(self, job):
        if not job["steps"]:
            return _b("steps_none")
        rows = []
        for st in job["steps"]:
            where = _b("look_where_item", n=st["item"]) if st["item"] else _b("look_where_all")
            if st.get("auto"):
                where = _b("look_where_auto")
            if st["status"] == "REPEAT":
                result = st["head"]
            elif st["status"] in ("ERROR", "EMPTY"):
                result = st["head"] + (_b("step_no_facts") if st["status"] == "EMPTY" else "")
            else:
                result = (st["summary"] or st["head"]) + (f"（#{st['result_id']}）" if st.get("result_id") else "")
                if st.get("unread_where"):
                    result += _b("step_unread", read=st.get("read"), chunks=st.get("chunks"), where=st["unread_where"])
                result += _b("step_facts", ids="、".join(f"F{i}" for i in st["facts"])) if st["facts"] else _b("step_no_facts")
            if st.get("fixed"):
                result = f"（參數照規格修正成 {shlex.join(st['fixed']['args'] or [])}）" + result
            rows.append(_b("step_row", n=st["n"], where=where, look_for=st["look_for"] or "—", tool=st["tool"], args=shlex.join(st["args"]),
                           result=result))
        return _b("steps", steps="\n".join(rows))

    def _board_text(self, job):
        counts = {}
        for f in job["facts"]:
            counts[f["item"]] = counts.get(f["item"], 0) + 1
        parts = [_b("question", question=job["question"])]
        if job["goal"] != job["question"]:
            parts.append(_b("goal", goal=job["goal"]))
        parts.append(_b("items", items=self._items_text(job, counts)))
        parts += [x for x in (job.get("known"), job.get("division")) if x]
        if job["previous"]:
            rows = [_b("previous_attempt", n=p.get("n"), skill=p.get("skill") or "—", status=p.get("status_text") or p.get("status") or "—",
                       note=f"（{p['note']}）" if p.get("note") else "", searched="、".join(p.get("searched") or []) or "—",
                       items="；".join(p.get("items") or []) or "—") for p in job["previous"]]
            parts.append(_b("previous", count=len({p.get("n") for p in job["previous"]}), attempts="\n".join(rows)))
        facts = job["facts"][-BOARD_FACTS_SHOWN:]
        if facts:
            more = len(job["facts"]) - len(facts)
            parts.append(_b("facts", facts=(_b("facts_more", count=more) + "\n" if more else "") + "\n".join(self._fact_row(f) for f in facts)))
        else:
            parts.append(_b("facts_none"))
        parts.append(self._steps_text(job))
        parts.append(_b("left", left=BOARD_STEPS_MAX - len(job["steps"])))
        return "\n\n".join(parts)

    # ---------------------------------------------------------------- 回答
    def _answer(self, job):
        n = len(job["items"])
        system = prompt_files.load("board/answer.md")
        facts = "\n".join(self._fact_row(f) for f in job["facts"]) or "（沒有）"
        parts = [_b("question", question=job["question"])] + ([_b("goal", goal=job["goal"])] if job["goal"] != job["question"] else [])
        parts += [_b("items", items=self._items_text(job)), _b("answer_facts", facts=facts), self._steps_text(job)]
        user = "\n\n".join(parts)
        schema = board_answer_schema(n, len(job["facts"]), DOMAIN_ANSWER_CHARS, DOMAIN_REFS_MAX)
        given = self._ask_answers(job, system, user, schema)
        if given is None:
            return self._finish(job, "failed", note="回答的模型沒有回覆（或回覆不是 JSON）")
        problems = self._problems(job, given)
        if problems:
            rows = [_b("answers_problem", k=k, item=job["items"][k - 1], why="；".join(w)) for k, w in sorted(problems.items())]
            fix_user = (user + "\n\n" + json.dumps({"answers": given}, ensure_ascii=False) + "\n\n" + _b("answers_fix", problems="\n".join(rows)))
            again = self._ask_answers(job, system, fix_user, schema, role="answer_fix")
            if again is not None:
                p2 = self._problems(job, again)
                if sum(map(len, p2.values())) <= sum(map(len, problems.values())):
                    given, problems = again, p2
            job["nudged"] = True
        facts_by = {f["id"]: f for f in job["facts"]}
        job["answers"] = [dict(a, refs=list(dict.fromkeys(r for i in a["facts"] if i in facts_by for r in facts_by[i]["refs"])), domain="")
                          for a in given]
        if given and len({a["item"] for a in given}) == n and all(a["status"] == "out_of_domain" for a in given):
            return self._finish(job, "out_of_domain", note="；".join(dict.fromkeys(a["text"] for a in given if a["text"])) or "—", problems=problems)
        return self._finish(job, "stopped" if job["stop"] else "done", note=job["stop"], problems=problems)

    def _ask_answers(self, job, system, user, schema, role="answer"):
        for _ in range(2):
            out = self.model(role, system, user, schema, BOARD_ANSWER_PREDICT, self._log(job["id"]))
            if out and isinstance(out.get("answers"), list):
                break
        else:
            return None
        n, seen, given = len(job["items"]), set(), []
        for a in out["answers"]:
            if not isinstance(a, dict) or not isinstance(a.get("item"), int) or not 1 <= a["item"] <= n or a["item"] in seen:
                continue
            seen.add(a["item"])
            status = a.get("status") if a.get("status") in ("answered", "not_found", "out_of_domain") else "not_found"
            given.append({"item": a["item"], "status": status, "text": " ".join(str(a.get("text") or "").split()),
                          "facts": [i for i in dict.fromkeys(a.get("facts") or []) if isinstance(i, int)]})
        return sorted(given, key=lambda a: a["item"])

    def _problems(self, job, given):
        """回答的核對 → {項目編號: [沒過的原因]}：每一項都要有；答到的要寫根據的事實、事實在公佈欄上、回答裡的名稱與數值在那幾則事實裡
        （extract.missing_tokens，問題、子目標、項目裡本來就有的字不核對）；查不到、不屬於的要寫原因。"""
        facts = {f["id"]: f for f in job["facts"]}
        got = {a["item"]: a for a in given}
        allowed = "\n".join([job["question"], job["goal"]] + job["items"])
        source = "\n".join(f["text"] + "\n" + "\n".join(f["rows"]) for f in job["facts"])
        out = {}
        for k in range(1, len(job["items"]) + 1):
            a, why = got.get(k), []
            if a is None:
                why.append(_b("why_missing"))
            elif a["status"] != "answered":
                if not a["text"]:
                    why.append(_b("why_no_reason"))
            else:
                if not a["facts"]:
                    why.append(_b("why_no_facts"))
                unknown = [i for i in a["facts"] if i not in facts]
                if unknown:
                    why.append(_b("why_fact_unknown", ids="、F".join(map(str, unknown))))
                cited = [facts[i] for i in a["facts"] if i in facts]
                if cited:
                    evidence = "\n".join(f["text"] + "\n" + "\n".join(f["rows"]) + "\n" + " ".join(f["refs"]) for f in cited)
                    bad = extract.missing_tokens(a["text"], evidence, source, allowed)
                    if bad:
                        close = answers.near(bad, evidence)
                        why.append(_b("why_tokens", tokens="、".join(bad)) + (_b("why_near", near="、".join(close)) if close else ""))
            if why:
                out[k] = why
        return out

    # ---------------------------------------------------------------- 收尾與報告
    def _finish(self, job, status, note="", problems=None):
        problems = problems or {}
        job.update(status=status, updated=_now(), problems={str(k): v for k, v in problems.items()})
        report = self._report(job, note, problems)
        self.store.write(job["id"], "report.md", report)
        job["result"] = {"status": status, "note": note, "report": report,
                         "sources": [st["result_id"] for st in job["steps"] if st.get("result_id")]}
        self.store.save(job)
        self._note(job["id"], f"📌 公佈欄結束：{STATUS_TEXT[status]}" + (f"（{note[:100]}）" if note else ""))
        return job

    def _report(self, job, note, problems):
        lines = [f"# 公佈欄的結果：{STATUS_TEXT[job['status']]}", f"- 問題：{job['question']}"]
        if job["goal"] != job["question"]:
            lines.append(f"- 子目標：{job['goal']}")
        lines += [f"- 要回答的項目 {k}：{x}" for k, x in enumerate(job["items"], 1)]
        if job["previous"]:
            lines.append(f"- 第 {job['attempt']} 次交給這個領域（之前：" + "；".join(
                f"第 {p.get('n')} 次 {p.get('skill') or '—'}：{p.get('status_text') or p.get('status') or '—'}" for p in job["previous"]) + "）")
        ran = sum(1 for st in job["steps"] if st["status"] != "REPEAT")
        lines.append(f"- 做法：{STEP_SKILL}，{len(job['steps'])} 步（執行 {ran} 個工具），公佈欄上 {len(job['facts'])} 則事實")
        if note:
            lines.append(f"- 說明：{note}")
        lines += ["", "## 每一項的回答（照公佈欄的事實；回答裡的名稱與數值由程式核對）"]
        facts = {f["id"]: f for f in job["facts"]}
        got = {a["item"]: a for a in job["answers"]}
        for k, item in enumerate(job["items"], 1):
            a = got.get(k)
            if a is None:
                lines.append(f"{k}. {item}：（沒有回答）")
            elif a["status"] in ("not_found", "out_of_domain"):
                lines.append(f"{k}. {item}：{'查不到' if a['status'] == 'not_found' else '不屬於這個領域'}。{a['text']}")
            else:
                refs = [r for r in a["refs"] if not r.startswith("#")] or a["refs"]
                lines.append(f"{k}. {item}：{a['text']}" + (f"（出處：{'、'.join(refs[:DOMAIN_REFS_MAX * 2])}）" if refs else "")
                             + (f"（根據 {'、'.join(f'F{i}' for i in a['facts'])}）" if a["facts"] else ""))
                rows = list(dict.fromkeys(r for i in a["facts"] if i in facts for r in facts[i]["rows"]))
                lines += [f"   > {r}" for r in rows[:DOMAIN_QUOTE_LINES]]
            if k in problems:
                lines.append(f"   ⚠️ 沒有通過核對：{'；'.join(problems[k])}")
        lines += ["", "## 公佈欄的事實（程式核對過名稱與數值在原文裡）"]
        for f in job["facts"]:
            lines.append(f"F{f['id']}（第 {f['step']} 步，{f['source']}）：{f['text']}（出處：{'、'.join(f['refs']) or '—'}）")
            lines += [f"   > {r}" for r in f["rows"]]
        if not job["facts"]:
            lines.append("（沒有）")
        lines += ["", "## 做了哪些步驟"]
        for st in job["steps"]:
            if st["status"] == "REPEAT":
                lines.append(f"{st['n']}. {_cmd(st['tool'], st['args'])} → {st['head']}")
            else:
                res = st["summary"] if st["status"] == "PASS" and st["summary"] else st["head"]
                lines.append(f"{st['n']}. {_cmd(st['tool'], st.get('ran_args') or st['args'])} → {res}"
                             + (f"（#{st['result_id']}）" if st.get("result_id") else "")
                             + (f"；事實 {'、'.join(f'F{i}' for i in st['facts'])}" if st["facts"] else ""))
        if not job["steps"]:
            lines.append("（沒有執行任何工具）")
        return "\n".join(lines)

    # ---------------------------------------------------------------- 其他
    def _link(self, previous, jid, attempt):
        """之前的工作（中階、子工作階段或公佈欄）記下這一次（決策圖從上一次連到下一次）。"""
        dirs = {"sub": SUB_JOBS_DIRNAME, "board": BOARD_JOBS_DIRNAME}
        for p in previous:
            store = JobStore(os.path.join(self.agent.script_dir, "logs", dirs.get(p.get("kind"), MID_JOBS_DIRNAME)))
            pj = store.load(p.get("job")) if p.get("job") else None
            if pj:
                pj.setdefault("next", []).append({"job": jid, "n": attempt, "kind": "board"})
                store.save(pj)

    def _log(self, jid, **extra):
        return lambda rec: self.store.append(jid, "calls.jsonl", dict(rec, **extra))

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


def _split_include(args):
    """`--include "*.cpp|*.h"`（一個參數寫了好幾種檔名）→ 每一種一個 --include：腳本的 --include 一次只吃一種寫法，寫在一起會 0 筆、又沒有錯誤可以修。"""
    out, i = [], 0
    while i < len(args):
        if args[i] == "--include" and i + 1 < len(args) and re.search(r"[|,，]", args[i + 1]):
            for g in [x.strip() for x in re.split(r"[|,，]", args[i + 1]) if x.strip()]:
                out += ["--include", g]
            i += 2
            continue
        out.append(args[i])
        i += 1
    return out


def _locations(lines, receipt, cwd):
    """工具輸出的行號 → (檔案的絕對路徑, 檔案裡的行號)：`## 檔案（…）` 的節（search_text、py_refs、code_defs）、`120→`（search_text、view_file）、
    `行 120`（code_ast_reader、py_refs、code_defs）；只看一個檔案的工具（view_file、code_ast_reader）用收據的 path。對不上的行不列。"""
    single = receipt.get("path") if isinstance(receipt.get("path"), str) else None
    cur, out = single, {}
    for i, ln in enumerate(lines, 1):
        m = _HEAD_PATH.match(ln)
        if m:
            p = os.path.normpath(os.path.join(cwd or ".", os.path.expanduser(m.group(1).strip())))
            if os.path.isfile(p):
                cur = p
                continue
        if not cur:
            continue
        m = _NUMBERED.match(ln) or _AT_LINE.search(ln)
        if m:
            out[i] = (cur, int(m.group(1)))
    return out
