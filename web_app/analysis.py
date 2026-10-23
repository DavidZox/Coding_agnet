"""📊 數據分析面板的後端：analysis job 的清單與內容（/api/analysis/state 輪詢）、job 資料夾裡的檔案（報告、去重後的 Log、Topic 的事實）、
設定（數據根目錄、預設容器）、目前的數據，以及 /analyze 系列指令。

analysis_run 本身在主對話的回合裡同步執行（agent_core/analysis_job.py，全部由程式做；主模型選用、或 /analyze 與 📊 分析模式直接交給它），
這裡只讀它寫在 logs/analysis_jobs/<編號>/ 的檔案，所以分析進行中也能輪詢（ThreadingHTTPServer，不進主對話的 lock）。"""
import os
import re
from agent_core.analysis_job import _STATUS_TEXT
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
    return {"data_root": cfg.get("data_root") or "", "container": cfg.get("container") or ""}


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


def analysis_action(action, data):
    """面板的操作：settings（數據根目錄、預設容器）、data（目前的數據）。回傳 {ok, message}。"""
    cfg = agent.analysis_cfg
    if action == "settings":
        msgs = []
        if "data_root" in data:
            cfg["data_root"] = str(data.get("data_root") or "").strip()
            msgs.append(f"數據根目錄：{cfg['data_root'] or '自動尋找（容器的 /workspace 底下的 experiment_logs）'}")
        if "container" in data:
            cfg["container"] = str(data.get("container") or "").strip()
            if cfg["container"] and not agent.target_container:
                agent.target_container = cfg["container"]
            msgs.append(f"預設容器：{cfg['container'] or '（沒有）'}")
        agent.save_analysis_settings()
        return {"ok": True, "message": "📊 已更新：" + ("；".join(msgs) or "（沒有改變）")}
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
/analyze [問題]                 直接交給數據分析（analysis_run：Log 去重＋程式量全部 Topic 的事實 → 程式寫重點 → 事實報告，
                                全部由程式做；不判斷原因，AI 依報告回答）；問題省略＝這段數據發生了哪些狀態變化；
                                數據用目前的數據（沒有就用 latest）；一次最多 3 分鐘，更長的先用 mcap_slicer 切
/analysis                       看最近一次數據分析 job；/analysis jobs 列出最近的 job
/analysis_data <數據>            設定目前分析的數據（實驗資料夾、bag、切片、.mcap、實驗名稱或 latest；主機路徑會自動換成容器路徑）
/analysis_root <路徑>|-          數據根目錄（mcap_recorder 錄到這裡、實驗名稱與 latest 相對於它；- 改回自動尋找 experiment_logs）
/analysis_container <容器>|-     數據分析預設的容器（目標容器沒設定時用）
/analysis_mode on|off          📊 分析模式（同輸入框旁的按鈕）：送出的問題直接交給 analysis_run
右欄「📊 數據分析」面板：進度、去重後的 Log、Topic 的事實、最後的事實報告。"""


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
                "📊 已開啟分析模式：送出的問題直接交給數據分析（analysis_run），數據用目前的數據（"
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
    elif cmd in ("/analysis_slice", "/analysis_source", "/analysis_hints", "/analysis_model", "/analysis_workers"):
        # 第九輪以前的設定（動態時間切片、源碼脈絡、推理提示）；2026-10-23 改成全部由程式做之後，各角色的模型與 worker 上限也拿掉了
        events.append({"channel": "system", "text": f"📊 {cmd} 已經拿掉：數據分析全部由程式做（量整段數據的全部 Topic、程式寫重點），"
                                                     "不用源碼、不呼叫模型。只想看其中一段，先用 mcap_slicer 切出來再分析。"})
    elif cmd == "/analysis":
        jobs = agent.analysis_list_jobs(15)
        if arg.lower() == "jobs":
            events.append({"channel": "system", "text": "📊 最近的數據分析 job：\n" + ("\n".join(
                f"- {j['id']}｜{_STATUS_TEXT.get(j['status'], j['status'])}｜{j['data_label']}｜重點 {j['highlights']} 則｜{j['question'][:50]}"
                for j in jobs) or "（沒有）")})
        else:
            jid = arg if re.match(r"^\d{8}_\d{6}", arg or "") else (jobs[0]["id"] if jobs else None)
            report = analysis_file(jid, "report.md") if jid else None
            events.append({"channel": "system", "text": (f"📊 job {jid}：\n{report}" if report else
                                                         f"📊 job {jid} 還沒有報告" if jid else "📊 還沒有數據分析 job：/analyze [問題] 開始。")})
    else:
        events.append({"channel": "system", "text": ANALYSIS_HELP})
    return True
