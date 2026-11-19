"""新架構的高階（agent_core/orchestrator.py，D10 第 4 步的 4-1）的離線自我測試：假的主模型與中階的模型照劇本回，真的中階、低階與工具
（工作目錄是臨時的小專案），直接驅動 Web 的回合（web_app.flows.run_turn）與 CLI（agent_core.cli.main），幾秒跑完、不需要 Ollama。

- 領域（skills_system/DOMAIN.md）：system prompt 的「領域」一節、技能索引拿掉領域的工具、回覆的 schema 多「交給領域」；沒有 DOMAIN.md 時照舊；
- 擋領域的工具（技能名稱、腳本、規格）；共用的工具與其他技能照舊；
- 交給領域 → 中階 → 報告存成 #編號 交回主模型（不提煉）；決策圖的連結先推給畫面；
- 核對：沒有的領域、子目標是空的、項目數、一樣的再交一次；
- 依報告回答：出處不在報告裡提醒一次；
- 中階沒有做完、也沒有報告（沒有適合的做法、失敗、不屬於這個領域、取消）：這一回合放行領域的工具，下一回合又擋；
  不屬於這個領域：排除，再交時附這一回合做過的事；
- 問使用者：Web（停下來、問題、回答不合法再問、回答之後接回同一個工作、取消；經過 HTTP 的 /api/send 與 /api/decision）、
  CLI（輸入回答、0 取消）、/clear 取消；
- 評測的 worker 怎麼記（evals/domain_calls.py）。

    python3 evals/orch/selftest.py
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts", "web_app", "vision"]
FIVE = ("search_text", "find_file", "list_dir", "view_file", "code_ast_reader")
FILES = {
    "pkg/mod.py": "def alpha(x):\n    return x + 1\n\n\ndef beta():\n    return alpha(2)\n",
    "pkg/use.py": "from pkg.mod import alpha\n\n\ndef gamma():\n    return alpha(3)\n",
    "docs/guide.md": "# 指南\n\n## 啟動\n\n啟動前先檢查電源。\n",
}
SEL_PY = {"understanding": "找一個名稱定義在哪、誰呼叫", "asks": ["位置"], "skill": "py_usage", "reason": "Python 名稱的定義與呼叫"}


def con_py(name="alpha", path="pkg"):
    return {"understanding": "名稱與範圍", "name": {"quote": name, "value": name}, "path": {"quote": path, "value": path},
            "exclude": {"quote": "", "value": ""}}


def select(skill, reason="理由", asks=("位置",)):
    return {"understanding": "理解", "asks": list(asks), "skill": skill, "reason": reason}


def dispatch(goal, items, domain="repo_analysis"):
    return {"thought": "交給領域", "reply": "交給領域查。", "action": {"domain": domain, "goal": goal, "items": items}}


def step(cmd, args=""):
    return {"thought": "照做", "reply": "執行中", "action": {"command": cmd, "args": args}}


def say(reply):
    return {"thought": "回覆", "reply": reply, "action": None}


class FakeChat:
    """假的 ollama.chat：照 format 的欄位分角色（主模型、挑技能、合約、判斷），各自依序取劇本；主模型的一則可以是函式（看對話決定回什麼）。"""

    def __init__(self, main=(), select=(), contract=(), judge=()):
        self.q = {"main": list(main), "select": list(select), "contract": list(contract), "judge": list(judge)}
        self.calls = []

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = set((format or {}).get("properties", {})) if isinstance(format, dict) else set()
        role = ("main" if "action" in props else "select" if "asks" in props else "judge" if props & {"lines", "branch"}
                else "contract" if "understanding" in props else "other")
        self.calls.append({"role": role, "format": format})
        if role == "other":
            data = {"answer": "（摘要）", "facts": [], "errors": [], "not_covered": "無", "suggested_questions": [], "index_hint": "（摘要）",
                    "related_records": [], "overview": "（摘要）", "key_progress": [], "results_and_errors": [], "user_preferences": [],
                    "open_items": [], "relevant": False, "summary": ""}
        else:
            q = self.q[role]
            item = q.pop(0) if q else ({"thought": "", "reply": "好的。", "action": None} if role == "main" else None)
            data = item(messages) if callable(item) else item
        return {"message": {"content": json.dumps(data, ensure_ascii=False) if data is not None else ""},
                "prompt_eval_count": 100, "eval_count": 20}

    def count(self, role):
        return sum(1 for c in self.calls if c["role"] == role)


def make_env():
    tmp = tempfile.mkdtemp(prefix="orch_selftest_")
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
        from agent_core.config import DOMAIN_RESULT_HEAD, SKILL_DOC_PREFIX
        from agent_core.orchestrator import _REF
        from agent_core.schemas import agent_reply_schema
        from web_app import flows
        from web_app.commands import handle_slash_command
        from web_app.state import agent, pending, state
        agent.current_cwd = tmp
        state["auto_mode"] = True

        def turn(user, fake):
            ollama.chat = fake
            agent.set_current_task(user)
            agent.messages.append({"role": "user", "content": user})
            events = []
            agent.progress_callback = lambda text: events.append({"channel": "progress", "text": text})   # 同 server.py：進度推到畫面
            try:
                return events, flows.run_turn(events)
            finally:
                agent.progress_callback = None

        def tools_of(events):
            return [e["text"] for e in events if e["channel"] == "tool"]

        def mid_job(jid):
            with open(os.path.join(tmp, "logs", "mid_jobs", jid, "job.json"), encoding="utf-8") as f:
                return json.load(f)

        def cite(messages):
            """依報告回答：引用報告裡的第一個出處（檔案:行號）。"""
            rep = next(m["content"] for m in reversed(messages) if m["role"] == "user" and DOMAIN_RESULT_HEAD in m["content"])
            return say(f"alpha 定義在 {_REF.findall(rep)[0]}。")

        def t_registry():
            sp = agent.get_system_prompt()
            assert "## Domains" in sp and "### repo_analysis：" in sp and "- py_usage — " in sp and "- config_trace — " in sp, sp[:200]
            skills = sp[sp.index("## Available Skills"):]
            assert not [t for t in FIVE if f"[{t}]" in skills], "領域的工具不列在主對話的技能索引"
            assert all(f"[{t}]" in skills for t in ("result_grep", "result_view", "change_dir", "file_ops")), "共用的工具與其他技能照舊"
            act = agent_reply_schema(agent.domain_names())["properties"]["action"]["anyOf"]
            assert act[2]["properties"]["domain"]["enum"] == ["repo_analysis"] and act[2]["properties"]["items"]["maxItems"] == 6, act
            fake = FakeChat(main=[say("你好。")])
            turn("你好", fake)
            fmt = next(c["format"] for c in fake.calls if c["role"] == "main")
            assert len(fmt["properties"]["action"]["anyOf"]) == 3, "主對話送的 schema 有「交給領域」"
            path = os.path.join(tmp, "skills_system", "DOMAIN.md")
            os.rename(path, path + ".off")
            try:
                sp = agent.get_system_prompt()
                assert "## Domains" not in sp and "[search_text]" in sp, "沒有 DOMAIN.md：照舊（沒有領域、工具照列）"
                assert agent.domain_gate("search_text") is None and len(agent_reply_schema(agent.domain_names())["properties"]["action"]["anyOf"]) == 2
            finally:
                os.rename(path + ".off", path)
            assert "## Domains" in agent.get_system_prompt(), "檔案改回來就重讀"

        def t_gate():
            fake = FakeChat(main=[step("search_text"), step("scripts/grep_cmd.py", "alpha ."), step("view_file.md"),
                                  step("change_dir"), step("result_list"), say("好")])
            events, _ = turn("找 alpha", fake)
            tools = tools_of(events)
            assert tools[0].startswith("[ERROR] search_text 是 repo_analysis 領域的工具") and "交給領域" in tools[0], tools[0]
            assert tools[1].startswith("[ERROR] search_text 是 repo_analysis 領域的工具"), "腳本對回技能一樣擋"
            assert tools[2].startswith("[ERROR] view_file 是 repo_analysis 領域的工具"), "規格也不給"
            assert tools[3].startswith(SKILL_DOC_PREFIX) and tools[4].startswith(SKILL_DOC_PREFIX), "其他技能、共用的工具照舊載入規格"

        def t_dispatch_report():
            fake = FakeChat(main=[dispatch("在 pkg 的 .py 裡找 alpha 定義在哪、哪裡呼叫", ["alpha 定義在哪個檔案", "哪些地方呼叫 alpha"]), cite],
                            select=[SEL_PY], contract=[con_py()])
            events, awaiting = turn("pkg 裡的 alpha 定義在哪、哪些地方呼叫它？", fake)
            assert not awaiting
            text = tools_of(events)[0]
            assert text.startswith(DOMAIN_RESULT_HEAD + "repo_analysis 的報告（做完；做法 py_usage）"), text[:200]
            assert "pkg/mod.py:1" in text and "- 要回答的項目 2：哪些地方呼叫 alpha" in text and "依這份報告回答使用者" in text, text
            links = [e["text"] for e in events if e["channel"] == "progress" and e["text"].startswith("🔗 決策圖：/topology?src=logs&ref=mid_jobs/")]
            assert links, "決策圖的連結先推給畫面"
            jid = links[0].rsplit("/", 1)[1]
            job = mid_job(jid)
            assert job["status"] == "done" and job["items"] == ["alpha 定義在哪個檔案", "哪些地方呼叫 alpha"] and job["question"].startswith("pkg 裡的 alpha")
            rec = agent.trajectory[-1]
            assert rec["script"] == "domain_repo_analysis" and rec["result_file"], "結果存成 #編號"
            fed = next(m["content"] for m in agent.messages if m["role"] == "user" and DOMAIN_RESULT_HEAD in m["content"] and "做法 py_usage" in m["content"])
            assert "pkg/mod.py:1" in fed, "報告原文進主對話（不提煉）"
            assert fake.count("main") == 2 and fake.count("select") == 1 and fake.count("contract") == 1, fake.calls
            assert not any("【系統核對】" in m["content"] for m in agent.messages if m["role"] == "user"), "出處在報告裡：不提醒"

        def t_reply_refs():
            fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha", ["alpha 定義在哪"]), say("alpha 定義在 pkg/zzz.py:99。"), cite],
                            select=[SEL_PY], contract=[con_py()])
            turn("pkg 裡的 alpha 定義在哪？", fake)
            nudges = [m["content"] for m in agent.messages if m["role"] == "user" and m["content"].startswith("【系統核對】")]
            assert nudges and "pkg/zzz.py:99" in nudges[-1], nudges
            assert fake.count("main") == 3, "提醒一次之後重寫"
            assert agent.domain_reply_check({"reply": "還是 pkg/zzz.py:99", "action": None, "valid": True}) is None, "每回合最多提醒一次"

        def t_validation():
            bad = [{"thought": "", "reply": "", "action": {"domain": "nope", "goal": "g", "items": ["a"]}}, dispatch("", ["a"]),
                   dispatch("在 pkg 找", []), dispatch("在 pkg 找", [f"項目{i}" for i in range(7)]),
                   dispatch("列出 pkg 的檔案", ["有哪些檔案"]), dispatch("列出 pkg 的檔案", ["有哪些檔案"]), say("好")]
            fake = FakeChat(main=bad, select=[select("none", "沒有列目錄的做法")])
            events, _ = turn("pkg 有哪些檔案？", fake)
            tools = tools_of(events)
            assert tools[0].startswith("[ERROR] 沒有「nope」這個領域（有的領域：repo_analysis）"), tools[0]
            assert tools[1].startswith("[ERROR] 交給 repo_analysis 時 goal 是空的"), tools[1]
            assert tools[2].startswith("[ERROR] 要回答的項目有 0 項（要 1～6 項）") and tools[3].startswith("[ERROR] 要回答的項目有 7 項"), tools[2:4]
            assert tools[4].startswith(DOMAIN_RESULT_HEAD) and tools[5].startswith("[ERROR] 這個問題已經用一樣的子目標與項目交給過 repo_analysis"), tools[5]
            assert fake.count("select") == 1, "核對沒過的不執行中階、一樣的不再跑一次"

        def t_no_skill_unlock():
            fake = FakeChat(main=[dispatch("列出 pkg 有哪些檔案", ["pkg 底下有哪些檔案"]), step("list_dir"), step("scripts/ls_cmd.py", "pkg"),
                                  say("有 mod.py、use.py")], select=[select("none", "沒有列目錄的做法")])
            events, _ = turn("pkg 底下有哪些檔案？", fake)
            tools = tools_of(events)
            assert "沒有適合的寫好的做法：沒有列目錄的做法" in tools[0] and "- [list_dir](tools/list_dir.md)" in tools[0], tools[0]
            assert tools[1].startswith(SKILL_DOC_PREFIX) and tools[2].startswith("[PASS]") and "mod.py" in tools[2], tools[1:3]
            events, _ = turn("再列一次 pkg", FakeChat(main=[step("scripts/ls_cmd.py", "pkg"), say("好")]))
            assert tools_of(events)[0].startswith("[ERROR] list_dir 是 repo_analysis 領域的工具"), "放行只在那一回合"

        def t_out_of_domain():
            fake = FakeChat(main=[dispatch("看 cam_box 容器在不在跑", ["cam_box 現在的狀態"]), dispatch("再找一次 cam_box", ["狀態"]),
                                  step("scripts/ls_cmd.py", "pkg"), say("不屬於。")],
                            select=[select("out_of_domain", "問的是正在跑的容器", asks=("內容",))])
            events, _ = turn("cam_box 容器現在在跑嗎？", fake)
            tools = tools_of(events)
            assert "repo_analysis 說這個問題不屬於它：問的是正在跑的容器" in tools[0] and "- [list_dir](tools/list_dir.md)" in tools[0], tools[0]
            assert tools[1].startswith("[ERROR] 這個問題已經交給過 repo_analysis，它說不屬於它") and "1. repo_analysis（做法 —）：不屬於這個領域，決策圖 /topology" in tools[1], tools[1]
            assert tools[2].startswith("[PASS]"), "回到主對話照現在的方式做：這一回合放行領域的工具（G7）"

        def ask_turn(fake_main_tail=()):
            fake = FakeChat(main=[dispatch("在 pkgx 裡找 alpha 定義在哪", ["alpha 定義在哪"])] + list(fake_main_tail),
                            select=[SEL_PY], contract=[con_py(path="pkgx")])
            events, awaiting = turn("pkgx 裡的 alpha 定義在哪？", fake)
            return fake, events, awaiting

        def t_ask_web():
            fake, events, awaiting = ask_turn([cite])
            assert awaiting and pending["mode"] == "domain" and agent.domain_pending, (awaiting, pending)
            ask = [e for e in events if e["channel"] == "domain_ask"]
            assert ask and "repo_analysis 要問你：工作目錄底下找不到「pkgx」" in ask[0]["text"] and "/topology?src=logs&ref=mid_jobs/" in ask[0]["text"], ask
            last = agent.messages[-1]["content"]
            assert "停下來要問使用者" in last and "系統已經直接問使用者" in last, "等回答的說明進主對話"
            assert fake.count("main") == 1, "回答之前主模型不再被呼叫"
            ev = []
            assert flows.answer_domain_turn("nowhere", ev) and "剛才的回答不能用" in [e for e in ev if e["channel"] == "domain_ask"][0]["text"]
            jid = agent.domain_pending["job"]
            ev = []
            assert flows.answer_domain_turn("pkg", ev) is False and pending["mode"] is None and agent.domain_pending is None
            text = tools_of(ev)[0]
            assert text.startswith(DOMAIN_RESULT_HEAD + "使用者回答「pkg」之後，repo_analysis 接著做完：repo_analysis 的報告（做完") and "pkg/mod.py:1" in text, text[:300]
            job = mid_job(jid)
            assert job["status"] == "done" and job["asked"][-1]["answer"] == "pkg" and job["asked"][-1]["errors"][0]["answer"] == "nowhere", job["asked"]
            assert fake.count("main") == 2, "接回之後主模型照報告回答"

        def t_ask_cancel():
            fake, events, awaiting = ask_turn([say("沒有做完，缺範圍。")])
            jid = agent.domain_pending["job"]
            ev = []
            assert flows.answer_domain_turn(None, ev, cancel=True) is False and agent.domain_pending is None and pending["mode"] is None
            assert "使用者沒有回答 repo_analysis 的問題（取消了）" in tools_of(ev)[0] and mid_job(jid)["status"] == "cancelled"
            assert "- [view_file](tools/view_file.md)" in tools_of(ev)[0] and agent.domain_gate("scripts/cat_cmd.py") is None, "取消之後這一回合放行"
            fake, events, awaiting = ask_turn()
            jid = agent.domain_pending["job"]
            assert handle_slash_command("/clear", []) and agent.domain_pending is None and pending["mode"] is None, "/clear 一起取消"
            assert mid_job(jid)["status"] == "cancelled"

        def t_cli():
            import builtins
            import contextlib
            import io
            from agent_core import cli
            for lines, want in ((["/auto on", "pkgx 裡的 alpha 定義在哪？", "nowhere", "pkg"], "做完"), (["/auto on", "pkgx 裡的 alpha 定義在哪？", "0"], "取消")):
                asked, buf = [], io.StringIO()

                def fake_input(prompt=""):
                    asked.append(prompt)
                    if not lines:
                        raise KeyboardInterrupt
                    return lines.pop(0)
                main_tail = [cite] if want == "做完" else [say("沒有做完。")]
                ollama.chat = FakeChat(main=[dispatch("在 pkgx 裡找 alpha 定義在哪", ["alpha 定義在哪"])] + main_tail,
                                       select=[SEL_PY], contract=[con_py(path="pkgx")])
                real_input, real_cwd = builtins.input, os.getcwd()
                builtins.input = fake_input
                try:
                    with contextlib.redirect_stdout(buf):
                        cli.main()
                finally:
                    builtins.input = real_input
                    os.chdir(real_cwd)
                out = buf.getvalue()
                assert "repo_analysis 要問你：工作目錄底下找不到「pkgx」" in out and any(p.startswith("回答（輸入編號選候選") for p in asked), out[-1500:]
                if want == "做完":
                    assert "剛才的回答不能用" in out and "使用者回答「pkg」之後" in out and "alpha 定義在 pkg/" in out, out[-2000:]
                else:
                    assert "使用者沒有回答 repo_analysis 的問題（取消了）" in out, out[-2000:]

        def t_http():
            # 經過 Web 伺服器：問題（中階要問 → done 帶 awaiting_decision、pending_mode＝domain）→ 有問題時其他斜線指令被擋 →
            # 打字回答走 /api/send → 再問一次取消走 /api/decision
            import threading
            import urllib.request
            from http.server import ThreadingHTTPServer
            from web_app import server
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ConsoleHandler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"

            def post(path, body):
                req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    lines = [json.loads(x) for x in r.read().decode("utf-8").splitlines() if x.strip()]
                return [x for x in lines if x.get("type") == "done"][-1], [x["event"] for x in lines if x.get("type") == "event"]
            try:
                for how in ("answer", "cancel"):
                    ollama.chat = FakeChat(main=[dispatch("在 pkgx 裡找 alpha 定義在哪", ["alpha 定義在哪"]), cite if how == "answer" else say("取消了。")],
                                           select=[SEL_PY], contract=[con_py(path="pkgx")])
                    done, events = post("/api/send", {"message": "pkgx 裡的 alpha 定義在哪？"})
                    assert done["awaiting_decision"] and done["pending_mode"] == "domain", done
                    assert any(e["channel"] == "domain_ask" for e in events) and any(e["channel"] == "progress" and "🔗 決策圖" in e["text"] for e in events)
                    done, _ = post("/api/send", {"message": "/model"})
                    assert done["awaiting_decision"] and done["pending_mode"] == "domain", "有問題時斜線指令被擋（/clear 除外）"
                    if how == "answer":
                        done, events = post("/api/send", {"message": "pkg"})
                        assert not done["awaiting_decision"] and any(e["channel"] == "tool" and "使用者回答「pkg」之後" in e["text"] for e in events), events
                    else:
                        done, events = post("/api/decision", {"action": "cancel"})
                        assert not done["awaiting_decision"] and any(e["channel"] == "tool" and "（取消了）" in e["text"] for e in events), events
                    assert pending["mode"] is None and agent.domain_pending is None
            finally:
                httpd.shutdown()
                httpd.server_close()

        def t_worker_record():
            from evals import domain_calls
            ollama.chat = FakeChat(select=[SEL_PY], contract=[con_py()])
            agent.set_current_task("pkg 裡的 alpha 定義在哪？")
            parsed = {"action": dispatch("在 pkg 裡找 alpha", ["alpha 定義在哪"])["action"]}
            result = agent.run_tool(parsed)
            calls = domain_calls.calls(agent, parsed, result)
            assert calls[0]["skill"] == "repo_analysis" and calls[0]["mid_status"] == "done" and calls[0]["mid_skill"] == "py_usage", calls[0]
            via = {c["skill"] for c in calls[1:] if c.get("via") == "repo_analysis"}
            assert via == {"search_text", "code_ast_reader"}, calls
            assert domain_calls.calls(agent, {"action": {"domain": "nope", "goal": "g", "items": []}}, "[ERROR] x")[0]["status"] == "ERROR"
            ollama.chat = FakeChat(select=[SEL_PY], contract=[con_py(path="pkgx")])
            agent.set_current_task("pkgx 裡的 alpha 定義在哪？")
            parsed = {"action": dispatch("在 pkgx 裡找 alpha", ["alpha 定義在哪"])["action"]}
            t = {}
            result = domain_calls.settle(agent, parsed, agent.run_tool(parsed), t)
            assert agent.domain_pending is None and t["domain_asks"] and "取消了" in result, (t, result[:200])

        for name, fn in [("領域：system prompt 的「領域」一節、技能索引拿掉領域的工具、schema 多「交給領域」；沒有 DOMAIN.md 時照舊", t_registry),
                         ("擋領域的工具：技能名稱、腳本、規格都擋，其他技能與共用的工具照舊", t_gate),
                         ("交給領域 → 中階 → 報告存成 #編號 交回主模型（不提煉），決策圖的連結先推給畫面", t_dispatch_report),
                         ("依報告回答：出處不在報告裡提醒一次", t_reply_refs),
                         ("核對：沒有的領域、子目標是空的、項目數、一樣的再交一次", t_validation),
                         ("沒有適合的做法：這一回合放行領域的工具，下一回合又擋", t_no_skill_unlock),
                         ("不屬於這個領域：排除，再交時附這一回合做過的事；這一回合照現在的方式做（放行領域的工具）", t_out_of_domain),
                         ("問使用者（Web）：停下來、回答不合法再問、回答之後接回同一個工作", t_ask_web),
                         ("問使用者：取消（這一回合放行領域的工具）、/clear 一起取消", t_ask_cancel),
                         ("問使用者（CLI）：輸入回答、0 取消", t_cli),
                         ("問使用者（經過 Web 伺服器）：/api/send 打字回答、/api/decision 取消、有問題時斜線指令被擋", t_http),
                         ("評測的 worker 怎麼記：領域與領域裡用到的工具、沒人回答就取消", t_worker_record)]:
            check(name, fn)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
