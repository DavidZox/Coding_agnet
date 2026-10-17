"""AnalysisMixin：數據解析的多 agent 協同——analysis_run 偽技能（同 ops_run、result_recall：要呼叫模型，在 harness 的 process 裡做）。

只要有 .mcap 就能用的事實報告：量到什麼、什麼時候、Log 說了什麼；不做因果推論（原因要對照源碼另外分析——第九輪的源碼脈絡與因果推論
留在 root_cause_reference/）。一次分析一整段數據，最長 ANALYSIS_MAX_SECONDS 秒；更長的數據先用 mcap_slicer 切出要看的時間段。

0. 資料預備（程式）：rosout_parser --json 把 Log 去重成唯一訊號（L#：層級、Node、次數、每一次的時間戳、印出 Log 的檔案:行 函式——
   /rosout 的欄位，錄製時就在 MCAP 裡）；mcap_analyzer --json 讀全域 Topic Metadata。
1. Orchestrator 規劃（format=ANALYSIS_PLAN_SCHEMA）：看去重後的 Log 與 Topic Metadata，寫對問題的理解、挑出相關的 Log 訊號，把不同的
   Topic 指派給不同的 worker。程式檢查（L# 存在、Topic 可以分析、不重複、最多 N 個），有問題交回修一次，還是不行由程式補指派。
2. Workers（AnalysisWorker：每個一個乾淨的 session，可以平行）：只看自己的 Topic、Key 目錄與子任務（不給 Log 與問題），用
   mcap_feature_measure 自己決定量哪些 Key（整段數據）；寫局部報告（量到的現象）。程式核對用詞跟量測一致、不寫原因，有問題交回修一次。
3. 事實（程式，_build_facts）：從量測結果整理每個 Topic 的類別、事件與到最後的值；Topic 的事件與 Log 依時間排成時間線，前後
   ANALYSIS_ALIGN_SEC 秒內的 Log 與 Topic 變化互相對照（只寫時間差，不說誰造成誰），對不上的照實標出；0.1 秒內不同 Topic 一起變化的
   列成「同時」。
4. Synthesizer（format=ANALYSIS_SUMMARY_SCHEMA）：把事實寫成摘要。程式核對：不寫原因與推測、用詞跟量測一致，有問題交回修一次。
5. Orchestrator 檢查（format=ANALYSIS_CHECK_SCHEMA）：WARN 以上或規劃時挑的 Log 前後量到的 Topic 都沒有變化、數據裡還有沒量的 Topic 時，
   決定要不要補量（每一項對應一則 Log）；補派 worker，回到 3（最多補 max_rounds − 1 輪）。
6. 報告（程式組）：事實的表格、摘要、分析過程。

全部產物在 logs/analysis_jobs/<編號>/：job.json、events.jsonl、log_digest.md、topic_metadata.md、plan.json、
workers/W<n>_<topic>.md（局部報告）與 .transcript.md（worker 的完整對話）、prompts/（交給模型的輸入）、report.md。
回傳給主對話的是報告的重點（存成 #編號）。

設計依據同 ops_job：agent 之間只傳精簡、結構化的產物（ReWOO）；能由程式做的（去重、時間戳換算、數字、事實的整理、檢查）不交給模型；
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
    ANALYSIS_ALIGN_SEC,
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
    ANALYSIS_TOOL_RESULT_MAX_CHARS,
    ANALYSIS_WORKER_MAX_STEPS,
    ANALYSIS_WORKER_MODEL,
    ANALYSIS_WORKER_SCRIPTS,
    NUM_CTX,
    PROJECT_ROOT,
    THINK_EXTRA_PREDICT,
)
from .model_caps import think_arg
from .protocol import parse_agent_reply
from .schemas import (ANALYSIS_CHECK_SCHEMA, ANALYSIS_PLAN_SCHEMA, ANALYSIS_SUMMARY_SCHEMA, ANALYSIS_WORKER_REPLY_SCHEMA,
                      ANALYSIS_WORKER_REPORT_SCHEMA)

_PROMPTS = os.path.join(PROJECT_ROOT, ANALYSIS_AGENTS_DIRNAME)
ROLES = ("orchestrator", "worker", "synthesizer")
ROLE_LABELS = {"orchestrator": "Orchestrator", "worker": "Worker", "synthesizer": "Synthesizer"}
DEFAULT_QUESTION = "這段錄製期間發生了哪些狀態變化？"
WORKER_CATEGORIES = ("numeric", "vector", "state", "kv", "matrix", "array")
_CATEGORY_TEXT = {"numeric": "數值", "vector": "向量", "state": "狀態", "kv": "鍵值", "matrix": "矩陣", "array": "陣列",
                  "text": "文字", "time": "時間"}   # 同 _ros2_data_common.CATEGORY_LABELS（給 worker 看的 Key 目錄）
_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "UNKNOWN": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
_MARKERS = ("[ANALYSIS_DATA]", "[TARGET_CONTAINER]", "[CWD_CHANGED]", "[ROS2_WORKSPACE]")
_RECORDER_NODE = re.compile(r"^(rosbag2(_\w+)?|ros2_bag\w*)$")
_STATUS_TEXT = {"preparing": "資料預備", "planning": "Orchestrator 規劃", "working": "Workers 分析", "synthesizing": "Synthesizer 整合事實",
                "checking": "Orchestrator 檢查", "done": "完成", "failed": "失敗"}
_ACTIVE = ("preparing", "planning", "working", "synthesizing", "checking")
# 第九輪以前的選項（源碼脈絡、時間窗）：改成只做事實報告、整段量測之後拿掉，收到就說清楚，不要默默變成問題的一部分
_REMOVED_OPTIONS = ("--source", "--no-source", "--before", "--after")
_NOISE_TOPICS = ("/parameter_events", "/clock", "/events/write_split")   # ROS 2 框架與錄製工具自己的 Topic：不補量
_FEW_MESSAGES = 10     # 同量測工具的 EDGE_MIN_MESSAGES：更少的看不出固定頻率，不判斷中斷、頭尾沒有訊息不算開始或停止發布
_SUMMARY_MAX = ANALYSIS_SUMMARY_SCHEMA["properties"]["summary"]["maxLength"]   # 摘要的長度上限（格式限制，超過會被截斷在半句）
_TIMELINE_MAX = 60     # 報告的時間線最多幾列（超過時依重要性留，見 _build_facts）
_MAIN_TIMELINE_MAX = 15


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

    def load_analysis_settings(self):
        cfg = {"orchestrator": ANALYSIS_ORCHESTRATOR_MODEL, "worker": ANALYSIS_WORKER_MODEL,
               "synthesizer": ANALYSIS_SYNTHESIZER_MODEL, "orchestrator_think": ANALYSIS_THINK_DEFAULT,
               "worker_think": False, "synthesizer_think": ANALYSIS_THINK_DEFAULT,
               # 各角色的上下文長度（None＝NUM_CTX）。8 GB 顯卡上 deepseek-r1:8b 用 32k 時 KV cache 約 4.8 GB、四成跑到 CPU
               # （10.6 token/s）；Synthesizer 的輸入約 3k、輸出幾千，12288 就放得下（7.2 GB 中 6.3 GB 在 GPU，26.7 token/s）
               "orchestrator_ctx": None, "worker_ctx": None, "synthesizer_ctx": None,
               "data_root": ANALYSIS_DATA_ROOT,
               "container": "",
               "rounds": ANALYSIS_MAX_ROUNDS, "max_workers": ANALYSIS_MAX_WORKERS, "parallel": ANALYSIS_PARALLEL_WORKERS}
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
        """analysis_run 技能：解析參數 → 資料預備 → Orchestrator 規劃 → Workers → 事實（程式）→ Synthesizer 摘要 → Orchestrator 檢查
        （→ 補量 → 再整理一次）→ 報告。回傳給主對話的報告（或 [ERROR]）。"""
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
            self._job_status(job, "working")
            self._analysis_run_workers(job)
            text = self._analysis_conclude(job)   # 事實 → 摘要 → 檢查（→ 補量 → 再整理）→ 報告
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
        name = label or role   # prompts/ 的檔名（Orchestrator 的檢查：orchestrator_check）
        with self._analysis_lock:   # 交給模型的輸入留在 job 資料夾（prompts/）：對照、重播（只換 prompt 重跑一個角色）用
            n = job.setdefault("_prompt_n", {}).get(name, 0) + 1
            job["_prompt_n"][name] = n
        self._job_write(job, f"prompts/{name}{'' if n == 1 else f'_{n}'}.md", f"# system\n{system}\n\n# user\n{user}\n")
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
        try:
            dur = float(idx.get("duration_sec") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        if int(dur) > ANALYSIS_MAX_SECONDS:   # 以整秒算：錄 3 分鐘常是 180.05 秒
            return (f"[ERROR] 數據 {idx.get('label')} 長 {dur:g} 秒，超過一次分析的上限 {ANALYSIS_MAX_SECONDS} 秒。先用 mcap_slicer 切出"
                    f"要看的時間段（{ANALYSIS_MAX_SECONDS} 秒以內，例如 --window +60,+200），再用 analysis_run --data <切片資料夾> 分析。")
        out = self._analysis_tool("rosout_parser_cmd.py", [job["data"], "--json", "--top", "2000", "--all-nodes"])
        logs, _ = split_json_output(out)
        if logs and "signals" in logs:
            job["signals"] = logs["signals"]
            job["log_source"] = logs.get("source")
            job["log_total"] = logs.get("total_events")
        else:
            job["signals"], job["log_source"] = [], None
            job["log_error"] = _short(out, 300)
        digest = self._digest_text(job, limit=None, include_recorder=True)
        self._job_write(job, "log_digest.md", f"# 去重後的 Log（{job.get('log_source') or job.get('log_error')}）\n\n{digest}\n")
        self._job_write(job, "topic_metadata.md", f"# 全域 Topic Metadata：{idx.get('label')}\n\n{self._topics_text(job)}\n")
        workers_ok = sum(1 for t in idx["topics"] if t["role"] == "worker")
        self._analysis_note(job, f"📊 數據 {idx.get('label')}：{idx.get('duration_sec')} 秒、{len(idx['topics'])} 個 Topic（可分析 "
                                 f"{workers_ok} 個）；Log {job.get('log_total') or 0} 則 → {len(job['signals'])} 個唯一訊號"
                                 + (f"（{job['log_error']}）" if job.get("log_error") else ""))
        if not workers_ok:
            return "[ERROR] 這份數據沒有可以分析的 Topic（都是 Log、沒有訊息，或訊息型別無法解碼：自訂訊息要先用 ROS2_workspace_env 確認 Workspace）。"
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
        if others:
            lines.append("（不能指派給 worker：" + "、".join(others) + "）")
        return "\n".join(lines)

    # ---------------------------------------------------------------- 1. Orchestrator 規劃
    def _analysis_orchestrate(self, job):
        idx = job["index"]
        self._analysis_note(job, f"🧭 Orchestrator（{self.analysis_model('orchestrator')}）：對齊問題、挑相關的 Log 訊號、分派 Topic…")
        forced = [t for t in job["options"]["topics"] if any(x["topic"] == t and x["role"] == "worker" for x in idx["topics"])]
        must = f"\n使用者指定一定要分析的 Topic：{'、'.join(forced)}（要指派）" if forced else ""
        user = (f"【使用者的問題】\n{job['question']}\n\n"
                f"【數據】{idx.get('label')}：共 {idx.get('duration_sec')} 秒（時間都寫成距離數據開頭的秒數，+秒）\n\n"
                f"【去重後的 Log（唯一訊號；L# 是編號，×N 是出現次數；＠檔名:行 函式＝印出這則 Log 的程式位置）】\n{self._digest_text(job)}\n\n"
                f"【全域 Topic Metadata（可以指派給 worker 的 Topic 與它們的 Key）】\n{self._topics_text(job)}\n\n"
                f"【限制】最多指派 {job['max_workers']} 個 worker，每個 worker 一個不同的 Topic、量整段數據；Log（/rosout）不能指派——"
                "Log 由你負責看。" + must + "\n（每個欄位都用繁體中文寫）")
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
            plan["assignments"] = self._auto_assignments(job, plan["related"], job["max_workers"], forced)
            plan["auto_assigned"] = True
            issues.append("Orchestrator 沒有給出可用的指派，由程式依關聯度指派")
        plan["issues"] = issues
        job["plan"] = plan
        self._job_write(job, "plan.json", json.dumps({"plan": plan}, ensure_ascii=False, indent=1))
        atxt = "；".join(f"W{n}→{a['topic']}" for n, a in enumerate(plan["assignments"], 1))
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
        assigns, problems = self._clean_assignments(job, data.get("assignments"), forced)
        issues += problems
        return {"understanding": _short(data.get("understanding"), 500), "related": related, "assignments": assigns}, issues

    def _clean_assignments(self, job, items, forced):
        """模型的指派 → 檢查過的指派與問題清單：Topic 要在數據裡、可以分析、不重複，最多 N 個；使用者指定的 Topic 一定有。"""
        issues = []
        topics = {t["topic"]: t for t in job["index"]["topics"]}
        lower = {k.lower(): k for k in topics}
        assigns, seen = [], set()
        for a in items or []:
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
            subtask = _short(a.get("subtask") or "", 400) or "看這個 Topic 在整段數據裡的變化（狀態跳轉、數值的變化、訊息中斷、開始或停止發布）"
            assigns.append({"topic": name, "subtask": subtask})
        for t in forced:
            if t not in seen:
                assigns.insert(0, {"topic": t, "subtask": "使用者指定要分析這個 Topic：看它在整段數據裡的變化"})
                seen.add(t)
        if len(assigns) > job["max_workers"]:
            issues.append(f"指派了 {len(assigns)} 個 worker，超過上限 {job['max_workers']}（只保留前 {job['max_workers']} 個）")
            assigns = assigns[: job["max_workers"]]
        if not assigns:
            issues.append("沒有任何有效的指派：至少把一個可分析的 Topic 指派給 worker")
        return assigns, issues

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
        out = [{"topic": t, "subtask": "使用者指定要分析這個 Topic：看它在整段數據裡的變化"} for t in forced]
        for _, _, _, topic in scored:
            if len(out) >= n:
                break
            if topic not in forced:
                out.append({"topic": topic, "subtask": "看這個 Topic 在整段數據裡的變化（狀態跳轉、數值的變化、訊息中斷、開始或停止發布）"})
        return out

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
                    "summary": "", "analyzed_keys": [], "program_flags": [], "program_anomalies": [], "measure": {}}

    # ---------------------------------------------------------------- 3～6. 事實 → 摘要 → 檢查 → 報告
    def _analysis_conclude(self, job):
        """worker 量完之後：程式整理事實 → Synthesizer 寫摘要 → Orchestrator 檢查要不要補量（補量的 worker 量完回到這裡，最多補
        max_rounds − 1 輪）→ 程式組報告。補量之前的報告留成 report_r<n>.md。"""
        while True:
            rnd = len(job.setdefault("rounds", [])) + 1
            facts = _build_facts(job)
            self._job_status(job, "synthesizing")
            summary = self._analysis_summary(job, rnd, facts)
            fresh = []
            if rnd < job["max_rounds"]:
                self._job_status(job, "checking")
                fresh = self._analysis_check(job, rnd, facts, summary)
            job["report"] = _report_data(facts, summary)
            job["rounds"].append({"round": rnd, "workers": [w["n"] for w in job["workers"]], "followups": [a["topic"] for a in fresh]})
            report_md = self._render_report(job, facts, summary)
            self._job_write(job, "report.md", report_md)
            self._job_save(job)
            if not fresh:
                return self._report_for_main(job, facts, summary)
            self._job_write(job, f"report_r{rnd}.md", report_md)
            self._analysis_followups(job, rnd + 1, fresh)

    def _analysis_summary(self, job, rnd, facts):
        """Synthesizer：把程式整理的事實與各 worker 的局部報告寫成摘要（量到什麼、什麼時候、Log 說了什麼），不寫原因與推測。
        程式核對（_summary_issues），有問題交回修一次（prompts/synthesizer_2.md）；修完還在的，報告上標「程式核對：未修正」。
        JSON 壞掉時由程式寫一份（各 Topic 的類別與變化）。"""
        self._analysis_note(job, f"🧩 Synthesizer（{self.analysis_model('synthesizer')}）：把 {len(job['workers'])} 個 Topic 的事實寫成摘要"
                                 + (f"（第 {rnd} 輪）" if rnd > 1 else "") + "…")
        system, user = _read_prompt("synthesizer.md"), _summary_user(job, facts)
        data = self._analysis_session(job, "analysis_synthesizer", "synthesizer", system, user, ANALYSIS_SUMMARY_SCHEMA, 2048)
        text = _short((data or {}).get("summary"), _SUMMARY_MAX)
        issues = _summary_issues(job, text) if text else []
        if issues:
            self._analysis_note(job, f"🧩 摘要沒有通過程式核對，交回 Synthesizer 修正一次：{'；'.join(issues)[:200]}")
            fix = (user + "\n\n【上一版摘要】\n" + text + "\n\n【程式檢查發現的問題：修正後輸出完整的摘要】\n" + "\n".join(f"- {x}" for x in issues))
            data2 = self._analysis_session(job, "analysis_synthesizer", "synthesizer", system, fix, ANALYSIS_SUMMARY_SCHEMA, 2048)
            text2 = _short((data2 or {}).get("summary"), _SUMMARY_MAX)
            left = _summary_issues(job, text2) if text2 else None
            job.setdefault("summary_checks", []).append({"round": rnd, "issues": issues, "left": left})
            if text2:
                text, issues = text2, left
        if not text:
            self._analysis_note(job, "🧩 Synthesizer 沒有給出摘要，由程式整理一份（各 Topic 的類別與變化）")
            text, issues = _fallback_summary(facts), []
        return {"summary": text, "unresolved": list(issues or [])}

    def _analysis_check(self, job, rnd, facts, summary):
        """Orchestrator 檢查（看完事實與摘要）：WARN 以上或規劃時挑的 Log，前後 ANALYSIS_ALIGN_SEC 秒內量到的 Topic 都沒有變化，
        而數據裡還有沒量的 Topic——問它要不要補量、補哪個 Topic（每一項寫它對應哪一則 Log）。程式核對：Log 要在那份清單裡、
        Topic 要可以分析而且還沒量過、最多 ANALYSIS_FOLLOWUP_WORKERS 個；不符合的不補（不交回）。
        沒有那種 Log、或沒有可以補的 Topic 就不問：沒有對應的變化本身就是事實，報告照實寫。"""
        analyzed = {w["topic"] for w in job["workers"]}
        left = [t for t in job["index"]["topics"] if t["role"] == "worker" and t["topic"] not in analyzed and t["topic"] not in _NOISE_TOPICS]
        lonely = facts["unmatched_logs"]
        rec = {"round": rnd, "unmatched": [x["id"] for x in lonely], "asked": False, "followups": [], "issues": []}
        job.setdefault("checks", []).append(rec)
        if not lonely or not left:
            rec["why"] = "每則相關的 Log 前後都有量到的變化" if not lonely else "數據裡沒有還沒量的 Topic"
            self._analysis_note(job, f"🧭 檢查：{rec['why']}，不補量", kind="plan")
            return []
        rec["asked"] = True
        self._analysis_note(job, f"🧭 Orchestrator（{self.analysis_model('orchestrator')}）：{'、'.join(x['id'] for x in lonely)} 前後量到的 "
                                 "Topic 都沒有變化，檢查要不要補量…")
        data = self._analysis_session(job, "analysis_orchestrator_check", "orchestrator", _read_prompt("orchestrator_check.md"),
                                      _check_user(job, facts, summary, lonely, left), ANALYSIS_CHECK_SCHEMA, 1536,
                                      label="orchestrator_check")
        ok_ids = {x["id"] for x in lonely}
        lower = {t["topic"].lower(): t["topic"] for t in left}
        fresh, problems = [], []
        for f in (data or {}).get("followups") or []:
            f = f if isinstance(f, dict) else {}
            m = re.search(r"L\d+", str(f.get("signal") or "").upper())
            sid = m.group() if m else ""
            raw = str(f.get("topic") or "").strip()
            topic = lower.get((raw if raw.startswith("/") else "/" + raw).lower())
            if sid not in ok_ids:
                problems.append(f"{raw}：對應的 Log「{sid or f.get('signal')}」不在「前後量到的 Topic 都沒有變化」的清單裡，不補")
            elif not topic:
                problems.append(f"{raw}：不是還沒量、可以分析的 Topic，不補")
            elif topic in [a["topic"] for a in fresh]:
                continue
            elif len(fresh) >= ANALYSIS_FOLLOWUP_WORKERS:
                problems.append(f"{topic}：一次最多補 {ANALYSIS_FOLLOWUP_WORKERS} 個，不補")
            else:
                fresh.append({"topic": topic, "signal": sid,
                              "subtask": _short(f.get("subtask") or "", 400) or f"看這個 Topic 在 {sid} 前後的變化"})
        rec.update(followups=[dict(a) for a in fresh], issues=problems)
        self._analysis_note(job, ("🔁 Orchestrator 指派補量：" + "；".join(f"{a['topic']}（為了 {a['signal']}）" for a in fresh)) if fresh else
                            ("🔁 Orchestrator 判斷不用補量，分析結束" + (f"（程式檢查：{'；'.join(problems)[:160]}）" if problems else "")),
                            kind="plan")
        return fresh

    def _analysis_followups(self, job, rnd, fresh):
        """補量：Orchestrator 指派的還沒量的 Topic，流程同 worker（整段數據）。"""
        start = len(job["workers"])
        for a in fresh:
            a["round"] = rnd
        job["plan"].setdefault("followups", []).extend(fresh)
        self._job_write(job, "plan.json", json.dumps({"plan": job["plan"]}, ensure_ascii=False, indent=1))
        self._analysis_note(job, f"🔁 補派 {len(fresh)} 個 worker：" + "；".join(f"W{start + i}→{a['topic']}" for i, a in enumerate(fresh, 1)),
                            kind="plan")
        self._job_status(job, "working")
        par = max(1, min(int(self.analysis_cfg.get("parallel") or 1), len(fresh)))
        with ThreadPoolExecutor(max_workers=par) as ex:
            futures = [ex.submit(self._analysis_one_worker, job, start + i, a) for i, a in enumerate(fresh, 1)]
            job["workers"] += [f.result() for f in futures]
        self._job_save(job)

    def _render_report(self, job, facts, summary):
        """報告（Frontmatter Markdown）：摘要、各 Topic 的結果、時間線、同時發生的變化、前後沒有變化的 Log、沒有分析的 Topic、分析過程。
        除了摘要，全部由程式從量測結果與 Log 整理。"""
        plan = job["plan"]
        tags = {row["topic"]: row["tags"] for row in facts["topics"]}
        fm = {"artifact": "fact_report", "job": job["id"], "question": job["question"], "data": job.get("data_label"),
              "data_path": job["data"], "time_range": job.get("time_range"), "related_signals": [r["id"] for r in plan["related"]],
              "workers": [{"topic": w["topic"], "analyzed_keys": w.get("analyzed_keys"), "tags": tags.get(w["topic"]), "file": w.get("file")}
                          for w in job["workers"]],
              "unmatched_logs": [x["id"] for x in facts["unmatched_logs"]], "models": job["models"]}
        if plan.get("followups"):
            fm["followups"] = [{"topic": a["topic"], "signal": a.get("signal")} for a in plan["followups"]]
        lines = [frontmatter(fm), f"# 數據事實報告\n\n**問題**：{job['question']}\n\n**數據**：{job.get('data_label')}（{job['data']}，"
                                  f"{job.get('duration_sec')} 秒）\n",
                 f"> 只列數據裡量到的事實與 Log 的原文。「前後 {ANALYSIS_ALIGN_SEC:g} 秒內」只是時間上的對照，不代表誰造成誰；"
                 "原因要對照源碼另外分析。\n",
                 "## 摘要（Synthesizer）\n" + (summary["summary"] or "-") + "\n"
                 + "".join(f"- ⚠️ 程式核對：未修正：{x}\n" for x in summary["unresolved"])]
        lines.append("## 各 Topic 的結果\n| Topic | 類別 | 發布 | 變化 | 到最後 |\n|---|---|---|---|---|\n" + "\n".join(
            f"| W{r['w']} {r['topic']} | {'、'.join(r['tags'])} | {_cell(r['publish'])} | {_cell('；'.join(r['changes']) or '-')} | "
            f"{_cell('；'.join(r['end']) or ('；'.join(r['still'][:4]) + '（沒有變化）' if r['still'] else '-'))} |"
            for r in facts["topics"]) + "\n")
        if facts["timeline"]:
            lines.append(f"## 時間線\n| 時間 | 來源 | 事件 | 前後 {ANALYSIS_ALIGN_SEC:g} 秒內 |\n|---|---|---|---|\n" + "\n".join(
                f"| {r['time']} | {_cell(r['source'])} | {_cell(r['event'])} | {_cell(r['near'])} |" for r in facts["timeline"])
                + (f"\n\n（另有 {facts['timeline_hidden']} 個事件沒有列出：多半是同一個項目反覆切換，次數在「各 Topic 的結果」）"
                   if facts.get("timeline_hidden") else "") + "\n")
        if facts["same_time"]:
            lines.append(f"## 同時發生的變化（{ANALYSIS_SAME_TIME_SEC:g} 秒內）\n" + "\n".join(
                f"- {g['time']}：{'、'.join(g['events'])}" for g in facts["same_time"]) + "\n")
        if facts["unmatched_logs"]:
            lines.append(f"## 前後 {ANALYSIS_ALIGN_SEC:g} 秒內量到的 Topic 都沒有變化的 Log\n" + "\n".join(
                f"- {x['id']} {x['level']} {_plus(x['t'])} {x['node']}：{_short(x['text'], 160)}{x['where']}" for x in facts["unmatched_logs"]) + "\n")
        if facts["not_analyzed"]:
            lines.append("## 沒有分析的 Topic\n" + "\n".join(f"- {k}：{'、'.join(v)}" for k, v in facts["not_analyzed"].items()) + "\n")
        # Orchestrator 的理解與挑訊號的理由是規劃用的文字（可能有推測），不放進事實報告；完整的在 plan.json
        steps = ["- Orchestrator 挑的相關 Log：" + ("、".join(r["id"] for r in plan["related"]) or "（沒有）")]
        steps += [f"- W{w['n']} {w['topic']}：{_short(w.get('subtask'), 160)}"
                  + (f"（第 {w['round']} 輪補量，為了 {w.get('signal')}）" if w.get("round") else "")
                  + f"→ 量了 {'、'.join(w.get('analyzed_keys') or []) or '（沒有）'}" + ("（系統代選 Key）" if w.get("key_selection") == "fallback" else "")
                  + (f"；失敗：{w.get('error')}" if w.get("status") == "failed" else "") + f" `{w.get('file') or '-'}`"
                  for w in job["workers"]]
        for c in job.get("checks") or []:
            steps.append(f"- 第 {c['round']} 輪的檢查：" + (("補量 " + "、".join(f"{a['topic']}（為了 {a['signal']}）" for a in c["followups"]))
                                                        if c["followups"] else ("Orchestrator 判斷不用補量" if c["asked"] else f"不用問（{c.get('why')}）"))
                         + (f"（程式檢查：{'；'.join(c['issues'])[:200]}）" if c.get("issues") else ""))
        if plan.get("issues"):
            steps.append(f"- 規劃的程式檢查：{'；'.join(plan['issues'])[:300]}")
        lines.append("## 分析過程\n" + "\n".join(steps) + "\n")
        return "\n".join(lines)

    def _report_for_main(self, job, facts, summary):
        """回傳給主對話的報告重點（以 ANALYSIS_REPORT_HEAD 開頭：不再摘要、整份進主對話，並存成 #編號）。"""
        n = len(job["workers"])
        lines = [f"{ANALYSIS_REPORT_HEAD}（job {job['id']}：{n} 個 worker、模型呼叫 {{CALLS}} 次、{{SECONDS}} 秒）",
                 f"問題：{job['question']}", f"數據：{job.get('data_label')}（{job.get('duration_sec')} 秒）",
                 f"摘要：{summary['summary']}"]
        if summary["unresolved"]:
            lines.append("程式核對：未修正（摘要裡這幾處跟量到的事實對不上，回答時以下面的事實為準）：" + "；".join(
                _short(x, 160) for x in summary["unresolved"]))
        lines.append("各 Topic：\n" + "\n".join(
            f"- W{r['w']} {r['topic']}｜{'、'.join(r['tags'])}｜{r['publish']}"
            + (f"｜{'；'.join(r['changes'][:3])}" if r["changes"] else "") + (f"｜到最後：{'；'.join(r['end'][:3])}" if r["end"] else "")
            for r in facts["topics"]))
        if facts["timeline"]:
            rows = _top_rows(facts["timeline"], _MAIN_TIMELINE_MAX)
            lines.append(f"時間線（重點 {len(rows)}/{len(facts['timeline']) + facts.get('timeline_hidden', 0)} 列）：\n" + "\n".join(
                f"- {r['time']}｜{r['source']}｜{_short(r['event'], 140)}｜前後 {ANALYSIS_ALIGN_SEC:g} 秒內：{r['near']}" for r in rows))
        if facts["same_time"]:
            lines.append("同時發生的變化：" + "；".join(f"{g['time']} {'、'.join(g['events'])}" for g in facts["same_time"][:5]))
        if facts["unmatched_logs"]:
            lines.append(f"前後 {ANALYSIS_ALIGN_SEC:g} 秒內量到的 Topic 都沒有變化的 Log："
                         + "；".join(f"{x['id']} {_plus(x['t'])} {x['node']}：{_short(x['text'], 80)}" for x in facts["unmatched_logs"][:6]))
        if facts["not_analyzed"]:
            lines.append("沒有分析的 Topic：" + "；".join(f"{k}：{'、'.join(v[:8])}" for k, v in facts["not_analyzed"].items()))
        lines.append(f"完整報告：logs/{ANALYSIS_JOBS_DIRNAME}/{job['id']}/report.md（各 worker 的局部報告在 workers/）")
        lines.append("（依這份報告回答使用者：只陳述報告裡的事實——時間、數值、狀態、Log 的原文。報告沒有判斷原因：使用者問「為什麼」時，"
                     "照事實說明發生了什麼、先後順序，並說明原因要對照源碼另外分析）")
        return "\n".join(lines)


