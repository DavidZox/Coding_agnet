"""Coding 面板的後端：coding orchestrator（agent_core/coding_job.py）的狀態查詢與操作，以及 /code 系列 slash 指令。

orchestrator 是背景服務，job 可能跑好幾十分鐘，所以不走 /api/send 那種「一個請求串流到回合結束」：畫面每 1.5 秒輪詢
GET /api/code/state（job 的完整狀態＋新的事件），操作（核准、修改計畫、暫停、停止、重試、還原…）是一般的 POST /api/code/<動作>，
立刻回傳。只有「用說的改計畫」要呼叫規劃 session，會花幾秒。"""
import os
from agent_core.coding_job import ACTIVE_STATUSES, STATUS_LABELS
from skills_system.scripts import _code_common as cc
from .state import agent, state

coding = agent.coding
_models_cache = {"ts": 0, "names": []}


def available_models():
    """Ollama 裡已經下載的模型（設定面板的下拉選單用；60 秒快取，連不到就回空 list）。"""
    import time
    if time.time() - _models_cache["ts"] < 60:
        return _models_cache["names"]
    try:
        import ollama
        res = ollama.list()
        models = res.get("models") if hasattr(res, "get") else getattr(res, "models", [])
        names = sorted({(m.get("model") or m.get("name")) if hasattr(m, "get") else getattr(m, "model", "") for m in models or []} - {None, ""})
    except Exception:
        names = []
    _models_cache.update(ts=time.time(), names=names)
    return names


def _thinking_map(names):
    """{模型: 支不支援 thinking}（Ollama /api/show 的 capabilities，有快取）；畫面只在支援時顯示 thinking 開關。"""
    from agent_core.model_caps import supports_thinking
    return {m: supports_thinking(m) for m in set(names) if m}


def _job_ref(ref):
    if ref in (None, "", "latest"):
        return coding.active_job() or coding.latest()
    return coding.get(str(ref).lstrip("#"))


def code_state(job_ref=None, since=0):
    """GET /api/code/state：選取的 job（沒指定＝執行中的，否則最新的）、它的新事件、最近的 job 清單與設定。"""
    job = _job_ref(job_ref)
    return {
        "job": coding.view(job) if job else None,
        "events": coding.events(job["id"], int(since or 0)) if job else [],
        "jobs": coding.list_jobs(15),
        "active": (coding.active_job() or {}).get("id"),
        "workspace": coding.workspace_default(),
        "models": coding.model_state(),     # planner、worker 與各自的 thinking 開關
        "available_models": available_models(),
        "thinking": _thinking_map(available_models() + [coding.planner_model(), coding.worker_model()]),
        "code_mode": state.get("code_mode", False),
        "auto_approve": coding.auto_approve,
        "on_fail": coding.on_fail,
        "python": coding.python,       # 空白＝自動；python_auto 是自動偵測到的（工作區的 .venv → harness 的 venv）
        "python_auto": cc.project_python(coding.workspace_default()) if not coding.python else "",
    }


