"""AnalysisMixin：數據解析的多 agent 協同——analysis_run 偽技能（同 ops_run、result_recall：要呼叫模型，在 harness 的 process 裡做）。

ROS 2／MCAP 智慧診斷的 Orchestrator → Workers → Synthesizer（Map-Reduce），在主對話的回合裡同步執行：
0. 資料預備（程式，按需處理）：rosout_parser --json 把 Log 去重成唯一訊號（L#：層級、Node、次數、每一次的時間戳）；
   mcap_analyzer --json 讀全域 Topic Metadata（錄製時建好的索引直接讀快取，沒有就建一次）。
1. Orchestrator（format=ANALYSIS_PLAN_SCHEMA）：同時看「去重後的 Log」與「全域 Topic Metadata」：寫對問題的理解、挑出相關的
   Log 訊號、時間窗前後幾秒，把不同的 Topic 指派給不同的 worker（廣度優先）。程式檢查：訊號編號要存在、Topic 要存在而且可分析、
   同一個 Topic 只給一個 worker、最多 N 個；有問題把具體的問題交回修一次，還是不行由程式依關聯度補指派。精確的時間窗由程式依訊號的
   時間戳算（前後秒數、重疊的合併、限制在數據範圍內），模型只填訊號編號、不必抄 19 位數的時間。String／Log 只有 Orchestrator 看。
2. Workers（AnalysisWorker：每個一個乾淨的 session，可以平行）：只看得到自己的 Topic、時間窗、Key 目錄與子任務（不給 Log 字串）；
   用 mcap_feature_measure 自己決定量哪些 Key（數據、Topic、時間窗由系統帶入）；做完寫局部報告（format=ANALYSIS_WORKER_REPORT_SCHEMA）。
   程式再用 --json 把分析過的 Key 量一次，數字填進 Frontmatter（key_metrics、program_flags）——模型只寫判斷與說明。
3. Synthesizer（format=ANALYSIS_REPORT_SCHEMA）：拿 Orchestrator 的 Log 視角＋全部局部報告做因果拼圖，寫根因診斷報告
   （結論、根因、時間線、證據、尚未確認、建議），也是 Frontmatter Markdown。

全部產物在 logs/analysis_jobs/<編號>/：job.json、events.jsonl、log_digest.md、topic_metadata.md、plan.json、
workers/W<n>_<topic>.md（局部報告）與 .transcript.md（worker 的完整對話）、report.md。回傳給主對話的是報告的重點（存成 #編號）。

設計依據同 ops_job：agent 之間只傳精簡、結構化的產物（ReWOO）；能由程式做的（去重、時間戳換算、數字、檢查）不交給模型；
驗證集中由程式做（MAST：驗證不足是多 agent 系統主要的失敗原因）。
"""
import json
import os
import re
import shlex
import time
from concurrent.futures import ThreadPoolExecutor

from .config import (
    ANALYSIS_AGENTS_DIRNAME,
    ANALYSIS_DATA_ROOT,
    ANALYSIS_DIGEST_MAX_SIGNALS,
    ANALYSIS_JOBS_DIRNAME,
    ANALYSIS_MAX_WINDOWS,
    ANALYSIS_MAX_WORKERS,
    ANALYSIS_ORCHESTRATOR_MODEL,
    ANALYSIS_PARALLEL_WORKERS,
    ANALYSIS_PROGRAM_HINTS,
    ANALYSIS_REPORT_HEAD,
    ANALYSIS_SETTINGS_NAME,
    ANALYSIS_SIGNAL_OCCURRENCES,
    ANALYSIS_SLICE,
    ANALYSIS_SLICES_DIRNAME,
    ANALYSIS_SOURCE_CACHE_DIRNAME,
    ANALYSIS_SOURCE_MAX_CHARS,
    ANALYSIS_SOURCE_ROOT,
    ANALYSIS_SYNTHESIZER_MODEL,
    ANALYSIS_THINK_DEFAULT,
    ANALYSIS_TOOL_RESULT_MAX_CHARS,
    ANALYSIS_WINDOW_AFTER,
    ANALYSIS_WINDOW_BEFORE,
    ANALYSIS_WORKER_MAX_STEPS,
    ANALYSIS_WORKER_MODEL,
    ANALYSIS_WORKER_SCRIPTS,
    NUM_CTX,
    PROJECT_ROOT,
    THINK_EXTRA_PREDICT,
)
from . import source_index
from .model_caps import think_arg
from .protocol import parse_agent_reply
from .schemas import (ANALYSIS_PLAN_SCHEMA, ANALYSIS_PLAN_SCHEMA_SOURCE, ANALYSIS_REPORT_SCHEMA, ANALYSIS_WORKER_REPLY_SCHEMA,
                      ANALYSIS_WORKER_REPORT_SCHEMA)

_PROMPTS = os.path.join(PROJECT_ROOT, ANALYSIS_AGENTS_DIRNAME)
ROLES = ("orchestrator", "worker", "synthesizer")
ROLE_LABELS = {"orchestrator": "Orchestrator", "worker": "Worker", "synthesizer": "Synthesizer"}
DEFAULT_QUESTION = "這段錄製期間系統發生了什麼異常或狀態變化？找出最可能的根因。"
WORKER_CATEGORIES = ("numeric", "vector", "state", "kv", "matrix", "array")
_CATEGORY_TEXT = {"numeric": "數值", "vector": "向量", "state": "狀態", "kv": "鍵值", "matrix": "矩陣", "array": "陣列",
                  "text": "文字", "time": "時間"}   # 同 _ros2_data_common.CATEGORY_LABELS（給 worker 看的 Key 目錄）
_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "UNKNOWN": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
_MARKERS = ("[ANALYSIS_DATA]", "[TARGET_CONTAINER]", "[CWD_CHANGED]", "[ROS2_WORKSPACE]")
_RECORDER_NODE = re.compile(r"^(rosbag2(_\w+)?|ros2_bag\w*)$")
# Log 裡「某個輸入沒有／逾時／遺失」的原因代碼：NO_CMD_VEL_RAW、NO_SAFETY_COMMAND_YET、IMU_TIMEOUT、LOST_ODOM…
_REASON_RE = re.compile(r"\b(?:NO|MISSING|LOST|STALE)_([A-Z0-9_]+?)(?:_YET|_RECEIVED|_DATA|_MSG)?\b|\b([A-Z0-9_]+?)_(?:TIMEOUT|STALE|LOST|MISSING)\b")
_STATUS_TEXT = {"preparing": "資料預備", "planning": "Orchestrator 規劃", "working": "Workers 分析", "synthesizing": "Synthesizer 整合",
                "done": "完成", "failed": "失敗"}
_ACTIVE = ("preparing", "planning", "working", "synthesizing")


