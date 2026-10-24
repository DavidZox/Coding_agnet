"""/workflow 指令（CLI 與 Web 共用）與不用互動的入口（心跳、排程）：使用者自己指定工作流，不經過模型的選擇。

    /workflow                          列出工作流（名稱、用途、呼叫語法）
    /workflow show <名稱>              看一個工作流的步驟與需要的資訊
    /workflow <名稱> key=value …       執行：會改變狀態的步驟照常經過確認關卡（同 AI 呼叫 workflow_run）；報告進對話，AI 接著依報告回答
    /workflow --continue | --cancel    停在【確認】的工作流接著做／不做了

    python3 Agent_Runner.py --workflow <名稱> key=value … [--yes] [--model 模型] [--cwd 目錄]    不用互動：直接執行一次，印出報告
    python3 Agent_Runner.py --workflow --continue --yes                                         接著做停在【確認】的那一個

不用互動的入口是之後「心跳定期跑固定的工作流」的雛形：選哪個工作流、給什麼值都是呼叫端決定的，模型只在工作流的判斷點出手；
沒有人在旁邊確認，所以會改變狀態的工作流要呼叫端明確給 --yes（事先核准）才會執行，不然只印出需要確認哪幾步、不執行。
模型沒有給 --model 時用 Web Console 上次設定的主對話模型（logs/model_settings.json），沒有設定過就是 CLI 的預設。
每一次執行都跟對話裡執行的一樣存檔：logs/workflow_jobs/<編號>/（每一步、判斷點的模型呼叫）、logs/tool_results/（每一步的輸出、報告）。
結束碼：0 完成、依判斷提早結束或取消了；1 執行了但沒有完成、或成功判準沒過；2 停在【確認】（之後 --workflow --continue --yes 接著做）；
3 需要核准、沒有執行；4 沒有執行（參數不對、沒有這個工作流、規格有問題、這個環境關閉了工作流）。"""
import json
import shlex

WORKFLOW_SCRIPT = "scripts/workflow_run_cmd.py"
USAGE = "用法：/workflow（列出全部）｜/workflow show <名稱>｜/workflow <名稱> 名稱=值 …（執行）｜/workflow --continue｜/workflow --cancel"
HEADLESS_USAGE = ("用法：python3 Agent_Runner.py --workflow [<名稱> 名稱=值 …｜show <名稱>｜--continue｜--cancel] [--yes] [--model 模型] [--cwd 目錄]"
                  "（不接名稱＝列出全部）")
EXIT_CODES = {"done": 0, "ended": 0, "cancelled": 0, "failed": 1, "unverified": 1, "paused": 2}
EXIT_NEEDS_APPROVAL, EXIT_NOT_RUN = 3, 4


def parse(text):
    """/workflow 後面的字 → (種類, 內容)：list／show（名稱）／run（workflow_run 的參數）／error（說明）。"""
    t = (text or "").strip()
    if not t or t in ("list", "--list", "ls"):
        return "list", ""
    if t == "show" or t.startswith("show "):
        name = t[4:].strip()
        return ("show", name) if name else ("error", f"要看哪一個？{USAGE}")
    return "run", t


def list_text(agent):
    wfs = agent.list_workflows()
    if not wfs:
        return "目前沒有工作流（skills_system/workflows/ 是空的）。用 /make_skill <名稱> 可以把做對的一段對話存成工作流。"
    lines = [f"🧩 工作流 {len(wfs)} 個（/workflow <名稱> 名稱=值 … 執行；/workflow show <名稱> 看步驟）："]
    for wf in wfs:
        need = " ".join(f"[{i['name']}=<…>]" if i["optional"] else f"{i['name']}=<…>" for i in wf["inputs"])
        lines.append(f"- {wf['name']}：{wf['description']}\n  /workflow {wf['name']} {need}".rstrip())
    return "\n".join(lines)


def show_text(agent, name):
    from . import workflow_spec as ws
    wf = agent.load_workflow(name)
    if not wf:
        names = [w["name"] for w in agent.list_workflows()]
        return f"沒有工作流 {name}。現有的：{'、'.join(names) or '（沒有）'}"
    need = "\n".join(f"- {i['name']}{'（選填）' if i['optional'] else ''}：{i['description']}" for i in wf["inputs"]) or "- 不需要"
    problems = agent.validate_workflow(wf)
    return (f"🧩 {wf['name']}：{wf['title']}\n{wf['description']}\n\n需要的資訊：\n{need}\n\n步驟：\n{ws.outline(wf)}"
            + (f"\n\n⚠️ 規格有問題（執行時會被擋下）：{'；'.join(problems)}" if problems else "")
            + f"\n\n規格：skills_system/workflows/{wf['name']}.md")


