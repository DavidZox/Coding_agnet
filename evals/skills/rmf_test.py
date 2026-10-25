"""調度系統技能（workpackage_send／workpackage_status／workpackage_cancel／overpending_cancel／semantic_map／rmf_handshake）的自我測試。

測試伺服器是評測沙盒的 rmf_sim（evals/ops/dataset/sandbox/rmf_sim/rmf_sim.py --no-ros，純標準庫，照真的 fih_rmf_system 維護）：
每個情境在 127.0.0.1 的空 port 上起一個新的（設定各自不同：沒有名稱的地圖、忙碌／離線／完成訊號遺失的機器人、刪除晚到、短的
ping 間隔），技能以環境變數 RMF_WEB_CONSOLE_URL／RMF_MANUAL_TRIGGER_URL 指過去；DOCKER_HOST 指到不存在的位址、TARGET_CONTAINER
清空，rmf_handshake 不會碰到主機上的任何容器。另外有幾個假的伺服器（接受連線但不回、一連上就斷、沒有 /api/topology 的舊版）測錯誤訊息。
ROS 2 的情境（--ros2 發布 fih_rmf_msgs/WorkPackage、status 在容器裡聽交握 topic）要 evals/ops 的沙盒 daemon（cah_ops_dind）：
設 RMF_TEST_SANDBOX=1、先 `python evals/ops/dataset/sandbox/sandbox.py up` 才跑（會 reset 沙盒裡的容器），否則略過。
"""
import contextlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from selftest import PROJECT, SCRIPTS, Skip, assert_error, first_line, run_script

# selftest.py 以 __main__ 執行時，`from selftest import Skip` 拿到的是另一份模組的類別，它的 except Skip 接不到：用 __main__ 的
_MAIN = sys.modules.get("__main__")
SkipTest = getattr(_MAIN, "Skip", Skip) if os.path.basename(getattr(_MAIN, "__file__", "") or "") == "selftest.py" else Skip

SIM = os.path.join(PROJECT, "evals", "ops", "dataset", "sandbox", "rmf_sim", "rmf_sim.py")
NO_DOCKER = "tcp://127.0.0.1:9"          # 不存在的 daemon：rmf_handshake 猜不到也碰不到任何容器
ROBOTS3 = [{"id": "tb1", "station": "home", "behavior": "normal"}, {"id": "tb2", "station": "a0", "behavior": "normal"},
           {"id": "tb3", "station": "a8", "behavior": "normal"}]


def pkg(pid, robot, *stops, loop=False):
    return {"task_id": pid, "assign_amr": robot, "loop": loop, "loop_count": None, "stops": [{"station": s} for s in stops]}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_json(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode() or "null")


