"""新架構的決策圖（Web 的 /topology 頁面，唯讀）：列出中階與低階的工作，把一個工作整理成頁面要畫的資料。

來源：正式的 logs/（mid_jobs/<編號>/、edg_jobs/<編號>/）與評測結果（evals/results/<目錄>/logs/<題目>/ 底下的 mid_jobs/、edg_jobs/，
或低階評測直接放在題目目錄的 job.json）。中階的工作附上它用到的低階工作（排圖的、查參數的），清單裡不另外列。

一個中階的工作整理成每一版的圖（mid 的 graphs），每一版附：
- 每個節點跑完那一版時的狀態與每一次嘗試（低階 job.json 的 nodes；之後重排掉的，從 replans 的 replaced 找回當時的狀態）；
- 跟上一版比沿用、重跑、新加、拿掉的節點（低階的 replans）；
- 這一版的回退與問使用者（marks：頁面畫成虛線與另外的節點）、上一版的回退加進來的節點（extra_edges：從條件的節點畫虛線）；
- 這一版跑完時的判斷（judgments：判斷節點挑的行、選的路），判斷加進來的節點在之後的每一版都從那個判斷節點畫虛線（extra_edges，
  看得到一路追下去的鏈）；換技能的回退（marks 的 switched）。

只讀檔案、不改任何東西，也不 import web_app.state（不用起 agent；離線測試直接呼叫，root 換成臨時的副本）。路徑一律在這裡組：
來源只認 logs 與 evals/results/<目錄>，工作只認來源底下的相對路徑（每一段都是名稱，不能有 ..），收據只認 receipts/ 底下的 .json。
"""
import json
import os
import re

from agent_core.config import EDG_JOBS_DIRNAME, MID_JOBS_DIRNAME, PROJECT_ROOT
from agent_core.mid import STATUS_TEXT

RESULTS_DIR = os.path.join("evals", "results")
_SEG = re.compile(r"^\w[\w.+@-]*$")               # 路徑的一段（目錄或工作的名稱；不能是 . 或 ..）
_RECEIPT = re.compile(r"^receipts/\w[\w.-]*\.json$")


# ================================================================ 讀檔
def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _jsonl(path):
    out = []
    for line in _read(path).splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _listdir(path):
    try:
        return os.listdir(path)
    except OSError:
        return []


def _inside(path, base):
    rp, rb = os.path.realpath(path), os.path.realpath(base)
    return rp == rb or rp.startswith(rb + os.sep)


# ================================================================ 來源與工作的路徑
def _src_dir(src, root):
    """來源的 logs 目錄；不認得的來源回 None。"""
    if src == "logs":
        return os.path.join(root, "logs")
    parts = str(src or "").split("/")
    if len(parts) == 3 and parts[:2] == ["evals", "results"] and _SEG.match(parts[2]):
        d = os.path.join(root, RESULTS_DIR, parts[2], "logs")
        if os.path.isdir(d) and _inside(d, os.path.join(root, RESULTS_DIR)):
            return d
    return None


def _job_dir(src, ref, root):
    """工作的目錄（裡面有 job.json）；路徑不合規則或找不到回 None。"""
    base = _src_dir(src, root)
    parts = str(ref or "").split("/")
    if not base or not 1 <= len(parts) <= 3 or not all(_SEG.match(p) for p in parts):
        return None
    d = os.path.join(base, *parts)
    return d if os.path.isfile(os.path.join(d, "job.json")) and _inside(d, base) else None


def _job_refs(base, flat):
    """來源底下的工作 [(ref, 種類)]：flat＝正式的 logs/（mid_jobs/、edg_jobs/ 直接在底下）；評測的多一層題目的目錄。"""
    out = []
    groups = [""] if flat else sorted(g for g in _listdir(base) if _SEG.match(g) and os.path.isdir(os.path.join(base, g)))
    for g in groups:
        gdir = os.path.join(base, g) if g else base
        if g and os.path.isfile(os.path.join(gdir, "job.json")):
            out.append((g, "edg"))                 # 低階評測：題目的目錄就是一個工作
            continue
        for sub, kind in ((MID_JOBS_DIRNAME, "mid"), (EDG_JOBS_DIRNAME, "edg")):
            for jid in sorted(_listdir(os.path.join(gdir, sub))):
                if _SEG.match(jid) and os.path.isfile(os.path.join(gdir, sub, jid, "job.json")):
                    out.append(("/".join(x for x in (g, sub, jid) if x), kind))
    return out


def _group(ref):
    """中階工作的 ref 前面那一段（評測的題目；正式的 logs/ 是空的）：它用到的低階工作在同一層的 edg_jobs/。"""
    parts = ref.split("/")
    return "/".join(parts[:-2])


