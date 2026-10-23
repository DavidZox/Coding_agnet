"""AnalysisMixin：數據分析 analysis_run 偽技能——全部由程式做，不呼叫模型（2026-10-23 起）。

只要有 .mcap 就能用的事實報告：量到什麼、什麼時候、Log 說了什麼；不做因果推論（原因要對照源碼另外分析——第九輪的源碼脈絡與因果推論
留在 doc/archive/root_cause_reference/）。一次分析一整段數據，最長 ANALYSIS_MAX_SECONDS 秒；更長的數據先用 mcap_slicer 切出要看的時間段。

1. 資料預備：rosout_parser --json 把 Log 去重成唯一訊號（L#：層級、Node、次數、每一次的時間戳、印出 Log 的檔案:行 函式——/rosout 的
   欄位，錄製時就在 MCAP 裡）；mcap_analyzer --json 讀全域 Topic Metadata；mcap_analyzer --facts --json 量全部的 Topic、全部的 Key
   （發布方式、中斷、開始／停止發布、狀態跳轉、數值切換、尖峰、範圍）。build_facts 整理成有編號的事實：T#＝Topic、E#＝Topic 的事件
   （同一則訊息裡一起改變的項目算一個事件）、L#＝Log 訊號；時間線、前後 1 秒內的對照、同時發生、重要的時間點。
2. 重點（_program_highlights，照規則寫）：每個重要的時間點一則（Log 的則數與層級、事件），那一刻全部的 Log 與事件的完整內容列在下面；
   反覆切換的 Topic、到最後跟開頭不同的值（依 Topic 分組）、只有數值連續變動的 Topic、沒有變化的 Topic。
3. 報告：重點、各 Topic 的結果、時間線、同時發生的變化、前後沒有任何變化的 Log、沒有量的 Topic。

模型的角色在主對話：讀報告、回答使用者的問題，要細看時自己用數據技能（rosout_parser、mcap_analyzer、mcap_feature_measure、mcap_slicer）；
回答寫的變化與值由 turn_guard.analysis_reply_check（agent_core/claims.py）跟報告的事實核對。第十一、十二輪由 Orchestrator → Workers →
Synthesizer 寫說明與重點，三個版本的比較裡沒有比程式寫的好（讀者答題 261／261／257 題，見〈設計筆記〉2.15〈七〉），2026-10-23 拿掉；
那時的程式在 git 的 803a6c7。

全部產物在 logs/analysis_jobs/<編號>/：job.json（事實、重點、報告的資料）、events.jsonl、log_digest.md、topic_metadata.md、
topic_facts.json（程式量的事實）、report.md。回傳給主對話的是報告的重點（存成 #編號）。
"""
import json
import os
import re
import shlex
import time

from .config import (
    ANALYSIS_ALIGN_SEC,
    ANALYSIS_ANSWER_NOTE,
    ANALYSIS_DATA_ROOT,
    ANALYSIS_JOBS_DIRNAME,
    ANALYSIS_MAX_SECONDS,
    ANALYSIS_REPORT_HEAD,
    ANALYSIS_SAME_TIME_SEC,
    ANALYSIS_SETTINGS_NAME,
)

DEFAULT_QUESTION = "這段錄製期間發生了哪些狀態變化？"
_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "UNKNOWN": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
_MARKERS = ("[ANALYSIS_DATA]", "[TARGET_CONTAINER]", "[CWD_CHANGED]", "[ROS2_WORKSPACE]")
_RECORDER_NODE = re.compile(r"^(rosbag2(_\w+)?|ros2_bag\w*)$")
# 以前的 job 還有規劃、workers、Synthesizer、檢查的狀態（2026-10-22 以前），面板與清單照樣看得懂
_STATUS_TEXT = {"preparing": "資料預備", "planning": "Orchestrator 規劃", "working": "Workers 說明", "synthesizing": "Synthesizer 整理重點",
                "checking": "Orchestrator 檢查", "reasoning": "因果推論", "done": "完成", "failed": "失敗"}