# ---------------------------------------------------------------- 用詞：worker 的局部報告與 Synthesizer 的摘要共用一套
# 不是事實的寫法：原因、誰造成誰、推測。事實層只寫量到什麼、什麼時候
_NOT_FACT_WORDS = ("導致", "造成", "引起", "觸發", "根因", "原因", "證實", "證明", "排除", "歸因", "因此", "所以", "由於", "因為",
                   "可能是", "推測", "疑似", "或許")
_INTERRUPT_WORDS = ("中斷", "間歇", "斷斷續續", "丟失", "遺失")   # 不用「斷訊」：「診斷訊息」裡就有
# 否定的說法不算：否定詞到子句結束（逗號、句號）都算否定的範圍——「沒有任何狀態跳轉、數值尖峰或訊息中斷」「是否中斷」；
# 工具那一行的名稱「程式判斷的異常（訊息中斷）」也不算
_NEGATED_INTERRUPT = re.compile(r"程式判斷的異常（訊息中斷）|(?:沒有|無|未|並非|不是|不屬於|而非|不算|是否|有沒有)[^，。；\n]{0,25}")
_INTERRUPT_AS_TIME = re.compile(r"(?:中斷|間歇)(?:後|之後|前|之前|期間|時|的那一刻)")   # 有量到的中斷時：拿它當時間參考（「中斷後 0.51 秒」）
_SIGNAL_REF = re.compile(r"(?<![A-Za-z0-9_])L(\d+)(?![0-9])")