def _edg_ref(group, eid):
    return "/".join(x for x in (group, EDG_JOBS_DIRNAME, eid) if x)


# ================================================================ 清單
def sources(root=PROJECT_ROOT):
    """有工作的來源：正式的 logs/（一定列）與評測結果的目錄（名稱開頭是時間，新的在前）；每個附中階、低階工作的數量。"""
    keys = ["logs"] + [f"evals/results/{n}" for n in sorted(_listdir(os.path.join(root, RESULTS_DIR)), reverse=True) if _SEG.match(n)]
    out = []
    for key in keys:
        base = _src_dir(key, root)
        refs = _job_refs(base, key == "logs") if base else []
        if key == "logs" or refs:
            out.append({"key": key, "mid": sum(k == "mid" for _, k in refs), "edg": sum(k == "edg" for _, k in refs)})
    return out


def jobs(src, root=PROJECT_ROOT):
    """一個來源的工作：中階的，加上沒有被中階用到的低階工作；正式的 logs/ 新的在前，評測照題目排。來源不認得回 None。"""
    base = _src_dir(src, root)
    if not base:
        return None
    mids, edgs, used = [], [], set()
    for ref, kind in _job_refs(base, src == "logs"):
        job = _load(os.path.join(base, *ref.split("/"), "job.json")) or {}
        case = ref.split("/")[0] if src != "logs" else ""
        if kind == "mid":
            used |= {_edg_ref(_group(ref), e) for e in [job.get("edg_job")] + [f.get("edg_job") for f in job.get("fetches") or []] if e}
            mids.append({"ref": ref, "kind": "mid", "id": job.get("id"), "case": case, "status": job.get("status"),
                         "status_text": STATUS_TEXT.get(job.get("status"), job.get("status")), "title": job.get("question", ""),
                         "skill": job.get("skill"), "versions": len(job.get("graphs") or []),
                         "fallbacks": [f.get("fallback") for f in job.get("fallbacks") or []],
                         "judged": sum(1 for j in job.get("judgments") or [] if j.get("round")), "created": job.get("created")})
        else:
            insts = [i for st in (job.get("nodes") or {}).values() for i in st.get("instances") or []]
            edgs.append({"ref": ref, "kind": "edg", "id": job.get("id"), "case": case, "status": job.get("status"),
                         "title": (job.get("graph") or {}).get("goal", ""), "versions": 1 + len(job.get("replans") or []),
                         "fixed": any(i.get("fixed") for i in insts), "created": job.get("created")})
    out = mids + [e for e in edgs if e["ref"] not in used]
    if src == "logs":
        out.sort(key=lambda j: j.get("created") or "", reverse=True)
    return out


# ================================================================ 一個工作
def _box(snap, st):
    """節點框要顯示的：狀態、原因、實例數、帶入的統計、最後一次嘗試的收據狀態與 #編號、修正、確認關卡。
    st 是低階的節點狀態（有的話以它為準），snap 是中階存的那一版的摘要。都沒有回 None（這一版沒有跑到）。"""
    if st:
        insts = st.get("instances") or []
        last = [i["attempts"][-1] for i in insts if i.get("attempts")]
        return {"state": st.get("state"), "reason": st.get("reason", ""), "instances": len(insts), "each": st.get("each"),
                "results": [a["result_id"] for a in last if a.get("result_id") is not None],
                "statuses": sorted({a["status"] for a in last if a.get("status")}),
                "fixed": any(i.get("fixed") for i in insts), "fix_failed": any("fix" in i and not i.get("fixed") for i in insts),
                "decisions": [d for i in insts for d in i.get("decisions") or []]}
    if snap:
        return {"state": snap.get("state"), "reason": snap.get("reason", ""), "instances": snap.get("instances", 0),
                "each": snap.get("each"), "results": snap.get("results") or [], "statuses": [], "fixed": bool(snap.get("fixed")),
                "fix_failed": False, "decisions": []}
    return None


def _state_at(edg, i, nid):
    """低階的節點在第 i 次重排之前（第 i+1 版跑完時）的狀態：被重排換掉的在 replans[i].replaced；沿用的往後一版找。"""
    reps = edg.get("replans") or []
    while i < len(reps):
        if nid in (reps[i].get("replaced") or {}):
            return reps[i]["replaced"][nid]
        if nid not in (reps[i].get("kept") or []):
            return None
        i += 1
    return (edg.get("nodes") or {}).get(nid)


