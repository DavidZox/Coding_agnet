"""數據分析（analysis_run：程式量全部的事實 → Orchestrator → Workers 說明 → Synthesizer 重點 → Orchestrator 檢查）的離線自我測試：
假的 ollama.chat 照劇本回答、數據技能回傳用從真實數據錄下的輸出（evals/analysis/fixtures/，exp_5090_overheat：+16.50s 馬達過熱 WARN →
安全閘 LIMITED、/cmd_vel 0.2 → 0.1，+22.61s 解除），不需要 Ollama、不需要 docker。

    python3 evals/analysis/selftest.py

測的是 harness 的程式把關（模型能力用真模型量：test_data/tools/run_regression.py，或直接 /analyze）：
- 量測（_ros2_data_common）：發布方式由內容與時間判斷（狀態改變時才發布的不算中斷、低頻的固定頻率照樣判斷停止）、尖峰（雜訊不算、
  單獨跳出去又回來的才算）、數值切換、反覆切換只留頭尾、陣列只量長度；
- 事實（程式）：T#／E# 的編號每次一樣、同一則訊息的變化合成一個事件、時間線與前後 1 秒的對照、同時發生、前後沒有任何變化的 Log；
- Orchestrator 的計畫檢查：不存在的 L#／Topic、Log Topic、重複 → 交回修一次；沒有變化的 Topic 不派（不算問題）；可以寫 T#；
  給不出計畫時程式補指派；
- Worker 與 Synthesizer：每一則說明的程式核對（編號、原因與推測、跟引用的事件不符的用詞、寫錯的時間、太長）→ 交回修一次，
  還是不行的那一則不列；時間由程式依編號補上；Synthesizer 沒有可用的重點時由程式列出；
- Orchestrator 檢查：相關的 Log 前後有變化、還沒有說明的 Topic 才問；補派的程式核對；最多補一輪、report_r1.md；
- 主對話：依報告回答卻寫成因果 → 提醒一次改寫；
- 一次最多 3 分鐘、拿掉的選項說清楚、設定檔只存改過的值；dispatch、Web 的 /analyze 回合、面板、程式重新啟動時標中斷。
每一個情境都在臨時目錄複製一份專案，不碰正式的 logs/。"""
import json
import os
import random
import re
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
COPY = ["agent_core", "skills_system", "prompts", "web_app", "vision"]
FIX = os.path.join(HERE, "fixtures")
DATA = "/workspace/experiment_logs/exp_5090_overheat"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def fixture_json(name):
    return json.loads(fixture(name).split("\n[ANALYSIS_DATA]")[0])


SUMMARY_DEFAULT = {"highlights": [{"refs": ["E3"], "text": "/cmd_vel_raw 開始發布"},
                                  {"refs": ["L18", "E8"], "text": "L18 WARN system_health_monitor：MON_FAULT_RAISED；同一時間安全閘 mode 由 NORMAL 變成 LIMITED"},
                                  {"refs": ["E14"], "text": "安全閘回到 NORMAL"},
                                  {"refs": ["E16"], "text": "/cmd_vel_raw 停止發布"}]}   # overheat 的 4 個重要時間點都寫到


class FakeChat:
    """依 format（schema）分辨角色：Orchestrator 規劃／Orchestrator 檢查／Worker／Synthesizer／主對話。各自照劇本依序回答。
    worker 沒有劇本時引用自己那個 Topic 的 T#（從任務說明讀）。"""

    def __init__(self, schemas, plans=(), checks=(), worker=(), summaries=(), main=()):
        self.s = schemas
        self.q = {"plan": list(plans), "check": list(checks), "worker": list(worker), "summary": list(summaries), "main": list(main)}
        self.seen = {k: [] for k in self.q}

    def _next(self, role, default):
        q = self.q[role]
        return q.pop(0) if q else default

    def _role(self, format):
        """格式 → 角色：看格式最上層的欄位（Synthesizer 的則數上限每次不同，格式是複製的，不能用 is 比）。"""
        props = set(((format or {}).get("properties") or {}).keys()) if isinstance(format, dict) else set()
        for role in ("plan", "check", "summary", "worker"):
            if props and props == set(self.s[role]["properties"]):
                return role
        return "main"

    def __call__(self, model=None, messages=None, format=None, **kw):
        role = self._role(format)
        self.formats = getattr(self, "formats", []) + [(role, format)]
        if role == "plan":
            role, default = "plan", {}
        elif role == "check":
            role, default = "check", {"followups": []}
        elif role == "summary":
            role, default = "summary", SUMMARY_DEFAULT
        elif role == "worker":
            m = re.search(r"【你負責的 Topic】(T\d+)", messages[-1]["content"])
            role, default = "worker", {"notes": [{"refs": [m.group(1) if m else "T1"], "text": "這個 Topic 的變化如事件所列"}]}
        else:
            role, default = "main", {"thought": "依報告回答", "reply": "依報告：+16.50s 安全閘進入 LIMITED，+22.61s 回到 NORMAL。", "action": None}
        self.seen[role].append(messages)
        out = self._next(role, default)
        if isinstance(out, Exception):   # 劇本裡放例外：模擬 Ollama 的錯誤（例如輸出重複被中止）
            raise out
        content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return {"message": {"content": content}, "prompt_eval_count": 100, "eval_count": 20}