def _read_prompt(name):
    try:
        with open(os.path.join(_PROMPTS, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _clip(text, n):
    text = text or ""
    if len(text) <= n:
        return text
    head, tail = text[: n * 2 // 3], text[-n // 3:]
    return f"{head}\n…（中間省略 {len(text) - len(head) - len(tail)} 字）…\n{tail}"


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


def _sec3(ns):
    return None if ns is None else round(ns / 1e9, 3)


def _num(v):
    if isinstance(v, float):
        return float(f"{v:.6g}")
    return v


def frontmatter(fields):
    """Frontmatter（YAML）：每個欄位一行，值用 JSON 寫（JSON 是合法的 YAML flow 寫法：程式好讀、人也看得懂）。"""
    return "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fields.items()) + "\n---\n"


def is_recorder_node(node):
    return bool(_RECORDER_NODE.match(str(node or "").strip("/").split("/")[-1]))


def key_line_summary(entry, limit=10):
    """一個 Topic 的 Key 一行摘要（同 _ros2_data_common.key_summary，給 Orchestrator 的 Topic 總表用）。"""
    parts = []
    for k in entry.get("keys", []):
        if k["category"] == "time" or k["key"].startswith("header."):
            continue
        tag = k["dim"].replace(" ", "") if k["category"] == "vector" else k["category"]
        if k.get("map_by"):
            tag += f"×{k.get('entries', '?')}"
        parts.append(f"{k['key']}({tag})")
    return " ".join(parts[:limit]) + (f" …共 {len(parts)} 個" if len(parts) > limit else "")


class AnalysisMixin:

    # ---------------------------------------------------------------- 設定（logs/analysis_settings.json）
    def analysis_settings_file(self):
        return os.path.join(self.script_dir, "logs", ANALYSIS_SETTINGS_NAME)

    def load_analysis_settings(self):
        cfg = {"orchestrator": ANALYSIS_ORCHESTRATOR_MODEL, "worker": ANALYSIS_WORKER_MODEL,
               "synthesizer": ANALYSIS_SYNTHESIZER_MODEL, "orchestrator_think": ANALYSIS_THINK_DEFAULT,
               "worker_think": False, "synthesizer_think": ANALYSIS_THINK_DEFAULT,
               # 各角色的上下文長度（None＝NUM_CTX）。8 GB 顯卡上 deepseek-r1:8b 用 32k 時 KV cache 約 4.8 GB、四成跑到 CPU
               # （10.6 token/s）；Synthesizer 的輸入約 3k、輸出幾千，12288 就放得下（7.2 GB 中 6.3 GB 在 GPU，26.7 token/s）
               "orchestrator_ctx": None, "worker_ctx": None, "synthesizer_ctx": None,
               "data_root": ANALYSIS_DATA_ROOT,
               "container": "",
               "source_root": ANALYSIS_SOURCE_ROOT, "program_hints": ANALYSIS_PROGRAM_HINTS,
               "max_workers": ANALYSIS_MAX_WORKERS, "parallel": ANALYSIS_PARALLEL_WORKERS,
               "before": ANALYSIS_WINDOW_BEFORE, "after": ANALYSIS_WINDOW_AFTER, "slice": ANALYSIS_SLICE}
        try:
            with open(self.analysis_settings_file(), encoding="utf-8") as f:
                saved = json.load(f)
            for k in cfg:
                if k in saved and saved[k] not in ("",) and type(saved[k]) in (str, int, float, bool, type(None)):
                    cfg[k] = saved[k]
        except (OSError, ValueError):
            pass
        return cfg

    def save_analysis_settings(self):
        path = self.analysis_settings_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = dict(self.analysis_cfg, saved=time.strftime("%Y-%m-%d %H:%M:%S"))
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
        keep = {k: v for k, v in job.items() if k not in ("index", "events") and not k.startswith("_")}
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
            if job.get("status") not in _ACTIVE:
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
                        "workers": len(j.get("workers") or []), "confidence": (j.get("report") or {}).get("confidence")})
        return out

    def analysis_job_detail(self, jid):
        """Web 面板用：job.json、事件、各 worker 的局部報告與報告全文。"""
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
        """analysis_run 技能：解析參數 → 資料預備 → Orchestrator → Workers → Synthesizer。回傳給主對話的報告（或 [ERROR]）。"""
        try:
            toks = shlex.split(remainder or "")
        except ValueError:
            toks = (remainder or "").replace('"', " ").split()
        opts = {"data": "", "workers": None, "before": None, "after": None, "topics": [], "source": None}
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
            if t == "--source" and nxt:   # 這一次用的源碼目錄（覆蓋設定）
                opts["source"], i = nxt, i + 2
                continue
            if t == "--no-source":
                opts["source"], i = "", i + 1
                continue
            if t in ("--workers", "--before", "--after") and nxt:
                try:
                    opts[t[2:]] = int(nxt) if t == "--workers" else float(nxt)
                except ValueError:
                    return f"[ERROR] {t} 要是數字，收到 {nxt}"
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
               "program_hints": bool(cfg.get("program_hints", True)), "model_calls": 0}
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
            self._job_status(job, "working")
            self._analysis_slice(job)
            self._analysis_run_workers(job)
            self._job_status(job, "synthesizing")
            text = self._analysis_synthesize(job)
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

    def _analysis_session(self, job, kind, role, system, user, schema, predict):
        model, want = self.analysis_model(role), self.analysis_think(role)
        think = think_arg(model, want)
        with self._analysis_lock:   # 交給模型的輸入留在 job 資料夾（prompts/）：對照、重播（只換 prompt 重跑一個角色）用
            n = job.setdefault("_prompt_n", {}).get(role, 0) + 1
            job["_prompt_n"][role] = n
        self._job_write(job, f"prompts/{role}{'' if n == 1 else f'_{n}'}.md", f"# system\n{system}\n\n# user\n{user}\n")
        res = self._timed_chat(kind, model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                               format=schema, options={"temperature": 0.2, "num_ctx": self.analysis_ctx(role),
                                                       "num_predict": predict + (THINK_EXTRA_PREDICT if think else 0)},
                               think=think)
        with self._analysis_lock:
            job["model_calls"] += 1
        try:
            data = json.loads(res["message"]["content"])
            return tidy(data) if isinstance(data, dict) else None
        except (ValueError, TypeError, KeyError):
            return None

    # ---------------------------------------------------------------- 0. 資料預備
    def _analysis_prepare(self, job):
        self._analysis_note(job, "📊 資料預備：讀全域 Topic Metadata（索引）與去重後的 Log…")
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
        out = self._analysis_tool("rosout_parser_cmd.py", [job["data"], "--json", "--top", "2000", "--all-nodes"])
        logs, _ = split_json_output(out)
        if logs and "signals" in logs:
            job["signals"] = logs["signals"]
            job["log_source"] = logs.get("source")
            job["log_total"] = logs.get("total_events")
        else:
            job["signals"], job["log_source"] = [], None
            job["log_error"] = _short(out, 300)
        digest = self._digest_text(job, limit=None, include_recorder=True, with_source=True)
        self._job_write(job, "log_digest.md", f"# 去重後的 Log（{job.get('log_source') or job.get('log_error')}）\n\n{digest}\n")
        self._job_write(job, "topic_metadata.md", f"# 全域 Topic Metadata：{idx.get('label')}\n\n{self._topics_text(job)}\n")
        workers_ok = sum(1 for t in idx["topics"] if t["role"] == "worker")
        self._analysis_note(job, f"📊 數據 {idx.get('label')}：{idx.get('duration_sec')} 秒、{len(idx['topics'])} 個 Topic（可分析 "
                                 f"{workers_ok} 個）；Log {job.get('log_total') or 0} 則 → {len(job['signals'])} 個唯一訊號"
                                 + (f"（{job['log_error']}）" if job.get("log_error") else ""))
        if not workers_ok:
            return "[ERROR] 這份數據沒有可以分析的 Topic（都是 Log、沒有訊息，或訊息型別無法解碼：自訂訊息要先用 ROS2_workspace_env 確認 Workspace）。"
        self._analysis_source(job)
        return None

    def _analysis_source(self, job):
        """源碼脈絡（有設定源碼目錄時）：Log 的源碼位置（/rosout 的 file:line，錄製時就在 MCAP 裡）對回程式碼、這次在執行的節點的
        發布／訂閱關係、Log 裡的代碼在源碼的條件。程式整理（source_index），不呼叫模型；失敗不影響分析（照沒有源碼的流程）。"""
        opt = job["options"].get("source")
        root = (opt if opt is not None else (self.analysis_cfg.get("source_root") or "")).strip()
        if not root:
            return
        t0 = time.time()
        try:
            idx = source_index.load(root, cache_dir=os.path.join(self.script_dir, "logs", ANALYSIS_SOURCE_CACHE_DIRNAME))
            if idx is None:
                job["source_error"] = f"源碼目錄不存在：{root}"
                self._analysis_note(job, f"🧬 源碼脈絡：{job['source_error']}（照沒有源碼的流程分析）")
                return
            topics = {t["topic"]: {"type": t.get("type"), "count": t.get("message_count")} for t in job["index"]["topics"]}
            js = source_index.JobSource(idx, topics, job.get("signals"), job["index"].get("msg_definitions"))
        except Exception as e:   # noqa: BLE001  源碼解析的問題不能中斷分析
            job["source_error"] = f"{type(e).__name__}: {e}"
            self._analysis_note(job, f"🧬 源碼脈絡失敗：{job['source_error']}（照沒有源碼的流程分析）")
            return
        job["_source"] = js
        job["source"] = js.summary()
        self._job_write(job, "source_context.md", _source_doc(job, js))
        sites = len(js.log_sites)
        logged = sum(1 for s in job.get("signals") or [] if s.get("sources") and not is_recorder_node(s["node"]))
        self._analysis_note(job, f"🧬 源碼脈絡（{time.time() - t0:.1f} 秒；索引 {len(idx.files)} 個檔案，新解析 {idx.parsed} 個）："
                                 f"在執行的節點 {'、'.join(c['name'] for c in js.nodes) or '（源碼裡找不到）'}；"
                                 f"Log 的源碼位置對到 {sites}/{logged} 個訊號"
                                 + (f"；對不到的檔案 {len(js.unresolved)} 個" if js.unresolved else ""))

    def _signal_ns(self, s, key="first_sec"):
        return int(round(float(s[key]) * 1e9))

    def _digest_text(self, job, limit=ANALYSIS_DIGEST_MAX_SIGNALS, include_recorder=False, with_source=False):
        """去重後的 Log（給 Orchestrator 與 Synthesizer）：略過錄製工具自己的 Log；WARN 以上全部，其餘依時間補到上限。
        include_recorder：給人看的 log_digest.md 連 rosbag2 的 Log 也列（標明是錄製工具的）。
        with_source：每個訊號後面接 Log 的源碼位置（＠檔名:行 函式；有源碼脈絡時用對到的檔案，源碼版本可能不同時標出來）。"""
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
            src = _signal_source(job, s) if with_source and not rec else ""
            lines.append(f"{s['id']} {s['level']} ×{s['count']} {when} {s['node']}：{_short(s['message'], 200)}{var}{rec}{src}")
        hidden = len(sigs) - len(chosen)
        if hidden > 0:
            lines.append(f"（另有 {hidden} 個 INFO 訊號沒有列出）")
        rec = sum(1 for s in all_sigs if is_recorder_node(s["node"]))
        if rec and not include_recorder:
            lines.append(f"（略過錄製工具 rosbag2 自己的 Log {rec} 個訊號）")
        return "\n".join(lines)

    def _topics_text(self, job):
        base = job["index"]["start_ns"]
        lines, others = [], []
        for t in job["index"]["topics"]:
            if t["role"] != "worker":
                others.append(f"{t['topic']}（{ {'log': 'Log，由你看', 'empty': '沒有訊息', 'text_only': '只有文字', 'undecodable': '無法解碼'}.get(t['role'], t['role']) }）")
                continue
            span = ""
            if t.get("first_sec") is not None:
                span = f"｜{_rel(int(t['first_sec'] * 1e9), base)}～{_rel(int(t['last_sec'] * 1e9), base)}"
            lines.append(f"- {t['topic']}｜{t['type']}｜{t['message_count']} 則｜{t.get('avg_frequency_hz', '-')} Hz{span}｜"
                         f"Key：{key_line_summary(t)}")
            src = job["_source"].topic_source_line(t["topic"]) if job.get("_source") else ""
            if src:   # 源碼的維度：誰發布、什麼時候、依賴哪些輸入 Topic、誰訂閱
                lines.append(f"  {src}")
        if others:
            lines.append("（不能指派給 worker：" + "、".join(others) + "）")
        if job.get("_source"):
            miss = job["_source"].missing_inputs()
            if miss:
                have = {x["topic"] for x in job["index"]["topics"]}
                lines.append("（數據裡沒有、但在執行的節點會訂閱的 Topic——沒有被錄到，不能量測："
                             + "；".join(f"{t}{'（有這個 Topic，但沒有訊息）' if t in have else ''} → {'、'.join(cbs)}"
                                        for t, cbs in miss) + "）")
        return "\n".join(lines)

    # ---------------------------------------------------------------- 1. Orchestrator
    def _analysis_orchestrate(self, job):
        cfg = self.analysis_cfg
        idx = job["index"]
        before = job["options"]["before"] if job["options"]["before"] is not None else float(cfg.get("before") or ANALYSIS_WINDOW_BEFORE)
        after = job["options"]["after"] if job["options"]["after"] is not None else float(cfg.get("after") or ANALYSIS_WINDOW_AFTER)
        self._analysis_note(job, f"🧭 Orchestrator（{self.analysis_model('orchestrator')}）：對齊問題、挑 Log 訊號、分派 Topic…")
        forced = [t for t in job["options"]["topics"] if any(x["topic"] == t and x["role"] == "worker" for x in idx["topics"])]
        user = (f"【使用者的問題】\n{job['question']}\n\n"
                f"【數據】{idx.get('label')}：共 {idx.get('duration_sec')} 秒（時間都寫成距離數據開頭的秒數，+秒）\n\n"
                f"【去重後的 Log（唯一訊號；L# 是編號，×N 是出現次數"
                + ("；＠檔名:行 函式＝印出這則 Log 的源碼位置" if job.get("_source") else "")
                + f"）】\n{self._digest_text(job, with_source=bool(job.get('_source')))}\n\n"
                f"【全域 Topic Metadata（可以指派給 worker 的 Topic 與它們的 Key"
                + ("；每個 Topic 下面一行是源碼：誰發布、依賴哪些輸入 Topic、誰訂閱" if job.get("_source") else "")
                + f"）】\n{self._topics_text(job)}\n\n"
                + (_gap_text_for_plan(job, self._coverage_gaps(job, all_signals=True)) if _name_hints(job) else "")
                + f"【限制】最多指派 {job['max_workers']} 個 worker，每個 worker 一個不同的 Topic；Log（/rosout）不能指派——Log 由你負責看。"
                f"時間窗預設訊號前 {before:g} 秒、後 {after:g} 秒（before_sec、after_sec 可以依問題調整，0.5～60 秒）。"
                + (f"\n使用者指定一定要分析的 Topic：{'、'.join(forced)}（要指派）" if forced else "")
                + (f"\n{_SOURCE_PLAN_LINE}" if job.get("_source") else "")
                + "\n（每個欄位都用繁體中文寫）")
        system = _read_prompt("orchestrator.md")
        schema = ANALYSIS_PLAN_SCHEMA_SOURCE if job.get("_source") else ANALYSIS_PLAN_SCHEMA
        data = self._analysis_session(job, "analysis_orchestrator", "orchestrator", system, user, schema, 3072)
        plan, issues = self._clean_plan(job, data, before, after, forced)
        if issues:
            fix = (user + "\n\n【上一版計畫】\n" + json.dumps(data or {}, ensure_ascii=False)[:3500]
                   + "\n\n【程式檢查發現的問題：修正後輸出完整的計畫】\n" + "\n".join(f"- {x}" for x in issues))
            self._analysis_note(job, f"🧭 Orchestrator 的計畫有 {len(issues)} 個問題，交回修正一次：{'；'.join(issues)[:200]}")
            data2 = self._analysis_session(job, "analysis_orchestrator", "orchestrator", system, fix, schema, 3072)
            plan2, issues2 = self._clean_plan(job, data2, before, after, forced)
            if plan2["assignments"] and (len(issues2) <= len(issues) or not plan["assignments"]):
                plan, issues = plan2, issues2
        if not plan["assignments"]:
            plan["assignments"] = self._auto_assignments(job, plan["related"], job["max_workers"], forced)
            plan["auto_assigned"] = True
            issues.append("Orchestrator 沒有給出可用的指派，由程式依關聯度指派")
        plan["issues"] = issues
        windows = self._make_windows(job, plan["related"], plan["before"], plan["after"])
        for a in plan["assignments"]:
            ids = [w["id"] for w in windows if set(w["signals"]) & set(a.get("signals") or [])]
            a["windows"] = ids or [w["id"] for w in windows]
        job["plan"], job["windows"] = plan, windows
        self._job_write(job, "plan.json", json.dumps({"plan": plan, "windows": windows}, ensure_ascii=False, indent=1))
        base = job["index"]["start_ns"]
        wtxt = "；".join(f"{w['id']} {_rel(w['start_ns'], base)}～{_rel(w['end_ns'], base)}"
                        + (f"（{','.join(w['signals'])}）" if w["signals"] else "") for w in windows)
        atxt = "；".join(f"W{n}→{a['topic']}" for n, a in enumerate(plan["assignments"], 1))
        self._analysis_note(job, f"🧭 計畫：相關訊號 {', '.join(r['id'] for r in plan['related']) or '（沒有，分析整段數據）'}；"
                                 f"時間窗 {wtxt}；指派 {atxt}" + ("（程式補指派）" if plan.get("auto_assigned") else ""),
                            kind="plan")

    def _clean_plan(self, job, data, before, after, forced):
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
        topics = {t["topic"]: t for t in job["index"]["topics"]}
        lower = {k.lower(): k for k in topics}
        assigns, seen = [], set()
        for a in data.get("assignments") or []:
            raw = str((a or {}).get("topic", "")).strip()
            name = raw if raw.startswith("/") else "/" + raw
            name = lower.get(name.lower(), name)
            e = topics.get(name)
            if not e:
                issues.append(f"Topic「{raw}」不在數據裡（只能從 Topic Metadata 選）")
                continue
            if e["role"] != "worker":
                issues.append(f"{name} 不能指派給 worker（{'Log 由 Orchestrator 自己看' if e['role'] == 'log' else e['role']}）")
                continue
            if name in seen:
                issues.append(f"{name} 重複指派（一個 Topic 只給一個 worker，換別的 Topic 擴大分析廣度）")
                continue
            seen.add(name)
            sigs = [sig_by_id[s.strip().upper()]["id"] for s in (a.get("signals") or []) if s.strip().upper() in sig_by_id]
            subtask = _short(a.get("subtask") or "", 400) or "檢查這個 Topic 在時間窗內的變化，跟問題有沒有關"
            item = {"topic": name, "subtask": subtask, "signals": sigs}
            sc = _short(a.get("source_context") or "", 240)
            if sc and sc not in ("無", "沒有", "-", "（無）", "none", "None"):
                item["source_context"] = sc
            assigns.append(item)
        for t in forced:
            if t not in seen:
                assigns.insert(0, {"topic": t, "subtask": "使用者指定要分析這個 Topic：檢查它在時間窗內的變化與異常", "signals": []})
                seen.add(t)
        if len(assigns) > job["max_workers"]:
            issues.append(f"指派了 {len(assigns)} 個 worker，超過上限 {job['max_workers']}（只保留前 {job['max_workers']} 個）")
            assigns = assigns[: job["max_workers"]]
        if not assigns:
            issues.append("沒有任何有效的指派：至少把一個可分析的 Topic 指派給 worker")

        def _sec(v, default):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return default
            return min(60.0, max(0.5, v)) if v == v else default
        plan = {"understanding": _short(data.get("understanding"), 500), "related": related,
                "before": _sec(data.get("before_sec"), before), "after": _sec(data.get("after_sec"), after),
                "assignments": assigns, "report_focus": _short(data.get("report_focus"), 300)}
        return plan, issues

    def _auto_assignments(self, job, related, n, forced):
        """Orchestrator 沒給出可用的指派時：依「跟相關 Log 的 Node／訊息共用的詞」排 Topic，同分看可量測的 Key 與筆數。"""
        sig_by_id = {s["id"]: s for s in job.get("signals") or []}
        words = set()
        for r in related:
            s = sig_by_id.get(r["id"])
            if s:
                words |= set(re.findall(r"[a-z]{3,}", (s["node"] + " " + s["message"]).lower()))
        scored = []
        for t in job["index"]["topics"]:
            if t["role"] != "worker":
                continue
            tw = set(re.findall(r"[a-z]{3,}", t["topic"].lower()))
            usable = sum(1 for k in t.get("keys", []) if k["category"] in WORKER_CATEGORIES)
            scored.append((len(tw & words), usable, t["message_count"], t["topic"]))
        scored.sort(reverse=True)
        out = [{"topic": t, "subtask": "使用者指定要分析這個 Topic：檢查它在時間窗內的變化與異常", "signals": []} for t in forced]
        for _, _, _, topic in scored:
            if len(out) >= n:
                break
            if topic not in forced:
                out.append({"topic": topic, "subtask": "檢查這個 Topic 在時間窗內的變化（狀態跳轉、數值異常、訊息中斷），判斷跟問題有沒有關",
                            "signals": [r["id"] for r in related]})
        return out

    def _make_windows(self, job, related, before, after):
        """相關訊號的時間戳（每個訊號最多前幾次出現）前後各取 before／after 秒；重疊的合併、限制在數據範圍內、最多 N 個。
        沒有相關訊號時整段數據一個時間窗。"""
        idx = job["index"]
        start, end = idx["start_ns"], idx["end_ns"]
        sig_by_id = {s["id"]: s for s in job.get("signals") or []}
        anchors = []
        for r in related:
            s = sig_by_id.get(r["id"])
            for t in (s or {}).get("times_sec", [])[:ANALYSIS_SIGNAL_OCCURRENCES]:
                anchors.append((int(round(float(t) * 1e9)), r["id"]))
        if not anchors:
            return [{"id": "W1", "start_ns": start, "end_ns": end, "anchor_ns": None, "signals": [], "label": "整段數據"}]
        anchors.sort()
        wins = []
        for t, sid in anchors:
            s, e = t - int(before * 1e9), t + int(after * 1e9)
            if wins and s <= wins[-1]["end_ns"]:
                w = wins[-1]
                w["end_ns"] = max(w["end_ns"], e)
                if sid not in w["signals"]:
                    w["signals"].append(sid)
            else:
                wins.append({"start_ns": s, "end_ns": e, "anchor_ns": t, "signals": [sid]})
        out = []
        for w in wins:
            s, e = max(w["start_ns"], start), min(w["end_ns"], end)
            if e > s:
                out.append(dict(w, start_ns=s, end_ns=e))
        if not out:   # Log 的時間都不在數據範圍內（時鐘不同）：退回整段數據
            return [{"id": "W1", "start_ns": start, "end_ns": end, "anchor_ns": None, "signals": [], "label": "整段數據（Log 的時間不在數據範圍內）"}]
        out = out[:ANALYSIS_MAX_WINDOWS]
        for i, w in enumerate(out, 1):
            w["id"] = f"W{i}"
            sig = sig_by_id.get(w["signals"][0], {})
            w["label"] = f"{w['signals'][0]} {sig.get('level', '')} {sig.get('node', '')}".strip()
        return out

    # ---------------------------------------------------------------- 1.5 動態時間切片
    def _analysis_slice(self, job):
        """設計的「動態時間切片」：Orchestrator 挑的訊號換算成時間窗之後，每個時間窗用 mcap_slicer 切一片——只含指派的 Topic
        （和 /rosout，給人用 Foxglove 看），每個 Topic 再帶上時間窗之前的最後一則（狀態接得上）——worker 只讀自己時間窗的切片，
        數據再長也只看關鍵的那幾段。整段數據（沒有相關訊號）不切；切片失敗就讀原本的數據（記在進度裡）。
        切片留在數據資料夾的 analysis_slices/<job 編號>/。"""
        wins = [w for w in job["windows"] if w.get("anchor_ns") is not None]
        if not self.analysis_cfg.get("slice", True):
            self._analysis_note(job, "✂️ 切片：設定關閉（/analysis_slice on 可以打開），worker 直接讀原本的數據")
            return
        if not wins:
            self._analysis_note(job, "✂️ 切片：時間窗是整段數據，不切片（worker 直接讀原本的數據）")
            return
        have = {t["topic"] for t in job["index"]["topics"]}
        topics = sorted({a["topic"] for a in job["plan"]["assignments"]} | ({"/rosout"} & have))
        args = [job["data"]]
        for w in wins:
            args += ["--window", f"{_epoch(w['start_ns'])},{_epoch(w['end_ns'])},{_epoch(w['anchor_ns'])},{w['id']}"]
        args += ["--topics", *topics, "--with-state", "--out", f"{job['data'].rstrip('/')}/{ANALYSIS_SLICES_DIRNAME}/{job['id']}", "--json"]
        t0 = time.time()
        out = self._analysis_tool("mcap_slicer_cmd.py", args)
        js, _ = split_json_output(out)
        by_id = {(sl.get("trigger") or {}).get("id"): sl for sl in (js or {}).get("slices") or []}
        base = job["index"]["start_ns"]
        made = []
        for w in wins:
            sl = by_id.get(w["id"])
            if not sl:
                continue
            w.update(slice=sl["dir"], slice_host=sl.get("host_dir"), slice_messages=sl.get("messages"),
                     slice_state_messages=sl.get("state_messages"))
            made.append(f"{w['id']} {_rel(w['start_ns'], base)}～{_rel(w['end_ns'], base)} {sl.get('messages')} 則"
                        f"＋狀態快照 {sl.get('state_messages')} 則")
        job["slices"] = {w["id"]: {"dir": w["slice"], "host_dir": w.get("slice_host"), "messages": w.get("slice_messages"),
                                   "state_messages": w.get("slice_state_messages")} for w in wins if w.get("slice")}
        whole = sum(t.get("message_count") or 0 for t in job["index"]["topics"])
        job["data_messages"] = whole   # 整份數據的訊息數（job.json 不存索引；回歸評分算切片比例用）
        if made:
            self._analysis_note(job, f"✂️ 切片（{time.time() - t0:.1f} 秒；只含 {len(topics)} 個 Topic，原本整份 {whole} 則）：" + "；".join(made))
        else:
            self._analysis_note(job, "✂️ 切片失敗，worker 改讀原本的數據：" + _short(out, 200))
        self._job_save(job)

    # ---------------------------------------------------------------- 2. Workers
    def _analysis_run_workers(self, job):
        assigns = job["plan"]["assignments"]
        par = max(1, min(int(self.analysis_cfg.get("parallel") or 1), len(assigns)))
        self._analysis_note(job, f"🔧 派 {len(assigns)} 個 worker（同時 {par} 個；模型 {self.analysis_model('worker')}）")
        with ThreadPoolExecutor(max_workers=par) as ex:
            futures = [ex.submit(self._analysis_one_worker, job, n, a) for n, a in enumerate(assigns, 1)]
            job["workers"] = [f.result() for f in futures]
        self._job_save(job)

    def _analysis_one_worker(self, job, n, assignment):
        try:
            return AnalysisWorker(self, job, n, assignment).run()
        except Exception as e:   # noqa: BLE001  一個 worker 壞掉不影響其他 worker
            self._analysis_note(job, f"❌ W{n} {assignment['topic']}：{type(e).__name__}: {e}", kind="worker_error", worker=n)
            return {"n": n, "topic": assignment["topic"], "status": "failed", "error": f"{type(e).__name__}: {e}",
                    "summary": "", "anomaly_detected": None, "analyzed_keys": [], "program_flags": [], "evidence": []}

    # ---------------------------------------------------------------- 3. Synthesizer
    def _coverage_gaps(self, job, all_signals=False):
        """程式檢查：相關的（與 WARN 以上的）Log 提到「某個輸入沒有／逾時」（NO_X、X_TIMEOUT…），數據裡卻沒有名稱對得上 X 的 Topic。
        實測 e4b 的 Synthesizer 三次都拿名稱相近的輸出 Topic（/cmd_vel 是 0）去「證實」NO_CMD_VEL_RAW——/cmd_vel_raw 根本沒錄到。
        all_signals：看全部的 Log（錄製工具自己的除外）——給 Orchestrator 用，那時還沒有挑相關的訊號。
        回傳 [(原因代碼, 對應的名稱, [L#…])]；名稱相近的 Topic 用 _similar_topics 找。"""
        names = [t["topic"].lower().replace("/", "_") for t in job["index"]["topics"] if t.get("message_count")]
        related = {r["id"] for r in (job.get("plan") or {}).get("related") or []}
        gaps = {}
        for s in job.get("signals") or []:
            if all_signals:
                if is_recorder_node(s["node"]):
                    continue
            elif s["id"] not in related and _LEVEL_RANK.get(s["level"], 1) < 2:
                continue
            for m in _REASON_RE.finditer(s["message"]):
                x = (m.group(1) or m.group(2) or "").lower()
                if len(x) < 3 or any(x in n for n in names):
                    continue
                gaps.setdefault(m.group(0), (x, []))[1].append(s["id"])
        return [(code, x, sorted(set(ids), key=lambda i: int(i[1:]) if i[1:].isdigit() else 0)) for code, (x, ids) in gaps.items()]

    def _analysis_synthesize(self, job):
        self._analysis_note(job, f"🧩 Synthesizer（{self.analysis_model('synthesizer')}）：整合 {len(job['workers'])} 份局部報告…")
        base = job["index"]["start_ns"]
        plan = job["plan"]
        sig_by_id = {s["id"]: s for s in job.get("signals") or []}
        rel_lines = []
        for r in plan["related"]:
            s = sig_by_id.get(r["id"], {})
            if s:
                rel_lines.append(f"- {s['id']} {s['level']} ×{s['count']} {_rel(self._signal_ns(s), base)} {s['node']}："
                                 f"{_short(s['message'], 260)}（Orchestrator：{r['why']}）"
                                 + (_signal_source(job, s) if job.get("_source") else ""))
        warn = [s for s in job.get("signals") or [] if _LEVEL_RANK.get(s["level"], 1) >= 2 and s["id"] not in {r["id"] for r in plan["related"]}
                and not is_recorder_node(s["node"])]
        for s in warn[:10]:
            rel_lines.append(f"- {s['id']} {s['level']} ×{s['count']} {_rel(self._signal_ns(s), base)} {s['node']}：{_short(s['message'], 200)}"
                             + (_signal_source(job, s) if job.get("_source") else ""))
        win_lines = [f"- {w['id']}：{_rel(w['start_ns'], base)}～{_rel(w['end_ns'], base)}" + (f"（錨點 {w['label']}，{_rel(w['anchor_ns'], base)}）" if w.get("anchor_ns") else "")
                     for w in job["windows"]]
        all_topics = "、".join(f"{t['topic']}（{t['message_count']} 則）" for t in job["index"]["topics"])
        hints = job["program_hints"]   # off：不給程式的推理提示（缺口、名稱相近、背景條件、共同的上游、一段完整的發布），也不事後更正
        gaps = self._coverage_gaps(job)
        flow_text = _flow_block(job["workers"], base, job.get("signals"), hints=hints, upstream_hint=_name_hints(job))
        bg = _background_codes(job["workers"], [c for c, _, _ in gaps])
        job["coverage_gaps"] = [{"reason": c, "name": x, "signals": ids, "background": (bg.get(c) or {}).get("where"),
                                 "changed": (bg.get(c) or {}).get("changed")} for c, x, ids in gaps]
        gap_text = "\n".join(
            (f"- {c}（{'、'.join(ids)}）：數據裡沒有名稱含「{x}」的 Topic，沒有被量測；不過 {bg[c]['where']} 在每次跳轉前後都有 {c}"
             f"（跳轉時新增／移除的是 {'、'.join(bg[c]['changed']) or '別的項目'}）——它是背景條件，不是這次變化的原因，"
             f"根因看新增／移除的那一項" if c in bg else
             f"- {c}（{'、'.join(ids)}）：數據裡沒有名稱含「{x}」的 Topic——沒有被量測，不能拿其他 Topic（例如名稱相近的輸出）"
             f"證明它；寫進 unknowns，信心最多 medium")
            + (_similar_note(job, c, x) if _name_hints(job) else "") for c, x, ids in gaps)
        reports = []
        reminders = _proxy_reminders(job, gaps) if _name_hints(job) else {}
        for w in job["workers"]:
            if w.get("status") == "failed":
                reports.append(f"### W{w['n']} {w['topic']}\n（這個 worker 失敗：{w.get('error')}）")
                continue
            ev = "\n".join(f"  - {e.get('time')}｜{e.get('key')}｜{e.get('observation')}" for e in w.get("evidence") or [])
            reports.append(f"### W{w['n']} {w['topic']}（{w.get('data_type')}）\n"
                           f"- 子任務：{w.get('subtask')}\n- 分析的 Key：{'、'.join(w.get('analyzed_keys') or [])}\n"
                           f"- anomaly_detected：{w.get('anomaly_detected')}（信心 {w.get('confidence')}）\n"
                           f"- 程式判斷的異常指標：{'；'.join(w.get('program_flags') or []) or '沒有'}\n"
                           f"- 局部報告：{w.get('summary')}\n" + (f"- 證據：\n{ev}" if ev else "")
                           + reminders.get(w["topic"], ""))
        user = (f"【使用者的問題】\n{job['question']}\n\n【Orchestrator 對問題的理解】\n{plan['understanding']}\n"
                + (f"報告要聚焦：{plan['report_focus']}\n" if plan.get("report_focus") else "")
                + f"\n【數據】{job.get('data_label')}：共 {job.get('duration_sec')} 秒（時間是距離數據開頭的秒數）\n\n"
                f"【Log（Orchestrator 的宏觀視角：相關的訊號與其他 WARN 以上的訊號）】\n" + ("\n".join(rel_lines) or "（沒有相關的 Log）")
                + "\n\n【時間窗】\n" + "\n".join(win_lines)
                + f"\n\n【數據裡有的 Topic（全部）】\n{all_topics}"
                + _source_text(job, "synthesizer", related=[r["id"] for r in plan["related"]])
                + (f"\n\n【程式檢查：Log 提到、但數據裡沒有對應 Topic 的輸入】\n{gap_text}" if gaps and hints else "")
                + (f"\n\n【程式整理：訊息流（Topic 的中斷、中途開始或停止發布）】\n{flow_text}" if flow_text else "")
                + "\n\n【各 Worker 的局部報告（每個 worker 一個 Topic）】\n" + "\n\n".join(reports)
                + "\n\n（每個欄位都用繁體中文寫；時間寫成 +秒）")
        data = self._analysis_session(job, "analysis_synthesizer", "synthesizer", _read_prompt("synthesizer.md"), user,
                                      ANALYSIS_REPORT_SCHEMA, 4096)
        job["synth_raw"] = json.loads(json.dumps(data, ensure_ascii=False)) if data else None   # 模型原本寫的（程式更正之前）
        if not data:
            data = self._fallback_report(job)
        # 時間線：L# 的時間校正、補上訊息流的事件、依時間排序（模型偶爾排錯；寫不出數字的放最後，其餘順序不變）
        data["timeline"] = [x for x in data.get("timeline") or [] if isinstance(x, dict)]
        fixed = _fix_signal_times(data["timeline"], sig_by_id, base)
        if fixed:
            self._analysis_note(job, f"🛠 時間線：{fixed} 個 Log 訊號（L#）的時間跟 Log 對不上，照 Log 的時間戳校正")
        added = _ensure_flow_events(data["timeline"], job["workers"])
        if added:
            self._analysis_note(job, f"🛠 時間線：補上 {added} 個訊息流的事件（Topic 的中斷、中途開始或停止）")
        data["timeline"] = sorted(data["timeline"], key=_timeline_key)
        # 背景條件（每次跳轉前後都在）：結論、根因沒有拿它當原因就不列 unknowns、不限制信心（實測：提醒反而把 Synthesizer 引到它身上）；
        # 拿它當原因（實測 e4b 3 次：「缺少速度指令」），程式在後面附更正——恢復之後仍在的原因不可能是這次變化的原因——並照一般的缺口處理
        relied = [c for c in bg if _relies_on(data.get("root_cause"), c) or _relies_on(data.get("conclusion"), c)] if hints else []
        for c in relied:
            changed = "、".join(bg[c]["changed"]) or "別的項目"
            fix = f"（程式更正：{c} 在 {bg[c]['where']} 每次跳轉前後都在、恢復之後仍在，不可能是這次變化的原因；跳轉時新增／移除的是 {changed}，根因要看這幾項）"
            for field in ("root_cause", "conclusion"):
                if _relies_on(data.get(field), c):
                    data[field] = (data.get(field) or "") + fix
            job.setdefault("corrections", []).append({"reason": c, "where": bg[c]["where"], "changed": bg[c]["changed"]})
            self._analysis_note(job, f"🛠 根因更正：{c} 是背景條件（恢復之後仍在），報告拿它當原因，附上程式更正")
        gaps = [g for g in gaps if g[0] not in bg or g[0] in relied]
        if gaps and hints:   # 程式保證：缺的輸入一定列在「尚未確認」、信心最多 medium（模型常忽略這條規則，2.18）
            unknowns = list(data.get("unknowns") or [])
            for c, x, ids in gaps:
                if not any(x in str(u).lower() or c.lower() in str(u).lower() for u in unknowns):
                    unknowns.append(f"Log 回報 {c}（{'、'.join(ids)}），但數據裡沒有名稱含「{x}」的 Topic，這個原因沒有被數據證實（程式檢查）")
            data["unknowns"] = unknowns[:6]
            if data.get("confidence") == "high":
                data["confidence"] = "medium"
                data["root_cause"] = (data.get("root_cause") or "") + f"（程式檢查：Log 提到的 {'、'.join(c for c, _, _ in gaps)} 不在數據裡，信心調為 medium）"
        job["report"] = {k: data.get(k) for k in ("conclusion", "root_cause", "confidence", "timeline", "evidence", "unknowns",
                                                  "recommendations")}
        report_md = self._render_report(job, data)
        self._job_write(job, "report.md", report_md)
        return self._report_for_main(job, data)

    def _fallback_report(self, job):
        """Synthesizer 沒有給出合法的 JSON：用各 worker 的結果拼一份（信心低），至少讓使用者看得到量測到的事實。"""
        anomalies = [w for w in job["workers"] if w.get("anomaly_detected")]
        return {"conclusion": ("有異常的 Topic：" + "、".join(w["topic"] for w in anomalies)) if anomalies else "各 worker 都沒有發現明確的異常",
                "root_cause": "Synthesizer 沒有產生報告，以下只列各 worker 的結果，根因需要人工判斷。", "confidence": "low",
                "timeline": [], "evidence": [{"source": w["topic"], "fact": _short(w.get("summary"), 240)} for w in job["workers"]],
                "unknowns": ["整合報告沒有產生"], "recommendations": []}

    def _render_report(self, job, data):
        base = job["index"]["start_ns"]
        plan = job["plan"]
        fm = {"artifact": "diagnosis_report", "job": job["id"], "question": job["question"], "data": job.get("data_label"),
              "data_path": job["data"], "time_range": job.get("time_range"),
              "windows": {w["id"]: [_sec3(w["start_ns"]), _sec3(w["end_ns"])] for w in job["windows"]},
              "related_signals": [r["id"] for r in plan["related"]],
              "workers": [{"topic": w["topic"], "analyzed_keys": w.get("analyzed_keys"), "anomaly_detected": w.get("anomaly_detected"),
                           "file": w.get("file")} for w in job["workers"]],
              "anomalies": [w["topic"] for w in job["workers"] if w.get("anomaly_detected")],
              "confidence": data.get("confidence"), "models": job["models"]}
        if job.get("slices"):
            fm["slices"] = {k: v.get("host_dir") or v["dir"] for k, v in job["slices"].items()}
        if job.get("source"):
            fm["source_root"] = job["source"]["root"]
            fm["source_nodes"] = job["source"]["nodes"]
        if not job["program_hints"]:
            fm["program_hints"] = False
        lines = [frontmatter(fm), f"# 數據診斷報告\n\n**問題**：{job['question']}\n\n**數據**：{job.get('data_label')}（{job['data']}，"
                                  f"{job.get('duration_sec')} 秒）\n",
                 f"## 結論\n{data.get('conclusion') or '-'}\n", f"## 根因（信心：{data.get('confidence')}）\n{data.get('root_cause') or '-'}\n"]
        if data.get("timeline"):
            lines.append("## 時間線\n| 時間 | 來源 | 事件 |\n|---|---|---|\n" + "\n".join(
                f"| {t.get('time')} | {t.get('source')} | {t.get('event')} |" for t in data["timeline"]) + "\n")
        if data.get("evidence"):
            lines.append("## 證據\n" + "\n".join(f"- **{e.get('source')}**：{e.get('fact')}" for e in data["evidence"]) + "\n")
        if data.get("unknowns"):
            lines.append("## 尚未確認\n" + "\n".join(f"- {u}" for u in data["unknowns"]) + "\n")
        if data.get("recommendations"):
            lines.append("## 建議\n" + "\n".join(f"- {r}" for r in data["recommendations"]) + "\n")
        lines.append("## 分析過程\n" + f"- Orchestrator 的理解：{plan['understanding']}\n"
                     + "- 時間窗：" + "；".join(f"{w['id']} {_rel(w['start_ns'], base)}～{_rel(w['end_ns'], base)}" + (f"（{w['label']}）" if w.get("label") else "")
                                               for w in job["windows"]) + "\n"
                     + "".join(f"- 切片 {k}：`{v.get('host_dir') or v['dir']}`（{v.get('messages')} 則＋狀態快照 {v.get('state_messages')} 則）\n"
                               for k, v in (job.get("slices") or {}).items())
                     + "\n".join(f"- W{w['n']} {w['topic']}：{'⚠️ 有異常' if w.get('anomaly_detected') else '沒有異常' if w.get('anomaly_detected') is False else '失敗'}"
                                 f"（{'、'.join(w.get('analyzed_keys') or [])}）→ `{w.get('file') or '-'}`" for w in job["workers"]) + "\n")
        return "\n".join(lines)

    def _report_for_main(self, job, data):
        """回傳給主對話的報告重點（以 ANALYSIS_REPORT_HEAD 開頭：不再摘要、整份進主對話，並存成 #編號）。"""
        base = job["index"]["start_ns"]
        n = len(job["workers"])
        lines = [f"{ANALYSIS_REPORT_HEAD}（job {job['id']}：{n} 個 worker、模型呼叫 {{CALLS}} 次、{{SECONDS}} 秒）",
                 f"問題：{job['question']}",
                 f"數據：{job.get('data_label')}（{job.get('duration_sec')} 秒）；時間窗："
                 + "；".join(f"{w['id']} {_rel(w['start_ns'], base)}～{_rel(w['end_ns'], base)}" + (f"（{w['label']}）" if w.get("label") else "")
                            for w in job["windows"]),
                 f"結論：{data.get('conclusion')}", f"根因（信心 {data.get('confidence')}）：{data.get('root_cause')}"]
        if data.get("timeline"):
            lines.append("時間線：\n" + "\n".join(f"- {t.get('time')}｜{t.get('source')}｜{t.get('event')}" for t in data["timeline"][:8]))
        if data.get("evidence"):
            lines.append("證據：\n" + "\n".join(f"- {e.get('source')}：{e.get('fact')}" for e in data["evidence"][:8]))
        if data.get("unknowns"):
            lines.append("尚未確認：" + "；".join(data["unknowns"]))
        if data.get("recommendations"):
            lines.append("建議：" + "；".join(data["recommendations"]))
        lines.append("各 worker：" + "；".join(f"W{w['n']} {w['topic']}（{'⚠️ 有異常' if w.get('anomaly_detected') else '沒有異常' if w.get('anomaly_detected') is False else '失敗'}）"
                                            for w in job["workers"]))
        lines.append(f"完整報告：logs/{ANALYSIS_JOBS_DIRNAME}/{job['id']}/report.md（各 worker 的局部報告在 workers/）")
        lines.append("（依這份報告回答使用者：引用結論、根因、時間與數值；尚未確認的部分照實說明）")
        return "\n".join(lines)


