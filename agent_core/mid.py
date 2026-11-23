"""新架構的中階（Domain Worker；D10 第 3 步的 3a，照 D3、D5 的中階、D6、D7；〈新架構討論紀錄〉第 4 節〈第 3 步〉）。

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
   - ask：問使用者（例如範圍太大：附各子目錄的筆數），回答之後照新的參數重新排圖；
   - switch：換成同一個領域的另一個複合技能（參數照寫好的對應帶過去），照它的骨架重新排圖（例：.py 裡沒有這個名稱、C++ 檔有）；
     換過去的技能答不了問題要的每一種就不換。
   重排最多 MID_REPLAN_MAX 次，再要重排就熔斷（circuit_break）；加的節點全都跑過＝不收斂，不再重排（D5 中 4）。
6. **判斷節點**（3b，模型；原文的整理與核對在 agent_core/judge.py）：低階跑到判斷節點就停（回退照舊先比），模型看原始問題、子目標、
   節點的 goal、它依賴的節點的原文（照收據從檔案讀，附行號），挑出回答問題的行（來源 #編號、檔案、一字不改的片段、標籤）、從節點列的
   分支選一條、填那條路的參數；程式核對片段在原文的某一行（行號與整行由程式填）、參數在原文裡，沒過的交回修一次。
   結束的路（沒有 add）就結束；有 add 的照分支加節點（id 加上第幾次）、後面接同一個判斷，交給低階重排（跑過的不重跑）。
   判斷每個工作最多 MID_JUDGE_MAX 次（另外算，不佔重排的次數），用完了還要接著做就熔斷；要接著找的都找過了＝不收斂，停（死路）。
7. **報告**（程式）：照收據整理（定義、呼叫、每個檔案的數量、總數，各附 #編號；search_text 的節點寫 lines 的再列提到的每一行與前後行，
   從檔案讀、列不下時先拿掉前後行）；判斷挑出的行（檔案:行號、#編號、整行）與經過；
   用了哪些回退、哪裡沒做完、自己補的參數。depends_on（硬性前置的複合技能）目前的技能都用不到，有技能用到時再做。
8. **上一次的經過**（4-2，〈新架構討論紀錄〉第 4 節〈第 4 步〉I）：同一個問題再交給這個領域時，高階把之前幾次的紀錄（技能、參數、結果、
   停下來的原因、找過的字、那一次的項目）交下來（previous）：挑技能與合約看得到這一節，判斷看得到之前找過的字；照一樣的技能與一樣的參數
   再跑一次結果也一樣，程式先把合約交回修一次（附原因），還是一樣就停（repeated，寫明跟第幾次一樣）。幾次之間用 previous、attempt 串起來。

每一次存在 logs/mid_jobs/<編號>/：job.json（選的技能、參數與原文、每一版的圖與節點的狀態、回退、換技能 switched、判斷 judgments、
問使用者的問題與回答 asked、結果）、report.md、events.jsonl、calls.jsonl（挑技能、合約與判斷的模型呼叫）。低階的執行（每個節點的嘗試、
收據、第 1 級）在 logs/edg_jobs/<edg_job>/。Web 的拓撲圖（web_app/topology.py）用這兩份。
"""
import collections
import json
import os
import re
import time

from . import edg, judge, prompt_files, skill_spec
from .config import (EDG_JOBS_DIRNAME, MID_CONTRACT_PREDICT, MID_JOBS_DIRNAME, MID_JOBS_KEEP, MID_JUDGE_LINES, MID_JUDGE_MAX,
                     MID_JUDGE_MODEL, MID_JUDGE_PREDICT, MID_MODEL, MID_REPLAN_MAX, MID_REPORT_LINES, MID_SELECT_PREDICT, NUM_CTX,
                     SUB_JOBS_DIRNAME)
from .jobstore import JobStore
from .schemas import mid_contract_schema, mid_judge_schema, mid_select_schema

TYPES = ("name", "text", "path", "glob", "names", "words")
KINDS = ("位置", "數量", "內容")       # 問題要的是哪幾種（挑技能時模型分類，複合技能的 answers 寫它答得了哪幾種）
STATUS_TEXT = {"done": "做完", "dead_end": "死路（照〈回退〉或判斷都沒有可以接著做的）",
               "circuit_break": f"熔斷（重排超過 {MID_REPLAN_MAX} 次，或判斷超過 {MID_JUDGE_MAX} 次）",
               "no_skill": "這個領域沒有適合的複合技能", "out_of_domain": "不屬於這個領域", "failed": "失敗", "need_user": "要問使用者",
               "cancelled": "使用者取消", "repeated": "跟之前的某一次一樣（同一個技能、同樣的參數，再跑一次結果也一樣），停"}
JUDGE_RESULT = {"done": "結束", "replanned": "照這條路加了節點，接著做", "no_new_nodes": "要接著找的都找過了（不收斂），停",
                "circuit_break": f"判斷已經 {MID_JUDGE_MAX} 次，還要接著做：停（熔斷）", "params_rejected": "這條路要填的值沒有通過核對，停",
                "no_lines": "這條路要有挑出的行，但挑的行都沒有通過核對", "no_input": "要看的節點沒有結果（0 筆），沒有判斷",
                "failed": "判斷的模型沒有回覆、回覆不是 JSON，或選了清單外的路"}
SWITCH_TYPES = {("name", "names"), ("name", "words"), ("names", "words"), ("words", "names")}   # 換技能時參數的種類可以這樣換（其他要一樣）
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


def searched(job):
    """一個工作找過的字：每一版的圖裡 search_text 節點的關鍵字（| 分開的每一個，照第一次出現的寫法）。高階交「上一次的經過」用。"""
    out = []
    for g in job.get("graphs") or []:
        for n in (g.get("graph") or {}).get("nodes") or []:
            args = n.get("args") or []
            if n.get("tool") == "search_text" and args and isinstance(args[0], str):
                for w in args[0].split("|"):
                    w = w.strip()
                    if w and w.lower() not in {x.lower() for x in out}:
                        out.append(w)
    return out


def _param_sig(values):
    """參數（{名稱: 值}）比對用的寫法：同一個技能、這個寫法一樣＝同樣的參數。"""
    return json.dumps({k: values[k] for k in sorted(values or {})}, ensure_ascii=False)


# =====================================================================================================================
# 領域與複合技能
# =====================================================================================================================
def load_domain(base_path, tools_dir, name):
    """skills_system/<領域>/SKILLS.md 與它列的複合技能 → {"name", "title", "intro", "skills": {名稱: 規格}, "catalog": {名稱: 那一行的說明},
    "tools", "practice", "problems"}。catalog 是高階分流看的入口技能（agent_core/orchestrator.py）；practice 是〈做法〉一節（現在的做法，
    只給子工作階段看，agent_core/sub.py）。沒有複合技能的領域照樣能用：交給它的問題在子工作階段裡一步一步做（第 5 步）。"""
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


