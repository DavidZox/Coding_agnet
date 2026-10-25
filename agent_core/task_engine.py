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

from . import prompt_files
from . import workflow_spec as ws
from .config import (GUARDED_SKILLS, NUM_CTX, PROMPTS_DIR, SKILL_DOC_PREFIX, TASK_JOBS_DIRNAME, TASK_JOBS_KEEP, TASK_MAX_ITEMS,
                     TASK_MAX_REPLANS, TASK_WORKER_MAX_STEPS)
from .extract import missing_tokens
from .jobstore import JobStore
from .protocol import action_text, parse_agent_reply
from .turn_guard import _PROMISE_RE
from .schemas import (TASK_FACTS_FIX_SCHEMA, TASK_GOAL_CHECK_SCHEMA, TASK_PLAN_SCHEMA, TASK_SYNTH_FIX_SCHEMA, TASK_SYNTH_SCHEMA,
                      TASK_WORKER_REPLY_SCHEMA, TASK_WORKER_WRAPUP_SCHEMA, task_profile_schema)

_DIR = os.path.join(PROMPTS_DIR, "orchestra")
DEFAULT_PROFILE = "ops"
REPORT_KIND = "report"                 # 程式加在計畫最後的一步：依核對過的內容寫報告檔（計畫的 output），不派 worker
SYNTH_MAX_ITEMS = 30                   # 整合最多留幾則（給主對話與寫進檔案的）
TASK_SCRIPT = "scripts/task_run_cmd.py"
_ENGINE = "orchestra/engine.md"   # 程式組進給模型的字：標籤、程式檢查的問題、提醒、對照目標的問題（_t 取一則）
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
# worker 說還在做、接著要做（「現在正在查詢…」「接下來我會讀…」）卻沒有動作：不是做完了（主對話的同一種提醒在 turn_guard._PROMISE_RE）
_STILL_WORKING = re.compile(_PROMISE_RE.pattern + r"|(?:正在|開始|準備)\s*(?:幫你|為你)?\s*(?:查詢|查看|查|檢查|確認|讀取|讀|看|搜尋|尋找|找|列出|分析|整理)")
_RID = re.compile(r"#?\s*(\d+)")
_STATUS_TEXT = {"done": "完成", "unverified": "做完了但檢查沒過", "failed": "沒有完成", "pending": "沒有執行", "skipped": "沒有做",
                "replaced": "沒有做成，重排了剩下的步驟"}
_MARK = {"done": "✅", "failed": "❌", "unverified": "⚠️ 檢查沒過", "pending": "⬜", "skipped": "⏭️", "replaced": "↩️ 沒做成、重排了"}


def _t(key, /, **fields):
    """prompts/orchestra/engine.md 的一則，{名稱} 換成 fields。"""
    return prompt_files.load(_ENGINE, key, **fields)


def _read(name):
    """prompts/orchestra/<name> 整份（planner.md、worker.md）。"""
    return prompt_files.load(f"orchestra/{name}")


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


def _writes_path(it, path, definite=False):
    """這一步自己會寫這個檔。definite＝一定會寫：工作流的參數裡有這個路徑（工作流照規格寫，規劃拿不掉）；
    不是 definite 時也算用寫檔的技能、目標裡寫了這個路徑的（可能是備份、讀，只當成交回規劃的提醒）。"""
    if it.get("workflow"):
        return path in " ".join([it.get("workflow_args") or ""] + [str(v) for v in (it.get("inputs") or {}).values()])
    return not definite and bool(set(it["skills"]) & _WRITE_SKILLS) and path in f"{it['title']} {it['goal']}"


def _expect_in_args(check):
    """檢查要看到的字（正規表示式；不合法就當字串，不分大小寫，同 TaskRun.check）在檢查的參數裡就找得到。"""
    expect, args = check.get("expect") or "", check.get("args") or ""
    try:
        return bool(re.search(expect, args, re.I))
    except re.error:
        return expect.lower() in args.lower()


_PLACEHOLDER = re.compile(r"[（(]?\s*(無|沒有|不適用|未知|n/?a|none|unknown|—+|-+)\s*[)）]?[。.]?", re.I)
_INLINE_RID = re.compile(r"\s*[（(]?\s*#(\d+)(?:\s*[、,，]\s*#(\d+))*\s*[)）]?")


def _synth_item(text, refs):
    """整合的一則 → (句子, 出處)：句子裡夾的 #編號（「…Up #3」「…（#4、#6）」）拿出來併進出處，排版時出處另外附在最後。"""
    refs = [str(r).strip() for r in refs or [] if str(r).strip()][:4]
    text = " ".join(str(text or "").split())
    inline = [m for m in re.findall(r"#(\d+)", "".join(x.group(0) for x in _INLINE_RID.finditer(text)))]
    have = {m.group(1) for m in (_RID.search(r) for r in refs) if m}
    refs += [r for r in dict.fromkeys(inline) if r not in have][:max(0, 4 - len(refs))]
    text = _INLINE_RID.sub("", text).strip(" ，,；;")
    if _PLACEHOLDER.fullmatch(text):
        return "", refs                              # 「無」「unknown」這種佔位的一則：不是內容，不算拿掉
    return text, refs


def synth_count(syn):
    """整合裡核對過的則數（沒有整合是 0）。"""
    return sum(len(s["items"]) for s in (syn or {}).get("sections") or [])


def _refs_text(refs):
    out = []
    for r in refs or []:
        m = _RID.search(str(r))
        if m and f"#{m.group(1)}" not in out:
            out.append(f"#{m.group(1)}")
    return "、".join(out)


def synth_markdown(job, syn, append=False):
    """整合的結果 → 報告檔的 Markdown（程式排版；每一則後面附出處）。append＝附加到既有的檔案（標題降一級）。"""
    h1, h2 = ("##", "###") if append else ("#", "##")
    lines = [f"{h1} {syn.get('title') or job['task'][:60]}", "",
             f"（{time.strftime('%Y-%m-%d %H:%M')} 由任務 {job['id']} 整理；每一則都核對過出處，括號裡的 #編號是工具輸出的存檔）", ""]
    for sec in syn.get("sections") or []:
        lines.append(f"{h2} {sec['heading'] or '內容'}")
        lines += [f"- {x['text']}（{_refs_text(x['refs'])}）" for x in sec["items"]]
        lines.append("")
    if syn.get("unknowns"):
        lines += [f"{h2} 還不確定、沒查到的", syn["unknowns"], ""]
    return "\n".join(lines).rstrip() + "\n"


