"""主對話的離線自我測試：假的 ollama.chat 照劇本回答，直接驅動 Web 的回合迴圈（web_app.flows.run_turn），
幾秒鐘跑完、不需要 Ollama。

    python3 evals/chat/selftest.py

測的是 harness 的程式把關（不是模型能力；模型能力用 evals/chat/run.py 量）：
- 卡住偵測：同樣的動作第二次得到同樣的結果時附提醒、第三次加強提醒（換技能或參數）、第四次停下這一回合（⛔），不會一直跑到步數上限；
- 沒有執行卻宣稱做完：這一回合沒有跑任何工具、回覆卻說「已經重新啟動了」→ 提醒一次；條件句、疑問句、真的有執行過工具的不提醒；
- 路徑找不到時列出相近的路徑（view_file／list_dir／change_dir）；
- 兩階段揭露照舊：技能名稱回規格文件、腳本路徑才執行；不在技能清單裡的名稱（例如 2026-11 拿掉的 workflow_run、task_run）不會被當成技能；
- 🧠 模型設定：主對話換模型、thinking 開關只對支援的模型送出、設定存檔與載入、/model 與 /think；
- prompts/ 裡給模型的文字都讀得到（讀不到時程式不會報錯，只會默默變成空的）。
- CLI 的主迴圈（真的 cli.main()）：會改變狀態的技能先問 y/n，n 不執行、y 才執行；
- 說要去做卻沒有動作（「我會先查…」、action 是 null）：提醒一次；問使用者的、做過的事不提醒。
- 收據：寫收據的腳本執行完讀得到收據、軌跡記摘要、存檔旁邊存一份、刪存檔時一起刪；規格裡給程式看的欄位不給模型。
- 回覆的字串上限（第 5 步 5-1b）：schema 的 thought、command、args 有上限（都在 SCHEMA_MAX_CHARS 以內）、reply 沒有；command 寫成 null 當成沒有動作；寫到上限被截斷的不執行、
  重問一次（提醒只放進那一次送出的快照），還是被截斷就不執行那個動作，對話裡不留那段截斷的參數。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts", "web_app", "vision"]


class FakeMain:
    """主模型的假回覆：每次 ask_ai 依序取一個 {thought, reply, action}；用完了就回「沒有動作」。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = sorted((format or {}).get("properties", {})) if isinstance(format, dict) else []
        if "action" in props:
            self.calls += 1
            data = self.script.pop(0) if self.script else {"thought": "", "reply": "好的。", "action": None}
            return {"message": {"content": json.dumps(data, ensure_ascii=False)}, "prompt_eval_count": 100, "eval_count": 20}
        return {"message": {"content": "（摘要）"}, "prompt_eval_count": 100, "eval_count": 20}


def step(cmd, args="", reply="執行中"):
    return {"thought": "照做", "reply": reply, "action": {"command": cmd, "args": args}}


def say(reply):
    return {"thought": "回覆", "reply": reply, "action": None}


def make_env():
    tmp = tempfile.mkdtemp(prefix="chat_selftest_")
    for item in COPY:
        src = os.path.join(PROJECT, item)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(tmp, item), ignore=shutil.ignore_patterns("__pycache__"))
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(tmp, item))
    # 這裡測主迴圈本身（直接執行 ls、cat 這些工具）：拿掉領域的清單，工具不交給領域（分領域在 evals/orch/selftest.py 測）
    os.remove(os.path.join(tmp, "skills_system", "DOMAIN.md"))
    return tmp


