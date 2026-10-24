"""數據技能（ROS2_topic_echo、mcap_*、rosout_parser 與共用層 _ros2_data_common）的測試：不需要容器的部分直接測函式；
需要容器的情境在測試容器 cah_analysis_test 執行中時才跑（裡面要有 ROS 2；沒有就略過）。"""
import json
import os
import subprocess
import sys

from selftest import SCRIPTS, Skip, assert_error, run_script

sys.path.insert(0, SCRIPTS)
import _ros2_data_common as rd  # noqa: E402

LIVE = os.environ.get("AGENT_LIVE_CONTAINER", "cah_analysis_test")


class _String:
    """假的 std_msgs/String（describe_keys 只需要 get_fields_and_field_types 與屬性）。"""
    @classmethod
    def get_fields_and_field_types(cls):
        return {"data": "string"}

    def __init__(self, data):
        self.data = data


def t_echo_args():
    """ROS2_topic_echo 的參數：位置參數、--topic／--container、秒數帶單位、--where 要搭配 --duration、不認識的選項"""
    import ROS2_topic_echo_cmd as echo
    os.environ.setdefault("TARGET_CONTAINER", "x")
    o, err = echo.parse_cli(["--topic", "/fleet", "--duration", "5s"])
    assert err is None and o["topic"] == "/fleet" and o["duration"] == 5, (o, err)
    o, err = echo.parse_cli(["odom", "--duration", "10秒", "--where", "v>1"])
    assert err is None and o["topic"] == "/odom" and o["wheres"] == ["v>1"], (o, err)
    o, err = echo.parse_cli(["/odom", "30"])
    assert err is None and o["timeout"] == 30 and o["duration"] is None, (o, err)
    o, err = echo.parse_cli(["/robot/status", "20s"])
    assert err is None and o["topic"] == "/robot/status" and o["timeout"] == 20, "topic 名稱結尾的 s 不是秒數的單位"
    o, err = echo.parse_cli(["/odom", "--where", "v>1"])
    assert_error(err, "--duration")
    o, err = echo.parse_cli(["/odom", "--bogus", "1"])
    assert_error(err, "不認識的選項", "--duration")
    o, err = echo.parse_cli(["/odom", "--where", "v<abc", "--duration", "5"])
    assert_error(err, "數字")


def t_json_keys():
    """字串裡的 JSON 展開成 Key：巢狀欄位、依名稱展開的清單、空清單變成集合狀態；不是 JSON 的那一則跳過、不算錯誤"""
    samples = [_String(json.dumps({"mode": "IDLE" if i < 5 else "RUNNING", "battery": 80 - i, "errors": [] if i < 7 else ["E1"],
                                   "robots": [{"name": "a", "v": i}, {"name": "b", "v": 2 * i}]})) for i in range(12)] + [_String("")]
    keys = {k["key"]: k for k in rd.describe_keys(_String, samples)}
    assert keys["data"]["category"] == "text" and keys["data"].get("json"), keys["data"]
    assert keys["data.mode"]["category"] == "state" and keys["data.battery"]["category"] == "numeric", keys
    assert keys["data.errors"]["category"] == "state" and keys["data.errors"]["dim"] == "set", keys["data.errors"]
    assert keys["data.robots.v"]["map_by"] == ["data.robots.name"], keys["data.robots.v"]
    descs = dict(keys)
    series, errors = {k: {} for k in descs}, {}
    for t, s in enumerate(samples):
        rd._collect(s, t * 100_000_000, list(descs), descs, series, errors)
    assert not errors, errors
    feats, flags = rd.measure_key(series["data.mode"], descs["data.mode"], {"start_ns": 0, "end_ns": 13 * 100_000_000}, "data.mode")
    assert flags == ["data.mode 狀態跳轉 1 次"], flags


