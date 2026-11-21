"""方向的實驗：公佈欄的 worker（agent_core/board.py）的離線自我測試：假的模型照劇本回（規劃、提煉、回答、主模型），真的低階、提煉的核對與工具
（工作目錄是臨時的小專案），幾秒跑完、不需要 Ollama。

- 一步一步：規劃 → 低階執行（決策圖一步長一個節點，跑過的不重跑）→ 提煉成事實（輸出的行號換成 檔案:行號、附那一行的原文；對不上原文的拿掉；
  程式算好的數量另外記一則）→ 照事實回答（答到的要有事實、名稱與數值在事實裡；沒過交回修一次）→ 報告；
- 公佈欄給規劃看的文字：原始問題、項目與事實的數量、事實（F 編號與出處）、試過的步驟（[ERROR] 附下一步、0 筆、跟第幾步一樣）、還能走幾步；
- 上限：跟之前一樣的工具與參數擋下（連續兩次＝卡住）、步數用完、規劃的模型沒有回覆、回答的模型沒有回覆、每一項都不屬於這個領域；
- 輸出的行號 → 檔案:行號（search_text 的 `## 檔案` 與 `120→`、view_file 的收據、py_refs 與 code_defs 的 `行 120`）；規劃看到的工具用法從規格取；
- 接上高階（設定 AGENT_DOMAIN_BOARD）：分工交給公佈欄、報告一項一項、主對話照 4-2 依報告回答（出處是公佈欄的 檔案:行號）、交給後面的領域的
  「前面查到的」、主對話不能直接用〈公佈欄的工具〉、評測的 worker 怎麼記、Web 的決策圖（清單、每一步、長出來的圖）。

    python3 evals/board/selftest.py
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
FILES = {
    "pkg/mod.py": "def alpha(x):\n    return x + 1\n\n\ndef beta():\n    return alpha(2)\n",
    "pkg/use.py": "from pkg.mod import alpha\n\n\ndef gamma():\n    return alpha(3)\n",
    "config/robots.yaml": "robots:\n  - id: r1\n    max_speed: 1.5\n  - id: r2\n    max_speed: 0.8\n",
    "docs/guide.md": "# 指南\n\n## 啟動\n\n啟動前先檢查電源。\n",
}
ITEMS = ["alpha 定義在哪", "誰呼叫 alpha"]


def body_line(msgs, needle):
    """提煉的 user 訊息裡（`  12→內容`），第一個含 needle 的那一行的輸出行號。"""
    for ln in msgs[-1]["content"].split("\n"):
        m = re.match(r"^[ >]\s*(\d+)→(.*)$", ln)
        if m and needle in m.group(2):
            return m.group(1)
    raise AssertionError(f"輸出裡沒有 {needle}：{msgs[-1]['content'][-600:]}")


def plan(tool, args, look_for="找", item=0, understanding="還缺事實"):
    return {"understanding": understanding, "next": "tool", "item": item, "look_for": look_for, "tool": tool, "args": list(args)}


ANSWER_NOW = {"understanding": "事實夠了", "next": "answer", "item": 0, "look_for": "", "tool": "none", "args": []}


def answer(*rows):
    return {"answers": [{"item": k, "status": st, "text": t, "facts": list(f)} for k, st, t, f in rows]}


class FakeChat:
    """假的 ollama.chat：照 format 的欄位分角色（規劃、提煉、回答、主模型、第 1 級修正），各自依序取劇本；一則可以是函式（看訊息決定回什麼）。"""

    def __init__(self, plan=(), look=(), answer=(), main=()):
        self.q = {"plan": list(plan), "look": list(look), "answer": list(answer), "main": list(main)}
        self.calls = []

    @staticmethod
    def role(fmt):
        props = set((fmt or {}).get("properties", {})) if isinstance(fmt, dict) else set()
        if "look_for" in props:
            return "plan"
        if props == {"relevant", "facts"}:
            return "look"
        if props == {"answers"}:
            return "answer"
        if "action" in props:
            return "main"
        if "fixable" in props:
            return "fix"
        return "other"

    def __call__(self, model=None, messages=None, format=None, **kw):
        role = self.role(format)
        self.calls.append({"role": role, "messages": messages, "format": format})
        if role == "fix":
            data = {"reason": "（測試）修不好", "fixable": False, "args": []}
        elif role == "other":
            data = {"answer": "（摘要）", "facts": [], "errors": [], "not_covered": "無", "suggested_questions": [], "index_hint": "（摘要）",
                    "related_records": [], "relevant": False, "summary": ""}
        else:
            q = self.q[role]
            if q:
                item = q.pop(0)
            elif role == "plan":
                item = ANSWER_NOW
            elif role == "look":
                item = {"relevant": False, "facts": []}
            elif role == "main":
                item = {"thought": "", "reply": "好的。", "action": None}
            else:
                item = None
            data = item(messages) if callable(item) else item
        return {"message": {"content": json.dumps(data, ensure_ascii=False) if data is not None else ""},
                "prompt_eval_count": 100, "eval_count": 20}

    def count(self, role):
        return sum(1 for c in self.calls if c["role"] == role)

    def users(self, role):
        return [c["messages"][-1]["content"] for c in self.calls if c["role"] == role]


def make_env():
    tmp = tempfile.mkdtemp(prefix="board_selftest_")
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
    sys.path.append(PROJECT)                  # evals/domain_calls.py 從專案讀
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
        from agent_core import board, orchestrator
        from agent_core.config import DOMAIN_RESULT_HEAD
        from web_app import flows, topology
        from web_app.state import agent, state
        agent.current_cwd = tmp
        state["auto_mode"] = True
        reg = agent.domain_registry()["domains"]["repo_analysis"]

        def worker():
            return board.Worker(agent, "repo_analysis", tools=reg["board_tools"], title=reg["title"], intro=reg["intro"])

        def run(fake, question="pkg 裡的 alpha 定義在哪、誰呼叫它？", items=ITEMS, **kw):
            ollama.chat = fake
            agent.current_cwd = tmp
            return worker().start(question, "在 pkg 的 .py 裡找 alpha 的定義與呼叫", items, **kw)

        def edg_job(eid):
            with open(os.path.join(tmp, "logs", "edg_jobs", eid, "job.json"), encoding="utf-8") as f:
                return json.load(f)

        def look_alpha(msgs):
            return {"relevant": True, "facts": [
                {"text": "alpha 定義在 pkg/mod.py 第 1 行", "lines": body_line(msgs, "定義 行 1-2")},
                {"text": "beta 在 pkg/mod.py 第 6 行呼叫 alpha", "lines": body_line(msgs, "（在 beta）")},
                {"text": "gamma 在 pkg/use.py 第 5 行呼叫 alpha", "lines": body_line(msgs, "（在 gamma）")},
                {"text": "delta_fn 在 pkg/mod.py 呼叫 alpha", "lines": body_line(msgs, "（在 beta）")}]}

        def t_steps():
            fake = FakeChat(plan=[plan("py_refs", ["alpha", "pkg"], "alpha 的定義與每一處呼叫"), ANSWER_NOW], look=[look_alpha],
                            answer=[answer((1, "answered", "alpha 定義在 pkg/mod.py:1", [2]),
                                           (2, "answered", "beta（pkg/mod.py:6）與 gamma（pkg/use.py:5）", [3, 4]))])
            job = run(fake)
            assert job["status"] == "done" and job["kind"] == "board" and not job["problems"], (job["status"], job["problems"])
            st = job["steps"][0]
            assert st["status"] == "PASS" and st["facts"] == [1, 2, 3, 4] and st["dropped"] == 1, ("程式的事實一則、提煉三則、對不上原文的拿掉一則", st)
            f1, f2 = job["facts"][0], job["facts"][1]
            assert f1["source"] == "程式" and f1["text"].startswith("py_refs「alpha」4 處、2 份檔案：定義 1、呼叫 2、import 1") and f1["refs"] == [f"#{st['result_id']}"], f1
            assert "pkg/mod.py 2 處（呼叫 1、定義 1）" in f1["text"], f1["text"]
            assert f2["refs"] == ["pkg/mod.py:1", f"#{st['result_id']}"] and f2["rows"] == ["pkg/mod.py:1：def alpha(x):"], "輸出的行號換成 檔案:行號，附那一行的原文"
            assert job["facts"][3]["refs"][0] == "pkg/use.py:5", job["facts"][3]
            assert not any("delta_fn" in f["text"] for f in job["facts"]), "名稱不在引用的那幾行：程式拿掉"
            assert job["answers"][1]["refs"] == ["pkg/mod.py:6", f"#{st['result_id']}", "pkg/use.py:5"], job["answers"][1]
            ej = edg_job(job["edg_job"])
            assert [n["id"] for n in ej["graph"]["nodes"]] == ["s1"] and ej["nodes"]["s1"]["state"] == "done", "這一步是低階決策圖上的一個節點"
            rep = job["result"]["report"]
            assert rep.startswith("# 公佈欄的結果：做完") and "## 公佈欄的事實" in rep and "   > pkg/mod.py:1：def alpha(x):" in rep, rep
            assert "1. alpha 定義在哪：alpha 定義在 pkg/mod.py:1（出處：pkg/mod.py:1）（根據 F2）" in rep, rep
            with open(os.path.join(tmp, "logs", "board_jobs", job["id"], "calls.jsonl"), encoding="utf-8") as f:
                calls = [json.loads(x) for x in f]
            assert [(c["role"], c.get("step")) for c in calls] == [("plan", 1), ("plan", 2), ("answer", None)], calls
            board_text = fake.users("plan")[1]
            for want in ("【使用者的原始問題】\npkg 裡的 alpha", "1. alpha 定義在哪（還沒有事實）" if False else "1. alpha 定義在哪（", "F2（第 1 步）：alpha 定義在 pkg/mod.py 第 1 行（出處：pkg/mod.py:1、#",
                         "第 1 步（為好幾項找：alpha 的定義與每一處呼叫）：py_refs alpha pkg → py_refs「alpha」4 處", "；新的事實 F1、F2、F3、F4", "【還能走】11 步"):
                assert want in board_text, (want, board_text)
            look_user = fake.users("look")[0]
            assert "【這一步特別要找的】（為好幾項；原文裡回答其他項目的事實也要摘）\nalpha 的定義與每一處呼叫" in look_user and "【這份輸出】py_refs alpha pkg（#" in look_user, look_user[:600]

        def t_answer_fix():
            fake = FakeChat(plan=[plan("py_refs", ["alpha", "pkg"]), ANSWER_NOW], look=[look_alpha],
                            answer=[answer((1, "answered", "alpha 定義在 pkg/mod.py:12", [2]), (2, "answered", "beta 與 gamma", [])),
                                    answer((1, "answered", "alpha 定義在 pkg/mod.py:1", [2]), (2, "answered", "beta 與 gamma 呼叫", [3, 4]))])
            job = run(fake)
            assert job["nudged"] and not job["problems"] and job["answers"][0]["text"] == "alpha 定義在 pkg/mod.py:1", job["answers"]
            fix = fake.users("answer")[1]
            assert "【系統核對】" in fix and re.search(r"第 1 項（alpha 定義在哪）：「[^」]*pkg/mod\.py:12[^」]*」在根據的事實裡找不到", fix), fix[-500:]
            assert "第 2 項（誰呼叫 alpha）：答到的要在 facts 寫根據的事實編號" in fix, fix[-500:]
            fake = FakeChat(plan=[plan("py_refs", ["alpha", "pkg"]), ANSWER_NOW], look=[look_alpha],
                            answer=[answer((1, "answered", "alpha 定義在 pkg/mod.py:12", [2]), (2, "not_found", "", [])),
                                    answer((1, "answered", "alpha 定義在 pkg/mod.py:99", [2]), (2, "not_found", "", []))])
            job = run(fake)
            assert set(job["problems"]) == {"1", "2"} and "pkg/mod.py:99" in job["problems"]["1"][0] and job["problems"]["2"] == ["查不到、不屬於這個領域要寫原因"], job["problems"]
            assert "⚠️ 沒有通過核對：「" in job["result"]["report"] and "pkg/mod.py:99" in job["result"]["report"], "修過一次還是沒過：報告標出來"

        def t_repeat_error():
            def look_yaml(msgs):
                return {"relevant": True, "facts": [{"text": "config/robots.yaml 第 3 行 max_speed: 1.5", "lines": body_line(msgs, "1.5")}]}
            assert board._split_include(["x", ".", "--include", "*.cpp|*.h", "-w", "--include", "*.py"]) == ["x", ".", "--include", "*.cpp", "--include", "*.h", "-w", "--include", "*.py"]
            fake = FakeChat(plan=[plan("view_file", ["nope.txt"], "設定"), plan("search_text", ["max_speed", "config"], "每台的 max_speed", 1),
                                  plan("search_text", ["max_speed", "config"]), plan("search_text", ["max_speed", "config"]),
                                  plan("list_dir", ["."])],
                            look=[look_yaml], answer=[answer((1, "answered", "r1 的 max_speed 是 1.5", [2]))])
            job = run(fake, question="config 裡 r1 的 max_speed 是多少？", items=["r1 的 max_speed"])
            assert [s["status"] for s in job["steps"]] == ["ERROR", "PASS", "REPEAT", "REPEAT"], [s["status"] for s in job["steps"]]
            assert job["status"] == "stopped" and "卡住" in job["stop"] and fake.count("plan") == 4, "連續兩次擋下＝卡住：不再規劃，照事實回答"
            assert job["steps"][0]["head"].startswith("[ERROR] 找不到檔案") and job["steps"][2]["head"] == "跟第 2 步一樣（同樣的工具與參數），沒有執行"
            assert [n["id"] for n in edg_job(job["edg_job"])["graph"]["nodes"]] == ["s1", "s2"], "擋下的重複不排進圖"
            assert job["facts"][0]["text"] == "search_text「max_speed」共 2 筆、1 個檔案：config/robots.yaml 2 筆", job["facts"][0]
            assert job["facts"][1]["refs"][0] == "config/robots.yaml:3", job["facts"][1]
            text = fake.users("plan")[3]
            assert "第 1 步（為好幾項找：設定）：view_file nope.txt → [ERROR] 找不到檔案" in text and "第 3 步（為好幾項找：找）：search_text max_speed config → 跟第 2 步一樣" in text, text
            assert "1. r1 的 max_speed（2 則事實）" in text, text

        def t_limits():
            old = board.BOARD_STEPS_MAX
            board.BOARD_STEPS_MAX = 2
            try:
                fake = FakeChat(plan=[plan("list_dir", ["pkg"]), plan("find_file", ["*.py", "pkg"]), plan("list_dir", ["docs"])],
                                answer=[answer((1, "not_found", "沒有找到", []), (2, "not_found", "沒有找到", []))])
                job = run(fake)
            finally:
                board.BOARD_STEPS_MAX = old
            assert job["status"] == "stopped" and job["stop"].startswith("步數用完（最多 2 步）") and fake.count("plan") == 2, job["stop"]
            assert job["facts"] and job["facts"][-1]["text"].startswith("find_file「*.py」找到 2 個（檔案 2、目錄 0）：pkg/mod.py、pkg/use.py"), job["facts"]
            fake = FakeChat(plan=[None, None], answer=[answer((1, "not_found", "還沒查", []), (2, "not_found", "還沒查", []))])
            job = run(fake)
            assert job["status"] == "stopped" and "規劃的模型沒有回覆" in job["stop"] and not job["steps"], job["stop"]
            fake = FakeChat(plan=[ANSWER_NOW], answer=[None, None])
            job = run(fake)
            assert job["status"] == "failed" and "回答的模型沒有回覆" in job["result"]["note"] and job["answers"] == []
            fake = FakeChat(plan=[ANSWER_NOW], answer=[answer((1, "out_of_domain", "要問正在跑的系統", []), (2, "out_of_domain", "同上", []))])
            job = run(fake)
            assert job["status"] == "out_of_domain" and job["result"]["note"] == "要問正在跑的系統；同上", job["result"]

        def t_locations():
            out = agent.run_script("grep_cmd.py", ["alpha", "pkg"], "alpha pkg")
            lines = out.split("\n")
            locs = board._locations(lines, agent.last_receipt, tmp)
            hits = sorted(set(locs.values()))
            assert (os.path.join(tmp, "pkg", "mod.py"), 1) in hits and (os.path.join(tmp, "pkg", "use.py"), 5) in hits, hits
            out = agent.run_script("cat_cmd.py", ["pkg/use.py"], "pkg/use.py")
            locs = board._locations(out.split("\n"), agent.last_receipt, tmp)
            assert sorted(locs.values())[:2] == [(os.path.join(tmp, "pkg", "use.py"), 1), (os.path.join(tmp, "pkg", "use.py"), 2)], locs
            out = agent.run_script("code_defs_cmd.py", ["pkg"], "pkg")
            locs = board._locations(out.split("\n"), agent.last_receipt, tmp)
            assert (os.path.join(tmp, "pkg", "use.py"), 4) in locs.values(), (out, locs)
            usage = board.tool_usage(agent.tools_dir, "search_text")
            assert usage.startswith("### search_text：在檔案「內部文字」裡搜關鍵字") and "EXECUTE: scripts/grep_cmd.py" in usage, usage
            fake = FakeChat(plan=[ANSWER_NOW], answer=[answer((1, "not_found", "x", []), (2, "not_found", "x", []))])
            run(fake)
            system = next(c["messages"][0]["content"] for c in fake.calls if c["role"] == "plan")
            assert all(f"### {t}：" in system for t in reg["board_tools"]) and "result_view" not in system, "規劃看到〈公佈欄的工具〉的用法"
            assert fake.calls[0]["format"]["properties"]["tool"]["enum"] == reg["board_tools"] + ["none"]

        def t_unseen():
            seen = {}

            def look_view(msgs):
                seen["body"] = msgs[-1]["content"]
                return {"relevant": True, "facts": [{"text": "alpha 回傳 x + 1", "lines": body_line(msgs, "return x + 1")}]}
            with open(os.path.join(tmp, "big.txt"), "w", encoding="utf-8") as f:
                f.write("".join(f"foo {k}\n" for k in range(25)))
            with open(os.path.join(tmp, "docs", "more.txt"), "w", encoding="utf-8") as f:
                f.write("foo\n")
            fake = FakeChat(plan=[plan("view_file", ["pkg/mod.py", "--lines", "2"], "alpha 的實作"), plan("search_text", ["foo", ".", "--include", "*.txt"])],
                            look=[look_view], answer=[answer((1, "answered", "alpha 回傳 x + 1", [1]), (2, "not_found", "沒有找", []))])
            job = run(fake)
            body = seen["body"].split("【這一段的原文】", 1)[1]
            assert "    3→    return x + 1" in body and "    2→def alpha(x):" in body and not re.search(r"\d→\s*\d+→", body), ("提煉只看到一種行號", body)
            f1 = job["facts"][0]
            assert f1["refs"][0] == "pkg/mod.py:2" and f1["rows"] == ["pkg/mod.py:2：return x + 1"], ("輸出的第 3 行是檔案的第 2 行", f1)
            assert job["steps"][0]["summary"] == "pkg/mod.py 第 1～2 行（共 6 行）；還有第 3～6 行沒有看（view_file pkg/mod.py --from 3）", job["steps"][0]["summary"]
            assert "只列了前面幾筆" in job["steps"][1]["summary"] and "big.txt 25 筆" in job["steps"][1]["summary"], job["steps"][1]["summary"]
            text = fake.users("plan")[1]
            assert "→ pkg/mod.py 第 1～2 行（共 6 行）；還有第 3～6 行沒有看（view_file pkg/mod.py --from 3）" in text, text
            from agent_core import extract
            old = (extract.EXTRACT_CHUNK_CHARS, extract.EXTRACT_MAX_CHUNKS)
            extract.EXTRACT_CHUNK_CHARS, extract.EXTRACT_MAX_CHUNKS = 60, 1
            try:
                fake = FakeChat(plan=[plan("view_file", ["config/robots.yaml"], "r2 的 max_speed")],
                                answer=[answer((1, "not_found", "沒有讀到", []), (2, "not_found", "沒有讀到", []))])
                job = run(fake)
            finally:
                extract.EXTRACT_CHUNK_CHARS, extract.EXTRACT_MAX_CHUNKS = old
            st = job["steps"][0]
            assert st["read"] == 1 and st["chunks"] > 1 and st["unread_where"].startswith("config/robots.yaml 第 "), st
            text = fake.users("answer")[0]
            assert f"；輸出太長，提煉只讀了 1/{st['chunks']} 段，沒有讀：config/robots.yaml 第 " in text, text

        def t_view_pages():
            with open(os.path.join(tmp, "long.md"), "w", encoding="utf-8") as f:
                f.write("".join(f"第 {k} 段說明\n" for k in range(1, 2301)) + "結尾：代號 ZX-99\n")
            seen = []

            def look_long(msgs):
                seen.append(msgs[-1]["content"])
                if "ZX-99" in msgs[-1]["content"]:
                    return {"relevant": True, "facts": [{"text": "long.md 的結尾寫代號 ZX-99", "lines": body_line(msgs, "ZX-99")}]}
                return {"relevant": False, "facts": []}
            old = board.BOARD_VIEW_PAGES
            board.BOARD_VIEW_PAGES = 3
            try:
                fake = FakeChat(plan=[plan("view_file", ["long.md"], "結尾的代號", 1), plan("py_refs", ["alpha", "pkg", "--kind", "def|call"])],
                                look=[look_long] * 20, answer=[answer((1, "answered", "代號 ZX-99", [1]), (2, "not_found", "x", []))])
                job = run(fake, question="long.md 結尾的代號是什麼？", items=["結尾的代號", "alpha"])
            finally:
                board.BOARD_VIEW_PAGES = old
            steps = job["steps"]
            assert [(s["tool"], s["args"], s["auto"]) for s in steps[:2]] == [("view_file", ["long.md"], False), ("view_file", ["long.md", "--from", "2001"], True)], steps
            assert fake.count("plan") == 3, "程式接著看的那一段不花規劃的呼叫"
            assert job["facts"][0]["refs"][0] == "long.md:2301", job["facts"][0]
            text = fake.users("plan")[1]
            assert "第 2 步（程式接著看上一步沒看完的部分，找：結尾的代號）：view_file long.md --from 2001 → long.md 第 2001～2301 行（共 2301 行）" in text, text
            assert steps[2]["summary"].startswith("py_refs「alpha」（只算定義、呼叫）3 處"), ("過濾的種類寫進摘要", steps[2]["summary"])

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

        def t_dispatch():
            orchestrator.DOMAIN_BOARD = ("repo_analysis",)
            try:
                dispatch = {"thought": "分工", "reply": "交給領域查。", "action": {"domains": [
                    {"domain": "repo_analysis", "goal": "在 pkg 的 .py 裡找 alpha 的定義與呼叫", "items": ITEMS}]}}

                def cite(messages):
                    return {"thought": "依報告回答", "reply": "查到了。", "action": None, "answers": [
                        {"item": 1, "status": "answered", "text": "alpha 定義在 pkg/mod.py:1", "refs": ["pkg/mod.py:1"]},
                        {"item": 2, "status": "answered", "text": "gamma 呼叫 alpha（pkg/use.py:5）", "refs": ["pkg/use.py:5"]}]}
                fake = FakeChat(main=[dispatch, cite], plan=[plan("py_refs", ["alpha", "pkg"]), ANSWER_NOW], look=[look_alpha],
                                answer=[answer((1, "answered", "alpha 定義在 pkg/mod.py:1", [2]), (2, "answered", "gamma（pkg/use.py:5）", [4]))])
                events, awaiting = turn("pkg 裡的 alpha 定義在哪、誰呼叫它？", fake)
                assert not awaiting
                d = agent._domain_turn["dispatches"][-1]
                assert d["kind"] == "board" and d["status"] == "done" and d["skill"] == board.STEP_SKILL and len(d["answers"]) == 2, d
                assert d["calls"] == [{"tool": "py_refs", "script": None, "args": ["alpha", "pkg"], "status": "PASS", "head": d["calls"][0]["head"]}]
                report = next(m["content"] for m in agent.messages if m["role"] == "user" and DOMAIN_RESULT_HEAD in m["content"])
                assert "repo_analysis 的報告（做完；做法 公佈欄（一次決定一步））" in report and "pkg/use.py:5" in report, report[:400]
                assert any("ref=board_jobs/" in e["text"] for e in events if e["channel"] == "progress"), "決策圖的連結先推給畫面"
                final = [e["text"] for e in events if e["channel"] == "chat" and e.get("role") == "assistant"][-1]
                assert "1. alpha 定義在哪：alpha 定義在 pkg/mod.py:1（出處：pkg/mod.py:1）" in final and "> pkg/mod.py:1：def alpha(x):" in final, final
                assert "沒有通過核對" not in final, final
                known = agent._known_text()
                assert "repo_analysis" in known and "alpha 定義在 pkg/mod.py:1" in known, "交給後面的領域：公佈欄一項一項的回答"
                assert agent.domain_gate("code_defs").startswith("[ERROR] code_defs 是 repo_analysis 領域的工具"), "〈公佈欄的工具〉主對話也不能直接用"
                from evals import domain_calls
                rec = domain_calls.calls(agent, dispatch, DOMAIN_RESULT_HEAD + "x")
                assert rec[0]["board_status"] == "done" and rec[0]["board_steps"] == 1 and rec[1]["skill"] == "py_refs" and rec[1]["via"] == "repo_analysis", rec
                jobs = topology.jobs("logs", root=tmp)
                b = next(j for j in jobs if j["kind"] == "board" and j["id"] == d["job"])
                assert b["steps"] == 1 and b["skill"] == board.STEP_SKILL, b
                eid = json.load(open(os.path.join(tmp, "logs", "board_jobs", d["job"], "job.json"), encoding="utf-8"))["edg_job"]
                assert not any(j["kind"] == "edg" and j["id"] == eid for j in jobs), "公佈欄長出來的低階工作不另外列"
                view = topology.job_view("logs", f"board_jobs/{d['job']}", root=tmp)
                assert view["kind"] == "board" and [n["id"] for n in view["versions"][0]["graph"]["nodes"]] == ["s1"] and len(view["facts"]) == 4, view.keys()
                assert view["steps"][0]["tool"] == "py_refs" and view["report"].startswith("# 公佈欄的結果") and view["calls"], view["steps"][0]
            finally:
                orchestrator.DOMAIN_BOARD = ()

        def t_off_by_default():
            fake = FakeChat()
            assert orchestrator.DOMAIN_BOARD == () or os.environ.get("AGENT_DOMAIN_BOARD"), "預設沒有領域交給公佈欄（實驗用的設定）"
            assert reg["board_tools"] == ["search_text", "find_file", "list_dir", "view_file", "code_ast_reader", "code_defs", "py_refs"], reg["board_tools"]
            assert "code_defs" not in reg["tools"] and "py_refs" not in reg["tools"], "子工作階段（舊的做法）照舊不給新的工具：新舊比較時舊的不變"
            del fake

        for name, fn in [("一步一步：規劃 → 低階執行（決策圖長一個節點）→ 提煉成事實（檔案:行號、原文；對不上的拿掉；程式的數量另記）→ 照事實回答 → 報告；"
                          "公佈欄給規劃看的文字", t_steps),
                         ("回答的核對：名稱與數值要在根據的事實裡、答到的要寫事實、查不到要寫原因；沒過交回修一次，還是沒過的標出來", t_answer_fix),
                         ("試過的步驟：[ERROR] 附原因、跟之前一樣的工具與參數擋下（不排進圖），連續兩次＝卡住；程式的數量記成事實；"
                          "--include 一個參數寫好幾種檔名時程式拆開", t_repeat_error),
                         ("上限：步數用完、規劃的模型沒有回覆、回答的模型沒有回覆、每一項都不屬於這個領域", t_limits),
                         ("沒看到的寫出來：提煉只看到一種行號（工具自己的行號拿掉、程式照原本的輸出換成 檔案:行號）；檔案還有幾行沒有看、"
                          "search_text 只列了前面幾筆、提煉沒有讀的段落（檔案的第幾行）都寫進試過的步驟", t_unseen),
                         ("整份的檔案沒看完：程式接著看下一段（不花規劃的呼叫，最多 BOARD_VIEW_PAGES 段）；py_refs 只算幾種時摘要寫明", t_view_pages),
                         ("輸出的行號 → 檔案:行號（search_text、view_file、code_defs）；規劃看到的工具用法從規格取、schema 只列〈公佈欄的工具〉", t_locations),
                         ("接上高階（AGENT_DOMAIN_BOARD）：分工交給公佈欄、報告、依報告回答、交給後面的領域、主對話不能直接用、評測的紀錄、決策圖", t_dispatch),
                         ("預設不開（實驗用的設定）；舊的做法照舊（子工作階段不給新的工具）", t_off_by_default)]:
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
