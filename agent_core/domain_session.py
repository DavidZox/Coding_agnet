"""領域 session（2026-11-23 框架，docs/框架討論紀錄.md）：主 session 交辦的任務（子目標、要回答的項目）在這裡做完，經過與結果交回主 session。
每一項附使用者的原話（主 session 抄、程式核對過；框架討論紀錄第 6 輪的 B）：第一則訊息、提煉的錨點與報告都帶著，項目的意思以原話為準。

一個迴圈，每一輪模型回一個 JSON，state 是三種之一，由程式核對、照它接著做（F4）：
1. **domains**（選領域，可以多個）：要在 DOMAIN.md 的清單裡。程式載入這些領域的技能清單交給它——領域的〈做法〉、有骨架的技能（說明、
   什麼時候用、參數）、單步的工具（技能索引的那一行與〈語法〉的參數寫法）、共用的工具。第一輪一定是這個；重選最多 DOMAIN_RESELECT_MAX 次。
2. **skill**（用一個技能）：只寫技能的名稱；程式接著給那個技能的參數表單，下一輪只填表單（_form_turn，schema 只有該填的欄位：
   schemas.domain_form_schema；表單的那一輪不算在回的輪數裡）。
   - 有骨架的技能（composite.py）：每個參數一欄（quote、value），原文要一字不改（F3），程式核對（composite.verify_param；原文＝問題、
     子目標、項目、前面每一步交給它的結果；開頭多抄了程式的標題「【子目標】」這種的，拿掉標題再核對；quote 抄了別段、值本身就在原文裡的也收；
     空的與預設值當成沒提到（路徑的預設值配的 quote 寫了別的名稱的照核對交回），工作目錄底下的絕對路徑換成相對的；範圍是 path 的技能的搜尋字
     原文裡沒有、要搜的範圍裡有的也收：_contract、_scope_hits）。沒過的只把那幾個參數交回重填
     一次，還是沒過就回到選技能，都不算一步；過了交給 composite.Runner 跑骨架與回退。缺參數、路徑有好幾個也交回它決定（附候選）。
   - 工具：表單只有 args（一行參數，照工具的〈語法〉寫，不是 JSON），程式照技能名稱找腳本執行（agent._run_tool_once：跟主對話同一條路——
     確認關卡、存檔 #編號、收據、狀態標記的同步）；只能用選的領域的工具與共用的工具（orchestrator.domain_gate 看 agent._sub_allowed）。
     args 整個是 JSON、照抄了〈語法〉的佔位符（<…>、[…]）、或可以不寫的部分填成「[]」的不執行，交回重填一次，還是一樣就回到選技能，
     都不算一步（_args_problem）。
   - 有骨架的技能跑完，程式照收據算的彙整（composite.Runner._totals：每個檔案的數量與總數）存成 #編號，接在技能的狀態後面（回報時可以當出處）。
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
from .schemas import DOMAIN_REPLY_CHARS, domain_form_schema, domain_session_schema
from .turn import _content_for_context

STATES = ("domains", "skill", "report")
STATUS_TEXT = {"running": "執行中", "need_user": "等使用者回答", "done": "做完", "stopped": "停下來（步數用完或卡住）",
               "cancelled": "使用者取消", "failed": "失敗（模型沒有回覆）"}
_KEEP_RESULTS = 3                           # 對話太長時，最新的這幾份結果不清
_SYNTAX = re.compile(r"`EXECUTE:\s*scripts/[\w.-]+\s*([^`]*)`")
_PLACEHOLDER = re.compile(r"<[^<>`\s][^<>`]*>|\[[^\[\]`]+\]")   # 〈語法〉的佔位符：<名稱>、[路徑]（args 照抄了它＝沒有換成值）
_EMPTY_ARG = re.compile(r"(?<!\S)\[\s*\](?!\S)")    # args 裡單獨的「[]」：〈語法〉裡可以不寫的部分填成空的中括號（沒有換成值；引號裡的不算）
# 程式給模型看的標題（「【子目標】」「【要回答的項目】（…）」「【第 2 步的結果】…（…）」）：表單的原文開頭抄了它、核對沒過時拿掉再核對
# 一次（第 3 步 e4b 合約沒過的 191 個參數裡 110 個是這樣，值是對的；設計筆記 2.57 ①）
_LABEL = re.compile(r"^【[^】]{1,20}】\s*(?:（[^）]{0,60}）)?\s*")


def _s(key, /, **fields):
    """prompts/domain/session.md 的一則。"""
    return prompt_files.load("domain/session.md", key, **fields)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _json_object(raw):
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse_reply(raw):
    """模型回覆（JSON 字串）→ {"thought", "state", "domains", "skill", "answers", "reply", "cut"}；不是 JSON 物件回 None。
    state 不是三種之一時是空字串；cut：寫到字串上限（被截斷）的欄位。"""
    data = _json_object(raw)
    if data is None:
        return None
    state = str(data.get("state") or "").strip()
    domains = data.get("domains") if isinstance(data.get("domains"), list) else []
    out = {"thought": str(data.get("thought") or "").strip(), "state": state if state in STATES else "",
           "domains": list(dict.fromkeys(str(x).strip() for x in domains if str(x).strip())),
           "skill": str(data.get("skill") or "").strip(), "answers": parse_answers(data.get("answers")),
           "reply": str(data.get("reply") or "").strip()}
    caps = (("thought", REPLY_THOUGHT_CHARS), ("reply", DOMAIN_REPLY_CHARS))
    out["cut"] = [k for k, n in caps if isinstance(data.get(k), str) and len(data[k]) >= n]
    return out


def parse_form(raw, params=None):
    """表單那一輪的回覆 → {"thought", "params": {名稱: {"quote", "value"}}, "args", "cut"}；不是 JSON 物件回 None。
    params＝有骨架的技能這一輪要填的參數名稱（沒寫的當成空的）；None＝工具，只取 args。"""
    data = _json_object(raw)
    if data is None:
        return None
    out = {"thought": str(data.get("thought") or "").strip(), "params": {}, "args": "", "cut": []}
    caps = [("thought", REPLY_THOUGHT_CHARS)]
    if params is None:
        out["args"] = str(data.get("args") or "").strip()
        caps.append(("args", REPLY_ARGS_CHARS))
    else:
        cells = data.get("params") if isinstance(data.get("params"), dict) else {}
        for name in params:
            cell = cells.get(name) if isinstance(cells.get(name), dict) else {}
            out["params"][name] = {"quote": str(cell.get("quote") or ""), "value": str(cell.get("value") or "")}
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


def answered_items(job):
    """回報裡答到、而且過了核對的每一項：[(項目, 回答)]（主 session 依報告回答時核對有沒有漏了報告的編號與數字，orchestrator._answer_problems）。"""
    bad, items = set(job.get("problems") or {}), job.get("items") or []
    return [(items[a["item"] - 1], a["text"]) for a in job.get("answers") or []
            if a.get("status") == "answered" and 1 <= a.get("item", 0) <= len(items) and str(a["item"]) not in bad]


class DomainSession:
    """start(問題, 子目標, 項目) → job（也存成 job.json）；停在確認關卡時 resume(編號, approve=…)，使用者取消 cancel(編號)。
    registry：orchestrator.load_registry 的結果。fixer：有骨架的技能交給低階的第 1 級修正（None＝預設的模型）。"""

    def __init__(self, agent, registry, fixer=None):
        self.agent = agent
        self.reg = registry
        self.fixer = fixer
        self.store = JobStore(os.path.join(agent.script_dir, "logs", DOMAIN_JOBS_DIRNAME))

    # ---------------------------------------------------------------- 進入點
    def start(self, question, goal, items, quotes=None, previous=None, attempt=1):
        """quotes：每一項的使用者原話（跟 items 一樣長；orchestrator 核對過）。previous：同一個問題之前交辦的經過
        （[{"n", "job", "status_text", "note", "steps"}]，orchestrator 從這一回合的紀錄取）。"""
        jid = self.store.new_id()
        self.store.prune(DOMAIN_JOBS_KEEP)
        job = {"id": jid, "kind": "domain", "status": "running", "created": _now(), "updated": _now(), "cwd": self.agent.current_cwd,
               "question": question, "goal": (goal or question).strip(), "items": list(items or []),
               "quotes": list(quotes or [""] * len(items or [])), "attempt": attempt,
               "previous": list(previous or []), "domains": [], "picks": [], "messages": [], "steps": [], "turns": 0, "form": None, "forms": 0,
               "blocked": [], "sources": "", "need_user": None, "asked": [], "nudged": False, "answers": [], "problems": {}, "result": None}
        job["system"] = self._system()
        job["messages"].append({"role": "user", "content": self._first(job)})
        job["sources"] = "\n".join([job["question"], job["goal"]] + job["items"] + [q for q in job["quotes"] if q])
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
            if job["form"]:                         # 選了技能：這一輪填它的參數表單
                stop = self._form_turn(job)
                if stop:
                    return stop
                continue
            if len(job["steps"]) >= DOMAIN_STEPS_MAX:
                return self._finish(job, "stopped", note=f"技能用了 {DOMAIN_STEPS_MAX} 次（上限），照做到的收尾")
            if job["turns"] >= DOMAIN_TURNS_MAX:
                return self._finish(job, "stopped", note=f"回了 {DOMAIN_TURNS_MAX} 輪還沒有回報（上限），照做到的收尾")
            parsed, raw = self._ask(job, domain_session_schema(list(self.reg["domains"]), len(job["items"])), parse_reply)
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
            self._skill(job, parsed)

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
        """選了一個技能：在清單裡就交給它那個技能的參數表單（下一輪填，_form_turn）；不在清單裡擋下。"""
        skills, tools = self._available(job)
        name = parsed["skill"]
        if name not in skills and name not in tools:
            self._tell(job, _s("err_skill", skill=name or "（空的）", names="、".join(list(skills) + tools)), f"技能清單裡沒有「{name}」")
            return
        spec = skills[name][1] if name in skills else None
        job["form"] = {"skill": name, "composite": spec is not None, "round": 1, "only": None, "kept": {},
                       "thought": parsed["thought"], "reply": parsed["reply"]}
        text = (_s("form_composite", skill=name, params=self._param_rows(spec)) if spec is not None else
                _s("form_tool", skill=name, syntax=self._syntax(name)))
        job["messages"].append({"role": "user", "content": text})
        job["updated"] = _now()
        self.store.save(job)
        self._note(job["id"], f"🧭 選技能：{name}（{parsed['thought'][:60]}）")

    def _form_turn(self, job):
        """填表單的那一輪：有骨架的技能照合約核對、工具核對 args 的寫法（_args_problem）——沒過的交回重填一次（有骨架的技能只有沒過的那幾個
        參數），還是沒過就回到選技能（都不算一步）；工具先拿掉照抄的工具名稱。過了就執行（跟之前某一步一模一樣的不執行）。
        回 job＝停下來（確認關卡、模型沒有回覆），None＝接著做。"""
        form = job["form"]
        name = form["skill"]
        skills, _ = self._available(job)
        spec = skills[name][1] if form["composite"] else None
        names = None if spec is None else [p["name"] for p in spec["parameters"] if form["only"] is None or p["name"] in form["only"]]
        parsed, raw = self._ask(job, domain_form_schema(names), lambda text: parse_form(text, names), form=name)
        job["form"] = None
        if parsed is None:
            return self._finish(job, "failed", note=f"領域 session 的模型沒有填 {name} 的參數表單（或回覆不是 JSON）")
        job["forms"] += 1
        job["messages"].append({"role": "assistant", "content": raw})
        pending = {"skill": name, "thought": form["thought"], "reply": form["reply"]}
        if spec is None:
            pending["args"] = self._own_args(name, parsed["args"])
            why = self._args_problem(name, pending["args"])
            if why and form["round"] == 1:
                job["form"] = dict(form, round=2)
                self._tell(job, _s("form_fix_tool", skill=name, problem=why, syntax=self._syntax(name)), f"{name} 的 args 寫法不對")
                return None
            if why:
                self._tell(job, _s("form_failed", skill=name, problems=why), f"{name} 的 args 重填之後還是寫法不對")
                return None
            if self._same(job, name, " ".join(pending["args"].split())):
                return None
            guard = self.agent.guard_check({"action": self._action(name, pending["args"])})
            if guard:
                self._wait(job, pending, guard)
                return job
            self._tool(job, pending)
            return None
        cells = dict(form["kept"], **parsed["params"])
        params, problems, bad = self._contract(job, spec, cells)
        if problems and form["round"] == 1:
            job["form"] = dict(form, round=2, only=bad, kept={k: v for k, v in cells.items() if k not in bad})
            self._tell(job, _s("form_fix", skill=name, problems="\n".join(problems), params=self._param_rows(spec, bad)),
                       f"{name} 的參數沒有通過核對")
            return None
        if problems:
            self._tell(job, _s("form_failed", skill=name, problems="\n".join(problems)), f"{name} 的參數重填之後還是沒有通過核對")
            return None
        how = composite.param_sig({k: v["value"] for k, v in params.items()})
        if self._same(job, name, how):
            return None
        self._composite(job, pending, self.reg["domains"][skills[name][0]], name, params, how)
        return None

    def _own_args(self, tool, args):
        """工具的參數：開頭照抄了工具名稱或腳本路徑的（「find_file x .」「scripts/ls_cmd.py .」）拿掉那一段，其他照原樣。"""
        head, _, rest = args.strip().partition(" ")
        script = self._script_of(tool) or ""
        if head in (tool, f"{tool}.md") or (script and os.path.basename(head) == script):
            return rest.strip()
        return args

    def _args_problem(self, tool, args):
        """工具表單的 args 寫法：整個是 JSON（物件或陣列）、照抄了〈語法〉的佔位符（<…>、[…]）、或可以不寫的部分填成單獨的「[]」→ 說明；
        過了是 ""。建議 1 的比較裡 26b 一次把佔位符當成鍵寫成 JSON（{"<名稱關鍵字>": …}），連錯 4 步（設計筆記 2.58）；e4b 把〈語法〉裡可以不寫的
        部分填成「[]」照樣執行、回「找不到路徑：[]」（設計筆記 2.70、2.71）。"""
        text = args.strip()
        if text.startswith(("{", "[")):
            try:
                if isinstance(json.loads(text), (dict, list)):
                    return _s("reject_args_json")
            except ValueError:
                pass
        marks = sorted({m.group() for row in self._syntax_args(tool) for m in _PLACEHOLDER.finditer(row)})
        copied = [m for m in marks if m in text] + (["[]"] if _EMPTY_ARG.search(text) else [])
        return _s("reject_args_placeholder", marks="、".join(copied)) if copied else ""

    def _same(self, job, skill, how):
        """跟之前某一步一模一樣：不執行，交給模型那一步的結果（回 True）。"""
        prev = next((st for st in job["steps"] if st["skill"] == skill and st["sig"] == how), None)
        if prev:
            self._tell(job, _s("err_same", n=prev["n"], skill=skill, how=prev["how"], head=prev["head"] or "—"), f"跟第 {prev['n']} 步一樣，沒有執行")
        return bool(prev)

    def _contract(self, job, spec, cells):
        """表單的每一欄（{參數: {"quote", "value"}}）→ ({名稱: {"value", "quote"（核對過的那一段）, "source"}}, [沒過的說明], [沒過的參數])。
        值是空的或規格的預設值（路徑寫工作目錄本身＝「.」）當成沒提到（表單列出每個參數，模型會把「沒有提到就用 .」照寫進 value）——路徑的預設值
        配的 quote 寫了別的名稱的不算，照核對交回（quote 寫的範圍不換成整個工作目錄，設計筆記 2.70）；
        工作目錄底下的絕對路徑先換成相對的（composite.unmentioned、relative）。原文要在這個 session 給模型看過的字裡：照 quote 核對沒過的，原文開頭是
        程式的標題（_LABEL）就拿掉標題再核對一次，再拿值本身當原文核對一次（值就在原文裡就收，composite.own_quote；設計筆記 2.69）。範圍是 path 的
        技能的搜尋字還是沒過的，最後數要搜的範圍裡有沒有（_scope_hits：每一個都有才收，出處寫 scope；檔名寫法不數；設計筆記 2.71、2.72）。要讀的那一份
        （沒有預設值的路徑）只寫了上層、或上層與名稱寫在同一段，抄的原文寫「<a> 的 <b>」的，照補路徑的做法找到剛好一份就換成那一份（_doc_of，記 given、of；
        設計筆記 2.74）。都沒過的交回，說明照模型抄的 quote 寫（沒抄 quote 的寫明沒抄原文）。"""
        params, problems, later = {}, {}, []
        scope = composite.scope_param(spec)
        for p in spec["parameters"]:
            cell = cells.get(p["name"])
            if not cell:
                continue
            quote = composite._unquote(cell["quote"])
            given = composite.relative(p, composite._unquote(cell["value"]), job["cwd"])
            if composite.unmentioned(p, given, quote, job["cwd"]):
                continue
            value, why = (composite.verify_param(p, quote, given, job["sources"]) if quote
                          else (None, _s("reject_no_quote", name=p["name"], value=given)))
            for again in [x for x in (_LABEL.sub("", quote, count=1), composite.own_quote(p, given)) if x and x != quote] if why else []:
                value2, why2 = composite.verify_param(p, again, given, job["sources"])
                if not why2:
                    quote, value, why = again, value2, None
                    break
            of = self._doc_of(job, p, quote, given, value)
            if of:
                params[p["name"]] = {"value": of[0], "quote": quote, "source": "contract", "given": given, "of": of[1]}
            elif why and scope and composite.scope_items(p, given):
                later.append((p, quote, given, why))
            elif why:
                problems[p["name"]] = why
            elif value is not None:
                params[p["name"]] = {"value": value, "quote": quote, "source": "contract"}
                if p["type"] == "path" and value != composite.plain_path(given):
                    params[p["name"]]["given"] = given      # 程式只留了原文裡的名稱（composite._name_only）：結果裡寫明
        for p, quote, given, why in later:
            hits = None if scope in problems else self._scope_hits(job, p, given, params, scope)
            if hits is None:
                problems[p["name"]] = why
            else:
                params[p["name"]] = {"value": composite.words_of(given) if p["type"] == "words" else given, "quote": quote, "source": "scope",
                                     "hits": hits}
        bad = [p["name"] for p in spec["parameters"] if p["name"] in problems]
        return params, [problems[k] for k in bad], bad

    def _scope_hits(self, job, p, value, params, scope):
        """原文沒有的搜尋字：程式數要搜的範圍裡有沒有（composite.scope_items 的每一個；原文裡有的那一個不數）→ {每一個: 筆數}，有一個是 0 就回
        None。範圍＝同一張表單核對過的 path（沒提到、或工作目錄裡還找不到——執行時才照 fetch 查——用工作目錄）與骨架搜尋時的 files、exclude；
        照 search_text 照字面、不分大小寫數幾行（設計筆記 2.71、2.72）。範圍裡有這個 agent 自己的 logs（工作目錄就是它的專案）時不數 logs：
        模型剛填的表單已經記在裡面，會數到它自己寫的字。"""
        root = job["cwd"] or "."
        if not os.path.isdir(root):
            return None
        where = os.path.join(root, (params.get(scope) or {}).get("value") or ".")
        where = where if os.path.exists(where) else root
        inc = (params.get("files") or {}).get("value")
        exc = list((params.get("exclude") or {}).get("value") or [])
        own = os.path.abspath(os.path.join(self.agent.script_dir, "logs"))
        if own.startswith(os.path.abspath(where).rstrip("/") + "/"):
            exc.append(os.path.basename(own))
        out = {}
        for x in composite.scope_items(p, value):
            if composite._in_source(x, job["sources"], p["type"]):
                continue
            n = self._count(f"數「{x}」在範圍裡有沒有（參數 {p['name']}：原文沒有）",
                            [x, where, "-F", "-l"] + (["--include", inc] if inc else []) + (["--exclude-dir", "|".join(exc)] if exc else []))
            if not n:
                return None
            out[x] = n
        return out

    def _count(self, goal, args):
        """程式照 search_text 數一次（composite.Runner.count：不交給修正的模型、讀收據的筆數）。"""
        return composite.Runner(self.agent).count(goal, args)

    def _doc_of(self, job, p, quote, given, value):
        """要讀的那一份（沒有預設值的路徑：doc_lookup 的 doc）只寫了上層、或上層與名稱寫在同一段，抄的原文（在原文裡）寫「<a> 的 <b>」（composite.path_of）
        → 照補路徑的做法找 <a>/<b>（fetch：檔名是 <b>.md、路徑裡有 <a>），剛好一份 → (那一份的路徑, 原文的那一段)；不然 None，照原本的核對（只寫上層的
        照舊用整個上層、同一段兩個名稱的照舊交回）。e4b 文件題 doc 只寫套件的 o～r 16 次：用整個套件當要讀的文件，詞一般的就讀不到那一行（設計筆記 2.74）。"""
        if p["type"] != "path" or "default" in p or not p.get("fetch") or not quote or not composite._in_source(quote, job["sources"], p["type"]):
            return None
        got = composite.path_of(quote, given)
        if not got or got[0] == value:
            return None
        found = self._find(job, p, got[0])
        return (found[0], got[1]) if len(found) == 1 else None

    def _find(self, job, p, value):
        """程式照 fetch 找一次（composite.Runner.find：不交給修正的模型）→ 候選（相對於工作目錄）。"""
        return composite.Runner(self.agent).find(job["cwd"], p, value)

    def _composite(self, job, parsed, domain, name, params, how):
        """執行有骨架的技能（parsed：選技能那一輪的 thought、reply），每個節點的結果接進對話、記一步。"""
        res = composite.Runner(self.agent, fixer=self.fixer, note=lambda t: self._note(job["id"], t)).run(domain, name, params)
        lines = [_s("composite_status", status=composite.STATUS_TEXT[res["status"]], note=f"（{res['note']}）" if res["note"] else "")]
        for sw in res["switched"]:
            lines.append(_s("composite_switched", fallback=sw["fallback"], frm=sw["from"], to=sw["to"]))
        for fb in res["fallbacks"]:
            if fb.get("result") == "replanned":
                lines.append(_s("composite_fallback", say=fb["say"]))
        lines += [_s("composite_of", name=k, given=v["given"], value=v["value"], of=v["of"]) if v.get("of")
                  else _s("composite_kept", name=k, given=v["given"], value=v["value"]) for k, v in params.items() if v.get("given")]
        for a in res["auto_filled"]:
            lines.append(_s("composite_filled", name=a["param"], given=a["given"], value=a["value"]))
        if res["need"]:
            cands = "；".join(res["need"].get("candidates") or [])
            lines.append(_s("composite_need", question=res["need"]["question"], candidates=_s("composite_candidates", candidates=cands) if cands else ""))
        totals, trid = self._totals(res)
        parts, rids, summarized = ["\n".join(lines + ([totals] if totals else []))], [trid] if trid else [], False
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

    def _totals(self, res):
        """有骨架的技能的彙整（composite.Runner._totals）存成 #編號、回報時可以當出處 → (接在技能的狀態後面的那一段, #編號)；沒有是 ("", None)。"""
        if not res.get("totals"):
            return "", None
        a, text = self.agent, "\n".join(res["totals"])
        a.last_receipt = None               # 不是腳本的輸出：軌跡不要記上一支腳本的收據
        a._record_trajectory(f"{res['skill']}_totals", [], text, a.current_cwd, a.container_cwd, a.target_container)
        if not a.last_result_id:              # 存檔失敗：照樣給它看，只是不能當出處
            return text, None
        return _s("composite_totals", rid=a.last_result_id, text=text), a.last_result_id

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
        allowed = "\n".join([job["question"], job["goal"]] + job["items"] + job["quotes"])
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
        lines += [f"- 要回答的項目 {k}：{x}" + (f"（使用者的原話：「{q}」）" if q else "") for k, (x, q) in enumerate(zip(job["items"], job["quotes"]), 1)]
        if job["previous"]:
            lines.append(f"- 第 {job['attempt']} 次交辦（之前：" + "；".join(f"第 {p.get('n')} 次 {p.get('status_text') or '—'}" for p in job["previous"]) + "）")
        labels = [composite.domain_label(self.reg["domains"][d]) if d in self.reg["domains"] else d for d in job["domains"]]
        lines.append(f"- 領域：{'、'.join(labels) or '（沒有選）'}；用了 {len(job['steps'])} 個技能")    # 報告給主 session：不寫識別名稱
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
    def _ask(self, job, schema, parse, form=None):
        """模型一次 → (parsed, 原文)。form＝填哪個技能的表單（None＝每一輪的決定：state 要是三種之一）。不是 JSON（或 state 不對）：附上那一則
        與提醒再問一次；寫到字串上限被截斷：不執行，接提醒再問一次。兩次都不行回 (None, 原文)。每次呼叫記進 calls.jsonl（送出的最後一則與回覆）。"""
        msgs = self._fit(job)
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
            parsed = parse(raw)
            ok = parsed is not None and (form is not None or bool(parsed["state"]))
            cut = parsed["cut"] if ok else []
            error = None if ok and not cut else err or ("寫到長度上限被截斷：" + "、".join(cut) if cut else
                                                         "回覆不是表單的 JSON 或是空的" if form else "回覆不是 JSON、是空的，或 state 不是三種之一")
            self.store.append(job["id"], "calls.jsonl", {"turn": job["turns"] + (0 if form else 1), "form": form, "model": model,
                                                         "user": msgs[-1]["content"], "response": raw, "error": error,
                                                         "ms": round((time.time() - t0) * 1000)})
            if ok and not cut:
                return parsed, raw
            msgs = msgs + ([{"role": "user", "content": _s("cut", fields="、".join(cut))}] if cut else
                           [{"role": "assistant", "content": raw}, {"role": "user", "content": _s("retry_form" if form else "retry")}])
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
        items = "\n".join(_s("item_quote", k=k, item=x, quote=q) if q else f"{k}. {x}" for k, (x, q) in enumerate(zip(job["items"], job["quotes"]), 1))
        prev = ""
        if job["previous"]:
            rows = [_s("previous_attempt", n=p.get("n"), steps=p.get("steps") or "—", status=p.get("status_text") or "—",
                       note=f"（{p['note']}）" if p.get("note") else "") for p in job["previous"]]
            prev = _s("previous", count=len(job["previous"]), attempts="\n".join(rows))
        return _s("first", goal=job["goal"], items=items, question=job["question"], previous=prev)

    @staticmethod
    def _param_rows(spec, only=None):
        """有骨架的技能的參數，每個一行（名稱、種類、必填或沒提到時怎麼辦、意思）；only＝只列這幾個（交回重填時）。技能清單與表單共用。"""
        kinds = {"name": _s("type_name"), "text": _s("type_text"), "path": _s("type_path"), "glob": _s("type_glob"),
                 "names": _s("type_names"), "words": _s("type_words")}
        rows = []
        for p in spec["parameters"]:
            if only is not None and p["name"] not in only:
                continue
            common = {"name": p["name"], "kind": kinds[p["type"]], "desc": p["desc"]}
            if p.get("required"):
                rows.append(_s("param_required", **common))
            elif "default" in p:
                rows.append(_s("param_default", default=p["default"], **common))
            else:
                rows.append(_s("param_optional", **common))
        return "\n".join(rows) or "  —"

    def _skills_text(self, job):
        """選了領域之後交給模型的技能清單：每個領域的〈做法〉、有骨架的技能（說明、什麼時候用、參數）、工具（索引的那一行與〈語法〉）；
        最後是共用的工具（選的領域沒有列的）。"""
        blocks, listed = [], set()
        for name in job["domains"]:
            d = self.reg["domains"][name]
            entries = []
            for sk, spec in d["skills"].items():
                entries.append(_s("composite_entry", name=sk, description=spec["meta"]["description"],
                                  when=" ".join(spec["sections"].get("什麼時候用", "").split()) or "—", params=self._param_rows(spec)))
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

    def _syntax_args(self, tool):
        """規格的〈語法〉裡每一個 `EXECUTE: scripts/x.py <參數>` 的參數部分（就是 args 要寫的）。"""
        try:
            with open(os.path.join(self.agent.tools_dir, f"{tool}.md"), encoding="utf-8") as f:
                body = skill_spec.sections(f.read()).get("語法", "")
        except OSError:
            return []
        return [m.group(1).strip() for m in _SYNTAX.finditer(body)]

    def _syntax(self, tool):
        """交給模型看的 args 寫法：〈語法〉的參數部分，最多 DOMAIN_SYNTAX_LINES 行。"""
        rows = [f"`{row}`" if row else _s("syntax_none") for row in self._syntax_args(tool)]
        return "　".join(dict.fromkeys(rows[:DOMAIN_SYNTAX_LINES])) or "—"

    @staticmethod
    def _anchor(job):
        """提煉長輸出時的「想知道什麼」：這一件事的子目標與項目（附使用者的原話）。"""
        items = [_s("anchor_item", item=x, quote=q) if q else x for x, q in zip(job["items"], job["quotes"])]
        return _s("anchor", goal=job["goal"], items="；".join(items))

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