def t_where():
    """--where：第一筆符合與前一筆、符合的時段、true／false、陣列任一個元素、數字的字串、比不了的筆數"""
    c, err = rd.parse_where("voltage<24")
    assert err is None
    pts = [(i * 100_000_000, 24.5 - i * 0.1) for i in range(20)]
    r = rd.condition_features(pts, c, 2_000_000_000)
    assert r["matched"] == 14 and r["first"]["index"] == 7 and r["prev"]["index"] == 6 and r["stays_after_first"], r
    c, _ = rd.parse_where("ok==true")
    assert rd.condition_features([(0, True), (1, False)], c, 2)["matched"] == 1, "true 要跟布林值比得了"
    c, _ = rd.parse_where("ranges<0.5")
    assert rd.condition_features([(0, (1.0, 2.0)), (1, (0.2, 3.0))], c, 2)["matched"] == 1, "陣列任一個元素符合"
    c, _ = rd.parse_where("count>18")
    r = rd.condition_features([(0, "19"), (1, "x"), (2, 17)], c, 3)
    assert r["matched"] == 1 and r["uncomparable"] == 1, r
    assert rd.parse_where("mode=RUNNING")[0]["op"] == "==", "單一個 = 當成 =="
    assert rd.parse_where("v<abc")[1], "大小比較要數字"


def t_log_lines():
    """容器的 log：docker 的時間、launch 的程序名稱、顏色碼、ROS 的格式、traceback 合成一則 ERROR，去重跟 rosout_parser 同一套"""
    lines = ["2026-10-23T04:15:30.100000000Z [talker-1] [INFO] [1791967507.100000000] [talker]: n=1",
             "2026-10-23T04:15:30.200000000Z [talker-1] [INFO] [1791967507.200000000] [talker]: n=2",
             "2026-10-23T04:15:31.000000000Z \x1b[33m[WARN] [1791967508.000000000] [planner]: stale\x1b[0m",
             "2026-10-23T04:15:31.500000000Z Traceback (most recent call last):",
             '2026-10-23T04:15:31.500000000Z   File "/ws/nav.py", line 12, in <module>',
             "2026-10-23T04:15:31.500000000Z ValueError: invalid speed 3.5",
             "2026-10-23T04:15:33.000000000Z plain line"]
    ev = rd.parse_log_lines(lines)
    assert [e["level"] for e in ev] == ["INFO", "INFO", "WARN", "ERROR", "INFO"], [e["level"] for e in ev]
    assert ev[0]["proc"] == "talker-1" and ev[2]["msg"] == "stale", ev[:3]
    assert ev[3]["msg"] == "ValueError: invalid speed 3.5" and len(ev[3]["detail"]) == 3, ev[3]
    groups = rd.dedup_events(ev)
    assert groups[0]["count"] == 2 and groups[0]["message"] == "n=1", "只差在數字的算同一個訊號"


def t_no_container():
    """數據技能沒有目標容器：[ERROR] 寫下一步（docker_containers／docker_open）"""
    env = {"TARGET_CONTAINER": "", "ANALYSIS_DATA": ""}
    for script, args in (("ROS2_topic_echo_cmd.py", ["/odom"]), ("mcap_feature_measure_cmd.py", ["--topic", "/odom", "--key", "x"])):
        code, out = run_script(script, *args, env=env, timeout=60)
        assert_error(out, "docker_containers")


def t_not_recording():
    """數據技能給了主機上的一般檔案（文字 Log 的資料夾、.log 檔）：找容器之前就說不是錄製數據、下一步是 search_text／view_file；
    有 .mcap 的實驗資料夾（第二層）與主機上不存在的路徑照舊交給容器端（沒有目標容器時回 docker_containers 的下一步）"""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="skills_data_")
    os.makedirs(os.path.join(tmp, "logs", "2026-10-10"))
    for name in ("robot_tb1.log", "robot_tb3.log"):
        with open(os.path.join(tmp, "logs", "2026-10-10", name), "w", encoding="utf-8") as f:
            f.write("2026-10-10 07:00:08 [ERROR] tb3 E1203 motor fault\n")
    os.makedirs(os.path.join(tmp, "exp1", "bag"))
    open(os.path.join(tmp, "exp1", "bag", "exp1_0.mcap"), "wb").close()
    env = {"TARGET_CONTAINER": "", "ANALYSIS_DATA": "", "ANALYSIS_DATA_ROOT": ""}
    code, out = run_script("rosout_parser_cmd.py", "logs/2026-10-10/", "--level", "ERROR", cwd=tmp, env=env, timeout=60)
    assert_error(out, "不是錄製數據", "robot_tb3.log", 'search_text "ERROR|WARN" logs/2026-10-10/', "view_file")
    assert "docker_containers" not in out, out
    code, out = run_script("mcap_feature_measure_cmd.py", "logs/2026-10-10/robot_tb3.log", "--topic", "/odom", "--key", "x",
                           cwd=tmp, env=env, timeout=60)
    assert_error(out, "mcap_feature_measure", "是一個檔案", "search_text")
    for data in ("exp1", "no_such_experiment"):
        code, out = run_script("rosout_parser_cmd.py", data, cwd=tmp, env=env, timeout=60)
        assert_error(out, "docker_containers")
        assert "不是錄製數據" not in out, f"{data} 要交給容器端判斷：{out}"


