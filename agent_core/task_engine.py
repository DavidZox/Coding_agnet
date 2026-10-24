"""TaskMixin：通用的任務引擎（task_run 偽技能）——規劃 → 程式檢查計畫 → 每一步一個 worker（或一個工作流）→ 程式檢查 → 程式寫報告。

「類型」（profile）是 prompts/orchestra/profiles/<名稱>.md：規劃與執行要知道的領域知識（第一個是維運 ops）；規劃與執行的通則在
prompts/orchestra/planner.md、worker.md。task_run 的腳本檔只讓存在性檢查與確認關卡照常運作，執行在 harness 的 process 裡（同 workflow_run）。

    task_run [--profile <類型>] "<任務>"     規劃並執行（任務照使用者的原話）
    task_run --continue [<工作>]             停下來等確認的任務接著做（確認關卡列出接下來要改的步驟）
    task_run --cancel [<工作>]               不做了

流程（都在主對話的一個工具呼叫裡同步做）：
1. 規劃：規劃 session（format=TASK_PLAN_SCHEMA）把任務拆成 2～6 步：目標、技能（或一個工作流）、會不會改變狀態、做完怎麼檢查。
   規劃看得到技能與工作流的清單、工作目錄、目標容器、每個容器現在的狀態。程式檢查（_task_issues）：技能與工作流存在、工作流的參數、
   會改變狀態的標記、檢查的寫法、要在停著的容器裡做的事、使用者提到的文件（手冊、規定…）有沒有先讀——有問題把具體的問題交回修一次。
2. 先查：計畫開頭只查詢的步驟直接做（不用確認）；做完把核對過的事實交回規劃 session 重排剩下的步驟（照查到的事實排要改的部分）。
3. 確認：要改變狀態的步驟還沒核准 → 停下來（awaiting_approval），報告列出要改的部分；harness 不經過模型直接用 task_run --continue
   請使用者確認（take_task_continuation），核准＝這些步驟標明的狀態變更都核准了。第一步就要改變狀態時，開始時就確認。
4. 執行：每一步派一個乾淨的 worker（任務、這一步的目標、前面各步核對過的事實、這一步技能的規格），跟主對話一樣的 JSON 協議一步一步
   用技能；沒有核准的狀態變更一律 [DENIED]。做完回報結果與事實，每條事實附出處（工具結果的 #編號）：程式核對事實裡的名稱與數值
   在那份輸出裡找得到（extract.missing_tokens），對不上的交回改一次、還是不行就拿掉。worker 說做完後由程式跑這一步的檢查；沒過換一個
   worker 帶著原因重試一次。工作流的步驟交給工作流的執行器（agent_core/workflow.py），它的報告就是這一步的結果。
5. 失敗：重試還是沒做完 → 把事實與失敗的原因交回規劃 session 重排剩下的步驟（一個任務最多重排 TASK_MAX_REPLANS 次）；重排出新的
   會改變狀態的步驟時再停下來確認。
6. 報告（程式寫，不再交給提煉）：每一步的結果、核對過的事實（#編號）、檢查。存檔 logs/task_jobs/<編號>/：job.json（每一版計畫、
   每一步的狀態與事實）、calls.jsonl（每一次模型呼叫的 prompt 與原文回覆）、events.jsonl（進度）、report.md。

Plan 模式（agent_core/plan.py）用同一個引擎：規劃 → 使用者看、改計畫 → 核准＝整份計畫的狀態變更都核准了 → 照計畫執行（不重排）。

設計依據：小模型「先規劃再照表執行」常輸給邊做邊調整（ADaPT、InterCode）→ 先查完再排要改的、失敗時重排；驗證由程式集中做（MAST）；
agent 之間只傳核對過的事實（ReWOO）。"""
import json
import os
import re
import time

from . import workflow_spec as ws
from .config import (GUARDED_SKILLS, NUM_CTX, PROMPTS_DIR, SKILL_DOC_PREFIX, TASK_JOBS_DIRNAME, TASK_JOBS_KEEP, TASK_MAX_ITEMS,
                     TASK_MAX_REPLANS, TASK_WORKER_MAX_STEPS)
from .extract import missing_tokens
from .jobstore import JobStore
from .protocol import action_text, parse_agent_reply
from .schemas import TASK_FACTS_FIX_SCHEMA, TASK_PLAN_SCHEMA, TASK_WORKER_REPLY_SCHEMA, TASK_WORKER_WRAPUP_SCHEMA

_DIR = os.path.join(PROMPTS_DIR, "orchestra")
DEFAULT_PROFILE = "ops"
TASK_SCRIPT = "scripts/task_run_cmd.py"
# 每一步都可以用的技能（查詢、找名稱、切換目錄或目標容器）；其中有些也能改變狀態（docker_ctl restart、ROS2_param set…），
# 那種用法只有這一步標了 changes_state、核准了、而且技能列在這一步的 skills 裡才放行
TASK_ALWAYS_READ = {"list_dir", "find_file", "search_text", "view_file", "csv_query", "change_dir", "docker_containers", "docker_images",
                    "docker_ctl", "docker_runcmd", "host_runcmd", "ROS2_topic_list", "ROS2_topic_echo", "ROS2_node_list",
                    "ROS2_node_info", "ROS2_param", "ROS2_domain_id", "workpackage_status", "semantic_map", "rmf_handshake",
                    "docker_open"}
# worker 不能用的：任務引擎自己、工作流（計畫裡寫成工作流的步驟，由程式執行）、記憶、麥克風、看存檔（worker 看得到自己的輸出）
_NOT_FOR_WORKERS = {"task_run", "workflow_run", "modify_memory", "stt_engine", "result_recall", "result_grep", "result_view", "result_list"}
# 在容器「裡面」做事的技能：容器停著時做不了（計畫的前提檢查）
_IN_CONTAINER = {"docker_runcmd", "ROS2_topic_list", "ROS2_topic_echo", "ROS2_node_list", "ROS2_node_info", "ROS2_param", "ROS2_topic_pub",
                 "ROS2_domain_id", "ROS2_workspace_env", "mcap_recorder", "mcap_analyzer", "mcap_feature_measure", "mcap_slicer",
                 "rosout_parser"}
_READ_SKILLS = {"view_file", "search_text", "find_file", "list_dir"}
# 目標寫了要寫進某個檔案（記一筆、寫入、附加…＋路徑），這一步卻沒有寫檔的技能：執行時寫不了（2026-10-24 cx_restart_verify）
_WRITE_WORDS = re.compile(r"記一筆|記錄到|記到|寫入|寫到|寫進|寫成|附加|新增一行|存成|存到")
_PATH = re.compile(r"[\w.-]+/[\w./-]*\.[A-Za-z0-9]{1,5}\b|[\w-]+\.(?:md|txt|csv|yaml|yml|json|log)\b")
_WRITE_SKILLS = {"file_ops", "host_runcmd"}
# 計畫的目標寫了這些動作、用的又是兩用的技能（docker_ctl、ROS2_param…）時，這一步算會改變狀態
_CHANGE_WORDS = re.compile(r"重新啟動|重啟|啟動|停掉|關掉|restart|改成|改為|修改|設定為|設成|設為|寫入|新增|建立|"
                           r"複製|移動|補發|回覆?\s*(yes|no)|發布|publish|送出|派送|取消", re.I)
# 描述狀態而不是要做的動作：「是否已停止」「為什麼沒有啟動」「有沒有修改」
_NOT_ACTION_BEFORE = re.compile(r"(不要|不能|不可|別|勿|不|是否|有沒有|有無|是不是|已經|已|為什麼|為何|沒有|未)\s*$")
_START_WORDS = re.compile(r"重新啟動|重啟|啟動|開起來|restart|start", re.I)
# 使用者提到這些文件時，要先讀那份文件再排要改的步驟（不替使用者假設文件寫了什麼）
_DOC_WORDS = re.compile(r"手冊|規定|規範|守則|規則|說明書|SOP|README", re.I)
_FAILED_RE = re.compile(r"^\s*(❌|沒有完成|未完成|無法完成|做不到)")
_RID = re.compile(r"#?\s*(\d+)")
_STATUS_TEXT = {"done": "完成", "unverified": "做完了但檢查沒過", "failed": "沒有完成", "pending": "沒有執行", "skipped": "沒有做",
                "replaced": "沒有做成，重排了剩下的步驟"}
