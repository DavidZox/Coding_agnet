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
- 中階沒有做完、也沒有報告（沒有適合的做法、失敗、取消）：接著開子工作階段，用領域的工具一步一步做（第 5 步，取代放行；主對話照舊擋）；
  不屬於這個領域：排除，再交時附這一回合做過的事；
- 子工作階段（第 5 步，agent_core/sub.py）：沒有複合技能的領域直接開；自己的對話（主對話看不到試錯）、只能用領域的工具、確認關卡停下來與接回
  （同意、不同意、取消）、步數用完、卡住、收尾的核對（出處是自己的工具結果、修一次）、報告、決策圖；回覆的協議（5-1 的評測之後）：
  沒有動作也沒有回答提醒一次（不算交回修）、收尾寫成 {"command": "null"}、寫到長度上限被截斷的不執行；
  長輸出照舊提煉，結尾的下一步建議只寫它能用的 result_grep、result_view（待辦 4k ①）；
- 凍結的四個領域（第 5 步 5-2）：「領域」一節、主對話的索引拿掉它們的工具（工具全部交給領域的那一節連說明都不列）、子工作階段的工具清單
  帶那一節的說明、〈做法〉從 AGENT.md 搬過去、擋與放行；數據分析在子工作階段裡執行（G4）：報告原樣附上、主對話照它核對回答；
- 問使用者：Web（停下來、問題、回答不合法再問、回答之後接回同一個工作、取消；經過 HTTP 的 /api/send 與 /api/decision）、
  CLI（輸入回答、0 取消）、/clear 取消；
- 評測的 worker 怎麼記（evals/domain_calls.py）；
- 回覆的欄位順序（5-3 之後）：action 放最後；
- 查得到的領域（5-4）：子工作階段查不到、不屬於的那一項寫哪個領域查得到（schema 的欄位），報告寫明、分工的結果列出「第 N 項：X 說要交給 Y 查」
  （查過、排除的附上），主模型照它再分工；主對話叫複合技能的名稱回交給哪個領域、子工作階段裡也擋。

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
DOMAINS = ["repo_analysis", "robotics_infra", "rmf_dispatch", "data_analysis", "multimodal"]   # DOMAIN.md 的領域（第 5 步 5-2 登記凍結的四個）
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
    """只用到一個領域的分工。"""
    return plan((domain, goal, items))


def plan(*entries):
    """分工（第 5 步 5-3）：entries＝[(領域, 子目標, 項目)]，照順序做。"""
    return {"thought": "分工", "reply": "交給領域查。", "action": {"domains": [{"domain": d, "goal": g, "items": list(i)} for d, g, i in entries]}}


def step(cmd, args=""):
    return {"thought": "照做", "reply": "執行中", "action": {"command": cmd, "args": args}}


def say(reply):
    return {"thought": "回覆", "reply": reply, "action": None}


class FakeChat:
    """假的 ollama.chat：照 format 的欄位分角色（主模型、挑技能、合約、判斷），各自依序取劇本；主模型的一則可以是函式（看對話決定回什麼）。"""

    def __init__(self, main=(), select=(), contract=(), judge=(), sub=()):
        self.q = {"main": list(main), "select": list(select), "contract": list(contract), "judge": list(judge), "sub": list(sub)}
        self.calls = []

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = set((format or {}).get("properties", {})) if isinstance(format, dict) else set()
        system = messages[0]["content"] if messages and messages[0].get("role") == "system" else ""
        role = ("sub" if SUB_MARK in system else "main" if "action" in props else "select" if "asks" in props
                else "judge" if props & {"lines", "branch"} else "contract" if "understanding" in props else "other")
        self.calls.append({"role": role, "format": format})
        if role == "other":
            data = {"answer": "（摘要）", "facts": [], "errors": [], "not_covered": "無", "suggested_questions": [], "index_hint": "（摘要）",
                    "related_records": [], "overview": "（摘要）", "key_progress": [], "results_and_errors": [], "user_preferences": [],
                    "open_items": [], "relevant": False, "summary": ""}
        else:
            q = self.q[role]
            if q:
                item = q.pop(0)
            elif role == "sub":                     # 子工作階段的劇本用完：每一項都查不到（附原因），收尾
                item = {"thought": "收尾", "reply": "查不到。", "action": None,
                        "answers": [{"item": k, "status": "not_found", "text": "（測試）沒有查到", "refs": []} for k in _item_enum(format)]}
            else:
                item = {"thought": "", "reply": "好的。", "action": None} if role == "main" else None
            data = item(messages) if callable(item) else item
        return {"message": {"content": json.dumps(data, ensure_ascii=False) if data is not None else ""},
                "prompt_eval_count": 100, "eval_count": 20}

    def count(self, role):
        return sum(1 for c in self.calls if c["role"] == role)


SUB_MARK = "的子工作階段：主對話把使用者的問題分給幾個領域"     # 子工作階段的 system prompt（prompts/sub/session.md）


def _answer_shapes(fmt):
    """answers 每一項的形狀：主對話一種；子工作階段兩種（答到的、查不到與不屬於的多 domain，第 5 步 5-4）。"""
    try:
        one = fmt["properties"]["answers"]["items"]
    except (KeyError, TypeError):
        return []
    return one["anyOf"] if "anyOf" in one else [one]