_ACTIVE = ("preparing", "planning", "working", "synthesizing", "checking", "reasoning")
# 拿掉的選項：源碼脈絡、時間窗（第九輪以前）；worker 上限、最多幾輪（2026-10-23 改成全部由程式做）——收到就說清楚，不要默默變成問題的一部分
_REMOVED_OPTIONS = {"--source": "source", "--no-source": "source", "--before": "window", "--after": "window",
                    "--workers": "program", "--rounds": "program"}
# ROS 2 框架與錄製工具自己的 Topic：列在事實裡（則數），不列事件（/parameter_events 的 node 欄位只是「最後一個發參數事件的節點」）
_FRAMEWORK_TOPICS = ("/parameter_events", "/clock", "/events/write_split")
_MAIN_TIMELINE_MAX = 15  # 回到主對話的時間線重點
_MAIN_HIGHLIGHTS_MAX = 24   # 回到主對話的重點最多幾則（事件很多時依重要性留，照時間排；完整的在報告）
_FLAP_KEEP = (5, 2)      # 同一個 Topic 的變化事件太多（反覆切換）：時間線只列前 5 個與最後 2 個，次數在各 Topic 的結果
_MOMENT_KINDS = ("start", "stop", "gap", "resume", "change", "first")   # 算「重要的時間點」的事件（一則訊息、尖峰不算）
_EVENT_RANK = {"start": 1, "stop": 1, "gap": 1, "resume": 1, "change": 2, "first": 3, "spike": 3, "message": 6}
_EVENT_ORDER = {"start": 0, "first": 1, "message": 2, "change": 3, "spike": 4, "gap": 5, "resume": 6, "stop": 7}
_EVENT_TAGS = ("訊息中斷", "開始或停止發布", "狀態改變", "數值切換", "尖峰", "第一則在中途")   # 有這些類別＝有事件
_HL_CHANGES = 1          # 程式寫的重點：事件少（≤2）時一個事件列前幾個變化（其餘寫「另 N 項」；完整的內容列在那一則下面）
_HL_LIST = 8             # 到最後跟開頭不同的值、沒有變化的 Topic：一則最多列幾個 Topic（其餘寫「等 N 個」）


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
        return {"data_root": ANALYSIS_DATA_ROOT, "container": ""}

    def load_analysis_settings(self):
        """預設值＋設定檔裡使用者改過的值。設定檔只存跟預設值不同的（save_analysis_settings）：預設值以後改了，沒改過的設定跟著新的預設，
        不會被當時存下的舊預設蓋住。舊版的設定（各角色的模型、worker 上限、源碼目錄、時間窗…）讀的時候略過，下次存檔就不見了。"""
        cfg = self.analysis_defaults()
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
        defaults = self.analysis_defaults()
        data = {k: v for k, v in self.analysis_cfg.items() if k in defaults and v != defaults[k]}
        data["saved"] = time.strftime("%Y-%m-%d %H:%M:%S")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

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
        """進度：印出、記進 events.jsonl、交給畫面（Web 在執行工具時設 progress_callback，推到右欄）。"""
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
                        "highlights": len((j.get("report") or {}).get("highlights") or [])})
        return out

    def analysis_job_detail(self, jid):
        """Web 面板用：job.json、事件、報告全文（以前的 job 另有各 worker 的說明）。"""
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

    # ---------------------------------------------------------------- 主流程（全部由程式做）
    def analysis_run(self, remainder):
        """analysis_run 技能：解析參數 → 資料預備（Log 去重、量全部 Topic 的事實）→ 程式寫重點 → 報告。回傳給主對話的報告（或 [ERROR]）。"""
        try:
            toks = shlex.split(remainder or "")
        except ValueError:
            toks = (remainder or "").replace('"', " ").split()
        opts = {"data": "", "topics": []}
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
                why = {"source": "它只做事實報告，不用源碼。",
                       "window": "它一次量整段數據（沒有時間窗）；只想看其中一段，先用 mcap_slicer 切出來，再用 --data 指定切片資料夾。",
                       "program": "它全部由程式做（量全部的 Topic、程式寫重點），沒有 worker，也不分輪。"}[_REMOVED_OPTIONS[t]]
                return f"[ERROR] analysis_run 沒有 {t} 這個選項了：{why}"
            words.append(t)
            i += 1
        question = " ".join(words).strip().strip('"').strip() or DEFAULT_QUESTION
        data = opts["data"] or self.analysis_data
        if not data:
            return ("[ERROR] analysis_run 需要數據：args 加 --data <實驗資料夾、bag、切片資料夾、.mcap，或實驗名稱、latest>；"
                    "也可以先用 mcap_analyzer 看一份數據（系統會記住目前的數據）。")
        job = {"id": time.strftime("%Y%m%d_%H%M%S"), "created": time.strftime("%Y-%m-%d %H:%M:%S"), "question": question,
               "data": data, "status": "preparing", "options": opts, "generated_by": "program"}
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
            facts = job["facts"]
            highlights = sorted((_render_note(n, facts, details=True) for n in _program_highlights(facts)),
                                key=lambda h: (h["t"] is None, h["t"] or 0))
            job["report"] = _report_data(job, facts, highlights)
            job["seconds"] = round(time.time() - t0, 1)
            self._job_write(job, "report.md", self._render_report(job, facts, highlights))
            text = self._report_for_main(job, facts, highlights)
        except Exception as e:   # noqa: BLE001  任何一段失敗：已完成的產物留在 job 資料夾
            job["error"] = f"{type(e).__name__}: {e}"
            job["seconds"] = round(time.time() - t0, 1)
            self._job_status(job, "failed")
            self.analysis_last = {"id": job["id"], "status": "failed"}
            self._analysis_note(job, f"❌ 數據分析中斷：{job['error']}", kind="error")
            return (f"[ERROR] 數據分析中斷（{job['status']}）：{job['error']}。已完成的部分在 "
                    f"logs/{ANALYSIS_JOBS_DIRNAME}/{job['id']}/。")
        self._job_status(job, "done")
        self.analysis_last = {"id": job["id"], "status": "done"}
        self._analysis_note(job, f"✅ 數據分析完成（{job['seconds']:.0f} 秒；重點 {len(highlights)} 則，程式整理）", kind="done")
        return text

    def _analysis_tool(self, script, args, extra_env=None):
        """在 harness 裡執行數據技能（同 run_tool 的執行原語，但不記軌跡、不存檔：job 資料夾有完整紀錄）。"""
        path = os.path.join(self.base_path, "scripts", script)
        return self._exec_script(script, path, list(args), extra_env=extra_env)

    # ---------------------------------------------------------------- 資料預備（程式）
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
        job["scan_info"] = {"cached": bool(scan.get("cached")), "seconds": scan.get("seconds")}
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

    def _digest_text(self, job, limit=None, include_recorder=False):
        """去重後的 Log（log_digest.md）：略過錄製工具自己的 Log；WARN 以上全部，其餘依時間補到上限。每個訊號後面接印出它的
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

    # ---------------------------------------------------------------- 報告（程式）
    def _render_report(self, job, facts, highlights):
        """報告（Frontmatter Markdown）：重點、各 Topic 的結果、時間線、同時發生的變化、前後沒有任何變化的 Log、沒有訊息或無法解碼的 Topic、
        資料來源。全部由程式從量測結果與 Log 整理。"""
        fm = {"artifact": "fact_report", "job": job["id"], "question": job["question"], "data": job.get("data_label"),
              "data_path": job["data"], "time_range": job.get("time_range"), "generated_by": "program",
              "unmatched_logs": [x["id"] for x in facts["unmatched_logs"]]}
        if job["options"].get("topics"):
            fm["focus_topics"] = job["options"]["topics"]
        lines = [frontmatter(fm), f"# 數據事實報告\n\n**問題**：{job['question']}\n\n**數據**：{job.get('data_label')}（{job['data']}，"
                                  f"{job.get('duration_sec')} 秒）\n",
                 f"> 只列數據裡量到的事實與 Log 的原文，全部由程式整理。「前後 {ANALYSIS_ALIGN_SEC:g} 秒內」只是時間上的對照，不代表誰造成誰；"
                 "原因要對照源碼另外分析。編號：T#＝Topic、E#＝Topic 的事件、L#＝Log 訊號。\n"]
        lines.append(f"## 重點\n**總覽**：{facts['overview']}\n\n" + ("\n".join(_note_line(h) for h in highlights) or "（沒有重點）") + "\n")
        lines.append("## 各 Topic 的結果（程式量測整段數據的全部 Key）\n| 編號 | Topic | 類別 | 發布 | 變化 | 到最後 |\n|---|---|---|---|---|---|\n"
                     + "\n".join(f"| {r['id']} | {r['topic']} | {'、'.join(r['tags'])} | {_cell(r['publish'])} | "
                                 f"{_cell('；'.join(r['changes'] + r['ranges']) or '-')} | "
                                 f"{_cell('；'.join(r['end']) or ('；'.join(r['still'][:4]) + '（沒有變化）' if r['still'] else '-'))} |"
                                 for r in facts["topics"]) + "\n")
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
        src = [f"- Log：{job.get('log_source') or job.get('log_error') or '（沒有）'}" + (f"，共 {job['log_total']} 則" if job.get("log_total") else ""),
               f"- 量測：{'讀快取（topic_facts.json）' if (job.get('scan_info') or {}).get('cached') else '這次量的'}"
               + (f"，{job['scan_info']['seconds']} 秒" if (job.get("scan_info") or {}).get("seconds") else ""),
               f"- 整份報告由程式整理，{job.get('seconds')} 秒，沒有呼叫模型"]
        lines.append("## 資料來源\n" + "\n".join(src) + "\n")
        return "\n".join(lines)

    def _report_for_main(self, job, facts, highlights):
        """回傳給主對話的報告重點（以 ANALYSIS_REPORT_HEAD 開頭：不再摘要、整份進主對話，並存成 #編號）。"""
        lines = [f"{ANALYSIS_REPORT_HEAD}（job {job['id']}：程式整理，{job['seconds']:.0f} 秒）",
                 f"問題：{job['question']}", f"數據：{job.get('data_label')}（{job.get('duration_sec')} 秒）",
                 f"總覽：{facts['overview']}"]
        focus = [r for t in job["options"].get("topics") or [] for r in facts["topics"] if r["topic"] == t]
        missing = [t for t in job["options"].get("topics") or [] if not any(r["topic"] == t for r in facts["topics"])]
        if focus or missing:
            lines.append("指定的 Topic：\n" + "\n".join(
                f"- {r['id']} {r['topic']}｜{'、'.join(r['tags'])}｜{r['publish']}"
                + (f"｜變化：{'；'.join(r['changes'] + r['ranges'])}" if r["changes"] or r["ranges"] else "")
                + (f"｜到最後：{'；'.join(r['end'])}" if r["end"] else (f"｜沒有變化：{'；'.join(r['still'][:6])}" if r["still"] else ""))
                + (f"｜事件：{'、'.join(r['events'])}" if r["events"] else "") for r in focus)
                + "".join(f"\n- {t}：這份數據裡沒有這個 Topic" for t in missing))
        shown = _top_highlights(highlights, _MAIN_HIGHLIGHTS_MAX)
        if shown:
            lines.append("重點（程式整理；引用的事件與 Log 的內容列在每一則下面）：\n" + "\n".join(
                _note_line(h, n=110, bold=False, max_lines=10 if len(shown) <= 10 else 5) for h in shown)
                + (f"\n（另有 {len(highlights) - len(shown)} 則重點在完整報告）" if len(shown) < len(highlights) else ""))
        busy = [r for r in facts["topics"] if r["events"] or "數值變動" in r["tags"]]
        if busy:
            lines.append("有變化的 Topic：\n" + "\n".join(
                f"- {r['id']} {r['topic']}｜{'、'.join(r['tags'])}｜{r['publish']}"
                + (f"｜{'；'.join((r['changes'] + r['ranges'])[:3])}" if r["changes"] or r["ranges"] else "")
                + (f"｜到最後：{'；'.join(r['end'][:3])}" if r["end"] else "") for r in busy))
        quiet = [r["topic"] for r in facts["topics"] if not (r["events"] or "數值變動" in r["tags"])]
        if quiet:
            lines.append(f"沒有變化的 Topic（{len(quiet)} 個）：{'、'.join(quiet[:12])}" + ("…" if len(quiet) > 12 else ""))
        cited = {r for h in shown for r in h["refs"]}
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
        lines.append(f"完整報告：logs/{ANALYSIS_JOBS_DIRNAME}/{job['id']}/report.md")
        lines.append(ANALYSIS_ANSWER_NOTE + "：只陳述報告裡的事實——時間、數值、狀態、Log 的原文，可以引用編號。報告沒有判斷原因："
                     "「前後 1 秒內」「同時」只是時間上的先後，不要寫成誰導致、造成、觸發誰；使用者問「為什麼」時，照事實說明發生了什麼、"
                     "先後順序，並說明原因要對照源碼另外分析；要細看某個 Topic、某一段時間或某則 Log，用數據技能"
                     "（mcap_feature_measure、mcap_analyzer、rosout_parser、mcap_slicer）查）")
        return "\n".join(lines)