def _arg_problems(nid, n, types, always, extra=None):
    """工具節點的參數裡用到的 {參數}：要宣告過；名稱清單放在 {"if": 名稱, "args": [...]} 裡（一項一組）；搜尋的字整個參數只寫 {名稱}
    （程式用 | 接成一個關鍵字）；可能沒有值的要放在 if 裡（或節點寫 if）。extra：判斷節點分支的參數（選了那條路就一定有值）。"""
    p, extra = [], extra or {}
    for a, group in _arg_strings(n.get("args", [])):
        for ref in _PARAM.findall(a):
            t = extra.get(ref) or types.get(ref)
            if t is None:
                p.append(f"{nid}：參數 {ref} 沒有宣告")
            elif t == "names" and group != ref:
                p.append(f"{nid}：名稱清單 {ref} 要放在 {{\"if\": \"{ref}\", \"args\": [...]}} 裡（一項一組）")
            elif t == "words" and (a != "{" + ref + "}" or group is not None):
                p.append(f"{nid}：搜尋的字 {ref} 要整個參數只寫 {{{ref}}}（程式用 | 接成一個關鍵字）")
            elif ref not in extra and ref not in always and ref not in (group, n.get("if")):
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
    if "report" in n and (not isinstance(n["report"], str) or n.get("tool") not in REPORTERS
                          or (n["tool"] == "code_ast_reader" and "--refs" not in n.get("args", []))):
        p.append(f"{nid}：report 寫報告裡的小標題；能當報告的是 {'、'.join(REPORTERS)}（code_ast_reader 要用 --refs）")
    if "lines" in n and (n["lines"] is not True or n.get("tool") != "search_text" or "report" not in n):
        p.append(f"{nid}：lines 只用在寫了 report 的 search_text 節點，寫 true（報告也列出提到的每一行與前後行）")
    return p + _arg_problems(nid, n, types, always)


def _branch_problems(jid, b, tools, topo, types, always):
    """判斷節點的一條路：id、say、參數（搜尋的字、檔案、行號；行號前面要有一個檔案）、add（工具節點：下一次判斷讀它的結果）。"""
    bid = b["id"]
    where = f"{jid}.{bid}"
    p = [] if str(b.get("say") or "").strip() else [f"{where}：要寫 say（給模型看的這條路的說明）"]
    if not isinstance(b.get("need_lines", False), bool):
        p.append(f"{where}：need_lines 要是 true 或 false（選這條路要有挑出的行）")
    bp, btypes = b.get("params") or [], {}
    for q in bp if isinstance(bp, list) else [None]:
        qn = q.get("name") if isinstance(q, dict) else None
        if not isinstance(qn, str) or not _IDENT.match(qn) or qn in btypes or qn in types:
            p.append(f"{where}：參數的名稱不合法、重複，或跟技能的參數同名：{qn!r}")
        elif q.get("type") not in judge.PARAM_TYPES:
            p.append(f"{where}：{qn} 的 type 只能是 {'、'.join(judge.PARAM_TYPES)}")
        else:
            if q["type"] == "line" and "path" not in btypes.values():
                p.append(f"{where}：行號 {qn} 前面要有一個檔案（path）的參數")
            btypes[qn] = q["type"]
    if list(btypes.values()).count("path") > 1:
        p.append(f"{where}：一條路最多一個檔案（path）的參數")
    add = b.get("add")
    if add is None:
        return p + ([f"{where}：沒有 add 的路（結束）不用填參數"] if btypes else [])
    if not isinstance(add, list) or not add:
        return p + [f"{where}：add 要是工具節點的陣列"]
    aids, used = set(), set()
    for n in add:
        aid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(aid, str) or not _IDENT.match(aid) or aid in aids or aid in tools or aid == jid:
            p.append(f"{where}：add 的節點 id 不合法，或跟其他節點重複：{aid!r}")
            continue
        aids.add(aid)
        if n.get("kind", "tool") != "tool" or n.get("tool") not in judge.READERS:
            p.append(f"{where}.{aid}：add 要是工具節點，而且是判斷讀得懂的工具（{'、'.join(judge.READERS)}）：下一次判斷讀它的結果")
            continue
        if n["tool"] not in topo["sub_skills"]:
            p.append(f"{where}.{aid}：工具 {n['tool']} 不在 topology 的 sub_skills")
        if any(d not in aids for d in n.get("depends_on") or []):
            p.append(f"{where}.{aid}：depends_on 只能是同一條路 add 的節點")
        if any(isinstance(a, dict) and "from" in a for a in n.get("args") or []):
            p.append(f"{where}.{aid}：參數不能從別的節點帶入（寫字串與 if 群組）")
        p += _arg_problems(f"{where}.{aid}", n, types, always, btypes)
        used |= {ref for a, _ in _arg_strings(n.get("args", [])) for ref in _PARAM.findall(a)}
    p += [f"{where}：參數 {q} 沒有用在 add 的節點" for q in btypes if q not in used]
    return p


def _judgment_problems(j, tools, topo, types, always):
    """判斷節點（3b）：goal、depends_on（〈骨架〉裡判斷讀得懂的工具節點）、labels（挑出的行可以標的種類）、branches（看完之後可以選的路，
    至少一條結束的路）。"""
    jid = j["id"]
    p = [] if str(j.get("goal") or "").strip() else [f"{jid}：判斷節點要寫 goal（要判斷什麼）"]
    deps = j.get("depends_on")
    if not isinstance(deps, list) or not deps or any(d not in tools for d in deps):
        p.append(f"{jid}：判斷節點的 depends_on 要是〈骨架〉的工具節點")
    else:
        p += [f"{jid}：判斷讀不懂 {d} 的工具 {tools[d].get('tool')}（讀得懂的：{'、'.join(judge.READERS)}）"
              for d in deps if tools[d].get("tool") not in judge.READERS]
    labels = j.get("labels")
    if not isinstance(labels, list) or not labels or not all(isinstance(x, str) and x.strip() for x in labels) or len(set(labels)) != len(labels):
        p.append(f"{jid}：labels 要是不重複的字串陣列（挑出的行可以標的種類）")
    branches = j.get("branches")
    if not isinstance(branches, list) or not branches:
        return p + [f"{jid}：branches 要是陣列（看完之後可以選的路）"]
    bids = set()
    for b in branches:
        bid = b.get("id") if isinstance(b, dict) else None
        if not isinstance(bid, str) or not _IDENT.match(bid) or bid in bids:
            p.append(f"{jid}：分支的 id 不合法或重複：{bid!r}")
            continue
        bids.add(bid)
        p += _branch_problems(jid, b, tools, topo, types, always)
    if not any(isinstance(b, dict) and b.get("add") is None for b in branches):
        p.append(f"{jid}：至少要有一條結束的路（沒有 add）")
    return p


