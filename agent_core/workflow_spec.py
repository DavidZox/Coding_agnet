"""工作流的規格（skills_system/workflows/<名稱>.md，OKF type: Workflow）：解析與驗證。純函式，不呼叫模型、不執行技能。

格式跟技能規格同一套 OKF，type 不同；文本是給人看、也給模型當錨點的，但步驟由程式照文本推進（agent_core/workflow.py）：

    ---
    type: Workflow
    title: 工作包卡住的處理
    description: 工作包卡住：查原因；完成訊號遺失就補發、等它跑完、寫處理紀錄（SKILLS.md 的一行描述）
    version: 0.1.0
    dependencies: ["workpackage_status", "rmf_handshake", "file_ops"]      # 步驟用到的技能（程式核對）
    changes_state: true                                                     # 有沒有會改變狀態的步驟（程式核對）
    ---
    # 用途
    # 需要的資訊
    * `{wp_id}`：工作包編號（例：`WP_L2`）
    * `{note_file}`：處理紀錄寫到哪個檔案（選填）                          # 選填：沒給時用到它的步驟略過
    * `{note_file}`：…（選填，預設 `ops_notes/{today}.md`）                # 選填有預設值；{today}／{now} 是內建的
    # 步驟
    1. 【執行】查狀態：`EXECUTE: scripts/workpackage_status_cmd.py {wp_id}`　檢查：輸出有「[PASS]」
    2. 【檢查】看第 1 步：「已完成」→ 結束；「完成訊號多半遺失了」→ 第 4 步；其他 → 第 3 步
    3. 【確認】<要使用者確認什麼>                                           # 工作流停下來，使用者確認後 workflow_run --continue
    4. 【執行】補發：`EXECUTE: scripts/rmf_handshake_cmd.py fin {robot}`  # {robot} 不在需要的資訊：執行時由模型依前面的輸出決定（判斷點）
    5. 【告知】<要回報什麼>
    # 成功判準
    * `EXECUTE: scripts/workpackage_status_cmd.py {wp_id}` 輸出有「COMPLETED」
    * 第 4 步的輸出有「已經由 manual_trigger 補發」
    # 異常與注意事項

規則（validate 檢查）：步驟從 1 連號；【執行】一定有 `EXECUTE: scripts/…`，腳本要存在；【檢查】的分支只能往後跳（沒有迴圈），
「看第 N 步」只能看前面的【執行】步；沒有分支的【檢查】是關卡（模型判斷繼續或結束）；檢查與分支的條件是「輸出有這幾個字」
（「A」或「B」＝其中一個）。"""
import json
import os
import re

BUILTIN = ("today", "now")
KINDS = ("執行", "檢查", "確認", "告知")
_FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
_SECTION_RE = re.compile(r"^# (.+)$", re.M)
_STEP_RE = re.compile(r"^(\d+)\.\s*【(執行|檢查|確認|告知)】\s*(.*)$")
_CMD_RE = re.compile(r"`EXECUTE:\s*(scripts/[A-Za-z0-9_]+\.py)([^`]*)`")
_CHECK_RE = re.compile(r"檢查：\s*輸出有\s*((?:「[^」]+」\s*(?:或\s*)?)+)")
_QUOTED_RE = re.compile(r"「([^」]+)」")
_BRANCH_RE = re.compile(r"((?:「[^」]+」\s*(?:或\s*)?)+|其他)\s*→\s*(?:第\s*(\d+)\s*步|(結束))")
_SOURCE_RE = re.compile(r"看第\s*(\d+)\s*步")
_INPUT_RE = re.compile(r"^\*\s*`\{([A-Za-z_][A-Za-z0-9_]*)\}`\s*[：:]\s*(.*)$")
_DEFAULT_RE = re.compile(r"預設\s*`([^`]*)`")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SUCCESS_STEP_RE = re.compile(r"第\s*(\d+)\s*步的輸出有\s*((?:「[^」]+」\s*(?:或\s*)?)+)")
_SUCCESS_EXPECT_RE = re.compile(r"輸出有\s*((?:「[^」]+」\s*(?:或\s*)?)+)")


def _front(text):
    m = _FRONT_RE.match(text)
    meta = {}
    if not m:
        return meta, text
    for ln in m.group(1).splitlines():
        k, sep, v = ln.partition(":")
        if not sep:
            continue
        v = v.strip()
        if v.startswith("["):
            try:
                v = json.loads(v)
            except ValueError:
                pass
        elif v.lower() in ("true", "false"):
            v = v.lower() == "true"
        meta[k.strip()] = v
    return meta, text[m.end():]


