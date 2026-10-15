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

# /make_skill 的流程技能草稿（Ollama format=）：欄位意義見 SkillAgent._make_skill_prompts，驗證見 _normalize_skill_draft。
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
TOOL_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}},
        "errors": {"type": "array", "items": {"type": "string"}},
        "not_covered": {"type": "string"},
        "suggested_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"question": {"type": "string"}, "keywords": {"type": "string"}},
                "required": ["question", "keywords"],
            },
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


# /plan 草稿（PlanMixin）：第一版由規劃 session 產生整份步驟；之後的自然語言修改只輸出「要套用的操作」，
# 不重寫整份——小模型重寫時會把 4 步變 2 步、把沒提到的步驟改掉。操作由 harness 套用在保存的草稿上。
PLAN_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": {
            "type": "object",
            "properties": {"skill": {"type": "string"}, "goal": {"type": "string"}},
            "required": ["skill", "goal"],
        }},
    },
    "required": ["steps"],
}

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


# 🧭 非編碼的多步驟任務（agent_core/ops_job.py）的規劃 session。欄位順序＝生成順序：先寫對任務的理解（要查什麼、要改什麼、
# 使用者有沒有說先確認），再列步驟，最後寫要回報的重點——同 MAKE_SKILL_SCHEMA 的教訓，直接列步驟時小模型會漏掉條件。
# check：做完那一步用哪個唯讀技能確認（技能、參數、輸出要出現的字樣）；只有查詢的步驟填 null。
_OPS_CHECK = {
    "type": "object",
    "properties": {"skill": _text(40), "args": _text(300), "expect": _text(120)},
    "required": ["skill", "args", "expect"],
}

_OPS_ITEM = {
    "type": "object",
    "properties": {
        "title": _text(60),
        "goal": _text(600),
        "skills": {"type": "array", "maxItems": 5, "items": _text(40)},
        "changes_state": {"type": "boolean"},
        "check": {"anyOf": [{"type": "null"}, _OPS_CHECK]},
    },
    "required": ["title", "goal", "skills", "changes_state", "check"],
}

OPS_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "understanding": _text(400),
        "summary": _text(200),
        "items": {"type": "array", "maxItems": 6, "items": _OPS_ITEM},
        "report": _text(300),
    },
    "required": ["understanding", "summary", "items", "report"],
}


# ops worker 的回覆：同 AGENT_REPLY_SCHEMA，但每個字串都有上限——實測（2026-10-10，gemma4:26b）worker 寫檔時偶爾在一個欄位裡
# 失控、一次輸出三萬多個 token（一百多秒）才被上下文長度截斷；有上限就一定在合理的長度內結束、而且是合法的 JSON。
OPS_WORKER_REPLY_SCHEMA = {
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
    },
    "required": ["thought", "reply", "action"],
}


# ops worker 用完步數還沒回報時，最後一次請它總結：這一步到底做完了沒有（實測：worker 改好檔案後一直做額外的檢查，用完 10 輪，
# 做完的工作被當成失敗）
OPS_WORKER_WRAPUP_SCHEMA = {
    "type": "object",
    "properties": {"done": {"type": "boolean"}, "summary": _text(1500)},
    "required": ["done", "summary"],
}


# 📊 數據解析的多 agent 協同（agent_core/analysis_job.py）。陣列與字串都有上限（同 OPS 的理由：小模型偶爾在一個欄位裡失控）。
# Orchestrator：欄位順序＝生成順序——先寫對問題的理解，再挑相關的 Log 訊號（只填編號，精確的時間戳由程式換算），
# 最後才指派 Topic（每個 worker 一個不同的 Topic）與子任務。
_ANALYSIS_ASSIGNMENT = {
    "type": "object",
    "properties": {
        "topic": _text(120),
        "subtask": _text(400),
        "signals": {"type": "array", "maxItems": 4, "items": _text(12)},
    },
    "required": ["topic", "subtask", "signals"],
}

ANALYSIS_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "understanding": _text(500),
        "related_signals": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {"id": _text(12), "why": _text(160)},
            "required": ["id", "why"],
        }},
        "before_sec": {"type": "number"},
        "after_sec": {"type": "number"},
        "assignments": {"type": "array", "maxItems": 8, "items": _ANALYSIS_ASSIGNMENT},
        "report_focus": _text(300),
    },
    "required": ["understanding", "related_signals", "before_sec", "after_sec", "assignments", "report_focus"],
}

# 有源碼脈絡時的計畫：每個指派多一個 source_context（這個子任務根據的源碼線索：檔案:行 函式、代碼的條件），
# 交給 worker、寫進局部報告的 Frontmatter
ANALYSIS_PLAN_SCHEMA_SOURCE = json.loads(json.dumps(ANALYSIS_PLAN_SCHEMA))
ANALYSIS_PLAN_SCHEMA_SOURCE["properties"]["assignments"]["items"]["properties"]["source_context"] = _text(240)
ANALYSIS_PLAN_SCHEMA_SOURCE["properties"]["assignments"]["items"]["required"] = ["topic", "subtask", "signals", "source_context"]

# worker 每一步的決定：同主對話的 {thought, reply, action}，字串有上限
ANALYSIS_WORKER_REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": _text(500),
        "reply": _text(1500),
        "action": {"anyOf": [
            {"type": "null"},
            {
                "type": "object",
                "properties": {"command": _text(120), "args": _text(600)},
                "required": ["command", "args"],
            },
        ]},
    },
    "required": ["thought", "reply", "action"],
}

# worker 的局部報告（Frontmatter Markdown 的模型部分）：analyzed_keys 程式會核對是不是真的量過；數字一律由程式從量測結果填，
# 這裡只要模型判斷「跟子任務有沒有關、算不算異常」與文字說明
ANALYSIS_WORKER_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "analyzed_keys": {"type": "array", "maxItems": 6, "items": _text(120)},
        "anomaly_detected": {"type": "boolean"},
        "summary": _text(800),
        "evidence": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {"time": _text(40), "key": _text(120), "observation": _text(200)},
            "required": ["time", "key", "observation"],
        }},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["analyzed_keys", "anomaly_detected", "summary", "evidence", "confidence"],
}

# Synthesizer 的根因診斷報告（Root Cause Analysis）
ANALYSIS_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "conclusion": _text(500),
        "root_cause": _text(700),
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "timeline": {"type": "array", "maxItems": 10, "items": {
            "type": "object",
            "properties": {"time": _text(40), "source": _text(80), "event": _text(220)},
            "required": ["time", "source", "event"],
        }},
        "evidence": {"type": "array", "maxItems": 10, "items": {
            "type": "object",
            "properties": {"source": _text(80), "fact": _text(260)},
            "required": ["source", "fact"],
        }},
        "unknowns": {"type": "array", "maxItems": 5, "items": _text(220)},
        "recommendations": {"type": "array", "maxItems": 5, "items": _text(220)},
    },
    "required": ["conclusion", "root_cause", "confidence", "timeline", "evidence", "unknowns", "recommendations"],
}
