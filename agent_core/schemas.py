"""給 Ollama format= 的 JSON schema：主對話回覆、滾動摘要、工具摘要、技能草稿。"""
import json


# 🧷 回覆協議：模型每次回覆都是一個 JSON 物件 {thought, reply, action}。執行與否只看 action 欄位，
# reply 裡不論寫了什麼（包括解釋、舉例時抄出來的 `EXECUTE: ...` 字串）都不會被執行——這是「實體隔離」：
# 給人看的文字與給系統執行的指令分開存放，不再用文字比對從回覆裡找指令。以 Ollama 的 format= schema 強制
# 結構（與摘要、make_skill 同一機制），小模型不需要自律「解釋時不要輸出指令」。
# action 為 null 或 {"command": 技能名稱｜規格標明的腳本路徑, "args": 參數字串}；args 是字串而不是物件，
# 因為所有技能腳本都吃位置參數、規格文件的寫法也是位置參數，這樣既有的 tools/*.md 一份都不用改：
# 規格裡的 `EXECUTE: <路徑> <參數>` 範例就對應 command=<路徑>、args=<參數>。
AGENT_REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "reply": {"type": "string"},
        "action": {"anyOf": [
            {"type": "null"},
            {
                "type": "object",
                "properties": {"command": {"type": "string"}, "args": {"type": "string"}},
                "required": ["command", "args"],
            },
        ]},
    },
    "required": ["thought", "reply", "action"],
}

# /make_skill 的工作流草稿（Ollama format=）：欄位意義見 SkillAgent._make_skill_prompts，驗證見 _normalize_skill_draft。
# 欄位順序＝生成順序：先讀完對話寫用途，再逐條列出使用者的要求（requirements），然後才寫需要的資訊與步驟——實測
# 直接寫步驟時，e4b 與 26b 都會漏掉使用者說過的條件（「低電量的車不要派任務」「派之前先跟我確認」）；
# 最後才寫標題與索引描述（根據寫好的內容總結）。
# 陣列與字串都有上限（同視覺提取的教訓：小模型偶爾會在陣列或字串裡失控，有上限就一定是合法的 JSON）。
MAKE_SKILL_STEP_KINDS = ["執行", "確認", "檢查", "告知"]


def _text(n):
    return {"type": "string", "maxLength": n}


MAKE_SKILL_SCHEMA = {
    "type": "object",
    "properties": {
        "purpose": _text(400),
        "requirements": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {"said": _text(150), "rule": _text(150), "step": {"type": "integer"}},
                "required": ["said", "rule", "step"],
            },
        },
        "inputs": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {"name": _text(40), "description": _text(120), "source": _text(80), "example": _text(120)},
                "required": ["name", "description", "source", "example"],
            },
        },
        "steps": {
            "type": "array",
            "maxItems": 15,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": MAKE_SKILL_STEP_KINDS},
                    "instruction": _text(300),
                    "skill": _text(40),
                    "command": _text(300),
                    "on_failure": _text(200),
                },
                "required": ["kind", "instruction", "skill", "command", "on_failure"],
            },
        },
        "success_criteria": _text(200),
        "pitfalls": {"type": "array", "maxItems": 8, "items": _text(150)},
        "title": _text(30),
        "description": _text(100),
        "category": _text(40),
    },
    "required": ["purpose", "requirements", "inputs", "steps", "success_criteria", "pitfalls", "title", "description",
                 "category"],
}

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


# /plan 草稿的自然語言修改（PlanMixin）：只輸出「要套用的操作」，不重寫整份——小模型重寫時會把 4 步變 2 步、把沒提到的步驟改掉。
# 操作由 harness 套用在保存的草稿（任務引擎的計畫）上。
PLAN_OPS_SCHEMA = {
    "type": "object",
    "properties": {
        "ops": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["add", "insert", "edit", "delete", "move"]},
                "step": {"type": "integer"},
                "to": {"type": "integer"},
                "skill": {"type": "string"},
                "goal": {"type": "string"},
            },
            "required": ["op", "step", "to", "skill", "goal"],
        }},
    },
    "required": ["ops"],
}


# 🧭 任務引擎（agent_core/task_engine.py）的規劃 session。欄位順序＝生成順序：先寫對任務的理解（要查什麼、要改什麼、
# 使用者有沒有說先確認），再列步驟，最後寫要回報的重點——同 MAKE_SKILL_SCHEMA 的教訓，直接列步驟時小模型會漏掉條件。
# 每一步：技能（skills），或整段正好是一個工作流（workflow＋workflow_args，skills 留空）；check：做完那一步用哪個唯讀技能確認
# （技能、參數、輸出要出現的字樣），只有查詢的步驟填 null。
_TASK_CHECK = {
    "type": "object",
    "properties": {"skill": _text(40), "args": _text(300), "expect": _text(120)},
    "required": ["skill", "args", "expect"],
}

