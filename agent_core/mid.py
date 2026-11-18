"""新架構的中階（Domain Worker；D10 第 3 步的 3a，照 D3、D5 的中階、D6、D7；〈新架構討論紀錄〉第 5 節）。

一個領域（skills_system/<領域>/SKILLS.md 與它的複合技能）收到使用者的問題（與這一層的子目標）之後：
1. **挑技能**（模型一次）：先寫理解，再寫問題要的是哪幾種（位置、數量、內容），再從領域的複合技能裡選一個；這個領域沒有技能做得到
   是 no_skill，不屬於這個領域是 out_of_domain（中 2，往上交）。程式核對選的在清單裡，而且答得了問題要的每一種（規格的 answers），
   答不了也是 no_skill。
2. **合約**（D6）：模型照技能的參數從原文抽值，每個附抄的原文；程式照參數的種類核對（原文真的在問題裡、值對得上原文），沒過的
   與漏了的必填參數交回修一次。
   沒提到的用預設值；路徑在工作目錄找不到時照規格的 fetch 查一次（剛好一個就自己補，記成「自己補的」；好幾個或沒有就問使用者）；
   必填的沒提到就問使用者（ask）。
3. **排圖**（程式）：〈骨架〉代入參數就是一張決策圖（D3：模型不寫節點）。`{"if": 參數, "args": [...]}` 的參數有值才放（名稱清單一項一組）；
   節點寫 `if` 的，參數沒有值就不排，依賴它的也不排。
4. **執行**：交給低階（agent_core/edg.py）：照圖執行、守門、第 1 級。
5. **第 2 級**（程式）：照收據比對〈回退〉的條件（節點的狀態、收據的欄位、帶入的實例有沒有超過上限），照列的順序取第一個還沒用過的：
   - add：在圖上加節點，交給低階的 replan 接著跑同一個工作（重排只改圖：跑過的不重跑，D7）；
   - ask：問使用者（例如範圍太大：附各子目錄的筆數），回答之後照新的參數重新排圖。
   重排最多 MID_REPLAN_MAX 次，再要重排就熔斷（circuit_break）；加的節點全都跑過＝不收斂，不再重排（D5 中 4）。
6. **報告**（程式）：照收據整理（定義、呼叫、每個檔案的數量、總數，各附 #編號）；用了哪些回退、哪裡沒做完、自己補的參數。
   判斷節點（要看內容才能決定的）與 depends_on（硬性前置的複合技能）第一版的兩個技能用不到，跟用到的複合技能一起做（3b）。

每一次存在 logs/mid_jobs/<編號>/：job.json（選的技能、參數與原文、每一版的圖與節點的狀態、回退、問使用者的問題與回答 asked、結果）、report.md、
events.jsonl、calls.jsonl（挑技能與合約的模型呼叫）。低階的執行（每個節點的嘗試、收據、第 1 級）在 logs/edg_jobs/<edg_job>/。
Web 的拓撲圖（web_app/topology.py）用這兩份。
"""
import collections
import json
import os
import re
import time

from . import edg, prompt_files, skill_spec
from .config import (EDG_JOBS_DIRNAME, MID_CONTRACT_PREDICT, MID_JOBS_DIRNAME, MID_JOBS_KEEP, MID_MODEL, MID_REPLAN_MAX,
                     MID_REPORT_LINES, MID_SELECT_PREDICT, NUM_CTX)
from .jobstore import JobStore
from .schemas import mid_contract_schema, mid_select_schema

TYPES = ("name", "text", "path", "glob", "names")
KINDS = ("位置", "數量", "內容")       # 問題要的是哪幾種（挑技能時模型分類，複合技能的 answers 寫它答得了哪幾種）
STATUS_TEXT = {"done": "做完", "dead_end": "死路（照〈回退〉也沒有可以換的做法）", "circuit_break": f"熔斷（重排超過 {MID_REPLAN_MAX} 次）",
               "no_skill": "這個領域沒有適合的複合技能", "out_of_domain": "不屬於這個領域", "failed": "失敗", "need_user": "要問使用者"}
CANDIDATES_MAX = 10
_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DIRNAME = re.compile(r"^[\w.-]+$")             # 目錄或檔案的名稱（一段路徑；\w 含中文）
_SPLIT = re.compile(r"[、,，;；\s]+")
_ENTRY = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(([^)]+)\)")
_QUOTES = "\"'`「」『』“”‘’"
_REF_GROUPS = (("import", "import"), ("assign", "指定"), ("ref", "其他用到"))


def _i(key, /, **fields):
    """prompts/mid/inputs.md 的一則。"""
    return prompt_files.load("mid/inputs.md", key, **fields)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _empty(v):
    return v is None or v == "" or v == []