def _item_enum(fmt):
    shapes = _answer_shapes(fmt)
    return shapes[0]["properties"]["item"]["enum"] if shapes else []


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
        from agent_core.answers import REF as _REF
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
            entry = act[2]["properties"]["domains"]["items"]["properties"]
            assert entry["domain"]["enum"] == DOMAINS and entry["items"]["maxItems"] == 6 and act[2]["properties"]["domains"]["maxItems"] == 4, act
            assert "分工" in sp and '{"domains": [{"domain": "<領域名稱>"' in sp, "「領域」一節寫分工的格式"
            fake = FakeChat(main=[say("你好。")])
            turn("你好", fake)
            fmt = next(c["format"] for c in fake.calls if c["role"] == "main")
            assert len(fmt["properties"]["action"]["anyOf"]) == 3, "主對話送的 schema 有「分工」"
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
            assert tools[0].startswith("[ERROR] search_text 是 repo_analysis 領域的工具") and '「分工」{"domains": [{"domain": "repo_analysis"' in tools[0], tools[0]
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
            assert "pkg/mod.py:1" in text and "- 要回答的項目 2：哪些地方呼叫 alpha" in text and "依上面的報告回答使用者" in text, text
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
            assert list(fmts[1]["properties"]) == ["thought", "reply", "answers", "action"], "action 放最後（t_reply_order）"
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
            # 這一回合主對話自己執行過的工具（共用的列目錄、找檔案）也算出處：存檔的 #編號；收據裡沒有的行不算
            def ans(messages):
                return answer("見下面。", [(1, "answered", "alpha 定義在 pkg/mod.py，pkg 裡有 mod.py", ["pkg/mod.py:1", f"#{agent.last_result_id}"])])
            fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha", ["alpha 定義在哪"]), step("list_dir"), step("scripts/ls_cmd.py", "pkg"), ans],
                            select=[SEL_PY], contract=[con_py()])
            before = len(agent.messages)
            events, _ = turn("pkg 裡的 alpha 定義在哪？", fake)
            nudges = [m["content"] for m in agent.messages[before:] if m["role"] == "user" and m["content"].startswith("【系統核對】")]
            assert not nudges, ("自己查的工具結果也算出處", nudges)
            shown = chats(events)[-1]
            assert "（出處：pkg/mod.py:1、#" in shown and "   > pkg/mod.py:1" in shown, shown
            assert agent._cited("pkg/mod.py:9")[0] == "unknown", "報告與收據裡都沒有的行不算"

        def t_redispatch_previous():
            # 第 1 次中階沒有適合的做法（接著開子工作階段）→ 同一個項目再交：中階的挑技能與合約看得到上一次的經過（中階停下來的原因與
            # 子工作階段做到的，兩筆）；幾次串起來（決策圖的上一次、下一次，中階與子工作階段之間也連）
            from web_app import topology
            fake = FakeChat(main=[dispatch("看 pkg 的 alpha", ["alpha 定義在哪"]), dispatch("在 pkg 的 .py 裡找 alpha 的定義", ["alpha 定義在哪"]), cite],
                            select=[select("none", "沒有看檔案的做法"), SEL_PY], contract=[con_py()])
            events, _ = turn("pkg 裡的 alpha 定義在哪？", fake)
            first, second = agent._domain_turn["dispatches"]
            assert first["kind"] == "sub" and first["mid"]["status"] == "no_skill" and second["kind"] == "mid" and second["status"] == "done", first
            assert second["n"] == 2 and second["previous"] == [first["job"]]
            job2 = mid_job(second["job"])
            assert job2["attempt"] == 2 and [(p["kind"], p["status"]) for p in job2["previous"]] == [("mid", "no_skill"), ("sub", "done")], job2["previous"]
            assert mid_job(first["mid"]["job"])["next"] == [{"job": first["job"], "n": 1, "kind": "sub"}, {"job": second["job"], "n": 2, "kind": "mid"}]
            calls = open(os.path.join(tmp, "logs", "mid_jobs", second["job"], "calls.jsonl"), encoding="utf-8").read()
            assert calls.count("【上一次的經過】同一個問題之前交給這個領域 1 次") == 2 and "第 1 次：做法 —" in calls and "沒有看檔案的做法" in calls, "挑技能與合約都看得到"
            assert "第 1 次：做法 一步一步（子工作階段）" in calls and "結果：做完" in calls
            assert "第 2 次交給這個領域（之前：第 1 次 —：這個領域沒有適合的複合技能；第 1 次 一步一步（子工作階段）：做完）" in job2["result"]["report"]
            v2 = topology.job_view("logs", f"mid_jobs/{second['job']}", root=tmp)
            v1 = topology.job_view("logs", f"mid_jobs/{first['mid']['job']}", root=tmp)
            assert v2["chain"]["attempt"] == 2 and [x["ref"] for x in v2["chain"]["previous"]] == [f"mid_jobs/{first['mid']['job']}", f"sub_jobs/{first['job']}"], v2["chain"]
            assert v1["chain"]["next"] == [{"ref": f"sub_jobs/{first['job']}", "n": 1, "retry": False}, {"ref": f"mid_jobs/{second['job']}", "n": 2, "retry": False}], v1["chain"]

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

        def t_mid_retry():
            # A″（開關 AGENT_MID_RETRY，預設關）：中階跑過、有結果、但沒做完（判斷說看過的行都沒寫）→ 第一次的報告照樣交回，程式接著讓中階
            # 再做一次（帶著上一次的經過與查到的；合約的值可以從查到的抄）；兩份報告都交回、照兩份核對；不開子工作階段；最多一次
            from agent_core import orchestrator
            from evals import domain_calls
            q = "guide 文件裡，啟動前要做什麼？"
            go = dispatch("照 guide 文件找啟動前要做什麼", ["啟動前要做什麼"])
            con_doc = {"understanding": "u", "doc": {"quote": "guide", "value": "guide"}, "words": {"quote": "啟動", "value": "啟動"}}
            con_lines = {"understanding": "u", "keyword": {"quote": "啟動前", "value": "啟動前"}, "files": {"quote": "", "value": ""},
                         "path": {"quote": "docs/guide.md", "value": "docs/guide.md"}, "exclude": {"quote": "", "value": ""}}
            nothing = {"understanding": "u", "reason": "r", "lines": [], "branch": "not_found", "params": {}}
            found = answer("找到了。", [(1, "answered", "啟動前先檢查電源", ["docs/guide.md:5"])])
            missing = answer("文件沒有寫。", [(1, "not_found", "文件裡沒有寫啟動前要做什麼", [])])
            # 開關關（A）：只有第一次
            fake = FakeChat(main=[go, missing], select=[select("doc_lookup", asks=("內容",))], contract=[con_doc], judge=[nothing])
            events, _ = turn(q, fake)
            (e,) = agent._domain_turn["dispatches"]
            assert e["retry"] is None and e["skill"] == "doc_lookup" and fake.count("select") == 1, e
            assert "自動再做" not in tools_of(events)[0]
            orchestrator.MID_RETRY = True
            try:
                fake = FakeChat(main=[go, found], select=[select("doc_lookup", asks=("內容",)), select("find_lines", asks=("位置", "內容"))],
                                contract=[con_doc, con_lines], judge=[nothing])
                events, _ = turn(q, fake)
                (e,) = agent._domain_turn["dispatches"]
                assert e["retry"] == "judge_not_found" and e["mid"]["skill"] == "doc_lookup" and (e["skill"], e["status"]) == ("find_lines", "done"), e
                job1, job2 = mid_job(e["mid"]["job"]), mid_job(e["job"])
                assert job2["retry"]["of"] == job1["id"] and job2["retry"]["trigger"] == "judge_not_found" and job2["previous"][-1]["skill"] == "doc_lookup"
                assert job2["params"]["path"]["source"] == "found" and job2["params"]["keyword"]["source"] == "question", job2["params"]
                text = tools_of(events)[0]
                assert "repo_analysis 的報告（做完；做法 doc_lookup）" in text and "上面這一次沒有做完（做完，但判斷說看過的行都沒有寫這件事）" in text, text[:800]
                assert "repo_analysis 的報告（做完；做法 find_lines）" in text and "docs/guide.md:5" in text, text[-600:]
                assert len(agent._domain_turn["reports"]) == 2 and fake.count("sub") == 0, "兩份報告都交回；不開子工作階段"
                assert "沒有通過核對" not in chats(events)[-1], "照再做的那一份報告寫的出處通過核對"
                assert [p["n"] for p in agent._attempt_infos(e)] == [1, 1] and agent._attempt_infos(e)[0]["searched"] == ["啟動"], "之後再交：兩筆都給"
                rec = domain_calls.calls(agent, {"action": go["action"]}, "ok")
                assert (rec[0]["mid_skill"], rec[0]["retry"], rec[0]["retry_skill"], rec[0]["retry_job"]) == ("doc_lookup", "judge_not_found", "find_lines", e["job"]), rec[0]
                assert [c["skill"] for c in rec[1:]].count("search_text") == 2, "兩次用到的工具都記"
                from web_app import topology
                v1 = topology.job_view("logs", f"mid_jobs/{job1['id']}", root=tmp)
                v2 = topology.job_view("logs", f"mid_jobs/{job2['id']}", root=tmp)
                assert v1["chain"]["next"] == [{"ref": f"mid_jobs/{job2['id']}", "n": 1, "retry": True}] and v2["chain"]["retry"], (v1["chain"], v2["chain"])
                # 再做的那一次沒有報告（挑了「沒有適合的」）：照第一份回答，不排除、不開子工作階段
                fake = FakeChat(main=[go, missing], select=[select("doc_lookup", asks=("內容",)), select("none", "沒有別的做法")],
                                contract=[con_doc], judge=[nothing])
                events, _ = turn(q, fake)
                (e,) = agent._domain_turn["dispatches"]
                assert e["retry"] == "judge_not_found" and e["status"] == "no_skill" and agent._reported(e) and agent.domain_items() == ["啟動前要做什麼"], e
                assert "再做的那一次沒有報告（這個領域沒有適合的複合技能：沒有別的做法" in tools_of(events)[0] and fake.count("sub") == 0
                assert "repo_analysis" not in agent._domain_turn["excluded"]
                # 沒有觸發（做完、沒有判斷的技能）：照舊一次
                fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha", ["alpha 定義在哪"]), cite], select=[SEL_PY], contract=[con_py()])
                turn("pkg 裡的 alpha 定義在哪？", fake)
                (e,) = agent._domain_turn["dispatches"]
                assert e["retry"] is None and fake.count("select") == 1 and e["status"] == "done", e
            finally:
                orchestrator.MID_RETRY = False

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
            bad = [dispatch("g", ["a"], domain="nope"), dispatch("", ["a"]),
                   dispatch("在 pkg 找", []), dispatch("在 pkg 找", [f"項目{i}" for i in range(7)]),
                   dispatch("列出 pkg 的檔案", ["有哪些檔案"]), dispatch("列出 pkg 的檔案", ["有哪些檔案"]), say("好")]
            fake = FakeChat(main=bad, select=[select("none", "沒有列目錄的做法")])
            events, _ = turn("pkg 有哪些檔案？", fake)
            tools = tools_of(events)
            assert tools[0].startswith("[ERROR] 沒有「nope」這個領域（有的領域：" + "、".join(DOMAINS) + "）"), tools[0]
            assert tools[1].startswith("[ERROR] 交給 repo_analysis 時 goal 是空的"), tools[1]
            assert tools[2].startswith("[ERROR] 要回答的項目有 0 項（要 1～6 項）") and tools[3].startswith("[ERROR] 要回答的項目有 7 項"), tools[2:4]
            assert tools[4].startswith(DOMAIN_RESULT_HEAD) and tools[5].startswith("[ERROR] 這個問題已經用一樣的子目標與項目交給過 repo_analysis"), tools[5]
            assert fake.count("select") == 1, "核對沒過的不執行中階、一樣的不再跑一次"

        def t_no_skill_sub():
            # 沒有適合的做法：程式接著開子工作階段，用這個領域的工具一步一步做（第 5 步 G3，取代放行）；主對話看不到試錯，照舊不能直接用
            from evals import domain_calls

            def sub_ans(messages):
                return {"thought": "收尾", "reply": "看完兩個檔案。", "action": None,
                        "answers": [{"item": 1, "status": "answered", "text": "mod.py 定義 alpha，use.py 的 gamma 呼叫 alpha",
                                     "refs": ["pkg/mod.py:1", "pkg/use.py:4"]}]}

            def main_ans(messages):
                return answer("見報告。", [(1, "answered", "mod.py 定義 alpha", ["pkg/mod.py:1"])])
            fake = FakeChat(main=[dispatch("比較 pkg/mod.py 與 pkg/use.py", ["兩個檔案差在哪"]), step("scripts/cat_cmd.py", "pkg/mod.py"), main_ans],
                            select=[select("none", "沒有比較兩個檔案的做法")],
                            sub=[step("view_file"), step("scripts/cat_cmd.py", "pkg/mod.py"), step("scripts/cat_cmd.py", "pkg/use.py"), sub_ans])
            before = len(agent.messages)
            events, _ = turn("pkg/mod.py 跟 pkg/use.py 差在哪？", fake)
            tools = tools_of(events)
            assert "repo_analysis 的中階沒有做完（這個領域沒有適合的複合技能：沒有比較兩個檔案的做法" in tools[0], tools[0][:300]
            assert "系統接著在子工作階段裡用這個領域的工具一步一步做" in tools[0] and "repo_analysis 的報告（做完；做法 一步一步（子工作階段））" in tools[0]
            for want in ("1. 兩個檔案差在哪：mod.py 定義 alpha，use.py 的 gamma 呼叫 alpha（出處：pkg/mod.py:1、pkg/use.py:4）",
                         "   > pkg/mod.py:1：def alpha(x):", "   > pkg/use.py:4：def gamma():", "1. 載入 view_file 的規格",
                         "2. scripts/cat_cmd.py pkg/mod.py → [PASS]", "- 第 1 次交給這個領域（之前：第 1 次 —：這個領域沒有適合的複合技能（沒有比較兩個檔案的做法））"):
                assert want in tools[0], (want, tools[0])
            assert tools[1].startswith("[ERROR] view_file 是 repo_analysis 領域的工具"), "主對話照舊不能直接用（沒有放行）"
            shown = chats(events)[-1]
            assert "1. 兩個檔案差在哪：mod.py 定義 alpha（出處：pkg/mod.py:1）\n   > pkg/mod.py:1：def alpha(x):" in shown and "   > 1. " not in shown, \
                ("使用者看到的出處原文是報告附的那一行，不是報告裡同樣寫了出處的回答那一行", shown)
            assert not any(SKILL_DOC_PREFIX in m["content"] and "view_file" in m["content"] for m in agent.messages[before:]), "子工作階段的試錯不進主對話"
            assert fake.count("sub") == 4 and any("ref=sub_jobs/" in e["text"] for e in events if e["channel"] == "progress")
            d = agent._domain_turn["dispatches"][-1]
            job = json.load(open(os.path.join(tmp, "logs", "sub_jobs", d["job"], "job.json"), encoding="utf-8"))
            assert [st["tool"] for st in job["steps"]] == ["view_file", "view_file", "view_file"] and job["steps"][0]["doc"] and job["status"] == "done"
            assert "【要回答的項目】（收尾時 answers 照這個編號）\n1. 兩個檔案差在哪" in job["messages"][0]["content"]
            assert "【上一次的經過】同一個問題之前交給這個領域 1 次" in job["messages"][0]["content"] and "沒有比較兩個檔案的做法" in job["messages"][0]["content"]
            assert "（這份工具結果的存檔是 #" not in job["messages"][2]["content"] and "（這份工具結果的存檔是 #" in job["messages"][4]["content"], \
                "載入規格沒有存檔；執行的結果前面標 #編號"
            calls = domain_calls.calls(agent, {"action": dispatch("比較 pkg/mod.py 與 pkg/use.py", ["兩個檔案差在哪"])["action"]}, tools[0])
            assert calls[0]["mid_status"] == "no_skill" and calls[0]["sub_status"] == "done" and calls[0]["sub_steps"] == 2, calls[0]
            assert [(c["skill"], c["via"], c["args"]) for c in calls[1:]] == [("view_file", "repo_analysis", ["pkg/mod.py"]), ("view_file", "repo_analysis", ["pkg/use.py"])], calls

        def t_sub_inline_cite():
            # 回答的內文寫「檔案:行號」、出處寫 #編號（待辦 4l ①）：內文的 檔案:行號 跟出處一樣照收據核對。收據裡有的通過；以前整串當成一個名稱，
            # 在 search_text 的原文（每一行寫成「行號→」）裡找不到，一定擋。收據裡沒有的照樣擋（交回修一次，還是一樣就標出來）
            def sub_ans(line):
                def f(messages):
                    rid = re.findall(r"存檔是 #(\d+)", "\n".join(m["content"] for m in messages))[-1]
                    return {"thought": "收尾", "reply": "找到了。", "action": None,
                            "answers": [{"item": 1, "status": "answered", "text": f"alpha 定義在pkg/mod.py:{line}", "refs": [f"#{rid}"]}]}
                return f
            for line, ok in ((1, True), (5, False)):
                fake = FakeChat(main=[dispatch("在 pkg 裡找 alpha 的定義", ["alpha 定義在哪"]), say("好")],
                                select=[select("none", "沒有適合的做法")],
                                sub=[step("search_text"), step("scripts/grep_cmd.py", '"def alpha" pkg'), sub_ans(line), sub_ans(line)])
                turn("pkg 裡的 alpha 定義在哪？", fake)
                job = sub_job(agent._domain_turn["dispatches"][-1]["job"])
                fix = [m["content"] for m in job["messages"] if m["role"] == "user" and m["content"].startswith("【系統核對】")]
                assert job["steps"][-1]["status"] == "PASS" and job["status"] == "done", (job["steps"][-1], job["status"])
                if ok:
                    assert not fix and not job["problems"], (fix, job["problems"])
                else:
                    assert len(fix) == 1 and "pkg/mod.py:5" in fix[0] and "pkg/mod.py:5" in "".join(job["problems"]["1"]), (fix, job["problems"])

        def t_out_of_domain():
            fake = FakeChat(main=[dispatch("看 cam_box 容器在不在跑", ["cam_box 現在的狀態"]), dispatch("再找一次 cam_box", ["狀態"]),
                                  step("scripts/cat_cmd.py", "pkg/mod.py"), say("不屬於。")],
                            select=[select("out_of_domain", "問的是正在跑的容器", asks=("內容",))])
            events, _ = turn("cam_box 容器現在在跑嗎？", fake)
            tools = tools_of(events)
            assert "repo_analysis 說它的子目標不屬於它：問的是正在跑的容器" in tools[0] and "重新分工時交給別的領域" in tools[0] and "[view_file]" not in tools[0], tools[0]
            assert tools[1].startswith("[ERROR] 這個問題已經交給過 repo_analysis，它說不屬於它") and "1. repo_analysis（做法 —）：不屬於這個領域，決策圖 /topology" in tools[1], tools[1]
            assert tools[2].startswith("[ERROR] view_file 是 repo_analysis 領域的工具"), "不屬於的也不放行（第 5 步）"
            assert fake.count("sub") == 0, "不屬於這個領域不開子工作階段"

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
            text = tools_of(ev)[0]
            assert "repo_analysis 的中階沒有做完（使用者取消：要問的是：工作目錄底下找不到「pkgx」：要查哪裡？" in text and "# 子工作階段的結果" in text, text[:400]
            assert mid_job(jid)["status"] == "cancelled" and agent.domain_gate("scripts/cat_cmd.py"), "取消之後接著開子工作階段；主對話照舊擋"
            # 再交時的上一次的經過：中階那一筆帶著它用的參數（再交的中階看得到、跟它一模一樣的擋得到），子工作階段那一筆接在後面
            d = agent._domain_turn["dispatches"][-1]
            info = agent._attempt_infos(d)
            assert [(i["kind"], i["status"]) for i in info] == [("mid", "cancelled"), ("sub", d["status"])] and \
                info[0]["skill"] == "py_usage" and info[0]["params"]["name"] == "alpha" and info[0]["params"]["path"] == "pkgx", info
            subs = len(os.listdir(os.path.join(tmp, "logs", "sub_jobs")))
            fake, events, awaiting = ask_turn()
            jid = agent.domain_pending["job"]
            assert handle_slash_command("/clear", []) and agent.domain_pending is None and pending["mode"] is None, "/clear 一起取消"
            assert mid_job(jid)["status"] == "cancelled" and len(os.listdir(os.path.join(tmp, "logs", "sub_jobs"))) == subs, "/clear 不接著做"

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
                    assert "repo_analysis 的中階沒有做完（使用者取消" in out and "系統接著在子工作階段裡" in out, out[-2000:]

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
                        assert not done["awaiting_decision"] and any(e["channel"] == "tool" and "（使用者取消" in e["text"] and "子工作階段" in e["text"]
                                                                     for e in events), events
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
            assert domain_calls.calls(agent, {"action": dispatch("g", [], domain="nope")["action"]}, "[ERROR] x")[0]["status"] == "ERROR"
            ollama.chat = FakeChat(select=[SEL_PY], contract=[con_py(path="pkgx")])
            agent.set_current_task("pkgx 裡的 alpha 定義在哪？")
            parsed = {"action": dispatch("在 pkgx 裡找 alpha", ["alpha 定義在哪"])["action"]}
            t = {}
            result = domain_calls.settle(agent, parsed, agent.run_tool(parsed), t)
            assert agent.domain_pending is None and t["domain_asks"] and "（使用者取消" in result and "子工作階段" in result, (t, result[:200])
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

        def with_test_domain(fn):
            """暫時加一個沒有複合技能的領域 test_ops（工具：file_ops、list_dir；〈做法〉一節）：交給它就直接開子工作階段。"""
            dom = os.path.join(tmp, "skills_system", "DOMAIN.md")
            old = open(dom, encoding="utf-8").read()
            os.makedirs(os.path.join(tmp, "skills_system", "test_ops"), exist_ok=True)
            with open(os.path.join(tmp, "skills_system", "test_ops", "SKILLS.md"), "w", encoding="utf-8") as f:
                f.write("# test_ops：測試用的檔案操作\n\n改工作目錄裡的文字檔。不包含：讀程式碼。\n\n## 做法\n- 改之前先列目錄確認檔案在不在。\n\n"
                        "## 複合技能\n\n## 工具\n- [file_ops](../tools/file_ops.md)\n- [list_dir](../tools/list_dir.md)\n")
            with open(dom, "w", encoding="utf-8") as f:
                f.write(old.replace("- [repo_analysis](repo_analysis/SKILLS.md)", "- [repo_analysis](repo_analysis/SKILLS.md)\n- [test_ops](test_ops/SKILLS.md)"))
            try:
                fn()
            finally:
                with open(dom, "w", encoding="utf-8") as f:
                    f.write(old)

        def sub_job(jid):
            with open(os.path.join(tmp, "logs", "sub_jobs", jid, "job.json"), encoding="utf-8") as f:
                return json.load(f)

        def t_sub_domain_guard():
            # 沒有複合技能的領域：直接開子工作階段（不挑技能）；「領域」一節寫明；system prompt 有〈做法〉與能用的工具；
            # 會改狀態的工具停下來問使用者（Web），同意之後接回同一步、不同意把 [DENIED] 交給模型接著做
            def body():
                assert "（沒有寫好的做法：交給這個領域的問題，系統在子工作階段裡用它的工具一步一步做" in agent.get_system_prompt()
                assert agent.domain_gate("scripts/file_ops_cmd.py"), "主對話不能直接用 test_ops 的工具"

                def fin(messages):
                    rid = re.findall(r"存檔是 #(\d+)", "\n".join(m["content"] for m in messages))[-1]
                    return {"thought": "收尾", "reply": "寫好了。", "action": None,
                            "answers": [{"item": 1, "status": "answered", "text": "寫好了", "refs": [f"#{rid}"]}]}
                for approve in (True, False):
                    target = os.path.join(tmp, f"notes_{approve}.txt")
                    fake = FakeChat(main=[dispatch("在工作目錄寫 notes", ["寫好了沒"], domain="test_ops"),
                                          lambda m: answer("見報告。", [(1, "answered" if approve else "not_found", "寫好了" if approve else "使用者沒有同意",
                                                                       [f"#{agent._domain_turn['dispatches'][-1]['result_id']}"] if approve else [])])],
                                    sub=[step("file_ops"), step("scripts/file_ops_cmd.py", f'write notes_{approve}.txt --text "hello"'),
                                         fin if approve else {"thought": "沒寫", "reply": "使用者沒有同意。", "action": None,
                                                              "answers": [{"item": 1, "status": "not_found", "text": "使用者沒有同意寫入", "refs": []}]}])
                    events, awaiting = turn("幫我寫 notes", fake)
                    assert awaiting and agent.domain_pending["worker"] == "sub" and agent.domain_pending["kind"] == "guard", agent.domain_pending
                    assert fake.count("select") == 0, "沒有複合技能：不挑技能"
                    jid = agent.domain_pending["job"]
                    job = sub_job(jid)
                    assert "## 這個領域現在的做法\n- 改之前先列目錄確認檔案在不在。" in job["system"] and "- [file_ops](tools/file_ops.md)" in job["system"]
                    assert "- [result_view](tools/result_view.md)" in job["system"], "共用的工具也能用"
                    ev = []
                    assert flows.answer_domain_turn("是" if approve else "否", ev) is False and agent.domain_pending is None
                    job = sub_job(jid)
                    assert job["asked"][-1]["approve"] is approve and job["status"] == "done", job["asked"]
                    assert os.path.exists(target) is approve
                    text = tools_of(ev)[0]
                    want = "（使用者同意）" if approve else "使用者沒有同意（確認關卡），沒有執行"
                    assert want in text and "test_ops 的報告（做完；做法 一步一步（子工作階段））" in text, text[:600]
                    if not approve:
                        assert any("[DENIED]" in m["content"] for m in job["messages"]), "不同意：[DENIED] 交給子工作階段的模型"
            with_test_domain(body)

        def t_sub_limits():
            # 子工作階段的上限與收尾：不是這個領域的工具擋下來；同樣的動作 4 次卡住就收尾；步數用完照做到的收尾；
            # 收尾的出處不是自己的工具結果 → 交回修一次，還是不對就標出來
            from agent_core import sub as subm

            def body():
                fake = FakeChat(main=[dispatch("列出工作目錄", ["有哪些檔案"], domain="test_ops"), say("好")],
                                sub=[step("scripts/cat_cmd.py", "pkg/mod.py")] + [step("scripts/ls_cmd.py", "pkg")] * 4)
                turn("工作目錄有哪些檔案？", fake)
                job = sub_job(agent._domain_turn["dispatches"][-1]["job"])
                assert job["steps"][0]["status"] == "ERROR" and "view_file 不是 test_ops 這個領域的工具" in job["steps"][0]["head"], job["steps"][0]
                assert job["status"] == "stopped" and "同樣的動作 4 次都得到同樣的結果" in job["result"]["note"] and len(job["steps"]) == 5, job["result"]
                old = subm.SUB_STEPS_MAX
                subm.SUB_STEPS_MAX = 2
                try:
                    fake = FakeChat(main=[dispatch("列出工作目錄", ["有哪些檔案"], domain="test_ops"), say("好")],
                                    sub=[step("list_dir"), step("scripts/ls_cmd.py", "pkg"), step("scripts/ls_cmd.py", "docs")])
                    turn("工作目錄有哪些檔案？", fake)
                finally:
                    subm.SUB_STEPS_MAX = old
                job = sub_job(agent._domain_turn["dispatches"][-1]["job"])
                assert job["status"] == "stopped" and "步數用完（最多 2 步）" in job["result"]["note"] and len(job["steps"]) == 2, job["result"]
                bad = {"thought": "收尾", "reply": "好", "action": None, "answers": [{"item": 1, "status": "answered", "text": "有 mod.py", "refs": ["#99999"]}]}
                fake = FakeChat(main=[dispatch("列出工作目錄", ["有哪些檔案"], domain="test_ops"), say("好")],
                                sub=[step("scripts/ls_cmd.py", "pkg"), bad, bad])
                turn("工作目錄有哪些檔案？", fake)
                job = sub_job(agent._domain_turn["dispatches"][-1]["job"])
                fix = [m["content"] for m in job["messages"] if m["role"] == "user" and m["content"].startswith("【系統核對】")]
                assert len(fix) == 1 and "出處 #99999 不在這個子工作階段的工具結果裡" in fix[0], fix
                assert job["status"] == "done" and "⚠️ 沒有通過核對：出處 #99999 不在這個子工作階段的工具結果裡" in job["result"]["report"]
            with_test_domain(body)

        def t_sub_protocol():
            # 子工作階段的回覆（第 5 步 5-1 的評測之後）：每一則不是用工具就是收尾——沒有動作也沒有回答提醒一次（上一步之後只一次，不算交回修，
            # 收尾的核對照樣能交回修）；收尾寫成 {"command": "null"} 跟 action null 一樣；寫到長度上限被截斷的不執行、只接提醒重問一次，
            # 還是被截斷就不執行那個動作（對話裡不留那段截斷的參數）
            from agent_core.config import REPLY_ARGS_CHARS
            empty = {"thought": "我將先用 list_dir 看目錄", "reply": "我將列出目錄。", "action": None, "answers": []}
            bad = {"thought": "收尾", "reply": "好", "action": None, "answers": [{"item": 1, "status": "answered", "text": "有 mod.py", "refs": ["#99999"]}]}
            long_step = step("scripts/ls_cmd.py", "x" * REPLY_ARGS_CHARS)

            def good(messages):
                rid = re.findall(r"存檔是 #(\d+)", "\n".join(m["content"] for m in messages))[-1]
                return {"thought": "收尾", "reply": "列好了。", "action": None,
                        "answers": [{"item": 1, "status": "answered", "text": "有 mod.py", "refs": [f"#{rid}"]}]}

            def run(sub):
                turn("pkg 裡有哪些檔案？", FakeChat(main=[dispatch("列出 pkg", ["有哪些檔案"], domain="test_ops"), say("好")], sub=sub))
                job = sub_job(agent._domain_turn["dispatches"][-1]["job"])
                users = [m["content"] for m in job["messages"] if m["role"] == "user"]
                return job, sum(u.startswith("【系統提醒】上一則 action 是 null、answers 也是空的") for u in users), sum(u.startswith("【系統核對】") for u in users)

            def body():
                job, empties, fixes = run([empty, step("scripts/ls_cmd.py", "pkg"), bad, good])
                assert (empties, fixes, job["status"], job["problems"], len(job["steps"]), job["empty_at"]) == (1, 1, "done", {}, 1, 0), (empties, fixes, job["result"])
                job, empties, fixes = run([empty, empty])          # 提醒之後還是沒有動作也沒有回答：照收尾核對（交回修一次），劇本用完收尾
                assert (empties, fixes, job["status"], len(job["steps"])) == (1, 1, "done", 0) and job["answers"][0]["status"] == "not_found", job["result"]
                job, empties, fixes = run([step("scripts/ls_cmd.py", "pkg"), lambda m: dict(good(m), action={"command": "null", "args": ""})])
                assert (empties, fixes, job["status"], job["problems"], len(job["steps"])) == (0, 0, "done", {}, 1) and job["answers"][0]["refs"], job["result"]
                job, empties, fixes = run([long_step, step("scripts/ls_cmd.py", "pkg"), good])
                assert [st["args"] for st in job["steps"]] == [["pkg"]] and job["status"] == "done" and empties == 0, job["steps"]
                with open(os.path.join(tmp, "logs", "sub_jobs", job["id"], "calls.jsonl"), encoding="utf-8") as f:
                    calls = [json.loads(ln) for ln in f]
                assert calls[0]["error"] == "寫到長度上限被截斷：args" and calls[1]["user"].startswith("【系統提醒】上一次的回覆裡 args 寫到長度上限被截斷了"), calls[:2]
                assert not any("xxxxxxxxxx" in m["content"] for m in job["messages"]), "截斷的回覆不進子工作階段的對話"
                job, empties, fixes = run([long_step, long_step, step("scripts/ls_cmd.py", "pkg"), good])   # 重問之後還是被截斷：不執行，接著提醒
                assert [st["args"] for st in job["steps"]] == [["pkg"]] and job["status"] == "done" and empties == 1, (job["steps"], empties)
                assert not any("xxxxxxxxxx" in m["content"] for m in job["messages"]), "存進對話的是不含截斷參數的 JSON"
            with_test_domain(body)

        def t_sub_followup():
            # 待辦 4k ①（設計筆記 2.47）：子工作階段的長輸出照舊提煉，結尾的下一步建議只寫它能用的 result_grep、result_view
            # （它沒有 result_recall：5c 照建議叫了 18 次，全部被擋），也不叫它問使用者
            many = os.path.join(tmp, "many")
            os.makedirs(many, exist_ok=True)
            for k in range(150):
                open(os.path.join(many, f"file_with_a_rather_long_name_{k:03d}.txt"), "w").close()

            def body():
                turn("many 裡有哪些檔案？", FakeChat(main=[dispatch("列出 many", ["有哪些檔案"], domain="test_ops"), say("好")],
                                                   sub=[step("scripts/ls_cmd.py", "many")]))
                job = sub_job(agent._domain_turn["dispatches"][-1]["job"])
                got = [m["content"] for m in job["messages"] if m["role"] == "user" and "[tool result - 任務導向摘要]" in m["content"]]
                assert job["steps"][0]["summarized"] and len(got) == 1, job["steps"]
                assert "result_grep" in got[0] and "result_view" in got[0] and "result_recall" not in got[0], got[0]
                assert not any(w in got[0] for w in ("使用者追問", "問使用者", "已顯示給使用者", "使用者目標")), "子工作階段沒有使用者可以問、使用者也沒看到輸出"
            try:
                with_test_domain(body)
            finally:
                shutil.rmtree(many, ignore_errors=True)

        def t_sub_topology():
            # 決策圖：子工作階段在清單裡（種類、步數），一個工作整理成每一步、收尾的回答與核對；跟中階一樣串起上一次、下一次
            from web_app import topology
            jobs = topology.jobs("logs", root=tmp)
            subs = [j for j in jobs if j["kind"] == "sub"]
            assert subs and subs[0]["ref"].startswith("sub_jobs/") and "steps" in subs[0] and subs[0]["skill"] == "一步一步（子工作階段）", subs[:1]
            assert topology.sources(root=tmp)[0]["sub"] == len(subs), topology.sources(root=tmp)
            ref = next(j["ref"] for j in subs if j["title"] == "pkg/mod.py 跟 pkg/use.py 差在哪？")   # 中階沒有適合的做法之後開的那一個
            v = topology.job_view("logs", ref, root=tmp)
            assert v["kind"] == "sub" and v["versions"] == [] and v["steps"] and "rep" not in v["steps"][0] and v["report"].startswith("# 子工作階段的結果")
            assert v["system"] and isinstance(v["calls"], list) and v["calls"][0]["role"] == "step" and v["status_text"]
            assert v["chain"]["previous"] and v["chain"]["previous"][0]["ref"].startswith("mid_jobs/"), v["chain"]

        def t_frozen_domains():
            # 第 5 步 5-2：凍結的工具登記成四個領域（沒有複合技能：直接開子工作階段）；主對話的索引拿掉它們，工具全部交給領域的那幾節
            # （標題與說明）也不列；子工作階段列工具時，那一節的說明（目標容器、ROS 2 Workspace）放在第一個工具前面；〈做法〉從 AGENT.md 搬過去
            reg = agent.domain_registry()
            assert list(reg["domains"]) == DOMAINS and not reg["problems"], (list(reg["domains"]), reg["problems"])
            sp = agent.get_system_prompt()
            assert all(f"### {d}：" in sp for d in DOMAINS) and sp.count("（沒有寫好的做法：交給這個領域的問題") == 4, "四個凍結的領域在「領域」一節"
            skills = sp[sp.index("## Available Skills"):]
            frozen = {t for d in DOMAINS[1:] for t in reg["domains"][d]["tools"]}
            assert len(frozen) == 28 and not [t for t in frozen if f"[{t}]" in skills], "凍結的 28 個工具不列在主對話的索引"
            assert all(f"[{t}]" in skills for t in ("change_dir", "file_ops", "host_runcmd", "csv_query") + SHARED), "不屬於領域的照舊"
            for gone in ("## 容器化環境", "## ROS2套件", "## 調度系統", "## 多模態資訊", "## ROS 2 數據解析", "**目標容器**", "**ROS 2 Workspace 狀態**",
                         "執行邊界"):
                assert gone not in skills, f"工具全部交給領域的那一節（標題與說明）不列：{gone}"
            lines = agent._index_lines(reg["domains"]["robotics_infra"]["tools"] + reg["shared"]).split("\n")
            k = next(i for i, ln in enumerate(lines) if "**目標容器**" in ln)
            assert lines[k + 1].startswith("- [docker_containers]"), "目標容器的說明放在容器工具的前面"
            k = next(i for i, ln in enumerate(lines) if "**ROS 2 Workspace 狀態**" in ln)
            assert lines[k + 1].startswith("- [ROS2_domain_id]"), "ROS 2 Workspace 的說明放在 ROS2_* 的前面"
            assert sum("**目標容器**" in ln for ln in lines) == 1, "一節的說明只列一次"
            assert not any(ln.startswith(">") for ln in agent._index_lines(reg["domains"]["repo_analysis"]["tools"]).split("\n")), \
                "repo_analysis 的工具那幾節沒有說明：跟以前一樣只有工具"
            with open(os.path.join(tmp, "prompts", "AGENT.md"), encoding="utf-8") as f:
                prof = f.read()
            assert "## Data Analysis" not in prof and "工作包卡住" not in prof and "容器停了" not in prof and "CURRENT_TARGET_CONTAINER" not in prof
            assert "改設定檔的一個值" in prof and "使用者提到手冊" in prof and "只查不改" in prof, "跨領域的做法留在主對話"
            practice = {d: reg["domains"][d]["practice"] for d in DOMAINS}
            assert "**數據在哪裡**" in practice["data_analysis"] and "analysis_run" in practice["data_analysis"]
            assert "ROS2_topic_echo" not in practice["data_analysis"], "正在跑的系統不是 data_analysis 的事"
            assert "工作包卡住" in practice["rmf_dispatch"] and "handshake" in practice["rmf_dispatch"] and "容器停了" in practice["robotics_infra"]
            assert "CURRENT_TARGET_CONTAINER" in practice["robotics_infra"] and not practice["multimodal"]
            for tool, dom in (("docker_ctl", "robotics_infra"), ("workpackage_status", "rmf_dispatch"), ("analysis_run", "data_analysis"),
                              ("stt_engine", "multimodal"), ("scripts/ROS2_param_cmd.py", "robotics_infra")):
                assert agent.domain_gate(tool).startswith(f"[ERROR] {tool.split('/')[-1].replace('_cmd.py', '')} 是 {dom} 領域的工具"), tool
            agent._sub_allowed = {"domain": "rmf_dispatch", "tools": set(reg["domains"]["rmf_dispatch"]["tools"] + reg["shared"])}
            try:
                assert agent.domain_gate("docker_containers") is None and agent.domain_gate("rmf_handshake") is None
                assert agent.domain_gate("docker_ctl").startswith("[ERROR] docker_ctl 不是 rmf_dispatch 這個領域的工具"), "子工作階段只能用那個領域的工具"
            finally:
                agent._sub_allowed = None

        def t_sub_analysis():
            # G4：analysis_run 在 data_analysis 的子工作階段裡執行：數據分析的報告原樣附在交回主對話的報告裡；主對話照它核對回答
            # （analysis_reply_check：answers 的回答寫成因果 → 提醒一次），之後的回合也核對寫到報告的那幾行
            from agent_core.config import ANALYSIS_ANSWER_NOTE, ANALYSIS_REPORT_HEAD
            areport = (f"{ANALYSIS_REPORT_HEAD}（job 20260101_000000：程式整理，1 秒）\n問題：安全閘什麼時候恢復？\n數據：exp_x（30.000 秒）\n"
                       "重點（程式整理）：\n- +3.20s　/scan 中斷（E1）\n- +15.50s　/safety_gate 狀態改變：PROTECTIVE_STOP → RUNNING（E2）\n"
                       f"{ANALYSIS_ANSWER_NOTE}：只陳述報告裡的事實）")

            def fin(messages):
                rid = re.findall(r"存檔是 #(\d+)", "\n".join(m["content"] for m in messages))[-1]
                return {"thought": "收尾", "reply": "看完報告。", "action": None,
                        "answers": [{"item": 1, "status": "answered", "text": "+15.50s 安全閘從 PROTECTIVE_STOP 變成 RUNNING（E2）", "refs": [f"#{rid}"]}]}

            def ans(text):
                def f(messages):
                    rid = re.findall(r"數據分析的報告（#(\d+)，原樣）", last_report(messages))[-1]
                    return answer("見報告。", [(1, "answered", text, [f"#{rid}"])])
                return f
            real, n0 = agent.analysis_run, len(agent.messages)
            agent.analysis_run = lambda remainder="": areport
            try:
                fake = FakeChat(main=[dispatch("錄製的數據 exp_x 裡安全閘什麼時候恢復", ["什麼時候恢復"], domain="data_analysis"),
                                      ans("雷達斷線導致安全閘停住，+15.50s 恢復 RUNNING（E2）"), ans("+15.50s 安全閘從 PROTECTIVE_STOP 變成 RUNNING（E2）")],
                                sub=[step("analysis_run"), step("scripts/analysis_run_cmd.py", '--data exp_x "安全閘什麼時候恢復"'), fin])
                events, _ = turn("錄製的 exp_x 裡安全閘什麼時候恢復？", fake)
            finally:
                agent.analysis_run = real
            d = agent._domain_turn["dispatches"][-1]
            job = sub_job(d["job"])
            rid = [st["result_id"] for st in job["steps"] if st["tool"] == "analysis_run" and not st["doc"]][0]
            assert d["kind"] == "sub" and fake.count("select") == 0, "沒有複合技能：直接開子工作階段"
            assert f"## 數據分析的報告（#{rid}，原樣）\n{areport}" in job["result"]["report"], "數據分析的報告原樣附在報告裡"
            mine = agent.messages[n0:]
            result = next(m["content"] for m in mine if m["role"] == "user" and DOMAIN_RESULT_HEAD in m["content"])
            assert areport.split("\n")[4] in result, "交回主對話的報告裡有數據分析的報告"
            assert agent._analysis_ctx and agent._analysis_ctx["report"].startswith(ANALYSIS_REPORT_HEAD) and ANALYSIS_ANSWER_NOTE not in agent._analysis_ctx["report"]
            nudges = [m["content"] for m in mine if m["role"] == "user" and m["content"].startswith("[harness]") and "導致" in m["content"]]
            assert len(nudges) == 1 and fake.count("main") == 3, "answers 寫成因果：提醒一次改寫（analysis_reply_check 看 answers 的回答）"
            assert "+15.50s 安全閘從 PROTECTIVE_STOP 變成 RUNNING" in [e for e in events if e["channel"] == "chat"][-1]["text"]
            agent.begin_turn()                      # 之後的回合：寫到報告的那幾行照樣核對
            assert agent.analysis_reply_check({"reply": "是雷達斷線導致的（E2）", "action": None, "valid": True}), "之後的回合也核對"
            assert agent.analysis_reply_check({"reply": "好的，還有別的問題嗎？", "action": None, "valid": True}) is None, "跟報告無關的不核對"

        def t_plan_two_domains():
            # 5-3 分工：一次選兩個領域、照順序做；後面的領域收到前面的領域查到的（子工作階段一項一項的回答）與這個問題的分工（哪一項是它、
            # 主對話這一回合已經做過的）；子工作階段的第一則先放它的子目標，原始問題只當對照，提煉的錨點只放子目標與項目；報告一起交回、
            # 每個領域各自存成 #編號，最後列一次這一回合所有的項目；評測的 worker 每個領域記一筆
            from agent_core import sub as subm
            from evals import domain_calls
            seen = {}

            def fin1(messages):
                seen["first"] = messages[1]["content"]
                rid = re.findall(r"存檔是 #(\d+)", "\n".join(m["content"] for m in messages))[-1]
                return {"thought": "收尾", "reply": "列好了。", "action": None,
                        "answers": [{"item": 1, "status": "answered", "text": "pkg 裡有 mod.py 與 use.py", "refs": [f"#{rid}"]}]}

            def fin2(messages):
                seen["second"] = messages[1]["content"]
                return {"thought": "收尾", "reply": "查不到。", "action": None,
                        "answers": [{"item": 1, "status": "not_found", "text": "（測試）調度系統沒有這些檔案的紀錄", "refs": []}]}

            def main_ans(messages):
                rid = agent._domain_turn["dispatches"][0]["result_id"]
                return answer("見報告。", [(1, "answered", "pkg 裡有 mod.py 與 use.py", [f"#{rid}"]), (2, "not_found", "調度系統沒有紀錄", [])])
            two = plan(("robotics_infra", "列出 pkg 有哪些檔案", ["pkg 有哪些檔案"]), ("rmf_dispatch", "查調度系統裡有沒有 pkg 的檔案的紀錄", ["有沒有紀錄"]))
            fake = FakeChat(main=[step("list_dir"), step("scripts/ls_cmd.py", "docs"), two, main_ans],
                            sub=[step("list_dir"), step("scripts/ls_cmd.py", "pkg"), fin1, fin2])
            events, _ = turn("pkg 裡有哪些檔案？調度系統有沒有它們的紀錄？", fake)
            d1, d2 = agent._domain_turn["dispatches"]
            assert (d1["domain"], d2["domain"], d1["kind"], d2["kind"]) == ("robotics_infra", "rmf_dispatch", "sub", "sub"), (d1, d2)
            assert d1["result_id"] and d2["result_id"] and d1["result_id"] != d2["result_id"], "每個領域的結果各自存成 #編號"
            first, second = seen["first"], seen["second"]
            assert first.startswith("【你的子目標】（你要做的只有這個）\n列出 pkg 有哪些檔案"), first[:200]
            assert first.index("【要回答的項目】") < first.index("【這個問題的分工】") < first.index("【使用者的原始問題】（只用來對照"), first
            assert "1. robotics_infra：列出 pkg 有哪些檔案（你）" in first and "2. rmf_dispatch：查調度系統裡有沒有 pkg 的檔案的紀錄（之後由它做）" in first, first
            assert "- 主對話這一回合已經做的：scripts/ls_cmd.py docs → [PASS]" in first and "【前面的領域查到的】" not in first, first
            assert "【前面的領域查到的】（系統從它們的報告取，可以直接用）\n- robotics_infra：pkg 有哪些檔案：pkg 裡有 mod.py 與 use.py（出處：#" in second, second
            assert "1. robotics_infra：列出 pkg 有哪些檔案（做完了，結果在上面）" in second and "2. rmf_dispatch：查調度系統裡有沒有 pkg 的檔案的紀錄（你）" in second
            assert second.count("主對話這一回合已經做的：") == 1, "子工作階段（分工執行期間）的工具不算主對話做的"
            job1 = sub_job(d1["job"])
            anchor = subm.Session._anchor(job1)
            assert "列出 pkg 有哪些檔案" in anchor and "調度系統有沒有它們的紀錄" not in anchor, "提煉的錨點只放子目標與項目"
            text = tools_of(events)[-1]
            assert text.startswith(DOMAIN_RESULT_HEAD + "robotics_infra 的報告（做完") and "\n\nrmf_dispatch 的報告（做完" in text, text[:300]
            assert text.count("這一回合要回答的項目（answers 照這個編號）") == 1 and "這一回合要回答的項目（answers 照這個編號）：\n1. pkg 有哪些檔案\n2. 有沒有紀錄" in text
            shown = chats(events)[-1]
            assert "1. pkg 有哪些檔案：pkg 裡有 mod.py 與 use.py（出處：#" in shown and "2. 有沒有紀錄：查不到。調度系統沒有紀錄" in shown, shown
            calls = [c for c in domain_calls.calls(agent, {"action": two["action"]}, text) if not c.get("via")]
            assert [(c["skill"], c["result_id"], c["sub_status"]) for c in calls] == [("robotics_infra", d1["result_id"], "done"),
                                                                                   ("rmf_dispatch", d2["result_id"], "done")], calls

        def t_plan_known_mid():
            # 分工的後一項是有複合技能的領域（中階）：前面的領域查到的接在中階收到的問題後面（合約可以從那裡抄）；挑技能時子目標在前、
            # 使用者的問題當背景（5-3：挑技能、判斷屬不屬於這個領域只看子目標）
            fin = {"thought": "收尾", "reply": "查到了。", "action": None,
                   "answers": [{"item": 1, "status": "not_found", "text": "（測試）要找的名稱是 alpha", "refs": []}]}
            fake = FakeChat(main=[plan(("rmf_dispatch", "查要找的名稱", ["要找哪個名稱"]), ("repo_analysis", "在 pkg 的 .py 裡找那個名稱定義在哪", ["定義在哪"])), cite],
                            select=[SEL_PY], contract=[con_py()], sub=[fin])
            turn("先查要找的名稱，再找它在 pkg 裡定義在哪", fake)
            d = agent._domain_turn["dispatches"][-1]
            job = mid_job(d["job"])
            assert job["question"].startswith("先查要找的名稱") and "【前面的領域查到的】" in job["question"] and "（測試）要找的名稱是 alpha" in job["question"], job["question"]
            calls = open(os.path.join(tmp, "logs", "mid_jobs", d["job"], "calls.jsonl"), encoding="utf-8").read()
            assert calls.index("【這一層的子目標】") < calls.index("【使用者的原始問題】（背景：裡面其他的事分給了別的領域或主對話"), "挑技能：子目標在前、問題當背景"

        def t_plan_validation():
            # 分工的核對：超過 4 個領域、同一個領域兩次、某一項沒過（寫明第幾項）；沒過就一項都不執行；domains 是空的＝沒有動作
            five = plan(*[(d, "查一下", ["a"]) for d in DOMAINS])
            dup = plan(("robotics_infra", "查 A", ["a"]), ("robotics_infra", "查 B", ["b"]))
            bad2 = plan(("robotics_infra", "查 A", ["a"]), ("nope", "查 B", ["b"]))
            fake = FakeChat(main=[five, dup, bad2, say("好")])
            events, _ = turn("查一下", fake)
            tools = tools_of(events)
            assert tools[0].startswith("[ERROR] 分工列了 5 個領域（要 1～4 個）"), tools[0]
            assert tools[1].startswith("[ERROR] 分工裡 robotics_infra 出現了不只一次"), tools[1]
            assert tools[2].startswith("[ERROR] 分工的第 2 項（nope）：沒有「nope」這個領域"), tools[2]
            assert fake.count("sub") == 0 and agent._domain_turn["dispatches"] == [] and agent._domain_turn["plan"] is None, "沒過就一項都不執行"
            assert agent.parse_reply(json.dumps({"thought": "", "reply": "好", "action": {"domains": []}}))["action"] is None

        def t_plan_pause():
            # 分工的第 1 項停在確認關卡：先問使用者（等回答的說明進主對話），回答之後接回那一項、接著做第 2 項，報告一起交回
            def body():
                def fin_ok(messages):
                    rid = re.findall(r"存檔是 #(\d+)", "\n".join(m["content"] for m in messages))[-1]
                    return {"thought": "收尾", "reply": "寫好了。", "action": None,
                            "answers": [{"item": 1, "status": "answered", "text": "寫好了", "refs": [f"#{rid}"]}]}
                fin2 = {"thought": "收尾", "reply": "好。", "action": None,
                        "answers": [{"item": 1, "status": "not_found", "text": "（測試）沒有紀錄", "refs": []}]}
                fake = FakeChat(main=[plan(("test_ops", "在工作目錄寫 plan_notes", ["寫好了沒"]), ("rmf_dispatch", "查調度系統的紀錄", ["有沒有紀錄"])),
                                      say("好")],
                                sub=[step("file_ops"), step("scripts/file_ops_cmd.py", 'write plan_notes.txt --text "hi"'), fin_ok, fin2])
                events, awaiting = turn("寫 plan_notes，再查調度系統的紀錄", fake)
                assert awaiting and agent.domain_pending["domain"] == "test_ops" and agent._domain_turn["plan"]["next"] == 0, agent.domain_pending
                assert fake.count("sub") == 2, "第 2 項還沒開始"
                last = agent.messages[-1]["content"]
                assert "test_ops 停下來要問使用者" in last and "分工裡還沒做的也會接著做" in last, last
                ev = []
                assert flows.answer_domain_turn("是", ev) is False and agent.domain_pending is None and agent._domain_turn["plan"] is None
                text = tools_of(ev)[0]
                assert text.startswith(DOMAIN_RESULT_HEAD + "使用者回答「是」之後，test_ops 接著做完：test_ops 的報告（做完"), text[:200]
                assert "\n\nrmf_dispatch 的報告（做完" in text and "1. 寫好了沒\n2. 有沒有紀錄" in text and fake.count("sub") == 4, text
                assert os.path.exists(os.path.join(tmp, "plan_notes.txt"))
            with_test_domain(body)

        def t_sub_out_of_domain():
            # 子工作階段一項一項回「不屬於這個領域」（5-3）：每一項都是＝排除這個領域（照中階的處理），沒有報告、分工裡其他的照樣做；
            # 只有幾項：報告寫明，項目照樣要回答；schema 只有子工作階段多 out_of_domain
            ood = {"thought": "不屬於", "reply": "這不是容器的事。", "action": None,
                   "answers": [{"item": 1, "status": "out_of_domain", "text": "問的是程式碼裡的定義", "refs": []}]}
            fin2 = {"thought": "收尾", "reply": "好。", "action": None, "answers": [{"item": 1, "status": "not_found", "text": "（測試）沒有紀錄", "refs": []}]}
            fake = FakeChat(main=[plan(("robotics_infra", "alpha 定義在哪", ["alpha 定義在哪"]), ("rmf_dispatch", "查調度系統的紀錄", ["有沒有紀錄"])),
                                  plan(("robotics_infra", "再查 alpha", ["alpha 在哪"])), say("好")], sub=[ood, fin2])
            events, _ = turn("alpha 定義在哪？調度系統有沒有紀錄？", fake)
            tools = tools_of(events)
            d1, d2 = agent._domain_turn["dispatches"]
            assert d1["status"] == "out_of_domain" and agent._domain_turn["excluded"]["robotics_infra"] == "問的是程式碼裡的定義", d1
            assert "robotics_infra 說它的子目標不屬於它：問的是程式碼裡的定義" in tools[0] and "rmf_dispatch 的報告（做完" in tools[0], tools[0][:400]
            assert agent.domain_items() == ["有沒有紀錄"], "不屬於的那一個沒有報告：項目不算"
            assert tools[1].startswith("[ERROR] 這個問題已經交給過 robotics_infra，它說不屬於它"), tools[1]
            part = {"thought": "收尾", "reply": "一項查不到、一項不屬於。", "action": None, "answers": [
                {"item": 1, "status": "not_found", "text": "（測試）沒有紀錄", "refs": []},
                {"item": 2, "status": "out_of_domain", "text": "設定在工作目錄的檔案", "refs": []}]}
            fake = FakeChat(main=[plan(("rmf_dispatch", "查紀錄與設定", ["有沒有紀錄", "設定檔寫什麼"])), say("好")], sub=[part])
            turn("調度系統有沒有紀錄？設定檔寫什麼？", fake)
            d = agent._domain_turn["dispatches"][-1]
            job = sub_job(d["job"])
            assert d["status"] == "done" and "2. 設定檔寫什麼：不屬於這個領域。設定在工作目錄的檔案" in job["result"]["report"], job["result"]["report"]
            assert agent.domain_items() == ["有沒有紀錄", "設定檔寫什麼"] and "rmf_dispatch" not in agent._domain_turn["excluded"]
            fmt_sub = next(c["format"] for c in fake.calls if c["role"] == "sub")
            assert any("out_of_domain" in sh["properties"]["status"]["enum"] for sh in _answer_shapes(fmt_sub))
            fmt_main = [c["format"] for c in fake.calls if c["role"] == "main"][-1]
            assert all("out_of_domain" not in sh["properties"]["status"]["enum"] for sh in _answer_shapes(fmt_main)), "主對話沒有這一種"

        def t_old_archive_ref():
            # 主對話的核對不收報告文字裡出現、但不是這一回合的工具結果的 #編號（5-3）：子工作階段引用之前的存檔、自己的核對標了沒過，
            # 主對話照樣引用也擋
            ollama.chat = FakeChat()
            agent.set_current_task("先列一下 docs")
            agent.run_tool({"action": {"command": "scripts/ls_cmd.py", "args": "docs"}})
            old = agent.last_result_id
            stale = {"thought": "收尾", "reply": "照之前的結果。", "action": None,
                     "answers": [{"item": 1, "status": "answered", "text": "docs 有 guide.md", "refs": [f"#{old}"]}]}
            fake = FakeChat(main=[dispatch("現在 docs 裡有哪些檔案", ["有哪些檔案"], domain="robotics_infra"),
                                  answer("見報告。", [(1, "answered", "docs 有 guide.md", [f"#{old}"])]), say("好")], sub=[stale, stale])
            turn("docs 現在有哪些檔案？", fake)
            job = sub_job(agent._domain_turn["dispatches"][-1]["job"])
            assert f"⚠️ 沒有通過核對：出處 #{old} 不在這個子工作階段的工具結果裡" in job["result"]["report"], job["result"]["report"]
            assert agent._cited(f"#{old}")[0] == "unknown", "報告裡寫了、但不是這一回合的工具結果：不算出處"
            nudges = [m["content"] for m in agent.messages if m["role"] == "user" and m["content"].startswith("【系統核對】")]
            assert nudges and f"出處 #{old} 不在這一回合的報告與工具結果裡" in nudges[-1], nudges[-1:]

        def t_sub_prompt():
            # 子工作階段的說明：兩階段協議那幾行照抄 AGENT.md（跟主對話同一份寫法與範例）；只做子目標、做不到的寫還需要什麼、不屬於、
            # 現在的狀態要重查
            with open(os.path.join(tmp, "prompts", "AGENT.md"), encoding="utf-8") as f:
                prof = f.read().split("\n")
            i = next(k for k, ln in enumerate(prof) if ln.startswith("2. **兩階段執行"))
            rows = []
            for ln in prof[i + 1:]:
                if not ln.startswith("   - "):
                    break
                rows.append(ln)
            rows += [ln for ln in prof if ln.startswith(("   - 範例（選取技能，取得規格）", "   - 範例（依規格內容執行）"))]
            system = agent._sub("robotics_infra")._system()
            assert len(rows) == 7 and all(r in system for r in rows), [r for r in rows if r not in system]
            for want in ("只做【你的子目標】", "不要用這個領域的工具繞過去做", "status 寫 out_of_domain", "問的是現在的狀態", "用工具重新查"):
                assert want in system, want

        def t_reply_order():
            # 回覆的欄位順序就是生成順序（Ollama 照 schema 的順序輸出）：action 一律放最後。主對話（有沒有 answers）與子工作階段的 schema、
            # AGENT.md 與子工作階段說明裡的每個範例都照這個順序、寫完 action 就結束；存回對話的 JSON（drop_cut）也一樣。answers 排在 action
            # 後面時，模型照範例寫完 action 要收尾的 `"}}` 不合法，結尾的符號寫進了 args（第 5 步 5-3 的評測）
            from agent_core.config import REPLY_ARGS_CHARS
            from agent_core.protocol import drop_cut, parse_agent_reply
            orders = [list(agent_reply_schema(agent.domain_names())["properties"]),
                      list(agent_reply_schema(agent.domain_names(), 2)["properties"]),
                      list(agent_reply_schema((), 2, others=["rmf_dispatch"])["properties"])]
            full = ["thought", "reply", "answers", "action"]
            assert orders == [["thought", "reply", "action"], full, full], orders
            with open(os.path.join(tmp, "prompts", "AGENT.md"), encoding="utf-8") as f:
                texts = {"AGENT.md": f.read(), "子工作階段": agent._sub("robotics_infra")._system()}
            counts = {}
            for where, text in texts.items():
                for ex in re.findall(r"範例（[^）]*）：`([^`]+)`", text):
                    keys = list(json.loads(ex))
                    assert keys == [k for k in full if k in keys] and keys[-1] == full[-1], (where, keys)
                    counts[where] = counts.get(where, 0) + 1
            assert counts == {"AGENT.md": 4, "子工作階段": 2}, counts
            parsed = parse_agent_reply(json.dumps({"thought": "t", "reply": "r", "action": {"command": "c", "args": "a" * REPLY_ARGS_CHARS}}))
            _, raw = drop_cut(parsed)
            assert parsed["cut"] == ["args"] and list(json.loads(raw)) == full and json.loads(raw)["action"] is None, raw[:200]

        def t_sub_route():
            # 5-4：子工作階段查不到、不屬於的那一項寫哪個領域查得到（schema 的欄位：答到的沒有，查不到、不屬於的一定有，選項是其他領域與
            # none）；報告寫明，分工的結果後面列「第 N 項：X 說要交給 Y 查」，主模型照它再分工（程式不自己再交）；Y 查過這一項、說過不屬於的附上
            from agent_core.protocol import parse_agent_reply
            seen = {}

            def fin1(messages):
                rid = re.findall(r"存檔是 #(\d+)", "\n".join(m["content"] for m in messages))[-1]
                return {"thought": "收尾", "reply": "一項查到、一項要調度系統。", "action": None, "answers": [
                    {"item": 1, "status": "answered", "text": "pkg 裡有 mod.py 與 use.py", "refs": [f"#{rid}"]},
                    {"item": 2, "status": "not_found", "text": "（測試）站點的名稱不在容器裡", "refs": [], "domain": "rmf_dispatch"}]}

            def redo(messages):
                seen["routes"] = last_report(messages)
                return plan(("rmf_dispatch", "查站點的名稱", ["站點叫什麼"]))

            def fin2(messages):
                return {"thought": "收尾", "reply": "查不到。", "action": None, "answers": [
                    {"item": 1, "status": "not_found", "text": "（測試）語義地圖沒有名稱", "refs": [], "domain": "none"}]}

            def main_ans(messages):
                seen["second"] = last_report(messages)
                rid = agent._domain_turn["dispatches"][0]["result_id"]
                return answer("見報告。", [(1, "answered", "pkg 裡有 mod.py 與 use.py", [f"#{rid}"]), (2, "not_found", "語義地圖沒有名稱", [])])
            fake = FakeChat(main=[plan(("robotics_infra", "列出 pkg 的檔案、查站點的名稱", ["pkg 有哪些檔案", "站點叫什麼"])), redo, main_ans],
                            sub=[step("list_dir"), step("scripts/ls_cmd.py", "pkg"), fin1, fin2])
            events, _ = turn("pkg 有哪些檔案？站點叫什麼？", fake)
            fmt = next(c["format"] for c in fake.calls if c["role"] == "sub")
            shapes = _answer_shapes(fmt)
            assert [sh["properties"]["status"]["enum"] for sh in shapes] == [["answered"], ["not_found", "out_of_domain"]], shapes
            assert "domain" not in shapes[0]["properties"] and shapes[1]["required"][-1] == "domain", "答到的沒有 domain；查不到的一定有、排在最後"
            assert shapes[1]["properties"]["domain"]["enum"] == [d for d in DOMAINS if d != "robotics_infra"] + ["none"], shapes[1]
            d1, d2 = agent._domain_turn["dispatches"]
            system = sub_job(d1["job"])["system"]
            assert "## 其他領域（查不到、不屬於的那一項，domain 寫哪一個查得到；都不是寫 none）" in system, system
            assert "- rmf_dispatch：調度系統 — 調度系統的工作包" in system and "- robotics_infra：" not in system, "列其他領域（標題與說明的第一行），沒有自己"
            report = sub_job(d1["job"])["result"]["report"]
            assert "2. 站點叫什麼：查不到。（測試）站點的名稱不在容器裡（查得到的領域：rmf_dispatch）" in report, report
            assert sub_job(d1["job"])["answers"][1]["domain"] == "rmf_dispatch" and sub_job(d1["job"])["answers"][0]["domain"] == ""
            routes = seen["routes"]
            want = "- 第 2 項（站點叫什麼）：robotics_infra 說要交給 rmf_dispatch 查"
            assert want + "\n" in routes and routes.index(want) < routes.index("這一回合要回答的項目（answers 照這個編號）"), routes
            assert d2["domain"] == "rmf_dispatch" and d2["items"] == ["站點叫什麼"] and fake.count("sub") == 4, "主模型照它再分工"
            assert "說要交給" not in seen["second"].split("rmf_dispatch 的報告")[1] and "（查得到的領域" not in seen["second"], "none 不列"
            shown = chats(events)[-1]
            assert "2. 站點叫什麼：查不到。語義地圖沒有名稱" in shown, shown
            # 兩個領域同一項都查不到、互相說對方查得到：程式附上「這一回合查過這一項」；說了不屬於自己的領域（排除）也附上
            nf = lambda to: {"thought": "收尾", "reply": "查不到。", "action": None,
                             "answers": [{"item": 1, "status": "not_found", "text": "（測試）沒有", "refs": [], "domain": to}]}
            ood = {"thought": "不屬於", "reply": "不是調度的事。", "action": None,
                   "answers": [{"item": 1, "status": "out_of_domain", "text": "（測試）是容器的事", "refs": [], "domain": "robotics_infra"}]}
            fake = FakeChat(main=[plan(("robotics_infra", "查 A", ["A 在哪"]), ("multimodal", "查 A", ["A 在哪"]), ("rmf_dispatch", "查 B", ["B 在哪"])),
                                  say("好")], sub=[nf("multimodal"), nf("robotics_infra"), ood])
            events, _ = turn("A 在哪？B 在哪？", fake)
            text = tools_of(events)[-1]
            for want in ("- 第 1 項（A 在哪）：robotics_infra 說要交給 multimodal 查（multimodal 這一回合查過這一項：做完）",
                         "- 第 1 項（A 在哪）：multimodal 說要交給 robotics_infra 查（robotics_infra 這一回合查過這一項：做完）",
                         "- 「B 在哪」：rmf_dispatch 說要交給 robotics_infra 查"):
                assert want in text, (want, text)
            assert agent._domain_turn["excluded"] == {"rmf_dispatch": "（測試）是容器的事"} and agent.domain_items() == ["A 在哪"]
            # 回答的解析：答到的不留 domain；查不到的照寫（none 也照寫，報告與列出時才不算）；主對話的 schema 沒有 domain
            got = parse_agent_reply(json.dumps({"thought": "", "reply": "", "action": None, "answers": [
                {"item": 1, "status": "answered", "text": "a", "refs": ["#1"], "domain": "rmf_dispatch"},
                {"item": 2, "status": "not_found", "text": "b", "refs": [], "domain": "none"}]}))["answers"]
            assert [a["domain"] for a in got] == ["", "none"], got
            assert all("domain" not in sh["properties"] for sh in _answer_shapes(agent_reply_schema(agent.domain_names(), 2)))

        def t_gate_composite():
            # 5-4：主對話叫複合技能的名稱（或規格檔名）回交給哪個領域（以前落到「沒有這個技能（已經移除的名稱）」）；子工作階段裡也擋
            fake = FakeChat(main=[step("py_usage"), step("doc_lookup.md"), step("no_such_skill"), say("好")])
            events, _ = turn("找 alpha", fake)
            tools = tools_of(events)
            assert tools[0].startswith("[ERROR] py_usage 是 repo_analysis 領域寫好的做法（複合技能）") and \
                '「分工」{"domains": [{"domain": "repo_analysis"' in tools[0], tools[0]
            assert tools[1].startswith("[ERROR] doc_lookup 是 repo_analysis 領域寫好的做法"), tools[1]
            assert tools[2].startswith("[ERROR] 沒有 `no_such_skill` 這個技能"), "不是任何技能的照舊"
            assert agent.domain_gate("scripts/py_usage_cmd.py").startswith("[ERROR] py_usage 是 repo_analysis 領域寫好的做法"), "寫成腳本的複合技能也擋"
            reg = agent.domain_registry()
            assert reg["skills"]["py_usage"] == "repo_analysis" and set(reg["skills"]) == set(reg["domains"]["repo_analysis"]["skills"])
            agent._sub_allowed = {"domain": "robotics_infra", "tools": set(reg["domains"]["robotics_infra"]["tools"] + reg["shared"])}
            try:
                blocked = agent.domain_gate("py_usage")
                assert blocked.startswith("[ERROR] py_usage 不是 robotics_infra 這個領域的工具"), blocked
                assert agent.domain_gate("list_dir") is None and agent.domain_gate("no_such_skill") is None
            finally:
                agent._sub_allowed = None

        for name, fn in [("領域：system prompt 的「領域」一節、技能索引拿掉領域的工具、schema 多「分工」；沒有 DOMAIN.md 時照舊", t_registry),
                         ("擋領域的工具：技能名稱、腳本、規格都擋，其他技能與共用的工具（列目錄、找檔案、回顧存檔）照舊", t_gate),
                         ("交給領域 → 中階 → 報告存成 #編號 交回主模型（不提煉），決策圖的連結先推給畫面；使用者看到照項目排好的回答", t_dispatch_report),
                         ("依報告回答的 schema：有報告時多 answers（項目的編號，排在 action 前面），新的問題歸零", t_answers_schema),
                         ("find_lines 的報告列出提到的行（檔案:行號：內容），主模型照它寫的出處通過核對、回答附那一行的原文", t_find_lines_cite),
                         ("answers 的核對：出處不在報告、數字不在出處那幾段、查不到沒寫原因、少一項、寫法看不懂、reply 的出處；只把沒過的交回修一次",
                          t_answers_fix),
                         ("answers 修過一次還是沒過：照樣結束，那一項標「沒有通過核對」附報告的 #編號", t_answers_fail_twice),
                         ("這一回合自己執行過的工具結果也算出處：共用的工具存檔的 #編號；報告與收據裡都沒有的行不算", t_answers_own_results),
                         ("帶著上一次的經過再交：中階停下來的原因與子工作階段做到的都交給中階、第幾次、幾次串起來（中階與子工作階段之間也連）",
                          t_redispatch_previous),
                         ("一樣的技能與參數：合約交回修一次，還是一樣就停（跟之前一樣），照報告回答、照舊擋", t_repeated),
                         ("A″（開關）：中階跑過、有結果、但沒做完 → 第一次的報告照樣交回，中階帶著查到的再做一次（合約可以抄查到的），"
                          "兩份報告照著回答與核對、評測記兩次；再做的沒有報告照第一份回答；不開子工作階段；沒觸發與開關關照舊", t_mid_retry),
                         ("同一個項目最多交 3 次：第 4 次程式擋下來", t_item_tries),
                         ("核對：沒有的領域、子目標是空的、項目數、一樣的再交一次", t_validation),
                         ("沒有適合的做法：接著開子工作階段一步一步做（主對話看不到試錯、照舊擋）；報告附每一項的回答、出處的原文與每一步；評測照 via 記",
                          t_no_skill_sub),
                         ("子工作階段的回答內文寫「檔案:行號」、出處寫 #編號：內文的照收據核對（待辦 4l ①：收據裡有的通過，沒有的照樣擋）",
                          t_sub_inline_cite),
                         ("不屬於這個領域：排除，再交時附這一回合做過的事；不開子工作階段、也不放行", t_out_of_domain),
                         ("問使用者（Web）：停下來、回答不合法再問、回答之後接回同一個工作", t_ask_web),
                         ("問使用者：取消（接著開子工作階段）、/clear 一起取消（不接著做）", t_ask_cancel),
                         ("問使用者（CLI）：輸入回答、0 取消", t_cli),
                         ("問使用者（經過 Web 伺服器）：/api/send 打字回答、/api/decision 取消、有問題時斜線指令被擋", t_http),
                         ("評測的 worker 怎麼記：領域與領域裡用到的工具、沒人回答就取消、依報告回答的 answers 與照項目排好的回覆", t_worker_record),
                         ("子工作階段：沒有複合技能的領域直接開（不挑技能）、〈做法〉與能用的工具、確認關卡停下來（Web）同意接回、不同意交 [DENIED]",
                          t_sub_domain_guard),
                         ("子工作階段的上限與收尾：不是這個領域的工具擋下來、卡住、步數用完、出處不是自己的工具結果交回修一次再標出來", t_sub_limits),
                         ("子工作階段的回覆：沒有動作也沒有回答提醒一次（不算交回修）、收尾寫成 {\"command\": \"null\"}、寫到長度上限被截斷的不執行"
                          "（重問一次，還是被截斷就不執行）", t_sub_protocol),
                         ("子工作階段的長輸出照舊提煉，結尾的下一步建議只寫它能用的 result_grep、result_view（待辦 4k ①：不寫 result_recall、"
                          "不叫它問使用者）", t_sub_followup),
                         ("決策圖：子工作階段在清單裡、整理成每一步與收尾的回答、串起上一次", t_sub_topology),
                         ("凍結的四個領域（5-2）：「領域」一節、索引拿掉它們的工具與整節的說明、子工作階段的工具帶那一節的說明、〈做法〉搬過去、擋與放行",
                          t_frozen_domains),
                         ("數據分析在子工作階段裡（G4）：報告原樣附上、主對話照它核對回答（answers 寫成因果提醒一次）、之後的回合也核對", t_sub_analysis),
                         ("分工（5-3）：兩個領域照順序做、後面的收到前面查到的與分工（主對話做過的）、子目標在前、錨點只放子目標、報告一起交回、"
                          "評測每個領域記一筆", t_plan_two_domains),
                         ("分工的後一項是中階：前面查到的接在問題後面；挑技能時子目標在前、問題當背景", t_plan_known_mid),
                         ("分工的核對：超過 4 個、同一個領域兩次、第幾項沒過；沒過就一項都不執行", t_plan_validation),
                         ("分工停在確認關卡：先問使用者，回答之後接回、接著做下一項，報告一起交回", t_plan_pause),
                         ("子工作階段回「不屬於這個領域」：每一項都是＝排除（分工裡其他的照做）、只有幾項寫進報告；只有子工作階段的 schema 有",
                          t_sub_out_of_domain),
                         ("主對話的核對不收報告文字裡出現、不是這一回合工具結果的 #編號（子工作階段引用舊存檔）", t_old_archive_ref),
                         ("子工作階段的說明：兩階段協議照抄 AGENT.md、只做子目標、做不到寫還需要什麼、不屬於、現在的狀態要重查", t_sub_prompt),
                         ("回覆的欄位順序：action 放最後（主對話、子工作階段的 schema，每個範例的結尾，存回對話的 JSON）", t_reply_order),
                         ("查得到的領域（5-4）：子工作階段查不到、不屬於的寫哪個領域查得到（schema 的欄位），報告寫明、分工的結果列出、主模型照它再分工；"
                          "查過、排除的附上", t_sub_route),
                         ("擋複合技能的名稱（5-4）：主對話回交給哪個領域、子工作階段裡也擋，不是任何技能的照舊", t_gate_composite)]:
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
