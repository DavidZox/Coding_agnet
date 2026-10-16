"""📊 數據分析面板的後端：analysis job 的清單與內容（/api/analysis/state 輪詢）、job 資料夾裡的檔案（局部報告、worker 對話、報告）、
設定（數據根目錄、預設容器、worker 數、時間窗）、目前的數據，以及 /analyze 系列指令。

analysis_run 本身在主對話的回合裡同步執行（agent_core/analysis_job.py，主模型選用、或 /analyze 與 📊 分析模式直接交給它），
這裡只讀它寫在 logs/analysis_jobs/<編號>/ 的檔案，所以分析進行中也能輪詢（ThreadingHTTPServer，不進主對話的 lock）。"""
import os
import re
from agent_core.analysis_job import ROLES, ROLE_LABELS, _STATUS_TEXT
from .state import agent, state


def available_models():
    """Ollama 裡的模型名稱（排序）；連不到時回空清單。"""
    try:
        import ollama
        res = ollama.list()
        models = res.get("models") if hasattr(res, "get") else getattr(res, "models", [])
        names = {(m.get("model") or m.get("name")) if hasattr(m, "get") else getattr(m, "model", "") for m in models or []}
        return sorted(n for n in names if n)
    except Exception:   # noqa: BLE001
        return []


def settings_view():
    cfg = agent.analysis_cfg
    return {"data_root": cfg.get("data_root") or "", "container": cfg.get("container") or "",
            "max_workers": cfg.get("max_workers"), "parallel": cfg.get("parallel"),
            "before": cfg.get("before"), "after": cfg.get("after"),
            "source_root": cfg.get("source_root") or "", "program_hints": bool(cfg.get("program_hints", True)),
            "rounds": cfg.get("rounds"),
            "models": {r: agent.analysis_model(r) for r in ROLES},
            "think": {r: agent.analysis_think(r) for r in ROLES},
            "follows_main": {r: not cfg.get(r) for r in ROLES}}


def analysis_state(job_id=None):
    jobs = agent.analysis_list_jobs(20)
    jid = job_id or (jobs[0]["id"] if jobs else None)
    return {"jobs": jobs, "detail": agent.analysis_job_detail(jid) if jid else None, "settings": settings_view(),
            "data": agent.analysis_data, "container": agent.target_container}


def analysis_file(job_id, rel):
    """job 資料夾裡的一個檔案（只認資料夾內的相對路徑）；不存在回 None。"""
    base = os.path.realpath(os.path.join(agent.analysis_jobs_dir(), os.path.basename(str(job_id or ""))))
    path = os.path.realpath(os.path.join(base, str(rel or "")))
    if not path.startswith(base + os.sep) or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _num(v, cast, lo, hi):
    try:
        x = cast(v)
    except (TypeError, ValueError):
        raise ValueError(f"{v!r} 不是數字")
    if not lo <= x <= hi:
        raise ValueError(f"{x} 要介於 {lo}～{hi}")
    return x


def analysis_action(action, data):
    """面板的操作：settings（數據根目錄、預設容器、worker 數、同時幾個、時間窗前後秒數）、data（目前的數據）。回傳 {ok, message}。"""
    cfg = agent.analysis_cfg
    if action == "settings":
        msgs = []
        try:
            if "data_root" in data:
                cfg["data_root"] = str(data.get("data_root") or "").strip()
                msgs.append(f"數據根目錄：{cfg['data_root'] or '自動尋找（容器的 /workspace 底下的 experiment_logs）'}")
            if "container" in data:
                cfg["container"] = str(data.get("container") or "").strip()
                if cfg["container"] and not agent.target_container:
                    agent.target_container = cfg["container"]
                msgs.append(f"預設容器：{cfg['container'] or '（沒有）'}")
            if "max_workers" in data:
                cfg["max_workers"] = _num(data["max_workers"], int, 1, 8)
            if "parallel" in data:
                cfg["parallel"] = _num(data["parallel"], int, 1, 8)
            if "before" in data:
                cfg["before"] = _num(data["before"], float, 0.5, 60)
            if "after" in data:
                cfg["after"] = _num(data["after"], float, 0.5, 60)
            if "slice" in data:
                cfg["slice"] = str(data["slice"]).strip().lower() in ("1", "true", "on", "yes")
            if "source_root" in data:   # 受測系統的源碼目錄（ROS 2 工作區的 src）：源碼脈絡
                cfg["source_root"] = os.path.expanduser(str(data.get("source_root") or "").strip())
                msgs.append(f"源碼目錄：{cfg['source_root'] or '（沒有：不用源碼脈絡）'}")
            if "program_hints" in data:
                cfg["program_hints"] = str(data["program_hints"]).strip().lower() in ("1", "true", "on", "yes")
                msgs.append(f"程式的推理提示：{'開' if cfg['program_hints'] else '關'}")
            if "rounds" in data:   # 最多幾輪（有源碼脈絡時，因果推論可以指派補分析；1＝不補）
                cfg["rounds"] = _num(data["rounds"], int, 1, 3)
                msgs.append(f"最多 {cfg['rounds']} 輪（補分析）")
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        agent.save_analysis_settings()
        msgs.append(f"worker 上限 {cfg['max_workers']}、同時 {cfg['parallel']} 個、時間窗前 {cfg['before']} 秒／後 {cfg['after']} 秒、"
                    f"切片 {'開' if cfg.get('slice', True) else '關'}")
        return {"ok": True, "message": "📊 已更新：" + "；".join(msgs)}
    if action == "data":
        agent.analysis_data = str(data.get("path") or "").strip()
        return {"ok": True, "message": f"📊 目前分析的數據：{agent.analysis_data or '（沒有）'}"}
    return {"ok": False, "error": f"不認識的操作 {action}"}


