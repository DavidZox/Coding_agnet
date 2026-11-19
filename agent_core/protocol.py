"""回覆協議與訊息包裝：解析主模型的 JSON 回覆、把工具結果包成主對話訊息、判斷回傳是不是規格文件或已提煉的結果。"""
import json
import os
from .config import (ANALYSIS_REPORT_HEAD, DOMAIN_RESULT_HEAD, REPLY_ARGS_CHARS, REPLY_COMMAND_CHARS, REPLY_TEXT_CHARS, REPLY_THOUGHT_CHARS,
                     SKILL_DOC_PREFIX, TOOL_RESULT_FRAME, TOOL_SUMMARY_TAG)
from . import prompt_files

_FRAME = "harness/tool_results.md"   # 工具結果的框架句（【系統回傳】是程式認的標記，留在程式）
_CAPS = (("thought", REPLY_THOUGHT_CHARS), ("reply", REPLY_TEXT_CHARS))           # 回覆的字串上限（schemas.agent_reply_schema）
_ACTION_CAPS = (("command", REPLY_COMMAND_CHARS), ("args", REPLY_ARGS_CHARS))


def attach_skill_docs(message, blocks):
    """把使用者手動載入的技能規格區塊（manual_skill_block 的回傳）附在這則使用者訊息後面。
    跟 📷 影像分析結果同一種做法：使用者原文在前、系統插入的內容在後，主對話維持純文字單一訊息，
    不會出現連續兩則 user 訊息。"""
    blocks = [b for b in (blocks or []) if b]
    if not blocks:
        return message
    return message + "\n\n" + "\n\n".join(blocks)


def quote_cli_arg(arg):
    """含空白／引號的參數以雙引號包住（與規格範例一致，shlex 可還原）。"""
    arg = str(arg)
    if arg == "" or any(c.isspace() for c in arg) or '"' in arg or "'" in arg:
        return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return arg


def _answers(value):
    """依報告回答的 answers（4-2）→ [{"item": int, "status": "answered"／"not_found", "text": str, "refs": [str]}]；格式不對的那一筆不要。"""
    out = []
    for a in value if isinstance(value, list) else []:
        if not isinstance(a, dict):
            continue
        try:
            item = int(a.get("item"))
        except (TypeError, ValueError):
            continue
        refs = a.get("refs")
        refs = [" ".join(str(x).split()) for x in (refs if isinstance(refs, list) else [refs]) if x is not None and str(x).strip()]
        status = str(a.get("status") or "").strip()
        out.append({"item": item, "status": status if status in ("answered", "not_found") else "answered",
                    "text": str(a.get("text") or "").strip(), "refs": refs})
    return out


def parse_agent_reply(raw):
    """模型回覆（JSON 字串）→ {"thought", "reply", "action", "answers", "valid", "cut"}。

    action 正規化為 None、{"command": str, "args": str}，或「交給領域」{"domain": str, "goal": str, "items": [str]}（新架構的高階，
    agent_core/orchestrator.py；項目去掉空白與空的，數量與長度由高階核對）。不是合法 JSON 時 valid=False、reply=原文、
    action=None：降級成「只顯示文字、不執行任何東西」，絕不退回用文字比對找指令（那正是要避免的誤觸發來源）。
    對非 format= 強制的後端保留一點容錯：args 給成陣列／物件、把整行 `EXECUTE: ...` 塞進 command、
    command 裡夾帶參數，都會被整理成同一種形狀；command 寫成 null／none 的跟 action 填 null 一樣（e4b 收尾時這樣寫，第 5 步 5-1 的評測）。
    answers 是依領域的報告回答的每一項（4-2；沒有時是空的清單，_answers）。cut：寫到字串上限（被截斷）的欄位（thought、reply、command、args；
    REPLY_*_CHARS），呼叫的一方重問一次（conversation.ask_ai、sub.Session._ask），還是被截斷就 drop_cut。"""
    text = (raw or "").strip()
    if text.startswith("```"):  # format= 下不會出現，保險去掉程式碼區塊包裹
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        data = None
    if not isinstance(data, dict):
        return {"thought": "", "reply": (raw or "").strip(), "action": None, "answers": [], "valid": False, "cut": []}

    thought = str(data.get("thought") or "").strip()
    reply = data.get("reply")
    reply = "" if reply is None else str(reply).strip()
    answers = _answers(data.get("answers"))
    action = data.get("action")
    cut = [k for k, n in _CAPS if isinstance(data.get(k), str) and len(data[k]) >= n]
    if isinstance(action, dict):
        cut += [k for k, n in _ACTION_CAPS if isinstance(action.get(k), str) and len(action[k]) >= n]
    norm = None
    if isinstance(action, dict) and str(action.get("domain") or "").strip():
        items = action.get("items")
        items = [" ".join(str(x).split()) for x in (items if isinstance(items, list) else [items]) if x is not None and str(x).strip()]
        norm = {"domain": str(action["domain"]).strip(), "goal": " ".join(str(action.get("goal") or "").split()), "items": items}
        return {"thought": thought, "reply": reply, "action": norm, "answers": answers, "valid": True, "cut": cut}
    if isinstance(action, str) and action.strip().lower() not in ("", "null", "none"):
        action = {"command": action, "args": ""}
    if isinstance(action, dict):
        command = str(action.get("command") or "").strip()
        args = action.get("args")
        if isinstance(args, list):
            args = " ".join(quote_cli_arg(a) for a in args)
        elif isinstance(args, dict):
            args = " ".join(quote_cli_arg(v) for v in args.values())
        args = "" if args is None else str(args).strip()
        if command.upper().startswith("EXECUTE:"):
            command = command[len("EXECUTE:"):].strip()
        head, _, rest = command.partition(" ")
        if rest.strip():  # command 夾帶了參數："scripts/cd_cmd.py /opt" → 拆到 args 前面
            # 同樣的參數 command 與 args 都寫了一次（實測 ops worker 常這樣）：只留一份，不然參數會重複（ls rmf_sim ls）
            same = " ".join(rest.split()) == " ".join(args.split()) or (args and " ".join(args.split()).startswith(" ".join(rest.split())))
            command, args = head, (args if same else rest.strip() + (" " + args if args else ""))
        if command and command.lower() not in ("null", "none"):
            norm = {"command": command, "args": args}
    return {"thought": thought, "reply": reply, "action": norm, "answers": answers, "valid": True, "cut": cut}