def validate_skill(spec, tools_dir, domain_tools):
    """複合技能的規格寫得對不對 → 問題的清單（空的才能用）。最後用假的參數排一次圖（判斷節點每條路加的節點也排），交給低階的 validate 檢查。
    換技能（switch）的對象與參數的對應在 load_domain 核對（要看同一個領域的其他技能）。"""
    p = []
    meta, topo, params = spec["meta"], spec["topology"], spec["parameters"]
    if meta.get("type") != "Skill":
        p.append("type 要是 Skill")
    p += [f"缺少 {k}" for k in ("title", "description") if not meta.get(k)]
    if not isinstance(topo, dict) or not isinstance(topo.get("depends_on"), list) or not isinstance(topo.get("sub_skills"), list):
        return p + ["topology 要有 depends_on 與 sub_skills（陣列）"]
    if topo["depends_on"]:
        p.append("depends_on（硬性前置的複合技能）還沒接上：這個領域都是唯讀的，目前的技能用不到")
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
                                  and any("{value}" in a or "{stem}" in a for a in f["args"])):
            p.append(f"{n}：fetch 只用在路徑，寫成 {{\"tool\": 這個領域的工具, \"args\": [含 {{value}} 或 {{stem}} 的參數…]}}")
    nodes = (spec["skeleton"] or {}).get("nodes") if isinstance(spec["skeleton"], dict) else None
    fallbacks = spec["fallbacks"]
    if not isinstance(nodes, list) or not nodes:
        return p + ["〈骨架〉要有 nodes"]
    if not isinstance(fallbacks, list):
        return p + ["〈回退〉要是陣列"]
    adds = [n for fb in fallbacks if isinstance(fb, dict) for n in (fb.get("change") or {}).get("add") or []]
    ids, tools, judgments = set(), {}, []
    for n, added in [(x, False) for x in nodes] + [(x, True) for x in adds]:
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(n, dict) or nid in ids:
            p.append(f"節點要是物件、id 不能重複：{nid!r}")
            continue
        ids.add(nid)
        kind = n.get("kind", "tool")
        if kind == "judgment" and not added:
            judgments.append(n)
        elif kind == "judgment":
            p.append(f"{nid}：判斷節點只能寫在〈骨架〉（回退加的是工具節點）")
        elif kind != "tool":
            p.append(f"{nid}：kind 只能是 tool 或 judgment")
        else:
            tools[nid] = n
            p += _tool_problems(n, topo, types, always)
    if len(judgments) > 1:
        p.append("〈骨架〉最多一個判斷節點（判斷之後的步驟由分支加）")
    for j in judgments:
        p += _judgment_problems(j, {k: v for k, v in tools.items() if any(v is x for x in nodes)}, topo, types, always)
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
            p.append(f"回退 {fid}：change 要是 add（加節點）、ask（問使用者）或 switch（換技能）其中一個")
        elif "ask" in change and (change["ask"] not in types or change.get("from") not in ids | {None}):
            p.append(f"回退 {fid}：ask 要是宣告過的參數，from 要是節點")
        elif "switch" in change and (not isinstance(change["switch"], str) or not isinstance(change.get("params"), dict)
                                     or any(src not in types for src in change["params"].values())):
            p.append(f"回退 {fid}：switch 寫換過去的技能名稱，params 寫 {{換過去的參數: 這個技能的參數}}")
        if not fb.get("say"):
            p.append(f"回退 {fid}：要寫 say（給使用者與報告看的一句話）")
    if p:
        return p
    dummy = {n: (["d"] if t in ("names", "words") else "x") for n, t in types.items()}
    branch_nodes = []
    for j in judgments:
        for b in j["branches"]:
            local = dict(dummy, **{q["name"]: {"words": ["d"], "path": "x", "line": "1"}[q["type"]] for q in b.get("params") or []})
            expanded, _ = expand_nodes(b.get("add") or [], local)
            branch_nodes += [dict(n, id=f"{n['id']}_{b['id']}", depends_on=[f"{d}_{b['id']}" for d in n.get("depends_on") or []])
                             for n in expanded]
    graph = expand_nodes(nodes, dummy)[0] + expand_nodes(adds, dummy)[0] + branch_nodes
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


def _in_source(q, source, t):
    """抄的原文在問題或子目標裡：整段一字不改；名稱清單與搜尋的字的名稱常在原文不同的地方，可以是用「、」分開的幾段，每一段一字不改。"""
    src = _norm(source)
    if q in src:
        return True
    parts = [x.strip() for x in re.split(r"[、；;]", q) if x.strip()]
    return t in ("names", "words") and len(parts) > 1 and all(x in src for x in parts)