class Sim:
    """一個 rmf_sim --no-ros（只綁 127.0.0.1）。with 區塊結束就關掉。"""

    def __init__(self, robots=None, packages=(), nodes=None, edges=None, ping=(20, 20), **params):
        self.cfg = {"robots": robots or ROBOTS3, "packages": list(packages), "params": params}
        if nodes is not None:
            self.cfg["nodes"] = nodes
        if edges is not None:
            self.cfg["edges"] = edges
        self.ping = ping

    def __enter__(self):
        fd, self.cfg_path = tempfile.mkstemp(suffix=".json", prefix="rmf_test_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False)
        self.web, self.trig = free_port(), free_port()
        self.url, self.trigger = f"http://127.0.0.1:{self.web}", f"http://127.0.0.1:{self.trig}"
        self.proc = subprocess.Popen([sys.executable, SIM, "--no-ros", "--host", "127.0.0.1", "--web-port", str(self.web),
                                      "--trigger-port", str(self.trig), "--config", self.cfg_path,
                                      "--ws-ping-interval", str(self.ping[0]), "--ws-ping-timeout", str(self.ping[1])],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                http_json(self.url + "/api/robots")
                return self
            except OSError:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"rmf_sim 沒有起來：{self.proc.stderr.read()[-800:]}")
                time.sleep(0.1)
        raise RuntimeError("rmf_sim 10 秒內沒有回應")

    def __exit__(self, *exc):
        self.stop()
        os.remove(self.cfg_path)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def env(self, **extra):
        return dict({"RMF_WEB_CONSOLE_URL": self.url, "RMF_MANUAL_TRIGGER_URL": self.trigger, "DOCKER_HOST": NO_DOCKER,
                     "TARGET_CONTAINER": ""}, **extra)

    def run(self, script, *args, timeout=120):
        code, out = run_script(script, *args, env=self.env(), timeout=timeout)
        assert code == 0, f"{script} {' '.join(args)} exit code {code}：{out[:800]}"
        return out

    def state(self):
        return http_json(self.url + "/api/sim_state")

    def log(self, kind, **match):
        return [e for e in self.state()["log"] if e["kind"] == kind and all(e.get(k) == v for k, v in match.items())]

    def wait_for(self, pred, seconds, what):
        deadline = time.time() + seconds
        while time.time() < deadline:
            st = self.state()
            if pred(st):
                return st
            time.sleep(0.3)
        raise AssertionError(f"{seconds} 秒內沒有等到：{what}")

    def current_item(self, pid):
        return self.state()["packages"][pid]["current_item"]["item_id"]


def load(name):
    spec = importlib.util.spec_from_file_location(f"rmf_{name}", os.path.join(SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, SCRIPTS)
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def no_network():
    """parse_args 要是純函式：期間一連網路就失敗。"""
    def boom(*a, **k):
        raise AssertionError("parse_args 不應該連線")
    saved = (socket.create_connection, urllib.request.urlopen)
    socket.create_connection, urllib.request.urlopen = boom, boom
    try:
        yield
    finally:
        socket.create_connection, urllib.request.urlopen = saved


@contextlib.contextmanager
def fake_server(kind):
    """silent：接受連線、不回任何東西；close：一連上就關；old：沒有 /api/topology 的舊版 web_console（有 /api/stations、/api/robots）。"""
    if kind == "old":
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = {"/api/stations": {"stations": [{"id": "3", "label": "a3"}, {"id": "7", "label": "7"}]},
                        "/api/robots": {"robots": ["tb1"]}}.get(self.path)
                data = json.dumps(body if body is not None else {"detail": "Not Found"}).encode()
                self.send_response(200 if body is not None else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{srv.server_address[1]}"
        finally:
            srv.shutdown()
        return
    ls = socket.socket()
    ls.bind(("127.0.0.1", 0))
    ls.listen(16)
    held, stop = [], threading.Event()

    def loop():
        ls.settimeout(0.2)
        while not stop.is_set():
            try:
                c, _ = ls.accept()
            except OSError:
                continue
            if kind == "close":
                c.close()
            else:
                held.append(c)
    threading.Thread(target=loop, daemon=True).start()
    try:
        yield f"127.0.0.1:{ls.getsockname()[1]}"
    finally:
        stop.set()
        for c in held:
            c.close()
        ls.close()


# ================================================================ 參數（guard 用的 parse_args，純函式）
def t_parse_send_guard():
    """workpackage_send.parse_args：選項的值不能把 --dry-run 吞掉（guard 只在真的 dry-run 時放行）"""
    send = load("workpackage_send_cmd")
    with no_network():
        ok = send.parse_args(["WP1", "a3", "--dry-run"])
        assert ok["error"] is None and ok["dry_run"] is True and ok["stations"] == ["a3"], ok
        for argv in (["WP1", "a3", "--desc", "--dry-run"], ["WP1", "a3", "--amr", "--dry-run"], ["WP1", "a3", "--desc=--dry-run"],
                     ["WP1", "a3", "--url", "--dry-run"], ["WP1", "a3", "--type", "--dry-run"]):
            p = send.parse_args(argv)
            assert p["error"] and p["error"].startswith("[ERROR]") and "--" in p["error"], (argv, p)
        p = send.parse_args(["WP1", "a3", "--ros2", "--dry-run"])
        assert p["error"] is None and p["dry_run"] and p["ros2"] == "", p
        p = send.parse_args(["WP1", "a3,a7", "--ros2", "rmf_sim", "--loop", "3", "--amr", "tb1"])
        assert p["ros2"] == "rmf_sim" and p["loop"] and p["loop_count"] == 3 and p["amr"] == "tb1" and not p["dry_run"], p
        p = send.parse_args(["WP1", "a3", "--loop"])
        assert p["loop"] is True and p["loop_count"] is None, p
        for argv, word in ((["WP/1", "a3"], "/"), (["WP::1", "a3"], "::"), (["WP1", "a3", "--amr", "tb 1"], "合法"),
                           (["WP1", "a3", "--weight", "-1"], "--weight"), (["WP1", "a3", "--loop", "3", "--forever"], "矛盾"),
                           (["WP1"], "2 個位置參數"), (["WP1", "a3", "--status"], "workpackage_status")):
            p = send.parse_args(argv)
            assert p["error"] and word in p["error"], (argv, p["error"])


def t_parse_handshake_guard():
    """rmf_handshake.parse_args：選項的值不會混進機器人清單、status 是唯讀、機器人 id 驗證"""
    hs = load("rmf_handshake_cmd")
    with no_network():
        p = hs.parse_args(["status", "tb1"])
        assert p["error"] is None and p["readonly"] and p["target"] == "tb1" and p["seconds"] == 4, p
        p = hs.parse_args(["status", "--container", "X", "tb1"])
        assert p["target"] == "tb1" and p["container"] == "X", p
        p = hs.parse_args(["fin", "tb2", "--container", "rmf_sim"])
        assert p["robots"] == ["tb2"] and p["task_id"] is None and not p["readonly"] and p["ignored"] == ["--container rmf_sim"], p
        p = hs.parse_args(["fin", "tb2", "--seconds", "10"])
        assert p["robots"] == ["tb2"] and p["task_id"] is None, p
        p = hs.parse_args(["yes", "tb1", "--container", "rmf_sim"])
        assert p["robots"] == ["tb1"], p
        p = hs.parse_args(["yes", "tb1,tb3"])
        assert p["robots"] == ["tb1", "tb3"], p
        p = hs.parse_args(["fin", "tb2", "WP_L2::0::0::ab12cd34-3"])
        assert p["robots"] == ["tb2"] and p["task_id"] == "WP_L2::0::0::ab12cd34-3", p
        for argv, word in ((["status", "tb1", "--seconds", "1000"], "1～60"), (["status", "tb1", "--seconds", "abc"], "秒數"),
                           (["yes", "tb1;rm"], "合法"), (["status", "tb1 tb2"], "空白"), (["tb1", "status"], "動作要放第一個"),
                           (["fin"], "fin 要"), (["status", "tb1", "--container", "a b"], "容器名稱"), (["yes"], "至少一台"),
                           (["status", "--url", "--seconds", "3", "tb1"], "-- 開頭")):
            p = hs.parse_args(argv)
            assert p["error"] and word in p["error"], (argv, p["error"])


# ================================================================ workpackage_send
def t_send_station_resolution():
    """發送：數字只當節點 id（2＝a3，不是語意名稱含 2 的站）、語意名稱、輸出列出送出的值與 id"""
    with Sim() as sim:
        out = sim.run("workpackage_send_cmd.py", "WPX", "2", "--dry-run")
        assert first_line(out).startswith("[PASS]") and "dry-run" in first_line(out), out
        assert "a3（id 2｜組裝線區-1）" in out and '"station": "a3"' in out and "「2」＝節點 id → a3" in out, out
        out = sim.run("workpackage_send_cmd.py", "WPX", "home,組裝線區-2,id4", "--dry-run")
        assert "home（id 0｜充電待命區） → a7（id 5｜組裝線區-2） → a6（id 4）" in out, out
        assert_error(sim.run("workpackage_send_cmd.py", "WPX", "組裝", "--dry-run"), "符合 2 個站點", "a3", "a7", "下一步")
        assert_error(sim.run("workpackage_send_cmd.py", "WPX", "a9"), "沒有站點「a9」", "semantic_map --stations", "下一步")
        assert_error(sim.run("workpackage_send_cmd.py", "WPX", "99"), "沒有站點「99」")
        assert not sim.log("package_received"), "dry-run 與錯誤都不應該送出"


def t_send_checks_and_confirm():
    """發送：送出後確認 orchestrtor 收到；重複的 id、名冊沒有的機器人、無限循環"""
    with Sim() as sim:
        out = sim.run("workpackage_send_cmd.py", "WP1", "home,a3", "--amr", "tb1")
        assert first_line(out).startswith("[PASS] work package「WP1」已送出：2 站") and "orchestrtor 已收到（RUNNING" in first_line(out), out
        assert len(sim.log("package_received", package_id="WP1")) == 1
        assert_error(sim.run("workpackage_send_cmd.py", "WP1", "a7", "--amr", "tb2"), "已經有 work package WP1", "換一個 task_id", "workpackage_cancel")
        assert not sim.log("package_duplicate"), "重複的 id 不應該送出"
        assert_error(sim.run("workpackage_send_cmd.py", "WP2", "a3", "--amr", "tb9"), "名冊裡沒有 tb9", "tb1、tb2、tb3", "下一步")
        out = sim.run("workpackage_send_cmd.py", "auto", "a3,a7", "--loop")
        assert "循環：是（無限，直到手動刪除）" in first_line(out) and "機器人：交給 distribute 挑" in first_line(out), out
        st = sim.state()
        auto = [r for r in st["received"] if r["task_id"].startswith("WP-")]
        assert auto and auto[0]["loop"] is True and auto[0]["loop_count"] is None and auto[0]["assign_amr"] == "", auto


def t_send_unreachable_and_old_console():
    """發送：連不上、web_console 沒有 /api/topology 時不送（說原因、下一步、--no-check），--url 不寫 http:// 也可以"""
    port = free_port()
    out = run_script("workpackage_send_cmd.py", "WP1", "a3", "--url", f"127.0.0.1:{port}")[1]
    assert_error(out, "沒辦法核對站點", "連不上 web_console", "--url", "RMF_WEB_CONSOLE_URL", "--no-check")
    with fake_server("old") as url:
        out = run_script("workpackage_send_cmd.py", "WP1", "a3", "--amr", "tb1", "--url", url)[1]
        assert_error(out, "沒有 /api/topology", "--no-check", "沒有送出")
    with Sim() as sim:
        out = run_script("semantic_map_cmd.py", "--stations", "--url", f"127.0.0.1:{sim.web}")[1]
        assert out.startswith("[PASS]") and "a3｜id 2｜組裝線區-1" in out, out


def t_send_unnamed_map():
    """沒有名稱的地圖（name 全是空字串）：站點以 id 表示、語意名稱照常可用、機器人照 id 走完"""
    nodes = [{"id": 0, "name": "", "label": "加工線通道-6", "description": "轉角", "x": 0.0, "y": 0.0},
             {"id": 1, "name": "", "label": "組裝線區-4", "x": 1.0, "y": 0.0},
             {"id": 2, "name": "", "label": "加工線通道-5", "x": 2.0, "y": 0.0},
             {"id": 3, "name": "", "label": "", "x": 2.0, "y": 1.0}]
    nodes += [{"id": 10 + i, "name": "", "label": f"倉儲區-{i}", "x": 5.0 + i, "y": 5.0} for i in range(1, 16)]
    edges = [{"id": 18, "start_id": 0, "end_id": 1, "label": "", "description": "", "points": [[0, 0], [1, 0]]}]
    with Sim(robots=[{"id": "tb1", "station": "0", "behavior": "normal"}], nodes=nodes, edges=edges) as sim:
        out = sim.run("semantic_map_cmd.py", "--stations")
        assert "19 站（有名稱 0、只有 id 19；有語意名稱 18）" in first_line(out), out
        assert "\n- id 0｜加工線通道-6" in out and "\n- id 3\n" in out and "送工作包寫 id 或語意名稱" in out, out
        out = sim.run("semantic_map_cmd.py")
        assert "## 站點（19 個" in out and "- id 0（加工線通道-6）：tb1 在此" in out, out
        out = sim.run("semantic_map_cmd.py", "倉儲")
        assert "站點 15 個" in out and "…另有 3 個站點符合" in out, out
        out = sim.run("workpackage_send_cmd.py", "WPU", "2,組裝線區-4", "--amr", "tb1")
        assert first_line(out).startswith("[PASS]") and "id 2（加工線通道-5） → id 1（組裝線區-4）" in out, out
        assert sim.state()["received"][0]["stops"] == [{"station": "2", "description": ""}, {"station": "1", "description": ""}]
        sim.wait_for(lambda st: st["packages"]["WPU"]["status"] == "COMPLETED", 20, "WPU 完成（機器人照 id 走）")
        out = sim.run("workpackage_status_cmd.py", "WPU")
        assert "COMPLETED" in first_line(out) and "路線 id 2（加工線通道-5） → id 1（組裝線區-4）" in out, out


# ================================================================ workpackage_status
def t_status_snapshot_and_lookup():
    """狀態快照：分節、RUNNING 全列、找不到 id 回 [ERROR]（附相近的）、工作項 id 也查得到"""
    with Sim(robots=[ROBOTS3[0], ROBOTS3[1], dict(ROBOTS3[2], behavior="busy")],
             packages=[pkg("WP_A", "tb1", "a0"), pkg("WP_C3", "tb3", "a6")], authorize_timeout_sec=2.0, threshold_recovery_sec=3.0) as sim:
        sim.wait_for(lambda st: st["packages"]["WP_A"]["status"] == "COMPLETED", 15, "WP_A 完成")
        out = sim.run("workpackage_status_cmd.py")
        assert first_line(out).startswith("[PASS] 目前狀態：work package 2 個（RUNNING 1、COMPLETED 1）"), out
        for sec in ("## work package（2 個", "## distribute 佇列", "## 機器人（3 台", "## 最近事件"):
            assert sec in out, (sec, out)
        assert out.index("- WP_C3 RUNNING") < out.index("- WP_A COMPLETED"), "RUNNING 要在前"
        assert_error(sim.run("workpackage_status_cmd.py", "WP_C"), "沒有 work package WP_C", "相近的", "WP_C3", "下一步")
        item = sim.current_item("WP_C3")
        out = sim.run("workpackage_status_cmd.py", item)
        assert first_line(out).startswith(f"[PASS] 工作項 {item}：distribute") and "WP_C3（RUNNING）目前的工作項" in first_line(out), out
        assert_error(sim.run("workpackage_status_cmd.py", "--watch", "0"), "1～300")


def t_status_render_many_completed():
    """狀態快照：已完成的很多時 RUNNING 一定列出，寫明另有幾個沒列（不默默截掉）"""
    st = load("workpackage_status_cmd")
    pk = [{"package_id": f"OLD{i:02d}", "status": "COMPLETED", "iteration": 1, "station_count": 1, "stations": ["a3"],
           "updated_at": i} for i in range(40)]
    pk += [{"package_id": "NEW1", "status": "RUNNING", "station_index": 0, "station_count": 1, "stations": ["a7"],
            "current_item": {"item_id": "NEW1::0::0::x-1", "station": "a7", "status": "DISPATCHED", "robot_id": None, "waiting_for_robot": True}}]
    data = {"step_counter": 5, "state": "REPORT", "raw_tasks": [{"id": "NEW1::0::0::x-1", "age": 1.0}], "robots": {},
            "orchestrtor": {"step_counter": 5, "packages": pk}}
    out = st.render_all(data, None)
    assert "另有 11 個已完成的沒列" in first_line(out) and "- NEW1 RUNNING" in out, out
    assert "…另有 11 個已完成（COMPLETED）的沒列出" in out and "- OLD39 COMPLETED" in out and "- OLD00 COMPLETED" not in out, out


def t_status_watch_series():
    """--watch：每個對象一條狀態序列（變遷有前後與時間、占比）、摘要在前；帶 task_id 只看它；不存在的 id 回 [ERROR]"""
    with Sim(packages=[pkg("WP_A", "tb1", "a3", "a7"), pkg("WP_B", "tb2", "a8")]) as sim:
        out = sim.run("workpackage_status_cmd.py", "--watch", "5")
        lines = out.splitlines()
        assert lines[0].startswith("[PASS] 觀察 5.") and "收到" in lines[0], out
        assert lines[1].startswith("## 結束時"), "摘要要在前面"
        assert "## work package 的變化" in out and "## 工作項（distribute 佇列）的變化" in out and "## 機器人的變化" in out, out
        assert "--- #1 " in out and " → " in out and "時間占比：" in out, out
        assert "進入" not in out and "離開 raw" not in out, "一次移動只寫一行（從 → 到）"
        out = sim.run("workpackage_status_cmd.py", "WP_B", "--watch", "3")
        assert "WP_A" not in out, f"帶 task_id 只看它：{out}"
        assert_error(sim.run("workpackage_status_cmd.py", "NOPE", "--watch", "2"), "一直沒有 NOPE", "下一步")


def t_watch_answers_pings():
    """--watch 會回 pong：web_console 每 1 秒 ping、1 秒內沒 pong 就斷（同 uvicorn 20＋20 秒），觀察 6 秒不會中斷"""
    with Sim(ping=(1, 1)) as sim:
        out = sim.run("workpackage_status_cmd.py", "--watch", "6")
        assert "⚠️" not in first_line(out) and "ping" in first_line(out) and "都已回應" in first_line(out), out
        # 對照：不回 pong 的客戶端會被斷線（證明上面的測試有意義）
        rc = load("_rmf_common")

        class NoPong(rc.WsStream):
            def _send(self, opcode, payload=b""):
                if opcode != 0xA:
                    super()._send(opcode, payload)
        with NoPong(sim.url) as ws:
            for _ in ws.frames(duration=8):
                pass
            assert ws.end == "close" and ws.close_code == 1011 and ws.elapsed < 6, (ws.end, ws.close_code, ws.elapsed)
            assert "1011" in ws.end_text()


def t_watch_early_end():
    """--watch 途中 web_console 斷線：第一行寫只觀察到幾秒、原因，附中斷前的整理與下一步"""
    with Sim(packages=[pkg("WP_A", "tb1", "a3")]) as sim:
        p = subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "workpackage_status_cmd.py"), "--watch", "20"], cwd=PROJECT,
                             env=dict(os.environ, **sim.env()), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
        time.sleep(3)
        sim.stop()
        out = p.communicate(timeout=60)[0].strip()
    head = first_line(out)
    assert head.startswith("[PASS] ⚠️ 只觀察到") and "就中斷（要求 20 秒" in head, out
    assert "下一步：再執行一次" in out.splitlines()[1] and "## 結束時" in out, out
    assert "--watch 20 接著看" in out.splitlines()[1], "下一步的指令要能直接執行（--watch 要帶秒數）"


def t_status_until_done():
    """--until-done：工作包完成就結束（不等滿秒數）、已經完成的立刻回、時間到還沒完成寫現況與下一步；第一幀就沒有、無限循環、
    沒帶工作包、帶了工作項都馬上回 [ERROR]"""
    st = load("workpackage_status_cmd")
    assert st.parse_args(["WP_A", "--until-done"])["watch"] == 300, "沒給 --watch 就最多等 300 秒"
    assert_error(st.parse_args(["--until-done"])["error"], "要指定工作包", "下一步")
    assert_error(st.parse_args(["WP_A::0::0::x-1", "--until-done"])["error"], "workpackage_status WP_A --until-done")
    with Sim(robots=[ROBOTS3[0], dict(ROBOTS3[1], behavior="slow"), ROBOTS3[2]],
             packages=[pkg("WP_A", "tb1", "a0"), pkg("WP_S", "tb2", "a8"), pkg("WP_L", "tb3", "a6", loop=True)]) as sim:
        t0 = time.time()
        out = sim.run("workpackage_status_cmd.py", "WP_A", "--until-done", "--watch", "120")
        took = time.time() - t0
        assert first_line(out).startswith("[PASS] WP_A 已完成：COMPLETED") and "看到完成就結束觀察" in first_line(out), out[:600]
        assert took < 60, f"完成就要結束，不是看滿 120 秒（{took:.0f} 秒）"
        assert "## 結束時" in out and "- WP_A COMPLETED" in out, out[:800]
        out = sim.run("workpackage_status_cmd.py", "WP_A", "--until-done")
        assert "觀察開始時就已經完成" in first_line(out), out[:400]
        out = sim.run("workpackage_status_cmd.py", "WP_S", "--until-done", "--watch", "3")
        lines = out.splitlines()
        assert "WP_S 還沒完成：結束時 RUNNING" in lines[0] and lines[1].startswith("下一步：要繼續等就再執行一次 workpackage_status WP_S --until-done"), out[:600]
        t0 = time.time()
        assert_error(sim.run("workpackage_status_cmd.py", "NOPE", "--until-done"), "沒有 work package NOPE", "下一步")
        assert_error(sim.run("workpackage_status_cmd.py", "WP_L", "--until-done"), "無限循環", "--watch 秒", "workpackage_cancel WP_L")
        assert time.time() - t0 < 30, "找不到、無限循環：第一幀就回，不等到 300 秒"
    assert_error(load("workpackage_send_cmd").parse_args(["WP9", "a3", "--amr", "tb1", "--until-done"])["error"], "workpackage_status")


def t_until_done_stuck():
    """--until-done 看得出不會自己往下走就提早結束（2026-10-24 以前一律等滿 300 秒：一直回 no 的機器人、完成訊號遺失）：
    完成訊號遺失、閒著的機器人一直不接授權 → 寫原因與下一步；第一次授權沒回應之後照常的、走很慢（在動）的照常等。
    第一行不能有「已完成」（工作流的檢查看這三個字）"""
    robots = [dict(ROBOTS3[0], behavior="lost_fin"), dict(ROBOTS3[1], behavior="lost_yes_once"), dict(ROBOTS3[2], behavior="busy"),
              {"id": "tb4", "station": "a4", "behavior": "slow"}]
    pk = [pkg("WP_F", "tb1", "a3"), pkg("WP_Y", "tb2", "a7"), pkg("WP_B", "tb3", "a6"), pkg("WP_S", "tb4", "a8")]
    with Sim(robots=robots, packages=pk, authorize_timeout_sec=2.0, threshold_recovery_sec=2.0) as sim:
        procs = {p["task_id"]: subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "workpackage_status_cmd.py"), p["task_id"], "--until-done",
                                                 "--watch", "12" if p["task_id"] == "WP_S" else "40"], cwd=PROJECT,
                                                env=dict(os.environ, **sim.env()), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
                 for p in pk}
        outs = {pid: p.communicate(timeout=90)[0].strip() for pid, p in procs.items()}
    head, nxt = outs["WP_F"].splitlines()[0], outs["WP_F"].splitlines()[1]
    assert head.startswith("[PASS] WP_F 沒有進展，提早結束觀察") and "完成訊號多半遺失了" in head and "已完成" not in head, outs["WP_F"][:600]
    assert nxt.startswith("下一步：") and "rmf_handshake fin tb1 WP_F::" in nxt and "workpackage_status WP_F --until-done" in nxt, nxt
    head, nxt = outs["WP_B"].splitlines()[0], outs["WP_B"].splitlines()[1]
    assert head.startswith("[PASS] WP_B 沒有進展，提早結束觀察") and "tb3 閒著" in head and "授權 2 次都逾時" in head and "已完成" not in head, outs["WP_B"][:600]
    assert "rmf_handshake status tb3 --seconds 15" in nxt and "## 結束時" in outs["WP_B"], nxt
    assert first_line(outs["WP_Y"]).startswith("[PASS] WP_Y 已完成：COMPLETED"), outs["WP_Y"][:400]
    assert "WP_S 還沒完成" in first_line(outs["WP_S"]), "走很慢（自報 running）不是卡住：照常等到時間到"