def drop_cut(parsed):
    """寫到字串上限、重問一次還是被截斷的回覆 → (不執行動作的 parsed, 存進對話的原文)。command／args 被截斷的，action 換成 None
    （截斷的參數不能執行）；被截斷的 thought／reply 照樣留著、後面接一句說明。存進對話的是重新組的 JSON（沒有那段截斷的參數）：
    對話裡不留下一大段重複的字（跟空白回覆的重試同一個原則，conversation.ask_ai）。"""
    out = dict(parsed, cut=[])
    mark = prompt_files.load("harness/reminders.md", "cut_mark")
    for k, _ in _CAPS:
        if k in parsed["cut"]:
            out[k] = parsed[k] + mark
    if {"command", "args"} & set(parsed["cut"]):
        out["action"] = None
    raw = json.dumps({"thought": out["thought"], "reply": out["reply"], "action": out["action"], "answers": out["answers"]}, ensure_ascii=False)
    return out, raw


def answers_text(answers):
    """answers 的純文字（壓縮、對話片段存檔用：回答的內容不能因為寫在 answers 就在摘要裡不見）。"""
    return "\n".join(f"{a['item']}. " + ("查不到：" if a["status"] == "not_found" else "") + a["text"]
                     + (f"（出處：{'、'.join(a['refs'])}）" if a["refs"] else "") for a in answers or [])


def action_text(action):
    """action 的單行文字表示（顯示與軌跡用）：`command args`；交給領域是「→ 領域：子目標（項目：…）」。"""
    if not action:
        return ""
    if action.get("domain"):
        return f"→ {action['domain']}：{action.get('goal', '')}（項目：{'；'.join(action.get('items') or [])}）"
    return f"{action['command']} {action['args']}".strip()


def tool_result_message(content, action=None):
    """把工具結果包成進主對話的 user 訊息（CLI 三種模式、Web、捨棄通知統一用這個）。
    第一行固定 [tool result]（HARNESS_MARKERS 判定、壓縮切點、軌跡都認它），第二行是框架句：明說這是系統執行
    上一輪 action 的結果、不是使用者提供的、不要感謝使用者。

    為什麼寫在每一則裡而不是只寫在 AGENT.md：工具結果只能以 user 角色進入主對話——實測 Ollama 的 gemma4 模板會把
    role=tool 的訊息整個丟掉（模型完全看不到內容）；而 AGENT.md 的 Harness Messages 規則對 4B 模型不夠，實測仍回
    「感謝您提供的語義地圖」。影像分析結果（web_app.flows._run_vision_subsession）用的是同一招。
    action 可給 parse_reply 的 action dict 或指令字串，只取腳本檔名放進框架句方便模型對應。"""
    label = ""
    if isinstance(action, dict) and action.get("domain"):
        label = str(action["domain"])
    elif isinstance(action, dict) and action.get("command"):
        label = os.path.basename(str(action["command"]).strip())
    elif isinstance(action, str) and action.strip():
        label = os.path.basename(action.strip().split()[0])
    what = prompt_files.load(_FRAME, "frame_action", label=label) if label else prompt_files.load(_FRAME, "frame_action_plain")
    frame = TOOL_RESULT_FRAME + prompt_files.load(_FRAME, "frame", what=what)
    tail = TOOL_RESULT_FRAME + prompt_files.load(_FRAME, "frame_tail")   # 結尾再提醒一次：長輸出時開頭那句離模型太遠
    return f"[tool result]\n{frame}\n{content}\n{tail}"


def is_skill_doc_result(result):
    """result 是否為 run_tool 載入規格文件的回傳（而非腳本執行結果）。"""
    return bool(result) and result.lstrip().startswith(SKILL_DOC_PREFIX)


def is_exempt_result(result, tool_tokens):
    """不套用工具回傳門檻的結果：技能規格文件，以及本身已經是任務導向擷取的結果（result_recall 的輸出，以
    TOOL_SUMMARY_TAG 開頭）——後者再摘要一次只會摘要的摘要、多一次模型呼叫。所有腳本輸出（包括分析型的
    --watch／--duration／語義地圖）都走同一套規則——超過門檻就交給獨立 session 做任務導向擷取。
    CLI／Web 的 ⚠️ 標記與 _content_for_context 共用這個判斷。"""
    # analysis_run 的事實報告（ANALYSIS_REPORT_HEAD 開頭）同理：它本身就是程式整理好、有編號的事實；交給領域的結果（中階照收據
    # 整理的報告，DOMAIN_RESULT_HEAD 開頭）也是
    return is_skill_doc_result(result) or result.startswith((TOOL_SUMMARY_TAG, ANALYSIS_REPORT_HEAD, DOMAIN_RESULT_HEAD))