def code_action(action, data):
    """POST /api/code/<action>：回傳 {ok, message, job?}；不合法的操作 raise ValueError（server 轉成 400）。"""
    jid = data.get("job")
    if action == "submit":
        job, err = coding.submit(data.get("task"), data.get("workspace"), "web")
        if err:
            raise ValueError(err)
        return {"ok": True, "message": f"已建立 coding job #{job['id']}", "job": job["id"]}
    if action == "workspace":
        path = str(data.get("path") or "").strip()
        if not path:
            coding.default_workspace = None
            coding.save_settings()
            return {"ok": True, "message": f"coding 工作區改回跟著主對話的工作目錄：{coding.workspace_default()}"}
        ws, err = coding.check_workspace(path)
        if err:
            raise ValueError(err)
        coding.default_workspace = ws
        coding.save_settings()
        return {"ok": True, "message": f"coding 工作區：{ws}"}
    if action == "model":
        if "planner" in data or "worker" in data:   # 「套用」一次送兩個（以前分兩次送，第二次讀到的是重畫後的舊值）
            def flag(key):
                return None if key not in data or data[key] is None else bool(data[key])
            models = coding.set_models(str(data.get("planner") or "").strip() or None,
                                       str(data.get("worker") or "").strip() or None,
                                       flag("planner_think"), flag("worker_think"))
        else:
            role, model = data.get("role") or "all", str(data.get("model") or "").strip() or None
            models = coding.set_model(role, model)
        th = lambda role: "，thinking 開" if models[f"{role}_think"] and _thinking_map([models[role]]).get(models[role]) else ""  # noqa: E731
        return {"ok": True, "message": f"規劃 {models['planner']}{th('planner')}、worker {models['worker']}{th('worker')}"
                                       f"（下一個 job 開始生效，已存檔）",
                "models": models}
    if action == "python":
        path, err = coding.set_python(data.get("path"))
        if err:
            raise ValueError(err)
        return {"ok": True, "message": f"測試用的 Python：{path}（已存檔）" if path else
                f"測試用的 Python 改回自動（工作區的 .venv／venv → harness 的 Python）"}
    if action == "settings":
        if "auto_approve" in data:
            coding.auto_approve = bool(data["auto_approve"])
        if data.get("on_fail") in ("ask", "skip", "stop"):
            coding.on_fail = data["on_fail"]
        if "code_mode" in data:
            state["code_mode"] = bool(data["code_mode"])
        coding.save_settings()
        return {"ok": True, "message": "已更新設定（已存檔）"}
    if jid is None:
        raise ValueError("缺少 job 編號")
    jid = int(str(jid).lstrip("#"))
    if action == "approve":
        coding.approve(jid)
        return {"ok": True, "message": f"job #{jid} 已核准，開始執行"}
    if action == "revise":
        note = coding.revise(jid, str(data.get("feedback") or "").strip() or "（沒有內容）")
        return {"ok": True, "message": note}
    if action == "edit_item":
        coding.edit_item(jid, int(data.get("n") or 0), {k: data.get(k) for k in ("title", "goal", "files", "verify") if k in data})
        return {"ok": True, "message": "已更新"}
    if action == "delete_item":
        coding.delete_item(jid, int(data.get("n")))
        return {"ok": True, "message": "已刪除"}
    if action == "move_item":
        coding.move_item(jid, int(data.get("n")), int(data.get("to")))
        return {"ok": True, "message": "已移動"}
    if action == "final_verify":
        coding.set_final_verify(jid, data.get("cmd") or "")
        return {"ok": True, "message": "已更新整體驗證指令"}
    if action == "cancel":
        coding.cancel(jid)
        return {"ok": True, "message": f"job #{jid}：已要求停止"}
    if action == "pause":
        coding.pause(jid)
        return {"ok": True, "message": f"job #{jid}：目前這一步做完就暫停"}
    if action == "resume":
        coding.resume(jid)   # 暫停的繼續；程式重新啟動而中斷的從中斷的地方接著做
        return {"ok": True, "message": f"job #{jid}：繼續執行"}
    if action == "decide":
        coding.decide(jid, data.get("decision"), str(data.get("note") or ""))
        return {"ok": True, "message": f"job #{jid}：{data.get('decision')}"}
    if action == "revert":
        return {"ok": True, "message": coding.revert(jid)}
    if action == "revert_file":
        return {"ok": True, "message": coding.revert_file(jid, str(data.get("file") or ""))}
    raise ValueError(f"不認得的動作：{action}")


def code_diff(job_ref, rel=None):
    job = _job_ref(job_ref)
    if not job:
        return None
    return coding.diff_text(job, rel) or "（沒有任何變更）"