# ---------------------------------------------------------------- 用詞（回歸評分：報告的文字不寫原因、誰造成誰、推測）
_NOT_FACT_WORDS = ("導致", "造成", "引起", "觸發", "根因", "原因", "證實", "證明", "排除", "歸因", "因此", "所以", "由於", "因為",
                   "可能是", "推測", "疑似", "或許")


def _not_fact_words(text, quoted=""):
    """寫了哪些「不是事實」的字（原因、誰造成誰、推測）；quoted（Log 原文、量到的字串）裡本來就有的不算。"""
    return [w for w in _NOT_FACT_WORDS if w in (text or "") and w not in quoted]


# ---------------------------------------------------------------- 重點（程式照規則寫）
def _event_head(e):
    """重點裡一個事件的名稱：Topic，開始／停止發布、中斷、恢復、第一則再加上那個動作（變化的內容列在那一則下面）。"""
    return e["topic"] if e["kind"] == "change" else f"{e['topic']} {str(e['text']).split('（')[0]}"


def _event_brief(e):
    """重點裡一個事件的一句話（程式）：開始／停止發布、中斷、恢復、第一則照事件的文字；同一則訊息裡的變化列前 _HL_CHANGES 項
    （其餘寫「另 N 項」，完整的內容由 _render_note 列在那一則下面）。"""
    text = str(e["text"])
    if e["kind"] != "change":
        return f"{e['topic']} {text.split('（')[0]}"
    parts = [p.strip() for p in text.split("；") if p.strip()]
    more = len(parts) - _HL_CHANGES
    return f"{e['topic']} " + "；".join(_short(p, 70) for p in parts[:_HL_CHANGES]) + (f"（另 {more} 項）" if more > 0 else "")


