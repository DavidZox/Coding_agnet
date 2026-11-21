"""給 Ollama format= 的 JSON schema：主對話回覆、滾動摘要、工具摘要、數據分析。"""
from .config import (DOMAIN_ANSWER_CHARS, DOMAIN_GOAL_CHARS, DOMAIN_ITEM_CHARS, DOMAIN_ITEMS_MAX, DOMAIN_PLAN_MAX, DOMAIN_REFS_MAX,
                     REPLY_ARGS_CHARS, REPLY_COMMAND_CHARS, REPLY_THOUGHT_CHARS, SCHEMA_MAX_CHARS)


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
# action 為 null、{"command": 技能名稱｜規格標明的腳本路徑, "args": 參數字串}，或（有領域時）「分工」
# {"domains": [{"domain": DOMAIN.md 列的領域, "goal": 這個領域的子目標, "items": [要回答的項目]}, …]}（新架構的高階，agent_core/orchestrator.py；
# 第 5 步 5-3：要用的領域一次選出來，同一個領域只出現一次）。
# args 是字串而不是物件，因為所有技能腳本都吃位置參數、規格文件的寫法也是位置參數，這樣既有的 tools/*.md 一份都不用改：
# 規格裡的 `EXECUTE: <路徑> <參數>` 範例就對應 command=<路徑>、args=<參數>。
# items：這一回合交給領域、有報告的項目數（4-2，G4）。有的時候多一個 answers：每一項一筆 {item: 編號, status: answered／not_found,
# text: 回答或查不到的原因, refs: 報告裡的出處}，程式核對之後照項目排給使用者；還要做別的動作時填 []。
# 欄位順序就是生成順序（Ollama 照 schema 的順序輸出）：action 一律放最後，回覆寫完 action 就結束，跟 AGENT.md 與子工作階段的範例一樣。
# answers 排在 action 後面時，模型照範例寫完 action 要收尾的 `"}}` 不合法，結尾的符號就寫進了 args（第 5 步 5-3 的評測：`"args": "WP_P1}}"`）。
# others：子工作階段（主對話是 None）。收尾多一種 status out_of_domain（這一項不屬於這個領域，text 寫理由；第 5 步 5-3），查不到、不屬於的
# 那一項多一個 domain：哪個領域查得到（others 的其中一個，都不是寫 NO_ROUTE；第 5 步 5-4）。每一項是兩種形狀之一：答到的沒有 domain，
# 查不到、不屬於的一定有（文法保證：原因寫成程式看得懂的欄位，不靠主模型讀報告的文字）；domain 排在 text 後面：先寫原因再選領域。
# thought、command、args 也有上限（REPLY_*_CHARS，第 5 步 5-1）：寫到上限＝被截斷，protocol.parse_agent_reply 記在 cut。reply 不設上限
# （給使用者的回答可能比 2000 字長，Ollama 又不套用超過 2000 的上限；config 的說明）。
NO_ROUTE = "none"


def agent_reply_schema(domains=(), items=0, others=None):
    actions = [
        {"type": "null"},
        {"type": "object", "properties": {"command": _text(REPLY_COMMAND_CHARS), "args": _text(REPLY_ARGS_CHARS)}, "required": ["command", "args"]},
    ]
    if domains:
        entry = {"type": "object", "properties": {
            "domain": {"type": "string", "enum": list(domains)}, "goal": _text(DOMAIN_GOAL_CHARS),
            "items": {"type": "array", "items": _text(DOMAIN_ITEM_CHARS), "minItems": 1, "maxItems": DOMAIN_ITEMS_MAX}},
            "required": ["domain", "goal", "items"]}
        actions.append({"type": "object", "properties": {
            "domains": {"type": "array", "items": entry, "minItems": 1, "maxItems": DOMAIN_PLAN_MAX}}, "required": ["domains"]})
    props = {"thought": _text(REPLY_THOUGHT_CHARS), "reply": {"type": "string"}}
    if items:
        def answer(statuses, route=None):
            p = {"item": {"type": "integer", "enum": list(range(1, items + 1))}, "status": {"type": "string", "enum": statuses},
                 "text": _text(DOMAIN_ANSWER_CHARS), "refs": {"type": "array", "items": _text(DOMAIN_ITEM_CHARS), "maxItems": DOMAIN_REFS_MAX}}
            if route is not None:
                p["domain"] = {"type": "string", "enum": route}
            return {"type": "object", "properties": p, "required": list(p)}
        one = (answer(["answered", "not_found"]) if others is None else
               {"anyOf": [answer(["answered"]), answer(["not_found", "out_of_domain"], list(others) + [NO_ROUTE])]})
        props["answers"] = {"type": "array", "maxItems": items, "items": one}
    props["action"] = {"anyOf": actions}
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