def code_report(job_ref):
    job = _job_ref(job_ref)
    if not job:
        return None
    path = os.path.join(coding.job_dir(job["id"]), "report.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return coding.render_report(job)


def code_worker_log(job_ref, item, attempt):
    job = _job_ref(job_ref)
    if not job:
        return None
    path = os.path.join(coding.job_dir(job["id"]), "workers", f"item{int(item)}_try{int(attempt)}.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def header_label():
    """標題列的一小段：執行中（或需要處理）的 coding job。"""
    job = coding.active_job()
    if not job:
        return None
    items = job.get("items") or []
    done = sum(1 for it in items if it["status"] == "done")
    return {"id": job["id"], "status": job["status"], "label": STATUS_LABELS.get(job["status"], job["status"]),
            "done": done, "total": len(items), "needs": bool(job.get("needs"))}


# ---------------------------------------------------------------- /code 系列 slash 指令
CODE_HELP = """🧑‍💻 coding orchestrator 指令：
/code <任務描述>          交給 coding orchestrator：探索專案、列計畫（在 Coding 面板核准後才開始改檔案）
/code                     看目前（或最近）的 coding job
/code jobs                列出最近的 job
/code approve [N]         核准計畫、開始執行
/code pause|resume [N]    暫停／繼續（目前這一步做完才暫停；程式重新啟動而中斷的 job 也用 resume 接著做）
/code cancel [N]          停止（已改好的檔案保留）
/code retry|skip|stop [N] [補充說明]   某一項失敗、在等你決定時：重試（可附說明給 worker）／跳過／停止
/code revert N            把 job 改過的檔案全部還原成 job 開始前的樣子
/code_ws [路徑]           查看／設定 coding 工作區（專案根目錄；沒設定就跟著主對話的工作目錄）
/code_model [planner|worker|all] [模型]   查看／設定規劃與 worker 用的模型，例如 /code_model planner gemma4:26b
/code_mode on|off         開啟後，輸入框送出的每個任務都直接交給 coding orchestrator（等同按 🧑‍💻 Code）
/code_autoapprove on|off  計畫列好後自動核准（長時間無人看管時用；預設關）
/code_python [路徑|-]     查看／設定跑 Python 測試用的直譯器（- 改回自動：工作區的 .venv → harness 的 Python）
主對話的 AI 也會在你要它改程式時用 code_job_send 交出去；進度、核准、diff、報告都在右邊的「🧑‍💻 Coding」面板。"""


def handle_code_command(text, events):
    """/code、/code_ws、/code_model、/code_mode、/code_autoapprove。回傳 True＝已處理。"""
    import re
    lower = text.lower()
    if not (lower == "/code" or lower.startswith(("/code ", "/code_ws", "/code_model", "/code_mode", "/code_autoapprove", "/code_help",
                                                   "/code_python"))):
        return False

    def say(msg, channel="system", **extra):
        events.append({"channel": channel, "text": msg, **extra})

    try:
        if lower.startswith("/code_help"):
            say(CODE_HELP)
            return True
        if lower.startswith("/code_ws"):
            arg = text[len("/code_ws"):].strip()
            if not arg:
                say(f"🧑‍💻 coding 工作區：{coding.workspace_default()}" + ("（跟著主對話的工作目錄）" if not coding.default_workspace else "")
                    + "；設定：/code_ws <專案路徑>，改回跟著工作目錄：/code_ws -")
                return True
            say("🧑‍💻 " + code_action("workspace", {"path": "" if arg == "-" else arg})["message"], "code")
            return True
        if lower.startswith("/code_python"):
            arg = text[len("/code_python"):].strip()
            if not arg:
                say(f"🧑‍💻 測試用的 Python：{coding.python or '自動（' + cc.project_python(coding.workspace_default()) + '）'}"
                    "；設定：/code_python <路徑>，改回自動：/code_python -")
                return True
            say("🧑‍💻 " + code_action("python", {"path": "" if arg == "-" else arg})["message"], "code")
            return True
        if lower.startswith("/code_model"):
            parts = text.split()[1:]
            if not parts:
                say(f"🧑‍💻 規劃模型 {coding.planner_model()}、worker 模型 {coding.worker_model()}。設定：/code_model planner|worker|all <模型>"
                    f"（例如 /code_model planner gemma4:26b）")
                return True
            role, model = (parts[0], parts[1] if len(parts) > 1 else "") if parts[0] in ("planner", "worker", "all") else ("all", parts[0])
            say("🧑‍💻 " + code_action("model", {"role": role, "model": model})["message"], "code")
            return True
        if lower.startswith("/code_mode"):
            on = lower.endswith("on")
            state["code_mode"] = on
            say("🧑‍💻 已開啟 Code 模式：之後送出的任務都直接交給 coding orchestrator（/code_mode off 關閉）" if on
                else "🧑‍💻 已關閉 Code 模式：訊息回到主對話")
            return True
        if lower.startswith("/code_autoapprove"):
            coding.auto_approve = lower.endswith("on")
            coding.save_settings()
            say("🧑‍💻 計畫列好後自動核准：" + ("開（不會停下來等你核准，worker 直接開始改檔案）" if coding.auto_approve else "關（預設，要在面板核准）"))
            return True
        arg = text[len("/code"):].strip()
        if not arg:
            job = coding.active_job() or coding.latest()
            if not job:
                say("🧑‍💻 目前還沒有 coding job：用 /code <任務描述> 送出（或按 🧑‍💻 Code），/code_help 看全部指令。")
            else:
                say(f"🧑‍💻 job #{job['id']}（{STATUS_LABELS.get(job['status'], job['status'])}）：{job['task']}\n{coding.plan_text(job)}",
                    "code", job=job["id"])
            return True
        m = re.match(r"^(jobs|status|approve|pause|resume|cancel|retry|skip|stop|revert|help)\b\s*(#?\d+)?\s*(.*)$", arg, re.I | re.S)
        if not m:
            res = code_action("submit", {"task": arg})
            say(f"🧑‍💻 已交給 coding orchestrator：job #{res['job']}（工作區 {coding.workspace_default()}）。正在探索專案、列計畫，"
                f"列好後在右邊的 Coding 面板核准才會開始改檔案。", "code", job=res["job"])
            return True
        verb, num, rest = m.group(1).lower(), m.group(2), m.group(3).strip()
        if verb == "help":
            say(CODE_HELP)
            return True
        if verb == "jobs":
            rows = [f"#{j['id']} {j['label']}（{j['done']}/{j['total']}）：{j['task'][:60]}" for j in coding.list_jobs(15)]
            say("🧑‍💻 最近的 coding job：\n" + ("\n".join(rows) or "（還沒有）"))
            return True
        job = _job_ref(num)
        if not job:
            say("⚠️ 找不到 coding job" + (f" #{num}" if num else ""))
            return True
        jid = job["id"]
        if verb == "status":
            say(f"🧑‍💻 job #{jid}（{STATUS_LABELS.get(job['status'], job['status'])}）：{job['task']}\n{coding.plan_text(job)}", "code", job=jid)
        elif verb in ("retry", "skip", "stop") and job["status"] == "needs_attention":
            say("🧑‍💻 " + code_action("decide", {"job": jid, "decision": verb, "note": rest})["message"], "code", job=jid)
        elif verb in ("retry", "skip"):
            say(f"⚠️ job #{jid} 目前不是在等你決定（{STATUS_LABELS.get(job['status'], job['status'])}）")
        else:
            verb = "cancel" if verb == "stop" else verb
            say("🧑‍💻 " + code_action(verb, {"job": jid})["message"], "code", job=jid)
        return True
    except ValueError as e:
        say(f"⚠️ {e}")
        return True


def submit_from_chat(message, events):
    """Code 模式：輸入框的任務直接交給 orchestrator（不經過主對話）。"""
    try:
        res = code_action("submit", {"task": message})
    except ValueError as e:
        events.append({"channel": "system", "text": f"⚠️ 沒有建立 coding job：{e}"})
        return None
    events.append({"channel": "code", "job": res["job"], "text": (
        f"🧑‍💻 已交給 coding orchestrator：job #{res['job']}（工作區 {coding.workspace_default()}）。正在探索專案、列計畫，"
        f"列好後在右邊的 Coding 面板核准才會開始改檔案。")})
    return res["job"]


def is_active(job_id):
    job = coding.get(job_id)
    return bool(job and job["status"] in ACTIVE_STATUSES)
