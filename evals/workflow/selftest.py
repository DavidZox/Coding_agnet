"""工作流（agent_core/workflow.py、workflow_spec.py、skills_system/workflows/）的離線自我測試：假的模型、假的技能輸出（照技能的真實格式），
不需要 Ollama、容器、沙盒。

    python3 evals/workflow/selftest.py

- 規格：skills_system/workflows/ 每一份都解析、驗證得過（腳本存在、分支往後、dependencies 與 changes_state 跟步驟一致），SKILLS.md〈工作流〉
  跟資料夾對得上；解析的細節（分支、檢查、選填、預設、成功判準）；
- 命令的值：雙引號裡的內容（引號、換行、反斜線）放進 file_ops 的命令後，file_ops 自己解析回來一字不差；
- 執行（stuck_package_fix）：完成訊號遺失——程式選分支、模型只填機器人與紀錄、成功判準由程式跑；其他原因——提早結束、沒有補發；
  選填的沒給——那一步略過；模型填不出值——停下來、不執行；技能回 [ERROR]——帶著錯誤請模型改一次值；
- 【確認】停下來、--continue 接著做、--cancel；沒有「其他」時模型選分支、關卡；
- 參數與確認關卡：參數錯、必填沒給、選填的預設（{today}）；開始時列出到第一個【確認】之前會改變狀態的步驟、--continue 的說明；
- dispatch：工作流的名稱當技能載入時說明用 workflow_run；沒有核准不執行；AGENT_WORKFLOWS=0 時不接受；
- /workflow（CLI 與 Web 共用的 agent_core/workflow_cmd.py）：列出、看步驟；不用互動的入口（Agent_Runner.py --workflow）沒有 --yes 不執行
  會改變狀態的、結束碼（完成／提早結束 0、沒有完成 1、停在【確認】2、要核准 3、沒有執行 4）、--continue；工作流的報告不再交給提煉；
  `Agent_Runner.py --workflow` 真的當成一個行程跑（結束碼、印出的報告、沒有 --yes 不改；OLLAMA_HOST 指到沒有服務的位址，證明不需要模型）；
- /make_skill：草稿排成工作流、交給同一套驗證、註冊到 workflows/ 與 SKILLS.md〈工作流〉。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import os
import re
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts", "web_app", "vision", "Agent_Runner.py"]

CONFIRM_WF = """---
type: Workflow
title: 測試用的確認
description: 測試【確認】與關卡
version: 0.1.0
dependencies: ["workpackage_status", "workpackage_cancel"]
changes_state: true
---
# 用途
測試。
# 需要的資訊
* `{wp_id}`：工作包
# 步驟
1. 【執行】看工作包：`EXECUTE: scripts/workpackage_status_cmd.py {wp_id}`　檢查：輸出有「[PASS]」
2. 【檢查】看第 1 步，要不要取消：「RUNNING」→ 第 3 步
3. 【確認】要取消 {wp_id} 嗎
4. 【執行】取消：`EXECUTE: scripts/workpackage_cancel_cmd.py {wp_id}`　檢查：輸出有「[PASS]」
5. 【檢查】還要繼續嗎
6. 【告知】回報
# 成功判準
* 第 4 步的輸出有「已取消」
* 第 1 步的輸出有「RUNNING」
"""


class FakeTools:
    """假的技能：依命令（腳本＋參數）回照真實格式寫的輸出；每次執行照常記軌跡（存檔、#編號）。"""

    def __init__(self, agent, rules):
        self.a, self.rules, self.ran = agent, rules, []

    def __call__(self, parsed, approved=False):
        action = parsed["action"]
        script = os.path.basename(action["command"])
        args = action.get("args", "")
        if script == "workflow_run_cmd.py":   # 工作流本身走真的 dispatch（確認關卡、存檔）；裡面的每一步再回到這裡
            return type(self.a)._run_tool_once(self.a, parsed, approved)
        self.ran.append((script, args, approved))
        out = next((o for pat, o in self.rules if re.search(pat, f"{script} {args}")), "[PASS] （假的輸出）")
        out = out(args) if callable(out) else out
        self.a._record_trajectory(script, args.split(), out, self.a.current_cwd, "", "")
        return out