class AnalysisWorker:
    """一個 Topic 的數據解析手：乾淨的 session，只看自己的 Topic、時間窗與 Key 目錄，自己決定量測哪些 Key。"""

    def __init__(self, agent, job, n, assignment):
        self.a, self.job, self.n, self.asg = agent, job, n, assignment
        self.topic = assignment["topic"]
        self.entry = next(t for t in job["index"]["topics"] if t["topic"] == self.topic)
        self.windows = [w for w in job["windows"] if w["id"] in assignment["windows"]]
        self.model = agent.analysis_model("worker")
        self.think = think_arg(self.model, agent.analysis_think("worker"))
        self.env = {"ANALYSIS_DATA": job["data"], "ANALYSIS_TOPIC": self.topic,
                    "ANALYSIS_WINDOWS": json.dumps([dict({"id": w["id"], "start_ns": w["start_ns"], "end_ns": w["end_ns"],
                                                          "anchor_ns": w.get("anchor_ns")}, **({"slice": w["slice"]} if w.get("slice") else {}))
                                                     for w in self.windows])}
        self.keys = {k["key"]: k for k in self.entry.get("keys", [])}
        self.measured = {}
        self.calls = []
        self.key_selection = "worker"
        self.tag = f"W{n} {self.topic}"

    # ---- 任務說明
    def _brief(self):
        base = self.job["index"]["start_ns"]
        plan = self.job["plan"]
        wl = []
        for w in self.windows:
            line = f"- {w['id']}：{_rel(w['start_ns'], base)} ～ {_rel(w['end_ns'], base)}（{(w['end_ns'] - w['start_ns']) / 1e9:.1f} 秒）"
            if w.get("anchor_ns"):
                line += f"；錨點 {w['label']}（{_rel(w['anchor_ns'], base)}）"
            wl.append(line)
        kl, skip = [], []
        for k in self.entry.get("keys", []):
            if k["category"] not in WORKER_CATEGORIES:
                skip.append(k["key"])
                continue
            info = []
            if k.get("map_by"):
                info.append(f"依名稱展開 {k.get('entries', '?')} 項" + (f"，例：{'、'.join(k.get('examples', [])[:2])}" if k.get("examples") else ""))
            if k.get("components"):
                info.append("分量 " + ",".join(k["components"]))
            if k.get("values"):
                info.append("抽樣的值：" + "、".join(str(v) for v in k["values"][:5]))
            if k.get("range"):
                info.append(f"抽樣範圍 {k['range'][0]}～{k['range'][1]}")
            if k.get("note"):
                info.append(k["note"])
            # 類別寫中文（同量測工具的輸出）：英文的 state 每一列都有，實測 26b 把它當成 Key 送 --key state（/system/safety_command 35 次 15 次）
            kl.append(f"- {k['key']}｜{_CATEGORY_TEXT.get(k['category'], k['category'])}｜{k['dim']}｜{k['type']}"
                      + (f"｜{'；'.join(info)}" if info else ""))
        parts = [f"【使用者的問題】{self.job['question']}",
                 f"【Orchestrator 對問題的理解】{plan['understanding'] or '（沒有）'}",
                 f"【你的子任務】{self.asg['subtask']}",
                 f"【你負責的 Topic】{self.topic}（{self.entry['type']}，整段 {self.entry['message_count']} 則、"
                 f"{self.entry.get('avg_frequency_hz', '-')} Hz）——其他 Topic 有別的 worker 負責，你只量這一個",
                 "【時間窗】（系統已經帶入：量測時不用寫 --window，會量全部時間窗；只想看其中一個才寫 --window W1）\n" + "\n".join(wl),
                 "【這個 Topic 可以量測的 Key】（Key｜類別｜維度｜ROS 型別｜抽樣看到的）\n" + "\n".join(kl)]
        if skip:
            parts.append(f"【不量測的欄位】{'、'.join(skip)}（文字或時間；Log 與自由文字由 Orchestrator 負責）")
        src = _source_text(self.job, "worker", topic=self.topic, assignment=self.asg)
        if src:
            parts.append(src.strip())
        return "\n\n".join(parts)

    def _chat(self, msgs, schema, predict):
        res = self.a._timed_chat("analysis_worker", model=self.model, messages=msgs, format=schema,
                                 options={"temperature": 0.2, "num_ctx": self.a.analysis_ctx("worker"),
                                          "num_predict": predict + (THINK_EXTRA_PREDICT if self.think else 0)}, think=self.think)
        with self.a._analysis_lock:
            self.job["model_calls"] += 1
        return res["message"]["content"]

    # ---- 動作的檢查與執行
    def _normalize(self, action):
        """worker 的 action → (腳本, 參數) 或 (None, 錯誤訊息)。數據路徑、--topic 一律由系統決定。"""
        command = str(action.get("command") or "").strip()
        token = os.path.basename(command.split()[0]) if command else ""
        stem = token[:-3] if token.endswith(".md") else token
        script = self.a._normalize_script_name(stem)
        if script not in ANALYSIS_WORKER_SCRIPTS:
            return None, (f"[ERROR] worker 只能用 mcap_feature_measure（量測特徵）與 mcap_analyzer（看 Key、原始值）："
                          f"action.command 填 scripts/mcap_feature_measure_cmd.py，args 填 --key <Key>。收到：{command}")
        args = self.a._parse_script_args(script, action.get("args") or "")
        out, keys, i = [], [], 0
        with_value = {"--key", "--window", "--filter", "--topic", "--preview", "--around", "--before", "--after"}
        while i < len(args):
            t = args[i]
            if t in with_value and i + 1 < len(args):
                v = args[i + 1]
                if t == "--topic":
                    norm = v if v.startswith("/") else "/" + v
                    if norm != self.topic:
                        return None, f"[ERROR] 你只負責 {self.topic}；{v} 由別的 worker 負責（或不需要分析）。只量測 {self.topic} 的 Key。"
                elif t == "--key":
                    keys.append(v)
                    out += [t, v]
                else:
                    out += [t, v]
                i += 2
                continue
            if t in ("--all-entries",):
                out.append(t)
            i += 1   # 其他（位置參數的數據路徑、--json、--refresh…）：系統決定，丟掉
        if script == "mcap_feature_measure_cmd.py":
            if not keys:
                return None, "[ERROR] 要用 --key 指定要量測的 Key（可以一次寫好幾個 --key），Key 名稱照【這個 Topic 可以量測的 Key】。"
            out = ["--topic", self.topic] + out
        else:
            out = ["--topic", self.topic] + out
        return script, out

    def _run_tool(self, script, args):
        out = self.a._analysis_tool(script, args, extra_env=self.env)
        ok = not out.lstrip().startswith("[ERROR]")
        if ok and script == "mcap_feature_measure_cmd.py":   # 照輸出算真的量到的 Key（工具略過不存在的、把「類別.Key」改寫成 Key）
            for k in dict.fromkeys(re.findall(r"^\s*▸ (\S+?)（", out, re.M)):
                self.measured[k] = self.measured.get(k, 0) + 1
        self.calls.append({"script": script, "args": args, "ok": ok, "head": out.strip().splitlines()[0][:200] if out.strip() else ""})
        clean = "\n".join(ln for ln in out.splitlines() if not ln.startswith(_MARKERS))
        return clean

    def _auto_keys(self, n=3):
        """worker 一個 Key 都沒量：系統挑——狀態優先（狀態跳轉最常是線索），再來數值與向量，略過 header.*。"""
        order = {"state": 0, "kv": 1, "numeric": 2, "vector": 3, "array": 4, "matrix": 5}
        cands = [k for k in self.entry.get("keys", []) if k["category"] in order and not k["key"].startswith("header.")]
        cands.sort(key=lambda k: order[k["category"]])
        return [k["key"] for k in cands[:n]]

    # ---- 主迴圈
    def run(self):
        a, job = self.a, self.job
        a._analysis_note(job, f"🔧 {self.tag}：{_short(self.asg['subtask'], 80)}", kind="worker", worker=self.n)
        msgs = [{"role": "system", "content": _read_prompt("worker.md")}, {"role": "user", "content": self._brief()}]
        seen, steps, nudged = {}, 0, False
        while steps < ANALYSIS_WORKER_MAX_STEPS:
            steps += 1
            raw = self._chat(msgs, ANALYSIS_WORKER_REPLY_SCHEMA, 2048)
            parsed = parse_agent_reply(raw)
            if not parsed.get("valid"):
                msgs.append({"role": "assistant", "content": raw[:1500]})
                msgs.append({"role": "user", "content": "[系統] 你的回覆不是完整的 JSON，這一輪沒有執行。請縮短：thought 一兩句，一次只做一個動作。"})
                continue
            msgs.append({"role": "assistant", "content": raw})
            action = parsed.get("action") or _action_in_reply(parsed.get("reply"))
            if parsed.get("thought"):
                a._analysis_note(job, f"💭 {self.tag}：{_short(parsed['thought'], 120)}", kind="worker_step", worker=self.n)
            if not action:
                if not self.measured and not nudged:
                    nudged = True
                    msgs.append({"role": "user", "content": "[系統] 你還沒有量測任何 Key。先用 mcap_feature_measure 量跟子任務有關的 Key"
                                                            "（action.command 填 scripts/mcap_feature_measure_cmd.py，args 填 --key <Key>，"
                                                            "可以一次好幾個 --key），看到數字再下結論。"})
                    continue
                break
            script, args = self._normalize(action)
            if script is None:
                out = args
            else:
                sig = script + " " + " ".join(args)
                seen[sig] = seen.get(sig, 0) + 1
                if seen[sig] >= 3:
                    out = "[ERROR] 同一個量測已經做了 3 次，結果不會變：換別的 Key，或 action 填 null 結束、寫結論。"
                else:
                    a._analysis_note(job, f"▶ {self.tag}：{script.replace('_cmd.py', '')} {' '.join(args[2:])}", kind="worker_step", worker=self.n)
                    out = self._run_tool(script, args)
            msgs.append({"role": "user", "content": f"[tool result] {action.get('command', '')} {action.get('args', '')}\n"
                                                    f"{_clip(out, ANALYSIS_TOOL_RESULT_MAX_CHARS)}"})
        if not self.measured:
            keys = self._auto_keys()
            if keys:
                self.key_selection = "fallback"
                args = ["--topic", self.topic] + [x for k in keys for x in ("--key", k)]
                out = self._run_tool("mcap_feature_measure_cmd.py", args)
                msgs.append({"role": "user", "content": f"[系統] 你沒有量測任何 Key，系統替你量了 {'、'.join(keys)}：\n"
                                                        f"{_clip(out, ANALYSIS_TOOL_RESULT_MAX_CHARS)}"})
        msgs.append({"role": "user", "content": (
            "[系統] 量測結束，寫這個 Topic 的局部報告：analyzed_keys＝你實際量測過的 Key；anomaly_detected＝有沒有跟子任務或問題有關的"
            "異常（尖峰、狀態跳轉、訊息中斷、數值不合理）；summary＝三到六句，寫看到什麼、跟子任務的關係，引用量測的數字與時間（+秒）；"
            "evidence＝關鍵的時間點（+秒）、Key 與觀察；confidence＝high／medium／low。沒有量到的東西不要寫。")})
        try:
            rep = json.loads(self._chat(msgs, ANALYSIS_WORKER_REPORT_SCHEMA, 2048))
        except (ValueError, TypeError, KeyError):
            rep = {}
        rep = tidy(rep) if isinstance(rep, dict) else {}
        analyzed = [k for k in rep.get("analyzed_keys") or [] if k in self.measured] or list(self.measured)
        metrics, flags, data_type, ev_ts = {}, [], None, []
        if analyzed:
            args = ["--topic", self.topic, "--json"] + [x for k in analyzed for x in ("--key", k)]
            js, _ = split_json_output(a._analysis_tool("mcap_feature_measure_cmd.py", args, extra_env=self.env))
            if js:
                metrics, flags, data_type, ev_ts = _metrics_from_measure(js, analyzed)
        anomaly = bool(rep.get("anomaly_detected")) if rep else bool(flags)
        summary = _short(rep.get("summary"), 900) or "（worker 沒有寫摘要）"
        evidence = [e for e in rep.get("evidence") or [] if isinstance(e, dict)][:6]
        flow = _flow_events(metrics, self.job["index"]["start_ns"])
        broken = _flow_events(metrics, self.job["index"]["start_ns"], segments=False)
        if flow:   # 訊息流中斷（停發、中途開始／停止）本身就是異常：實測 e4b 看到 10 秒的中斷仍以「狀態沒變」判沒有異常
            if broken and not anomaly and self.job["program_hints"]:   # 一段完整的發布（中途開始又中途停止、中間沒有中斷）不強制：實測 /cmd_vel_raw 一次指令被當成故障
                anomaly = True
                summary += "（程式判斷：" + "；".join(f"{t} {what}" for t, what in broken) + "——訊息流中斷本身就是異常）"
            have = " ".join(str(e.get("time")) for e in evidence)
            evidence += [{"time": t, "key": "（訊息流）", "observation": f"{what}（程式量測）"} for t, what in flow if t not in have]
        result = {"n": self.n, "topic": self.topic, "type": self.entry["type"], "subtask": self.asg["subtask"], "status": "done",
                  "windows": [w["id"] for w in self.windows], "analyzed_keys": analyzed, "key_selection": self.key_selection,
                  "anomaly_detected": anomaly,
                  "confidence": rep.get("confidence") or "low", "summary": summary,
                  "evidence": evidence[:8], "program_flags": flags, "flow_events": flow,
                  "data_type": data_type, "steps": steps, "calls": len(self.calls),
                  "key_metrics": metrics}   # 程式量的數字也留在 job 裡：Synthesizer 前的程式檢查要用（_background_codes）
        if self.asg.get("source_context"):
            result["source_context"] = self.asg["source_context"]
        result["file"] = self._write(result, metrics, ev_ts, msgs)
        mark = "⚠️ 有異常" if result["anomaly_detected"] else "沒有異常"
        a._analysis_note(job, f"✅ {self.tag}：{mark}（{'、'.join(analyzed) or '沒有量測'}；{steps} 輪）", kind="worker_done", worker=self.n)
        return result

    def _write(self, result, metrics, ev_ts, msgs):
        base = self.job["index"]["start_ns"]
        s = min((w["start_ns"] for w in self.windows), default=None)
        e = max((w["end_ns"] for w in self.windows), default=None)
        fm = {"artifact": "worker_report", "job": self.job["id"], "worker": self.n, "topic": self.topic,
              "message_type": self.entry["type"], "data_type": result["data_type"], "time_range": [_sec3(s), _sec3(e)],
              "windows": result["windows"], "analyzed_key": (result["analyzed_keys"] or [None])[0],
              "analyzed_keys": result["analyzed_keys"], "key_selection": result["key_selection"],
              "anomaly_detected": result["anomaly_detected"], "confidence": result["confidence"],
              "program_flags": result["program_flags"], "key_metrics": metrics, "evidence_timestamps": ev_ts[:12],
              "model": self.model, "steps": result["steps"]}
        if result.get("source_context"):   # Orchestrator 給這個子任務的源碼線索（不是已證實的根因）
            fm["source_context"] = result["source_context"]
        slices = {w["id"]: w.get("slice_host") or w["slice"] for w in self.windows if w.get("slice")}
        if slices:   # 這個 worker 讀的切片（沒有＝讀原本的數據）
            fm["data_slices"] = slices
        ev = "\n".join(f"- {x.get('time')}｜`{x.get('key')}`｜{x.get('observation')}" for x in result["evidence"]) or "（沒有）"
        calls = "\n".join(f"- {'✅' if c['ok'] else '❌'} `{c['script'].replace('_cmd.py', '')} {' '.join(c['args'][2:])}`：{c['head']}"
                          for c in self.calls) or "（沒有）"
        wins = "\n".join(f"- {w['id']}：{_rel(w['start_ns'], base)}～{_rel(w['end_ns'], base)}" + (f"（錨點 {w['label']}）" if w.get("label") else "")
                         + (f"；切片 `{w.get('slice_host') or w['slice']}`" if w.get("slice") else "") for w in self.windows)
        body = (f"## 子任務\n{result['subtask']}\n\n## 時間窗\n{wins}\n\n## 分析摘要\n{result['summary']}\n\n## 證據\n{ev}\n\n"
                f"## 量測紀錄\n{calls}\n")
        rel = f"workers/W{self.n}_{_slug(self.topic)}.md"
        self.a._job_write(self.job, rel, frontmatter(fm) + "\n" + body)
        tr = "\n\n".join(f"### {m['role']}\n{m['content']}" for m in msgs)
        self.a._job_write(self.job, f"workers/W{self.n}_{_slug(self.topic)}.transcript.md", tr)
        return rel


