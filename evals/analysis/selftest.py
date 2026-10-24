"""數據分析（analysis_run：全部由程式做——Log 去重、量全部 Topic 的事實、程式寫重點、報告）的離線自我測試：數據技能回傳用從真實數據錄下的
輸出（evals/analysis/fixtures/，exp_5090_overheat：+16.50s 馬達過熱 WARN → 安全閘 LIMITED、/cmd_vel 0.2 → 0.1，+22.61s 解除），
不需要 Ollama、不需要 docker。

    python3 evals/analysis/selftest.py

測的是：
- 量測（_ros2_data_common）：發布方式由內容與時間判斷（狀態改變時才發布的不算中斷、低頻的固定頻率照樣判斷停止）、尖峰（雜訊不算、
  單獨跳出去又回來的才算）、數值切換、反覆切換只留頭尾、陣列只量長度；
- 事實（程式）：T#／E# 的編號每次一樣、同一則訊息的變化合成一個事件、時間線與前後 1 秒的對照、同時發生、前後沒有任何變化的 Log；
- 報告（程式）：每個重要的時間點一則重點（引用那一刻全部的編號，Log 與事件的內容列在下面）、到最後跟開頭不同的值、指定的 Topic、
  不呼叫模型；
- 句子的意思（agent_core/claims.py）與主對話：依報告回答卻寫成因果、或寫錯事實 → 提醒一次改寫；
- 一次最多 3 分鐘、拿掉的選項說清楚、設定檔只存改過的值；dispatch、Web 的 /analyze 回合、面板、程式重新啟動時標中斷；
- CLI 的 /analyze（驅動真的 cli.main() 迴圈）：選項照原樣交給 analysis_run，跟 Web 同一套參數。
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


class FakeChat:
    """假的 ollama.chat：只有主對話會呼叫（數據分析全部由程式做）；照劇本依序回答，記下每次的呼叫。"""

    def __init__(self, main=()):
        self.q = {"main": list(main)}
        self.seen = {"main": []}

    def __call__(self, model=None, messages=None, format=None, **kw):
        self.seen["main"].append(messages)
        q = self.q["main"]
        out = q.pop(0) if q else {"thought": "依報告回答", "reply": "依報告：+16.50s 安全閘進入 LIMITED，+22.61s 回到 NORMAL。", "action": None}
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
        from agent_core.config import ANALYSIS_REPORT_HEAD
        from agent_core.protocol import is_exempt_result
        from agent_core import analysis_job as aj
        from web_app.state import agent, state
        from web_app import flows
        sys.path.insert(0, os.path.join(tmp, "skills_system", "scripts"))
        import _ros2_data_common as rd
        agent.target_container = "ros2_web_container"
        IDX, SCAN, LOGS = fixture_json("index_output.txt"), fixture_json("facts_output.txt"), fixture_json("rosout_output.txt")

        def setup(extra_signals=(), index=None, scan=None, **kw):
            fake = FakeChat(**kw)
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
            assert cmd["tags"] == ["數值切換"] and cmd["publish"].startswith("整段持續發布") and cmd["end"] == ["linear.x＝0.0（中間變過，最後回到開頭的值）"], cmd
            agg = rows["/diagnostics_agg"]
            assert any("（+16.50s 才出現，那時是 1）" in x for x in agg["end"]) and agg["end"][0].endswith("那時是 1）"), \
                "中途才出現的項目：寫出現的時間，不寫成錄製開始時的值"
            assert agg["values"]["status.level[/Actuators/Drivetrain & Base Control/Motors/act_motor_left]"]["late"], agg["values"]
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

        # ------------------------------------------------------------ 報告（程式）
        def t_program_report():
            fake, calls = setup()
            out = agent.analysis_run(f'--data {DATA} --topic /diagnostics_agg --topic nope "馬達過熱的前後發生了什麼"')
            assert not fake.seen["main"], "數據分析不呼叫模型"
            assert out.startswith(ANALYSIS_REPORT_HEAD + "（job ") and "：程式整理，" in out.split("\n")[0], out[:200]
            d, job = last_job()
            assert job["status"] == "done" and job["generated_by"] == "program" and not {"workers", "plan", "model_calls"} & set(job), sorted(job)
            assert not os.path.exists(os.path.join(d, "prompts")) and os.path.exists(os.path.join(d, "topic_facts.json")), os.listdir(d)
            assert any(c["script"] == "mcap_analyzer_cmd.py" and "--facts" in c["args"] for c in calls), "事實由程式量全部的 Topic"
            assert not any(c["script"] in ("mcap_feature_measure_cmd.py", "mcap_slicer_cmd.py") for c in calls)
            hl = job["report"]["highlights"]
            moments = aj._moments(job["facts"])[0]
            timed = [h for h in hl if h["t"] is not None]
            assert len(timed) == 4 and all(set(m["refs"]) <= set(h["refs"]) for m, h in zip(moments, timed)), "每個重要的時間點一則，引用那一刻全部的編號"
            m2 = timed[1]
            assert m2["time"] == "+16.50s～+16.52s" and m2["text"].startswith("3 則 Log（WARN 2、INFO 1）；6 個事件：/diagnostics 開始發布、"), m2
            assert [x.split()[0] for x in m2["facts"]] == ["L18", "L19", "L20", "E4", "E5", "E6", "E7", "E8", "E9"], "Log 在前、事件在後，那一刻全部列出"
            assert "E8 /system/safety_gate_status：mode：NORMAL → LIMITED；latest_reaction：NONE → LIMIT_SPEED" in m2["facts"]
            assert {"L21", "L22"} <= set(timed[2]["refs"]) and timed[2]["text"].startswith("3 則 Log（INFO 3）"), "前後 1 秒內時間線上的 INFO（故障清除）也列進那一刻"
            assert timed[0]["text"] == "1 則 Log（INFO 1）；3 個事件：/system/safety_gate_status、/cmd_vel、/cmd_vel_raw 開始發布", timed[0]
            whole = [h["text"] for h in hl if h["t"] is None]
            assert whole[0] == ("到數據結束時跟開頭不同：/diagnostics：status.level[act_motor_left]＝0（開頭 1）、status.message[act_motor_left]＝OK"
                                "（開頭 Motor overheat）（另 1 項）；中途才出現：/diagnostics_agg 4 項"), "依 Topic 分組：每個有變的 Topic 都看得到"
            # 事件 2 個以內：寫第一個變化
            few = aj._program_highlights({"events": {"E1": {"id": "E1", "topic": "/gate", "t": 1.0, "kind": "change", "text": "mode：A → B；x：1 → 2"}},
                                          "signals": {}, "logs": [], "topics": [], "timeline": []})
            assert few[0]["text"] == "/gate mode：A → B（另 1 項）", few
            md = open(os.path.join(d, "report.md"), encoding="utf-8").read()
            assert md.startswith("---\nartifact: \"fact_report\"") and "generated_by: \"program\"" in md, md[:300]
            assert "## 重點\n**總覽**：7 個 Topic：有事件的 7 個" in md and "- **+16.50s～+16.52s**　3 則 Log（WARN 2、INFO 1）" in md, md[:2000]
            assert "## Workers" not in md and "## 各 Topic 的結果（程式量測整段數據的全部 Key）" in md and "## 資料來源" in md and "沒有呼叫模型" in md
            assert "原因要對照源碼另外分析" in md
            assert "指定的 Topic：\n- T5 /diagnostics_agg｜狀態改變｜" in out and "- /nope：這份數據裡沒有這個 Topic" in out, out[:1500]
            assert "重點（程式整理；引用的事件與 Log 的內容列在每一則下面）：\n- +9.14s～+9.24s　1 則 Log（INFO 1）；3 個事件" in out, out[:2500]
            assert "\n  - L18 WARN system_health_monitor：" in out and "…另" not in out.split("有變化的 Topic")[0], "主對話看得到那一刻全部的 Log 與事件"
            assert "要細看某個 Topic" in out and "不要寫成誰導致、造成、觸發誰" in out and is_exempt_result(out, 5000)
            tl = out.split("時間線（重點沒有引用的")[1].split("\n同時發生")[0] if "時間線（重點沒有引用的" in out else ""
            assert "- E8｜" not in tl and "- E3｜" not in tl, "主對話的時間線只列重點沒有引用的"
            for opt in ("--workers 3", "--rounds 1"):
                res = agent.analysis_run(f'--data {DATA} {opt} "看一下"')
                assert res.startswith(f"[ERROR] analysis_run 沒有 {opt.split()[0]} 這個選項了") and "全部由程式做" in res, res
            # 主對話最多看 _MAIN_HIGHLIGHTS_MAX 則：整段的都留，時間點依重要性（ERROR、WARN 的 Log 多的先留），照時間排
            many = [{"t": float(i), "refs": [f"E{i}"], "facts": ["L1 ERROR x"] if i == 9 else []} for i in range(1, 11)] + [{"t": None, "refs": ["T1"], "facts": []}]
            top = aj._top_highlights(many, 4)
            assert [h["refs"][0] for h in top] == ["E1", "E2", "E9", "T1"], [h["refs"] for h in top]

        # ------------------------------------------------------------ 句子的意思（agent_core/claims.py）
        def t_claims():
            from agent_core.analysis_job import build_facts
            from agent_core.claims import problems
            facts = build_facts({"index": IDX, "scan": SCAN, "signals": LOGS["signals"], "plan": {"related": []}})
            ok = [("mode 從 NORMAL 變成 LIMITED", ["E8"]), ("安全閘的mode從NORMAL變成LIMITED（限速）", ["E8"]),
                  ("linear.x：0.2 → 0.1", ["E9"]), ("/cmd_vel 的 linear.x 由 0.2 降為 0.1", ["E9"]),
                  ("status.message 從 Motor overheat 變成 OK，error_code 為 0x03402901", ["E10"]),
                  ("到數據結束時 mode 是 NORMAL，primary_reaction 為 NONE", ["T1", "T7"]),
                  ("/system/safety_command 的狀態與數值回到初始狀態", ["E13"]), ("/diagnostics_agg 回到初始狀態", ["E11"]),
                  ("安全閘回到 NORMAL", ["E14"]), ("其餘項目沒有變化", ["T7"]), ("mode 是否回到初始狀態", ["E8"]),
                  ("/cmd_vel_raw 開始發布", ["E3"]), ("這個 Topic 從 +9.14s 開始發布", ["T3"]),
                  # 第十二輪 a 實測的誤擋（修正後要放行）：照訊息定義寫常數名稱（OK=0、WARN=1）、整句的「其餘」、沒有變化的群組、
                  # 錄製中途才開始發布的 Topic 沒有初始值、「相關數值」只看那一刻變過的、「或」是列舉
                  ("level 從 OK 變成 WARN，hardware_id 變成 motor_left", ["E6"]), ("level 回到 OK", ["E12"]),
                  ("linear.x 為 0.2，其餘項目皆為 0.0，且沒有變化", ["T2"]), ("其中 status.hardware_id 沒有變化", ["T5"]),
                  ("/diagnostics 中間變過，最後回到開頭的值", ["T4"]), ("mode 為 NORMAL 或 LIMITED", ["E8"]),
                  ("/system/safety_command 的相關數值回到初始值", ["E13"]),
                  # 第十二輪 c 實測：句子裡寫的 T# 是主詞、接著說的子句沿用主詞、有自己的中文主詞的子句不沿用、Topic 的第一則訊息算「變成」
                  ("/cmd_vel 降速；T2 中間變過，最後回到開頭的值", ["E9"]), ("/cmd_vel 的 angular.z 為 0.0，沒有變化", ["T2"]),
                  ("/system/safety_gate_status 的 mode 變成 LIMITED，各項診斷層級回到初始值", ["E8", "E5"]),
                  ("/cmd_vel_raw 開始發布，linear.x 變成 0.2", ["E3"]),
                  # 第十二輪 d 實測：否定的「沒有回到初始」、寫明的例外（「但 X 仍是 V」）、一組 Key 的共同開頭（「winning 項目」）
                  ("/system/safety_command 的狀態沒有回到初始狀態", ["E7"]),
                  ("/system/safety_gate_status 回到初始狀態，但 stop_reasons 仍是 []", ["E14"]),
                  ("/system/safety_gate_status 回到初始狀態。但仍是 []。", ["E14"]),
                  ("/system/safety_gate_status 的 latest 項目回到初始值", ["E14"]),
                  # 子句中間的「但」、只說其中幾項（照抄事實的「回到開頭的值 N 項」）、停止發布之前的值
                  ("/system/safety_gate_status 回到初始值（mode、latest_reaction）但 stop_reasons 仍是 []", ["E14"]),
                  ("/system/safety_gate_status 變過又回到開頭的值 2 項", ["E14"]), ("/cmd_vel_raw 在停止發布前沒有變化", ["T3"]),
                  # 引用的幾次變化合起來（0 → 0.2 → 0.1）、「到最後」只管它後面的說法、並列的主詞（有一個對得上就不擋）
                  ("linear.x 從 0.0 變成 0.1", ["E2", "E9"]), ("linear.x 降為 0.1，此時 linear.x 為 0.1，到最後 linear.x 為 0.0", ["E9"]),
                  ("/diagnostics_toplevel_state 與 /diagnostics 的 level 變為 1", ["E6", "E10"]),
                  # 「回到初始值或變更」（列舉）、句子自己寫出的發布事件不算、「為 X」之後列的才是「沒有變化」的主詞
                  ("/system/safety_command 回到初始值或變更", ["E7"]), ("/cmd_vel_raw 在發布期間沒有變化，最後停止發布", ["T3"]),
                  ("mode 為 NORMAL、linear.y 整段沒有變化", ["T1", "T2"])]
            for text, refs in ok:
                assert problems(text, refs, facts) == [], (text, problems(text, refs, facts))
            bad = [("mode 從 LIMITED 變成 NORMAL", ["E8"], "引用的事件裡 mode 是 NORMAL → LIMITED"),
                   ("linear.x：0.1 → 0.2", ["E9"], "linear.x 是 0.2 → 0.1"),
                   ("primary_reaction 變為 HARD_STOP", ["E7"], "引用的事件裡 primary_reaction 是 NONE → LIMIT_SPEED"),
                   ("到數據結束時 mode 仍是 LIMITED", ["T1"], "到數據結束時 mode＝NORMAL"),
                   ("/system/safety_command 的狀態回到初始狀態", ["E7"], "+16.50s 之後 primary_reaction＝LIMIT_SPEED（開頭 NONE）"),
                   ("/diagnostics_agg 整段沒有變化", ["T5"], "它有 2 個事件（E5、E11）"),
                   ("mode 之後沒有再改變", ["E8"], "mode 在 +22.61s 從 LIMITED 變成 NORMAL"),
                   ("level 從 OK 變成 ERROR", ["E6"], "引用的事件裡 level 是 0 → 1"),
                   ("到數據結束時 mode 回到 LIMITED", ["T1"], "到數據結束時 mode＝NORMAL"),
                   ("/cmd_vel_raw 開始發布；T1 整段沒有變化", ["E3"], "它有 4 個事件"),
                   ("/system/safety_gate_status 回到初始狀態，但 mode 仍是 NORMAL", ["E14"], "stop_reasons＝[]（開頭 [NO_CMD_VEL_RAW]）"),
                   ("/system/safety_gate_status 的 stop 項目回到初始值", ["E14"], "stop_reasons＝[]"),
                   ("/system/safety_command 回到初始狀態，但 active_error_tasks 沒有回到初始", ["E7"], "primary_reaction＝LIMIT_SPEED"),
                   ("/system/safety_gate_status 回到初始值（mode、stop_reasons）但 latest_reaction 仍是 NONE", ["E14"], "stop_reasons＝[]"),
                   ("/cmd_vel 在停止發布前沒有變化", ["T2"], "它有 4 個事件"),
                   ("linear.x 從 0.0 變成 0.3", ["E2", "E9"], "引用的事件裡 linear.x 是 0 → 0.2"),
                   ("此時 linear.x 為 0.3，到最後 linear.x 為 0.0", ["E9"], "引用的那一刻 linear.x 是 0.2／0.1"),
                   ("/diagnostics_toplevel_state 與 /diagnostics 的 level 變為 2", ["E6", "E10"], "status.level[act_motor_left] 是 1 → 0"),
                   ("/cmd_vel_raw 整段沒有變化", ["T3"], "它有 2 個事件（E3、E16）"),
                   ("mode 為 NORMAL、linear.x 整段沒有變化", ["T1", "T2"], "linear.x 在 +9.17s 從 0 變成 0.2")]
            for text, refs, want in bad:
                got = problems(text, refs, facts)
                assert got and want in got[0], (text, got)
            assert problems("mode 從 LIMITED 變成 NORMAL", ["E8"], {"topics": [], "events": {}}) == [], "第十一輪以前的 job（沒有 values）不核對"
            # 第十二輪 a 的 job 沒有 fields：接著說、自己寫了 Key 的子句，Key 用自己的（實測 overheat 把它當成整個 Topic 沒有變化）
            old = dict(facts, topics=[{k: v for k, v in r.items() if k != "fields"} for r in facts["topics"]])
            text = "這個 Topic 中間變過，最後回到開頭的值，且 active_error_tasks 與 active_error_codes 沒有變化"
            assert problems(text, ["T7"], old) == [], problems(text, ["T7"], old)

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
            # 回答寫的變化、值跟這份報告的事實對不上（實測 lidar：「status.level 從 0 變為 2（E6）」）：事實從 job 讀
            fake, calls = setup()
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            agent.begin_turn()
            agent.note_tool_result({"action": {"command": "scripts/analysis_run_cmd.py", "args": ""}}, out)
            ok = ("- **+16.50s**：`mode` 從 `NORMAL` 變成 `LIMITED`（E8），`/cmd_vel` 的 linear.x 由 0.2 降為 0.1（E9）\n"
                  "- 到數據結束時 mode 是 NORMAL（T1）；/system/safety_command 在 +22.60s 回到初始狀態（E13）")
            assert agent.analysis_reply_check({"reply": ok, "action": None}) is None, "寫對的不提醒"
            bad = "- `/cmd_vel` 的 `linear.x` 從 0.1 變成 0.2（E9）\n- 到數據結束時 mode 仍是 LIMITED（T1）"
            nudge = agent.analysis_reply_check({"reply": bad, "action": None})
            assert nudge and "跟報告的事實對不上" in nudge and "引用的事件裡 linear.x 是 0.2 → 0.1" in nudge and "到數據結束時 mode＝NORMAL" in nudge, nudge
            assert "「導致」" not in nudge and any("跟報告的事實對不上" in x for x in agent.pop_notices())
            # 之後的回合（追問、討論那份報告）：只核對寫到報告的那幾行（編號、Topic、+秒）；跟報告無關的回答不核對；/clear 之後不再對照
            # （實測：追問「為什麼一直鎖著」的回答寫了「觸發了緊急停止鎖定機制」，以前只核對執行報告的那一回合）
            agent.begin_turn()
            nudge = agent.analysis_reply_check({"reply": "安全閘是因為在 +16.50s 時觸發了限速，之後一直維持", "action": None})
            assert nudge and "「觸發」" in nudge, nudge
            agent.pop_notices()
            agent.begin_turn()
            assert agent.analysis_reply_check({"reply": "這個 Python 錯誤導致程式無法啟動", "action": None}) is None, "跟報告無關的回答不核對"
            nudge = agent.analysis_reply_check({"reply": "另外，到數據結束時 mode 仍是 LIMITED（T1）", "action": None})
            assert nudge and "到數據結束時 mode＝NORMAL" in nudge, nudge
            agent.pop_notices()
            agent.reset_conversation()
            assert agent.analysis_reply_check({"reply": "+16.50s 觸發限速（E8）", "action": None}) is None, "/clear 之後不再對照"

        def t_dispatch_and_state():
            fake, calls = setup()
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
            fake, calls = setup(main=[causal])
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
            assert set(settings_view()) == {"data_root", "container"}, settings_view()
            ev = []
            handle_analysis_command("/analysis_mode on", ev)
            assert state["analysis_mode"] and "分析模式" in ev[-1]["text"]
            handle_analysis_command("/analysis_mode off", ev)
            for cmd in ("/analysis_workers 9", "/analysis_model all gemma4:26b", "/analysis_source ~/ws/src"):
                handle_analysis_command(cmd, ev)
                assert "已經拿掉" in ev[-1]["text"], (cmd, ev[-1])
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

        def t_cli_analyze():
            # CLI 的 /analyze 跟 Web 同一套參數（analyze_command_args）：驅動真的 cli.main() 迴圈，選項照原樣交給 analysis_run、
            # 沒有 --data 時補目前的數據、沒有選項時整段是問題（2026-10-24 以前 CLI 整段加引號，--data 被當成問題的一部分）
            import builtins
            import contextlib
            import io
            from agent_core import cli
            from agent_core.agent import SkillAgent
            setup()
            seen, lines = [], ["/analyze --data exp_other LiDAR 出錯之後發生了什麼", "/analyze --topic /cmd_vel 什麼時候歸零", "/analyze 馬達過熱前後"]

            def fake_input(prompt=""):
                if not lines:
                    raise KeyboardInterrupt
                return lines.pop(0)
            real_run, real_input = SkillAgent.run_tool, builtins.input

            def fake_run(self, parsed, approved=False):
                action = (parsed or {}).get("action")
                if not action:
                    return None                    # 這一輪沒有動作（跟真的 run_tool 一樣回空的）
                seen.append((action["args"], approved))
                return "[ERROR] 測試：不執行"
            SkillAgent.run_tool = fake_run
            builtins.input = fake_input
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    cli.main()
            finally:
                SkillAgent.run_tool, builtins.input = real_run, real_input
            args = [a for a, _ in seen]
            assert args[0] == "--data exp_other LiDAR 出錯之後發生了什麼", args
            assert args[1].startswith("--data ") and args[1].endswith(" --topic /cmd_vel 什麼時候歸零"), args
            assert args[2].startswith("--data ") and args[2].endswith(" 馬達過熱前後"), "沒有選項：整段是問題"
            assert all(ap for _, ap in seen), "使用者直接指定的：不經過確認關卡"
            assert agent.analyze_command_args("--data exp_other x") == args[0].replace("LiDAR 出錯之後發生了什麼", "x"), "跟 Web 同一個函式"

        def t_limits_and_settings():
            long_idx = dict(IDX, duration_sec=181.2)
            fake, calls = setup(index=long_idx)
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            assert out.startswith("[ERROR] 數據") and "超過一次分析的上限 180 秒" in out and "mcap_slicer" in out, out
            assert last_job()[1]["status"] == "failed"
            assert not any("--facts" in c["args"] for c in calls), "太長就不量"
            fake, calls = setup(index=dict(IDX, duration_sec=180.056))
            assert agent.analysis_run(f'--data {DATA} "看一下"').startswith(ANALYSIS_REPORT_HEAD), "以整秒算：180.056 秒可以"
            # 只有 Log（例如只錄到 bridge 的 /rosout）：照樣出報告——Log 的時間線與重點，沒有 Topic 可以量
            only_log = dict(IDX, topics=[dict(t, role="empty") if t["role"] in ("worker", "text_only") else t for t in IDX["topics"]])
            fake, calls = setup(index=only_log, scan={"version": 3, "topics": {}})
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            d, job = last_job()
            assert out.startswith(ANALYSIS_REPORT_HEAD) and job["status"] == "done", out[:600]
            hl = job["report"]["highlights"]
            assert hl[0]["refs"] == ["L18", "L19"] and hl[0]["text"] == "2 則 Log（WARN 2）", "沒有事件：INFO 不進時間線，只有 WARN 以上的"
            assert any(r["ref"] == "L18" for r in job["report"]["timeline"]), job["report"]["timeline"]
            assert any("只有 Log" in json.loads(x)["text"] for x in open(os.path.join(d, "events.jsonl"), encoding="utf-8"))
            # 有 Topic 卻一個都解不開：環境的問題，回錯誤
            undec = dict(IDX, topics=[dict(t, role="undecodable") if t["role"] in ("worker", "text_only") else t for t in IDX["topics"]])
            fake, calls = setup(index=undec)
            out = agent.analysis_run(f'--data {DATA} "看一下"')
            assert out.startswith("[ERROR] 這份數據的 Topic 都無法解碼") and "ROS2_workspace_env" in out, out
            for opt, why in (("--before 3", "mcap_slicer"), ("--source ~/ws/src", "不用源碼"), ("--no-source", "不用源碼")):
                out = agent.analysis_run(f'--data {DATA} {opt} "看一下"')
                assert out.startswith(f"[ERROR] analysis_run 沒有 {opt.split()[0]} 這個選項了") and why in out, out
            path = agent.analysis_settings_file()
            with open(path, "w", encoding="utf-8") as f:   # 舊版的設定：各角色的模型、worker 上限、源碼目錄、時間窗…讀的時候略過
                json.dump({"source_root": "/x", "program_hints": False, "before": 3, "slice": False, "max_workers": 5, "orchestrator": "m",
                           "data_root": "/data/logs"}, f)
            cfg = agent.load_analysis_settings()
            assert cfg == {"data_root": "/data/logs", "container": ""}, cfg
            # 設定檔只存跟預設值不同的：預設值以後改了，沒改過的設定跟著新的預設
            keep = dict(agent.analysis_cfg)
            agent.analysis_cfg = dict(agent.analysis_defaults(), data_root="/data/logs")
            agent.save_analysis_settings()
            saved = json.load(open(path, encoding="utf-8"))
            assert set(saved) == {"data_root", "saved"} and saved["data_root"] == "/data/logs", saved
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
                         ("報告（程式）：每個時間點一則重點（那一刻全部的 Log 與事件）、到最後跟開頭不同的值、指定的 Topic、不呼叫模型", t_program_report),
                         ("句子的意思：變化、某一刻與到最後的值、沒有變化、回到初始（中途才出現的不算）跟事實核對；中文主詞、部分、疑問不核對", t_claims),
                         ("主對話：依報告回答卻寫成因果、或寫錯事實 → 提醒一次（之後的回合核對寫到報告的那幾行）；否定、條件、Log 原文不算", t_main_reply_check),
                         ("dispatch：analysis_run 偽技能存檔與軌跡、[ANALYSIS_DATA] 同步、省略 --data、腳本拿得到環境變數", t_dispatch_and_state),
                         ("Web：/analyze 的回合（進度、報告進主對話、寫成因果時改寫）、面板 state 與設定、拿掉的指令、分析模式", t_web),
                         ("CLI：/analyze 的選項照原樣交給 analysis_run、沒有 --data 時補目前的數據（跟 Web 共用 analyze_command_args）", t_cli_analyze),
                         ("限制與設定：一次最多 3 分鐘（以整秒算）、只有 Log 的錄製、拿掉的選項、設定檔只存改過的值", t_limits_and_settings),
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
