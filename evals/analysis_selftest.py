"""數據分析（analysis_run：Orchestrator → Workers → 事實（程式）→ Synthesizer 摘要 → Orchestrator 檢查）的離線自我測試：
假的 ollama.chat 照劇本回答、數據技能回傳用從真實數據錄下的輸出（evals/analysis_fixtures/，exp_20261014_084506），
不需要 Ollama、不需要 docker。

    python3 evals/analysis_selftest.py

測的是 harness 的程式把關（模型能力用真模型量：test_data/tools/run_regression.py，或直接 /analyze）：
- Orchestrator 的計畫檢查：不存在的 L#／Topic、Log Topic、重複的 Topic → 交回修一次（重複的 L# 只合併）；修不好由程式依關聯度補指派；
- Worker：只准量測技能、--topic 固定成指派的 Topic、時間窗拿掉（量整段）、reply 裡的動作 JSON 也照做、同一個量測第三次擋下、
  一個 Key 都沒量時系統代選；局部報告的事實來自程式量測（模型寫的 analyzed_keys 只留真的量過的）；用詞跟量測不符、寫原因交回修一次；
- 事實（程式）：每個 Topic 的類別、發布、變化、到最後的值；時間線的 Topic 事件與 Log、前後 1 秒內的對照、同時發生的變化、
  前後沒有變化的 Log、沒有分析的 Topic；
- Synthesizer 的摘要：寫原因、推測、跟量測不符的用詞交回修一次，還在就標「程式核對：未修正」；JSON 壞掉時程式寫一份；
- Orchestrator 檢查：前後沒有量到變化的 Log＋還有沒量的 Topic 才問；補量的程式核對；最多補一輪、report_r1.md；
- 一次最多 3 分鐘、拿掉的選項說清楚；回傳以 ANALYSIS_REPORT_HEAD 開頭、不再交給摘要 session；
- dispatch 攔下 analysis_run 偽技能並存檔、[ANALYSIS_DATA] 同步目前的數據、腳本拿得到 ANALYSIS_DATA；
- Web：/analyze 的回合（報告進主對話、進度推到右欄）、/api/analysis/state 讀得到 job、檔案端點擋路徑穿越；
- 程式重新啟動時，沒做完的 job 標成中斷。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import re
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


def fixture_json(name):
    return json.loads(fixture(name).split("\n[ANALYSIS_DATA]")[0])


SUMMARY_DEFAULT = {"summary": "安全閘的 mode 在 +15.54s 由 PROTECTIVE_STOP 變成 NORMAL。"}


class FakeChat:
    """依 format（schema）分辨角色：Orchestrator 規劃／Orchestrator 檢查／Worker 的每一步／Worker 的局部報告／Synthesizer 的摘要／
    主對話。各自照劇本依序回答。"""

    def __init__(self, schemas, plans=(), checks=(), worker=(), reports=(), summaries=(), main=()):
        self.s = schemas
        self.q = {"plan": list(plans), "check": list(checks), "worker": list(worker), "report": list(reports),
                  "summary": list(summaries), "main": list(main)}
        self.seen = {k: [] for k in self.q}

    def _next(self, role, default):
        q = self.q[role]
        return q.pop(0) if q else default

    def __call__(self, model=None, messages=None, format=None, **kw):
        if format is self.s["plan"]:
            role, default = "plan", {}
        elif format is self.s["check"]:
            role, default = "check", {"followups": []}
        elif format is self.s["summary"]:
            role, default = "summary", SUMMARY_DEFAULT
        elif format is self.s["worker"]:
            role, default = "worker", {"thought": "量測夠了", "reply": "完成", "action": None}
        elif format is self.s["report"]:
            role, default = "report", {"analyzed_keys": [], "summary": "mode 在 +15.54s 由 PROTECTIVE_STOP 變成 NORMAL"}
        else:
            role, default = "main", {"thought": "依報告回答", "reply": "依報告：+15.54s 恢復 NORMAL。", "action": None}
        self.seen[role].append(messages)
        out = self._next(role, default)
        content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return {"message": {"content": content}, "prompt_eval_count": 100, "eval_count": 20}


def fake_exec_factory(agent, calls, extra_signals=(), index=None):
    """數據技能的假回傳：mcap_analyzer／rosout_parser 用錄下的 --json 輸出（extra_signals：多加的 Log 訊號；index：換掉 Topic Metadata）；
    mcap_feature_measure 依參數回文字或 JSON。"""
    def fake_exec(script_name, script_path, clean_args, extra_env=None):
        calls.append({"script": script_name, "args": list(clean_args), "env": dict(extra_env or {})})
        if script_name == "mcap_analyzer_cmd.py":
            return (json.dumps(index) + f"\n[ANALYSIS_DATA] {DATA}") if index else fixture("index_output.txt")
        if script_name == "rosout_parser_cmd.py":
            if not extra_signals:
                return fixture("rosout_output.txt")
            logs = fixture_json("rosout_output.txt")
            logs["signals"] = logs["signals"] + list(extra_signals)
            return json.dumps(logs, ensure_ascii=False) + f"\n[ANALYSIS_DATA] {DATA}"
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
        from agent_core.schemas import (ANALYSIS_CHECK_SCHEMA, ANALYSIS_PLAN_SCHEMA, ANALYSIS_SUMMARY_SCHEMA, ANALYSIS_WORKER_REPLY_SCHEMA,
                                        ANALYSIS_WORKER_REPORT_SCHEMA)
        from agent_core.config import ANALYSIS_REPORT_HEAD
        from agent_core.protocol import is_exempt_result
        from web_app.state import agent, state
        from web_app import flows
        schemas = {"plan": ANALYSIS_PLAN_SCHEMA, "check": ANALYSIS_CHECK_SCHEMA, "summary": ANALYSIS_SUMMARY_SCHEMA,
                   "worker": ANALYSIS_WORKER_REPLY_SCHEMA, "report": ANALYSIS_WORKER_REPORT_SCHEMA}
        agent.target_container = "ros2_web_container"
        agent.analysis_cfg.update(parallel=1, max_workers=3, rounds=2)
        GOOD_PLAN = {"understanding": "安全閘在開頭進入保護停止，之後恢復",
                     "related_signals": [{"id": "L28", "why": "進入 PROTECTIVE_STOP"}, {"id": "L30", "why": "恢復 NORMAL"}],
                     "assignments": [{"topic": "/system/safety_gate_status", "subtask": "看 mode 的跳轉"}]}
        LIDAR = {"id": "L32", "level": "WARN", "node": "lidar_driver", "count": 1, "message": "LiDAR timeout",
                 "first_sec": 1791967537.0117, "last_sec": 1791967537.0117, "times_sec": [1791967537.0117],
                 "sources": [{"file": "/workspace/ws/src/lidar_pkg/src/lidar_node.cpp", "function": "checkTimeout", "line": 88}]}

        def setup(extra_signals=(), index=None, **kw):
            fake = FakeChat(schemas, **kw)
            ollama.chat = fake
            calls = []
            agent._exec_script = fake_exec_factory(agent, calls, extra_signals, index)
            return fake, calls

        def last_job():
            d = os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"])
            return d, json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))

        def t_plan_repair():
            bad = {"understanding": "x", "related_signals": [{"id": "L99", "why": "不存在"}, {"id": "L28", "why": "ok"}],
                   "assignments": [{"topic": "/nonexistent", "subtask": "a"}, {"topic": "/rosout", "subtask": "b"},
                                   {"topic": "cmd_vel", "subtask": "c"}, {"topic": "/cmd_vel", "subtask": "d"}]}
            fake, calls = setup(plans=[bad, GOOD_PLAN])
            out = agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            assert out.startswith(ANALYSIS_REPORT_HEAD), out[:200]
            assert len(fake.seen["plan"]) == 2, "計畫有問題：交回 Orchestrator 修一次"
            fix_prompt = fake.seen["plan"][1][1]["content"]
            for issue in ("L99 不存在", "/nonexistent」不在數據裡", "/rosout 不能指派", "/cmd_vel 重複指派"):
                assert issue in fix_prompt, (issue, fix_prompt[-800:])
            plan_prompt = fake.seen["plan"][0][1]["content"]
            assert "量整段數據" in plan_prompt and "before_sec" not in plan_prompt and "【源碼" not in plan_prompt, plan_prompt[-600:]
            d, job = last_job()
            assert [a["topic"] for a in job["plan"]["assignments"]] == ["/system/safety_gate_status"], job["plan"]
            assert "windows" not in job and "slices" not in job, "沒有時間窗、不切片：量整段"
            tl = job["report"]["timeline"]
            assert [float(t["time"].strip("+s")) for t in tl] == sorted(float(t["time"].strip("+s")) for t in tl), "時間線依時間排序"
            assert {("+0.75s", "L28 WARN safety_motion_controller"), ("+15.54s", "L30 INFO safety_motion_controller")} <= \
                {(t["time"], t["source"]) for t in tl}, "相關的與 WARN 以上的 Log 由程式依時間戳放進時間線"
            assert job["status"] == "done" and not job.get("checks", [{}])[0].get("asked"), "每則相關的 Log 前後都有量到的變化：不問要不要補量"
            assert "Log" not in agent._digest_text({"index": fixture_json("index_output.txt"), "signals": []})[:2], "沒有 Log 時說明"
            assert any(c["script"] == "rosout_parser_cmd.py" and "--all-nodes" in c["args"] for c in calls)
            assert not any(c["script"] == "mcap_slicer_cmd.py" for c in calls)

        def t_plan_duplicate_signal():
            # 同一個 L# 列兩次（大小寫不同也算）：合併就好，不交回修正（實測 26b 重複列 L17，舊版報成「L17 不存在」退回一次）
            dup = dict(GOOD_PLAN, related_signals=[{"id": "L28", "why": "a"}, {"id": "l28", "why": "b"}, {"id": "L30", "why": "c"}])
            fake, calls = setup(plans=[dup])
            agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            assert len(fake.seen["plan"]) == 1, "重複的 L# 不交回修正"
            d, job = last_job()
            assert [r["id"] for r in job["plan"]["related"]] == ["L28", "L30"] and not job["plan"]["issues"], job["plan"]

        def t_rate_facts():
            # 一段完整的發布（中途開始又中途停止、中間沒有中斷）＝開始與停止兩個事件、不是中斷；真的中斷＝中斷與恢復兩個事件、
            # 程式判斷的異常。worker 不判斷異常；Synthesizer 拿到程式整理的事實，不拿問題
            base_js = fixture_json("measure_json.txt")
            rate = base_js["windows"][0]["rate"]
            seg = json.loads(json.dumps(base_js))
            seg["windows"][0]["rate"].update(messages=80, single_session=True, started_late=True, stopped_early=True, gaps=[])
            gap = json.loads(json.dumps(base_js))
            gap["windows"][0]["rate"].update(messages=80, gaps=[{"start_sec": rate["first_sec"] + 2, "duration_sec": 5.0}])
            measure = {"thought": "量 mode", "reply": "", "action": {"command": "scripts/mcap_feature_measure_cmd.py", "args": "--key mode"}}
            calm = {"analyzed_keys": ["mode"], "summary": "mode 在 +15.54s 由 PROTECTIVE_STOP 變成 NORMAL"}
            for js, broken in ((seg, False), (gap, True)):
                fake, calls = setup(plans=[GOOD_PLAN], worker=[measure], reports=[calm])
                plain = agent._exec_script

                def exec_with(script_name, script_path, clean_args, extra_env=None, _js=js, _plain=plain):
                    if script_name == "mcap_feature_measure_cmd.py" and "--json" in clean_args:
                        return json.dumps(_js, ensure_ascii=False) + f"\n[ANALYSIS_DATA] {DATA}"
                    return _plain(script_name, script_path, clean_args, extra_env)
                agent._exec_script = exec_with
                agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
                d, job = last_job()
                w = job["workers"][0]
                assert "anomaly_detected" not in w and bool(w["program_anomalies"]) is broken, w["program_anomalies"]   # 舊版工具沒有 anomalies：照量到的中斷
                row = job["report"]["topics"][0]
                events = [t["event"] for t in job["report"]["timeline"] if t["source"].startswith("W1")]
                if broken:
                    assert "訊息中斷" in row["tags"] and "開始或停止發布" not in row["tags"], row
                    assert "訊息中斷 5.00 秒" in events and any(e.startswith("恢復發布") for e in events), events
                else:
                    assert row["tags"][0] == "開始或停止發布" and "訊息中斷" not in row["tags"] and "一段完整的發布" in row["publish"], row
                    assert "開始發布（之前沒有訊息）" in events and "停止發布（之後到數據結束沒有訊息）" in events, events
                sp = fake.seen["summary"][0][1]["content"]
                assert "【各 Topic 的結果（程式從量測結果整理）】" in sp and "【使用者的問題】" not in sp and "安全閘為什麼停下來" not in sp, sp[:600]
                assert ("恢復發布" in sp) is broken and ("一段完整的發布" in sp) is (not broken)

        def t_category_not_key():
            # Key 目錄的類別寫中文（英文的 state 每一列都有，實測 26b 送 --key state）；工具略過不存在的 Key、把「類別.Key」改寫成 Key 時，
            # worker 照輸出的「▸ Key（」算真的量到的
            measure = {"thought": "量安全狀態", "reply": "", "action": {"command": "scripts/mcap_feature_measure_cmd.py",
                                                                  "args": "--key state --key state.mode"}}
            fake, calls = setup(plans=[GOOD_PLAN], worker=[measure], reports=[{"analyzed_keys": ["mode"], "summary": "mode 跳轉一次"}])
            plain = agent._exec_script

            def exec_new_tool(script_name, script_path, clean_args, extra_env=None, _plain=plain):
                if script_name == "mcap_feature_measure_cmd.py" and "--json" not in clean_args:   # 新版工具：略過 state、state.mode 換成 mode
                    return fixture("measure_text.txt").replace("程式判斷的異常（訊息中斷）", "沒有量測：state（沒有這個 Key：state 是 Key 的類別（狀態），不是 Key）\n程式判斷的異常（訊息中斷）")
                return _plain(script_name, script_path, clean_args, extra_env)
            agent._exec_script = exec_new_tool
            agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            brief = fake.seen["worker"][0][1]["content"]
            assert "- mode｜狀態｜scalar｜string" in brief and "｜state｜" not in brief, brief[-900:]
            assert "【數據】整段 +0.00s～+51.89s（51.9 秒）：量測工具量的是整段，不用寫時間窗" in brief, brief[:900]
            d, job = last_job()
            w = job["workers"][0]
            assert w["key_selection"] == "worker" and w["analyzed_keys"] == ["mode"], w
            keys_order = [k["key"] for t in fixture_json("index_output.txt")["topics"] if t["topic"] == "/system/safety_gate_status" for k in t["keys"]]
            assert "mode" in w["fact_keys"] and "stop_reasons" in w["fact_keys"] and not any(k.startswith("header.") for k in w["fact_keys"]), \
                "程式最後量測：worker 挑的 Key＋這個 Topic 全部的狀態類 Key"
            assert w["fact_keys"] == [k for k in keys_order if k in w["fact_keys"]], "照 Topic Metadata 的順序（不看 worker 先量哪個）"
            sp = fake.seen["summary"][0][1]["content"]
            assert "【各 worker 的局部報告】" not in sp and "mode 跳轉一次" not in sp, "Synthesizer 只拿程式整理的事實"

        def t_auto_assign_and_default_question():
            fake, calls = setup(plans=[{}, "不是 JSON"])
            out = agent.analysis_run(f'--data {DATA}')
            assert out.startswith(ANALYSIS_REPORT_HEAD), out[:300]
            d, job = last_job()
            topics = [a["topic"] for a in job["plan"]["assignments"]]
            assert job["plan"].get("auto_assigned") and topics and len(set(topics)) == len(topics) <= 3, job["plan"]
            assert "/rosout" not in topics
            assert job["question"] == "這段錄製期間發生了哪些狀態變化？", "沒有問題時用預設問題"
            assert not any(c["script"] == "mcap_slicer_cmd.py" for c in calls), "不切片"

        def t_worker_rules():
            reply_action = {"thought": "量 mode", "action": None,
                            "reply": json.dumps({"command": "scripts/mcap_feature_measure_cmd.py", "args": "--key mode --window W1"})}
            same = {"thought": "再量一次", "reply": "量 mode", "action": {"command": "mcap_feature_measure", "args": "--key mode"}}
            other = {"thought": "也看看別的 Topic", "reply": "", "action": {"command": "scripts/mcap_feature_measure_cmd.py",
                                                                          "args": "--topic /cmd_vel --key linear"}}
            shell = {"thought": "用 shell", "reply": "", "action": {"command": "scripts/host_runcmd_cmd.py", "args": "ls"}}
            done = {"thought": "夠了", "reply": "完成", "action": None}
            report = {"analyzed_keys": ["mode", "不存在的Key"], "summary": "mode 在 +15.54s 由 PROTECTIVE_STOP $\\rightarrow$ NORMAL"}
            fake, calls = setup(plans=[GOOD_PLAN], worker=[reply_action, other, shell, same, same, done], reports=[report])
            out = agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            measure = [c for c in calls if c["script"] == "mcap_feature_measure_cmd.py"]
            text_calls = [c for c in measure if "--json" not in c["args"]]
            assert len(text_calls) == 2, [c["args"] for c in measure]   # reply 裡的動作照做＋同一個量測第二次；第三次擋下
            assert all(c["args"][:2] == ["--topic", "/system/safety_gate_status"] for c in measure), "--topic 固定成指派的 Topic"
            assert all("--window" not in c["args"] and c["env"]["ANALYSIS_TOPIC"] == "/system/safety_gate_status"
                       and c["env"]["ANALYSIS_WINDOWS"] == "" for c in measure), "量整段：時間窗拿掉、不帶時間窗"
            tr = "\n".join(m["content"] for m in fake.seen["report"][0])
            assert "你只負責 /system/safety_gate_status" in tr and "worker 只能用 mcap_feature_measure" in tr
            assert "同一個量測已經做了 3 次" in tr
            d, job = last_job()
            md = open(os.path.join(d, "workers", "W1_system_safety_gate_status.md"), encoding="utf-8").read()
            fm = dict(line.split(": ", 1) for line in md.split("---\n")[1].strip().splitlines())
            assert json.loads(fm["analyzed_keys"]) == ["mode"], "analyzed_keys 只留真的量過的"
            items = json.loads(fm["measure"])["items"]
            assert items[0]["name"] == "mode" and items[0]["count"] == 1 and items[0]["last"] == "NORMAL", items
            assert json.loads(fm["topic"]) == "/system/safety_gate_status" and "anomaly_detected" not in fm and "report_issues" not in fm
            assert "PROTECTIVE_STOP → NORMAL" in md and "rightarrow" not in md, "LaTeX 箭頭換成 →"
            assert os.path.exists(os.path.join(d, "workers", "W1_system_safety_gate_status.transcript.md"))
            report_md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
            assert report_md.startswith("---\nartifact: \"fact_report\"") and "mode：PROTECTIVE_STOP → NORMAL（+15.54s）" in report_md, report_md[:1500]
            assert "原因要對照源碼另外分析" in report_md and "## 根因" not in report_md and "## 結論" not in report_md
            assert GOOD_PLAN["understanding"] not in report_md and "Orchestrator 挑的相關 Log：L28、L30" in report_md, "規劃用的文字不進事實報告"
            assert job["workers"][0]["measure"]["items"] == items, "程式量的事實也留在 job 裡"
            assert "mode＝NORMAL（開頭 PROTECTIVE_STOP）" in out and "rightarrow" not in out, out[:1500]

        def t_worker_fallback_and_summary_fallback():
            fake, calls = setup(plans=[GOOD_PLAN], worker=[{"thought": "a", "reply": "看起來沒事", "action": None}] * 3,
                                summaries=["{壞掉的 JSON"])
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            w = job["workers"][0]
            assert w["key_selection"] == "fallback" and w["analyzed_keys"], w
            nudges = [m["content"] for m in fake.seen["worker"][1] if m["role"] == "user"]
            assert any("你還沒有量測任何 Key" in t for t in nudges), "沒量測就說完成：先推回去一次"
            assert job["report"]["summary"].startswith("（Synthesizer 沒有產生摘要，以下由程式整理）W1 /system/safety_gate_status：狀態改變"), job["report"]
            assert out.startswith(ANALYSIS_REPORT_HEAD) and is_exempt_result(out, 5000), "報告不再交給摘要 session"
            assert "系統代選 Key" in open(os.path.join(d, "report.md"), encoding="utf-8").read()

        def t_dispatch_and_state():
            fake, calls = setup(plans=[GOOD_PLAN])
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
            from agent_core.dispatch import DispatchMixin
            probe = os.path.join(tmp, "probe_env.py")
            with open(probe, "w") as f:
                f.write("import os\nprint(os.environ.get('ANALYSIS_DATA'), os.environ.get('ANALYSIS_TOPIC'))\n")
            agent.analysis_data = "/data/x"
            got = DispatchMixin._exec_script(agent, "probe_env.py", probe, [], extra_env={"ANALYSIS_TOPIC": "/t"})
            assert got == "/data/x /t", got

        def t_web():
            state["auto_mode"] = True
            fake, calls = setup(plans=[GOOD_PLAN])
            events = []
            agent.progress_callback = lambda text: events.append({"channel": "progress", "text": text})
            try:
                agent.messages.append({"role": "user", "content": "安全閘停下來的前後發生了什麼"})
                awaiting = flows.run_analysis_turn("安全閘停下來的前後發生了什麼", events, data=DATA)
            finally:
                agent.progress_callback = None
                state["auto_mode"] = False
            assert awaiting is False
            assert any(e["channel"] == "progress" and "數據分析 job" in e["text"] for e in events), "進度推到右欄"
            assert any(e["channel"] == "tool" and e["text"].startswith(ANALYSIS_REPORT_HEAD) for e in events)
            assert any(m["role"] == "user" and ANALYSIS_REPORT_HEAD in m["content"] for m in agent.messages), "報告進主對話"
            chats = [e for e in events if e["channel"] == "chat"]
            assert chats and "15.54" in chats[-1]["text"] and not chats[-1].get("action"), "主模型依報告回答"
            from web_app.analysis import analysis_file, analysis_state, handle_analysis_command, settings_view
            st = analysis_state()
            assert st["detail"]["job"]["status"] == "done" and "report.md" in st["detail"]["files"], st["detail"]["job"]["status"]
            assert analysis_file(st["detail"]["job"]["id"], "../../model_settings.json") is None, "擋路徑穿越"
            assert set(settings_view()) >= {"rounds", "max_workers"} and not {"before", "after", "source_root", "program_hints"} & set(settings_view())
            ev = []
            handle_analysis_command("/analysis_mode on", ev)
            assert state["analysis_mode"] and "分析模式" in ev[-1]["text"]
            handle_analysis_command("/analysis_mode off", ev)
            handle_analysis_command("/analysis_workers 9", ev)
            assert "⚠️" in ev[-1]["text"], "worker 上限 1～8"
            handle_analysis_command("/analysis_source ~/ws/src", ev)
            assert "已經拿掉" in ev[-1]["text"], "拿掉的設定說清楚"
            stats = flows.build_stats()
            assert stats["analysis"]["status"] == "done" and "analysis_mode" in stats
            # 「/analyze --data X 問題」：選項照原樣交給 analysis_run（以前整段加引號當成問題，數據靜靜地用了目前的）
            seen = []
            real = agent.run_tool
            agent.run_tool = lambda parsed, approved=False: (seen.append(parsed["action"]["args"]), "[ERROR] 測試：不執行")[1]
            try:
                flows.run_analysis_turn("--data exp_other LiDAR 出錯之後發生了什麼", [], data=DATA)
                flows.run_analysis_turn("--topic /cmd_vel 什麼時候歸零", [], data=DATA)
                flows.run_analysis_turn("安全閘停下來的前後發生了什麼", [], data=DATA)
            finally:
                agent.run_tool = real
            assert seen[0] == "--data exp_other LiDAR 出錯之後發生了什麼", seen
            assert seen[1].startswith("--data ") and seen[1].endswith(" --topic /cmd_vel 什麼時候歸零"), seen
            assert seen[2].endswith('"安全閘停下來的前後發生了什麼"') or seen[2].endswith("安全閘停下來的前後發生了什麼"), seen

        def t_mark_interrupted():
            made = []
            for jid, status, old in (("20200101_000000", "working", True), ("20200101_000002", "reasoning", True),
                                     ("20200101_000001", "working", False)):
                d = os.path.join(agent.analysis_jobs_dir(), jid)
                os.makedirs(d, exist_ok=True)
                made.append(d)
                for name, body in (("job.json", {"id": jid, "status": status}), ("events.jsonl", {"text": "x"})):
                    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                        json.dump(body, f)
                    if old:
                        os.utime(os.path.join(d, name), (1, 1))
            assert agent.analysis_mark_interrupted() == 2, "只標進度很久沒更新的（第九輪以前的 reasoning 也算）"
            job = json.load(open(os.path.join(made[0], "job.json"), encoding="utf-8"))
            assert job["status"] == "failed" and "Workers 分析" in job["error"], job
            assert json.load(open(os.path.join(made[2], "job.json"), encoding="utf-8"))["status"] == "working"
            for d in made:
                shutil.rmtree(d)

        def t_recorder_target():
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "mcap_recorder_cmd", os.path.join(tmp, "skills_system", "scripts", "mcap_recorder_cmd.py"))
            rec = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rec)
            out_root, name, note, err = rec.normalize_target("exp_event_cmdvel", "")   # 實測：模型把資料夾名稱放進 --out-root
            assert (out_root, name, err) == ("", "exp_event_cmdvel", "") and "--name exp_event_cmdvel" in note, note
            assert rec.normalize_target("/data/logs", "exp_a") == ("/data/logs", "exp_a", "", "")
            assert rec.normalize_target("", "") == ("", "", "", "")
            assert rec.normalize_target("logs/exp", "")[3].startswith("[ERROR]"), "含 / 的相對路徑擋下"
            assert rec.normalize_target("exp_x", "exp_y")[3].startswith("[ERROR]"), "已經給了 --name 就不猜"
            assert rec.normalize_target("", "../escape")[3].startswith("[ERROR]"), "--name 不能帶路徑"

        def t_features():
            sys.path.insert(0, os.path.join(tmp, "skills_system", "scripts"))
            import _ros2_data_common as rd
            s = 1_000_000_000
            win = {"start_ns": 0, "end_ns": 30 * s}
            # 實測 /cmd_vel_raw：10 Hz 只在 +10～+18s 發布 → 相鄰間隔都正常，但中途才開始、中途停止
            mid = [10 * s + i * s // 10 for i in range(81)]
            r = rd.rate_features(mid, win)
            assert r["started_late"] and r["stopped_early"] and not r["gaps"], r
            full = [i * s // 10 for i in range(301)]
            r = rd.rate_features(full, win)
            assert not r["started_late"] and not r["stopped_early"], r
            assert "started_late" not in rd.rate_features([12 * s, 20 * s, 25 * s], win), "筆數少（狀態改變才發布）不判斷頭尾"
            few = rd.rate_features([0, 16_183_000_000, 18_790_000_000, 21_620_000_000, 24_360_000_000], {"start_ns": 0, "end_ns": 45 * s})
            assert few["gaps"] == [] and "started_late" not in few, "實測 cmdgap 的 safety_gate_status 整段 5 則：不算訊息中斷"
            assert rd.rate_features([i * s // 10 for i in range(100)] + [20 * s + i * s // 10 for i in range(100)], win)["gaps"], "固定頻率的照樣算中斷"
            # 實測 /system/safety_gate_status：只在狀態改變時發布 → 時間窗開頭沿用之前的最後一則，兩次跳轉都算到（手動指定時間窗時）
            pts = [(13 * s, ()), (21 * s, ("NO_CMD_VEL_RAW",))]
            f = rd.state_features(pts, 30 * s, initial=(int(0.5 * s), ("NO_CMD_VEL_RAW",)), window_start_ns=3 * s)
            assert f["transition_count"] == 2 and f["first"] == "[NO_CMD_VEL_RAW]" and f["samples"] == 2, f
            assert f["carried_age_sec"] == 2.5 and "沿用" in rd.feature_lines("stop_reasons", f, 0)[0]
            assert rd.state_features(pts, 30 * s)["transition_count"] == 1, "沒給 initial 維持原本的算法"
            # 實測 /cmd_vel 的 linear.x：0 → 0.1 → 0，最大跳變只看得到上去那次 → 列每次切換
            f = rd.numeric_features([(0, 0.0), (s, 0.0), (2 * s, 0.1), (3 * s, 0.1), (4 * s, 0.0)])
            assert f["step_count"] == 2 and f["levels"] == 2 and f["steps"][1]["t_ns"] == 4 * s, f
            assert "數值切換 2 次" in "\n".join(rd.feature_lines("linear.x", f, 0))
            noisy = rd.numeric_features([(i * s, 1.0 + i * 0.013) for i in range(20)])
            assert "steps" not in noisy, "連續變化的數值不列切換"
            assert rd.rate_features(mid, win)["single_session"], "中途開始又中途停止、中間沒有中斷＝一段連續的發布"
            warm = [int(1.15 * s) + i * s // 20 for i in range(200)]   # 實測開機的範例：/cmd_vel 在 +1.15s 才有第一筆
            r = rd.rate_features(warm, win, data_start_ns=0)
            assert r.get("warmup_start") and not r["started_late"], "錄製剛開始的延遲不算中途才開始"
            assert rd.rate_features(mid, win, data_start_ns=0)["started_late"], "+10s 才開始：超過錄製剛開始的範圍，照樣算中途才開始"
            assert not rd.rate_features(full, win)["single_session"]
            assert rd.analysis_windows() == [], "analysis_run 不帶時間窗：量測工具量整段"
            w = rd.parse_window("3.37s-31.79s", 0)   # 實測 worker 的寫法；負號不能當分隔（手動用 --window 時）
            assert (w["start_ns"], w["end_ns"]) == (3_370_000_000, 31_790_000_000), w
            assert rd.parse_window("+10,+20", 0)["end_ns"] == 20 * s

        def t_facts():
            # 事實（程式）：類別、發布、變化、到最後的值；時間線的 Topic 事件與 Log、前後 1 秒內的對照（同一個來源只留最近的）、
            # 出現很多次的 Log 只取第一次與最後一次、錄製工具的 Log 不算、同時發生的變化、前後沒有變化的 Log、沒有分析的 Topic
            from agent_core.analysis_job import _build_facts, _top_rows
            b = 1_000_000_000_000_000_000
            T = lambda x: b / 1e9 + x   # noqa: E731
            sig = lambda i, lv, node, msg, ts, **kw: dict({"id": i, "level": lv, "node": node, "message": msg, "count": len(ts),   # noqa: E731
                                                           "first_sec": T(ts[0]), "last_sec": T(ts[-1]), "times_sec": [T(t) for t in ts]}, **kw)
            job = {"index": {"start_ns": b, "end_ns": b + 40 * 10 ** 9, "topics": [
                       {"topic": t, "role": "worker"} for t in ("/gate", "/cmd", "/raw", "/diag", "/broken", "/odom")]
                       + [{"topic": "/empty", "role": "empty"}, {"topic": "/rosout", "role": "log"}]},
                   "plan": {"related": [{"id": "L2", "why": "模式改變"}]},
                   "signals": [sig("L1", "WARN", "lidar", "LiDAR timeout", [10.0],
                                   sources=[{"file": "/ws/src/lidar_pkg/src/lidar.cpp", "function": "check", "line": 42}]),
                               sig("L2", "INFO", "gate", "mode changed", [20.0]),
                               dict(sig("L3", "INFO", "x", "periodic", [1.0, 30.0]), count=10),
                               sig("L4", "WARN", "rosbag2_recorder", "錄製工具自己的", [5.0]),
                               sig("L5", "ERROR", "imu", "IMU lost", [35.0])],
                   "workers": [
                       {"n": 1, "topic": "/gate", "status": "done", "measure": {"rate": {"messages": 3, "first_sec": T(0.5), "last_sec": T(20.0)},
                        "items": [{"name": "mode", "kind": "state", "first": "NORMAL", "last": "LIMITED", "count": 2,
                                   "changes": [{"t": T(10.05), "from": "NORMAL", "to": "STOP"}, {"t": T(20.0), "from": "STOP", "to": "LIMITED"}]}]}},
                       {"n": 2, "topic": "/cmd", "status": "done", "measure": {"rate": {"messages": 300, "avg_hz": 10.0, "first_sec": T(0.2),
                        "last_sec": T(10.1), "stopped_early": True}, "items": [{"name": "linear.x", "kind": "numeric", "first": 0.1, "last": 0.0,
                        "min": 0.0, "max": 0.1, "mean": 0.09, "constant": False, "count": 1, "changes": [{"t": T(10.0), "from": 0.1, "to": 0.0}]}]}},
                       {"n": 3, "topic": "/raw", "status": "done", "measure": {"rate": {"messages": 80, "first_sec": T(2.5), "last_sec": T(10.0),
                        "single_session": True, "started_late": True, "stopped_early": True},
                        "items": [{"name": "x", "kind": "numeric", "first": 0.1, "last": 0.1, "constant": True}]}},
                       {"n": 4, "topic": "/diag", "status": "done", "measure": {"rate": {"messages": 200, "first_sec": T(0.1), "last_sec": T(39.9),
                        "gaps": [{"start_sec": T(25.0), "duration_sec": 3.0}]}, "items": [{"name": "temp", "kind": "numeric", "first": 40, "last": 80,
                        "min": 40, "max": 99, "mean": 60, "constant": False, "spike_count": 1, "spikes": [{"t": T(27.0), "value": 99}]}]}},
                       {"n": 5, "topic": "/broken", "status": "failed", "error": "RuntimeError: x"}]}
            f = _build_facts(job)
            rows = {r["topic"]: r for r in f["topics"]}
            assert rows["/gate"]["tags"] == ["狀態改變"] and "則數少" in rows["/gate"]["publish"], rows["/gate"]
            assert rows["/gate"]["changes"] == ["mode：NORMAL → STOP（+10.05s） → LIMITED（+20.00s）"], rows["/gate"]["changes"]
            assert rows["/gate"]["end"] == ["mode＝LIMITED（開頭 NORMAL）"]
            assert rows["/cmd"]["tags"] == ["開始或停止發布", "數值切換"] and "+10.10s 之後停止發布（到數據結束沒有訊息）" in rows["/cmd"]["publish"]
            assert rows["/cmd"]["end"] == ["linear.x＝0.0（開頭 0.1）"], rows["/cmd"]["end"]
            assert rows["/raw"]["tags"] == ["開始或停止發布"] and "只在 +2.50s～+10.00s 連續發布（一段完整的發布，中間沒有中斷）" in rows["/raw"]["publish"]
            assert rows["/raw"]["still"] == ["x＝0.1"] and rows["/raw"]["end"] == []
            assert rows["/diag"]["tags"] == ["訊息中斷", "數值變動", "尖峰"] and "temp：40 → 80（範圍 40～99，平均 60）" in rows["/diag"]["changes"]
            assert rows["/broken"]["tags"] == ["量測失敗"]
            tl = {(r["time"], r["source"].split(" ")[0], r["event"]): r["near"] for r in f["timeline"]}
            assert tl[("+10.00s", "W2", "linear.x：0.1 → 0.0")] == "L1（同時）", tl
            assert tl[("+10.05s", "W1", "mode：NORMAL → STOP")] == "L1（早 0.05 秒）"
            l1 = next(r for r in f["timeline"] if r["source"].startswith("L1 "))
            assert l1["source"] == "L1 WARN lidar" and l1["event"].endswith("＠lidar.cpp:42 check"), l1
            assert l1["near"] == "W2 /cmd（同時）、W3 /raw（同時）、W1 /gate（晚 0.05 秒）", l1["near"]
            assert tl[("+25.00s", "W4", "訊息中斷 3.00 秒")] == "沒有對應的 Log" and ("+28.00s", "W4", "恢復發布（中斷 3.00 秒之後的第一則）") in tl
            assert ("+27.00s", "W4", "temp 尖峰 99") in tl
            l2 = next(r for r in f["timeline"] if r["source"].startswith("L2 "))
            assert l2["near"] == "W1 /gate（同時）", "相關的 INFO Log 也列"
            l5 = next(r for r in f["timeline"] if r["source"].startswith("L5 "))
            assert l5["near"] == "量到的 Topic 沒有變化"
            assert not any(r["source"].startswith(("L3 ", "L4 ")) for r in f["timeline"]), "沒對到變化的 INFO、錄製工具的 Log 不列"
            assert [x["id"] for x in f["unmatched_logs"]] == ["L5"], f["unmatched_logs"]
            assert f["same_time"] == [{"time": "+10.00s～+10.10s", "events": ["W2 /cmd（linear.x：0.1 → 0.0）", "W3 /raw（停止發布（之後到數據結束沒有訊息））",
                                                                            "W1 /gate（mode：NORMAL → STOP）", "W2 /cmd（停止發布（之後到數據結束沒有訊息））"]}], f["same_time"]
            assert f["not_analyzed"] == {"沒有分析": ["/odom"], "沒有訊息": ["/empty"]}, f["not_analyzed"]
            from agent_core.analysis_job import _near_text
            many = [({"id": f"L{i}", "t": 10 + i * 0.01}, i * 0.01) for i in range(6)]
            assert _near_text(many, "id", lambda x: x["id"], "-") == "L0（同時）、L1（晚 0.01 秒）、L2（晚 0.02 秒）…共 6 個", "太多就列最近的幾個與總數"
            # 出現很多次的 Log：第一次與最後一次（對得到變化才進時間線）
            job["signals"][2] = dict(sig("L3", "INFO", "x", "periodic", [10.0, 30.0]), count=10)
            f = _build_facts(job)
            l3 = [r for r in f["timeline"] if r["source"].startswith("L3 ")]
            assert [r["event"] for r in l3] == ["periodic（第一次，共 10 次）"], l3
            # 時間線太長：依重要性留（WARN 以上的 Log 一定在），省略的數量記下來
            job["workers"][0]["measure"]["items"][0].update(count=80, changes=[{"t": T(0.2 + i * 0.4), "from": "A", "to": "B"} for i in range(80)])
            f = _build_facts(job)
            assert len(f["timeline"]) == 60 and f["timeline_hidden"] > 0 and any(r["source"].startswith("L5 ") for r in f["timeline"]), len(f["timeline"])
            top = _top_rows(f["timeline"], 15)
            assert len(top) == 15 and {r["time"] for r in f["timeline"] if r["rank"] == 0} <= {r["time"] for r in top}, "WARN 以上的 Log 一定留"
            assert [r["t"] for r in top] == sorted(r["t"] for r in top), "留下的照時間排"

        def t_check_followup():
            # 前後沒有量到變化的 Log（L32 WARN +30.00s）＋還有沒量的 Topic：Orchestrator 檢查要不要補量；補量的程式核對（Log 要在清單裡、
            # Topic 要還沒量、最多 2 個）；補量的 worker 量完再整理一次（第 2 輪不再問）；第 1 輪的報告留成 report_r1.md
            follow = {"followups": [{"signal": "L32（+30.00s）", "topic": "cmd_vel", "subtask": "看 +30s 前後速度指令有沒有變化"},
                                    {"signal": "L99", "topic": "/diagnostics_agg", "subtask": "x"},
                                    {"signal": "L32", "topic": "/system/safety_gate_status", "subtask": "y"}]}
            fake, calls = setup(extra_signals=[LIDAR], plans=[GOOD_PLAN], checks=[follow])
            agent.analysis_run(f'--data {DATA} "LiDAR 出錯的前後發生了什麼"')
            d, job = last_job()
            c = job["checks"][0]
            assert c["asked"] and c["unmatched"] == ["L32"] and [a["topic"] for a in c["followups"]] == ["/cmd_vel"], c
            assert any("「L99」不在「前後量到的 Topic 都沒有變化」的清單裡" in x for x in c["issues"]), c["issues"]
            assert any("/system/safety_gate_status：不是還沒量、可以分析的 Topic" in x for x in c["issues"]), c["issues"]
            prompt = fake.seen["check"][0][1]["content"]
            lone = prompt.split("【前後 1 秒內，已經量的 Topic 都沒有變化的 Log】")[1].split("【還沒量的 Topic")[0]
            assert "L32 WARN +30.00s lidar_driver：LiDAR timeout  ＠lidar_node.cpp:88 checkTimeout" in lone, lone
            cand = prompt.split("【還沒量的 Topic（可以補量）】")[1].split("【要決定的】")[0]
            assert "- /cmd_vel｜geometry_msgs/msg/Twist" in cand and "/system/safety_gate_status" not in cand and "/parameter_events" not in cand, cand
            assert "【摘要（Synthesizer）】" in prompt and "LiDAR 出錯的前後發生了什麼" in prompt
            assert [(w["topic"], w.get("round"), w.get("signal")) for w in job["workers"]] == [
                ("/system/safety_gate_status", None, None), ("/cmd_vel", 2, "L32")], job["workers"]
            assert len(job["rounds"]) == 2 and len(fake.seen["check"]) == 1 and len(fake.seen["summary"]) == 2, "第 2 輪不再問；摘要照最後的事實再寫一次"
            assert os.path.exists(os.path.join(d, "report_r1.md")) and os.path.exists(os.path.join(d, "prompts", "orchestrator_check.md"))
            md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
            assert "## 前後 1 秒內量到的 Topic 都沒有變化的 Log" in md and "第 1 輪的檢查：補量 /cmd_vel（為了 L32）" in md, md[-1500:]
            assert "W2 /cmd_vel：看 +30s 前後速度指令有沒有變化（第 2 輪補量，為了 L32）" in md
            # 每則相關的 Log 前後都有量到的變化：不問
            fake, calls = setup(plans=[GOOD_PLAN])
            agent.analysis_run(f'--data {DATA} "安全閘停下來的前後發生了什麼"')
            d, job = last_job()
            assert not fake.seen["check"] and job["checks"][0]["asked"] is False and len(job["rounds"]) == 1, job["checks"]
            assert not os.path.exists(os.path.join(d, "report_r1.md"))
            # --rounds 1：不補量、不檢查
            fake, calls = setup(extra_signals=[LIDAR], plans=[GOOD_PLAN], checks=[follow])
            agent.analysis_run(f'--data {DATA} --rounds 1 "LiDAR 出錯的前後發生了什麼"')
            d, job = last_job()
            assert not fake.seen["check"] and "checks" not in job and len(job["workers"]) == 1

        def t_fact_wording():
            # worker 只拿子任務（L# 換成時間）：不給使用者的問題與 Orchestrator 的理解；局部報告寫了「中斷」（量測沒有中斷）、原因 →
            # 交回 worker 修一次；摘要寫了原因或推測 → 交回 Synthesizer 修一次，還在就在報告與主對話標「程式核對：未修正」
            plan = dict(GOOD_PLAN, assignments=[{"topic": "/system/safety_gate_status", "subtask": "看 L28 (+0.75s) 與 L30 前後 mode 的跳轉"}])
            measure = {"thought": "量 mode", "reply": "", "action": {"command": "scripts/mcap_feature_measure_cmd.py", "args": "--key mode"}}
            bad = {"analyzed_keys": ["mode"], "summary": "mode 在 +15.54s 恢復；之前安全指令中斷導致保護停止"}
            good = dict(bad, summary="mode 在 +15.54s 由 PROTECTIVE_STOP 變成 NORMAL")
            summary_bad = {"summary": "安全閘因為沒有安全指令而保護停止"}
            fake, calls = setup(plans=[plan], worker=[measure], reports=[bad, good], summaries=[summary_bad, SUMMARY_DEFAULT])
            agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            brief = fake.seen["worker"][0][1]["content"]
            assert "【使用者的問題】" not in brief and GOOD_PLAN["understanding"] not in brief and "安全閘為什麼停下來" not in brief, brief[:400]
            assert not re.search(r"L(28|30)", brief) and "看 +0.75s 與 +15.54s 前後 mode 的跳轉" in brief, brief[:800]
            ask = fake.seen["report"][1][-1]["content"]
            assert "你寫了「中斷」" in ask and "你寫了「導致」" in ask, ask
            d, job = last_job()
            w = job["workers"][0]
            assert w["summary"] == good["summary"] and len(w["report_issues"]) == 2 and w["report_issues_left"] == [], w
            assert len(fake.seen["summary"]) == 2 and "寫了「因為」" in fake.seen["summary"][1][1]["content"], "摘要寫了原因：交回修一次"
            assert job["summary_checks"][0]["left"] == [] and job["report"]["unresolved"] == [], job["summary_checks"]
            assert os.path.exists(os.path.join(d, "prompts", "synthesizer_2.md"))
            # 修一次還在：報告與主對話都標示
            fake, calls = setup(plans=[plan], worker=[measure], reports=[good], summaries=[summary_bad, summary_bad])
            text = agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            d, job = last_job()
            md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
            assert job["report"]["unresolved"] and "⚠️ 程式核對：未修正：寫了「因為」" in md, md[:1500]
            assert "程式核對：未修正（摘要裡這幾處跟量到的事實對不上" in text, text[:1200]
            from agent_core.analysis_job import _interrupt_words, _not_fact_words, _summary_issues
            assert not _interrupt_words("沒有任何狀態跳轉、數值尖峰或訊息中斷") and not _interrupt_words("是否中斷看不出來")
            assert _interrupt_words("/cmd_vel_raw 指令源頭中斷") == ["中斷"]
            assert _interrupt_words("是發布節點當掉、通訊中斷，還是收到特定指令停止") == ["中斷"], "事實層不列可能的原因：推測裡的中斷也算"
            assert _not_fact_words("可能是上游節點關閉") == ["可能是"] and _not_fact_words("因為 X", quoted="because 因為") == []
            js = {"signals": [{"message": "LiDAR 數據中斷"}], "workers": [{"status": "done", "topic": "/a", "program_anomalies": []}]}
            assert _summary_issues(js, "+10s 印出 WARN「LiDAR 數據中斷」") == [], "Log 原文照抄不算"
            js["signals"] = [{"message": "LiDAR timeout"}]
            got = _summary_issues(js, "/a 在 +10s 中斷")
            assert got and got[0].startswith("寫了「/a 在 +10s 中斷」，但程式量到的 Topic 都沒有訊息中斷"), got
            from agent_core.analysis_job import _SUMMARY_MAX
            assert _summary_issues(js, "一" * (_SUMMARY_MAX - 5))[0].startswith("摘要太長，被截斷在半句"), "被格式的長度上限截斷：交回縮短"
            assert not _summary_issues(js, "一" * 795), "800 字以內不算太長（上限 800 時三成被截斷，放寬到 1200）"

        def t_limits():
            # 一次最多 3 分鐘（以整秒算，180.056 秒的錄製可以）；拿掉的選項說清楚；舊版設定檔的源碼目錄、推理提示、時間窗不再讀
            long_idx = dict(fixture_json("index_output.txt"), duration_sec=181.2)
            fake, calls = setup(index=long_idx, plans=[GOOD_PLAN])
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            assert out.startswith("[ERROR] 數據") and "超過一次分析的上限 180 秒" in out and "mcap_slicer" in out, out
            assert not fake.seen["plan"] and last_job()[1]["status"] == "failed"
            fake, calls = setup(index=dict(long_idx, duration_sec=180.056), plans=[GOOD_PLAN])
            assert agent.analysis_run(f'--data {DATA} "看一下"').startswith(ANALYSIS_REPORT_HEAD)
            for opt in ("--before 3", "--source ~/ws/src", "--no-source"):
                out = agent.analysis_run(f'--data {DATA} {opt} "看一下"')
                assert out.startswith(f"[ERROR] analysis_run 沒有 {opt.split()[0]} 這個選項了") and "mcap_slicer" in out, out
            with open(agent.analysis_settings_file(), "w", encoding="utf-8") as f:
                json.dump({"source_root": "/x", "program_hints": False, "before": 3, "slice": False, "max_workers": 5}, f)
            cfg = agent.load_analysis_settings()
            assert cfg["max_workers"] == 5 and not {"source_root", "program_hints", "before", "after", "slice"} & set(cfg), cfg
            os.remove(agent.analysis_settings_file())

        for name, fn in [("Orchestrator：不存在的 L#／Topic、Log Topic、重複的 Topic 交回修一次；沒有時間窗、不切片；Log 由程式放進時間線", t_plan_repair),
                         ("Orchestrator：同一個 L# 列兩次只合併、不交回修正", t_plan_duplicate_signal),
                         ("訊息流：一段完整的發布＝開始與停止、真的中斷＝中斷與恢復；worker 不判斷異常；Synthesizer 拿事實、不拿問題", t_rate_facts),
                         ("Key 目錄的類別寫中文；工具略過不存在的 Key 時照輸出算量到的 Key；任務說明寫整段數據", t_category_not_key),
                         ("Orchestrator 給不出計畫：程式依關聯度補指派（不重複、不派 Log）；預設問題", t_auto_assign_and_default_question),
                         ("Worker：reply 裡的動作照做、--topic 固定、時間窗拿掉、只准量測技能、第三次相同量測擋下；事實來自程式量測；事實報告", t_worker_rules),
                         ("Worker 沒量測：推回去一次、系統代選 Key；Synthesizer 壞掉：程式寫一份摘要；報告不再交給摘要 session",
                          t_worker_fallback_and_summary_fallback),
                         ("dispatch：analysis_run 偽技能存檔與軌跡、[ANALYSIS_DATA] 同步、省略 --data、腳本拿得到環境變數", t_dispatch_and_state),
                         ("Web：/analyze 的回合（進度、報告進主對話、主模型依報告回答）、面板 state 與設定、拿掉的指令、分析模式", t_web),
                         ("程式重新啟動：沒做完的 job（進度很久沒更新）標成中斷，剛更新的不動", t_mark_interrupted),
                         ("錄製：資料夾名稱放錯在 --out-root 改當 --name；含 / 的相對路徑、--name 帶路徑擋下", t_recorder_target),
                         ("量測工具：中途開始／停止發布（一段連續的寫成一句）、狀態沿用、數值切換、不帶時間窗＝整段", t_features),
                         ("事實（程式）：類別、發布、變化、到最後的值；時間線與前後 1 秒的對照、重複的 Log、同時發生、沒有變化的 Log、沒有分析的 Topic、"
                          "時間線太長時的取捨", t_facts),
                         ("Orchestrator 檢查：前後沒有量到變化的 Log 才問、補量的程式核對、第 2 輪不再問、report_r1.md；--rounds 1 不檢查",
                          t_check_followup),
                         ("只根據事實：worker 只拿子任務；局部報告與摘要寫原因、推測、跟量測不符的用詞交回修一次，還在就標「程式核對：未修正」", t_fact_wording),
                         ("限制：一次最多 3 分鐘（以整秒算）、拿掉的選項說清楚、舊設定不再讀", t_limits)]:
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
