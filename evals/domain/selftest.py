"""交辦與領域 session（agent_core/orchestrator.py、domain_session.py、composite.py；docs/框架討論紀錄.md）的離線自我測試：假的主模型與
領域 session 的模型照劇本回，真的有骨架的技能、低階與工具（工作目錄是臨時的小專案），直接驅動 Web 的回合（web_app.flows.run_turn），
幾秒跑完、不需要 Ollama。

- 主 session：system prompt 的「交辦」一節（每個領域一行）、技能索引拿掉領域的工具、回覆的 schema 多「交辦」；回覆的欄位順序（主 session 的
  action 最後、AGENT.md 的範例與存回對話的 JSON 也一樣；領域 session 照說明的順序）；擋領域的工具與有骨架的技能
  （領域 session 裡只能用它選的領域的工具與共用的工具）；交辦的核對（子目標是空的、項目數、一樣的再交一次、同一個項目最多 3 次）；
- 交辦的每一項是使用者的原話（quote 不在使用者說過的話裡擋下；之前幾則訊息裡的也可以）：領域 session 的第一則訊息、提煉的錨點、報告與
  要回答的項目都用原話；一輪的第一次交辦要把最新這一則的每一個問句放進項目（漏了交回一次、交回過照收）；
- 交辦帶前文：這一則之前的對話（使用者的話與當時的回覆）附在領域 session 的第一則訊息、算可以抄的原文，錨點帶使用者前面的話；長的存檔並提煉；
  每一項從新的對話開始（前文只看這一段對話）；
- 領域 session 用工具：選領域 → 技能清單（做法、有骨架的技能與參數、工具與 args 的寫法、共用的工具）→ 用一個工具（存檔 #編號）→ 回報（核對過）
  → 報告交回主 session（不提煉）＋依報告回答的說明 → 主 session 照項目回答（附出處那一行的原文）；
- 選了技能之後的參數表單：schema 只有該填的欄位（有骨架的技能每個參數一欄、參數名稱就是欄位；工具只有 args）、表單的那一輪不算在回的輪數裡；
  工具的 args 整個是 JSON、照抄了〈語法〉的佔位符、或可以不寫的部分填成「[]」的交回重填一次、還是一樣就回到選技能（不算一步；有中括號的搜尋字、
  引號裡的「[]」不誤擋）；
- 有骨架的技能：合約（原文要在給它看過的字裡）沒過的只把那幾個參數交回重填一次、還是沒過就回到選技能，都不算一步；原文開頭抄了程式的
  標題（「【子目標】」）的拿掉再核對；照骨架執行、每個節點的結果附 #編號；一模一樣的不執行；路徑的一段混了說明的字或結尾的萬用字元時
  只留原文裡的那個名稱（結果裡寫明；好幾個名稱、翻譯、接在一起的照舊交回）；值對得上原文的不擋：quote 抄了別段或沒抄、值本身就在原文裡，
  搜尋的字不分大小寫，預設值與空的當成沒提到，工作目錄與底下的絕對路徑換成「.」與相對路徑（編的檔名、翻成英文的字、搜尋的文字寫成好幾個、
  原文沒有的值照舊交回；路徑的預設值配的 quote 寫了別的名稱的交回，quote 是工作目錄或它路徑上的一段的照收；「.」「..」不算名稱；
  骨架對搜尋的字加 --case 的載入時擋下）；原文沒有的搜尋字，要搜的範圍（同一張表單的 path、files、exclude）裡有才收、出處寫範圍
  （範圍裡沒有的、詞組照字面沒有的、| 分開的有一個沒有的、正規表示式的符號、寫成好幾個的、path 沒過的、doc_lookup 的字、自己選的檔名寫法照舊
  交回；agent 自己的 logs 不數）；
  回退換技能（.py 沒有、C++ 檔有 → cpp_symbol）；路徑有好幾個交回它決定（附候選）；0 筆照實交回（跑完、結果是 0 筆）；
  cpp_symbol 先列有本體的定義（code_defs --has：.cpp 的成員函式、標頭檔的類別；; 結尾的宣告不列），再搜名稱（宣告與用到的地方）；
  程式照收據算的彙整（AST 的定義、呼叫與 import 每個檔案幾處、總共幾處；名稱符合的檔案扣掉不含的子目錄）存成 #編號、接在技能的狀態後面，
  回報的總數照它寫、出處寫它的 #編號就過核對；
- 狀態與上限：第一輪不是選領域、回覆不是 JSON、重選領域超過上限、技能用完上限；
- 確認關卡：停下來、主 session 轉問使用者（Web）、不同意 → [DENIED] 交給它接著做；
- 長的結果照舊提煉（錨點是交辦的子目標與項目）；
- 主 session 依報告回答的核對（出處不在報告 → 交回修一次；漏了報告這一項寫的編號或數字 → 交回修一次，名稱不核對）；同一個問題再交辦時
  帶著上一次的經過；
- 評測的 worker 怎麼記（evals/domain_calls.py）。

    python3 evals/domain/selftest.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts", "web_app", "vision"]
HIDDEN = ("search_text", "view_file", "code_ast_reader")     # 領域讀內容的工具：主 session 不直接用
SHARED = ("list_dir", "find_file", "result_list", "result_grep", "result_view")   # 共用的工具（DOMAIN.md）
FILES = {
    "pkg/mod.py": "def alpha(x):\n    return x + 1\n\n\ndef beta():\n    return alpha(2)\n",
    "pkg/use.py": "from pkg.mod import alpha\n\n\ndef gamma():\n    return alpha(3)\n",
    "cpp/node.hpp": "int delta(int x);\n",
    "cpp/node.cpp": "#include \"node.hpp\"\n\nint delta(int x) {\n  return x * 2;\n}\n",
    "left/sub/a.cpp": "// alpha\n",
    "right/sub/b.cpp": "// alpha\n",
    "docs/spec.md": "# 規格\n\n| 編號 | 狀態 | 情境 | 結果 |\n|---|---|---|---|\n| SPEC-A12 | WAITING | 不同編號的確認 | 不變：繼續等，最多 30 秒 |\n",
    "amr_07/docs/cam_driver.md": "# cam_driver\n\n| 編號 | 指令 | 結果 |\n|---|---|---|\n| WP_0815 | stop | 停下、不回報 |\n",
    "amr_07/test/test_cam_driver.md": "# cam_driver 的測試\n\nWP_0815 stop\n",
    "amr_08/docs/lidar.md": "# lidar\n",
    "amr_08/old/lidar.md": "# lidar（舊）\n",
    "logs/big.log": "".join(f"2026-01-01 00:00:{k % 60:02d} worker_{k % 7} step {k} value {k * 3}\n" for k in range(600)),
}
CAM_FILES = {       # cpp_symbol 分開宣告與定義（t_cpp_defs 寫進臨時的小專案）：標頭檔有類別與宣告、.cpp 有成員函式的定義
    "cam/frame_grabber.h": "#pragma once\nnamespace cam {\nclass FrameGrabber {\n public:\n  void grabFrame();\n  int count() const { return n_; }\n"
                           " private:\n  int n_ = 0;\n};\n}  // namespace cam\n",
    "cam/frame_grabber.cpp": "#include \"frame_grabber.h\"\nnamespace cam {\n// FrameGrabber::grabFrame 寫進畫面\nvoid FrameGrabber::grabFrame()\n{\n"
                             "  ++n_;\n}\n}  // namespace cam\n",
}
SESSION_MARK = "你是領域 session"


def task(goal, items):
    """主 session 的交辦：items 的每一項是使用者的原話（項目就是原話，框架討論紀錄第 27 輪）。"""
    return {"thought": "交辦", "reply": "交辦給領域 session。", "action": {"task": {"goal": goal, "items": [{"quote": x} for x in items]}}}


def say(reply):
    return {"thought": "回覆", "reply": reply, "action": None}


def answer(reply, rows):
    """依報告回答的回覆：rows＝[(項目編號, status, text, refs)]。"""
    return {"thought": "依報告回答", "reply": reply, "action": None,
            "answers": [{"item": k, "status": st, "text": t, "refs": list(refs)} for k, st, t, refs in rows]}


def ds(state, domains=(), skill="", answers=(), reply="這一步", thought="想法"):
    """領域 session 每一輪的決定：answers＝[(項目編號, status, text, refs)]。選技能只寫名稱，參數在下一輪的表單（fill）。"""
    return {"thought": thought, "state": state, "domains": list(domains), "skill": skill,
            "answers": [{"item": k, "status": st, "text": t, "refs": list(r)} for k, st, t, r in answers], "reply": reply}


def fill(params=None, args=None, thought="填表單"):
    """選了技能的下一輪（參數表單）：有骨架的技能 params＝[(名稱, 值, 原文)]；工具 args＝字串。"""
    if params is None:
        return {"thought": thought, "args": args or ""}
    return {"thought": thought, "params": {n: {"quote": q, "value": v} for n, v, q in params}}


def _items(fmt):
    try:
        return fmt["properties"]["answers"]["items"]["properties"]["item"]["enum"]
    except (KeyError, TypeError):
        return []


class FakeChat:
    """假的 ollama.chat：照 format 的欄位分角色（主 session、領域 session（每一輪的決定與參數表單）、第 1 級修正、其他＝提煉與摘要），
    各自依序取劇本；一則可以是函式（看對話決定回什麼），或 "RAW:" 開頭的字串（原樣回，測回覆不是 JSON）。"""

    def __init__(self, main=(), session=()):
        self.q = {"main": list(main), "session": list(session)}
        self.calls = []

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = set((format or {}).get("properties", {})) if isinstance(format, dict) else set()
        form = props in ({"thought", "params"}, {"thought", "args"})
        role = ("fix" if "fixable" in props else "session" if "state" in props or form else "main" if "action" in props else "other")
        self.calls.append({"role": role, "format": format, "messages": messages})
        if role == "fix":
            data = {"reason": "（測試）不修", "fixable": False, "args": []}
        elif role == "other":
            data = {"answer": "（摘要）", "facts": [], "errors": [], "not_covered": "無", "suggested_questions": [], "index_hint": "（摘要）",
                    "related_records": [], "overview": "（摘要）", "key_progress": [], "results_and_errors": [], "user_preferences": [],
                    "open_items": [], "relevant": False, "summary": "（摘要）"}
        else:
            q = self.q[role]
            if q:
                item = q.pop(0)
            elif role == "session" and form:        # 劇本用完時的表單：什麼都不填
                item = fill(args="") if "args" in props else fill(params=[])
            elif role == "session":                 # 劇本用完：還沒選領域就選 repo_analysis，選過了每一項都查不到（附原因），回報
                last = messages[-1]["content"] if messages else ""
                item = (ds("domains", domains=["repo_analysis"]) if "先選領域" in last or "還沒選領域" in last else
                        ds("report", answers=[(k, "not_found", "（測試）沒有查到", []) for k in _items(format)], reply="查不到"))
            else:
                item = say("好的。")
            data = item(messages) if callable(item) else item
        content = data[4:] if isinstance(data, str) and data.startswith("RAW:") else json.dumps(data, ensure_ascii=False)
        return {"message": {"content": content}, "prompt_eval_count": 100, "eval_count": 20}

    def session_msgs(self, k=-1):
        """領域 session 第 k 次被呼叫時看到的對話（最後一則）。"""
        return [c["messages"] for c in self.calls if c["role"] == "session"][k]


def make_env():
    tmp = tempfile.mkdtemp(prefix="domain_selftest_")
    for item in COPY:
        shutil.copytree(os.path.join(PROJECT, item), os.path.join(tmp, item), ignore=shutil.ignore_patterns("__pycache__"))
    for rel, text in FILES.items():
        os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
        with open(os.path.join(tmp, rel), "w", encoding="utf-8") as f:
            f.write(text)
    return tmp


def main():
    tmp = make_env()
    os.environ["AGENT_PERF_LOG"] = "0"
    sys.path.insert(0, tmp)
    sys.path.append(PROJECT)                  # evals/domain_calls.py（評測的 worker 用的）從專案讀
    cwd = os.getcwd()
    os.chdir(tmp)
    results = []

    def check(name, fn):
        try:
            agent.reset_conversation()      # 每一項從新的對話開始：前文只看這一段對話（框架討論紀錄第 28 輪）
            fn()
            results.append((name, True, ""))
            print(f"✅ {name}")
        except Exception:   # noqa: BLE001
            results.append((name, False, traceback.format_exc()))
            print(f"❌ {name}")

    try:
        import ollama
        ollama.list = lambda: {"models": []}
        from agent_core import answers, composite, domain_session, skill_spec
        from agent_core.config import DOMAIN_RESULT_HEAD, TOOL_RESULT_TOKEN_THRESHOLD
        from agent_core.jobstore import JobStore
        from agent_core.config import REPLY_ARGS_CHARS
        from agent_core.protocol import action_text, drop_cut, parse_agent_reply
        from agent_core.schemas import agent_reply_schema, domain_form_schema, domain_session_schema
        from web_app import flows
        from web_app.state import agent, state
        from evals import domain_calls
        agent.current_cwd = tmp
        state["auto_mode"] = True

        def turn(user, fake):
            ollama.chat = fake
            agent.set_current_task(user)
            agent.messages.append({"role": "user", "content": user})
            events = []
            agent.progress_callback = lambda text: events.append({"channel": "progress", "text": text})
            try:
                return events, flows.run_turn(events)
            finally:
                agent.progress_callback = None

        def tools_of(events):
            return [e["text"] for e in events if e["channel"] == "tool"]

        def last_job():
            store = JobStore(os.path.join(tmp, "logs", "domain_jobs"))
            jid = agent._domain_turn["tasks"][-1]["job"]
            return store.load(jid)

        def final_reply(events):
            return [e["text"] for e in events if e["channel"] == "chat" and e.get("role") == "assistant"][-1]

        # ------------------------------------------------------------ 主 session
        def t_prompt_schema():
            fake = FakeChat(main=[say("你好")])
            turn("你好", fake)
            call = next(c for c in fake.calls if c["role"] == "main")
            system = call["messages"][0]["content"]
            assert "## Tasks（交辦" in system, "system prompt 要有交辦一節"
            reg = agent.domain_registry()
            tasks = system.split("## Tasks（交辦")[1]
            for name, d in reg["domains"].items():
                assert composite.domain_label(d) in tasks and composite.domain_label(d) != d["title"], ("交辦一節列領域做什麼", d["title"])
                assert name not in system, f"主 session 看到的字不寫領域的名稱（它不指定領域）：{name}"
            avail = system.split("## Available Skills")[1].split("## Tasks")[0]
            for t in HIDDEN:
                assert f"[{t}]" not in avail, f"{t} 是領域的工具，主 session 的索引不列"
            for t in SHARED:
                assert f"[{t}]" in avail, f"{t} 是共用的工具"
            actions = call["format"]["properties"]["action"]["anyOf"]
            assert any("task" in (a.get("properties") or {}) for a in actions), "回覆的 schema 要有交辦"
            assert not any("domains" in (a.get("properties") or {}) for a in actions)
            assert "task" not in str(agent_reply_schema(False, 0)), "沒有領域時沒有交辦"
            items = next(a for a in actions if "task" in (a.get("properties") or {}))["properties"]["task"]["properties"]["items"]["items"]
            assert list(items["properties"]) == ["quote"], "交辦的每一項只寫使用者的原話（項目就是原話）"
            raw = {"goal": " 找  alpha ", "items": [{"quote": " 在 哪 ", "item": " 哪裡 "}, {"quote": "", "item": " "}, {"quote": "", "item": "在哪"}, "只寫字串"]}
            parsed = parse_agent_reply(json.dumps({"thought": "", "reply": "", "action": {"task": raw}}, ensure_ascii=False))
            assert parsed["action"] == {"task": {"goal": "找 alpha", "background": [], "constraints": [],
                                                 "items": [{"quote": "在 哪"}, {"quote": "在哪"}, {"quote": "只寫字串"}]}}, \
                ("另外寫了 item 的只取 quote、quote 是空的才用 item、字串當成原話；沒寫背景與限制的是空的", parsed["action"])
            task_props = next(a for a in actions if "task" in (a.get("properties") or {}))["properties"]["task"]
            assert list(task_props["properties"]) == ["goal", "background", "constraints", "items"] and task_props["required"] == list(task_props["properties"]), \
                ("先挑出背景與限制、剩下的才是項目（框架討論紀錄第 32 輪的 U1）", task_props)
            assert action_text(parsed["action"]).startswith("→ 交辦：找 alpha")

        def t_reply_order():
            # 回覆的欄位順序就是生成順序（Ollama 照 schema 的順序輸出）。主 session：action 一律放最後——answers 排在 action 後面時，
            # 模型照範例寫完 action 要收尾的 `"}}` 不合法，結尾的符號寫進了 args（三階層第 5 步 5-3 的評測）；AGENT.md 的每個範例照這個順序、
            # 寫完 action 就結束；存回對話的 JSON（drop_cut）也一樣。領域 session：照 domain/session.md 寫的順序（先理由與狀態，最後一句 reply）。
            full = ["thought", "reply", "answers", "action"]
            orders = [list(agent_reply_schema(True)["properties"]), list(agent_reply_schema(True, 2)["properties"]),
                      list(agent_reply_schema(False, 2)["properties"])]
            assert orders == [["thought", "reply", "action"], full, full], orders
            with open(os.path.join(tmp, "prompts", "AGENT.md"), encoding="utf-8") as f:
                examples = re.findall(r"範例（[^）]*）：`([^`]+)`", f.read())
            for ex in examples:
                keys = list(json.loads(ex))
                assert keys == [k for k in full if k in keys] and keys[-1] == "action", keys
            assert len(examples) == 4, len(examples)
            parsed = parse_agent_reply(json.dumps({"thought": "t", "reply": "r", "action": {"command": "c", "args": "a" * REPLY_ARGS_CHARS}}))
            _, raw = drop_cut(parsed)
            assert parsed["cut"] == ["args"] and list(json.loads(raw)) == full and json.loads(raw)["action"] is None, raw[:200]
            order = list(domain_session_schema(["repo_analysis"], 2)["properties"])
            assert order == ["thought", "state", "domains", "skill", "answers", "reply"], order
            system = domain_session.DomainSession(agent, agent.domain_registry())._system()
            assert "、".join(order) in system, "domain/session.md 寫的欄位順序跟 schema 一樣"
            assert list(domain_form_schema()["properties"]) == ["thought", "args"], "工具的表單只有 args"
            form = domain_form_schema(["name", "path"])["properties"]
            assert list(form) == ["thought", "params"] and list(form["params"]["properties"]) == ["name", "path"], form
            assert list(form["params"]["properties"]["name"]["properties"]) == ["quote", "value"], "每一欄先抄原文再寫值"

        def t_gate():
            assert "交辦" in (agent.domain_gate("search_text") or ""), "主 session 叫領域的工具要擋"
            assert "交辦" in (agent.domain_gate("scripts/grep_cmd.py") or ""), "腳本也擋"
            assert "有骨架的技能" in (agent.domain_gate("py_usage") or ""), "有骨架的技能的名稱也擋"
            assert agent.domain_gate("list_dir") is None, "共用的工具照用"
            named = agent.domain_gate("repo_analysis") or ""
            assert "是領域的名稱，不是技能" in named and "交辦" in named, named
            assert "repo_analysis" not in agent.domain_gate("search_text") and "repo_analysis" not in agent.domain_gate("py_usage"), \
                "擋下的說明寫領域做什麼、不寫識別名稱"
            assert agent.domain_gate("pkg") is None, "只認領域的名稱"
            agent._sub_allowed = {"domain": "repo_analysis", "tools": {"search_text", "list_dir"}}
            try:
                assert agent.domain_gate("search_text") is None, "領域 session 裡選的領域的工具可以用"
                blocked = agent.domain_gate("docker_ctl") or ""
                assert "不在你選的領域的技能清單裡" in blocked and "search_text" in blocked, blocked
            finally:
                agent._sub_allowed = None

        def t_task_checks():
            agent.set_current_task("檢查")
            assert "goal" in agent.run_task({"task": {"goal": "", "items": [{"quote": "檢查"}]}}), "子目標是空的要擋"
            assert "1～6 項" in agent.run_task({"task": {"goal": "g", "items": []}}), "項目數要擋"
            fake = FakeChat(main=[task("找 alpha", ["定義在哪"]), task("找 alpha", ["定義在哪"]), say("好")])
            events, _ = turn("找 alpha 定義在哪", fake)
            outs = tools_of(events)
            assert outs[0].startswith(DOMAIN_RESULT_HEAD) and "交辦的報告" in outs[0], outs[0][:200]
            assert "一模一樣" in outs[1], outs[1][:200]
            fake = FakeChat(main=[task(f"找 alpha 第 {k} 次", ["找 alpha"]) for k in range(4)] + [say("好")])
            events, _ = turn("找 alpha", fake)
            assert "最多 3 次" in tools_of(events)[3], tools_of(events)[3][:200]

        def t_quote():
            # 交辦的每一項是使用者的原話（框架討論紀錄第 27 輪）：帶進領域 session 的第一則訊息、報告、主 session 要回答的項目與提煉的錨點；之前幾則訊息
            # 裡的也可以。改寫的項目由程式拿掉、問句由程式整句放進項目（第 34 輪，t_ask_items）
            q = "pkg 裡的 beta 定義在哪？它還被誰用到？"
            fake = FakeChat(main=[task("找 pkg 裡的 beta", ["beta 定義在哪", "它還被誰用到"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            events, _ = turn(q, fake)
            outs = tools_of(events)
            first = fake.session_msgs(0)
            assert "每一項是使用者的原話" in first[0]["content"], "system prompt 寫明項目是使用者的原話"
            assert "【要回答的項目】（使用者的原話；回報時 answers 照這個編號）\n1. beta 定義在哪\n2. 它還被誰用到\n" in first[-1]["content"], \
                first[-1]["content"][:600]
            job = last_job()
            assert job["items"] == ["beta 定義在哪", "它還被誰用到"] and "quotes" not in job, job["items"]
            assert "- 要回答的項目 2：它還被誰用到\n" in job["result"]["report"], job["result"]["report"][:400]
            assert "1. beta 定義在哪\n2. 它還被誰用到" in outs[0], "主 session 要回答的項目也是原話"
            assert "它還被誰用到" in domain_session.DomainSession._anchor(job), "提煉的錨點是原話"
            fake = FakeChat(main=[task("找 pkg 裡呼叫 beta 的函式", ["那呼叫它的函式呢", "它還被誰用到"]), say("好")])
            events, _ = turn("那呼叫它的函式呢？", fake)
            assert tools_of(events)[0].startswith(DOMAIN_RESULT_HEAD), ("之前一則訊息裡的原話也可以（這一則的問句也放進了項目）", tools_of(events)[0][:200])

        # ------------------------------------------------------------ 領域 session：工具
        def t_domain_named():
            fake = FakeChat(main=[{"thought": "找檔案", "reply": "用 repo_analysis 找。", "action": {"command": "repo_analysis", "args": ""}},
                                  task("找 pkg 裡的 alpha 定義在哪", ["定義在哪"]), say("好")])
            turn("pkg 裡的 alpha 定義在哪？", fake)
            mains = [c for c in fake.calls if c["role"] == "main"]
            told = mains[1]["messages"][-1]["content"]
            assert "repo_analysis 是領域的名稱，不是技能" in told and "交辦" in told, told[:400]
            assert "已經移除" not in told and "沒有這個功能" not in told, ("不要說成移除的技能（e4b 會因此放棄）", told[:400])
            report = mains[2]["messages"][-1]["content"]
            head = [ln for ln in report.split("\n") if ln.startswith("- 領域：")]
            assert head and "repo_analysis" not in head[0] and "找檔案" in head[0], ("報告給主 session：領域寫它做什麼", report[:400])

        def t_tool_flow():
            q = "pkg 裡的 alpha 定義在哪個檔案的第幾行？"
            fake = FakeChat(
                main=[task("在 pkg 找 alpha 定義在哪", ["alpha 定義在哪個檔案的第幾行"]),
                      answer("找到了。", [(1, "answered", "定義在 pkg/mod.py:1（def alpha）", ["pkg/mod.py:1"])])],
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text"), fill(args='search_text "def alpha" pkg'),
                         ds("report", answers=[(1, "answered", "定義在 pkg/mod.py 第 1 行（def alpha）", ["pkg/mod.py:1"])], reply="找到了")])
            events, _ = turn(q, fake)
            first = fake.session_msgs(0)
            assert SESSION_MARK in first[0]["content"] and "repo_analysis" in first[0]["content"], "system prompt 有領域清單"
            assert "【子目標】" in first[-1]["content"] and "先選領域" in first[-1]["content"]
            listing = fake.session_msgs(1)[-1]["content"]
            assert "【技能清單】" in listing and "py_usage" in listing and "參數：" in listing, listing[:500]
            assert "args 的寫法：`\"<關鍵字>\"" in listing and "`search_text " not in listing, "工具附 args 的寫法（只有參數的部分）"
            form = fake.session_msgs(2)[-1]["content"]
            assert form.startswith("【參數表單】search_text（工具）") and "args 的寫法：`\"<關鍵字>\"" in form, form[:300]
            assert list([c for c in fake.calls if c["role"] == "session"][2]["format"]["properties"]) == ["thought", "args"], "工具的表單只有 args"
            job = last_job()
            assert job["status"] == "done" and job["domains"] == ["repo_analysis"], job["status"]
            assert [s["skill"] for s in job["steps"]] == ["search_text"] and job["steps"][0]["result_ids"], job["steps"]
            assert job["steps"][0]["args"] == '"def alpha" pkg', "args 開頭照抄的工具名稱拿掉"
            assert job["turns"] == 3 and job["forms"] == 1, ("表單的那一輪不算在回的輪數裡", job["turns"], job["forms"])
            assert not job["problems"], job["problems"]
            result = fake.session_msgs(3)[-1]["content"]
            assert result.startswith("[tool result]") and "【第 1 步的結果】search_text" in result and "（存檔 #" in result, result[:300]
            report = tools_of(events)[0]
            assert report.startswith(DOMAIN_RESULT_HEAD) and "交辦的報告（做完）" in report and "這一回合要回答的項目" in report, report[:300]
            assert "> " in report and "pkg/mod.py:1" in report, "報告的回答附出處那一行"
            shown = final_reply(events)
            assert "1. alpha 定義在哪個檔案的第幾行：定義在 pkg/mod.py:1" in shown and "> " in shown, ("照項目（原話）排", shown)

        def t_tool_records():
            fake = FakeChat(    # 這一項自己交辦一次（每一項從新的對話開始；之前用的是上一項留下的）
                main=[task("在 pkg 找 alpha 定義在哪", ["alpha 定義在哪個檔案的第幾行"]),
                      answer("找到了。", [(1, "answered", "定義在 pkg/mod.py:1（def alpha）", ["pkg/mod.py:1"])])],
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text"), fill(args='search_text "def alpha" pkg'),
                         ds("report", answers=[(1, "answered", "定義在 pkg/mod.py 第 1 行（def alpha）", ["pkg/mod.py:1"])], reply="找到了")])
            turn("pkg 裡的 alpha 定義在哪個檔案的第幾行？", fake)
            parsed = {"action": {"task": {"goal": "在 pkg 找 alpha 定義在哪",
                                          "items": [{"quote": "alpha 定義在哪個檔案的第幾行"}]}}}
            recs = domain_calls.calls(agent, parsed, DOMAIN_RESULT_HEAD + "報告")
            head = recs[0]
            assert head["skill"] == "domain_session" and head["job"] and head["domains"] == ["repo_analysis"] and head["steps"] == 1, head
            assert head["turns"] == 3 and head["forms"] == 1, head
            assert recs[1]["skill"] == "search_text" and recs[1]["via"] == "domain_session" and recs[1]["args"] == ["def alpha", "pkg"], recs[1]
            err = domain_calls.calls(agent, parsed, "[ERROR] 不行")
            assert len(err) == 1 and err[0]["status"] == "ERROR"

        # ------------------------------------------------------------ 領域 session：有骨架的技能
        def t_composite():
            q = "pkg 裡的 alpha 定義在哪、哪裡用到？"
            fake = FakeChat(
                main=[task("找 pkg 裡的 alpha 定義在哪、哪裡用到", ["定義在哪", "哪裡用到"]), say("好")],
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="py_usage"),
                         fill(params=[("name", "omega", "omega"), ("path", "pkg", "pkg")]), fill(params=[("name", "alpha", "alpha")]),
                         ds("skill", skill="py_usage"), fill(params=[("name", "alpha", "alpha"), ("path", "pkg", "pkg")])])
            turn(q, fake)
            calls = [c for c in fake.calls if c["role"] == "session"]
            form = fake.session_msgs(2)[-1]["content"]
            assert form.startswith("【參數表單】py_usage（有骨架的技能）") and "- name（名稱，必填）" in form, form[:400]
            assert list(calls[2]["format"]["properties"]["params"]["properties"]) == ["name", "path", "exclude"], "表單：參數名稱就是欄位"
            rejected = fake.session_msgs(3)[-1]["content"]
            assert "參數沒有通過核對" in rejected and "omega" in rejected and "只重填這幾個參數" in rejected, rejected[:300]
            assert list(calls[3]["format"]["properties"]["params"]["properties"]) == ["name"], "交回重填時只有沒過的參數"
            job = last_job()
            comp = [s for s in job["steps"] if s["kind"] == "composite"]
            assert len(comp) == 1, f"合約沒過不算一步、一模一樣的不執行：{[s['skill'] for s in job['steps']]}"
            st = comp[0]
            assert st["status"] == "done" and st["params"]["name"]["value"] == "alpha", st["params"]
            assert st["params"]["path"]["value"] == "pkg", "重填時沒過的以外照第一次填的"
            assert len(st["result_ids"]) >= 2 and {o["tool"] for o in st["composite"]["outputs"]} >= {"search_text", "code_ast_reader"}, st
            shown = fake.session_msgs(4)[-1]["content"]
            assert "技能的狀態：跑完" in shown and "— 名稱的每一處：code_ast_reader" in shown, shown[:500]
            same = fake.session_msgs(6)[-1]["content"]
            assert "一模一樣" in same, same[:200]

        def t_path_names():
            goal = "找 pkg 裡的 alpha 定義在哪、哪裡用到"
            fake = FakeChat(main=[task(goal, ["定義在哪", "哪裡用到"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="py_usage"),
                                     fill(params=[("name", "alpha", "alpha"), ("path", "pkg 裡", "pkg 裡的 alpha")])])
            turn("pkg 裡的 alpha 定義在哪、哪裡用到？", fake)
            shown = fake.session_msgs(3)[-1]["content"]
            assert "系統只留原文裡的名稱：path「pkg 裡」→ pkg" in shown and "技能的狀態：跑完" in shown, shown[:500]
            st = next(s for s in last_job()["steps"] if s["kind"] == "composite")
            assert st["params"]["path"]["value"] == "pkg" and st["params"]["path"]["given"] == "pkg 裡", st["params"]
            assert "given" not in st["params"]["name"], ("照寫的不記", st["params"])
            P = {"name": "doc", "type": "path"}
            q = "amr_07 的 cam_driver 規格書"

            def vp(quote, value):
                return composite.verify_param(P, quote, value, quote)

            assert vp(q, "amr_07/cam_driver 規格書") == ("amr_07/cam_driver", None), "名稱＋說明的字：只留名稱"
            assert vp(q, "amr_07/cam_driver*") == ("amr_07/cam_driver", None), "結尾的萬用字元：只留名稱"
            assert vp(q, "cam_driver 規格書") == ("cam_driver", None)
            assert vp("amr_07/", "./amr_07/") == ("amr_07", None), "開頭的 ./、結尾的 / 照舊"
            for quote, value in ((q, "amr_07 的 cam_driver 規格書"), (q, "amr_07/cam_driver_spec"), (q, "amr_07/cam_driver_規格書"),
                                 (q, "amr_07/driver 規格書"), ("amr_07", "../amr_07"), ("docs 底下的 *.md", "docs/*.md"),
                                 ("Camera Driver Spec.md", "Camera Driver Spec.md"), (q, "amr_07/規格書 cam_driver x")):
                got = vp(quote, value)
                assert got[0] is None and "不是抄的原文" in got[1], ("好幾個名稱、翻譯、接在一起、名稱的一部分、原文沒有的目錄、開頭的萬用字元、"
                                                                    "沒有拿掉東西、有別的英數字：照舊交回", value, got)

        def t_form():
            q = "pkg 裡的 alpha 定義在哪？"
            goal = "找 pkg 裡的 alpha 定義在哪"
            fake = FakeChat(main=[task(goal, ["定義在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]),
                                     ds("skill", skill="cpp_symbol"), fill(params=[("names", "zzz", "zzz"), ("path", ".", "")]),
                                     fill(params=[("names", "nosuch_name", "")]),
                                     ds("skill", skill="py_usage"),
                                     fill(params=[("name", "alpha", f"【子目標】\n{goal}"), ("path", "pkg", f"【子目標】{goal}")])])
            turn(q, fake)
            calls = [c for c in fake.calls if c["role"] == "session"]
            assert list(calls[3]["format"]["properties"]["params"]["properties"]) == ["names"], "照寫了預設值（沒抄原文）的 path 不算沒過"
            failed = fake.session_msgs(4)[-1]["content"]
            assert "重填之後還是沒有通過核對" in failed and "值「nosuch_name」沒有抄原文" in failed, failed[:300]
            assert "state" in calls[4]["format"]["properties"], "重填還是沒過：回到每一輪的決定"
            job = last_job()
            assert [s["skill"] for s in job["steps"]] == ["py_usage"], f"沒過的不算一步：{[s['skill'] for s in job['steps']]}"
            st = job["steps"][0]
            assert st["params"]["name"]["quote"] == goal and st["params"]["path"]["value"] == "pkg", ("抄了程式的標題：拿掉再核對", st["params"])
            whys = [b["why"] for b in job["blocked"]]
            assert whys[:2] == ["cpp_symbol 的參數沒有通過核對", "cpp_symbol 的參數重填之後還是沒有通過核對"], whys
            assert job["turns"] == 4 and job["forms"] == 3, (job["turns"], job["forms"])

        def t_grounded():
            goal = "找 pkg 裡的 alpha 定義在哪"
            fake = FakeChat(main=[task(goal, ["定義在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="py_usage"),
                                     fill(params=[("name", "alpha", "沒有出現過的一段"), ("path", os.path.join(tmp, "pkg"), ""),
                                                  ("exclude", "", "隨便一句")])])
            turn("pkg 裡的 alpha 定義在哪？", fake)
            job = last_job()
            assert job["forms"] == 1 and not [b for b in job["blocked"] if "核對" in b["why"]], ("第一次就過", job["blocked"])
            st = job["steps"][0]
            assert st["params"]["name"] == {"value": "alpha", "quote": "alpha", "source": "contract"}, ("值本身在原文裡", st["params"])
            assert st["params"]["path"]["value"] == "pkg" and "given" not in st["params"]["path"], ("工作目錄底下的絕對路徑", st["params"])
            assert "exclude" not in st["params"] and "技能的狀態：跑完" in fake.session_msgs(3)[-1]["content"], ("空的當成沒提到", st["params"])
            fake = FakeChat(main=[task(goal, ["定義在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="py_usage"),
                                     fill(params=[("name", "alpha", "alpha"), ("path", ".", goal)]), fill(params=[("path", "pkg", goal)])])
            turn("pkg 裡的 alpha 定義在哪？", fake)
            fix = fake.session_msgs(3)[-1]["content"]
            assert "參數沒有通過核對" in fix and "路徑「.」" in fix, ("預設值配寫著 pkg 的 quote：照核對交回重填", fix[:300])
            assert last_job()["steps"][0]["params"]["path"]["value"] == "pkg", ("重填成 quote 寫的範圍", last_job()["steps"])
            sess = domain_session.DomainSession(agent, agent.domain_registry())
            specs = agent.domain_registry()["domains"]["repo_analysis"]["skills"]
            job = {"cwd": "/w/src", "sources": "照 amr_07 的 cam_driver 規格書：QoS 設定在哪？頻率多少？WP_0815、cam_driver 在哪一行？\n"
                                             "【第 1 步的結果】find_file\namr_07/config/cam.yaml"}

            def form(skill, cells):
                return sess._contract(job, specs[skill], {k: {"quote": q, "value": v} for k, (v, q) in cells.items()})

            params, problems, _ = form("find_lines", {"keyword": ("qos", "qos"), "path": (".", "沒有提到路徑"), "exclude": ("", "隨便一句")})
            assert not problems and set(params) == {"keyword"} and params["keyword"]["value"] == "qos", ("大小寫、預設值配沒有名稱的 quote、空的", params, problems)
            for quote in ("/w/src", "src 底下", "."):
                params, problems, _ = form("find_lines", {"keyword": ("QoS", "QoS"), "path": (".", quote)})
                assert not problems and set(params) == {"keyword"}, ("預設值配的 quote 是工作目錄或它路徑上的一段：當成沒提到", quote, params, problems)
            for quote, why in (("照 amr_07 的 cam_driver 規格書", "路徑「.」"), ("amr_07/config/cam.yaml", "路徑「.」"), ("amr_07 的設定檔", "不在子目標")):
                params, problems, bad = form("find_lines", {"keyword": ("QoS", "QoS"), "path": (".", quote)})
                assert bad == ["path"] and why in problems[0], ("預設值配寫著別的名稱的 quote：照核對交回（quote 裡有「.」也一樣）", quote, params, problems)
            params, problems, _ = form("find_lines", {"keyword": ("QoS", ""), "path": ("/w/src/", "")})
            assert not problems and set(params) == {"keyword"}, ("沒抄 quote、值在原文裡；工作目錄本身＝預設值", params, problems)
            params, problems, _ = form("find_lines", {"keyword": ("QoS", "別段"), "path": ("/w/src/amr_07/config/", "")})
            assert not problems and params["path"]["value"] == "amr_07/config" and "given" not in params["path"], ("絕對路徑換成相對的", params, problems)
            params, problems, _ = form("doc_lookup", {"doc": ("amr_07/cam_driver", "amr_07 的 cam_driver 規格書"), "words": ("wp_0815, CAM_DRIVER", "沒有的一段")})
            assert not problems and params["words"]["value"] == ["wp_0815", "CAM_DRIVER"], ("搜尋的字每一個在原文裡（不分大小寫）", params, problems)
            for skill, cells, why in (("doc_lookup", {"doc": ("amr_07/cam_driver_spec.md", "amr_07 的 cam_driver 規格書"), "words": ("WP_0815", "WP_0815")}, "編的檔名"),
                                      ("find_lines", {"keyword": ("frequency", "頻率多少")}, "翻成英文的字"),
                                      ("find_lines", {"keyword": ("QoS、cam_driver", "QoS")}, "搜尋的文字寫成好幾個"),
                                      ("find_lines", {"keyword": ("map", "")}, "原文沒有的值"),
                                      ("find_lines", {"keyword": ("QoS", "QoS"), "path": ("/etc/amr_07", "amr_07")}, "工作目錄外的絕對路徑照每一段核對")):
                params, problems, bad = form(skill, cells)
                assert problems and len(bad) == 1, (why, params, problems)
            assert "值「map」沒有抄原文" in form("find_lines", {"keyword": ("map", "")})[1][0], "沒抄 quote 的說明照舊"
            assert composite.verify_param({"name": "path", "type": "path"}, "/opt/amr_07", "/opt/amr_07", "/opt/amr_07") == ("/opt/amr_07", None), \
                "絕對路徑開頭的空段照收"
            vp = {"name": "path", "type": "path"}
            assert composite.verify_param(vp, "amr_07/../cam.yaml", "../amr_07", "amr_07/../cam.yaml")[0] is None, "「..」不是名稱"
            assert composite.verify_param(vp, "文件/設計.md", "文件/設計.md", "文件/設計.md") == ("文件/設計.md", None), "中文的名稱照收"
            text = open(os.path.join(tmp, "skills_system", "repo_analysis", "find_lines.md"), encoding="utf-8").read()
            assert text.count('"-C", "2"],') == 1, "骨架的寫法變了：改這個測試"
            spec = dict(skill_spec.composite(text.replace('"-C", "2"],', '"-C", "2", "--case"],')), name="find_lines", text=text)
            problems = composite.validate_skill(spec, os.path.join(tmp, "skills_system", "tools"),
                                                agent.domain_registry()["domains"]["repo_analysis"]["tools"])
            assert any("--case" in x for x in problems), ("搜尋的字不分大小寫：骨架加 --case 的擋下", problems)

        def t_scope():
            # 原文沒有的搜尋字：要搜的範圍裡有才收；檔名寫法照舊照原文核對（框架討論紀錄第 20、21 輪，設計筆記 2.71、2.72）
            fake = FakeChat(main=[task("找 pkg 裡的函式", ["在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="find_lines"),
                                     fill(params=[("keyword", "beta", "函式的名稱"), ("path", "pkg", "pkg 裡")])])
            turn("pkg 裡的函式在哪？", fake)
            job = last_job()
            assert job["forms"] == 1 and not [b for b in job["blocked"] if "核對" in b["why"]], ("範圍裡有：第一次就過", job["blocked"])
            kw = job["steps"][0]["params"]["keyword"]
            assert kw["source"] == "scope" and kw["value"] == "beta" and kw["hits"]["beta"] >= 1, ("出處寫範圍與筆數", kw)
            assert "def beta" in fake.session_msgs(3)[-1]["content"], "照那個字搜到"
            with open(os.path.join(tmp, "logs", "note.txt"), "w", encoding="utf-8") as f:
                f.write("uniq_logword\n")
            sess = domain_session.DomainSession(agent, agent.domain_registry())
            specs = agent.domain_registry()["domains"]["repo_analysis"]["skills"]
            assert composite.scope_param(specs["find_lines"]) == "path" and composite.scope_param(specs["doc_lookup"]) is None
            job = {"cwd": tmp, "sources": "找 pkg、cpp 與 sub 目錄裡的定義（hpp 檔也看）；照 docs/spec.md 回答"}

            def form(skill, cells):
                return sess._contract(job, specs[skill], {k: {"quote": q, "value": v} for k, (v, q) in cells.items()})

            params, problems, _ = form("find_lines", {"keyword": ("beta|gamma", ""), "path": ("pkg", "pkg")})
            assert not problems and params["keyword"]["source"] == "scope" and set(params["keyword"]["hits"]) == {"beta", "gamma"}, \
                ("| 分開的每一個都有", params, problems)
            params, problems, bad = form("find_lines", {"keyword": ("def beta", "定義"), "files": ("*.py", ""), "path": ("pkg", "pkg")})
            assert bad == ["files"] and params["keyword"]["source"] == "scope", ("自己選的檔名寫法範圍裡有也照舊交回；詞組照字面有", params, problems)
            params, problems, _ = form("cpp_symbol", {"names": ("delta", ""), "path": ("cpp", "cpp")})
            assert not problems and params["names"]["value"] == ["delta"] and params["names"]["source"] == "scope", ("搜尋的字", params, problems)
            params, problems, _ = form("py_usage", {"name": ("gamma", ""), "path": ("pkg", "pkg")})
            assert not problems and params["name"]["source"] == "scope", ("名稱", params, problems)
            params, problems, _ = form("find_lines", {"keyword": ("beta", "")})
            assert not problems and params["keyword"]["source"] == "scope", ("沒寫 path：數工作目錄", params, problems)
            params, problems, _ = form("find_lines", {"keyword": ("beta", ""), "path": ("sub", "sub 目錄")})
            assert not problems and params["path"]["value"] == "sub", ("path 還找不到（執行時才照 fetch 查）：數工作目錄", params, problems)
            params, problems, bad = form("find_lines", {"keyword": ("delta", ""), "files": ("*.py", ""), "path": ("cpp", "cpp")})
            assert bad == ["files"] and params["keyword"]["source"] == "scope", ("檔名寫法照原文核對、沒過的交回；搜尋字照 path 數", params, problems)
            for cells, why in (({"keyword": ("beta", ""), "path": ("cpp", "cpp")}, "換了範圍就沒有"),
                               ({"keyword": ("return", ""), "files": ("*.hpp", "hpp 檔"), "path": ("cpp", "cpp")}, "照原文核對過的 files 縮小之後沒有"),
                               ({"keyword": ("omega", "函式"), "path": ("pkg", "pkg")}, "範圍裡沒有"),
                               ({"keyword": ("beta def", ""), "path": ("pkg", "pkg")}, "詞組照字面沒有"),
                               ({"keyword": ("beta|omega", ""), "path": ("pkg", "pkg")}, "| 分開的有一個沒有"),
                               ({"keyword": ("bet.*", ""), "path": ("pkg", "pkg")}, "正規表示式的符號"),
                               ({"keyword": ("beta、gamma", ""), "path": ("pkg", "pkg")}, "用「、」寫成好幾個（另外談）"),
                               ({"keyword": ("beta", ""), "exclude": ("pkg", "pkg")}, "exclude 拿掉之後沒有"),
                               ({"keyword": ("uniq_logword", "")}, "agent 自己的 logs 不數（剛填的表單記在裡面）")):
                params, problems, bad = form("find_lines", cells)
                assert bad == ["keyword"] and "keyword" not in params, (why, params, problems)
            assert "抄的原文「函式」" in form("find_lines", {"keyword": ("omega", "函式"), "path": ("pkg", "pkg")})[1][0], "沒過的說明照舊"
            params, problems, bad = form("find_lines", {"keyword": ("beta", ""), "path": ("pkgx", "pkgx")})
            assert bad == ["keyword", "path"], ("path 沒過：不數，一起交回", params, problems)
            params, problems, bad = form("doc_lookup", {"doc": ("docs/spec.md", "docs/spec.md"), "words": ("WAITING", "")})
            assert bad == ["words"], ("doc_lookup 不數（要搜的文件執行時才找）", params, problems)

        def t_doc_of():
            # 要讀的那一份只寫了上層、或上層與名稱寫在同一段：照原文的「<a> 的 <b>」找到那一份（框架討論紀錄第 24 輪，設計筆記 2.74）
            q = "照 amr_07 的 cam_driver 規格書"
            goal = f"{q}：WP_0815 收到 stop 會怎樣"
            fake = FakeChat(main=[task(goal, ["收到 stop 會怎樣"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="doc_lookup"),
                                     fill(params=[("doc", "amr_07", q), ("words", "WP_0815", "WP_0815")])])
            turn(f"{goal}？", fake)
            job = last_job()
            assert job["forms"] == 1 and not [b for b in job["blocked"] if "核對" in b["why"]], ("第一次就過", job["blocked"])
            doc = job["steps"][0]["params"]["doc"]
            assert doc == {"value": "amr_07/docs/cam_driver.md", "quote": q, "source": "contract", "given": "amr_07", "of": "amr_07 的 cam_driver"}, doc
            shown = fake.session_msgs(3)[-1]["content"]
            assert "系統照原文的「amr_07 的 cam_driver」找到要讀的那一份：doc「amr_07」→ amr_07/docs/cam_driver.md" in shown, shown[:600]
            assert "停下、不回報" in shown and "test_cam_driver" not in shown, ("照那一份搜到、沒有搜整個 amr_07", shown[:800])
            sess = domain_session.DomainSession(agent, agent.domain_registry())
            specs = agent.domain_registry()["domains"]["repo_analysis"]["skills"]
            job = {"cwd": tmp, "sources": f"{q}；amr_08 的 lidar 規格書；amr_07 的 imu 規格書；amr_07 的 cam_driver 與 amr_07 的 imu；"
                                          "amr_07 底下的 cam_driver 規格書；WP_0815"}

            def doc_cell(value, quote):
                params, _, bad = sess._contract(job, specs["doc_lookup"], {"doc": {"quote": quote, "value": value},
                                                                           "words": {"quote": "WP_0815", "value": "WP_0815"}})
                return params.get("doc"), bad

            for value in ("amr_07", "amr_07 cam_driver 規格書", "amr_07 的 cam_driver 規格書", "amr_07的cam_driver規格書"):
                got, bad = doc_cell(value, q)
                assert not bad and got == {"value": "amr_07/docs/cam_driver.md", "quote": q, "source": "contract", "given": value,
                                           "of": "amr_07 的 cam_driver"}, ("只寫上層、兩個名稱寫在同一段：照原文找到那一份（檔名一樣的才算，測試規格不算）", value, got, bad)
            for value, quote, kept, why in (("amr_07/cam_driver 規格書", q, "amr_07/cam_driver", "已經寫成 <a>/<b>：照舊只留名稱，執行時照補路徑的做法找"),
                                            ("cam_driver", q, "cam_driver", "只寫 <b>：照舊"),
                                            ("amr_08", "amr_08 的 lidar 規格書", "amr_08", "好幾份：照舊用整個上層"),
                                            ("amr_07", "amr_07 的 imu 規格書", "amr_07", "找不到：照舊"),
                                            ("amr_07", "amr_07 的 cam_driver 與 amr_07 的 imu", "amr_07", "<a> 開頭的有好幾種：看不出是哪一個"),
                                            ("amr_07", "amr_07 底下的 cam_driver 規格書", "amr_07", "原文沒有「<a> 的 <b>」"),
                                            ("amr_07", "amr_07 的 cam_driver 說明", "amr_07", "抄的不在原文裡：不照它找（值本身在原文裡照舊收）")):
                got, bad = doc_cell(value, quote)
                assert not bad and got["value"] == kept and "of" not in got, (why, got, bad)
            for value, quote, why in (("amr_08 lidar 規格書", "amr_08 的 lidar 規格書", "好幾份：同一段兩個名稱照舊交回"),
                                      ("amr_07 imu 規格書", "amr_07 的 imu 規格書", "找不到：照舊交回"),
                                      ("amr_07/cam_driver_spec.md", q, "編的檔名：照舊交回")):
                got, bad = doc_cell(value, quote)
                assert bad == ["doc"] and got is None, (why, got, bad)
            params, problems, _ = sess._contract(job, specs["find_lines"], {"keyword": {"quote": "WP_0815", "value": "WP_0815"},
                                                                            "path": {"quote": q, "value": "amr_07"}})
            assert not problems and params["path"]["value"] == "amr_07" and "of" not in params["path"], ("有預設值的路徑（要搜的範圍）不在這一項", params, problems)
            assert composite.path_of("x 的 amr_07 的 cam_driver", "amr_07") == ("amr_07/cam_driver", "amr_07 的 cam_driver"), "「x 的 <a> 的 <b>」也找得到"

        def t_form_tool():
            fake = FakeChat(main=[task("找 pkg 裡的 alpha 定義在哪", ["定義在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text"),
                                     fill(args='{"<關鍵字>": "def alpha", "[路徑…]": "pkg"}'), fill(args='"<關鍵字>" pkg'),
                                     ds("skill", skill="search_text"), fill(args='"[a-z]+ alpha" pkg')])
            turn("pkg 裡的 alpha 定義在哪？", fake)
            calls = [c for c in fake.calls if c["role"] == "session"]
            form = fake.session_msgs(2)[-1]["content"]
            assert form.startswith("【參數表單】search_text（工具）") and "不是 JSON" in form, form[:300]
            fix = fake.session_msgs(3)[-1]["content"]
            assert "args 沒有通過核對" in fix and "args 寫成了 JSON" in fix and "`\"<關鍵字>\" [路徑…] [選項]`" in fix, fix[:400]
            assert set(calls[3]["format"]["properties"]) == {"thought", "args"}, "重填：一樣只有 args"
            failed = fake.session_msgs(4)[-1]["content"]
            assert "重填之後還是沒有通過核對" in failed and "照抄了寫法裡的 <關鍵字>" in failed, failed[:300]
            assert "state" in calls[4]["format"]["properties"], "重填還是沒過：回到每一輪的決定"
            job = last_job()
            assert [(s["skill"], s["args"]) for s in job["steps"]] == [("search_text", '"[a-z]+ alpha" pkg')], job["steps"]
            assert [b["why"] for b in job["blocked"]][:2] == ["search_text 的 args 寫法不對", "search_text 的 args 重填之後還是寫法不對"], job["blocked"]
            assert job["forms"] == 3 and job["turns"] == 4, (job["forms"], job["turns"])
            sess = domain_session.DomainSession(agent, agent.domain_registry())
            assert sess._args_problem("search_text", '"[A-Z]+_ERR" pkg -C 2') == "", "中括號的搜尋字不是佔位符"
            assert sess._args_problem("search_text", '["def alpha", "pkg"]') and sess._args_problem("view_file", "<檔案> --from 3"), "陣列、照抄佔位符"
            assert "[]" in sess._args_problem("search_text", '"def alpha" pkg [] []'), "可以不寫的部分填成「[]」：沒有換成值"
            assert sess._args_problem("search_text", '"[]" pkg') == "" and sess._args_problem("search_text", '"a[]" pkg -C 2') == "", "引號裡的「[]」照搜"

        def t_totals():
            def report(messages):
                text = "\n".join(m["content"] for m in messages if m["role"] == "user")
                rid = re.findall(r"【程式照收據算的彙整】（存檔 #(\d+)", text)[-1]
                return ds("report", answers=[(1, "answered", "呼叫總共 2 次：pkg/mod.py 1 次、pkg/use.py 1 次", [f"#{rid}"])], reply="數好了")
            fake = FakeChat(main=[task("數 pkg 裡的 alpha 呼叫幾次", ["pkg 裡的 alpha 在哪些檔案呼叫、各幾次、總共幾次？"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="py_usage"),
                                     fill(params=[("name", "alpha", "alpha"), ("path", "pkg", "pkg")]), report])
            turn("pkg 裡的 alpha 在哪些檔案呼叫、各幾次、總共幾次？", fake)
            shown = fake.session_msgs(3)[-1]["content"]
            for want in ("【程式照收據算的彙整】（存檔 #", "## 名稱的每一處（code_ast_reader）", "- 定義（1）：\n    - pkg/mod.py:1　def alpha",
                         "- 呼叫：總共 2 次（2 個檔案）：\n    - pkg/mod.py：1 次\n    - pkg/use.py：1 次", "- import：總共 1 處（1 個檔案）",
                         "- 定義以外的每一種加起來：總共 3 處（2 個檔案）"):
                assert want in shown, (want, shown[:1500])
            assert shown.index("【程式照收據算的彙整】") < shown.index("— 名稱的每一處：code_ast_reader"), "彙整接在技能的狀態後面、各節點的結果前面"
            rid = int(re.search(r"【程式照收據算的彙整】（存檔 #(\d+)", shown).group(1))
            job = last_job()
            assert job["steps"][0]["result_ids"][0] == rid and len(job["steps"][0]["result_ids"]) >= 3, job["steps"][0]["result_ids"]
            assert job["status"] == "done" and not job["blocked"], ("總數照彙整寫、出處是彙整的 #編號：核對過", job["blocked"])
            with open(agent.result_file_path(rid), encoding="utf-8") as f:
                assert "[PASS] py_usage 的彙整" in f.read(), "彙整存成 #編號"
            fake = FakeChat(main=[task("數 . 底下名稱符合 *.cpp 的檔案，不含 left", ["有幾個"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="count_in_scope"),
                                     fill(params=[("files", "*.cpp", "*.cpp"), ("exclude", "left", "left")])])
            turn("數 . 底下名稱符合 *.cpp 的檔案有幾個，不含 left 目錄", fake)
            shown = fake.session_msgs(3)[-1]["content"]
            head = shown.split("\n— ")[0]
            assert "- 名稱符合「*.cpp」的檔案：總共 2 個（從 . 開始找）；不含 left 裡的 1 個：" in head, shown[:1500]
            assert "right/sub/b.cpp" in head and "left/sub/a.cpp" not in head, ("扣掉的不列", head)

        def t_composite_switch():
            q = "cpp 底下的 delta 定義在哪？"
            fake = FakeChat(main=[task("找 cpp 底下的 delta 定義在哪", ["定義在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="py_usage"),
                                     fill(params=[("name", "delta", "delta"), ("path", "cpp", "cpp")])])
            turn(q, fake)
            st = last_job()["steps"][0]
            assert st["composite"]["skill"] == "cpp_symbol" and st["composite"]["switched"], st["composite"]
            shown = fake.session_msgs(3)[-1]["content"]
            assert "py_usage 換成 cpp_symbol" in shown and "node.cpp" in shown, shown[:600]

        def t_composite_need_and_empty():
            q = "sub 裡的 alpha 在哪？找不到的 zeta 呢？"
            fake = FakeChat(main=[task("找 sub 裡的 alpha，與 zeta", ["alpha 在哪", "找不到的 zeta 呢"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]),
                                     ds("skill", skill="cpp_symbol"), fill(params=[("names", "alpha", "alpha"), ("path", "sub", "sub")]),
                                     ds("skill", skill="cpp_symbol"), fill(params=[("names", "zeta", "zeta")])])
            turn(q, fake)
            steps = last_job()["steps"]
            assert steps[0]["status"] == "need" and not steps[0]["result_ids"], steps[0]
            need = fake.session_msgs(3)[-1]["content"]
            assert "有好幾個" in need and "left/sub" in need and "right/sub" in need, need[:400]
            assert steps[1]["status"] == "done" and steps[1]["result_ids"], "0 筆照實交回：跑完、附結果"
            empty = fake.session_msgs(5)[-1]["content"]
            assert "技能的狀態：跑完" in empty and "範圍外提到這些名稱的 C++ 檔" in empty, empty[:500]

        # ------------------------------------------------------------ 狀態與上限
        def t_states_limits():
            fake = FakeChat(main=[task("找 alpha", ["找 alpha"]), say("好")],
                            session=["RAW:不是 JSON", ds("skill", skill="search_text"), ds("domains", domains=["repo_analysis"]),
                                     ds("domains", domains=["repo_analysis"]), ds("domains", domains=["repo_analysis"]),
                                     ds("domains", domains=["repo_analysis"])])
            turn("找 alpha", fake)
            job = last_job()
            whys = [b["why"] for b in job["blocked"]]
            assert "還沒選領域" in whys and "重選領域超過上限" in whys, whys
            assert len(job["picks"]) == 3, "第一次加上再選 2 次"
            saved = domain_session.DOMAIN_STEPS_MAX
            domain_session.DOMAIN_STEPS_MAX = 2
            try:
                fake = FakeChat(main=[task("找 alpha 與 beta", ["找 alpha 與 beta"]), say("好")],
                                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text"), fill(args="alpha"),
                                         ds("skill", skill="search_text"), fill(args="beta"), ds("skill", skill="search_text"), fill(args="gamma")])
                turn("找 alpha 與 beta", fake)
            finally:
                domain_session.DOMAIN_STEPS_MAX = saved
            job = last_job()
            assert job["status"] == "stopped" and len(job["steps"]) == 2, (job["status"], len(job["steps"]))

        # ------------------------------------------------------------ 確認關卡
        def t_guard():
            fake = FakeChat(main=[task("重新啟動 cam_driver 容器", ["重新啟動 cam_driver"]), say("沒有重新啟動。")],
                            session=[ds("domains", domains=["robotics_infra"]), ds("skill", skill="docker_ctl"), fill(args="restart cam_driver"),
                                     ds("report", answers=[(1, "not_found", "使用者沒有同意重新啟動", [])], reply="沒有做")])
            events, waiting = turn("重新啟動 cam_driver", fake)
            assert waiting and agent.domain_pending and agent.domain_pending["kind"] == "guard", "停在確認關卡"
            assert any(e["channel"] == "domain_ask" and e["kind"] == "guard" for e in events)
            events2 = []
            flows.answer_domain_turn("否", events2)
            job = last_job()
            assert job["steps"][0]["status"] == "DENIED" and job["asked"][0]["approve"] is False, job["steps"]
            assert job["status"] == "done" and not agent.domain_pending
            assert "使用者回答「否」之後" in tools_of(events2)[0], tools_of(events2)[0][:200]

        # ------------------------------------------------------------ 提煉、再交辦、主 session 的核對
        def t_long_output():
            goal = "看 logs/big.log 最後的 step 是多少"
            fake = FakeChat(main=[task(goal, ["最後的 step"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="view_file"), fill(args="logs/big.log")])
            turn(goal, fake)
            st = last_job()["steps"][0]
            assert st["status"] == "PASS" and st["summarized"], st
            extract = [c for c in fake.calls if c["role"] == "other"]
            assert extract and any(goal in json.dumps(c["messages"], ensure_ascii=False) for c in extract), "提煉的錨點是交辦的子目標"

        def t_previous():
            fake = FakeChat(main=[task("找 alpha 定義", ["定義在哪"]), task("在 pkg 找 alpha 定義", ["定義在哪"]), say("好")])
            turn("alpha 定義在哪", fake)
            first = fake.session_msgs(-1)[1]["content"]
            assert "【上一次的經過】" in first and "第 1 次" in first, first[:600]

        def t_main_check():
            fake = FakeChat(
                main=[task("在 pkg 找 alpha 定義在哪", ["定義在哪"]),
                      answer("找到了。", [(1, "answered", "定義在 pkg/use.py:5", ["pkg/use.py:5"])]),
                      answer("找到了。", [(1, "answered", "定義在 pkg/mod.py:1（def alpha）", ["pkg/mod.py:1"])])],
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text"), fill(args='"def alpha" pkg'),
                         ds("report", answers=[(1, "answered", "定義在 pkg/mod.py 第 1 行（def alpha）", ["pkg/mod.py:1"])], reply="找到了")])
            events, _ = turn("alpha 定義在哪", fake)
            mains = [c for c in fake.calls if c["role"] == "main"]
            assert "沒有通過核對" in mains[2]["messages"][-1]["content"], "出處不在報告：交回修一次"
            assert "⚠️" not in final_reply(events), final_reply(events)

        def t_kept():
            fake = FakeChat(
                main=[task("照 docs/spec.md 回答", ["WAITING 時收到不同編號的確認會怎樣？引用規格的編號。"]),
                      answer("查到了。", [(1, "answered", "不變、繼續等", ["docs/spec.md:5"])]),
                      answer("查到了。", [(1, "answered", "不變、繼續等，最多 30 秒（SPEC-A12）", ["docs/spec.md:5"])])],
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text"), fill(args='"SPEC-A12" docs'),
                         ds("report", answers=[(1, "answered", "不變、繼續等，最多 30 秒（SPEC-A12）", ["docs/spec.md:5"])], reply="查到了")])
            events, _ = turn("照 docs/spec.md：WAITING 時收到不同編號的確認會怎樣？引用規格的編號。", fake)
            mains = [c for c in fake.calls if c["role"] == "main"]
            fix = mains[2]["messages"][-1]["content"]
            assert "沒有通過核對" in fix and "報告裡這一項寫了「SPEC-A12、30」，回答裡沒有" in fix, fix[:400]
            shown = final_reply(events)
            assert "⚠️" not in shown and "SPEC-A12" in shown, shown
            assert answers.dropped("總共 42 次（a.py 28 次、b.py 14 次），編號 REQ-7、WP_0815；見 a.py:12、第 40 行",
                                   "共 42 次：a.py 28、b.py 14；REQ-7、WP_0815") == [], "都寫了"
            assert answers.dropped("規格 TSK-F23-B04：重發，15.5 秒", "重發，15.50 秒") == ["TSK-F23-B04"], "數值一樣算有、編號漏了"
            assert answers.dropped("由 safety_node 合併，來源 3 個；設定在 config/nav2_v2.yaml", "由節點合併") == [], "名稱、10 以下的數、路徑不核對"
            assert answers.dropped("等 30 秒", "等一下", allowed="最多 30 秒嗎") == [], "問題裡本來就有的不核對"

        def t_archive_id():
            # 回答的文字寫了存檔的 #編號：交回修一次，#編號只寫在 refs（框架討論紀錄第 27 輪的 R2）
            fake = FakeChat(
                main=[task("照 docs/spec.md 回答", ["WAITING 時收到不同編號的確認會怎樣？引用規格的編號。"]),
                      answer("查到了。", [(1, "answered", "不變、繼續等（SPEC-A12，見 #3）", ["docs/spec.md:5"])]),
                      answer("查到了。", [(1, "answered", "不變、繼續等（SPEC-A12）", ["docs/spec.md:5"])])],
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text"), fill(args='"SPEC-A12" docs'),
                         ds("report", answers=[(1, "answered", "不變、繼續等，規格書的編號 #9", ["docs/spec.md:5"])], reply="查到了"),
                         ds("report", answers=[(1, "answered", "不變、繼續等（SPEC-A12）", ["docs/spec.md:5"])], reply="查到了")])
            events, _ = turn("照 docs/spec.md：WAITING 時收到不同編號的確認會怎樣？引用規格的編號。", fake)
            fix = fake.session_msgs(4)[-1]["content"]
            assert "沒有通過核對" in fix and "存檔的編號「#9」" in fix, ("領域 session 的回報：交回修一次", fix[:400])
            mains = [c for c in fake.calls if c["role"] == "main"]
            told = mains[2]["messages"][-1]["content"]
            assert "沒有通過核對" in told and "存檔的編號「#3」" in told, ("主 session 的回答：交回修一次", told[:400])
            shown = final_reply(events)
            assert "⚠️" not in shown and "SPEC-A12" in shown, shown

            def cited(ref):
                return ("id", [], ["#4 第 2 行：alpha"], [])

            said = [{"item": 1, "status": "answered", "text": "#4 裡寫 alpha", "refs": ["#4"]}]
            assert not answers.answer_problems(["x"], said, cited, "#4 寫了什麼", "alpha"), "使用者自己寫了 #編號的不擋"
            got = answers.answer_problems(["x"], said, cited, "", "alpha")
            assert any("#4" in w for w in got.get(1, [])), got
            assert not answers.answer_problems(["x"], [{"item": 1, "status": "not_found", "text": "#4 裡沒有", "refs": []}], cited, "", ""), \
                "查不到的原因不擋"

        def t_cover():
            # 每一句都要有歸屬（框架討論紀錄第 28 輪的 1；第 31 輪起「。」結尾的句子也算）：問句由程式整句放進項目（第 34 輪，t_ask_items）；
            # 「。」結尾的句子漏了，一輪的第一次交辦交回一次、補上就過；交回過一次照收；之後的交辦不核對
            q = "pkg 裡的 alpha 定義在哪？引用規格的編號。"
            fake = FakeChat(main=[task("找 pkg 裡的 alpha", ["pkg 裡的 alpha 定義在哪"]),
                                  task("找 pkg 裡的 alpha", ["pkg 裡的 alpha 定義在哪", "引用規格的編號"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            events, _ = turn(q, fake)
            outs = tools_of(events)
            assert outs[0].startswith("[ERROR]") and "「引用規格的編號。」沒有放進交辦的任何一欄" in outs[0], ("漏了的句子交回", outs[0][:300])
            assert last_job()["items"] == ["pkg 裡的 alpha 定義在哪", "引用規格的編號"], "補上就過"
            fake = FakeChat(main=[task("找 pkg 裡的 alpha", ["pkg 裡的 alpha 定義在哪"]), task("找 pkg 裡的 alpha", ["pkg 裡的 alpha 定義在哪"]),
                                  task("找呼叫 alpha 的地方", ["pkg 裡的 alpha 定義在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            events, _ = turn(q, fake)
            outs = tools_of(events)
            assert outs[0].startswith("[ERROR]") and not outs[1].startswith("[ERROR]"), ("交回過一次照收", [o[:80] for o in outs])
            assert len(outs) > 2 and not outs[2].startswith("[ERROR]"), ("之後的交辦不核對", [o[:80] for o in outs])
            agent.current_task = "照 docs/spec.md：alpha 在哪？預設多少？引用規格的編號。"
            assert agent._uncovered(["alpha 在哪"]) == ["預設多少？", "引用規格的編號。"], agent._uncovered(["alpha 在哪"])
            assert agent._uncovered(["alpha 在哪？預設多少"]) == ["引用規格的編號。"], "原話跨兩句：兩句都算（第三句沒抄到）"
            agent.current_task = "alpha 在哪? 誰用到?"
            assert agent._uncovered(["alpha 在哪"]) == ["誰用到?"], agent._uncovered(["alpha 在哪"])
            agent.current_task = "列出 pkg 底下符合 a?b 的檔案"
            assert agent._uncovered(["列出"]) == [], "「?」在字中間不算句尾；項目抄了這一句的一段就算"

        def t_context():
            # 交辦帶前文（第 28 輪的 2、3）：第一句沒有前文；第二句附上一句與當時的回覆、算可以抄的原文；前文裡使用者的話不用在出處裡找、
            # 當時的回覆要；錨點帶使用者前面的話；最新這一則的標示寫明項目照前後文讀；短的照原文、不提煉
            fake = FakeChat(main=[task("找 pkg 裡的 alpha", ["pkg 裡的 alpha 定義在哪"]), say("好")], session=[ds("domains", domains=["repo_analysis"])])
            turn("pkg 裡的 alpha 定義在哪？", fake)
            assert last_job()["context"] is None and "【前文】" not in fake.session_msgs(0)[-1]["content"], "第一句沒有前文"
            agent.reset_conversation()
            turn("pkg 裡的 alpha 定義在哪？", FakeChat(main=[say("alpha 定義在 pkg/mod.py 的第 1 行。")]))
            fake = FakeChat(main=[task("找呼叫 pkg 裡的 alpha 的地方", ["誰呼叫它"]), say("好")], session=[ds("domains", domains=["repo_analysis"])])
            turn("誰呼叫它？", fake)
            first = fake.session_msgs(0)[-1]["content"]
            assert "要回答的項目是從這一則切出來的" in first, first[:600]
            assert "【前文】" in first and "- 使用者：pkg 裡的 alpha 定義在哪？\n  當時的回覆：alpha 定義在 pkg/mod.py 的第 1 行。" in first, first[:900]
            job = last_job()
            assert job["context"] and job["context"]["result_id"] is None, job["context"]
            assert "當時的回覆：alpha 定義在 pkg/mod.py 的第 1 行。" in job["sources"], "前文算可以抄的原文"
            allowed = domain_session.DomainSession._allowed(job)
            assert "pkg 裡的 alpha 定義在哪？" in allowed and "pkg/mod.py 的第 1 行" not in allowed, "前文裡使用者的話不核對、當時的回覆要"
            assert "使用者前面說的" in domain_session.DomainSession._anchor(job) and "pkg 裡的 alpha 定義在哪？" in domain_session.DomainSession._anchor(job)
            assert not [c for c in fake.calls if c["role"] == "other"], "前文短的照原文：不提煉"

        def t_context_long():
            # 前文超過門檻：存成一份存檔（dispatch_context）、照錨點提煉，附提煉的結果（跟工具結果一樣）
            turn("把 pkg 的說明都列出來", FakeChat(main=[say("alpha 的說明：" + "、".join(f"第 {k} 段 value {k * 3}" for k in range(400)))]))
            fake = FakeChat(main=[task("找呼叫 alpha 的地方", ["誰呼叫它"]), say("好")], session=[ds("domains", domains=["repo_analysis"])])
            turn("誰呼叫它？", fake)
            ctx = last_job()["context"]
            assert ctx and ctx["result_id"] and ctx["tokens"] > TOOL_RESULT_TOKEN_THRESHOLD, ctx
            first = fake.session_msgs(0)[-1]["content"]
            assert f"系統存成 #{ctx['result_id']}" in first and ctx["shown"] in first, first[:600]
            extract = [c for c in fake.calls if c["role"] == "other"]
            assert extract and any("誰呼叫它" in json.dumps(c["messages"], ensure_ascii=False) for c in extract), "照錨點（子目標與項目）提煉"
            rec = next(r for r in reversed(agent.trajectory) if r.get("id") == ctx["result_id"])
            assert rec["script"] == "dispatch_context", rec

        def t_cpp_defs():
            # cpp_symbol 分開宣告與定義：先列有本體的定義（code_defs --has），再搜名稱（標頭檔的宣告與用到的地方）——框架討論紀錄第 29 輪
            for rel, text in CAM_FILES.items():
                os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
                with open(os.path.join(tmp, rel), "w", encoding="utf-8") as f:
                    f.write(text)
            q = "cam 裡 FrameGrabber 的哪個成員函式抓畫面？定義在哪個檔案的第幾行？"
            fake = FakeChat(main=[task("找 cam 裡 FrameGrabber 抓畫面的成員函式與定義的位置", [q]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="cpp_symbol"),
                                     fill(params=[("names", "FrameGrabber", "FrameGrabber"), ("path", "cam", "cam")])])
            turn(q, fake)
            st = next(s for s in last_job()["steps"] if s["kind"] == "composite")
            assert st["status"] == "done" and [o["tool"] for o in st["composite"]["outputs"]] == ["code_defs", "search_text"], st["composite"]
            shown = fake.session_msgs(3)[-1]["content"]
            assert "— 有本體的定義：code_defs" in shown and "— 提到這些名稱的行" in shown, shown[:800]
            defs = shown.split("— 有本體的定義：code_defs", 1)[1].split("\n— ", 1)[0]
            for want in ("def FrameGrabber::grabFrame（行 4-7）", "class FrameGrabber（行 3-9）", "def FrameGrabber::count（行 6）"):
                assert want in defs, (want, defs)
            assert "grabFrame();" not in defs, ("標頭檔裡 ; 結尾的宣告不在定義那一份", defs)
            hits = shown.split("— 提到這些名稱的行", 1)[1]
            assert "grabFrame();" in hits, ("宣告在搜尋那一份", hits[:600])

        def t_cover_parts():
            # 交辦的核對看每一句與「、」接的每一段（框架討論紀錄第 31 輪）：「。」結尾、要你做的句子也算；一句裡用「、」接的只抄一段不算——
            # 問句由程式整句放進項目（第 34 輪）、「。」結尾的交回，說明列出缺的那幾段；整句抄了、用「、」接的幾段抄在同一項就過
            from agent_core.orchestrator import ask_parts, ask_sentences
            assert ask_parts("a、b？c。d") == [(0, 1, "a"), (2, 3, "b？"), (4, 5, "c。"), (6, 7, "d")], ask_parts("a、b？c。d")
            assert ask_sentences("a、b？c。d") == [(0, 4, "a、b？", True), (4, 6, "c。", False), (6, 7, "d", False)], ask_sentences("a、b？c。d")
            agent.current_task = "照 docs/spec.md：alpha 的預設值是多少？引用規格的編號。"
            assert agent._uncovered(["alpha 的預設值是多少？"]) == ["引用規格的編號。"], agent._uncovered(["alpha 的預設值是多少？"])
            assert agent._uncovered(["alpha 的預設值是多少？引用規格的編號。"]) == [], "原話跨兩句：兩句都算"
            agent.current_task = "啟動時 cam_driver 的影像發布到哪個 topic、頻率多少、會不會發 TF？誰用這個影像？"
            got = agent._uncovered(["cam_driver 的影像發布到哪個 topic"])
            assert got == ["頻率多少", "會不會發 TF？", "誰用這個影像？"], got
            assert agent._uncovered(["啟動時 cam_driver 的影像發布到哪個 topic、頻率多少、會不會發 TF？", "誰用這個影像？"]) == [], "整句抄了就過"
            q = "pkg 裡的 alpha 發布到哪個 topic、頻率多少？"
            fake = FakeChat(main=[task("找 pkg 裡的 alpha", ["pkg 裡的 alpha 發布到哪個 topic"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn(q, fake)[0])
            assert not outs[0].startswith("[ERROR]") and last_job()["items"] == ["pkg 裡的 alpha 發布到哪個 topic、頻率多少？"], \
                ("只抄一段的問句由程式整句放進項目", outs[0][:300])
            q = "照 docs/spec.md 列出 alpha 的預設值、引用規格的編號。"
            fake = FakeChat(main=[task("照 docs/spec.md 查 alpha", ["照 docs/spec.md 列出 alpha 的預設值"]),
                                  task("照 docs/spec.md 查 alpha", ["照 docs/spec.md 列出 alpha 的預設值、引用規格的編號。"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn(q, fake)[0])
            assert outs[0].startswith("[ERROR]") and "「引用規格的編號。」沒有放進交辦的任何一欄" in outs[0] and "「、」接的每一段都要抄到" in outs[0], outs[0][:300]
            assert last_job()["items"] == ["照 docs/spec.md 列出 alpha 的預設值、引用規格的編號。"], "補上就過"

        def t_ref_line():
            # 出處把原文的行號寫成 #N（框架討論紀錄第 31 輪）：#N 不是存檔、但收據裡有某個檔案的第 N 行 → 交回的說明寫明檔案與存檔、出處怎麼寫；
            # 對不到的照舊
            q = "照 docs/spec.md：WAITING 時收到不同編號的確認會怎樣？"
            fake = FakeChat(
                main=[task("照 docs/spec.md 查 WAITING 時收到不同編號的確認", [q]), say("好")],
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text"), fill(args='"SPEC-A12" docs/spec.md'),
                         ds("report", answers=[(1, "answered", "不變：繼續等，最多 30 秒（SPEC-A12）", ["#5"])], reply="找到了"),
                         ds("report", answers=[(1, "answered", "不變：繼續等，最多 30 秒（SPEC-A12）", ["docs/spec.md:5"])], reply="改好了")])
            turn(q, fake)
            job = last_job()
            rid = job["steps"][0]["result_ids"][0]
            fix = fake.session_msgs(4)[-1]["content"]
            assert "出處 #5 不在這個 session 的結果裡" in fix and f"5 是 #{rid} 裡 docs/spec.md 的第 5 行" in fix and "「docs/spec.md:5」" in fix, fix[:600]
            assert job["status"] == "done" and not job["problems"], (job["status"], job["problems"])
            path = agent.result_file_path(rid)
            assert answers.line_owners([(rid, path)], 5, job["cwd"]) == [(rid, "docs/spec.md")], answers.line_owners([(rid, path)], 5, job["cwd"])
            assert answers.line_owners([(rid, path)], 9, job["cwd"]) == [], "收據裡沒有第 9 行"
            assert domain_session.DomainSession._ref_unknown(job, "#9", [(rid, path)]) == "出處 #9 不在這個 session 的結果裡", "對不到的照舊"

        def task3(goal, items, background=(), constraints=()):
            t = task(goal, items)
            t["action"]["task"].update(background=[{"quote": x} for x in background], constraints=[{"quote": x} for x in constraints])
            return t

        def t_task_context():
            # 交辦時分清楚問題、限制與背景（框架討論紀錄第 32 輪的 U1）：背景與限制放進自己的欄就不交回；沒放進任何一欄的交回；問句只放進背景或限制的
            # 由程式整句放進項目（第 34 輪）；背景與限制只記在 job，領域 session 的第一則訊息與提煉的錨點不放（第 36 輪的 L1）；評測的紀錄記下三欄
            q = "pkg 的 alpha 最近改過。alpha 定義在哪？先不要改任何檔案。"
            fake = FakeChat(main=[task3("找 pkg 裡的 alpha 定義在哪", ["alpha 定義在哪？"], ["pkg 的 alpha 最近改過。"], ["先不要改任何檔案。"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            events, _ = turn(q, fake)
            outs = tools_of(events)
            assert not outs[0].startswith("[ERROR]"), ("背景與限制放進自己的欄：不交回", outs[0][:300])
            job = last_job()
            assert (job["items"], job["background"], job["constraints"]) == (["alpha 定義在哪？"], ["pkg 的 alpha 最近改過。"], ["先不要改任何檔案。"]), job
            first = fake.session_msgs(0)[-1]["content"]
            assert "【限制】" not in first and "【背景】" not in first and "- 先不要改任何檔案。" not in first, ("第一則訊息不放背景與限制", first[:900])
            assert "【要回答的項目】（使用者的原話；回報時 answers 照這個編號）\n1. alpha 定義在哪？\n\n【使用者的原始問題】" in first, first[:900]
            anchor = domain_session.DomainSession._anchor(job)
            assert "要回答的項目：alpha 定義在哪？" in anchor and "最近改過" not in anchor and "先不要改" not in anchor, ("錨點不放背景與限制", anchor)
            fake = FakeChat(main=[task3("找 pkg 裡的 alpha", ["alpha 定義在哪？"]),
                                  task3("找 pkg 裡的 alpha", ["alpha 定義在哪？"], ["pkg 的 alpha 最近改過。"], ["先不要改任何檔案。"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn(q, fake)[0])
            assert outs[0].startswith("[ERROR]") and "「pkg 的 alpha 最近改過。」、「先不要改任何檔案。」沒有放進交辦的任何一欄" in outs[0], outs[0][:400]
            assert not outs[1].startswith("[ERROR]"), "補上就過"
            q2 = "alpha 定義在哪？誰呼叫它？"
            fake = FakeChat(main=[task3("找 pkg 裡的 alpha", ["alpha 定義在哪？"], ["誰呼叫它？"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn(q2, fake)[0])
            assert not outs[0].startswith("[ERROR]"), outs[0][:400]
            assert (last_job()["items"], last_job()["added"]) == (["alpha 定義在哪？", "誰呼叫它？"], ["誰呼叫它？"]), "問句只放進背景：程式整句放進項目"
            parsed = {"action": {"task": {"goal": "g", "background": [{"quote": "b"}], "constraints": [{"quote": "c"}], "items": [{"quote": "i"}]}}}
            rec = domain_calls.calls(agent, parsed, "[ERROR] 不行")[0]
            assert rec["background"] == ["b"] and rec["constraints"] == ["c"] and rec["items"] == ["i"], rec

        def t_context_dropped():
            # 背景與限制不是使用者的原話的由程式拿掉、不交回（框架討論紀錄第 33 輪的 V1）：填的「無」、自己整理的經過拿掉，交辦照收；job 只記原話的
            # 那幾則（領域 session 看不到背景與限制，第 36 輪）；拿掉的記在 job 與評測的紀錄。歸屬只算原話的：改寫的限制拿掉之後，那一段照樣算沒放進任何一欄
            q = "pkg 的 alpha 最近改過。alpha 定義在哪？先不要改任何檔案。"
            act = task3("找 pkg 裡的 alpha 定義在哪", ["alpha 定義在哪？"], ["pkg 的 alpha 最近改過。", "之前查過一次沒找到"], ["無", "先不要改任何檔案。"])
            fake = FakeChat(main=[act, say("好")], session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn(q, fake)[0])
            assert not outs[0].startswith("[ERROR]"), ("不是原話的背景與限制拿掉、交辦照收", outs[0][:300])
            job = last_job()
            assert (job["background"], job["constraints"], job["dropped"]) == (["pkg 的 alpha 最近改過。"], ["先不要改任何檔案。"],
                                                                              ["之前查過一次沒找到", "無"]), job
            first = fake.session_msgs(0)[-1]["content"]
            assert "之前查過一次沒找到" not in first and "- 無" not in first, first[:900]
            assert "之前查過一次沒找到" not in domain_session.DomainSession._anchor(job), "提煉的錨點也沒有"
            rec = domain_calls.calls(agent, act, outs[0])[0]
            assert rec["background"] == ["pkg 的 alpha 最近改過。", "之前查過一次沒找到"] and rec["dropped"] == ["之前查過一次沒找到", "無"], rec
            fake = FakeChat(main=[task3("找 pkg 裡的 alpha", ["alpha 定義在哪？"], ["pkg 的 alpha 最近改過。"], ["不要改檔案"]),
                                  task3("找 pkg 裡的 alpha", ["alpha 定義在哪？"], ["pkg 的 alpha 最近改過。"], ["先不要改任何檔案。"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn(q, fake)[0])
            assert outs[0].startswith("[ERROR]") and "「先不要改任何檔案。」沒有放進交辦的任何一欄" in outs[0], ("改寫的限制拿掉，那一段照樣交回", outs[0][:400])
            assert not outs[1].startswith("[ERROR]") and last_job()["dropped"] == [], "補上原話就過"

        def t_ask_items():
            # 問句由程式整句放進項目（框架討論紀錄第 34 輪的 W1b）：一輪還沒有收下的交辦時，最新這一則的問句有一段不在項目，程式把整句照原話放進項目
            # （項目裡是這一句一部分的換成整句、放在原本的位置，沒有就加在最後）；改寫的項目拿掉；一項都沒留下、也沒有問句可放時交回第一項；
            # 第二次以後的交辦照模型挑的項目；放進去的與拿掉的記在 job 與評測的紀錄
            q = "pkg 的 alpha 最近改過。pkg 裡的 alpha 定義在哪、誰呼叫它？它的預設值是多少？"
            act = task3("找 pkg 裡的 alpha", ["alpha 的預設值是什麼？", "alpha 定義在哪"], ["pkg 的 alpha 最近改過。", "pkg 裡的 alpha 定義在哪、誰呼叫它？"])
            fake = FakeChat(main=[act, say("好")], session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn(q, fake)[0])
            assert not outs[0].startswith("[ERROR]"), ("問句由程式放進項目、改寫的拿掉：不交回", outs[0][:300])
            job = last_job()
            whole = ["pkg 裡的 alpha 定義在哪、誰呼叫它？", "它的預設值是多少？"]
            assert (job["items"], job["added"], job["dropped"]) == (whole, whole, ["alpha 的預設值是什麼？"]), job
            assert "1. pkg 裡的 alpha 定義在哪、誰呼叫它？\n2. 它的預設值是多少？\n" in fake.session_msgs(0)[-1]["content"], "領域 session 看到的是整句"
            rec = domain_calls.calls(agent, act, outs[0])[0]
            assert rec["items"] == ["alpha 的預設值是什麼？", "alpha 定義在哪"] and rec["added"] == whole and rec["dropped"] == ["alpha 的預設值是什麼？"], rec
            fake = FakeChat(main=[task("改 alpha 的名稱", ["將 alpha 改名為 beta"]), say("好")], session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn("把 pkg 的 alpha 改名成 beta。", fake)[0])
            assert outs[0].startswith("[ERROR]") and "第 1 項「將 alpha 改名為 beta」不在使用者說過的話裡" in outs[0], ("一項都沒留下：交回", outs[0][:300])
            fake = FakeChat(main=[task("找 alpha 的定義", ["alpha 定義在哪？", "誰呼叫它？"]), task("再找呼叫 alpha 的地方", ["誰呼叫它？"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"])])
            outs = tools_of(turn("alpha 定義在哪？誰呼叫它？", fake)[0])
            assert not outs[1].startswith("[ERROR]") and (last_job()["items"], last_job()["added"]) == (["誰呼叫它？"], []), \
                ("第二次以後的交辦照模型挑的項目", outs[1][:200])

        for name, fn in [("主 session：交辦一節、索引、回覆的 schema 與解析", t_prompt_schema),
                         ("回覆的欄位順序（主 session 的 action 最後；領域 session 照說明的順序）", t_reply_order), ("擋領域的工具與有骨架的技能", t_gate),
                         ("主 session 把領域的名稱當技能：說明要交辦；看到的字不寫識別名稱", t_domain_named),
                         ("交辦的核對", t_task_checks), ("交辦的每一項是使用者的原話（核對、帶到領域 session、追問時用之前的訊息）", t_quote),
                         ("領域 session 用工具：選領域、技能清單、結果、回報、主 session 照項目回答", t_tool_flow),
                         ("評測的紀錄（domain_calls）", t_tool_records),
                         ("有骨架的技能：合約、執行、一模一樣的不執行", t_composite),
                         ("路徑的一段混了說明的字或萬用字元：只留原文裡的名稱、結果裡寫明", t_path_names),
                         ("參數表單：抄到程式的標題照樣核對、重填還是沒過回到選技能", t_form),
                         ("參數表單：值對得上原文的不擋（值本身在原文裡、大小寫、預設值、工作目錄的絕對路徑）、編的與翻譯的照舊交回、"
                          "預設值配寫著別的名稱的 quote 交回", t_grounded),
                         ("參數表單：原文沒有的搜尋字，要搜的範圍裡有才收（出處寫範圍）、範圍裡沒有的與自己選的檔名寫法照舊交回", t_scope),
                         ("參數表單：要讀的那一份只寫了上層、或上層與名稱寫在同一段，照原文的「<a> 的 <b>」找到剛好一份才換（找不到、好幾份照舊）", t_doc_of),
                         ("工具的參數表單：args 寫成 JSON、照抄佔位符、填「[]」的交回重填", t_form_tool),
                         ("有骨架的技能的彙整：程式照收據算的數量存成 #編號、總數照它寫就過核對", t_totals), ("回退換技能", t_composite_switch),
                         ("路徑有好幾個交回決定、0 筆照實交回", t_composite_need_and_empty), ("狀態與上限", t_states_limits),
                         ("確認關卡", t_guard), ("長的結果照舊提煉", t_long_output), ("再交辦帶著上一次的經過", t_previous),
                         ("主 session 依報告回答的核對", t_main_check), ("依報告回答漏了報告的編號與數字：交回修一次", t_kept),
                         ("回答的文字寫了存檔的 #編號：交回修一次（回報與主 session 的回答；使用者自己寫了的、查不到的原因不擋）", t_archive_id),
                         ("每一句都要有歸屬：「。」結尾的句子漏了，一輪的第一次交辦交回一次、補上就過、交回過照收、之後的交辦不核對（「?」在字中間的不算句尾；問句由程式放進項目）", t_cover),
                         ("交辦帶前文：附上一句與當時的回覆、算可以抄的原文、錨點帶使用者前面的話；第一句沒有前文", t_context),
                         ("交辦帶前文：長的存檔並照錨點提煉", t_context_long),
                         ("cpp_symbol 分開宣告與定義：有本體的定義那一份列 .cpp 的成員函式與標頭檔的類別、不列 ; 結尾的宣告，搜尋那一份照舊", t_cpp_defs),
                         ("交辦的核對看每一句與「、」接的每一段：「。」結尾的句子也算、只抄一段不算（問句由程式整句放進項目、「。」結尾的交回並列出缺的那幾段）、整句抄了就過", t_cover_parts),
                         ("出處把原文的行號寫成 #N：收據裡有某個檔案的第 N 行時交回的說明寫明檔案與存檔，對不到的照舊", t_ref_line),
                         ("交辦時分清楚問題、限制與背景：各放進自己的欄、沒有歸屬的交回、問句只放進背景的由程式放進項目、背景與限制只記在 job（第一則訊息與提煉的錨點不放）、評測的紀錄", t_task_context),
                         ("背景與限制不是使用者的原話的由程式拿掉、不交回：交辦照收、job 只記原話的、拿掉的記在 job 與評測的紀錄、改寫的那一段照樣算沒放進", t_context_dropped),
                         ("問句由程式整句放進項目：只抄一段或只放進背景的換成整句、改寫的項目拿掉、一項都沒留下時交回、第二次以後的交辦不放、記在 job 與評測的紀錄", t_ask_items)]:
            check(name, fn)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    ok = sum(1 for _, passed, _ in results if passed)
    print(f"\n交辦與領域 session 的自我測試：{ok}/{len(results)} 通過")
    for name, passed, tb in results:
        if not passed:
            print(f"\n--- {name} ---\n{tb}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