def _interrupt_words(text):
    """文字（去掉否定的說法之後）用了哪些「中斷、間歇、丟失」類的字。"""
    t = _NEGATED_INTERRUPT.sub("", text or "")
    return [w for w in _INTERRUPT_WORDS if w in t]


def _not_fact_words(text, quoted=""):
    """寫了哪些「不是事實」的字（原因、誰造成誰、推測）；quoted（Log 原文、量到的字串）裡本來就有的不算。"""
    return [w for w in _NOT_FACT_WORDS if w in (text or "") and w not in quoted]


# ---------------------------------------------------------------- worker 的任務說明與局部報告的程式核對
_WORKER_REPORT_ASK = (
    "[系統] 量測結束，寫這個 Topic 的局部報告：analyzed_keys＝你實際量測過的 Key；"
    "summary＝三到六句，照量測工具的說法寫量到的現象（什麼時候開始／停止發布、數值、跳轉、有沒有訊息中斷），引用數字與時間（+秒）。"
    "沒有量到的東西不要寫；不寫原因、不推測，也不寫跟其他 Topic、Log 的關係。")


def _worker_subtask(job, text):
    """交給 worker 的子任務：L#（Log 訊號的編號）換成它出現的時間（+秒）。worker 看不到 Log，L# 對它沒有意義，
    還會讓它在局部報告裡引用 Log、寫「證實 L17 時…」（實測 26b：子任務引用 L# 38/40、局部報告引用 L# 29/40）。"""
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