def _set_items(text):
    """key_metrics 裡集合狀態的寫法「[A, B]」→ {A, B}；不是集合（或被截短）回 None。"""
    t = str(text or "").strip()
    if not (t.startswith("[") and t.endswith("]")):
        return None
    return {x.strip() for x in t[1:-1].split(",") if x.strip()}


def _background_codes(workers, codes):
    """程式判斷：worker 量到的集合狀態（stop_reasons、active_error_codes…）有跳轉，但這個代碼在每次跳轉前後都在＝背景條件，
    不是這次變化的原因。實測 exp_event_lifecycle：stop_reasons [NO_CMD_VEL_RAW] → [MON_INITIALIZING, NO_CMD_VEL_RAW] → [NO_CMD_VEL_RAW]，
    /cmd_vel_raw 沒錄到，覆蓋缺口的提醒反而讓 Synthesizer 把根因寫成 NO_CMD_VEL_RAW。只看 key_metrics 列全的跳轉（≤5 次）。
    回傳 {代碼: {"where": 「Topic 的 Key」, "changed": 跳轉時新增或移除的項目}}。"""
    out = {}
    for w in workers:
        for win in (w.get("key_metrics") or {}).values():
            for key, f in (win or {}).items():
                if not isinstance(f, dict) or not f.get("transitions") or f["transitions"] > len(f.get("changes") or []):
                    continue
                states, changed = [_set_items(f.get("first")), _set_items(f.get("last"))], set()
                for ch in f["changes"]:
                    a, _, rest = str(ch).partition(" → ")
                    before, after = _set_items(a), _set_items(rest.rsplit(" @", 1)[0])
                    states += [before, after]
                    if before is not None and after is not None:
                        changed |= before ^ after
                if any(x is None for x in states):
                    continue
                for c in codes:
                    if all(c in x for x in states):
                        out.setdefault(c, {"where": f"{w['topic']} 的 {key}", "changed": sorted(changed)})
    return out