def t_until_confirmed():
    """--until-confirmed：等目前這一站的授權有結果就結束（只要確認授權時不用等整個工作包跑完）——confirm 給機器人＝成功（走很慢的也是、
    第一次授權沒回應之後照常的也是）、閒著的機器人一直不接＝失敗（同 --until-done 的提早結束）、已經 confirm 的立刻回；參數錯回 [ERROR]"""
    st = load("workpackage_status_cmd")
    assert_error(st.parse_args(["WP_A", "--until-done", "--until-confirmed"])["error"], "只能選一個", "--until-confirmed")
    assert_error(st.parse_args(["--until-confirmed"])["error"], "要指定工作包", "下一步")
    assert_error(st.parse_args(["WP_A::0::0::x-1", "--until-confirmed"])["error"], "workpackage_status WP_A --until-confirmed")
    assert st.parse_args(["WP_A", "--until-confirmed"])["watch"] == 300
    robots = [ROBOTS3[0], dict(ROBOTS3[1], behavior="lost_yes_once"), dict(ROBOTS3[2], behavior="busy"),
              {"id": "tb4", "station": "a4", "behavior": "slow"}]
    pk = [pkg("WP_A", "tb1", "a3", "a7"), pkg("WP_Y", "tb2", "a7"), pkg("WP_B", "tb3", "a6"), pkg("WP_S", "tb4", "a8")]
    with Sim(robots=robots, packages=pk, authorize_timeout_sec=2.0, threshold_recovery_sec=2.0) as sim:
        procs = {p["task_id"]: subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "workpackage_status_cmd.py"), p["task_id"],
                                                 "--until-confirmed", "--watch", "40"], cwd=PROJECT, env=dict(os.environ, **sim.env()),
                                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True) for p in pk}
        outs = {pid: p.communicate(timeout=90)[0].strip() for pid, p in procs.items()}
        for pid, rid in (("WP_A", "tb1"), ("WP_Y", "tb2"), ("WP_S", "tb4")):
            assert first_line(outs[pid]).startswith(f"[PASS] {pid} 授權成功：工作項 {pid}::") and f"已經 confirm 給 {rid}" in first_line(outs[pid]), outs[pid][:400]
        head = first_line(outs["WP_B"])
        assert head.startswith("[PASS] WP_B 授權沒有成功，提早結束觀察") and "tb3 閒著" in head, outs["WP_B"][:500]
        assert "rmf_handshake status tb3" in outs["WP_B"].splitlines()[1], outs["WP_B"][:600]
        out = sim.run("workpackage_status_cmd.py", "WP_A", "--until-confirmed")
        assert "授權成功" in first_line(out) and "觀察開始時就是這樣" in first_line(out), out[:300]


