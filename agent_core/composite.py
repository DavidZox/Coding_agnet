"""有骨架的技能（複合技能）：領域與技能規格的載入與核對、參數照原文核對（合約）、骨架代入參數、交給低階執行、照收據套用回退。
領域 session（agent_core/domain_session.py）選了有骨架的技能時由這裡執行（docs/框架討論紀錄.md F2、F3、F5）。

1. **規格**（skills_system/<領域>/<技能>.md）：frontmatter 的 parameters（名稱、種類、說明、必填或預設、路徑的 fetch）、answers、topology，
   〈骨架〉（工具節點：程式做的步驟）與〈回退〉（照收據的條件改圖）。骨架裡沒有判斷節點：讀交給提煉，下一步交給領域 session（F2）。
2. **合約**（verify_param，F3）：每個參數的原文要一字不改地在給的原文裡（領域 session 給的：問題、子目標、項目、前面每一步的結果），
   值照種類對得上原文（名稱、名稱清單、搜尋的字要原樣在原文裡；路徑的每一段是原文的名稱；文字與檔案名稱的寫法每一段在原文裡）。
3. **補齊**（Runner.run 的第一步）：沒提到的用預設值；路徑在工作目錄找不到時照 fetch 查一次（剛好一個就自己補，記在 auto_filled）。
   必填的沒有、路徑有好幾個或找不到：不問使用者，回 need（說明與候選），交回領域 session 決定（寫完整的路徑、換參數、換技能或回報）。
4. **排圖、執行**：〈骨架〉代入參數就是一張圖（`{"if": 參數, "args": [...]}` 的參數有值才放，名稱清單一項一組；節點寫 if 的，參數沒有值就
   不排）。交給低階（agent_core/edg.py）：照圖執行、照收據守門、第 1 級修正；每個節點的結果存成 #編號（跟主對話同一條路）。
5. **回退**（程式照收據比對條件，照列的順序取第一個還沒用過的）：add 在圖上加節點重排（跑過的不重跑）；switch 換成同一個領域的另一個
   技能（參數照寫好的對應帶過去）；ask 不問使用者，回 need（附範圍裡各子目錄的筆數當候選）。重排與換技能合計最多 MID_REPLAN_MAX 次，
   再要就熔斷；加的節點全都跑過＝不收斂，不再重排。
6. **結果**：狀態（done 跑完、stopped 有節點沒成功、need 要領域 session 決定、circuit_break、failed）、最後用的技能與參數、自己補的、
   回退與換技能的經過，與每一個節點跑過的實例（工具、參數、狀態、#編號）。原文由領域 session 照 #編號讀（太長的提煉）。
"""
import collections
import json
import os
import re
import time

from . import edg, prompt_files, skill_spec
from .config import EDG_JOBS_DIRNAME, MID_REPLAN_MAX

TYPES = ("name", "text", "path", "glob", "names", "words")
KINDS = ("位置", "數量", "內容")       # 複合技能規格的 answers：它答得了問題要的哪幾種（載入時核對寫法）
STATUS_TEXT = {"done": "跑完", "stopped": "有節點沒有成功", "need": "要你決定（見下面的說明）",
               "circuit_break": f"熔斷（重排與換技能超過 {MID_REPLAN_MAX} 次）", "failed": "失敗"}
SWITCH_TYPES = {("name", "names"), ("name", "words"), ("names", "words"), ("words", "names")}   # 換技能時參數的種類可以這樣換（其他要一樣）
CANDIDATES_MAX = 10
WORD = re.compile(r"^[\w./:@~-]+(?: [\w./:@~-]+)*$")   # 搜尋的一個字（或英文的詞組，中間一個空白）：沒有 |、括號與其他正規表示式的符號
_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DIRNAME = re.compile(r"^[\w.-]+$")             # 目錄或檔案的名稱（一段路徑；\w 含中文）
_SPLIT = re.compile(r"[、,，;；\s]+")
_WORD_SPLIT = re.compile(r"[、,，;；\n]+")      # 搜尋的字用「、」分開（英文的詞組裡的空白不分）
_ENTRY = re.compile(r"^- \[([A-Za-z0-9_]+)\]\(([^)]+)\)")
_QUOTES = "\"'`「」『』“”‘’"