def main():
    tmp = make_env()
    os.environ["AGENT_PERF_LOG"] = "0"
    sys.path.insert(0, tmp)
    cwd = os.getcwd()
    os.chdir(tmp)
    results = []
    try:
        import ollama
        ollama.list = lambda: {"models": []}
        from web_app import flows
        from web_app.state import agent, state
        agent.current_cwd = tmp
        state["auto_mode"] = True

        def turn(user, script):
            fake = FakeMain(script)
            ollama.chat = fake
            agent.set_current_task(user)
            agent.messages.append({"role": "user", "content": user})
            events = []
            flows.run_turn(events)
            tools = [e["text"] for e in events if e.get("channel") == "tool"]
            system = [e["text"] for e in events if e.get("channel") == "system"]
            return fake, tools, system

        def check(name, fn):
            try:
                fn()
                results.append((name, True, ""))
                print(f"✅ {name}")
            except Exception as e:
                import traceback
                results.append((name, False, traceback.format_exc()))
                print(f"❌ {name}：{e}")

        def t_stuck():
            fake, tools, system = turn("看一下 nope.txt", [step("scripts/cat_cmd.py", "nope.txt")] * 6)
            assert fake.calls == 4, f"第四次就該停下來（v4.1），實際呼叫了 {fake.calls} 次模型"
            assert agent.stuck and "nope.txt" in agent.stuck, agent.stuck
            assert "系統提醒" in tools[1] and "系統提醒" not in tools[0], tools[:2]
            assert "這個做法行不通" in tools[2] and "再重複一次" in tools[2], "第三次要加強提醒、要它換技能或參數"
            assert any(s.startswith("⛔") for s in system), system
            assert tools[3].startswith("[ERROR]"), "第一行一定還是 [ERROR]"

        def t_same_error_not_consecutive():
            script = [step("scripts/cat_cmd.py", "missing.txt"), step("scripts/ls_cmd.py", "."), step("scripts/cat_cmd.py", "missing.txt"),
                      step("scripts/ls_cmd.py", "skills_system"), step("scripts/cat_cmd.py", "missing.txt"),
                      step("scripts/ls_cmd.py", "agent_core"), step("scripts/cat_cmd.py", "missing.txt"), say("找不到")]
            fake, tools, system = turn("讀 missing.txt", script)
            assert "系統提醒" in tools[2], "不連續、但同樣的錯誤第二次也要提醒（v4.1）"
            assert fake.calls == 7 and agent.stuck, (fake.calls, agent.stuck)

        def t_v4_rule():
            os.environ["AGENT_TURN_GUARD_RULE"] = "v4"
            try:
                fake, tools, system = turn("看一下 nope.txt", [step("scripts/cat_cmd.py", "nope.txt")] * 6)
            finally:
                del os.environ["AGENT_TURN_GUARD_RULE"]
            assert fake.calls == 3 and agent.stuck, "評測對照組的舊規則：第三次就停"
            assert "再重複一次，這一回合就會停下來" in tools[1], tools[1][-120:]

        def t_reset_each_turn():
            fake, tools, system = turn("再試一次別的", [say("好的，請告訴我正確的檔名。")])
            assert agent.stuck is None and fake.calls == 1, (agent.stuck, fake.calls)

        def t_claim():
            fake, tools, system = turn("幫我重新啟動 nav2", [say("已經幫你重新啟動 nav2 了。"), say("抱歉，我還沒有執行任何動作；要重新啟動 nav2 需要先確認容器。")])
            assert fake.calls == 2, f"應該提醒一次後再問一次，實際 {fake.calls} 次"
            assert any(m["role"] == "user" and m["content"].startswith("[harness] 你在這一回合沒有執行任何工具") for m in agent.messages)
            assert any("沒有執行任何工具" in s for s in system), system

        def t_claim_only_once():
            fake, tools, system = turn("重啟 amcl", [say("已重新啟動 amcl。"), say("已重新啟動 amcl。"), say("已重新啟動 amcl。")])
            assert fake.calls == 2, f"每回合最多提醒一次，實際 {fake.calls} 次"

        def t_hedge_no_nudge():
            for reply in ("如果要重新啟動 nav2，我可以幫你執行，要嗎？", "還沒有重新啟動，需要你先確認。", "目前無法建立連線。"):
                fake, tools, system = turn("nav2 怎麼了", [say(reply)])
                assert fake.calls == 1, (reply, fake.calls)

        def t_claim_describes_state():
            # 描述數據或系統的狀態（前面有主詞）不是宣稱做了：數據診斷的追問常寫「指令已停止發布」「系統已完成初始化」
            reply = "根據報告，/cmd_vel_raw 在 +34.25s 已停止發布，安全閘到最後仍是 LIMITED；馬達的警告解除之前，系統已完成的限速不會自己解除。"
            fake, tools, system = turn("那要怎麼讓安全閘恢復？", [say(reply)])
            assert fake.calls == 1 and not any("沒有執行任何工具" in s for s in system), (fake.calls, system)

        def t_claim_after_tool_ok():
            fake, tools, system = turn("看一下 prompts/AGENT.md 的開頭", [step("scripts/cat_cmd.py", "prompts/AGENT.md"), say("已經讀完了，重點如下…")])
            assert fake.calls == 2 and not any("沒有執行任何工具" in s for s in system), (fake.calls, system)

        def t_path_suggestions():
            fake, tools, system = turn("看 agent_core/Agent.py", [step("scripts/cat_cmd.py", "agent_core/Agent.py"), say("找不到")])
            assert "相近的路徑：agent_core/agent.py" in tools[0], tools[0]
            fake, tools, system = turn("列出 skills_system/script", [step("scripts/ls_cmd.py", "skills_system/script"), say("好")])
            assert "相近的路徑：skills_system/scripts" in tools[0], tools[0]
            fake, tools, system = turn("切到 Agent_core", [step("scripts/cd_cmd.py", "Agent_core"), say("好")])
            assert "相近的路徑：agent_core" in tools[0], tools[0]

        def t_two_stage_disclosure():
            fake, tools, system = turn("看 prompts/AGENT.md", [step("view_file", "prompts/AGENT.md"), step("scripts/cat_cmd.py", "prompts/AGENT.md"), say("好")])
            assert "規格文件" in tools[0] and tools[1].startswith("[PASS] 檔案內容"), [t[:80] for t in tools]
            # 不在技能清單裡的名稱（2026-11 拿掉的 workflow_run 與工作流的名稱）：不是技能、不載入任何規格，system prompt 也不再列工作流
            assert agent._load_skill_doc("workflow_run") is None and agent._load_skill_doc("config_edit") is None
            assert "workflow_run" not in agent.get_system_prompt() and "## 工作流" not in agent.get_system_prompt()
            # 2026-11-18 拿掉的 task_run（任務引擎）也一樣
            assert agent._load_skill_doc("task_run") is None and "task_run" not in agent.get_system_prompt()

        def t_script_skill_map():
            # 腳本 → 技能：規格裡 `EXECUTE: scripts/<x>.py` 指令位置的腳本都對回那個技能（只提到的不算：code_ast_reader 的範例把
            # scripts/ls_cmd.py 當成參數，以前 ls_cmd.py 被認成 code_ast_reader，任務的 worker 用 list_dir 被擋）
            import glob
            import re
            mapping = agent._script_skill_map()
            for p in glob.glob(os.path.join(tmp, "skills_system", "tools", "*.md")):
                skill = os.path.basename(p)[:-3]
                for s in re.findall(r"EXECUTE:\s*scripts/([A-Za-z0-9_]+\.py)", open(p, encoding="utf-8").read()):
                    assert mapping.get(s) == skill, (s, mapping.get(s), skill)
            assert mapping["ls_cmd.py"] == "list_dir" and mapping["cat_cmd.py"] == "view_file"

        def t_prompts_loaded():
            # 給模型的文字都在 prompts/：路徑錯了不會報錯（AGENT.md、模式規則、記憶、維運／提煉的 prompt 都會默默變成空的），所以直接檢查讀到的內容
            text = agent.get_system_prompt()
            for rel in ("AGENT.md", os.path.join("context_modes", agent.context_mode + ".md")):
                with open(os.path.join(tmp, "prompts", rel), encoding="utf-8") as f:
                    first = next(line for line in f.read().splitlines() if line.strip())
                assert first in text, f"system prompt 裡沒有 prompts/{rel}"
            assert agent._memory_entries(), "讀不到 prompts/Memory.md 的條目"
            from agent_core.extract import read_prompt as extract_prompt
            for name in ("worker.md", "merger.md"):
                assert extract_prompt(name).strip(), f"讀不到 prompts/extract/{name}"

        def fake_show(model):
            return {"capabilities": ["completion", "thinking"] if str(model).startswith(("gemma4", "deepseek-r1")) else ["completion", "tools"]}

        class ThinkingMain(FakeMain):
            """記下每次主對話呼叫送的 think，回覆附上 message.thinking（像 Ollama 的 thinking 模式）。"""
            def __init__(self, script):
                super().__init__(script)
                self.thinks = []

            def __call__(self, model=None, messages=None, format=None, **kw):
                res = super().__call__(model=model, messages=messages, format=format, **kw)
                if "action" in sorted((format or {}).get("properties", {})):
                    self.thinks.append(kw.get("think"))
                    if kw.get("think"):
                        res["message"]["thinking"] = "先想一下：使用者只是打招呼。"
                return res

        def t_think_main():
            from agent_core import model_caps
            ollama.show = fake_show
            model_caps._cache.clear()
            old_model, old_think = agent.model, agent.main_think
            try:
                agent.set_main_model("gemma4:26b")
                agent.main_think = True
                fake = ThinkingMain([say("你好")])
                ollama.chat = fake
                agent.set_current_task("你好")
                agent.messages.append({"role": "user", "content": "你好"})
                events = []
                flows.run_turn(events)
                assert fake.thinks == [True], f"支援 thinking 的模型打開後要送 think=True：{fake.thinks}"
                assert any(e.get("channel") == "thinking" and "打招呼" in e["text"] for e in events), "右欄要有模型的思考"
                assert not any("打招呼" in (m.get("content") or "") for m in agent.messages), "思考內容不進對話"
                agent.set_main_model("qwen2.5-coder:32b")       # 不支援 thinking：開關開著也不送（Ollama 會回 400）
                fake = ThinkingMain([say("你好")])
                ollama.chat = fake
                agent.messages.append({"role": "user", "content": "再一次"})
                events = []
                flows.run_turn(events)
                assert fake.thinks == [False], fake.thinks
                assert not any(e.get("channel") == "thinking" for e in events)
            finally:
                agent.set_main_model(old_model)
                agent.main_think = old_think

        def t_model_settings():
            from agent_core import model_caps
            ollama.show = fake_show
            model_caps._cache.clear()
            old = agent.model
            assert agent._summary_follows_main, "沒有 AGENT_SUMMARY_MODEL 時摘要模型跟著主模型"
            agent.set_main_model("gemma4:26b")
            agent.main_think = True
            assert agent.summary_model == "gemma4:26b", agent.summary_model
            agent.save_model_settings()
            agent.set_main_model(old)
            agent.main_think = False
            note = agent.load_model_settings({"gemma4:26b", old})
            assert agent.model == "gemma4:26b" and agent.main_think is True and "上次的設定" in (note or ""), (agent.model, note)
            agent.set_main_model(old)
            note = agent.load_model_settings({old})     # 存的模型已經不在 Ollama 裡：不套用、說明原因
            assert agent.model == old and "不在 Ollama 裡" in (note or ""), note
            # Web 的 🧠：主對話的模型與 thinking（模型支援才送）、/think、/model（數據分析全部由程式做，沒有自己的模型）
            from agent_core.model_caps import think_arg
            from web_app.models import model_update, model_view
            view = model_view()
            assert view["thinking"].get(agent.model) is not None, view["thinking"]
            res = model_update({"main": "gemma4:e4b", "main_think": True})
            assert res["ok"] and agent.model == "gemma4:e4b" and agent.main_think is True, res
            assert think_arg(agent.model, agent.main_think) is True, "gemma4 支援 thinking：照設定送"
            assert "主對話 gemma4:e4b（thinking 開）" in res["message"], res["message"]
            ev = []
            from web_app.commands import handle_slash_command
            handle_slash_command("/think main off", ev)
            assert agent.main_think is False and "主對話 gemma4:e4b（thinking 關）" in ev[-1]["text"], ev
            handle_slash_command("/think orchestrator off", ev)
            assert "用法：/think main on|off" in ev[-1]["text"], ev
            handle_slash_command("/model gemma4:26b", ev)
            assert agent.model == "gemma4:26b", agent.model
            agent.set_main_model(old)

        def t_promise():
            # 說要去做卻沒有動作（「我會先查…」、action 是 null）：提醒一次，它接著真的去做；問使用者的、做過的事不提醒
            fake, tools, system = turn("amr_07 的設定在哪裡", [say("我會先查 amr_07 的設定檔。"), step("scripts/ls_cmd.py", "."), say("在目前的目錄。")])
            assert fake.calls == 3 and tools, (fake.calls, tools)
            assert any(m["role"] == "user" and m["content"].startswith("[harness] 你說要「我會先查」") for m in agent.messages)
            assert any("卻沒有執行任何工具" in s for s in system), system
            for reply in ("請問要我先查哪一台？", "我查到設定在 config/amr.yaml。", "我先查了一下，設定在 config/amr.yaml。"):
                fake, tools, system = turn("設定在哪", [say(reply)])
                assert fake.calls == 1, (reply, fake.calls)

        def run_cli(lines, fake):
            import builtins
            import contextlib
            import io
            from agent_core import cli
            asked = []

            def fake_input(prompt=""):
                asked.append(prompt)
                if not lines:
                    raise KeyboardInterrupt
                return lines.pop(0)
            ollama.chat = fake
            real_input, buf = builtins.input, io.StringIO()
            builtins.input = fake_input
            try:
                with contextlib.redirect_stdout(buf):
                    cli.main()
            finally:
                builtins.input = real_input
            return buf.getvalue(), asked

        def t_receipts():
            # last_receipt 是「這一次 run_tool」的收據（每次呼叫都重設，跟 last_result_id 一樣）：執行完馬上讀
            text = agent.run_tool(step("scripts/ls_cmd.py", "agent_core"))
            r = agent.last_receipt
            assert r and r["tool"] == "list_dir" and r["status"] == "pass" and r["counts"]["files"] > 0, r
            rec = agent.trajectory[-1]
            assert rec["receipt"] == {k: r[k] for k in ("status", "error_kind", "counts", "truncated")}, rec.get("receipt")
            side = os.path.join(agent.results_dir(), rec["result_file"][:-3] + ".receipt.json")
            with open(side, encoding="utf-8") as f:
                saved = json.load(f)
            assert saved["id"] == rec["id"] and saved["items"] == r["items"], "收據的全文跟存檔放在一起"
            assert text.startswith("[PASS] 目錄列表") and "receipt" not in text and '"counts"' not in text, "給模型的文字不含收據"
            agent.run_tool(step("scripts/cat_cmd.py", "nope.txt"))
            assert agent.last_receipt["status"] == "error" and agent.last_receipt["error_kind"] == "args", agent.last_receipt
            agent.run_tool(step("scripts/cd_cmd.py", "agent_core"))
            assert agent.last_receipt is None and "receipt" not in agent.trajectory[-1], "沒寫收據的腳本（還沒做收據的技能）是 None"
            agent.run_tool(say("好"))
            assert agent.last_receipt is None, "這一次沒有執行腳本"
            agent.current_cwd = tmp
            import agent_core.archive as archive
            keep = archive.TOOL_RESULTS_KEEP
            archive.TOOL_RESULTS_KEEP = 1
            try:
                removed = agent._prune_tool_results(agent.results_dir())
            finally:
                archive.TOOL_RESULTS_KEEP = keep
            assert rec["result_file"] in removed and not os.path.exists(side), "刪存檔時收據一起刪"
            with open(os.path.join(tmp, "skills_system", "tools", "search_text.md"), encoding="utf-8") as f:
                raw = f.read()
            doc = agent._load_skill_doc("search_text")
            assert "\nparameters:" in raw and "\nreceipt:" in raw and "parameters:" not in doc and "receipt:" not in doc, doc[:300]
            assert doc.startswith("---\ntype: Tool") and "# 語法" in doc

        def t_cli_guard():
            # CLI 的主迴圈（真的 cli.main()）：會改變狀態的技能先問 y/n；n 不執行、y 才執行，AI 依結果回答
            path = os.path.join(tmp, "config", "cam_cli.yaml")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            for answer, expect in (("n", "exposure: 10"), ("y", "exposure: 20")):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("exposure: 10\n")
                fake = FakeMain([step("scripts/file_ops_cmd.py", f"set {path} exposure 20"), say("好了。")])
                out, asked = run_cli(["/auto on", "把 exposure 改成 20", answer], fake)
                assert "確定執行？(y/n): " in asked, asked
                with open(path, encoding="utf-8") as f:
                    got = f.read().strip()
                assert got == expect, (answer, got, out[-1500:])
                assert fake.calls == (1 if answer == "n" else 2), (answer, fake.calls)

        def t_reply_cut():
            # 回覆的字串上限（第 5 步 5-1 的評測：模型在參數裡一直重複同一段，沒有上限時一次寫兩萬多個 token、JSON 解析不了）
            from agent_core.config import REPLY_ARGS_CHARS, REPLY_COMMAND_CHARS, REPLY_THOUGHT_CHARS, SCHEMA_MAX_CHARS
            from agent_core.protocol import parse_agent_reply
            from agent_core.schemas import _text, agent_reply_schema
            props = agent_reply_schema()["properties"]
            act = props["action"]["anyOf"][1]["properties"]
            assert (props["thought"]["maxLength"], act["command"]["maxLength"], act["args"]["maxLength"]) == \
                (REPLY_THOUGHT_CHARS, REPLY_COMMAND_CHARS, REPLY_ARGS_CHARS) and "maxLength" not in props["reply"], props
            # Ollama（llama.cpp 的文法）不套用超過 2000 的 maxLength（實測 2001 不截）：每個上限都在 SCHEMA_MAX_CHARS 以內，寫大了建 schema 時就報錯
            def caps(node):
                if isinstance(node, dict):
                    yield from ([node["maxLength"]] if "maxLength" in node else [])
                    for v in node.values():
                        yield from caps(v)
                elif isinstance(node, list):
                    for v in node:
                        yield from caps(v)
            assert SCHEMA_MAX_CHARS == 2000 and max(caps(agent_reply_schema(("repo_analysis",), 3))) <= SCHEMA_MAX_CHARS
            try:
                _text(SCHEMA_MAX_CHARS + 1)
                raise AssertionError("超過 SCHEMA_MAX_CHARS 的上限要報錯")
            except ValueError:
                pass
            for cmd in ("null", "None", "NULL"):       # e4b 收尾時寫成 {"command": "null"}：跟 action 填 null 一樣
                p = parse_agent_reply(json.dumps({"thought": "收尾", "reply": "好", "action": {"command": cmd, "args": ""}}))
                assert p["action"] is None and p["valid"] and p["cut"] == [], (cmd, p)
            long_args = "x" * REPLY_ARGS_CHARS
            fake, tools, system = turn("列出目前的目錄", [step("scripts/ls_cmd.py", long_args, reply="列出目錄"),
                                                        step("scripts/ls_cmd.py", ".", reply="列出目錄"), say("列好了。")])
            assert fake.calls == 3 and len(tools) == 1 and long_args not in tools[0], (fake.calls, [t[:200] for t in tools])
            assert any("寫到長度上限被截斷（args），已自動重試一次。" in s for s in system), system
            assert not any("xxxxxxxxxx" in (m.get("content") or "") or "寫到長度上限被截斷了" in (m.get("content") or "") for m in agent.messages), \
                "截斷的那一則與重問的提醒都不進對話"
            fake, tools, system = turn("再列一次", [step("scripts/ls_cmd.py", long_args, reply="好"), step("scripts/ls_cmd.py", long_args, reply="好")])
            assert fake.calls == 2 and not tools, (fake.calls, [t[:200] for t in tools])
            assert any("重試後還是被截斷，這一次的動作不執行。" in s for s in system), system
            last = json.loads(next(m["content"] for m in reversed(agent.messages) if m["role"] == "assistant"))
            assert last["action"] is None and "xxxxxxxxxx" not in json.dumps(last), last

        def seed_live(rid=501, session="20260926_101500"):
            """放一份「之前的 session」的即時狀態存檔（評測世界的寫法：檔頭沒有 memory，照技能判斷）與檢索清單的一行。"""
            d = agent.results_dir()
            os.makedirs(d, exist_ok=True)
            fn = f"{session}_{rid:03d}_docker_containers.md"
            with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                f.write("\n".join(["---", f"id: {rid}", f"session: {session}", "ts: 2026-09-26 10:20:00", "script: docker_containers_cmd.py",
                                   "skill: docker_containers", "command: EXECUTE: scripts/docker_containers_cmd.py", f"cwd: {tmp}", "container: ",
                                   "status: PASS", "chars: 40", "task: 有哪些容器在跑", "---", "NAME       STATUS", "nav2_test  Up 20 hours"]) + "\n")
            with open(os.path.join(d, "tools_use_index.md"), "a", encoding="utf-8") as f:
                f.write(f"#{rid} | 2026-09-26 10:20 | {session} | {fn} | 有哪些容器在跑：nav2_test 在運行\n")
            return fn

        def t_memory_kinds():
            # 存檔分讀取型與動作型（框架討論紀錄第 42 輪）：檔頭記 memory（動作照確認關卡的判斷、即時狀態照規格的 live、其他是檔案內容）；動作另外記一行、
            # system prompt 列「最近執行過的動作」；檢索清單寫之前的 session、技能、即時狀態；讀回（result_view）開頭寫那一份的事實；存檔之後改過的檔案列出來
            from skills_system.scripts import _results_common as rc
            d = agent.results_dir()
            seed_live()
            agent.set_current_task("看一下")
            act = agent._record_trajectory("file_ops_cmd.py", ["write", "kind_note.txt", "hi"], "[PASS] 寫入 kind_note.txt（2 字）", tmp, "", "")
            live = agent._record_trajectory("docker_containers_cmd.py", [], "[PASS] 容器 nav2_test Exited", tmp, "", "")
            text = agent._record_trajectory("cat_cmd.py", ["x.txt"], "[PASS] x.txt 的內容", tmp, "", "")
            kinds = [rc.read_header(os.path.join(d, r["result_file"]))[0].get("memory") for r in (act, live, text)]
            assert kinds == ["action", "live", "content"], kinds
            block = agent._actions_block()
            assert "最近執行過的動作" in block and f"#{act['id']}" in block and "file_ops write kind_note.txt hi" in block, block
            assert "最近執行過的動作" in agent.get_system_prompt(), "system prompt 有這一區"
            row = next(r for r in agent._tool_use_index_rows() if r[0] == 501)
            assert "之前的 session，docker_containers，即時狀態" in row[1], row
            assert agent._row_facts({"kind": "conversation", "file": "x"}) == "", "對話片段不標"
            facts = rc.archive_facts(os.path.join(d, "20260926_101500_501_docker_containers.md"))
            assert "即時狀態" in facts and "天前" in facts and "#501" in facts, facts
            assert "動作" in rc.archive_facts(os.path.join(d, act["result_file"])), "動作的事實"
            assert rc.archive_facts(os.path.join(d, text["result_file"])) == "", "檔案內容沒改過：不寫"
            target = os.path.join(tmp, "kind_changed.txt")
            with open(target, "w", encoding="utf-8") as f:
                f.write("old\n")
            rec = {"id": agent._next_id(), "script": "view_file_cmd.py", "skill": "view_file", "command": "EXECUTE: scripts/view_file_cmd.py kind_changed.txt",
                   "cwd": tmp, "status": "PASS", "task": "看", "args": ["kind_changed.txt"]}
            fn = agent._archive_tool_result(rec, "1→old", {"status": "pass", "cwd": tmp, "items": [{"path": target}]})
            os.utime(target, (time.time() + 120, time.time() + 120))
            changed = rc.archive_facts(os.path.join(d, fn))
            assert "kind_changed.txt" in changed and "改過" in changed, changed
            out = agent.run_script("result_view_cmd.py", ["501"])
            assert "即時狀態" in out and "#501" in out, out[:400]

        def t_memory_reply_no_sendback():
            # 主 session 的回覆引用了這一回合之前存的即時狀態：不交回（框架討論紀錄第 43 輪的（F1））——第 42 輪交回之後，模型把問之前查的
            # 當成問現在、去重查；問的是現在還是當時由模型看清單與讀回時程式寫的事實判斷（t_memory_kinds）。領域 session 的回報照舊核對
            # （domain_selftest 的 t_stale_refs）
            if not os.path.exists(os.path.join(agent.results_dir(), "20260926_101500_501_docker_containers.md")):
                seed_live()
            agent.set_current_task("昨天查的那份容器清單裡有 nav2_test 嗎？")
            assert agent._turn_first_id > 501, agent._turn_first_id
            said = lambda text: {"reply": text, "valid": True, "action": None, "answers": []}
            assert agent.reply_check(said("根據 #501（2026-09-26 查的），nav2_test 在那份清單裡。")) is None, "引用之前的即時狀態：不交回"
            agent.run_script("result_view_cmd.py", ["501"])
            vid = agent.last_result_id
            assert agent.reply_check(said(f"照 #{vid}，nav2_test 在那份清單裡。")) is None, "看舊存檔的衍生輸出：不交回"

        def t_guard_previous():
            # 確認關卡寫出之前做過同樣的動作（框架討論紀錄第 45 輪）：同一個技能、同樣的參數照 actions_index.md 記的寫法比；
            # 沒做過的跟以前一樣，做過兩次寫「一共 2 次」，參數不一樣的不寫；不擋（照樣要確認）
            agent.set_current_task("寫一下")
            act = {"action": {"command": "scripts/file_ops_cmd.py", "args": "write guard_prev.txt hi"}}
            info = agent.state_change_info(act)
            assert info and not info.get("previous") and "之前做過" not in agent.guard_prompt_text(info), info
            rec = agent._record_trajectory("file_ops_cmd.py", ["write", "guard_prev.txt", "hi"], "[PASS] 寫入 guard_prev.txt（2 字）", tmp, "", "")
            text = agent.guard_prompt_text(agent.state_change_info(act))
            assert f"之前做過：#{rec['id']}" in text and "PASS" in text and "寫入 guard_prev.txt" in text and "一共" not in text, text
            agent._record_trajectory("file_ops_cmd.py", ["write", "guard_prev.txt", "hi"], "[PASS] 寫入 guard_prev.txt（2 字）", tmp, "", "")
            assert "一共 2 次" in agent.guard_prompt_text(agent.state_change_info(act))
            other = agent.state_change_info({"action": {"command": "scripts/file_ops_cmd.py", "args": "write guard_prev.txt bye"}})
            assert other and "之前做過" not in agent.guard_prompt_text(other), "參數不一樣的不寫"

        for name, fn in [("卡住偵測：同樣的動作第二次附提醒、第三次加強提醒、第四次停下這一回合（v4.1）", t_stuck),
                         ("卡住偵測：同一個錯誤不管中間做了什麼，第二次提醒、第四次算卡住", t_same_error_not_consecutive),
                         ("卡住偵測：評測對照組的舊規則（AGENT_TURN_GUARD_RULE=v4，第三次就停）", t_v4_rule),
                         ("卡住偵測：每個新回合重新計數", t_reset_each_turn),
                         ("沒有執行卻宣稱做完：提醒一次", t_claim),
                         ("沒有執行卻宣稱做完：每回合最多提醒一次", t_claim_only_once),
                         ("描述數據或系統的狀態（前面有主詞的「已停止」「已完成」）不是宣稱做了", t_claim_describes_state),
                         ("條件句、疑問句、否定句不提醒", t_hedge_no_nudge),
                         ("這一回合真的執行過工具：不提醒", t_claim_after_tool_ok),
                         ("路徑找不到時列出相近的路徑（view_file／list_dir／change_dir）", t_path_suggestions),
                         ("兩階段揭露照舊：技能名稱回規格、腳本路徑才執行；不在技能清單裡的名稱（拿掉的 workflow_run、task_run）不是技能", t_two_stage_disclosure),
                         ("prompts/ 裡的文字都讀得到：AGENT.md、上下文模式的規則、長期記憶、提煉（worker、整合）", t_prompts_loaded),
                         ("🧠 主對話 thinking：支援的模型才送 think=True，思考內容推到右欄、不進對話", t_think_main),
                         ("🧠 模型設定：換主模型（摘要跟著換）、存檔與載入、thinking 只對支援的模型送、/model 與 /think", t_model_settings),
                         ("說要去做卻沒有動作（「我會先查…」）：提醒一次；問使用者的、做過的事不提醒", t_promise),
                         ("腳本 → 技能的對照：規格裡 EXECUTE 指令位置的腳本都對回那個技能（只提到的不算）", t_script_skill_map),
                         ("收據：寫收據的腳本執行完讀得到、軌跡記摘要、存檔旁邊存一份、刪存檔時一起刪；規格裡給程式看的欄位不給模型", t_receipts),
                         ("CLI 的主迴圈：會改變狀態的技能先問 y/n，n 不執行、y 才執行", t_cli_guard),
                         ("回覆的字串上限：schema 有上限、command 寫成 null 是沒有動作、寫到上限被截斷的不執行（重問一次，還是被截斷就不執行）", t_reply_cut),
                         ("存檔分讀取型與動作型：檔頭記種類、動作另列一區、檢索清單寫之前的 session 與即時狀態、讀回開頭寫事實、存檔之後改過的檔案列出來", t_memory_kinds),
                         ("主 session 的回覆引用了這一回合之前的即時狀態：不交回（問的是現在還是當時由模型看程式寫的事實判斷）", t_memory_reply_no_sendback),
                         ("確認關卡寫出之前做過同樣的動作：同一個技能、同樣的參數；沒做過、參數不一樣的不寫；做過兩次寫一共幾次", t_guard_previous)]:
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