def t_until_done_stuck_rules():
    """StuckWatch 的規則（假的快照）：機器人在忙（自報 running）時的授權逾時不算；工作包往下走就重新算；完成訊號遺失要持續
    CONFIRM_SECONDS 才算（剛到站、訊息還在路上的不算）"""
    st, rc = load("workpackage_status_cmd"), load("_rmf_common")

    def frame(where, real="standby", status="DISPATCHED", robot_id=None, idx=0, x=0.0):
        iid = f"WP_Z::0::{idx}::x-{idx + 1}"
        data = {"orchestrtor": {"packages": [{"package_id": "WP_Z", "status": "RUNNING", "station_index": idx, "station_count": 3, "iteration": 0,
                                              "items_done": idx, "current_item": {"item_id": iid, "station": "p2", "status": status,
                                                                                  "robot_id": robot_id}}]},
                "robots": {"amr_07": {"status": "ONLINE", "real_state": real, "state": "duty", "x": x, "y": 0.0}},
                "processing_tasks": [], "overpending_tasks": [], "raw_tasks": []}
        if where == "processing":
            data["processing_tasks"] = [{"id": iid, "robot": "amr_07", "station": "p2"}]
        elif where == "OverPending":
            data["overpending_tasks"] = [{"id": iid, "wait": 0.5}]
        elif where == "raw":
            data["raw_tasks"] = [{"id": iid, "age": 0.5}]
        return data
    cycle = ["processing", "processing", "OverPending", "raw", "processing", "OverPending"]
    w = st.StuckWatch("WP_Z")
    assert not any(w.feed(i, frame(q, real="running"), None) for i, q in enumerate(cycle)), "在忙時的逾時不算"
    w = st.StuckWatch("WP_Z")
    got = [w.feed(i, frame(q), None) for i, q in enumerate(cycle)]
    assert got[:-1] == [None] * 5 and got[-1] == {"kind": "auth_loop", "robot": "amr_07", "item": "WP_Z::0::0::x-1", "count": 2}, got
    w = st.StuckWatch("WP_Z")
    seq = [frame("processing"), frame("OverPending"), frame("processing", idx=1), frame("OverPending", idx=1)]
    assert not any(w.feed(i, f, None) for i, f in enumerate(seq)), "中間往下一站走了：重新算"
    node = {"ref": "p2", "name": "p2", "sid": "2", "sem": "", "x": 0.0, "y": 0.0}
    topo = {"by_name": {"p2": node}, "by_id": {"2": node}}
    w = st.StuckWatch("WP_Z")
    at_station = frame(None, robot_id="amr_07")
    assert rc.fin_lost(at_station, at_station["orchestrtor"]["packages"][0], topo)["robot"] == "amr_07"
    assert w.feed(0.0, at_station, topo) is None and w.feed(rc.CONFIRM_SECONDS - 0.5, at_station, topo) is None, "剛到站的不算"
    got = w.feed(rc.CONFIRM_SECONDS, at_station, topo)
    assert got and got["kind"] == "fin_lost" and got["lasted"] == rc.CONFIRM_SECONDS, got
    away = frame(None, robot_id="amr_07", x=5.0)
    assert rc.fin_lost(away, away["orchestrtor"]["packages"][0], topo) is None, "不在那一站：不是完成訊號遺失（可能導航失敗）"