def _i(key, /, **fields):
    """prompts/domain/session.md 的一則（合約沒過、要領域 session 決定的說明）。"""
    return prompt_files.load("domain/session.md", key, **fields)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _empty(v):
    return v is None or v == "" or v == []


def param_sig(values):
    """參數（{名稱: 值}）比對用的寫法：同一個技能、這個寫法一樣＝同樣的參數。"""
    return json.dumps({k: values[k] for k in sorted(values or {})}, ensure_ascii=False)


def words_of(value):
    """搜尋的字：清單或用「、」分開的一串 → 去掉引號、空的與重複的（中間的空白合成一個）。"""
    raw = value if isinstance(value, list) else _WORD_SPLIT.split(str(value or ""))
    out = []
    for x in raw:
        w = _norm(x).strip(_QUOTES).strip()
        if w and w not in out:
            out.append(w)
    return out


# =====================================================================================================================
# 領域與技能的規格
# =====================================================================================================================
def load_domain(base_path, tools_dir, name):
    """skills_system/<領域>/SKILLS.md 與它列的有骨架的技能 → {"name", "title", "intro", "skills": {名稱: 規格}, "catalog": {名稱: 那一行的說明},
    "tools", "practice", "problems"}。intro 是開頭的說明（含「不包含」）；practice 是〈做法〉一節；tools 是〈工具〉列的單步工具。"""
    out = {"name": name, "title": name, "intro": "", "skills": {}, "catalog": {}, "tools": [], "practice": "", "problems": []}
    try:
        with open(os.path.join(base_path, name, "SKILLS.md"), encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError:
        out["problems"].append(f"沒有 skills_system/{name}/SKILLS.md")
        return out
    if lines and lines[0].startswith("# "):
        out["title"] = lines[0][2:].strip()
    section, intro, entries, practice = None, [], [], []
    for ln in lines[1:]:
        if ln.startswith("## "):
            section = ln[3:].strip()
        elif section is None:
            intro.append(ln)
        elif section == "做法":
            practice.append(ln)
        elif (m := _ENTRY.match(ln)) and section in ("複合技能", "工具"):
            entries.append((section, m.group(1), m.group(2)))
            if section == "複合技能":
                out["catalog"][m.group(1)] = ln[m.end():].strip().lstrip("—-– ").strip()
    out["intro"] = "\n".join(intro).strip()
    out["practice"] = "\n".join(practice).strip()
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
    out["problems"] += _switch_problems(out["skills"])
    return out


def _arg_strings(args):
    """參數裡的字串：(字串, 所在的 if 群組的參數或 None)。"""
    for a in args if isinstance(args, list) else []:
        if isinstance(a, str):
            yield a, None
        elif isinstance(a, dict) and "if" in a:
            for x in a.get("args", []):
                yield x, a["if"]


def _arg_problems(nid, n, types, always):
    """工具節點的參數裡用到的 {參數}：要宣告過；名稱清單放在 {"if": 名稱, "args": [...]} 裡（一項一組）；搜尋的字整個參數只寫 {名稱}
    （程式用 | 接成一個關鍵字）；可能沒有值的要放在 if 裡（或節點寫 if）。"""
    p = []
    for a, group in _arg_strings(n.get("args", [])):
        for ref in _PARAM.findall(a):
            t = types.get(ref)
            if t is None:
                p.append(f"{nid}：參數 {ref} 沒有宣告")
            elif t == "names" and group != ref:
                p.append(f"{nid}：名稱清單 {ref} 要放在 {{\"if\": \"{ref}\", \"args\": [...]}} 裡（一項一組）")
            elif t == "words" and (a != "{" + ref + "}" or group is not None):
                p.append(f"{nid}：搜尋的字 {ref} 要整個參數只寫 {{{ref}}}（程式用 | 接成一個關鍵字）")
            elif ref not in always and ref not in (group, n.get("if")):
                p.append(f"{nid}：{ref} 可能沒有值，要放在 if 裡（或節點寫 if）")
    for a in n.get("args", []) if isinstance(n.get("args"), list) else []:
        if isinstance(a, dict) and "if" in a and a["if"] not in types:
            p.append(f"{nid}：if 的參數 {a['if']} 沒有宣告")
    return p


def _tool_problems(n, topo, types, always):
    nid = n["id"]
    p = []
    if n.get("tool") not in topo["sub_skills"]:
        p.append(f"{nid}：工具 {n.get('tool')} 不在 topology 的 sub_skills")
    if n.get("if") is not None and n["if"] not in types:
        p.append(f"{nid}：if 的參數 {n['if']} 沒有宣告")
    if "report" in n and not (isinstance(n["report"], str) and n["report"].strip()):
        p.append(f"{nid}：report 寫這個節點的結果在交給領域 session 時的小標題")
    return p + _arg_problems(nid, n, types, always)


def validate_skill(spec, tools_dir, domain_tools):
    """有骨架的技能的規格寫得對不對 → 問題的清單（空的才能用）。最後用假的參數排一次圖，交給低階的 validate 檢查。
    換技能（switch）的對象與參數的對應在 load_domain 核對（要看同一個領域的其他技能）。"""
    p = []
    meta, topo, params = spec["meta"], spec["topology"], spec["parameters"]
    if meta.get("type") != "Skill":
        p.append("type 要是 Skill")
    p += [f"缺少 {k}" for k in ("title", "description") if not meta.get(k)]
    if not isinstance(topo, dict) or not isinstance(topo.get("depends_on"), list) or not isinstance(topo.get("sub_skills"), list):
        return p + ["topology 要有 depends_on 與 sub_skills（陣列）"]
    if topo["depends_on"]:
        p.append("depends_on（硬性前置的技能）還沒接上：目前的技能用不到")
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
            if "default" in x:
                p.append(f"{n}：必填的參數不能有預設值")
        elif "default" in x:
            always.add(n)
        f = x.get("fetch")
        if f is not None and not (x.get("type") == "path" and isinstance(f, dict) and f.get("tool") in domain_tools
                                  and isinstance(f.get("args"), list) and all(isinstance(a, str) for a in f["args"])
                                  and any("{value}" in a or "{stem}" in a for a in f["args"])):
            p.append(f"{n}：fetch 只用在路徑，寫成 {{\"tool\": 這個領域的工具, \"args\": [含 {{value}} 或 {{stem}} 的參數…]}}")
    nodes = (spec["skeleton"] or {}).get("nodes") if isinstance(spec["skeleton"], dict) else None
    fallbacks = spec["fallbacks"]
    if not isinstance(nodes, list) or not nodes:
        return p + ["〈骨架〉要有 nodes"]
    if not isinstance(fallbacks, list):
        return p + ["〈回退〉要是陣列"]
    adds = [n for fb in fallbacks if isinstance(fb, dict) for n in (fb.get("change") or {}).get("add") or []]
    ids = set()
    for n in nodes + adds:
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(n, dict) or nid in ids:
            p.append(f"節點要是物件、id 不能重複：{nid!r}")
            continue
        ids.add(nid)
        if n.get("kind", "tool") != "tool":
            p.append(f"{nid}：骨架只放工具節點（程式做的步驟）；讀交給提煉，下一步交給領域 session")
            continue
        p += _tool_problems(n, topo, types, always)
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
        if not isinstance(change, dict) or len(change.keys() & {"add", "ask", "switch"}) != 1:
            p.append(f"回退 {fid}：change 要是 add（加節點）、ask（交回領域 session 決定）或 switch（換技能）其中一個")
        elif "ask" in change and (change["ask"] not in types or change.get("from") not in ids | {None}):
            p.append(f"回退 {fid}：ask 要是宣告過的參數，from 要是節點")
        elif "switch" in change and (not isinstance(change["switch"], str) or not isinstance(change.get("params"), dict)
                                     or any(src not in types for src in change["params"].values())):
            p.append(f"回退 {fid}：switch 寫換過去的技能名稱，params 寫 {{換過去的參數: 這個技能的參數}}")
        if not fb.get("say"):
            p.append(f"回退 {fid}：要寫 say（給領域 session 與報告看的一句話）")
    if p:
        return p
    dummy = {n: (["d"] if t in ("names", "words") else "x") for n, t in types.items()}
    graph = expand_nodes(nodes, dummy)[0] + expand_nodes(adds, dummy)[0]
    problems, _, _ = edg.validate(tools_dir, {"goal": "檢查", "nodes": graph})
    return [f"排出的圖：{x}" for x in problems]


def _switch_problems(skills):
    """換技能（〈回退〉的 switch）：換過去的技能在這個領域、參數的對應存在而且種類合得來（一樣，或名稱換成清單）、換過去的必填參數都有對應。"""
    out = []
    for name, spec in skills.items():
        mine = {x["name"]: x["type"] for x in spec["parameters"]}
        for fb in spec["fallbacks"]:
            ch = fb.get("change") or {}
            if "switch" not in ch:
                continue
            target = skills.get(ch["switch"])
            if target is None or target is spec:
                out.append(f"{name}：回退 {fb['id']} 換過去的 {ch['switch']} 不是這個領域的其他技能")
                continue
            theirs = {x["name"]: x for x in target["parameters"]}
            for dst, src in ch["params"].items():
                if src not in mine:
                    continue                       # 這個技能沒宣告的參數：validate_skill 已經報了
                if dst not in theirs:
                    out.append(f"{name}：回退 {fb['id']} 的 {dst} 不是 {ch['switch']} 的參數")
                elif mine[src] != theirs[dst]["type"] and (mine[src], theirs[dst]["type"]) not in SWITCH_TYPES:
                    out.append(f"{name}：回退 {fb['id']} 的 {src}（{mine[src]}）換不成 {ch['switch']} 的 {dst}（{theirs[dst]['type']}）")
            out += [f"{name}：回退 {fb['id']} 沒有對應 {ch['switch']} 的必填參數 {x}" for x, q in theirs.items()
                    if q.get("required") and x not in ch["params"]]
    return out


def _fill(text, params):
    """{參數} 換成值；清單（搜尋的字）用 | 接起來（search_text 的同義詞寫法）。"""
    def one(m):
        v = params[m.group(1)]
        return "|".join(str(x) for x in v) if isinstance(v, list) else str(v)
    return _PARAM.sub(one, text)


def expand_nodes(nodes, params):
    """骨架（或回退加的節點）代入參數 → (圖的節點, 沒有排的節點 id)。節點的 if 參數沒有值就不排，依賴它的也不排。"""
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


def _in_source(q, source, t):
    """抄的原文在原文裡：整段一字不改；名稱清單與搜尋的字的名稱常在原文不同的地方，可以是用「、」分開的幾段，每一段一字不改。"""
    src = _norm(source)
    if q in src:
        return True
    parts = [x.strip() for x in re.split(r"[、；;]", q) if x.strip()]
    return t in ("names", "words") and len(parts) > 1 and all(x in src for x in parts)


def verify_param(p, quote, value, source):
    """(值, 交回修的那一則)：值是 None 表示沒提到或沒過（沒過時第二個是給模型的說明）。名稱清單與搜尋的字的值是 list。"""
    q, v, name = _unquote(quote), _unquote(value), p["name"]
    if not q and not v:
        return None, None
    if not q or not _in_source(q, source, p["type"]):
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
    if t == "words":
        items = words_of(v)
        miss = [x for x in items if x not in q or not WORD.match(x) or x.startswith("-")]
        return (items, None) if items and not miss else (None, _i("reject_words", name=name, missing="、".join(miss) or v, quote=q))
    items = [_unquote(x) for x in _SPLIT.split(v) if _unquote(x)]
    miss = [x for x in items if x not in q or not _DIRNAME.match(x)]
    return (items, None) if items and not miss else (None, _i("reject_names", name=name, missing="、".join(miss) or v, quote=q))


def _named(found, value, name):
    """找到的路徑的檔名就是查的名稱，而且原文前面的每一段（目錄）照順序都在路徑裡。"""
    if os.path.basename(found) != name:
        return False
    rest = iter(found.split("/")[:-1])
    return all(any(part == seg for seg in rest) for part in value.rstrip("/").split("/")[:-1] if part not in ("", "."))


def _exists(cwd, path):
    return os.path.exists(os.path.join(cwd or ".", os.path.expanduser(path)))


def _node_key(n):
    return json.dumps([n.get("tool"), n.get("args")], ensure_ascii=False, sort_keys=True)


# =====================================================================================================================
# 執行一個有骨架的技能
# =====================================================================================================================
class Runner:
    """run(領域, 技能, 參數) → 結果（dict）。參數是領域 session 核對過的 {名稱: {"value", "quote", "source"}}。fixer 交給低階
    （第 1 級修正的模型，None＝預設）；note(文字)：進度（領域 session 記進它的 events.jsonl）。"""

    def __init__(self, agent, fixer=None, note=None):
        self.agent = agent
        self.fixer = fixer
        self.note = note or (lambda text: None)
        self._receipts = {}

    def run(self, domain, skill, params):
        st = {"skill": skill, "params": {k: dict(v) for k, v in params.items()}, "auto_filled": [], "fetches": [], "graphs": [],
              "edg_jobs": [], "fallbacks": [], "applied": [], "replans": 0, "switched": [], "status": None, "note": "", "need": None,
              "cwd": self.agent.current_cwd}
        cause, edg_job = None, None
        while True:
            spec = domain["skills"][st["skill"]]
            need = self._complete(st, spec)
            if need:
                return self._end(st, "need", need=need)
            values = {k: v["value"] for k, v in st["params"].items()}
            nodes, _ = expand_nodes(spec["skeleton"]["nodes"], values)
            if not nodes:
                gates = [n["if"] for n in spec["skeleton"]["nodes"] if n.get("if")]
                return self._end(st, "need", need={"param": gates[0] if gates else "", "candidates": [],
                                                   "question": _i("need_any", names="、".join(dict.fromkeys(gates)))})
            graph = {"goal": f"{st['skill']}：" + "；".join(f"{k}＝{v}" for k, v in values.items()), "nodes": nodes}
            while True:
                st["graphs"].append({"version": len(st["graphs"]) + 1, "time": _now(), "skill": st["skill"], "cause": cause, "graph": graph})
                ex = self._executor()
                ej = ex.replan(edg_job, graph) if edg_job else ex.start(graph)
                edg_job = ej["id"]
                st["graphs"][-1]["edg_job"] = edg_job
                if edg_job not in st["edg_jobs"]:
                    st["edg_jobs"].append(edg_job)
                self.note(f"🧱 {st['skill']} 第 {len(st['graphs'])} 版的圖：{len(graph['nodes'])} 個節點 → {ej['status']}")
                kind, info = self._after(st, domain, spec, ej, values, graph)
                if kind == "replan":
                    graph, cause = info, {"kind": "fallback", "fallback": st["fallbacks"][-1]["fallback"]}
                    continue
                break
            if kind == "switch":
                cause, edg_job = {"kind": "switch", "fallback": st["fallbacks"][-1]["fallback"]}, None
                continue
            return info

    # ---------------------------------------------------------------- 補齊參數
    def _complete(self, st, spec):
        """預設值；原文的路徑在工作目錄找不到時照 fetch 查一次（剛好一個就自己補）。要領域 session 決定的事回 need，或 None。"""
        for p in spec["parameters"]:
            cur = st["params"].get(p["name"])
            if cur is None:
                if "default" in p:
                    st["params"][p["name"]] = {"value": p["default"], "source": "default"}
                elif p.get("required"):
                    return {"param": p["name"], "candidates": [], "question": _i("need_missing", name=p["name"], desc=p["desc"])}
                continue
            if p["type"] != "path" or cur.get("checked"):
                continue
            if _exists(st["cwd"], cur["value"]):
                cur["checked"] = True
                continue
            if not p.get("fetch"):
                return {"param": p["name"], "candidates": [], "question": _i("need_none", name=p["name"], value=cur["value"])}
            exact, found = self._fetch(st, p, cur["value"])
            if len(exact) == 1:
                st["auto_filled"].append({"param": p["name"], "given": cur["value"], "value": exact[0]})
                self.note(f"🧱 自己補的：{p['name']}「{cur['value']}」→ {exact[0]}")
                cur.update(value=exact[0], source="fetch", checked=True)
                continue
            cands = (exact or found)[:CANDIDATES_MAX]
            return {"param": p["name"], "candidates": cands,
                    "question": _i("need_many" if cands else "need_none", name=p["name"], value=cur["value"])}
        return None

    def _fetch(self, st, p, value):
        """照 fetch 查一次 → (候選, 全部找到的)；都是相對於工作目錄的路徑。{value} 是原文的最後一段、{stem} 是它去掉副檔名；
        候選＝路徑結尾跟原文一樣，或檔名就是查的那個名稱、原文前面的每一段照順序都在路徑裡。"""
        f = p["fetch"]
        last = os.path.basename(value.rstrip("/")) or value
        args = [a.replace("{value}", last).replace("{stem}", os.path.splitext(last)[0] or last) for a in f["args"]]
        name = args[0] if args and not any(c in args[0] for c in "*?[/") else None
        ej = self._executor().start({"goal": f"找「{value}」在工作目錄的哪裡（{p['desc']}）",
                                     "nodes": [{"id": "fetch", "tool": f["tool"], "args": args, "expect": ["pass", "empty"]}]})
        found = []
        for inst in ej["nodes"].get("fetch", {}).get("instances", []):
            r = self._receipt(ej, (inst.get("attempts") or [{}])[-1]) or {}
            found += [self._rel(st, it["path"]) for it in r.get("items") or [] if it.get("path")]
        exact = [x for x in found if x == value or x.endswith("/" + value) or (name and _named(x, value, name))]
        st["fetches"].append({"param": p["name"], "given": value, "edg_job": ej["id"], "status": ej["status"], "found": len(found),
                              "exact": exact[:CANDIDATES_MAX]})
        return exact, found

    # ---------------------------------------------------------------- 執行之後：回退
    def _after(self, st, domain, spec, ej, values, graph):
        """→ ("replan", 新的圖)、("switch", None) 或 ("end", 結果)。"""
        st["graphs"][-1]["status"] = ej["status"]
        if ej["status"] == "need_user":
            return "end", self._end(st, "failed", ej, note=_i("guard_in_skill", text=(ej.get("need_user") or {}).get("text", "")))
        if ej["status"] == "invalid":
            return "end", self._end(st, "failed", ej, note="排出的圖沒有通過檢查：" + "；".join(ej["problems"]))
        for fb in spec["fallbacks"]:
            if fb["id"] in st["applied"] or not self._when(fb["when"], ej):
                continue
            st["applied"].append(fb["id"])
            entry = {"fallback": fb["id"], "skill": st["skill"], "say": fb["say"], "change": fb["change"], "time": _now()}
            st["fallbacks"].append(entry)
            change = fb["change"]
            if "ask" in change:
                entry["result"] = "ask"
                return "end", self._end(st, "need", ej, need={"param": change["ask"], "question": fb["say"],
                                                             "candidates": self._subdirs(st, ej, change.get("from"))})
            if st["replans"] >= MID_REPLAN_MAX:
                entry["result"] = "circuit_break"
                return "end", self._end(st, "circuit_break", ej, note=f"還要套用 {fb['id']}，但已經重排 {st['replans']} 次")
            if "switch" in change:
                self._switch(st, domain, fb, entry)
                return "switch", None
            extra, _ = expand_nodes(change["add"], values)
            ran = {_node_key(n) for g in st["graphs"] for n in g["graph"]["nodes"]}
            if all(_node_key(n) in ran for n in extra):
                entry["result"] = "no_new_nodes"
                continue
            st["replans"] += 1
            entry.update(result="replanned", added=[n["id"] for n in extra])
            self.note(f"🧱 回退 {fb['id']}（{fb['say'][:60]}），加了 {'、'.join(entry['added'])}")
            return "replan", {"goal": graph["goal"], "nodes": graph["nodes"] + extra}
        stops = "；".join(f"{s['node']}：{s['reason'] or s['state']}" for s in ej.get("stops") or [])
        return "end", self._end(st, "stopped" if ej["status"] == "stopped" else "done", ej, note=stops)

    def _switch(self, st, domain, fb, entry):
        """換技能：參數照對應帶過去（名稱換成清單），之後照換過去的技能補參數、照它的骨架排圖（算一次重排）。"""
        target = domain["skills"][fb["change"]["switch"]]
        types = {p["name"]: p["type"] for p in target["parameters"]}
        params = {}
        for dst, src in fb["change"]["params"].items():
            cur = st["params"].get(src)
            if cur is None or _empty(cur["value"]):
                continue
            v = cur["value"]
            params[dst] = {"value": [v] if types[dst] in ("names", "words") and not isinstance(v, list) else v, "source": "switch",
                           "from": src, "checked": bool(cur.get("checked"))}
        st["switched"].append({"from": st["skill"], "to": target["name"], "fallback": fb["id"], "time": _now(),
                               "params": {k: v["value"] for k, v in params.items()}})
        entry.update(result="switched", to=target["name"])
        self.note(f"🧱 回退 {fb['id']}（{fb['say'][:60]}），換技能 {st['skill']} → {target['name']}")
        st.update(skill=target["name"], params=params, applied=[])
        st["replans"] += 1

    def _when(self, when, ej):
        """回退的條件：node 的狀態（state）、帶入的實例超過上限（capped），其他的鍵比對那個節點某一個實例最後一次嘗試的收據。"""
        nst = ej["nodes"].get(when["node"])
        if not nst:
            return False
        if "state" in when and nst["state"] != when["state"]:
            return False
        if "capped" in when:
            each = nst.get("each") or {}
            if (each.get("instances", 0) > each.get("ran", 0)) != when["capped"]:
                return False
        keys = {k: v for k, v in when.items() if k not in ("node", "state", "capped")}
        if not keys:
            return True
        for inst in nst.get("instances", []):
            r = self._receipt(ej, (inst.get("attempts") or [{}])[-1])
            if r and all(r.get(k) == v for k, v in keys.items()):
                return True
        return False

    def _subdirs(self, st, ej, nid):
        """要縮小範圍時的候選：那個節點（search_text）收據裡每個檔案的筆數，照搜尋起點底下的第一層子目錄加總，多的在前。"""
        counts = collections.Counter()
        for inst in (ej["nodes"].get(nid) or {}).get("instances", []):
            r = self._receipt(ej, (inst.get("attempts") or [{}])[-1]) or {}
            roots = r.get("paths") or [st["cwd"]]
            for path, n in (r.get("per_file") or {}).items():
                root = next((x for x in roots if path.startswith(x.rstrip("/") + "/")), None)
                if root is None:
                    continue
                first = os.path.relpath(path, root).split(os.sep)[0]
                counts[self._rel(st, os.path.join(root, first))] += n
        return [f"{p}（{n} 筆）" for p, n in counts.most_common(CANDIDATES_MAX)]

    # ---------------------------------------------------------------- 結束
    def _end(self, st, status, ej=None, note="", need=None):
        """結果：狀態、說明、要領域 session 決定的事，與每一版的圖跑過的節點實例（同一份結果只列一次）。"""
        st.update(status=status, note=note, need=need)
        st["outputs"] = self._outputs(st)
        self.note(f"🧱 {st['skill']}：{STATUS_TEXT[status]}" + (f"（{note[:100]}）" if note else ""))
        return st

    def _outputs(self, st):
        out, seen = [], set()
        ex = self._executor()
        for jid in st["edg_jobs"]:
            ej = ex.store.load(jid) or {}
            nodes = {n["id"]: n for g in st["graphs"] if g.get("edg_job") == jid for n in g["graph"]["nodes"]}
            for nid in ej.get("order") or []:
                nst, n = (ej.get("nodes") or {}).get(nid) or {}, nodes.get(nid) or {}
                for inst in nst.get("instances", []):
                    a = (inst.get("attempts") or [{}])[-1]
                    key = a.get("result_id") or (nid, json.dumps(inst.get("args"), ensure_ascii=False))
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"node": nid, "tool": n.get("tool"), "args": inst.get("args") or [], "state": inst.get("state"),
                                "reason": inst.get("reason", ""), "result_id": a.get("result_id"), "head": a.get("head", ""),
                                "why": n.get("why", ""), "report": n.get("report", "")})
        return out

    # ---------------------------------------------------------------- 小工具
    def _executor(self):
        return edg.Executor(self.agent, fixer=self.fixer)

    def _rel(self, st, path):
        cwd = st["cwd"] or "."
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