def action_for(args):
    return {"command": WORKFLOW_SCRIPT, "args": args}


def synthetic_reply(args):
    """放進主對話的那一則「AI 的動作」（跟 /analyze 一樣）：之後的回合 AI 看得到這個工作流是使用者指定的。"""
    return json.dumps({"thought": "使用者用 /workflow 直接指定要執行的工作流，照使用者給的參數執行",
                       "reply": reply_text(args), "action": action_for(args)}, ensure_ascii=False)


def reply_text(args):
    return f"照你指定的執行工作流：{args}"


def user_note(args):
    return f"（我用 /workflow 直接執行工作流：{args}。執行完照報告告訴我結果；停在【確認】或沒有完成時說明卡在哪裡、接下來可以怎麼做。）"


def begin(agent, args):
    """CLI 與 Web 共用的開頭：記下任務、結束上一個計畫、把使用者的指定與「AI 的動作」放進主對話。
    回傳 (parsed, guard, 提示)：guard 有值＝要先經過確認關卡（CLI 問 y/n、Web 推確認卡片），核准後 run_tool(parsed, approved=True)；
    提示是結束上一個計畫的說明（沒有就是 None）。"""
    agent.set_current_task(f"/workflow {args}")
    note = agent.end_plan_for_new_task()
    agent.messages.append({"role": "user", "content": user_note(args)})
    agent.messages.append({"role": "assistant", "content": synthetic_reply(args)})
    parsed = {"thought": "", "reply": reply_text(args), "action": action_for(args)}
    return parsed, agent.guard_check(parsed), note


def job_status(agent):
    """剛才那次 workflow_run 的工作 → 狀態（done／ended／failed／unverified／paused／cancelled）；沒有執行（參數錯等）是 None。"""
    job_id = getattr(agent, "last_workflow_job", None)
    job = agent._workflow_store().load(job_id) if job_id else None
    return (job or {}).get("status")


def run_headless(args, yes=False, model=None, agent=None, cwd=None):
    """不用互動執行一次（心跳、排程、測試）：回傳 (結束碼, 印出的文字)。會改變狀態的步驟沒有 yes 就不執行。"""
    if agent is None:
        from .agent import SkillAgent
        agent = SkillAgent(model=model) if model else SkillAgent()
        if not model:
            agent.load_model_settings()
        agent.reset_conversation()
    if cwd:
        agent.current_cwd = cwd
    kind, arg = parse(args)
    if kind == "list":
        return 0, list_text(agent)
    if kind == "show":
        return 0, show_text(agent, arg)
    if kind == "error":
        return EXIT_NOT_RUN, arg
    agent.set_current_task(f"/workflow {arg}")
    parsed = {"action": action_for(arg)}
    guard = agent.guard_check(parsed)
    if guard and not yes:
        return EXIT_NEEDS_APPROVAL, (f"[需要核准，沒有執行] {agent.guard_prompt_text(guard)}\n"
                                     f"（不用互動的執行沒有人在旁邊確認：事先核准就加 --yes 再執行一次）")
    report = agent.run_tool(parsed, approved=True) or "[ERROR] 沒有輸出"
    status = job_status(agent)
    return EXIT_CODES.get(status, 1) if status else EXIT_NOT_RUN, report


def main_headless(argv):
    """Agent_Runner.py --workflow 的進入點：選項（--yes、--model、--cwd）放在哪裡都可以，其他的字照順序是 workflow_run 的參數
    （整段用引號包成一個也可以）。印出報告，回傳結束碼。"""
    opts, rest, it = {"yes": False, "model": None, "cwd": None}, [], iter(argv)
    for tok in it:
        if tok == "--workflow":
            continue
        if tok in ("--yes", "-y"):
            opts["yes"] = True
        elif tok in ("--model", "--cwd"):
            val = next(it, None)
            if not val:
                print(f"{tok} 後面要接值。{HEADLESS_USAGE}")
                return EXIT_NOT_RUN
            opts[tok[2:]] = val
        elif tok in ("-h", "--help"):
            print(f"{HEADLESS_USAGE}\n\n{__doc__}")
            return 0
        else:
            rest.append(tok)
    args = rest[0] if len(rest) == 1 else shlex.join(rest)
    code, text = run_headless(args, yes=opts["yes"], model=opts["model"], cwd=opts["cwd"])
    print(text)
    return code