def fake_exec_factory(agent, calls, extra_signals=(), index=None, scan=None):
    """數據技能的假回傳：mcap_analyzer（--json＝Topic Metadata、--facts --json＝全部 Topic 的事實）、rosout_parser 用錄下的輸出
    （extra_signals：多加的 Log 訊號；index、scan：換掉 Metadata 或事實）。"""
    def fake_exec(script_name, script_path, clean_args, extra_env=None):
        calls.append({"script": script_name, "args": list(clean_args), "env": dict(extra_env or {})})
        if script_name == "mcap_analyzer_cmd.py" and "--facts" in clean_args:
            return (json.dumps(scan, ensure_ascii=False) + f"\n[ANALYSIS_DATA] {DATA}") if scan else fixture("facts_output.txt")
        if script_name == "mcap_analyzer_cmd.py":
            return (json.dumps(index, ensure_ascii=False) + f"\n[ANALYSIS_DATA] {DATA}") if index else fixture("index_output.txt")
        if script_name == "rosout_parser_cmd.py":
            if not extra_signals:
                return fixture("rosout_output.txt")
            logs = fixture_json("rosout_output.txt")
            logs["signals"] = logs["signals"] + list(extra_signals)
            return json.dumps(logs, ensure_ascii=False) + f"\n[ANALYSIS_DATA] {DATA}"
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
        from agent_core.schemas import (ANALYSIS_CHECK_SCHEMA, ANALYSIS_NOTE_MAX, ANALYSIS_PLAN_SCHEMA, ANALYSIS_SUMMARY_SCHEMA,
                                        ANALYSIS_WORKER_SCHEMA)
        from agent_core.config import ANALYSIS_REPORT_HEAD
        from agent_core.protocol import is_exempt_result
        from agent_core import analysis_job as aj
        from web_app.state import agent, state
        from web_app import flows
        sys.path.insert(0, os.path.join(tmp, "skills_system", "scripts"))
        import _ros2_data_common as rd
        schemas = {"plan": ANALYSIS_PLAN_SCHEMA, "check": ANALYSIS_CHECK_SCHEMA, "summary": ANALYSIS_SUMMARY_SCHEMA,
                   "worker": ANALYSIS_WORKER_SCHEMA}
        agent.target_container = "ros2_web_container"
        agent.analysis_cfg.update(parallel=1, max_workers=3, rounds=2)
        GOOD_PLAN = {"understanding": "馬達過熱的前後安全閘與速度指令的變化",
                     "related_signals": [{"id": "L18", "why": "馬達過熱 WARN"}, {"id": "L20", "why": "安全閘進入 LIMITED"}],
                     "assignments": [{"topic": "/system/safety_gate_status", "subtask": "說明 L18 前後 mode 的跳轉"}]}
        IDX, SCAN, LOGS = fixture_json("index_output.txt"), fixture_json("facts_output.txt"), fixture_json("rosout_output.txt")

        def setup(extra_signals=(), index=None, scan=None, **kw):
            fake = FakeChat(schemas, **kw)
            ollama.chat = fake
            calls = []
            agent._exec_script = fake_exec_factory(agent, calls, extra_signals, index, scan)
            return fake, calls

        def last_job():
            d = os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"])
            return d, json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))

        def facts_of(scan=None, signals=None, related=()):
            job = {"index": IDX, "scan": scan or SCAN, "signals": LOGS["signals"] if signals is None else signals,
                   "plan": {"related": [{"id": r, "why": ""} for r in related]}}
            return aj.build_facts(job)

        # ------------------------------------------------------------ 量測（程式）
        def t_measure():
            s = 1_000_000_000
            win = {"start_ns": 0, "end_ns": 30 * s}
            # 實測 cmdgap 的 /system/safety_gate_status：整段 5 則，3 個間隔約 2.7 秒、1 個 16.18 秒——每一則都帶著狀態改變
            times = [0, 16_183_000_000, 18_790_000_000, 21_620_000_000, 24_360_000_000]
            r = rd.rate_features(times, {"start_ns": 0, "end_ns": 45 * s}, change_times=set(times[1:]))
            assert r["pattern"] == "on_change" and "gaps" not in r and "stopped_early" not in r, r
            assert r["times_sec"] == [rd.sec(t) for t in times], "不是固定頻率：每一則的時間就是事實"
            r = rd.rate_features(times, {"start_ns": 0, "end_ns": 45 * s})
            assert r["pattern"] == "periodic" and r["gaps"], "沒有內容可以看時只看時間（3/4 的間隔接近 2.7 秒）：內容是必要的"
            # 低頻的固定頻率 Topic（1 Hz、8 則）：舊版要 10 則以上才判斷，停止發布看不到
            r = rd.rate_features([i * s for i in range(8)], win, change_times=set())
            assert r["pattern"] == "periodic" and r["stopped_early"] and r["period_sec"] == 1.0, r
            assert rd.rate_features([0, 3 * s], win)["pattern"] == "few", "只有一兩則看不出規律"
            rnd = random.Random(7)
            irregular = sorted(rnd.randint(0, 30 * s) for _ in range(40))
            r = rd.rate_features(irregular, win)
            assert r["pattern"] == "irregular" and "gaps" not in r, r
            gap = [i * s // 10 for i in range(100)] + [20 * s + i * s // 10 for i in range(100)]
            r = rd.rate_features(gap, win)
            assert r["pattern"] == "periodic" and r["gap_count"] == 1 and r["gaps"][0]["duration_sec"] == 10.1, r
            mid = [10 * s + i * s // 10 for i in range(81)]   # 實測 /cmd_vel_raw：10 Hz 只在 +10～+18s 發布
            r = rd.rate_features(mid, win)
            assert r["started_late"] and r["stopped_early"] and r["single_session"] and not r["gaps"], r
            full = [i * s // 10 for i in range(301)]
            r = rd.rate_features(full, win)
            assert not r["started_late"] and not r["stopped_early"] and not r["single_session"], r
            warm = [int(1.15 * s) + i * s // 20 for i in range(200)]   # 實測開機：/cmd_vel 在 +1.15s 才有第一筆
            r = rd.rate_features(warm, win, data_start_ns=0)
            assert r.get("warmup_start") and not r["started_late"], "錄製剛開始的延遲不算中途才開始"
            r = rd.rate_features([12 * s, 20 * s, 25 * s], win, data_start_ns=0, change_times={20 * s, 25 * s})
            assert r["late_first"], "不是固定頻率、第一則在錄製剛開始之後：事實裡列成一個事件"
            # 尖峰：雜訊不算（舊版 2.5σ 在 3 分鐘的感測器數據裡每個 Key 都有幾百個），單獨跳出去又回來的才算
            noise = [(i * s // 100, 9.8 + rnd.gauss(0, 0.05)) for i in range(3000)]
            f = rd.numeric_features(noise)
            assert f["spike_count"] == 0 and "steps" not in f, f["spike_count"]
            bump = list(noise)
            bump[1500] = (bump[1500][0], 25.0)
            f = rd.numeric_features(bump)
            assert f["spike_count"] == 1 and f["spikes"][0]["t_ns"] == bump[1500][0] and abs(f["spikes"][0]["baseline"] - 9.8) < 0.2, f["spikes"]
            assert f["max"] == 25.0 and f["max_t_ns"] == bump[1500][0], "最大值與它的時間"
            ramp = [(i * s, float(i)) for i in range(50)]
            assert rd.numeric_features(ramp)["spike_count"] == 0, "一直往上走不是尖峰"
            glitch = [(i * s, 1.5) for i in range(30)]
            glitch[10] = (10 * s, 1.0)
            f = rd.numeric_features(glitch)
            assert f["step_count"] == 2 and f["spike_count"] == 0, "只有幾種值：列切換，不另外算尖峰"
            f = rd.numeric_features([(0, 0.0), (s, 0.0), (2 * s, 0.1), (3 * s, 0.1), (4 * s, 0.0)])
            assert f["step_count"] == 2 and f["levels"] == 2 and f["steps"][1]["t_ns"] == 4 * s, f
            # 反覆切換：特徵是完整的（發布方式要用），輸出只留前 30 次與最後 10 次
            pts = [(i * s // 10, "A" if i % 2 else "B") for i in range(300)]
            f = rd.state_features(pts, 30 * s)
            t = rd.trim_changes(f)
            assert f["transition_count"] == 299 and len(f["transitions"]) == 299 and len(t["transitions"]) == 40, len(t["transitions"])
            assert t["transitions"][-1] == f["transitions"][-1] and t["transition_count"] == 299
            assert rd.publish_pattern([p[0] for p in pts], rd.change_times([f]))[0] == "on_change", "每一則都在改變"
            # 狀態沿用（手動指定時間窗時）
            pts = [(13 * s, ()), (21 * s, ("NO_CMD_VEL_RAW",))]
            f = rd.state_features(pts, 30 * s, initial=(int(0.5 * s), ("NO_CMD_VEL_RAW",)), window_start_ns=3 * s)
            assert f["transition_count"] == 2 and f["first"] == "[NO_CMD_VEL_RAW]" and f["samples"] == 2, f
            # 陣列：位元組陣列（影像、點雲的 data）只量長度，浮點數陣列另外量有限元素的平均
            class Img:
                data = bytes(640 * 480)
            class Scan:
                ranges = [1.0, float("inf"), 3.0]
            assert rd.array_point(Img(), {"key": "data", "type": "sequence<uint8>"}) == (640 * 480, None)
            assert rd.array_point(Scan(), {"key": "ranges", "type": "sequence<float>"}) == (3, 2.0)
            f = rd.array_features([(0, rd.ArrayPoint((3, 2.0))), (s, rd.ArrayPoint((4, 2.5)))])
            assert f["length_min"] == 3 and f["length_max"] == 4 and f["element_mean"]["max"] == 2.5, f
            js = rd.jsonable({"min_t_ns": 2 * s, "t_ns": s})
            assert js["min_t_sec"] == 2.0 and js["t_sec"] == 1.0
            w = rd.parse_window("3.37s-31.79s", 0)
            assert (w["start_ns"], w["end_ns"]) == (3_370_000_000, 31_790_000_000), w

        # ------------------------------------------------------------ 事實（程式）
        def t_facts():
            f = facts_of(related=("L20",))
            rows = {r["topic"]: r for r in f["topics"]}
            gate = rows["/system/safety_gate_status"]
            assert gate["id"] == "T1" and gate["pattern"] == "on_change" and "訊息中斷" not in gate["tags"], gate
            assert gate["publish"].startswith("狀態改變時才發布：5 則（+0.00s、+9.14s、+16.50s、+22.61s、+34.77s）"), gate["publish"]
            assert "mode：NORMAL → LIMITED（+16.50s） → NORMAL（+22.61s）" in gate["changes"], gate["changes"]
            raw = rows["/cmd_vel_raw"]
            assert raw["tags"] == ["開始或停止發布"] and "只在 +9.24s～+34.24s 連續發布（一段完整的發布，中間沒有中斷）" in raw["publish"], raw
            assert [f["events"][e]["kind"] for e in raw["events"]] == ["start", "stop"]
            cmd = rows["/cmd_vel"]
            assert cmd["tags"] == ["數值切換"] and cmd["publish"].startswith("整段持續發布") and cmd["end"] == ["linear.x＝0.0（跟開頭一樣）"], cmd
            assert [r["topic"] for r in f["topics"]][:3] == ["/system/safety_gate_status", "/cmd_vel", "/cmd_vel_raw"], "依第一個事件的時間編號"
            assert [int(e[1:]) for e in sorted(f["events"], key=lambda e: f["events"][e]["t"])] == sorted(int(e[1:]) for e in f["events"])
            e8 = f["events"]["E8"]
            assert e8["topic"] == "/system/safety_gate_status" and e8["text"] == "mode：NORMAL → LIMITED；latest_reaction：NONE → LIMIT_SPEED", e8
            assert f == facts_of(related=("L20",)), "同一份數據的事實每次一樣"
            tl = {r["ref"]: r for r in f["timeline"]}
            assert tl["E9"]["near"].startswith("L18（早 0.01 秒）"), tl["E9"]
            assert tl["L18"]["source"] == "L18 WARN system_health_monitor" and "＠" in tl["L18"]["event"], tl["L18"]
            assert "L20" in tl and "L21" in tl, "相關的與對得到事件的 INFO Log 也列"
            assert [r["t"] for r in f["timeline"]] == sorted(r["t"] for r in f["timeline"])
            assert any(g["time"].startswith("+16.50s") and len(g["events"]) >= 5 for g in f["same_time"]), f["same_time"]
            assert f["unmatched_logs"] == [] and f["unreadable"]["ROS 2 框架的 Topic（不列事件）"] == ["/parameter_events"], f["unreadable"]
            assert f["overview"].startswith("7 個 Topic：有事件的 7 個"), f["overview"]
            assert "MON_FAULT_RAISED" in f["quoted"] and "LIMIT_SPEED" in f["quoted"]
            # WARN 前後沒有任何 Topic 的事件：列在「前後沒有任何 Topic 變化的 Log」
            lone = {"id": "L40", "level": "WARN", "node": "lidar_driver", "count": 1, "message": "LiDAR timeout", "first_sec": IDX["start_sec"] + 40,
                    "last_sec": IDX["start_sec"] + 40, "times_sec": [IDX["start_sec"] + 40],
                    "sources": [{"file": "/ws/src/lidar_pkg/src/lidar_node.cpp", "function": "checkTimeout", "line": 88}]}
            f2 = facts_of(signals=LOGS["signals"] + [lone])
            assert [x["id"] for x in f2["unmatched_logs"]] == ["L40"] and f2["unmatched_logs"][0]["where"] == "  ＠lidar_node.cpp:88 checkTimeout"
            assert next(r for r in f2["timeline"] if r["ref"] == "L40")["near"] == "沒有任何 Topic 的事件"
            # 反覆切換：時間線只列頭尾，次數在各 Topic 的結果
            scan = json.loads(json.dumps(SCAN))
            base = IDX["start_sec"]
            it = next(i for i in scan["topics"]["/system/safety_command"]["items"] if i["name"] == "primary_reaction")
            it.update(count=50, changes=[{"t": base + 1 + i * 0.5, "from": "A" if i % 2 else "B", "to": "B" if i % 2 else "A"} for i in range(40)])
            f3 = facts_of(scan=scan)
            row = next(r for r in f3["topics"] if r["topic"] == "/system/safety_command")
            assert len(row["events"]) == sum(aj._FLAP_KEEP) and any("變化共" in c for c in row["changes"]), row["events"]

        # ------------------------------------------------------------ Orchestrator
        def t_plan_repair():
            bad = {"understanding": "x", "related_signals": [{"id": "L99", "why": "不存在"}, {"id": "L18", "why": "ok"}],
                   "assignments": [{"topic": "/nonexistent", "subtask": "a"}, {"topic": "/rosout", "subtask": "b"},
                                   {"topic": "cmd_vel", "subtask": "c"}, {"topic": "/cmd_vel", "subtask": "d"},
                                   {"topic": "/parameter_events", "subtask": "e"}]}
            fake, calls = setup(plans=[bad, dict(GOOD_PLAN, assignments=GOOD_PLAN["assignments"] + [{"topic": "T3", "subtask": "看指令"}])])
            out = agent.analysis_run(f'--data {DATA} "馬達過熱的前後發生了什麼"')
            assert out.startswith(ANALYSIS_REPORT_HEAD), out[:300]
            assert len(fake.seen["plan"]) == 2, "計畫有問題：交回 Orchestrator 修一次"
            fix_prompt = fake.seen["plan"][1][1]["content"]
            for issue in ("L99 不存在", "/nonexistent」不在事實裡", "/rosout 不能指派", "/cmd_vel 重複指派", "/parameter_events」不在事實裡"):
                assert issue in fix_prompt, (issue, fix_prompt[-800:])
            plan_prompt = fake.seen["plan"][0][1]["content"]
            assert "【全部 Topic 的事實（程式量測整段數據的全部 Key；T# 是 Topic 的編號）】" in plan_prompt and "- T1 /system/safety_gate_status｜" in plan_prompt
            d, job = last_job()
            assert [a["topic"] for a in job["plan"]["assignments"]] == ["/system/safety_gate_status", "/cmd_vel_raw"], "可以寫 T#"
            assert any(c["script"] == "mcap_analyzer_cmd.py" and "--facts" in c["args"] for c in calls), "事實由程式量全部的 Topic"
            assert not any(c["script"] in ("mcap_feature_measure_cmd.py", "mcap_slicer_cmd.py") for c in calls), "worker 不再自己量、不切片"
            assert os.path.exists(os.path.join(d, "topic_facts.json")) and "facts" in job and "scan" not in job
            assert {"L18", "L19", "L20"} <= {r["ref"] for r in job["facts"]["timeline"]}, "WARN 以上與規劃時挑的 Log 進時間線"
            dup = dict(GOOD_PLAN, related_signals=[{"id": "L18", "why": "a"}, {"id": "l18", "why": "b"}, {"id": "L20", "why": "c"}])
            fake, calls = setup(plans=[dup])
            agent.analysis_run(f'--data {DATA} "馬達過熱"')
            d, job = last_job()
            assert len(fake.seen["plan"]) == 1 and [r["id"] for r in job["plan"]["related"]] == ["L18", "L20"] and not job["plan"]["issues"]

        def t_plan_quiet_and_auto():
            # 沒有變化的 Topic 不派（程式已經寫了「沒有變化」，不算問題、不交回）；Orchestrator 給不出計畫 → 程式依事件與相關的 Log 指派
            scan = json.loads(json.dumps(SCAN))
            for it in scan["topics"]["/diagnostics_toplevel_state"]["items"]:
                it.update(count=0, changes=[], last=it.get("first"))
            plan = dict(GOOD_PLAN, assignments=[{"topic": "/diagnostics_toplevel_state", "subtask": "x"}] + GOOD_PLAN["assignments"])
            fake, calls = setup(scan=scan, plans=[plan])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            assert len(fake.seen["plan"]) == 1 and job["plan"]["skipped"] == ["/diagnostics_toplevel_state（沒有變化）"], job["plan"]
            assert [a["topic"] for a in job["plan"]["assignments"]] == ["/system/safety_gate_status"]
            fake, calls = setup(plans=[{}, "不是 JSON"])
            out = agent.analysis_run(f'--data {DATA}')
            d, job = last_job()
            topics = [a["topic"] for a in job["plan"]["assignments"]]
            assert out.startswith(ANALYSIS_REPORT_HEAD) and job["plan"].get("auto_assigned") and len(topics) == 3, job["plan"]
            assert len(set(topics)) == 3 and "/rosout" not in topics and "/parameter_events" not in topics
            assert job["question"] == "這段錄製期間發生了哪些狀態變化？", "沒有問題時用預設問題"

        # ------------------------------------------------------------ Workers
        def t_worker_notes():
            # 每一則說明的程式核對：引用別的 Topic 的事件、寫原因、寫錯時間、寫「中斷」卻沒有引用中斷、太長 → 交回修一次；修好的照列，
            # 時間由程式依編號補上
            bad = {"notes": [{"refs": ["E9"], "text": "/cmd_vel 降速"},
                             {"refs": ["E8"], "text": "馬達過熱導致 mode 變成 LIMITED"},
                             {"refs": ["E8"], "text": "+12.00s mode 變成 LIMITED"},
                             {"refs": ["E14"], "text": "安全閘的訊息中斷後回到 NORMAL"},
                             {"refs": ["T1"], "text": "很長" * (ANALYSIS_NOTE_MAX // 2)},
                             {"refs": ["E8"], "text": "mode 從 NORMAL 變成 LIMITED（定義：限速放行）"}]}
            good = {"notes": [{"refs": ["E8"], "text": "mode 從 NORMAL 變成 LIMITED（定義：限速放行），latest_reaction 變成 LIMIT_SPEED"},
                              {"refs": ["e14", "E 14"], "text": "+22.61s mode 回到 NORMAL"},
                              {"refs": ["T1"], "text": "只在狀態改變時發布，整段 5 則"}]}
            fake, calls = setup(plans=[GOOD_PLAN], worker=[bad, good])
            agent.analysis_run(f'--data {DATA} "馬達過熱的前後發生了什麼"')
            brief = fake.seen["worker"][0][1]["content"]
            assert "【使用者的問題】" not in brief and GOOD_PLAN["understanding"] not in brief and "馬達過熱的前後" not in brief, brief[:400]
            assert not re.search(r"\bL(18|20)\b", brief) and "說明 +16.50s 前後 mode 的跳轉" in brief, "L# 換成時間（worker 看不到 Log）"
            assert "【訊息定義（錄製時存在 MCAP 裡的 .msg，含註解）】" in brief and "E8｜+16.50s｜mode：NORMAL → LIMITED" in brief, brief[-1500:]
            ask = fake.seen["worker"][1][1]["content"]
            for issue in ("第 1 則", "E9 不在可以引用的事實裡", "第 2 則", "寫了「導致」", "寫了 +12.00s", "寫了「中斷」", "太長、被截斷在半句"):
                assert issue in ask, (issue, ask[-1500:])
            assert "第 6 則" not in ask, "沒問題的不列"
            d, job = last_job()
            w = job["workers"][0]
            assert [h["refs"] for h in w["notes"]] == [["E8"], ["E14"], ["T1"]] and w["notes"][0]["time"] == "+16.50s", w["notes"]
            assert w["notes"][1]["time"] == "+22.61s" and w["notes"][2]["time"] == "" and len(w["issues"]) == 5 and "dropped" not in w, w
            md = open(os.path.join(d, "workers", "W1_system_safety_gate_status.md"), encoding="utf-8").read()
            assert md.startswith("---\nartifact: \"worker_notes\"") and "- **+16.50s**　mode 從 NORMAL 變成 LIMITED" in md, md[:1200]
            assert os.path.exists(os.path.join(d, "prompts", "worker_W1_2.md"))
            # 修一次還不行：那一則不列，記在 dropped；一則都沒有時用第一版通過的
            fake, calls = setup(plans=[GOOD_PLAN], worker=[bad, {"notes": [{"refs": ["E8"], "text": "因為過熱所以限速"}]}])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            w = job["workers"][0]
            assert [h["text"] for h in w["notes"]] == ["mode 從 NORMAL 變成 LIMITED（定義：限速放行）"], w["notes"]
            assert len(w["dropped"]) == 5, w["dropped"]
            # 模型的輸出被 Ollama 中止（重複太多）：當成沒有輸出，交回一次；連線這類錯誤照樣丟出去
            import ollama
            abort = ollama.ResponseError("prediction aborted, token repeat limit reached", 500)
            fake, calls = setup(plans=[GOOD_PLAN], worker=[abort, good])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            w = job["workers"][0]
            assert w["status"] == "done" and [h["refs"] for h in w["notes"]] == [["E8"], ["E14"], ["T1"]], w
            assert len(job["model_aborted"]) == 1 and job["model_aborted"][0].startswith("worker_W1："), job.get("model_aborted")
            assert "模型的輸出被 Ollama 中止 1 次" in open(os.path.join(d, "report.md"), encoding="utf-8").read()
            fake, calls = setup(plans=[GOOD_PLAN], worker=[ollama.ResponseError("model 'x' not found", 404)])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            assert job["workers"][0]["status"] == "failed" and "not found" in job["workers"][0]["error"], job["workers"][0]
            # T#（整個 Topic）連同它的事件算引用：寫這個 Topic 的開始發布、那些時間都對
            from agent_core.analysis_job import _check_note
            facts = job["facts"]
            t3 = next(r for r in facts["topics"] if r["topic"] == "/cmd_vel_raw")
            note, issues = _check_note({"refs": [t3["id"]], "text": "這個 Topic 在 +9.24s 開始發布、+34.24s 之後停止發布"}, {t3["id"]}, facts)
            assert not issues, issues
            note, issues = _check_note({"refs": [t3["id"]], "text": "這個 Topic 在 +12.00s 訊息中斷"}, {t3["id"]}, facts)
            assert len(issues) == 2, issues
            from agent_core.analysis_job import _interrupt_words, _not_fact_words
            assert not _interrupt_words("沒有任何狀態跳轉、數值尖峰或訊息中斷") and not _interrupt_words("是否中斷看不出來")
            assert _interrupt_words("/cmd_vel_raw 指令源頭中斷") == ["中斷"]
            assert _not_fact_words("可能是上游節點關閉") == ["可能是"] and _not_fact_words("因為 X", quoted="because 因為") == []

        # ------------------------------------------------------------ Synthesizer
        def t_summary_highlights():
            bad = {"highlights": [{"refs": ["E99"], "text": "不存在的事件"},
                                  {"refs": ["L18", "E8"], "text": "馬達過熱觸發安全閘限速"},
                                  {"refs": ["E3"], "text": "/cmd_vel_raw 停止發布"},
                                  {"refs": ["T2"], "text": "/cmd_vel 開始發布"},
                                  {"refs": ["E14"], "text": "安全閘回到 NORMAL"}]}
            good = {"highlights": [{"refs": ["E14"], "text": "安全閘回到 NORMAL"},
                                   {"refs": ["L18", "E8", "E9"], "text": "L18 WARN system_health_monitor：MON_FAULT_RAISED；同一時間 mode 變成 LIMITED、/cmd_vel 的 linear.x 由 0.2 變成 0.1"},
                                   {"refs": ["E3", "E16"], "text": "/cmd_vel_raw 開始發布，之後停止發布"}]}
            fake, calls = setup(plans=[GOOD_PLAN], summaries=[bad, good])
            out = agent.analysis_run(f'--data {DATA} "馬達過熱的前後發生了什麼"')
            sp = fake.seen["summary"][0][1]["content"]
            assert "【使用者的問題】" not in sp and "馬達過熱的前後" not in sp and "【Orchestrator 挑的相關 Log】L18、L20" in sp, sp[-800:]
            assert "- E8｜+16.50s｜T1 /system/safety_gate_status｜" in sp and "【Workers 的說明" in sp, sp[:2000]
            # 則數上限跟著事實：overheat 是 4 個重要的時間點（+9.1、+16.5、+22.5、+34.2～+34.8 秒）→ 上限照格式的預設 8；格式是複製的
            fmt = [f for r, f in fake.formats if r == "summary"][0]
            assert fmt["properties"]["highlights"]["maxItems"] == 8 and "最多 8 則（重要的時間點 4 個" in sp, sp[-400:]
            from agent_core.analysis_job import _highlight_cap, _key_moments
            from agent_core.schemas import ANALYSIS_SUMMARY_SCHEMA as SS
            many = {"topics": [], "events": {f"E{i}": {"id": f"E{i}", "topic": f"/t{i}", "t": i * 3.0, "kind": "change"} for i in range(1, 15)},
                    "logs": [{"id": "L1", "t": 1.5, "level": "WARN"}, {"id": "L2", "t": 2.0, "level": "INFO"}, {"id": "L3", "t": 6.4, "level": "ERROR"}]}
            assert _key_moments(many) == 15 and _highlight_cap(many) == 17, "WARN 以上的 Log 也算；1 秒內的算同一個；INFO 不算"
            assert _highlight_cap({"topics": [], "events": {f"E{i}": {"id": f"E{i}", "topic": "/x", "t": i * 2.0, "kind": "stop"} for i in range(60)},
                                   "logs": []}) == 24, "防失控的硬上限"
            flapping = dict(many, topics=[{"id": "T1", "topic": "/t1", "flap": 95}, {"id": "T2", "topic": "/t2", "flap": 30}])
            assert _key_moments(flapping) == 14 and _highlight_cap(flapping) == 18, "反覆切換的 Topic 不逐次算時間點、整個算一則（另加一則）"
            assert SS["properties"]["highlights"]["maxItems"] == 8, "共用的格式不被改到"
            ask = fake.seen["summary"][1][1]["content"]
            for issue in ("E99 不在可以引用的事實裡", "寫了「觸發」", "寫了「停止發布」，但引用的事件裡沒有停止發布", "寫了「開始發布」，但引用的事件裡沒有開始發布"):
                assert issue in ask, (issue, ask[-1500:])
            d, job = last_job()
            hl = job["report"]["highlights"]
            assert [h["time"] for h in hl] == ["+9.24s～+34.24s", "+16.50s～+16.52s", "+22.61s"], "時間由程式依編號補上、依時間排"
            assert job["summary_checks"][0]["left"] == [] and not job["report"]["dropped"], job["summary_checks"]
            md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
            assert "## 重點\n**總覽（程式）**：7 個 Topic：有事件的 7 個" in md and "- **+16.50s～+16.52s**　L18 WARN" in md, md[:2500]
            assert "## Workers 的說明" in md and "## 各 Topic 的結果（程式量測整段數據的全部 Key）" in md and "| T1 | /system/safety_gate_status |" in md
            assert "原因要對照源碼另外分析" in md and "## 根因" not in md and GOOD_PLAN["understanding"] not in md
            assert out.startswith(ANALYSIS_REPORT_HEAD) and "重點（時間由程式依編號補上；引用的事件與 Log 的內容由程式列在下面）：\n- +9.24s～+34.24s　/cmd_vel_raw 開始發布" in out, out[:1500]
            # 重點引用的事件與 Log 由程式列在下面（事件在前）；同一刻其他的編號掛在第一則引用到那一刻的重點（also）；主對話最多列 6 行
            assert ("（L18、E8、E9；同一時間：E4、E5、E6、E7、L19）\n  - E4 /diagnostics：開始發布" in out
                    and "\n  - E8 /system/safety_gate_status：mode：NORMAL → LIMITED" in out and "…另 2 個事件與 Log（完整的在報告）" in out), out[:2500]
            assert "（L18、E8、E9；同一時間：E4、E5、E6、E7、L19）\n  - E4 /diagnostics：" in md and "\n  - L19 WARN system_health_monitor：" in md, md[:3000]
            assert [x[:3] for x in hl[1]["facts"]] == ["E4 ", "E5 ", "E6 ", "E7 ", "E8 ", "E9 ", "L18", "L19"] and set(hl[1]["also"]) == {"E4", "E5", "E6", "E7", "L19"}, hl[1]
            assert "\n  - E" not in md.split("## Workers 的說明")[1].split("## 時間線")[0], "worker 的說明只引用自己那個 Topic：不列內容"
            tl = out.split("時間線（重點沒有引用的")[1].split("\n同時發生")[0] if "時間線（重點沒有引用的" in out else ""
            assert "- E8｜" not in tl and "- E3｜" not in tl, "主對話的時間線只列重點沒有引用的"
            ask = fake.seen["summary"][1][1]["content"]
            assert "【上一版有問題的那幾則（其他的通過了，程式會保留，不用重寫）】" in ask and "安全閘回到 NORMAL" not in ask.split("【上一版有問題的那幾則")[1], \
                "只交回有問題的那幾則"
            assert "不要寫成誰導致、造成、觸發誰" in out and is_exempt_result(out, 5000)
            # 實測（第十一輪 camera、lidar）：7 則裡 1 則太長，修正版只回修好的那一則（或整份少抄）——通過的 6 則要留著；
            # 同一段寫了好幾次（模型重複）只留一則
            long_one = {"refs": ["L18", "E8", "E9"], "text": "；".join(["L18 WARN system_health_monitor：MON_FAULT_RAISED"] * 7)}
            seven = {"highlights": [{"refs": ["E3"], "text": "/cmd_vel_raw 開始發布"}, long_one, long_one,
                                    {"refs": ["E14"], "text": "安全閘回到 NORMAL"}, {"refs": ["E14"], "text": "安全閘回到 NORMAL"},
                                    {"refs": ["E16"], "text": "/cmd_vel_raw 停止發布"}, {"refs": ["T5"], "text": "整段沒有變化"}]}
            fixed = {"highlights": [{"refs": ["L18", "E8", "E9"], "text": "同一時間 1 則 WARN Log；mode 變成 LIMITED、/cmd_vel 的 linear.x 由 0.2 變成 0.1"}]}
            fake, calls = setup(plans=[GOOD_PLAN], summaries=[seven, fixed])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            hl = job["report"]["highlights"]
            assert [h["refs"] for h in hl] == [["E3"], ["L18", "E8", "E9"], ["E14"], ["E16"], ["T5"]], [h["refs"] for h in hl]
            assert not job["report"]["dropped"] and {"E8", "E9", "L18"} <= {x.split()[0] for x in hl[1]["facts"]} and "同一時間 1 則 WARN Log" in hl[1]["text"], hl[1]
            ask = fake.seen["summary"][1][1]["content"].split("【上一版有問題的那幾則")[1]
            assert ask.count("MON_FAULT_RAISED；L18") >= 1 and "/cmd_vel_raw 開始發布" not in ask, ask[:600]
            # 實測（第十一輪 cmdvel_holdout）：修正版沒照指示，把通過的那幾則拆開重寫一遍——引用的編號全部已經在通過的裡面＝重複，不收
            first = {"highlights": [{"refs": ["E3", "E16"], "text": "/cmd_vel_raw 開始發布，之後停止發布"},
                                    {"refs": ["L18", "E8", "E9"], "text": "同一時間 1 則 WARN Log；安全閘進入 LIMITED，/cmd_vel 降速"},
                                    {"refs": ["T1"], "text": "到數據結束時 mode 是 NORMAL，之後停止發布"}]}
            again = {"highlights": [{"refs": ["E3"], "text": "/cmd_vel_raw 開始發布"}, {"refs": ["E16"], "text": "/cmd_vel_raw 停止發布"},
                                    {"refs": ["E8"], "text": "安全閘進入 LIMITED"}, {"refs": ["T1"], "text": "到數據結束時 mode 是 NORMAL"},
                                    {"refs": ["E14"], "text": "安全閘回到 NORMAL"}]}
            fake, calls = setup(plans=[GOOD_PLAN], summaries=[first, again])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            assert [h["refs"] for h in job["report"]["highlights"]] == [["E3", "E16"], ["L18", "E8", "E9"], ["E14"], ["T1"]], \
                [h["refs"] for h in job["report"]["highlights"]]
            # 漏寫的時間點（照時間寫、上限用完就停，實測任務失敗的那一刻被漏掉）：程式核對，跟有問題的那幾則一起交回一次補寫
            part = {"highlights": [{"refs": ["L18", "E8"], "text": "同一時間 1 則 WARN Log；安全閘進入 LIMITED"},
                                   {"refs": ["E14"], "text": "安全閘回到 NORMAL"}]}
            add = {"highlights": [{"refs": ["E3"], "text": "/cmd_vel_raw 開始發布"}, {"refs": ["E16", "E17"], "text": "/cmd_vel_raw 停止發布，/cmd_vel 回到 0"}]}
            fake, calls = setup(plans=[GOOD_PLAN], summaries=[part, add])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            rec = job["summary_checks"][0]
            assert rec["moments"] == 4 and [m.split()[0] for m in rec["missing"]] == ["M1", "M4"] and rec["left_missing"] == [], rec
            ask = fake.seen["summary"][1][1]["content"]
            assert "【沒有寫到的重要時間點" in ask and "- M1 +9.14s～+9.24s：" in ask and "上一版有問題的那幾則" not in ask, ask[-900:]
            assert [h["refs"] for h in job["report"]["highlights"]] == [["E3"], ["L18", "E8"], ["E14"], ["E16", "E17"]]
            sp = fake.seen["summary"][0][1]["content"]
            assert "【重要的時間點（程式算的" in sp and "- M2 +16.50s～+16.52s：" in sp, sp[-1500:]
            # 交回之後還是漏掉：程式補一則（標明程式列出，內容照樣列在下面），漏寫幾個記在 summary_checks
            fake, calls = setup(plans=[GOOD_PLAN], summaries=[part, part])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            rec, hl = job["summary_checks"][0], job["report"]["highlights"]
            assert [m.split()[0] for m in rec["filled"]] == ["M1", "M4"] and [m.split()[0] for m in rec["left_missing"]] == ["M1", "M4"], rec
            assert [h.get("program", False) for h in hl] == [True, False, False, True] and "（程式列出）" in hl[0]["text"], hl
            assert hl[0]["facts"][0].startswith("E1 /system/safety_gate_status") and "E16" in hl[3]["refs"], hl[3]
            # 兩次都沒有可用的重點：程式依事實列出（WARN 以上的 Log、有事件的 Topic 的第一個事件）
            fake, calls = setup(plans=[GOOD_PLAN], summaries=["{壞掉的 JSON", {"highlights": [{"refs": ["E8"], "text": "因為過熱"}]}])
            agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            hl = job["report"]["highlights"]
            assert job["report"]["fallback"] and len(hl) == 4 and hl[0]["refs"][0] == "E1" and "L18" in hl[1]["refs"], hl   # 一個時間點一則
            assert hl[1]["facts"][0].startswith("E4 ") and any(x.startswith("L18 WARN") for x in hl[1]["facts"]), hl[1]
            assert "以上由程式依事實列出" in open(os.path.join(d, "report.md"), encoding="utf-8").read()

        # ------------------------------------------------------------ Orchestrator 檢查
        def t_check_followup():
            follow = {"followups": [{"signal": "L18（+16.50s）", "topic": "cmd_vel", "subtask": "說明降速"},
                                    {"signal": "L99", "topic": "/diagnostics_agg", "subtask": "x"},
                                    {"signal": "L18", "topic": "/system/safety_gate_status", "subtask": "y"},
                                    {"signal": "L19", "topic": "T7", "subtask": "z"}]}
            fake, calls = setup(plans=[GOOD_PLAN], checks=[follow])
            agent.analysis_run(f'--data {DATA} "馬達過熱的前後發生了什麼"')
            d, job = last_job()
            c = job["checks"][0]
            assert c["asked"] and [a["topic"] for a in c["followups"]] == ["/cmd_vel", "/system/safety_command"], c
            assert any("「L99」不是它前後的那幾則" in x for x in c["issues"]) and any("/system/safety_gate_status：不在" in x for x in c["issues"]), c["issues"]
            prompt = fake.seen["check"][0][1]["content"]
            cand = prompt.split("還沒有說明的 Topic（程式量的事實）】")[1].split("【要決定的】")[0]
            assert "- T2 /cmd_vel｜前後的 Log：L18 WARN" in cand and "/system/safety_gate_status" not in cand and "/cmd_vel_raw" not in cand, cand
            assert [(w["topic"], w.get("round"), w.get("signal")) for w in job["workers"]] == [
                ("/system/safety_gate_status", None, None), ("/cmd_vel", 2, "L18"), ("/system/safety_command", 2, "L19")], job["workers"]
            assert len(job["rounds"]) == 2 and len(fake.seen["check"]) == 1 and [c["round"] for c in job["summary_checks"]] == [1, 2], \
                "第 2 輪不再問；重點照全部的說明再寫一次"
            assert os.path.exists(os.path.join(d, "report_r1.md")) and os.path.exists(os.path.join(d, "prompts", "orchestrator_check.md"))
            md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
            assert "第 1 輪的檢查：補派 /cmd_vel（為了 L18）、/system/safety_command（為了 L19）" in md, md[-1500:]
            # 相關的 Log 前後有變化的 Topic 都已經有說明：不問
            agent.analysis_cfg["max_workers"] = 8
            try:
                every = dict(GOOD_PLAN, assignments=[{"topic": t, "subtask": "x"} for t in ("/system/safety_gate_status", "/cmd_vel", "/diagnostics",
                                                                                              "/diagnostics_agg", "/diagnostics_toplevel_state", "/system/safety_command")])
                fake, calls = setup(plans=[every])
                agent.analysis_run(f'--data {DATA} "看一下"')
            finally:
                agent.analysis_cfg["max_workers"] = 3
            d, job = last_job()
            assert not fake.seen["check"] and job["checks"][0]["asked"] is False and len(job["rounds"]) == 1, job["checks"]
            # --rounds 1：不檢查
            fake, calls = setup(plans=[GOOD_PLAN], checks=[follow])
            agent.analysis_run(f'--data {DATA} --rounds 1 "看一下"')
            d, job = last_job()
            assert not fake.seen["check"] and "checks" not in job and len(job["workers"]) == 1

        # ------------------------------------------------------------ 主對話
        def t_main_reply_check():
            agent.begin_turn()
            assert agent.analysis_reply_check({"reply": "L18 觸發安全閘限速", "action": None}) is None, "這一回合沒有分析報告：不核對"
            report = ANALYSIS_REPORT_HEAD + "（job x）\nL5 INFO node：event=RESET_TRIGGERED（觸發重置）"
            agent.note_tool_result({"action": {"command": "scripts/analysis_run_cmd.py", "args": ""}}, report)
            for ok in ("時間上的先後不代表誰造成誰，原因要對照源碼另外分析", "如果要知道是不是過熱導致的，要對照源碼", "L5 印出觸發重置（Log 原文）"):
                assert agent.analysis_reply_check({"reply": ok, "action": None}) is None, ok
            nudge = agent.analysis_reply_check({"reply": "依報告，L18 的過熱觸發安全閘限速，導致 /cmd_vel 降速。", "action": None})
            assert nudge and "「導致」" in nudge and "原因要對照源碼另外分析" in nudge, nudge
            assert agent.analysis_reply_check({"reply": "再一次導致", "action": None}) is None, "每回合最多提醒一次"
            agent.pop_notices()

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
            from agent_core.dispatch import DispatchMixin
            probe = os.path.join(tmp, "probe_env.py")
            with open(probe, "w") as f:
                f.write("import os\nprint(os.environ.get('ANALYSIS_DATA'), os.environ.get('ANALYSIS_TOPIC'))\n")
            agent.analysis_data = "/data/x"
            got = DispatchMixin._exec_script(agent, "probe_env.py", probe, [], extra_env={"ANALYSIS_TOPIC": "/t"})
            assert got == "/data/x /t", got

        def t_web():
            state["auto_mode"] = True
            causal = {"thought": "依報告回答", "reply": "L18 的馬達過熱觸發安全閘限速，導致 /cmd_vel 降到 0.1。", "action": None}
            fake, calls = setup(plans=[GOOD_PLAN], main=[causal])
            events = []
            agent.progress_callback = lambda text: events.append({"channel": "progress", "text": text})
            try:
                agent.set_current_task("馬達過熱的前後發生了什麼")
                agent.messages.append({"role": "user", "content": "馬達過熱的前後發生了什麼"})
                awaiting = flows.run_analysis_turn("馬達過熱的前後發生了什麼", events, data=DATA)
            finally:
                agent.progress_callback = None
                state["auto_mode"] = False
            assert awaiting is False
            assert any(e["channel"] == "progress" and "數據分析 job" in e["text"] for e in events), "進度推到右欄"
            assert any(e["channel"] == "tool" and e["text"].startswith(ANALYSIS_REPORT_HEAD) for e in events)
            assert any(m["role"] == "user" and ANALYSIS_REPORT_HEAD in m["content"] for m in agent.messages), "報告進主對話"
            chats = [e for e in events if e["channel"] == "chat"]
            assert any("把先後寫成因果" in e["text"] for e in events if e["channel"] == "system"), ("寫成因果：提醒一次改寫",
                                                                                                [e for e in events if e["channel"] != "progress"][-8:])
            assert "16.50" in chats[-1]["text"] and "導致" not in chats[-1]["text"] and len(fake.seen["main"]) == 2, chats[-1]
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
            seen = []
            real = agent.run_tool
            agent.run_tool = lambda parsed, approved=False: (seen.append(parsed["action"]["args"]), "[ERROR] 測試：不執行")[1]
            try:
                flows.run_analysis_turn("--data exp_other LiDAR 出錯之後發生了什麼", [], data=DATA)
                flows.run_analysis_turn("--topic /cmd_vel 什麼時候歸零", [], data=DATA)
            finally:
                agent.run_tool = real
            assert seen[0] == "--data exp_other LiDAR 出錯之後發生了什麼", seen
            assert seen[1].startswith("--data ") and seen[1].endswith(" --topic /cmd_vel 什麼時候歸零"), seen

        def t_limits_and_settings():
            long_idx = dict(IDX, duration_sec=181.2)
            fake, calls = setup(index=long_idx, plans=[GOOD_PLAN])
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            assert out.startswith("[ERROR] 數據") and "超過一次分析的上限 180 秒" in out and "mcap_slicer" in out, out
            assert not fake.seen["plan"] and last_job()[1]["status"] == "failed"
            assert not any("--facts" in c["args"] for c in calls), "太長就不量"
            fake, calls = setup(index=dict(IDX, duration_sec=180.056), plans=[GOOD_PLAN])
            assert agent.analysis_run(f'--data {DATA} "看一下"').startswith(ANALYSIS_REPORT_HEAD), "以整秒算：180.056 秒可以"
            # 只有 Log（例如只錄到 bridge 的 /rosout）：照樣出報告——Log 的時間線與重點，沒有 Topic 可以量、不派 worker
            only_log = dict(IDX, topics=[dict(t, role="empty") if t["role"] in ("worker", "text_only") else t for t in IDX["topics"]])
            fake, calls = setup(index=only_log, scan={"version": 3, "topics": {}}, plans=[{"understanding": "看 Log", "related_signals": [], "assignments": []}],
                                summaries=[{"highlights": [{"refs": ["L18"], "text": "1 則 WARN Log：馬達過熱"}]}])
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            assert out.startswith(ANALYSIS_REPORT_HEAD) and job["status"] == "done" and not job["workers"], out[:600]
            assert job["report"]["highlights"][0]["refs"] == ["L18"] and any(r["ref"] == "L18" for r in job["report"]["timeline"]), job["report"]["highlights"]
            assert any("只有 Log" in json.loads(x)["text"] for x in open(os.path.join(d, "events.jsonl"), encoding="utf-8"))
            # 有 Topic 卻一個都解不開：環境的問題，回錯誤
            undec = dict(IDX, topics=[dict(t, role="undecodable") if t["role"] in ("worker", "text_only") else t for t in IDX["topics"]])
            fake, calls = setup(index=undec, plans=[GOOD_PLAN])
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            assert out.startswith("[ERROR] 這份數據的 Topic 都無法解碼") and "ROS2_workspace_env" in out, out
            for opt in ("--before 3", "--source ~/ws/src", "--no-source"):
                out = agent.analysis_run(f'--data {DATA} {opt} "看一下"')
                assert out.startswith(f"[ERROR] analysis_run 沒有 {opt.split()[0]} 這個選項了") and "mcap_slicer" in out, out
            path = agent.analysis_settings_file()
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"source_root": "/x", "program_hints": False, "before": 3, "slice": False, "max_workers": 5}, f)
            cfg = agent.load_analysis_settings()
            assert cfg["max_workers"] == 5 and not {"source_root", "program_hints", "before", "after", "slice"} & set(cfg), cfg
            # 設定檔只存跟預設值不同的：預設值以後改了，沒改過的設定跟著新的預設
            keep = dict(agent.analysis_cfg)
            agent.analysis_cfg = dict(agent.analysis_defaults(), max_workers=5)
            agent.save_analysis_settings()
            saved = json.load(open(path, encoding="utf-8"))
            assert set(saved) == {"max_workers", "saved"} and saved["max_workers"] == 5, saved
            agent.analysis_cfg = dict(agent.analysis_defaults())
            agent.save_analysis_settings()
            assert set(json.load(open(path, encoding="utf-8"))) == {"saved"}
            agent.analysis_cfg = keep
            os.remove(path)

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
            assert job["status"] == "failed" and "Workers 說明" in job["error"], job
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

        for name, fn in [("量測：發布方式由內容與時間判斷、低頻的照樣判斷停止、尖峰不含雜訊、反覆切換只留頭尾、陣列只量長度", t_measure),
                         ("事實（程式）：T#／E# 每次一樣、同一則訊息的變化合成一個事件、時間線與對照、前後沒有任何變化的 Log、反覆切換", t_facts),
                         ("Orchestrator：不存在的 L#／Topic、Log Topic、框架的 Topic、重複交回修一次；可以寫 T#；同一個 L# 只合併", t_plan_repair),
                         ("Orchestrator：沒有變化的 Topic 不派、不交回；給不出計畫時程式補指派；預設問題", t_plan_quiet_and_auto),
                         ("Worker：每一則說明的核對（編號、原因、時間、中斷、太長）交回修一次；修不好的不列；時間由程式補", t_worker_notes),
                         ("Synthesizer：每一則重點的核對交回修一次；時間依編號補上、依時間排；沒有可用的重點時程式列出", t_summary_highlights),
                         ("Orchestrator 檢查：相關的 Log 前後有變化、還沒有說明的才問；補派的核對；第 2 輪不再問；--rounds 1 不檢查", t_check_followup),
                         ("主對話：依報告回答卻寫成因果 → 提醒一次；否定、條件、Log 原文不算", t_main_reply_check),
                         ("dispatch：analysis_run 偽技能存檔與軌跡、[ANALYSIS_DATA] 同步、省略 --data、腳本拿得到環境變數", t_dispatch_and_state),
                         ("Web：/analyze 的回合（進度、報告進主對話、寫成因果時改寫）、面板 state 與設定、拿掉的指令、分析模式", t_web),
                         ("限制與設定：一次最多 3 分鐘（以整秒算）、拿掉的選項、設定檔只存改過的值", t_limits_and_settings),
                         ("程式重新啟動：沒做完的 job（進度很久沒更新）標成中斷，剛更新的不動", t_mark_interrupted),
                         ("錄製：資料夾名稱放錯在 --out-root 改當 --name；含 / 的相對路徑、--name 帶路徑擋下", t_recorder_target)]:
            if os.environ.get("SELFTEST_ONLY", "") in name:   # 只跑名稱含這個字的（除錯用）
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
