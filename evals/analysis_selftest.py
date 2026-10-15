"""數據解析（analysis_run：Orchestrator → Workers → Synthesizer）的離線自我測試：假的 ollama.chat 照劇本回答、數據技能回傳用
從真實數據錄下的輸出（evals/analysis_fixtures/，exp_20261014_084506），不需要 Ollama、不需要 docker。

    python3 evals/analysis_selftest.py

測的是 harness 的程式把關（模型能力用真模型量：evals/run_evals.py 的 analysis_* 情境，或直接 /analyze）：
- Orchestrator 的計畫檢查：不存在的 L#／Topic、Log Topic、重複的 Topic → 交回修一次（重複的 L# 只合併）；修不好由程式依關聯度補指派；
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

    def __init__(self, schemas, plans=(), assigns=(), worker=(), reports=(), synth=(), main=()):
        self.s = schemas
        self.q = {"plan": list(plans), "assign": list(assigns), "worker": list(worker), "report": list(reports), "synth": list(synth),
                  "main": list(main)}
        self.seen = {k: [] for k in self.q}

    def _next(self, role, default):
        q = self.q[role]
        return q.pop(0) if q else default

    def __call__(self, model=None, messages=None, format=None, **kw):
        if format is self.s["plan"] or format is self.s.get("plan_src"):
            role, default = "plan", {}
        elif format is self.s.get("assign"):   # Orchestrator 的第二步（有源碼脈絡時：帶源碼分派）
            role, default = "assign", {}
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


DEMO_WS = {   # 源碼索引用的小工作區：Python 的 GATE、C++ 的 MON、沒編譯的舊版 GATE、沒在執行的 teleop（也發布 /cmd_vel）、launch 檔
    "demo/package.xml": "<package><name>demo_pkg</name></package>\n",
    "demo/CMakeLists.txt": ("cmake_minimum_required(VERSION 3.8)\nproject(demo_pkg)\nadd_executable(monitor_node src/monitor_node.cpp)\n"
                            "# add_executable(old_gate_node src/old_gate.cpp)\ninstall(PROGRAMS demo_pkg/gate.py DESTINATION lib/${PROJECT_NAME})\n"),
    "demo/demo_pkg/gate.py": '''import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

PROTECT = frozenset({'SAFETY_TIMEOUT', 'NO_SAFETY_YET'})


class Gate(Node):
    def __init__(self):
        super().__init__('safety_motion_controller')
        self.timeout = self.declare_parameter('raw_timeout_sec', 0.5).value
        self.last_raw_ns = None
        self.reaction = None
        self.sub_raw = self.create_subscription(Twist, '/cmd_vel_raw', self.on_raw, 10)
        self.sub_cmd = self.create_subscription(Twist, '/system/safety_command', self.on_safety, 10)
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.timer = self.create_timer(0.05, self.on_timer)

    def _fresh(self, t, now):
        return t is not None and now - t < self.timeout

    def on_raw(self, msg):
        self.last_raw_ns = 1
        self.latest = msg

    def on_safety(self, msg):
        self.reaction = msg

    def _reasons(self, now):
        reasons = []
        if not self._fresh(self.last_raw_ns, now):
            reasons.append('NO_CMD_VEL_RAW')
        if self.reaction is None:
            reasons.append('NO_SAFETY_YET')
        return reasons

    def on_timer(self):
        reasons = self._reasons(0)
        out = Twist()
        if not reasons:
            out = self.latest
        self.pub.publish(out)
        if PROTECT.intersection(reasons):
            self.get_logger().warn(f'mode=PROTECTIVE_STOP reasons={reasons}')
''',
    "demo/src/old_gate.cpp": ('#include <rclcpp/rclcpp.hpp>\nclass OldGate : public rclcpp::Node {\npublic:\n'
                              '  OldGate() : Node("safety_motion_controller") {\n'
                              '    pub_ = this->create_publisher<geometry_msgs::msg::Twist>("/cmd_vel", 10);\n  }\n};\n'),
    "demo/src/monitor_node.cpp": '''#include <rclcpp/rclcpp.hpp>
// 註解裡的 create_publisher<X>("/fake", 10) 不算
class Monitor : public rclcpp::Node {
public:
  explicit Monitor(const rclcpp::NodeOptions & options = rclcpp::NodeOptions())
  : Node("system_health_monitor", options) {
    sub_ = this->create_subscription<diagnostic_msgs::msg::DiagnosticArray>(
      "/diagnostics_agg", 10, std::bind(&Monitor::diagCallback, this, std::placeholders::_1));
    pub_ = this->create_publisher<Status>("/system/safety_command", 10);
    raw_ = this->create_subscription<Twist>("/cmd_vel_raw", 10, [this](const Twist::SharedPtr m) { onRaw(m); });
  }

private:
  void onRaw(const Twist::SharedPtr) { last_raw_ = 1; }

  void diagCallback(const diagnostic_msgs::msg::DiagnosticArray::SharedPtr msg) {
    if (msg->status.empty()) {
      RCLCPP_WARN(get_logger(), "%s",
                  "event=MON_EMPTY");
      return;
    }
    Status out;
    if (state_ == 0) {
      out.primary_reaction = "INIT";
    }
    pub_->publish(out);
  }

  int state_ = 0;
  int last_raw_ = 0;
};
''',
    "demo/launch/demo.launch.py": ("from launch import LaunchDescription\nfrom launch_ros.actions import Node\n\n\n"
                                   "def generate_launch_description():\n    return LaunchDescription([\n"
                                   "        Node(package='demo_pkg', executable='gate.py', name='safety_motion_controller'),\n"
                                   "        Node(package='demo_pkg', executable='monitor_node', name='system_health_monitor'),\n"
                                   "        Node(package='diagnostic_aggregator', executable='aggregator_node', name='diagnostic_aggregator'),\n"
                                   "    ])\n"),
    "other/package.xml": "<package><name>other_pkg</name></package>\n",
    "other/setup.py": "from setuptools import setup\nsetup(name='other_pkg', entry_points={'console_scripts': ['teleop = other_pkg.teleop:main']})\n",
    "other/other_pkg/teleop.py": ("from rclpy.node import Node\n\n\nclass Teleop(Node):\n    def __init__(self):\n"
                                 "        super().__init__('teleop')\n        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)\n"
                                 "        self.key = self.create_publisher(Twist, '/key_event', 10)\n"),
}


def make_demo_ws(root):
    for rel, text in DEMO_WS.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return root


def fake_exec_factory(agent, calls):
    """數據技能的假回傳：mcap_analyzer／rosout_parser 用錄下的 --json 輸出；mcap_feature_measure 依參數回文字或 JSON。"""
    def fake_exec(script_name, script_path, clean_args, extra_env=None):
        calls.append({"script": script_name, "args": list(clean_args), "env": dict(extra_env or {})})
        if script_name == "mcap_analyzer_cmd.py":
            return fixture("index_output.txt")
        if script_name == "rosout_parser_cmd.py":
            return fixture("rosout_output.txt")
        if script_name == "mcap_slicer_cmd.py":   # 每個 --window 回一片（標籤＝時間窗編號）
            labels = [clean_args[i + 1].split(",")[3] for i in range(len(clean_args) - 1) if clean_args[i] == "--window"]
            return json.dumps({"slices": [{"dir": f"/fake/analysis_slices/sliced_bag_{n}_x", "trigger": {"id": lab},
                                           "messages": 100 * n, "state_messages": 2, "host_dir": f"/host/sliced_bag_{n}_x"}
                                          for n, lab in enumerate(labels, 1)]}) + "\n[TARGET_CONTAINER] ros2_web_container"
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
        from agent_core.schemas import ANALYSIS_ASSIGN_SCHEMA, ANALYSIS_PLAN_SCHEMA_SOURCE
        schemas = {"plan": ANALYSIS_PLAN_SCHEMA, "plan_src": ANALYSIS_PLAN_SCHEMA_SOURCE, "assign": ANALYSIS_ASSIGN_SCHEMA,
                   "worker": ANALYSIS_WORKER_REPLY_SCHEMA, "report": ANALYSIS_WORKER_REPORT_SCHEMA, "synth": ANALYSIS_REPORT_SCHEMA}
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
            # NO_CMD_VEL_RAW 在 stop_reasons 每次跳轉前後都在（[NO_CMD_VEL_RAW, NO_SAFETY_COMMAND_YET] → [MON_INITIALIZING, NO_CMD_VEL_RAW]
            # → [NO_CMD_VEL_RAW]）＝背景條件：根因沒用到它就不列、不限制信心
            assert job["coverage_gaps"][0]["background"] == "/system/safety_gate_status 的 stop_reasons", job["coverage_gaps"]
            assert "背景條件" in fake.seen["synth"][0][1]["content"]
            assert job["report"]["confidence"] == "high" and "程式檢查" not in job["report"]["root_cause"], job["report"]
            assert not any("cmd_vel_raw" in u for u in job["report"]["unknowns"]), job["report"]["unknowns"]
            assert [t["time"] for t in job["report"]["timeline"]] == ["+0.75s", "+15.54s"], "時間線依時間排序"
            # 根因還是寫了沒量測的輸入：照一般的缺口處理（列進尚未確認、信心最多 medium）
            fake, calls = setup(plans=[GOOD_PLAN], synth=[dict(SYNTH, confidence="high", unknowns=[], root_cause="NO_CMD_VEL_RAW 造成停車")])
            out = agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            job = json.load(open(os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"], "job.json"), encoding="utf-8"))
            assert job["report"]["confidence"] == "medium" and "程式檢查" in job["report"]["root_cause"], "缺的輸入：信心最多 medium"
            assert any("cmd_vel_raw" in u for u in job["report"]["unknowns"]) and "尚未確認：" in out
            # 而且它是背景條件（恢復之後仍在）：程式在根因後面附更正，指出跳轉時真正新增／移除的項目
            assert "程式更正：NO_CMD_VEL_RAW" in job["report"]["root_cause"] and "MON_INITIALIZING" in job["report"]["root_cause"], job["report"]
            assert job["corrections"][0]["changed"] == ["MON_INITIALIZING", "NO_SAFETY_COMMAND_YET"], job["corrections"]
            # 排除它的寫法不算拿它當原因：不更正、不限制信心
            fake, calls = setup(plans=[GOOD_PLAN], synth=[dict(SYNTH, confidence="high", unknowns=[],
                                                               root_cause="初始化造成停車；NO_CMD_VEL_RAW 是背景條件，而非原因")])
            agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            job = json.load(open(os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"], "job.json"), encoding="utf-8"))
            assert job["report"]["confidence"] == "high" and "程式更正" not in job["report"]["root_cause"], job["report"]
            assert "Log" not in agent._digest_text({"index": json.loads(fixture("index_output.txt").split("\n[ANALYSIS_DATA]")[0]),
                                                    "signals": []})[:2], "沒有 Log 時說明"
            assert any(c["script"] == "rosout_parser_cmd.py" and "--all-nodes" in c["args"] for c in calls)

        def t_plan_duplicate_signal():
            # 同一個 L# 列兩次（大小寫不同也算）：合併就好，不交回修正（實測 26b 重複列 L17，舊版報成「L17 不存在」退回一次）
            dup = dict(GOOD_PLAN, related_signals=[{"id": "L28", "why": "a"}, {"id": "l28", "why": "b"}, {"id": "L30", "why": "c"}])
            fake, calls = setup(plans=[dup], synth=[SYNTH])
            agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            assert len(fake.seen["plan"]) == 1, "重複的 L# 不交回修正"
            job = json.load(open(os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"], "job.json"), encoding="utf-8"))
            assert [r["id"] for r in job["plan"]["related"]] == ["L28", "L30"] and not job["plan"]["issues"], job["plan"]

        def t_segment_not_fault():
            # 一段完整的發布（中途開始又中途停止、中間沒有中斷）：worker 不因此強制算異常、Synthesizer 拿到「完整的發布」；
            # 真的中斷照樣強制算異常（實測 e4b 看到 10 秒的中斷仍以「狀態沒變」判沒有異常）
            base_js = json.loads(fixture("measure_json.txt").split("\n[ANALYSIS_DATA]")[0])
            rate = base_js["windows"][0]["rate"]
            seg = json.loads(json.dumps(base_js))
            seg["windows"][0]["rate"].update(single_session=True, started_late=True, stopped_early=True, gaps=[])
            gap = json.loads(json.dumps(base_js))
            gap["windows"][0]["rate"]["gaps"] = [{"start_sec": rate["first_sec"] + 2, "duration_sec": 5.0}]
            measure = {"thought": "量 mode", "reply": "", "action": {"command": "scripts/mcap_feature_measure_cmd.py", "args": "--key mode"}}
            calm = {"analyzed_keys": ["mode"], "anomaly_detected": False, "summary": "mode 照預期變化", "evidence": [], "confidence": "medium"}
            for js, forced in ((seg, False), (gap, True)):
                fake, calls = setup(plans=[GOOD_PLAN], worker=[measure], reports=[calm], synth=[SYNTH])
                plain = agent._exec_script

                def exec_with(script_name, script_path, clean_args, extra_env=None, _js=js, _plain=plain):
                    if script_name == "mcap_feature_measure_cmd.py" and "--json" in clean_args:
                        return json.dumps(_js, ensure_ascii=False) + f"\n[ANALYSIS_DATA] {DATA}"
                    return _plain(script_name, script_path, clean_args, extra_env)
                agent._exec_script = exec_with
                agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
                job = json.load(open(os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"], "job.json"), encoding="utf-8"))
                w = job["workers"][0]
                assert w["anomaly_detected"] is forced and ("訊息流中斷本身就是異常" in w["summary"]) is forced, (forced, w)
                assert w["flow_events"], "兩種都列進訊息流（證據、時間線）"
                synth_prompt = fake.seen["synth"][0][1]["content"]
                assert ("是一段完整的發布" in synth_prompt) is (not forced), synth_prompt[-1500:]
                # 範例數據有 WARN（L28 PROTECTIVE_STOP）：不下「正常的操作序列」的判斷
                assert "正常的操作序列（不是故障）" not in synth_prompt

        def t_missing_input_proxy():
            # Log 提到、數據裡沒有的輸入（NO_CMD_VEL_RAW → /cmd_vel_raw 沒錄到）：Orchestrator 規劃時就拿到程式檢查，名稱相近的 /cmd_vel
            # 點名是另一個 Topic；Synthesizer 也一樣（實測 26b 派 /cmd_vel「驗證 NO_CMD_VEL_RAW」、報告寫「/cmd_vel 穩定，排除指令丟失」，25 次 15 次）
            fake, calls = setup(plans=[GOOD_PLAN], synth=[SYNTH])
            agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            plan_prompt = fake.seen["plan"][0][1]["content"]
            assert "【程式檢查：Log 提到、但數據裡沒有的輸入】" in plan_prompt and "NO_CMD_VEL_RAW" in plan_prompt, plan_prompt[-1200:]
            assert "名稱相近的 /cmd_vel 是另一個 Topic" in plan_prompt and "NO_SAFETY_COMMAND_YET" not in plan_prompt.split("【程式檢查")[1], \
                "對得上 /system/safety_command 的不算缺"
            synth_prompt = fake.seen["synth"][0][1]["content"]
            assert "名稱相近的 /cmd_vel 是另一個 Topic" in synth_prompt and "都不能證明也不能排除 NO_CMD_VEL_RAW" in synth_prompt, synth_prompt[-1500:]
            # 派了 /cmd_vel：Synthesizer 看到的那份局部報告旁邊附程式提醒（實測只有缺口說明時，25 次仍有 9 次拿它排除指令中斷）
            with_cmd_vel = dict(GOOD_PLAN, assignments=GOOD_PLAN["assignments"] + [{"topic": "/cmd_vel", "subtask": "看速度", "signals": []}])
            fake, calls = setup(plans=[with_cmd_vel], synth=[SYNTH])
            agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            synth_prompt = fake.seen["synth"][0][1]["content"]
            w_cmd = synth_prompt[synth_prompt.index("### W2 /cmd_vel"):]
            assert "程式提醒：/cmd_vel 不是「cmd_vel_raw」" in w_cmd, w_cmd[:800]
            assert "程式提醒" not in synth_prompt[synth_prompt.index("### W1 "):synth_prompt.index("### W2 ")], "別的 Topic 不附"
            from agent_core.analysis_job import _similar_topics
            job = {"index": {"topics": [{"topic": "/cmd_vel", "message_count": 5}, {"topic": "/odom", "message_count": 5},
                                        {"topic": "/imu/data", "message_count": 0}]}}
            assert _similar_topics(job, "cmd_vel_raw") == ["/cmd_vel"] and _similar_topics(job, "imu_data") == [], "沒有訊息的不算"

        def t_category_not_key():
            # Key 目錄的類別寫中文（英文的 state 每一列都有，實測 26b 送 --key state）；工具略過不存在的 Key、把「類別.Key」改寫成 Key 時，
            # worker 照輸出的「▸ Key（」算真的量到的
            measure = {"thought": "量安全狀態", "reply": "", "action": {"command": "scripts/mcap_feature_measure_cmd.py",
                                                                  "args": "--key state --key state.mode"}}
            fake, calls = setup(plans=[GOOD_PLAN], worker=[measure],
                                reports=[{"analyzed_keys": ["mode"], "anomaly_detected": True, "summary": "mode 跳轉", "evidence": [],
                                          "confidence": "high"}], synth=[SYNTH])
            plain = agent._exec_script

            def exec_new_tool(script_name, script_path, clean_args, extra_env=None, _plain=plain):
                if script_name == "mcap_feature_measure_cmd.py" and "--json" not in clean_args:   # 新版工具：略過 state、state.mode 換成 mode
                    return fixture("measure_text.txt").replace("異常指標（程式判斷）", "沒有量測：state（沒有這個 Key：state 是 Key 的類別（狀態），不是 Key）\n異常指標（程式判斷）")
                return _plain(script_name, script_path, clean_args, extra_env)
            agent._exec_script = exec_new_tool
            agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
            brief = fake.seen["worker"][0][1]["content"]
            assert "- mode｜狀態｜scalar｜string" in brief and "｜state｜" not in brief, brief[-900:]
            job = json.load(open(os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"], "job.json"), encoding="utf-8"))
            w = job["workers"][0]
            assert w["key_selection"] == "worker" and w["analyzed_keys"] == ["mode"], w

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
            assert not any(c["script"] == "mcap_slicer_cmd.py" for c in calls) and not job.get("slices"), "整段數據不切片"

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
            assert job["workers"][0]["key_metrics"] == metrics, "程式量的數字也留在 job 裡（Synthesizer 前的程式檢查要用）"
            assert "→ NORMAL" in out and "rightarrow" not in out
            # 動態時間切片：每個時間窗一片（只含指派的 Topic＋/rosout、帶狀態快照），worker 的時間窗帶著自己的切片
            sl = [c for c in calls if c["script"] == "mcap_slicer_cmd.py"]
            assert len(sl) == 1, [c["args"] for c in sl]
            a = sl[0]["args"]
            wins = [a[i + 1].split(",") for i in range(len(a) - 1) if a[i] == "--window"]
            assert [w[3] for w in wins] == [w["id"] for w in job["windows"]] and "--with-state" in a, a
            assert a[a.index("--topics") + 1:a.index("--with-state")] == ["/rosout", "/system/safety_gate_status"], a
            assert a[a.index("--out") + 1].endswith(f"/analysis_slices/{job['id']}") and "--json" in a, a
            assert job["slices"]["W1"]["dir"] == "/fake/analysis_slices/sliced_bag_1_x" and job["windows"][0]["slice"], job["slices"]
            env_w = json.loads(measure[0]["env"]["ANALYSIS_WINDOWS"])
            assert env_w[0]["slice"] == "/fake/analysis_slices/sliced_bag_1_x", env_w
            assert json.loads(fm["data_slices"])["W1"] == "/host/sliced_bag_1_x", fm.get("data_slices")
            assert "slices:" in report_md and "切片 W1" in report_md, report_md[-600:]
            # 關掉切片：worker 直接讀原本的數據
            agent.analysis_cfg["slice"] = False
            try:
                fake, calls = setup(plans=[GOOD_PLAN], synth=[SYNTH])
                agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
                assert not any(c["script"] == "mcap_slicer_cmd.py" for c in calls), "切片關閉"
                assert all("slice" not in w for c in calls if c["script"] == "mcap_feature_measure_cmd.py"
                           for w in json.loads(c["env"]["ANALYSIS_WINDOWS"]))
            finally:
                agent.analysis_cfg["slice"] = True

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
            gap = job["coverage_gaps"][0]
            assert gap["reason"] == "NO_CMD_VEL_RAW" and (gap["background"] or any("cmd_vel_raw" in u for u in job["report"]["unknowns"])), \
                "缺的輸入：不是背景條件就一定列在尚未確認"
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
            # 實測 /system/safety_gate_status：只在狀態改變時發布 → 時間窗開頭沿用之前的最後一則，兩次跳轉都算到
            pts = [(13 * s, ()), (21 * s, ("NO_CMD_VEL_RAW",))]
            f = rd.state_features(pts, 30 * s, initial=(int(0.5 * s), ("NO_CMD_VEL_RAW",)), window_start_ns=3 * s)
            assert f["transition_count"] == 2 and f["first"] == "[NO_CMD_VEL_RAW]" and f["samples"] == 2, f
            assert f["carried_age_sec"] == 2.5 and "沿用" in rd.feature_lines("stop_reasons", f, 0)[0]
            assert rd.state_features(pts, 30 * s)["transition_count"] == 1, "沒給 initial 維持原本的算法"
            feats, flags = rd.measure_key({"value": pts}, {"category": "state"}, {"start_ns": 3 * s, "end_ns": 30 * s},
                                          "stop_reasons", carry={"value": (int(0.5 * s), ("NO_CMD_VEL_RAW",))})
            assert feats["value"]["transition_count"] == 2 and "狀態跳轉 2 次" in flags[0], (feats, flags)
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
            assert rd.rate_features(warm, win)["started_late"], "不知道數據開頭時照舊判斷"
            assert rd.rate_features(mid, win, data_start_ns=0)["started_late"], "+10s 才開始：超過錄製剛開始的範圍，照樣算中途才開始"
            assert not rd.rate_features(full, win)["single_session"]
            w = rd.parse_window("+1,+2,,W1,/x/sliced_bag_1_x", 0)
            assert w["label"] == "W1" and w["data"] == "/x/sliced_bag_1_x" and rd.parse_window("+1,+2", 0)["data"] == ""
            os.environ["ANALYSIS_WINDOWS"] = json.dumps([{"id": "W1", "start_ns": 5 * s, "end_ns": 20 * s, "anchor_ns": 10 * s,
                                                          "slice": "/x/sliced_bag_1_x"}])
            try:
                assert rd.resolve_window_ids("w1") == f"{5 * s},{20 * s},{10 * s},W1,/x/sliced_bag_1_x"
                assert rd.slice_for_window({"start_ns": 6 * s, "end_ns": 19 * s}) == "/x/sliced_bag_1_x", "落在切片的時間窗裡"
                assert rd.slice_for_window({"start_ns": 4 * s, "end_ns": 19 * s}) == "", "超出切片的範圍：讀原本的數據"
                assert rd.slice_for_window({"start_ns": 5 * s - 50_000_000, "end_ns": 20 * s}) == "/x/sliced_bag_1_x", "四捨五入的誤差"
                aw = rd.matching_analysis_window({"start_ns": 5 * s + 300_000_000, "end_ns": 20 * s - 200_000_000})
                assert aw and aw["id"] == "W1", "自己抄的時間窗跟指派的幾乎一樣＝那個時間窗"
                assert rd.matching_analysis_window({"start_ns": 2 * s, "end_ns": 20 * s}) is None
            finally:
                del os.environ["ANALYSIS_WINDOWS"]
            w = rd.parse_window("3.37s-31.79s", 0)   # 實測 worker 的寫法；負號不能當分隔
            assert (w["start_ns"], w["end_ns"]) == (3_370_000_000, 31_790_000_000), w
            assert rd.parse_window("+10,+20", 0)["end_ns"] == 20 * s

        def t_timeline_fix():
            from agent_core.analysis_job import _fix_signal_times
            base = 1_000_000_000_000_000_000
            sigs = {"L17": {"id": "L17", "count": 1, "first_sec": 1e9 + 18.711, "last_sec": 1e9 + 18.711, "times_sec": [1e9 + 18.711]},
                    "L5": {"id": "L5", "count": 40, "first_sec": 1e9 + 1.0, "last_sec": 1e9 + 30.0, "times_sec": [1e9 + 1.0, 1e9 + 2.0]}}
            tl = [{"time": "+8.71s", "source": "L17", "event": "重啟"},           # 實測：模型寫成時間窗的開頭
                  {"time": "+18.71s", "source": "L17 WARN", "event": "對的不動"},
                  {"time": "+12.00s", "source": "L5", "event": "出現 40 次、只記 2 個時間戳：落在範圍內不動"},
                  {"time": "+3.00s", "source": "L5、L17", "event": "兩個訊號：不判斷"},
                  {"time": "+9.00s", "source": "/cmd_vel", "event": "Topic 不動"}]
            assert _fix_signal_times(tl, sigs, base) == 1, tl
            assert [x["time"] for x in tl] == ["+18.71s", "+18.71s", "+12.00s", "+3.00s", "+9.00s"], tl
            from agent_core.analysis_job import _ensure_flow_events, _flow_block, _flow_events
            s1 = 1_000_000_000
            fe = _flow_events({"W1": {"_rate": {"gaps": [{"start_sec": 250.29, "duration_sec": 10.018}]}}}, 100 * s1)
            assert fe == [("+150.29s", "訊息中斷 10.02 秒")], fe
            assert "只在 +13.47s～+21.28s 連續發布" in _flow_events({"W1": {"_rate": {"published_only": [113.47, 121.28]}}}, 100 * s1)[0][1]
            ws2 = [{"topic": "/system/safety_command", "flow_events": fe},
                   {"topic": "/diagnostics_toplevel_state", "flow_events": [("+150.30s", "訊息中斷 10.02 秒")]}]
            block = _flow_block(ws2)
            assert "同一時間（+150.29s）一起中斷：/system/safety_command、/diagnostics_toplevel_state" in block, block
            tl2 = [{"time": "+150.82s", "source": "L17", "event": "保護停止"}]
            assert _ensure_flow_events(tl2, ws2) == 2 and _ensure_flow_events(tl2, ws2) == 0, tl2   # 補過就不再補
            tl3 = [{"time": "+150.29s", "source": "Topic/Message Flow", "event": "/system/safety_command 和 /diagnostics_toplevel_state 訊息中斷"}]
            assert _ensure_flow_events(tl3, ws2) == 0, "模型寫在同一列（事件裡有 Topic）就不重複補"
            assert _flow_block([{"topic": "/a", "flow_events": fe}]).count("一起中斷") == 0, "只有一個 Topic 不算同時中斷"
            from agent_core.analysis_job import _segment_notes
            km_seg = {"W1": {"_rate": {"published_only": [114.11, 121.21], "started_at": 114.11, "stopped_after": 121.21}}}
            assert _flow_events(km_seg, 100 * s1, segments=False) == [], "一段完整的發布不算中斷"
            info = [{"id": "L15", "level": "INFO", "node": "safety_motion_controller", "times_sec": [114.01],
                     "message": "event=GATE_STATE_CHANGED mode=NORMAL reasons=[]"},
                    {"id": "L17", "level": "INFO", "node": "safety_motion_controller", "times_sec": [121.76],
                     "message": "event=GATE_STATE_CHANGED mode=NORMAL reasons=[NO_CMD_VEL_RAW]"},
                    {"id": "L3", "level": "WARN", "node": "rosbag2_recorder", "times_sec": [100.5], "message": "錄製工具自己的 WARN 不算"}]
            ws_seg = [{"topic": "/cmd_vel_raw", "flow_events": _flow_events(km_seg, 100 * s1), "key_metrics": km_seg}]
            note = "\n".join(_segment_notes(ws_seg, 100 * s1, info))
            assert "+14.11s～+21.21s 是一段完整的發布" in note and "L17（+21.76s，NO_CMD_VEL_RAW）是逾時判斷的結果" in note, note
            assert "正常的操作序列（不是故障）" in note, "Log 沒有 WARN 以上、別的 Topic 沒有中斷：交給 Synthesizer 正常操作的判斷"
            warn = info + [{"id": "L20", "level": "WARN", "node": "x", "times_sec": [125.0], "message": "something"}]
            assert "正常的操作序列" not in "\n".join(_segment_notes(ws_seg, 100 * s1, warn)), "有 WARN：不下正常操作的判斷"
            with_gap = ws_seg + [{"topic": "/diagnostics_agg", "key_metrics": {"W1": {"_rate": {"gaps": [{"start_sec": 130.0,
                                                                                                    "duration_sec": 5.0}]}}}}]
            assert "正常的操作序列" not in "\n".join(_segment_notes(with_gap, 100 * s1, info)), "別的 Topic 中斷：不下正常操作的判斷"
            burst = [{"topic": "/system_health_monitor/transition_event",
                      "key_metrics": {"W1": {"_rate": {"published_only": [121.0, 121.01]}}}}]
            assert "逾時判斷" not in "\n".join(_segment_notes(burst, 100 * s1, info)), "原因代碼對不上這個 Topic：不當成它的逾時"
            assert "一段完整的發布" in _flow_block(ws_seg, 100 * s1, info) and "一段完整的發布" not in _flow_block(ws2), "沒給數據開頭：照舊"
            from agent_core.analysis_job import _relies_on
            assert _relies_on("直接原因是 MON_INITIALIZING 和缺乏原始速度指令（NO_CMD_VEL_RAW）。", "NO_CMD_VEL_RAW")
            assert _relies_on("原因包括 'NO_SAFETY_COMMAND_YET' 和 'NO_CMD_VEL_RAW'", "NO_CMD_VEL_RAW")
            assert not _relies_on("雖然 Log 提到了 NO_CMD_VEL_RAW，但數據顯示此為背景條件，而非導致保護停止的關鍵因素。", "NO_CMD_VEL_RAW")
            assert not _relies_on("初始化造成停車。", "NO_CMD_VEL_RAW") and not _relies_on(None, "X")
            assert _relies_on("NO_CMD_VEL_RAW 不是唯一原因", "NO_CMD_VEL_RAW"), "「不是唯一」＝原因之一"
            assert not _relies_on("雖然 Log 提到了 NO_CMD_VEL_RAW，但根據 W1 的數據，MON_INITIALIZING 是新增的關鍵原因", "NO_CMD_VEL_RAW"), "讓步子句"
            assert not _relies_on("信心是中等，因為 NO_CMD_VEL_RAW 的具體來源未被量測", "NO_CMD_VEL_RAW"), "只說沒被量測"
            assert _relies_on("數據證實了 NO_CMD_VEL_RAW 的情況，因為 /cmd_vel 持續為零", "NO_CMD_VEL_RAW")
            assert _relies_on("雖然有診斷訊息，但直接原因是 NO_CMD_VEL_RAW", "NO_CMD_VEL_RAW"), "代碼在「但」之後＝原因"
            from agent_core.analysis_job import _background_codes
            km = {"W1": {"stop_reasons": {"transitions": 2, "first": "[NO_CMD_VEL_RAW]", "last": "[NO_CMD_VEL_RAW]", "changes": [
                "[NO_CMD_VEL_RAW] → [MON_INITIALIZING, NO_CMD_VEL_RAW] @1.0", "[MON_INITIALIZING, NO_CMD_VEL_RAW] → [NO_CMD_VEL_RAW] @2.0"]}}}
            ws = [{"topic": "/system/safety_gate_status", "key_metrics": km}]
            assert _background_codes(ws, ["NO_CMD_VEL_RAW"]) == {"NO_CMD_VEL_RAW": {"where": "/system/safety_gate_status 的 stop_reasons",
                                                                                   "changed": ["MON_INITIALIZING"]}}
            km["W1"]["stop_reasons"]["changes"][0] = "[] → [MON_INITIALIZING, NO_CMD_VEL_RAW] @1.0"   # 中途才出現：不是背景
            km["W1"]["stop_reasons"]["first"] = "[]"
            assert _background_codes(ws, ["NO_CMD_VEL_RAW"]) == {}

        def t_source_index():
            # 源碼索引：Python（ast）與 C++（遮掉註解、字串之後配對大括號）的發布／訂閱／計時器／參數／publish 位置；CMake 沒編譯的檔案不算；
            # /rosout 的 file（建置路徑、安裝路徑）對回源碼；在執行的節點＝Log 的節點＋transition_event＋同一個 launch 檔
            from agent_core import source_index as si
            ws = make_demo_ws(os.path.join(tmp, "demo_ws"))
            idx = si.load(ws, cache_dir=os.path.join(tmp, "logs", "source_index"))
            gate, mon = "demo/demo_pkg/gate.py", "demo/src/monitor_node.cpp"
            g, m = idx.code(gate), idx.code(mon)
            assert {x["topic"] for x in g["subs"]} == {"/cmd_vel_raw", "/system/safety_command"} and g["timers"][0]["cb"] == "on_timer"
            assert g["params"][0]["name"] == "raw_timeout_sec" and g["params"][0]["var"] == "timeout", g["params"]
            assert [p[2] for p in g["publish"]] == ["Gate.on_timer"] and g["writes"]["Gate.on_raw"] == ["last_raw_ns", "latest"]
            assert [x["cb"] for x in m["subs"]] == ["diagCallback", "onRaw"], "std::bind 與 lambda 的 callback"
            assert [x["topic"] for x in m["pubs"]] == ["/system/safety_command"], "註解裡的 create_publisher 不算"
            assert m["publish"][0][2] == "Monitor::diagCallback" and m["nodes"][0][0] == "system_health_monitor"
            warn_c = next(a for a, b in m["logs"] if b > a)   # 跨兩行的 RCLCPP_WARN：行號是最後一行也算 Log 呼叫
            assert idx.is_log_site(mon, warn_c + 1)
            assert idx.built(mon) and idx.built(gate) and not idx.built("demo/src/old_gate.cpp"), "CMake 註解掉的不算有編譯"
            assert idx.resolve("/workspace/ws/src/demo/src/monitor_node.cpp") == mon
            assert idx.resolve("/workspace/ws/install/demo_pkg/lib/demo_pkg/gate.py") == gate, "安裝後的路徑：套件名稱對得上"
            assert idx.resolve("./src/rosbag2_transport/recorder.cpp") is None
            warn_line = next(i for i, ln in enumerate(DEMO_WS[gate].splitlines(), 1) if "get_logger().warn" in ln)
            sig = [{"id": "L1", "level": "WARN", "node": "safety_motion_controller", "message": "mode=PROTECTIVE_STOP reasons=['NO_CMD_VEL_RAW', 'NO_SAFETY_YET']",
                    "sources": [{"file": "/ws/install/demo_pkg/lib/demo_pkg/gate.py", "function": "on_timer", "line": warn_line}]},
                   {"id": "L2", "level": "INFO", "node": "safety_motion_controller", "message": "x",
                    "sources": [{"file": "/ws/install/demo_pkg/lib/demo_pkg/gate.py", "function": "on_timer", "line": 3}]}]
            topics = {"/cmd_vel": {"count": 10}, "/system/safety_command": {"count": 5}, "/diagnostics_agg": {"count": 5},
                      "/system_health_monitor/transition_event": {"count": 0}}
            js = si.JobSource(idx, topics, sig)
            assert js.impl == {"safety_motion_controller": gate, "system_health_monitor": mon}, js.impl   # teleop 也發布 /cmd_vel，但沒在執行
            assert [n["name"] for n in js.external_nodes()] == ["diagnostic_aggregator"]
            assert js.log_sites["L1"]["ok"] and "版本" in js.log_sites["L2"]["note"], js.log_sites
            line = js.topic_source_line("/cmd_vel")
            assert "safety_motion_controller 發布（on_timer ← 計時器 on_timer（週期 0.05））" in line, line
            assert "依賴的輸入：/cmd_vel_raw（✗數據裡沒有）、/system/safety_command" in line, line
            assert "收到 /diagnostics_agg（diagCallback）" in js.topic_source_line("/system/safety_command")
            assert js.topic_source_line("/system_health_monitor/transition_event") == "", "框架的 Topic 不列"
            assert ("/cmd_vel_raw", ["safety_motion_controller.on_raw", "system_health_monitor.onRaw"]) in js.missing_inputs()
            tl = "\n".join(js.token_lines(["NO_CMD_VEL_RAW", "INIT"]))
            assert "條件 `if not self._fresh(self.last_raw_ns, now)`" in tl and "_fresh：`return t is not None and now - t < self.timeout`" in tl, tl
            assert "last_raw_ns ← on_raw（收到 /cmd_vel_raw（✗數據裡沒有））" in tl, tl
            assert "INIT（monitor_node.cpp:" in tl and "條件 `if (state_ == 0)`" in tl, tl
            js2 = si.JobSource(idx, topics, sig)   # 第二次讀快取
            assert idx.parsed and si.load(ws, cache_dir=os.path.join(tmp, "logs", "source_index")).parsed == 0 and js2.impl == js.impl

        def t_source_context_pipeline():
            # 設定源碼目錄、關閉程式提示：三個角色都拿到源碼脈絡（Topic Metadata 每個 Topic 的發布者與依賴的輸入、Worker 自己的 Topic、
            # Synthesizer 的 Topic 關係與程式碼），計畫的每個指派多 source_context，沒有【程式檢查】的提示；產物有 source_context.md。
            # Orchestrator 分兩步：第一步的源碼只在 Log 與 Topic Metadata（整段【源碼脈絡】會讓它漏挑狀態改變），第二步訊號不變、
            # 帶整段源碼分派（第一步的指派留在 draft_assignments）；第二步給不出可用的指派就用第一步的
            ws = make_demo_ws(os.path.join(tmp, "demo_ws2"))
            plan = json.loads(json.dumps(GOOD_PLAN))
            plan["assignments"][0]["source_context"] = "第一步的線索"
            assign = {"source_reading": "NO_CMD_VEL_RAW 是 gate.py 的 _reasons 裡 /cmd_vel_raw 逾時；/cmd_vel 是輸出",
                      "assignments": [{"topic": "/system/safety_gate_status", "subtask": "看 stop_reasons 的跳轉", "signals": ["L28", "L30"],
                                       "source_context": "gate.py:31 _reasons"}]}

            def run(**kw):
                fake, _ = setup(**kw)
                agent.analysis_cfg.update(source_root=ws, program_hints=False)
                try:
                    agent.analysis_run(f'--data {DATA} "安全閘為什麼停下來"')
                finally:
                    agent.analysis_cfg.update(source_root="", program_hints=True)
                d = os.path.join(agent.analysis_jobs_dir(), agent.analysis_last["id"])
                return fake, d, json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))
            fake, d, job = run(plans=[plan], assigns=[assign], synth=[SYNTH])
            plan_prompt = fake.seen["plan"][0][1]["content"]
            assert "  源碼：safety_motion_controller 發布" in plan_prompt and "source_context 填這個子任務根據的源碼線索" in plan_prompt, plan_prompt[-2500:]
            assert "依賴的輸入：/cmd_vel_raw（✗數據裡沒有）" in plan_prompt and "【程式檢查" not in plan_prompt and "【源碼脈絡" not in plan_prompt
            assert len(fake.seen["assign"]) == 1, "第二步：帶源碼分派"
            assign_prompt = fake.seen["assign"][0][1]["content"]
            assert assign_prompt.startswith(plan_prompt.split("【限制】")[0]), "第二步沿用第一步的問題、Log、Topic Metadata"
            assert "【源碼脈絡（" in assign_prompt and "NO_CMD_VEL_RAW（gate.py:" in assign_prompt and "【程式檢查" not in assign_prompt, assign_prompt[-3000:]
            assert "【第一步已經決定（這一步不改）】" in assign_prompt and "- L28 +" in assign_prompt and "source_reading" in assign_prompt
            brief = fake.seen["worker"][0][1]["content"]
            assert "【源碼脈絡：/system/safety_gate_status" in brief and "Orchestrator 指出的源碼線索：gate.py:31 _reasons" in brief, brief[-1500:]
            synth = fake.seen["synth"][0][1]["content"]
            assert "Topic 之間的關係" in synth and "【程式檢查" not in synth, synth[-3000:]
            assert job["source"]["nodes"]["safety_motion_controller"] == "demo/demo_pkg/gate.py" and not job["program_hints"], job.get("source")
            p = job["plan"]
            assert p["steps"] == 2 and p["assignments"][0]["source_context"] == "gate.py:31 _reasons" and p["source_reading"].startswith("NO_CMD_VEL_RAW")
            assert p["draft_assignments"][0]["source_context"] == "第一步的線索" and [r["id"] for r in p["related"]] == ["L28", "L30"], p
            assert job["synth_raw"]["conclusion"] and os.path.exists(os.path.join(d, "source_context.md"))
            assert all(os.path.exists(os.path.join(d, "prompts", f)) for f in ("orchestrator.md", "orchestrator_assign.md"))
            md = open(os.path.join(d, "workers", "W1_system_safety_gate_status.md"), encoding="utf-8").read()
            assert 'source_context: "gate.py:31 _reasons"' in md and "source_root:" in open(os.path.join(d, "report.md"), encoding="utf-8").read()
            # 第二步給不出可用的指派（交回修一次也沒有）：沿用第一步的
            fake, d, job = run(plans=[plan], synth=[SYNTH])
            assert len(fake.seen["assign"]) == 2 and "steps" not in job["plan"], job["plan"]
            assert job["plan"]["assignments"][0]["source_context"] == "第一步的線索" and any("沿用第一步" in x for x in job["plan"]["issues"])
            # 關掉兩步（AGENT_ANALYSIS_PLAN_TWO_STEP=0）：照一步做
            from agent_core import analysis_job as aj
            aj.ANALYSIS_PLAN_TWO_STEP = False
            try:
                fake, d, job = run(plans=[plan], assigns=[assign], synth=[SYNTH])
            finally:
                aj.ANALYSIS_PLAN_TWO_STEP = True
            assert not fake.seen["assign"] and job["plan"]["assignments"][0]["source_context"] == "第一步的線索"

        for name, fn in [("Orchestrator：不存在的 L#／Topic、Log Topic、重複的 Topic 交回修一次（程式列出具體的問題）", t_plan_repair),
                         ("Orchestrator：同一個 L# 列兩次只合併、不交回修正", t_plan_duplicate_signal),
                         ("訊息流：一段完整的發布不強制算異常、交給 Synthesizer「完整的發布」；中斷照樣強制", t_segment_not_fault),
                         ("Log 提到、數據裡沒有的輸入：Orchestrator 與 Synthesizer 都拿到，名稱相近的 Topic 點名不能代替、它的報告旁附提醒", t_missing_input_proxy),
                         ("Key 目錄的類別寫中文；工具略過不存在的 Key 時照輸出算量到的 Key", t_category_not_key),
                         ("Orchestrator 給不出計畫：程式依關聯度補指派（不重複、不派 Log）；沒有相關訊號＝整段數據；預設問題", t_auto_assign_and_whole_window),
                         ("時間窗：訊號前後各取幾秒、重疊的合併、限制在數據範圍內；Log 的時間不在範圍內退回整段", t_windows),
                         ("Worker：reply 裡的動作照做、--topic 固定、只准量測技能、第三次相同量測擋下；Frontmatter 數字來自程式；動態時間切片", t_worker_rules),
                         ("Worker 沒量測：推回去一次、系統代選 Key；Synthesizer 壞掉：程式拼一份信心低的報告", t_worker_fallback_and_synth_fallback),
                         ("dispatch：analysis_run 偽技能存檔與軌跡、[ANALYSIS_DATA] 同步、省略 --data、腳本拿得到環境變數", t_dispatch_and_state),
                         ("Web：/analyze 的回合（進度、報告進主對話、主模型依報告回答）、面板 state、分析模式指令", t_web),
                         ("程式重新啟動：沒做完的 job（進度很久沒更新）標成中斷，剛更新的不動", t_mark_interrupted),
                         ("錄製：資料夾名稱放錯在 --out-root 改當 --name；含 / 的相對路徑、--name 帶路徑擋下", t_recorder_target),
                         ("量測：中途開始／停止發布（一段連續的寫成一句）、狀態沿用、數值切換、時間窗帶切片", t_features),
                         ("Synthesizer：L# 的時間校正、補上訊息流事件、同時中斷的 Topic；背景條件與程式更正", t_timeline_fix),
                         ("源碼索引：Python／C++ 的發布、訂閱、計時器、參數；沒編譯的不算；Log 的路徑對回源碼；在執行的節點；依賴的輸入與代碼的條件",
                          t_source_index),
                         ("源碼脈絡：Orchestrator 分兩步（先挑訊號、再帶【源碼脈絡】分派；給不出就用第一步的）、Worker 與 Synthesizer 拿到【源碼脈絡】、計畫多 source_context、關閉程式提示時沒有【程式檢查】；產物 source_context.md、prompts/",
                          t_source_context_pipeline)]:
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