def _listed(items, n=_HL_LIST):
    return "、".join(items[:n]) + (f"…等 {len(items)} 個" if len(items) > n else "")


def _program_highlights(facts):
    """重點（程式照規則寫，不呼叫模型）→ [{refs, text}]：
    - 每個重要的時間點（_moments）一則：Log 的則數與層級（WARN 以上的，加上時間線上前後 ANALYSIS_ALIGN_SEC 秒內的 INFO——例如故障清除的
      MON_FAULT_CLEARED），事件 2 個以內寫第一個變化（_event_brief）、更多時列出是哪些（_event_head）；refs＝那一刻全部的編號，完整的內容
      （每則 Log 的層級、節點與原文，事件的每個變化）由 _render_note 列在下面；
    - 反覆切換的 Topic 各一則（次數）；
    - 到數據結束時跟開頭不同的值（依 Topic 分組，每個 Topic 前 2 項）與中途才出現的項目（每個 Topic 幾項）一則、只有數值連續變動的
      Topic 一則、整段沒有變化的 Topic 一則。"""
    ev, sig = facts["events"], facts["signals"]
    moments, flap = _moments(facts)
    tl_logs = [(r["t"], r["ref"]) for r in facts["timeline"] if str(r.get("ref") or "").startswith("L") and r.get("t") is not None]
    out = []
    for m in moments:
        near = [ref for t, ref in tl_logs if m["t0"] - ANALYSIS_ALIGN_SEC <= t <= m["t1"] + ANALYSIS_ALIGN_SEC and ref not in m["refs"]]
        m = dict(m, refs=list(m["refs"]) + list(dict.fromkeys(near)))
        logs = [r for r in m["refs"] if r in sig]
        evs = sorted((r for r in m["refs"] if r in ev), key=lambda r: int(r[1:]))
        parts = []
        if logs:
            levels = {}
            for r in logs:
                levels[sig[r]["level"]] = levels.get(sig[r]["level"], 0) + 1
            order = sorted(levels.items(), key=lambda kv: -_LEVEL_RANK.get(kv[0], 1))
            parts.append(f"{len(logs)} 則 Log（{'、'.join(f'{k} {v}' for k, v in order)}）")
        if len(evs) <= 2:
            parts += [_event_brief(ev[r]) for r in evs]
        else:
            parts.append(f"{len(evs)} 個事件：" + "、".join(_event_head(ev[r]) for r in evs))
        out.append({"refs": list(m["refs"]), "text": "；".join(parts)})
    for r in flap:
        out.append({"refs": [r["id"]], "text": f"{r['topic']} 反覆切換 {r['flap']} 次"})
    # 到最後跟開頭不同：依 Topic 分組，每個 Topic 列前 2 項（其餘寫「另 N 項」），每個有變的 Topic 都看得到——只照項目排時，
    # 一個診斷 Topic 的十幾項會把安全閘的 ESTOP_LATCHED 擠出去；中途才出現的項目只寫每個 Topic 幾項（值在各 Topic 的結果）
    diff = [(r, [x for x in r["end"] if "（開頭 " in x]) for r in facts["topics"]]
    diff = [(r, d) for r, d in diff if d]
    late = [(r, [x for x in r["end"] if "才出現" in x]) for r in facts["topics"]]
    late = [(r, d) for r, d in late if d]
    if diff or late:
        parts = [f"{r['topic']}：{'、'.join(_short(x, 80) for x in d[:2])}" + (f"（另 {len(d) - 2} 項）" if len(d) > 2 else "")
                 for r, d in diff[:_HL_LIST]]
        if len(diff) > _HL_LIST:
            parts.append(f"…等 {len(diff)} 個 Topic")
        if late:
            parts.append("中途才出現：" + "、".join(f"{r['topic']} {len(d)} 項" for r, d in late))
        out.append({"refs": list(dict.fromkeys(r["id"] for r, _ in diff + late)), "text": "到數據結束時跟開頭不同：" + "；".join(parts)})
    cont = [r for r in facts["topics"] if not r["events"] and "數值變動" in r["tags"]]
    if cont:
        out.append({"refs": [r["id"] for r in cont], "text": "只有數值連續變動：" + _listed([r["topic"] for r in cont])})
    quiet = [r for r in facts["topics"] if not (r["events"] or "數值變動" in r["tags"]) and "沒有訊息" not in r["tags"]]
    if quiet:
        out.append({"refs": [r["id"] for r in quiet], "text": "整段沒有變化：" + _listed([r["topic"] for r in quiet])})
    return out