def _worker_report_issues(rep, anomalies, flags):
    """局部報告跟量測工具的結果對不對得上（程式核對，有問題交回 worker 修一次）：
    - 量測沒有訊息中斷，報告卻寫「中斷／間歇／丟失」（實測 26b：/cmd_vel_raw 一段完整的發布寫成「數據中斷」32/40）；
    - 寫了原因、誰造成誰或推測（_NOT_FACT_WORDS）：worker 只描述量到的現象。"""
    issues = []
    text = str(rep.get("summary") or "")
    changes = [f for f in flags if f not in anomalies]
    words = _interrupt_words(text) if not anomalies else []
    if words:
        issues.append(f"你寫了「{'、'.join(words)}」，但量測工具量到的沒有訊息中斷"
                      + (f"（量到的是：{'；'.join(changes[:3])}）" if changes else "")
                      + "——照工具的說法寫：開始發布、停止發布、一段完整的發布、沒有訊息，不要寫成中斷、間歇或丟失")
    bad = _not_fact_words(text)
    if bad:
        issues.append(f"你寫了「{'、'.join(bad)}」：局部報告只寫這個 Topic 量到的現象與時間，不寫原因、不推測，"
                      "也不寫它跟 Log 或其他 Topic 的關係")
    return issues


class AnalysisWorker:
    """一個 Topic 的數據量測手：乾淨的 session，只看自己的 Topic 與 Key 目錄，自己決定量測哪些 Key（整段數據）。"""

    def __init__(self, agent, job, n, assignment):
        self.a, self.job, self.n, self.asg = agent, job, n, assignment
        self.topic = assignment["topic"]
        self.entry = next(t for t in job["index"]["topics"] if t["topic"] == self.topic)
        self.model = agent.analysis_model("worker")
        self.think = think_arg(self.model, agent.analysis_think("worker"))
        # ANALYSIS_WINDOWS 空的＝量測工具量整段數據（不讓 worker 自己挑一段：事實要完整）
        self.env = {"ANALYSIS_DATA": job["data"], "ANALYSIS_TOPIC": self.topic, "ANALYSIS_WINDOWS": ""}
        self.measured = {}
        self.calls = []
        self.key_selection = "worker"
        self.tag = f"W{n} {self.topic}"

    # ---- 任務說明
    def _brief(self):
        idx = self.job["index"]
        base, end = idx["start_ns"], idx["end_ns"]
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
        # 只給子任務（要觀察的現象與時間），不給使用者的問題與 Orchestrator 的理解：理解裡有 Log 與推測的原因（實測 26b 30/40），
        # worker 照著推測寫「證實 L17 時 /cmd_vel_raw 中斷」，跟量到的「一段完整的發布、中間沒有中斷」相反（32/40）
        parts = [f"【你的子任務】{_worker_subtask(self.job, self.asg['subtask'])}",
                 f"【你負責的 Topic】{self.topic}（{self.entry['type']}，整段 {self.entry['message_count']} 則、"
                 f"{self.entry.get('avg_frequency_hz', '-')} Hz）——其他 Topic 有別的 worker 負責，你只量這一個",
                 f"【數據】整段 {_rel(base, base)}～{_rel(end, base)}（{(end - base) / 1e9:.1f} 秒）：量測工具量的是整段，不用寫時間窗",
                 "【這個 Topic 可以量測的 Key】（Key｜類別｜維度｜ROS 型別｜抽樣看到的）\n" + "\n".join(kl)]
        if skip:
            parts.append(f"【不量測的欄位】{'、'.join(skip)}（文字或時間；Log 與自由文字由 Orchestrator 負責）")
        return "\n\n".join(parts)

    def _report(self, msgs):
        """請 worker 寫局部報告（一次呼叫）→ dict（壞掉回 {}）。"""
        try:
            rep = json.loads(self._chat(msgs, ANALYSIS_WORKER_REPORT_SCHEMA, 2048))
        except (ValueError, TypeError, KeyError):
            rep = {}
        return tidy(rep) if isinstance(rep, dict) else {}

    def _chat(self, msgs, schema, predict):
        res = self.a._timed_chat("analysis_worker", model=self.model, messages=msgs, format=schema,
                                 options={"temperature": 0.2, "num_ctx": self.a.analysis_ctx("worker"),
                                          "num_predict": predict + (THINK_EXTRA_PREDICT if self.think else 0)}, think=self.think)
        with self.a._analysis_lock:
            self.job["model_calls"] += 1
        return res["message"]["content"]

    # ---- 動作的檢查與執行
    def _normalize(self, action):
        """worker 的 action → (腳本, 參數) 或 (None, 錯誤訊息)。數據路徑、--topic 一律由系統決定；時間窗（--window、--around…）
        拿掉——量整段。"""
        command = str(action.get("command") or "").strip()
        token = os.path.basename(command.split()[0]) if command else ""
        stem = token[:-3] if token.endswith(".md") else token
        script = self.a._normalize_script_name(stem)
        if script not in ANALYSIS_WORKER_SCRIPTS:
            return None, (f"[ERROR] worker 只能用 mcap_feature_measure（量測特徵）與 mcap_analyzer（看 Key、原始值）："
                          f"action.command 填 scripts/mcap_feature_measure_cmd.py，args 填 --key <Key>。收到：{command}")
        args = self.a._parse_script_args(script, action.get("args") or "")
        out, keys, i = [], [], 0
        keep = {"--key", "--filter", "--topic", "--preview"}
        drop = {"--window", "--around", "--before", "--after"}
        while i < len(args):
            t = args[i]
            if t in keep | drop and i + 1 < len(args):
                v = args[i + 1]
                if t == "--topic":
                    norm = v if v.startswith("/") else "/" + v
                    if norm != self.topic:
                        return None, f"[ERROR] 你只負責 {self.topic}；{v} 由別的 worker 負責（或不需要分析）。只量測 {self.topic} 的 Key。"
                elif t == "--key":
                    keys.append(v)
                    out += [t, v]
                elif t in keep:
                    out += [t, v]
                i += 2
                continue
            if t in ("--all-entries",):
                out.append(t)
            i += 1   # 其他（位置參數的數據路徑、--json、--refresh…）：系統決定，丟掉
        if script == "mcap_feature_measure_cmd.py" and not keys:
            return None, "[ERROR] 要用 --key 指定要量測的 Key（可以一次寫好幾個 --key），Key 名稱照【這個 Topic 可以量測的 Key】。"
        return script, ["--topic", self.topic] + out

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
        msgs.append({"role": "user", "content": _WORKER_REPORT_ASK})
        rep = self._report(msgs)
        analyzed = [k for k in rep.get("analyzed_keys") or [] if k in self.measured] or list(self.measured)
        # 事實一律由程式量：worker 分析過的 Key，加上這個 Topic 全部的狀態類 Key（實測 boot 5 次裡 worker 挑的狀態 Key 有 3 種組合，
        # 同一個 Topic 的事實就有 3 種；數值類照 worker 挑的——依名稱展開的數值很多，雜訊大）
        state = {k["key"] for k in self.entry.get("keys", []) if k["category"] == "state" and not k["key"].startswith("header.")}
        order = {k["key"]: i for i, k in enumerate(self.entry.get("keys", []))}   # 照 Topic Metadata 的順序：報告每次一樣（不看 worker 先量哪個）
        fact_keys = sorted(set(analyzed) | state, key=lambda k: (order.get(k, order.get(k.rsplit(".", 1)[0], len(order))), k)) \
            if analyzed else []
        measure, flags, anomalies = {}, [], []
        if fact_keys:
            args = ["--topic", self.topic, "--json"] + [x for k in fact_keys for x in ("--key", k)]
            js, _ = split_json_output(a._analysis_tool("mcap_feature_measure_cmd.py", args, extra_env=self.env))
            if js:
                measure = _measure_facts(js, fact_keys)
                flags = list(js.get("flags") or [])
                anomalies = list(js["anomalies"]) if "anomalies" in js else _gap_flags(measure)   # 舊版工具沒有 anomalies
        # 程式核對局部報告跟量測：用詞不能跟量測相反（停止發布寫成中斷）、不寫原因與推測；有問題交回修一次
        issues = _worker_report_issues(rep, anomalies, flags) if rep else []
        left = []
        if issues:
            a._analysis_note(job, f"🛠 {self.tag}：局部報告跟量測不符，交回修正一次：{'；'.join(issues)[:160]}", kind="worker_step", worker=self.n)
            msgs.append({"role": "assistant", "content": json.dumps(rep, ensure_ascii=False)})
            msgs.append({"role": "user", "content": "[系統] 程式檢查局部報告，發現跟量測工具的結果不符：\n" + "\n".join(f"- {x}" for x in issues)
                                                    + "\n照量測工具的結果修正，重新輸出完整的局部報告（同樣的 JSON 格式）。"})
            rep2 = self._report(msgs)
            if rep2:
                rep = dict(rep2, analyzed_keys=rep.get("analyzed_keys"))   # 量測過的 Key 照第一版（數字已經照它重量）
                left = _worker_report_issues(rep, anomalies, flags)
        result = {"n": self.n, "topic": self.topic, "type": self.entry["type"], "subtask": self.asg["subtask"], "status": "done",
                  "analyzed_keys": analyzed, "fact_keys": fact_keys, "key_selection": self.key_selection,
                  "summary": _short(rep.get("summary"), 900) or "（worker 沒有寫摘要）",
                  "program_flags": flags, "program_anomalies": anomalies, "measure": measure,
                  "data_type": measure.get("data_type"), "steps": steps, "calls": len(self.calls)}
        if self.asg.get("round"):   # 補量的 worker：第幾輪、為了哪一則 Log
            result["round"], result["signal"] = self.asg["round"], self.asg.get("signal")
        if issues:   # 程式核對局部報告發現的問題（交回修了一次）與修完還在的
            result["report_issues"], result["report_issues_left"] = issues, left
        result["file"] = self._write(result, msgs)
        row, _ = _topic_facts(result, job["index"]["start_ns"] / 1e9)
        a._analysis_note(job, f"✅ {self.tag}：{'、'.join(row['tags'])}（{'、'.join(analyzed) or '沒有量測'}；{steps} 輪）",
                         kind="worker_done", worker=self.n)
        return result

    def _write(self, result, msgs):
        idx = self.job["index"]
        fm = {"artifact": "worker_report", "job": self.job["id"], "worker": self.n, "topic": self.topic,
              "message_type": self.entry["type"], "data_type": result["data_type"], "time_range": [_sec3(idx["start_ns"]), _sec3(idx["end_ns"])],
              "analyzed_keys": result["analyzed_keys"], "fact_keys": result["fact_keys"], "key_selection": result["key_selection"],
              "program_flags": result["program_flags"], "program_anomalies": result["program_anomalies"],
              "measure": result["measure"], "model": self.model, "steps": result["steps"]}
        if result.get("round"):   # 補量的 worker（第幾輪、為了哪一則 Log）
            fm["round"], fm["signal"] = result["round"], result.get("signal")
        if result.get("report_issues"):   # 程式核對局部報告：交回修正的問題、修完還在的
            fm["report_issues"] = result["report_issues"]
            fm["report_issues_left"] = result["report_issues_left"]
        calls = "\n".join(f"- {'✅' if c['ok'] else '❌'} `{c['script'].replace('_cmd.py', '')} {' '.join(c['args'][2:])}`：{c['head']}"
                          for c in self.calls) or "（沒有）"
        body = f"## 子任務\n{result['subtask']}\n\n## 分析摘要\n{result['summary']}\n\n## 量測紀錄\n{calls}\n"
        rel = f"workers/W{self.n}_{_slug(self.topic)}.md"
        self.a._job_write(self.job, rel, frontmatter(fm) + "\n" + body)
        tr = "\n\n".join(f"### {m['role']}\n{m['content']}" for m in msgs)
        self.a._job_write(self.job, f"workers/W{self.n}_{_slug(self.topic)}.transcript.md", tr)
        return rel


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