def _sections(body):
    out, heads = {}, list(_SECTION_RE.finditer(body))
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        out[h.group(1).strip()] = body[h.end():end].strip("\n")
    return out


def _quoted(text):
    return [q.strip() for q in _QUOTED_RE.findall(text or "") if q.strip()]


def parse(text, name="", path=""):
    """規格原文 → dict：name、path、meta、purpose、inputs、steps、success、pitfalls、errors（解析時就看得出的問題）。"""
    meta, body = _front(text)
    sec = _sections(body)
    wf = {"name": name, "path": path, "meta": meta, "title": str(meta.get("title") or name), "description": str(meta.get("description") or ""),
          "purpose": sec.get("用途", "").strip(), "inputs": [], "steps": [], "success": [], "pitfalls": [], "errors": []}
    for ln in sec.get("需要的資訊", "").splitlines():
        m = _INPUT_RE.match(ln.strip())
        if not m:
            continue
        desc = m.group(2).strip()
        d = _DEFAULT_RE.search(desc)
        wf["inputs"].append({"name": m.group(1), "description": desc, "optional": "選填" in desc, "default": d.group(1) if d else None})
    raw_steps, cur = [], None
    for ln in sec.get("步驟", "").splitlines():
        m = _STEP_RE.match(ln.strip())
        if m:
            cur = {"n": int(m.group(1)), "kind": m.group(2), "text": m.group(3).strip()}
            raw_steps.append(cur)
        elif cur is not None and ln.strip():
            cur["text"] += " " + ln.strip()
    for s in raw_steps:
        text = s["text"]
        step = {"n": s["n"], "kind": s["kind"], "text": text, "title": re.split(r"[：:`（(]", text, maxsplit=1)[0].strip() or s["kind"]}
        if s["kind"] == "執行":
            m = _CMD_RE.search(text)
            step["script"] = os.path.basename(m.group(1)) if m else None
            step["args"] = m.group(2).strip() if m else ""
            c = _CHECK_RE.search(text)
            step["check"] = _quoted(c.group(1)) if c else []
        elif s["kind"] == "檢查":
            src = _SOURCE_RE.search(text)
            step["source"] = int(src.group(1)) if src else None
            branches = []
            for b in _BRANCH_RE.finditer(text):
                when = None if b.group(1).strip() == "其他" else _quoted(b.group(1))
                branches.append({"when": when, "to": "end" if b.group(3) else int(b.group(2))})
            step["branches"] = branches
        wf["steps"].append(step)
    for ln in sec.get("成功判準", "").splitlines():
        ln = ln.strip().lstrip("*").strip()
        if not ln:
            continue
        m = _SUCCESS_STEP_RE.search(ln)
        if m:
            wf["success"].append({"step": int(m.group(1)), "expect": _quoted(m.group(2)), "text": ln})
            continue
        c = _CMD_RE.search(ln)
        e = _SUCCESS_EXPECT_RE.search(ln[c.end():] if c else ln)
        if c and e:
            wf["success"].append({"script": os.path.basename(c.group(1)), "args": c.group(2).strip(), "expect": _quoted(e.group(1)), "text": ln})
        else:
            wf["success"].append({"text": ln, "manual": True})     # 程式驗證不了的寫法：照列在報告裡，不算通過或沒過
    wf["pitfalls"] = [ln.strip().lstrip("*").strip() for ln in sec.get("異常與注意事項", "").splitlines() if ln.strip().lstrip("*").strip()]
    return wf


def placeholders(text):
    return list(dict.fromkeys(PLACEHOLDER_RE.findall(text or "")))


def fill_names(wf, step):
    """這一步執行時要由模型決定的佔位符：不是需要的資訊、也不是內建的（{today}、{now}）。"""
    declared = {i["name"] for i in wf["inputs"]}
    return [p for p in placeholders(step.get("args", "")) if p not in declared and p not in BUILTIN]


def skipped_by(wf, step, values):
    """這一步的命令用到、但選填又沒有給的資訊（有的話整步略過）：執行（WorkflowRun.do_exec）與確認畫面用同一條規則。"""
    optional = {i["name"] for i in wf["inputs"] if i["optional"]}
    return [p for p in placeholders(step.get("args", "")) if p in optional and p in values and not values[p]]


