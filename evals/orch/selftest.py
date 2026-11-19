"""新架構的高階（agent_core/orchestrator.py，D10 第 4 步的 4-1）的離線自我測試：假的主模型與中階的模型照劇本回，真的中階、低階與工具
（工作目錄是臨時的小專案），直接驅動 Web 的回合（web_app.flows.run_turn）與 CLI（agent_core.cli.main），幾秒跑完、不需要 Ollama。

- 領域（skills_system/DOMAIN.md）：system prompt 的「領域」一節、技能索引拿掉領域的工具、回覆的 schema 多「交給領域」；沒有 DOMAIN.md 時照舊；
- 擋領域的工具（技能名稱、腳本、規格）；共用的工具（回顧存檔、列目錄、找檔案）與其他技能照舊；
- 交給領域 → 中階 → 報告存成 #編號 交回主模型（不提煉）；決策圖的連結先推給畫面；find_lines 的報告（提到的行）照「檔案:行號」寫出處；
- 核對：沒有的領域、子目標是空的、項目數、一樣的再交一次；
- 依報告回答（4-2）：有報告時回覆的 schema 多 answers；每一項的核對（少一項、出處不在報告、數字與名稱不在出處那幾段、查不到沒寫原因、
  寫法看不懂）沒過的交回修一次，還是沒過的標出來；使用者看到的回答由程式照項目排、附出處那一行的原文（Web、CLI）；
- 帶著上一次的經過再交（4-2）：之前沒做完或項目重複的，經過交給中階（挑技能、合約看得到）、幾次串在一起（決策圖的上一次、下一次）；
  一樣的技能與參數先交回合約修一次、還是一樣就停（repeated）；同一個項目最多交 3 次；
- 中階沒有做完、也沒有報告（沒有適合的做法、失敗、不屬於這個領域、取消）：這一回合放行領域的工具，下一回合又擋；
  不屬於這個領域：排除，再交時附這一回合做過的事；
- 問使用者：Web（停下來、問題、回答不合法再問、回答之後接回同一個工作、取消；經過 HTTP 的 /api/send 與 /api/decision）、
  CLI（輸入回答、0 取消）、/clear 取消；
- 評測的 worker 怎麼記（evals/domain_calls.py）。

    python3 evals/orch/selftest.py
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
HIDDEN = ("search_text", "view_file", "code_ast_reader")     # 領域讀內容的工具：主對話不直接用
SHARED = ("list_dir", "find_file", "result_list", "result_grep", "result_view")   # 共用的工具（DOMAIN.md）
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

        def last_report(messages):
            return next(m["content"] for m in reversed(messages) if m["role"] == "user" and DOMAIN_RESULT_HEAD in m["content"])

        def items_of(messages):
            """最後一份報告後面列的「這一回合要回答的項目」。"""
            block = last_report(messages).split("這一回合要回答的項目（answers 照這個編號）：", 1)[1]
            return [ln.split(". ", 1)[1] for ln in block.strip().split("\n") if re.match(r"^\d+\. ", ln)]

        def answer(reply, rows):
            """依報告回答的回覆：rows＝[(項目編號, status, text, refs)]。"""
            return {"thought": "依報告回答", "reply": reply, "action": None,
                    "answers": [{"item": k, "status": st, "text": t, "refs": list(refs)} for k, st, t, refs in rows]}

        def cite(messages):
            """依報告回答：每一項都引用報告裡的第一個出處（檔案:行號）。"""
            ref = _REF.findall(last_report(messages))[0]
            return answer(f"alpha 定義在 {ref}。", [(k, "answered", f"見 {ref}", [ref]) for k in range(1, len(items_of(messages)) + 1)])

        def chats(events):
            return [e["text"] for e in events if e["channel"] == "chat" and e.get("role") == "assistant"]

        def t_registry():
            sp = agent.get_system_prompt()
            assert "## Domains" in sp and "### repo_analysis：" in sp and "- py_usage — " in sp and "- config_trace — " in sp, sp[:200]
            skills = sp[sp.index("## Available Skills"):]
            assert not [t for t in HIDDEN if f"[{t}]" in skills], "領域的工具不列在主對話的技能索引"
            assert all(f"[{t}]" in skills for t in SHARED + ("change_dir", "file_ops")), "共用的工具（列目錄、找檔案、回顧存檔）與其他技能照舊"
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
            fake = FakeChat(main=[step("search_text"), step("scripts/grep_cmd.py", "alpha ."), step("view_file.md"), step("scripts/cat_cmd.py", "pkg/mod.py"),
                                  step("change_dir"), step("result_list"), step("list_dir"), step("scripts/ls_cmd.py", "pkg"), step("find_file"),
                                  step("scripts/find_file_cmd.py", "mod.py ."), say("好")])
            events, _ = turn("找 alpha", fake)
            tools = tools_of(events)
            assert tools[0].startswith("[ERROR] search_text 是 repo_analysis 領域的工具") and "交給領域" in tools[0], tools[0]
            assert tools[1].startswith("[ERROR] search_text 是 repo_analysis 領域的工具"), "腳本對回技能一樣擋"
            assert tools[2].startswith("[ERROR] view_file 是 repo_analysis 領域的工具") and tools[3].startswith("[ERROR] view_file 是"), "規格也不給"
            assert tools[4].startswith(SKILL_DOC_PREFIX) and tools[5].startswith(SKILL_DOC_PREFIX), "其他技能、共用的工具照舊載入規格"
            assert tools[6].startswith(SKILL_DOC_PREFIX) and tools[7].startswith("[PASS]") and "mod.py" in tools[7], "列目錄是共用的工具：直接用"
            assert tools[8].startswith(SKILL_DOC_PREFIX) and tools[9].startswith("[PASS]") and "pkg/mod.py" in tools[9], tools[8:10]

        def t_dispatch_report():
            fake = FakeChat(main=[dispatch("在 pkg 的 .py 裡找 alpha 定義在哪、哪裡呼叫", ["alpha 定義在哪個檔案", "哪些地方呼叫 alpha"]), cite],
                            select=[SEL_PY], contract=[con_py()])
            events, awaiting = turn("pkg 裡的 alpha 定義在哪、哪些地方呼叫它？", fake)
            assert not awaiting
            text = tools_of(events)[0]
            assert text.startswith(DOMAIN_RESULT_HEAD + "repo_analysis 的報告（做完；做法 py_usage）"), text[:200]
            assert "pkg/mod.py:1" in text and "- 要回答的項目 2：哪些地方呼叫 alpha" in text and "依這份報告回答使用者" in text, text
            assert "這一回合要回答的項目（answers 照這個編號）：\n1. alpha 定義在哪個檔案\n2. 哪些地方呼叫 alpha" in text, "報告後面列這一回合的項目"
            links = [e["text"] for e in events if e["channel"] == "progress" and e["text"].startswith("🔗 決策圖：/topology?src=logs&ref=mid_jobs/")]
            assert links, "決策圖的連結先推給畫面"
            jid = links[0].rsplit("/", 1)[1]
            job = mid_job(jid)
            assert job["status"] == "done" and job["items"] == ["alpha 定義在哪個檔案", "哪些地方呼叫 alpha"] and job["question"].startswith("pkg 裡的 alpha")
            assert job["attempt"] == 1 and job["previous"] == [], "第一次交：沒有上一次的經過"
            rec = agent.trajectory[-1]
            assert rec["script"] == "domain_repo_analysis" and rec["result_file"], "結果存成 #編號"
            fed = next(m["content"] for m in agent.messages if m["role"] == "user" and DOMAIN_RESULT_HEAD in m["content"] and "做法 py_usage" in m["content"])
            assert "pkg/mod.py:1" in fed, "報告原文進主對話（不提煉）"
            assert fake.count("main") == 2 and fake.count("select") == 1 and fake.count("contract") == 1, fake.calls
            assert not any("【系統核對】" in m["content"] for m in agent.messages if m["role"] == "user"), "出處在報告裡：不提醒"
            shown = chats(events)
            assert len(shown) == 2 and shown[0] == "交給領域查。", "依報告回答的那一則只顯示照項目排好的版本"
            for want in ("alpha 定義在 pkg/mod.py:1。", "1. alpha 定義在哪個檔案：見 pkg/mod.py:1（出處：pkg/mod.py:1）",
                         "   > pkg/mod.py:1　def alpha，行 1-2", "2. 哪些地方呼叫 alpha：", "🔗 決策圖：/topology?src=logs&ref=mid_jobs/"):
                assert want in shown[1], (want, shown[1])

        def t_answers_schema():
            fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha", ["alpha 定義在哪", "誰呼叫"]), cite], select=[SEL_PY], contract=[con_py()])
            turn("pkg 裡的 alpha 定義在哪、誰呼叫？", fake)
            fmts = [c["format"] for c in fake.calls if c["role"] == "main"]
            assert "answers" not in fmts[0]["properties"], "還沒有報告：沒有 answers"
            ans = fmts[1]["properties"]["answers"]
            assert "answers" in fmts[1]["required"] and ans["items"]["properties"]["item"]["enum"] == [1, 2], ans
            assert list(fmts[1]["properties"]) == ["thought", "reply", "action", "answers"], "先決定動作，再寫每一項的回答"
            assert agent.domain_items() == ["alpha 定義在哪", "誰呼叫"]
            agent.set_current_task("下一個問題")
            assert agent.domain_items() == [], "新的問題：項目歸零"

        def t_find_lines_cite():
            def ans(messages):
                return answer("找到了。", [(1, "answered", "docs/guide.md 第 5 行", ["docs/guide.md:5（提到）：啟動前先檢查電源。"]),
                                         (2, "answered", "啟動前先檢查電源", ["docs/guide.md:5"])])
            fake = FakeChat(main=[dispatch("在 docs 的文件裡找「電源」，列出提到的行", ["哪一行提到電源", "那一行寫什麼"]), ans],
                            select=[select("find_lines", "列出提到的行", asks=("位置", "內容"))],
                            contract=[{"understanding": "u", "keyword": {"quote": "電源", "value": "電源"}, "files": {"quote": "", "value": ""},
                                       "path": {"quote": "docs", "value": "docs"}, "exclude": {"quote": "", "value": ""}}])
            before = len(agent.messages)
            events, _ = turn("docs 的文件裡哪一行提到電源？寫了什麼？", fake)
            text = tools_of(events)[0]
            assert text.startswith(DOMAIN_RESULT_HEAD + "repo_analysis 的報告（做完；做法 find_lines）"), text[:200]
            assert "    - docs/guide.md:5（提到）：啟動前先檢查電源。" in text and "    - docs/guide.md:3：## 啟動" in text, text
            assert not any("【系統核對】" in m["content"] for m in agent.messages[before:] if m["role"] == "user"), "照報告的「檔案:行號」寫出處：通過核對"
            shown = chats(events)[-1]
            assert "2. 那一行寫什麼：啟動前先檢查電源（出處：docs/guide.md:5）\n   > docs/guide.md:5（提到）：啟動前先檢查電源。" in shown, shown
            assert "1. 哪一行提到電源：docs/guide.md 第 5 行（出處：docs/guide.md:5）" in shown, "refs 抄了整行：顯示只留 檔案:行號"

        def t_answers_fix():
            # 第一次的 answers：第 1 項出處不在報告、第 2 項數字不在出處那幾段、第 3 項查不到沒寫原因、第 4 項少了、第 5 項出處寫法看不懂；
            # 交回修一次（只列沒過的），修好之後照項目排
            items = ["alpha 定義在哪", "呼叫幾次", "beta 在哪", "gamma 在哪", "誰 import"]
            bad = answer("pkg/zzz.py:7 有寫。", [(1, "answered", "在 pkg/mod.py", ["pkg/zzz.py:99"]), (2, "answered", "總共 37 次", ["pkg/use.py:5"]),
                                              (3, "not_found", "", []), (5, "answered", "use.py", ["use.py 那一行"])])
            fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha", items), bad, cite], select=[SEL_PY], contract=[con_py()])
            events, _ = turn("pkg 裡的 alpha 定義在哪、呼叫幾次？", fake)
            nudges = [m["content"] for m in agent.messages if m["role"] == "user" and m["content"].startswith("【系統核對】")]
            assert len(nudges) == 1, nudges
            n = nudges[0]
            for want in ("- 第 1 項（alpha 定義在哪）：出處 pkg/zzz.py:99 不在這一回合的報告與工具結果裡", "- 第 2 項（呼叫幾次）：「37、共 37」在出處的那幾段裡找不到",
                         "- 第 3 項（beta 在哪）：查不到（not_found）要寫原因", "- 第 4 項（gamma 在哪）：沒有回答（answers 少了這一項）",
                         "- 第 5 項（誰 import）：出處 use.py 那一行 的寫法看不懂", "- reply：寫了報告裡沒有的出處 pkg/zzz.py:7"):
                assert want in n, (want, n)
            assert fake.count("main") == 3 and "🔎 回答沒有通過程式的核對，交回 AI 修一次。" in [e["text"] for e in events if e["channel"] == "system"]
            assert len(chats(events)) == 2 and "⚠️" not in chats(events)[-1], "修好之後只顯示照項目排好的回答"
            assert agent.domain_reply_check(bad) is None, "每回合最多交回一次"
            assert agent._cited("lib/mod.py:1")[0] == "line" and agent._cited("lib/mod.py:1")[1][0].startswith("pkg/mod.py:1"), \
                "目錄寫錯、檔名與行號在報告裡只對到一個檔案：算同一個出處（原文用報告的完整路徑）"
            assert agent._cited("pkg/nope.py:1")[0] == "unknown" and agent._cited("od.py:1")[0] == "unknown"
            probs = agent._answer_problems(answer("", [(1, "answered", "定義在 pkg/mdo.py", ["pkg/mod.py:1"])]))
            assert probs[1] == ["「pkg/mdo.py」在出處的那幾段裡找不到（那幾段裡相近的寫法：pkg/mod.py）"], probs[1]

        def t_answers_fail_twice():
            bad = answer("見報告。", [(1, "answered", "在 pkg/zzz.py", ["pkg/zzz.py:99"])])
            fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha", ["alpha 定義在哪"]), bad, bad], select=[SEL_PY], contract=[con_py()])
            events, _ = turn("pkg 裡的 alpha 定義在哪？", fake)
            shown = chats(events)[-1]
            assert "1. alpha 定義在哪：在 pkg/zzz.py（出處：pkg/zzz.py:99）" in shown and "⚠️ 沒有通過核對：出處 pkg/zzz.py:99 不在這一回合的報告與工具結果裡（報告：#" in shown, shown
            assert fake.count("main") == 3, "交回一次之後還是沒過：照樣結束，標出來"

        def t_answers_own_results():
            # 放行之後主對話自己查的也算出處：view_file 的收據裡有的 檔案:行號（原文由程式從檔案讀）、這一回合存檔的 #編號（共用的列目錄）
            def ans(messages):
                return answer("見下面。", [(1, "answered", "alpha 回傳 x + 1，pkg 裡有 mod.py", ["pkg/mod.py:2", f"#{agent.last_result_id}"])])
            fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha", ["alpha 回傳什麼"]), dispatch("看 pkg/mod.py 的內容", ["mod.py 第 2 行寫什麼"]),
                                  step("view_file"), step("scripts/cat_cmd.py", "pkg/mod.py"), step("scripts/ls_cmd.py", "pkg"), ans],
                            select=[SEL_PY, select("none", "沒有看檔案的做法")], contract=[con_py()])
            before = len(agent.messages)
            events, _ = turn("pkg 裡的 alpha 回傳什麼？", fake)
            nudges = [m["content"] for m in agent.messages[before:] if m["role"] == "user" and m["content"].startswith("【系統核對】")]
            assert not nudges, ("自己查的工具結果也算出處", nudges)
            shown = chats(events)[-1]
            assert "1. alpha 回傳什麼：alpha 回傳 x + 1，pkg 裡有 mod.py（出處：pkg/mod.py:2、#" in shown and "   > pkg/mod.py:2：return x + 1" in shown, shown
            assert agent._cited("pkg/mod.py:9")[0] == "unknown", "收據裡沒有的行（檔案只有 2 行）不算"

        def t_redispatch_previous():
            # 第 1 次沒有適合的做法 → 同一個項目再交：中階的挑技能與合約看得到上一次的經過；兩次串起來（決策圖的上一次、下一次）
            from web_app import topology
            fake = FakeChat(main=[dispatch("看 pkg 的 alpha", ["alpha 定義在哪"]), dispatch("在 pkg 的 .py 裡找 alpha 的定義", ["alpha 定義在哪"]), cite],
                            select=[select("none", "沒有看檔案的做法"), SEL_PY], contract=[con_py()])
            events, _ = turn("pkg 裡的 alpha 定義在哪？", fake)
            first, second = [x for x in agent._domain_turn["dispatches"]]
            assert first["status"] == "no_skill" and second["status"] == "done" and second["n"] == 2 and second["previous"] == [first["job"]]
            sel2 = [c for c in fake.calls if c["role"] == "select"][1]
            job2 = mid_job(second["job"])
            assert job2["attempt"] == 2 and job2["previous"][0]["job"] == first["job"] and job2["previous"][0]["status"] == "no_skill", job2["previous"]
            assert mid_job(first["job"])["next"] == [{"job": second["job"], "n": 2}], "上一次的工作記下這一次"
            calls = open(os.path.join(tmp, "logs", "mid_jobs", second["job"], "calls.jsonl"), encoding="utf-8").read()
            assert calls.count("【上一次的經過】同一個問題之前交給這個領域 1 次") == 2 and "第 1 次：做法 —" in calls and "沒有看檔案的做法" in calls, "挑技能與合約都看得到"
            assert "第 2 次交給這個領域（之前：第 1 次 —：這個領域沒有適合的複合技能）" in job2["result"]["report"]
            v2 = topology.job_view("logs", f"mid_jobs/{second['job']}", root=tmp)
            v1 = topology.job_view("logs", f"mid_jobs/{first['job']}", root=tmp)
            assert v2["chain"]["attempt"] == 2 and v2["chain"]["previous"][0]["ref"] == f"mid_jobs/{first['job']}", v2["chain"]
            assert v1["chain"]["next"] == [{"ref": f"mid_jobs/{second['job']}", "n": 2}], v1["chain"]
            assert sel2 is not None

        def t_repeated():
            # 第 2 次挑一樣的技能、合約也一樣：先交回合約修一次（附原因），還是一樣就停（repeated），照報告回答
            fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha", ["alpha 定義在哪"]), dispatch("再找一次 pkg 的 alpha", ["alpha 定義在哪"]), cite],
                            select=[SEL_PY, SEL_PY], contract=[con_py(), con_py(), con_py()])
            events, _ = turn("pkg 裡的 alpha 定義在哪？", fake)
            first, second = agent._domain_turn["dispatches"]
            assert first["status"] == "done" and second["status"] == "repeated", (first["status"], second["status"])
            job2 = mid_job(second["job"])
            assert job2["same_as"]["n"] == 1 and job2["same_as"]["still"] and job2["graphs"] == [], job2["same_as"]
            assert fake.count("contract") == 3, "第 2 次的合約交回修一次"
            calls = open(os.path.join(tmp, "logs", "mid_jobs", second["job"], "calls.jsonl"), encoding="utf-8").read()
            assert "這次的參數跟第 1 次一模一樣（做法 py_usage；name＝alpha；path＝pkg" in calls, "交回修時附原因"
            text = tools_of(events)[1]
            assert "repo_analysis 的報告（跟之前的某一次一樣" in text and "跟第 1 次一樣（做法 py_usage" in text, text[:400]
            assert agent.domain_gate("search_text"), "有報告（跟之前一樣也算）：照舊擋"

        def t_item_tries():
            # 同一個項目最多交 3 次（G5）：第 4 次程式擋下來（不執行中階）
            same = ["alpha 定義在哪"]
            fake = FakeChat(main=[dispatch("找 alpha（1）", same), dispatch("找 alpha（2）", same), dispatch("找 alpha（3）", same),
                                  dispatch("找 alpha（4）", same), say("查不到。")],
                            select=[select("none", "沒有做法"), select("none", "沒有做法"), select("none", "沒有做法")])
            events, _ = turn("pkg 裡的 alpha 定義在哪？", fake)
            tools = tools_of(events)
            assert tools[3].startswith("[ERROR] 「alpha 定義在哪」這個問題已經交給 repo_analysis 3 次（同一個項目最多 3 次）"), tools[3]
            assert fake.count("select") == 3, "第 4 次不執行中階"

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
            fake = FakeChat(main=[dispatch("比較 pkg/mod.py 與 pkg/use.py", ["兩個檔案差在哪"]), step("view_file"), step("scripts/cat_cmd.py", "pkg/mod.py"),
                                  say("mod.py 定義 alpha")], select=[select("none", "沒有比較兩個檔案的做法")])
            events, _ = turn("pkg/mod.py 跟 pkg/use.py 差在哪？", fake)
            tools = tools_of(events)
            assert "沒有適合的寫好的做法：沒有比較兩個檔案的做法" in tools[0] and "- [view_file](tools/view_file.md)" in tools[0], tools[0]
            assert "[list_dir]" not in tools[0], "放行時只列被擋的工具（共用的本來就能用）"
            assert tools[1].startswith(SKILL_DOC_PREFIX) and tools[2].startswith("[PASS]") and "def alpha" in tools[2], tools[1:3]
            events, _ = turn("再看一次 pkg/mod.py", FakeChat(main=[step("scripts/cat_cmd.py", "pkg/mod.py"), say("好")]))
            assert tools_of(events)[0].startswith("[ERROR] view_file 是 repo_analysis 領域的工具"), "放行只在那一回合"

        def t_out_of_domain():
            fake = FakeChat(main=[dispatch("看 cam_box 容器在不在跑", ["cam_box 現在的狀態"]), dispatch("再找一次 cam_box", ["狀態"]),
                                  step("scripts/cat_cmd.py", "pkg/mod.py"), say("不屬於。")],
                            select=[select("out_of_domain", "問的是正在跑的容器", asks=("內容",))])
            events, _ = turn("cam_box 容器現在在跑嗎？", fake)
            tools = tools_of(events)
            assert "repo_analysis 說這個問題不屬於它：問的是正在跑的容器" in tools[0] and "- [view_file](tools/view_file.md)" in tools[0], tools[0]
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
            # 依報告回答：answers 與核對的結果記進那一步；最後的回覆換成程式照項目排好的那一份
            ollama.chat = FakeChat(select=[SEL_PY], contract=[con_py()])
            agent.set_current_task("pkg 裡的 alpha 定義在哪？")
            agent.run_tool({"action": dispatch("在 pkg 裡找 alpha", ["alpha 定義在哪"])["action"]})
            bad = agent.parse_reply(json.dumps(answer("見報告。", [(1, "answered", "x", ["pkg/zzz.py:9"])]), ensure_ascii=False))
            t = {"steps": [{"reply": bad["reply"]}]}
            domain_calls.record_answers(agent, bad, t)
            assert t["steps"][-1]["answers"][0]["refs"] == ["pkg/zzz.py:9"] and "不在這一回合的報告與工具結果裡" in t["steps"][-1]["answer_problems"]["1"][0], t
            good = agent.parse_reply(json.dumps(answer("在 pkg/mod.py:1。", [(1, "answered", "pkg/mod.py", ["pkg/mod.py:1"])]), ensure_ascii=False))
            t = {"steps": [{"reply": good["reply"]}]}
            rendered = domain_calls.finalize(agent, good, t)
            assert rendered and t["steps"][-1]["reply"] == rendered and "1. alpha 定義在哪：pkg/mod.py（出處：pkg/mod.py:1）" in rendered, rendered
            assert domain_calls.finalize(agent, dict(good, action={"command": "x", "args": ""}), t) is None, "還有動作：不換"

        for name, fn in [("領域：system prompt 的「領域」一節、技能索引拿掉領域的工具、schema 多「交給領域」；沒有 DOMAIN.md 時照舊", t_registry),
                         ("擋領域的工具：技能名稱、腳本、規格都擋，其他技能與共用的工具（列目錄、找檔案、回顧存檔）照舊", t_gate),
                         ("交給領域 → 中階 → 報告存成 #編號 交回主模型（不提煉），決策圖的連結先推給畫面；使用者看到照項目排好的回答", t_dispatch_report),
                         ("依報告回答的 schema：有報告時多 answers（項目的編號、先寫動作再寫回答），新的問題歸零", t_answers_schema),
                         ("find_lines 的報告列出提到的行（檔案:行號：內容），主模型照它寫的出處通過核對、回答附那一行的原文", t_find_lines_cite),
                         ("answers 的核對：出處不在報告、數字不在出處那幾段、查不到沒寫原因、少一項、寫法看不懂、reply 的出處；只把沒過的交回修一次",
                          t_answers_fix),
                         ("answers 修過一次還是沒過：照樣結束，那一項標「沒有通過核對」附報告的 #編號", t_answers_fail_twice),
                         ("放行之後自己查的也算出處：收據裡有的 檔案:行號（原文從檔案讀）、這一回合存檔的 #編號", t_answers_own_results),
                         ("帶著上一次的經過再交：挑技能與合約看得到、第幾次、兩次串起來（決策圖的上一次、下一次）", t_redispatch_previous),
                         ("一樣的技能與參數：合約交回修一次，還是一樣就停（跟之前一樣），照報告回答、照舊擋", t_repeated),
                         ("同一個項目最多交 3 次：第 4 次程式擋下來", t_item_tries),
                         ("核對：沒有的領域、子目標是空的、項目數、一樣的再交一次", t_validation),
                         ("沒有適合的做法：這一回合放行領域的工具，下一回合又擋", t_no_skill_unlock),
                         ("不屬於這個領域：排除，再交時附這一回合做過的事；這一回合照現在的方式做（放行領域的工具）", t_out_of_domain),
                         ("問使用者（Web）：停下來、回答不合法再問、回答之後接回同一個工作", t_ask_web),
                         ("問使用者：取消（這一回合放行領域的工具）、/clear 一起取消", t_ask_cancel),
                         ("問使用者（CLI）：輸入回答、0 取消", t_cli),
                         ("問使用者（經過 Web 伺服器）：/api/send 打字回答、/api/decision 取消、有問題時斜線指令被擋", t_http),
                         ("評測的 worker 怎麼記：領域與領域裡用到的工具、沒人回答就取消、依報告回答的 answers 與照項目排好的回覆", t_worker_record)]:
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
