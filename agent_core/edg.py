"""新架構的低階執行器（EDG Executor；D10 第 2 步，照 D3、D4、D5 的低階、D7 的中→低與低→中；〈設計筆記〉2.29）。

中階排好的決策圖（JSON）交給這裡，程式照圖一個一個執行工具節點：
1. **檢查圖**（validate）：id、依賴、沒有循環、工具存在而且寫收據、參數是字串或「從前一個節點的收據帶入」、帶入的欄位是那個工具收據的
   項目、判斷節點不被依賴（判斷之後的部分由中階接著排）。沒過就不執行（狀態 invalid，問題列在 problems）。
2. **執行前檢查參數**：用腳本自己的 parse_args（純函式，確認關卡也這樣讀參數），不花模型呼叫；會改變狀態的經過確認關卡
   （guard_check；要確認時停下來，need_user，resume 接回同一個節點）。
3. **執行**：走主對話同一條路（dispatch.run_script）：存檔、#編號、收據、軌跡都一樣。帶入的參數一項一個實例（最多 EDG_EACH_MAX 個）；
   同一個工具＋同樣的參數在同一張圖裡只跑一次。
4. **守門**：照收據判斷——狀態是節點的 expect（預設 pass；「0 筆也算答案」寫 ["pass", "empty"]）、要完整（complete）時 truncated 不能為真。
   成功但不合預期是 unexpected（中 1：結果沒有用），交回中階換做法。
5. **第 1 級**：參數錯（args）與逾時（timeout）每個實例修一次——交給修正的模型（只給工具規格、錯誤、子目標；D5），程式核對新的參數
   不一樣、過得了 parse_args、逾時只用規格 narrow 列出的縮小方式、參數錯的修正不能把範圍（narrow 標 inside 的路徑）換成上層，
   才重跑一次；修完還是錯就往上報。環境（env）、腳本的錯（parse）不修。找不到路徑而相近的路徑（收據的 near）有好幾個時也不修：
   要哪一個是上一層的決定（第 1 級曾經挑第一個、跑到別的專案的同名目錄），候選附在原因裡往上報。
6. **往上交**（低 → 中）：每個節點的狀態、每次嘗試的收據摘要與 #編號、修正的紀錄；停下來的原因（stops）、等中階判斷的節點（judgments）。
7. **重排**（replan，中階的第 2 級用）：照新的圖接著跑同一個工作——定義沒變、依賴也沒重跑的節點保留狀態（不重跑）；新的、改了的重新跑；
   圖上拿掉的與重跑的節點，原本的狀態記在 replans（收據檔都還在）。同一個工具＋同樣的參數之前跑過的，直接用之前的收據（D5 中 4）。

每一次執行存在 logs/edg_jobs/<編號>/：job.json（圖、每個節點與實例的狀態、嘗試、修正）、receipts/（每次嘗試的收據全文；重排之後重跑的檔名加上第幾版）、
events.jsonl（進度）、calls.jsonl（修正的模型呼叫）。確認關卡的決定記在實例的 decisions。Web 的拓撲圖（web_app/topology.py）用 job.json。
"""
import importlib
import json
import os
import re
import shlex
import time

from . import prompt_files, skill_spec
from .config import EDG_EACH_MAX, EDG_FIX_PREDICT, EDG_JOBS_DIRNAME, EDG_JOBS_KEEP, EDG_MODEL, NUM_CTX
from .jobstore import JobStore
from .schemas import EDG_FIX_SCHEMA

STATUSES = ("pass", "empty")              # expect 可以寫的收據狀態
FIXABLE = ("args", "timeout")             # 第 1 級修的錯誤種類（env、parse 往上報）
BAD = ("failed", "unexpected", "blocked", "denied")
NODE_FINAL = BAD + ("done", "judgment")
INSTANCE_FINAL = ("done", "unexpected", "failed", "denied")
ERROR_TEXT_MAX = 3000                     # 交給修正的錯誤原文最多幾個字
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_TOOL = re.compile(r"^[A-Za-z0-9_]+$")


def _i(key, /, **fields):
    """prompts/edg/inputs.md 的一則。"""
    return prompt_files.load("edg/inputs.md", key, **fields)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# =====================================================================================================================