def show(text, values):
    """給人看的標題與命令：知道的值代進去；判斷點才決定的、沒有給的照樣是 {名稱}。"""
    return PLACEHOLDER_RE.sub(lambda m: str(values[m.group(1)]) if values.get(m.group(1)) else m.group(0), text or "")


def validate(wf, script_exists, script_skill=None, state_changing=None):
    """回傳問題清單（空的＝可以用）。script_exists(script)：腳本在不在；script_skill(script)：腳本對到的技能名稱；
    state_changing(step)：這一步會不會改變狀態（用來核對 changes_state）。"""
    errs = list(wf.get("errors") or [])
    meta = wf["meta"]
    if meta.get("type") != "Workflow":
        errs.append("frontmatter 的 type 要是 Workflow")
    for k in ("title", "description"):
        if not meta.get(k):
            errs.append(f"frontmatter 少了 {k}")
    names = [i["name"] for i in wf["inputs"]]
    if len(set(names)) != len(names):
        errs.append("需要的資訊有重複的名稱")
    steps = wf["steps"]
    if not steps:
        errs.append("沒有步驟（# 步驟 底下要有「1. 【執行】…」這樣的行）")
    for i, s in enumerate(steps, 1):
        if s["n"] != i:
            errs.append(f"步驟要從 1 連號：第 {i} 個步驟寫成 {s['n']}")
    by_n = {s["n"]: s for s in steps}
    used_skills, changing = [], []
    for s in steps:
        if s["kind"] == "執行":
            if not s.get("script"):
                errs.append(f"第 {s['n']} 步【執行】沒有 `EXECUTE: scripts/…` 的命令")
                continue
            if not script_exists(s["script"]):
                errs.append(f"第 {s['n']} 步的腳本 {s['script']} 不存在")
            if script_skill:
                sk = script_skill(s["script"])
                if sk and sk not in used_skills:
                    used_skills.append(sk)
            if state_changing and state_changing(s):
                changing.append(s["n"])
        elif s["kind"] == "檢查":
            src = s.get("source")
            if src is not None and (src >= s["n"] or by_n.get(src, {}).get("kind") != "執行"):
                errs.append(f"第 {s['n']} 步【檢查】要看的第 {src} 步不是前面的【執行】步")
            if src is None and not any(by_n[k]["kind"] == "執行" for k in range(1, s["n"])):
                errs.append(f"第 {s['n']} 步【檢查】前面沒有【執行】步可以看")
            for b in s["branches"]:
                if b["to"] != "end" and (b["to"] <= s["n"] or b["to"] not in by_n):
                    errs.append(f"第 {s['n']} 步的分支要往後跳到存在的步驟（寫成第 {b['to']} 步；不能往回跳）")
    for c in wf["success"]:
        if c.get("step") and by_n.get(c["step"], {}).get("kind") != "執行":
            errs.append(f"成功判準看的第 {c['step']} 步不是【執行】步")
        if c.get("script") and not script_exists(c["script"]):
            errs.append(f"成功判準的腳本 {c['script']} 不存在")
    deps = meta.get("dependencies")
    if script_skill and isinstance(deps, list):
        missing = [x for x in used_skills if x not in deps]
        if missing:
            errs.append(f"dependencies 沒有列到步驟用的技能：{'、'.join(missing)}")
    if state_changing and "changes_state" in meta and bool(meta["changes_state"]) != bool(changing):
        errs.append(f"changes_state 寫 {meta['changes_state']}，但會改變狀態的步驟是：{'、'.join(map(str, changing)) or '沒有'}")
    return errs


def outline(wf, mark=None, values=None):
    """整份大綱（判斷點的錨點、確認畫面、/workflow show）：每一步一行；mark＝目前這一步。values＝已經知道的值（需要的資訊）：
    代進標題與命令（判斷點才決定的照樣是 {名稱}），選填的沒給、會略過的步驟標出來。"""
    values = values or {}
    lines = []
    for s in wf["steps"]:
        cmd, skip = "", []
        if s["kind"] == "執行" and s.get("script"):
            script = s["script"][:-7] if s["script"].endswith("_cmd.py") else s["script"]
            cmd = f"（{script} {show(s.get('args', ''), values)}".rstrip() + "）"
            skip = skipped_by(wf, s, values)
        lines.append(f"{s['n']}. 【{s['kind']}】{show(s['text'] if s['kind'] != '執行' else s['title'], values)}{cmd}"
                     + (f"（略過：選填的 {'、'.join(skip)} 沒有給）" if skip else "") + ("　← 現在這一步" if s["n"] == mark else ""))
    return "\n".join(lines)