def _top_highlights(highlights, n):
    """回到主對話的重點最多 n 則：整段的（到最後的值、沒有變化…）都留；時間點的依重要性挑（ERROR、WARN 的 Log 多、引用的編號多的先留），
    再照時間排。完整的在報告。"""
    if len(highlights) <= n:
        return highlights
    whole = [i for i, h in enumerate(highlights) if h["t"] is None]
    timed = [i for i, h in enumerate(highlights) if h["t"] is not None]

    def score(h):
        rows = h.get("facts") or []
        return (-sum(1 for x in rows if re.match(r"L\d+ (ERROR|FATAL)", x)), -sum(1 for x in rows if re.match(r"L\d+ WARN", x)), -len(h["refs"]))
    keep = set(whole) | set(sorted(timed, key=lambda i: score(highlights[i]))[: max(0, n - len(whole))])
    return [h for i, h in enumerate(highlights) if i in keep]


def _report_data(job, facts, highlights):
    """job.json 的 report（回歸評分與 Web 面板讀）：總覽、重點、各 Topic、時間線…，只留純資料。"""
    return {"overview": facts["overview"], "highlights": highlights, "summary": "\n".join(h["text"] for h in highlights),
            "topics": [{k: r[k] for k in ("id", "topic", "type", "pattern", "tags", "publish", "changes", "ranges", "end", "still", "events")}
                       for r in facts["topics"]],
            "timeline": [{k: r[k] for k in ("ref", "time", "source", "event", "near")} for r in facts["timeline"]],
            "same_time": facts["same_time"], "unmatched_logs": facts["unmatched_logs"], "unreadable": facts["unreadable"]}