# ================================================================ workpackage_cancel
def t_cancel():
    """取消：打錯的 id 不送（附相近的）、工作項 id 指路、存在的確認從清單消失並說明當前那一站"""
    with Sim(packages=[pkg("WP_KEEP", "tb1", "a3", "a7", loop=True), pkg("WP_DROP", "tb2", "a7", "a8", loop=True)]) as sim:
        time.sleep(1)
        assert_error(sim.run("workpackage_cancel_cmd.py", "WP_DR0P"), "沒有 work package WP_DR0P", "沒有送出", "相近的", "WP_DROP")
        assert_error(sim.run("workpackage_cancel_cmd.py", "WP_DROP::0::0::x-1"), "工作項 id", "workpackage_cancel WP_DROP", "overpending_cancel")
        assert not [e for e in sim.log("http") if e.get("method") == "DELETE"], "打錯的 id 不應該送出 DELETE"
        out = sim.run("workpackage_cancel_cmd.py", "WP_DROP")
        assert first_line(out).startswith("[PASS] 已取消 work package WP_DROP") and "快照確認已從 orchestrtor 的清單移除" in first_line(out), out
        assert "目前那一站" in out, out
        assert sim.log("package_cancelled", package_id="WP_DROP") and not sim.log("package_cancelled", package_id="WP_KEEP")
        assert_error(sim.run("workpackage_cancel_cmd.py", "WP_DROP"), "沒有 work package WP_DROP", "取消過")
        # 取消後同一個 id 可以再送（真的 orchestrtor 會從清單移除）
        out = sim.run("workpackage_send_cmd.py", "WP_DROP", "a3", "--amr", "tb2")
        assert first_line(out).startswith("[PASS]"), out
        assert "WP_DROP#2" in sim.state()["packages"]


