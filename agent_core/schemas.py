"""給 Ollama format= 的 JSON schema：主對話回覆、領域 session 的回覆、滾動摘要、工具摘要、提煉、第 1 級修正。"""
from .config import (DOMAIN_ANSWER_CHARS, DOMAIN_GOAL_CHARS, DOMAIN_ITEM_CHARS, DOMAIN_ITEMS_MAX, DOMAIN_REFS_MAX,
                     REPLY_ARGS_CHARS, REPLY_COMMAND_CHARS, REPLY_THOUGHT_CHARS, SCHEMA_MAX_CHARS)

DOMAIN_REPLY_CHARS = 600         # 領域 session 每一輪的 reply（一句這一步在做什麼，回報時一句總結）
DOMAIN_SKILL_CHARS = 80          # 領域 session 選的技能名稱


def _text(n):
    """字串欄位都有上限（同視覺提取的教訓：小模型偶爾會在陣列或字串裡失控，有上限就一定是合法的 JSON）。上限要在 SCHEMA_MAX_CHARS（2000）
    以內：Ollama（llama.cpp 的文法）不套用更大的 maxLength，寫大了就在這裡報錯，不會默默沒有上限。"""
    if n > SCHEMA_MAX_CHARS:
        raise ValueError(f"maxLength {n} 超過 {SCHEMA_MAX_CHARS}：Ollama 不會套用這個上限")
    return {"type": "string", "maxLength": n}


# 🧷 回覆協議：模型每次回覆都是一個 JSON 物件 {thought, reply, action}。執行與否只看 action 欄位，
# reply 裡不論寫了什麼（包括解釋、舉例時抄出來的 `EXECUTE: ...` 字串）都不會被執行——這是「實體隔離」：
# 給人看的文字與給系統執行的指令分開存放，不再用文字比對從回覆裡找指令。以 Ollama 的 format= schema 強制
# 結構（與摘要同一機制），小模型不需要自律「解釋時不要輸出指令」。
# action 為 null、{"command": 技能名稱｜規格標明的腳本路徑, "args": 參數字串}，或（有領域時）「交辦」{"task": {"goal": 子目標,
# "items": [{"quote": 使用者的原話, "item": 要回答的項目}]}}（agent_core/orchestrator.py：交給領域 session，不指定領域；
# quote 一字不改地抄使用者的原話、程式核對，領域 session 照原話判斷項目的意思——框架討論紀錄第 6 輪的 B）。
# args 是字串而不是物件，因為所有技能腳本都吃位置參數、規格文件的寫法也是位置參數，這樣既有的 tools/*.md 一份都不用改：
# 規格裡的 `EXECUTE: <路徑> <參數>` 範例就對應 command=<路徑>、args=<參數>。
# items：這一回合交辦、有報告的項目數。有的時候多一個 answers：每一項一筆 {item: 編號, status: answered／not_found,
# text: 回答或查不到的原因, refs: 報告裡的出處}，程式核對之後照項目排給使用者；還要做別的動作時填 []。
# 欄位順序就是生成順序（Ollama 照 schema 的順序輸出）：action 一律放最後，回覆寫完 action 就結束，跟 AGENT.md 的範例一樣
# （answers 排在 action 後面時，模型照範例寫完 action 要收尾的 `"}}` 不合法，結尾的符號就寫進了 args）。
# thought、command、args 也有上限（REPLY_*_CHARS）：寫到上限＝被截斷，protocol.parse_agent_reply 記在 cut。reply 不設上限
# （給使用者的回答可能比 2000 字長，Ollama 又不套用超過 2000 的上限；config 的說明）。


def _answer(items):
    p = {"item": {"type": "integer", "enum": list(range(1, items + 1))}, "status": {"type": "string", "enum": ["answered", "not_found"]},
         "text": _text(DOMAIN_ANSWER_CHARS), "refs": {"type": "array", "items": _text(DOMAIN_ITEM_CHARS), "maxItems": DOMAIN_REFS_MAX}}
    return {"type": "object", "properties": p, "required": list(p)}


def _task_item():
    """交辦的一項：quote＝使用者的原話裡、這一項在問的那一段（一字不改，orchestrator._check_task 核對），item＝要回報的事（可以把「它」
    這種指代補上名稱）。先寫 quote 再寫 item：欄位的順序就是生成的順序，先抄原話再寫自己的話（同參數表單的 quote、value）。"""
    p = {"quote": _text(DOMAIN_GOAL_CHARS), "item": _text(DOMAIN_ITEM_CHARS)}
    return {"type": "object", "properties": p, "required": list(p)}


def agent_reply_schema(tasks=False, items=0):
    actions = [
        {"type": "null"},
        {"type": "object", "properties": {"command": _text(REPLY_COMMAND_CHARS), "args": _text(REPLY_ARGS_CHARS)}, "required": ["command", "args"]},
    ]
    if tasks:
        task = {"type": "object", "properties": {
            "goal": _text(DOMAIN_GOAL_CHARS),
            "items": {"type": "array", "items": _task_item(), "minItems": 1, "maxItems": DOMAIN_ITEMS_MAX}},
            "required": ["goal", "items"]}
        actions.append({"type": "object", "properties": {"task": task}, "required": ["task"]})
    props = {"thought": _text(REPLY_THOUGHT_CHARS), "reply": {"type": "string"}}
    if items:
        props["answers"] = {"type": "array", "maxItems": items, "items": _answer(items)}
    props["action"] = {"anyOf": actions}
    return {"type": "object", "properties": props, "required": list(props)}