def _render_note(note, facts, details=False):
    """一則說明 → {refs, text, t, time}：時間由程式依 refs 算（E# 的時間；L# 取最接近同一則裡 E# 的那一次，沒有 E# 就是第一次）。
    details（重點）：引用的 Log 與事件的內容列在下面（facts：每則 Log 的層級、節點與原文在前，事件的完整內容在後）。"""
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
        lines = [f"{r} {facts['signals'][r]['level']} {facts['signals'][r]['node']}：{_short(facts['signals'][r]['text'], 120)}"
                 for r in sorted((r for r in cited if r in facts["signals"]), key=lambda r: int(r[1:]))]
        lines += [f"{r} {facts['events'][r]['topic']}：{facts['events'][r]['text']}" for r in ev]
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
    refs = '、'.join(h['refs'][:12]) + (f"…等 {len(h['refs'])} 個" if len(h['refs']) > 12 else "")
    line = f"- {'**' + when + '**' if bold else when}　{h['text']}（{refs}{also}）"
    rows = h.get("facts") or []
    shown = rows if max_lines is None else rows[:max_lines]
    line += "".join(f"\n  - {_short(x, n) if n else x}" for x in shown)
    if len(rows) > len(shown):
        line += f"\n  - …另 {len(rows) - len(shown)} 個事件與 Log（完整的在報告）"
    return line