# ================================================================ overpending_cancel
def _busy_world(**params):
    return dict(robots=[ROBOTS3[0], ROBOTS3[1], dict(ROBOTS3[2], behavior="busy")], packages=[pkg("WP_OV", "tb3", "a4")], **params)


def t_overpending_errors_and_wait():
    """OverPending：參數錯、給工作包 id、打錯的 id、此刻不在逾時區（未刪除）、--wait 等它進來再刪並確認"""
    with Sim(**_busy_world(authorize_timeout_sec=2.0, threshold_recovery_sec=4.0)) as sim:
        time.sleep(0.6)
        assert_error(sim.run("overpending_cancel_cmd.py", "X", "--wait", "0"), "1～300")
        item = sim.current_item("WP_OV")
        assert_error(sim.run("overpending_cancel_cmd.py", "WP_OV"), "是 work package 的 id", item, "workpackage_cancel WP_OV")
        assert_error(sim.run("overpending_cancel_cmd.py", item[:-1] + "9"), "找不到工作項", "相近的", item)
        out = sim.run("overpending_cancel_cmd.py", item)
        assert first_line(out).startswith("[PASS] 未刪除") and "--wait 30" in out, out
        out = sim.run("overpending_cancel_cmd.py", item, "--wait", "30")
        assert first_line(out).startswith(f"[PASS] 已刪除 OverPending 工作項 {item}") and "快照確認它已不在 distribute 的任何佇列" in out, out
        assert sim.log("overpending_cancelled", task_id=item)


def t_overpending_race():
    """OverPending 刪除晚到一步（送達前已回流 raw）：檢查全部的佇列，回 [ERROR] 沒有刪到，不會說已刪除"""
    # 週期：OverPending 1.5 秒 → raw → processing 3 秒（授權逾時）→ OverPending…；DELETE 晚 2 秒生效，一定落在 processing
    with Sim(**_busy_world(authorize_timeout_sec=3.0, threshold_recovery_sec=1.5, cancel_latency_sec=2.0)) as sim:
        time.sleep(0.5)
        item = sim.current_item("WP_OV")
        out = sim.run("overpending_cancel_cmd.py", item, "--wait", "20")
        assert_error(out, "沒有刪到", "--wait 30")
        sim.wait_for(lambda st: any(e["kind"] == "overpending_cancel_miss" for e in st["log"]), 8, "延遲的刪除生效（落空）")
        assert not sim.log("overpending_cancelled"), "延遲的刪除應該落空"


# ================================================================ semantic_map
def t_semantic_map():
    """語義地圖：每站一行（名稱｜id｜語意名稱）、有東西的站與機器人各一行、關鍵字每站一筆、找不到回 [ERROR]、舊版改用 /api/stations"""
    with Sim(packages=[pkg("WP_A", "tb1", "a3")]) as sim:
        out = sim.run("semantic_map_cmd.py")
        assert first_line(out).startswith("[PASS] 語義地圖：7 站（有名稱 7；有語意名稱 4）"), out
        assert "## 站點（7 個" in out and "\n- a3｜id 2｜組裝線區-1\n" in out and "\n- a4｜id 3\n" in out, out
        assert "## 目前有機器人或工作包的站" in out and "## 機器人（3 台）" in out and "\n- tb2 ONLINE" in out, out
        out = sim.run("semantic_map_cmd.py", "組裝")
        assert "--- #1 a3｜id 2｜組裝線區-1" in out and "--- #2 a7｜id 5｜組裝線區-2" in out, out
        out = sim.run("semantic_map_cmd.py", "2")
        assert "站點 1 個" in out and "--- #1 a3｜id 2" in out, out
        assert_error(sim.run("semantic_map_cmd.py", "不存在的站"), "找不到", "--stations")
        out = sim.run("semantic_map_cmd.py", "--robots")
        assert first_line(out).startswith("[PASS] 目前場域的機器人：3 台") and "\n- tb3 ONLINE" in out, out
    with fake_server("old") as url:
        out = run_script("semantic_map_cmd.py", "--stations", "--url", url)[1]
        assert out.startswith("[PASS]") and "改用 /api/stations" in out and "- a3｜id 3" in out and "- id 7" in out, out
        assert_error(run_script("semantic_map_cmd.py", "--url", url)[1], "404", "--stations")


# ================================================================ 連線的錯誤
def t_connection_errors():
    """連線的錯誤都有原因與下一步：拒絕連線、接受連線但不握手（不會當掉）、一連上就斷、沒有錯誤的 --ros2 提示"""
    port = free_port()
    out = run_script("workpackage_status_cmd.py", "--url", f"127.0.0.1:{port}")[1]
    assert_error(out, "連不上 web_console", "--url", "RMF_WEB_CONSOLE_URL", "下一步")
    assert "--ros2" not in out, "沒有 --ros2 的技能不應該提示它"
    with fake_server("silent") as addr:
        t = time.time()
        code, out = run_script("workpackage_status_cmd.py", "--url", addr, timeout=60)
        assert code == 0 and time.time() - t < 15, (code, time.time() - t, out)
        assert_error(out, "沒有完成 WebSocket 握手", "--url", "下一步")
    with fake_server("close") as addr:
        code, out = run_script("semantic_map_cmd.py", "--url", addr)
        assert code == 0, out
        assert_error(out, "中途關閉連線", "下一步")
    out = run_script("workpackage_cancel_cmd.py", "WP1", "--url", "http://:x")[1]
    assert_error(out, "不合法", "http://主機:port")