_DISMISS = ("背景", "而非", "並非", "不是", "不可能", "排除", "無關", "不影響", "不構成")
# 只是說它沒有被量測、無法證實（尚未確認的內容），不算拿它當原因
_NEUTRAL = ("未被量測", "沒有被量測", "未量測", "無法證實", "沒有被數據證實", "未被證實", "不在數據裡", "缺乏對", "沒有對應")


def _relies_on(text, code):
    """結論／根因有沒有拿這個代碼當原因：提到它的句子裡有一句不是在排除它（背景、而非、不是…）、不是在說它沒被量測、
    也不是讓步子句（「雖然 Log 提到了 X，但 …」）就算。實測 e4b 排除時會寫「此為背景條件，而非導致保護停止的關鍵因素」，
    當原因時寫「原因包括 … NO_CMD_VEL_RAW」「數據證實了 NO_CMD_VEL_RAW 的情況」。"""
    c = code.lower()
    for sent in re.split(r"[。；;\n]", str(text or "")):
        s = sent.replace("不是唯一", "")
        if c not in s.lower() or any(m in s for m in _DISMISS + _NEUTRAL):
            continue
        m = re.search(r"雖然(.*?)但", s)
        if m and c in m.group(1).lower() and c not in s[m.end():].lower():
            continue
        return True
    return False


