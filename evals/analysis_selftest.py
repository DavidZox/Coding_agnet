"""數據解析（analysis_run：Orchestrator → Workers → Synthesizer）的離線自我測試：假的 ollama.chat 照劇本回答、數據技能回傳用
從真實數據錄下的輸出（evals/analysis_fixtures/，exp_20261014_084506），不需要 Ollama、不需要 docker。

    python3 evals/analysis_selftest.py

測的是 harness 的程式把關（模型能力用真模型量：evals/run_evals.py 的 analysis_* 情境，或直接 /analyze）：
- Orchestrator 的計畫檢查：不存在的 L#／Topic、Log Topic、重複的 Topic → 交回修一次；修不好由程式依關聯度補指派；
- 時間窗：訊號的時間戳前後各取幾秒、重疊的合併、限制在數據範圍內；沒有相關訊號＝整段數據；
- Worker：只准量測技能、--topic 固定成指派的 Topic、reply 裡的動作 JSON 也照做、同一個量測第三次擋下、一個 Key 都沒量時系統代選；
  局部報告的 Frontmatter 數字來自程式量測（模型寫的 analyzed_keys 只留真的量過的）；
- Synthesizer 的 JSON 壞掉：程式拼一份信心低的報告；回傳以 ANALYSIS_REPORT_HEAD 開頭、不再交給摘要 session；
- dispatch 攔下 analysis_run 偽技能並存檔、[ANALYSIS_DATA] 同步目前的數據、腳本拿得到 ANALYSIS_DATA；
- Web：/analyze 的回合（報告進主對話、進度推到右欄）、/api/analysis/state 讀得到 job、檔案端點擋路徑穿越；
- 程式重新啟動時，沒做完的 job 標成中斷。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
COPY = ["agent_core", "skills_system", "analysis_agents", "ops_agents", "context_modes", "web_app", "vision", "subagent",
        "AGENT.md", "Memory.md"]
FIX = os.path.join(HERE, "analysis_fixtures")
DATA = "/workspace/app/diagnostics_package/toolkit/experiment_logs/exp_20261014_084506"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class FakeChat:
    """依 format（schema）分辨角色：Orchestrator／Worker 的每一步／Worker 的局部報告／Synthesizer／主對話。各自照劇本依序回答。"""

    def __init__(self, schemas, plans=(), worker=(), reports=(), synth=(), main=()):
        self.s = schemas
        self.q = {"plan": list(plans), "worker": list(worker), "report": list(reports), "synth": list(synth), "main": list(main)}
        self.seen = {k: [] for k in self.q}

    def _next(self, role, default):
        q = self.q[role]
        return q.pop(0) if q else default

    def __call__(self, model=None, messages=None, format=None, **kw):
        if format is self.s["plan"]:
            role, default = "plan", {}
        elif format is self.s["worker"]:
            role, default = "worker", {"thought": "量測夠了", "reply": "完成", "action": None}
        elif format is self.s["report"]:
            role, default = "report", {"analyzed_keys": [], "anomaly_detected": False, "summary": "沒有異常", "evidence": [], "confidence": "low"}
        elif format is self.s["synth"]:
            role, default = "synth", None
        else:
            role, default = "main", {"thought": "依報告回答", "reply": "依報告：+15.54s 恢復 NORMAL。", "action": None}
        self.seen[role].append(messages)
        out = self._next(role, default)
        content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return {"message": {"content": content}, "prompt_eval_count": 100, "eval_count": 20}


def fake_exec_factory(agent, calls):
    """數據技能的假回傳：mcap_analyzer／rosout_parser 用錄下的 --json 輸出；mcap_feature_measure 依參數回文字或 JSON。"""
    def fake_exec(script_name, script_path, clean_args, extra_env=None):
        calls.append({"script": script_name, "args": list(clean_args), "env": dict(extra_env or {})})
        if script_name == "mcap_analyzer_cmd.py":
            return fixture("index_output.txt")
        if script_name == "rosout_parser_cmd.py":
            return fixture("rosout_output.txt")
        if script_name == "mcap_feature_measure_cmd.py":
            if "--json" in clean_args:
                return fixture("measure_json.txt")
            keys = [clean_args[i + 1] for i in range(len(clean_args) - 1) if clean_args[i] == "--key"]
            if any(k not in ("mode", "stop_reasons", "estop_latched", "latest_reaction") for k in keys):
                return "[ERROR] /system/safety_gate_status 沒有 Key「%s」" % keys[0]
            return fixture("measure_text.txt")
        return f"[ERROR] （自我測試）沒有 {script_name} 的假資料"
    return fake_exec


def main():
    tmp = tempfile.mkdtemp(prefix="analysis_selftest_")
    for item in COPY:
        src = os.path.join(PROJECT, item)
        dst = os.path.join(tmp, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "drafts"))
        elif os.path.exists(src):
            shutil.copy2(src, dst)
    os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
    cwd = os.getcwd()
    os.chdir(tmp)
    sys.path.insert(0, tmp)
    os.environ["WEB_CONSOLE_MODEL"] = "gemma4:e4b"
    os.environ["AGENT_PERF_LOG"] = "0"
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
        from agent_core import model_caps
        model_caps._cache.clear()
        ollama.show = lambda model: {"capabilities": ["completion"]}
        from agent_core.schemas import (ANALYSIS_PLAN_SCHEMA, ANALYSIS_REPORT_SCHEMA, ANALYSIS_WORKER_REPLY_SCHEMA,
                                        ANALYSIS_WORKER_REPORT_SCHEMA)
        from agent_core.config import ANALYSIS_REPORT_HEAD
        from agent_core.protocol import is_exempt_result
        from web_app.state import agent, state
        from web_app import flows
        schemas = {"plan": ANALYSIS_PLAN_SCHEMA, "worker": ANALYSIS_WORKER_REPLY_SCHEMA,
                   "report": ANALYSIS_WORKER_REPORT_SCHEMA, "synth": ANALYSIS_REPORT_SCHEMA}
        agent.target_container = "ros2_web_container"
        agent.analysis_cfg.update(parallel=1, max_workers=3)
        GOOD_PLAN = {"understanding": "安全閘在開頭進入保護停止，之後恢復", "before_sec": 5, "after_sec": 5,
                     "related_signals": [{"id": "L28", "why": "進入 PROTECTIVE_STOP"}, {"id": "L30", "why": "恢復 NORMAL"}],
                     "assignments": [{"topic": "/system/safety_gate_status", "subtask": "看 mode 的跳轉", "signals": ["L28", "L30"]}],
                     "report_focus": "原因與恢復"}
        SYNTH = {"conclusion": "開頭保護停止、+15.54s 恢復", "root_cause": "初始化時沒有安全指令", "confidence": "medium",
                 "timeline": [{"time": "+15.54s", "source": "L30", "event": "恢復 NORMAL"}, {"time": "+0.75s", "source": "L28", "event": "進入 PROTECTIVE_STOP"}],
                 "evidence": [{"source": "/system/safety_gate_status", "fact": "mode PROTECTIVE_STOP $\\rightarrow$ NORMAL @+15.54s"}],
                 "unknowns": ["/cmd_vel_raw 不在數據裡"], "recommendations": ["加錄 /cmd_vel_raw"]}

        def setup(**kw):
            fake = FakeChat(schemas, **kw)
            ollama.chat = fake
            calls = []
            agent._exec_script = fake_exec_factory(agent, calls)
            return fake, calls

        def t_plan_repair():
            bad = {"understanding": "x", "before_sec": 5, "after_sec": 5, "report_focus": "",
                   "related_signals": [{"id": "L99", "why": "不存在"}, {"id": "L28", "why": "ok"}],
                   "assignments": [{"topic": "/nonexistent", "subtask": "a", "signals": []},
                                   {"topic": "/rosout", "subtask": "b", "signals": []},
                                   {"topic": "cmd_vel", "subtask": "c", "signals": []},
                                   {"topic": "/cmd_vel", "subtask": "d", "signals": []}]}
            fake, calls = setup(plans=[bad, GOOD_PLAN], synth=[dict(SYNTH, confidence="high", unknowns=[])])
            out = agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            assert out.startswith(ANALYSIS_REPORT_HEAD), out[:200]
            assert len(fake.seen["plan"]) == 2, "計畫有問題：交回 Orchestrator 修一次"
            fix_prompt = fake.seen["plan"][1][1]["content"]
            for issue in ("L99 不存在", "/nonexistent」不在數據裡", "/rosout 不能指派", "/cmd_vel 重複指派"):
                assert issue in fix_prompt, (issue, fix_prompt[-800:])
            job = json.load(open(os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"], "job.json"), encoding="utf-8"))
            assert [a["topic"] for a in job["plan"]["assignments"]] == ["/system/safety_gate_status"], job["plan"]
            assert job["report"]["confidence"] == "medium" and "程式檢查" in job["report"]["root_cause"], "缺的輸入：信心最多 medium"
            assert [t["time"] for t in job["report"]["timeline"]] == ["+0.75s", "+15.54s"], "時間線依時間排序"
            assert any("cmd_vel_raw" in u for u in job["report"]["unknowns"]) and "尚未確認：" in out
            assert "Log" not in agent._digest_text({"index": json.loads(fixture("index_output.txt").split("\n[ANALYSIS_DATA]")[0]),
                                                    "signals": []})[:2], "沒有 Log 時說明"
            assert any(c["script"] == "rosout_parser_cmd.py" and "--all-nodes" in c["args"] for c in calls)

        def t_auto_assign_and_whole_window():
            fake, calls = setup(plans=[{}, "不是 JSON"], synth=[SYNTH])
            out = agent.analysis_run(f'--data {DATA}')
            assert out.startswith(ANALYSIS_REPORT_HEAD), out[:300]
            job = json.load(open(os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"], "job.json"), encoding="utf-8"))
            topics = [a["topic"] for a in job["plan"]["assignments"]]
            assert job["plan"].get("auto_assigned") and topics and len(set(topics)) == len(topics) <= 3, job["plan"]
            assert "/rosout" not in topics
            assert job["windows"] == [dict(job["windows"][0], id="W1", label="整段數據")], job["windows"]
            assert job["question"].startswith("這段錄製期間"), "沒有問題時用預設問題"

        def t_windows():
            idx = json.loads(fixture("index_output.txt").split("\n[ANALYSIS_DATA]")[0])
            sig = json.loads(fixture("rosout_output.txt").split("\n[ANALYSIS_DATA]")[0])["signals"]
            job = {"index": idx, "signals": sig}
            wins = agent._make_windows(job, [{"id": "L28"}, {"id": "L29"}, {"id": "L30"}], 5, 5)
            assert len(wins) == 2, wins
            w1, w2 = wins
            assert w1["start_ns"] == idx["start_ns"] and set(w1["signals"]) == {"L28", "L29"}, "重疊的合併、開頭限制在數據範圍內"
            l30 = next(s for s in sig if s["id"] == "L30")
            t30 = int(round(l30["first_sec"] * 1e9))
            assert w2["start_ns"] == t30 - 5_000_000_000 and w2["end_ns"] == t30 + 5_000_000_000 and w2["signals"] == ["L30"]
            assert w2["label"].startswith("L30 INFO safety_motion_controller")
            rec_only = [s for s in sig if s["node"] == "rosbag2_recorder"]
            text = agent._digest_text({"index": idx, "signals": rec_only})
            assert "全部是錄製工具 rosbag2 自己的訊息" in text and "沒有 /rosout" not in text, "只有 rosbag2 的 Log：不能說成沒有 Log"
            assert "（錄製工具 rosbag2 自己的 Log）" in agent._digest_text({"index": idx, "signals": rec_only}, limit=None, include_recorder=True)
            far = agent._make_windows({"index": idx, "signals": [dict(l30, times_sec=[1.0], first_sec=1.0)]}, [{"id": "L30"}], 5, 5)
            assert far[0]["label"].startswith("整段數據"), "Log 的時間不在數據範圍內：退回整段數據"

        def t_worker_rules():
            reply_action = {"thought": "量 mode", "action": None,
                            "reply": json.dumps({"command": "scripts/mcap_feature_measure_cmd.py", "args": "--key mode"})}
            same = {"thought": "再量一次", "reply": "量 mode", "action": {"command": "mcap_feature_measure", "args": "--key mode"}}
            other = {"thought": "也看看別的 Topic", "reply": "", "action": {"command": "scripts/mcap_feature_measure_cmd.py",
                                                                          "args": "--topic /cmd_vel --key linear"}}
            shell = {"thought": "用 shell", "reply": "", "action": {"command": "scripts/host_runcmd_cmd.py", "args": "ls"}}
            done = {"thought": "夠了", "reply": "完成", "action": None}
            report = {"analyzed_keys": ["mode", "不存在的Key"], "anomaly_detected": True, "summary": "mode 在 +15.54s 由 PROTECTIVE_STOP 變 NORMAL",
                      "evidence": [{"time": "+15.54s", "key": "mode", "observation": "PROTECTIVE_STOP $\\rightarrow$ NORMAL"}], "confidence": "high"}
            fake, calls = setup(plans=[GOOD_PLAN], worker=[reply_action, other, shell, same, same, done], reports=[report], synth=[SYNTH])
            out = agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            measure = [c for c in calls if c["script"] == "mcap_feature_measure_cmd.py"]
            text_calls = [c for c in measure if "--json" not in c["args"]]
            assert len(text_calls) == 2, [c["args"] for c in measure]   # reply 裡的動作照做＋同一個量測第二次；第三次擋下
            assert all(c["args"][:2] == ["--topic", "/system/safety_gate_status"] for c in measure), "--topic 固定成指派的 Topic"
            assert all(c["env"]["ANALYSIS_TOPIC"] == "/system/safety_gate_status" and json.loads(c["env"]["ANALYSIS_WINDOWS"])
                       for c in measure), "系統帶入 Topic 與時間窗"
            tr = "\n".join(m["content"] for m in fake.seen["report"][0])
            assert "你只負責 /system/safety_gate_status" in tr and "worker 只能用 mcap_feature_measure" in tr
            assert "同一個量測已經做了 3 次" in tr
            job_dir = os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"])
            md = open(os.path.join(job_dir, "workers", "W1_system_safety_gate_status.md"), encoding="utf-8").read()
            fm = dict(line.split(": ", 1) for line in md.split("---\n")[1].strip().splitlines())
            assert json.loads(fm["analyzed_keys"]) == ["mode"], "analyzed_keys 只留真的量過的"
            metrics = json.loads(fm["key_metrics"])
            assert metrics["W1"]["mode"]["transitions"] == 1 and metrics["W1"]["mode"]["last"] == "NORMAL", metrics
            assert json.loads(fm["anomaly_detected"]) is True and json.loads(fm["topic"]) == "/system/safety_gate_status"
            assert "PROTECTIVE_STOP → NORMAL" in md and "rightarrow" not in md, "LaTeX 箭頭換成 →"
            assert os.path.exists(os.path.join(job_dir, "workers", "W1_system_safety_gate_status.transcript.md"))
            report_md = open(os.path.join(job_dir, "report.md"), encoding="utf-8").read()
            assert report_md.startswith("---\nartifact: \"diagnosis_report\"") and "mode PROTECTIVE_STOP → NORMAL" in report_md
            synth_prompt = fake.seen["synth"][0][1]["content"]
            assert "NO_CMD_VEL_RAW" in synth_prompt and "沒有名稱含「cmd_vel_raw」的 Topic" in synth_prompt, "程式檢查：缺的輸入交給 Synthesizer"
            assert "safety_command」的 Topic" not in synth_prompt, "NO_SAFETY_COMMAND_YET 對得上 /system/safety_command，不算缺"
            job = json.load(open(os.path.join(job_dir, "job.json"), encoding="utf-8"))
            assert [g["reason"] for g in job["coverage_gaps"]] == ["NO_CMD_VEL_RAW"], job["coverage_gaps"]
            assert "→ NORMAL" in out and "rightarrow" not in out

        def t_worker_fallback_and_synth_fallback():
            fake, calls = setup(plans=[GOOD_PLAN], worker=[{"thought": "a", "reply": "看起來沒事", "action": None}] * 3,
                                synth=["{壞掉的 JSON"])
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            job = json.load(open(os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"], "job.json"), encoding="utf-8"))
            w = job["workers"][0]
            assert w["key_selection"] == "fallback" and w["analyzed_keys"], w
            nudges = [m["content"] for m in fake.seen["worker"][1] if m["role"] == "user"]
            assert any("你還沒有量測任何 Key" in t for t in nudges), "沒量測就說完成：先推回去一次"
            assert job["report"]["confidence"] == "low" and out.startswith(ANALYSIS_REPORT_HEAD), job["report"]
            assert any("cmd_vel_raw" in u for u in job["report"]["unknowns"]), "缺的輸入一定列在尚未確認"
            assert is_exempt_result(out, 5000), "報告不再交給摘要 session"

        def t_dispatch_and_state():
            fake, calls = setup(plans=[GOOD_PLAN], synth=[SYNTH])
            agent.analysis_data = ""
            out = agent.run_tool({"action": {"command": "scripts/analysis_run_cmd.py", "args": f'--data {DATA} "安全閘"'}})
            assert out.startswith(ANALYSIS_REPORT_HEAD) and agent.last_result_id, (out[:100], agent.last_result_id)
            assert agent.trajectory[-1]["script"] == "analysis_run_cmd.py"
            assert agent.analysis_data == DATA, "[ANALYSIS_DATA] 同步目前的數據"
            assert "CURRENT_ANALYSIS_DATA: " + DATA in agent.build_state_tail()
            assert agent.analysis_run("").startswith("[PASS]"), "省略 --data：用目前的數據"
            agent.analysis_data = ""
            assert agent.analysis_run('"q"').startswith("[ERROR] analysis_run 需要數據")
            # 真的 _exec_script：腳本拿得到 ANALYSIS_DATA 與 extra_env
            from agent_core.agent import SkillAgent
            real = SkillAgent.__dict__["_exec_script"] if "_exec_script" in SkillAgent.__dict__ else None
            from agent_core.dispatch import DispatchMixin
            probe = os.path.join(tmp, "probe_env.py")
            with open(probe, "w") as f:
                f.write("import os\nprint(os.environ.get('ANALYSIS_DATA'), os.environ.get('ANALYSIS_TOPIC'))\n")
            agent.analysis_data = "/data/x"
            got = DispatchMixin._exec_script(agent, "probe_env.py", probe, [], extra_env={"ANALYSIS_TOPIC": "/t"})
            assert got == "/data/x /t", got
            del real

        def t_web():
            state["auto_mode"] = True
            fake, calls = setup(plans=[GOOD_PLAN], synth=[SYNTH])
            events = []
            agent.progress_callback = lambda text: events.append({"channel": "progress", "text": text})
            try:
                agent.messages.append({"role": "user", "content": "安全閘為什麼停下來"})
                awaiting = flows.run_analysis_turn("安全閘為什麼停下來", events, data=DATA)
            finally:
                agent.progress_callback = None
                state["auto_mode"] = False
            assert awaiting is False
            assert any(e["channel"] == "progress" and "數據分析 job" in e["text"] for e in events), "進度推到右欄"
            assert any(e["channel"] == "tool" and e["text"].startswith(ANALYSIS_REPORT_HEAD) for e in events)
            assert any(m["role"] == "user" and ANALYSIS_REPORT_HEAD in m["content"] for m in agent.messages), "報告進主對話"
            chats = [e for e in events if e["channel"] == "chat"]
            assert chats and "15.54" in chats[-1]["text"] and not chats[-1].get("action"), "主模型依報告回答"
            from web_app.analysis import analysis_file, analysis_state, handle_analysis_command
            st = analysis_state()
            assert st["detail"]["job"]["status"] == "done" and "report.md" in st["detail"]["files"], st["detail"]["job"]["status"]
            assert analysis_file(st["detail"]["job"]["id"], "../../model_settings.json") is None, "擋路徑穿越"
            ev = []
            handle_analysis_command("/analysis_mode on", ev)
            assert state["analysis_mode"] and "分析模式" in ev[-1]["text"]
            handle_analysis_command("/analysis_mode off", ev)
            handle_analysis_command("/analysis_workers 9", ev)
            assert "⚠️" in ev[-1]["text"], "worker 上限 1～8"
            stats = flows.build_stats()
            assert stats["analysis"]["status"] == "done" and "analysis_mode" in stats

        def t_mark_interrupted():
            d = os.path.join(agent.analysis_jobs_dir(), "20200101_000000")
            os.makedirs(d, exist_ok=True)
            for name, body in (("job.json", {"id": "20200101_000000", "status": "working"}), ("events.jsonl", {"text": "x"})):
                with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                    json.dump(body, f)
                os.utime(os.path.join(d, name), (1, 1))
            fresh = os.path.join(agent.analysis_jobs_dir(), "20200101_000001")
            os.makedirs(fresh, exist_ok=True)
            with open(os.path.join(fresh, "job.json"), "w", encoding="utf-8") as f:
                json.dump({"id": "20200101_000001", "status": "working"}, f)
            assert agent.analysis_mark_interrupted() == 1, "只標進度很久沒更新的"
            job = json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))
            assert job["status"] == "failed" and "Workers 分析" in job["error"], job
            assert json.load(open(os.path.join(fresh, "job.json"), encoding="utf-8"))["status"] == "working"
            shutil.rmtree(d)
            shutil.rmtree(fresh)

        for name, fn in [("Orchestrator：不存在的 L#／Topic、Log Topic、重複的 Topic 交回修一次（程式列出具體的問題）", t_plan_repair),
                         ("Orchestrator 給不出計畫：程式依關聯度補指派（不重複、不派 Log）；沒有相關訊號＝整段數據；預設問題", t_auto_assign_and_whole_window),
                         ("時間窗：訊號前後各取幾秒、重疊的合併、限制在數據範圍內；Log 的時間不在範圍內退回整段", t_windows),
                         ("Worker：reply 裡的動作照做、--topic 固定、只准量測技能、第三次相同量測擋下；Frontmatter 數字來自程式", t_worker_rules),
                         ("Worker 沒量測：推回去一次、系統代選 Key；Synthesizer 壞掉：程式拼一份信心低的報告", t_worker_fallback_and_synth_fallback),
                         ("dispatch：analysis_run 偽技能存檔與軌跡、[ANALYSIS_DATA] 同步、省略 --data、腳本拿得到環境變數", t_dispatch_and_state),
                         ("Web：/analyze 的回合（進度、報告進主對話、主模型依報告回答）、面板 state、分析模式指令", t_web),
                         ("程式重新啟動：沒做完的 job（進度很久沒更新）標成中斷，剛更新的不動", t_mark_interrupted)]:
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
