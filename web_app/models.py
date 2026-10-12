"""「🧠 模型」設定的後端：主對話（非 coding）、Coding 規劃、Coding worker 三個角色各自的模型與 thinking 開關。

GET /api/models 回傳目前的設定、Ollama 裡的模型、每個模型支不支援 thinking（畫面只在支援時顯示開關）；
POST /api/models 一次套用（沒給的欄位不變）。主對話的設定存在 logs/model_settings.json、Coding 的存在 logs/coding_settings.json，
重開 Web Console 也記得。/model 與 /think 指令（commands.py）走同一組函式。"""
from agent_core.model_caps import supports_thinking
from .coding import available_models, coding
from .state import agent

ROLE_LABELS = {"main": "主對話", "planner": "Coding 規劃", "worker": "Coding worker"}


def thinking_map(names):
    return {m: supports_thinking(m) for m in names if m}


def model_view():
    names = available_models()
    cs = coding.model_state()
    current = {"main": agent.model, "planner": cs["planner"], "worker": cs["worker"]}
    return {
        "main": agent.model, "main_think": bool(agent.main_think),
        "planner": cs["planner"], "planner_think": cs["planner_think"],
        "worker": cs["worker"], "worker_think": cs["worker_think"],
        "summary_model": agent.summary_model, "summary_follows_main": agent._summary_follows_main,
        "available": names,
        "thinking": thinking_map(set(names) | set(current.values())),
    }


def _flag(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("1", "on", "true", "yes"):
        return True
    if isinstance(v, str) and v.strip().lower() in ("0", "off", "false", "no"):
        return False
    return None if v is None else bool(v)


def model_update(data):
    """套用設定；回傳 {ok, message, models}。模型名稱不在 Ollama 裡 → ValueError（server 轉成 400）。"""
    names = available_models()
    for role in ("main", "planner", "worker"):
        m = str(data.get(role) or "").strip()
        if m and names and m not in names:
            raise ValueError(f"{ROLE_LABELS[role]}的模型 {m} 不在 Ollama 裡（ollama list 看得到的才能用）")
    main = str(data.get("main") or "").strip()
    if main:
        agent.set_main_model(main)
    if "main_think" in data and _flag(data["main_think"]) is not None:
        agent.main_think = _flag(data["main_think"])
    agent.save_model_settings()
    coding.set_models(str(data.get("planner") or "").strip() or None, str(data.get("worker") or "").strip() or None,
                      _flag(data.get("planner_think")), _flag(data.get("worker_think")))
    view = model_view()
    return {"ok": True, "message": "🧠 " + describe(view) + "（主對話下一輪生效；Coding 下一個 job 生效，已存檔）", "models": view}


def describe(view=None):
    view = view or model_view()
    parts = []
    for role in ("main", "planner", "worker"):
        m = view[role]
        think = view[f"{role}_think"]
        if view["thinking"].get(m):
            t = "thinking 開" if think else "thinking 關"
        else:
            t = "不支援 thinking"
        parts.append(f"{ROLE_LABELS[role]} {m}（{t}）")
    return "、".join(parts) + f"；摘要模型 {view['summary_model']}" + ("（跟著主對話）" if view["summary_follows_main"] else "")