def _flow_events(metrics, base_ns, segments=True):
    """key_metrics 的 _rate → 訊息流的事件 [(+秒, 說明)]：中斷（開始時間、多久）、只在一段時間連續發布、中途才開始、中途停止。
    segments=False：不列「只在一段時間連續發布」——那是一段完整的發布（例如一次指令從開始到結束），不是中斷，worker 不因此強制算異常。"""
    out = []
    base = base_ns / 1e9
    for wm in (metrics or {}).values():
        r = (wm or {}).get("_rate") or {}
        for g in r.get("gaps") or []:
            out.append((f"+{g['start_sec'] - base:.2f}s", f"訊息中斷 {g['duration_sec']:.2f} 秒"))
        if r.get("published_only"):
            a, b = r["published_only"]
            if segments:
                out.append((f"+{a - base:.2f}s", f"只在 +{a - base:.2f}s～+{b - base:.2f}s 連續發布（一段完整的發布，中間沒有中斷；"
                                                 "之前、之後都沒有訊息）"))
        else:
            if r.get("started_at"):
                out.append((f"+{r['started_at'] - base:.2f}s", "中途才開始發布"))
            if r.get("stopped_after"):
                out.append((f"+{r['stopped_after'] - base:.2f}s", "之後停止發布"))
    return out


def _similar_topics(job, x):
    """數據裡（有訊息的）名稱相近、但不是 X 的 Topic：最後一段名稱（或整個名稱）包含在 X 裡，例如 /cmd_vel 之於 cmd_vel_raw。"""
    out = []
    for t in job["index"]["topics"]:
        if not t.get("message_count"):
            continue
        last = t["topic"].rstrip("/").rsplit("/", 1)[-1].lower()
        full = t["topic"].lower().strip("/").replace("/", "_")
        if (len(last) >= 3 and last in x) or (len(full) >= 3 and full in x):
            out.append(t["topic"])
    return out