def header_label():
    """標題列的 📊：最近一次 analysis job 的狀態。"""
    last = getattr(agent, "analysis_last", None)
    if not last:
        jobs = agent.analysis_list_jobs(1)
        last = jobs[0] if jobs else None
    if not last:
        return None
    return {"id": last["id"], "status": last.get("status"), "label": _STATUS_TEXT.get(last.get("status"), last.get("status"))}


ANALYSIS_HELP = """📊 數據分析指令：
/analyze [問題]                 直接交給數據診斷（analysis_run：Log 去重＋Topic Metadata → Orchestrator 分派 → Workers 量測 → Synthesizer 報告）；
                                問題省略＝找出這段數據的異常與根因；數據用目前的數據（沒有就用 latest）
/analysis                       看最近一次數據分析 job；/analysis jobs 列出最近的 job
/analysis_data <數據>            設定目前分析的數據（實驗資料夾、bag、切片、.mcap、實驗名稱或 latest；主機路徑會自動換成容器路徑）
/analysis_root <路徑>|-          數據根目錄（mcap_recorder 錄到這裡、實驗名稱與 latest 相對於它；- 改回自動尋找 experiment_logs）
/analysis_container <容器>|-     數據分析預設的容器（目標容器沒設定時用）
/analysis_model <角色|all> <模型> orchestrator／worker／synthesizer 的模型（- 改回跟著主對話）
/analysis_workers <N>           一次最多派幾個 worker（1～8）
/analysis_slice on|off          動態時間切片：每個時間窗先用 mcap_slicer 切一片，worker 只讀切片（預設開；整段數據不切）
/analysis_source <源碼目錄>|-     受測系統的源碼目錄（ROS 2 工作區的 src）：Log 的源碼位置、在執行的節點的發布／訂閱關係、代碼的條件交給三個角色（- 不用）
/analysis_hints on|off          程式的推理提示（名稱比對的缺口、背景條件、共同的上游、一段完整的發布）；off＝只給數據與源碼的事實
/analysis_mode on|off          📊 分析模式（同輸入框旁的按鈕）：送出的問題直接交給 analysis_run
右欄「📊 數據分析」面板：計畫（相關的 Log 訊號、時間窗、每個 worker 的 Topic）、每個 worker 的局部報告、最後的報告。"""