class FakeModel:
    """假的判斷點：fill（schema 有 values）照 answers 依序回值；check（schema 有 choice）回 choice。"""

    def __init__(self, fills=(), choices=()):
        self.fills, self.choices, self.calls = list(fills), list(choices), []

    def __call__(self, model=None, messages=None, format=None, **kw):
        props = (format or {}).get("properties", {}) if isinstance(format, dict) else {}
        user = messages[-1]["content"] if messages else ""
        self.calls.append(("fill" if "values" in props else "check" if "choice" in props else "other", user))
        if "values" in props:
            data = {"values": self.fills.pop(0) if self.fills else {}, "reason": "照第 2 步的輸出"}
        elif "choice" in props:
            data = {"choice": self.choices.pop(0) if self.choices else 0, "reason": "照第 1 步"}
        else:
            data = {}
        return {"message": {"content": json.dumps(data, ensure_ascii=False)}, "prompt_eval_count": 50, "eval_count": 10}


STUCK_LOST = [
    (r"workpackage_status_cmd\.py WP_L2 --until-done", "[PASS] WP_L2 已完成：COMPLETED（共 1 輪），在 +3.0s 看到完成就結束觀察（最多 300 秒，收到 7 幀）"),
    (r"workpackage_status_cmd\.py WP_L2$", "[PASS] work package WP_L2：COMPLETED\n## WP_L2\n- WP_L2 COMPLETED：已完成（共 1 輪）"),
    (r"rmf_handshake_cmd\.py status WP_L2", "[PASS] WP_L2 → tb2 的交握狀況：完成訊號多半遺失了（task_exec_fin）\n## 判斷\n- 完成訊號多半遺失了：工作包 WP_L2 的工作項 WP_L2::0::0::ab-1 已經 confirm 給 tb2"),
    (r"rmf_handshake_cmd\.py fin tb2", "[PASS] 已經由 manual_trigger 補發 /tb2/task_exec_fin（task_id=WP_L2::0::0::ab-1，HTTP 200）"),
    (r"file_ops_cmd\.py append", "[PASS] 已附加 ops_notes/2026-10-10.md（5 行）"),
]