# 新架構的中階（agent_core/mid.py）：挑技能與合約的 schema 跟著領域的技能、技能的參數變，所以用函式產生。
# 挑技能：先寫理解（要找什麼、範圍、要回答哪幾項），再寫問題要的是哪幾種（位置、數量、內容：程式核對選的技能答得了每一種），
# 再從列出的名稱裡選一個（none＝這個領域沒有技能做得到、out_of_domain＝不屬於這個領域），最後寫理由。
def mid_select_schema(names, kinds):
    return {"type": "object",
            "properties": {"understanding": _text(400),
                           "asks": {"type": "array", "items": {"type": "string", "enum": list(kinds)}, "minItems": 1, "maxItems": len(kinds)},
                           "skill": {"type": "string", "enum": list(names) + ["none", "out_of_domain"]}, "reason": _text(300)},
            "required": ["understanding", "asks", "skill", "reason"]}


# 合約：每個參數一格，先抄原文（quote）再寫值（value）；沒提到的兩個都留空。only＝只重寫這幾個參數（核對沒過、交回修一次時）。
def mid_contract_schema(params, only=None):
    props = {"understanding": _text(300)}
    for p in params:
        if only is None or p["name"] in only:
            props[p["name"]] = {"type": "object", "properties": {"quote": _text(200), "value": _text(200)}, "required": ["quote", "value"]}
    return {"type": "object", "properties": props, "required": list(props)}


# 判斷節點（agent_core/judge.py、mid.Worker._judgment）：先寫理解，再挑行（來源是原文的 #編號、檔案是原文裡的檔案、行號、片段一字不改、
# 標籤照技能列的；片段對到好幾行時用行號選），再從技能列的分支選一條、填那條路要的參數（每條路的參數合在一起，沒有要填的留空），最後寫理由。
# fix＝交回修一次：只重寫沒過的（挑的行重抄；分支的參數沒過時可以重選分支）。
def _judge_param(p, files):
    if p["type"] == "words":
        return {"type": "array", "items": _text(80), "maxItems": 8}
    if p["type"] == "path":
        return {"type": "string", "enum": list(files) + [""]}
    return {"type": "integer"}


def mid_judge_schema(sources, files, labels, branches, max_lines, fix_lines=False, fix_branch=False):
    line = {"type": "object", "properties": {"source": {"type": "string", "enum": list(sources)}, "file": {"type": "string", "enum": list(files)},
                                             "line": {"type": "integer"}, "quote": _text(300), "label": {"type": "string", "enum": list(labels)}},
            "required": ["source", "file", "line", "quote", "label"]}
    params = {}
    for b in branches:
        for p in b.get("params") or []:
            params.setdefault(p["name"], _judge_param(p, files))
    props = {}
    if not (fix_lines or fix_branch):
        props["understanding"] = _text(400)
    if fix_lines or not fix_branch:
        props["lines"] = {"type": "array", "items": line, "maxItems": max_lines}
    if fix_branch or not fix_lines:
        props["branch"] = {"type": "string", "enum": [b["id"] for b in branches]}
        if params:
            props["params"] = {"type": "object", "properties": params, "required": list(params)}
    if not (fix_lines or fix_branch):
        props["reason"] = _text(300)
    return {"type": "object", "properties": props, "required": list(props)}


# 公佈欄的 worker（agent_core/board.py，方向的實驗）：規劃一次決定一步——先寫理解（每一項還缺什麼），再寫下一步是用工具還是回答、為第幾項
# （0＝好幾項共用）、要在輸出裡找什麼（提煉的錨點），最後是工具與參數（一個一個的字串；回答時 tool 寫 none、args 空的）。
def board_plan_schema(tools, n_items):
    return {"type": "object",
            "properties": {"understanding": _text(500), "next": {"type": "string", "enum": ["tool", "answer"]},
                           "item": {"type": "integer", "enum": list(range(0, n_items + 1))}, "look_for": _text(200),
                           "tool": {"type": "string", "enum": list(tools) + ["none"]},
                           "args": {"type": "array", "items": _text(300), "maxItems": 16}},
            "required": ["understanding", "next", "item", "look_for", "tool", "args"]}


# 公佈欄的「看」：一份工具輸出（太長時的一段）摘出跟問題有關的事實，每一則附輸出的行號（程式核對名稱與數值在那幾行，再換成 檔案:行號）。
def board_look_schema(max_facts, fact_chars):
    return {"type": "object",
            "properties": {"relevant": {"type": "boolean"},
                           "facts": {"type": "array", "items": {"type": "object", "properties": {"text": _text(fact_chars), "lines": _text(40)},
                                                                "required": ["text", "lines"]}, "maxItems": max_facts}},
            "required": ["relevant", "facts"]}


# 公佈欄的回答：每一項一筆——答到、查不到或不屬於這個領域，回答或理由，根據的事實編號（程式核對回答裡的名稱與數值在那幾則事實裡）。
def board_answer_schema(n_items, n_facts, answer_chars, refs_max):
    one = {"type": "object",
           "properties": {"item": {"type": "integer", "enum": list(range(1, n_items + 1))},
                          "status": {"type": "string", "enum": ["answered", "not_found", "out_of_domain"]}, "text": _text(answer_chars),
                          "facts": {"type": "array", "items": {"type": "integer", "enum": list(range(1, n_facts + 1)) or [0]},
                                    "maxItems": refs_max}},
           "required": ["item", "status", "text", "facts"]}
    return {"type": "object", "properties": {"answers": {"type": "array", "items": one, "minItems": 1, "maxItems": n_items}},
            "required": ["answers"]}