# ---------------------------------------------------------------- 量測結果 → 事實
def _measure_facts(js, analyzed):
    """mcap_feature_measure --json（整段數據）→ 這個 Topic 量到的事實：訊息流（則數、頻率、第一則／最後一則、中斷、中途開始或停止）
    與每個項目（Key、向量的分量、依名稱展開的項目）的特徵。時間都是 epoch 秒；依名稱展開的對照表只留有變化的項目
    （DiagnosticArray 常有幾十個不變的）。"""
    win = (js.get("windows") or [{}])[0]
    rate = win.get("rate") or {}
    out = {"rate": {k: rate[k] for k in ("messages", "avg_hz", "max_gap_sec", "first_sec", "last_sec", "gaps", "started_late",
                                         "stopped_early", "single_session", "warmup_start", "starts_after_window_sec")
                    if rate.get(k) not in (None, False, [])},
           "items": []}
    for key in analyzed:
        kd = (win.get("keys") or {}).get(key)
        if not kd:
            continue
        out.setdefault("data_type", kd.get("data_type"))
        is_map = bool(kd.get("map_by")) or kd.get("category") == "kv"
        for label, f in (kd.get("entries") or {}).items():
            kind = f.get("kind")
            if is_map and not ((kind == "state" and f.get("transition_count")) or (kind == "numeric" and not f.get("constant"))):
                continue
            item = {"name": key if label == "value" else (f"{key}[{label}]" if is_map else f"{key}.{label}"), "kind": kind}
            if kind == "state":
                item.update(first=f.get("first"), last=f.get("last"), count=f.get("transition_count") or 0,
                            changes=[{"t": x.get("t_sec"), "from": x.get("from"), "to": x.get("to")} for x in f.get("transitions") or []])
            elif kind == "numeric":
                item.update(first=_num(f.get("first")), last=_num(f.get("last")), min=_num(f.get("min")), max=_num(f.get("max")),
                            mean=_num(f.get("mean")), constant=bool(f.get("constant")))
                if f.get("steps"):   # 只有幾種值（速度指令 0／0.1、設定值）：每次切換的時間
                    item.update(count=f.get("step_count") or len(f["steps"]),
                                changes=[{"t": s.get("t_sec"), "from": _num(s.get("from")), "to": _num(s.get("to"))} for s in f["steps"]])
                if f.get("spike_count"):
                    item.update(spike_count=f["spike_count"],
                                spikes=[{"t": s.get("t_sec"), "value": _num(s.get("value"))} for s in f.get("spikes") or []])
            elif kind == "array":
                item.update({k: f.get(k) for k in ("length_min", "length_max") if k in f})
            out["items"].append(item)
    return out