def domain_session_schema(domains, items):
    """領域 session 每一輪的回覆（agent_core/domain_session.py，F4）：state 是三種之一——domains（選領域）、skill（用一個技能：只寫名稱，
    參數在下一輪的表單填，domain_form_schema）、report（回報）。欄位都要寫（用不到的寫空的），程式照 state 取用與核對；欄位的順序就是
    生成的順序（先寫理由與狀態，最後一句 reply）。"""
    props = {"thought": _text(REPLY_THOUGHT_CHARS),
             "state": {"type": "string", "enum": ["domains", "skill", "report"]},
             "domains": {"type": "array", "items": {"type": "string", "enum": list(domains)}, "maxItems": max(1, len(domains))},
             "skill": _text(DOMAIN_SKILL_CHARS),
             "answers": {"type": "array", "items": _answer(max(1, items)), "maxItems": max(1, items)},
             "reply": _text(DOMAIN_REPLY_CHARS)}
    return {"type": "object", "properties": props, "required": list(props)}


def domain_form_schema(params=None):
    """選了技能的下一輪：那個技能的參數表單（F3）。params＝有骨架的技能這一輪要填的參數名稱——每個參數一欄 {quote, value}，參數名稱就是
    欄位（先抄原文再寫值；交回重填時只有沒過的那幾個）；None＝工具：只有 args。只有該填的欄位：有骨架的技能的參數寫成 args、工具的參數
    寫成 params、參數那一筆的名稱跟叫 name 的參數撞在一起（第 3 步的紀錄，設計筆記 2.57 ①），都寫不出來。"""
    props = {"thought": _text(REPLY_THOUGHT_CHARS)}
    if params is None:
        props["args"] = _text(REPLY_ARGS_CHARS)
    else:
        cell = {"type": "object", "properties": {"quote": _text(DOMAIN_GOAL_CHARS), "value": _text(DOMAIN_GOAL_CHARS)}, "required": ["quote", "value"]}
        props["params"] = {"type": "object", "properties": {name: cell for name in params}, "required": list(params)}
    return {"type": "object", "properties": props, "required": list(props)}


# 融合摘要的 JSON schema：交給 Ollama 的 format= 做結構化輸出，再由 _render_summary_markdown 排版。
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "key_progress": {"type": "array", "items": {"type": "string"}},
        "results_and_errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["category", "description", "detail"],
            },
        },
        "user_preferences": {"type": "array", "items": {"type": "string"}},
        "open_items": {"type": "array", "items": {"type": "string"}},
        # 只描述「這次被壓掉的那一段」（不是整份滾動摘要），寫進檢索清單的「過去的對話片段」，日後靠它認出要 recall 哪一段
        "segment_hint": {"type": "string"},
    },
    "required": ["overview", "key_progress", "results_and_errors", "user_preferences", "open_items", "segment_hint"],
}

# 任務導向摘要的結構（Ollama format=）：answer 一句話回答這一步的目的、facts 照抄的相關事實、errors 錯誤原文、
# not_covered 原始輸出沒有／被省略而無法確認的部分——讓主模型知道「摘要裡沒有」不等於「輸出裡沒有」。
_CITED = {"type": "object", "properties": {"text": {"type": "string"}, "lines": {"type": "string"}, "record": {"type": "string"}},
          "required": ["text", "lines"]}

# 工具回傳的提煉（agent_core/extract.py）：整合（或輸出不長時一次寫完）的結果。facts／errors 每一條附原文的行號（lines：「120」或「120-125」；
# 好幾份存檔一起讀時 record＝存檔編號），程式核對寫的名稱與數值真的在那幾行。
TOOL_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "facts": {"type": "array", "items": _CITED},
        "errors": {"type": "array", "items": _CITED},
        "not_covered": {"type": "string"},
        "suggested_questions": {
            "type": "array",
            "items": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
        },
        "index_hint": {"type": "string"},
        "related_records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["id", "reason"],
            },
        },
    },
    "required": ["answer", "facts", "errors", "not_covered", "suggested_questions", "index_hint", "related_records"],
}

# 分段提煉的整合：交出去的事實與錯誤由程式列（worker 核對過的全部，extract.listed_items），整合不挑、不寫事實，只寫回答與其他欄位
TOOL_SUMMARY_MERGE_SCHEMA = {
    "type": "object",
    "properties": {k: v for k, v in TOOL_SUMMARY_SCHEMA["properties"].items() if k not in ("facts", "errors")},
    "required": [k for k in TOOL_SUMMARY_SCHEMA["required"] if k not in ("facts", "errors")],
}

# 提煉的 worker：只讀一段原文，摘出跟問題有關的事實（附行號）
_LINED = {"type": "object", "properties": {"text": {"type": "string"}, "lines": {"type": "string"}}, "required": ["text", "lines"]}
EXTRACT_WORKER_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "facts": {"type": "array", "items": _LINED},
        "errors": {"type": "array", "items": _LINED},
        "summary": {"type": "string"},
    },
    "required": ["relevant", "facts", "errors", "summary"],
}

# 低階執行器的第 1 級修正（agent_core/edg.py）：一個工具節點參數錯（或逾時）時，只改這個節點的字面參數。先寫理由（哪裡錯、照規格怎麼改），
# 再寫修不修得好（要換工具、要使用者決定的是修不好，往上交）與新的參數（一個一個的字串，不用 shell 的引號）；程式再用腳本的 parse_args
# 檢查、核對逾時的縮小方式與範圍。寫成一行參數（像主對話的 action.args）時，e4b 常漏了引號、把腳本路徑也寫進去（2.29）。
EDG_FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": _text(300),
        "fixable": {"type": "boolean"},
        "args": {"type": "array", "items": _text(300), "maxItems": 20},
    },
    "required": ["reason", "fixable", "args"],
}