_MARK = {"done": "✅", "failed": "❌", "unverified": "⚠️ 檢查沒過", "pending": "⬜", "skipped": "⏭️", "replaced": "↩️ 沒做成、重排了"}


def _read(name):
    try:
        with open(os.path.join(_DIR, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _clip(text, n=6000):
    text = text or ""
    if len(text) <= n:
        return text
    head, tail = text[: n * 2 // 3], text[-n // 3:]
    return f"{head}\n…（中間省略 {len(text) - len(head) - len(tail)} 字；完整的在存檔）…\n{tail}"


def _one_line(text, n=200):
    return " ".join(str(text or "").split())[:n]


def _task_broken(items):
    return [it for it in items if it.get("broken")]


def _clean_wf_args(text):
    """workflow_args 的寫法整理（2026-10-24 實測規劃的寫法）：
    - 用逗號或分號隔開參數（`file=a.yaml, robot=x`）：值的結尾多了一個逗號——拿掉每一段結尾的 ，；,;（值中間的照留：stops=p0,p2）；
    - 值裡有空白卻沒加引號（`check_command=grep fps /etc/camera.conf expect=…`）：沒有「名稱=」的片段接到前一個值後面。
    引號不成對、開頭就沒有「名稱=」的照原樣交給工作流的參數檢查回報。"""
    import shlex
    try:
        toks = shlex.split(text or "")
    except ValueError:
        return (text or "").strip()
    out = []
    for t in (t.rstrip(",;，；") for t in toks):
        if not t:
            continue
        if re.match(r"[A-Za-z_][A-Za-z0-9_]*=", t) or not out or "=" not in out[-1]:
            out.append(t)
        else:
            out[-1] += " " + t
    return shlex.join(out)


def _steps_text(items):
    return "；".join(f"第 {it['n']} 步 {it['title']}" for it in items)


def _mentions_change(text):
    for m in _CHANGE_WORDS.finditer(text or ""):
        if not _NOT_ACTION_BEFORE.search(text[max(0, m.start() - 4):m.start()]):
            return True
    return False


def parse_profile(text, name):
    """prompts/orchestra/profiles/<名稱>.md → {name, title, description, plan, work}。frontmatter 照 OKF（type: Profile）；
    「# 規劃」一節給規劃 session，「# 執行」一節給 worker。"""
    meta, body = {}, text or ""
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) == 3:
            for ln in parts[1].splitlines():
                k, sep, v = ln.partition(":")
                if sep:
                    meta[k.strip()] = v.strip()
            body = parts[2]
    sections = {}
    for sec in re.split(r"^# ", body, flags=re.M):
        head, _, content = sec.partition("\n")
        if head.strip():
            sections[head.strip()] = content.strip()
    return {"name": meta.get("name") or name, "title": meta.get("title") or name, "description": meta.get("description", ""),
            "type": meta.get("type", ""), "plan": sections.get("規劃", ""), "work": sections.get("執行", "")}


class TaskMixin:

    # ---------------------------------------------------------------- 類型、存檔、進度
    def task_profiles(self):
        d = os.path.join(_DIR, "profiles")
        out = []
        for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if fn.endswith(".md") and not fn.startswith("_"):
                p = self.load_task_profile(fn[:-3])
                if p:
                    out.append(p)
        return out

    def load_task_profile(self, name):
        name = (name or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", name):
            return None
        text = _read(os.path.join("profiles", f"{name}.md"))
        return parse_profile(text, name) if text else None

    def _task_store(self):
        return JobStore(os.path.join(self.script_dir, "logs", TASK_JOBS_DIRNAME))

    def _task_save(self, job):
        store = self._task_store()
        try:
            store.save(job)
            store.prune(TASK_JOBS_KEEP)
        except OSError:
            pass

    def _task_note(self, job, text):
        """進度：印出、記進 events.jsonl，執行中有 progress_callback（Web）時也推到右欄。"""
        print(text)
        if job and job.get("id"):
            try:
                self._task_store().append(job["id"], "events.jsonl", {"text": text})
            except OSError:
                pass
        cb = getattr(self, "progress_callback", None)
        if cb:
            try:
                cb(text)
            except Exception:   # noqa: BLE001  畫面的問題不能中斷執行
                pass

    # ---------------------------------------------------------------- 規劃看得到的
    def task_skill_names(self):
        return [s["name"] for s in self.list_skills() if s["name"] not in _NOT_FOR_WORKERS]

    def _task_catalog(self):
        return "\n".join(f"- {s['name']}：{s['description']}" for s in self.list_skills() if s["name"] not in _NOT_FOR_WORKERS)

    def _task_workflow_catalog(self):
        """給規劃看的工作流：用途與每個參數的說明（格式、例子）。2026-10-24 只列參數名稱時，規劃照抄來源的寫法——CSV 的
        `home;a3` 當成 stops（要逗號隔開）、`backup=robots.yaml.bak`（要的是副檔名 .bak）——工作流第一步就失敗或建錯檔。"""
        lines = []
        for wf in self.list_workflows():
            if any(s["kind"] == "確認" for s in wf["steps"]):
                continue                             # 有【確認】的工作流會停下來等使用者，不放進計畫
            need = "\n".join(f"    {i['name']}=…{'（選填）' if i['optional'] else ''}：{_one_line(i['description'], 160)}" for i in wf["inputs"])
            lines.append(f"- {wf['name']}：{wf['description']}\n  workflow_args：\n{need or '    （不用）'}")
        return "\n".join(lines) or "（沒有）"

    def _task_containers(self):
        """每個容器現在的狀態 {名稱: 狀態}（docker ps -a）；docker 不能用時回 (None, 原因)。"""
        try:
            from skills_system.scripts._docker_common import run_docker
            ok, out, err = run_docker(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"], 8, what="查詢容器狀態")
        except Exception as e:   # noqa: BLE001
            return None, f"{type(e).__name__}: {e}"
        if not ok:
            return None, _one_line(err, 160)
        found = {}
        for ln in out.splitlines():
            parts = ln.split("\t")
            if len(parts) >= 3 and parts[0].strip():
                found[parts[0].strip()] = {"running": parts[1].strip() == "running", "status": parts[2].strip()}
        return found, None

    def _task_env_text(self, containers=None, why=None):
        try:
            entries = sorted(os.listdir(self.current_cwd))
        except OSError:
            entries = []
        shown = "、".join(entries[:40]) + ("…" if len(entries) > 40 else "")
        lines = [f"現在時間：{time.strftime('%Y-%m-%d %H:%M')}", f"工作目錄：{self.current_cwd}（{len(entries)} 項：{shown}）",
                 f"目標容器：{self.target_container or '（未設定）'}"]
        if containers:
            items = sorted(containers.items())
            lines.append("容器（名稱：狀態）：" + "；".join(f"{n}：{c['status']}" for n, c in items[:30])
                         + (f"；…共 {len(items)} 個" if len(items) > 30 else ""))
        elif why:
            lines.append(f"容器：查不到（{why}）")
        return "\n".join(lines)

    # ---------------------------------------------------------------- 模型呼叫（每一次都存）
    def _task_call(self, job, kind, messages, schema, num_predict=4096, extra=None):
        """一次模型呼叫：回傳 (原文, 解析好的 dict 或 None)。prompt 與原文記進 calls.jsonl（worker 的對話只記這一輪新加的訊息）。"""
        raw, data, err = "", None, None
        t0 = time.time()
        try:
            res = self._timed_chat(f"task_{kind}", model=self.model, messages=messages, format=schema,
                                   options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": num_predict}, think=False)
            raw = res["message"]["content"]
            data = json.loads(raw)
        except Exception as e:   # noqa: BLE001  Ollama 沒有回應、JSON 被截斷…：照實記下來
            err = f"{type(e).__name__}: {e}"
        job["model_calls"] = job.get("model_calls", 0) + 1
        rec = {"kind": kind, "seconds": round(time.time() - t0, 1), "response": raw, "error": err}
        rec.update(extra or {})
        # worker 的每一輪只記這一輪新加的訊息（工具結果或系統的提醒）；system 與任務說明在 worker_start 整份記一次
        rec["messages"] = messages[-1:] if kind.startswith("worker") else messages
        try:
            self._task_store().append(job["id"], "calls.jsonl", rec)
        except OSError:
            pass
        return raw, (data if isinstance(data, dict) else None)

    # ---------------------------------------------------------------- 計畫：清理與程式檢查
    def _task_item(self, raw, n):
        """模型（或使用者）給的一步 → 清理過的 item 與問題清單。做不了的一步標 broken（工作流不存在、有【確認】、參數不對；
        要改變狀態卻沒有可以用的技能；列的技能全都不存在）：修一次還是這樣，整份計畫不執行（_task_broken）。"""
        issues = []
        names = set(self.task_skill_names())
        workflows = {w["name"] for w in self.list_workflows()}
        title = _one_line(raw.get("title"), 60)
        goal = _one_line(raw.get("goal"), 600)
        wf_name = str(raw.get("workflow") or "").strip()
        wf_args = _clean_wf_args(str(raw.get("workflow_args") or ""))
        raw_skills = [str(s).strip() for s in raw.get("skills") or [] if str(s).strip()]
        skills, unknown = [], []
        for s in raw_skills:
            s = s[len("scripts/"):] if s.startswith("scripts/") else s
            s = self._script_skill_map().get(s, s) if s.endswith(".py") else s
            if s == "workflow_run" and not wf_name:
                continue
            if s in workflows and not wf_name:
                wf_name = s                          # 工作流的名稱寫在 skills（2026-10-24 實測常見）：當成工作流的步驟
                continue
            if s and s not in skills and s not in workflows:
                (skills if s in names else unknown).append(s)
        it = {"n": n, "title": title or goal[:30], "goal": goal or title, "skills": skills, "workflow": "", "workflow_args": "",
              "inputs": {}, "changes_state": bool(raw.get("changes_state")), "check": None, "approved": False, "status": "pending",
              "summary": "", "facts": [], "dropped": [], "attempts": 0, "steps": 0, "evidence": "", "calls": []}
        if unknown:
            issues.append(f"第 {n} 步的技能 {'、'.join(unknown)} 不在技能清單裡（只能用清單裡的名稱）")
        if wf_name:
            wf = self.load_workflow(wf_name)
            if not wf:
                issues.append(f"第 {n} 步的工作流 {wf_name} 不存在（只能用工作流清單裡的名稱，或改用技能）")
            elif any(s["kind"] == "確認" for s in wf["steps"]):
                issues.append(f"第 {n} 步的工作流 {wf_name} 有【確認】、會停下來等使用者，不能放進計畫：改用技能")
            else:
                action, _, values, err = self._wf_parse_args(f"{wf_name} {wf_args}")
                inputs, err2 = (None, err) if err else self._wf_check_inputs(wf, values)
                if err2:
                    issues.append(f"第 {n} 步的工作流 {wf_name}：{_one_line(err2, 300)}")
                else:
                    it.update(workflow=wf_name, workflow_args=wf_args, inputs=inputs,
                              skills=list((wf.get("meta") or {}).get("dependencies") or []),
                              changes_state=bool(self._wf_segment(wf, 1, inputs)))
            if not it["workflow"]:
                it["broken"] = True
            return it, issues
        mentioned = [w for w in workflows if re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", f"{title} {goal}")]
        if mentioned:
            issues.append(f"第 {n} 步的目標寫了工作流 {'、'.join(mentioned)}，但沒有填 workflow：要用工作流就填 workflow 與 workflow_args"
                          f"（skills 給空的），不用的話目標不要寫工作流的名稱")
        if not skills:
            if it["changes_state"] or (raw_skills and unknown):
                it["broken"] = True              # 要改變狀態卻沒有技能、列的技能全都不存在：worker 做不了
            issues.append(f"第 {n} 步沒有列出要用的技能（或工作流）")
        write = _WRITE_WORDS.search(goal) and _PATH.search(goal)
        if write and not set(skills) & _WRITE_SKILLS:
            issues.append(f"第 {n} 步要寫進 {_PATH.search(goal).group(0)}，skills 要列 file_ops（不然執行時不能寫）")
        changes = it["changes_state"]
        if any(s in GUARDED_SKILLS and s not in TASK_ALWAYS_READ for s in skills):
            changes = True                           # file_ops、ROS2_topic_pub、workpackage_send…：一定會改變狀態
        elif not changes and _mentions_change(f"{title} {goal}") and any(s in GUARDED_SKILLS for s in skills):
            changes = True                           # 兩用的技能（docker_ctl restart、ROS2_param set…）而目標寫了要改
        it["changes_state"] = changes
        check = raw.get("check") if isinstance(raw.get("check"), dict) else None
        if check and changes:
            cs = str(check.get("skill") or "").strip()
            check = {"skill": cs, "args": str(check.get("args") or "").strip(), "expect": str(check.get("expect") or "").strip()}
            if cs not in names:
                issues.append(f"第 {n} 步的檢查技能「{cs}」不在技能清單裡")
            elif check["expect"]:
                it["check"] = check
        return it, issues

    def _task_clean(self, data, start=1):
        items, issues = [], []
        for raw in (data or {}).get("items") or []:
            if not isinstance(raw, dict) or not (raw.get("title") or raw.get("goal") or raw.get("workflow")):
                continue
            it, problems = self._task_item(raw, start + len(items))
            items.append(it)
            issues += problems
        if len(items) > TASK_MAX_ITEMS:
            issues.append(f"步驟太多（{len(items)} 步）：合併成最多 {TASK_MAX_ITEMS} 步")
        return items[:TASK_MAX_ITEMS], issues

    def _task_issues(self, job, items, containers, done=()):
        """程式看得出來的前提問題（交回規劃 session 修）：在停著的容器裡做事、使用者提到的文件沒有先讀。"""
        issues = []
        text_of = lambda it: f"{it['title']} {it['goal']}"   # noqa: E731
        if containers:
            names = sorted(containers, key=len, reverse=True)
            mention = lambda it: [c for c in names if re.search(rf"(?<![\w.-]){re.escape(c)}(?![\w.-])", text_of(it))]   # noqa: E731
            for i, it in enumerate(items):
                if it["workflow"] or not set(it["skills"]) & _IN_CONTAINER:
                    continue
                for c in mention(it):
                    if containers[c]["running"]:
                        continue
                    later = next((j for j in items[i + 1:] if "docker_ctl" in j["skills"] and c in mention(j)
                                  and _START_WORDS.search(text_of(j))), None)
                    if later:
                        issues.append(f"第 {it['n']} 步要在 {c} 裡面做，但 {c} 現在沒有在跑（{containers[c]['status']}），第 {later['n']} 步才啟動它："
                                      f"把啟動排在前面")
                    else:
                        issues.append(f"第 {it['n']} 步要在 {c} 裡面做，但 {c} 現在沒有在跑（{containers[c]['status']}）：容器停著時只能看狀態與 "
                                      f"log（docker_ctl status／logs）；要進容器得先啟動（使用者要求才可以）")
        m = _DOC_WORDS.search(job["task"])
        first_change = next((k for k, it in enumerate(items) if it["changes_state"]), None)
        if m and first_change is not None:
            read_before = any(set(it["skills"]) & _READ_SKILLS for it in list(done) + items[:first_change])
            if not read_before:
                issues.append(f"使用者提到「{m.group(0)}」：先排一步找到並讀那份文件（find_file／search_text／view_file），"
                              f"後面要改的步驟照文件寫的做（不要先假設文件的內容）")
        return issues

    # ---------------------------------------------------------------- 規劃（第一版）與重排
    def _task_planner_system(self, profile):
        return _read("planner.md") + (f"\n\n## 這一類任務（{profile['title']}）\n{profile['plan']}" if profile.get("plan") else "")

    def _task_plan_call(self, job, profile, user, kind):
        """規劃（或重排）一次；有程式檢查出的問題就帶著問題交回修一次。回傳 (data, items, issues)。"""
        system = self._task_planner_system(profile)
        containers, why = self._task_containers()
        start = sum(1 for it in job["items"] if it["status"] != "pending") + 1
        done = [it for it in job["items"] if it["status"] != "pending"]
        user = user.replace("{ENV}", self._task_env_text(containers, why))
        _, data = self._task_call(job, kind, [{"role": "system", "content": system}, {"role": "user", "content": user}], TASK_PLAN_SCHEMA)
        job["plan_calls"] = job.get("plan_calls", 0) + 1
        items, issues = self._task_clean(data, start)
        issues += self._task_issues(job, items, containers, done)
        if issues and data is not None:
            fix = (user + "\n\n【上一版計畫】\n" + json.dumps({"items": data.get("items")}, ensure_ascii=False)[:4000]
                   + "\n\n【程式檢查發現的問題：修正後輸出完整的計畫】\n" + "\n".join(f"- {x}" for x in issues))
            _, data2 = self._task_call(job, kind + "_fix", [{"role": "system", "content": system}, {"role": "user", "content": fix}],
                                       TASK_PLAN_SCHEMA)
            job["plan_calls"] += 1
            items2, issues2 = self._task_clean(data2, start)
            issues2 += self._task_issues(job, items2, containers, done)
            score = lambda its, iss: (len(_task_broken(its)), len(iss))   # noqa: E731  做不了的步驟少的優先，再看問題的數量
            if items2 and score(items2, issues2) <= score(items, issues):
                data, items, issues = data2, items2, issues2
        return data, items, issues

    def task_plan(self, task, profile_name=None, mode="auto"):
        """第一版計畫 → (job, 錯誤)。mode：auto＝task_run（只有一步的任務不用規劃，回錯誤）；plan＝Plan 模式的草稿（使用者自己看、改）。"""
        task = " ".join((task or "").strip().strip('"').strip("'").split())
        if len(task) < 4:
            return None, "[ERROR] task_run 需要任務描述：args 填使用者的原話。"
        profile = self.load_task_profile(profile_name or DEFAULT_PROFILE)
        if not profile:
            names = "、".join(p["name"] for p in self.task_profiles()) or "（沒有）"
            return None, f"[ERROR] 沒有任務類型 {profile_name}：現有的是 {names}。下一步：不帶 --profile，或照這幾個名稱寫。"
        store = self._task_store()
        job = {"id": store.new_id(profile["name"]), "profile": profile["name"], "task": task, "mode": mode, "status": "planning",
               "items": [], "plans": [], "replans": 0, "plan_calls": 0, "model_calls": 0, "seconds": 0.0,
               "created": time.strftime("%Y-%m-%d %H:%M:%S"), "model": self.model}
        self._task_note(job, f"🧭 任務（{profile['title']}）：規劃中…")
        t0 = time.time()
        user = (f"【技能清單】\n{self._task_catalog()}\n\n【工作流清單】（整件事或其中一段正好是其中一個時，那一步寫 workflow）\n"
                f"{self._task_workflow_catalog()}\n\n【目前狀態】\n{{ENV}}\n\n【任務】\n{task}\n\n（計畫的每個欄位都用繁體中文寫）")
        data, items, issues = self._task_plan_call(job, profile, user, "plan")
        job["seconds"] += round(time.time() - t0, 1)
        job.update(items=items, issues=issues, status="draft" if mode == "plan" else "planned",
                   understanding=_one_line((data or {}).get("understanding"), 400), summary=_one_line((data or {}).get("summary"), 200),
                   report_focus=_one_line((data or {}).get("report"), 300))
        job["plans"].append({"version": 1, "why": "第一版", "items": [it["title"] for it in items], "issues": issues})
        self._task_save(job)
        if not items:
            return None, ("[ERROR] 規劃 session 沒有給出可以執行的步驟" + (f"（{'；'.join(issues)}）" if issues else "")
                          + "：這個任務直接用技能一步一步做。")
        broken = _task_broken(items)
        if broken and mode == "auto":
            # 修一次還是有做不了的步驟：不照著做（以前照做，worker 找不到工具、做滿 10 輪才失敗——2026-10-24 cx_batch_dispatch）
            return None, (f"[ERROR] 規劃出來的計畫有做不了的步驟（第 {'、'.join(str(it['n']) for it in broken)} 步：{'；'.join(issues)[:600]}），"
                          f"這次沒有執行任何步驟。下一步：這個任務直接用技能一步一步做，或把要做的事說得更具體再交給 task_run。")
        if mode == "auto" and len(items) == 1:
            it = items[0]
            if it["workflow"]:
                return None, (f"[ERROR] 這個任務正好是工作流 {it['workflow']}，不需要規劃：直接 workflow_run {it['workflow']} {it['workflow_args']}"
                              f"（系統會請使用者確認，不用先問）。")
            # 一步就做得完的任務不需要規劃（實測：主對話把「先不要修改、查原因」當成要先看計畫，規劃出一步就停下來問使用者）
            return None, (f"[ERROR] 這個任務一步就做得完，不需要規劃：直接用 {'、'.join(it['skills']) or '對應的技能'} 做"
                          f"（{it['goal']}），不用先問使用者。")
        self.task_job = job
        return job, None

    def _task_replan(self, job, why, allow_empty=True):
        """剩下的步驟交回規劃 session 重排（先查完、或某一步失敗之後）：看得到前面核對過的事實。重排出步驟就取代剩下的；
        規劃不出來就保留原本的。allow_empty：查完之後可以「不用再做什麼」（items 空的）；失敗之後重排出空的＝沒有辦法，不算換了計畫。
        回傳是否換了計畫。"""
        profile = self.load_task_profile(job["profile"]) or {"title": job["profile"], "plan": ""}
        done = [it for it in job["items"] if it["status"] != "pending"]
        rest = [it for it in job["items"] if it["status"] == "pending"]
        self._task_note(job, f"🧭 {why}：照前面查到的事實重排剩下的步驟…")
        user = (f"【技能清單】\n{self._task_catalog()}\n\n【工作流清單】\n{self._task_workflow_catalog()}\n\n【目前狀態】\n{{ENV}}\n\n"
                f"【任務】\n{job['task']}\n\n【已經做完的步驟與查到的事實】\n{self._task_facts_text(done)}\n\n"
                f"【原本剩下的步驟】\n" + ("\n".join(f"- {it['title']}：{it['goal']}" for it in rest) or "（沒有）")
                + f"\n\n【為什麼重排】{why}\n\n只排還沒做的部分（已經查到的不要再查一次）：照上面查到的事實決定要改什麼、怎麼改；"
                  "不需要再改變任何狀態時，只排確認或整理的步驟，或 items 給空的。（計畫的每個欄位都用繁體中文寫）")
        t0 = time.time()
        data, items, issues = self._task_plan_call(job, profile, user, "replan")
        job["seconds"] += round(time.time() - t0, 1)
        job["replans"] += 1
        if data is None or (not items and not allow_empty) or _task_broken(items):
            job["plans"].append({"version": len(job["plans"]) + 1, "why": why, "items": None,
                                 "issues": ["規劃 session 沒有給出可以執行的新步驟，保留原本的"] + issues})
            return False
        job["items"] = done + items
        if data.get("report"):
            job["report_focus"] = _one_line(data["report"], 300)
        job["plans"].append({"version": len(job["plans"]) + 1, "why": why, "items": [it["title"] for it in items], "issues": issues})
        self._task_save(job)
        return True

    # ---------------------------------------------------------------- 給人看的計畫、事實
    @staticmethod
    def task_item_text(it):
        mark = "⚠️ 會改變狀態" if it["changes_state"] else "只查詢"
        if it["workflow"]:
            how = f"工作流 {it['workflow']} {it['workflow_args']}".strip()
        else:
            how = f"技能：{'、'.join(it['skills']) or '—'}"
        chk = (f"；做完檢查：{it['check']['skill']} {it['check']['args']} 要看到「{it['check']['expect']}」" if it.get("check") else "")
        return f"{it['n']}. {it['title']}（{mark}；{how}{chk}）\n   {it['goal']}"

    def task_plan_text(self, job, pending_only=False):
        items = [it for it in job["items"] if not pending_only or it["status"] == "pending"]
        lines = [f"計畫（{len(items)} 步）：{job.get('summary') or job['task']}"] + [self.task_item_text(it) for it in items]
        if job.get("report_focus"):
            lines.append(f"最後回報：{job['report_focus']}")
        return "\n".join(lines)

    @staticmethod
    def _task_facts_text(items, limit=700):
        out = []
        for it in items:
            line = f"第 {it['n']} 步「{it['title']}」{_STATUS_TEXT.get(it['status'], it['status'])}：{_clip(it['summary'], limit)}"
            for f in it.get("facts") or []:
                line += f"\n  - {f['text']}（#{f['ref']}）"
            if it.get("evidence"):
                line += f"\n  - 檢查：{it['evidence']}"
            out.append(line)
        return "\n".join(out) or "（還沒有）"

    # ---------------------------------------------------------------- 確認關卡與 harness 的接續
    @staticmethod
    def _task_parse_args(remainder):
        """task_run 的參數 → (動作, 工作編號或任務, 類型, 錯誤)。動作：start／continue／cancel。"""
        text = (remainder or "").strip()
        if not text:
            return None, None, None, ("[ERROR] task_run 需要任務描述：args 填使用者的原話（系統會先規劃，要改變狀態的部分給使用者確認再做）；"
                                      "停下來等確認的任務用 task_run --continue。")
        head = text.split(maxsplit=1)
        if head[0] in ("--continue", "--cancel"):
            return head[0][2:], (head[1].strip() if len(head) > 1 else None), None, None
        profile = None
        if head[0] == "--profile":
            rest = head[1].split(maxsplit=1) if len(head) > 1 else []
            if len(rest) < 2:
                return None, None, None, "[ERROR] 用法：task_run --profile <類型> \"<任務>\"。"
            profile, text = rest[0], rest[1]
        elif head[0].startswith("--"):
            return None, None, None, f"[ERROR] 不認識的選項 {head[0]}。用法：task_run [--profile <類型>] \"<任務>\"；task_run --continue；task_run --cancel。"
        return "start", text.strip().strip('"').strip("'").strip(), profile, None

    def _task_find(self, job_id=None, statuses=("awaiting_approval", "approved")):
        """工作編號 → job（記憶體裡的優先：同一次啟動）；沒給編號就找最近一個在等的。"""
        cur = getattr(self, "task_job", None)
        if cur and (job_id in (None, cur["id"])) and cur.get("status") in statuses:
            return cur
        store = self._task_store()
        if job_id:
            job = store.load(job_id)
            return job if job and job.get("status") in statuses else None
        for jid in reversed(store.ids()[-20:]):
            job = store.load(jid)
            if job and job.get("status") in statuses:
                return job
        return None

    def _task_planned(self, task, profile):
        """確認關卡剛規劃好、還沒開始的同一個任務（guard 規劃一次，task_run 接著用同一份）。"""
        cur = getattr(self, "task_job", None)
        task = " ".join((task or "").split())
        if cur and cur.get("status") == "planned" and cur["task"] == task and cur["profile"] == (profile or DEFAULT_PROFILE):
            return cur
        return None

    @staticmethod
    def _task_first_pending(job):
        return next((it for it in job["items"] if it["status"] == "pending"), None)

    def task_guard_reason(self, remainder):
        """task_run 的確認說明（guard.py）。開始：計畫的第一步就要改變狀態時列出整份計畫（之後要改的步驟查完再確認）；
        --continue：接下來要改的步驟。不用確認時回 None（只查詢、取消、參數錯或規劃失敗——交給 task_run 回報）。"""
        action, target, profile, err = self._task_parse_args(remainder)
        if err or action == "cancel":
            return None
        if action == "continue":
            job = self._task_find(target)
            if not job:
                return None
            changing = [it for it in job["items"] if it["status"] == "pending" and it["changes_state"] and not it["approved"]]
            if not changing:
                return None                          # Plan 模式核准過的計畫：不再問一次
            done = [it for it in job["items"] if it["status"] != "pending"]
            return (f"任務接著做：會改變狀態的是 {_steps_text(changing)}"
                    + (f"\n已經查到的：\n{self._task_facts_text(done, 300)}" if done else "")
                    + "\n" + self.task_plan_text(job, pending_only=True))
        job = self._task_planned(target, profile)
        if job is None:
            failed = getattr(self, "_task_plan_failed", None)
            if failed and failed[0] == " ".join(target.split()):
                return None                          # 剛剛規劃失敗：交給 task_run 回報，不再規劃一次（以前 dispatch 的關卡又規劃一次，
                                                     # 第二次的計畫第一步要改就被擋成 [DENIED]——2026-10-24 cx_restart_verify）
            job, err = self.task_plan(target, profile)
            if err:
                self._task_plan_failed = (" ".join(target.split()), err)
                return None
        first = self._task_first_pending(job)
        if not first or not first["changes_state"]:
            return None                              # 開頭只查詢：先查完、要改的部分之後再確認（或整份都只查詢）
        changing = [it for it in job["items"] if it["changes_state"]]
        return f"依計畫執行 {len(job['items'])} 步，會改變狀態的是：{_steps_text(changing)}\n" + self.task_plan_text(job)

    def take_task_continuation(self):
        """任務停下來等確認時（awaiting_approval），harness 不經過模型直接接著問使用者：回傳要執行的 parsed（含 raw＝要放進對話的
        assistant 訊息）；沒有在等的回 None。CLI、Web、評測的 worker 在下一次問模型之前呼叫。"""
        jid = getattr(self, "task_pending_approval", None)
        self.task_pending_approval = None
        if not jid:
            return None
        job = self._task_find(jid)
        if not job:
            return None
        action = {"command": TASK_SCRIPT, "args": f"--continue {jid}"}
        if job.get("status") == "approved":
            thought, reply = "使用者在 Plan 模式核准了計畫，交給任務引擎照計畫做", "照核准的計畫執行。"
        else:
            thought, reply = "任務引擎查完、重排了要改的步驟，等使用者確認", "查完了，接下來要改變狀態的步驟請你確認。"
        raw = json.dumps({"thought": thought, "reply": reply, "action": action}, ensure_ascii=False)
        return {"thought": thought, "reply": reply, "action": action, "valid": True, "raw": raw}

    # ---------------------------------------------------------------- task_run 偽技能
    def task_run(self, remainder):
        """task_run 偽技能（dispatch 在確認關卡之後呼叫）：回傳給主對話的報告。"""
        action, target, profile, err = self._task_parse_args(remainder)
        if err:
            return err
        if action == "cancel":
            job = self._task_find(target)
            if not job:
                return "[ERROR] 沒有停下來等確認的任務。下一步：用 task_run \"<任務>\" 開始一個。"
            job["status"] = "cancelled"
            self._task_save(job)
            self.task_pending_approval = None
            return f"[PASS] 任務取消了（工作 {job['id']}）：停在第 {self._task_first_pending(job)['n'] if self._task_first_pending(job) else '?'} 步之前，後面的步驟沒有做。"
        if action == "continue":
            job = self._task_find(target)
            if not job:
                return ("[ERROR] 沒有停下來等確認的任務" + (f"（{target}）" if target else "")
                        + "。下一步：用 task_run \"<任務>\" 開始一個；做完的任務看檢索清單裡的報告（result_recall）。")
            for it in job["items"]:                  # 走到這裡＝使用者在確認關卡核准了（或確認關卡關掉）：剩下要改的步驟都核准
                if it["status"] == "pending" and it["changes_state"]:
                    it["approved"] = True
            self.task_job = job
            return TaskRun(self, job).run()
        job = self._task_planned(target, profile)
        if job is None:
            failed = getattr(self, "_task_plan_failed", None)
            if failed and failed[0] == " ".join(target.split()):
                self._task_plan_failed = None
                return failed[1]                      # 確認關卡剛剛規劃失敗：不再規劃一次
            job, err = self.task_plan(target, profile)
            if err:
                return err
        first = self._task_first_pending(job)
        if first and first["changes_state"] or not getattr(self, "guard_enabled", True):
            for it in job["items"]:                  # 開始時就確認過整份計畫（第一步就要改）、或確認關卡關掉：計畫裡要改的都核准
                if it["changes_state"]:
                    it["approved"] = True
            job["approved_at_start"] = True
        return TaskRun(self, job).run()


class TaskRun:
    """一次執行（或停下來等確認之後接著執行）：照 job["items"] 一步一步做，到做完、失敗或要改變狀態的步驟還沒核准。"""

    def __init__(self, agent, job):
        self.a, self.job = agent, job
        self.profile = agent.load_task_profile(job["profile"]) or {"name": job["profile"], "title": job["profile"], "plan": "", "work": ""}

    def note(self, text):
        self.a._task_note(self.job, text)

    def save(self):
        self.a._task_save(self.job)

    def run(self):
        job, a = self.job, self.a
        t0 = time.time()
        job["status"] = "running"
        self.save()
        while True:
            it = a._task_first_pending(job)
            if it is None:
                break
            if it["changes_state"] and not it["approved"]:
                done = [x for x in job["items"] if x["status"] != "pending"]
                if (job["mode"] == "auto" and done and not job.get("surveyed") and job["replans"] < TASK_MAX_REPLANS):
                    job["surveyed"] = True           # 先查的步驟做完了：照查到的事實重排要改的部分（只重排一次）
                    a._task_replan(job, "查詢的步驟做完了")
                    continue
                job["status"] = "awaiting_approval"
                job["seconds"] += round(time.time() - t0, 1)
                self.save()
                a.task_pending_approval = job["id"]
                self.note(f"⏸️ 任務查完了，要改變狀態的步驟等使用者確認（工作 {job['id']}）")
                return self.report()
            n_items = len(job["items"])
            self.note(f"🧭 任務第 {it['n']}/{n_items} 步：{it['title']}")
            self.do_item(it)
            self.save()
            if it["status"] == "failed":
                if job["mode"] == "auto" and job["replans"] < TASK_MAX_REPLANS:
                    why = f"第 {it['n']} 步「{it['title']}」沒有完成：{_one_line(it['summary'], 300)}"
                    it["status"] = "replaced"        # 先標成「重排了」：重排得出來就照新的做，這一步不算整個任務失敗
                    if a._task_replan(job, why, allow_empty=False):
                        continue
                    it["status"] = "failed"
                break
        failed = next((x for x in job["items"] if x["status"] == "failed"), None)
        unverified = [x for x in job["items"] if x["status"] == "unverified"]
        job["status"] = "failed" if failed else ("unverified" if unverified else "done")
        job["seconds"] += round(time.time() - t0, 1)
        job["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        report = self.report()
        self.save()
        try:
            a._task_store().write(job["id"], "report.md", report + "\n")
        except OSError:
            pass
        a.task_last = job
        self.note(f"🧭 任務：{_STATUS_TEXT.get(job['status'], job['status'])}（{job['seconds']:.0f} 秒）")
        return report

    # ------------------------------------------------ 一步
    def facts_before(self, it):
        done = [x for x in self.job["items"] if x["status"] != "pending" and x is not it]
        return self.a._task_facts_text(done) if done else ""

    def prior_rids(self, it):
        """這個任務前面做過的工具結果編號（前面各步、這一步之前的嘗試：worker 執行過的、工作流每一步的輸出）——worker 看得到前面各步的事實
        與 #編號，回報時常引用它們（例如只整理前面結果的步驟），核對時讀回存檔的原文。"""
        rids = set()
        for x in self.job["items"]:
            if x["status"] == "pending" and x is not it:
                continue
            rids |= {str(c["rid"]) for c in x.get("calls") or [] if c.get("rid")}
            rids |= {str(f["ref"]) for f in x.get("facts") or [] if f.get("ref")}
        return rids

    def do_item(self, it):
        if it["workflow"]:
            return self.do_workflow(it)
        prev_failure = None
        while it["attempts"] < 2:
            it["attempts"] += 1
            res = TaskWorker(self, it, prev_failure).run()
            it["steps"] += res["steps"]
            it["calls"] += res["calls"]
            it["summary"], it["facts"], it["dropped"] = res["summary"], res["facts"], res["dropped"]
            if res["status"] != "done":
                it["status"] = "failed"
                prev_failure = res["summary"]
                continue
            ok, evidence = self.check(it)
            it["evidence"] = evidence
            if ok:
                it["status"] = "done"
                return
            # 檢查沒過：換一個 worker 帶著檢查的輸出再做一次；第二次還是沒過，多半是計畫寫的檢查條件不適用（例如要「看到 0」
            # 卻是「找不到」）——不擋下後面的步驟，標成「檢查沒過」交給主對話與使用者確認
            it["status"] = "unverified"
            prev_failure = (f"你回報完成了，但做完之後的檢查沒有通過：{evidence}。先查清楚現在的狀態：沒做好就修正；"
                            f"確定已經完成、是檢查的條件不適用，就照實回報並說明。")

    def do_workflow(self, it):
        """工作流的步驟：交給工作流的執行器（它自己推進、檢查、存檔），報告的每一步當這一步的事實（#編號是那一步的輸出）。"""
        a = self.a
        wf = a.load_workflow(it["workflow"])
        it["attempts"] += 1
        if not wf:
            it.update(status="failed", summary=f"工作流 {it['workflow']} 不存在")
            return
        store = a._workflow_store()
        wjob = {"id": store.new_id(wf["name"]), "spec": wf, "inputs": it["inputs"], "given": {}, "status": "running", "cursor": 1,
                "steps": {str(s["n"]): {"status": "pending"} for s in wf["steps"]}, "notes": [], "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model": a.model, "seconds": 0.0, "model_calls": 0, "task_job": self.job["id"]}
        from .workflow import WorkflowRun
        report = WorkflowRun(a, wjob).run()
        it["workflow_job"] = wjob["id"]
        it["steps"] += wjob.get("model_calls", 0)
        self.job["model_calls"] = self.job.get("model_calls", 0) + wjob.get("model_calls", 0)
        facts = []
        for s in wf["steps"]:
            st = wjob["steps"][str(s["n"])]
            if s["kind"] == "執行" and st.get("rid") and st.get("status") == "done":
                facts.append({"text": f"{ws.show(s['title'], it['inputs'])}：{_one_line(st.get('head'), 160)}", "ref": str(st["rid"])})
        it["facts"] = facts[:8]
        it["summary"] = _one_line(report.splitlines()[0] if report else "", 400)
        it["status"] = {"done": "done", "ended": "done", "unverified": "unverified"}.get(wjob["status"], "failed")

    def check(self, it):
        """worker 回報完成後由程式跑 check（唯讀技能）：輸出要找得到 expect（正規表示式，不合法就當字串；不分大小寫）。
        檢查本身執行失敗（[ERROR]，多半是計畫寫的參數不對）不算這一步失敗，標明「沒有驗證」交給主對話判斷。"""
        a = self.a
        chk = it.get("check")
        if not chk:
            return True, ""
        script = next((s for s, name in a._script_skill_map().items() if name == chk["skill"]), None)
        if not script:
            return True, f"（檢查技能 {chk['skill']} 找不到腳本，沒有驗證）"
        parsed = {"action": {"command": f"scripts/{script}", "args": chk["args"]}}
        if a.state_change_info(parsed):
            return True, "（檢查用的動作會改變狀態，沒有執行、沒有驗證）"
        out = a._run_tool_once(parsed, approved=False) or ""
        first = out.strip().splitlines()[0][:200] if out.strip() else "（沒有輸出）"
        if out.lstrip().startswith("[ERROR]"):
            return True, f"（檢查 {chk['skill']} {chk['args']} 執行失敗，沒有驗證：{first}）"
        try:
            hit = re.search(chk["expect"], out, re.I)
        except re.error:
            hit = chk["expect"].lower() in out.lower()
        rid = getattr(a, "last_result_id", None)
        return bool(hit), (f"{chk['skill']} {chk['args']} → {'有' if hit else '沒有'}「{chk['expect']}」（{first}）"
                           + (f"（#{rid}）" if rid else ""))

    # ------------------------------------------------ 報告
    def report(self):
        job = self.job
        items = job["items"]
        took = f"{job['seconds']:.0f} 秒"
        if job["status"] == "awaiting_approval":
            done = [it for it in items if it["status"] != "pending"]
            rest = [it for it in items if it["status"] == "pending"]
            head = (f"[PASS] ⏸️ 任務（工作 {job['id']}）查完了，接下來要改變狀態的步驟等使用者確認（系統會直接請使用者確認；"
                    f"使用者同意後 task_run --continue 接著做，不要了就 task_run --cancel）")
            lines = [head]
            if done:
                lines += ["## 已經做完的", self.a._task_facts_text(done)]
            lines += ["## 接下來的計畫"] + [self.a.task_item_text(it) for it in rest]
            return "\n".join(lines)
        n_done = sum(1 for it in items if it["status"] in ("done", "unverified"))
        if job["status"] == "done":
            head = f"[PASS] 任務完成（{n_done}/{len(items)} 步，{took}）"
        elif job["status"] == "unverified":
            bad = "、".join(str(it["n"]) for it in items if it["status"] == "unverified")
            head = f"[PASS] 任務的步驟都做了（{took}），但第 {bad} 步做完之後的檢查沒有通過：回答時說明檢查的結果，請使用者確認"
        else:
            bad = next((it for it in items if it["status"] == "failed"), None)
            head = (f"[ERROR] 任務沒有做完：第 {bad['n'] if bad else '?'} 步沒有完成（試了 {bad['attempts'] if bad else 0} 次），"
                    f"後面的步驟沒有做（{n_done}/{len(items)} 步做完，{took}）")
        lines = [head, "## 步驟"]
        for it in items:
            lines.append(f"{it['n']}. {_MARK.get(it['status'], '⬜ 沒有執行')} {it['title']}" + (f"：{it['summary']}" if it["summary"] else ""))
            for f in it.get("facts") or []:
                lines.append(f"   - {f['text']}（#{f['ref']}）")
            if it.get("dropped"):
                lines.append(f"   - （另外 {len(it['dropped'])} 條在引用的輸出裡找不到，拿掉了）")
            if it.get("evidence"):
                lines.append(f"   - 檢查：{it['evidence']}")
        if len(job["plans"]) > 1:
            lines.append("## 計畫改過")
            lines += [f"- 第 {p['version']} 版：{p['why']}" for p in job["plans"][1:]]
        if job.get("report_focus"):
            lines.append(f"要回報給使用者的重點：{job['report_focus']}")
        lines.append(f"（工作 {job['id']}，紀錄在 logs/{TASK_JOBS_DIRNAME}/{job['id']}/；依上面的結果回答使用者：引用具體的值、名稱與前後變化"
                     f"（#編號是那一次工具輸出的存檔，要看完整的用 result_recall）；沒做完的說明卡在哪裡、原因與建議）")
        return "\n".join(lines)


class TaskWorker:
    """計畫的一步：乾淨的 session，只看任務、這一步的目標、前面各步核對過的事實；這一步技能的規格整份附上（不用先載入）。"""

    def __init__(self, run, item, prev_failure=None):
        self.run_, self.a, self.job, self.item, self.prev_failure = run, run.a, run.job, item, prev_failure
        names = set(self.a.task_skill_names())
        self.allowed = set(item["skills"]) | (TASK_ALWAYS_READ & names)
        self.writable = set(item["skills"]) if item["changes_state"] and item["approved"] else set()
        self.outputs = {}                            # 這一步執行過的工具結果：#編號 → 原文
        self.prior = run.prior_rids(item)            # 這個任務前面做過的工具結果編號（引用時讀回存檔核對）
        self.prior_text = {}                         # 讀回來的：#編號 → 原文（讀不到是 None）
        self.seen = {}                               # 動作 → 做了幾次（同一個動作第 3 次就停）

    def _system(self):
        docs = []
        for skill in sorted(set(self.item["skills"])):
            doc = self.a._load_skill_doc(skill)
            if doc:
                body = doc.split("---", 2)[-1].strip() if doc.startswith("---") else doc.strip()
                docs.append(f"### {skill}\n{body[:3000]}")
        others = sorted(self.allowed - set(self.item["skills"]))
        work = self.run_.profile.get("work")
        return (_read("worker.md") + (f"\n\n## 這一類任務（{self.run_.profile['title']}）\n{work}" if work else "")
                + "\n\n## 這一步的技能規格\n" + "\n\n".join(docs)
                + f"\n\n## 其他可以用的技能（查詢用；action.command 填技能名稱會拿到規格）\n{'、'.join(others)}")

    def _brief(self):
        overview = "\n".join(f"{it['n']}. {it['title']}" + ("　← 你負責這一步" if it is self.item else
                                                              "（之後別人負責，不要做）" if it["status"] == "pending" else
                                                              f"（{_STATUS_TEXT.get(it['status'], it['status'])}）")
                              for it in self.job["items"])
        perm = ("這一步可以改變狀態（使用者已經核准），可以用來改變狀態的技能：" + "、".join(sorted(self.writable))
                if self.writable else "這一步只查詢，不能改變任何狀態")
        parts = [f"【使用者的任務】{self.job['task']}", f"【整份計畫】\n{overview}",
                 f"【你負責的這一步】第 {self.item['n']} 步：{self.item['title']}\n目標：{self.item['goal']}\n{perm}"]
        if self.item.get("check"):
            c = self.item["check"]
            parts.append(f"【做完之後系統會檢查】{c['skill']} {c['args']}，輸出要有「{c['expect']}」")
        before = self.run_.facts_before(self.item)
        if before:
            parts.append("【前面各步的結果與事實】（#編號是那一次工具輸出的存檔）\n" + before)
        if self.prev_failure:
            parts.append(f"【上一次做這一步沒有成功】{self.prev_failure}\n先查清楚現在的狀態再做，不要重複同樣的做法。")
        containers, why = self.a._task_containers()
        parts.append(f"【目前狀態】\n{self.a._task_env_text(containers, why)}")
        return "\n\n".join(parts)

    def _call(self, msgs, schema, turn, kind="worker", num_predict=8192):
        return self.a._task_call(self.job, kind, msgs, schema, num_predict=num_predict,
                                 extra={"item": self.item["n"], "attempt": self.item["attempts"], "turn": turn})

    def run(self):
        a = self.a
        msgs = [{"role": "system", "content": self._system()}, {"role": "user", "content": self._brief()}]
        try:
            a._task_store().append(self.job["id"], "calls.jsonl", {"kind": "worker_start", "item": self.item["n"],
                                                                   "attempt": self.item["attempts"], "messages": msgs})
        except OSError:
            pass
        steps, executed, nudged, last_reply, calls = 0, 0, False, "", []
        while steps < TASK_WORKER_MAX_STEPS:
            steps += 1
            raw, data = self._call(msgs, TASK_WORKER_REPLY_SCHEMA, steps)
            if not raw and data is None:
                return self._result("failed", "模型呼叫失敗（見 calls.jsonl）", [], steps, calls)
            parsed = parse_agent_reply(raw)
            if not parsed.get("valid"):              # 被長度上限截斷、不是完整的 JSON：不執行，請它縮短再回一次
                msgs.append({"role": "assistant", "content": raw[:2000]})
                msgs.append({"role": "user", "content": "[系統] 你的回覆太長被截斷，不是完整的 JSON，這一輪沒有執行。請縮短："
                                                        "thought 一兩句、reply 寫重點，一次只做一個動作。"})
                continue
            msgs.append({"role": "assistant", "content": raw})
            last_reply = (parsed.get("reply") or "").strip() or last_reply
            action = parsed.get("action")
            if not action:
                if executed == 0 and not nudged and self.item["skills"]:
                    nudged = True                    # 一個技能都沒用就說做完了：先推回去一次
                    msgs.append({"role": "user", "content": "[系統] 你還沒有用任何技能。這一步的目標要實際查詢或操作才知道結果："
                                                            "action 填技能的腳本路徑去做，做完再回報。"})
                    continue
                failed = bool(_FAILED_RE.match(last_reply))
                return self._finish(msgs, "failed" if failed else "done", last_reply, (data or {}).get("facts"), steps, calls)
            out, name, payload = self._act(action)
            if out is None:                          # 同一個動作做了 3 次
                return self._result("failed", f"同一個動作做了 3 次還是沒有進展（{payload[:120]}）。{last_reply}", [], steps, calls)
            if not out.startswith(SKILL_DOC_PREFIX) and name:
                executed += 1
                rid = getattr(a, "last_result_id", None)
                if rid:
                    self.outputs[str(rid)] = out
                calls.append({"skill": name, "args": payload.split(maxsplit=1)[1] if len(payload.split(maxsplit=1)) > 1 else "",
                              "status": "ERROR" if out.lstrip().startswith(("[ERROR]", "[DENIED]")) else "PASS",
                              "head": out.strip().splitlines()[0][:200] if out.strip() else "", "rid": rid})
                tag = f"[tool result #{rid}]" if rid else "[tool result]"
            else:
                tag = "[tool result]"
            msgs.append({"role": "user", "content": f"{tag} {payload[:200]}\n{_clip(out)}"})
        # 用完步數：最後請它總結這一步做完了沒有（不能再用技能）。做完了就交給程式的檢查判斷，沒做完才算失敗
        msgs.append({"role": "user", "content": f"[系統] 已經用完 {TASK_WORKER_MAX_STEPS} 輪，不能再用技能了。依上面的執行結果判斷："
                                                "這一步的目標做完了沒有？done 填 true／false；summary 寫做了什麼、看到的關鍵事實；"
                                                "facts 列出關鍵事實（路徑、名稱、數值、修改前→後），ref 填出處的工具結果編號。"})
        raw, data = self._call(msgs, TASK_WORKER_WRAPUP_SCHEMA, steps + 1, kind="worker_wrapup", num_predict=4096)
        data = data or {}
        summary = str(data.get("summary") or "").strip() or last_reply
        if data.get("done") is True and executed:
            return self._finish(msgs, "done", summary, data.get("facts"), steps + 1, calls)
        return self._result("failed", f"做了 {TASK_WORKER_MAX_STEPS} 輪還沒做完。{summary}", [], steps + 1, calls)

    def _act(self, action):
        """執行 worker 的一個動作（權限照計畫）：回傳 (輸出, 技能名稱, 動作文字)；同一個動作第 3 次回 (None, …)。"""
        a = self.a
        payload = action_text(action)
        token = os.path.basename(payload.split()[0]) if payload.strip() else ""
        doc_name = token[:-3] if token.endswith(".md") else token
        if a._load_skill_doc(doc_name) is not None:
            name = doc_name
        else:
            name = a._script_skill_map().get(a._normalize_script_name(token)) or doc_name
        if name not in self.allowed:
            return (f"[ERROR] 這一步不能用 {name}：可以用的技能是 {'、'.join(sorted(self.allowed))}。"
                    f"需要別的技能才做得到的話，就停下來（action 填 null）在 reply 說明。"), None, payload
        info = a.state_change_info({"action": action})
        if info and info["skill"] not in self.writable:
            why = "計畫沒有核准這一步改變狀態" if self.item["changes_state"] else "這一步只查詢"
            return (f"[DENIED] 這個動作會改變狀態（{info['skill']}：{info['reason']}），但{why}，沒有執行。"
                    f"只做這一步的目標；做不到就停下來在 reply 說明。"), None, payload
        key = payload.strip()
        self.seen[key] = self.seen.get(key, 0) + 1
        if self.seen[key] >= 3:
            return None, name, payload
        before = getattr(a, "last_result_id", None)
        out = a._run_tool_once({"action": action}, approved=bool(info)) or "[ERROR] 沒有執行任何東西"
        if getattr(a, "last_result_id", None) == before:
            a.last_result_id = None                  # 規格文件、沒有存檔的：不要沿用上一次的編號
        return out, name, payload

    # ------------------------------------------------ 事實的核對
    def _source(self, ref):
        """事實的出處 → 那份輸出的原文：這一步執行過的，或這個任務前面做過的（讀回存檔）；都不是回 None。"""
        if ref in self.outputs:
            return self.outputs[ref]
        if ref in self.prior:
            if ref not in self.prior_text:
                self.prior_text[ref] = self.a.result_text(ref)
            return self.prior_text[ref]
        return None

    def _check_facts(self, facts, summary):
        """核對 worker 寫的事實：每條要有出處（這一步執行過的、或這個任務前面做過的工具結果 #編號），寫的名稱與數值要在那份輸出裡找得到。
        回傳 (通過的, 對不上的 [(事實, 問題)])。使用者的任務、這一步的目標裡本來就有的字不核對。"""
        allowed = f"{self.job['task']} {self.item['goal']} {self.item['title']}"
        ok, bad = [], []
        for f in facts or []:
            if not isinstance(f, dict):
                continue
            text = _one_line(f.get("text"), 200)
            if not text:
                continue
            m = _RID.search(str(f.get("ref") or ""))
            ref = m.group(1) if m else ""
            src = self._source(ref)
            if src is None:
                mine = "、".join("#" + r for r in self.outputs) or "沒有"
                before = "、".join("#" + r for r in sorted(self.prior, key=lambda r: int(r) if r.isdigit() else 0)) or "沒有"
                bad.append(({"text": text, "ref": ref}, f"出處 #{ref or '?'} 不是這個任務執行過的工具結果（這一步的是 {mine}；"
                                                         f"前面各步的是 {before}）"))
                continue
            missing = missing_tokens(text, src, src, allowed)
            if missing:
                bad.append(({"text": text, "ref": ref}, f"「{'、'.join(missing)}」在 #{ref} 的輸出裡找不到"))
            else:
                ok.append({"text": text, "ref": ref})
        return ok, bad

    def _finish(self, msgs, status, summary, facts, steps, calls):
        """worker 說做完（或沒做完）時：核對事實，對不上的交回改一次（帶著具體的問題），還是不行就拿掉。"""
        ok, bad = self._check_facts(facts, summary)
        if bad and (self.outputs or self.prior):
            ask = ("[系統] 你列的事實有幾條在引用的工具輸出裡找不到（系統核對名稱與數值）：\n"
                   + "\n".join(f"- 「{f['text']}」（#{f['ref']}）：{why}" for f, why in bad)
                   + "\n照輸出的原文改正（或換成正確的出處），找不到根據的就拿掉；facts 輸出完整的清單，summary 照改正後的寫。")
            msgs = msgs + [{"role": "user", "content": ask}]
            raw, data = self._call(msgs, TASK_FACTS_FIX_SCHEMA, steps + 1, kind="worker_facts_fix", num_predict=2048)
            if data:
                ok2, bad2 = self._check_facts(data.get("facts"), data.get("summary"))
                if len(bad2) <= len(bad):
                    ok, bad = ok2, bad2
                    summary = str(data.get("summary") or "").strip() or summary
                steps += 1
        return self._result(status, summary, ok, steps, calls, dropped=[f for f, _ in bad])

    @staticmethod
    def _result(status, summary, facts, steps, calls, dropped=()):
        return {"status": status, "summary": summary or "（沒有說明）", "facts": list(facts)[:8], "dropped": list(dropped),
                "steps": steps, "calls": calls}