def t_not_recording_real_data():
    """主機端的「不是錄製數據」判斷不能擋到真的錄製：test_data 裡每一份有 .mcap 的數據（實驗資料夾、bag 資料夾）與它的上一層都放行
    （test_data 不在版控裡，沒有就略過；2026-10-23 是 1,481 份）"""
    import glob
    from selftest import PROJECT
    root = os.path.join(PROJECT, "test_data")
    mcaps = glob.glob(os.path.join(root, "**", "*.mcap"), recursive=True)
    if not mcaps:
        raise Skip("沒有 test_data 的錄製（不在版控裡）")
    dirs = set()
    for m in mcaps:
        d = os.path.dirname(m)
        dirs.add(os.path.dirname(d) if os.path.basename(d) in ("bag", "mcap") else d)
    blocked = [(d, e[:160]) for d in sorted(dirs) for cand in (d, os.path.dirname(d)) for e in [rd.not_recording(cand, "x")] if e]
    assert not blocked, f"{len(blocked)} 份真的錄製被擋：{blocked[:3]}"


def _live():
    r = subprocess.run(["docker", "inspect", LIVE, "--format", "{{.State.Running}}"], capture_output=True, text=True)
    if r.stdout.strip() != "true":
        raise Skip(f"測試容器 {LIVE} 沒有在跑")


def t_echo_live():
    """ROS2_topic_echo 實測（測試容器裡起一個發 JSON 狀態的 publisher）：單筆、--duration 的狀態跳轉與 --where、名稱打錯列出相近的"""
    _live()
    pub = ("import json,time,rclpy\nfrom std_msgs.msg import String\nrclpy.init()\nn=rclpy.create_node('agent_skills_test_pub')\n"
           "p=n.create_publisher(String,'/agent_skills_test/status',10)\nt0=time.time()\n"
           "while time.time()-t0<25:\n  k=time.time()-t0\n  p.publish(String(data=json.dumps({'mode':'IDLE' if k<4 else 'RUNNING','v':round(k,2)})))\n"
           "  time.sleep(0.1)\n")
    subprocess.run(["docker", "exec", "-i", LIVE, "bash", "-c", "cat > /tmp/agent_skills_test_pub.py"], input=pub, text=True, check=True)
    subprocess.run(["docker", "exec", "-d", LIVE, "bash", "-lc", "source /opt/ros/*/setup.bash; python3 /tmp/agent_skills_test_pub.py"],
                   check=True)
    env = {"TARGET_CONTAINER": LIVE}
    try:
        import time
        time.sleep(2)
        code, out = run_script("ROS2_topic_echo_cmd.py", "/agent_skills_test/status", env=env, timeout=120)
        assert out.startswith("[PASS] /agent_skills_test/status（std_msgs/msg/String）的一筆訊息"), out[:300]
        code, out = run_script("ROS2_topic_echo_cmd.py", "/agent_skills_test/status", "--duration", "6", "--where", "data.mode==RUNNING",
                               env=env, timeout=180)
        assert out.startswith("[PASS] 觀察") and "## 有變化的欄位" in out and "data.mode" in out and "條件 data.mode==RUNNING" in out, out[:1500]
        code, out = run_script("ROS2_topic_echo_cmd.py", "/agent_skills_test/stat", env=env, timeout=120)
        assert_error(out, "相近的", "ROS2_topic_list")
    finally:
        subprocess.run(["docker", "exec", LIVE, "pkill", "-f", "agent_skills_test_pub.py"], capture_output=True)
