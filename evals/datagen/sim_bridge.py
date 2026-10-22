"""fih_amr_bridge 的模擬（domain_bridge_node.py：一個 process 兩個 rclpy Context，本地 domain ↔ 對外 domain 依白名單單向轉送序列化的
位元組），照目錄：
- 只有本地那一邊的節點寫 /rosout（名稱 tb1.bridge_local_node）；對外那一邊 enable_rosout=False。錄製在機器人的本地 domain：
  看得到 bridge 的 Log，與「對外 → 本地」轉進來的 Topic（發布者是 bridge 自己）。
- 啟動（0.3 秒內）：.env、白名單、三個設定值、（設定有問題時的 WARN）、每條路由一行、最後「Bridge 啟動：…」。
- 每 5 秒稽核一次兩邊的 graph（第一次在啟動後約 5 秒）：expect_publisher 的來源沒有 publisher、接收端有別的 publisher（同一台機器人
  跑了兩個 bridge）→ WARN，只在狀態改變時印；恢復 → INFO「已恢復：…」。
- 停止（SIGINT／SIGTERM，或任一邊的 executor 結束）：INFO「Bridge 停止，轉送則數：…」。
- Isaac Sim 的設定（bridge_isaacsim.yaml，start_sim.sh 選的）多 8 條路由：/clock、/odom、/scan、/scan_b、/imu、/joint_states_in、
  /isaac/initialpose 從對外轉進本地（/cmd_vel 從本地轉出去）。Isaac 沒開時，5 個 expect_publisher 的來源各一則 WARN；開了之後這些
  Topic 才在本地出現（發布者是 bridge，錄製工具中途才訂閱到）。Isaac 的 header.stamp 與 /clock 是模擬時間。"""
import math

from sim_core import INF, Alive, Motion, Signal, quat_yaw, twist

PKG = "/workspaces/amr_base/install/fih_amr_bridge"
SRC = f"{PKG}/lib/python3.12/site-packages/fih_amr_bridge/domain_bridge_node.py"
NODE = "tb1.bridge_local_node"
ENV = "/workspaces/amr_base/.env"
QOS = "reliable/volatile/keep_last(10)"
# 預設的白名單（bridge.yaml）：(本地 Topic, 對外 Topic, 型別, 方向)
ROUTES = [("/tb1/robot_state", "/tb1/robot_state", "fih_rmf_msgs/msg/RobotState", "out"),
          ("/tb1/handshake_states", "/tb1/handshake_states", "fih_rmf_msgs/msg/HandshakeState", "out"),
          ("/tb1/task_exec_fin", "/tb1/task_exec_fin", "fih_rmf_msgs/msg/TaskExecutionFinished", "out"),
          ("/tb1/allocator_status", "/tb1/allocator_status", "fih_rmf_msgs/msg/AllocatorCommand", "in")]
# Isaac Sim 的白名單（bridge_isaacsim.yaml）多的 8 條：(本地 Topic, 對外 Topic, 型別, 方向, expect_publisher, Hz)
ISAAC = [("/clock", "/tb1/clock", "rosgraph_msgs/msg/Clock", "in", True, 60),
         ("/odom", "/tb1/odom", "nav_msgs/msg/Odometry", "in", True, 30),
         ("/scan", "/tb1/scan", "sensor_msgs/msg/LaserScan", "in", True, 10),
         ("/scan_b", "/tb1/scan_b", "sensor_msgs/msg/LaserScan", "in", False, 10),
         ("/imu", "/tb1/imu", "sensor_msgs/msg/Imu", "in", False, 60),
         ("/joint_states_in", "/tb1/joint_states_in", "sensor_msgs/msg/JointState", "in", True, 30),
         ("/cmd_vel", "/tb1/cmd_vel", "geometry_msgs/msg/Twist", "out", False, None),
         ("/isaac/initialpose", "/tb1/initialpose", "geometry_msgs/msg/PoseWithCovarianceStamped", "in", True, None)]
AUDIT = 5.0