_TASK_ITEM = {
    "type": "object",
    "properties": {
        "title": _text(60),
        "goal": _text(600),
        "skills": {"type": "array", "maxItems": 5, "items": _text(40)},
        "workflow": _text(60),
        "workflow_args": _text(400),
        "changes_state": {"type": "boolean"},
        "check": {"anyOf": [{"type": "null"}, _TASK_CHECK]},
    },
    "required": ["title", "goal", "skills", "workflow", "workflow_args", "changes_state", "check"],
}

# 使用者要把結果寫成檔案（報告、紀錄、交班）時的檔案與寫法：不排寫檔的步驟，系統最後依核對過的內容寫（path 空的＝不用寫檔）
_TASK_OUTPUT = {
    "type": "object",
    "properties": {"path": _text(200), "mode": {"type": "string", "enum": ["write", "append"]}},
    "required": ["path", "mode"],
}

TASK_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "understanding": _text(400),
        "summary": _text(200),
        "items": {"type": "array", "maxItems": 6, "items": _TASK_ITEM},
        "output": _TASK_OUTPUT,
        "report": _text(300),
    },
    "required": ["understanding", "summary", "items", "output", "report"],
}


def task_profile_schema(names):
    """沒有指定任務類型時選一個（只填類型與一句理由）：enum 是現有的類型。"""
    return {"type": "object", "properties": {"profile": {"type": "string", "enum": list(names)}, "reason": _text(200)},
            "required": ["profile", "reason"]}


# 整合（Synthesizer）：所有步驟做完之後依核對過的事實寫結論或報告。每一則附出處（工具輸出的 #編號），程式核對名稱與數值在引用的
# 輸出裡；unknowns 是還不確定、沒查到的（也核對）。欄位順序＝生成順序：先分節寫每一則，最後寫不確定的
_TASK_SYNTH_ITEM = {"type": "object", "properties": {"text": _text(300), "refs": {"type": "array", "maxItems": 4, "items": _text(12)}},
                    "required": ["text", "refs"]}
TASK_SYNTH_SCHEMA = {
    "type": "object",
    "properties": {
        "title": _text(80),
        "sections": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {"heading": _text(40), "items": {"type": "array", "maxItems": 12, "items": _TASK_SYNTH_ITEM}},
            "required": ["heading", "items"]}},
        "unknowns": _text(600),
    },
    "required": ["title", "sections", "unknowns"],
}

# 整合的核對不過時交回改一次：只輸出那幾則（n＝交回時的編號）改正後的內容，找不到根據的 text 給空字串（拿掉）
TASK_SYNTH_FIX_SCHEMA = {
    "type": "object",
    "properties": {"fixes": {"type": "array", "maxItems": 20, "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"}, "text": _text(300), "refs": {"type": "array", "maxItems": 4, "items": _text(12)}},
        "required": ["n", "text", "refs"]}}},
    "required": ["fixes"],
}

# worker 回報的事實：每條附出處（這一步執行過的工具結果 #編號），程式核對名稱與數值在那份輸出裡找得到
_TASK_FACT = {"type": "object", "properties": {"text": _text(200), "ref": _text(20)}, "required": ["text", "ref"]}
_TASK_FACTS = {"type": "array", "maxItems": 8, "items": _TASK_FACT}

# worker 的回覆：同 AGENT_REPLY_SCHEMA 加上 facts（做完那一輪才寫），每個字串都有上限——實測（2026-10-10，gemma4:26b）worker 寫檔時
# 偶爾在一個欄位裡失控、一次輸出三萬多個 token（一百多秒）才被上下文長度截斷；有上限就一定在合理的長度內結束、而且是合法的 JSON。
TASK_WORKER_REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": _text(600),
        "reply": _text(2000),
        "action": {"anyOf": [
            {"type": "null"},
            {
                "type": "object",
                "properties": {"command": _text(200), "args": _text(6000)},
                "required": ["command", "args"],
            },
        ]},
        "facts": _TASK_FACTS,
    },
    "required": ["thought", "reply", "action", "facts"],
}

# worker 用完步數還沒回報時，最後一次請它總結：這一步到底做完了沒有（實測：worker 改好檔案後一直做額外的檢查，用完 10 輪，
# 做完的工作被當成失敗）
TASK_WORKER_WRAPUP_SCHEMA = {
    "type": "object",
    "properties": {"done": {"type": "boolean"}, "summary": _text(1500), "facts": _TASK_FACTS},
    "required": ["done", "summary", "facts"],
}

# worker 回報「沒有完成」時對照這一步的目標問一次：目標做到了沒有（查到的結果有問題、修不了，不算沒做到）、照實的摘要
TASK_GOAL_CHECK_SCHEMA = {
    "type": "object",
    "properties": {"goal_met": {"type": "boolean"}, "summary": _text(1500)},
    "required": ["goal_met", "summary"],
}

# 事實核對不過時交回改一次：只輸出改正後的事實與摘要
TASK_FACTS_FIX_SCHEMA = {
    "type": "object",
    "properties": {"facts": _TASK_FACTS, "summary": _text(1500)},
    "required": ["facts", "summary"],
}