# 工具規格與腳本的參數解析
# =====================================================================================================================
def load_spec(tools_dir, tool):
    """{"text", "contract", "script"}；沒有規格回 None；給程式看的欄位 JSON 寫錯時 contract 是 {"error": …}。"""
    try:
        with open(os.path.join(tools_dir, f"{tool}.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    try:
        contract = skill_spec.contract(text)
    except ValueError as e:
        contract = {"error": str(e)}
    return {"text": text, "contract": contract, "script": skill_spec.script(text, tool)}


def _parser(script):
    """腳本的參數解析（parse_args：純函式，回傳的最後一個值是錯誤）；沒有就回 None。"""
    try:
        mod = importlib.import_module(f"skills_system.scripts.{script[:-3]}")
    except Exception:   # noqa: BLE001  載入不了：當成沒有參數解析（validate 已確認腳本存在；執行時腳本自己會報錯）
        return None
    return getattr(mod, "parse_args", None)


def parse(script, args):
    """(解析的結果, 錯誤的文字)：照腳本自己的 parse_args；沒有 parse_args 回 (None, None)（不能事先檢查）。"""
    fn = _parser(script)
    if fn is None:
        return None, None
    try:
        out = fn(list(args))
    except Exception as e:   # noqa: BLE001  解析本身丟例外：當成參數錯（照實寫出例外）
        return None, f"[ERROR] 參數解析失敗：{type(e).__name__}: {e}"
    if not isinstance(out, tuple) or not out:
        return out, None
    return (out[0] if len(out) == 2 else out[:-1]), out[-1] or None


def _paths(value):
    return [value] if isinstance(value, str) else [v for v in (value or []) if isinstance(v, str)]


def _inside(old, new, cwd):
    """新的路徑每一個都在原本某個路徑裡面，而且至少一個比原本的窄。"""
    def real(p):
        return os.path.realpath(os.path.join(cwd, os.path.expanduser(p)))
    olds, news = [real(p) for p in _paths(old) or ["."]], [real(p) for p in _paths(new)]
    if not news:
        return False
    for n in news:
        if not any(os.path.commonpath([o, n]) == o for o in olds):
            return False
    return set(news) != set(olds)


def _added(old, new):
    old, new = list(old or []), list(new or [])
    return len(new) > len(old) and all(x in new for x in old)


def widened(script, rules, old_args, new_args, cwd):
    """參數錯的修正把範圍換成原本路徑的上層（範圍放大）→ 原因；沒有回 None。範圍＝規格 narrow 標 inside 的鍵（逾時只能往裡面縮的那幾個）：
    第 1 級只改字面參數，範圍要放大是中階的決定（例：關鍵字含空白被拆開時，把路徑換成整個工作目錄）。原本的參數解析不了時不核對。"""
    keys = [k for k, r in (rules or {}).items() if r.get("rule") == "inside"]
    po, _ = parse(script, old_args)
    pn, _ = parse(script, new_args)
    if not keys or not isinstance(po, dict) or not isinstance(pn, dict):
        return None

    def real(p):
        return os.path.realpath(os.path.join(cwd, os.path.expanduser(p)))
    for k in keys:
        olds = [real(p) for p in _paths(po.get(k)) or ["."]]
        for n in (real(p) for p in _paths(pn.get(k)) or ["."]):
            wider = [o for o in olds if o != n and os.path.commonpath([o, n]) == n]
            if wider:
                return f"修正把{(rules[k].get('arg') or k)}換成原本路徑的上層（{n} 包含 {wider[0]}），範圍放大要交回中階決定"
    return None


def narrowed(script, old_args, new_args, rules, cwd):
    """(True, "") 或 (False, 原因)：新的參數只照規格 narrow 列的方式縮小（parse_args 的結果只有這些鍵變了，而且照規則變）。"""
    po, _ = parse(script, old_args)
    pn, _ = parse(script, new_args)
    if not isinstance(po, dict) or not isinstance(pn, dict):
        return False, "這個工具的參數解析不是 dict，核對不了縮小的方式"
    changed = sorted(k for k in set(po) | set(pn) if k != "notes" and po.get(k) != pn.get(k))
    if not changed:
        return False, "參數解析的結果沒有變"
    for k in changed:
        rule = (rules.get(k) or {}).get("rule")
        if rule == "inside" and _inside(po.get(k), pn.get(k), cwd):
            continue
        if rule == "added" and _added(po.get(k), pn.get(k)):
            continue
        return False, f"改了 {k}，不是規格列出的縮小方式（可以動的：{'、'.join(rules)}）"
    return True, ""


# =====================================================================================================================
# 檢查圖
# =====================================================================================================================
def _topo(by_id):
    """依賴的先後（Kahn）；有循環時回 (None, 循環裡的節點)。"""
    deps = {nid: [d for d in n.get("depends_on", []) if d in by_id] for nid, n in by_id.items()}
    order, done = [], set()
    pending = list(by_id)
    while pending:
        ready = [nid for nid in pending if all(d in done for d in deps[nid])]
        if not ready:
            return None, pending
        for nid in ready:
            order.append(nid)
            done.add(nid)
        pending = [nid for nid in pending if nid not in done]
    return order, []


def _definition(n):
    """節點的定義（重排時比對有沒有改）：工具、參數、依賴、預期、要完整、判斷節點的目標。"""
    return json.dumps({k: n.get(k) for k in ("kind", "tool", "args", "depends_on", "expect", "complete", "goal")}, ensure_ascii=False, sort_keys=True)


def _binding(a):
    return isinstance(a, dict) and set(a) == {"from", "field"} and all(isinstance(v, str) for v in a.values())


def validate(tools_dir, graph):
    """(問題的清單, {工具: 規格}, 執行的順序)。問題是空的才能執行。"""
    if not isinstance(graph, dict):
        return ["圖要是 JSON 物件"], {}, []
    problems = []
    if not str(graph.get("goal") or "").strip():
        problems.append("缺少 goal（子目標）")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return problems + ["nodes 要是非空的陣列"], {}, []
    by_id = {}
    for i, n in enumerate(nodes, 1):
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(nid, str) or not _ID.match(nid):
            problems.append(f"第 {i} 個節點的 id 不合法（英文字母開頭，只有英數字與底線）：{nid!r}")
        elif nid in by_id:
            problems.append(f"id 重複：{nid}")
        else:
            by_id[nid] = n
    specs = {}
    for nid, n in by_id.items():
        deps = n.get("depends_on", [])
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            problems.append(f"{nid}：depends_on 要是節點 id 的陣列")
            continue
        for d in deps:
            if d not in by_id or d == nid:
                problems.append(f"{nid}：depends_on 的 {d} 不存在")
            elif by_id[d].get("kind", "tool") == "judgment":
                problems.append(f"{nid}：不能依賴判斷節點 {d}（判斷之後的部分由中階看了結果再排）")
        kind = n.get("kind", "tool")
        if kind == "judgment":
            if not str(n.get("goal") or "").strip():
                problems.append(f"{nid}：判斷節點要寫 goal（要判斷什麼）")
            if not deps:
                problems.append(f"{nid}：判斷節點要有 depends_on（要看哪些節點的收據）")
            continue
        if kind != "tool":
            problems.append(f"{nid}：kind 只能是 tool 或 judgment")
            continue
        tool = n.get("tool")
        spec = load_spec(tools_dir, tool) if isinstance(tool, str) and _TOOL.match(tool) else None
        if spec is None:
            problems.append(f"{nid}：沒有 {tool!r} 這個工具（skills_system/tools/ 沒有它的規格）")
            continue
        if "error" in spec["contract"]:
            problems.append(f"{nid}：{tool} 的規格裡給程式看的欄位寫錯了：{spec['contract']['error']}")
            continue
        if "receipt" not in spec["contract"] or not spec["script"]:
            problems.append(f"{nid}：{tool} 不寫收據，不能當工具節點（程式要照收據守門）")
            continue
        specs[tool] = spec
        args = n.get("args", [])
        if not isinstance(args, list):
            problems.append(f"{nid}：args 要是陣列")
            continue
        sources = set()
        for a in args:
            if isinstance(a, str):
                continue
            if not _binding(a):
                problems.append(f"{nid}：參數只能是字串，或 {{\"from\": 節點, \"field\": 收據項目的鍵}}：{a!r}")
                continue
            sources.add(a["from"])
            if a["from"] not in deps:
                problems.append(f"{nid}：參數從 {a['from']} 帶入，depends_on 要有 {a['from']}")
        if len(sources) > 1:
            problems.append(f"{nid}：一個節點只能從一個節點帶入參數（收到 {'、'.join(sorted(sources))}）")
        expect = n.get("expect", ["pass"])
        if not isinstance(expect, list) or not expect or any(e not in STATUSES for e in expect):
            problems.append(f"{nid}：expect 只能是 pass、empty 組成的陣列")
        if not isinstance(n.get("complete", False), bool):
            problems.append(f"{nid}：complete 要是 true 或 false")
    for nid, n in by_id.items():                     # 帶入的欄位要是來源工具收據的項目
        for a in n.get("args", []) if isinstance(n.get("args", []), list) else []:
            src = by_id.get(a["from"]) if _binding(a) else None
            if src and src.get("tool") in specs:
                keys = [k.rstrip("?") for k in specs[src["tool"]]["contract"]["receipt"].get("items", [])]
                if a["field"] not in keys:
                    problems.append(f"{nid}：{src['tool']} 的收據項目沒有 {a['field']}（有：{'、'.join(keys) or '沒有項目'}）")
    order, cycle = _topo(by_id)
    if order is None:
        problems.append(f"depends_on 有循環：{'、'.join(cycle)}")
    return problems, specs, order or []


# =====================================================================================================================
# 第 1 級修正的模型
# =====================================================================================================================
def fix_message(req):
    """交給修正的 user 訊息：子目標、這一步要做什麼、工具與規格、這一次的參數、錯誤、逾時的縮小方式。"""
    parts = [_i("goal", goal=req["goal"])]
    if req.get("why"):
        parts.append(_i("why", why=req["why"]))
    parts.append(_i("tool", tool=req["tool"], spec=req["spec"].strip()))
    parts.append(_i("args", args=json.dumps(req["args"], ensure_ascii=False)))
    kind = _i("kind_args") if req["kind"] == "args" else _i("kind_timeout")
    parts.append(_i("error_pre" if req["stage"] == "pre" else "error_run", kind=kind, error=req["error"].strip()))
    if req.get("narrow"):
        rules = "\n".join(_i("narrow_inside", arg=r.get("arg") or k) if r["rule"] == "inside" else _i("narrow_added", arg=r.get("arg") or k)
                          for k, r in req["narrow"].items())
        parts.append(_i("narrow", rules=rules))
    return "\n\n".join(parts)


class ModelFixer:
    """修正一次：fixer(req, log) → {"reason", "fixable", "args"} 或 None（沒有回覆、不是 JSON）；每次呼叫交給 log 記進 calls.jsonl。"""

    def __init__(self, agent):
        self.agent = agent

    def __call__(self, req, log):
        system, user = prompt_files.load("edg/fix.md"), fix_message(req)
        model = EDG_MODEL or self.agent.model
        t0, raw, err = time.time(), "", None
        try:
            res = self.agent._timed_chat(
                "edg_fix", perf={"job": req.get("job"), "node": req.get("node")}, model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                format=EDG_FIX_SCHEMA, options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": EDG_FIX_PREDICT}, think=False)
            raw = (res["message"]["content"] or "").strip()
        except Exception as e:   # noqa: BLE001  模型呼叫失敗：這一次不修，往上報
            err = f"{type(e).__name__}: {e}"
        try:
            data = json.loads(raw) if raw else None
        except ValueError:
            data = None
        if not isinstance(data, dict) and not err:
            err = "回覆不是 JSON" if raw else "沒有回覆"
        log({"role": "fix", "node": req.get("node"), "model": model, "system": system, "user": user, "response": raw,
             "error": err if not isinstance(data, dict) else None, "ms": round((time.time() - t0) * 1000)})
        return data if isinstance(data, dict) else None


# =====================================================================================================================
# 執行
# =====================================================================================================================
class Executor:
    """照決策圖執行：start(graph) 或 resume(編號, approve) → job（dict，也存成 job.json）。fixer 預設是 ModelFixer。"""

    def __init__(self, agent, fixer=None):
        self.agent = agent
        self.store = JobStore(os.path.join(agent.script_dir, "logs", EDG_JOBS_DIRNAME))
        self.fixer = fixer if fixer is not None else ModelFixer(agent)
        self._cache = {}

    # ---------------------------------------------------------------- 進入點
    def start(self, graph):
        problems, specs, order = validate(self.agent.tools_dir, graph)
        jid = self.store.new_id()
        self.store.prune(EDG_JOBS_KEEP)
        job = {"id": jid, "status": "invalid" if problems else "running", "created": _now(), "updated": _now(),
               "cwd": self.agent.current_cwd, "graph": graph, "problems": problems, "order": order,
               "nodes": {nid: {"state": "pending"} for nid in order}, "stops": [], "judgments": [], "need_user": None}
        if problems:
            self.store.save(job)
            self._note(jid, "🔗 決策圖沒有通過檢查，沒有執行：" + "；".join(problems))
            return job
        self._note(jid, f"🔗 開始執行決策圖：{len(order)} 個節點")
        return self._run(job, specs)

    def resume(self, jid, approve=None):
        """接回停下來的工作。need_user 時 approve＝True／False 是使用者對那一個動作的決定。"""
        job = self.store.load(jid)
        if not job:
            return None
        problems, specs, _ = validate(self.agent.tools_dir, job["graph"])
        if problems:
            job.update(status="invalid", problems=problems, updated=_now())
            self.store.save(job)
            return job
        pending = job.get("need_user")
        if pending and approve is not None:
            inst = job["nodes"][pending["node"]]["instances"][pending["instance"]]
            inst["approved"] = bool(approve)
            inst.setdefault("decisions", []).append({"time": _now(), "approve": bool(approve), "text": pending.get("text", "")})
        self._rebuild_cache(job)
        return self._run(job, specs)

    def replan(self, jid, graph):
        """中階重排：同一個工作換成新的圖接著跑。定義（工具、參數、依賴、預期…）沒變、依賴的節點也都保留的節點不重跑；
        其他的重新跑。拿掉的、重跑的節點原本的狀態記在 job["replans"]。新的圖沒通過檢查就不執行（狀態 invalid）。"""
        job = self.store.load(jid)
        if not job:
            return None
        problems, specs, order = validate(self.agent.tools_dir, graph)
        if problems:
            job.update(status="invalid", problems=problems, updated=_now())
            self.store.save(job)
            self._note(jid, "🔗 重排的圖沒有通過檢查，沒有執行：" + "；".join(problems))
            return job
        old = {n["id"]: n for n in job["graph"]["nodes"]}
        new = {n["id"]: n for n in graph["nodes"]}
        kept, nodes = [], {}
        for nid in order:
            same = nid in old and _definition(old[nid]) == _definition(new[nid]) and job["nodes"].get(nid, {}).get("state") in NODE_FINAL
            if same and all(d in kept for d in new[nid].get("depends_on", [])):
                kept.append(nid)
                nodes[nid] = job["nodes"][nid]
            else:
                nodes[nid] = {"state": "pending"}
        replaced = {nid: dict(st, tool=old[nid].get("tool")) for nid, st in job["nodes"].items() if nid not in kept}
        job.setdefault("replans", []).append({"time": _now(), "kept": kept, "rerun": [n for n in order if n not in kept and n in old],
                                              "added": [n for n in order if n not in old], "dropped": [n for n in old if n not in new],
                                              "replaced": replaced})
        job.update(graph=graph, order=order, nodes=nodes, problems=[], stops=[], judgments=[], need_user=None)
        self._note(jid, f"🔗 重排：保留 {len(kept)} 個節點，要跑 {len(order) - len(kept)} 個")
        self._rebuild_cache(job)
        return self._run(job, specs)

    def _rebuild_cache(self, job):
        """這個工作之前成功跑過的嘗試（含重排前的）：同一個工具＋同樣的參數不重跑，直接用之前的收據。"""
        tools = {n["id"]: n.get("tool") for n in job["graph"]["nodes"]}
        states = [(tools.get(nid), st) for nid, st in job["nodes"].items()]
        states += [(st.get("tool"), st) for r in job.get("replans", []) for st in r["replaced"].values()]
        self._cache = {}
        for tool, st in states:
            for inst in st.get("instances", []):
                for a in inst.get("attempts", []):
                    if tool and a.get("check") == "run" and a.get("status") != "error":
                        self._cache.setdefault(self._key(tool, a["args"]), a)

    # ---------------------------------------------------------------- 圖
    def _run(self, job, specs):
        """照順序跑還沒結束的節點。工具在排圖時的工作目錄執行（resume 時主對話可能已經換了目錄），跑完換回來。"""
        nodes = {n["id"]: n for n in job["graph"]["nodes"]}
        job.update(status="running", need_user=None)
        saved_cwd = self.agent.current_cwd
        if job.get("cwd") and os.path.isdir(job["cwd"]):
            self.agent.current_cwd = job["cwd"]
        try:
            for nid in job["order"]:
                st = job["nodes"][nid]
                if st["state"] in NODE_FINAL:
                    continue
                n = nodes[nid]
                bad = [d for d in n.get("depends_on", []) if job["nodes"][d]["state"] in BAD]
                if bad:
                    st.update(state="blocked", reason=f"依賴的節點沒有成功：{'、'.join(bad)}")
                    self._note(job["id"], f"🔗 {nid}：跳過（{st['reason']}）")
                    continue
                if n.get("kind") == "judgment":
                    st["state"] = "judgment"
                    continue
                self._run_node(job, n, st, specs[n["tool"]], nodes)
                job["updated"] = _now()
                self.store.save(job)
                if st["state"] == "need_user":
                    job["status"] = "need_user"
                    self.store.save(job)
                    return job
        finally:
            self.agent.current_cwd = saved_cwd
        self._finish(job, nodes)
        return job

    def _finish(self, job, nodes):
        job["stops"] = [{"node": nid, "state": st["state"], "reason": st.get("reason", "")}
                        for nid, st in job["nodes"].items() if st["state"] in BAD]
        job["judgments"] = [{"node": nid, "goal": nodes[nid]["goal"],
                             "inputs": [{"node": d, "results": self._result_ids(job["nodes"][d])} for d in nodes[nid]["depends_on"]]}
                            for nid, st in job["nodes"].items() if st["state"] == "judgment"]
        job["status"] = "stopped" if job["stops"] else "judgment" if job["judgments"] else "done"
        job["updated"] = _now()
        self.store.save(job)
        self._note(job["id"], f"🔗 決策圖執行完：{job['status']}" + "".join(f"；{s['node']} {s['state']}（{s['reason']}）" for s in job["stops"]))

    @staticmethod
    def _result_ids(st):
        return [inst["attempts"][-1].get("result_id") for inst in st.get("instances", []) if inst.get("attempts")]

    # ---------------------------------------------------------------- 節點
    def _run_node(self, job, n, st, spec, nodes):
        if "instances" not in st:
            insts, each = self._instances(job, n)
            st["instances"] = [{"args": a, "state": "pending", "attempts": []} for a in insts]
            if each:
                st["each"] = each
        for i, inst in enumerate(st["instances"]):
            if inst["state"] in INSTANCE_FINAL:
                continue
            self._run_instance(job, n, i, inst, spec)
            if inst["state"] == "need_user":
                st["state"] = "need_user"
                job["need_user"] = {"node": n["id"], "instance": i, "guard": inst["guard"],
                                    "text": self.agent.guard_prompt_text(inst["guard"])}
                return
        states = [inst["state"] for inst in st["instances"]]
        each = st.get("each") or {}
        capped = each.get("instances", 0) > each.get("ran", 0)
        if "failed" in states or "denied" in states:
            st["state"] = "failed"
        elif "unexpected" in states:
            st["state"] = "unexpected"
        elif capped and n.get("complete"):
            st["state"] = "unexpected"
        else:
            st["state"] = "done"
        reasons = [f"#{k + 1} {inst['reason']}" if len(states) > 1 else inst["reason"]
                   for k, inst in enumerate(st["instances"]) if inst.get("reason")]
        if capped:
            reasons.append(f"帶入的項目有 {each['instances']} 個，只跑了前 {each['ran']} 個")
        if not st["instances"]:
            reasons.append(f"{each.get('from')} 的收據沒有可以帶入的項目")
        st["reason"] = "；".join(reasons)
        self._note(job["id"], f"🔗 {n['id']}（{n['tool']}）：{st['state']}" + (f"（{st['reason']}）" if st["reason"] else ""))

    def _instances(self, job, n):
        """這個節點要跑的參數：沒有帶入的就是一個；從前一個節點的收據帶入時，每一個項目一個（同樣的參數只留一個，最多 EDG_EACH_MAX 個）。"""
        args = n.get("args", [])
        binds = [a for a in args if isinstance(a, dict)]
        if not binds:
            return [list(args)], None
        src = binds[0]["from"]
        items, truncated = [], False
        for inst in job["nodes"][src].get("instances", []):
            receipt = self._load_receipt(job, inst)
            items += (receipt or {}).get("items") or []
            truncated = truncated or bool((receipt or {}).get("truncated"))
        out, seen, missing = [], set(), 0
        for it in items:
            vals = [a if isinstance(a, str) else it.get(a["field"]) for a in args]
            if any(v is None or v == "" for v in vals):
                missing += 1
                continue
            vals = [str(v) for v in vals]
            if tuple(vals) not in seen:
                seen.add(tuple(vals))
                out.append(vals)
        each = {"from": src, "items": len(items), "instances": len(out), "ran": min(len(out), EDG_EACH_MAX),
                "missing": missing, "inputs_truncated": truncated}
        return out[:EDG_EACH_MAX], each

    # ---------------------------------------------------------------- 實例：執行、守門、第 1 級
    def _run_instance(self, job, n, i, inst, spec):
        while True:
            if not inst["attempts"]:
                args = inst["args"]
            elif (inst.get("fix") or {}).get("accepted") and len(inst["attempts"]) == 1:
                args = inst["fix"]["args"]
            else:
                inst.update(state="failed", reason=inst.get("reason") or "沒有可以再試的參數")
                return
            rec = self._attempt(job, n, i, inst, spec, args)
            if "need_user" in rec:
                inst.update(state="need_user", guard=rec["need_user"])
                return
            if "denied" in rec:
                inst.update(state="denied", reason="使用者沒有同意執行")
                return
            inst.pop("guard", None)
            inst["attempts"].append(rec)
            state, reason = self._outcome(n, rec)
            if state != "error":
                inst.update(state=state, reason=reason, fixed=len(inst["attempts"]) > 1)
                return
            kind = rec.get("error_kind")
            if kind in FIXABLE and "fix" not in inst:
                inst["fix"] = self._fix(job, n, spec, args, rec)
                if inst["fix"].get("accepted"):
                    self._note(job["id"], f"🔗 {n['id']}：第 1 級修正 {json.dumps(args, ensure_ascii=False)} → "
                                          f"{json.dumps(inst['fix']['args'], ensure_ascii=False)}（{inst['fix']['reason']}）")
                    continue
                reason = f"{reason}；沒有修正：{inst['fix']['why']}"
            elif "fix" in inst:
                reason = f"修正之後還是錯：{reason}"
            inst.update(state="failed", reason=reason)
            return

    def _attempt(self, job, n, i, inst, spec, args):
        """執行一次（或執行前的檢查就沒過）→ 這次嘗試的紀錄；要使用者確認時回 {"need_user": 關卡的說明}、拒絕過回 {"denied": …}。"""
        script = spec["script"]
        rec = {"args": list(args)}
        _, err = parse(script, args)
        if err:
            rec.update(check="pre", status="error", error_kind="args", text=str(err)[:ERROR_TEXT_MAX], head=str(err).splitlines()[0][:300])
            return rec
        raw = shlex.join(args)
        guard = self.agent.guard_check({"action": {"command": f"scripts/{script}", "args": raw}})
        if guard:
            approved = inst.pop("approved", None)
            if approved is None:
                return {"need_user": guard}
            if approved is False:
                return {"denied": guard}
        key = self._key(n["tool"], args)
        if key in self._cache:
            prev = self._cache[key]
            rec.update({k: prev.get(k) for k in ("check", "status", "error_kind", "counts", "truncated", "result_id", "receipt_file", "head")},
                       reused=True)
            return rec
        text = self.agent.run_script(script, list(args), raw)
        receipt = self.agent.last_receipt or {"status": "error", "error_kind": "parse", "note": "腳本沒有寫收據"}
        rec.update(check="run", status=receipt.get("status"), error_kind=receipt.get("error_kind"), counts=receipt.get("counts"),
                   truncated=bool(receipt.get("truncated")), result_id=self.agent.last_result_id,
                   head=(text.strip().splitlines() or [""])[0][:300])
        rec["receipt_file"] = self._save_receipt(job, n["id"], i, len(inst["attempts"]), receipt)
        if rec["status"] == "error":
            rec["text"] = text[:ERROR_TEXT_MAX]
            if receipt.get("near"):
                rec["near"] = list(receipt["near"])
        else:
            self._cache[key] = rec
        return rec

    @staticmethod
    def _outcome(n, rec):
        """守門（照收據）：done、unexpected（成功但不合預期）或 error，附原因。"""
        status = rec.get("status")
        if status == "error":
            return "error", f"{rec.get('error_kind')}：{rec.get('head', '')}"
        expect = n.get("expect", ["pass"])
        if status not in expect:
            return "unexpected", f"收據的狀態是 {status}，預期 {'／'.join(expect)}"
        if n.get("complete") and rec.get("truncated"):
            return "unexpected", "結果不完整（收據的 truncated 為真），這個節點要完整的結果"
        return "done", ""

    def _fix(self, job, n, spec, args, rec):
        """第 1 級：修正一次 → {"reason", "fixable", "args", "accepted", "why"}；程式核對過才 accepted。找不到路徑而相近的路徑有好幾個時
        不交給修正的模型（要哪一個是上一層的決定）→ {"accepted": False, "near": 候選, "why"}。"""
        kind = rec["error_kind"]
        near = rec.get("near") or []
        if kind == "args" and len(near) > 1:
            return {"accepted": False, "near": list(near),
                    "why": f"找不到路徑，相近的路徑有 {len(near)} 個（{'、'.join(near)}）：第 1 級不替上一層選，交回上一層決定"}
        scope = spec["contract"].get("narrow")
        narrow = scope if kind == "timeout" else None
        if kind == "timeout" and not narrow:
            return {"accepted": False, "why": "規格沒有列逾時時的縮小方式"}
        if not self.fixer:
            return {"accepted": False, "why": "沒有修正的模型"}
        req = {"job": job["id"], "node": n["id"], "tool": n["tool"], "spec": skill_spec.for_model(spec["text"]), "args": list(args),
               "error": rec.get("text") or rec.get("head") or "", "kind": kind, "stage": rec["check"],
               "goal": job["graph"]["goal"], "why": n.get("why", ""), "narrow": narrow}
        out = self.fixer(req, lambda r: self.store.append(job["id"], "calls.jsonl", r))
        if not out:
            return {"accepted": False, "why": "修正的模型沒有回覆，或回覆不是 JSON"}
        fix = {"reason": str(out.get("reason") or "")[:300], "fixable": bool(out.get("fixable")),
               "args": [str(a) for a in out.get("args") or [] if str(a) != ""]}
        if not fix["fixable"]:
            return dict(fix, accepted=False, why=f"修正的模型判斷改參數修不好：{fix['reason']}")
        quoted = [a for a in fix["args"] if len(a) >= 2 and a[0] == a[-1] and a[0] in "\"'" and a not in args]
        if quoted:                 # 參數是一個一個的字串：外面再包一層引號，腳本收到的就是帶引號的字（搜的會是另一串字）
            return dict(fix, accepted=False, why=f"新的參數外面多了 shell 的引號：{quoted[0]}")
        if fix["args"] == list(args):
            return dict(fix, accepted=False, why="參數沒有改")
        _, err = parse(spec["script"], fix["args"])
        if err:
            return dict(fix, accepted=False, why=f"新的參數沒有通過檢查：{str(err).splitlines()[0]}")
        if kind == "timeout":
            ok, why = narrowed(spec["script"], args, fix["args"], narrow, job["cwd"] or ".")
            if not ok:
                return dict(fix, accepted=False, why=why)
        else:
            wide = widened(spec["script"], scope, args, fix["args"], job["cwd"] or ".")
            if wide:
                return dict(fix, accepted=False, why=wide)
        return dict(fix, accepted=True, why="")

    # ---------------------------------------------------------------- 存檔
    @staticmethod
    def _key(tool, args):
        return json.dumps([tool, list(args)], ensure_ascii=False)

    def _save_receipt(self, job, nid, i, k, receipt):
        """receipts/<節點>_<實例>_<嘗試>.json；重排之後重跑的加上第幾版（_v2…），不蓋掉之前那一版的收據（拓撲圖照版本看、中階讀的是這一版的）。"""
        v = len(job.get("replans") or [])
        rel = f"receipts/{nid}_{i + 1}_{k + 1}" + (f"_v{v + 1}" if v else "") + ".json"
        self.store.write(job["id"], rel, json.dumps(receipt, ensure_ascii=False))
        return rel

    def _load_receipt(self, job, inst):
        rel = (inst.get("attempts") or [{}])[-1].get("receipt_file")
        if not rel:
            return None
        try:
            with open(self.store.path(job["id"], rel), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _note(self, jid, text):
        """進度：印出、記進 events.jsonl、交給畫面（Web 執行工具時設的 progress_callback）。"""
        print(text)
        self.store.append(jid, "events.jsonl", {"text": text})
        cb = getattr(self.agent, "progress_callback", None)
        if cb:
            try:
                cb(text)
            except Exception:   # noqa: BLE001  畫面的問題不能中斷執行
                pass