# ================================================================ rmf_handshake
def t_handshake_trigger_checks():
    """交握 yes／no／fin：名冊核對、選項的值不會被當成機器人或 task_id、fin 找不到在等的工作項就不送"""
    with Sim() as sim:
        assert_error(sim.run("rmf_handshake_cmd.py", "no", "tb9"), "名冊裡沒有 tb9", "下一步")
        out = sim.run("rmf_handshake_cmd.py", "yes", "tb1", "--container", "rmf_sim")
        assert first_line(out).startswith("[PASS] 已經由 manual_trigger 對 tb1 送出 handshake yes") and "已略過 --container rmf_sim" in out, out
        assert "下一筆派給它的工作項會直接 confirm" in out, out
        calls = sim.log("manual_trigger_call")
        assert [c["robot"] for c in calls] == ["tb1"], calls
        assert_error(sim.run("rmf_handshake_cmd.py", "fin", "tb2", "--container", "rmf_sim"), "找不到 tb2 唯一一個", "沒有送出")
        assert_error(sim.run("rmf_handshake_cmd.py", "fin", "tb2", "--seconds", "10"), "找不到 tb2 唯一一個")
        assert len(sim.log("manual_trigger_call")) == 1, "fin 不應該送出"
        out = sim.run("rmf_handshake_cmd.py", "no", "tb1,tb3")
        assert first_line(out).startswith("[PASS]") and {c["robot"] for c in sim.log("manual_trigger_call", value="no")} == {"tb1", "tb3"}, out
    port = free_port()
    with Sim() as sim:
        code, out = run_script("rmf_handshake_cmd.py", "yes", "tb1", "--trigger", f"127.0.0.1:{port}", env=sim.env())
        assert_error(out, "連不上 manual_trigger", "ros2 run fih_rmf_system manual_trigger", "--trigger", "RMF_MANUAL_TRIGGER_URL")
        assert "rmf_launch.py 帶起" not in out and "--ros2" not in out, out


def t_handshake_status_mapping():
    """交握 status：給工作包會換成它的機器人（離線、忙碌）；沒聽 topic 時說明，不會說「看不出異常」"""
    world = dict(robots=ROBOTS3 + [{"id": "tb5", "station": "a6", "behavior": "offline"}, dict(ROBOTS3[2], id="tb4", behavior="busy")],
                 packages=[pkg("WP_E5", "tb5", "a3"), pkg("WP_C4", "tb4", "a6")], authorize_timeout_sec=1.5, threshold_recovery_sec=3.0)
    with Sim(**world) as sim:
        time.sleep(4)
        out = sim.run("rmf_handshake_cmd.py", "status", "WP_E5")
        assert first_line(out).startswith("[PASS] WP_E5 → tb5 的交握狀況：離線（OFFLINE）"), out
        assert "看不出異常" not in out, out
        out = sim.run("rmf_handshake_cmd.py", "status", "WP_C4")
        assert first_line(out).startswith("[PASS] WP_C4 → tb4 的交握狀況："), out
        assert "授權逾時" in out and "沒有聽" in out and "看不出異常" not in out, out
        assert_error(sim.run("rmf_handshake_cmd.py", "status", "tb9"), "名冊裡沒有 tb9", "工作包")
    port = free_port()
    out = run_script("rmf_handshake_cmd.py", "status", "tb1", "--url", f"127.0.0.1:{port}", env={"DOCKER_HOST": NO_DOCKER, "TARGET_CONTAINER": ""})[1]
    assert_error(out, "看不到 tb1 的任何資料", "--container", "下一步")
    out = run_script("rmf_handshake_cmd.py", "status", "tb1;rm", "--url", f"127.0.0.1:{port}", env={"DOCKER_HOST": NO_DOCKER, "TARGET_CONTAINER": ""})[1]
    assert out.startswith("[ERROR]") and "機器人 id" in out, out


def t_handshake_listen_verdicts():
    """交握 status 的判斷依證據分開：沒有回覆時看 handshake_states 有沒有發布者；聽不到 authorize 時看 allocator_status 有沒有發布者、
    聽完的快照工作項還在不在授權中（進了 OverPending＝剛好在冷卻，不是容器不對）；聽的結果（JSON）解析成次數與時間線"""
    hs = load("rmf_handshake_cmd")
    item = {"id": "WP_C3::0::0::x-1", "station": "a6"}
    data = {"events": []}

    def verdict(**lis):
        base = {"ok": True, "authorize": 0, "confirm": 0, "other": 0, "yes": 0, "no": 0, "seconds": 4, "domain": "42", "publishers": {"A": 1, "H": 1}}
        base.update(lis)
        d = hs._diagnose("tb3", {"status": "ONLINE", "real_state": "standby"}, data, None, base, [item], [], [])
        return d[0][1], d[0][2]
    title, text = verdict(authorize=5, publishers={"A": 1, "H": 0})
    assert title == "沒有回應授權" and "沒有任何 /tb3/handshake_states 的發布者" in text and "rmf_handshake yes tb3" in text, text
    assert verdict(authorize=5, no=5)[0] == "對授權一直回 no"
    title, text = verdict(publishers={"A": 0, "H": 0})
    assert title.startswith("看不到 distribute 的授權 topic") and "--container" in text, text
    title, text = verdict(after={item["id"]: "OverPending"})
    assert title.startswith("這幾秒剛好沒有授權") and "OverPending 冷卻" in text and "--seconds 15" in text, text
    title, text = verdict(after={item["id"]: "processing"})
    assert title == "有發布者但聽不到 authorize" and "resource_allocator" in text, text
    import _docker_common
    old = _docker_common.ros2_exec
    try:
        _docker_common.ros2_exec = lambda c, cmd, t: (True, 'some warning\n{"domain": "42", "publishers": {"A": 1, "H": 1}, "events": '
                                                      '[[0.31, "A", "authorize"], [0.32, "H", "no"], [0.81, "A", "authorize"]], "seconds": 4.0}\n', "")
        lis = hs._listen("rmf_sim", "tb3", 4)
        assert lis["ok"] and lis["authorize"] == 2 and lis["no"] == 1 and lis["publishers"] == {"A": 1, "H": 1}, lis
        assert lis["timeline"][1] == (0.32, "H", "no") and lis["noise"] == ["some warning"], lis
        _docker_common.ros2_exec = lambda c, cmd, t: (True, '{"error": "NO_MSGS", "detail": "x"}\n', "")
        assert "fih_rmf_msgs" in hs._listen("rmf_sim", "tb3", 4)["error"]
        assert "python3 -c" in hs._listen_command("tb3", 4) and " tb3 4 " in hs._listen_command("tb3", 4)
    finally:
        _docker_common.ros2_exec = old