# ---------------------------------------------------------------- 事實（程式）
def _short_block(text, n):
    """多行文字截短（保留換行）。"""
    text = str(text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"

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
           "ranges": [], "end": [], "still": [], "events": [], "values": {}, "quiet_keys": list((entry.get("quiet") or {}).keys())}
    evs, tags = [], []
    # 中途才出現的項目（DiagnosticArray 的某一項在故障時才加進來）：它的「開頭」是出現那一刻的值，不是錄製開始時的狀態
    late_after = (rate.get("first_sec") or 0) + max(1.0, 3 * float(rate.get("period_sec") or 0))

    def late(it):
        return bool(rate.get("first_sec")) and it.get("first_t") is not None and float(it["first_t"]) > late_after

    def end_text(it):
        name = it["name"]
        if late(it):
            return f"{name}＝{_val(it.get('last'))}（{_plus(float(it['first_t']) - base)} 才出現，那時是 {_val(it.get('first'))}）"
        if it.get("last") != it.get("first"):
            return f"{name}＝{_val(it.get('last'))}（開頭 {_val(it.get('first'))}）"
        return f"{name}＝{_val(it.get('last'))}（中間變過，最後回到開頭的值）"

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
                row["end"].append(end_text(it))
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
                row["end"].append(end_text(it))
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
    # 到最後仍跟開頭不同的排在前面（最後的狀態是什麼，常常就是使用者要問的）
    row["end"].sort(key=lambda x: 0 if "（開頭 " in x else 1 if "才出現" in x else 2)
    row["values"] = _key_values(items, base, late)
    row["fields"] = [it["name"] for it in items] + row["quiet_keys"]   # 句子裡寫到這些名稱＝主詞是某個項目（不是整個 Topic）
    row["tags"] = list(dict.fromkeys(tags)) or ["沒有變化"]
    return row, evs