def _similar_note(job, code, x):
    """缺口說明的補充：名稱相近的 Topic 是另一個 Topic，有沒有在發布、數值多少都不能證明也不能排除這個原因。
    實測 26b：數據裡沒有 /cmd_vel_raw 時，Orchestrator 派 /cmd_vel「驗證 NO_CMD_VEL_RAW」，報告寫「/cmd_vel 穩定發布，排除指令丟失」（25 次 15 次）。"""
    sim = _similar_topics(job, x)
    if not sim:
        return ""
    return (f"；數據裡名稱相近的 {'、'.join(sim)} 是另一個 Topic，不是「{x}」——它有沒有在發布、數值多少，"
            f"都不能證明也不能排除 {code}")


def _proxy_reminders(job, gaps):
    """名稱相近、但不是沒錄到的那個輸入的 Topic：在它的局部報告旁邊附程式提醒（Topic → 文字）。
    實測 26b：缺口說明寫了「名稱相近的 /cmd_vel 不能證明也不能排除 NO_CMD_VEL_RAW」，Synthesizer 讀到 W3 的「/cmd_vel 穩定 20 Hz」
    仍寫「排除指令流中斷」（25 次 9 次）——提醒放在它引用的那份報告旁邊。"""
    out = {}
    for c, x, _ids in gaps:
        for t in _similar_topics(job, x):
            out[t] = out.get(t, "") + (f"\n- 程式提醒：{t} 不是「{x}」（數據裡沒有）——這份報告的數字（有沒有在發布、數值多少）"
                                       f"不能用來證明或排除 {c}")
    return out


def _gap_text_for_plan(job, gaps):
    """給 Orchestrator 的程式檢查：Log 提到、數據裡沒有的輸入，以及不能拿來代替它的名稱相近的 Topic。"""
    if not gaps:
        return ""
    rows = []
    for c, x, ids in gaps:
        row = f"- {c}（{'、'.join(ids[:6])}）：指的是名稱含「{x}」的 Topic，這份數據沒有錄到"
        sim = _similar_topics(job, x)
        if sim:
            row += (f"；名稱相近的 {'、'.join(sim)} 是另一個 Topic——不能拿它代替「{x}」去驗證 {c}，"
                    f"要派它的話，子任務寫成看它自己的變化")
        rows.append(row)
    return "【程式檢查：Log 提到、但數據裡沒有的輸入】\n" + "\n".join(rows) + "\n\n"


# ---------------------------------------------------------------------------------------------------------------------
# 源碼脈絡（agent_core/source_index.py 整理的事實）→ 各角色的文字
# ---------------------------------------------------------------------------------------------------------------------
_SOURCE_GUIDE = ("看法：Topic 之間的因果方向看「訂閱的 Topic → callback 寫入的變數 → 什麼時候發布」；Log 裡的代碼看它在源碼裡成立的條件，"
                 "以及條件讀的變數由哪個 Topic（callback）或參數寫入。源碼是線索，不是已經發生的事——發生了什麼、什麼時候，要看 Log 與數據；"
                 "標（✗數據裡沒有）的 Topic 沒有被錄到，不能量測。")


def _name_hints(job):
    """用名稱猜 Topic 關係的程式提示（Orchestrator 的缺口檢查、名稱相近的 Topic、報告旁的提醒、「通常是共同的上游」）：
    有源碼脈絡時不用——誰發布、依賴哪些輸入 Topic、哪些輸入沒錄到，源碼已經給了真正的關係（實測 26b：只靠源碼，有事件的數據拿
    /cmd_vel 當 /cmd_vel_raw 的證據 20 次 1 次，名稱提示 2 次、都沒有 15 次）。一段完整的發布、背景條件這類判斷照 program_hints。"""
    return bool(job["program_hints"]) and not job.get("_source")


def _signal_source(job, s):
    """Log 訊號後面接的源碼位置：「  ＠檔名:行 函式」（源碼版本可能不同、源碼目錄裡找不到時標出來）。"""
    js = job.get("_source")
    site = js.log_sites.get(s["id"]) if js else None
    if site:
        return f"  ＠{os.path.basename(site['file'])}:{site['line']} {site['func']}" + ("（源碼版本可能不同）" if site.get("note") else "")
    src = (s.get("sources") or [None])[0]
    if not src:
        return ""
    return f"  ＠{os.path.basename(str(src.get('file')))}:{src.get('line')} {src.get('function')}" + ("（源碼目錄裡找不到）" if js else "")


def _fit(rows, cap):
    """文字超過上限：先拿掉參數列，再從後面整行截掉（附省略說明）。"""
    text = "\n".join(rows)
    if len(text) <= cap:
        return text
    rows = [r for r in rows if not r.startswith("  參數：")]
    out, n = [], 0
    for r in rows:
        if n + len(r) + 1 > cap - 40:
            out.append(f"…（源碼脈絡超過 {cap} 字，後面省略；完整內容在 job 資料夾的 source_context.md）")
            break
        out.append(r)
        n += len(r) + 1
    return "\n".join(out)


def _msg_consts(js, mtype, limit=14):
    """msg 定義（MCAP 的 schema）裡的常數：NAME=值（狀態、原因代碼的全集）。"""
    out = []
    for ln in (js.msg_defs.get(mtype) or "").splitlines():
        m = re.match(r"^\s*[\w/]+\s+([A-Z][A-Z0-9_]*)\s*=\s*(.+?)\s*$", ln)
        if m:
            out.append(f"{m.group(1)}={m.group(2).strip()}")
    return out[:limit] + ([f"…共 {len(out)} 個"] if len(out) > limit else [])


def _metric_tokens(workers):
    """worker 量到的狀態值裡的代碼（stop_reasons 的 [A, B]、mode 的值…）。"""
    toks = []
    for w in workers or []:
        toks += source_index.tokens_in(json.dumps(w.get("key_metrics") or {}, ensure_ascii=False))
    return list(dict.fromkeys(toks))


# Orchestrator 的源碼脈絡只放在 Log（＠檔名:行 函式）與 Topic Metadata（每個 Topic 的源碼一行、沒錄到的輸入）裡，加這一行說明
# source_context：實測（gemma4:26b，只重跑 Orchestrator）再給一整段【源碼脈絡】（節點卡、代碼的條件）時，cmdvel 數據挑指令開始的
# L15 從 20/20 掉到 7/20（時間窗看不到開始）；只留 Topic 的源碼一行＋這一行：18/20，/cmd_vel 的子任務寫成驗證輸入一樣少
_SOURCE_PLAN_LINE = "source_context 填這個子任務根據的源碼線索（Log 後面的 ＠檔名:行 函式、Topic 的源碼一行），沒有就寫「無」。"


def _source_text(job, role, topic=None, assignment=None, related=None):
    """各角色的【源碼脈絡】：Worker＝自己的 Topic 的發布者、依賴的輸入、訂閱者、msg 定義的說明與常數、發布的程式碼；
    Synthesizer＝每個 Topic 的源碼一行、在執行的節點、相關 Log 的源碼位置、代碼的條件（Log 與 worker 量到的狀態值）、相關函式的程式碼。
    Orchestrator 不用這一段（見 _SOURCE_PLAN_LINE）。沒有源碼脈絡回空字串。"""
    js = job.get("_source")
    if not js:
        return ""
    cap = ANALYSIS_SOURCE_MAX_CHARS.get(role, 6000)
    head = f"【源碼脈絡（程式從源碼目錄 {js.idx.root} 整理：這次在執行的節點）】"
    if role == "worker":
        rows = [f"【源碼脈絡：{topic}（程式從源碼目錄整理；源碼是線索，數字以量測為準）】",
                "- " + js.topic_source_line(topic)]
        pubs = [(c, p) for c in js.nodes for p in c["pubs"] if p["topic"] == topic]
        mtype = (js.topics.get(topic) or {}).get("type")
        comment = js.msg_comment(mtype, 400) if mtype else ""
        if comment:
            rows.append(f"- msg 定義的說明（{mtype}，錄製時存在 MCAP 裡）：{comment}")
        consts = _msg_consts(js, mtype) if mtype else []
        if consts:
            rows.append("- msg 定義的常數：" + "、".join(consts))
        if (assignment or {}).get("source_context"):
            rows.append(f"- Orchestrator 指出的源碼線索：{assignment['source_context']}")
        for c, p in pubs[:1]:
            for x in p["sites"][:1]:
                code = js.function_code(c["file"], x["func"], mark=(x["line"],), max_lines=24)
                if code:
                    rows.append(f"發布的程式碼（{c['file']}）：\n{code}")
        return _fit(rows, cap)
    # synthesizer
    warn = {s["id"] for s in js.signals if s.get("level") in ("WARN", "ERROR", "FATAL")}
    ids = set(related or []) | warn
    toks = list(dict.fromkeys(js.signal_tokens(ids=ids) + _metric_tokens(job.get("workers"))))
    topics = [w["topic"] for w in job.get("workers") or []]
    topics += [t["topic"] for t in job["index"]["topics"] if t.get("role") == "worker" and t["topic"] not in topics]
    rows = [head, _SOURCE_GUIDE, "Topic 之間的關係（每個 Topic：誰發布、什麼時候、依賴哪些輸入 Topic、誰訂閱）："]
    rows += [f"- {t}：{js.topic_source_line(t)}" for t in topics if js.topic_source_line(t)]
    miss = js.missing_inputs()
    if miss:
        rows.append("- 數據裡沒有、但在執行的節點會訂閱的 Topic（沒有被錄到，不能量測）：" + "；".join(f"{t} → {'、'.join(cbs)}" for t, cbs in miss))
    rows += ["在執行的節點："] + js.node_lines(compact=True) + js.orphan_lines()
    ll = js.log_lines(ids=ids)
    if ll:
        rows += ["相關 Log 的源碼位置："] + ll
    tl = js.token_lines(toks, limit=10)
    if tl:
        rows += ["代碼在源碼的條件："] + tl
    text = _fit(rows, cap - 2500)
    # 相關的程式碼：WARN 以上的代碼產生的函式 → 指派的 Topic 的發布函式（短的：直接看得出輸出怎麼算）→ 其他代碼的函式
    warn_toks = js.signal_tokens(ids=warn)
    token_funcs, pub_funcs = [], []
    for tok in toks:
        for site in js.token_info(tok, limit=1)["sites"]:
            if site["func"]:
                token_funcs.append((tok in warn_toks, site["file"], site["func"], (site["line"], site.get("cond_line") or site["line"])))
    for w in job.get("workers") or []:
        for c in js.nodes:
            for p in c["pubs"]:
                if p["topic"] == w["topic"] and p["sites"]:
                    pub_funcs.append((c["file"], p["sites"][0]["func"], (p["sites"][0]["line"],)))
    funcs = ([f[1:] for f in token_funcs if f[0]] + pub_funcs + [f[1:] for f in token_funcs if not f[0]])
    seen, code_rows = set(), []
    for rel, func, marks in funcs:
        if (rel, func) in seen or len(seen) >= 5:
            continue
        seen.add((rel, func))
        code = js.function_code(rel, func, mark=marks, max_lines=36)
        if code and len(text) + sum(len(x) for x in code_rows) + len(code) + 80 <= cap:
            code_rows.append(f"（{rel}：{func}；▶＝相關的行）\n{code}")
    if code_rows:
        text += "\n相關的程式碼：\n" + "\n".join(code_rows)
    return "\n\n" + text


def _source_doc(job, js):
    """job 資料夾的 source_context.md（給人看的完整版）。"""
    s = js.summary()
    rows = [f"# 源碼脈絡：{s['root']}", "",
            f"- 索引：{s['files']} 個檔案；在執行的節點：" + "、".join(f"{k}（{v}）" for k, v in s["nodes"].items()),
            f"- 判斷在執行的依據：Log 的節點、數據裡的 /<節點>/transition_event、同一個 launch 檔啟動的節點；名稱：{'、'.join(s['running'])}",
            "", "## 節點與 Topic", *js.node_lines(), *js.orphan_lines(), "", "## Log 的源碼位置", *(js.log_lines() or ["（沒有）"]),
            "", "## 代碼在源碼的條件", *(js.token_lines(js.signal_tokens(), limit=30) or ["（沒有）"])]
    if s["unresolved"]:
        rows += ["", "## 對不到源碼的 Log 位置", *[f"- {u['id']}：{u['file']}" for u in s["unresolved"]]]
    return "\n".join(rows) + "\n"


