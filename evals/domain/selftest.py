"""交辦與領域 session（agent_core/orchestrator.py、domain_session.py、composite.py；docs/框架討論紀錄.md）的離線自我測試：假的主模型與
領域 session 的模型照劇本回，真的有骨架的技能、低階與工具（工作目錄是臨時的小專案），直接驅動 Web 的回合（web_app.flows.run_turn），
幾秒跑完、不需要 Ollama。

- 主 session：system prompt 的「交辦」一節（每個領域一行）、技能索引拿掉領域的工具、回覆的 schema 多「交辦」；回覆的欄位順序（主 session 的
  action 最後、AGENT.md 的範例與存回對話的 JSON 也一樣；領域 session 照說明的順序）；擋領域的工具與有骨架的技能
  （領域 session 裡只能用它選的領域的工具與共用的工具）；交辦的核對（子目標是空的、項目數、一樣的再交一次、同一個項目最多 3 次）；
- 領域 session 用工具：選領域 → 技能清單（做法、有骨架的技能與參數、工具與 args 的寫法、共用的工具）→ 用一個工具（存檔 #編號）→ 回報（核對過）
  → 報告交回主 session（不提煉）＋依報告回答的說明 → 主 session 照項目回答（附出處那一行的原文）；
- 有骨架的技能：合約（原文要在給它看過的字裡）沒過的交回改、不算一步；照骨架執行、每個節點的結果附 #編號；一模一樣的不執行；
  參數寫錯欄位（有骨架的技能寫在 args、工具寫在 params）擋下說明、不執行；
  回退換技能（.py 沒有、C++ 檔有 → cpp_symbol）；路徑有好幾個交回它決定（附候選）；0 筆照實交回（跑完、結果是 0 筆）；
- 狀態與上限：第一輪不是選領域、回覆不是 JSON、重選領域超過上限、技能用完上限；
- 確認關卡：停下來、主 session 轉問使用者（Web）、不同意 → [DENIED] 交給它接著做；
- 長的結果照舊提煉（錨點是交辦的子目標與項目）；
- 主 session 依報告回答的核對（出處不在報告 → 交回修一次）；同一個問題再交辦時帶著上一次的經過；
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
    "logs/big.log": "".join(f"2026-01-01 00:00:{k % 60:02d} worker_{k % 7} step {k} value {k * 3}\n" for k in range(600)),
}
SESSION_MARK = "你是領域 session"


def task(goal, items):
    return {"thought": "交辦", "reply": "交辦給領域 session。", "action": {"task": {"goal": goal, "items": list(items)}}}


def say(reply):
    return {"thought": "回覆", "reply": reply, "action": None}


def answer(reply, rows):
    """依報告回答的回覆：rows＝[(項目編號, status, text, refs)]。"""
    return {"thought": "依報告回答", "reply": reply, "action": None,
            "answers": [{"item": k, "status": st, "text": t, "refs": list(refs)} for k, st, t, refs in rows]}


def ds(state, domains=(), skill="", params=(), args="", answers=(), reply="這一步", thought="想法"):
    """領域 session 的一輪：params＝[(名稱, 值, 原文)]、answers＝[(項目編號, status, text, refs)]。"""
    return {"thought": thought, "state": state, "domains": list(domains), "skill": skill,
            "params": [{"name": n, "value": v, "quote": q} for n, v, q in params], "args": args,
            "answers": [{"item": k, "status": st, "text": t, "refs": list(r)} for k, st, t, r in answers], "reply": reply}


def _items(fmt):
    try:
        return fmt["properties"]["answers"]["items"]["properties"]["item"]["enum"]
    except (KeyError, TypeError):
        return []


class FakeChat:
    """假的 ollama.chat：照 format 的欄位分角色（主 session、領域 session、第 1 級修正、其他＝提煉與摘要），各自依序取劇本；
    一則可以是函式（看對話決定回什麼），或 "RAW:" 開頭的字串（原樣回，測回覆不是 JSON）。"""

    def __init__(self, main=(), session=()):
        self.q = {"main": list(main), "session": list(session)}
        self.calls = []

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = set((format or {}).get("properties", {})) if isinstance(format, dict) else set()
        role = "session" if "state" in props else "main" if "action" in props else "fix" if "fixable" in props else "other"
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
            fn()
            results.append((name, True, ""))
            print(f"✅ {name}")
        except Exception:   # noqa: BLE001
            results.append((name, False, traceback.format_exc()))
            print(f"❌ {name}")

    try:
        import ollama
        ollama.list = lambda: {"models": []}
        from agent_core import domain_session
        from agent_core.config import DOMAIN_RESULT_HEAD
        from agent_core.jobstore import JobStore
        from agent_core.config import REPLY_ARGS_CHARS
        from agent_core.protocol import action_text, drop_cut, parse_agent_reply
        from agent_core.schemas import agent_reply_schema, domain_session_schema
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
            for d in reg["domains"].values():
                assert d["title"] in system, d["title"]
            avail = system.split("## Available Skills")[1].split("## Tasks")[0]
            for t in HIDDEN:
                assert f"[{t}]" not in avail, f"{t} 是領域的工具，主 session 的索引不列"
            for t in SHARED:
                assert f"[{t}]" in avail, f"{t} 是共用的工具"
            actions = call["format"]["properties"]["action"]["anyOf"]
            assert any("task" in (a.get("properties") or {}) for a in actions), "回覆的 schema 要有交辦"
            assert not any("domains" in (a.get("properties") or {}) for a in actions)
            assert "task" not in str(agent_reply_schema(False, 0)), "沒有領域時沒有交辦"
            parsed = parse_agent_reply(json.dumps({"thought": "", "reply": "", "action": {"task": {"goal": " 找  alpha ", "items": ["哪裡", " "]}}},
                                                  ensure_ascii=False))
            assert parsed["action"] == {"task": {"goal": "找 alpha", "items": ["哪裡"]}}, parsed["action"]
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
            assert order == ["thought", "state", "domains", "skill", "params", "args", "answers", "reply"], order
            system = domain_session.DomainSession(agent, agent.domain_registry())._system()
            assert "、".join(order) in system, "domain/session.md 寫的欄位順序跟 schema 一樣"

        def t_gate():
            assert "交辦" in (agent.domain_gate("search_text") or ""), "主 session 叫領域的工具要擋"
            assert "交辦" in (agent.domain_gate("scripts/grep_cmd.py") or ""), "腳本也擋"
            assert "有骨架的技能" in (agent.domain_gate("py_usage") or ""), "有骨架的技能的名稱也擋"
            assert agent.domain_gate("list_dir") is None, "共用的工具照用"
            agent._sub_allowed = {"domain": "repo_analysis", "tools": {"search_text", "list_dir"}}
            try:
                assert agent.domain_gate("search_text") is None, "領域 session 裡選的領域的工具可以用"
                blocked = agent.domain_gate("docker_ctl") or ""
                assert "不在你選的領域的技能清單裡" in blocked and "search_text" in blocked, blocked
            finally:
                agent._sub_allowed = None

        def t_task_checks():
            agent.set_current_task("檢查")
            assert "goal" in agent.run_task({"task": {"goal": "", "items": ["a"]}}), "子目標是空的要擋"
            assert "1～6 項" in agent.run_task({"task": {"goal": "g", "items": []}}), "項目數要擋"
            fake = FakeChat(main=[task("找 alpha", ["定義在哪"]), task("找 alpha", ["定義在哪"]), say("好")])
            events, _ = turn("找 alpha 定義在哪", fake)
            outs = tools_of(events)
            assert outs[0].startswith(DOMAIN_RESULT_HEAD) and "交辦的報告" in outs[0], outs[0][:200]
            assert "一模一樣" in outs[1], outs[1][:200]
            fake = FakeChat(main=[task(f"找 alpha 第 {k} 次", ["項目A"]) for k in range(4)] + [say("好")])
            events, _ = turn("找 alpha", fake)
            assert "最多 3 次" in tools_of(events)[3], tools_of(events)[3][:200]

        # ------------------------------------------------------------ 領域 session：工具
        def t_tool_flow():
            q = "pkg 裡的 alpha 定義在哪個檔案的第幾行？"
            fake = FakeChat(
                main=[task("在 pkg 找 alpha 定義在哪", ["alpha 定義在哪個檔案、哪一行"]),
                      answer("找到了。", [(1, "answered", "定義在 pkg/mod.py:1（def alpha）", ["pkg/mod.py:1"])])],
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text", args='search_text "def alpha" pkg'),
                         ds("report", answers=[(1, "answered", "定義在 pkg/mod.py 第 1 行（def alpha）", ["pkg/mod.py:1"])], reply="找到了")])
            events, _ = turn(q, fake)
            first = fake.session_msgs(0)
            assert SESSION_MARK in first[0]["content"] and "repo_analysis" in first[0]["content"], "system prompt 有領域清單"
            assert "【子目標】" in first[-1]["content"] and "先選領域" in first[-1]["content"]
            listing = fake.session_msgs(1)[-1]["content"]
            assert "【技能清單】" in listing and "py_usage" in listing and "參數：" in listing, listing[:500]
            assert "args 的寫法：`\"<關鍵字>\"" in listing and "`search_text " not in listing, "工具附 args 的寫法（只有參數的部分）"
            job = last_job()
            assert job["status"] == "done" and job["domains"] == ["repo_analysis"], job["status"]
            assert [s["skill"] for s in job["steps"]] == ["search_text"] and job["steps"][0]["result_ids"], job["steps"]
            assert job["steps"][0]["args"] == '"def alpha" pkg', "args 開頭照抄的工具名稱拿掉"
            assert not job["problems"], job["problems"]
            result = fake.session_msgs(2)[-1]["content"]
            assert result.startswith("[tool result]") and "【第 1 步的結果】search_text" in result and "（存檔 #" in result, result[:300]
            report = tools_of(events)[0]
            assert report.startswith(DOMAIN_RESULT_HEAD) and "交辦的報告（做完）" in report and "這一回合要回答的項目" in report, report[:300]
            assert "> " in report and "pkg/mod.py:1" in report, "報告的回答附出處那一行"
            shown = final_reply(events)
            assert "1. alpha 定義在哪個檔案、哪一行：定義在 pkg/mod.py:1" in shown and "> " in shown, shown

        def t_tool_records():
            parsed = {"action": {"task": {"goal": "在 pkg 找 alpha 定義在哪", "items": ["alpha 定義在哪個檔案、哪一行"]}}}
            recs = domain_calls.calls(agent, parsed, DOMAIN_RESULT_HEAD + "報告")
            head = recs[0]
            assert head["skill"] == "domain_session" and head["job"] and head["domains"] == ["repo_analysis"] and head["steps"] == 1, head
            assert recs[1]["skill"] == "search_text" and recs[1]["via"] == "domain_session" and recs[1]["args"] == ["def alpha", "pkg"], recs[1]
            err = domain_calls.calls(agent, parsed, "[ERROR] 不行")
            assert len(err) == 1 and err[0]["status"] == "ERROR"

        # ------------------------------------------------------------ 領域 session：有骨架的技能
        def t_composite():
            q = "pkg 裡的 alpha 定義在哪、哪裡用到？"
            fake = FakeChat(
                main=[task("找 pkg 裡的 alpha 定義在哪、哪裡用到", ["定義在哪", "哪裡用到"]), say("好")],
                session=[ds("domains", domains=["repo_analysis"]),
                         ds("skill", skill="py_usage", params=[("name", "omega", "omega")]),
                         ds("skill", skill="py_usage", params=[("name", "alpha", "alpha"), ("path", "pkg", "pkg")]),
                         ds("skill", skill="py_usage", params=[("name", "alpha", "alpha"), ("path", "pkg", "pkg")])])
            turn(q, fake)
            rejected = fake.session_msgs(2)[-1]["content"]
            assert "參數沒有通過核對" in rejected and "omega" in rejected, rejected[:300]
            job = last_job()
            comp = [s for s in job["steps"] if s["kind"] == "composite"]
            assert len(comp) == 1, f"合約沒過不算一步、一模一樣的不執行：{[s['skill'] for s in job['steps']]}"
            st = comp[0]
            assert st["status"] == "done" and st["params"]["name"]["value"] == "alpha" and st["params"]["path"]["value"] == "pkg", st
            assert len(st["result_ids"]) >= 2 and {o["tool"] for o in st["composite"]["outputs"]} >= {"search_text", "code_ast_reader"}, st
            shown = fake.session_msgs(3)[-1]["content"]
            assert "技能的狀態：跑完" in shown and "— 名稱的每一處：code_ast_reader" in shown, shown[:500]
            same = fake.session_msgs(4)[-1]["content"]
            assert "一模一樣" in same, same[:200]

        def t_wrong_field():
            q = "pkg 裡的 alpha 定義在哪？"
            fake = FakeChat(main=[task("找 pkg 裡的 alpha 定義在哪", ["定義在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]),
                                     ds("skill", skill="py_usage", args='{"name": "alpha", "path": "pkg"}'),
                                     ds("skill", skill="search_text", params=[("keyword", "alpha", "alpha")])])
            turn(q, fake)
            comp = fake.session_msgs(2)[-1]["content"]
            assert "py_usage 是有骨架的技能" in comp and "沒有執行" in comp and "name、path" in comp, comp[:300]
            tool = fake.session_msgs(3)[-1]["content"]
            assert "search_text 是工具" in tool, tool[:300]
            job = last_job()
            assert not job["steps"], f"寫錯欄位的不執行、不算一步：{[s['skill'] for s in job['steps']]}"
            whys = [b["why"] for b in job["blocked"]][:2]
            assert whys == ["py_usage 有骨架，參數寫在 args", "search_text 是工具，參數寫在 params"], whys

        def t_composite_switch():
            q = "cpp 底下的 delta 定義在哪？"
            fake = FakeChat(main=[task("找 cpp 底下的 delta 定義在哪", ["定義在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]),
                                     ds("skill", skill="py_usage", params=[("name", "delta", "delta"), ("path", "cpp", "cpp")])])
            turn(q, fake)
            st = last_job()["steps"][0]
            assert st["composite"]["skill"] == "cpp_symbol" and st["composite"]["switched"], st["composite"]
            shown = fake.session_msgs(2)[-1]["content"]
            assert "py_usage 換成 cpp_symbol" in shown and "node.cpp" in shown, shown[:600]

        def t_composite_need_and_empty():
            q = "sub 裡的 alpha 在哪？找不到的 zeta 呢？"
            fake = FakeChat(main=[task("找 sub 裡的 alpha，與 zeta", ["alpha 在哪", "zeta 在哪"]), say("好")],
                            session=[ds("domains", domains=["repo_analysis"]),
                                     ds("skill", skill="cpp_symbol", params=[("names", "alpha", "alpha"), ("path", "sub", "sub")]),
                                     ds("skill", skill="cpp_symbol", params=[("names", "zeta", "zeta")])])
            turn(q, fake)
            steps = last_job()["steps"]
            assert steps[0]["status"] == "need" and not steps[0]["result_ids"], steps[0]
            need = fake.session_msgs(2)[-1]["content"]
            assert "有好幾個" in need and "left/sub" in need and "right/sub" in need, need[:400]
            assert steps[1]["status"] == "done" and steps[1]["result_ids"], "0 筆照實交回：跑完、附結果"
            empty = fake.session_msgs(3)[-1]["content"]
            assert "技能的狀態：跑完" in empty and "範圍外提到這些名稱的 C++ 檔" in empty, empty[:500]

        # ------------------------------------------------------------ 狀態與上限
        def t_states_limits():
            fake = FakeChat(main=[task("找 alpha", ["在哪"]), say("好")],
                            session=["RAW:不是 JSON", ds("skill", skill="search_text", args="alpha"), ds("domains", domains=["repo_analysis"]),
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
                fake = FakeChat(main=[task("找 alpha 與 beta", ["在哪"]), say("好")],
                                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text", args="alpha"),
                                         ds("skill", skill="search_text", args="beta"), ds("skill", skill="search_text", args="gamma")])
                turn("找 alpha 與 beta", fake)
            finally:
                domain_session.DOMAIN_STEPS_MAX = saved
            job = last_job()
            assert job["status"] == "stopped" and len(job["steps"]) == 2, (job["status"], len(job["steps"]))

        # ------------------------------------------------------------ 確認關卡
        def t_guard():
            fake = FakeChat(main=[task("重新啟動 cam_driver 容器", ["重新啟動了沒"]), say("沒有重新啟動。")],
                            session=[ds("domains", domains=["robotics_infra"]), ds("skill", skill="docker_ctl", args="restart cam_driver"),
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
                            session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="view_file", args="logs/big.log")])
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
                session=[ds("domains", domains=["repo_analysis"]), ds("skill", skill="search_text", args='"def alpha" pkg'),
                         ds("report", answers=[(1, "answered", "定義在 pkg/mod.py 第 1 行（def alpha）", ["pkg/mod.py:1"])], reply="找到了")])
            events, _ = turn("alpha 定義在哪", fake)
            mains = [c for c in fake.calls if c["role"] == "main"]
            assert "沒有通過核對" in mains[2]["messages"][-1]["content"], "出處不在報告：交回修一次"
            assert "⚠️" not in final_reply(events), final_reply(events)

        for name, fn in [("主 session：交辦一節、索引、回覆的 schema 與解析", t_prompt_schema),
                         ("回覆的欄位順序（主 session 的 action 最後；領域 session 照說明的順序）", t_reply_order), ("擋領域的工具與有骨架的技能", t_gate),
                         ("交辦的核對", t_task_checks), ("領域 session 用工具：選領域、技能清單、結果、回報、主 session 照項目回答", t_tool_flow),
                         ("評測的紀錄（domain_calls）", t_tool_records),
                         ("有骨架的技能：合約、執行、一模一樣的不執行", t_composite),
                         ("參數寫錯欄位：有骨架的技能寫在 args、工具寫在 params", t_wrong_field), ("回退換技能", t_composite_switch),
                         ("路徑有好幾個交回決定、0 筆照實交回", t_composite_need_and_empty), ("狀態與上限", t_states_limits),
                         ("確認關卡", t_guard), ("長的結果照舊提煉", t_long_output), ("再交辦帶著上一次的經過", t_previous),
                         ("主 session 依報告回答的核對", t_main_check)]:
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
