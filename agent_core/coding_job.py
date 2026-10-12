"""CodingOrchestrator：長時間、跨檔案的程式開發任務（coding job）——排隊、規劃、等使用者核准、依序派 worker、驗證、報告、還原。

跟 fih_rmf_system 的 orchestrator 同一個樣子：一個常駐的服務（背景執行緒）從收件匣接工作，一次處理一個 job，狀態與事件都寫進
logs/coding_jobs/<編號>/，任何人（Web、CLI、技能腳本）都看得到：
- 收件匣 logs/coding_jobs/inbox/*.json：code_job_send 技能（主對話的 AI 派工）寫進來；Web 的 🧑‍💻 與 /code 直接呼叫 submit()。
- state.json：job 的完整狀態（計畫、每一項的進度與結果、整體驗證、報告的存檔編號）；events.jsonl：給畫面的事件流；
  control.json：技能腳本（code_job_cancel）寫的停止要求；backup/：每個被改的檔案在 job 開始前的版本（還原用）；
  payloads/：worker 輸出的檔案內容；workers/：每個 worker 的完整紀錄；report.md：最後的報告。
- 狀態：queued → planning → awaiting_approval →（使用者核准）running ⇄ paused／needs_attention → verifying → done／partial／
  failed／cancelled；還原後是 reverted。

安全：規劃、核准之前不會改任何檔案；核准的計畫畫面上看得到每一項要改哪些檔案、跑哪些指令。worker 只能用 CODING_WORKER_SCRIPTS，
寫入限制在工作區內（CODE_WORKSPACE），指令有安全檢查（_code_common.check_command），每個檔案第一次被改之前都先備份。
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
from skills_system.scripts import _code_common as cc
from skills_system.scripts import _cpp_common as cpp
from .coding_planner import CodingPlannerMixin
from .coding_worker import CodingWorker
from .config import (
    CODING_AUTO_APPROVE,
    CODING_FINAL_FIX_ROUNDS,
    CODING_ITEM_ATTEMPTS,
    CODING_JOBS_DIRNAME,
    CODING_ON_FAIL,
    CODING_PLANNER_MODEL,
    CODING_PLANNER_THINK,
    CODING_RUN_TIMEOUT,
    CODING_SETTINGS_NAME,
    CODING_WORKER_MODEL,
    CODING_WORKER_THINK,
    TOOL_EXEC_TIMEOUT,
)
from .model_caps import think_arg

STATUS_LABELS = {
    "queued": "排隊中", "planning": "規劃中", "awaiting_approval": "等你核准計畫", "running": "執行中", "paused": "已暫停",
    "needs_attention": "需要你決定", "verifying": "整體驗證中", "done": "完成", "partial": "部分完成", "failed": "失敗",
    "cancelled": "已停止", "reverted": "已還原",
}
ACTIVE_STATUSES = {"queued", "planning", "awaiting_approval", "running", "paused", "needs_attention", "verifying"}
FINISHED_STATUSES = {"done", "partial", "failed", "cancelled", "reverted"}
ITEM_MARKS = {"pending": "⬜", "running": "🔄", "done": "✅", "failed": "❌", "skipped": "⏭️"}
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(cc.__file__))
_FORBIDDEN_WORKSPACES = {"/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc", "/root", "/sbin", "/sys", "/usr",
                         "/var", "/opt", "/home", "/tmp"}
# 「跑整套測試」的整體驗證指令（沒有指定測試檔、測試模組）：大型專案改成依序跑每一項的驗證指令（見 _final_check）
_WHOLE_SUITE_RE = re.compile(r"^\s*(?:code_test|(?:python3?\s+-m\s+)?(?:py\.test|pytest)(?:\s+-[-\w=]+)*|"
                             r"(?:python3?\s+)?\.?/?tests/runtests\.py(?:\s+--[-\w=]+(?:\s+\d+)?)*|(?:python3?\s+)?bin/test(?:\s+-[-\w]+)*|"
                             r"make\s+(?:check|test)|ctest(?:\s+--output-on-failure)?)\s*$")
LARGE_PROJECT_TEST_FILES = 50
# 驗證指令交給 code_test 的兩種寫法：code_test [參數]、單純的 pytest 指令（沒有 && ; | 這些 shell 的組合）
_CODE_TEST_CMD_RE = re.compile(r"^\s*code_test\b(.*)$")
_PYTEST_CMD_RE = re.compile(r"^\s*(?:(?:\S*/)?python3?(?:\.\d+)?\s+-m\s+)?(?:py\.test|pytest)\b(.*)$")


class _Stop(Exception):
    pass


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class CodingOrchestrator(CodingPlannerMixin):
    def __init__(self, agent, jobs_dir=None):
        self.agent = agent
        self.dir = jobs_dir or os.path.join(agent.script_dir, "logs", CODING_JOBS_DIRNAME)
        self.inbox = os.path.join(self.dir, "inbox")
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._thread = None
        self._stop = False
        self.jobs = {}          # id -> state dict
        self._events = {}       # id -> [event]
        self.models = {"planner": CODING_PLANNER_MODEL, "worker": CODING_WORKER_MODEL}
        self.think = {"planner": CODING_PLANNER_THINK, "worker": CODING_WORKER_THINK}   # 各角色的 thinking 開關（使用者的選擇）
        self.default_workspace = None    # /code_ws 設定；沒有就用主對話的工作目錄
        self.auto_approve = CODING_AUTO_APPROVE
        self.on_fail = CODING_ON_FAIL
        self.python = ""                 # 跑 Python 測試用的直譯器（空白＝自動：工作區的 .venv → harness 的 venv）
        self.settings_file = os.path.join(agent.script_dir, "logs", CODING_SETTINGS_NAME)
        self._load_settings()
        self._load_existing()

    # ================================================================ 模型與路徑
    def planner_model(self):
        return self.models.get("planner") or self.agent.model

    def worker_model(self):
        return self.models.get("worker") or self.agent.model

    def think_for(self, role):
        """這個角色這次呼叫要送的 think：使用者打開、而且目前的模型支援 thinking 才是 True。"""
        model = self.planner_model() if role == "planner" else self.worker_model()
        return think_arg(model, self.think.get(role))

    def model_state(self):
        return dict(planner=self.planner_model(), worker=self.worker_model(),
                    planner_think=bool(self.think.get("planner")), worker_think=bool(self.think.get("worker")))

    def set_model(self, role, model):
        if role not in ("planner", "worker", "all"):
            raise ValueError("角色只能是 planner、worker 或 all")
        for r in (("planner", "worker") if role == "all" else (role,)):
            self.models[r] = model or None
        self.save_settings()
        return self.model_state()

    def set_models(self, planner=None, worker=None, planner_think=None, worker_think=None):
        """一次設定兩個角色的模型與 thinking（Coding 面板與「🧠 模型」的「套用」）；給 None 的不變。"""
        if planner:
            self.models["planner"] = planner
        if worker:
            self.models["worker"] = worker
        if planner_think is not None:
            self.think["planner"] = bool(planner_think)
        if worker_think is not None:
            self.think["worker"] = bool(worker_think)
        self.save_settings()
        return self.model_state()

    def set_think(self, role, on):
        if role not in ("planner", "worker"):
            raise ValueError("角色只能是 planner 或 worker")
        self.think[role] = bool(on)
        self.save_settings()
        return self.model_state()

    # ---------------------------------------------------------------- ⚙️ 設定（存檔，重開也記得）
    def _load_settings(self):
        """logs/coding_settings.json：使用者在 Coding 面板設定過的模型、工作區、失敗時怎麼辦、自動核准。
        畫面上的設定比環境變數優先（那是使用者最後一次明確的選擇）；檔案不在就用環境變數與預設值。"""
        try:
            with open(self.settings_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for role in ("planner", "worker"):
            if data.get(role):
                self.models[role] = data[role]
            if isinstance(data.get(f"{role}_think"), bool):
                self.think[role] = data[f"{role}_think"]
        ws = data.get("workspace")
        if ws and os.path.isdir(ws):
            self.default_workspace = ws
        if data.get("on_fail") in ("ask", "skip", "stop"):
            self.on_fail = data["on_fail"]
        if isinstance(data.get("auto_approve"), bool):
            self.auto_approve = data["auto_approve"]
        if isinstance(data.get("python"), str):
            self.python = data["python"]

    def set_python(self, path):
        """測試用的 Python（空字串＝自動）。回傳 (實際的路徑或空字串, 錯誤)。"""
        path = os.path.expanduser(str(path or "").strip())
        if path and not (os.path.isfile(path) and os.access(path, os.X_OK)) and not shutil.which(path):
            return None, f"找不到可以執行的 Python：{path}"
        self.python = path
        self.save_settings()
        return path, None

    def save_settings(self):
        data = {"planner": self.models.get("planner"), "worker": self.models.get("worker"),
                "planner_think": bool(self.think.get("planner")), "worker_think": bool(self.think.get("worker")),
                "workspace": self.default_workspace, "on_fail": self.on_fail, "auto_approve": self.auto_approve,
                "python": self.python, "saved": _now()}
        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            tmp = self.settings_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.settings_file)
        except OSError:
            pass

    def job_dir(self, jid):
        return os.path.join(self.dir, f"{int(jid):03d}")

    def backup_dir(self, job):
        return os.path.join(self.job_dir(job["id"]), "backup")

    def workspace_default(self):
        return self.default_workspace or self.agent.current_cwd

    # ================================================================ 狀態與事件（持久化）
    def _load_existing(self):
        """啟動時讀回既有的 job（給畫面看歷史、code_diff／還原）。上次沒跑完的 job 標成 failed（原因：程式重新啟動），
        已經做完的項目與備份都還在，可以還原或重新送一次任務。"""
        if not os.path.isdir(self.dir):
            return
        for name in sorted(os.listdir(self.dir)):
            if not name.isdigit():
                continue
            try:
                with open(os.path.join(self.dir, name, "state.json"), encoding="utf-8") as f:
                    job = json.load(f)
            except (OSError, ValueError):
                continue
            if job.get("status") in ACTIVE_STATUSES:
                job["interrupted_status"] = job["status"]
                job["status"] = "failed"
                job["interrupted"] = True
                job["error"] = "程式重新啟動時這個 job 還沒做完：按「▶ 從中斷的地方繼續」（或 /code resume）接著做，已完成的項目不會重做"
                job["needs"] = None
                self._write_state(job)
            self.jobs[job["id"]] = job

    def _write_state(self, job):
        d = self.job_dir(job["id"])
        os.makedirs(d, exist_ok=True)
        job["updated"] = _now()
        tmp = os.path.join(d, "state.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in job.items() if not k.startswith("_")}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(d, "state.json"))

    def save(self, job):
        with self._lock:
            self._write_state(job)
            self._cond.notify_all()

    def emit(self, job, etype, text, item=None, **data):
        """記一筆事件（畫面的 Coding 面板逐筆顯示；也寫進 events.jsonl）。"""
        with self._lock:
            evs = self._events.setdefault(job["id"], self._read_events(job["id"]))
            ev = {"seq": len(evs) + 1, "ts": time.strftime("%H:%M:%S"), "type": etype, "text": text, "item": item, **data}
            evs.append(ev)
            try:
                with open(os.path.join(self.job_dir(job["id"]), "events.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            except OSError:
                pass
            self._cond.notify_all()
        return ev

    def _read_events(self, jid):
        out = []
        try:
            with open(os.path.join(self.job_dir(jid), "events.jsonl"), encoding="utf-8") as f:
                for ln in f:
                    try:
                        out.append(json.loads(ln))
                    except ValueError:
                        continue
        except OSError:
            pass
        return out

    def events(self, jid, since=0):
        with self._lock:
            evs = self._events.get(jid)
            if evs is None:
                evs = self._events[jid] = self._read_events(jid)
            return [e for e in evs if e["seq"] > since]

    def get(self, jid):
        with self._lock:
            return self.jobs.get(int(jid)) if str(jid).isdigit() else None

    def latest(self):
        with self._lock:
            return self.jobs[max(self.jobs)] if self.jobs else None

    def list_jobs(self, limit=20):
        with self._lock:
            return [self.summary_of(self.jobs[k]) for k in sorted(self.jobs, reverse=True)[:limit]]

    def active_job(self):
        with self._lock:
            act = [j for j in self.jobs.values() if j["status"] in ACTIVE_STATUSES]
            return min(act, key=lambda j: j["id"]) if act else None

    def summary_of(self, job):
        items = job.get("items") or []
        done = sum(1 for i in items if i["status"] == "done")
        return {"id": job["id"], "task": job["task"], "status": job["status"], "label": STATUS_LABELS.get(job["status"], job["status"]),
                "done": done, "total": len(items), "workspace": job["workspace"], "created": job.get("created"),
                "report_id": job.get("report_id")}

    @staticmethod
    def new_item(n, title, goal, files, context_files, verify):
        return {"n": n, "title": title, "goal": goal, "files": list(files), "context_files": list(context_files),
                "verify": verify or "", "status": "pending", "attempts": 0, "summary": "", "changed": [], "notes": [],
                "verify_output": "", "started": None, "finished": None, "steps": 0}

    @staticmethod
    def renumber(job):
        for i, it in enumerate(job["items"], 1):
            it["n"] = i

    # ================================================================ 對外的操作（Web／CLI 呼叫，執行緒安全）
    def check_workspace(self, path):
        """回傳 (絕對路徑, 錯誤)。"""
        p = os.path.realpath(os.path.expanduser(str(path or "").strip() or self.workspace_default()))
        if not os.path.isdir(p):
            return None, f"工作區不存在或不是目錄：{p}"
        if p in _FORBIDDEN_WORKSPACES or p == os.path.realpath(os.path.expanduser("~")):
            return None, f"不能把 {p} 整個當成工作區，請指定專案目錄（/code_ws <路徑>）。"
        return p, None

    def submit(self, task, workspace=None, source="web"):
        """建立一個 job（排隊），回傳 (job, 錯誤)。服務執行緒會接著規劃。"""
        task = str(task or "").strip()
        if not task:
            return None, "任務內容是空的。"
        ws, err = self.check_workspace(workspace)
        if err:
            return None, err
        with self._lock:
            os.makedirs(self.dir, exist_ok=True)
            existing = [int(n) for n in os.listdir(self.dir) if n.isdigit()]
            jid = max(existing + list(self.jobs) + [0]) + 1
            job = {"id": jid, "task": task, "workspace": ws, "status": "queued", "source": source, "created": _now(),
                   "updated": _now(), "models": {"planner": self.planner_model(), "worker": self.worker_model()},
                   "understanding": "", "questions": [], "summary": "", "risks": [], "warnings": [], "items": [],
                   "final_verify": "", "test_cmd": "", "final_output": "", "error": None, "needs": None,
                   "report_id": None, "report_file": None, "started": None, "finished": None,
                   "cancel_requested": False, "pause_requested": False, "model_calls": 0, "seconds": None,
                   "final_ok": None, "_files_cache": None, "approved_at": None, "interrupted": False,
                   "resume_mode": None, "self_edit": os.path.realpath(self.agent.script_dir) == ws}
            os.makedirs(os.path.join(self.job_dir(jid), "backup"), exist_ok=True)
            self.jobs[jid] = job
            self._write_state(job)
            self.emit(job, "phase", f"📥 收到任務（來源：{source}），工作區 {ws}")
            self._cond.notify_all()
        self.start_service()
        return job, None

    def _require(self, jid, statuses=None):
        job = self.get(jid)
        if not job:
            raise ValueError(f"找不到 coding job #{jid}")
        if statuses and job["status"] not in statuses:
            raise ValueError(f"job #{jid} 目前是「{STATUS_LABELS.get(job['status'], job['status'])}」，不能這樣操作")
        return job

    def approve(self, jid):
        with self._lock:
            job = self._require(jid, {"awaiting_approval"})
            if not job["items"]:
                raise ValueError("計畫是空的，不能核准（先加一項，或取消）")
            empty = [str(it["n"]) for it in job["items"] if not str(it.get("goal") or "").strip()]
            if empty:
                raise ValueError(f"第 {'、'.join(empty)} 項還沒有寫「要做的事」，worker 會不知道要改什麼：先 ✏️ 編輯或刪掉再核准")
            job["status"] = "running"
            job["needs"] = None
            job["approved_at"] = _now()
            self._write_state(job)
            self.emit(job, "phase", "✅ 使用者核准了計畫，開始執行")
            self._cond.notify_all()
            return job

    def revise(self, jid, feedback):
        """用說的改計畫（會呼叫規劃 session，花幾秒到十幾秒）。回傳說明文字。"""
        job = self._require(jid, {"awaiting_approval"})
        self.emit(job, "phase", f"✏️ 依你的意見修改計畫：{feedback}")
        note = self.revise_plan_with_feedback(job, feedback)
        with self._lock:
            self._write_state(job)
            self.emit(job, "plan", note)
        return note

    def edit_item(self, jid, n, fields):
        """直接改計畫的某一項（畫面上的編輯）：title／goal／files／verify；n=0 代表新增一項。"""
        with self._lock:
            job = self._require(jid, {"awaiting_approval", "needs_attention"})
            files = fields.get("files")
            if isinstance(files, str):
                files = [x for x in re.split(r"[,，、\s]+", files) if x]
            if n == 0:
                it = self.new_item(len(job["items"]) + 1, fields.get("title") or "（新的一項）", fields.get("goal") or "",
                                   [c for c in (self._clean_path(job, f) for f in files or []) if c], [], "")
                job["items"].append(it)
            else:
                if not 1 <= n <= len(job["items"]):
                    raise ValueError(f"沒有第 {n} 項")
                it = job["items"][n - 1]
                if it["status"] in ("done", "running"):
                    raise ValueError(f"第 {n} 項已經{'完成' if it['status'] == 'done' else '在執行'}，不能改")
                if fields.get("title") is not None:
                    it["title"] = " ".join(str(fields["title"]).split())[:60] or it["title"]
                if fields.get("goal") is not None:
                    it["goal"] = str(fields["goal"]).strip()[:2000] or it["goal"]
                if files is not None:
                    it["files"] = [c for c in (self._clean_path(job, f) for f in files) if c]
            if fields.get("verify") is not None:
                v, why = self._clean_verify(fields["verify"])
                if why:
                    raise ValueError(why)
                it["verify"] = v
            self._write_state(job)
            self.emit(job, "plan", f"✏️ 第 {it['n']} 項已更新：{it['title']}")
            return job

    def delete_item(self, jid, n):
        with self._lock:
            job = self._require(jid, {"awaiting_approval"})
            if not 1 <= n <= len(job["items"]):
                raise ValueError(f"沒有第 {n} 項")
            gone = job["items"].pop(n - 1)
            self.renumber(job)
            self._write_state(job)
            self.emit(job, "plan", f"🗑️ 刪除第 {n} 項：{gone['title']}")
            return job

    def move_item(self, jid, n, to):
        with self._lock:
            job = self._require(jid, {"awaiting_approval"})
            items = job["items"]
            if not (1 <= n <= len(items) and 1 <= to <= len(items)):
                raise ValueError("編號超出範圍")
            items.insert(to - 1, items.pop(n - 1))
            self.renumber(job)
            self._write_state(job)
            self.emit(job, "plan", f"↕️ 第 {n} 項移到第 {to} 項")
            return job

    def set_final_verify(self, jid, cmd):
        with self._lock:
            job = self._require(jid, {"awaiting_approval"})
            v, why = self._clean_verify(cmd)
            if why:
                raise ValueError(why)
            job["final_verify"] = v
            self._write_state(job)
            return job

    def cancel(self, jid):
        with self._lock:
            job = self._require(jid)
            if job["status"] in FINISHED_STATUSES:
                raise ValueError(f"job #{jid} 已經結束（{STATUS_LABELS[job['status']]}）")
            job["cancel_requested"] = True
            if job["status"] in ("queued", "awaiting_approval", "needs_attention", "paused"):
                job["status"] = "cancelled"
                job["needs"] = None
                job["finished"] = _now()
                self.emit(job, "phase", "⏹️ 已停止這個 job（還沒執行的項目不會做）")
            else:
                self.emit(job, "phase", "⏹️ 收到停止要求：目前這一步做完就停")
            self._write_state(job)
            self._cond.notify_all()
            return job

    def pause(self, jid):
        with self._lock:
            job = self._require(jid, {"running"})
            job["pause_requested"] = True
            self._write_state(job)
            self.emit(job, "phase", "⏸️ 收到暫停要求：目前這一步做完就暫停")
            return job

    def resume(self, jid):
        """暫停的 job 繼續；程式重新啟動而中斷的 job 從中斷的地方接著做（resume_interrupted）。"""
        job = self._require(jid)
        if job.get("interrupted") and job["status"] == "failed":
            return self.resume_interrupted(jid)
        with self._lock:
            job = self._require(jid, {"paused", "running"})
            job["pause_requested"] = False
            if job["status"] == "paused":
                job["status"] = "running"
                self.emit(job, "phase", "▶️ 繼續執行")
            self._write_state(job)
            self._cond.notify_all()
            return job

    def resume_interrupted(self, jid):
        """程式重新啟動時沒做完的 job：已核准的從第一個沒做完的項目接著做；還沒核准的回到等核准；還沒有計畫的重新規劃。"""
        with self._lock:
            job = self._require(jid, {"failed"})
            if not job.get("interrupted"):
                raise ValueError(f"job #{jid} 不是因為程式重新啟動而中斷的，不能接著做（要重來請重新送出任務）")
            for it in job.get("items") or []:
                if it["status"] in ("running", "failed"):
                    it["status"] = "pending"
                    it["attempts"] = 0
            if job.get("approved_at") and job.get("items"):
                job["resume_mode"] = "execute"
                what = "從第一個沒做完的項目接著做"
            elif job.get("items"):
                job["resume_mode"] = "approval"
                what = "回到等你核准計畫"
            else:
                job["resume_mode"] = None
                what = "重新規劃"
            job.update(status="queued", interrupted=False, error=None, cancel_requested=False, pause_requested=False,
                       finished=None, final_ok=None)
            self._write_state(job)
            self.emit(job, "phase", f"▶️ 接著做中斷的 job：{what}")
            self._cond.notify_all()
        self.start_service()
        return job

    def decide(self, jid, action, note=""):
        """某一項失敗後使用者的決定：retry（可附補充說明）／skip／stop。"""
        with self._lock:
            job = self._require(jid, {"needs_attention"})
            needs = job.get("needs") or {}
            n = needs.get("item")
            it = job["items"][n - 1] if n and 1 <= n <= len(job["items"]) else None
            if action == "retry":
                if it:
                    it["status"] = "pending"
                    it["attempts"] = 0
                    if note.strip():
                        it["notes"].append(note.strip())
                job["status"] = "running"
                self.emit(job, "phase", f"🔁 重試第 {n} 項" + (f"（補充：{note.strip()}）" if note.strip() else ""))
            elif action == "skip":
                if it:
                    it["status"] = "skipped"
                job["status"] = "running"
                self.emit(job, "phase", f"⏭️ 跳過第 {n} 項，繼續下一項")
            elif action == "stop":
                job["cancel_requested"] = True
                job["status"] = "running"
                self.emit(job, "phase", "⏹️ 停止：不再做剩下的項目，直接產生報告")
            else:
                raise ValueError("決定只能是 retry、skip 或 stop")
            job["needs"] = None
            self._write_state(job)
            self._cond.notify_all()
            return job

    def revert(self, jid):
        """把 job 改過的檔案還原成 job 開始前的樣子（原本不存在的檔案刪掉）。回傳說明文字。"""
        with self._lock:
            job = self._require(jid)
            if job["status"] in ACTIVE_STATUSES - {"awaiting_approval", "queued"}:
                raise ValueError("job 還在執行（或在等你決定），先停止再還原")
            bdir = self.backup_dir(job)
            manifest = cc.load_manifest(bdir)
            restored, removed, failed = [], [], []
            for rel, entry in manifest.items():
                dst = os.path.join(job["workspace"], rel)
                try:
                    if entry.get("existed"):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(os.path.join(bdir, "files", rel), dst)
                        restored.append(rel)
                    elif os.path.exists(dst):
                        os.remove(dst)
                        removed.append(rel)
                except OSError as e:
                    failed.append(f"{rel}（{e}）")
            if job["status"] not in ACTIVE_STATUSES:
                job["status"] = "reverted"
            self._write_state(job)
            text = (f"↩️ 已還原 job #{job['id']}：{len(restored)} 個檔案還原成原本的內容"
                    + (f"、刪除 {len(removed)} 個新增的檔案" if removed else "")
                    + (f"；失敗 {len(failed)} 個：{'、'.join(failed)}" if failed else "") + "。")
            self.emit(job, "phase", text)
            return text

    def revert_file(self, jid, rel):
        """只把 job 改過的某一個檔案還原成 job 開始前的樣子（原本不存在的就刪掉）。回傳說明文字。"""
        with self._lock:
            job = self._require(jid)
            if job["status"] in ACTIVE_STATUSES - {"awaiting_approval", "queued"}:
                raise ValueError("job 還在執行（或在等你決定），先停止再還原")
            bdir = self.backup_dir(job)
            entry = cc.load_manifest(bdir).get(rel)
            if entry is None:
                raise ValueError(f"{rel} 不是這個 job 改過的檔案")
            dst = os.path.join(job["workspace"], rel)
            if entry.get("existed"):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(os.path.join(bdir, "files", rel), dst)
                text = f"↩️ 已把 {rel} 還原成 job #{job['id']} 開始前的內容"
            else:
                if os.path.exists(dst):
                    os.remove(dst)
                text = f"↩️ 已刪除 job #{job['id']} 新增的 {rel}"
            self.emit(job, "phase", text)
            return text

    def project_rules(self, job, max_chars=3000):
        """工作區根目錄的開發規範檔（AGENTS.md、CLAUDE.md、CODING.md…，像 Claude Code 讀 CLAUDE.md）：給規劃與每個 worker 看。"""
        for name in ("AGENTS.md", "CLAUDE.md", "CODING.md", ".coding_agent.md"):
            path = os.path.join(job["workspace"], name)
            if os.path.isfile(path):
                try:
                    return name, cc.clip_middle(cc.read_text(path).strip(), max_chars, name)
                except OSError:
                    continue
        return None, ""

    def cancel_requested(self, job):
        """worker 每一步之前檢查：記憶體裡的停止要求，或技能腳本寫的 control.json。"""
        if job.get("cancel_requested"):
            return True
        try:
            with open(os.path.join(self.job_dir(job["id"]), "control.json"), encoding="utf-8") as f:
                ctl = json.load(f)
            if ctl.get("cancel"):
                job["cancel_requested"] = True
                self.emit(job, "phase", "⏹️ 收到停止要求（code_job_cancel）：目前這一步做完就停")
                return True
        except (OSError, ValueError):
            pass
        return False

    def wait_if_paused(self, job):
        with self._lock:
            if not job.get("pause_requested"):
                return
            job["status"] = "paused"
            self._write_state(job)
            self.emit(job, "phase", "⏸️ 已暫停（按「繼續」或 /code resume）")
            while job.get("pause_requested") and not job.get("cancel_requested") and not self._stop:
                self._cond.wait(timeout=1.0)
            if job["status"] == "paused":
                job["status"] = "running"
                self._write_state(job)

    def _wait_user(self, job, waiting_status):
        """在 waiting_status（等核准、等決定）時阻塞服務執行緒，直到使用者改變狀態（或程式結束）。"""
        with self._lock:
            while job["status"] == waiting_status and not self._stop:
                self._cond.wait(timeout=1.0)
                if self.cancel_requested(job) and job["status"] == waiting_status:
                    job["status"] = "cancelled"
                    job["finished"] = _now()
                    self._write_state(job)

    # ================================================================ 執行腳本
    def _script_env(self, job):
        env = os.environ.copy()
        env["CODE_WORKSPACE"] = job["workspace"]
        env["CODE_BACKUP_DIR"] = self.backup_dir(job)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if self.python:
            env["CODE_PYTHON"] = self.python
        return env

    def run_script(self, job, script, args, timeout=None, extra_env=None):
        """以子程序執行 skills_system/scripts/<script>（cwd＝工作區、stdin 接 /dev/null），回傳輸出文字。"""
        path = os.path.join(_SCRIPTS_DIR, script)
        env = self._script_env(job)
        env.update(extra_env or {})
        try:
            res = subprocess.run([sys.executable, path] + list(args), cwd=job["workspace"], env=env,
                                 capture_output=True, text=True, timeout=timeout or TOOL_EXEC_TIMEOUT, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return f"[ERROR] {script} 執行逾時（超過 {timeout or TOOL_EXEC_TIMEOUT} 秒）"
        if res.returncode == 0:
            return res.stdout.strip() or "[PASS]（沒有輸出）"
        out = res.stderr.strip() or res.stdout.strip() or "（沒有任何輸出）"
        return out if out.startswith("[ERROR]") else f"[ERROR] {script} 異常結束（exit {res.returncode}）：\n{out}"

    def run_verify_command(self, job, command):
        """驗證指令：code_test 與單純的 pytest 指令交給 code_test（專案的 Python、真的 pytest；C／C++ 建置後跑 gtest；
        通過／失敗數算好、失敗與編譯錯誤整理過）；其他（make、cmake、執行程式…）交給 code_run。"""
        cmd = (command or "").strip()
        m = _CODE_TEST_CMD_RE.match(cmd) or (None if re.search(r"[;&|<>`$]", cmd) else _PYTEST_CMD_RE.match(cmd))
        if m:
            try:
                args = shlex.split(m.group(1))
            except ValueError:
                args = m.group(1).split()
            return self.run_script(job, "code_test_cmd.py", args + ["--timeout", str(CODING_RUN_TIMEOUT)],
                                   timeout=CODING_RUN_TIMEOUT + 30)
        return self.run_script(job, "code_run_cmd.py", ["--timeout", str(CODING_RUN_TIMEOUT), cmd],
                               timeout=CODING_RUN_TIMEOUT + 30)

    # ---------------------------------------------------------------- 回歸檢查（開工前的測試基準）
    def suite_cases(self, job):
        """跑整個專案的測試（code_test 不給路徑），回傳 (每個測試的結果 {名稱: passed／failed／skipped}, 第一行, 完整輸出)。"""
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            out = self.run_script(job, "code_test_cmd.py", ["--timeout", str(CODING_RUN_TIMEOUT)], timeout=CODING_RUN_TIMEOUT + 30,
                                  extra_env={"CODE_TEST_JSON": path})
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        return data.get("cases") or {}, out.split("\n", 1)[0], out

    def take_baseline(self, job):
        """核准之後、第一項之前跑一次整個專案的測試，記下每個測試的結果；之後每一項的驗證與整體驗證都檢查
        「開工前通過、現在沒有通過」的測試（回歸）。評測（2026-10，SWE-bench 子集）：harness 有 4／24 題「修好了卻弄壞既有測試」，
        自己的驗證只跑新寫的測試、抓不到。大型專案（測試檔 LARGE_PROJECT_TEST_FILES 個以上）跑整套太久，不做。"""
        if job.get("files_before") is None:          # 計畫以外新增的檔案（除錯腳本、暫存檔）在報告裡列出來，給人審查
            job["files_before"] = sorted(rel for _, rel in cc.iter_files(job["workspace"]))
        if job.get("baseline") is not None or job.get("test_files", 0) >= LARGE_PROJECT_TEST_FILES:
            return
        self.emit(job, "phase", "🧪 開工前先跑一次專案的測試，當作之後回歸檢查的基準")
        cases, head, out = self.suite_cases(job)
        job["baseline"] = {"cases": cases, "head": head}
        if cases:
            passed = sum(1 for v in cases.values() if v == "passed")
            failed = sum(1 for v in cases.values() if v == "failed")
            self.emit(job, "phase", f"🧪 基準：{passed} 個測試通過、{failed} 個失敗（之後會檢查原本通過的有沒有被改壞）")
        self.save(job)

    def regressions(self, job):
        """開工前通過、現在沒有通過（失敗或不見了）的測試。回傳 (清單, 現在的結果, 輸出)；沒有基準時回傳 (None, None, None)。"""
        base = (job.get("baseline") or {}).get("cases") or {}
        if not base:
            return None, None, None
        now, head, out = self.suite_cases(job)
        broken = sorted(k for k, v in base.items() if v == "passed" and now.get(k) not in ("passed", "skipped"))
        return broken, now, out

    def regression_text(self, broken, now, out):
        missing = [k for k in broken if k not in now]
        msg = (f"[ERROR] 回歸：開工前通過的 {len(broken)} 個測試現在沒有通過：{'、'.join(broken[:12])}"
               + ("…" if len(broken) > 12 else ""))
        if missing and len(missing) == len(broken):
            msg += "（這些測試這次一個都沒有跑到：多半是建置或 import 失敗，見下面的輸出）"
        elif missing:
            msg += f"（其中 {len(missing)} 個這次沒有跑到）"
        return msg + "\n" + cc.clip_middle(out, 3000, "測試輸出") + \
            "\n（修正時不要改掉原本的行為；這些測試原本會過，是這次的修改讓它們失敗。）"

    def save_payload(self, job, n, step, text):
        d = os.path.join(self.job_dir(job["id"]), "payloads")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"item{n}_step{step}_{int(time.time() * 1000) % 100000}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    # ================================================================ 交接
    def handoff_notes(self, job, before_n):
        """給後面的 worker：前面各項做了什麼、改了哪些檔案、那些檔案現在有哪些函式／類別（簽名）。"""
        lines = []
        for it in job["items"]:
            if it["n"] >= before_n or it["status"] not in ("done", "skipped", "failed"):
                continue
            mark = ITEM_MARKS.get(it["status"], "")
            lines.append(f"{it['n']}. {mark} {it['title']}：{it.get('summary') or '（沒有摘要）'}")
            if it.get("changed"):
                lines.append(f"   改過的檔案：{'、'.join(it['changed'])}")
                for rel in it["changed"][:4]:
                    path = os.path.join(job["workspace"], rel)
                    if (rel.endswith(".py") or cpp.is_c_family(rel)) and os.path.isfile(path):
                        try:
                            outline = self.outline_of(path, cc.read_text(path))
                        except OSError:
                            continue
                        if outline and not outline.startswith("```"):
                            lines.append(f"   {rel} 目前的結構：\n" + "\n".join("   " + x for x in outline.split("\n")[:25]))
        return "\n".join(lines)

    # ================================================================ 服務
    def start_service(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._thread = threading.Thread(target=self._service_loop, name="coding-orchestrator", daemon=True)
            self._thread.start()

    def stop_service(self):
        with self._lock:
            self._stop = True
            self._cond.notify_all()

    def _heartbeat(self):
        try:
            os.makedirs(self.dir, exist_ok=True)
            act = self.active_job()
            with open(os.path.join(self.dir, "service.json"), "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "ts": time.time(), "job": act["id"] if act else None}, f)
        except OSError:
            pass

    def _ingest_inbox(self):
        """技能腳本（code_job_send）放進收件匣的請求 → 建立 job。"""
        if not os.path.isdir(self.inbox):
            return
        for name in sorted(os.listdir(self.inbox)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.inbox, name)
            try:
                with open(path, encoding="utf-8") as f:
                    req = json.load(f)
                os.remove(path)
            except (OSError, ValueError):
                continue
            job, err = self.submit(req.get("task"), req.get("workspace"), req.get("source") or "code_job_send")
            if err:
                self.agent._add_notice(f"⚠️ code_job_send 送來的任務沒有建立：{err}")
            else:
                self.agent._add_notice(f"🧑‍💻 已建立 coding job #{job['id']}：{job['task'][:60]}（規劃好後在 Coding 面板核准）")

    def _service_loop(self):
        last_beat = 0
        while not self._stop:
            if time.time() - last_beat > 3:
                self._heartbeat()
                last_beat = time.time()
            self._ingest_inbox()
            with self._lock:
                queued = sorted((j for j in self.jobs.values() if j["status"] == "queued"), key=lambda j: j["id"])
                job = queued[0] if queued else None
                if job is None:
                    self._cond.wait(timeout=1.0)
                    continue
            try:
                self._run_job(job)
            except Exception as e:
                traceback.print_exc()
                job["status"] = "failed"
                job["error"] = f"orchestrator 發生錯誤：{e}"
                job["finished"] = _now()
                self.save(job)
                self.emit(job, "error", f"❌ {job['error']}")

    # ================================================================ 一個 job
    def _run_job(self, job):
        job["started"] = job.get("started") or _now()
        t0 = time.time()
        calls0 = len(self.agent.perf_calls)
        mode = job.get("resume_mode")
        job["resume_mode"] = None   # 不用 pop：畫面的執行緒可能正在序列化這個 dict（大小不能變）
        if mode == "execute":   # 中斷後接著做：計畫已核准，直接從沒做完的項目開始
            job["status"] = "running"
            self.save(job)
            self._execute(job)
            self._finish(job, t0, calls0)
            return
        if mode == "approval":
            job["status"] = "awaiting_approval"
            job["needs"] = {"kind": "approval", "message": "（中斷後接著做）計畫還沒核准：核准就開始修改檔案；也可以先修改計畫或取消。"}
            self.save(job)
            self._wait_user(job, "awaiting_approval")
            if job["status"] == "running":
                self._execute(job)
            self._finish(job, t0, calls0)
            return
        job["status"] = "planning"
        self.save(job)
        self.emit(job, "status", STATUS_LABELS["planning"])
        if job.get("self_edit"):
            self.emit(job, "phase", "⚠️ 工作區是 harness 本身的目錄：核准前請確認計畫不會改壞正在執行的程式")
        if not self.plan_job(job):
            job["status"] = "failed"          # finished 由 _finish 寫（報告存好之後）
            self.save(job)
            self.emit(job, "error", f"❌ 規劃失敗：{job['error']}")
            self._finish(job, t0, calls0)
            return
        if self.cancel_requested(job):
            self._finish(job, t0, calls0)
            return
        job["status"] = "awaiting_approval"
        job["needs"] = {"kind": "approval", "message": "計畫已經列好：核准就開始修改檔案；也可以先修改計畫或取消。"}
        self.save(job)
        self.emit(job, "plan", f"📋 計畫：{len(job['items'])} 項。{job.get('summary') or ''}".strip())
        if self.auto_approve:
            self.approve(job["id"])
        else:
            self._wait_user(job, "awaiting_approval")
        if job["status"] != "running":
            self._finish(job, t0, calls0)
            return
        self._execute(job)
        self._finish(job, t0, calls0)

    def _execute(self, job):
        self.take_baseline(job)
        while True:
            pending = [it for it in job["items"] if it["status"] == "pending"]
            if not pending or self.cancel_requested(job):
                break
            it = pending[0]
            outcome = self._run_item(job, it)
            if outcome == "cancelled":
                break
            if outcome == "failed":
                if self.on_fail == "skip":
                    it["status"] = "skipped"
                    self.emit(job, "item", f"⏭️ 第 {it['n']} 項失敗，依設定跳過", item=it["n"])
                    continue
                if self.on_fail == "stop":
                    job["cancel_requested"] = True
                    break
                job["status"] = "needs_attention"
                job["needs"] = {"kind": "failure", "item": it["n"],
                                "message": f"第 {it['n']} 項「{it['title']}」試了 {it['attempts']} 次都沒有通過驗證。"
                                           f"可以：重試（可以補充說明給 worker）、跳過這一項繼續、或停止。"}
                self.save(job)
                self.emit(job, "needs", job["needs"]["message"], item=it["n"])
                self._wait_user(job, "needs_attention")
                if job["status"] == "cancelled":
                    break
        if not self.cancel_requested(job) and job["status"] == "running":
            self._final_verify(job)

    def _run_item(self, job, it):
        it["status"] = "running"
        it["started"] = it["started"] or _now()
        self.save(job)
        self.emit(job, "item", f"🔄 開始第 {it['n']}/{len(job['items'])} 項：{it['title']}", item=it["n"], status="running")
        prev_failure = None
        while it["attempts"] < CODING_ITEM_ATTEMPTS:
            it["attempts"] += 1
            if it["attempts"] > 1:
                self.emit(job, "item", f"🔁 第 {it['n']} 項換一個新的 worker 重試（第 {it['attempts']} 次），帶上上一次失敗的原因",
                          item=it["n"], status="running")
            res = CodingWorker(self, job, it, it["attempts"], prev_failure).run()   # 步數與模型呼叫次數由 worker 即時累加
            it["changed"] = sorted(set(it.get("changed") or []) | set(res["changed"]))
            it["verify_output"] = res.get("verify") or it.get("verify_output", "")
            if res["status"] == "cancelled":
                it["status"] = "pending" if not res["changed"] else "failed"
                it["summary"] = "（job 被停止，這一項沒有做完）"
                self.save(job)
                return "cancelled"
            if res["status"] == "done":
                it["status"] = "done"
                it["summary"] = res["summary"]
                it["finished"] = _now()
                self.save(job)
                self.emit(job, "item", f"✅ 第 {it['n']} 項完成：{res['summary'][:200]}", item=it["n"], status="done",
                          changed=it["changed"])
                return "done"
            prev_failure = res["failure"]
            it["summary"] = res["summary"]
            self.save(job)
            self.emit(job, "item", f"❌ 第 {it['n']} 項這次沒有完成：{res['summary']}", item=it["n"], status="failed",
                      detail=res["failure"][:4000])
        it["status"] = "failed"
        it["finished"] = _now()
        self.save(job)
        return "failed"

    def _item_verify_commands(self, job):
        """每一項自己的驗證指令（去掉重複、照順序）：大型專案的整體驗證用這些，不跑整套測試。"""
        return list(dict.fromkeys((it.get("verify") or "").strip() for it in job.get("items") or []
                                  if (it.get("verify") or "").strip() and it.get("status") in ("done", "failed", "skipped")))

    def _final_check(self, job):
        """跑一次整體驗證（指令或靜態檢查＋建置），記進 job 並推事件；回傳 (輸出, 通過與否)。
        測試很多的大型專案（LARGE_PROJECT_TEST_FILES 個以上）而整體驗證是「跑整套測試」時，改成依序跑每一項自己的驗證指令：
        SWE-bench 評測（2026-10-09）——django 不帶測試模組的 runtests、不帶參數的 code_test 跑太久、或有跟這次修改無關的失敗，
        整體驗證跟官方結果幾乎無關（通過的 4 題裡 3 題其實沒解決），之後的修正 worker 反而把對的改壞。"""
        cmd = job.get("final_verify") or ""
        items_cmds = self._item_verify_commands(job)
        if cmd and _WHOLE_SUITE_RE.match(cmd) and job.get("test_files", 0) >= LARGE_PROJECT_TEST_FILES and items_cmds:
            self.emit(job, "phase", f"🧪 整體驗證：專案有 {job['test_files']} 個測試檔，不跑整套測試（{cmd}），改成依序跑每一項的驗證指令："
                                    f"{'；'.join(items_cmds)}")
            outs = [(c, self.run_verify_command(job, c)) for c in items_cmds]
            bad = [(c, o) for c, o in outs if o.lstrip().startswith("[ERROR]") and "沒辦法在這台主機跑這些測試" not in o.split("\n", 1)[0]]
            job["final_failing"] = [c for c, _ in bad]     # 修正 worker 用沒通過的那幾個指令驗證，不跑整套測試
            head = ("[ERROR] 整體驗證沒有通過：" + "、".join(c for c, _ in bad)) if bad else \
                f"[PASS] 整體驗證通過（{len(outs)} 個驗證指令）"
            out = head + "\n" + "\n".join(f"── {c} ──\n{cc.clip_middle(o, 3000, '輸出')}" for c, o in outs)
            ok = not bad
            job["final_output"] = out
            job["final_ok"] = ok
            self.emit(job, "verify", "✅ 整體驗證通過" if ok else "❌ 整體驗證沒有通過", ok=ok, detail=cc.clip_middle(out, 5000))
            return out, ok
        job["final_failing"] = None
        self.emit(job, "phase", f"🧪 整體驗證：{cmd or '對改過的檔案做靜態檢查'}")
        out = self.run_verify_command(job, cmd) if cmd else self._static_and_build(job)
        if cmd and "沒有收集到任何測試" in out.split("\n", 1)[0]:
            whole = self.run_script(job, "code_test_cmd.py", ["--timeout", str(CODING_RUN_TIMEOUT)], timeout=CODING_RUN_TIMEOUT + 30)
            if "沒有收集到任何測試" not in whole.split("\n", 1)[0]:
                # 專案有測試（原本就有或這個 job 寫的），整體驗證指令卻一個都沒跑到（標籤、路徑、-k 寫錯）：不能算通過，
                # 改跑整個專案的測試（評測：django 的「Ran 0 tests … OK」、pytest -k 篩不到，都被當成通過）
                out = whole + f"\n（整體驗證指令「{cmd}」沒有跑到任何測試，改跑整個專案的測試）"
            else:
                # 專案裡根本沒有測試（也沒有 worker 寫）：不算失敗，改成對改過的檔案做靜態檢查（C／C++ 再實際建置一次）
                out = self._static_and_build(job) + f"\n（整體驗證指令「{cmd}」沒有收集到任何測試，改用靜態檢查與建置）"
        elif cmd and "沒辦法在這台主機跑這些測試" in out.split("\n", 1)[0]:
            # 測試全部需要這台主機沒有的外部依賴（例如 ROS 2）：派 worker 修也沒用，改用靜態檢查與建置，原本的輸出附在後面
            out = (self._static_and_build(job) + f"\n（整體驗證指令「{cmd}」的測試需要這台主機沒有的外部依賴，改用靜態檢查與建置）\n"
                   + cc.clip_middle(out, 2500, "測試輸出"))
        ok = not out.lstrip().startswith("[ERROR]")
        if (job.get("baseline") or {}).get("cases"):
            broken, now, sout = self.regressions(job)
            job["final_tests"] = {"passed": sum(1 for v in now.values() if v == "passed"),
                                  "failed": sum(1 for v in now.values() if v == "failed"), "broken": broken[:20]}
            if broken and ok:
                ok = False
                out = self.regression_text(broken, now, sout) + "\n── 整體驗證指令的輸出 ──\n" + out
                job["final_failing"] = None
        job["final_output"] = out
        job["final_ok"] = ok
        self.emit(job, "verify", "✅ 整體驗證通過" if ok else "❌ 整體驗證沒有通過", ok=ok, detail=cc.clip_middle(out, 5000))
        return out, ok

    def _snapshot(self, job):
        """這個 job 碰過的每個檔案目前的內容（不存在記 None）：修正之前記一份，修壞了可以回到這裡。"""
        snap = {}
        for rel in cc.load_manifest(self.backup_dir(job)):
            path = os.path.join(job["workspace"], rel)
            try:
                snap[rel] = cc.read_text(path) if os.path.isfile(path) else None
            except OSError:
                snap[rel] = None
        return snap

    def _restore_snapshot(self, job, snap):
        """把檔案還原到 _snapshot 的狀態；修正時才第一次碰的檔案，還原成 job 開始前的樣子（原本不存在的刪掉）。回傳還原的檔案。"""
        bdir, ws, restored = self.backup_dir(job), job["workspace"], []
        for rel, entry in cc.load_manifest(bdir).items():
            path = os.path.join(ws, rel)
            if rel in snap:
                want = snap[rel]
            else:
                want = cc.original_text(rel, bdir) if entry.get("existed") else None
            now = cc.read_text(path) if os.path.isfile(path) else None
            if want == now:
                continue
            if want is None:
                os.remove(path)
            else:
                cc.write_text(path, want, newline=cc.detect_newline(path) if os.path.isfile(path) else None)
            restored.append(rel)
        return restored

    def _final_verify(self, job):
        """整體驗證：跑整體驗證指令（沒有就對改過的檔案做靜態檢查）；失敗時派「修正」worker（最多 CODING_FINAL_FIX_ROUNDS 次）。
        修正不能讓結果變差：派修正之前記下檔案內容與通過的測試數，修正結束（不論成功與否）重新驗證，通過的變少就還原到修正前——
        實測 26b 的修正 worker 第一次改 api.py 就把 of_text 弄不見，之後被判卡住，原本 6 個通過的測試全部變成 import 失敗，
        而舊版沒有重新驗證，報告還寫著「6 通過」。"""
        job["status"] = "verifying"
        self.save(job)
        out, ok = self._final_check(job)
        rounds = 0
        while not ok and rounds < CODING_FINAL_FIX_ROUNDS and not self.cancel_requested(job):
            rounds += 1
            cmd = (job.get("final_failing") or [job.get("final_verify") or ""])[0]
            snap = self._snapshot(job)
            before = cc.summarize_test_counts(out).get("passed", 0)
            changed = sorted({f for it in job["items"] for f in it.get("changed") or []})
            fix = self.new_item(len(job["items"]) + 1, "修正整體驗證的失敗",
                                f"全部項目做完後，整體驗證指令「{cmd or 'code_check'}」沒有通過，輸出如下。請找出原因並修正程式"
                                f"（是測試寫錯才改測試；不要為了讓測試通過而刪掉測試或改掉原本的需求）：\n"
                                f"{cc.clip_middle(out, 3000, '驗證輸出')}", changed[:6], [], cmd)
            job["items"].append(fix)
            job["status"] = "running"
            self.save(job)
            result = self._run_item(job, fix)
            if self.cancel_requested(job):
                break
            job["status"] = "verifying"
            self.save(job)
            new_out, new_ok = self._final_check(job)
            after = cc.summarize_test_counts(new_out).get("passed", 0)
            if not new_ok and after < before:
                restored = self._restore_snapshot(job, snap)
                fix["summary"] = (fix.get("summary") or "") + f"（修正後通過的測試從 {before} 變成 {after}，已還原到修正前）"
                job["final_output"], job["final_ok"] = out, False
                self.save(job)
                self.emit(job, "phase", f"↩️ 修正之後通過的測試變少（{before} → {after}），已把 {'、'.join(restored) or '檔案'} "
                                        f"還原到修正前的狀態")
                break
            out, ok = new_out, new_ok
            if result != "done" and not ok:
                break

    def _static_and_build(self, job):
        """沒有測試時的整體驗證：改過的檔案做靜態檢查；C／C++ 專案再用專案自己的建置檔建置一次（make 或 CMake）——
        編譯檢查抓不到「宣告了卻沒有實作」這種連結錯誤，也確認得到執行檔。第一行是兩者合起來的 [PASS]／[ERROR]。"""
        out = self.run_script(job, "code_check_cmd.py", [])
        build = cpp.build_command(job["workspace"]) if any(cpp.is_c_family(r) for r, *_ in self.changes(job)) else None
        if not build:
            return out
        bout = self.run_verify_command(job, build)
        ok = not out.lstrip().startswith("[ERROR]") and not bout.lstrip().startswith("[ERROR]")
        head = "[PASS] 靜態檢查與建置都通過" if ok else "[ERROR] 靜態檢查或建置沒有通過"
        return f"{head}（建置：{build}）\n── 靜態檢查 ──\n{out}\n── 建置 ──\n{cc.clip_middle(bout, 4000, '建置輸出')}"

    # ================================================================ 結束與報告
    def _finish(self, job, t0, calls0):
        """算出最後的狀態、寫報告、存成主對話的存檔，最後才把狀態寫進 job：別人（畫面、評測、/code）看到 done／partial 時，
        報告與存檔編號一定已經好了。"""
        items = job.get("items") or []
        final = job["status"]
        if final not in ("failed", "cancelled"):
            all_done = items and all(it["status"] == "done" for it in items)
            if job.get("cancel_requested"):
                final = "cancelled"
            elif all_done and job.get("final_ok") is not False:
                final = "done"
            else:
                final = "partial"
        job["seconds"] = round(time.time() - t0, 1)
        job["needs"] = None
        view = dict(job, status=final, finished=_now())
        report = self.render_report(view)
        try:
            with open(os.path.join(self.job_dir(job["id"]), "report.md"), "w", encoding="utf-8") as f:
                f.write(report)
            job["report_file"] = os.path.join(self.job_dir(job["id"]), "report.md")
        except OSError:
            pass
        self._archive_report(view, report)
        if view.get("report_id"):
            job["report_id"] = view["report_id"]
        job["finished"] = view["finished"]
        job["status"] = final
        self.save(job)
        self.emit(job, "report", report)
        self.emit(job, "status", STATUS_LABELS.get(job["status"], job["status"]))
        label = STATUS_LABELS.get(job["status"], job["status"])
        done = sum(1 for it in items if it["status"] == "done")
        self.agent._add_notice(f"🧑‍💻 coding job #{job['id']} {label}（{done}/{len(items)} 項）：{job['task'][:60]}"
                               + (f"；報告存檔 #{job['report_id']}" if job.get("report_id") else ""))

    def stray_files(self, job):
        """開工後新出現、但不在任何一項的 files 裡的檔案（worker 用 code_run 產生的除錯腳本、重現程式、輸出檔…）。"""
        before = set(job.get("files_before") or [])
        if not before and job.get("files_before") is None:
            return []
        listed = {f for it in job.get("items") or [] for f in it.get("files") or []}
        now = [rel for _, rel in cc.iter_files(job["workspace"])]
        return sorted(rel for rel in now if rel not in before and rel not in listed and not rel.startswith(".coding_agent"))

    def changes(self, job):
        """[(相對路徑, 狀態, +, −)]：job 開始以來每個檔案的變更。"""
        out = []
        bdir = self.backup_dir(job)
        for rel, entry in sorted(cc.load_manifest(bdir).items()):
            cur = os.path.join(job["workspace"], rel)
            exists = os.path.exists(cur)
            if not entry.get("existed") and not exists:
                continue
            old = cc.original_text(rel, bdir) or ""
            new = cc.read_text(cur) if exists else ""
            _, a, d = cc.unified_diff(old, new, rel)
            status = "新增" if not entry.get("existed") else ("刪除" if not exists else "修改")
            if a or d or status != "修改":
                out.append((rel, status, a, d))
        return out

    def diff_text(self, job, rel=None):
        bdir = self.backup_dir(job)
        parts = []
        for r, entry in sorted(cc.load_manifest(bdir).items()):
            if rel and os.path.normpath(r) != os.path.normpath(rel):
                continue
            cur = os.path.join(job["workspace"], r)
            old = cc.original_text(r, bdir) or ""
            new = cc.read_text(cur) if os.path.exists(cur) else ""
            d, _, _ = cc.unified_diff(old, new, r)
            if d:
                parts.append(d)
        return "\n\n".join(parts)

    def render_report(self, job):
        items = job.get("items") or []
        done = sum(1 for it in items if it["status"] == "done")
        mins = int((job.get("seconds") or 0) // 60)
        secs = int((job.get("seconds") or 0) % 60)
        lines = [f"# Coding job #{job['id']}：{job['task']}", "",
                 f"- 狀態：{STATUS_LABELS.get(job['status'], job['status'])}（{done}/{len(items)} 項完成）",
                 f"- 工作區：{job['workspace']}",
                 f"- 模型：規劃 {job['models']['planner']}、worker {job['models']['worker']}；模型呼叫 {job.get('model_calls', 0)} 次",
                 f"- 時間：{job.get('started') or job['created']} 開始，花了 {mins} 分 {secs} 秒"]
        if job.get("error"):
            lines.append(f"- 錯誤：{job['error']}")
        if job.get("summary"):
            lines += ["", f"做法：{job['summary']}"]
        lines += ["", "## 每一項的結果"]
        for it in items:
            lines.append(f"{it['n']}. {ITEM_MARKS.get(it['status'], '')} {it['title']}（嘗試 {it['attempts']} 次、{it['steps']} 步）")
            if it.get("summary"):
                lines.append(f"   - {it['summary']}")
            if it.get("changed"):
                lines.append(f"   - 改了：{'、'.join(it['changed'])}")
        ch = self.changes(job)
        if ch:
            ta, td = sum(c[2] for c in ch), sum(c[3] for c in ch)
            lines += ["", f"## 變更的檔案（{len(ch)} 個，+{ta} −{td}）"]
            lines += [f"- {rel}（{status}，+{a} −{d}）" for rel, status, a, d in ch]
        if job.get("final_output"):
            head = job["final_output"].split("\n", 1)[0]
            lines += ["", "## 整體驗證", f"`{job.get('final_verify') or 'code_check'}` → {head}"]
        base = (job.get("baseline") or {}).get("cases") or {}
        if base and job.get("final_tests"):
            ft = job["final_tests"]
            lines += ["", "## 測試（開工前 → 完成後）",
                      f"- 開工前：{sum(1 for v in base.values() if v == 'passed')} 個通過、{sum(1 for v in base.values() if v == 'failed')} 個失敗",
                      f"- 完成後：{ft['passed']} 個通過、{ft['failed']} 個失敗"
                      + (f"；**原本通過、現在失敗**：{'、'.join(ft['broken'])}" if ft.get("broken") else "；原本通過的測試都還通過")]
        cov = re.search(r"── 覆蓋率[\s\S]*?(?=\n── (?!覆蓋率)|\Z)", job.get("final_output") or "")
        if cov:
            lines += ["", "## 覆蓋率（整體驗證時量的）", "```", cov.group(0).strip(), "```"]
        stray = self.stray_files(job)
        if stray:
            lines += ["", "## 計畫以外新增的檔案（請確認是不是除錯或暫存用的，不需要就刪掉）"]
            lines += [f"- {rel}" for rel in stray[:30]]
        if ch:
            lines += ["", "## 還原", f"在 Web 的 Coding 面板按「↩ 還原」，或輸入 /code revert {job['id']}（job 開始前的版本在 "
                                    f"logs/coding_jobs/{job['id']:03d}/backup/）。"]
        return "\n".join(lines) + "\n"

    def _archive_report(self, job, report):
        """報告存成主對話的一份存檔（#編號、記進檢索清單），之後主對話的 AI 可以 result_recall 取回。"""
        try:
            rid = self.agent._next_id()
            items = job.get("items") or []
            done = sum(1 for it in items if it["status"] == "done")
            record = {"id": rid, "script": "coding_job", "skill": "code_job_send", "status": "PASS" if job["status"] == "done" else "ERROR",
                      "command": f"coding job #{job['id']}（{job['workspace']}）", "cwd": job["workspace"], "target_container": "",
                      "task": job["task"]}
            filename = self.agent._archive_tool_result(record, report)
            if not filename:
                return
            job["report_id"] = rid
            files = "、".join(r for r, *_ in self.changes(job)[:6]) or "沒有改檔案"
            hint = (f"coding job #{job['id']} {STATUS_LABELS.get(job['status'], job['status'])}（{done}/{len(items)} 項）："
                    f"{job['task'][:80]}；改了 {files}")
            self.agent.update_result_answer(rid, hint)
            self.agent._append_tool_use_index(rid, filename, hint)
        except Exception:
            traceback.print_exc()

    # ================================================================ 給主對話與畫面
    def state_line(self):
        """主對話動態區的一小段：目前（或最近一個）coding job 的狀態，讓 AI 回答「進度如何」時有根據。"""
        job = self.active_job() or self.latest()
        if not job:
            return ""
        items = job.get("items") or []
        done = sum(1 for it in items if it["status"] == "done")
        label = STATUS_LABELS.get(job["status"], job["status"])
        line = f"- job #{job['id']}（{label}，{done}/{len(items)} 項）：{job['task'][:80]}；工作區 {job['workspace']}"
        if job.get("report_id"):
            line += (f"；報告存檔 #{job['report_id']}（報告的細節用 result_recall {job['report_id']} \"<問題>\"）；"
                     f"使用者問程式碼「怎麼寫的、改成怎樣」時先用 code_diff --job {job['id']} 看實際的變更再回答")
        return "## Coding Jobs（coding orchestrator 的工作；細節用 code_job_status）\n" + line

    def view(self, job):
        """畫面用：job 的完整狀態（加上標籤、變更清單）。"""
        with self._lock:
            data = json.loads(json.dumps({k: v for k, v in job.items() if not k.startswith("_")}, ensure_ascii=False))
        data["label"] = STATUS_LABELS.get(job["status"], job["status"])
        data["changes"] = [{"file": r, "status": s, "added": a, "removed": d} for r, s, a, d in self.changes(job)]
        data["plan_text"] = self.plan_text(job)
        return data