def _segment_notes(workers, base_ns, signals):
    """一段完整的發布（中途開始又中途停止、中間沒有中斷）的程式判斷，接在「訊息流」後面給 Synthesizer：
    - 它是一次指令或一個動作從開始到結束，不是中斷；
    - Log 裡原因代碼對得上這個 Topic 的（NO_X、X_TIMEOUT…，X 在 Topic 名稱裡，同 _coverage_gaps），在它結束後 3 秒內出現＝逾時判斷的結果；
    - 整份數據的 Log 沒有 WARN 以上、別的 Topic 也沒有中斷時，狀態變化都能用它解釋就寫成正常的操作序列（Synthesizer 規則 6）。
    實測：/cmd_vel_raw 一次 0.1 m/s、8 秒的指令，26b 5/5 寫成「指令中斷」、沒說是正常的操作，e4b 4/5 寫成「間歇性」「波動」；
    規則只寫在 prompt 裡擋不住。"""
    base = base_ns / 1e9
    sigs = [s for s in signals or [] if not is_recorder_node(s.get("node", ""))]
    quiet = not any(_LEVEL_RANK.get(s.get("level"), 1) >= 2 for s in sigs) and not any(
        _flow_events(w.get("key_metrics"), base_ns, segments=False) for w in workers)
    notes = []
    for w in workers:
        name = w["topic"].lower().replace("/", "_")
        for wm in (w.get("key_metrics") or {}).values():
            seg = ((wm or {}).get("_rate") or {}).get("published_only")
            if not seg:
                continue
            a, b = seg
            text = (f"- {w['topic']} 在 +{a - base:.2f}s～+{b - base:.2f}s 是一段完整的發布（中途開始、中途停止、中間沒有中斷）："
                    "一次指令或一個動作從開始到結束，不是中斷或間歇性丟失")
            after = []
            for s in sigs:
                codes = [m.group(0) for m in _REASON_RE.finditer(s.get("message", ""))
                         if len(m.group(1) or m.group(2) or "") >= 3 and (m.group(1) or m.group(2)).lower() in name]
                t = next((t for t in s.get("times_sec") or [] if 0 <= t - b <= 3.0), None)
                if codes and t is not None:
                    after.append(f"{s['id']}（+{t - base:.2f}s，{codes[0]}）")
            if after:
                text += f"；它結束後的 {'、'.join(after)}是逾時判斷的結果（先停止、超過逾時才判定），不是另一個問題"
            if quiet:
                text += ("。這份數據的 Log 沒有 WARN 以上的訊號、其他 Topic 也沒有中斷：狀態變化都能用這段發布的開始與結束解釋時，"
                         "結論寫成正常的操作序列（不是故障）；發布的來源、為什麼結束，數據看不出來就寫進 unknowns")
            notes.append(text)
    return notes


def _flow_block(workers, base_ns=None, signals=None, hints=True, upstream_hint=True):
    """交給 Synthesizer 的「程式整理：訊息流」：每個 Topic 的中斷與開始／停止，加上同一時間一起中斷的 Topic（共同的上游）；
    有數據開頭（base_ns）時，一段完整的發布再接程式的判斷（_segment_notes）。
    hints=False：只列事實（哪些 Topic 在什麼時候中斷、一起中斷），不附「通常是共同的上游」與一段完整的發布的判斷；
    upstream_hint=False：不附「通常是共同的上游」（有源碼脈絡時，誰發布、依賴哪些輸入已經寫在 Topic 的關係裡）。"""
    rows, starts = [], []
    for w in workers:
        for t, what in w.get("flow_events") or []:
            rows.append(f"- {t} {w['topic']}：{what}")
            if what.startswith("訊息中斷"):
                starts.append((float(t.strip("+s")), w["topic"], what))
    together = []
    for t, tp, what in sorted(starts):
        if together and t - together[-1][0][0] <= 0.3:
            together[-1].append((t, tp, what))
        else:
            together.append([(t, tp, what)])
    for g in together:
        if len({tp for _, tp, _ in g}) >= 2:
            rows.append(f"- 同一時間（+{g[0][0]:.2f}s）一起中斷：{'、'.join(tp for _, tp, _ in g)}"
                        + ("——好幾個 Topic 同時停發，通常是共同的上游（發布它們的節點，或它們共同依賴的輸入）出了問題"
                           if hints and upstream_hint else ""))
    if base_ns is not None and hints:
        rows += _segment_notes(workers, base_ns, signals)
    return "\n".join(rows)


def _ensure_flow_events(timeline, workers):
    """時間線一定有訊息流的事件：某個 Topic 的中斷／開始／停止沒有寫進時間線（來源或事件提到這個 Topic、時間差 0.3 秒內），
    程式補一列。模型常把幾個 Topic 寫在同一列（來源寫「Topic/Message Flow」、事件裡列出 Topic），那樣就不重複補。"""
    added = 0
    for w in workers:
        for t, what in w.get("flow_events") or []:
            tv = float(t.strip("+s"))
            if not any(w["topic"] in f"{x.get('source')} {x.get('event')}" and abs(_timeline_key(x) - tv) <= 0.3 for x in timeline):
                timeline.append({"time": t, "source": w["topic"], "event": f"{what}（程式補上）"})
                added += 1
    return added


def _epoch(ns):
    """奈秒 → epoch 秒的字串（保留 9 位小數，不經過 float）。"""
    return f"{int(ns) // 1_000_000_000}.{int(ns) % 1_000_000_000:09d}"


def _fix_signal_times(timeline, sig_by_id, base_ns):
    """程式校正：來源是一個 Log 訊號（L#）的時間線項目，時間要是那則 Log 真的出現的時間。實測 e4b 把 L17（+18.71s）寫成
    時間窗的開頭 +8.71s，主模型照抄給使用者。差超過 0.05 秒就換成最接近的出現時間；出現次數比記下的時間戳多、而模型的時間
    落在第一次～最後一次之間的不動（可能是沒記下的那幾次）。回傳校正了幾個。"""
    fixed = 0
    for item in timeline:
        ids = re.findall(r"\bL\d+\b", str((item or {}).get("source") or ""))
        s = sig_by_id.get(ids[0]) if len(ids) == 1 else None
        if not s or s.get("first_sec") is None:
            continue
        base = base_ns / 1e9
        occ = [t - base for t in (s.get("times_sec") or [s["first_sec"]])]
        m = re.search(r"[+-]?\d+(?:\.\d+)?", str(item.get("time", "")))
        t = float(m.group()) if m else None
        if t is not None and s.get("count", 1) > len(occ) and s["first_sec"] - base - 0.05 <= t <= s["last_sec"] - base + 0.05:
            continue
        best = min(occ, key=lambda o: abs(o - t)) if t is not None else occ[0]
        if t is None or abs(best - t) > 0.05:
            item["time"] = f"+{best:.2f}s"
            fixed += 1
    return fixed


def _timeline_key(item):
    m = re.search(r"[+-]?\d+(?:\.\d+)?", str((item or {}).get("time", "")))
    return float(m.group()) if m else float("inf")


def _action_in_reply(reply):
    """實測（gemma4:e4b）：worker 常把動作的 JSON 寫進 reply、action 留 null。整段 reply 就是一個 {command, args} 物件時當作 action——
    worker 的工具只有唯讀的量測，照做沒有風險（主對話仍維持「reply 裡的文字一律不執行」）。"""
    text = (reply or "").strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        d = json.loads(text)
    except ValueError:
        return None
    if isinstance(d, dict) and isinstance(d.get("command"), str) and d["command"].strip():
        return {"command": d["command"].strip(), "args": str(d.get("args") or "").strip()}
    return None


def _compact_features(f):
    """量測結果 → Frontmatter 的 key_metrics（只留判斷用得到的數字）。"""
    if f.get("kind") == "numeric":
        if f.get("constant"):
            return {"constant": _num(f.get("first")), "samples": f.get("samples")}
        out = {k: _num(f.get(k)) for k in ("min", "max", "mean", "std", "slope_per_sec")}
        out["samples"] = f.get("samples")
        if f.get("spike_count"):
            out["spike_count"] = f["spike_count"]
            first = (f.get("spikes") or [{}])[0]
            out["spike_timestamp"] = first.get("t_sec")
            out["spike_value"] = _num(first.get("value"))
        j = f.get("max_jump")
        if f.get("steps"):
            out["changes"] = [f"{_num(s.get('from'))} → {_num(s.get('to'))} @{s.get('t_sec')}" for s in f["steps"][:5]]
        elif j and j.get("delta"):
            out["max_jump"] = {"from": _num(j.get("from")), "to": _num(j.get("to")), "t": j.get("t_sec")}
        return out
    if f.get("kind") == "state":
        out = {"transitions": f.get("transition_count"), "first": f.get("first"), "last": f.get("last")}
        if f.get("transitions"):
            out["changes"] = [f"{_short(t.get('from'), 40)} → {_short(t.get('to'), 40)} @{t.get('t_sec')}" for t in f["transitions"][:5]]
        return out
    if f.get("kind") == "array":
        out = {k: f.get(k) for k in ("length_min", "length_max") if k in f}
        if f.get("element_mean"):
            em = f["element_mean"]
            out["element_mean"] = {k: _num(em.get(k)) for k in ("min", "max", "mean", "std")}
        return out
    return {"kind": f.get("kind")}


def _metrics_from_measure(js, analyzed):
    """mcap_feature_measure --json → (key_metrics {時間窗: {項目: 數字}}, 程式判斷的異常指標, data_type, 證據時間戳)。
    依名稱展開的對照表只留有變化的項目（DiagnosticArray 常有幾十個不變的）。"""
    metrics, ev_ts, data_type = {}, [], None
    for w in js.get("windows") or []:
        win = w.get("window") or {}
        wid = win.get("label") or "W?"
        wm = {}
        rate = w.get("rate") or {}
        if rate:
            wm["_rate"] = {k: rate.get(k) for k in ("messages", "avg_hz", "max_gap_sec") if rate.get(k) is not None}
            if rate.get("gaps"):
                wm["_rate"]["gaps"] = rate["gaps"]
                ev_ts += [g.get("start_sec") for g in rate["gaps"]]
            if rate.get("single_session"):
                wm["_rate"]["published_only"] = [rate.get("first_sec"), rate.get("last_sec")]
            if rate.get("started_late"):   # 中途才開始／中途停止發布：時間點進證據（時間線排得到）
                wm["_rate"]["started_at"] = rate.get("first_sec")
                ev_ts.append(rate.get("first_sec"))
            if rate.get("stopped_early"):
                wm["_rate"]["stopped_after"] = rate.get("last_sec")
                ev_ts.append(rate.get("last_sec"))
        for key in analyzed:
            kd = (w.get("keys") or {}).get(key)
            if not kd:
                continue
            data_type = data_type or kd.get("data_type")
            is_map = bool(kd.get("map_by")) or kd.get("category") == "kv"
            for label, f in (kd.get("entries") or {}).items():
                if is_map and not ((f.get("kind") == "state" and f.get("transition_count")) or
                                   (f.get("kind") == "numeric" and not f.get("constant"))):
                    continue
                name = key if label == "value" else (f"{key}[{label}]" if is_map else f"{key}.{label}")
                wm[name] = _compact_features(f)
                if f.get("kind") == "state":
                    ev_ts += [t.get("t_sec") for t in f.get("transitions") or []][:3]
                if f.get("kind") == "numeric" and f.get("spike_count"):
                    ev_ts.append((f.get("spikes") or [{}])[0].get("t_sec"))
                if f.get("kind") == "numeric" and f.get("steps"):
                    ev_ts += [s.get("t_sec") for s in f["steps"]][:3]
        metrics[wid] = wm
    return metrics, list(js.get("flags") or []), data_type, sorted({t for t in ev_ts if t is not None})

