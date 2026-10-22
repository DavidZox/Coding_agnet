"""OpsMixin：非編碼的多步驟任務（orchestrator＋worker）——ops_plan 規劃、使用者確認、ops_run 一步一步派 worker 執行並驗證。

跟 coding orchestrator 同一個想法，但針對維運操作（檔案、容器、ROS 2、調度系統），在主對話的回合裡同步執行：
1. ops_plan（唯讀）：規劃 session（format=OPS_PLAN_SCHEMA）把任務拆成 2～6 步，每一步寫明目標、要用的技能、會不會改變狀態、
   做完用哪個唯讀技能檢查（check：技能、參數、輸出要出現的字樣）。程式檢查：技能要存在、會改變狀態的技能只能出現在
   標了 changes_state 的步驟（沒標就補上，確認時看得到）、查詢的步驟不需要 check；有問題就把具體的問題交回規劃 session 修一次。
   計畫存成草稿（self.ops_draft），回傳給主對話。
2. ops_run（確認關卡：guard 的說明就是整份計畫，使用者核准＝計畫裡標明的狀態變更都核准了）：每一步派一個乾淨的 worker——
   只看得到使用者的任務、這一步的目標、前面各步的結果摘要、這一步技能的規格；用跟主對話一樣的 JSON 協議一步一步用技能。
   計畫沒有核准的狀態變更一律 [DENIED]。worker 回報完成後由程式跑 check；沒過就換一個 worker 帶著原因重試一次，還是沒過就停下來
   （後面的步驟不做），把每一步的結果交還主對話。

設計依據（benchmark_study_3 的文獻整理）：小模型「先規劃再照表執行」常輸給邊做邊調整（ADaPT、InterCode），所以只在複雜的任務才用
（主對話依 AGENT.md 判斷），每一步留給 worker 自己探索的空間；驗證由程式集中做（MAST：驗證不足是多 agent 系統主要的失敗原因）；
agent 之間只傳精簡的結果摘要（ReWOO）。
"""
import json
import os
import re
import time

from .config import GUARDED_SKILLS, NUM_CTX, OPS_MAX_ITEMS, OPS_WORKER_MAX_STEPS, PROMPTS_DIR, SKILL_DOC_PREFIX
from .protocol import action_text, parse_agent_reply
from .schemas import OPS_PLAN_SCHEMA, OPS_WORKER_REPLY_SCHEMA, OPS_WORKER_WRAPUP_SCHEMA

_PROMPTS = os.path.join(PROMPTS_DIR, "ops")
# 每一步都可以用的技能（查詢、找名稱、切換目錄或目標容器）；其中有些也能改變狀態（docker_ctl restart、ROS2_param set…），
# 那種用法只有這一步標了 changes_state、而且技能列在這一步的 skills 裡才放行
OPS_ALWAYS_READ = {"list_dir", "find_file", "search_text", "view_file", "csv_query", "change_dir", "docker_containers", "docker_images",
                   "docker_ctl", "docker_runcmd", "host_runcmd", "ROS2_topic_list", "ROS2_topic_echo", "ROS2_node_list",
                   "ROS2_node_info", "ROS2_param", "ROS2_domain_id", "workpackage_status", "semantic_map", "rmf_handshake",
                   "docker_open"}
_NOT_FOR_OPS = {"ops_plan", "ops_run", "modify_memory", "stt_engine",
                "result_recall", "result_grep", "result_view", "result_list"}
# 計畫的目標寫了這些動作、用的又是兩用的技能（docker_ctl、ROS2_param…）時，這一步算會改變狀態
_CHANGE_WORDS = re.compile(r"重新啟動|重啟|啟動|停掉|關掉|restart|改成|改為|修改|設定為|設成|設為|寫入|新增|建立|"
                           r"複製|移動|補發|回覆?\s*(yes|no)|發布|publish|送出|派送|取消", re.I)