def _change(rep, prev_nodes):
    """跟上一版比：沿用、重跑、新加、拿掉的節點（拿掉的附它的定義與當時的狀態，頁面畫成淡的）。"""
    if not rep:
        return None
    prev = {n["id"]: n for n in prev_nodes}
    dropped = [x for x in rep.get("dropped") or [] if x in prev]
    return {"kept": rep.get("kept") or [], "rerun": rep.get("rerun") or [], "added": rep.get("added") or [], "dropped": dropped,
            "dropped_nodes": [prev[x] for x in dropped],
            "dropped_boxes": {x: _box(None, (rep.get("replaced") or {}).get(x)) for x in dropped}}


def _marks(job, versions):
    """回退與問使用者放到它發生的那一版（marks），回退加進來的節點在下一版從條件的節點畫虛線（extra_edges）。"""
    asked = job.get("asked") or []
    for fb in job.get("fallbacks") or []:
        k = fb.get("version") or 0
        if not 1 <= k <= len(versions):
            continue
        trigger = (fb.get("when") or {}).get("node")
        mark = {"id": f"fb_{fb.get('fallback')}_{k}", "type": fb.get("result"), "fallback": fb.get("fallback"), "from": trigger,
                "say": fb.get("say", ""), "when": fb.get("when"), "change": fb.get("change"), "time": fb.get("time")}
        nxt = versions[k] if k < len(versions) else None
        if fb.get("result") == "switched" and nxt:
            mark.update(to_version=k + 1, to=fb.get("to"))
        elif fb.get("result") == "replanned" and nxt:
            mark.update(to_version=k + 1, added=fb.get("added") or [])
            nxt["extra_edges"] += [{"from": trigger, "to": nid, "type": "fallback", "fallback": fb.get("fallback"),
                                    "say": fb.get("say", ""), "when": fb.get("when")} for nid in mark["added"]]
        elif fb.get("result") == "ask":
            ask = next((a for a in asked if a.get("fallback") == fb.get("fallback") and a.get("version") == k), None)
            if ask is None:                        # 有 asked 之前的工作：問題是回退的說明，回答從下一版的原因找
                ask = {"kind": "param", "param": (fb.get("change") or {}).get("ask"), "question": fb.get("say", ""), "candidates": []}
                need = job.get("need_user") or {}
                if need.get("fallback") == fb.get("fallback") and not nxt:
                    ask = dict(need)
                elif nxt and (nxt.get("cause") or {}).get("kind") == "user":
                    ask["answer"] = nxt["cause"].get("value")
            mark["ask"] = ask
            if nxt:
                mark["to_version"] = k + 1
        versions[k - 1]["marks"].append(mark)


def _judgments(job, versions):
    """判斷放到它發生的那一版（judgments）；照判斷加進來的節點，在之後每一版（兩個節點都還在的）從判斷節點畫虛線。"""
    for j in job.get("judgments") or []:
        k = j.get("version") or 0
        if not 1 <= k <= len(versions):
            continue
        item = dict(j, to_version=k + 1 if j.get("result") == "replanned" and k < len(versions) else None)
        versions[k - 1]["judgments"].append(item)
        if not item["to_version"]:
            continue
        for ver in versions[k:]:
            tools = {n["id"] for n in ver["graph"].get("nodes") or [] if n.get("kind", "tool") == "tool"}   # 加的判斷節點由依賴的邊接上
            if j["node"] in {n["id"] for n in ver["graph"].get("nodes") or []}:
                ver["extra_edges"] += [{"from": j["node"], "to": nid, "type": "judgment", "branch": j.get("branch"), "say": j.get("say", ""),
                                        "params": j.get("params"), "round": j.get("round"), "version": k} for nid in j.get("added") or [] if nid in tools]


def _asked(job):
    """問使用者的紀錄；有 asked 之前的工作只看得到現在在等的那一個。"""
    if "asked" in job:
        return job["asked"]
    need = job.get("need_user")
    return [dict(need, version=len(job.get("graphs") or []))] if need else []


def _edg_brief(ref, job):
    if not job:
        return None
    return {"ref": ref, "id": job.get("id"), "status": job.get("status"), "problems": job.get("problems") or [],
            "stops": job.get("stops") or [], "judgments": job.get("judgments") or [], "need_user": job.get("need_user"),
            "replans": [{k: r.get(k) for k in ("time", "kept", "rerun", "added", "dropped")} for r in job.get("replans") or []]}


def _texts(path):
    return [e.get("text", "") for e in _jsonl(path)]