def _gap_flags(measure):
    """量到的訊息中斷 → 程式判斷的異常（舊版量測工具的 --json 沒有 anomalies 時用）。"""
    gaps = (measure.get("rate") or {}).get("gaps") or []
    return [f"訊息中斷 {len(gaps)} 次（最長 {max(float(g.get('duration_sec') or 0) for g in gaps):g} 秒）"] if gaps else []


def _path(name, it, base, limit=3):
    """一個項目的變化：「mode：NORMAL → LIMITED（+21.76s）→ NORMAL（+30.10s）」；超過 limit 次只列前幾次與總次數。"""
    chs = it.get("changes") or []
    s = f"{name}：{_val(chs[0]['from'] if chs else it.get('first'))}"
    for c in chs[:limit]:
        s += f" → {_val(c['to'])}（{_plus(float(c['t']) - base)}）"
    n = it.get("count") or len(chs)
    return s + (f" …（共 {n} 次）" if n > limit else "")


def _topic_facts(w, base):
    """一個 worker 量到的事實 → (這個 Topic 的一列, 事件清單)。base＝數據開頭（epoch 秒）。
    列：類別（tags）、發布、變化、到最後的值（跟開頭不同的項目）、沒有變化的項目。
    事件：{"t": +秒, "w", "topic", "src", "text", "rank"}——rank 是時間線太長時的保留順序（小的先留）。"""
    tag = f"W{w['n']} {w['topic']}"
    row = {"w": w["n"], "topic": w["topic"], "type": w.get("type"), "tags": [], "publish": "", "changes": [], "end": [], "still": []}
    evs = []
    if w.get("status") == "failed":
        row.update(tags=["量測失敗"], publish=_short(w.get("error"), 120))
        return row, evs
    m = w.get("measure") or {}
    rate, items = m.get("rate") or {}, m.get("items") or []

    def ev(t_epoch, text, rank):
        if t_epoch is not None:
            evs.append({"t": round(float(t_epoch) - base, 3), "w": w["n"], "topic": w["topic"], "src": tag, "text": text, "rank": rank})

    tags = []
    n = rate.get("messages") or 0
    if not m:
        row.update(tags=["沒有量測結果"], publish="沒有量測結果（worker 沒有量到 Key，或量測工具沒有回傳）")
        return row, evs
    if not n:
        tags.append("沒有訊息")
        publish = "整段沒有訊息"
    else:
        first, last = rate.get("first_sec"), rate.get("last_sec")
        parts = [f"{n} 則" + (f"，平均 {rate['avg_hz']} Hz" if rate.get("avg_hz") and n >= _FEW_MESSAGES else "")]   # 則數少時平均頻率沒有意義
        gaps = rate.get("gaps") or []
        if rate.get("single_session"):
            parts.append(f"只在 {_plus(first - base)}～{_plus(last - base)} 連續發布（一段完整的發布，中間沒有中斷）")
            ev(first, "開始發布（之前沒有訊息）", 1)
            ev(last, "停止發布（之後到數據結束沒有訊息）", 1)
        else:
            if rate.get("started_late"):
                parts.append(f"{_plus(first - base)} 才開始發布")
                ev(first, "開始發布（之前沒有訊息）", 1)
            elif rate.get("warmup_start"):
                parts.append(f"第一則在 {_plus(first - base)}（錄製剛開始）")
            if rate.get("stopped_early"):
                parts.append(f"{_plus(last - base)} 之後停止發布（到數據結束沒有訊息）")
                ev(last, "停止發布（之後到數據結束沒有訊息）", 1)
        for g in gaps:
            s, d = float(g.get("start_sec")), float(g.get("duration_sec") or 0)
            ev(s, f"訊息中斷 {d:.2f} 秒", 1)
            ev(s + d, f"恢復發布（中斷 {d:.2f} 秒之後的第一則）", 1)
        if gaps:
            parts.append(f"訊息中斷 {len(gaps)} 次（最長 {max(float(g.get('duration_sec') or 0) for g in gaps):.2f} 秒）")
            tags.append("訊息中斷")
        if rate.get("single_session") or rate.get("started_late") or rate.get("stopped_early"):
            tags.append("開始或停止發布")
        if n < _FEW_MESSAGES:
            parts.append(f"則數少（不到 {_FEW_MESSAGES} 則看不出固定頻率：不判斷中斷，頭尾沒有訊息不算開始或停止）")
        elif len(parts) == 1:
            parts[0] = "整段持續發布（" + parts[0] + "）"
        publish = "；".join(parts)
    for it in items:
        name, kind = it["name"], it.get("kind")
        if kind == "state":
            if it.get("count"):
                tags.append("狀態改變")
                for c in it.get("changes") or []:
                    ev(c["t"], f"{name}：{_val(c['from'])} → {_val(c['to'])}", 2)
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
                    ev(c["t"], f"{name}：{_val(c['from'])} → {_val(c['to'])}", 3)
                row["changes"].append(_path(name, it, base))
                row["end"].append(f"{name}＝{_val(it.get('last'))}" + (f"（開頭 {_val(it.get('first'))}）" if it.get("last") != it.get("first")
                                                                       else "（跟開頭一樣）"))
            else:   # 連續變動的數值（沒有切換、只看得到範圍）：不列成時間線的事件
                tags.append("數值變動")
                row["changes"].append(f"{name}：{_val(it.get('first'))} → {_val(it.get('last'))}（範圍 {_val(it.get('min'))}～{_val(it.get('max'))}，"
                                      f"平均 {_val(it.get('mean'))}）")
                row["end"].append(f"{name}＝{_val(it.get('last'))}（開頭 {_val(it.get('first'))}）")
            if it.get("spike_count"):
                tags.append("尖峰")
                sp = it.get("spikes") or []
                for k, s in enumerate(sp[:3]):
                    ev(s["t"], f"{name} 尖峰 {_val(s['value'])}" + (f"（共 {it['spike_count']} 個）" if k == 0 and it["spike_count"] > 3 else ""), 4)
                if sp:
                    row["changes"].append(f"{name} 尖峰 {it['spike_count']} 個（第一個 {_plus(float(sp[0]['t']) - base)}＝{_val(sp[0]['value'])}）")
        elif kind == "array":
            lo, hi = it.get("length_min"), it.get("length_max")
            if lo is not None and lo != hi:
                row["changes"].append(f"{name} 長度 {lo}～{hi}")
            elif lo is not None:
                row["still"].append(f"{name} 長度 {lo}")
    row["tags"] = list(dict.fromkeys(tags)) or ["沒有變化"]
    row["publish"] = publish
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