def parse_profile(text, name):
    """prompts/orchestra/profiles/<名稱>.md → {name, title, description, changes_state, synthesis, plan, work, synth}。frontmatter 照 OKF
    （type: Profile）：knowledge＝另外附上哪幾個類型的〈規劃〉〈執行〉當領域知識（調查、整理報告用維運的：在哪裡找、用哪個技能查）；
    changes_state: false＝只查不改（計畫裡要改變狀態的步驟由程式擋下；寫報告檔例外，見 output）；synthesis：最後要不要
    整合——findings＝依查到的事實寫結論、report＝寫成報告、none（預設）＝程式的報告就夠（要寫報告檔時照樣整合）。
    「# 規劃」一節給規劃 session，「# 執行」一節給 worker，「# 整合」一節給整合的 session。"""
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
    synthesis = meta.get("synthesis", "none").strip().lower()
    return {"name": meta.get("name") or name, "title": meta.get("title") or name, "description": meta.get("description", ""),
            "type": meta.get("type", ""), "changes_state": meta.get("changes_state", "true").strip().lower() != "false",
            "synthesis": synthesis if synthesis in ("findings", "report") else "none",
            "knowledge": [k.strip() for k in re.split(r"[,，、\s]+", meta.get("knowledge", "")) if k.strip() and k.strip() != name],
            "plan": sections.get("規劃", ""), "work": sections.get("執行", ""), "synth": sections.get("整合", "")}


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

    def _task_pick_profile(self, task):
        """沒有指定類型（--profile）時選一個：只有一種就是它；有好幾種時問一次（task_profile_schema：enum 只有現有的類型、一句理由）。
        回傳 (類型, {"reason", "record"} 或 None)；問不出來用 DEFAULT_PROFILE。record 等工作有編號之後記進 calls.jsonl。"""
        profiles = self.task_profiles()
        default = self.load_task_profile(DEFAULT_PROFILE) or (profiles[0] if profiles else
                                                             {"name": DEFAULT_PROFILE, "title": DEFAULT_PROFILE, "description": "",
                                                              "changes_state": True, "synthesis": "none", "plan": "", "work": "", "synth": ""})
        if len(profiles) < 2:
            return default, None
        listing = "\n".join(_t("profile_pick_item", name=p["name"], title=p["title"], description=p["description"]) for p in profiles)
        messages = [{"role": "system", "content": _t("profile_pick_system")},
                    {"role": "user", "content": _t("profile_pick_user", profiles=listing, task=task)}]
        raw, data, err = "", None, None
        t0 = time.time()
        try:
            res = self._timed_chat("task_profile", model=self.model, messages=messages, format=task_profile_schema([p["name"] for p in profiles]),
                                   options={"temperature": 0.0, "num_ctx": NUM_CTX, "num_predict": 512}, think=False)
            raw = res["message"]["content"]
            data = json.loads(raw)
        except Exception as e:   # noqa: BLE001  問不出來：用預設的類型
            err = f"{type(e).__name__}: {e}"
        chosen = next((p for p in profiles if isinstance(data, dict) and p["name"] == data.get("profile")), None)
        record = {"kind": "profile", "seconds": round(time.time() - t0, 1), "response": raw, "error": err, "messages": messages}
        return chosen or default, {"reason": _one_line((data or {}).get("reason") if isinstance(data, dict) else "", 200)
                                   if chosen else f"沒有選出類型，用預設的 {default['name']}", "record": record}

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
            need = "\n".join(_t("wf_catalog_input", name=i["name"], optional=_t("wf_catalog_optional") if i["optional"] else "",
                                 description=_one_line(i["description"], 160)) for i in wf["inputs"])
            lines.append(_t("wf_catalog_item", name=wf["name"], description=wf["description"], inputs=need or _t("wf_catalog_no_inputs")))
        return "\n".join(lines) or _t("wf_catalog_none")

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
        lines = [_t("env_time", now=time.strftime('%Y-%m-%d %H:%M')),
                 _t("env_cwd", cwd=self.current_cwd, count=len(entries), entries=shown),
                 _t("env_target", target=self.target_container or _t("env_target_none"))]
        if containers:
            items = sorted(containers.items())
            lines.append(_t("env_containers", containers="；".join(f"{n}：{c['status']}" for n, c in items[:30]))
                         + (_t("env_containers_more", count=len(items)) if len(items) > 30 else ""))
        elif why:
            lines.append(_t("env_containers_unknown", why=why))
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
    def _task_item(self, raw, n, profile=None):
        """模型（或使用者）給的一步 → 清理過的 item 與問題清單。做不了的一步標 broken（工作流不存在、有【確認】、參數不對；
        要改變狀態卻沒有可以用的技能；列的技能全都不存在；只查不改的類型裡要改變狀態）：修一次還是這樣，整份計畫不執行（_task_broken）。"""
        it, issues = self._task_item_raw(raw, n)
        if profile and not profile.get("changes_state", True) and it["changes_state"]:
            if it.get("changes_by") == "words":
                # 兩用的技能（docker_ctl、rmf_handshake…）只因為目標的字（「啟動失敗」「是否一直回 no」）被判成要改：調查的目標常這樣寫
                # （2026-10-25 試跑：inv_two_stuck、inv_nav2_map 的計畫全被擋）。只查不改的類型照只查詢做——worker 本來就改不了
                it["changes_state"] = False
            else:
                it["broken"] = it["readonly_blocked"] = True
                issues.append(_t("issue_readonly_profile", n=n, title=profile["title"]))
        return it, issues

    def _task_item_raw(self, raw, n):
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
            issues.append(_t("issue_unknown_skills", n=n, skills='、'.join(unknown)))
        if wf_name:
            wf = self.load_workflow(wf_name)
            if not wf:
                issues.append(_t("issue_no_workflow", n=n, workflow=wf_name))
            elif any(s["kind"] == "確認" for s in wf["steps"]):
                issues.append(_t("issue_workflow_confirm", n=n, workflow=wf_name))
            else:
                action, _, values, err = self._wf_parse_args(f"{wf_name} {wf_args}")
                inputs, err2 = (None, err) if err else self._wf_check_inputs(wf, values)
                if err2:
                    issues.append(_t("issue_workflow_args", n=n, workflow=wf_name, error=_one_line(err2, 300)))
                else:
                    it.update(workflow=wf_name, workflow_args=wf_args, inputs=inputs,
                              skills=list((wf.get("meta") or {}).get("dependencies") or []),
                              changes_state=bool(self._wf_segment(wf, 1, inputs)))
            if not it["workflow"]:
                it["broken"] = True
            return it, issues
        mentioned = [w for w in workflows if re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", f"{title} {goal}")]
        if mentioned:
            issues.append(_t("issue_workflow_in_goal", n=n, workflows='、'.join(mentioned)))
        if not skills:
            if it["changes_state"] or (raw_skills and unknown):
                it["broken"] = True              # 要改變狀態卻沒有技能、列的技能全都不存在：worker 做不了
            issues.append(_t("issue_no_skills", n=n))
        write = _WRITE_WORDS.search(goal) and _PATH.search(goal)
        if write and not set(skills) & _WRITE_SKILLS:
            issues.append(_t("issue_write_needs_file_ops", n=n, path=_PATH.search(goal).group(0)))
        changes = it["changes_state"]
        it["changes_by"] = "plan" if changes else ""
        if any(s in GUARDED_SKILLS and s not in TASK_ALWAYS_READ for s in skills):
            changes = True                           # file_ops、ROS2_topic_pub、workpackage_send…：一定會改變狀態
            it["changes_by"] = it["changes_by"] or "skill"
        elif not changes and _mentions_change(f"{title} {goal}") and any(s in GUARDED_SKILLS for s in skills):
            changes = True                           # 兩用的技能（docker_ctl restart、ROS2_param set…）而目標寫了要改
            it["changes_by"] = "words"
        it["changes_state"] = changes
        check = raw.get("check") if isinstance(raw.get("check"), dict) else None
        if check and changes:
            cs = str(check.get("skill") or "").strip()
            check = {"skill": cs, "args": str(check.get("args") or "").strip(), "expect": str(check.get("expect") or "").strip()}
            if cs not in names:
                issues.append(_t("issue_unknown_check_skill", n=n, skill=cs))
            elif check["expect"] and _expect_in_args(check):
                # 要看到的字就在檢查的參數裡：輸出的開頭本來就照列參數（view_file 的檔名、ROS2_param 的名稱），一定找得到，
                # 檢查不出做完了沒（待辦 26，2026-10-25 cx_incident_timeline：expect「timeline」落在 reports/<報告> 的檔名上）。
                # 交回規劃改；修一次還是這樣就不用這個檢查，報告寫「沒有驗證」
                issues.append(_t("issue_expect_in_args", n=n, expect=check["expect"], args=check["args"]))
                it["check_note"] = f"計畫寫的檢查（{cs} {check['args']} 要看到「{check['expect']}」）要找的字就在參數裡，看不出做完了沒，沒有驗證"
            elif check["expect"]:
                it["check"] = check
        return it, issues

    def _task_clean(self, data, start=1, profile=None):
        items, issues = [], []
        for raw in (data or {}).get("items") or []:
            if not isinstance(raw, dict) or not (raw.get("title") or raw.get("goal") or raw.get("workflow")):
                continue
            it, problems = self._task_item(raw, start + len(items), profile)
            items.append(it)
            issues += problems
        if len(items) > TASK_MAX_ITEMS:
            issues.append(_t("issue_too_many_steps", count=len(items), max=TASK_MAX_ITEMS))
        return items[:TASK_MAX_ITEMS], issues

    def _task_output(self, data, items, done=(), accepted=None):
        """計畫的 output（要寫的報告檔）→ ({path, mode} 或 None, 問題清單)。報告檔由程式最後依核對過的內容寫（REPORT_KIND 那一步），
        所以：路徑要是工作目錄裡的檔案、已經有的檔案要說清楚是附加還是整份換掉；不能另外排一步自己寫同一個檔；要先有收集資料的步驟。"""
        out = (data or {}).get("output") if isinstance((data or {}).get("output"), dict) else {}
        path = str(out.get("path") or "").strip().strip("\"'`")
        if not path:
            return None, []
        mode = "append" if str(out.get("mode") or "").strip() == "append" else "write"
        issues = []
        full = os.path.join(self.current_cwd, os.path.expanduser(path))
        if path.endswith(("/", "\\")) or os.path.isdir(full) or not re.search(r"[^/\\]\.[A-Za-z0-9]{1,6}$", path):
            issues.append(_t("issue_output_not_file", path=path))
            return None, issues
        if mode == "write" and os.path.isfile(full) and accepted != {"path": path, "mode": mode}:
            issues.append(_t("issue_output_exists", path=path))   # 重排時照原本接受過的寫法就不再問
        for it in items:
            if _writes_path(it, path):
                issues.append(_t("issue_output_written_by_step", n=it["n"], path=path))
        if not items and not list(done):
            issues.append(_t("issue_output_needs_steps", path=path))
        return {"path": path, "mode": mode}, issues

    def _task_place_report(self, job):
        """計畫有 output 時，最後一步是程式寫報告（每次規劃、重排之後重新接在最後；已經寫過的不再加）。"""
        items = [it for it in job["items"] if not (it.get("kind") == REPORT_KIND and it["status"] == "pending")]
        out = job.get("output")
        if out and not any(it.get("kind") == REPORT_KIND for it in items):
            verb = "附加到" if out["mode"] == "append" else "寫成"
            items.append({"n": len(items) + 1, "kind": REPORT_KIND, "title": f"把報告{verb} {out['path']}"[:60],
                          "goal": f"系統依前面各步核對過的事實整理報告，{verb} {out['path']}（每一則附出處，程式核對）",
                          "skills": ["file_ops"], "workflow": "", "workflow_args": "", "inputs": {}, "changes_state": True,
                          "check": None, "approved": False, "status": "pending", "summary": "", "facts": [], "dropped": [],
                          "attempts": 0, "steps": 0, "evidence": "", "calls": [], "output": dict(out)})
        job["items"] = items

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
                        issues.append(_t("issue_container_started_later", n=it['n'], container=c, status=containers[c]['status'], later=later['n']))
                    else:
                        issues.append(_t("issue_container_stopped", n=it['n'], container=c, status=containers[c]['status']))
        m = _DOC_WORDS.search(job["task"])
        first_change = next((k for k, it in enumerate(items) if it["changes_state"]), None)
        if m and first_change is not None:
            read_before = any(set(it["skills"]) & _READ_SKILLS for it in list(done) + items[:first_change])
            if not read_before:
                issues.append(_t("issue_read_document_first", doc=m.group(0)))
        return issues

    # ---------------------------------------------------------------- 規劃（第一版）與重排
    def _task_knowledge(self, profile, part):
        """類型的 knowledge：別的類型的〈規劃〉或〈執行〉（part＝plan／work）當領域知識附在後面。"""
        out = []
        for name in profile.get("knowledge") or []:
            base = self.load_task_profile(name)
            if base and base.get(part):
                out.append("\n\n" + _t("knowledge_header", title=base["title"]) + "\n" + base[part])
        return "".join(out)

    def _task_planner_system(self, profile):
        return (_read("planner.md") + ("\n\n" + _t("worker_profile_header", title=profile["title"]) + "\n" + profile["plan"]
                                       if profile.get("plan") else "") + self._task_knowledge(profile, "plan"))

    def _task_plan_call(self, job, profile, user, kind):
        """規劃（或重排）一次；有程式檢查出的問題就帶著問題交回修一次。回傳 (data, items, issues, output)。"""
        system = self._task_planner_system(profile)
        containers, why = self._task_containers()
        done = [it for it in job["items"] if it["status"] != "pending"]
        start = len(done) + 1
        user = user.replace("{ENV}", self._task_env_text(containers, why))

        def clean(d):
            its, iss = self._task_clean(d, start, profile)
            iss += self._task_issues(job, its, containers, done)
            out, iss2 = self._task_output(d, its, done, job.get("output"))
            return its, iss + iss2, out

        _, data = self._task_call(job, kind, [{"role": "system", "content": system}, {"role": "user", "content": user}], TASK_PLAN_SCHEMA)
        job["plan_calls"] = job.get("plan_calls", 0) + 1
        items, issues, output = clean(data)
        if issues and data is not None:
            fix = _t("plan_fix", plan=user, previous=json.dumps({"items": data.get("items"), "output": data.get("output")},
                                                                 ensure_ascii=False)[:4000],
                     issues="\n".join(f"- {x}" for x in issues))
            _, data2 = self._task_call(job, kind + "_fix", [{"role": "system", "content": system}, {"role": "user", "content": fix}],
                                       TASK_PLAN_SCHEMA)
            job["plan_calls"] += 1
            items2, issues2, output2 = clean(data2)
            score = lambda its, iss: (len(_task_broken(its)), len(iss))   # noqa: E731  做不了的步驟少的優先，再看問題的數量
            if items2 and score(items2, issues2) <= score(items, issues):
                data, items, issues, output = data2, items2, issues2, output2
        writers = [it for it in items if output and _writes_path(it, output["path"], definite=True)]
        if writers:
            # 修一次之後還是有步驟自己寫這個檔（多半是工作流自己會寫紀錄，規劃拿不掉）：不另外寫報告，不然同一個檔寫兩次
            # （2026-10-25 階段驗證 cx_restart_verify：container_restart_verify 工作流記了一筆，程式又附加了一份）
            issues.append(_t("issue_output_dropped", n=writers[0]["n"], path=output["path"]))
            output = None
        return data, items, issues, output

    def task_plan(self, task, profile_name=None, mode="auto"):
        """第一版計畫 → (job, 錯誤)。mode：auto＝task_run（只有一步的任務不用規劃，回錯誤）；plan＝Plan 模式的草稿（使用者自己看、改）。"""
        task = " ".join((task or "").strip().strip('"').strip("'").split())
        if len(task) < 4:
            return None, "[ERROR] task_run 需要任務描述：args 填使用者的原話。"
        t0 = time.time()
        picked = None
        if profile_name:
            profile = self.load_task_profile(profile_name)
            if not profile:
                names = "、".join(p["name"] for p in self.task_profiles()) or "（沒有）"
                return None, f"[ERROR] 沒有任務類型 {profile_name}：現有的是 {names}。下一步：不帶 --profile（系統會選），或照這幾個名稱寫。"
        else:
            profile, picked = self._task_pick_profile(task)
        store = self._task_store()
        job = {"id": store.new_id(profile["name"]), "profile": profile["name"], "task": task, "mode": mode, "status": "planning",
               "items": [], "plans": [], "replans": 0, "plan_calls": 0, "model_calls": 0, "seconds": 0.0,
               "created": time.strftime("%Y-%m-%d %H:%M:%S"), "model": self.model}
        if picked:                                   # 選類型的那一次呼叫：有了工作編號才記得進 calls.jsonl
            job["profile_reason"] = picked.get("reason", "")
            job["model_calls"] += 1
            try:
                store.append(job["id"], "calls.jsonl", picked["record"])
            except OSError:
                pass
        self._task_note(job, f"🧭 任務（{profile['title']}）：規劃中…")
        user = _t("plan_user", skills=self._task_catalog(), workflows=self._task_workflow_catalog(), task=task)   # {ENV}：_task_plan_call 換
        data, items, issues, output = self._task_plan_call(job, profile, user, "plan")
        job["seconds"] += round(time.time() - t0, 1)
        job.update(items=items, issues=issues, status="draft" if mode == "plan" else "planned", output=output,
                   understanding=_one_line((data or {}).get("understanding"), 400), summary=_one_line((data or {}).get("summary"), 200),
                   report_focus=_one_line((data or {}).get("report"), 300))
        if items:
            self._task_place_report(job)
            items = job["items"]
        job["plans"].append({"version": 1, "why": "第一版", "items": [it["title"] for it in items], "issues": issues})
        self._task_save(job)
        if not items:
            return None, ("[ERROR] 規劃 session 沒有給出可以執行的步驟" + (f"（{'；'.join(issues)}）" if issues else "")
                          + "：這個任務直接用技能一步一步做。")
        broken = _task_broken(items)
        if broken and mode == "auto":
            # 修一次還是有做不了的步驟：不照著做（以前照做，worker 找不到工具、做滿 10 輪才失敗——2026-10-24 cx_batch_dispatch）
            if any(it.get("readonly_blocked") for it in broken):
                return None, (f"[ERROR] 這個任務要改變狀態（第 {'、'.join(str(it['n']) for it in broken if it.get('readonly_blocked'))} 步），"
                              f"但選的類型是{profile['title']}（只查不改），這次沒有執行任何步驟。下一步：要改的話用 "
                              f"task_run --profile {DEFAULT_PROFILE} \"<任務>\"；只要查的話照原話再交給 task_run（說清楚只查不改）。")
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
        profile = self.load_task_profile(job["profile"]) or {"title": job["profile"], "plan": "", "changes_state": True}
        done = [it for it in job["items"] if it["status"] != "pending"]
        rest = [it for it in job["items"] if it["status"] == "pending" and it.get("kind") != REPORT_KIND]
        self._task_note(job, f"🧭 {why}：照前面查到的事實重排剩下的步驟…")
        out = job.get("output")
        user = _t("replan_user", skills=self._task_catalog(), workflows=self._task_workflow_catalog(), task=job["task"],
                  done=self._task_facts_text(done), why=why,
                  rest="\n".join(_t("replan_rest_item", title=it["title"], goal=it["goal"]) for it in rest) or _t("replan_rest_none"),
                  output=_t("replan_output", path=out["path"], mode=out["mode"]) if out else _t("replan_output_none"))
        t0 = time.time()
        data, items, issues, output = self._task_plan_call(job, profile, user, "replan")
        job["seconds"] += round(time.time() - t0, 1)
        job["replans"] += 1
        if data is None or (not items and not allow_empty) or _task_broken(items):
            job["plans"].append({"version": len(job["plans"]) + 1, "why": why, "items": None,
                                 "issues": ["規劃 session 沒有給出可以執行的新步驟，保留原本的"] + issues})
            return False
        job["items"] = done + items
        if output:                                   # 重排可以改報告檔；沒寫就照原本的（使用者要的檔案不因為重排就不寫）
            job["output"] = output
        self._task_place_report(job)
        if data.get("report"):
            job["report_focus"] = _one_line(data["report"], 300)
        job["plans"].append({"version": len(job["plans"]) + 1, "why": why, "items": [it["title"] for it in items], "issues": issues})
        self._task_save(job)
        return True

    # ---------------------------------------------------------------- 給人看的計畫、事實
    @staticmethod
    def task_item_text(it):
        if it.get("kind") == REPORT_KIND:
            return f"{it['n']}. {it['title']}（⚠️ 會改變狀態；系統依核對過的事實寫，寫完讀回來比對）\n   {it['goal']}"
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
            line = _t("facts_step", n=it["n"], title=it["title"], status=_STATUS_TEXT.get(it["status"], it["status"]),
                      summary=_clip(it["summary"], limit))
            for f in it.get("facts") or []:
                line += "\n" + _t("facts_item", text=f["text"], ref=f["ref"])
            if it.get("evidence"):
                line += "\n" + _t("facts_check", evidence=it["evidence"])
            out.append(line)
        return "\n".join(out) or _t("facts_none")

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
        if cur and cur.get("status") == "planned" and cur["task"] == task and (not profile or cur["profile"] == profile):
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
            preview = ""
            if any(it.get("kind") == REPORT_KIND for it in changing) and job.get("synthesis"):
                body = synth_markdown(job, job["synthesis"], append=job["output"]["mode"] == "append")
                preview = f"\n要寫進 {job['output']['path']} 的內容：\n{_clip(body, 2500)}"
            return (f"任務接著做：會改變狀態的是 {_steps_text(changing)}"
                    + (f"\n已經查到的：\n{self._task_facts_text(done, 300)}" if done else "")
                    + "\n" + self.task_plan_text(job, pending_only=True) + preview)
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
            thought, reply = _t("continue_plan_thought"), _t("continue_plan_reply")
        else:
            thought, reply = _t("continue_survey_thought"), _t("continue_survey_reply")
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
                only_report = all(x.get("kind") == REPORT_KIND for x in job["items"] if x["status"] == "pending")
                if (job["mode"] == "auto" and done and not job.get("surveyed") and job["replans"] < TASK_MAX_REPLANS
                        and not only_report):
                    job["surveyed"] = True           # 先查的步驟做完了：照查到的事實重排要改的部分（只重排一次）
                    a._task_replan(job, _t("replan_why_surveyed"))
                    continue
                if it.get("kind") == REPORT_KIND:
                    # 寫報告檔之前先整合、核對：確認時使用者看得到要寫進去的內容；沒有核對過的內容就不寫、不用問
                    if not job.get("synthesis"):
                        self.synthesize()
                    if not synth_count(job["synthesis"]):
                        it.update(status="failed", attempts=it["attempts"] + 1,
                                  summary="整合不出核對過的內容，報告檔沒有寫（" + (job["synthesis"].get("note") or "每一則都對不上引用的輸出") + "）")
                        self.save()
                        break
                job["status"] = "awaiting_approval"
                job["seconds"] += round(time.time() - t0, 1)
                self.save()
                a.task_pending_approval = job["id"]
                self.note(f"⏸️ 任務查完了，要改變狀態的步驟等使用者確認（工作 {job['id']}）")
                return self.report()
            n_items = len(job["items"])
            self.note(f"🧭 任務第 {it['n']}/{n_items} 步：{it['title']}")
            if it.get("kind") == REPORT_KIND:
                self.do_report(it)
                self.save()
                if it["status"] == "failed":
                    break                            # 程式寫的報告沒寫成：重排也幫不上（內容就是前面查到的）
                continue
            self.do_item(it)
            self.save()
            if it["status"] in ("done", "unverified") and it.get("finding") and job["mode"] == "auto" and job["replans"] < TASK_MAX_REPLANS:
                # worker 說沒有完成、對照目標其實做到了：查到的狀況（問題還在）可能讓剩下的步驟不夠用（例如 domain 不對，要換一個再讀），
                # 照它重排剩下的步驟（不重試這一步）；規劃覺得不用再做什麼可以給空的。這就是照查到的事實重排過了：要改狀態之前不再重排
                # 一次（2026-10-24 cx_reassign：連著重排兩次把次數用完，後面的步驟失敗時就沒得重排）
                job["surveyed"] = True
                a._task_replan(job, _t("replan_why_finding", n=it["n"], title=it["title"], summary=_one_line(it["summary"], 300)))
                continue
            if it["status"] == "failed":
                if job["mode"] == "auto" and job["replans"] < TASK_MAX_REPLANS:
                    why = _t("replan_why_failed", n=it["n"], title=it["title"], summary=_one_line(it["summary"], 300))
                    it["status"] = "replaced"        # 先標成「重排了」：重排得出來就照新的做，這一步不算整個任務失敗
                    if a._task_replan(job, why, allow_empty=False):
                        continue
                    it["status"] = "failed"
                break
        if self.profile.get("synthesis") in ("findings", "report") and not job.get("synthesis"):
            self.synthesize()                        # 調查、整理報告：最後依核對過的事實整合（沒有報告檔時放在給主對話的報告裡）
        failed = next((x for x in job["items"] if x["status"] == "failed"), None)
        unverified = [x for x in job["items"] if x["status"] == "unverified"]
        job["status"] = "failed" if failed else ("unverified" if unverified else "done")
        if job["status"] == "done" and job.get("synthesis") is not None and not synth_count(job["synthesis"]):
            job["status"] = "unverified"             # 整份的成功判準：要的是結論或報告，卻整合不出核對過的內容
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
            # 前一次（重試之前）核對過的事實也留著：都是那個時候在輸出裡看得到的（以前重試的結果整個蓋掉）
            seen = {f["text"] for f in res["facts"]}
            it["facts"] = res["facts"] + [f for f in it["facts"] if f["text"] not in seen]
            it["summary"], it["dropped"] = res["summary"], res["dropped"]
            it["finding"] = bool(res.get("finding"))
            if res["status"] != "done":
                it["status"] = "failed"
                prev_failure = res["summary"]
                continue
            result, evidence, out = self.check(it)
            it["evidence"] = evidence
            if result == "pass":
                it["status"] = "done"
                return
            if result == "error":
                # 檢查出錯：多半是計畫寫的檢查不對，也可能正是沒做到的證據——對照目標問一次，做到了才算完成（標明程式沒有驗證）
                met, why = self.check_error_goal(it, res, out)
                if met:
                    it["status"] = "done"
                    it["evidence"] = f"{evidence}；程式沒有驗證，對照目標判斷做到了：{why}"
                    return
                it["evidence"] = evidence = f"{evidence}；對照目標判斷還沒做到" + (f"：{why}" if why else "")
                retry = _t("retry_check_error", evidence=evidence)
            else:
                retry = _t("retry_check_miss", evidence=evidence)
            # 換一個 worker 帶著檢查的輸出再做一次；第二次還是不過，多半是計畫寫的檢查條件不適用（例如要「看到 0」卻是「找不到」）——
            # 不擋下後面的步驟，標成「檢查沒過」交給主對話與使用者確認
            it["status"] = "unverified"
            prev_failure = retry

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
                # 輸出的開頭幾行（第一行常只是「執行完成」，值在下一行：2026-10-25 container_restart_verify 的 grep max_size）
                lines = [ln.strip() for ln in (a.result_text(st["rid"]) or "").splitlines() if ln.strip()]
                head = " ".join(lines[:3]) if lines else st.get("head")
                facts.append({"text": f"{ws.show(s['title'], it['inputs'])}：{_one_line(head, 240)}", "ref": str(st["rid"])})
        it["facts"] = facts[:8]
        it["summary"] = _one_line(report.splitlines()[0] if report else "", 400)
        it["status"] = {"done": "done", "ended": "done", "unverified": "unverified"}.get(wjob["status"], "failed")

    def check(self, it):
        """worker 回報完成後由程式跑 check（唯讀技能）：輸出要找得到 expect（正規表示式，不合法就當字串；不分大小寫）。
        回傳 (結果, 證據, 輸出)：pass＝找得到（沒有檢查、檢查跑不了的也算，證據寫「沒有驗證」）；miss＝找不到；error＝檢查回 [ERROR]
        （程式分不出是計畫寫的檢查不對、還是這一步沒做到，do_item 對照目標問一次）。"""
        a = self.a
        chk = it.get("check")
        if not chk:
            return "pass", (f"（{it['check_note']}）" if it.get("check_note") else ""), ""
        script = next((s for s, name in a._script_skill_map().items() if name == chk["skill"]), None)
        if not script:
            return "pass", f"（檢查技能 {chk['skill']} 找不到腳本，沒有驗證）", ""
        parsed = {"action": {"command": f"scripts/{script}", "args": chk["args"]}}
        if a.state_change_info(parsed):
            return "pass", "（檢查用的動作會改變狀態，沒有執行、沒有驗證）", ""
        out = a._run_tool_once(parsed, approved=False) or ""
        first = out.strip().splitlines()[0][:200] if out.strip() else "（沒有輸出）"
        rid = getattr(a, "last_result_id", None)
        ref = f"（#{rid}）" if rid else ""
        if out.lstrip().startswith("[ERROR]"):
            return "error", f"{chk['skill']} {chk['args']} → 檢查出錯（{first}）{ref}", out
        try:
            hit = re.search(chk["expect"], out, re.I)
        except re.error:
            hit = chk["expect"].lower() in out.lower()
        return ("pass" if hit else "miss"), f"{chk['skill']} {chk['args']} → {'有' if hit else '沒有'}「{chk['expect']}」（{first}）{ref}", out

    def check_error_goal(self, it, res, out):
        """檢查回 [ERROR]：對照這一步的目標問一次做到了沒有（TASK_GOAL_CHECK_SCHEMA）。只看系統記下的動作與檢查的輸出，不是 worker 說的。
        檢查出錯多半是計畫寫的檢查不對（2026-10-24～25 維運評測 15 次：17 次出錯裡 13 次是參數寫反、選項不存在、用了還不知道的編號，
        2 次是刪除之後本來就查不到，1 次是容器裡沒有那個指令），但也可能正是沒做到的證據（cx_incident_timeline：worker 只建了目錄
        就說報告寫好了，檢查讀不到報告——以前一律算完成、標「沒有驗證」，任務報 [PASS]）。一律當成沒過的話，計畫寫錯的檢查每次都多一個
        worker、還報「檢查沒過」。回傳 (做到了沒, 判斷的根據)；問不出來當成沒做到（換 worker 重試，不會報錯的完成）。"""
        chk = it["check"]
        acts = ("\n".join(_t("check_error_action", skill=c["skill"], args=_one_line(c["args"], 160), head=c["head"]) for c in res.get("calls") or [])
                or _t("check_error_no_actions"))
        ask = _t("check_error_ask", task=self.job["task"], n=it["n"], title=it["title"], goal=it["goal"],
                 report=_one_line(res.get("summary"), 600), actions=acts, skill=chk["skill"], args=chk["args"], expect=chk["expect"],
                 output=_clip(out, 1500))
        msgs = [{"role": "system", "content": _t("check_error_system")},
                {"role": "user", "content": ask}]
        raw, data = self.a._task_call(self.job, "check_error", msgs, TASK_GOAL_CHECK_SCHEMA, num_predict=2048,
                                      extra={"item": it["n"], "attempt": it["attempts"]})
        why = _one_line((data or {}).get("summary"), 400)
        return bool(data) and data.get("goal_met") is True and bool(why), why

    # ------------------------------------------------ 整合（Synthesizer）：依核對過的事實寫結論或報告，每一則附出處、程式核對
    def job_rids(self):
        """這個任務做過的工具結果編號（worker 與工作流每一步的輸出、程式跑的檢查）：整合只能引用這些。"""
        rids = set()
        for x in self.job["items"]:
            rids |= {str(c["rid"]) for c in x.get("calls") or [] if c.get("rid")}
            rids |= {str(f["ref"]) for f in x.get("facts") or [] if f.get("ref")}
            rids |= set(re.findall(r"#(\d+)", x.get("evidence") or ""))
        return rids

    def _output(self, rid):
        cache = self.__dict__.setdefault("_outputs", {})
        if rid not in cache:
            cache[rid] = self.a.result_text(rid)
        return cache[rid]

    def _synth_steps_text(self, items):
        out = []
        for it in items:
            lines = [_t("synth_step", n=it["n"], title=it["title"], status=_STATUS_TEXT.get(it["status"], it["status"]),
                        summary=_clip(it["summary"], 1500))]
            lines += [_t("synth_action", skill=c["skill"], args=_one_line(c["args"], 160), head=c["head"], rid=c["rid"])
                      for c in it.get("calls") or [] if c.get("rid")]
            lines += [_t("facts_item", text=f["text"], ref=f["ref"]) for f in it.get("facts") or []]
            if it.get("evidence"):
                lines.append(_t("facts_check", evidence=it["evidence"]))
            out.append("\n".join(lines))
        return "\n".join(out)

    def _synth_check(self, text, refs, rids, allowed):
        """一則 → 問題（None＝核對過）：要有出處、出處是這個任務的工具結果、名稱與數值在引用的輸出裡（extract.missing_tokens）。"""
        cited = []
        for r in refs or []:
            m = _RID.search(str(r))
            if m and m.group(1) not in cited:
                cited.append(m.group(1))
        if not cited:
            return _t("synth_no_ref")
        bad = [r for r in cited if r not in rids]
        if bad:
            return _t("synth_bad_ref", refs="、".join("#" + r for r in bad),
                      rids="、".join("#" + r for r in sorted(rids, key=lambda r: int(r) if r.isdigit() else 0)))
        texts = [self._output(r) for r in cited]
        if any(t is None for t in texts):
            return _t("synth_unreadable", refs="、".join("#" + r for r, t in zip(cited, texts) if t is None))
        ev = "\n".join(texts)
        missing = missing_tokens(text, ev, ev, allowed)
        return _t("synth_not_found", tokens="、".join(missing), refs="、".join("#" + r for r in cited)) if missing else None

    @staticmethod
    def _excerpt(text, sources, n=6):
        """交回改的時候附上引用的輸出裡跟這一則相關的幾行（有同樣的英數字的行），讓它照原文改。"""
        toks = {w.lower() for w in re.findall(r"[A-Za-z0-9_/.\-:]{2,}", text or "")}
        out = []
        for src in sources:
            for ln in (src or "").splitlines():
                if toks and any(w in ln.lower() for w in toks) and ln.strip() not in out:
                    out.append(ln.strip()[:200])
                    if len(out) >= n:
                        return out
        return out

    def synthesize(self):
        """所有步驟做完（或要寫報告檔之前）：整合的 session 依各步核對過的事實寫結論或報告（TASK_SYNTH_SCHEMA）。程式核對每一則
        （_synth_check），對不上的只把那幾則交回改一次（TASK_SYNTH_FIX_SCHEMA），還是不行就拿掉、註明；unknowns 也核對（對不上就不留）。
        結果存在 job["synthesis"]（給主對話的報告與報告檔都從這裡排版）；prompt 與原文在 calls.jsonl（kind＝synth、synth_fix）。"""
        job, a = self.job, self.a
        kind = "report" if (job.get("output") or self.profile.get("synthesis") == "report") else "findings"
        items = [x for x in job["items"] if x["status"] != "pending" and x.get("kind") != REPORT_KIND]
        rids = self.job_rids()
        syn = {"kind": kind, "title": "", "sections": [], "unknowns": "", "dropped": [], "fixed": 0, "note": ""}
        job["synthesis"] = syn
        if not items or not rids:
            syn["note"] = "沒有查到可以整理的事實"
            return syn
        self.note("🧭 任務：整合查到的事實…")
        t0 = time.time()
        out = job.get("output")
        now = time.strftime("%Y-%m-%d %H:%M")
        allowed = " ".join([job["task"], out["path"] if out else "", now])
        system = _read("synthesizer.md") + (("\n\n" + _t("worker_profile_header", title=self.profile["title"]) + "\n" + self.profile["synth"])
                                            if self.profile.get("synth") else "")
        user = _t("synth_user", task=job["task"],
                  goal=_t("synth_goal_file", path=out["path"], mode=_t("synth_mode_append") if out["mode"] == "append" else _t("synth_mode_write"))
                  if out else _t("synth_goal_report") if kind == "report" else _t("synth_goal_findings"),
                  focus=job.get("report_focus") or _t("synth_focus_none"), now=now, steps=self._synth_steps_text(items))
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        raw, data = a._task_call(job, "synth", msgs, TASK_SYNTH_SCHEMA, num_predict=6144)
        if not data:
            syn["note"] = "整合的 session 沒有回應（見 calls.jsonl）"
            job["seconds"] += round(time.time() - t0, 1)
            return syn
        syn["title"] = _one_line(data.get("title"), 80) or _one_line(job["task"], 80)
        flat = []                                    # [(節, 一則)]：交回改時的編號＝這裡的順序（1 起算）
        for sec in data.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            entry = {"heading": _one_line(sec.get("heading"), 40), "items": []}
            for x in sec.get("items") or []:
                if not isinstance(x, dict):
                    continue
                text, refs = _synth_item(_one_line(x.get("text"), 300), x.get("refs"))
                if text:
                    flat.append((entry, {"text": text, "refs": refs}))
            syn["sections"].append(entry)
        problems = {i: self._synth_check(x["text"], x["refs"], rids, allowed) for i, (_, x) in enumerate(flat, 1)}
        bad = {i: p for i, p in problems.items() if p}
        if bad:
            lines = []
            for i, p in bad.items():
                x = flat[i - 1][1]
                srcs = [self._output(m.group(1)) for m in (_RID.search(r) for r in x["refs"]) if m and m.group(1) in rids]
                ex = self._excerpt(x["text"], srcs)
                lines.append(_t("synth_fix_item", n=i, text=x["text"], refs="、".join(x["refs"]) or "—", problem=p)
                             + ("".join("\n" + _t("synth_fix_line", line=ln) for ln in ex)))
            ask = _t("synth_fix", items="\n".join(lines))
            raw2, fixed = a._task_call(job, "synth_fix", msgs + [{"role": "assistant", "content": raw[:6000]},
                                                                 {"role": "user", "content": ask}], TASK_SYNTH_FIX_SCHEMA, num_predict=3072)
            for f in (fixed or {}).get("fixes") or []:
                try:
                    i = int(f.get("n"))
                except (TypeError, ValueError):
                    continue
                if i not in bad:
                    continue
                text, refs = _synth_item(_one_line(f.get("text"), 300), f.get("refs"))
                if text and not self._synth_check(text, refs, rids, allowed):
                    flat[i - 1][1].update(text=text, refs=refs)
                    bad.pop(i)
                    syn["fixed"] += 1
            for i, p in bad.items():
                syn["dropped"].append({"text": flat[i - 1][1]["text"], "refs": flat[i - 1][1]["refs"], "problem": p})
        kept = 0
        for i, (entry, x) in enumerate(flat, 1):
            if i not in bad and kept < SYNTH_MAX_ITEMS:
                entry["items"].append(x)
                kept += 1
        syn["sections"] = [s for s in syn["sections"] if s["items"]]
        unknowns = _one_line(data.get("unknowns"), 600)
        if unknowns and unknowns.rstrip("。.") not in ("無", "沒有", "（無）"):
            alltext = "\n".join(t for t in (self._output(r) for r in rids) if t)
            missing = missing_tokens(unknowns, alltext, alltext, allowed)
            if missing:
                syn["dropped"].append({"text": unknowns, "refs": [], "problem": _t("synth_not_found", tokens="、".join(missing), refs="（全部）")})
            else:
                syn["unknowns"] = unknowns
        job["seconds"] += round(time.time() - t0, 1)
        self.save()
        return syn

    def do_report(self, it):
        """程式寫報告檔（計畫的 output）：整合過的內容排成 Markdown，用 file_ops 寫（或附加）——經過技能、有存檔編號、原檔自動備份；
        寫完讀回來比對（寫入＝整份一樣、附加＝檔尾是這一段）。核准在確認關卡（這一步標了會改變狀態）。"""
        a, job = self.a, self.job
        it["attempts"] += 1
        if not job.get("synthesis"):
            self.synthesize()
        syn = job["synthesis"]
        n = synth_count(syn)
        if not n:
            it.update(status="failed", summary="整合不出核對過的內容，報告檔沒有寫（" + (syn.get("note") or "每一則都對不上引用的輸出") + "）")
            return
        out = it["output"]
        body = synth_markdown(job, syn, append=out["mode"] == "append")
        body = body if body.endswith("\n") else body + "\n"
        quoted = body.replace('"', '\\"')            # file_ops：內容裡有真正的換行時只把 \" 換回 "（其他照原樣寫入）
        import shlex
        action = {"command": "scripts/file_ops_cmd.py", "args": f"{out['mode']} {shlex.quote(out['path'])} --text \"{quoted}\""}
        res = a._run_tool_once({"action": action}, approved=True) or "[ERROR] 沒有執行"
        rid = getattr(a, "last_result_id", None)
        head = res.strip().splitlines()[0][:200] if res.strip() else ""
        it["steps"] += 1
        it["calls"].append({"skill": "file_ops", "args": f"{out['mode']} {out['path']} --text …（{n} 則）", "head": head, "rid": rid,
                            "status": "ERROR" if res.lstrip().startswith(("[ERROR]", "[DENIED]")) else "PASS"})
        if res.lstrip().startswith(("[ERROR]", "[DENIED]")):
            it.update(status="failed", summary=f"報告檔沒有寫成：{head}")
            return
        full = os.path.join(a.current_cwd, os.path.expanduser(out["path"]))
        try:
            with open(full, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = None
        same = text is not None and (text.endswith(body) if out["mode"] == "append" else text == body)
        verb = "附加到" if out["mode"] == "append" else "寫入"
        it["summary"] = f"{verb} {out['path']}：{n} 則核對過出處的內容" + (f"（另外 {len(syn['dropped'])} 則對不上引用的輸出，沒有寫）" if syn["dropped"] else "")
        it["facts"] = [{"text": f"{head}", "ref": str(rid)}] if rid else []
        it["evidence"] = (f"程式讀回 {out['path']}：" + ("內容跟核對過的報告一樣" if same else "內容跟要寫的不一樣（讀不到或被改過）")
                          + (f"（#{rid}）" if rid else ""))
        it["status"] = "done" if same else "unverified"

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
        syn = job.get("synthesis")
        written = next((it for it in items if it.get("kind") == REPORT_KIND and it["status"] in ("done", "unverified")), None)
        if job["status"] == "done":
            head = f"[PASS] 任務完成（{n_done}/{len(items)} 步，{took}）" + (f"：報告寫在 {written['output']['path']}" if written else "")
        elif job["status"] == "unverified":
            bad = "、".join(str(it["n"]) for it in items if it["status"] == "unverified")
            if bad:
                head = f"[PASS] 任務的步驟都做了（{took}），但第 {bad} 步做完之後的檢查沒有通過：回答時說明檢查的結果，請使用者確認"
            else:
                head = (f"[PASS] 任務的步驟都做了（{took}），但整合不出核對過出處的結論（{(syn or {}).get('note') or '每一則都對不上引用的輸出'}）："
                        f"回答時照下面各步核對過的事實說，說明沒有整合出結論")
        else:
            bad = next((it for it in items if it["status"] == "failed"), None)
            head = (f"[ERROR] 任務沒有做完：第 {bad['n'] if bad else '?'} 步沒有完成（試了 {bad['attempts'] if bad else 0} 次），"
                    f"後面的步驟沒有做（{n_done}/{len(items)} 步做完，{took}）")
        lines = [head]
        if syn and synth_count(syn):
            lines.append(f"## {'報告' if syn['kind'] == 'report' else '結論'}（整合各步查到的事實；每一則都核對過出處）")
            lines.append(f"### {syn['title']}")
            for sec in syn["sections"]:
                lines.append(f"**{sec['heading'] or '內容'}**")
                lines += [f"- {x['text']}（{_refs_text(x['refs'])}）" for x in sec["items"]]
            if syn.get("unknowns"):
                lines.append(f"**還不確定、沒查到的**：{syn['unknowns']}")
            if syn.get("dropped"):
                lines.append(f"（另外 {len(syn['dropped'])} 則在引用的輸出裡找不到，拿掉了）")
        lines.append("## 步驟")
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
        basis = "〈結論〉" if syn and synth_count(syn) and syn["kind"] == "findings" else "上面的結果"
        lines.append(f"（工作 {job['id']}，紀錄在 logs/{TASK_JOBS_DIRNAME}/{job['id']}/；依{basis}回答使用者：引用具體的值、名稱與前後變化"
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
        return (_read("worker.md") + ("\n\n" + _t("worker_profile_header", title=self.run_.profile["title"]) + "\n" + work if work else "")
                + self.a._task_knowledge(self.run_.profile, "work")
                + "\n\n" + _t("worker_specs_header") + "\n" + "\n\n".join(docs)
                + "\n\n" + _t("worker_others_header") + "\n" + "、".join(others))

    def _brief(self):
        overview = "\n".join(f"{it['n']}. {it['title']}" + (_t("brief_mine") if it is self.item else
                                                              _t("brief_later") if it["status"] == "pending" else
                                                              _t("brief_status", status=_STATUS_TEXT.get(it["status"], it["status"])))
                              for it in self.job["items"])
        perm = (_t("brief_perm_write", skills="、".join(sorted(self.writable))) if self.writable else _t("brief_perm_read"))
        parts = [_t("brief_task", task=self.job["task"]), _t("brief_plan", overview=overview),
                 _t("brief_step", n=self.item["n"], title=self.item["title"], goal=self.item["goal"], permission=perm)]
        if self.item.get("check"):
            c = self.item["check"]
            parts.append(_t("brief_check", skill=c["skill"], args=c["args"], expect=c["expect"]))
        before = self.run_.facts_before(self.item)
        if before:
            parts.append(_t("brief_before", facts=before))
        if self.prev_failure:
            parts.append(_t("brief_retry", failure=self.prev_failure))
        containers, why = self.a._task_containers()
        parts.append(_t("brief_env", env=self.a._task_env_text(containers, why)))
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
        steps, executed, nudged, still_nudged, last_reply, calls = 0, 0, False, False, "", []
        while steps < TASK_WORKER_MAX_STEPS:
            steps += 1
            raw, data = self._call(msgs, TASK_WORKER_REPLY_SCHEMA, steps)
            if not raw and data is None:
                return self._result("failed", "模型呼叫失敗（見 calls.jsonl）", [], steps, calls)
            parsed = parse_agent_reply(raw)
            if not parsed.get("valid"):              # 被長度上限截斷、不是完整的 JSON：不執行，請它縮短再回一次
                msgs.append({"role": "assistant", "content": raw[:2000]})
                msgs.append({"role": "user", "content": _t("worker_truncated")})
                continue
            msgs.append({"role": "assistant", "content": raw})
            last_reply = (parsed.get("reply") or "").strip() or last_reply
            action = parsed.get("action")
            if not action:
                if executed == 0 and not nudged and self.item["skills"]:
                    nudged = True                    # 一個技能都沒用就說做完了：先推回去一次
                    msgs.append({"role": "user", "content": _t("worker_no_tool_yet")})
                    continue
                still = _STILL_WORKING.search(parsed.get("reply") or "")
                if still and not still_nudged and not _FAILED_RE.match(parsed.get("reply") or ""):
                    still_nudged = True              # 說還在做卻沒有動作：推回去一次（要繼續就做，做完了就回報結果）
                    msgs.append({"role": "user", "content": _t("worker_still_working", said=still.group(0))})
                    continue
                failed = bool(_FAILED_RE.match(last_reply))
                if failed and executed:              # 「沒有完成」常混了「問題還在」：對照這一步的目標問一次做到了沒有
                    met, summary, steps = self._goal_check(msgs, last_reply, steps)
                    if met:                          # 做到了，但查到的狀況有問題：交給 TaskRun 照它重排剩下的步驟
                        return self._finish(msgs, "done", summary, (data or {}).get("facts"), steps, calls, finding=True)
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
        msgs.append({"role": "user", "content": _t("worker_wrapup", max_steps=TASK_WORKER_MAX_STEPS)})
        raw, data = self._call(msgs, TASK_WORKER_WRAPUP_SCHEMA, steps + 1, kind="worker_wrapup", num_predict=4096)
        data = data or {}
        summary = str(data.get("summary") or "").strip() or last_reply
        if data.get("done") is True and executed:
            return self._finish(msgs, "done", summary, data.get("facts"), steps + 1, calls)
        # 沒做完：查到的事實照樣核對、留著（重排與整合看得到；以前整個丟掉——2026-10-25 試跑 inv_fleet_report：三台的電量都讀到了，
        # 卻因為對不出站名用完步數，電量也沒進報告）
        return self._finish(msgs, "failed", f"做了 {TASK_WORKER_MAX_STEPS} 輪還沒做完。{summary}", data.get("facts"), steps + 1, calls)

    def _goal_check(self, msgs, reply, steps):
        """worker 回報「沒有完成」時，對照這一步的目標問一次做到了沒有（TASK_GOAL_CHECK_SCHEMA，只有兩個欄位）。目標要查的查到了、
        要改的改好了就是做到了；查到的結果是有問題、問題還在、修不了，不算沒做到（2026-10-24 cx_batch_dispatch：診斷的步驟查到
        「一直回 no」卻回「沒有完成：已完成診斷，但問題仍未解決」，worker.md 寫清楚了也一樣——引擎就重試、重排，任務標成沒做完）。
        做到了的不重試，TaskRun 照查到的狀況重排剩下的步驟（cx_domain_fix：在 domain 42 讀不到也算「確認了」，但要換 domain 再讀）。
        回傳 (做到了沒, 摘要, 步數)；問不出來就照原本的「沒有完成」。"""
        ask = _t("goal_check_ask", goal=self.item["goal"])
        raw, data = self._call(msgs + [{"role": "user", "content": ask}], TASK_GOAL_CHECK_SCHEMA, steps + 1,
                               kind="worker_goal_check", num_predict=2048)
        summary = str((data or {}).get("summary") or "").strip()
        met = bool(data) and data.get("goal_met") is True and bool(summary)
        return met, (summary if met else reply), steps + 1

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
                bad.append(({"text": text, "ref": ref}, _t("facts_bad_ref", ref=ref or '?', mine=mine, before=before)))
                continue
            missing = missing_tokens(text, src, src, allowed)
            if missing:
                bad.append(({"text": text, "ref": ref}, _t("facts_not_found", tokens='、'.join(missing), ref=ref)))
            else:
                ok.append({"text": text, "ref": ref})
        return ok, bad

    def _finish(self, msgs, status, summary, facts, steps, calls, finding=False):
        """worker 說做完（或沒做完）時：核對事實，對不上的交回改一次（帶著具體的問題），還是不行就拿掉。"""
        ok, bad = self._check_facts(facts, summary)
        if bad and (self.outputs or self.prior):
            ask = (_t("facts_fix_head") + "\n" + "\n".join(_t("facts_fix_item", text=f["text"], ref=f["ref"], problem=why) for f, why in bad)
                   + "\n" + _t("facts_fix_tail"))
            msgs = msgs + [{"role": "user", "content": ask}]
            raw, data = self._call(msgs, TASK_FACTS_FIX_SCHEMA, steps + 1, kind="worker_facts_fix", num_predict=2048)
            if data:
                ok2, bad2 = self._check_facts(data.get("facts"), data.get("summary"))
                if len(bad2) <= len(bad):
                    ok, bad = ok2, bad2
                    summary = str(data.get("summary") or "").strip() or summary
                steps += 1
        return self._result(status, summary, ok, steps, calls, dropped=[f for f, _ in bad], finding=finding)

    @staticmethod
    def _result(status, summary, facts, steps, calls, dropped=(), finding=False):
        return {"status": status, "summary": summary or "（沒有說明）", "facts": list(facts)[:8], "dropped": list(dropped),
                "steps": steps, "calls": calls, "finding": finding}