# =====================================================================================================================
# 領域與複合技能
# =====================================================================================================================
def load_domain(base_path, tools_dir, name):
    """skills_system/<領域>/SKILLS.md 與它列的複合技能 → {"name", "title", "intro", "skills": {名稱: 規格}, "tools", "problems"}。"""
    out = {"name": name, "title": name, "intro": "", "skills": {}, "tools": [], "problems": []}
    try:
        with open(os.path.join(base_path, name, "SKILLS.md"), encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError:
        out["problems"].append(f"沒有 skills_system/{name}/SKILLS.md")
        return out
    if lines and lines[0].startswith("# "):
        out["title"] = lines[0][2:].strip()
    section, intro, entries = None, [], []
    for ln in lines[1:]:
        if ln.startswith("## "):
            section = ln[3:].strip()
        elif section is None:
            intro.append(ln)
        elif (m := _ENTRY.match(ln)) and section in ("複合技能", "工具"):
            entries.append((section, m.group(1), m.group(2)))
    out["intro"] = "\n".join(intro).strip()
    out["tools"] = [n for s, n, _ in entries if s == "工具"]
    for t in out["tools"]:
        if not os.path.exists(os.path.join(tools_dir, f"{t}.md")):
            out["problems"].append(f"工具 {t} 沒有規格（skills_system/tools/{t}.md）")
    for _, sname, rel in [e for e in entries if e[0] == "複合技能"]:
        try:
            with open(os.path.join(base_path, name, rel), encoding="utf-8") as f:
                text = f.read()
            spec = skill_spec.composite(text)
        except (OSError, ValueError) as e:
            out["problems"].append(f"{sname}：{e}")
            continue
        spec.update(name=sname, text=text)
        out["problems"] += [f"{sname}：{p}" for p in validate_skill(spec, tools_dir, out["tools"])]
        out["skills"][sname] = spec
    if not out["skills"]:
        out["problems"].append("沒有複合技能")
    return out


def _arg_strings(args):
    """參數裡的字串：(字串, 所在的 if 群組的參數或 None)。"""
    for a in args if isinstance(args, list) else []:
        if isinstance(a, str):
            yield a, None
        elif isinstance(a, dict) and "if" in a:
            for x in a.get("args", []):
                yield x, a["if"]


def validate_skill(spec, tools_dir, domain_tools):
    """複合技能的規格寫得對不對 → 問題的清單（空的才能用）。最後用假的參數排一次圖，交給低階的 validate 檢查。"""
    p = []
    meta, topo, params = spec["meta"], spec["topology"], spec["parameters"]
    if meta.get("type") != "Skill":
        p.append("type 要是 Skill")
    p += [f"缺少 {k}" for k in ("title", "description") if not meta.get(k)]
    if not isinstance(topo, dict) or not isinstance(topo.get("depends_on"), list) or not isinstance(topo.get("sub_skills"), list):
        return p + ["topology 要有 depends_on 與 sub_skills（陣列）"]
    if topo["depends_on"]:
        p.append("depends_on（硬性前置的複合技能）第一版還沒接上：這個領域都是唯讀的，目前的技能用不到")
    p += [f"sub_skills 的 {t} 不是這個領域的工具（SKILLS.md 的〈工具〉）" for t in topo["sub_skills"] if t not in domain_tools]
    answers = spec.get("answers")
    if not isinstance(answers, list) or not answers or any(a not in KINDS for a in answers):
        p.append(f"answers 要是 {'、'.join(KINDS)} 組成的陣列（這個技能答得了問題要的哪幾種）")
    if not isinstance(params, list):
        return p + ["parameters 要是陣列"]
    types, always = {}, set()
    for x in params:
        n = x.get("name") if isinstance(x, dict) else None
        if not isinstance(n, str) or not _IDENT.match(n) or n in types:
            p.append(f"參數名稱不合法或重複：{n!r}")
            continue
        types[n] = x.get("type")
        if x.get("type") not in TYPES:
            p.append(f"{n}：type 只能是 {'、'.join(TYPES)}")
        if not x.get("desc"):
            p.append(f"{n}：要寫 desc（給模型看的意思）")
        if x.get("required"):
            always.add(n)
            if not x.get("ask") or "default" in x:
                p.append(f"{n}：必填的參數要寫 ask（沒提到時問使用者什麼），也不能有預設值")
        elif "default" in x:
            always.add(n)
        f = x.get("fetch")
        if f is not None and not (x.get("type") == "path" and isinstance(f, dict) and f.get("tool") in domain_tools
                                  and isinstance(f.get("args"), list) and all(isinstance(a, str) for a in f["args"])
                                  and any("{value}" in a for a in f["args"])):
            p.append(f"{n}：fetch 只用在路徑，寫成 {{\"tool\": 這個領域的工具, \"args\": [含 {{value}} 的參數…]}}")
    nodes = (spec["skeleton"] or {}).get("nodes") if isinstance(spec["skeleton"], dict) else None
    fallbacks = spec["fallbacks"]
    if not isinstance(nodes, list) or not nodes:
        return p + ["〈骨架〉要有 nodes"]
    if not isinstance(fallbacks, list):
        return p + ["〈回退〉要是陣列"]
    adds = [n for fb in fallbacks if isinstance(fb, dict) for n in (fb.get("change") or {}).get("add") or []]
    ids = set()
    for n in list(nodes) + adds:
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(n, dict) or nid in ids:
            p.append(f"節點要是物件、id 不能重複：{nid!r}")
            continue
        ids.add(nid)
        if n.get("kind", "tool") != "tool":
            p.append(f"{nid}：判斷節點第一版還沒接上（跟用到它的複合技能一起做）")
            continue
        if n.get("tool") not in topo["sub_skills"]:
            p.append(f"{nid}：工具 {n.get('tool')} 不在 topology 的 sub_skills")
        if n.get("if") is not None and n["if"] not in types:
            p.append(f"{nid}：if 的參數 {n['if']} 沒有宣告")
        if "report" in n and (not isinstance(n["report"], str) or n.get("tool") not in REPORTERS
                              or (n["tool"] == "code_ast_reader" and "--refs" not in n.get("args", []))):
            p.append(f"{nid}：report 寫報告裡的小標題；能當報告的是 {'、'.join(REPORTERS)}（code_ast_reader 要用 --refs）")
        for a, group in _arg_strings(n.get("args", [])):
            for ref in _PARAM.findall(a):
                if ref not in types:
                    p.append(f"{nid}：參數 {ref} 沒有宣告")
                elif types[ref] == "names" and group != ref:
                    p.append(f"{nid}：名稱清單 {ref} 要放在 {{\"if\": \"{ref}\", \"args\": [...]}} 裡（一項一組）")
                elif ref not in always and ref not in (group, n.get("if")):
                    p.append(f"{nid}：{ref} 可能沒有值，要放在 if 裡（或節點寫 if）")
        for a in n.get("args", []) if isinstance(n.get("args"), list) else []:
            if isinstance(a, dict) and "if" in a and a["if"] not in types:
                p.append(f"{nid}：if 的參數 {a['if']} 沒有宣告")
    fids = set()
    for fb in fallbacks:
        fid = fb.get("id") if isinstance(fb, dict) else None
        if not isinstance(fid, str) or fid in fids:
            p.append(f"回退要有不重複的 id：{fid!r}")
            continue
        fids.add(fid)
        when, change = fb.get("when"), fb.get("change")
        if not isinstance(when, dict) or when.get("node") not in ids or len(when) < 2:
            p.append(f"回退 {fid}：when 要寫 node（骨架或回退加的節點）與至少一個條件")
        elif "capped" in when and not isinstance(when["capped"], bool):
            p.append(f"回退 {fid}：capped 要是 true 或 false")
        if not isinstance(change, dict) or len(change.keys() & {"add", "ask"}) != 1:
            p.append(f"回退 {fid}：change 要是 add（加節點）或 ask（問使用者）其中一個")
        elif "ask" in change and (change["ask"] not in types or change.get("from") not in ids | {None}):
            p.append(f"回退 {fid}：ask 要是宣告過的參數，from 要是節點")
        if not fb.get("say"):
            p.append(f"回退 {fid}：要寫 say（給使用者與報告看的一句話）")
    if p:
        return p
    dummy = {n: (["d"] if t == "names" else "x") for n, t in types.items()}
    problems, _, _ = edg.validate(tools_dir, {"goal": "檢查", "nodes": expand_nodes(nodes, dummy)[0] + expand_nodes(adds, dummy)[0]})
    return [f"排出的圖：{x}" for x in problems]


def _fill(text, params):
    return _PARAM.sub(lambda m: str(params[m.group(1)]), text)


def expand_nodes(nodes, params):
    """骨架（或回退加的節點）代入參數 → (決策圖的節點, 沒有排的節點 id)。節點的 if 參數沒有值就不排，依賴它的也不排。"""
    out, omitted = [], set()
    for n in nodes:
        if (n.get("if") and _empty(params.get(n["if"]))) or any(d in omitted for d in n.get("depends_on", [])):
            omitted.add(n["id"])
            continue
        m = {k: v for k, v in n.items() if k != "if"}
        args = []
        for a in n.get("args", []):
            if isinstance(a, str):
                args.append(_fill(a, params))
            elif "if" in a:
                v = params.get(a["if"])
                for item in ([] if _empty(v) else v if isinstance(v, list) else [v]):
                    local = dict(params, **{a["if"]: item})
                    args += [_fill(x, local) for x in a["args"]]
            else:
                args.append(dict(a))
        m["args"] = args
        if "why" in m:
            m["why"] = _fill(m["why"], params)
        out.append(m)
    return out, omitted


# =====================================================================================================================
# 合約：核對模型抄的原文與值
# =====================================================================================================================
def _norm(s):
    return " ".join(str(s or "").split())


def _unquote(s):
    return _norm(s).strip(_QUOTES).strip()


def verify_param(p, quote, value, source):
    """(值, 交回修的那一則) ：值是 None 表示沒提到或沒過（沒過時第二個是給模型的說明）。名稱清單的值是 list。
    原文要一字不改地在問題或子目標裡；值照種類對原文：名稱與名稱清單要原樣在原文裡；路徑的每一段（/ 分開）是原文裡的名稱
    （原文寫「a 的 b/ 底下」就是 a/b；原文沒有的上層目錄不能補）；文字與檔案名稱的寫法每一段英數字或中文都要在原文裡。"""
    q, v, name = _unquote(quote), _unquote(value), p["name"]
    if not q and not v:
        return None, None
    if not q or q not in _norm(source):
        return None, _i("reject_quote", name=name, quote=q or str(quote))
    t = p["type"]
    if t == "name":
        return (v, None) if _IDENT.match(v) and v in q else (None, _i("reject_name", name=name, value=v, quote=q))
    if t in ("text", "glob"):
        words = re.findall(r"\w+", v)
        miss = [w for w in words if w.lower() not in q.lower()]
        return (v, None) if words and not miss else (None, _i("reject_fragments", name=name, value=v, quote=q, missing="、".join(miss) or v))
    if t == "path":
        pv = (v[2:] if v.startswith("./") else v).rstrip("/") or v
        parts = [x for x in pv.split("/") if x not in ("", "~")]
        bad = [x for x in parts if not _DIRNAME.match(x) or x not in q]
        return (pv, None) if parts and not bad else (None, _i("reject_path", name=name, value=v, quote=q, missing="、".join(bad) or v))
    items = [_unquote(x) for x in _SPLIT.split(v) if _unquote(x)]
    miss = [x for x in items if x not in q or not _DIRNAME.match(x)]
    return (items, None) if items and not miss else (None, _i("reject_names", name=name, missing="、".join(miss) or v, quote=q))


def check_answer(p, answer, cwd):
    """使用者回答的值 → (值, 錯誤)；路徑要在工作目錄找得到。"""
    a = _unquote(answer)
    if not a:
        return None, "沒有回答"
    t = p["type"]
    if t == "name":
        return (a, None) if _IDENT.match(a) else (None, "要是一個名稱（英文字母或底線開頭，只有英數字與底線）")
    if t == "path":
        a = (a[2:] if a.startswith("./") else a).rstrip("/") or a
        return (a, None) if _exists(cwd, a) else (None, f"工作目錄（{cwd}）底下找不到 {a}")
    if t == "names":
        items = [x for x in _SPLIT.split(a) if x]
        return (items, None) if all(_DIRNAME.match(x) for x in items) else (None, "每一項要是一個目錄的名稱，用「、」分開")
    return a, None


def _exists(cwd, path):
    return os.path.exists(os.path.join(cwd or ".", os.path.expanduser(path)))


def _node_key(n):
    return json.dumps([n.get("tool"), n.get("args")], ensure_ascii=False, sort_keys=True)


# =====================================================================================================================
# 模型
# =====================================================================================================================
class ModelCaller:
    """一次模型呼叫：caller(role, system, user, schema, predict, log) → dict 或 None（沒有回覆、不是 JSON）；每次呼叫交給 log 記進 calls.jsonl。"""

    def __init__(self, agent):
        self.agent = agent

    def __call__(self, role, system, user, schema, predict, log):
        model = MID_MODEL or self.agent.model
        t0, raw, err = time.time(), "", None
        try:
            res = self.agent._timed_chat(
                f"mid_{role}", model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                format=schema, options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": predict}, think=False)
            raw = (res["message"]["content"] or "").strip()
        except Exception as e:   # noqa: BLE001  模型呼叫失敗：這一步當成沒有回覆
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


# =====================================================================================================================
# 中階
# =====================================================================================================================
class Worker:
    """一個領域的中階：start(問題, 子目標) 或 resume(編號, approve=…, answer=…) → job（dict，也存成 job.json）。
    model 預設是 ModelCaller（自我測試換成假的）；fixer 交給低階（第 1 級修正的模型，None＝預設）。"""

    def __init__(self, agent, domain="repo_analysis", model=None, fixer=None):
        self.agent = agent
        self.domain_name = domain
        self.store = JobStore(os.path.join(agent.script_dir, "logs", MID_JOBS_DIRNAME))
        self.model = model if model is not None else ModelCaller(agent)
        self.fixer = fixer
        self._receipts = {}

    # ---------------------------------------------------------------- 進入點
    def start(self, question, goal=None):
        jid = self.store.new_id()
        self.store.prune(MID_JOBS_KEEP)
        job = {"id": jid, "status": "running", "created": _now(), "updated": _now(), "cwd": self.agent.current_cwd,
               "domain": self.domain_name, "question": question, "goal": (goal or question).strip(), "selection": None, "skill": None,
               "contract": None, "params": {}, "rejected": [], "auto_filled": [], "fetches": [], "graphs": [], "edg_job": None,
               "fallbacks": [], "applied": [], "added": [], "replans": 0, "need_user": None, "asked": [], "result": None}
        self._note(jid, f"🧭 中階（{self.domain_name}）開始：{question[:80]}")
        domain = self._domain()
        if domain["problems"]:
            return self._finish(job, "failed", note="領域的規格有問題：" + "；".join(domain["problems"]))
        if not self._select(job, domain):
            return job
        self._contract(job, domain["skills"][job["skill"]])
        return self._proceed(job, domain)

    def resume(self, jid, approve=None, answer=None):
        """接回要問人的工作：確認關卡用 approve（True／False），問參數用 answer（使用者回答的值）。"""
        job = self.store.load(jid)
        if not job or job["status"] != "need_user":
            return job
        domain = self._domain()
        if domain["problems"]:
            return self._finish(job, "failed", note="領域的規格有問題：" + "；".join(domain["problems"]))
        need = job["need_user"]
        if need["kind"] == "guard":
            if approve is not None:
                self._answered(job, approve=bool(approve))
            job.update(status="running", need_user=None)
            return self._after(job, domain, self._executor().resume(job["edg_job"], approve))
        p = next(x for x in domain["skills"][job["skill"]]["parameters"] if x["name"] == need["param"])
        value, err = check_answer(p, answer, job["cwd"])
        if err:
            need["error"] = err
            if job.get("asked"):
                job["asked"][-1].setdefault("errors", []).append({"answer": str(answer or ""), "error": err, "time": _now()})
            self.store.save(job)
            return job
        self._answered(job, answer=value)
        job["params"][p["name"]] = {"value": value, "source": "user", "checked": True}
        self._note(jid, f"🧭 使用者回答 {p['name']}＝{value}")
        job.update(status="running", need_user=None)
        if job["graphs"]:                       # 跑過了（回退問的範圍）：照新的參數重新排，之前用過的回退可以再用
            job.update(applied=[], added=[], rebuild={"kind": "user", "param": p["name"], "value": value})
        return self._proceed(job, domain)

    # ---------------------------------------------------------------- 挑技能
    def _select(self, job, domain):
        names = list(domain["skills"])
        entries = "\n".join(_i("skill_entry", name=n, description=s["meta"]["description"], answers="、".join(s["answers"]),
                               when=s["sections"].get("什麼時候用", "").replace("\n", "\n  ")) for n, s in domain["skills"].items())
        parts = [_i("question", question=job["question"])] + ([_i("goal", goal=job["goal"])] if job["goal"] != job["question"] else [])
        parts += [_i("domain", domain=domain["title"], intro=domain["intro"]), _i("skills", skills=entries)]
        out = self.model("select", prompt_files.load("mid/select.md"), "\n\n".join(parts), mid_select_schema(names, KINDS),
                         MID_SELECT_PREDICT, self._log(job["id"]))
        if not out:
            self._finish(job, "failed", note="挑技能的模型沒有回覆，或回覆不是 JSON")
            return False
        skill = str(out.get("skill") or "")
        asks = [a for a in out.get("asks") or [] if a in KINDS]
        job["selection"] = {"understanding": str(out.get("understanding") or ""), "asks": asks, "skill": skill, "reason": str(out.get("reason") or "")}
        if skill in ("none", "out_of_domain"):
            self._finish(job, "no_skill" if skill == "none" else "out_of_domain", note=job["selection"]["reason"])
            return False
        if skill not in names:
            self._finish(job, "failed", note=f"選了清單外的「{skill}」")
            return False
        missing = [a for a in asks if a not in domain["skills"][skill]["answers"]]
        if missing:
            job["selection"]["rejected"] = skill
            self._finish(job, "no_skill", note=f"選了 {skill}，但問題要的「{'、'.join(missing)}」它答不了（它答得了：{'、'.join(domain['skills'][skill]['answers'])}）")
            return False
        job["skill"] = skill
        self._note(job["id"], f"🧭 挑技能：{skill}（{job['selection']['reason'][:80]}）")
        return True

    # ---------------------------------------------------------------- 合約
    def _contract(self, job, spec):
        params, source = spec["parameters"], job["question"] + "\n" + job["goal"]
        out = self._contract_call(job, spec, None, "")
        job["contract"] = {"understanding": str(out.get("understanding") or "")}
        bad = {}
        for p in params:
            cell = out.get(p["name"]) if isinstance(out.get(p["name"]), dict) else {}
            value, why = verify_param(p, cell.get("quote"), cell.get("value"), source)
            if why:
                bad[p["name"]] = why
                job["rejected"].append({"param": p["name"], "round": 1, "quote": cell.get("quote"), "value": cell.get("value"), "why": why})
            elif value is not None:
                job["params"][p["name"]] = {"value": value, "quote": _unquote(cell.get("quote")), "source": "question"}
        for p in params:                        # 漏了的必填參數也交回修一次（原文的核對照舊：問題裡真的沒有，模型就只能留空）
            if p.get("required") and p["name"] not in job["params"] and p["name"] not in bad:
                bad[p["name"]] = _i("reject_missing", name=p["name"])
                job["rejected"].append({"param": p["name"], "round": 1, "quote": "", "value": "", "why": bad[p["name"]]})
        if bad:
            again = self._contract_call(job, spec, list(bad), "\n".join(bad.values()))
            for p in [x for x in params if x["name"] in bad]:
                cell = again.get(p["name"]) if isinstance(again.get(p["name"]), dict) else {}
                value, why = verify_param(p, cell.get("quote"), cell.get("value"), source)
                if why:
                    job["rejected"].append({"param": p["name"], "round": 2, "quote": cell.get("quote"), "value": cell.get("value"), "why": why})
                elif value is not None:
                    job["params"][p["name"]] = {"value": value, "quote": _unquote(cell.get("quote")), "source": "question"}
        self._note(job["id"], "🧭 合約：" + ("；".join(f"{k}＝{v['value']}" for k, v in job["params"].items()) or "原文沒有提到參數")
                   + (f"（{len(job['rejected'])} 個沒過核對）" if job["rejected"] else ""))

    def _contract_call(self, job, spec, only, rejected):
        kinds = {"name": _i("type_name"), "text": _i("type_text"), "path": _i("type_path"), "glob": _i("type_glob"),
                 "names": _i("type_names")}
        rows = []
        for p in spec["parameters"]:
            if only is not None and p["name"] not in only:
                continue
            if p.get("required"):
                rows.append(_i("param_required", name=p["name"], kind=kinds[p["type"]], desc=p["desc"]))
            elif "default" in p:
                rows.append(_i("param_default", name=p["name"], kind=kinds[p["type"]], desc=p["desc"], default=p["default"]))
            else:
                rows.append(_i("param_optional", name=p["name"], kind=kinds[p["type"]], desc=p["desc"]))
        parts = [_i("question", question=job["question"])] + ([_i("goal", goal=job["goal"])] if job["goal"] != job["question"] else [])
        parts += [_i("skill", name=spec["name"], title=spec["meta"]["title"], description=spec["meta"]["description"]),
                  _i("params", params="\n".join(rows))]
        if rejected:
            parts.append(_i("rejected", rejected=rejected))
        out = self.model("contract_fix" if only else "contract", prompt_files.load("mid/contract.md"), "\n\n".join(parts),
                         mid_contract_schema(spec["parameters"], only), MID_CONTRACT_PREDICT, self._log(job["id"]))
        return out or {}

    def _complete(self, job, spec):
        """補齊參數（D6）：預設值；原文的路徑在工作目錄找不到時照 fetch 查一次；必填的沒有就問。回傳要問使用者的事，或 None。"""
        for p in spec["parameters"]:
            cur = job["params"].get(p["name"])
            if cur is None:
                if "default" in p:
                    job["params"][p["name"]] = {"value": p["default"], "source": "default"}
                elif p.get("required"):
                    return {"kind": "param", "param": p["name"], "question": p["ask"], "candidates": []}
                continue
            if p["type"] != "path" or cur.get("checked"):
                continue
            if _exists(job["cwd"], cur["value"]):
                cur["checked"] = True
                continue
            if not p.get("fetch"):
                return {"kind": "param", "param": p["name"], "question": f"工作目錄底下找不到「{cur['value']}」：要查哪裡？", "candidates": []}
            exact, found = self._fetch(job, p, cur["value"])
            if len(exact) == 1:
                job["auto_filled"].append({"param": p["name"], "given": cur["value"], "value": exact[0], "edg_job": job["fetches"][-1]["edg_job"]})
                self._note(job["id"], f"🧭 自己補的：{p['name']}「{cur['value']}」→ {exact[0]}")
                cur.update(value=exact[0], source="fetch", checked=True)
                continue
            cands = (exact or found)[:CANDIDATES_MAX]
            q = (f"「{cur['value']}」有好幾個，要哪一個？" if cands else f"工作目錄底下找不到「{cur['value']}」：要查哪裡？")
            return {"kind": "param", "param": p["name"], "question": q, "candidates": cands}
        return None

    def _fetch(self, job, p, value):
        """照 fetch 查一次 → (路徑結尾跟原文一樣的候選, 全部找到的)；都是相對於工作目錄的路徑。"""
        f = p["fetch"]
        args = [a.replace("{value}", os.path.basename(value.rstrip("/")) or value) for a in f["args"]]
        ej = self._executor().start({"goal": f"找「{value}」在工作目錄的哪裡（{p['desc']}）",
                                     "nodes": [{"id": "fetch", "tool": f["tool"], "args": args, "expect": ["pass", "empty"]}]})
        found = []
        for inst in ej["nodes"].get("fetch", {}).get("instances", []):
            r = self._receipt(ej, (inst.get("attempts") or [{}])[-1]) or {}
            found += [self._rel(job, it["path"]) for it in r.get("items") or [] if it.get("path")]
        exact = [x for x in found if x == value or x.endswith("/" + value)]
        job["fetches"].append({"param": p["name"], "given": value, "edg_job": ej["id"], "status": ej["status"], "found": len(found),
                               "exact": exact[:CANDIDATES_MAX]})
        return exact, found

    # ---------------------------------------------------------------- 排圖、執行、第 2 級
    def _proceed(self, job, domain):
        spec = domain["skills"][job["skill"]]
        need = self._complete(job, spec)
        if need:
            return self._wait(job, need)
        if job["graphs"] and "rebuild" not in job:
            return job
        cause = job.pop("rebuild", None)
        values = {k: v["value"] for k, v in job["params"].items()}
        nodes, _ = expand_nodes(spec["skeleton"]["nodes"], values)
        if not nodes:
            gates = [n["if"] for n in spec["skeleton"]["nodes"] if n.get("if")]
            ps = [p for p in spec["parameters"] if p["name"] in gates]
            return self._wait(job, {"kind": "param", "param": ps[0]["name"], "candidates": [],
                                    "question": "要找什麼？" + "、".join(f"{p['name']}（{p['desc']}）" for p in ps) + " 至少要有一個"})
        if cause:
            if job["replans"] >= MID_REPLAN_MAX:
                return self._finish(job, "circuit_break", note=f"照使用者的回答重排，已經重排 {job['replans']} 次")
            job["replans"] += 1
        return self._run(job, domain, {"goal": job["goal"], "nodes": nodes}, cause)

    def _run(self, job, domain, graph, cause):
        job["graphs"].append({"version": len(job["graphs"]) + 1, "time": _now(), "cause": cause, "graph": graph, "nodes": {}, "status": None})
        ex = self._executor()
        ej = ex.replan(job["edg_job"], graph) if job["edg_job"] else ex.start(graph)
        job["edg_job"] = ej["id"]
        self._note(job["id"], f"🧭 第 {len(job['graphs'])} 版的圖：{len(graph['nodes'])} 個節點 → 低階 {ej['id']}：{ej['status']}")
        return self._after(job, domain, ej)

    def _after(self, job, domain, ej):
        spec = domain["skills"][job["skill"]]
        self._snapshot(job, ej)
        if ej["status"] == "need_user":
            return self._wait(job, {"kind": "guard", "edg_job": ej["id"], "node": ej["need_user"]["node"], "question": ej["need_user"]["text"]})
        if ej["status"] == "invalid":
            return self._finish(job, "failed", ej, note="排出的圖沒有通過檢查：" + "；".join(ej["problems"]))
        values = {k: v["value"] for k, v in job["params"].items()}
        for fb in spec["fallbacks"]:
            if fb["id"] in job["applied"] or not self._when(fb["when"], ej):
                continue
            job["applied"].append(fb["id"])
            entry = {"fallback": fb["id"], "say": fb["say"], "when": fb["when"], "change": fb["change"], "version": len(job["graphs"]), "time": _now()}
            job["fallbacks"].append(entry)
            if "ask" in fb["change"]:
                entry["result"] = "ask"
                self._note(job["id"], f"🔁 第 2 級：{fb['id']}，問使用者 {fb['change']['ask']}")
                return self._wait(job, {"kind": "param", "param": fb["change"]["ask"], "question": fb["say"], "fallback": fb["id"],
                                        "candidates": self._subdirs(job, ej, fb["change"].get("from"))})
            extra, _ = expand_nodes(fb["change"]["add"], values)
            ran = {_node_key(n) for g in job["graphs"] for n in g["graph"]["nodes"]}
            if all(_node_key(n) in ran for n in extra):
                entry["result"] = "no_new_nodes"
                self._note(job["id"], f"🔁 第 2 級：{fb['id']} 排出來的節點都跑過了（不收斂），不重排")
                continue
            if job["replans"] >= MID_REPLAN_MAX:
                entry["result"] = "circuit_break"
                return self._finish(job, "circuit_break", ej, note=f"還要套用 {fb['id']}，但已經重排 {job['replans']} 次")
            job["replans"] += 1
            entry.update(result="replanned", added=[n["id"] for n in extra])
            job["added"].append(fb["id"])
            self._note(job["id"], f"🔁 第 2 級：{fb['id']}（{fb['say'][:60]}），加了 {'、'.join(entry['added'])}")
            graph = {"goal": job["goal"], "nodes": job["graphs"][-1]["graph"]["nodes"] + extra}
            return self._run(job, domain, graph, {"kind": "fallback", "fallback": fb["id"], "say": fb["say"], "added": entry["added"]})
        return self._finish(job, "done" if ej["status"] == "done" else "dead_end", ej)

    def _when(self, when, ej):
        """回退的條件：node 的狀態（state）、帶入的實例超過上限（capped），其他的鍵比對那個節點某一個實例最後一次嘗試的收據。"""
        st = ej["nodes"].get(when["node"])
        if not st:
            return False
        if "state" in when and st["state"] != when["state"]:
            return False
        if "capped" in when:
            each = st.get("each") or {}
            if (each.get("instances", 0) > each.get("ran", 0)) != when["capped"]:
                return False
        keys = {k: v for k, v in when.items() if k not in ("node", "state", "capped")}
        if not keys:
            return True
        for inst in st.get("instances", []):
            r = self._receipt(ej, (inst.get("attempts") or [{}])[-1])
            if r and all(r.get(k) == v for k, v in keys.items()):
                return True
        return False

    def _snapshot(self, job, ej):
        """這一版的圖跑完時每個節點的狀態（Web 的拓撲圖照版本畫：重排之後也看得到之前那一版）。"""
        nodes = {}
        for nid, st in ej["nodes"].items():
            insts = st.get("instances", [])
            nodes[nid] = {"state": st["state"], "reason": st.get("reason", ""), "instances": len(insts), "each": st.get("each"),
                          "results": [a["result_id"] for i in insts for a in (i.get("attempts") or [])[-1:] if a.get("result_id")],
                          "fixed": any(i.get("fixed") for i in insts)}
        job["graphs"][-1].update(nodes=nodes, status=ej["status"])

    def _subdirs(self, job, ej, nid):
        """問使用者縮小範圍時的候選：那個節點（search_text）收據裡每個檔案的筆數，照搜尋起點底下的第一層子目錄加總，多的在前。"""
        counts = collections.Counter()
        for inst in (ej["nodes"].get(nid) or {}).get("instances", []):
            r = self._receipt(ej, (inst.get("attempts") or [{}])[-1]) or {}
            roots = r.get("paths") or [job["cwd"]]
            for path, n in (r.get("per_file") or {}).items():
                root = next((x for x in roots if path.startswith(x.rstrip("/") + "/")), None)
                if root is None:
                    continue
                first = os.path.relpath(path, root).split(os.sep)[0]
                counts[self._rel(job, os.path.join(root, first))] += n
        return [f"{p}（{n} 筆）" for p, n in counts.most_common(CANDIDATES_MAX)]

    # ---------------------------------------------------------------- 結束
    def _wait(self, job, need):
        job.setdefault("asked", []).append(dict(need, time=_now(), version=len(job["graphs"])))
        job.update(status="need_user", need_user=need, updated=_now())
        self.store.save(job)
        self._note(job["id"], f"🧭 要問使用者：{need['question'][:100]}")
        return job

    @staticmethod
    def _answered(job, **fields):
        """問使用者的紀錄（asked 的最後一筆）記下回答：確認關卡的 approve、參數的 answer（Web 的拓撲圖看得到問了什麼、回答什麼）。"""
        if job.get("asked"):
            job["asked"][-1].update(fields, answered=_now())

    def _finish(self, job, status, ej=None, note=""):
        job.update(status=status, need_user=None, updated=_now())
        report = self._report(job, ej, note)
        self.store.write(job["id"], "report.md", report)
        sources = sorted({r for g in job["graphs"][-1:] for st in g["nodes"].values() for r in st["results"]})
        job["result"] = {"status": status, "note": note, "report": report, "sources": sources, "auto_filled": job["auto_filled"]}
        self.store.save(job)
        self._note(job["id"], f"🧭 中階結束：{STATUS_TEXT[status]}" + (f"（{note[:100]}）" if note else ""))
        return job

    def _report(self, job, ej, note):
        lines = [f"# 中階的結果：{STATUS_TEXT[job['status']]}", f"- 問題：{job['question']}"]
        if job["skill"]:
            lines.append(f"- 複合技能：{job['skill']}")
        if job["params"]:
            lines.append("- 參數：" + "；".join(f"{k}＝{self._show(v['value'])}（{self._source(v)}）" for k, v in job["params"].items()))
        lines += [f"- 自己補的：{a['param']}＝{a['value']}（原文寫「{a['given']}」，查到剛好一個）" for a in job["auto_filled"]]
        if note:
            lines.append(f"- 說明：{note}")
        if ej is None or not job["graphs"]:
            return "\n".join(lines)
        values = {k: v["value"] for k, v in job["params"].items()}
        graph = job["graphs"][-1]["graph"]
        for n in graph["nodes"]:
            if "report" not in n or n["id"] not in ej["nodes"]:
                continue
            body = REPORTERS[n["tool"]](self, job, ej, n, values)
            ids = job["graphs"][-1]["nodes"].get(n["id"], {}).get("results") or []
            lines += ["", f"## {n['report']}"] + body + ([f"- 出處：{'、'.join(f'#{r}' for r in ids)}"] if ids else [])
        if job["fallbacks"]:
            result = {"replanned": "重排", "no_new_nodes": "排出來的節點都跑過了，沒有重排", "ask": "問使用者", "circuit_break": "熔斷"}
            lines += ["", "## 第 2 級（回退）"] + [f"- {f['fallback']}：{f['say']}（{result.get(f.get('result'), '')}）" for f in job["fallbacks"]]
        stops = [(nid, st) for nid, st in ej["nodes"].items() if st["state"] in edg.BAD]
        if stops:
            lines += ["", "## 沒有做完的節點"] + [f"- {nid}：{st['state']}（{st.get('reason', '')}）" for nid, st in stops]
        return "\n".join(lines)

    @staticmethod
    def _show(v):
        return "、".join(v) if isinstance(v, list) else str(v)

    @staticmethod
    def _source(v):
        return {"question": f"原文「{v.get('quote', '')}」", "default": "預設", "fetch": "自己查到的", "user": "使用者回答"}.get(v["source"], v["source"])

    # ---------------------------------------------------------------- 報告：每一種工具怎麼整理
    def _instances(self, ej, nid):
        """節點每個實例：(實例, 最後一次嘗試, 收據或 None)。"""
        out = []
        for inst in (ej["nodes"].get(nid) or {}).get("instances", []):
            a = (inst.get("attempts") or [{}])[-1]
            out.append((inst, a, self._receipt(ej, a)))
        return out

    def _cap(self, rows, ids):
        if len(rows) <= MID_REPORT_LINES:
            return rows
        more = len(rows) - MID_REPORT_LINES
        return rows[:MID_REPORT_LINES] + [f"    - 還有 {more} 處沒有列（見 {'、'.join(f'#{i}' for i in ids) or '收據'}）"]

    def _render_refs(self, job, ej, node, values):
        """code_ast_reader --refs（一個檔案一個實例）：定義、呼叫（每個檔案幾次、總共幾次、每一處）、import、指定、其他用到；AST 沒跑成的檔案照搜尋命中的行。"""
        items, failed, ids, mentioned = [], [], [], []
        for inst, a, r in self._instances(ej, node["id"]):
            if a.get("result_id"):
                ids.append(a["result_id"])
            if inst["state"] == "done" and r and r.get("status") in ("pass", "empty"):
                items += r.get("items") or []
                if r["status"] == "empty":
                    mentioned.append(inst["args"][0])
            else:
                failed.append((inst["args"][0], inst.get("reason", "")))
        rel = lambda p: self._rel(job, p)   # noqa: E731
        where = lambda i: f"在 {i['scope']}" if i.get("scope") else "模組層"   # noqa: E731
        defs = [i for i in items if i["kind"] in ("def", "class")]
        calls = [i for i in items if i["kind"] == "call"]
        out = [f"- 名稱：{values.get('name', '')}（AST：註解與字串裡提到的不算，import 不算呼叫）",
               f"- 定義（{len(defs)}）：" + ("" if defs else "沒有")]
        out += [f"  - {rel(d['path'])}:{d['line']}　{d['kind']} {d.get('qualname') or d['name']}"
                + (f"（類別 {d['in_class']} 的方法）" if d.get("in_class") else "") + f"，行 {d.get('start', d['line'])}-{d.get('end', d['line'])}"
                for d in defs]
        per = collections.Counter(rel(c["path"]) for c in calls)
        out.append(f"- 呼叫：總共 {len(calls)} 次（{len(per)} 個檔案）")
        if calls:
            out.append("  - 每個檔案：")
            out += [f"    - {p}：{n} 次" for p, n in sorted(per.items())]
            out.append("  - 每一處：")
            out += self._cap([f"    - {rel(c['path'])}:{c['line']}（{where(c)}）：{c['text']}" for c in calls], ids)
        for kind, label in _REF_GROUPS:
            group = [i for i in items if i["kind"] == kind]
            if group:
                out.append(f"- {label}（{len(group)}）：")
                out += self._cap([f"    - {rel(i['path'])}:{i['line']}（{where(i)}）：{i['text']}" for i in group], ids)
        if mentioned:
            out.append(f"- 只在註解或字串裡提到、程式裡沒有用到的檔案（{len(mentioned)}）：" + "、".join(rel(p) for p in mentioned))
        if failed:
            src = next((a["from"] for a in node.get("args", []) if isinstance(a, dict)), None)
            hits = collections.defaultdict(list)
            for _, _, r in self._instances(ej, src) if src else []:
                for it in (r or {}).get("items") or []:
                    if it.get("line"):
                        hits[it["path"]].append(str(it["line"]))
            out.append(f"- AST 沒有分類的檔案（{len(failed)}）：")
            out += [f"    - {rel(p)}：{why}" + (f"；搜尋命中的行：{'、'.join(hits[p][:30])}" if hits.get(p) else "") for p, why in failed]
        each = (ej["nodes"].get(node["id"]) or {}).get("each") or {}
        if each.get("instances", 0) > each.get("ran", 0):
            out.append(f"- 還有 {each['instances'] - each['ran']} 個檔案沒有看（一次最多 {each['ran']} 個）")
        return out

    def _render_hits(self, job, ej, node, values):
        """search_text：範圍、每個檔案的筆數（收據記全部的檔案）、總共幾筆；逾時沒搜完要寫。"""
        out = []
        for inst, a, r in self._instances(ej, node["id"]):
            if not r or r.get("status") == "error":
                out.append(f"- 沒有搜成：{inst.get('reason', '')}")
                continue
            opts = r.get("options") or {}
            scope = "、".join(self._rel(job, p) for p in r.get("paths") or []) or "."
            out.append(f"- 搜尋「{r.get('pattern')}」，範圍：{scope}" + (f"；只看 {'、'.join(opts['include'])}" if opts.get("include") else "")
                       + (f"；不含 {'、'.join(opts['exclude_dir'])}" if opts.get("exclude_dir") else "") + ("；整個字" if opts.get("word") else ""))
            per = r.get("per_file") or {}
            if not per:
                out.append("- 沒有任何一行提到（0 筆）")
            else:
                out.append(f"- 每個檔案（{len(per)} 個）：")
                out += self._cap([f"    - {self._rel(job, p)}：{n} 筆" for p, n in sorted(per.items())], [a.get("result_id")])
                out.append(f"- 總共 {sum(per.values())} 筆（{len(per)} 個檔案）")
            if r.get("timed_out"):
                out.append("- 逾時沒有搜完：上面的數字不是全部")
        return out

    def _render_files(self, job, ej, node, values):
        """find_file：名稱符合的檔案有幾個（不含的子目錄由程式從收據扣掉，寫明扣了幾個）。"""
        out, skip = [], set(values.get("exclude") or [])
        for inst, a, r in self._instances(ej, node["id"]):
            if not r or r.get("status") == "error":
                out.append(f"- 沒有找成：{inst.get('reason', '')}")
                continue
            files = [self._rel(job, it["path"]) for it in r.get("items") or [] if it.get("kind") == "file"]
            kept = [f for f in files if not skip & set(f.split("/")[:-1])]
            out.append(f"- 名稱符合「{r.get('keyword')}」的檔案：{len(kept)} 個（從 {self._rel(job, r.get('root') or '.')} 開始找）"
                       + (f"；不含 {'、'.join(sorted(skip))} 裡的 {len(files) - len(kept)} 個" if len(kept) != len(files) else ""))
            out += self._cap([f"    - {f}" for f in kept], [a.get("result_id")])
            if r.get("truncated"):
                out.append("- 收據不完整（逾時或超過上限）：上面的數字不是全部")
        return out

    # ---------------------------------------------------------------- 小工具
    def _domain(self):
        return load_domain(self.agent.base_path, self.agent.tools_dir, self.domain_name)

    def _executor(self):
        return edg.Executor(self.agent, fixer=self.fixer)

    def _log(self, jid):
        return lambda rec: self.store.append(jid, "calls.jsonl", rec)

    def _rel(self, job, path):
        cwd = job["cwd"] or "."
        ap = os.path.abspath(os.path.join(cwd, path))
        return os.path.relpath(ap, cwd) if ap == cwd or ap.startswith(cwd.rstrip("/") + "/") else ap

    def _receipt(self, ej, attempt):
        rel = (attempt or {}).get("receipt_file")
        if not rel:
            return None
        path = os.path.join(self.agent.script_dir, "logs", EDG_JOBS_DIRNAME, ej["id"], rel)
        if path not in self._receipts:
            try:
                with open(path, encoding="utf-8") as f:
                    self._receipts[path] = json.load(f)
            except (OSError, ValueError):
                return None
        return self._receipts[path]

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


REPORTERS = {"code_ast_reader": Worker._render_refs, "search_text": Worker._render_hits, "find_file": Worker._render_files}