def verify_param(p, quote, value, source):
    """(值, 交回修的那一則) ：值是 None 表示沒提到或沒過（沒過時第二個是給模型的說明）。名稱清單的值是 list。
    原文要一字不改地在問題或子目標裡（名稱清單與搜尋的字可以是幾段，見 _in_source）；值照種類對原文：名稱、名稱清單與搜尋的字要原樣在原文裡；
    路徑的每一段（/ 分開）是原文裡的名稱（原文寫「a 的 b/ 底下」就是 a/b；原文沒有的上層目錄不能補）；文字與檔案名稱的寫法每一段英數字或
    中文都要在原文裡。"""
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
        items = judge.words_of(v)
        miss = [x for x in items if x not in q or not judge.WORD.match(x) or x.startswith("-")]
        return (items, None) if items and not miss else (None, _i("reject_words", name=name, missing="、".join(miss) or v, quote=q))
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
    if t == "words":
        items = judge.words_of(a)
        ok = items and all(judge.WORD.match(x) and not x.startswith("-") for x in items)
        return (items, None) if ok else (None, "每一個字只用文字、數字與 . / : @ ~ -（英文的詞組中間可以有一個空白），不以 - 開頭、不含 | 與括號；好幾個用「、」分開")
    return a, None


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
# 模型
# =====================================================================================================================
class ModelCaller:
    """一次模型呼叫：caller(role, system, user, schema, predict, log) → dict 或 None（沒有回覆、不是 JSON）；每次呼叫交給 log 記進 calls.jsonl。"""

    def __init__(self, agent):
        self.agent = agent

    def __call__(self, role, system, user, schema, predict, log):
        model = (MID_JUDGE_MODEL if role.startswith("judge") else "") or MID_MODEL or self.agent.model
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
        self._files = {}                        # 報告列提到的行時讀的檔案（judge.rows 的快取）

    # ---------------------------------------------------------------- 進入點
    def start(self, question, goal=None, items=None, on_start=None, previous=None, attempt=1):
        """items：高階交下來的要回答的項目（存進 job、列在報告開頭；挑技能與判斷先不看）。on_start(編號)：job 建好就呼叫
        （高階在執行中就把拓撲圖的連結推給畫面）。previous：同一個問題之前交給這個領域的經過（4-2：[{"n", "job", "skill", "params",
        "status", "note", "searched", "items"}]，高階從之前的工作取）；attempt：這是第幾次。"""
        jid = self.store.new_id()
        self.store.prune(MID_JOBS_KEEP)
        job = {"id": jid, "status": "running", "created": _now(), "updated": _now(), "cwd": self.agent.current_cwd,
               "domain": self.domain_name, "question": question, "goal": (goal or question).strip(), "items": list(items or []),
               "attempt": attempt, "previous": list(previous or []), "selection": None, "skill": None,
               "contract": None, "params": {}, "rejected": [], "auto_filled": [], "fetches": [], "graphs": [], "edg_job": None,
               "fallbacks": [], "applied": [], "added": [], "replans": 0, "switched": [], "judgments": [], "need_user": None, "asked": [],
               "result": None}
        self.store.save(job)
        for p in job["previous"]:                      # 4-2 的 I.4：上一次的工作記下這一次（決策圖從上一次連到下一次；上一次可能是子工作階段）
            store = self.store if p.get("kind", "mid") == "mid" else JobStore(os.path.join(self.agent.script_dir, "logs", SUB_JOBS_DIRNAME))
            pj = store.load(p.get("job")) if p.get("job") else None
            if pj:
                pj.setdefault("next", []).append({"job": jid, "n": attempt, "kind": "mid"})
                store.save(pj)
        if on_start:
            on_start(jid)
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

    def cancel(self, jid):
        """使用者不回答、取消要問人的工作：記在 asked，結束成 cancelled（報告寫明做到哪裡）。"""
        job = self.store.load(jid)
        if not job or job["status"] != "need_user":
            return job
        self._answered(job, cancelled=True)
        return self._finish(job, "cancelled", note=f"要問的是：{job['need_user']['question']}")

    # ---------------------------------------------------------------- 挑技能
    def _select(self, job, domain):
        names = list(domain["skills"])
        entries = "\n".join(_i("skill_entry", name=n, description=s["meta"]["description"], answers="、".join(s["answers"]),
                               when=s["sections"].get("什麼時候用", "").replace("\n", "\n  ")) for n, s in domain["skills"].items())
        # 5-3：挑技能、判斷屬不屬於這個領域只看這一層的子目標，原始問題是背景（以前看整個問題：子目標是讀設定檔，問題提到正在跑的系統就整題排除）
        parts = ([_i("goal", goal=job["goal"]), _i("select_question", question=job["question"])] if job["goal"] != job["question"]
                 else [_i("question", question=job["question"])])
        parts += [_i("domain", domain=domain["title"], intro=domain["intro"]), _i("skills", skills=entries)] + self._previous_part(job)
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
        params = spec["parameters"]
        out = self._contract_call(job, spec, None, "")
        job["contract"] = {"understanding": str(out.get("understanding") or "")}
        bad = {}
        for p in params:
            cell = out.get(p["name"]) if isinstance(out.get(p["name"]), dict) else {}
            value, why = self._verify(job, p, cell)
            if why:
                bad[p["name"]] = why
                job["rejected"].append({"param": p["name"], "round": 1, "quote": cell.get("quote"), "value": cell.get("value"), "why": why})
            elif value is not None:
                job["params"][p["name"]] = self._quoted(job, value, cell)
        for p in params:                        # 漏了的必填參數也交回修一次（原文的核對照舊：問題裡真的沒有，模型就只能留空）
            if p.get("required") and p["name"] not in job["params"] and p["name"] not in bad and not self._carried(job, p):
                bad[p["name"]] = _i("reject_missing", name=p["name"])
                job["rejected"].append({"param": p["name"], "round": 1, "quote": "", "value": "", "why": bad[p["name"]]})
        if bad:
            again = self._contract_call(job, spec, list(bad), "\n".join(bad.values()))
            for p in [x for x in params if x["name"] in bad]:
                cell = again.get(p["name"]) if isinstance(again.get(p["name"]), dict) else {}
                value, why = self._verify(job, p, cell)
                if why:
                    job["rejected"].append({"param": p["name"], "round": 2, "quote": cell.get("quote"), "value": cell.get("value"), "why": why})
                elif value is not None:
                    job["params"][p["name"]] = self._quoted(job, value, cell)
        self._carry_over(job, spec)
        self._note(job["id"], "🧭 合約：" + ("；".join(f"{k}＝{v['value']}" for k, v in job["params"].items()) or "原文沒有提到參數")
                   + (f"（{len(job['rejected'])} 個沒過核對）" if job["rejected"] else ""))

    def _contract_call(self, job, spec, only, rejected, note=""):
        kinds = {"name": _i("type_name"), "text": _i("type_text"), "path": _i("type_path"), "glob": _i("type_glob"),
                 "names": _i("type_names"), "words": _i("type_words")}
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
        if job.get("previous"):                 # 再交（第 5 步 G9）：參數只從這一次的子目標抄，原始問題只當背景
            parts = [_i("redispatch_goal", n=job.get("attempt") or len(job["previous"]) + 1, goal=job["goal"]),
                     _i("redispatch_question", question=job["question"])]
        else:
            parts = [_i("question", question=job["question"])] + ([_i("goal", goal=job["goal"])] if job["goal"] != job["question"] else [])
        parts += [_i("skill", name=spec["name"], title=spec["meta"]["title"], description=spec["meta"]["description"]),
                  _i("params", params="\n".join(rows))] + self._previous_part(job)
        if rejected:
            parts.append(_i("rejected", rejected=rejected))
        if note:                                       # 參數跟之前某一次一模一樣（_recontract）：整份重寫的原因
            parts.append(note)
        out = self.model("contract_fix" if only else "contract", prompt_files.load("mid/contract.md"), "\n\n".join(parts),
                         mid_contract_schema(spec["parameters"], only), MID_CONTRACT_PREDICT, self._log(job["id"]))
        return out or {}

    def _previous_part(self, job):
        """挑技能與合約的「上一次的經過」（同一個問題之前交給這個領域的每一次；第一次交的沒有這一節）。"""
        prev = job.get("previous") or []
        if not prev:
            return []
        rows = [_i("previous_attempt", n=p.get("n"), skill=p.get("skill") or "—", params=self._show_params(p.get("params")),
                   status=p.get("status_text") or STATUS_TEXT.get(p.get("status"), p.get("status") or "—"),
                   note=f"（{p['note']}）" if p.get("note") else "",
                   searched="、".join(p.get("searched") or []) or "—", items="；".join(p.get("items") or []) or "—") for p in prev]
        return [_i("previous", count=len({p.get("n") for p in prev}), attempts="\n".join(rows))]

    @staticmethod
    def _show_params(values):
        return "；".join(f"{k}＝{Worker._show(v)}" for k, v in (values or {}).items()) or "—"

    @staticmethod
    def _quote_source(job):
        """合約的原文：第一次是問題與子目標；再交（附了上一次的經過）時只有這一次的子目標（第 5 步 G9：4-2 時 26b 再交 31 次裡 22 次換了子目標，
        合約卻照原始問題抄一樣的參數，再交沒有換做法）。"""
        return job["goal"] if job.get("previous") else job["question"] + "\n" + job["goal"]

    def _verify(self, job, p, cell):
        """verify_param 照 _quote_source 的原文核對；再交時抄了原始問題（不是子目標）的，交回的說明寫明這次只從子目標抄。"""
        value, why = verify_param(p, cell.get("quote"), cell.get("value"), self._quote_source(job))
        q = _unquote(cell.get("quote"))
        if why and job.get("previous") and q and _in_source(q, job["question"], p["type"]):
            why = _i("reject_quote_goal", name=p["name"], quote=q)
        return value, why

    @staticmethod
    def _quoted(job, value, cell):
        return {"value": value, "quote": _unquote(cell.get("quote")), "source": "goal" if job.get("previous") else "question"}

    @staticmethod
    def _carried(job, p):
        """再交時這個參數之前最近一次同一個技能用過的值（沒有回 None）。"""
        for prev in reversed(job.get("previous") or []):
            if prev.get("skill") == job["skill"] and p["name"] in (prev.get("params") or {}):
                return prev
        return None

    def _carry_over(self, job, spec):
        """再交時子目標沒提到的參數沿用之前最近一次同一個技能的值（第 5 步 G9）；之後照舊補預設值、自己查、問使用者。"""
        for p in spec["parameters"]:
            prev = None if p["name"] in job["params"] else self._carried(job, p)
            if prev:
                job["params"][p["name"]] = {"value": prev["params"][p["name"]], "quote": "", "source": "previous", "from": prev.get("n")}

    def _same_as_before(self, job):
        """這次的技能與參數跟之前哪一次一模一樣：回傳那一次的紀錄，沒有回 None。"""
        mine = _param_sig({k: v["value"] for k, v in job["params"].items()})
        return next((p for p in job.get("previous") or [] if p.get("skill") == job["skill"] and _param_sig(p.get("params")) == mine), None)

    def _recontract(self, job, spec, same):
        """參數跟之前某一次一模一樣：整份合約交回修一次（附那一次的結果與原因），照原本的核對重來（之前補的、查的不留）。"""
        reason = _i("reject_same", n=same.get("n"), skill=same.get("skill") or "—", params=self._show_params(same.get("params")),
                    status=STATUS_TEXT.get(same.get("status"), same.get("status") or "—"))
        out = self._contract_call(job, spec, None, "", note=reason)
        job["params"] = {}
        for p in spec["parameters"]:
            cell = out.get(p["name"]) if isinstance(out.get(p["name"]), dict) else {}
            value, why = self._verify(job, p, cell)
            if why:
                job["rejected"].append({"param": p["name"], "round": 3, "quote": cell.get("quote"), "value": cell.get("value"), "why": why})
            elif value is not None:
                job["params"][p["name"]] = self._quoted(job, value, cell)
        self._carry_over(job, spec)
        job["same_as"] = {"n": same.get("n"), "job": same.get("job"), "fixed": True}
        self._note(job["id"], f"🧭 參數跟第 {same.get('n')} 次一樣，合約重寫一次：" + ("；".join(f"{k}＝{v['value']}" for k, v in job["params"].items())
                                                                              or "原文沒有提到參數"))

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
        """照 fetch 查一次 → (候選, 全部找到的)；都是相對於工作目錄的路徑。{value} 是原文的最後一段、{stem} 是它去掉副檔名；
        候選＝路徑結尾跟原文一樣，或檔名就是查的那個名稱、原文前面的每一段照順序都在路徑裡（「a 的 X 規格書」查 X.md：
        a/…/X.md 算，名稱含 X.md 的 test_X.md 不算）。"""
        f = p["fetch"]
        last = os.path.basename(value.rstrip("/")) or value
        args = [a.replace("{value}", last).replace("{stem}", os.path.splitext(last)[0] or last) for a in f["args"]]
        name = args[0] if args and not any(c in args[0] for c in "*?[/") else None
        ej = self._executor().start({"goal": f"找「{value}」在工作目錄的哪裡（{p['desc']}）",
                                     "nodes": [{"id": "fetch", "tool": f["tool"], "args": args, "expect": ["pass", "empty"]}]})
        found = []
        for inst in ej["nodes"].get("fetch", {}).get("instances", []):
            r = self._receipt(ej, (inst.get("attempts") or [{}])[-1]) or {}
            found += [self._rel(job, it["path"]) for it in r.get("items") or [] if it.get("path")]
        exact = [x for x in found if x == value or x.endswith("/" + value) or (name and _named(x, value, name))]
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
        if not job["graphs"] and job.get("previous"):          # 4-2：跟之前一模一樣的做法不再跑一次（先交回合約修一次）
            same = self._same_as_before(job)
            if same and not (job.get("same_as") or {}).get("fixed"):
                self._recontract(job, spec, same)
                need = self._complete(job, spec)
                if need:
                    return self._wait(job, need)
                same = self._same_as_before(job)
            if same:
                job["same_as"] = dict(job.get("same_as") or {}, n=same.get("n"), job=same.get("job"), still=True)
                return self._finish(job, "repeated", note=f"跟第 {same.get('n')} 次一樣（做法 {job['skill']}；"
                                                           f"{self._show_params({k: v['value'] for k, v in job['params'].items()})}），"
                                                           f"那一次的結果：{STATUS_TEXT.get(same.get('status'), same.get('status') or '—')}")
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
            if "switch" in fb["change"]:
                target = domain["skills"][fb["change"]["switch"]]
                missing = [a for a in (job["selection"] or {}).get("asks") or [] if a not in target["answers"]]
                if missing:
                    entry["result"] = "cannot_answer"
                    self._note(job["id"], f"🔁 第 2 級：{fb['id']} 換過去的 {target['name']} 答不了「{'、'.join(missing)}」，不換")
                    continue
                if job["replans"] >= MID_REPLAN_MAX:
                    entry["result"] = "circuit_break"
                    return self._finish(job, "circuit_break", ej, note=f"還要套用 {fb['id']}，但已經重排 {job['replans']} 次")
                return self._switch(job, domain, fb, target, entry)
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
        if ej["status"] == "judgment":
            return self._judgment(job, domain, ej)
        return self._finish(job, "done" if ej["status"] == "done" else "dead_end", ej)

    def _switch(self, job, domain, fb, target, entry):
        """換技能（回退的 switch）：參數照對應帶過去（名稱換成清單），之後照換過去的技能補參數、照它的骨架重排（算一次重排）。"""
        old, types = job["skill"], {p["name"]: p["type"] for p in target["parameters"]}
        params = {}
        for dst, src in fb["change"]["params"].items():
            cur = job["params"].get(src)
            if cur is None or _empty(cur["value"]):
                continue
            v = cur["value"]
            params[dst] = {"value": [v] if types[dst] in ("names", "words") and not isinstance(v, list) else v, "source": "switch",
                           "from": src, "checked": bool(cur.get("checked"))}
        job["switched"].append({"from": old, "to": target["name"], "fallback": fb["id"], "version": len(job["graphs"]), "time": _now(),
                                "params": {k: v["value"] for k, v in params.items()}})
        entry.update(result="switched", to=target["name"])
        job.update(skill=target["name"], params=params, applied=[], added=[],
                   rebuild={"kind": "switch", "fallback": fb["id"], "from": old, "to": target["name"], "say": fb["say"]})
        self._note(job["id"], f"🔁 第 2 級：{fb['id']}（{fb['say'][:60]}），換技能 {old} → {target['name']}")
        return self._proceed(job, domain)

    # ---------------------------------------------------------------- 判斷節點（3b）
    @staticmethod
    def _judged(job):
        return sum(1 for j in job.get("judgments") or [] if j["round"])

    def _input_key(self, ej, node):
        return [f"{d}:{a.get('result_id')}" for d in node.get("depends_on") or []
                for inst in (ej["nodes"].get(d) or {}).get("instances", []) for a in (inst.get("attempts") or [])[-1:]]

    def _pending(self, job, ej, graph):
        """還沒判斷的判斷節點（照低階交回的順序第一個）：同一個節點、同樣的輸入判斷過的不算（重排之後沿用的那幾個）。"""
        done = {(j["node"], tuple(j["input_key"])) for j in job["judgments"]}
        for j in ej.get("judgments") or []:
            node = graph.get(j["node"])
            if node and (node["id"], tuple(self._input_key(ej, node))) not in done:
                return node
        return None

    def _sources(self, job, ej, graph, node):
        """判斷節點要看的原文：它依賴的節點每個實例最後一次嘗試一份（#編號），行照收據從檔案讀（agent_core/judge.py）。"""
        out, cache = [], {}
        for d in node["depends_on"]:
            tool = graph[d].get("tool")
            for k, (inst, a, r) in enumerate(self._instances(ej, d)):
                rows = judge.rows(tool, r, cache)
                for row in rows:
                    row["file"] = self._rel(job, row["path"])
                if tool == "search_text":
                    what = _i("judge_what_search", pattern=(r or {}).get("pattern", ""), hits=((r or {}).get("counts") or {}).get("hits", 0),
                              scope="、".join(self._rel(job, x) for x in (r or {}).get("paths") or []) or ".")
                else:
                    c = (r or {}).get("counts") or {}
                    what = _i("judge_what_view", file=self._rel(job, (r or {}).get("path") or inst["args"][0]), start=c.get("from"), end=c.get("to"))
                out.append({"id": f"#{a['result_id']}" if a.get("result_id") else f"#{d}.{k + 1}", "node": d, "tool": tool, "what": what,
                            "context": int(((r or {}).get("options") or {}).get("context") or 0), "rows": rows})
        return out

    def _judgment(self, job, domain, ej):
        """判斷節點：模型挑行、選路（_judge），程式核對；結束的路就結束，有 add 的接著排（_next_round）。"""
        graph = {n["id"]: n for n in job["graphs"][-1]["graph"]["nodes"]}
        node = self._pending(job, ej, graph)
        if node is None:
            return self._finish(job, "done", ej)
        sources = self._sources(job, ej, graph, node)
        base = {"node": node["id"], "version": len(job["graphs"]), "time": _now(), "input_key": self._input_key(ej, node),
                "inputs": [{"node": x["node"], "source": x["id"]} for x in sources]}
        if not any(x["rows"] for x in sources):
            job["judgments"].append(dict(base, round=0, result="no_input", lines=[], rejected=[], params={}, param_rejected=[]))
            self._note(job["id"], f"⚖️ 判斷 {node['id']}：{JUDGE_RESULT['no_input']}")
            return self._finish(job, "done", ej, note=f"判斷節點 {node['id']}：{JUDGE_RESULT['no_input']}")
        if self._judged(job) >= MID_JUDGE_MAX:
            return self._finish(job, "circuit_break", ej, note=f"已經判斷 {MID_JUDGE_MAX} 次，{node['id']} 還要判斷")
        entry = self._judge(job, domain, node, sources, base)
        job["judgments"].append(entry)
        branch = next((b for b in node["branches"] if b["id"] == entry["branch"]), None)
        self._note(job["id"], f"⚖️ 判斷 {node['id']}（第 {entry['round']} 次）：{entry['branch'] or '—'}，挑了 {len(entry['lines'])} 行"
                              + (f"（{len(entry['rejected'])} 行沒過核對）" if entry["rejected"] else ""))
        if branch is None:
            entry["result"] = "failed"
            return self._finish(job, "failed", ej, note=f"判斷 {node['id']}：{JUDGE_RESULT['failed']}")
        if branch.get("add") is None:
            if branch.get("need_lines") and not any(j.get("lines") for j in job["judgments"]):     # 之前的判斷挑的行也算
                entry["result"] = "no_lines"
                return self._finish(job, "dead_end", ej, note=f"判斷 {node['id']} 選了 {branch['id']}：{JUDGE_RESULT['no_lines']}")
            entry["result"] = "done"
            return self._finish(job, "done", ej, note=f"判斷 {node['id']}：{branch['say']}")
        if entry["param_rejected"]:
            entry["result"] = "params_rejected"
            return self._finish(job, "dead_end", ej, note=f"判斷 {node['id']} 選了 {branch['id']}：{JUDGE_RESULT['params_rejected']}")
        return self._next_round(job, domain, ej, node, branch, entry)

    def _judge(self, job, domain, node, sources, base):
        """判斷一次：模型挑行、選路、填參數；程式核對，沒過的交回修一次（只重寫沒過的：挑的行重抄；參數沒過時可以重選路）。"""
        used, omitted = judge.select(sources)
        files, sids = judge.shown_files(sources), [x["id"] for x in sources if any(r["shown"] for r in x["rows"])]
        entry = dict(base, round=self._judged(job) + 1, shown={"chars": used, "rows": sum(r["shown"] for x in sources for r in x["rows"]),
                                                               "omitted": omitted},
                     understanding="", lines=[], rejected=[], branch=None, say="", params={}, param_rejected=[], reason="", result=None)
        system, user = prompt_files.load("mid/judge.md", lines=MID_JUDGE_LINES), self._judge_message(job, domain, node, sources, omitted)
        out = self.model("judge", system, user, mid_judge_schema(sids, files, node["labels"], node["branches"], MID_JUDGE_LINES),
                         MID_JUDGE_PREDICT, self._log(job["id"]))
        if not out:
            return entry
        entry.update(understanding=str(out.get("understanding") or ""), reason=str(out.get("reason") or ""))
        picked = [x for j in job["judgments"] for x in j.get("lines") or []]
        bad_lines = self._take_lines(entry, out.get("lines"), sources, 1, picked)
        branch = next((b for b in node["branches"] if b["id"] == out.get("branch")), None)
        params, bad_params = judge.check_params(branch, out.get("params"), sources, picked) if branch else ({}, [])
        if branch and branch.get("add") is not None and not bad_params:
            bad_params = self._stale(job, domain, branch, params)
        if bad_lines or bad_params:
            fix = self.model("judge_fix", system, user + "\n\n" + _i("judge_rejected", rejected="\n".join(bad_lines + bad_params)),
                             mid_judge_schema(sids, files, node["labels"], node["branches"], MID_JUDGE_LINES, fix_lines=bool(bad_lines),
                                              fix_branch=bool(bad_params)), MID_JUDGE_PREDICT, self._log(job["id"])) or {}
            if bad_lines:
                self._take_lines(entry, fix.get("lines"), sources, 2, picked)
            again = next((b for b in node["branches"] if b["id"] == fix.get("branch")), None) if bad_params else None
            if again:
                p2, bad2 = judge.check_params(again, fix.get("params"), sources, picked)
                bad2 = bad2 or (self._stale(job, domain, again, p2) if again.get("add") is not None else [])
                branch, params, bad_params = (again, p2, []) if not bad2 else (branch, params, bad_params + bad2)
        entry.update(branch=branch["id"] if branch else None, say=branch["say"] if branch else "", params=params, param_rejected=bad_params)
        return entry

    @staticmethod
    def _take_lines(entry, items, sources, rnd, picked):
        """模型挑的行逐一核對：過的加進 entry["lines"]（同一行只留一次、之前的判斷挑過的不再加，最多 MID_JUDGE_LINES 行），沒過的記原因；
        回傳這一輪沒過的說明。"""
        bad, before = [], {(x["path"], x["line"]) for x in picked}
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            line, why = judge.check_line(item, sources, picked)
            if why:
                bad.append(why)
                entry["rejected"].append({"round": rnd, "item": item, "why": why})
            elif ((line["path"], line["line"]) not in {(x["path"], x["line"]) for x in entry["lines"]} | before
                  and len(entry["lines"]) < MID_JUDGE_LINES):
                entry["lines"].append(dict(line, round=rnd))
        return bad

    def _judge_message(self, job, domain, node, sources, omitted):
        parts = [_i("question", question=job["question"])] + ([_i("goal", goal=job["goal"])] if job["goal"] != job["question"] else [])
        parts.append(_i("judge_goal", goal=node["goal"]))
        picked = [x for j in job["judgments"] for x in j.get("lines") or []]
        if picked:
            parts.append(_i("judge_picked", picked="\n".join(_i("judge_picked_line", file=x["file"], line=x["line"], label=x["label"], text=x["text"])
                                                           for x in picked)))
        searched = self._searched(job, domain)
        if searched:
            parts.append(_i("judge_searched", words="、".join(searched)))
        before = [w for p in job.get("previous") or [] for w in p.get("searched") or []]
        if before:
            parts.append(_i("judge_searched_before", words="、".join(dict.fromkeys(before))))
        text = judge.render(sources)
        if omitted:
            text += "\n" + _i("judge_omitted", omitted="；".join(f"{sid} 的 {f} {n} 行" for sid, fs in omitted.items() for f, n in fs.items()))
        parts += [_i("judge_sources", sources=text), _i("judge_labels", labels="、".join(node["labels"])),
                  _i("judge_branches", branches="\n".join(self._branch_text(b) for b in node["branches"]))]
        return "\n\n".join(parts)

    @staticmethod
    def _branch_text(b):
        if not b.get("params"):
            return _i("judge_branch", id=b["id"], say=b["say"])
        kinds = {"words": lambda n: _i("judge_param_words", name=n), "path": lambda n: _i("judge_param_path", name=n),
                 "line": lambda n: _i("judge_param_line", name=n)}
        return _i("judge_branch_params", id=b["id"], say=b["say"], params="、".join(kinds[q["type"]](q["name"]) for q in b["params"]))

    @staticmethod
    def _searched(job, domain, upto=None):
        """這個工作找過的字（照第一次出現的寫法）：技能的搜尋的字（words），加上判斷要接著找的（upto＝只算前幾次判斷）。"""
        out = []
        words = [w for p in domain["skills"][job["skill"]]["parameters"] if p["type"] == "words"
                 for w in (job["params"].get(p["name"]) or {}).get("value") or []]
        for w in words + [w for j in job["judgments"][:upto] for w in j.get("chase") or []]:
            if w.lower() not in {x.lower() for x in out}:
                out.append(w)
        return out

    def _stale(self, job, domain, branch, params, upto=None):
        """選的路照參數排出來會不會有新的結果：要接著找的字都找過了，或加的節點都跑過了 → 交回修的說明（空的＝會有新的結果）。
        判斷的時候先核對（沒過的交回修一次，可以重選路）；排下一版時再核對一次（upto=-1：不算這一次的判斷自己）。"""
        words = [w for q in branch.get("params") or [] if q["type"] == "words" for w in params.get(q["name"], [])]
        if words and {w.lower() for w in words} <= {w.lower() for w in self._searched(job, domain, upto)}:
            return [_i("reject_param_searched", words="、".join(words))]
        add, _ = expand_nodes(branch["add"], dict({k: v["value"] for k, v in job["params"].items()}, **params))
        ran = {_node_key(n) for g in job["graphs"] for n in g["graph"]["nodes"]}
        return [_i("reject_branch_ran", branch=branch["id"])] if all(_node_key(n) in ran for n in add) else []

    def _next_round(self, job, domain, ej, node, branch, entry):
        """有 add 的路：加的節點（id 加上下一次判斷是第幾次）、後面接同一個判斷，交給低階重排。判斷用完了熔斷；要接著找的都找過了不收斂。"""
        if self._judged(job) >= MID_JUDGE_MAX:
            entry["result"] = "circuit_break"
            return self._finish(job, "circuit_break", ej, note=f"判斷已經 {MID_JUDGE_MAX} 次，還要接著做：{branch['id']}（{branch['say']}）")
        k = self._judged(job) + 1
        entry["chase"] = [w for q in branch.get("params") or [] if q["type"] == "words" for w in entry["params"].get(q["name"], [])]
        if self._stale(job, domain, branch, entry["params"], upto=-1):
            entry["result"] = "no_new_nodes"
            return self._finish(job, "dead_end", ej, note=f"判斷 {node['id']} 選了 {branch['id']}：{JUDGE_RESULT['no_new_nodes']}")
        add, _ = expand_nodes(branch["add"], dict({key: v["value"] for key, v in job["params"].items()}, **entry["params"]))
        rename = {n["id"]: f"{n['id']}_{k}" for n in add}
        for n in add:
            n.update(id=rename[n["id"]], **({"depends_on": [rename.get(d, d) for d in n["depends_on"]]} if n.get("depends_on") else {}))
        template = node.get("template") or node["id"]
        nxt = dict(node, id=f"{template}_{k}", template=template, depends_on=[n["id"] for n in add])
        entry.update(result="replanned", added=[n["id"] for n in add] + [nxt["id"]])
        graph = {"goal": job["goal"], "nodes": job["graphs"][-1]["graph"]["nodes"] + add + [nxt]}
        return self._run(job, domain, graph, {"kind": "judgment", "node": node["id"], "branch": branch["id"], "say": branch["say"],
                                              "params": entry["params"], "added": entry["added"]})

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
        if job.get("goal") and job["goal"] != job["question"]:
            lines.append(f"- 子目標：{job['goal']}")
        lines += [f"- 要回答的項目 {k}：{x}" for k, x in enumerate(job.get("items") or [], 1)]
        if job.get("previous"):
            lines.append(f"- 第 {job.get('attempt') or len(job['previous']) + 1} 次交給這個領域（之前：" + "；".join(
                f"第 {p.get('n')} 次 {p.get('skill') or '—'}：{p.get('status_text') or STATUS_TEXT.get(p.get('status'), p.get('status') or '—')}"
                for p in job["previous"]) + "）")
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
        if job.get("judgments"):
            lines += self._render_judgments(job)
        if job["fallbacks"]:
            result = {"replanned": "重排", "no_new_nodes": "排出來的節點都跑過了，沒有重排", "ask": "問使用者", "circuit_break": "熔斷",
                      "switched": "換技能", "cannot_answer": "換過去的技能答不了，沒有換"}
            lines += ["", "## 第 2 級（回退）"] + [f"- {f['fallback']}：{f['say']}（{result.get(f.get('result'), '')}）" for f in job["fallbacks"]]
        stops = [(nid, st) for nid, st in ej["nodes"].items() if st["state"] in edg.BAD]
        if stops:
            lines += ["", "## 沒有做完的節點"] + [f"- {nid}：{st['state']}（{st.get('reason', '')}）" for nid, st in stops]
        return "\n".join(lines)

    def _render_judgments(self, job):
        """判斷挑出的行（每一次的合起來，同一行只列一次）與每一次判斷的經過。"""
        picked, seen = [], set()
        for j in job["judgments"]:
            for x in j.get("lines") or []:
                if (x["path"], x["line"]) not in seen:
                    seen.add((x["path"], x["line"]))
                    picked.append(x)
        out = ["", "## 判斷挑出的行（模型挑的；檔案、行號與內容由程式從原文取）"]
        out += [f"- {x['file']}:{x['line']}（{x['label']}，{x['source']}）：{x['text']}" for x in picked] or ["- 沒有挑出通過核對的行"]
        out += ["", "## 判斷的經過"]
        for j in job["judgments"]:
            if not j["round"]:
                out.append(f"- {j['node']}：{JUDGE_RESULT[j['result']]}")
                continue
            ps = "；".join(f"{k}＝{self._show(v)}" for k, v in (j.get("params") or {}).items())
            rej = len(j.get("rejected") or []) + len(j.get("param_rejected") or [])
            out.append(f"- 第 {j['round']} 次（{j['node']}）：" + (f"{j['branch']}（{j['say']}）" if j.get("branch") else "沒有選")
                       + (f"：{ps}" if ps else "") + f"；挑了 {len(j.get('lines') or [])} 行" + (f"（{rej} 個沒有通過核對）" if rej else "")
                       + f"；{JUDGE_RESULT.get(j.get('result'), '')}" + (f"；理由：{j['reason']}" if j.get("reason") else ""))
        return out

    @staticmethod
    def _show(v):
        return "、".join(str(x) for x in v) if isinstance(v, list) else str(v)

    @staticmethod
    def _source(v):
        return {"question": f"原文「{v.get('quote', '')}」", "goal": f"子目標「{v.get('quote', '')}」", "default": "預設",
                "fetch": "自己查到的", "user": "使用者回答", "switch": f"換技能時從 {v.get('from', '')} 帶過來",
                "previous": f"沿用第 {v.get('from', '')} 次"}.get(v["source"], v["source"])

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
                + (f"（類別 {d['in_class']} 的方法）" if d.get("in_class") else "") + f"，行 {d['line']}-{d.get('end', d['line'])}"
                + (f"（裝飾器在行 {d['decorator']}）" if d.get("decorator") else "")
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
        """search_text：範圍、每個檔案的筆數（收據記全部的檔案）、總共幾筆；逾時沒搜完要寫。節點寫 lines 的再列提到的每一行與前後行
        （_hit_lines）。"""
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
                if node.get("lines"):
                    out += self._hit_lines(job, r, a.get("result_id"))
            if r.get("timed_out"):
                out.append("- 逾時沒有搜完：上面的數字不是全部")
        return out

    def _hit_lines(self, job, receipt, rid):
        """提到的每一行與前後行（收據的 -C）：程式照收據從檔案讀（judge.rows），每行寫成「檔案:行號：內容」（主模型照這個寫出處）；
        超過 MID_REPORT_LINES 行時先拿掉前後行，還是列不下的寫明還有幾行、在哪個 #編號。"""
        rows = judge.rows("search_text", receipt, self._files)
        ctx = int((receipt.get("options") or {}).get("context") or 0)
        dropped = bool(ctx) and len(rows) > MID_REPORT_LINES
        if dropped:
            rows = [r for r in rows if r["hit"]]
        mark = bool(ctx) and not dropped
        head = ("- 提到的行（檔案:行號：內容，由程式從檔案取" + (f"；標「提到」的是那一行，其他是前後 {ctx} 行" if mark else "")
                + ("；行太多，前後行沒有列" if dropped else "") + "）：")
        body = [f"    - {self._rel(job, r['path'])}:{r['line']}" + ("（提到）" if mark and r["hit"] else "") + f"：{r['text']}" for r in rows]
        return [head] + (self._cap(body, [rid] if rid else []) if body else ["    - 檔案讀不到，沒有列（見收據）"])

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