def _build_facts(job):
    """事實（程式整理，不經過模型）：
    - topics：每個分析過的 Topic 一列（類別、發布、變化、到最後的值、沒有變化的項目）；
    - timeline：Topic 的事件與 Log 依時間排序，每一列附前後 ANALYSIS_ALIGN_SEC 秒內對照到的 Log（或 Topic 的變化）；Log 列出
      WARN 以上、規劃時挑的、跟 Topic 變化對得上的。超過 _TIMELINE_MAX 列時依重要性留（WARN 以上的 Log、開始／停止／中斷、
      相關的 Log、狀態跳轉、數值切換、尖峰、其他 Log），被省略的數量在 timeline_hidden；
    - same_time：ANALYSIS_SAME_TIME_SEC 秒內不同 Topic 一起變化；
    - unmatched_logs：WARN 以上或規劃時挑的 Log，每一次出現的前後量到的 Topic 都沒有變化（Orchestrator 檢查要不要補量的依據）；
    - not_analyzed：沒有分析、沒有訊息、無法解碼、只有文字的 Topic。"""
    idx = job["index"]
    base = idx["start_ns"] / 1e9
    topics, tev = [], []
    for w in sorted(job.get("workers") or [], key=lambda x: x["n"]):
        row, evs = _topic_facts(w, base)
        topics.append(row)
        tev += evs
    tev.sort(key=lambda e: (e["t"], e["w"]))
    related = {r["id"] for r in (job.get("plan") or {}).get("related") or []}
    logs = _log_events(job, base)
    for e in tev:
        e["near"] = [(x, x["t"] - e["t"]) for x in logs if abs(x["t"] - e["t"]) <= ANALYSIS_ALIGN_SEC]
    for x in logs:
        x["near"] = [(e, e["t"] - x["t"]) for e in tev if abs(e["t"] - x["t"]) <= ANALYSIS_ALIGN_SEC]
        x["key"] = _LEVEL_RANK.get(x["level"], 1) >= 2 or x["id"] in related
    rows = [{"t": e["t"], "time": _plus(e["t"]), "source": e["src"], "event": e["text"], "rank": e["rank"],
             "near": _near_text(e["near"], "id", lambda x: x["id"], "沒有對應的 Log")} for e in tev]
    for x in logs:
        if not (x["key"] or x["near"]):
            continue
        rank = 0 if _LEVEL_RANK.get(x["level"], 1) >= 2 else (1 if x["id"] in related else 5)
        rows.append({"t": x["t"], "time": _plus(x["t"]), "source": f"{x['id']} {x['level']} {x['node']}", "rank": rank,
                     "event": _short(x["text"], 200) + (f"（{x['note']}）" if x["note"] else "") + x["where"],
                     "near": _near_text(x["near"], "w", lambda e: e["src"], "量到的 Topic 沒有變化")})
    rows.sort(key=lambda r: (r["t"], r["source"]))
    hidden = 0
    if len(rows) > _TIMELINE_MAX:
        keep = sorted(range(len(rows)), key=lambda i: (rows[i]["rank"], rows[i]["t"]))[:_TIMELINE_MAX]
        hidden = len(rows) - _TIMELINE_MAX
        rows = [rows[i] for i in sorted(keep)]
    lonely = {}
    for x in logs:
        if x["key"]:
            d = lonely.setdefault(x["id"], dict({k: x[k] for k in ("id", "level", "node", "text", "where", "t")}, matched=False))
            d["matched"] = d["matched"] or bool(x["near"])
    groups, cur = [], []
    for e in tev + [None]:
        if e is not None and cur and e["t"] - cur[0]["t"] <= ANALYSIS_SAME_TIME_SEC:
            cur.append(e)
            continue
        if len({x["w"] for x in cur}) >= 2:
            groups.append({"time": _plus(cur[0]["t"]) + (f"～{_plus(cur[-1]['t'])}" if cur[-1]["t"] > cur[0]["t"] else ""),
                           "events": [f"{x['src']}（{x['text']}）" for x in cur]})
        cur = [e] if e is not None else []
    analyzed = {w["topic"] for w in job.get("workers") or []}
    kinds = {"worker": "沒有分析", "empty": "沒有訊息", "undecodable": "無法解碼", "text_only": "只有文字"}
    not_analyzed = {}
    for t in idx["topics"]:
        k = kinds.get(t.get("role"))
        if k and not (k == "沒有分析" and t["topic"] in analyzed):
            not_analyzed.setdefault(k, []).append(t["topic"])
    return {"topics": topics, "timeline": [{k: r[k] for k in ("t", "time", "source", "event", "near", "rank")} for r in rows],
            "timeline_hidden": hidden, "same_time": groups,
            "unmatched_logs": [{k: v for k, v in d.items() if k != "matched"} for d in lonely.values() if not d["matched"]],
            "not_analyzed": not_analyzed}


def _top_rows(rows, n):
    """時間線的重點 n 列（依重要性挑，再照時間排）：交給主對話用。"""
    if len(rows) <= n:
        return rows
    keep = sorted(range(len(rows)), key=lambda i: (rows[i]["rank"], rows[i]["t"]))[:n]
    return [rows[i] for i in sorted(keep)]


def _report_data(facts, summary):
    """job.json 的 report（回歸評分與 Web 面板讀）：摘要與事實，只留純資料。"""
    return {"summary": summary["summary"], "unresolved": summary["unresolved"], "topics": facts["topics"],
            "timeline": [{k: r[k] for k in ("time", "source", "event", "near")} for r in facts["timeline"]],
            "timeline_hidden": facts.get("timeline_hidden", 0), "same_time": facts["same_time"],
            "unmatched_logs": facts["unmatched_logs"], "not_analyzed": facts["not_analyzed"]}


# ---------------------------------------------------------------- Synthesizer 的摘要與 Orchestrator 的檢查：輸入與程式核對
def _changes(w):
    """worker 量到的變化（程式的 flags 裡不是訊息中斷的：開始／停止發布、一段完整的發布、狀態跳轉、尖峰…）。"""
    bad = set(w.get("program_anomalies") or [])
    return [f for f in w.get("program_flags") or [] if f not in bad]


