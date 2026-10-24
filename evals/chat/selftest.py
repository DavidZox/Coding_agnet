"""主對話的離線自我測試：假的 ollama.chat 照劇本回答，直接驅動 Web 的回合迴圈（web_app.flows.run_turn），
幾秒鐘跑完、不需要 Ollama。

    python3 evals/chat/selftest.py

測的是 harness 的程式把關（不是模型能力；模型能力用 evals/chat/run.py 量）：
- 卡住偵測：同樣的動作第二次得到同樣的結果時附提醒、第三次加強提醒（換技能或參數）、第四次停下這一回合（⛔），不會一直跑到步數上限；
- 沒有執行卻宣稱做完：這一回合沒有跑任何工具、回覆卻說「已經重新啟動了」→ 提醒一次；條件句、疑問句、真的有執行過工具的不提醒；
- 路徑找不到時列出相近的路徑（view_file／list_dir／change_dir）；
- 兩階段揭露照舊：技能名稱回規格文件、腳本路徑才執行；
- 🧠 模型設定：主對話換模型、thinking 開關只對支援的模型送出、設定存檔與載入、/model 與 /think；
- prompts/ 裡給模型的文字都讀得到（讀不到時程式不會報錯，只會默默變成空的）。
- 🧩 /workflow（Web）：列出、看步驟；直接執行的工作流照常經過確認卡片，核准才執行、拒絕不執行；報告完整進主對話，AI 依報告回答。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import os
import shutil
import sys
import tempfile

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

        def t_prompts_loaded():
            # 給模型的文字都在 prompts/：路徑錯了不會報錯（AGENT.md、模式規則、記憶、各角色的 prompt 都會默默變成空的），所以直接檢查讀到的內容
            text = agent.get_system_prompt()
            for rel in ("AGENT.md", os.path.join("context_modes", agent.context_mode + ".md")):
                with open(os.path.join(tmp, "prompts", rel), encoding="utf-8") as f:
                    first = next(line for line in f.read().splitlines() if line.strip())
                assert first in text, f"system prompt 裡沒有 prompts/{rel}"
            assert agent._memory_entries(), "讀不到 prompts/Memory.md 的條目"
            from agent_core.ops_job import _read_prompt as ops_prompt
            for name in ("planner.md", "worker.md"):
                assert ops_prompt(name).strip(), f"讀不到 prompts/ops/{name}"

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
            assert agent.summary_model == "gemma4:26b" and agent.skill_model == "gemma4:26b", (agent.summary_model, agent.skill_model)
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

        def t_workflow_web():
            # 🧩 /workflow：使用者直接指定工作流（不經過模型選擇）；會改變狀態的照常推確認卡片，核准才執行；報告直接進主對話、AI 依報告回答
            from web_app.commands import handle_slash_command
            from web_app.state import pending
            ev = []
            assert handle_slash_command("/workflow", ev) and "/workflow config_edit file=<…>" in ev[-1]["text"], ev[-1]
            assert handle_slash_command("/workflow show config_edit", ev) and "步驟：" in ev[-1]["text"], ev[-1]
            assert handle_slash_command("/workflow show", ev) and "用法" in ev[-1]["text"], ev[-1]
            assert not handle_slash_command("/workflow config_edit file=a.yaml", ev), "執行要跑一個回合：交給 server._handle_send"
            os.makedirs(os.path.join(tmp, "configs"), exist_ok=True)
            path = os.path.join(tmp, "configs", "robots.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write("robots:\n  - id: tb1\n    max_speed: 0.5\n  - id: tb2\n    max_speed: 0.5\n")
            read = lambda: open(path, encoding="utf-8").read()   # noqa: E731
            fake = FakeMain([say("改好了：tb1 的 max_speed 從 0.5 改成 0.9，tb2 沒有動。")])
            ollama.chat = fake
            n0, ev = len(agent.messages), []
            assert flows.run_workflow_turn("config_edit file=configs/robots.yaml robot=tb1 key=max_speed value=0.9", ev) is True
            guard = [e for e in ev if e.get("channel") == "guard"]
            assert pending["mode"] == "guard" and guard and "第 3 步" in guard[0]["text"], ev
            assert "0.9" not in read() and fake.calls == 0, "確認之前什麼都沒做、也沒有問模型"
            ev = []
            assert flows.apply_decision("y", ev) == "continue" and flows.run_turn(ev) is False
            assert "tb1\n    max_speed: 0.9" in read() and "tb2\n    max_speed: 0.5" in read(), read()
            tool = [e for e in ev if e.get("channel") == "tool"]
            assert tool and tool[0]["text"].startswith("[PASS] 工作流 config_edit（") and not tool[0]["oversized"], tool
            new = agent.messages[n0:]
            assert [m["role"] for m in new] == ["user", "assistant", "user", "assistant"], [m["role"] for m in new]
            assert "/workflow 直接執行工作流" in new[0]["content"] and "workflow_run_cmd.py" in new[1]["content"], new[:2]
            assert "[PASS] 工作流 config_edit（" in new[2]["content"] and "（摘要）" not in new[2]["content"], "報告完整進主對話、不再提煉"
            assert fake.calls == 1 and "改好了" in new[3]["content"], "AI 只在報告之後回答一次"
            ev = []
            assert flows.run_workflow_turn("config_edit file=configs/robots.yaml robot=tb1 key=max_speed value=1.2", ev) is True
            assert flows.apply_decision("n", ev) == "stop" and "1.2" not in read() and pending["mode"] is None
            assert "使用者沒有同意執行 workflow_run" in agent.messages[-1]["content"], agent.messages[-1]["content"][:200]

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
                         ("兩階段揭露照舊：技能名稱回規格、腳本路徑才執行", t_two_stage_disclosure),
                         ("prompts/ 裡的文字都讀得到：AGENT.md、上下文模式的規則、長期記憶、數據解析與維運各角色", t_prompts_loaded),
                         ("🧠 主對話 thinking：支援的模型才送 think=True，思考內容推到右欄、不進對話", t_think_main),
                         ("🧠 模型設定：換主模型（摘要跟著換）、存檔與載入、數據分析各角色的模型與 thinking、/model 與 /think", t_model_settings),
                         ("🧩 /workflow：列出、看步驟；直接執行要先過確認卡片，核准才改、拒絕不改；報告完整進主對話、AI 依報告回答", t_workflow_web)]:
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
