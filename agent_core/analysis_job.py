"""AnalysisMixin：數據解析的多 agent 協同——analysis_run 偽技能（同 ops_run、result_recall：要呼叫模型，在 harness 的 process 裡做）。

只要有 .mcap 就能用的事實報告：量到什麼、什麼時候、Log 說了什麼；不做因果推論（原因要對照源碼另外分析——第九輪的源碼脈絡與因果推論
留在 doc/archive/root_cause_reference/）。一次分析一整段數據，最長 ANALYSIS_MAX_SECONDS 秒；更長的數據先用 mcap_slicer 切出要看的時間段。

事實由程式量，模型只「選」和「說明」：
0. 資料預備（程式）：rosout_parser --json 把 Log 去重成唯一訊號（L#：層級、Node、次數、每一次的時間戳、印出 Log 的檔案:行 函式——
   /rosout 的欄位，錄製時就在 MCAP 裡）；mcap_analyzer --json 讀全域 Topic Metadata；mcap_analyzer --facts --json 量全部的 Topic、
   全部的 Key（發布方式、中斷、開始／停止發布、狀態跳轉、數值切換、尖峰、範圍）。build_facts 整理成有編號的事實：T#＝Topic、
   E#＝Topic 的事件（同一則訊息裡一起改變的項目算一個事件）。事實不靠模型挑 Topic、挑 Key，同一份數據每次一樣。
1. Orchestrator 規劃（format=ANALYSIS_PLAN_SCHEMA）：看問題、去重後的 Log 與全部 Topic 的事實總表，挑出相關的 Log 訊號，把要說明的
   Topic 指派給 worker。程式檢查（L# 存在、Topic 可以說明、不重複、最多 N 個），有問題交回修一次，還是不行由程式補指派。
2. Workers（AnalysisWorker，每個一次模型呼叫，可以平行）：看自己那個 Topic 的事實與訊息定義（MCAP 裡的 .msg，含註解），一則一則說明
   （notes：refs 指到這個 Topic 的 E#／T#）。程式核對每一則（編號存在、不寫原因、用詞跟引用的事件一致、寫的時間對得上），
   有問題交回修一次，還是不行的那一則不列。
3. Synthesizer（format=ANALYSIS_SUMMARY_SCHEMA）：整段數據的重點，一則一則（refs 指到 E#／L#／T#），時間由程式依 refs 補上；
   程式核對同 worker。沒有一則通過時由程式依事實列出重點。
4. Orchestrator 檢查（format=ANALYSIS_CHECK_SCHEMA）：WARN 以上或規劃時挑的 Log 前後 ANALYSIS_ALIGN_SEC 秒內有變化、還沒有 worker 說明的
   Topic，決定要不要補派 worker（每一項對應一則 Log）；補派之後回到 3（最多補 max_rounds − 1 輪）。
5. 報告（程式組）：重點、各 Topic 的結果、Workers 的說明、時間線、同時發生的變化、前後沒有任何變化的 Log、分析過程。

全部產物在 logs/analysis_jobs/<編號>/：job.json、events.jsonl、log_digest.md、topic_metadata.md、topic_facts.json（程式量的事實）、
plan.json、workers/W<n>_<topic>.md、prompts/（交給模型的輸入）、report.md。回傳給主對話的是報告的重點（存成 #編號）。

設計依據同 ops_job：agent 之間只傳精簡、結構化的產物（ReWOO）；能由程式做的（去重、量測、時間戳換算、事實的整理、檢查）不交給模型；
驗證集中由程式做（MAST：驗證不足是多 agent 系統主要的失敗原因）。
"""
import json
import os
import re
import shlex
import time
from concurrent.futures import ThreadPoolExecutor

try:
    from ollama import ResponseError as _ModelError
except ImportError:   # 只用程式那一層（evals/datagen/check_facts.py、評分）時不需要 ollama
    class _ModelError(Exception):
        pass

from .config import (
    ANALYSIS_AGENTS_DIRNAME,
    ANALYSIS_ALIGN_SEC,
    ANALYSIS_ANSWER_NOTE,
    ANALYSIS_DATA_ROOT,
    ANALYSIS_DIGEST_MAX_SIGNALS,
    ANALYSIS_FOLLOWUP_WORKERS,
    ANALYSIS_JOBS_DIRNAME,
    ANALYSIS_MAX_ROUNDS,
    ANALYSIS_MAX_SECONDS,
    ANALYSIS_MAX_WORKERS,
    ANALYSIS_ORCHESTRATOR_MODEL,
    ANALYSIS_PARALLEL_WORKERS,
    ANALYSIS_REPORT_HEAD,
    ANALYSIS_SAME_TIME_SEC,
    ANALYSIS_SETTINGS_NAME,
    ANALYSIS_SYNTHESIZER_MODEL,
    ANALYSIS_THINK_DEFAULT,
    ANALYSIS_WORKER_MODEL,
    NUM_CTX,
    PROMPTS_DIR,
    THINK_EXTRA_PREDICT,
)
from .model_caps import think_arg
from .schemas import (ANALYSIS_CHECK_SCHEMA, ANALYSIS_NOTE_MAX, ANALYSIS_PLAN_SCHEMA, ANALYSIS_SUMMARY_SCHEMA,
                      ANALYSIS_WORKER_SCHEMA)

_PROMPTS = os.path.join(PROMPTS_DIR, ANALYSIS_AGENTS_DIRNAME)
ROLES = ("orchestrator", "worker", "synthesizer")
ROLE_LABELS = {"orchestrator": "Orchestrator", "worker": "Worker", "synthesizer": "Synthesizer"}
DEFAULT_QUESTION = "這段錄製期間發生了哪些狀態變化？"
_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "UNKNOWN": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
_MARKERS = ("[ANALYSIS_DATA]", "[TARGET_CONTAINER]", "[CWD_CHANGED]", "[ROS2_WORKSPACE]")
_RECORDER_NODE = re.compile(r"^(rosbag2(_\w+)?|ros2_bag\w*)$")
_STATUS_TEXT = {"preparing": "資料預備", "planning": "Orchestrator 規劃", "working": "Workers 說明", "synthesizing": "Synthesizer 整理重點",
                "checking": "Orchestrator 檢查", "done": "完成", "failed": "失敗"}
_ACTIVE = ("preparing", "planning", "working", "synthesizing", "checking")
# 第九輪以前的選項（源碼脈絡、時間窗）：改成只做事實報告、整段量測之後拿掉，收到就說清楚，不要默默變成問題的一部分
_REMOVED_OPTIONS = ("--source", "--no-source", "--before", "--after")
# ROS 2 框架與錄製工具自己的 Topic：列在事實裡（則數），不列事件、不派 worker（/parameter_events 的 node 欄位只是「最後一個發參數事件的節點」）
_FRAMEWORK_TOPICS = ("/parameter_events", "/clock", "/events/write_split")
_TIMELINE_MAX = 60       # 交給 Synthesizer 的時間線最多幾列（超過時依重要性留；報告裡的時間線是完整的）
_MAIN_TIMELINE_MAX = 15  # 回到主對話的時間線重點
_FLAP_KEEP = (5, 2)      # 同一個 Topic 的變化事件太多（反覆切換）：時間線只列前 5 個與最後 2 個，次數在各 Topic 的結果
_TIME_TOL = 0.35         # 說明裡寫的時間跟引用的事實差多少以內算同一個（同 evals/analysis/regression.py 的 TOL）
_HIGHLIGHTS_HARD = 24    # 重點的則數上限跟著事實（_highlight_cap）；這個是防失控的硬上限
_MOMENT_KINDS = ("start", "stop", "gap", "resume", "change", "first")   # 算「重要的時間點」的事件（一則訊息、尖峰不算）
_EVENT_RANK = {"start": 1, "stop": 1, "gap": 1, "resume": 1, "change": 2, "first": 3, "spike": 3, "message": 6}
_EVENT_ORDER = {"start": 0, "first": 1, "message": 2, "change": 3, "spike": 4, "gap": 5, "resume": 6, "stop": 7}
_EVENT_TAGS = ("訊息中斷", "開始或停止發布", "狀態改變", "數值切換", "尖峰", "第一則在中途")   # 有這些類別＝有事件