_CONST = re.compile(r"^\s*[A-Za-z0-9_/]+\s+([A-Z][A-Z0-9_]*)\s*=\s*\"?([^\"#\s]+)\"?", re.M)
_FIELD_TYPE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_/]*)(?:\[[^\]]*\])?\s+[a-z_][A-Za-z0-9_]*\s*(?:#.*)?$", re.M)


def _msg_aliases(defs, typ):
    """訊息定義裡的常數（byte OK=0、uint8 LIMIT_SPEED=1）→ {值: [名稱…]}：模型照定義把值寫成名稱（level 的 0 寫 OK、1 寫 WARN）也算對
    （實測第十二輪：worker 寫「level 從 OK 變成 WARN」被當成跟事實的 0 → 1 對不上）。巢狀的型別（DiagnosticArray 的 DiagnosticStatus[]）一起看。"""
    by_short = {k.split("/")[-1]: k for k in defs}
    out, seen, todo = {}, set(), [typ]
    while todo:
        t = todo.pop()
        if not t or t in seen or t not in defs:
            continue
        seen.add(t)
        text = defs[t] if isinstance(defs[t], str) else ""
        for name, value in _CONST.findall(text):
            out.setdefault(value, []).append(name)
        for ft in _FIELD_TYPE.findall(text):
            todo.append(by_short.get(ft.split("/")[-1]))
    return out

def _key_values(items, base, late):
    """每個 Key 的值（核對模型寫的「從 A 變成 B」「沒有變化」「回到初始」「到最後是 X」用，agent_core/claims.py）：
    {Key: {first, last, changes: [[+秒, 從, 到]…], count（變化的總次數；changes 只留頭尾時比較多）, varies（有沒有變過）,
    late（中途才出現）}}。狀態與只有幾種值的數值有每一次的變化；連續變動的數值只有開頭與最後的值。"""
    out = {}
    for it in items:
        kind = it["kind"]
        if kind not in ("state", "numeric"):
            continue
        changes = [[round(float(c["t"]) - base, 3), c["from"], c["to"]] for c in it.get("changes") or []]
        varies = bool(it.get("count")) if kind == "state" else not it.get("constant")
        count = it.get("count") or len(changes)
        if late(it):   # 中途才出現：出現的那一刻也算一次變化（之前沒有值，None）——「…變成 2（出現的那一則）」是對的
            changes = [[round(float(it["first_t"]) - base, 3), None, it.get("first")]] + changes
        out[it["name"]] = {"first": it.get("first"), "last": it.get("last"), "changes": changes, "count": count,
                           "varies": varies, "continuous": kind == "numeric" and varies and not it.get("changes"), "late": late(it)}
    return out

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
        row["aliases"] = _msg_aliases(idx.get("msg_definitions") or {}, meta.get("type"))
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
    """全部 Topic 的事實總表（topic_metadata.md）：每個 Topic 一行。"""
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
    """時間線的重點 n 列（依重要性挑，再照時間排）：交給主對話用。"""
    if len(rows) <= n:
        return rows
    keep = sorted(range(len(rows)), key=lambda i: (rows[i]["rank"], rows[i]["t"]))[:n]
    return [rows[i] for i in sorted(keep)]

def _moments(facts):
    """重要的時間點（程式算的，每個一則重點）→ ([{id, t0, t1, refs}], 反覆切換的 Topic 列)：
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