def handle_analysis_command(text, events):
    """/analysis 系列（/analyze 要跑一個回合，在 server._handle_send 處理）。回傳 True＝已處理。"""
    lower = text.lower()
    if not lower.startswith("/analysis"):
        return False
    parts = text.split(maxsplit=2)
    cmd = parts[0].lower()
    arg = text[len(parts[0]):].strip()
    cfg = agent.analysis_cfg
    if cmd == "/analysis_help":
        events.append({"channel": "system", "text": ANALYSIS_HELP})
    elif cmd == "/analysis_mode":
        if arg.lower() not in ("on", "off"):
            events.append({"channel": "system", "text": "用法：/analysis_mode on|off"})
        else:
            state["analysis_mode"] = arg.lower() == "on"
            events.append({"channel": "system", "text": (
                "📊 已開啟分析模式：送出的問題直接交給數據診斷（analysis_run），數據用目前的數據（"
                f"{agent.analysis_data or 'latest'}）；/analysis_mode off 回到主對話。") if state["analysis_mode"]
                else "📊 已關閉分析模式，訊息回到主對話。"})
    elif cmd == "/analysis_data":
        if arg:
            agent.analysis_data = "" if arg == "-" else arg
        events.append({"channel": "system", "text": f"📊 目前分析的數據：{agent.analysis_data or '（沒有；工具會用 latest 或你指定的數據）'}"})
    elif cmd == "/analysis_root":
        if arg:
            res = analysis_action("settings", {"data_root": "" if arg == "-" else arg})
            events.append({"channel": "system", "text": res.get("message") or "⚠️ " + res.get("error", "")})
        else:
            events.append({"channel": "system", "text": f"📊 數據根目錄：{cfg.get('data_root') or '自動尋找（容器的 /workspace 底下的 experiment_logs）'}"})
    elif cmd == "/analysis_container":
        if arg:
            res = analysis_action("settings", {"container": "" if arg == "-" else arg})
            events.append({"channel": "system", "text": res.get("message") or "⚠️ " + res.get("error", "")})
        else:
            events.append({"channel": "system", "text": f"📊 預設容器：{cfg.get('container') or '（沒有）'}；目前的目標容器：{agent.target_container or '（沒有）'}"})
    elif cmd == "/analysis_workers":
        res = analysis_action("settings", {"max_workers": arg})
        events.append({"channel": "system", "text": res.get("message") or "⚠️ " + res.get("error", "")})
    elif cmd == "/analysis_slice":
        if arg.lower() not in ("on", "off"):
            on = agent.analysis_cfg.get("slice", True)
            events.append({"channel": "system", "text": f"✂️ 動態時間切片目前{'開' if on else '關'}（每個時間窗先切片、worker 只讀切片）。"
                                                         "用法：/analysis_slice on|off"})
        else:
            res = analysis_action("settings", {"slice": arg.lower() == "on"})
            events.append({"channel": "system", "text": res.get("message") or "⚠️ " + res.get("error", "")})
    elif cmd == "/analysis_source":
        if arg:
            res = analysis_action("settings", {"source_root": "" if arg == "-" else arg})
            events.append({"channel": "system", "text": res.get("message") or "⚠️ " + res.get("error", "")})
        else:
            root = cfg.get("source_root") or ""
            events.append({"channel": "system", "text": f"📊 源碼目錄：{root or '（沒有：不用源碼脈絡）'}"
                                                         + ("（目錄不存在）" if root and not os.path.isdir(root) else "")})
    elif cmd == "/analysis_hints":
        if arg.lower() not in ("on", "off"):
            on = cfg.get("program_hints", True)
            events.append({"channel": "system", "text": f"📊 程式的推理提示目前{'開' if on else '關'}。用法：/analysis_hints on|off"})
        else:
            res = analysis_action("settings", {"program_hints": arg.lower() == "on"})
            events.append({"channel": "system", "text": res.get("message") or "⚠️ " + res.get("error", "")})
    elif cmd == "/analysis_model":
        bits = arg.split()
        if len(bits) != 2 or bits[0].lower() not in ROLES + ("all",):
            desc = "、".join(f"{ROLE_LABELS[r]} {agent.analysis_model(r)}" for r in ROLES)
            events.append({"channel": "system", "text": f"📊 {desc}\n用法：/analysis_model orchestrator|worker|synthesizer|all <模型>（- ＝跟著主對話）"})
        else:
            names = available_models()
            model = None if bits[1] == "-" else bits[1]
            if model and names and model not in names:
                events.append({"channel": "system", "text": f"⚠️ 模型 {model} 不在 Ollama 裡（ollama list 看得到的才能用）"})
            else:
                agent.set_analysis_model(bits[0].lower(), model or "")
                desc = "、".join(f"{ROLE_LABELS[r]} {agent.analysis_model(r)}" for r in ROLES)
                events.append({"channel": "system", "text": f"📊 已更新（下一次分析生效，已存檔）：{desc}"})
    elif cmd == "/analysis":
        jobs = agent.analysis_list_jobs(15)
        if arg.lower() == "jobs":
            events.append({"channel": "system", "text": "📊 最近的數據分析 job：\n" + ("\n".join(
                f"- {j['id']}｜{_STATUS_TEXT.get(j['status'], j['status'])}｜{j['data_label']}｜{j['workers']} 個 worker｜{j['question'][:50]}"
                for j in jobs) or "（沒有）")})
        else:
            jid = arg if re.match(r"^\d{8}_\d{6}", arg or "") else (jobs[0]["id"] if jobs else None)
            report = analysis_file(jid, "report.md") if jid else None
            events.append({"channel": "system", "text": (f"📊 job {jid}：\n{report}" if report else
                                                         f"📊 job {jid} 還沒有報告" if jid else "📊 還沒有數據分析 job：/analyze [問題] 開始。")})
    else:
        events.append({"channel": "system", "text": ANALYSIS_HELP})
    return True