# 描述狀態而不是要做的動作：「是否已停止」「為什麼沒有啟動」「有沒有修改」
_NOT_ACTION_BEFORE = re.compile(r"(不要|不能|不可|別|勿|不|是否|有沒有|有無|是不是|已經|已|為什麼|為何|沒有|未)\s*$")
_FAILED_RE = re.compile(r"^\s*(❌|沒有完成|未完成|無法完成|做不到)")
_STATUS_TEXT = {"done": "完成", "unverified": "做完了但檢查沒過", "failed": "沒有完成", "pending": "沒有執行"}


def _read_prompt(name):
    try:
        with open(os.path.join(_PROMPTS, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _clip(text, n=6000):
    text = text or ""
    if len(text) <= n:
        return text
    head, tail = text[: n * 2 // 3], text[-n // 3:]
    return f"{head}\n…（中間省略 {len(text) - len(head) - len(tail)} 字）…\n{tail}"


def _mentions_change(text):
    for m in _CHANGE_WORDS.finditer(text or ""):
        if not _NOT_ACTION_BEFORE.search(text[max(0, m.start() - 4):m.start()]):
            return True
    return False


class OpsMixin:

    def _ops_note(self, text):
        """進度：印出，執行中有 progress_callback（Web）時也推到右欄（同 analysis_job 的 _analysis_note）。"""
        print(text)
        cb = getattr(self, "progress_callback", None)
        if cb:
            try:
                cb(text)
            except Exception:   # noqa: BLE001  畫面的問題不能中斷執行
                pass

    # ---------------------------------------------------------------- 規劃
    def ops_skill_names(self):
        return [s["name"] for s in self.list_skills() if s["name"] not in _NOT_FOR_OPS]

    def _ops_catalog(self):
        return "\n".join(f"- {s['name']}：{s['description']}" for s in self.list_skills() if s["name"] not in _NOT_FOR_OPS)

    def _ops_session(self, kind, system, user, schema):
        res = self._timed_chat(kind, model=self.model,
                               messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                               format=schema, options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": 4096}, think=False)
        try:
            data = json.loads(res["message"]["content"])
            return data if isinstance(data, dict) else None
        except (ValueError, TypeError, KeyError):
            return None

    def _ops_env_text(self):
        try:
            entries = sorted(os.listdir(self.current_cwd))
        except OSError:
            entries = []
        shown = "、".join(entries[:40]) + ("…" if len(entries) > 40 else "")
        return (f"現在時間：{time.strftime('%Y-%m-%d %H:%M')}\n工作目錄：{self.current_cwd}（{len(entries)} 項：{shown}）\n"
                f"目標容器：{self.target_container or '（未設定）'}")

    def _ops_clean_plan(self, data):
        """模型的計畫 → 清理過的步驟與問題清單（程式檢查）。"""
        names = set(self.ops_skill_names())
        items, issues = [], []
        for i, it in enumerate((data or {}).get("items") or [], 1):
            if not isinstance(it, dict):
                continue
            title = " ".join(str(it.get("title") or "").split())[:60]
            goal = " ".join(str(it.get("goal") or "").split())[:600]
            if not (title or goal):
                continue
            skills = []
            for s in it.get("skills") or []:
                s = str(s).strip()
                s = s[len("scripts/"):] if s.startswith("scripts/") else s
                s = self._script_skill_map().get(s, s) if s.endswith(".py") else s
                if s and s not in skills:
                    skills.append(s)
            unknown = [s for s in skills if s not in names]
            if unknown:
                issues.append(f"第 {i} 步的技能 {'、'.join(unknown)} 不在技能清單裡（只能用清單裡的名稱）")
            skills = [s for s in skills if s in names]
            if not skills:
                issues.append(f"第 {i} 步沒有列出要用的技能")
            changes = bool(it.get("changes_state"))
            if any(s in GUARDED_SKILLS and s not in OPS_ALWAYS_READ for s in skills):
                changes = True                       # file_ops、ROS2_topic_pub、workpackage_send…：一定會改變狀態
            elif not changes and _mentions_change(f"{title} {goal}") and any(s in GUARDED_SKILLS for s in skills):
                changes = True                       # 兩用的技能（docker_ctl restart、ROS2_param set…）而目標寫了要改
            check = it.get("check") if isinstance(it.get("check"), dict) else None
            if check:
                cs = str(check.get("skill") or "").strip()
                check = {"skill": cs, "args": str(check.get("args") or "").strip(), "expect": str(check.get("expect") or "").strip()}
                if cs not in names:
                    issues.append(f"第 {i} 步的檢查技能「{cs}」不在技能清單裡")
                    check = None
                elif not check["expect"]:
                    check = None
            if check and not changes:
                check = None                         # 查詢的步驟不用檢查（worker 的回報就是結果）
            items.append({"n": len(items) + 1, "title": title or goal[:30], "goal": goal or title, "skills": skills,
                          "changes_state": changes, "check": check, "status": "pending", "summary": "", "attempts": 0,
                          "steps": 0, "evidence": "", "calls": []})
        if len(items) > OPS_MAX_ITEMS:
            issues.append(f"步驟太多（{len(items)} 步）：合併成最多 {OPS_MAX_ITEMS} 步")
        return items[:OPS_MAX_ITEMS], issues

    def ops_plan(self, task, run_readonly=True):
        """規劃（ops_plan 技能）。回傳給主對話的文字（[PASS] 計畫…／[ERROR] …）；計畫都只查詢時直接執行、回傳執行報告。
        run_readonly=False：只規劃（ops_run 的確認關卡在規劃時用）。"""
        task = (task or "").strip().strip('"').strip()
        if len(task) < 4:
            return "[ERROR] ops_plan 需要任務描述：args 填使用者的原話。"
        self._ops_note("🧭 ops_plan：規劃中…")
        system = _read_prompt("planner.md")
        user = (f"【技能清單】\n{self._ops_catalog()}\n\n【目前狀態】\n{self._ops_env_text()}\n\n【任務】\n{task}\n\n"
                "（計畫的每個欄位都用繁體中文寫）")
        calls = 1
        try:
            data = self._ops_session("ops_plan", system, user, OPS_PLAN_SCHEMA)
        except Exception as e:   # noqa: BLE001
            return f"[ERROR] 規劃 session 失敗：{e}"
        items, issues = self._ops_clean_plan(data)
        if issues:   # 程式檢查出的具體問題交回規劃 session 修一次（不是請它「再想一次」）
            fix = (user + "\n\n【上一版計畫】\n" + json.dumps({"items": (data or {}).get("items")}, ensure_ascii=False)[:4000]
                   + "\n\n【程式檢查發現的問題：修正後輸出完整的計畫】\n" + "\n".join(f"- {x}" for x in issues))
            calls += 1
            try:
                data2 = self._ops_session("ops_plan", system, fix, OPS_PLAN_SCHEMA)
            except Exception:    # noqa: BLE001
                data2 = None
            items2, issues2 = self._ops_clean_plan(data2)
            if items2 and len(issues2) <= len(issues):
                data, items, issues = data2, items2, issues2
        if not items:
            return ("[ERROR] 規劃 session 沒有給出可以執行的步驟" + (f"（{'；'.join(issues)}）" if issues else "")
                    + "：這個任務直接用技能一步一步做。")
        if len(items) == 1:
            # 一步就做得完的任務不需要 orchestrator（實測：主對話把「先不要修改、查原因」當成要先看計畫，規劃出一步就停下來問使用者）
            it = items[0]
            return (f"[ERROR] 這個任務一步就做得完，不需要 ops 規劃：直接用 {'、'.join(it['skills']) or '對應的技能'} 做"
                    f"（{it['goal']}），不用先問使用者。")
        self.ops_draft = {"id": time.strftime("%Y%m%d_%H%M%S"), "task": task, "items": items, "status": "draft",
                          "understanding": str((data or {}).get("understanding") or "").strip(),
                          "summary": str((data or {}).get("summary") or "").strip(),
                          "report": str((data or {}).get("report") or "").strip(), "issues": issues, "plan_calls": calls}
        if run_readonly and not any(it["changes_state"] for it in items):
            # 只查詢的計畫不需要先給使用者看（不會改變任何狀態）：直接執行、回報結果。實測主對話把「先不要修改、查原因」
            # 當成要先看計畫，規劃完就停下來問使用者「要開始嗎」
            self._ops_note("🧭 ops_plan：計畫都只查詢，直接執行")
            return ("（計畫都只查詢、不會改變任何狀態，所以直接執行了）\n" + self.ops_run())
        return ("[PASS] " + self.ops_plan_text(self.ops_draft)
                + "\n\n（這是計畫草稿，還沒有執行。要執行就用 ops_run（action.command 填 scripts/ops_run_cmd.py、args 留空），"
                "系統會把整份計畫給使用者確認；使用者要改計畫就用 ops_plan 帶著修改後的要求重新規劃。）")

    def ops_plan_text(self, plan):
        lines = [f"計畫（{len(plan['items'])} 步）：{plan.get('summary') or plan['task']}"]
        for it in plan["items"]:
            mark = "⚠️ 會改變狀態" if it["changes_state"] else "只查詢"
            chk = (f"；做完檢查：{it['check']['skill']} {it['check']['args']} 要看到「{it['check']['expect']}」"
                   if it.get("check") else "")
            lines.append(f"{it['n']}. {it['title']}（{mark}；技能：{'、'.join(it['skills']) or '—'}{chk}）\n   {it['goal']}")
        if plan.get("report"):
            lines.append(f"最後回報：{plan['report']}")
        return "\n".join(lines)

    def _ops_task_text(self, task):
        return " ".join((task or "").strip().strip('"').strip("'").split())

    def _ops_ensure_draft(self, task):
        """ops_run 帶了任務：沒有同一個任務的草稿就先規劃。回傳 None（有草稿可以執行）或錯誤訊息。"""
        task = self._ops_task_text(task)
        plan = getattr(self, "ops_draft", None)
        if not task:
            return None if plan and plan.get("status") == "draft" else \
                "[ERROR] 目前沒有待執行的計畫：ops_run 的 args 填使用者的原話（系統會先規劃、給使用者確認再執行）。"
        if plan and plan.get("status") == "draft" and self._ops_task_text(plan["task"]) == task:
            return None
        failed = getattr(self, "_ops_plan_failed", None)
        if failed and failed[0] == task:
            return failed[1]                         # 確認關卡剛剛規劃失敗過：不再規劃一次
        res = self.ops_plan(task, run_readonly=False)
        if not res.startswith("[PASS]"):
            self._ops_plan_failed = (task, res)
            return res
        self._ops_plan_failed = None
        return None

    def ops_guard_reason(self, task=""):
        """ops_run 的確認說明：整份計畫（使用者核准＝計畫裡標明的狀態變更都核准了）。ops_run 帶了任務、還沒有那個任務的草稿時，
        在這裡先規劃（確認畫面要給使用者看計畫）。沒有可以執行的草稿時回傳 None（不用確認，ops_run 自己回錯誤）。"""
        if self._ops_ensure_draft(task):
            return None
        plan = getattr(self, "ops_draft", None)
        if not plan or plan.get("status") != "draft":
            return None
        changing = [f"第 {it['n']} 步 {it['title']}" for it in plan["items"] if it["changes_state"]]
        if not changing:
            return None                              # 都只查詢：不會改變任何狀態，不用確認
        return (f"依計畫執行 {len(plan['items'])} 步" + (f"，會改變狀態的是：{'；'.join(changing)}" if changing else "（都只查詢）")
                + "\n" + self.ops_plan_text(plan))

    # ---------------------------------------------------------------- 執行
    def ops_run(self, task=""):
        """執行計畫（ops_run 技能，使用者確認過）：帶了任務就執行那個任務的計畫（確認關卡已經規劃好；/guard off 時在這裡規劃），
        沒帶就執行 ops_plan 留下的草稿。回傳給主對話的報告。"""
        err = self._ops_ensure_draft(task)
        if err:
            self._ops_plan_failed = None
            return err
        plan = self.ops_draft
        plan["status"] = "running"
        t0 = time.time()
        facts = []
        for it in plan["items"]:
            prev_failure = None
            while it["attempts"] < 2:
                it["attempts"] += 1
                self._ops_note(f"🧭 ops 第 {it['n']}/{len(plan['items'])} 步（第 {it['attempts']} 次）：{it['title']}")
                res = OpsWorker(self, plan, it, facts, prev_failure).run()
                it["steps"] += res["steps"]
                it["calls"] += res["calls"]
                it["summary"] = res["summary"]
                if res["status"] != "done":
                    it["status"] = "failed"
                    prev_failure = res["summary"]
                    continue
                ok, evidence = self._ops_check(it)
                it["evidence"] = evidence
                if ok:
                    it["status"] = "done"
                    break
                # 檢查沒過：換一個 worker 帶著檢查的輸出再做一次；第二次還是沒過，多半是計畫寫的檢查條件不適用（例如要「看到 0」
                # 卻是「找不到」）——不擋下後面的步驟，標成「檢查沒過」交給主對話與使用者確認
                it["status"] = "unverified"
                prev_failure = (f"你回報完成了，但做完之後的檢查沒有通過：{evidence}。先查清楚現在的狀態：沒做好就修正；"
                                f"確定已經完成、是檢查的條件不適用，就照實回報並說明。")
            facts.append(f"第 {it['n']} 步「{it['title']}」{_STATUS_TEXT[it['status']]}：{it['summary'][:700]}")
            if it["status"] == "failed":
                break
        done = sum(1 for it in plan["items"] if it["status"] == "done")
        unverified = [it for it in plan["items"] if it["status"] == "unverified"]
        finished = done + len(unverified)
        plan["status"] = "done" if done == len(plan["items"]) else ("unverified" if finished == len(plan["items"]) else "failed")
        plan["seconds"] = round(time.time() - t0, 1)
        plan["model_calls"] = plan.get("plan_calls", 0) + sum(it["steps"] for it in plan["items"])
        self._ops_save(plan)
        self.ops_last, self.ops_draft = plan, None
        if plan["status"] == "done":
            head = f"[PASS] 計畫執行完成（{done}/{len(plan['items'])} 步，{plan['seconds']:.0f} 秒）"
        elif plan["status"] == "unverified":
            head = (f"[PASS] 計畫的步驟都做了（{plan['seconds']:.0f} 秒），但第 {'、'.join(str(it['n']) for it in unverified)} 步"
                    f"做完之後的檢查沒有通過：回答時說明檢查的結果，請使用者確認")
        else:
            bad = next(it for it in plan["items"] if it["status"] == "failed")
            head = (f"[ERROR] 計畫沒有做完：第 {bad['n']} 步沒有完成（試了 2 次），後面的步驟沒有執行"
                    f"（{finished}/{len(plan['items'])} 步做完）")
        body = []
        for it in plan["items"]:
            mark = {"done": "✅", "failed": "❌", "unverified": "⚠️ 檢查沒過"}.get(it["status"], "⬜ 沒有執行")
            body.append(f"{it['n']}. {mark} {it['title']}" + (f"：{it['summary']}" if it["summary"] else "")
                        + (f"\n   檢查：{it['evidence']}" if it.get("evidence") else ""))
        tail = f"\n要回報給使用者的重點：{plan['report']}" if plan.get("report") else ""
        return (head + "\n" + "\n".join(body) + tail
                + "\n（依上面的結果回答使用者：引用具體的值、名稱與前後變化；沒做完的說明卡在哪裡、原因與建議）")

    def _ops_check(self, it):
        """worker 回報完成後由程式跑 check（唯讀技能）：輸出要找得到 expect（正規表示式，不合法就當字串；不分大小寫）。
        檢查本身執行失敗（[ERROR]，多半是計畫寫的參數不對）不算這一步失敗，標明「沒有驗證」交給主對話判斷。"""
        chk = it.get("check")
        if not chk:
            return True, ""
        script = self._skill_script(chk["skill"])
        if not script:
            return True, f"（檢查技能 {chk['skill']} 找不到腳本，沒有驗證）"
        parsed = {"action": {"command": f"scripts/{script}", "args": chk["args"]}}
        if self.state_change_info(parsed):
            return True, "（檢查用的動作會改變狀態，沒有執行、沒有驗證）"
        out = self._run_tool_once(parsed, approved=False) or ""
        first = out.strip().splitlines()[0][:200] if out.strip() else "（沒有輸出）"
        if out.lstrip().startswith("[ERROR]"):
            return True, f"（檢查 {chk['skill']} {chk['args']} 執行失敗，沒有驗證：{first}）"
        try:
            hit = re.search(chk["expect"], out, re.I)
        except re.error:
            hit = chk["expect"].lower() in out.lower()
        return bool(hit), f"{chk['skill']} {chk['args']} → {'有' if hit else '沒有'}「{chk['expect']}」（{first}）"

    def _skill_script(self, skill):
        for script, name in self._script_skill_map().items():
            if name == skill:
                return script
        return None

    def _ops_save(self, plan):
        try:
            d = os.path.join(self.script_dir, "logs", "ops_jobs")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"{plan['id']}.json"), "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=1)
        except OSError:
            pass


class OpsWorker:
    """計畫的一步：乾淨的 session，只看這一步的目標、前面各步的結果，這一步技能的規格整份附上（不用先載入）。"""

    def __init__(self, agent, plan, item, facts, prev_failure=None):
        self.a, self.plan, self.item, self.facts, self.prev_failure = agent, plan, item, facts, prev_failure
        names = set(agent.ops_skill_names())
        self.allowed = set(item["skills"]) | (OPS_ALWAYS_READ & names)
        self.writable = set(item["skills"]) if item["changes_state"] else set()

    def _system(self):
        docs = []
        for skill in sorted(set(self.item["skills"])):
            doc = self.a._load_skill_doc(skill)
            if doc:
                body = doc.split("---", 2)[-1].strip() if doc.startswith("---") else doc.strip()
                docs.append(f"### {skill}\n{body[:3000]}")
        others = sorted(self.allowed - set(self.item["skills"]))
        return (_read_prompt("worker.md") + "\n\n## 這一步的技能規格\n" + "\n\n".join(docs)
                + f"\n\n## 其他可以用的技能（查詢用；action.command 填技能名稱會拿到規格）\n{'、'.join(others)}")

    def _brief(self):
        overview = "\n".join(f"{it['n']}. {it['title']}" + ("　← 你負責這一步" if it is self.item else
                                                              ("（已完成）" if it["status"] == "done" else "（之後別人負責，不要做）"))
                              for it in self.plan["items"])
        perm = ("這一步可以改變狀態（使用者已經核准計畫），可以用來改變狀態的技能：" + "、".join(sorted(self.writable))
                if self.writable else "這一步只查詢，不能改變任何狀態")
        parts = [f"【使用者的任務】{self.plan['task']}", f"【整份計畫】\n{overview}",
                 f"【你負責的這一步】第 {self.item['n']} 步：{self.item['title']}\n目標：{self.item['goal']}\n{perm}"]
        if self.item.get("check"):
            c = self.item["check"]
            parts.append(f"【做完之後系統會檢查】{c['skill']} {c['args']}，輸出要有「{c['expect']}」")
        if self.facts:
            parts.append("【前面各步的結果】\n" + "\n".join(self.facts))
        if self.prev_failure:
            parts.append(f"【上一次做這一步沒有成功】{self.prev_failure}\n先查清楚現在的狀態再做，不要重複同樣的做法。")
        parts.append(f"【目前狀態】\n{self.a._ops_env_text()}")
        return "\n\n".join(parts)

    def run(self):
        a = self.a
        msgs = [{"role": "system", "content": self._system()}, {"role": "user", "content": self._brief()}]
        seen, steps, executed, nudged, last_reply, calls = {}, 0, 0, False, "", []
        while steps < OPS_WORKER_MAX_STEPS:
            steps += 1
            try:
                res = a._timed_chat("ops_worker", model=a.model, messages=msgs, format=OPS_WORKER_REPLY_SCHEMA,
                                    options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": 8192}, think=False)
                raw = res["message"]["content"]
            except Exception as e:   # noqa: BLE001
                return {"status": "failed", "summary": f"模型呼叫失敗：{e}", "steps": steps, "calls": calls}
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
                return {"status": "failed" if failed else "done", "summary": last_reply or "（沒有說明）", "steps": steps, "calls": calls}
            payload = action_text(action)
            token = os.path.basename(payload.split()[0]) if payload.strip() else ""
            doc_name = token[:-3] if token.endswith(".md") else token
            if a._load_skill_doc(doc_name) is not None:
                name = doc_name
            else:
                name = a._script_skill_map().get(a._normalize_script_name(token)) or doc_name
            if name not in self.allowed:
                out = (f"[ERROR] 這一步不能用 {name}：可以用的技能是 {'、'.join(sorted(self.allowed))}。"
                       f"需要別的技能才做得到的話，就停下來（action 填 null）在 reply 說明。")
            else:
                info = a.state_change_info({"action": action})
                if info and info["skill"] not in self.writable:
                    out = (f"[DENIED] 這個動作會改變狀態（{info['skill']}：{info['reason']}），但計畫沒有核准這一步改變狀態，沒有執行。"
                           f"只做這一步的目標；做不到就停下來在 reply 說明。")
                else:
                    key = payload.strip()
                    seen[key] = seen.get(key, 0) + 1
                    if seen[key] >= 3:
                        return {"status": "failed", "summary": f"同一個動作做了 3 次還是沒有進展（{key[:120]}）。{last_reply}",
                                "steps": steps, "calls": calls}
                    out = a._run_tool_once({"action": action}, approved=bool(info)) or "[ERROR] 沒有執行任何東西"
                    if not out.startswith(SKILL_DOC_PREFIX):
                        executed += 1
                        calls.append({"skill": name, "args": payload.split(maxsplit=1)[1] if len(payload.split(maxsplit=1)) > 1 else "",
                                      "status": "ERROR" if out.lstrip().startswith(("[ERROR]", "[DENIED]")) else "PASS",
                                      "head": out.strip().splitlines()[0][:200] if out.strip() else ""})
            msgs.append({"role": "user", "content": f"[tool result] {payload[:200]}\n{_clip(out)}"})
        # 用完步數：最後請它總結這一步做完了沒有（不能再用技能）。做完了就交給程式的檢查判斷，沒做完才算失敗
        msgs.append({"role": "user", "content": f"[系統] 已經用完 {OPS_WORKER_MAX_STEPS} 輪，不能再用技能了。依上面的執行結果判斷："
                                                "這一步的目標做完了沒有？done 填 true／false，summary 寫做了什麼、看到的關鍵事實（路徑、名稱、數值、修改前→後）。"})
        try:
            res = a._timed_chat("ops_worker", model=a.model, messages=msgs, format=OPS_WORKER_WRAPUP_SCHEMA,
                                options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": 4096}, think=False)
            data = json.loads(res["message"]["content"])
        except Exception:    # noqa: BLE001
            data = {}
        summary = str(data.get("summary") or "").strip() or last_reply
        if data.get("done") is True and executed:
            return {"status": "done", "summary": summary, "steps": steps + 1, "calls": calls}
        return {"status": "failed", "summary": f"做了 {OPS_WORKER_MAX_STEPS} 輪還沒做完。{summary}", "steps": steps + 1, "calls": calls}