def _read_prompt(name):
    try:
        with open(os.path.join(_PROMPTS, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


_ARROW = re.compile(r"\s*(?:\$?\s*(?:\\rightarrow|\rightarrow|\\to|\\Rightarrow)\s*\$?|\$\s*→\s*\$)\s*")


def tidy(value):
    """模型寫的文字：把 LaTeX 的箭頭（$\\rightarrow$；JSON 裡的 \\r 會變成換行字元＋ightarrow）換成 →，去掉控制字元。
    dict／list 逐一處理。"""
    if isinstance(value, dict):
        return {k: tidy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [tidy(v) for v in value]
    if not isinstance(value, str):
        return value
    text = _ARROW.sub(" → ", value)
    return re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)


def _short(text, n=160):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def split_json_output(output):
    """工具 --json 的輸出 → (dict 或 None, 末行的狀態標記)。"""
    lines = (output or "").rstrip().splitlines()
    tail = []
    while lines and lines[-1].startswith(_MARKERS):
        tail.insert(0, lines.pop())
    body = "\n".join(lines)
    i = body.find("{")
    if i < 0:
        return None, tail
    try:
        return json.loads(body[i:]), tail
    except ValueError:
        return None, tail


def _slug(topic):
    return re.sub(r"[^A-Za-z0-9]+", "_", topic).strip("_")[:40] or "topic"


def _rel(ns, base_ns):
    if ns is None or base_ns is None:
        return "-"
    d = (ns - base_ns) / 1e9
    return f"{'+' if d >= 0 else '-'}{abs(d):.2f}s"


def _plus(t):
    """距離數據開頭的秒數 → 「+12.34s」。"""
    return f"{'+' if t >= 0 else '-'}{abs(t):.2f}s"


def _sec3(ns):
    return None if ns is None else round(ns / 1e9, 3)


def _num(v):
    if isinstance(v, float):
        return float(f"{v:.6g}")
    return v


def _val(v, n=60):
    """報告裡的一個值：數字取 6 位有效數字，文字截短。"""
    return str(_num(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else _short(v, n)


def _cell(text):
    """Markdown 表格的一格：| 換成全形，換行拿掉。"""
    return " ".join(str(text or "").split()).replace("|", "｜") or "-"


def frontmatter(fields):
    """Frontmatter（YAML）：每個欄位一行，值用 JSON 寫（JSON 是合法的 YAML flow 寫法：程式好讀、人也看得懂）。"""
    return "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fields.items()) + "\n---\n"


def is_recorder_node(node):
    return bool(_RECORDER_NODE.match(str(node or "").strip("/").split("/")[-1]))


def _signal_source(s):
    """Log 訊號是哪裡印的：「  ＠檔名:行 函式」（/rosout 的 file、line、function，錄製時就在 MCAP 裡；rosout.log 沒有）。"""
    src = (s.get("sources") or [None])[0]
    if not src:
        return ""
    return f"  ＠{os.path.basename(str(src.get('file') or ''))}:{src.get('line')} {src.get('function') or ''}".rstrip()


class AnalysisMixin:

    # ---------------------------------------------------------------- 設定（logs/analysis_settings.json）
    def analysis_settings_file(self):
        return os.path.join(self.script_dir, "logs", ANALYSIS_SETTINGS_NAME)

    @staticmethod
    def analysis_defaults():
        return {"orchestrator": ANALYSIS_ORCHESTRATOR_MODEL, "worker": ANALYSIS_WORKER_MODEL,
                "synthesizer": ANALYSIS_SYNTHESIZER_MODEL, "orchestrator_think": ANALYSIS_THINK_DEFAULT,
                "worker_think": False, "synthesizer_think": ANALYSIS_THINK_DEFAULT,
                # 各角色的上下文長度（None＝NUM_CTX）。8 GB 顯卡上 deepseek-r1:8b 用 32k 時 KV cache 約 4.8 GB、四成跑到 CPU
                # （10.6 token/s）；Synthesizer 的輸入約 3k、輸出幾千，12288 就放得下（7.2 GB 中 6.3 GB 在 GPU，26.7 token/s）
                "orchestrator_ctx": None, "worker_ctx": None, "synthesizer_ctx": None,
                "data_root": ANALYSIS_DATA_ROOT,
                "container": "",
                "rounds": ANALYSIS_MAX_ROUNDS, "max_workers": ANALYSIS_MAX_WORKERS, "parallel": ANALYSIS_PARALLEL_WORKERS}

    def load_analysis_settings(self):
        """預設值＋設定檔裡使用者改過的值。設定檔只存跟預設值不同的（save_analysis_settings）：預設值以後改了，沒改過的設定跟著新的預設，
        不會被當時存下的舊預設蓋住（第十輪把 worker 上限的預設從 4 改成 6，存過設定的人還是 4）。"""
        cfg = self.analysis_defaults()
        try:
            with open(self.analysis_settings_file(), encoding="utf-8") as f:
                saved = json.load(f)
            for k in cfg:   # 舊版的設定（源碼目錄、推理提示、時間窗、切片）不在這裡：讀的時候略過，下次存檔就不見了
                if k in saved and saved[k] not in ("",) and type(saved[k]) in (str, int, float, bool, type(None)):
                    cfg[k] = saved[k]
        except (OSError, ValueError):
            pass
        return cfg

    def save_analysis_settings(self):
        path = self.analysis_settings_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        defaults = self.analysis_defaults()
        data = {k: v for k, v in self.analysis_cfg.items() if k in defaults and v != defaults[k]}
        data["saved"] = time.strftime("%Y-%m-%d %H:%M:%S")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    def analysis_model(self, role):
        """各角色的模型：有設定就用，沒有就跟著主對話的模型。"""
        return self.analysis_cfg.get(role) or self.model

    def analysis_think(self, role):
        return bool(self.analysis_cfg.get(f"{role}_think"))

    def analysis_ctx(self, role):
        """各角色的上下文長度：有設定（正整數）就用，沒有就是 NUM_CTX。"""
        try:
            n = int(self.analysis_cfg.get(f"{role}_ctx") or 0)
        except (TypeError, ValueError):
            n = 0
        return n if n > 0 else NUM_CTX

    def set_analysis_model(self, role, model=None, think=None):
        roles = ROLES if role == "all" else (role,)
        for r in roles:
            if r not in ROLES:
                raise ValueError(f"沒有 {r} 這個角色（orchestrator／worker／synthesizer／all）")
            if model is not None:
                self.analysis_cfg[r] = (model or "").strip() or None
            if think is not None:
                self.analysis_cfg[f"{r}_think"] = bool(think)
        self.save_analysis_settings()

    def analysis_env(self):
        """每支腳本都帶的環境變數：目前分析的數據（省略數據路徑時用）、數據根目錄（實驗名稱、latest、錄製的位置）。"""
        env = {"ANALYSIS_DATA": self.analysis_data or ""}
        root = (self.analysis_cfg.get("data_root") or "").strip()
        if root:
            env["ANALYSIS_DATA_ROOT"] = root
        return env

    def analysis_state_line(self):
        """動態區的一行：目前分析的數據、最近一次 analysis_run。"""
        parts = [f"- CURRENT_ANALYSIS_DATA: {self.analysis_data or '（未設定：數據技能第一次指定數據後會記住；也可以給實驗名稱或 latest）'}"]
        last = getattr(self, "analysis_last", None)
        if last:
            parts.append(f"- LAST_ANALYSIS_JOB: {last['id']}（{_STATUS_TEXT.get(last['status'], last['status'])}；"
                         f"報告 logs/{ANALYSIS_JOBS_DIRNAME}/{last['id']}/report.md）")
        return "\n".join(parts)

    # ---------------------------------------------------------------- job 的檔案與進度
    def analysis_jobs_dir(self):
        return os.path.join(self.script_dir, "logs", ANALYSIS_JOBS_DIRNAME)

    def _job_dir(self, job):
        return os.path.join(self.analysis_jobs_dir(), job["id"])

    def _job_save(self, job):
        d = self._job_dir(job)
        os.makedirs(d, exist_ok=True)
        keep = {k: v for k, v in job.items() if k not in ("index", "scan", "events") and not k.startswith("_")}
        tmp = os.path.join(d, "job.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, os.path.join(d, "job.json"))

    def _job_write(self, job, rel, text):
        path = os.path.join(self._job_dir(job), rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def _analysis_note(self, job, text, kind="phase", **extra):
        """進度：印出、記進 events.jsonl、交給畫面（Web 在執行工具時設 progress_callback，推到右欄）。worker 平行時也會呼叫，所以上鎖。"""
        print(text)
        rec = {"ts": time.strftime("%H:%M:%S"), "kind": kind, "text": text, **extra}
        with self._analysis_lock:
            try:
                os.makedirs(self._job_dir(job), exist_ok=True)
                with open(os.path.join(self._job_dir(job), "events.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except OSError:
                pass
            cb = getattr(self, "progress_callback", None)
            if cb:
                try:
                    cb(text)
                except Exception:   # noqa: BLE001  畫面的問題不能中斷分析
                    pass

    def _job_status(self, job, status):
        job["status"] = status
        job["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._job_save(job)

    def analysis_mark_interrupted(self, stale_minutes=30):
        """啟動時：還標著進行中、但進度（events.jsonl）超過 stale_minutes 沒有更新的 job，是上一次程式在做完之前結束了
        （重新啟動、被停止）——標成 failed，面板才不會一直顯示「分析中」。analysis_run 是同步的，不會有別的程序接著做。"""
        d = self.analysis_jobs_dir()
        if not os.path.isdir(d):
            return 0
        n, now = 0, time.time()
        for name in os.listdir(d):
            path = os.path.join(d, name, "job.json")
            try:
                with open(path, encoding="utf-8") as f:
                    job = json.load(f)
            except (OSError, ValueError):
                continue
            if job.get("status") not in _ACTIVE + ("reasoning",):   # reasoning：第九輪以前的狀態（因果推論）
                continue
            ev = os.path.join(d, name, "events.jsonl")
            last = os.path.getmtime(ev) if os.path.exists(ev) else os.path.getmtime(path)
            if now - last < stale_minutes * 60:
                continue
            job["error"] = f"中斷：程式在這個 job 做完之前結束（停在「{_STATUS_TEXT.get(job['status'], job['status'])}」）"
            job["status"], job["updated"] = "failed", time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(job, f, ensure_ascii=False, indent=1)
                n += 1
            except OSError:
                pass
        return n

    def analysis_list_jobs(self, n=20):
        out = []
        d = self.analysis_jobs_dir()
        if not os.path.isdir(d):
            return out
        for name in sorted(os.listdir(d), reverse=True)[:n]:
            try:
                with open(os.path.join(d, name, "job.json"), encoding="utf-8") as f:
                    j = json.load(f)
            except (OSError, ValueError):
                continue
            out.append({"id": j.get("id", name), "status": j.get("status"), "question": j.get("question", ""),
                        "data_label": j.get("data_label", ""), "created": j.get("created"), "seconds": j.get("seconds"),
                        "workers": len(j.get("workers") or [])})
        return out

    def analysis_job_detail(self, jid):
        """Web 面板用：job.json、事件、各 worker 的說明與報告全文。"""
        d = os.path.join(self.analysis_jobs_dir(), os.path.basename(str(jid or "")))
        try:
            with open(os.path.join(d, "job.json"), encoding="utf-8") as f:
                job = json.load(f)
        except (OSError, ValueError):
            return None
        events = []
        try:
            with open(os.path.join(d, "events.jsonl"), encoding="utf-8") as f:
                events = [json.loads(ln) for ln in f if ln.strip()]
        except (OSError, ValueError):
            pass
        texts = {}
        for rel in ["log_digest.md", "topic_metadata.md", "report.md"] + [w.get("file") for w in job.get("workers") or [] if w.get("file")]:
            try:
                with open(os.path.join(d, rel), encoding="utf-8") as f:
                    texts[rel] = f.read()
            except (OSError, TypeError):
                pass
        return {"job": job, "events": events[-300:], "files": texts}

    # ---------------------------------------------------------------- 主流程
    def analysis_run(self, remainder):
        """analysis_run 技能：解析參數 → 資料預備（程式量全部的事實）→ Orchestrator 規劃 → Workers 說明 → Synthesizer 重點 →
        Orchestrator 檢查（→ 補派 → 再整理重點）→ 報告。回傳給主對話的報告（或 [ERROR]）。"""
        try:
            toks = shlex.split(remainder or "")
        except ValueError:
            toks = (remainder or "").replace('"', " ").split()
        opts = {"data": "", "workers": None, "topics": [], "rounds": None}
        words, i = [], 0
        while i < len(toks):
            t = toks[i]
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if t in ("--data", "--dir") and nxt:
                opts["data"], i = nxt, i + 2
                continue
            if t == "--topic" and nxt:
                opts["topics"].append(nxt if nxt.startswith("/") else "/" + nxt)
                i += 2
                continue
            if t in _REMOVED_OPTIONS:
                return (f"[ERROR] analysis_run 沒有 {t} 這個選項了：它只做事實報告，一次量整段數據（沒有時間窗），不用源碼。"
                        "只想看其中一段，先用 mcap_slicer 切出來，再用 --data 指定切片資料夾。")
            if t in ("--workers", "--rounds") and nxt:
                try:
                    opts[t[2:]] = int(nxt)
                except ValueError:
                    return f"[ERROR] {t} 要是整數，收到 {nxt}"
                i += 2
                continue
            words.append(t)
            i += 1
        question = " ".join(words).strip().strip('"').strip() or DEFAULT_QUESTION
        data = opts["data"] or self.analysis_data
        if not data:
            return ("[ERROR] analysis_run 需要數據：args 加 --data <實驗資料夾、bag、切片資料夾、.mcap，或實驗名稱、latest>；"
                    "也可以先用 mcap_analyzer 看一份數據（系統會記住目前的數據）。")
        cfg = self.analysis_cfg
        job = {"id": time.strftime("%Y%m%d_%H%M%S"), "created": time.strftime("%Y-%m-%d %H:%M:%S"), "question": question,
               "data": data, "status": "preparing", "options": opts,
               "models": {r: self.analysis_model(r) for r in ROLES},
               "model_options": {r: {"think": self.analysis_think(r), "ctx": self.analysis_ctx(r)} for r in ROLES},
               "max_workers": max(1, min(8, opts["workers"] or int(cfg.get("max_workers") or ANALYSIS_MAX_WORKERS))),
               "max_rounds": max(1, min(2, opts["rounds"] or int(cfg.get("rounds") or ANALYSIS_MAX_ROUNDS))),
               "model_calls": 0}
        while os.path.exists(self._job_dir(job)):
            job["id"] += "_1"
        t0 = time.time()
        self.analysis_last = {"id": job["id"], "status": "preparing"}
        self._analysis_note(job, f"📊 數據分析 job {job['id']}：{_short(question, 80)}")
        try:
            err = self._analysis_prepare(job)
            if err:
                job["error"] = err
                self._job_status(job, "failed")
                self.analysis_last = {"id": job["id"], "status": "failed"}
                return err
            self._job_status(job, "planning")
            self._analysis_orchestrate(job)
            job["facts"] = build_facts(job)   # 規劃挑的 Log 也要放進時間線：規劃之後再整理一次（Topic 與事件的編號不變）
            self._job_status(job, "working")
            self._analysis_run_workers(job, job["plan"]["assignments"])
            text = self._analysis_conclude(job)   # 重點 → 檢查（→ 補派 → 再寫重點）→ 報告
        except Exception as e:   # noqa: BLE001  任何一段失敗：已完成的產物留在 job 資料夾
            job["error"] = f"{type(e).__name__}: {e}"
            job["seconds"] = round(time.time() - t0, 1)
            self._job_status(job, "failed")
            self.analysis_last = {"id": job["id"], "status": "failed"}
            self._analysis_note(job, f"❌ 數據分析中斷：{job['error']}", kind="error")
            return (f"[ERROR] 數據分析中斷（{job['status']}）：{job['error']}。已完成的部分在 "
                    f"logs/{ANALYSIS_JOBS_DIRNAME}/{job['id']}/。")
        job["seconds"] = round(time.time() - t0, 1)
        self._job_status(job, "done")
        self.analysis_last = {"id": job["id"], "status": "done"}
        self._analysis_note(job, f"✅ 數據分析完成（{job['seconds']:.0f} 秒，模型呼叫 {job['model_calls']} 次）", kind="done")
        return text.replace("{SECONDS}", f"{job['seconds']:.0f}").replace("{CALLS}", str(job["model_calls"]))

    def _analysis_tool(self, script, args, extra_env=None):
        """在 harness 裡執行數據技能（同 run_tool 的執行原語，但不記軌跡、不存檔：job 資料夾有完整紀錄）。"""
        path = os.path.join(self.base_path, "scripts", script)
        return self._exec_script(script, path, list(args), extra_env=extra_env)

    def _analysis_session(self, job, kind, role, system, user, schema, predict, label=None):
        model, want = self.analysis_model(role), self.analysis_think(role)
        think = think_arg(model, want)
        name = label or role   # prompts/ 的檔名（worker：worker_W1；Orchestrator 的檢查：orchestrator_check）
        with self._analysis_lock:   # 交給模型的輸入留在 job 資料夾（prompts/）：對照、重播（只換 prompt 重跑一個角色）用
            n = job.setdefault("_prompt_n", {}).get(name, 0) + 1
            job["_prompt_n"][name] = n
        self._job_write(job, f"prompts/{name}{'' if n == 1 else f'_{n}'}.md", f"# system\n{system}\n\n# user\n{user}\n")
        try:
            res = self._timed_chat(kind, model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                   format=schema, options={"temperature": 0.2, "num_ctx": self.analysis_ctx(role),
                                                           "num_predict": predict + (THINK_EXTRA_PREDICT if think else 0)},
                                   think=think)
        except _ModelError as e:
            # 模型自己的輸出被中止（Ollama：prediction aborted, token repeat limit reached——同一段一直重複）＝沒有可用的輸出，
            # 跟 JSON 壞掉一樣交給各角色原本的退路（交回一次、程式補指派、程式列出重點）；連線、模型不存在這類錯誤照樣丟出去
            if "prediction aborted" not in str(e):
                raise
            with self._analysis_lock:
                job["model_calls"] += 1
                job.setdefault("model_aborted", []).append(f"{name}：{_short(str(e), 120)}")
            self._analysis_note(job, f"⚠️ {name} 的輸出被 Ollama 中止（{_short(str(e), 80)}）：當成沒有可用的輸出處理")
            return None
        with self._analysis_lock:
            job["model_calls"] += 1
        try:
            data = json.loads(res["message"]["content"])
            return tidy(data) if isinstance(data, dict) else None
        except (ValueError, TypeError, KeyError):
            return None

    # ---------------------------------------------------------------- 0. 資料預備（程式）
    def _analysis_prepare(self, job):
        self._analysis_note(job, "📊 資料預備：讀全域 Topic Metadata、去重後的 Log，量全部 Topic 的事實…")
        out = self._analysis_tool("mcap_analyzer_cmd.py", [job["data"], "--json"])
        idx, tail = split_json_output(out)
        if not idx or "topics" not in idx:
            return f"[ERROR] 讀不到數據的 Topic Metadata：{_short(out, 600)}"
        self._sync_state_from_tool_output("\n".join(tail))
        for ln in tail:
            if ln.startswith("[ANALYSIS_DATA]"):
                job["data"] = ln[len("[ANALYSIS_DATA]"):].strip()
        if not tail or not any(ln.startswith("[ANALYSIS_DATA]") for ln in tail):
            job["data"] = self.analysis_data or job["data"]
        job["index"] = idx
        job["data_label"] = idx.get("label")
        job["time_range"] = [_sec3(idx["start_ns"]), _sec3(idx["end_ns"])]
        job["duration_sec"] = idx.get("duration_sec")
        try:
            dur = float(idx.get("duration_sec") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        if int(dur) > ANALYSIS_MAX_SECONDS:   # 以整秒算：錄 3 分鐘常是 180.05 秒
            return (f"[ERROR] 數據 {idx.get('label')} 長 {dur:g} 秒，超過一次分析的上限 {ANALYSIS_MAX_SECONDS} 秒。先用 mcap_slicer 切出"
                    f"要看的時間段（{ANALYSIS_MAX_SECONDS} 秒以內，例如 --window +60,+200），再用 analysis_run --data <切片資料夾> 分析。")
        decodable = [t for t in idx["topics"] if t["role"] in ("worker", "text_only")]
        undecodable = [t["topic"] for t in idx["topics"] if t["role"] == "undecodable"]
        if not decodable and undecodable:   # 有訊息、卻一個都解不開＝環境的問題，分析出來的報告沒有意義
            return (f"[ERROR] 這份數據的 Topic 都無法解碼（{'、'.join(undecodable[:6])}{'…' if len(undecodable) > 6 else ''}）："
                    "自訂訊息要先用 ROS2_workspace_env 確認 Workspace（容器裡要有建好、載入的訊息套件）。")
        out = self._analysis_tool("rosout_parser_cmd.py", [job["data"], "--json", "--top", "2000", "--all-nodes"])
        logs, _ = split_json_output(out)
        if logs and "signals" in logs:
            job["signals"] = logs["signals"]
            job["log_source"] = logs.get("source")
            job["log_total"] = logs.get("total_events")
        else:
            job["signals"], job["log_source"] = [], None
            job["log_error"] = _short(out, 300)
        if not decodable and not job["signals"]:
            return "[ERROR] 這份數據沒有任何內容：沒有可以解碼的 Topic，也沒有 Log。"
        if not decodable:   # 只有 Log（例如只錄到 bridge 的 /rosout）：照樣整理 Log 的時間線與重點，沒有 Topic 可以量
            self._analysis_note(job, "📊 這份數據只有 Log，沒有可以量的 Topic：照樣整理去重後的 Log、時間線與重點")
        out = self._analysis_tool("mcap_analyzer_cmd.py", [job["data"], "--facts", "--json", "--timeout", "570"])
        scan, _ = split_json_output(out)
        if not scan or "topics" not in scan:
            return f"[ERROR] 量不到數據的事實（mcap_analyzer --facts）：{_short(out, 600)}"
        job["scan"] = scan
        job["facts"] = build_facts(job)
        self._job_write(job, "topic_facts.json", json.dumps(scan, ensure_ascii=False))
        digest = self._digest_text(job, limit=None, include_recorder=True)
        self._job_write(job, "log_digest.md", f"# 去重後的 Log（{job.get('log_source') or job.get('log_error')}）\n\n{digest}\n")
        self._job_write(job, "topic_metadata.md", f"# 全部 Topic 的事實：{idx.get('label')}（程式量測）\n\n{_facts_overview(job['facts'])}\n")
        f = job["facts"]
        self._analysis_note(job, f"📊 數據 {idx.get('label')}：{idx.get('duration_sec')} 秒；{f['overview']}"
                                 + ("（量測讀快取）" if scan.get("cached") else f"（量測 {scan.get('seconds')} 秒）")
                                 + (f"；Log：{job['log_error']}" if job.get("log_error") else ""))
        return None

    def _signal_ns(self, s, key="first_sec"):
        return int(round(float(s[key]) * 1e9))

    def _digest_text(self, job, limit=ANALYSIS_DIGEST_MAX_SIGNALS, include_recorder=False):
        """去重後的 Log（給 Orchestrator）：略過錄製工具自己的 Log；WARN 以上全部，其餘依時間補到上限。每個訊號後面接印出它的
        ＠檔名:行 函式。include_recorder：給人看的 log_digest.md 連 rosbag2 的 Log 也列（標明是錄製工具的）。"""
        base = job["index"]["start_ns"]
        all_sigs = job.get("signals") or []
        sigs = [s for s in all_sigs if include_recorder or not is_recorder_node(s["node"])]
        if not sigs:
            if all_sigs:   # 有 Log，只是全部是 rosbag2 自己的（實測：穩定狀態的 30 秒錄製，17 則全是 Subscribed to topic…）
                n = sum(s["count"] for s in all_sigs)
                return (f"（Log 共 {n} 則，全部是錄製工具 rosbag2 自己的訊息；受測系統在這段時間沒有輸出任何 Log——"
                        "Log 有讀到，不是缺少 Log）")
            return "（沒有 Log：" + (job.get("log_error") or "這份數據沒有 /rosout，也沒有 rosout.log") + "）"
        important = [s for s in sigs if _LEVEL_RANK.get(s["level"], 1) >= 2]
        others = [s for s in sigs if _LEVEL_RANK.get(s["level"], 1) < 2]
        chosen = sigs if limit is None else important + others[: max(0, limit - len(important))]
        chosen = sorted(chosen, key=lambda s: s["first_sec"])
        lines = []
        for s in chosen:
            when = _rel(self._signal_ns(s), base)
            if s["count"] > 1:
                when += f"～{_rel(self._signal_ns(s, 'last_sec'), base)}"
            var = f"（{len(s['variants'])} 種寫法）" if s.get("variants") else ""
            rec = "（錄製工具 rosbag2 自己的 Log）" if is_recorder_node(s["node"]) else ""
            lines.append(f"{s['id']} {s['level']} ×{s['count']} {when} {s['node']}：{_short(s['message'], 200)}{var}{rec}"
                         f"{'' if rec else _signal_source(s)}")
        hidden = len(sigs) - len(chosen)
        if hidden > 0:
            lines.append(f"（另有 {hidden} 個 INFO 訊號沒有列出）")
        rec = sum(1 for s in all_sigs if is_recorder_node(s["node"]))
        if rec and not include_recorder:
            lines.append(f"（略過錄製工具 rosbag2 自己的 Log {rec} 個訊號）")
        return "\n".join(lines)

    # ---------------------------------------------------------------- 1. Orchestrator 規劃
    def _analysis_orchestrate(self, job):
        idx, facts = job["index"], job["facts"]
        self._analysis_note(job, f"🧭 Orchestrator（{self.analysis_model('orchestrator')}）：對齊問題、挑相關的 Log 訊號、分派要說明的 Topic…")
        forced = [t for t in job["options"]["topics"] if any(r["topic"] == t for r in facts["topics"])]
        must = f"\n使用者指定一定要說明的 Topic：{'、'.join(forced)}（要指派）" if forced else ""
        user = (f"【使用者的問題】\n{job['question']}\n\n"
                f"【數據】{idx.get('label')}：共 {idx.get('duration_sec')} 秒（時間都寫成距離數據開頭的秒數，+秒）\n\n"
                f"【去重後的 Log（唯一訊號；L# 是編號，×N 是出現次數；＠檔名:行 函式＝印出這則 Log 的程式位置）】\n{self._digest_text(job)}\n\n"
                f"【全部 Topic 的事實（程式量測整段數據的全部 Key；T# 是 Topic 的編號）】\n{_facts_overview(facts)}\n\n"
                f"【限制】最多指派 {job['max_workers']} 個 worker，每個 worker 說明一個不同的 Topic；沒有變化的 Topic 不用派（程式已經寫了"
                "「沒有變化」）；Log（/rosout）不能指派——Log 由你負責看。" + must + "\n（每個欄位都用繁體中文寫）")
        system = _read_prompt("orchestrator.md")
        data = self._analysis_session(job, "analysis_orchestrator", "orchestrator", system, user, ANALYSIS_PLAN_SCHEMA, 3072)
        plan, issues = self._clean_plan(job, data, forced)
        if issues:
            fix = (user + "\n\n【上一版計畫】\n" + json.dumps(data or {}, ensure_ascii=False)[:3500]
                   + "\n\n【程式檢查發現的問題：修正後輸出完整的計畫】\n" + "\n".join(f"- {x}" for x in issues))
            self._analysis_note(job, f"🧭 Orchestrator 的計畫有 {len(issues)} 個問題，交回修正一次：{'；'.join(issues)[:200]}")
            data2 = self._analysis_session(job, "analysis_orchestrator", "orchestrator", system, fix, ANALYSIS_PLAN_SCHEMA, 3072)
            plan2, issues2 = self._clean_plan(job, data2, forced)
            if plan2["assignments"] and (len(issues2) <= len(issues) or not plan["assignments"]):
                plan, issues = plan2, issues2
        if not plan["assignments"]:
            plan["assignments"] = _auto_assignments(job, plan["related"], job["max_workers"], forced)
            if plan["assignments"]:
                plan["auto_assigned"] = True
                issues.append("Orchestrator 沒有給出可用的指派，由程式依事件與相關的 Log 指派")
        plan["issues"] = issues
        job["plan"] = plan
        self._job_write(job, "plan.json", json.dumps({"plan": plan}, ensure_ascii=False, indent=1))
        atxt = "；".join(f"W{n}→{a['topic']}" for n, a in enumerate(plan["assignments"], 1)) or "（沒有：全部的 Topic 都沒有變化）"
        self._analysis_note(job, f"🧭 計畫：相關訊號 {', '.join(r['id'] for r in plan['related']) or '（沒有）'}；指派 {atxt}"
                                 + ("（程式補指派）" if plan.get("auto_assigned") else ""), kind="plan")

    def _clean_plan(self, job, data, forced):
        """模型的計畫 → 檢查過的計畫與問題清單（程式檢查，問題會交回 Orchestrator 修一次）。"""
        data = data or {}
        issues = []
        sig_by_id = {str(s["id"]).upper(): s for s in job.get("signals") or []}
        related, seen_ids = [], set()
        for r in data.get("related_signals") or []:
            sid = str((r or {}).get("id", "")).strip().upper()
            if sid in seen_ids:   # 同一個 L# 列兩次：合併就好，不算問題（實測 26b 重複列 L17，舊版報成「不存在」退回修正一次）
                continue
            if sid in sig_by_id:
                seen_ids.add(sid)
                related.append({"id": sig_by_id[sid]["id"], "why": _short((r or {}).get("why", ""), 160)})
            elif sid:
                issues.append(f"Log 訊號 {sid} 不存在（只能用去重後 Log 裡的 L# 編號）")
        assigns, problems, skipped = _clean_assignments(job, data.get("assignments"), forced)
        issues += problems
        plan = {"understanding": _short(data.get("understanding"), 500), "related": related, "assignments": assigns}
        if skipped:
            plan["skipped"] = skipped
        return plan, issues

    # ---------------------------------------------------------------- 2. Workers
    def _analysis_run_workers(self, job, assigns, start=0):
        if not assigns:
            job.setdefault("workers", [])
            self._analysis_note(job, "🔧 沒有要說明的 Topic（全部沒有變化），不派 worker")
            return
        par = max(1, min(int(self.analysis_cfg.get("parallel") or 1), len(assigns)))
        self._analysis_note(job, f"🔧 派 {len(assigns)} 個 worker（同時 {par} 個；模型 {self.analysis_model('worker')}）")
        with ThreadPoolExecutor(max_workers=par) as ex:
            futures = [ex.submit(self._analysis_one_worker, job, start + n, a) for n, a in enumerate(assigns, 1)]
            job["workers"] = job.get("workers", []) + [f.result() for f in futures]
        self._job_save(job)

    def _analysis_one_worker(self, job, n, assignment):
        try:
            return AnalysisWorker(self, job, n, assignment).run()
        except Exception as e:   # noqa: BLE001  一個 worker 壞掉不影響其他 worker
            self._analysis_note(job, f"❌ W{n} {assignment['topic']}：{type(e).__name__}: {e}", kind="worker_error", worker=n)
            return {"n": n, "topic": assignment["topic"], "status": "failed", "error": f"{type(e).__name__}: {e}", "notes": []}

    # ---------------------------------------------------------------- 3～5. 重點 → 檢查 → 報告
    def _analysis_conclude(self, job):
        """worker 說明完之後：Synthesizer 寫重點 → Orchestrator 檢查要不要補派（補派的 worker 做完回到這裡，最多補 max_rounds − 1 輪）
        → 程式組報告。補派之前的報告留成 report_r<n>.md。"""
        facts = job["facts"]
        while True:
            rnd = len(job.setdefault("rounds", [])) + 1
            self._job_status(job, "synthesizing")
            summary = self._analysis_summary(job, rnd, facts)
            fresh = []
            if rnd < job["max_rounds"]:
                self._job_status(job, "checking")
                fresh = self._analysis_check(job, rnd, facts, summary)
            job["report"] = _report_data(job, facts, summary)
            job["rounds"].append({"round": rnd, "workers": [w["n"] for w in job["workers"]], "followups": [a["topic"] for a in fresh]})
            report_md = self._render_report(job, facts, summary)
            self._job_write(job, "report.md", report_md)
            self._job_save(job)
            if not fresh:
                return self._report_for_main(job, facts, summary)
            self._job_write(job, f"report_r{rnd}.md", report_md)
            self._analysis_followups(job, rnd + 1, fresh)

    def _analysis_summary(self, job, rnd, facts):
        """Synthesizer：整段數據的重點，一則一則（refs 指到 E#／L#／T#，時間由程式補）。程式核對每一則（_review_notes），有問題交回
        修一次（prompts/synthesizer_2.md），還是不行的那一則不列；一則都沒有通過（或 JSON 壞掉）時由程式依事實列出重點。"""
        self._analysis_note(job, f"🧩 Synthesizer（{self.analysis_model('synthesizer')}）：整理重點"
                                 + (f"（第 {rnd} 輪）" if rnd > 1 else "") + "…")
        allowed = set(facts["events"]) | set(facts["signals"]) | {r["id"] for r in facts["topics"]}
        cap = _highlight_cap(facts)   # 則數上限跟著事實：重要的時間點多，重點就可以多（固定的上限會逼模型把好幾件事塞進一則、或漏掉）
        schema, predict = _with_max_items(ANALYSIS_SUMMARY_SCHEMA, "highlights", cap), max(2048, 192 * cap)
        system, user = _read_prompt("synthesizer.md"), _summary_user(job, facts, cap)
        data = self._analysis_session(job, "analysis_synthesizer", "synthesizer", system, user, schema, predict)
        items = (data or {}).get("highlights") or []
        kept, problems = _review_notes(items, allowed, facts)
        kept = _unique(kept)
        moments = _moments(facts)[0]
        missing = _missing_moments(moments, kept) if kept else []
        record = {"round": rnd, "cap": cap, "moments": len(moments), "given": len(items), "issues": [_problem_text(p) for p in problems]}
        if missing:
            record["missing"] = [_moment_text(m) for m in missing]
        if problems or missing:
            why = ([f"{len(problems)} 則沒有通過核對：{_problem_text(problems[0])[:140]}"] if problems else []) + \
                  ([f"{len(missing)} 個重要的時間點沒有寫到：{'、'.join(m['id'] for m in missing)}"] if missing else [])
            self._analysis_note(job, f"🧩 交回 Synthesizer 一次：{'；'.join(why)[:200]}")
            data2 = self._analysis_session(job, "analysis_synthesizer", "synthesizer", system,
                                           _retry_text(user, "highlights", items, problems, missing=missing), schema, predict)
            kept, problems, saved = _merge_retry(kept, problems, (data2 or {}).get("highlights") or [], allowed, facts)
            record["left"] = [_problem_text(p) for p in problems]
            left_missing = _missing_moments(moments, kept)
            if missing:
                record["left_missing"] = [_moment_text(m) for m in left_missing]
            if saved:
                record["trimmed"] = saved
        fallback = False
        if not kept:
            self._analysis_note(job, "🧩 Synthesizer 沒有給出可用的重點，由程式依事實列出")
            kept, fallback = _fallback_highlights(facts), True
        else:   # 交回之後還是漏掉的時間點：程式補一則（重點才不會少掉一刻；模型漏寫幾個記在 summary_checks）
            filled = [_moment_note(m, facts) for m in _missing_moments(moments, kept)]
            if filled:
                record["filled"] = [_moment_text(m) for m in _missing_moments(moments, kept)]
                kept = kept + filled
        job.setdefault("summary_checks", []).append(record)
        kept = _attach_moments(kept, moments, facts)
        highlights = sorted((_render_note(n, facts, details=True) for n in kept), key=lambda h: (h["t"] is None, h["t"] or 0))
        return {"highlights": highlights, "dropped": [_problem_text(p) for p in problems], "fallback": fallback}

    def _analysis_check(self, job, rnd, facts, summary):
        """Orchestrator 檢查：WARN 以上或規劃時挑的 Log，前後 ANALYSIS_ALIGN_SEC 秒內有變化、但還沒有 worker 說明的 Topic——問它要不要
        補派 worker（每一項寫它對應哪一則 Log）。程式核對：Topic 要在候選清單裡、Log 要是它前後的那幾則、最多 ANALYSIS_FOLLOWUP_WORKERS 個；
        不符合的不補（不交回）。沒有候選就不問。"""
        explained = {w["topic"] for w in job["workers"]}
        cands = _check_candidates(job, facts, explained)
        rec = {"round": rnd, "candidates": [{"topic": c["topic"], "near": c["near"]} for c in cands], "asked": False,
               "followups": [], "issues": []}
        job.setdefault("checks", []).append(rec)
        if not cands:
            rec["why"] = "WARN 以上或相關的 Log 前後有變化的 Topic 都已經有 worker 說明（或前後沒有任何變化）"
            self._analysis_note(job, f"🧭 檢查：{rec['why']}，不補派", kind="plan")
            return []
        rec["asked"] = True
        self._analysis_note(job, f"🧭 Orchestrator（{self.analysis_model('orchestrator')}）：{'、'.join(c['topic'] for c in cands[:4])} "
                                 "在相關的 Log 前後有變化、還沒有說明，檢查要不要補派…")
        data = self._analysis_session(job, "analysis_orchestrator_check", "orchestrator", _read_prompt("orchestrator_check.md"),
                                      _check_user(job, facts, summary, cands), ANALYSIS_CHECK_SCHEMA, 1536, label="orchestrator_check")
        by_topic = {c["topic"].lower(): c for c in cands}
        by_tid = {c["tid"]: c for c in cands}
        fresh, problems = [], []
        for f in (data or {}).get("followups") or []:
            f = f if isinstance(f, dict) else {}
            m = re.search(r"L\d+", str(f.get("signal") or "").upper())
            sid = m.group() if m else ""
            raw = str(f.get("topic") or "").strip()
            c = by_tid.get(raw.upper()) or by_topic.get((raw if raw.startswith("/") else "/" + raw).lower())
            if not c:
                problems.append(f"{raw}：不在「相關的 Log 前後有變化、還沒有說明」的 Topic 清單裡，不補")
            elif sid not in c["near"]:
                problems.append(f"{c['topic']}：對應的 Log「{sid or f.get('signal')}」不是它前後的那幾則（{'、'.join(c['near'])}），不補")
            elif c["topic"] in [a["topic"] for a in fresh]:
                continue
            elif len(fresh) >= ANALYSIS_FOLLOWUP_WORKERS:
                problems.append(f"{c['topic']}：一次最多補 {ANALYSIS_FOLLOWUP_WORKERS} 個，不補")
            else:
                fresh.append({"topic": c["topic"], "signal": sid,
                              "subtask": _short(f.get("subtask") or "", 400) or f"說明這個 Topic 在 {sid} 前後的變化"})
        rec.update(followups=[dict(a) for a in fresh], issues=problems)
        self._analysis_note(job, ("🔁 Orchestrator 補派：" + "；".join(f"{a['topic']}（為了 {a['signal']}）" for a in fresh)) if fresh else
                            ("🔁 Orchestrator 判斷不用補派，分析結束" + (f"（程式檢查：{'；'.join(problems)[:160]}）" if problems else "")),
                            kind="plan")
        return fresh

    def _analysis_followups(self, job, rnd, fresh):
        """補派：Orchestrator 挑的、還沒有說明的 Topic，流程同 worker。"""
        start = len(job["workers"])
        for a in fresh:
            a["round"] = rnd
        job["plan"].setdefault("followups", []).extend(fresh)
        self._job_write(job, "plan.json", json.dumps({"plan": job["plan"]}, ensure_ascii=False, indent=1))
        self._analysis_note(job, f"🔁 補派 {len(fresh)} 個 worker：" + "；".join(f"W{start + i}→{a['topic']}" for i, a in enumerate(fresh, 1)),
                            kind="plan")
        self._job_status(job, "working")
        self._analysis_run_workers(job, fresh, start=start)

    def _render_report(self, job, facts, summary):
        """報告（Frontmatter Markdown）：重點、各 Topic 的結果、Workers 的說明、時間線、同時發生的變化、前後沒有任何變化的 Log、
        沒有訊息或無法解碼的 Topic、分析過程。除了重點與 Workers 的說明（一則一則，附事實的編號），全部由程式從量測結果與 Log 整理。"""
        plan = job["plan"]
        fm = {"artifact": "fact_report", "job": job["id"], "question": job["question"], "data": job.get("data_label"),
              "data_path": job["data"], "time_range": job.get("time_range"), "related_signals": [r["id"] for r in plan["related"]],
              "workers": [{"topic": w["topic"], "tid": w.get("tid"), "notes": len(w.get("notes") or []), "file": w.get("file")}
                          for w in job["workers"]],
              "unmatched_logs": [x["id"] for x in facts["unmatched_logs"]], "models": job["models"]}
        if plan.get("followups"):
            fm["followups"] = [{"topic": a["topic"], "signal": a.get("signal")} for a in plan["followups"]]
        lines = [frontmatter(fm), f"# 數據事實報告\n\n**問題**：{job['question']}\n\n**數據**：{job.get('data_label')}（{job['data']}，"
                                  f"{job.get('duration_sec')} 秒）\n",
                 f"> 只列數據裡量到的事實與 Log 的原文。「前後 {ANALYSIS_ALIGN_SEC:g} 秒內」只是時間上的對照，不代表誰造成誰；"
                 "原因要對照源碼另外分析。編號：T#＝Topic、E#＝Topic 的事件、L#＝Log 訊號。\n"]
        hl = "\n".join(_note_line(h) for h in summary["highlights"])
        lines.append(f"## 重點\n**總覽（程式）**：{facts['overview']}\n\n" + (hl or "（沒有重點）")
                     + ("\n\n（Synthesizer 沒有給出可用的重點，以上由程式依事實列出）" if summary.get("fallback") else "")
                     + (f"\n\n（另有 {len(summary['dropped'])} 則重點沒有通過程式核對，沒有列出，見 job.json 的 summary_checks）"
                        if summary.get("dropped") else "") + "\n")
        lines.append("## 各 Topic 的結果（程式量測整段數據的全部 Key）\n| 編號 | Topic | 類別 | 發布 | 變化 | 到最後 |\n|---|---|---|---|---|---|\n"
                     + "\n".join(f"| {r['id']} | {r['topic']} | {'、'.join(r['tags'])} | {_cell(r['publish'])} | "
                                 f"{_cell('；'.join(r['changes'] + r['ranges']) or '-')} | "
                                 f"{_cell('；'.join(r['end']) or ('；'.join(r['still'][:4]) + '（沒有變化）' if r['still'] else '-'))} |"
                                 for r in facts["topics"]) + "\n")
        ws = [w for w in job["workers"] if w.get("notes") or w.get("status") == "failed"]
        if ws:
            parts = []
            for w in ws:
                head = f"### W{w['n']} {w.get('tid') or ''} {w['topic']}" + (f"（第 {w['round']} 輪補派，為了 {w.get('signal')}）" if w.get("round") else "")
                body = "\n".join(_note_line(h) for h in w.get("notes") or []) or f"（失敗：{w.get('error')}）"
                parts.append(f"{head}\n{body}")
            lines.append("## Workers 的說明\n" + "\n\n".join(parts) + "\n")
        if facts["timeline"]:
            lines.append(f"## 時間線\n| 編號 | 時間 | 來源 | 事件 | 前後 {ANALYSIS_ALIGN_SEC:g} 秒內 |\n|---|---|---|---|---|\n" + "\n".join(
                f"| {r['ref'] or '-'} | {r['time']} | {_cell(r['source'])} | {_cell(r['event'])} | {_cell(r['near'])} |" for r in facts["timeline"])
                + "\n")
        if facts["same_time"]:
            lines.append(f"## 同時發生的變化（{ANALYSIS_SAME_TIME_SEC:g} 秒內）\n" + "\n".join(
                f"- {g['time']}：{'、'.join(g['events'])}" for g in facts["same_time"]) + "\n")
        if facts["unmatched_logs"]:
            lines.append(f"## 前後 {ANALYSIS_ALIGN_SEC:g} 秒內沒有任何 Topic 變化的 Log\n" + "\n".join(
                f"- {x['id']} {x['level']} {_plus(x['t'])} {x['node']}：{_short(x['text'], 160)}{x['where']}" for x in facts["unmatched_logs"]) + "\n")
        if facts["unreadable"]:
            lines.append("## 沒有量的 Topic\n" + "\n".join(f"- {k}：{'、'.join(v)}" for k, v in facts["unreadable"].items()) + "\n")
        # Orchestrator 的理解與挑訊號的理由是規劃用的文字（可能有推測），不放進事實報告；完整的在 plan.json
        steps = ["- Orchestrator 挑的相關 Log：" + ("、".join(r["id"] for r in plan["related"]) or "（沒有）")]
        steps += [f"- W{w['n']} {w['topic']}：{_short(w.get('subtask'), 160)}"
                  + (f"（第 {w['round']} 輪補派，為了 {w.get('signal')}）" if w.get("round") else "")
                  + f"→ {len(w.get('notes') or [])} 則說明" + (f"（{len(w['dropped'])} 則沒有通過程式核對）" if w.get("dropped") else "")
                  + (f"；失敗：{w.get('error')}" if w.get("status") == "failed" else "") + f" `{w.get('file') or '-'}`"
                  for w in job["workers"]]
        for c in job.get("checks") or []:
            steps.append(f"- 第 {c['round']} 輪的檢查：" + (("補派 " + "、".join(f"{a['topic']}（為了 {a['signal']}）" for a in c["followups"]))
                                                        if c["followups"] else ("Orchestrator 判斷不用補派" if c["asked"] else f"不用問（{c.get('why')}）"))
                         + (f"（程式檢查：{'；'.join(c['issues'])[:200]}）" if c.get("issues") else ""))
        if plan.get("skipped"):
            steps.append(f"- 規劃時沒有派的 Topic：{'；'.join(plan['skipped'])[:300]}")
        if job.get("model_aborted"):
            steps.append(f"- 模型的輸出被 Ollama 中止 {len(job['model_aborted'])} 次（當成沒有可用的輸出處理）：{'；'.join(job['model_aborted'])[:300]}")
        if plan.get("issues"):
            steps.append(f"- 規劃的程式檢查：{'；'.join(plan['issues'])[:300]}")
        lines.append("## 分析過程\n" + "\n".join(steps) + "\n")
        return "\n".join(lines)

    def _report_for_main(self, job, facts, summary):
        """回傳給主對話的報告重點（以 ANALYSIS_REPORT_HEAD 開頭：不再摘要、整份進主對話，並存成 #編號）。"""
        n = len(job["workers"])
        lines = [f"{ANALYSIS_REPORT_HEAD}（job {job['id']}：{n} 個 worker、模型呼叫 {{CALLS}} 次、{{SECONDS}} 秒）",
                 f"問題：{job['question']}", f"數據：{job.get('data_label')}（{job.get('duration_sec')} 秒）",
                 f"總覽（程式）：{facts['overview']}"]
        if summary["highlights"]:
            lines.append("重點（時間由程式依編號補上；引用的事件與 Log 的內容由程式列在下面）：\n" + "\n".join(
                _note_line(h, n=110, bold=False, max_lines=6) for h in summary["highlights"]))
        busy = [r for r in facts["topics"] if r["events"] or "數值變動" in r["tags"]]
        if busy:
            lines.append("有變化的 Topic：\n" + "\n".join(
                f"- {r['id']} {r['topic']}｜{'、'.join(r['tags'])}｜{r['publish']}"
                + (f"｜{'；'.join((r['changes'] + r['ranges'])[:3])}" if r["changes"] or r["ranges"] else "")
                + (f"｜到最後：{'；'.join(r['end'][:3])}" if r["end"] else "") for r in busy))
        quiet = [r["topic"] for r in facts["topics"] if not (r["events"] or "數值變動" in r["tags"])]
        if quiet:
            lines.append(f"沒有變化的 Topic（{len(quiet)} 個）：{'、'.join(quiet[:12])}" + ("…" if len(quiet) > 12 else ""))
        cited = {r for h in summary["highlights"] for r in h["refs"] + (h.get("also") or [])}
        rest = [r for r in facts["timeline"] if r["ref"] not in cited]   # 重點已經列了內容的不再列
        if rest:
            rows = _top_rows(rest, _MAIN_TIMELINE_MAX)
            lines.append(f"時間線（重點沒有引用的 {len(rest)} 列中的 {len(rows)} 列；完整的 {len(facts['timeline'])} 列在報告）：\n" + "\n".join(
                f"- {r['ref'] or '-'}｜{r['time']}｜{r['source']}｜{_short(r['event'], 140)}｜前後 {ANALYSIS_ALIGN_SEC:g} 秒內：{r['near']}"
                for r in rows))
        if facts["same_time"]:
            lines.append("同時發生的變化：" + "；".join(f"{g['time']} {'、'.join(g['events'])}" for g in facts["same_time"][:5]))
        if facts["unmatched_logs"]:
            lines.append(f"前後 {ANALYSIS_ALIGN_SEC:g} 秒內沒有任何 Topic 變化的 Log："
                         + "；".join(f"{x['id']} {_plus(x['t'])} {x['node']}：{_short(x['text'], 80)}" for x in facts["unmatched_logs"][:6]))
        if facts["unreadable"]:
            lines.append("沒有量的 Topic：" + "；".join(f"{k}：{'、'.join(v[:8])}" for k, v in facts["unreadable"].items()))
        lines.append(f"完整報告：logs/{ANALYSIS_JOBS_DIRNAME}/{job['id']}/report.md（各 worker 的說明在 workers/）")
        lines.append(ANALYSIS_ANSWER_NOTE + "：只陳述報告裡的事實——時間、數值、狀態、Log 的原文，可以引用編號。報告沒有判斷原因："
                     "「前後 1 秒內」「同時」只是時間上的先後，不要寫成誰導致、造成、觸發誰；使用者問「為什麼」時，照事實說明發生了什麼、"
                     "先後順序，並說明原因要對照源碼另外分析）")
        return "\n".join(lines)


# ---------------------------------------------------------------- 指派（程式檢查與補指派）
def _clean_assignments(job, items, forced):
    """模型的指派 → (檢查過的指派, 問題清單, 沒有派的 Topic)：Topic 要在事實裡（可以寫名稱或 T#）、不是框架的 Topic、不重複，最多 N 個；
    沒有變化的 Topic 不派（不算問題，程式已經寫了「沒有變化」）；使用者指定的 Topic 一定有。"""
    facts = job["facts"]
    rows = {r["topic"]: r for r in facts["topics"]}
    lower = {k.lower(): k for k in rows}
    by_tid = {r["id"]: r["topic"] for r in facts["topics"]}
    issues, skipped, assigns, seen = [], [], [], set()
    for a in items or []:
        a = a if isinstance(a, dict) else {}
        raw = str(a.get("topic", "")).strip()
        m = re.fullmatch(r"(T\d+)(?:\s+(\S+))?", raw.upper())
        name = by_tid.get(m.group(1)) if m else None
        if name is None:
            name = raw.split()[0] if raw else ""
            name = name if name.startswith("/") else "/" + name
            name = lower.get(name.lower(), name)
        r = rows.get(name)
        if not r:
            if name == "/rosout" or name in ("/rosout_agg",):
                issues.append(f"{name} 不能指派給 worker（Log 由 Orchestrator 自己看）")
            else:
                issues.append(f"Topic「{raw}」不在事實裡（只能從全部 Topic 的事實選，可以寫名稱或 T#）")
            continue
        if name in seen:
            issues.append(f"{name} 重複指派（一個 Topic 只給一個 worker，換別的 Topic 擴大說明的範圍）")
            continue
        seen.add(name)
        if not (r["events"] or "數值變動" in r["tags"]) and name not in forced:
            skipped.append(f"{name}（沒有變化）")
            continue
        subtask = _short(a.get("subtask") or "", 400) or "說明這個 Topic 在整段數據裡的變化"
        assigns.append({"topic": name, "subtask": subtask})
    for t in forced:
        if t not in seen:
            assigns.insert(0, {"topic": t, "subtask": "使用者指定要說明這個 Topic：說明它在整段數據裡的變化"})
            seen.add(t)
    if len(assigns) > job["max_workers"]:
        issues.append(f"指派了 {len(assigns)} 個 worker，超過上限 {job['max_workers']}（只保留前 {job['max_workers']} 個）")
        assigns = assigns[: job["max_workers"]]
    if not assigns and any(r["events"] or "數值變動" in r["tags"] for r in facts["topics"]):
        issues.append("沒有任何有效的指派：至少把一個有變化的 Topic 指派給 worker")
    return assigns, issues, skipped


def _auto_assignments(job, related, n, forced):
    """Orchestrator 沒給出可用的指派時：有事件的 Topic，依「事件在相關的 Log 前後 ANALYSIS_ALIGN_SEC 秒內」的次數、事件數排，同分看編號
    （程式的順序，每次一樣）。"""
    facts = job["facts"]
    key = {r["id"] for r in related} | {s["id"] for s in job.get("signals") or [] if _LEVEL_RANK.get(s.get("level"), 1) >= 2}
    log_times = [x["t"] for x in facts["logs"] if x["id"] in key]
    scored = []
    for i, r in enumerate(facts["topics"]):
        if not r["events"] or r["topic"] in forced:
            continue
        times = [facts["events"][e]["t"] for e in r["events"]]
        near = sum(1 for t in times if any(abs(t - lt) <= ANALYSIS_ALIGN_SEC for lt in log_times))
        scored.append((-near, -len(times), i, r["topic"]))
    scored.sort()
    out = [{"topic": t, "subtask": "使用者指定要說明這個 Topic：說明它在整段數據裡的變化"} for t in forced]
    for *_, topic in scored:
        if len(out) >= n:
            break
        out.append({"topic": topic, "subtask": "說明這個 Topic 在整段數據裡的變化（狀態、數值、開始或停止發布、訊息中斷）"})
    return out


def _check_candidates(job, facts, explained):
    """Orchestrator 檢查的候選：有事件、還沒有 worker 說明、而且事件在 WARN 以上或規劃時挑的 Log 前後 ANALYSIS_ALIGN_SEC 秒內的 Topic。"""
    related = {r["id"] for r in (job.get("plan") or {}).get("related") or []}
    key_logs = [x for x in facts["logs"] if _LEVEL_RANK.get(x["level"], 1) >= 2 or x["id"] in related]
    out = []
    for r in facts["topics"]:
        if not r["events"] or r["topic"] in explained:
            continue
        near = sorted({x["id"] for e in r["events"] for x in key_logs if abs(facts["events"][e]["t"] - x["t"]) <= ANALYSIS_ALIGN_SEC},
                      key=lambda s: int(s[1:]))
        if near:
            out.append({"tid": r["id"], "topic": r["topic"], "near": near,
                        "events": [f"{e} {_plus(facts['events'][e]['t'])} {facts['events'][e]['text']}" for e in r["events"][:6]]})
    return out


# ---------------------------------------------------------------- 用詞與編號：worker 的說明與 Synthesizer 的重點共用一套核對
# 不是事實的寫法：原因、誰造成誰、推測。事實層只寫量到什麼、什麼時候
_NOT_FACT_WORDS = ("導致", "造成", "引起", "觸發", "根因", "原因", "證實", "證明", "排除", "歸因", "因此", "所以", "由於", "因為",
                   "可能是", "推測", "疑似", "或許")
_INTERRUPT_WORDS = ("中斷", "間歇", "斷斷續續", "丟失", "遺失")   # 不用「斷訊」：「診斷訊息」裡就有
# 跟發布有關的說法要有對應的事件：寫「開始發布」就要引用開始發布的事件（實測 Synthesizer 把持續發布的 Topic 寫成開始與停止）
_PUBLISH_WORDS = {"開始發布": ("start", "first"), "停止發布": ("stop",), "恢復發布": ("resume",)}
# 否定的說法不算：否定詞到子句結束（逗號、句號）都算否定的範圍——「沒有任何狀態跳轉、數值尖峰或訊息中斷」「是否中斷」
_NEGATED = re.compile(r"(?:沒有|無|未|並非|不是|不屬於|而非|不算|是否|有沒有)[^，。；\n]{0,25}")
_SIGNAL_REF = re.compile(r"(?<![A-Za-z0-9_])L(\d+)(?![0-9])")
_TIME_IN_TEXT = re.compile(r"[+＋]\s?(\d{1,4}(?:\.\d+)?)\s?(?:s|秒)")
_REF = re.compile(r"^\s*([ELT])\s*[-_#]?\s*(\d+)\s*$")


def _interrupt_words(text):
    """文字（去掉否定的說法之後）用了哪些「中斷、間歇、丟失」類的字。"""
    t = _NEGATED.sub("", text or "")
    return [w for w in _INTERRUPT_WORDS if w in t]


def _not_fact_words(text, quoted=""):
    """寫了哪些「不是事實」的字（原因、誰造成誰、推測）；quoted（Log 原文、量到的字串）裡本來就有的不算。"""
    return [w for w in _NOT_FACT_WORDS if w in (text or "") and w not in quoted]


def _norm_ref(r):
    m = _REF.match(str(r or "").upper())
    return f"{m.group(1)}{int(m.group(2))}" if m else ""


def _ref_times(refs, facts):
    """引用的事實的時間（+秒）：E# 是事件的時間、L# 是這則 Log 每一次出現的時間；T# 沒有時間。"""
    out = []
    for r in refs:
        if r in facts["events"]:
            out.append(facts["events"][r]["t"])
        elif r in facts["signals"]:
            out += facts["signals"][r]["times"]
    return out


def _with_topic_events(refs, facts):
    """引用的編號，T#（整個 Topic）連同它的事件：核對用詞與時間時，說明整個 Topic 的一則可以寫它的開始、中斷與那些時間
    （實測 worker 的「這個 Topic 在 +23.10s 至 +27.20s 連續發布（T3）」被當成時間沒有根據，交回一次）。"""
    rows = {r["id"]: r for r in facts["topics"]}
    out = list(refs)
    for r in refs:
        out += [e for e in (rows[r]["events"] if r in rows else []) if e not in out]
    return out


def _check_note(note, allowed, facts):
    """一則說明（worker 的 note、Synthesizer 的 highlight）→ (整理過的 {refs, text}, 問題清單)。核對：
    - refs 要是允許的編號（worker 只能引用自己那個 Topic 的 E#／T#；Synthesizer 可以引用 E#、L#、T#）；
    - 太長（寫到格式的上限）＝失控、被截斷在半句；
    - 寫了原因、誰造成誰或推測（Log 原文、量到的字串裡本來就有的不算）；
    - 寫了「中斷」「開始發布」「停止發布」「恢復發布」，引用的事件裡卻沒有那種事件；
    - 寫了時間（+秒），引用的事實裡沒有這個時間（時間由程式依 refs 補上，不用自己寫）。
    T#（整個 Topic）連同它的事件算引用（_with_topic_events）。"""
    note = note if isinstance(note, dict) else {}
    refs = list(dict.fromkeys(r for r in (_norm_ref(x) for x in note.get("refs") or []) if r in allowed))
    text = " ".join(str(note.get("text") or "").split())
    issues = []
    if not text:
        issues.append("沒有寫說明")
    if not refs:
        bad = [str(x) for x in note.get("refs") or []]
        issues.append("沒有可以用的編號" + (f"（{'、'.join(bad[:4])} 不在可以引用的事實裡）" if bad else "") + "：每一則都要用 refs 指到事實的編號")
    if len(text) >= ANALYSIS_NOTE_MAX - 5:
        issues.append(f"太長、被截斷在半句（{len(text)} 字）：一則只寫一件事、一兩句話；同一時間的好幾則 Log 寫則數與層級就好"
                      "（refs 列編號，每則 Log 程式會列在這一則下面）")
    quoted = facts["quoted"]
    bad = _not_fact_words(text, quoted)
    if bad:
        issues.append(f"寫了「{'、'.join(bad)}」：只寫量到什麼、什麼時候、哪些一起變化，不寫原因、誰造成誰，也不推測")
    covered = _with_topic_events(refs, facts)   # T# 連同它的事件：「這個 Topic 從 +16.50s 開始發布」引用 T# 也對
    kinds = {facts["events"][r]["kind"] for r in covered if r in facts["events"]}
    plain = _NEGATED.sub("", text)
    words = [w for w in _interrupt_words(text) if w not in quoted]
    if words and not kinds & {"gap", "resume"}:
        issues.append(f"寫了「{words[0]}」，但引用的事件裡沒有訊息中斷（中斷＝固定頻率的 Topic 停了一段又恢復；只停止發布寫「停止發布」）")
    for word, ks in _PUBLISH_WORDS.items():
        if word in plain and word not in quoted and not kinds & set(ks):
            issues.append(f"寫了「{word}」，但引用的事件裡沒有{word}的事件（照引用的事件寫）")
    ref_t = _ref_times(covered, facts)
    loose = [m.group(0) for m in _TIME_IN_TEXT.finditer(text) if not any(abs(float(m.group(1)) - t) <= _TIME_TOL for t in ref_t)]
    if loose:
        issues.append(f"寫了 {'、'.join(loose[:3])}，引用的事實裡沒有這個時間（時間由程式依編號補上，不用自己寫）")
    return {"refs": refs, "text": text}, issues


def _review_notes(items, allowed, facts):
    """一串說明 → (通過的, [(第幾則, 整理過的, 問題)])。"""
    kept, problems = [], []
    for i, n in enumerate(items or [], 1):
        note, issues = _check_note(n, allowed, facts)
        if issues:
            problems.append((i, note, issues))
        else:
            kept.append(note)
    return kept, problems


_SENTENCE_END = re.compile(r"[。；！？]")


def _salvage(problems, allowed, facts):
    """交回修過還是太長的說明：截到最後一個完整的句子（。；！？），再核對一次；通過的照列（不讓一則失控的說明整則消失，
    也不留半句）。回傳 (救回來的, 還是不行的)。"""
    saved, left = [], []
    for i, note, issues in problems:
        cut = [m.end() for m in _SENTENCE_END.finditer(note["text"])]
        if cut and all(x.startswith("太長") for x in issues):
            text = note["text"][:cut[-1]].rstrip("；，、 ")
            fixed, again = _check_note({"refs": note["refs"], "text": text}, allowed, facts)
            if not again:
                saved.append(dict(fixed, trimmed=True))
                continue
        left.append((i, note, issues))
    return saved, left


def _unique(notes):
    """去掉重複的說明（同一組編號、或同一段文字：模型有時把同一則重複寫好幾次，或交回修正時整份重寫）。"""
    out, refs, texts = [], set(), set()
    for n in notes:
        k = frozenset(n["refs"])
        if k in refs or n["text"] in texts:
            continue
        refs.add(k)
        texts.add(n["text"])
        out.append(n)
    return out


def _retry_text(user, field, items, problems, why=None, missing=()):
    """交回修正的輸入：原本的輸入＋有問題的那幾則（原文）＋問題。只要模型輸出修正後的那幾則：通過的程式會保留（_merge_retry），
    不用叫它「沒問題的照抄」——實測照抄時常常少抄（7 則只回 2 則），通過的重點就不見了。"""
    bad, seen = [], set()
    for i, _, _ in problems:   # 同一則重複寫了好幾次的只附一次
        k = json.dumps(items[i - 1], ensure_ascii=False, sort_keys=True) if 0 < i <= len(items) else None
        if k and k not in seen:
            seen.add(k)
            bad.append(items[i - 1])
    why = why if why is not None else [_problem_text(p) for p in problems]
    if not bad and not missing:   # 上一版什麼都沒有（或格式壞掉）：要完整的
        return user + "\n\n【程式核對發現的問題】\n" + "\n".join(f"- {x}" for x in why) + f"\n\n【要輸出的】完整的 {field}"
    parts = [user]
    if bad:
        parts.append("【上一版有問題的那幾則（其他的通過了，程式會保留，不用重寫）】\n" + json.dumps({field: bad}, ensure_ascii=False)[:4000])
    if why:
        parts.append("【程式核對發現的問題】\n" + "\n".join(f"- {x}" for x in why))
    if missing:   # 重點漏掉的時間點：照時間寫、上限用完就停，最後的時間點常被漏掉（實測任務失敗的那一刻）
        parts.append("【沒有寫到的重要時間點（已經寫好的程式會保留；每個時間點補一則，refs 引用其中的編號）】\n"
                     + "\n".join(f"- {_moment_text(m)}" for m in missing))
    parts.append(f"【要輸出的】{field}：只放" + "與".join(x for x, on in (("修正後的那幾則", bad), ("補寫的時間點", missing)) if on)
                 + "（一則寫不下就拆成幾則；沒辦法照事實寫的可以不放）")
    return "\n\n".join(parts)


def _merge_retry(kept, problems, items2, allowed, facts):
    """交回修正的結果併進第一版 → (全部通過的, 沒有列出的, 截短救回的則數)：第一版通過的照留；修正的那幾則逐則核對，通過的補進來
    （跟留下的重複的不收：同一組編號、同一段文字，或引用的編號全部已經在通過的裡面——模型有時不照指示整份重寫一遍）。修正版有通過的＝原本有問題的那幾則已經被取代（修正時常拆開、改編號，對不回原本是哪一則；再救原本那一則
    會重複），只救修正版裡還是太長的；修正版一則都沒通過，修正版只是同幾則的重寫，救原本那幾則。太長的截到完整的句子（_salvage），
    其餘不列（同一段文字只記一次）。"""
    kept2, problems2 = _review_notes(items2, allowed, facts)
    covered = {r for n in kept for r in n["refs"]}
    fresh = lambda notes: [n for n in notes if not set(n["refs"]) <= covered]   # noqa: E731  引用的全部已經在通過的裡面＝重寫了一遍，重複
    out = _unique(list(kept) + fresh(kept2))
    saved, left = _salvage(problems2 if kept2 else list(problems), allowed, facts)
    n0 = len(out)
    out = _unique(out + fresh(saved))
    seen, uniq_left = set(), []
    for p in left:
        if p[1]["text"] not in seen:
            seen.add(p[1]["text"])
            uniq_left.append(p)
    return out, uniq_left, len(out) - n0


def _problem_text(p):
    i, note, issues = p
    return f"第 {i} 則（「{_short(note['text'], 50)}」）：{'；'.join(issues)}"


def _render_note(note, facts, details=False):
    """一則說明 → {refs, text, t, time}：時間由程式依 refs 算（E# 的時間；L# 取最接近同一則裡 E# 的那一次，沒有 E# 就是第一次）。
    details（Synthesizer 的重點）：引用的事件與 Log 的內容由程式列出（facts：事件的完整內容、Log 的層級、節點與原文）——模型只寫
    這一刻的重點，數值不用逐項抄（同一時間好幾個 Topic 改變時逐項抄會寫滿上限；抄的時候也可能把另一個項目的值寫錯）。"""
    e_times = [facts["events"][r]["t"] for r in note["refs"] if r in facts["events"]]
    times = list(e_times)
    for r in note["refs"]:
        if r in facts["signals"]:
            occ = facts["signals"][r]["times"]
            if occ:
                times.append(min(occ, key=lambda t: abs(t - sum(e_times) / len(e_times))) if e_times else occ[0])
    extra = {"trimmed": True} if note.get("trimmed") else {}
    if details:
        cited = list(note["refs"]) + [r for r in note.get("also") or [] if r not in note["refs"]]
        ev = sorted((r for r in cited if r in facts["events"]), key=lambda r: int(r[1:]))
        lines = [f"{r} {facts['events'][r]['topic']}：{facts['events'][r]['text']}" for r in ev]
        lines += [f"{r} {facts['signals'][r]['level']} {facts['signals'][r]['node']}：{_short(facts['signals'][r]['text'], 120)}"
                  for r in sorted((r for r in cited if r in facts["signals"]), key=lambda r: int(r[1:]))]
        if lines:
            extra["facts"] = lines
        if note.get("also"):
            extra["also"] = list(note["also"])
        if note.get("program"):
            extra["program"] = True
    if not times:
        return dict({"refs": note["refs"], "text": note["text"], "t": None, "time": ""}, **extra)
    lo, hi = min(times), max(times)
    return dict({"refs": note["refs"], "text": note["text"], "t": lo, "time": _plus(lo) + (f"～{_plus(hi)}" if hi - lo >= 0.005 else "")}, **extra)


def _note_line(h, n=None, bold=True, max_lines=None):
    """報告裡的一則說明或重點：時間（程式依編號補）、文字、編號（模型引用的；同一刻程式補上的列「同一時間」）；重點引用的事件與 Log
    由程式列在下面（n：每一行最多幾個字；max_lines：最多列幾行，其餘註明在報告）。"""
    when = h["time"] or "整段"
    also = f"；同一時間：{'、'.join(h['also'])}" if h.get("also") else ""
    line = f"- {'**' + when + '**' if bold else when}　{h['text']}（{'、'.join(h['refs'])}{also}）"
    rows = h.get("facts") or []
    shown = rows if max_lines is None else rows[:max_lines]
    line += "".join(f"\n  - {_short(x, n) if n else x}" for x in shown)
    if len(rows) > len(shown):
        line += f"\n  - …另 {len(rows) - len(shown)} 個事件與 Log（完整的在報告）"
    return line


def _moment_note(m, facts):
    """程式寫的一則重點（模型沒有寫到的時間點、或 Synthesizer 沒有給出可用的重點）：引用那個時間點的編號，內容由 _render_note 列在下面。"""
    ev = [r for r in m["refs"] if r in facts["events"]]
    logs = [r for r in m["refs"] if r in facts["signals"]]
    topics = list(dict.fromkeys(facts["events"][r]["topic"] for r in ev))
    what = "、".join(x for x in ((f"{len(topics)} 個 Topic 的事件" if ev else ""), (f"{len(logs)} 則 WARN 以上的 Log" if logs else "")) if x)
    return {"refs": m["refs"][:10], "text": f"同一時間 {what}（程式列出）", "program": True}


def _fallback_highlights(facts):
    """Synthesizer 沒有給出可用的重點：程式依事實列出——一個重要的時間點一則（引用那個時間點的編號，內容由 _render_note 列在下面），
    再加反覆切換的 Topic 各一則。"""
    moments, flap = _moments(facts)
    out = [_moment_note(m, facts) for m in moments[:_HIGHLIGHTS_HARD]]
    for r in flap:
        out.append({"refs": [r["id"]], "text": f"{r['topic']} 反覆切換 {r['flap']} 次（程式依事實列出）"})
    return out


def _worker_subtask(job, text):
    """交給 worker 的子任務：L#（Log 訊號的編號）換成它出現的時間（+秒）。worker 看不到 Log，L# 對它沒有意義，
    還會讓它在說明裡引用 Log、寫「證實 L17 時…」（實測 26b：子任務引用 L# 38/40、局部報告引用 L# 29/40）。"""
    base = job["index"]["start_ns"]
    sig = {str(s["id"]).upper(): s for s in job.get("signals") or []}

    def when(sid):
        s = sig.get(f"L{sid}")
        if not s:
            return None
        times = (s.get("times_sec") or [s.get("first_sec")])[:2]
        return "、".join(_rel(int(round(float(t) * 1e9)), base) for t in times if t is not None) or None

    # 「L17 (+21.76s)」「L17（+21.76s）」：模型自己寫了時間，留時間就好
    text = re.sub(r"(?<![A-Za-z0-9_])L(\d+)\s*[（(]\s*([+＋-]?\d+(?:\.\d+)?\s*s?)\s*[)）]",
                  lambda m: m.group(2) if sig.get(f"L{m.group(1)}") else m.group(0), text or "")
    return _SIGNAL_REF.sub(lambda m: when(m.group(1)) or m.group(0), text)


class AnalysisWorker:
    """一個 Topic 的說明者：乾淨的 session，只看自己那個 Topic 的事實（程式量的）、訊息定義與子任務；一次模型呼叫，輸出一則一則的說明。"""

    def __init__(self, agent, job, n, assignment):
        self.a, self.job, self.n, self.asg = agent, job, n, assignment
        self.topic = assignment["topic"]
        self.facts = job["facts"]
        self.row = next(r for r in self.facts["topics"] if r["topic"] == self.topic)
        self.tag = f"W{n} {self.topic}"

    def _brief(self):
        r, facts = self.row, self.facts
        msgdef = (self.job["index"].get("msg_definitions") or {}).get(r["type"]) or ""
        evs = "\n".join(f"- {e}｜{_plus(facts['events'][e]['t'])}｜{facts['events'][e]['text']}" for e in r["events"]) or "（沒有事件）"
        parts = [f"【你的子任務】{_worker_subtask(self.job, self.asg['subtask'])}",
                 f"【你負責的 Topic】{r['id']} {self.topic}（{r['type']}）——其他 Topic 有別的 worker 負責，你只說明這一個",
                 f"【數據】整段 {self.job.get('duration_sec')} 秒（+秒＝距離數據開頭）"]
        if msgdef:
            parts.append(f"【訊息定義（錄製時存在 MCAP 裡的 .msg，含註解）】\n{_short_block(msgdef, 1800)}")
        parts.append(f"【程式量到的事實（整段數據的全部 Key；只能引用這裡的編號）】\n{r['id']}｜類別：{'、'.join(r['tags'])}｜發布：{r['publish']}"
                     + (f"\n- 變化：{'；'.join(r['changes'])}" if r["changes"] else "")
                     + (f"\n- 數值範圍：{'；'.join(r['ranges'])}" if r["ranges"] else "")
                     + (f"\n- 到最後：{'；'.join(r['end'])}" if r["end"] else "")
                     + (f"\n- 沒有變化：{'；'.join(r['still'][:8])}" if r["still"] else "")
                     + f"\n事件（編號｜時間｜內容）：\n{evs}")
        allowed = "、".join([r["id"]] + r["events"][:12]) + ("…" if len(r["events"]) > 12 else "")
        parts.append(f"【要寫的】notes：1～{_max_items(ANALYSIS_WORKER_SCHEMA, 'notes')} 則，每則說明一件事（refs＝它根據的編號：{allowed}；text＝一兩句話）。"
                     "時間由程式依編號補上，不用寫。不寫原因、不推測，也不寫跟其他 Topic、Log 的關係。")
        return "\n\n".join(parts)

    def run(self):
        a, job = self.a, self.job
        a._analysis_note(job, f"🔧 {self.tag}：{_short(self.asg['subtask'], 80)}", kind="worker", worker=self.n)
        allowed = {self.row["id"]} | set(self.row["events"])
        system, user = _read_prompt("worker.md"), self._brief()
        label = f"worker_W{self.n}"
        data = a._analysis_session(job, "analysis_worker", "worker", system, user, ANALYSIS_WORKER_SCHEMA, 1536, label=label)
        items = (data or {}).get("notes") or []
        kept, problems = _review_notes(items, allowed, self.facts)
        kept = _unique(kept)
        issues = [_problem_text(p) for p in problems]
        if problems or not kept:
            why = issues or ["沒有寫任何說明（或格式壞掉）"]
            a._analysis_note(job, f"🛠 {self.tag}：說明沒有通過程式核對，交回修正一次：{why[0][:160]}", kind="worker_step", worker=self.n)
            data2 = a._analysis_session(job, "analysis_worker", "worker", system, _retry_text(user, "notes", items, problems, why),
                                        ANALYSIS_WORKER_SCHEMA, 1536, label=label)
            kept, problems, _ = _merge_retry(kept, problems, (data2 or {}).get("notes") or [], allowed, self.facts)
        notes = sorted((_render_note(n, self.facts) for n in kept), key=lambda h: (h["t"] is None, h["t"] or 0))
        result = {"n": self.n, "topic": self.topic, "tid": self.row["id"], "type": self.row["type"], "subtask": self.asg["subtask"],
                  "status": "done", "tags": self.row["tags"], "notes": notes}
        if issues:
            result["issues"] = issues
        if problems:
            result["dropped"] = [_problem_text(p) for p in problems]
        if self.asg.get("round"):   # 補派的 worker：第幾輪、為了哪一則 Log
            result["round"], result["signal"] = self.asg["round"], self.asg.get("signal")
        result["file"] = self._write(result)
        a._analysis_note(job, f"✅ {self.tag}：{len(notes)} 則說明（{'、'.join(self.row['tags'])}）"
                              + (f"；{len(result['dropped'])} 則沒有通過核對" if result.get("dropped") else ""),
                         kind="worker_done", worker=self.n)
        return result

    def _write(self, result):
        idx = self.job["index"]
        fm = {"artifact": "worker_notes", "job": self.job["id"], "worker": self.n, "topic": self.topic, "tid": result["tid"],
              "message_type": result["type"], "time_range": [_sec3(idx["start_ns"]), _sec3(idx["end_ns"])], "tags": result["tags"],
              "events": self.row["events"], "model": self.a.analysis_model("worker"), "notes": result["notes"]}
        for k in ("round", "signal", "issues", "dropped"):
            if result.get(k):
                fm[k] = result[k]
        body = f"## 子任務\n{result['subtask']}\n\n## 說明\n" + ("\n".join(_note_line(h) for h in result["notes"]) or "（沒有）") + "\n"
        rel = f"workers/W{self.n}_{_slug(self.topic)}.md"
        self.a._job_write(self.job, rel, frontmatter(fm) + "\n" + body)
        return rel


def _short_block(text, n):
    """多行文字截短（保留換行）。"""
    text = str(text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------- 事實（程式整理，不經過模型）
def _path(name, it, base, limit=3):
    """一個項目的變化：「mode：NORMAL → LIMITED（+21.76s）→ NORMAL（+30.10s）」；超過 limit 次只列前幾次與總次數。"""
    chs = it.get("changes") or []
    s = f"{name}：{_val(chs[0]['from'] if chs else it.get('first'))}"
    for c in chs[:limit]:
        s += f" → {_val(c['to'])}（{_plus(float(c['t']) - base)}）"
    n = it.get("count") or len(chs)
    return s + (f" …（共 {n} 次）" if n > limit else "")


def _topic_entry(topic, meta, entry, base):
    """一個 Topic 的量測結果（mcap_analyzer --facts 的一項）→ (列, 事件清單)。base＝數據開頭（epoch 秒）。
    列：類別（tags）、發布方式與則數、變化、數值範圍、到最後的值、沒有變化的項目。事件：{"t": +秒, "topic", "kind", "text"}——
    開始／停止發布、中斷與恢復（固定頻率的 Topic 才有）、第一則在中途、一則訊息（不是固定頻率、沒有狀態的 Topic）、
    同一則訊息裡的變化（狀態跳轉、數值切換，同一個時間的合成一個事件）、尖峰。"""
    rate, items = entry.get("rate") or {}, entry.get("items") or []
    row = {"topic": topic, "type": meta.get("type"), "pattern": rate.get("pattern"), "tags": [], "publish": "", "changes": [],
           "ranges": [], "end": [], "still": [], "events": []}
    evs, tags = [], []

    def ev(t_epoch, kind, text):
        if t_epoch is not None:
            evs.append({"t": round(float(t_epoch) - base, 3), "topic": topic, "kind": kind, "text": text})

    n = rate.get("messages") or 0
    pattern = rate.get("pattern")
    has_state = any(it["kind"] == "state" or it.get("changes") for it in items)
    if not n:
        tags.append("沒有訊息")
        row["publish"] = "整段沒有訊息"
    elif pattern == "periodic":
        first, last = rate["first_sec"], rate["last_sec"]
        head = f"{n} 則，固定頻率（週期 {_val(rate.get('period_sec'))} 秒）"
        parts = []
        if rate.get("single_session"):
            parts.append(f"只在 {_plus(first - base)}～{_plus(last - base)} 連續發布（一段完整的發布，中間沒有中斷）")
            ev(first, "start", "開始發布（之前沒有訊息）")
            ev(last, "stop", "停止發布（之後到數據結束沒有訊息）")
        else:
            if rate.get("started_late"):
                parts.append(f"{_plus(first - base)} 才開始發布")
                ev(first, "start", "開始發布（之前沒有訊息）")
            elif rate.get("warmup_start"):
                parts.append(f"第一則在 {_plus(first - base)}（錄製剛開始）")
            if rate.get("stopped_early"):
                parts.append(f"{_plus(last - base)} 之後停止發布（到數據結束沒有訊息）")
                ev(last, "stop", "停止發布（之後到數據結束沒有訊息）")
        gaps = rate.get("gaps") or []
        for g in gaps:
            s, d = float(g["start_sec"]), float(g.get("duration_sec") or 0)
            ev(s, "gap", f"訊息中斷 {d:.2f} 秒（之後 {_plus(s + d - base)} 恢復）")
            ev(s + d, "resume", f"恢復發布（中斷 {d:.2f} 秒之後的第一則）")
        if gaps:
            parts.append(f"訊息中斷 {rate.get('gap_count') or len(gaps)} 次（最長 {max(float(g.get('duration_sec') or 0) for g in gaps):.2f} 秒）")
            tags.append("訊息中斷")
        if rate.get("single_session") or rate.get("started_late") or rate.get("stopped_early"):
            tags.append("開始或停止發布")
        row["publish"] = head + "；" + "；".join(parts) if parts else f"整段持續發布（{head}）"
    else:
        first = rate["first_sec"]
        label = {"on_change": "狀態改變時才發布", "irregular": "不定期發布", "few": "只有"}.get(pattern, "發布")
        times = rate.get("times_sec") or []
        when = "、".join(_plus(float(t) - base) for t in times[:10]) + ("…" if len(times) > 10 else "") if times else \
            f"{_plus(first - base)}～{_plus(rate['last_sec'] - base)}"
        row["publish"] = f"{label}：{n} 則（{when}）" + ("；不是固定頻率，不判斷中斷與開始／停止發布" if pattern != "few" else "")
        if rate.get("late_first"):
            tags.append("第一則在中途")
            firsts = [f"{it['name']}＝{_val(it.get('first'), 40)}" for it in items if it["kind"] == "state"][:3]
            ev(first, "first", "第一則訊息" + (f"（{'、'.join(firsts)}）" if firsts else ""))
        if not has_state and len(times) > 1:
            for t in times[1:]:
                ev(t, "message", "一則訊息")
    if meta.get("role") == "text_only":
        row["still"].append("只有文字欄位（內容不量測）")
    change_at = {}
    for it in items:
        name, kind = it["name"], it["kind"]
        if kind == "state":
            if it.get("count"):
                tags.append("狀態改變")
                for c in it.get("changes") or []:
                    change_at.setdefault(c["t"], []).append(f"{name}：{_val(c['from'], 40)} → {_val(c['to'], 40)}")
                row["changes"].append(_path(name, it, base))
                row["end"].append(f"{name}＝{_val(it.get('last'))}" + (f"（開頭 {_val(it.get('first'))}）" if it.get("last") != it.get("first")
                                                                       else "（跟開頭一樣）"))
            else:
                row["still"].append(f"{name}＝{_val(it.get('first'))}")
        elif kind == "numeric":
            if it.get("constant"):
                row["still"].append(f"{name}＝{_val(it.get('first'))}")
            elif it.get("changes"):
                tags.append("數值切換")
                for c in it["changes"]:
                    change_at.setdefault(c["t"], []).append(f"{name}：{_val(c['from'])} → {_val(c['to'])}")
                row["changes"].append(_path(name, it, base))
                row["end"].append(f"{name}＝{_val(it.get('last'))}" + (f"（開頭 {_val(it.get('first'))}）" if it.get("last") != it.get("first")
                                                                       else "（跟開頭一樣）"))
            else:   # 連續變動的數值（沒有切換、只看得到範圍）：不列成時間線的事件
                tags.append("數值變動")
                row["ranges"].append(f"{name}：{_val(it.get('first'))} → {_val(it.get('last'))}（最小 {_val(it.get('min'))}＠"
                                     f"{_plus(float(it['min_t']) - base)}、最大 {_val(it.get('max'))}＠{_plus(float(it['max_t']) - base)}，"
                                     f"平均 {_val(it.get('mean'))}）")
            if it.get("spike_count"):
                tags.append("尖峰")
                sp = it.get("spikes") or []
                for k, s in enumerate(sp[:3]):
                    ev(s["t"], "spike", f"{name} 尖峰 {_val(s['value'])}（前後約 {_val(s.get('baseline'))}）"
                       + (f"（共 {it['spike_count']} 個）" if k == 0 and it["spike_count"] > 3 else ""))
                if sp:
                    row["changes"].append(f"{name} 尖峰 {it['spike_count']} 個（第一個 {_plus(float(sp[0]['t']) - base)}＝{_val(sp[0]['value'])}）")
        elif kind == "array":
            lo, hi = it.get("length_min"), it.get("length_max")
            if lo is not None and lo != hi:
                row["ranges"].append(f"{name} 長度 {lo}～{hi}")
            elif lo is not None:
                row["still"].append(f"{name} 長度 {lo}")
            em = it.get("element_mean")
            if em and not em.get("constant"):
                tags.append("數值變動")
                row["ranges"].append(f"{name} 元素平均：{_val(em.get('first'))} → {_val(em.get('last'))}（最小 {_val(em.get('min'))}、"
                                     f"最大 {_val(em.get('max'))}）")
    for key, q in (entry.get("quiet") or {}).items():
        row["still"].append(f"{key}：{q['count']} 項沒有變化（{q['values']}）")
    for t, texts in change_at.items():   # 同一則訊息裡改變的項目全部列（事實要完整；給模型看的地方另外截短）
        ev(t, "change", "；".join(texts))
    row["tags"] = list(dict.fromkeys(tags)) or ["沒有變化"]
    return row, evs


def _log_events(job, base):
    """時間線上的 Log（錄製工具自己的除外）：出現 3 次以內的每一次；更多次的只取第一次與最後一次（中間是反覆印的同一句）。"""
    out = []
    for s in job.get("signals") or []:
        if is_recorder_node(s.get("node", "")) or s.get("first_sec") is None:
            continue
        n = s.get("count") or 1
        if n > 3 and s.get("last_sec") is not None:
            occ = [(float(s["first_sec"]), f"第一次，共 {n} 次"), (float(s["last_sec"]), f"最後一次，共 {n} 次")]
        else:
            occ = [(float(t), "") for t in (s.get("times_sec") or [s["first_sec"]])[:3] if t is not None]
        for t, note in occ:
            out.append({"t": round(t - base, 3), "id": s["id"], "level": s.get("level"), "node": s.get("node"), "text": s.get("message"),
                        "note": note, "where": _signal_source(s)})
    return out


def _dt(dt):
    return "同時" if abs(dt) < 0.005 else (f"晚 {dt:.2f} 秒" if dt > 0 else f"早 {-dt:.2f} 秒")


def _near_text(near, key, label, empty, limit=4):
    """對照到的事件 → 「L15（晚 0.55 秒）、L16（同時）」：同一個來源只留最近的一次；超過 limit 個只列最近的幾個與總數
    （實測 lifecycle 重啟時 13 則 Log 擠在 0.03 秒內，每一列都列 13 則）。"""
    best = {}
    for x, dt in near:
        k = x[key]
        if k not in best or abs(dt) < abs(best[k][1]):
            best[k] = (x, dt)
    items = sorted(best.values(), key=lambda p: p[0]["t"])
    if len(items) > limit:
        keep = {id(p[0]) for p in sorted(items, key=lambda p: abs(p[1]))[:limit - 1]}
        return "、".join(f"{label(x)}（{_dt(dt)}）" for x, dt in items if id(x) in keep) + f"…共 {len(items)} 個"
    return "、".join(f"{label(x)}（{_dt(dt)}）" for x, dt in items) or empty


def build_facts(job):
    """事實（程式整理，不經過模型）：mcap_analyzer --facts 量的全部 Topic ＋ 去重後的 Log →
    - topics：每個 Topic 一列（T#：類別、發布、變化、數值範圍、到最後的值、沒有變化的項目、它的事件編號）。順序：有事件的依第一個事件的
      時間、只有數值連續變動的、沒有變化的、沒有訊息的；
    - events：{E#: 事件}，依時間編號（同一個 Topic 反覆切換的只編前 _FLAP_KEEP[0] 個與最後 _FLAP_KEEP[1] 個）；
    - signals：{L#: Log 訊號（每一次出現的時間）}；logs：時間線上的 Log；
    - timeline：Topic 的事件與 Log 依時間排序，每一列附前後 ANALYSIS_ALIGN_SEC 秒內對照到的 Log（或 Topic 的事件）；Log 列出 WARN 以上、
      規劃時挑的、跟 Topic 的事件對得上的；
    - same_time：ANALYSIS_SAME_TIME_SEC 秒內不同 Topic 一起變化；unmatched_logs：WARN 以上或規劃時挑的 Log，每一次出現的前後都沒有任何
      Topic 的事件；unreadable：沒有訊息、無法解碼、框架的 Topic；overview：一句話的總覽；quoted：Log 原文與量到的字串（核對用詞時照抄的不算）。"""
    idx, scan = job["index"], job.get("scan") or {"topics": {}}
    base = idx["start_ns"] / 1e9
    rows, evs, unreadable = [], [], {}
    for meta in idx["topics"]:
        t, role = meta["topic"], meta.get("role")
        if role == "log":
            continue
        if role in ("empty", "undecodable"):
            unreadable.setdefault({"empty": "沒有訊息", "undecodable": "無法解碼"}[role], []).append(t)
            continue
        if t in _FRAMEWORK_TOPICS:
            unreadable.setdefault("ROS 2 框架的 Topic（不列事件）", []).append(t)
            continue
        entry = (scan.get("topics") or {}).get(t)
        if entry is None:
            unreadable.setdefault("沒有量到", []).append(t)
            continue
        row, e = _topic_entry(t, meta, entry, base)
        rows.append(row)
        evs += e
    # 同一個 Topic 的變化事件太多（反覆切換）：只留頭尾
    flapped = {}
    for t in {e["topic"] for e in evs}:
        ch = sorted((e for e in evs if e["topic"] == t and e["kind"] == "change"), key=lambda e: e["t"])
        if len(ch) > sum(_FLAP_KEEP):
            drop = ch[_FLAP_KEEP[0]:-_FLAP_KEEP[1]]
            flapped[t] = (len(ch), len(drop))
            ids = {id(e) for e in drop}
            evs = [e for e in evs if id(e) not in ids]
    evs.sort(key=lambda e: (e["t"], e["topic"], _EVENT_ORDER.get(e["kind"], 9)))
    events = {}
    for i, e in enumerate(evs, 1):
        e["id"] = f"E{i}"
        events[e["id"]] = e
    first_t = {}
    for e in evs:
        first_t.setdefault(e["topic"], e["t"])
    group = lambda r: (0 if r["topic"] in first_t else 1 if "數值變動" in r["tags"] else 3 if "沒有訊息" in r["tags"] else 2)  # noqa: E731
    rows.sort(key=lambda r: (group(r), first_t.get(r["topic"], 0), r["topic"]))
    tid = {}
    for i, r in enumerate(rows, 1):
        r["id"] = f"T{i}"
        tid[r["topic"]] = r["id"]
        r["events"] = [e["id"] for e in evs if e["topic"] == r["topic"]]
        if r["topic"] in flapped:
            total, hidden = flapped[r["topic"]]
            r["flap"] = total
            r["changes"].append(f"（變化共 {total} 次：時間線只列前 {_FLAP_KEEP[0]} 次與最後 {_FLAP_KEEP[1]} 次）")
    for e in evs:
        e["tid"] = tid[e["topic"]]
    related = {r["id"] for r in (job.get("plan") or {}).get("related") or []}
    logs = _log_events(job, base)
    for e in evs:
        e["near"] = [(x, x["t"] - e["t"]) for x in logs if abs(x["t"] - e["t"]) <= ANALYSIS_ALIGN_SEC]
    for x in logs:
        x["near"] = [(e, e["t"] - x["t"]) for e in evs if abs(e["t"] - x["t"]) <= ANALYSIS_ALIGN_SEC]
        x["key"] = _LEVEL_RANK.get(x["level"], 1) >= 2 or x["id"] in related
    timeline = [{"ref": e["id"], "t": e["t"], "time": _plus(e["t"]), "source": f"{e['tid']} {e['topic']}", "event": e["text"],
                 "rank": _EVENT_RANK.get(e["kind"], 5), "near": _near_text(e["near"], "id", lambda x: x["id"], "沒有對應的 Log")}
                for e in evs]
    for x in logs:
        if not (x["key"] or x["near"]):
            continue
        rank = 0 if _LEVEL_RANK.get(x["level"], 1) >= 2 else (1 if x["id"] in related else 5)
        timeline.append({"ref": x["id"], "t": x["t"], "time": _plus(x["t"]), "source": f"{x['id']} {x['level']} {x['node']}", "rank": rank,
                         "event": _short(x["text"], 200) + (f"（{x['note']}）" if x["note"] else "") + x["where"],
                         "near": _near_text(x["near"], "id", lambda e: f"{e['id']} {e['topic']}", "沒有任何 Topic 的事件")})
    timeline.sort(key=lambda r: (r["t"], r["ref"][0] != "L", int(r["ref"][1:])))
    lonely = {}
    for x in logs:
        if x["key"]:
            d = lonely.setdefault(x["id"], dict({k: x[k] for k in ("id", "level", "node", "text", "where", "t")}, matched=False))
            d["matched"] = d["matched"] or bool(x["near"])
    groups, cur = [], []
    for e in evs + [None]:
        if e is not None and cur and e["t"] - cur[0]["t"] <= ANALYSIS_SAME_TIME_SEC:
            cur.append(e)
            continue
        if len({x["topic"] for x in cur}) >= 2:
            groups.append({"time": _plus(cur[0]["t"]) + (f"～{_plus(cur[-1]['t'])}" if cur[-1]["t"] > cur[0]["t"] else ""),
                           "events": [f"{x['id']} {x['topic']}（{_short(x['text'], 60)}）" for x in cur]})
        cur = [e] if e is not None else []
    signals = {}
    for s in job.get("signals") or []:
        if is_recorder_node(s.get("node", "")):
            continue
        signals[s["id"]] = {"level": s.get("level"), "node": s.get("node"), "text": s.get("message") or "", "count": s.get("count") or 1,
                            "times": [round(float(t) - base, 3) for t in (s.get("times_sec") or [s.get("first_sec")]) if t is not None]}
    quoted = " ".join(s["text"] for s in signals.values()) + " " + json.dumps(
        [[it.get("first"), it.get("last"), [(c.get("from"), c.get("to")) for c in it.get("changes") or []]]
         for e in (scan.get("topics") or {}).values() for it in e.get("items") or [] if it["kind"] == "state"], ensure_ascii=False)
    facts = {"topics": rows, "events": {k: {kk: v[kk] for kk in ("id", "t", "topic", "tid", "kind", "text")} for k, v in events.items()},
             "signals": signals, "logs": [{k: x[k] for k in ("id", "t", "level", "node", "text", "note", "where")} for x in logs],
             "timeline": timeline, "same_time": groups,
             "unmatched_logs": [{k: v for k, v in d.items() if k != "matched"} for d in lonely.values() if not d["matched"]],
             "unreadable": unreadable, "quoted": quoted}
    facts["overview"] = _overview(job, facts)
    return facts


def _overview(job, facts):
    """一句話的總覽（程式）：Topic 數、有事件的、只有數值連續變動的、沒有變化的；Log 的訊號數；前後沒有任何變化的 Log。"""
    rows = facts["topics"]
    busy = [r for r in rows if r["events"]]
    cont = [r for r in rows if not r["events"] and "數值變動" in r["tags"]]
    still = [r for r in rows if not r["events"] and "數值變動" not in r["tags"] and "沒有訊息" not in r["tags"]]
    counts = {}
    for r in busy:
        for t in r["tags"]:
            if t in _EVENT_TAGS:
                counts[t] = counts.get(t, 0) + 1
    tag_text = "、".join(f"{t} {c}" for t, c in counts.items())
    warn = sum(1 for s in facts["signals"].values() if _LEVEL_RANK.get(s["level"], 1) >= 2)
    other = sum(len(v) for v in facts["unreadable"].values())
    return (f"{len(rows)} 個 Topic：有事件的 {len(busy)} 個" + (f"（{tag_text}）" if tag_text else "")
            + f"、只有數值連續變動的 {len(cont)} 個、沒有變化的 {len(still)} 個" + (f"、沒有量的 {other} 個" if other else "")
            + f"；Log {len(facts['signals'])} 個訊號（WARN 以上 {warn} 個）"
            + (f"；前後 {ANALYSIS_ALIGN_SEC:g} 秒內沒有任何 Topic 變化的 Log：{'、'.join(x['id'] for x in facts['unmatched_logs'])}"
               if facts["unmatched_logs"] else ""))


def _facts_overview(facts):
    """全部 Topic 的事實總表（給 Orchestrator、topic_metadata.md）：每個 Topic 一行。"""
    lines = []
    for r in facts["topics"]:
        if r["events"]:
            items = [c.split("：")[0] for c in r["changes"] if not c.startswith("（")]
            ts = [facts["events"][e]["t"] for e in r["events"]]
            lines.append(f"- {r['id']} {r['topic']}｜{r['type']}｜{'、'.join(r['tags'])}｜{_short(r['publish'], 90)}"
                         + (f"｜變化：{'、'.join(items[:6])}" if items else "")
                         + f"｜事件 {len(ts)} 個（{_plus(min(ts))}～{_plus(max(ts))}）")
        elif "數值變動" in r["tags"]:
            names = [x.split("：")[0] for x in r["ranges"]]
            lines.append(f"- {r['id']} {r['topic']}｜{r['type']}｜數值變動（{'、'.join(names[:6])}{'…' if len(names) > 6 else ''}）｜"
                         f"{_short(r['publish'], 60)}")
        else:
            lines.append(f"- {r['id']} {r['topic']}｜{r['type']}｜{'、'.join(r['tags'])}｜{_short(r['publish'], 60)}")
    for k, v in facts["unreadable"].items():
        lines.append(f"（{k}：{'、'.join(v)}）")
    return "\n".join(lines) or "（沒有 Topic）"


def _top_rows(rows, n):
    """時間線的重點 n 列（依重要性挑，再照時間排）：交給主對話、Synthesizer 用。"""
    if len(rows) <= n:
        return rows
    keep = sorted(range(len(rows)), key=lambda i: (rows[i]["rank"], rows[i]["t"]))[:n]
    return [rows[i] for i in sorted(keep)]


def _report_data(job, facts, summary):
    """job.json 的 report（回歸評分與 Web 面板讀）：總覽、重點、各 Topic、時間線…，只留純資料。summary＝重點的文字（模型寫的部分，評分用）。"""
    return {"overview": facts["overview"], "highlights": summary["highlights"], "dropped": summary["dropped"],
            "fallback": summary.get("fallback", False), "summary": "\n".join(h["text"] for h in summary["highlights"]),
            "topics": [{k: r[k] for k in ("id", "topic", "type", "pattern", "tags", "publish", "changes", "ranges", "end", "still", "events")}
                       for r in facts["topics"]],
            "timeline": [{k: r[k] for k in ("ref", "time", "source", "event", "near")} for r in facts["timeline"]],
            "same_time": facts["same_time"], "unmatched_logs": facts["unmatched_logs"], "unreadable": facts["unreadable"],
            "notes": {w["topic"]: w.get("notes") or [] for w in job["workers"]}}


# ---------------------------------------------------------------- Synthesizer 與 Orchestrator 檢查的輸入
def _summary_user(job, facts, cap=None):
    """Synthesizer 的輸入：程式整理的事實（總覽、Topic 的一行摘要、時間線）、Orchestrator 挑的相關 Log（只有編號）、各 worker 的說明。
    不給使用者的問題與 Orchestrator 的理解（推測的原因不進事實那一層）。每個項目的變化都在時間線的事件裡，Topic 那一行只寫類別、
    事件編號與到最後的值（實測 178 秒、25 個 Topic 的數據，連變化一起列時輸入 40 KB、每次 30 秒以上）；完整的在報告。"""
    rows = facts["timeline"]
    shown = _top_rows(rows, _TIMELINE_MAX)
    tl = "\n".join(f"- {r['ref'] or '-'}｜{r['time']}｜{r['source']}｜{_short(r['event'], 110)}｜前後 {ANALYSIS_ALIGN_SEC:g} 秒內：{_short(r['near'], 90)}"
                   for r in shown)
    busy = [r for r in facts["topics"] if r["events"] or "數值變動" in r["tags"]]
    quiet = [f"{r['id']} {r['topic']}" for r in facts["topics"] if not (r["events"] or "數值變動" in r["tags"])]
    lines = [f"- {r['id']} {r['topic']}｜{'、'.join(r['tags'])}｜{_short(r['publish'], 70)}"
             + (f"｜事件：{'、'.join(r['events'][:10])}{'…' if len(r['events']) > 10 else ''}" if r["events"] else "")
             + (f"｜到最後：{'；'.join(_short(x, 60) for x in r['end'][:3])}" if r["end"] else "") for r in busy]
    notes = "\n".join(f"- W{w['n']} {w.get('tid') or ''} {w['topic']}：\n" + "\n".join(f"  - [{', '.join(h['refs'])}] {h['text']}" for h in w["notes"])
                      for w in job["workers"] if w.get("notes"))
    related = "、".join(r["id"] for r in job["plan"]["related"]) or "（沒有）"
    moments, flap = _moments(facts)
    mlist = "\n".join(f"- {_moment_text(m)}" for m in moments) or "（沒有）"
    flist = "、".join(f"{r['id']} {r['topic']}（變化 {r['flap']} 次）" for r in flap)
    return (f"【數據】{job.get('data_label')}：共 {job.get('duration_sec')} 秒（時間是距離數據開頭的秒數，+秒）\n\n"
            f"【總覽（程式）】{facts['overview']}\n\n"
            f"【有變化的 Topic（程式量測整段數據；T# 是 Topic 的編號）】\n{chr(10).join(lines) or '（沒有）'}\n\n"
            f"【沒有變化的 Topic】{'、'.join(quiet) or '（沒有）'}\n\n"
            f"【時間線（程式整理：E#＝Topic 的事件、L#＝Log 訊號；「前後 {ANALYSIS_ALIGN_SEC:g} 秒內」只是時間上的對照，不代表誰造成誰）】\n"
            f"{tl or '（沒有量到任何事件）'}"
            + (f"\n（另有 {len(rows) - len(shown)} 列沒有列出：多半是 INFO 的 Log 或同一個項目反覆切換）" if len(rows) > len(shown) else "")
            + f"\n\n【重要的時間點（程式算的：事件與 WARN 以上的 Log，1 秒內的算一個；每個時間點至少一則重點，refs 引用其中的編號）】\n{mlist}"
            + (f"\n【反覆切換的 Topic（可以一則帶過，不用逐次寫）】{flist}" if flist else "")
            + f"\n\n【Orchestrator 挑的相關 Log】{related}"
            + (f"\n\n【Workers 的說明（refs 是它們根據的編號）】\n{notes}" if notes else "")
            + f"\n\n（highlights：依時間一則一則寫重點，最多 {cap or _max_items(ANALYSIS_SUMMARY_SCHEMA, 'highlights')} 則"
              f"（重要的時間點 {len(moments)} 個：每個時間點一則，再加到最後的值、沒有變化的 Topic；事件少就少寫）；每則 refs 指到上面的編號、"
              "text 一兩句話，寫這一刻的重點：引用的事件的完整內容與每則 Log，程式會列在這一則下面，數值與 Log 不用逐項抄"
              "（同一時間好幾個 Topic 改變時寫最重要的變化，其他的編號放在 refs；好幾則 Log 寫則數與層級）；"
              "時間由程式依編號補上。只寫事實：不寫原因、不寫誰造成誰、不推測；繁體中文）")


def _max_items(schema, field):
    """格式上的則數上限（交給模型的說明照格式寫，兩邊不會不一致）。"""
    return schema["properties"][field]["maxItems"]


def _with_max_items(schema, field, n):
    """同一個格式、這一次的則數上限換成 n（不改共用的格式）。"""
    out = json.loads(json.dumps(schema))
    out["properties"][field]["maxItems"] = n
    return out


def _moments(facts):
    """重要的時間點（程式算的，給 Synthesizer 當清單、也拿來核對有沒有漏寫）→ ([{id, t0, t1, refs}], 反覆切換的 Topic 列)：
    Topic 的事件（開始／停止發布、中斷、恢復、狀態或數值的變化、第一則在中途）與 WARN 以上的 Log，依時間排，跟前一個差不到
    ANALYSIS_ALIGN_SEC 秒的算同一個時間點。只有反覆切換的 Topic 的事件的時間點不算（例如計數在 299／300 之間跳，總是單獨出現；
    它整個可以一則帶過，不強制寫）；反覆切換的 Topic 跟別的事件、Log 同時變的照算（實測安全閘一份錄製切換 10 多次，ESTOP_LATCHED
    那一次跟 ERROR Log 同時，不能不算）。"""
    flap = [r for r in facts["topics"] if r.get("flap")]
    noisy = {r["topic"] for r in flap}
    pts = sorted([(e["t"], e["id"]) for e in facts["events"].values() if e["kind"] in _MOMENT_KINDS]
                 + [(x["t"], x["id"]) for x in facts["logs"] if _LEVEL_RANK.get(x["level"], 1) >= 2])
    groups, last = [], None
    for t, ref in pts:
        if last is None or t - last > ANALYSIS_ALIGN_SEC:
            groups.append({"t0": t, "t1": t, "refs": []})
        groups[-1]["t1"] = t
        if ref not in groups[-1]["refs"]:
            groups[-1]["refs"].append(ref)
        last = t
    keep = [g for g in groups if not all(r in facts["events"] and facts["events"][r]["topic"] in noisy for r in g["refs"])]
    return [dict(g, id=f"M{i}") for i, g in enumerate(keep, 1)], flap


def _key_moments(facts):
    """重要的時間點有幾個（反覆切換的 Topic 不算）。"""
    return len(_moments(facts)[0])


def _attach_moments(notes, moments, facts):
    """每個重要的時間點，由第一則（依時間）引用到它的重點掛上那一刻其他的事件與 Log（also）：那一刻的事實由程式列全，模型寫重點。
    實測模型常只引用一刻裡的幾個編號（同一刻安全閘鎖定的事件沒引用，那一則下面就看不到）。"""
    def first_t(n):
        ts = [facts["events"][r]["t"] for r in n["refs"] if r in facts["events"]] + \
             [t for r in n["refs"] if r in facts["signals"] for t in facts["signals"][r]["times"][:1]]
        return min(ts) if ts else float("inf")
    order = sorted(range(len(notes)), key=lambda i: first_t(notes[i]))
    shown = {r for n in notes for r in n["refs"]}
    out = [dict(n) for n in notes]
    for m in moments:
        i = next((i for i in order if set(out[i]["refs"]) & set(m["refs"])), None)
        if i is None:
            continue
        extra = [r for r in m["refs"] if r not in shown]
        if extra:
            out[i]["also"] = out[i].get("also", []) + extra
            shown.update(extra)
    return out


def _missing_moments(moments, notes):
    """沒有任何一則引用到的時間點（一則引用了那個時間點的任何一個編號就算寫到了）。"""
    cited = {r for n in notes for r in n["refs"]}
    return [m for m in moments if not cited & set(m["refs"])]


def _moment_text(m, n=8):
    return f"{m['id']} {_plus(m['t0'])}" + (f"～{_plus(m['t1'])}" if m["t1"] - m["t0"] >= 0.005 else "") + \
        f"：{'、'.join(m['refs'][:n])}{'…' if len(m['refs']) > n else ''}"


def _highlight_cap(facts):
    """重點的則數上限：重要的時間點與反覆切換的 Topic 各一則，加上到最後的值、沒有變化的 Topic 各一則；至少是格式的預設
    （事件少時照舊），最多 _HIGHLIGHTS_HARD（防失控）。"""
    moments, flap = _moments(facts)
    return max(_max_items(ANALYSIS_SUMMARY_SCHEMA, "highlights"), min(_HIGHLIGHTS_HARD, len(moments) + len(flap) + 2))


def _check_user(job, facts, summary, cands):
    """Orchestrator 檢查的輸入：問題、規劃時挑的 Log、重點、還沒有說明而且在相關的 Log 前後有變化的 Topic（附它的事件與前後的 Log）。"""
    rel = "\n".join(f"- {r['id']}：{r['why']}" for r in job["plan"]["related"]) or "（沒有）"
    hl = "\n".join(f"- {h['time'] or '整段'}　{h['text']}（{'、'.join(h['refs'])}）" for h in summary["highlights"]) or "（沒有）"
    sig = facts["signals"]
    cand = "\n".join(f"- {c['tid']} {c['topic']}｜前後的 Log：" + "、".join(f"{s} {sig[s]['level']} {_short(sig[s]['text'], 60)}" for s in c["near"])
                     + "\n" + "\n".join(f"  - {e}" for e in c["events"]) for c in cands)
    explained = "、".join(f"W{w['n']} {w['topic']}" for w in job["workers"]) or "（沒有）"
    return (f"【使用者的問題】\n{job['question']}\n\n【數據】{job.get('data_label')}：共 {job.get('duration_sec')} 秒（+秒＝距離數據開頭）\n\n"
            f"【你規劃時挑的相關 Log】\n{rel}\n\n【已經有 worker 說明的 Topic】{explained}\n\n【目前的重點（Synthesizer）】\n{hl}\n\n"
            f"【在 WARN 以上或相關的 Log 前後 {ANALYSIS_ALIGN_SEC:g} 秒內有變化、還沒有說明的 Topic（程式量的事實）】\n{cand}\n\n"
            f"【要決定的】這些 Topic 要不要補派 worker 說明（最多 {ANALYSIS_FOLLOWUP_WORKERS} 個；topic＝名稱或 T#，signal＝它前後的 L#，"
            "subtask＝要說明哪些變化）；不需要就給空陣列。事實都已經量好了，補派只是多一份說明。只決定要不要補派，不寫原因。"
            "（每個欄位都用繁體中文寫）")