def make_env():
    tmp = tempfile.mkdtemp(prefix="workflow_selftest_")
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
        from agent_core.agent import SkillAgent
        from agent_core import workflow as wfm, workflow_spec as ws
        agent = SkillAgent(model="gemma4:e4b")
        agent.current_cwd = tmp

        def check(name, fn):
            try:
                fn()
                results.append((name, True, ""))
                print(f"✅ {name}")
            except Exception as e:   # noqa: BLE001
                results.append((name, False, traceback.format_exc()))
                print(f"❌ {name}：{e}")

        def setup(rules, fills=(), choices=()):
            tools, model = FakeTools(agent, rules), FakeModel(fills, choices)
            agent._run_tool_once = tools
            ollama.chat = model
            return tools, model

        def t_specs():
            wfs = agent.list_workflows()
            assert len(wfs) >= 5, [w["name"] for w in wfs]
            for wf in wfs:
                problems = agent.validate_workflow(wf)
                assert not problems, (wf["name"], problems)
            with open(os.path.join(tmp, "skills_system", "SKILLS.md"), encoding="utf-8") as f:
                index = f.read()
            listed = set(re.findall(r"^\s+- `([A-Za-z0-9_]+)` — ", index, re.M))
            assert listed == {w["name"] for w in wfs}, f"SKILLS.md〈工作流〉跟資料夾不一致：{listed ^ {w['name'] for w in wfs}}"
            for w in wfs:
                assert f"workflow_run {w['name']} " in index, f"SKILLS.md 要寫 {w['name']} 的呼叫語法"

        def t_parse_details():
            wf = ws.parse(CONFIRM_WF, "t", "t")
            s2, s5 = wf["steps"][1], wf["steps"][4]
            assert s2["source"] == 1 and s2["branches"] == [{"when": ["RUNNING"], "to": 3}], s2
            assert s5["branches"] == [] and wf["success"][0]["step"] == 4, (s5, wf["success"])
            stuck = agent.load_workflow("stuck_package_fix")
            assert [b["to"] for b in stuck["steps"][2]["branches"]] == ["end", 4, "end"] and stuck["steps"][2]["branches"][2]["when"] is None
            assert ws.fill_names(stuck, stuck["steps"][3]) == ["robot"] and ws.fill_names(stuck, stuck["steps"][5]) == ["robot", "note"]
            bad = ws.parse(CONFIRM_WF.replace("→ 第 3 步", "→ 第 1 步").replace("scripts/workpackage_cancel_cmd.py", "scripts/nope_cmd.py"), "b", "b")
            problems = agent.validate_workflow(bad)
            assert any("不能往回跳" in p for p in problems) and any("nope_cmd.py 不存在" in p for p in problems), problems

        def t_values_round_trip():
            fo = __import__("skills_system.scripts.file_ops_cmd", fromlist=["parse_raw"])
            text = '# 處理經過\n原因：完成訊號遺失（"task_exec_fin"）\n路徑 C:\\tmp\\a\t結果：COMPLETED'
            args = wfm.fill_template('append {note_file} --text "{note}"', {"note_file": "ops notes/a.md", "note": text}, "file_ops_cmd.py")
            pos, opts, err = fo.parse_raw(args)
            assert err is None and pos == ["append", "ops notes/a.md"] and opts["--text"] == text, (args, pos, opts)
            args = wfm.fill_template('{container} "{check_command}"', {"container": "web_cache", "check_command": 'grep "max_size" /etc/a.conf'},
                                     "docker_runcmd_cmd.py")
            import shlex
            assert shlex.split(args) == ["web_cache", 'grep "max_size" /etc/a.conf'], args

        def t_run_lost_fin():
            tools, model = setup(STUCK_LOST, fills=[{"robot": "tb2"}, {"note": "原因：完成訊號遺失\n處理：補發 fin\n結果：COMPLETED"}])
            out = agent.workflow_run("stuck_package_fix wp_id=WP_L2 note_file=ops_notes/2026-10-10.md")
            head = out.splitlines()[0]
            assert head.startswith("[PASS] 工作流 stuck_package_fix（工作包卡住的處理）完成：7/7 步做了，成功判準都過"), out
            assert "3. ✅【檢查】看第 2 步的判斷：「完成訊號多半遺失了」 → 第 4 步（程式判斷" in out, out
            assert "robot=tb2，模型依前面的輸出決定" in out and "✅ workpackage_status WP_L2 → 有「COMPLETED」" in out, out
            assert [c[0] for c in model.calls] == ["fill", "fill"], "只有兩個判斷點：機器人、紀錄的內容（第 6 步的機器人沿用第 4 步的）"
            assert "values" in model.calls[1][1] or "note" in model.calls[1][1]
            ran = [f"{s} {a}" for s, a, _ in tools.ran]
            assert any(r.startswith("rmf_handshake_cmd.py fin tb2") for r in ran) and all(ap for _, _, ap in tools.ran[:5]), ran
            assert any("--text" in r and "\\n處理：補發 fin" in r and "工作包 WP_L2（機器人 tb2）" in r for r in ran), \
                "紀錄的換行要寫成 \\n；開頭的工作包與機器人由程式填（機器人沿用第 4 步的值）"
            job = agent._workflow_store().load(re.search(r"工作 (\S+)，紀錄在", out).group(1))
            assert job["status"] == "done" and job["steps"]["4"]["values"] == {"robot": "tb2"} and job["steps"]["4"]["rid"], job["steps"]["4"]
            calls = agent._workflow_store().read_jsonl(job["id"], "calls.jsonl")
            assert len(calls) == 2 and calls[0]["kind"] == "fill" and "完成訊號多半遺失了" in calls[0]["user"], "判斷點看得到前面的輸出、存進 calls.jsonl"

        def t_run_other_cause():
            rules = [(r"rmf_handshake_cmd\.py status", "[PASS] WP_D4 → tb4 的交握狀況：沒有回應授權\n## 判斷\n- tb4 沒有回應授權")] + STUCK_LOST
            tools, model = setup(rules)
            out = agent.workflow_run("stuck_package_fix wp_id=WP_D4")
            assert out.startswith("[PASS] 工作流 stuck_package_fix 依判斷提早結束：其他 → 結束"), out
            assert not any(s == "rmf_handshake_cmd.py" and a.startswith("fin") for s, a, _ in tools.ran), "其他原因不能補發"
            assert not model.calls and "## 規格的注意事項" in out, "程式就判斷得出來，不用問模型"

        def t_skip_and_fail():
            tools, model = setup(STUCK_LOST, fills=[{"robot": "tb2"}])
            out = agent.workflow_run("stuck_package_fix wp_id=WP_L2")
            assert "6. ⏭️【執行】寫處理紀錄（選填的 note_file 沒有給）" in out and out.startswith("[PASS] 工作流 stuck_package_fix（"), out
            tools, model = setup(STUCK_LOST, fills=[{"robot": ""}])
            out = agent.workflow_run("stuck_package_fix wp_id=WP_L2")
            assert out.startswith("[ERROR] 工作流 stuck_package_fix 在第 4 步沒有完成（前面的輸出找不到 robot 的值"), out
            assert not any(s == "rmf_handshake_cmd.py" and a.startswith("fin") for s, a, _ in tools.ran), "沒有值就不執行"

        def t_retry_on_error():
            calls = {"n": 0}

            def fin(args):
                calls["n"] += 1
                return ("[ERROR] 名冊裡沒有 tb9（相近的：tb2）。下一步：改用名冊上的機器人 id" if "tb9" in args else
                        "[PASS] 已經由 manual_trigger 補發 /tb2/task_exec_fin")
            rules = [(r"rmf_handshake_cmd\.py fin", fin)] + STUCK_LOST
            tools, model = setup(rules, fills=[{"robot": "tb9"}, {"robot": "tb2"}])
            out = agent.workflow_run("stuck_package_fix wp_id=WP_L2")
            assert calls["n"] == 2 and "robot=tb2" in out and out.startswith("[PASS] 工作流 stuck_package_fix（"), out
            assert "名冊裡沒有 tb9" in model.calls[1][1], "第二次填值要看得到錯誤訊息"

        def t_confirm_pause_continue():
            real_load = agent.load_workflow
            agent.load_workflow = lambda name: ws.parse(CONFIRM_WF, name, os.path.join(tmp, "t.md")) if name == "confirm_test" else real_load(name)
            try:
                rules = [(r"workpackage_status_cmd\.py WP9", "[PASS] work package WP9：RUNNING，第 1/2 站"),
                         (r"workpackage_cancel_cmd\.py WP9", "[PASS] 已取消 WP9")]
                tools, model = setup(rules, choices=[0])
                assert agent.workflow_guard_reason("confirm_test wp_id=WP9") is None, "【確認】之前都只查詢：開始時不用確認"
                out = agent.workflow_run("confirm_test wp_id=WP9")
                assert out.startswith("[PASS] ⏸️ 工作流 confirm_test 停在第 3 步【確認】：要取消 WP9 嗎") and "workflow_run --continue" in out, out
                reason = agent.workflow_guard_reason("--continue")
                assert reason and "第 3 步【確認】" in reason and "第 4 步 取消" in reason, reason
                out = agent.workflow_run("--continue")
                assert out.startswith("[PASS] 工作流 confirm_test（測試用的確認）完成") and "3. ✅【確認】" in out, out
                assert [c[0] for c in model.calls] == ["check"], "沒有分支的【檢查】是關卡：模型判斷繼續"
                assert "✅ 第 4 步的輸出有「已取消」" in out, out
                # 接著做的是新的一次執行（記憶體裡沒有停下來之前的輸出）：第 1 步的輸出從存檔讀回原文——成功判準、判斷點看得到
                # （以前讀回來的是 (檔頭, 每一行) 的 tuple：成功判準一讀就出錯，判斷點看到的是 tuple 的字面）
                assert "✅ 第 1 步的輸出有「RUNNING」" in out, out
                gate = model.calls[0][1]
                assert "[PASS] work package WP9：RUNNING，第 1/2 站" in gate and "'session'" not in gate, gate[:600]
                tools, model = setup(rules)
                agent.workflow_run("confirm_test wp_id=WP9")
                out = agent.workflow_run("--cancel")
                assert out.startswith("[PASS] 工作流 confirm_test") and "取消了" in out, out
                assert agent.workflow_run("--continue").startswith("[ERROR] 沒有停在【確認】"), "取消之後不能繼續"
            finally:
                agent.load_workflow = real_load

        def t_model_branch():
            real_load = agent.load_workflow
            spec = CONFIRM_WF.replace("「RUNNING」→ 第 3 步", "「PAUSED」→ 第 3 步；「IDLE」→ 結束")
            agent.load_workflow = lambda name: ws.parse(spec, name, os.path.join(tmp, "t.md"))
            try:
                tools, model = setup([(r"workpackage_status_cmd\.py", "[PASS] work package WP9：RUNNING")], choices=[1])
                out = agent.workflow_run("x wp_id=WP9")
                assert out.startswith("[PASS] 工作流 x 依判斷提早結束：「IDLE」 → 結束") and "模型判斷" in out, out
                assert [c[0] for c in model.calls] == ["check"], "比對不出來、又沒有「其他」：交給模型選"
            finally:
                agent.load_workflow = real_load

        def t_args_and_guard():
            assert agent.workflow_run("nope x=1").startswith("[ERROR] 沒有工作流 nope。現有的：")
            out = agent.workflow_run("stuck_package_fix")
            assert "少了必填的：wp_id" in out and "這個工作流是：工作包卡住" in out and "不適合用這個工作流，改用技能一步一步做" in out, \
                "少了必填的：說明這個工作流的用途，需求本來就沒有這一項時改用技能，不要去問一個不存在的東西"
            assert "不認識的參數：wpid" in agent.workflow_run("stuck_package_fix wpid=WP1")
            assert "要寫成 名稱=值" in agent.workflow_run("stuck_package_fix WP1")
            assert agent.workflow_run("--list").startswith("[PASS] 工作流 ")
            reason = agent.workflow_guard_reason("stuck_package_fix wp_id=WP_L2 note_file=a.md")
            assert reason and "第 4 步 補發完成訊號" in reason and "第 6 步 寫處理紀錄" in reason and "第 1 步" not in reason.split("\n")[1], reason
            assert agent.workflow_guard_reason("stuck_package_fix") is None, "參數錯：交給 workflow_run 回錯誤，不用確認"
            reason = agent.workflow_guard_reason("stuck_package_fix wp_id=WP_L2")
            assert "第 6 步" not in reason.split("\n")[1] and "（略過：選填的 note_file 沒有給）" in reason, "選填的沒給、會略過的步驟不列成會改變狀態"
            reason = agent.workflow_guard_reason("config_edit file=c.yaml robot=tb1 key=max_speed value=0.9")
            lines = reason.split("\n")
            assert lines[0].endswith("參數：file=c.yaml、robot=tb1、key=max_speed、value=0.9、block=id: tb1"), "使用者給的與預設的值都列出來"
            assert lines[1] == '會改變狀態的步驟：第 3 步 只改 tb1 那一段的 max_speed（file_ops set c.yaml max_speed 0.9 --after "id: tb1"）', \
                "確認畫面是實際要執行的命令（值代進去）；沒給 backup 的備份那一步不列"
            inputs, err = agent._wf_check_inputs(ws.parse(CONFIRM_WF.replace("：工作包", "：工作包（選填，預設 `ops_{today}.md`）"), "t", "t"), {})
            assert err is None and re.fullmatch(r"ops_\d{4}-\d\d-\d\d\.md", inputs["wp_id"]), inputs

        def t_dispatch():
            from agent_core import dispatch as dm
            ollama.chat = FakeModel()
            del agent._run_tool_once                      # 用真的 dispatch
            out = agent.run_tool({"action": {"command": "stuck_package_fix", "args": ""}})
            assert "這是工作流（程式照步驟做，不是一個技能）" in out and "workflow_run_cmd.py" in out and "wp_id=<值>" in out, out[:600]
            out = agent.run_tool({"action": {"command": "scripts/workflow_run_cmd.py", "args": "stuck_package_fix wp_id=WP_L2"}})
            assert out.startswith("[DENIED]") and "workflow_run" in out, "會改變狀態：沒有核准不執行"
            old = dm.WORKFLOWS_ENABLED
            dm.WORKFLOWS_ENABLED = False
            try:
                out = agent.run_tool({"action": {"command": "scripts/workflow_run_cmd.py", "args": "--list"}}, approved=True)
                assert out.startswith("[ERROR] 這個環境關閉了工作流"), out
            finally:
                dm.WORKFLOWS_ENABLED = old

        def t_workflow_cmd():
            from agent_core import workflow_cmd as wc
            from agent_core.protocol import is_exempt_result
            assert wc.parse("") == ("list", "") and wc.parse(" show stuck_package_fix ") == ("show", "stuck_package_fix")
            assert wc.parse("show")[0] == "error" and wc.parse("--continue") == ("run", "--continue")
            listed = wc.list_text(agent)
            assert "/workflow stuck_package_fix wp_id=<…> [note_file=<…>]" in listed, listed
            assert "步驟：" in wc.show_text(agent, "stuck_package_fix") and wc.show_text(agent, "nope").startswith("沒有工作流 nope")
            reports = []
            # 不用互動的入口（心跳、排程）：會改變狀態的沒有 --yes 不執行，什麼都沒跑；--yes 才執行
            tools, model = setup(STUCK_LOST, fills=[{"robot": "tb2"}])
            code, text = wc.run_headless("stuck_package_fix wp_id=WP_L2", agent=agent)
            assert code == 3 and text.startswith("[需要核准，沒有執行]") and "第 4 步 補發完成訊號" in text and not tools.ran, (code, text)
            code, text = wc.run_headless("stuck_package_fix wp_id=WP_L2", yes=True, agent=agent)
            assert code == 0 and text.startswith("[PASS] 工作流 stuck_package_fix（") and [c[0] for c in model.calls] == ["fill"], (code, text)
            reports.append(text)
            # 程式判斷提早結束也算正常（0）；執行了但沒有完成（1）；參數錯、沒有執行（4）；不接名稱＝列出（0）
            setup([(r"rmf_handshake_cmd\.py status", "[PASS] WP_D4 → tb4 的交握狀況：沒有回應授權")] + STUCK_LOST)
            code, text = wc.run_headless("stuck_package_fix wp_id=WP_D4", yes=True, agent=agent)
            assert code == 0 and "依判斷提早結束" in text, (code, text)
            reports.append(text)
            setup(STUCK_LOST, fills=[{"robot": ""}])
            code, text = wc.run_headless("stuck_package_fix wp_id=WP_L2", yes=True, agent=agent)
            assert code == 1 and text.startswith("[ERROR] 工作流 stuck_package_fix 在第 4 步沒有完成"), (code, text)
            reports.append(text)
            code, text = wc.run_headless("stuck_package_fix wpid=WP_L2", yes=True, agent=agent)
            assert code == 4 and "不認識的參數：wpid" in text, (code, text)
            assert wc.run_headless("", agent=agent) == (0, wc.list_text(agent))
            # 停在【確認】：2；--continue 一樣要核准（3）；--yes 接著做完（0）
            real_load = agent.load_workflow
            agent.load_workflow = lambda name: ws.parse(CONFIRM_WF, name, os.path.join(tmp, "t.md")) if name == "confirm_test" else real_load(name)
            try:
                setup([(r"workpackage_status_cmd\.py WP9", "[PASS] work package WP9：RUNNING，第 1/2 站"),
                       (r"workpackage_cancel_cmd\.py WP9", "[PASS] 已取消 WP9")], choices=[0])
                code, text = wc.run_headless("confirm_test wp_id=WP9", agent=agent)
                assert code == 2 and "⏸️" in text, "開始時只查詢：不用核准，停在【確認】"
                reports.append(text)
                code, text = wc.run_headless("--continue", agent=agent)
                assert code == 3 and "第 3 步【確認】" in text, (code, text)
                code, text = wc.run_headless("--continue", yes=True, agent=agent)
                assert code == 0 and text.startswith("[PASS] 工作流 confirm_test（"), (code, text)
                reports.append(text)
            finally:
                agent.load_workflow = real_load
            for text in reports + [agent.workflow_run("--list")]:
                assert is_exempt_result(text, 99999), f"工作流的報告是程式整理好的：主對話直接收到完整的、不再提煉：{text[:60]}"
            # Agent_Runner.py --workflow：選項放在哪裡都可以，其他的字照順序是參數（有空白的值保留成一個）
            seen, real_run = [], wc.run_headless
            wc.run_headless = lambda args, **kw: (seen.append((args, kw)), (0, "ok"))[1]
            try:
                assert wc.main_headless(["--workflow", "config_edit", "file=a.yaml", "block=id: tb1", "--yes", "--model", "m"]) == 0
                assert wc.main_headless(["--workflow", "stuck_package_fix wp_id=WP_L2"]) == 0
                assert wc.main_headless(["--workflow", "--continue", "-y"]) == 0
                assert wc.main_headless(["--workflow", "x", "--model"]) == wc.EXIT_NOT_RUN
            finally:
                wc.run_headless = real_run
            assert seen[0] == ("config_edit file=a.yaml 'block=id: tb1'", {"yes": True, "model": "m", "cwd": None}), seen[0]
            assert agent._wf_parse_args(seen[0][0])[2] == {"file": "a.yaml", "block": "id: tb1"}
            assert seen[1][0] == "stuck_package_fix wp_id=WP_L2" and seen[2] == ("--continue", {"yes": True, "model": None, "cwd": None}), seen

        def t_headless_process():
            # Agent_Runner.py --workflow（之後心跳、排程直接呼叫的入口）當成一個行程跑：結束碼、印出的報告、沒有 --yes 不改。
            # OLLAMA_HOST 指到沒有服務的位址：config_edit 沒有判斷點，整條路不需要模型
            import subprocess
            ws_dir = tempfile.mkdtemp(prefix="wf_headless_", dir=tmp)
            path = os.path.join(ws_dir, "robots.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write("robots:\n  - id: tb1\n    max_speed: 0.5\n  - id: tb2\n    max_speed: 0.5\n")
            read = lambda: open(path, encoding="utf-8").read()   # noqa: E731

            def runner(*argv):
                p = subprocess.run([sys.executable, os.path.join(tmp, "Agent_Runner.py"), "--workflow", *argv], cwd=tmp, capture_output=True,
                                   text=True, timeout=120, stdin=subprocess.DEVNULL,
                                   env=dict(os.environ, AGENT_PERF_LOG="0", PYTHONDONTWRITEBYTECODE="1", OLLAMA_HOST="127.0.0.1:9"))
                return p.returncode, p.stdout + p.stderr
            call = ["config_edit", "file=robots.yaml", "robot=tb1", "key=max_speed", "value=0.9", "--cwd", ws_dir]
            code, out = runner(*call)
            assert code == 3 and out.startswith("[需要核准，沒有執行]") and "0.9" not in read(), (code, out[-600:])
            code, out = runner(*call, "--yes")
            assert code == 0 and "[PASS] 工作流 config_edit（" in out, (code, out[-800:])
            assert "tb1\n    max_speed: 0.9" in read() and "tb2\n    max_speed: 0.5" in read(), read()
            code, out = runner()
            assert code == 0 and "🧩 工作流" in out and "/workflow stuck_package_fix wp_id=<…>" in out, (code, out[-400:])
            code, out = runner("config_edit", "fil=x", "--yes")
            assert code == 4 and "不認識的參數：fil" in out, (code, out[-400:])

        def t_make_skill():
            draft_data = {"purpose": "查 topic 有沒有在發，沒有就重啟發布的容器", "requirements": [], "category": "工作流",
                          "title": "topic 不動就重啟", "description": "某個 topic 沒在發時重啟發布它的容器並確認",
                          "inputs": [{"name": "topic", "description": "要看的 topic", "source": "使用者提供", "example": "/odom"},
                                     {"name": "container", "description": "發布它的容器", "source": "第 1 步的回傳", "example": "nav2"}],
                          "steps": [{"kind": "執行", "instruction": "讀一筆", "skill": "ROS2_topic_echo",
                                     "command": "scripts/ROS2_topic_echo_cmd.py {topic}", "on_failure": "topic 名稱打錯就問使用者"},
                                    {"kind": "檢查", "instruction": "看第 1 步：「的一筆訊息」→ 結束；其他 → 第 3 步", "skill": "", "command": "",
                                     "on_failure": ""},
                                    {"kind": "執行", "instruction": "重啟發布它的容器（照第 1 步）", "skill": "docker_ctl",
                                     "command": "scripts/docker_ctl_cmd.py restart {container}", "on_failure": ""},
                                    {"kind": "告知", "instruction": "回報重啟前後", "skill": "", "command": "", "on_failure": ""}],
                          "success_criteria": "第 3 步的輸出有「Up」", "pitfalls": []}
            agent.skill_model = "x"
            draft = agent._normalize_skill_draft("topic_restart_fix", draft_data, [], [], {"messages": 3, "user_turns": 1, "dropped": 0})
            assert not draft["errors"], draft["errors"]
            assert [i["name"] for i in draft["inputs"]] == ["topic"] and any("{container}" in w and "判斷點" in w for w in draft["warnings"]), draft
            assert draft["changes_state"] is True, "docker_ctl restart 會改變狀態"
            doc = agent.render_skill_doc(draft)
            assert doc.startswith("---\ntype: Workflow\n") and "changes_state: true" in doc, doc[:300]
            msg = agent.register_skill_draft(dict(draft, paths={}))
            assert "已註冊工作流 topic_restart_fix" in msg, msg
            wf = agent.load_workflow("topic_restart_fix")
            assert wf and not agent.validate_workflow(wf) and ws.fill_names(wf, wf["steps"][2]) == ["container"], wf
            assert wf["success"][0]["step"] == 3 and wf["steps"][1]["branches"][0] == {"when": ["的一筆訊息"], "to": "end"}, wf["success"]
            with open(os.path.join(tmp, "skills_system", "SKILLS.md"), encoding="utf-8") as f:
                index = f.read()
            sec = index[index.index("## 工作流"):]
            sec = sec[:sec.index("\n## ", 3)]
            assert "  - `topic_restart_fix` — " in sec and "workflow_run topic_restart_fix topic=<" in sec, sec[-400:]
            assert "topic_restart_fix" in agent.workflow_run("--list")
            bad = dict(draft_data, steps=draft_data["steps"][:1] + [dict(draft_data["steps"][1], instruction="看第 1 步：「x」→ 第 1 步")]
                       + draft_data["steps"][2:])
            draft = agent._normalize_skill_draft("bad_flow", bad, [], [], {"messages": 1, "user_turns": 1, "dropped": 0})
            assert any("不能往回跳" in e for e in draft["errors"]), draft["errors"]

        for name, fn in [("規格：每一份都驗證得過、跟 SKILLS.md 對得上", t_specs), ("解析的細節與驗證找得到的錯", t_parse_details),
                         ("值放進命令：file_ops 解析回來一字不差、其他腳本照 shell 引號", t_values_round_trip),
                         ("完成訊號遺失：程式選分支、模型只填兩個值、成功判準程式跑、存檔", t_run_lost_fin),
                         ("其他原因：提早結束、沒有補發、不問模型", t_run_other_cause),
                         ("選填的沒給就略過；模型填不出值就停下來、不執行", t_skip_and_fail),
                         ("技能回 [ERROR]：帶著錯誤請模型改一次值", t_retry_on_error),
                         ("【確認】停下來、--continue 接著做（前面步驟的輸出從存檔讀回）、--cancel；關卡由模型判斷", t_confirm_pause_continue),
                         ("比對不出分支、又沒有「其他」：交給模型選", t_model_branch),
                         ("參數錯誤與確認關卡的說明", t_args_and_guard),
                         ("dispatch：名稱當技能載入、沒有核准不執行、可以關閉", t_dispatch),
                         ("/workflow 與不用互動的入口：列出、看步驟；沒有 --yes 不執行、結束碼、--continue；報告不再提煉；命令列參數", t_workflow_cmd),
                         ("Agent_Runner.py --workflow 當成行程跑：沒有 --yes 不改（3）、--yes 改了（0）、列出（0）、參數錯（4）；不需要模型", t_headless_process),
                         ("/make_skill 產生工作流：前面輸出的值交給判斷點、驗證得過、寫進 workflows/ 與 SKILLS.md；往回跳的擋下", t_make_skill)]:
            check(name, fn)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [r for r in results if not r[1]]
    for name, _, tb in failed:
        print(f"\n---- {name} ----\n{tb}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