class Bridge:
    """情境：start(t, warn_env)（錄製中途啟動，可以帶 ROBOT_NS 跟 .env 不同的 WARN）、duplicate(t, d)（同一台機器人又啟動一個 bridge，
    d 秒後停掉）、isaac_up(t)／isaac_down(t)（Isaac Sim 的設定：模擬器中途才開／中途關掉）、stop(t)。
    isaac=True：用 Isaac Sim 的白名單；cmd＝(v, w) 的 Signal（Isaac 裡的機器人照這個速度動，給 /odom、/imu、/joint_states_in）。"""

    def __init__(self, sim, isaac=False, cmd=None, scan_points=180):
        self.sim, self.rng = sim, sim.rng
        self.isaac = isaac
        self.v, self.w = cmd if cmd else (Signal(0.0), Signal(0.0))
        self.n_scan = scan_points
        self.started = None             # None＝錄製開始之前就在跑
        self.warn_env = False
        self.stopped = None
        self.dups = []                  # (t, d)
        self.sim_up = Alive(0.0, INF) if isaac else Alive(0.0, 0.0)   # Isaac Sim 有在跑的時段
        self.sim_events = []            # ("up"|"down", t)

    # ---- 情境
    def start(self, t, warn_env=False):
        self.started, self.warn_env = t, warn_env

    def stop(self, t):
        self.stopped = t

    def duplicate(self, t, d):
        self.dups.append((t, d))

    def isaac_up(self, t):
        self.sim_up = Alive(t, INF)
        self.sim_events.append(("up", t))

    def isaac_down(self, t):
        self.sim_up.stop(t)
        self.sim_events.append(("down", t))

    # ---- 模擬
    def _routes(self):
        rows = [(lo, gl, ty, d) for lo, gl, ty, d in ROUTES]
        if self.isaac:
            rows += [(lo, gl, ty, d) for lo, gl, ty, d, _, _ in ISAAC]
        return rows

    def _startup_logs(self, t, warn_env):
        sim = self.sim
        yaml = "bridge_isaacsim.yaml" if self.isaac else "bridge.yaml"
        lines = [("INFO", f".env：{ENV}（由套件安裝位置 {PKG} 推得）", 161),
                 ("INFO", f"白名單：{PKG}/share/fih_amr_bridge/config/{yaml}", 161)]
        for key, val, name in (("local_domain_id", 1, "LOCAL_DOMAIN_ID"), ("global_domain_id", 98, "GLOBAL_DOMAIN_ID"), ("robot_ns", "tb1", "ROBOT_NS")):
            lines.append(("INFO", f"  {key} = {val}（{ENV} 的 {name}）", 161))
        if warn_env:
            lines.append(("WARN", "環境變數 ROBOT_NS=tb2 跟 .env 的 tb1 不同，已忽略、以 .env 為準；同一個環境裡不經 start_sim.sh 啟動的 amr_base_sw 節點"
                                  "（TaskAgent、RobotStateBroadcaster）會用環境變數組本地 topic，跟 bridge 對不上。要同步請 recreate 容器，或 unset／重新 export", 163))
        for lo, gl, ty, d in self._routes():
            if d == "out":
                lines.append(("INFO", f"  [本地→對外] {lo} (domain 1) → {gl} (domain 98)  {ty}  {QOS}", 167))
            else:
                qos = f"sub best_effort/volatile/keep_last(10) / pub {QOS}" if self.isaac and lo != "/tb1/allocator_status" else QOS
                lines.append(("INFO", f"  [對外→本地] {gl} (domain 98) → {lo} (domain 1)  {ty}  {qos}", 167))
        n = len(self._routes())
        lines.append(("INFO", f"Bridge 啟動：robot_ns=tb1，本地 domain 1 ↔ 對外 domain 98，白名單 {n} 個 topic", 172))
        step = 0.25 / len(lines)
        for i, (lvl, msg, line) in enumerate(lines):
            sim.log(t + i * step, lvl, NODE, msg, (SRC, "_log_startup", line))

    def _audits(self, start, end):
        """這個 bridge 的稽核時間：啟動後約 5 秒第一次，之後每 5 秒（錄製開始前就在跑的：相位隨機）。"""
        t = start + AUDIT + self.rng.uniform(-0.05, 0.05) if start is not None else self.rng.uniform(0.2, AUDIT)
        out = []
        while t < min(end, self.sim.duration):
            out.append(t)
            t += AUDIT * (1 + self.rng.gauss(0, 0.001))
        return out

    def build(self):
        sim, rng, D = self.sim, self.rng, self.sim.duration
        end = self.stopped if self.stopped is not None else INF
        if self.started is not None:
            self._startup_logs(self.started, self.warn_env)
        audits = self._audits(self.started, end)
        # Isaac 的 expect_publisher 來源：稽核時看 Isaac 有沒有在跑，狀態改變才印
        if self.isaac:
            missing = None if self.started is not None else (not self.sim_up.contains(0.0))
            for a in audits:
                now = not self.sim_up.contains(a)
                if now != missing:
                    for k, (lo, gl, ty, d, expect, _) in enumerate(e for e in ISAAC if e[4]):
                        if now:
                            sim.log(a + k * 0.0004, "WARN", NODE, f"對外 domain 的 {gl} 沒有 publisher（白名單標記 expect_publisher）；"
                                    "請確認發布端已啟動、namespace 與 domain 正確", (SRC, "_report", 224))
                        elif missing is not None:
                            sim.log(a + k * 0.0004, "INFO", NODE, f"已恢復：{gl}（對外 domain）", (SRC, "_report", 226))
                    missing = now
        # 同一台機器人跑了兩個 bridge：兩個都在稽核時發現接收端有 2 個 publisher（兩個 bridge 的 Log 名稱一樣）
        for t, d in self.dups:
            self._startup_logs(t, False)
            second = self._audits(t, t + d)
            first = [a for a in audits if t < a]
            for who, ts in (("first", first), ("second", second)):
                warned = False
                for a in ts:
                    dup = a < t + d
                    if dup and not warned:
                        for k, (lo, gl, ty, dr) in enumerate(ROUTES):
                            side, topic = ("對外", gl) if dr == "out" else ("本地", lo)
                            pub = "/tb1/bridge_central_node" if dr == "out" else "/tb1/bridge_local_node"
                            sim.log(a + k * 0.0004, "WARN", NODE, f"{side} domain 的 {topic} 有 2 個 publisher ['{pub}', '{pub}']（預期只有本 bridge）；"
                                    "可能是同一台機器人跑了兩個 bridge，或本地節點跑在對外 domain，訂閱端會收到重複訊息", (SRC, "_report", 224))
                        warned = True
                    elif not dup and warned and who == "first":
                        for k, (lo, gl, ty, dr) in enumerate(ROUTES):
                            side, topic = ("對外", gl) if dr == "out" else ("本地", lo)
                            sim.log(a + k * 0.0004, "INFO", NODE, f"已恢復：{topic}（{side} domain）", (SRC, "_report", 226))
                        warned = False
                        break
            n = int(d * 10 * (1 + rng.gauss(0, 0.01)))
            sim.log(t + d, "INFO", NODE, f"Bridge 停止，轉送則數：/tb1/robot_state={n}, /tb1/handshake_states=0, /tb1/task_exec_fin=0, "
                                         "/tb1/allocator_status=0", (SRC, "destroy", 106))
        if self.stopped is not None and self.stopped < D:
            since = self.stopped - (self.started if self.started is not None else -rng.uniform(60, 900))
            sim.log(self.stopped, "INFO", NODE, f"Bridge 停止，轉送則數：/tb1/robot_state={int(since * 10)}, /tb1/handshake_states={rng.choice([0, 3])}, "
                                                f"/tb1/task_exec_fin={rng.choice([0, 1, 2])}, /tb1/allocator_status={rng.choice([0, 5])}", (SRC, "destroy", 106))
        if self.isaac:
            self._isaac_topics(end)
        self._expect()
        return self

    def _isaac_topics(self, end):
        """Isaac Sim 經 bridge 轉進本地的 Topic：Isaac 有在跑、bridge 也在跑的時候才有。"""
        sim, rng = self.sim, self.rng
        on = Alive()
        on.iv = []
        for a, b in self.sim_up.iv:   # Isaac 有在跑、bridge 也在跑：Isaac 開了之後很快就有（錄製開始前就在跑的＝一開始就有）
            a = a + 0.05 if a > 0 else 0.0
            if self.started is not None:
                a = max(a, self.started + 0.3)
            if a < min(b, end):
                on.iv.append((a, min(b, end)))
        t_sim0 = on.iv[0][0] if on.iv else 0.0
        motion = Motion(self.v, self.w)
        n = self.n_scan

        def stamp(t):   # Isaac 的模擬時間（從模擬開始算）
            st = max(0.0, (t - t_sim0) * 0.98 + 12.5)
            return {"sec": int(st), "nanosec": int((st - int(st)) * 1e9)}

        def hdr(t, frame):
            return {"stamp": stamp(t), "frame_id": frame}

        def scan(frame, phase):
            def build(t):
                x, y, yaw, v, w = motion.at(t)
                return {"header": hdr(t, frame), "angle_min": -math.pi, "angle_max": math.pi, "angle_increment": 2 * math.pi / n,
                        "time_increment": 0.0, "scan_time": 0.1, "range_min": 0.1, "range_max": 25.0,
                        "ranges": [round(3.0 + 1.2 * math.sin(i * 0.07 + phase + 0.3 * x) + rng.gauss(0, 0.01), 3) for i in range(n)],
                        "intensities": []}
            return build

        def odom(t):
            x, y, yaw, v, w = motion.at(t)
            return {"header": hdr(t, "odom"), "child_frame_id": "base_link",
                    "pose": {"pose": {"position": {"x": x, "y": y, "z": 0.0}, "orientation": quat_yaw(yaw)}, "covariance": [0.0] * 36},
                    "twist": {"twist": twist(round(v, 4), round(w, 4)), "covariance": [0.0] * 36}}

        def imu(t):
            x, y, yaw, v, w = motion.at(t)
            return {"header": hdr(t, "imu_link"), "orientation": quat_yaw(yaw), "orientation_covariance": [0.0] * 9,
                    "angular_velocity": {"x": 0.0, "y": 0.0, "z": round(w + rng.gauss(0, 0.002), 5)}, "angular_velocity_covariance": [0.0] * 9,
                    "linear_acceleration": {"x": round(rng.gauss(0, 0.02), 5), "y": round(rng.gauss(0, 0.02), 5), "z": round(9.81 + rng.gauss(0, 0.02), 5)},
                    "linear_acceleration_covariance": [0.0] * 9}

        def joints(t):
            x, y, yaw, v, w = motion.at(t)
            r, b = 0.0825, 0.46
            return {"header": hdr(t, ""), "name": ["left_wheel_joint", "right_wheel_joint"],
                    "position": [round((x - yaw * b / 2) / r, 4), round((x + yaw * b / 2) / r, 4)],
                    "velocity": [round((v - w * b / 2) / r, 4), round((v + w * b / 2) / r, 4)], "effort": []}

        builds = {"/clock": lambda t: {"clock": stamp(t)}, "/odom": odom, "/scan": scan("lidar_front", 0.0), "/scan_b": scan("lidar_back", 1.3),
                  "/imu": imu, "/joint_states_in": joints}
        for lo, gl, ty, d, expect, hz in ISAAC:
            if lo in builds:
                s = sim.periodic(lo, ty, hz, builds[lo], jitter=0.03, alive=Alive())
                s.alive.iv = list(on.iv)
                # 本地的發布者是 bridge（啟動時就建立每條路由的 publisher）：bridge 錄製前就在跑，錄製工具一開始就訂閱了，Isaac 中途才開
                # 也不會少錄；bridge 中途才啟動的，要等錄製工具發現了才訂閱
                if self.started is not None and self.started > 0.5:
                    s.appears = self.started + 0.2
        if on.iv:
            ip = sim.events("/isaac/initialpose", "geometry_msgs/msg/PoseWithCovarianceStamped")
            ip.latched = True
            t = on.iv[0][0] + 0.8
            ip.publish(t, {"header": hdr(t, "map"), "pose": {"pose": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": quat_yaw(0.0)},
                                                             "covariance": [0.0] * 36}})

    def _expect(self):
        sim = self.sim
        mine = sorted((t1, level, msg) for t1, level, node, msg, _ in sim.logs if node == NODE)
        if self.warn_env and self.started is not None:
            for t1, level, msg in mine:
                if level == "WARN" and "跟 .env 的" in msg:
                    sim.expect_log(t1, "WARN", "跟 .env 的", key=True, what="bridge 啟動：ROBOT_NS 跟 .env 不同")
                    break
        for t, d in self.dups:   # Log 去重時數字會被當成同一句（「有 2 個」），關鍵字用不含數字的部分
            for t1, level, msg in mine:
                if level == "WARN" and "預期只有本 bridge" in msg and t <= t1 <= t + d + AUDIT + 1:
                    sim.expect_log(t1, "WARN", "預期只有本 bridge", key=True, what="同一台機器人跑了兩個 bridge")
                    break
        if self.isaac:
            for t1, level, msg in mine:
                if level == "WARN" and "沒有 publisher" in msg:
                    sim.expect_log(t1, "WARN", "沒有 publisher", key=True, what="Isaac Sim 沒有在跑（expect_publisher 的來源沒有 publisher）")
            for kind, t in self.sim_events:
                for lo, gl, ty, d, expect, hz in ISAAC:
                    if hz and lo != "/clock":   # /clock 是 ROS 2 框架的 Topic，分析程式不列事件
                        if kind == "up":
                            sim.expect_start(lo, t, key=lo in ("/odom", "/scan"), what=f"Isaac Sim 開始：{lo}", tag=True)
                        else:
                            sim.expect_stop(lo, t, key=lo in ("/odom", "/scan"), what=f"Isaac Sim 關掉：{lo}")