def _excerpt(text, word, width=60):
    """引用一句話時以出問題的字為中心：太長就取它前後一段（交回時模型才看得到要改的是哪個字）。"""
    if len(text) <= width:
        return text
    i = max(0, text.find(word))
    a = max(0, i - (width - len(word)) // 2)
    b = min(len(text), a + width)
    a = max(0, b - width)
    return ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")


def _quoted(job):
    """Log 原文與量到的字串（例如故障矩陣的說明「LiDAR 數據中斷」是 winning_reason 的值）：摘要照抄這些字不算用詞不對。"""
    return (" ".join(str(s.get("message") or "") for s in job.get("signals") or [])
            + json.dumps([w.get("measure") for w in job.get("workers") or []], ensure_ascii=False))


def _wording_issues(job, texts):
    """用詞跟量測對不對得上：量測沒有訊息中斷的 Topic 寫成「中斷／間歇／丟失」。全部 Topic 都沒有訊息中斷時，這些字都沒有量測支持；
    有 Topic 中斷時，只看提到沒中斷的 Topic、沒提到中斷的 Topic 的句子。Log 原文或量到的字串有這個字的不算。
    實測 26b：報告寫「/cmd_vel_raw 的發布中斷」「指令源頭中斷」時 cmdvel 定性成正常的操作 10/33，沒寫 7/7。"""
    done = [w for w in job.get("workers") or [] if w.get("status") == "done"]
    if not done:
        return []
    broken = [w["topic"] for w in done if w.get("program_anomalies")]
    calm = [w for w in done if not w.get("program_anomalies")]
    quoted = _quoted(job)
    names = lambda clause: {t for t in re.findall(r"/[A-Za-z0-9_/]+", clause)}   # 句子提到的 Topic（完整名稱：/cmd_vel 不等於 /cmd_vel_raw）
    measured = {w["topic"] for w in done}
    found = []
    for t in texts:
        for clause in re.split(r"[，。；;\n]", str(t or "")):
            if broken:   # 實測：「在 +18.79s（中斷後 0.51 秒）/system/safety_gate_status…」說的是別的 Topic 的中斷
                clause = _INTERRUPT_AS_TIME.sub("", clause)
            bad = [x for x in _interrupt_words(clause) if x not in quoted]
            if not bad:
                continue
            said = names(clause)
            if said - measured:   # 提到沒有量測的 Topic（沒錄到、沒分析）：不是跟量測相反
                continue
            if broken and (not said or said & set(broken)):
                continue
            found.append(_excerpt(clause.strip(), bad[0]))
    if not found:
        return []
    facts = "；".join(f"{w['topic']} {'；'.join(_changes(w)[:2])}" for w in calm if _changes(w))[:500]
    return [f"寫了「{'」「'.join(dict.fromkeys(found[:3]))}」，但程式量到" + ("這幾個 Topic" if broken else "的 Topic 都") + "沒有訊息中斷"
            + (f"（量到的是：{facts}）" if facts else "")
            + "——照量測的說法寫：開始發布、停止發布、一段完整的發布、輸出歸零；中斷＝停了一段又恢復，只有量測工具量到訊息中斷才是"]


def _summary_issues(job, text):
    """摘要的程式核對：太長被截斷（實測 lidar：把五則 Log 整段抄進來，停在半句）；寫了原因、誰造成誰或推測（_NOT_FACT_WORDS，
    Log 原文裡本來就有的不算）；用詞跟量測不符（_wording_issues）。"""
    issues = []
    if len(text or "") >= _SUMMARY_MAX - 10:
        issues.append(f"摘要太長，被截斷在半句（{len(text)} 字）：寫三到六句、400 字以內；Log 只寫編號、層級、節點與訊息裡的代碼"
                      "（原文在時間線，不用整段抄）")
    bad = _not_fact_words(text, _quoted(job))
    if bad:
        issues.append(f"寫了「{'、'.join(bad)}」：摘要只寫量到什麼、什麼時候、哪些一起變化與 Log 的原文，不寫原因、誰造成誰，也不推測")
    return issues + _wording_issues(job, [text])


def _topics_lines(facts):
    return "\n".join(f"- W{r['w']} {r['topic']}（{r.get('type') or '-'}）｜類別：{'、'.join(r['tags'])}｜發布：{r['publish']}"
                     + (f"｜變化：{'；'.join(r['changes'])}" if r["changes"] else "")
                     + (f"｜到最後：{'；'.join(r['end'])}" if r["end"] else "")
                     + (f"｜沒有變化：{'；'.join(r['still'][:4])}" if r["still"] else "") for r in facts["topics"])


def _summary_user(job, facts):
    """Synthesizer 的輸入：數據與程式整理的事實（各 Topic 的結果、時間線、同時發生的變化）。不給使用者的問題與 Orchestrator 的理解
    （推測的原因不進事實那一層），也不給 worker 的局部報告：實測 steady 1/5 次照局部報告的「第一筆 +0.01s、最後一筆 +29.91s」寫成
    「開始發布……停止發布」，程式整理的是整段持續發布——事實只用程式整理的這一份。"""
    # Log 的原文截到 140 字（完整的在報告的時間線）：輸入短一點，摘要也比較不會整段抄
    tl = "\n".join(f"- {r['time']}｜{r['source']}｜{_short(r['event'], 140)}｜前後 {ANALYSIS_ALIGN_SEC:g} 秒內：{r['near']}"
                   for r in facts["timeline"])
    same = "\n".join(f"- {g['time']}：{'、'.join(g['events'])}" for g in facts["same_time"])
    return (f"【數據】{job.get('data_label')}：共 {job.get('duration_sec')} 秒（時間是距離數據開頭的秒數，+秒）\n\n"
            f"【各 Topic 的結果（程式從量測結果整理）】\n{_topics_lines(facts)}\n\n"
            f"【時間線（程式整理：Topic 的事件與 Log 依時間排序；「前後 {ANALYSIS_ALIGN_SEC:g} 秒內」只是時間上的對照，不代表誰造成誰）】\n"
            f"{tl or '（沒有量到任何事件）'}"
            + (f"\n\n【同時發生的變化（{ANALYSIS_SAME_TIME_SEC:g} 秒內）】\n{same}" if same else "")
            + "\n\n（只寫上面的事實與 Log 的原文：不寫原因、不寫誰造成誰、不推測；三到六句；繁體中文，時間寫成 +秒）")


def _fallback_summary(facts):
    """Synthesizer 沒有給出合法的 JSON：程式寫一份（各 Topic 的類別與變化）。"""
    return "（Synthesizer 沒有產生摘要，以下由程式整理）" + "；".join(
        f"W{r['w']} {r['topic']}：{'、'.join(r['tags'])}" + (f"（{'；'.join(r['changes'][:2])}）" if r["changes"] else "")
        for r in facts["topics"])


def _check_user(job, facts, summary, lonely, left):
    """Orchestrator 檢查的輸入：問題、規劃時挑的 Log、已經量的 Topic（程式整理）、摘要、前後沒有量到變化的 Log、還沒量的 Topic。"""
    rel = "\n".join(f"- {r['id']}：{r['why']}" for r in job["plan"]["related"]) or "（沒有）"
    lone = "\n".join(f"- {x['id']} {x['level']} {_plus(x['t'])} {x['node']}：{_short(x['text'], 200)}{x['where']}" for x in lonely)
    cand = "\n".join(f"- {t['topic']}｜{t['type']}｜{t['message_count']} 則｜Key：{key_line_summary(t)}" for t in left)
    return (f"【使用者的問題】\n{job['question']}\n\n【數據】{job.get('data_label')}：共 {job.get('duration_sec')} 秒（+秒＝距離數據開頭）\n\n"
            f"【你規劃時挑的相關 Log】\n{rel}\n\n【已經量的 Topic（程式從量測結果整理）】\n{_topics_lines(facts)}\n\n"
            f"【摘要（Synthesizer）】\n{summary['summary']}\n\n"
            f"【前後 {ANALYSIS_ALIGN_SEC:g} 秒內，已經量的 Topic 都沒有變化的 Log】\n{lone}\n\n【還沒量的 Topic（可以補量）】\n{cand}\n\n"
            f"【要決定的】上面這幾則 Log 的時間點，還沒量的 Topic 裡有沒有量得到對應變化的？有就補量（最多 {ANALYSIS_FOLLOWUP_WORKERS} 個；"
            "signal＝它對應的 L#，subtask＝要看哪些 Key、什麼時間附近、可能看到什麼變化）；沒有就給空陣列。只決定要不要補量，不寫原因。"
            "（每個欄位都用繁體中文寫）")