def _mid_view(base, ref, d, job):
    group = _group(ref)
    gdir = os.path.join(base, *group.split("/")) if group else base

    def edg(eid):
        if not eid or not _SEG.match(str(eid)):
            return None, None, ""
        edir = os.path.join(gdir, EDG_JOBS_DIRNAME, eid)
        return _edg_ref(group, eid), _load(os.path.join(edir, "job.json")), edir

    eref, ej, edir = edg(job.get("edg_job"))
    graphs = job.get("graphs") or []
    reps = (ej or {}).get("replans") or []
    versions = []
    for i, g in enumerate(graphs):
        applied = ej is not None and i <= len(reps) and g.get("status") != "invalid"
        nodes = {}
        for n in (g.get("graph") or {}).get("nodes") or []:
            st = _state_at(ej, i, n["id"]) if applied else None
            nodes[n["id"]] = {"box": _box((g.get("nodes") or {}).get(n["id"]) if applied else None, st), "detail": st}
        versions.append({"version": g.get("version", i + 1), "time": g.get("time"), "cause": g.get("cause"), "status": g.get("status"),
                         "graph": g.get("graph") or {"nodes": []}, "nodes": nodes,
                         "change": _change(reps[i - 1], graphs[i - 1]["graph"]["nodes"]) if 0 < i <= len(reps) else None,
                         "marks": [], "extra_edges": [], "judgments": []})
    _marks(job, versions)
    _judgments(job, versions)
    fetches = []
    for f in job.get("fetches") or []:
        fref, fj, _ = edg(f.get("edg_job"))
        fetches.append(dict(f, ref=fref, graph=(fj or {}).get("graph"),
                            nodes={nid: {"box": _box(None, st), "detail": st} for nid, st in ((fj or {}).get("nodes") or {}).items()}))
    keys = ("id", "status", "created", "updated", "cwd", "domain", "question", "goal", "selection", "skill", "contract", "params",
            "rejected", "auto_filled", "need_user", "fallbacks", "switched", "judgments", "result")
    view = {k: job.get(k) for k in keys}
    if view["result"]:
        view["result"] = {k: v for k, v in view["result"].items() if k != "report"}
    view.update(kind="mid", status_text=STATUS_TEXT.get(job.get("status"), job.get("status")), asked=_asked(job), fetches=fetches,
                versions=versions, edg=_edg_brief(eref, ej), report=_read(os.path.join(d, "report.md")),
                events=_texts(os.path.join(d, "events.jsonl")), calls=_jsonl(os.path.join(d, "calls.jsonl")),
                edg_events=_texts(os.path.join(edir, "events.jsonl")) if edir else [],
                edg_calls=_jsonl(os.path.join(edir, "calls.jsonl")) if edir else [])
    return view


def _edg_view(ref, d, job):
    reps = job.get("replans") or []
    graph = job.get("graph") or {"nodes": []}
    nodes = {n["id"]: {"box": _box(None, (job.get("nodes") or {}).get(n["id"])), "detail": (job.get("nodes") or {}).get(n["id"])}
             for n in graph.get("nodes") or []}
    version = {"version": 1 + len(reps), "time": job.get("updated"), "cause": None, "status": job.get("status"), "graph": graph,
               "nodes": nodes, "change": None, "marks": [], "extra_edges": [], "judgments": []}
    return {"kind": "edg", "id": job.get("id"), "status": job.get("status"), "created": job.get("created"), "updated": job.get("updated"),
            "cwd": job.get("cwd"), "goal": graph.get("goal", ""), "need_user": job.get("need_user"), "versions": [version],
            "edg": _edg_brief(ref, job), "events": [], "calls": [], "edg_events": _texts(os.path.join(d, "events.jsonl")),
            "edg_calls": _jsonl(os.path.join(d, "calls.jsonl"))}


def job_view(src, ref, root=PROJECT_ROOT):
    """一個工作整理成頁面要畫的資料（見模組的說明）；找不到或路徑不合規則回 None。originals：#編號的原文看不看得到
    （評測只留了收據，原文沒有留下來；正式的 logs/ 才有，Web 用 /api/results/<編號> 開）。"""
    d = _job_dir(src, ref, root)
    job = _load(os.path.join(d, "job.json")) if d else None
    if not job:
        return None
    if os.path.basename(os.path.dirname(d)) == MID_JOBS_DIRNAME:
        view = _mid_view(_src_dir(src, root), ref, d, job)
    else:
        view = _edg_view(ref, d, job)
    return dict(view, src=src, ref=ref, originals=src == "logs")


def receipt(src, ref, rel, root=PROJECT_ROOT):
    """低階工作的一份收據（receipts/ 底下的 .json，嘗試的 receipt_file）；找不到或路徑不合規則回 None。"""
    d = _job_dir(src, ref, root)
    if not d or not _RECEIPT.match(str(rel or "")):
        return None
    path = os.path.join(d, *str(rel).split("/"))
    return _load(path) if _inside(path, d) else None