def t_handshake_lost_fin():
    """完成訊號遺失：status 判斷出來（到站、閒置、工作項還在等），fin 不帶 task_id 補發後確認工作包往下走"""
    with Sim(robots=[ROBOTS3[0], dict(ROBOTS3[1], behavior="lost_fin_once"), ROBOTS3[2]], packages=[pkg("WP_L2", "tb2", "a3", "a7")]) as sim:
        sim.wait_for(lambda st: any(e["kind"] == "fin_suppressed" for e in st["log"]), 15, "tb2 到 a3、完成訊號遺失")
        time.sleep(1)
        out = sim.run("rmf_handshake_cmd.py", "status", "tb2")
        assert "完成訊號多半遺失了" in first_line(out) and "rmf_handshake fin tb2" in out, out
        out = sim.run("rmf_handshake_cmd.py", "status", "WP_L2")
        assert first_line(out).startswith("[PASS] WP_L2 → tb2") and "完成訊號多半遺失了" in out, out
        out = sim.run("rmf_handshake_cmd.py", "fin", "tb2")
        assert first_line(out).startswith("[PASS] 已經由 manual_trigger 補發 /tb2/task_exec_fin") and "快照確認：工作包 WP_L2" in out, out
        assert sim.log("task_exec_fin", robot="tb2", source="manual_trigger")
        sim.wait_for(lambda st: st["packages"]["WP_L2"]["status"] == "COMPLETED", 20, "WP_L2 跑完")
        # 機器人還在 running 時不補發
        out = sim.run("workpackage_send_cmd.py", "WP_M", "a8", "--amr", "tb1")
        assert first_line(out).startswith("[PASS]"), out
        sim.wait_for(lambda st: st["snapshot"]["robots"]["tb1"]["real_state"] == "running", 10, "tb1 出發")
        assert_error(sim.run("rmf_handshake_cmd.py", "fin", "tb1"), "還在執行", "沒有送出")


def t_mock_server_launcher():
    """mock_server.py：啟動 rmf_sim（--no-ros，只綁 127.0.0.1），/api/stations 回節點 id"""
    web, trig = free_port(), free_port()
    p = subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "mock_server.py"), "--port", str(web), "--trigger-port", str(trig)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 10
        while True:
            try:
                data = http_json(f"http://127.0.0.1:{web}/api/stations")
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.2)
        assert data["stations"][2] == {"id": "2", "label": "a3"}, data
    finally:
        p.terminate()
        p.wait(5)


# ================================================================ 沙盒（ROS 2）
def _sandbox():
    if os.environ.get("RMF_TEST_SANDBOX") != "1":
        raise SkipTest("要 ROS 2 的情境：設 RMF_TEST_SANDBOX=1，並先 python evals/ops/dataset/sandbox/sandbox.py up（會 reset 沙盒的容器）")
    sys.path.insert(0, os.path.join(PROJECT, "evals", "ops", "dataset", "sandbox"))
    sys.path.insert(0, os.path.join(PROJECT, "evals", "ops", "dataset"))
    import sandbox
    if sandbox.sd("info", timeout=20).returncode != 0:
        raise SkipTest(f"沙盒 daemon（{sandbox.DOCKER_HOST}）沒有在跑：先 sandbox.py up")
    return sandbox


def t_sandbox_ros2():
    """沙盒（ROS 2）：--ros2 發布 fih_rmf_msgs/WorkPackage、status 在容器裡聽到交握（回 no）、guess 的容器不設成目標"""
    sandbox = _sandbox()
    import scenarios
    sandbox.reset(scenarios.BY_ID["hs_busy_diag"]["world"])
    urls = sandbox.urls()
    env = {"RMF_WEB_CONSOLE_URL": urls["web_console"], "RMF_MANUAL_TRIGGER_URL": urls["manual_trigger"], "DOCKER_HOST": sandbox.DOCKER_HOST,
           "TARGET_CONTAINER": ""}
    code, out = run_script("workpackage_send_cmd.py", "WP_R", "a3", "--amr", "tb1", "--ros2", "rmf_sim", env=env, timeout=120)
    assert first_line(out).startswith("[PASS] work package「WP_R」已直接發布到 /incoming_work_packages") and "orchestrtor 已收到" in first_line(out), out
    st = sandbox.sim_state()
    assert [e for e in st["log"] if e["kind"] == "package_received" and e.get("package_id") == "WP_R" and e.get("source") == "ros2"], "要經 ROS topic 收到"
    code, out = run_script("workpackage_send_cmd.py", "WP_H", "a7", "--amr", "tb2", env=env, timeout=120)     # 走 web_console（ROS 模式）
    assert first_line(out).startswith("[PASS] work package「WP_H」已送出") and "orchestrtor 已收到" in first_line(out), out
    code, out = run_script("workpackage_send_cmd.py", "WP_R2", "a8", "--amr", "tb1", "--ros2", "rmf_sim", "--no-check",
                           "--url", "http://127.0.0.1:9", env=env, timeout=180)                              # web_console 連不上
    assert first_line(out).startswith("[PASS] work package「WP_R2」已直接發布") and "未核對拓譜圖" in out and "沒有核對 --amr" in out, out
    st = sandbox.sim_state()
    assert [e for e in st["log"] if e["kind"] == "package_received" and e.get("package_id") == "WP_R2" and e.get("source") == "ros2"], out
    code, out = run_script("rmf_handshake_cmd.py", "status", "WP_C3", "--container", "rmf_sim", "--seconds", "12", env=env, timeout=120)
    assert first_line(out).startswith("[PASS] WP_C3 → tb3 的交握狀況："), out
    assert "對授權一直回 no" in out and "/tb3/handshake_states：yes 0、no " in out and "[TARGET_CONTAINER] rmf_sim" in out, out
    code, out = run_script("rmf_handshake_cmd.py", "status", "tb3", "--seconds", "12", env=env, timeout=120)
    assert "自動選的" in out and "[TARGET_CONTAINER]" not in out, out


def t_sandbox_status_stable():
    """沙盒（ROS 2）：交握 status 連續幾次的判斷都對——忙碌的機器人只會是「一直回 no」或「剛好在冷卻」（不會是沒有回應、看不到 distribute），
    沒回應的機器人是「沒有回應授權」而且 handshake_states 沒有發布者（2026-10-23 以前的聽法從 CLI 啟動就開始計時，忙碌的被判錯 8 次）"""
    sandbox = _sandbox()
    import scenarios
    urls = sandbox.urls()
    env = {"RMF_WEB_CONSOLE_URL": urls["web_console"], "RMF_MANUAL_TRIGGER_URL": urls["manual_trigger"], "DOCKER_HOST": sandbox.DOCKER_HOST,
           "TARGET_CONTAINER": ""}
    busy_ok = ("對授權一直回 no", "這幾秒剛好沒有授權（工作項在冷卻／等待）")
    for sid, rid, n, allowed in (("hs_busy_diag", "tb3", 4, busy_ok), ("hs_silent_diag", "tb4", 2, ("沒有回應授權",))):
        world = scenarios.BY_ID[sid]["world"]
        sandbox.reset(world)
        time.sleep(world.get("wait", 0))
        verdicts = []
        for _ in range(n):
            code, out = run_script("rmf_handshake_cmd.py", "status", rid, env=env, timeout=120)
            head = first_line(out)
            assert head.startswith(f"[PASS] {rid} 的交握狀況："), out[:600]
            verdict = head.split("：", 1)[1]
            verdicts.append(verdict)
            assert verdict.split("；")[0] in allowed, f"{sid}：{verdict}\n{out[:1200]}"
            if rid == "tb4":
                assert f"graph 上沒有任何 /{rid}/handshake_states 的發布者" in out, out[:1200]
            time.sleep(3)
        print(f"     {sid}：{'｜'.join(verdicts)}")
