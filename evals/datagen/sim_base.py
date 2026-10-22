"""amr_base_hw 的模擬（底盤控制、IMU、兩顆 SICK LiDAR、scan 合併、RF2O、EKF、robot_state_publisher），照目錄（源碼與文件）：
- base_controller_node 每 16 ms 一個迴圈：/cmd_state 一定發；FC17h 成功才發 /wheel_rpm、/driver_state、/hardware_alarm、/base_state、
  /wheel_odom。沒有 /cmd_vel 的 watchdog、狀態改變不印 Log；序列埠壞了每個迴圈印一則 WARN（不節流）。
- SICK 的 Log 不進 /rosout（非節點的 logger）：LiDAR 斷線在數據裡只看得到 Topic 停了。
- /scan_merged 要兩顆 LiDAR 都在；任一顆停，/scan_merged、/scan、/rf2o_odom 一起停。
- EKF 的 /odom 輸入停了也照樣 30 Hz（預測）。"""
import math

from sim_core import Alive, Motion, Signal, header, quat_yaw, twist

PKG = "/workspaces/amr_base/install"
BASE_FILE = f"{PKG}/base_motor_controller/lib/python3.12/site-packages/base_motor_controller_py/nodes/base_controller_node.py"
TDK_FILE = f"{PKG}/tdk_ros2_imu/lib/python3.12/site-packages/tdk_ros2_imu/tdk_imu_node.py"
MERGER_FILE = f"{PKG}/hw_bringup/lib/python3.12/site-packages/hw_bringup/laser_scan_merger.py"
ALARMS = {
    2: "alarm=2 [過負載] 施加負載超過額定負載 5 秒以上，或超過轉矩限制 X 秒以上。 解決：降低負載，確認轉矩限制設定。",
    5: "alarm=5 [低電壓] 電源輸入電壓低於驅動器可接受下限。 解決：確認電源供應正常，無壓降問題。",
    6: "alarm=6 [驅動器過溫] 驅動器溫度高於可承受上限。 解決：改善散熱，降低負載或環境溫度。",
    12: "alarm=12 [過速度] 馬達轉速超過所設定的上限。 解決：降低指令轉速，確認速度上限參數設定。",
    21: "alarm=21 [通訊指令錯誤] RS232 或 RS485 通訊逾時。 解決：確認通訊連線與 baudrate 設定，檢查接線。",
}
JOINTS = ["L_WHEEL_JOINT", "R_WHEEL_JOINT", "TORSO_J1", "TORSO_J2", "L_ARM_J1", "L_ARM_J2", "L_ARM_J3", "R_ARM_J1", "R_ARM_J2",
          "R_ARM_J3", "HEAD_J1", "HEAD_J2"]
WHEEL_R, WHEEL_BASE, GEAR = 0.08, 0.555, 20


def motor_rpm(v, w):
    """/wheel_rpm 的 cmd：輪速 → 馬達 rpm（×20、四捨五入、未滿 60 拉到 60、右輪乘 -1）。"""
    out = []
    for side in (1, -1):   # 右、左
        wheel = (v + side * w * WHEEL_BASE / 2) / WHEEL_R * 60 / (2 * math.pi)
        rpm = round(wheel * GEAR)
        if rpm and abs(rpm) < 60:
            rpm = 60 if rpm > 0 else -60
        out.append(max(-4800, min(4800, rpm)))
    return float(-out[0]), float(out[1])


class Base:
    """情境用的時間線：teleop()、alarm()、alarm_reset()、usb_unplug()、power_cut()、lidar_unplug()、imu_unplug()、
    imu_checksum()、push_mode()、bump()、boot()。cmd：GATE 輸出的速度（diagnostics 也在時），沒有就自己帶 teleop 的 /cmd_vel。"""

    def __init__(self, sim, cmd=None, scan_points=270):
        self.sim, self.rng = sim, sim.rng
        self.own_cmd = cmd is None
        self.v, self.w = cmd if cmd else (Signal(0.0), Signal(0.0))
        self.n_scan = scan_points
        self.serial = Alive()
        self.loop_alive = Alive()
        self.slow = []              # (t0, t1)：序列埠逾時，每個迴圈 0.1 秒
        self.alarm = Signal(None)   # ("R"/"L", code)
        self.push = Signal(False)
        self.lidar = {"front": Alive(), "back": Alive()}
        self.imu = Alive()
        self.bumps = []
        self.checksum = []
        self.boot_t = None
        self.flood = []             # (t0, t1, error text)
        self.resets = []
        self.teleop_on = False

    # ---- 情境
    def boot(self, t):
        self.boot_t = t
        for a in (self.serial, self.loop_alive, self.imu, self.lidar["front"], self.lidar["back"]):
            a.iv = [(t + self.rng.uniform(0.3, 0.8), float("inf"))]
        for side in ("front", "back"):
            self.lidar[side].iv = [(t + self.rng.uniform(1.5, 4.0), float("inf"))]

    def teleop(self, t0, t1, v, w=0.0):
        self.teleop_on = True
        self.v.set(t0, v)
        self.w.set(t0, w)
        self.v.set(t1, 0.0)
        self.w.set(t1, 0.0)

    def alarm_on(self, t, side, code, clear_at=None):
        self.alarm.set(t, (side, code))
        if clear_at is not None:
            self.alarm.set(clear_at, None)

    def alarm_reset(self, t):
        self.resets.append(t)
        self.alarm.set(t + 0.33, None)

    def usb_unplug(self, t):
        self.serial.stop(t)
        self.flood.append((t, float("inf"), "(5, 'Input/output error')", 0.016))

    def power_cut(self, t, d, alarm_after=21):
        self.serial.gap(t, d)
        self.slow.append((t, t + d))
        self.flood.append((t, t + d, "回應長度不足: expected 37, got 0 raw=", 0.105))
        if alarm_after:
            self.alarm.set(t + d + 0.05, ("R", alarm_after))

    def lidar_unplug(self, side, t, d=None):
        if d is None:
            self.lidar[side].stop(t)
        else:
            self.lidar[side].gap(t, d)

    def imu_unplug(self, t):
        self.imu.stop(t)
        self.sim.log(t + 0.004, "FATAL", "tdk_imu", "IMU serial connection failed: [Errno 5] Input/output error", (TDK_FILE, "_poll_serial", 97))

    def imu_checksum(self, t0, t1):
        n, t = 0, t0
        while t < t1:
            n += self.rng.randint(1, 6)
            self.sim.log(t, "WARN", "tdk_imu", f"Discarded an IMU packet with an invalid checksum (total={n})", (TDK_FILE, "_warn_checksum_error", 113))
            t += 5.0 + self.rng.uniform(0, 0.02)

    def push_mode(self, t0, t1):
        self.push.set(t0, True)
        self.push.set(t1, False)
        self.sim.log(t1 + 0.002, "INFO", "base_controller_node", "cmd_vel unlocked after PUSH by zero command.", (BASE_FILE, "cmd_callback", 320))
        self.sim.log(t1 + 0.018, "INFO", "base_controller_node", "Motors re-engaged (FREE=OFF, SERVO-EN=ON) after push mode.",
                     (BASE_FILE, "control_loop", 558))

    def bump(self, t, g=3.2):
        self.bumps.append((t, g))

    # ---- 模擬
    def build(self):
        sim, rng, D = self.sim, self.rng, self.sim.duration
        state = Signal("idle")
        alarm_eff = self.alarm
        moving_v, moving_w = Signal(0.0), Signal(0.0)   # 輪子實際的指令（故障、推車時是 0）
        names = ["/cmd_state", "/wheel_rpm", "/driver_state", "/hardware_alarm", "/base_state", "/wheel_odom"]
        types = ["std_msgs/msg/String", "base_motor_controller/msg/WheelRpm", "std_msgs/msg/String", "std_msgs/msg/String",
                 "std_msgs/msg/String", "nav_msgs/msg/Odometry"]
        st = {n: sim.events(n, ty) for n, ty in zip(names, types)}
        for s in st.values():
            s.rate = 62.5
        if self.own_cmd and self.teleop_on:
            cmd = sim.events("/cmd_vel", "geometry_msgs/msg/Twist")
            cmd.rate = 20
            t = rng.uniform(0, 0.05)
            while t < D:
                cmd.publish(t, twist(self.v.at(t), self.w.at(t)))
                t += 0.05 * (1 + rng.gauss(0, 0.01))
        # 控制迴圈：62.5 Hz（序列埠逾時的那段每圈 0.1 秒）
        loops, t = [], (self.boot_t + 0.77) if self.boot_t is not None else rng.uniform(0, 0.016)
        while t < D:
            loops.append(t)
            slow = any(a <= t < b for a, b in self.slow)
            t += (0.105 if slow else 0.016) * (1 + rng.gauss(0, 0.01))
        motion = Motion(moving_v, moving_w, acc=1.2, wacc=2.5)
        prev_state = None
        for t in loops:
            if not self.loop_alive.contains(t):
                continue
            v, w = self.v.at(t), self.w.at(t)
            al = alarm_eff.at(t - 0.016)
            if al is not None:
                s_now = "fault"
            elif self.push.at(t):
                s_now = "push"
            elif abs(v) > 1e-6 or abs(w) > 1e-6:
                s_now = "run"
            else:
                s_now = "idle"
            if s_now != prev_state:
                state.set(t, s_now)
                prev_state = s_now
                go = s_now == "run"
                moving_v.set(t, v if go else 0.0)
                moving_w.set(t, w if go else 0.0)
            elif s_now == "run":
                moving_v.set(t, v)
                moving_w.set(t, w)
            label = "stop" if s_now in ("push",) or (abs(v) < 1e-6 and abs(w) < 1e-6) else (
                "forward" if v > 0 and abs(w) < 1e-6 else "backward" if v < 0 and abs(w) < 1e-6 else "spin" if abs(v) < 1e-6 else "turning")
            st["/cmd_state"].publish(t, {"data": label})
            if not self.serial.contains(t):
                continue
            x, y, yaw, mv, mw = motion.at(t)
            cr, cl = motor_rpm(v, w) if s_now != "push" else (0.0, 0.0)
            ar, al_rpm = motor_rpm(mv, mw)
            ar, al_rpm = -ar, al_rpm
            if s_now == "push":
                ar, al_rpm = rng.uniform(300, 800), rng.uniform(300, 800)
            noise = (lambda: rng.gauss(0, 1.5)) if abs(mv) > 0.01 or abs(mw) > 0.01 else (lambda: 0.0)
            st["/wheel_rpm"].publish(t, {"header": header(sim, t, "base_link"), "cmd_right_rpm": cr, "cmd_left_rpm": cl,
                                         "actual_right_rpm": float(round(ar + noise())), "actual_left_rpm": float(round(al_rpm + noise()))})
            ds = {"idle": "R: STOP | L: STOP", "run": "R: RUN | L: RUN", "push": "R: FREE | L: FREE"}.get(s_now)
            alarm_now = alarm_eff.at(t)
            if s_now == "fault" or alarm_now is not None:
                side = (alarm_now or al)[0]
                ds = "R: FAULT | L: RUN" if side == "R" else "R: RUN | L: FAULT"
            st["/driver_state"].publish(t, {"data": ds})
            if alarm_now is None:
                ha = "has_alarm=false | R: no_alarm | L: no_alarm"
            else:
                side, code = alarm_now
                det = ALARMS.get(code, f"alarm={code} (unknown)")
                ha = f"has_alarm=true | R: {det} | L: no_alarm" if side == "R" else f"has_alarm=true | R: no_alarm | L: {det}"
            st["/hardware_alarm"].publish(t, {"data": ha})
            st["/base_state"].publish(t, {"data": s_now})
            st["/wheel_odom"].publish(t, {"header": header(sim, t, "odom"), "child_frame_id": "base_link",
                                          "pose": {"pose": {"position": {"x": x, "y": y, "z": 0.0}, "orientation": quat_yaw(yaw)}, "covariance": [0.0] * 36},
                                          "twist": {"twist": twist(round(mv, 4), round(mw, 4)), "covariance": [0.01] + [0.0] * 35}})
        # 序列埠壞掉：每個迴圈一則 WARN（不節流）
        for a, b, text, dt in self.flood:
            t = a
            while t < min(b, D):
                sim.log(t + 0.0005, "WARN", "base_controller_node", f"FC17h transceive failed: {text}", (BASE_FILE, "control_loop", 572))
                t += dt * (1 + rng.gauss(0, 0.02))
        for t in self.resets:
            sim.log(t + 0.33, "INFO", "base_controller_node", "alarm reset OK，狀態回到 IDLE", (BASE_FILE, "_handle_alarm_reset", 509))
        self._sensors(motion)
        self._startup_logs()
        self._expect(state)
        return self

    def _sensors(self, motion):
        sim, rng, D = self.sim, self.rng, self.sim.duration
        imu = sim.events("/imu_data", "sensor_msgs/msg/Imu")
        imu.rate = 100
        t = rng.uniform(0, 0.01) if self.boot_t is None else self.boot_t + 0.45
        bumps = sorted(self.bumps)
        while t < D:
            if self.imu.contains(t):
                x, y, yaw, v, w = motion.at(t)
                ax = rng.gauss(0, 0.04)
                for tb, g in bumps:
                    if 0 <= t - tb < 0.0101:
                        ax = g * 9.80665
                imu.publish(t, {"header": header(sim, t, "L_BASE_IMU"), "orientation": quat_yaw(yaw), "orientation_covariance": [0.0] * 9,
                                "angular_velocity": {"x": rng.gauss(0, 0.004), "y": rng.gauss(0, 0.004), "z": w + rng.gauss(0, 0.005)},
                                "angular_velocity_covariance": [0.0] * 9,
                                "linear_acceleration": {"x": ax, "y": rng.gauss(0, 0.04), "z": 9.80665 + rng.gauss(0, 0.03)},
                                "linear_acceleration_covariance": [0.0] * 9})
            t += 0.01 * (1 + rng.gauss(0, 0.02))
        # LiDAR（15 Hz，兩顆的相位差固定在 20 ms 以內才合得起來）
        n = self.n_scan
        inc = 4.82 / (n - 1)
        scans = {}
        for side, frame in (("front", "L_BASE_SCAN_F"), ("back", "L_BASE_SCAN_B")):
            s = sim.events(f"/sick/{side}/lidar", "sensor_msgs/msg/LaserScan")
            s.rate = 15
            scans[side] = s
            t, ts = rng.uniform(0, 0.066) if side == "front" else None, []
            if side == "back":
                t = scans["front"].explicit[0][0] + rng.uniform(0.002, 0.012) if scans["front"].explicit else rng.uniform(0, 0.066)
            t0 = t
            k = 0
            while t0 + k / 15.0 < D:
                tt = t0 + k / 15.0 + rng.gauss(0, 0.0005)
                k += 1
                if 0 < tt < D and self.lidar[side].contains(tt):
                    s.publish(tt, self._scan(tt, frame, n, inc, side))
        merged = sim.events("/scan_merged", "sensor_msgs/msg/LaserScan")
        scan = sim.events("/scan", "sensor_msgs/msg/LaserScan")
        rf2o = sim.events("/rf2o_odom", "nav_msgs/msg/Odometry")
        for s in (merged, scan, rf2o):
            s.rate = 15
        back = [t for t, _ in scans["back"].explicit]
        import bisect
        nm = int(2 * math.pi / inc) + 1
        for t, _ in scans["front"].explicit:
            i = bisect.bisect_left(back, t - 0.02)
            if i < len(back) and abs(back[i] - t) <= 0.02:
                tm = max(t, back[i]) + 0.003
                body = self._scan(tm, "L_BASE_FOOTPRINT", nm, 2 * math.pi / (nm - 1), "merged", amin=-math.pi)
                body["intensities"] = []
                merged.publish(tm, body)
                scan.publish(tm + 0.001, body)
                x, y, yaw, v, w = motion.at(tm)
                rf2o.publish(tm + rng.uniform(0.002, 0.05), {"header": header(sim, tm, "odom"), "child_frame_id": "L_BASE_FOOTPRINT",
                                                              "pose": {"pose": {"position": {"x": x + rng.gauss(0, 0.01), "y": y + rng.gauss(0, 0.01), "z": 0.0},
                                                                                "orientation": quat_yaw(yaw)}, "covariance": [0.25] + [0.0] * 6 + [0.25] + [0.0] * 28},
                                                              "twist": {"twist": twist(v + rng.gauss(0, 0.02), w + rng.gauss(0, 0.02)), "covariance": [0.0] * 36}})
        odom = sim.events("/odom", "nav_msgs/msg/Odometry")
        tf = sim.events("/tf", "tf2_msgs/msg/TFMessage")
        js = sim.events("/joint_states", "sensor_msgs/msg/JointState")
        diag = sim.streams.get("/diagnostics") or sim.events("/diagnostics", "diagnostic_msgs/msg/DiagnosticArray")
        odom.rate, js.rate = 30, 10
        start = (self.boot_t + 0.78) if self.boot_t is not None else rng.uniform(0, 0.033)
        t = start
        while t < D:
            x, y, yaw, v, w = motion.at(t)
            odom.publish(t, {"header": header(sim, t, "odom"), "child_frame_id": "L_BASE_FOOTPRINT",
                             "pose": {"pose": {"position": {"x": x, "y": y, "z": 0.0}, "orientation": quat_yaw(yaw)}, "covariance": [0.0] * 36},
                             "twist": {"twist": twist(round(v, 4), round(w, 4)), "covariance": [0.0] * 36}})
            tf.publish(t + 0.0002, {"transforms": [{"header": header(sim, t, "odom"), "child_frame_id": "L_BASE_FOOTPRINT",
                                                    "transform": {"translation": {"x": x, "y": y, "z": 0.0}, "rotation": quat_yaw(yaw)}}]})
            t += 1 / 30 * (1 + rng.gauss(0, 0.01))
        t = (self.boot_t + 0.5) if self.boot_t is not None else rng.uniform(0, 0.1)
        while t < D:
            js.publish(t, {"header": header(sim, t), "name": JOINTS, "position": [0.0] * len(JOINTS), "velocity": [], "effort": []})
            tf.publish(t + 0.0004, {"transforms": [{"header": header(sim, t, "base_link"), "child_frame_id": j,
                                                    "transform": {"translation": {"x": 0.0, "y": 0.0, "z": 0.1}, "rotation": quat_yaw(0.0)}}
                                                   for j in JOINTS]})
            t += 0.1 * (1 + rng.gauss(0, 0.005))
        t = (self.boot_t + 1.8) if self.boot_t is not None else rng.uniform(0, 1.0)
        sim.expect_background("/diagnostics", "EKF 診斷的 Events in window 是整數計數，每秒在 299／300 之間跳（分析程式照整數狀態量，列成狀態改變）")
        while t < D:
            hz = 30.0 + rng.gauss(0, 0.05)
            diag.publish(t, {"header": header(sim, t), "status": [
                {"level": 0, "name": "ekf_filter_node: odometry/filtered topic status", "message": "Desired frequency met", "hardware_id": "none",
                 "values": [{"key": "Events in window", "value": str(int(hz * 10))}, {"key": "Events since startup", "value": str(int(t * 30))},
                            {"key": "Duration of window (s)", "value": "10.000000"}, {"key": "Actual frequency (Hz)", "value": f"{hz:.6f}"},
                            {"key": "Minimum acceptable frequency (Hz)", "value": "25.200000"},
                            {"key": "Maximum acceptable frequency (Hz)", "value": "35.200000"}]},
                {"level": 0, "name": "ekf_filter_node: Filter diagnostic updater",
                 "message": "The robot_localization state estimation node appears to be functioning properly.", "hardware_id": "none", "values": []}]})
            t += 1.0 * (1 + rng.gauss(0, 0.002))

    def _scan(self, t, frame, n, inc, side, amin=-2.41):
        rng = self.rng
        ranges = []
        for i in range(n):
            a = amin + i * inc
            r = 2.5 + 1.2 * math.cos(3 * a + (0.4 if side == "back" else 0.0)) + 0.6 * math.sin(7 * a)
            if (i * 37 + int(t * 7)) % 97 == 0:
                ranges.append(float("inf"))
            else:
                ranges.append(round(max(0.06, r + rng.gauss(0, 0.012)), 4))
        finite = [r for r in ranges if r != float("inf")]
        return {"header": header(self.sim, t, frame), "angle_min": amin, "angle_max": amin + inc * (n - 1), "angle_increment": inc,
                "time_increment": (1 / 15) / n, "scan_time": 1 / 15 + rng.gauss(0, 0.0003), "range_min": max(0.05, min(finite) - 0.001),
                "range_max": max(finite) + 0.001, "ranges": ranges, "intensities": [] if side == "merged" else [float(100 + (i % 50)) for i in range(n)]}

    def _startup_logs(self):
        if self.boot_t is None:
            return
        sim, t = self.sim, self.boot_t
        L = [(0.40, "INFO", "tdk_imu", "Publishing /dev/imu at 115200 baud on /tdk/imu with frame_id=L_BASE_IMU", (TDK_FILE, "__init__", 77)),
             (0.40, "INFO", "laser_scan_merger", "Merging /sick/front/lidar and /sick/back/lidar into /scan_merged in L_BASE_FOOTPRINT with 0.020 s sync tolerance",
              (MERGER_FILE, "__init__", 95)),
             (0.45, "INFO", "base_controller_node", "SerialConfig: port=/dev/base_motor_controller, baud=230400", (BASE_FILE, "__init__", 104)),
             (0.75, "INFO", "base_controller_node", "Md2Transport opened and motion prepared.", (BASE_FILE, "__init__", 171)),
             (0.751, "INFO", "base_controller_node", "Default motion profile applied at startup.", (BASE_FILE, "__init__", 172)),
             (0.752, "INFO", "base_controller_node", "Loop timing CSV : /workspaces/amr_base/src/amr_base_hw/base_motor_controller/exp/"
              "base_motor_controller_odom_straight_exp/loop_timing_20261017_093012.csv", (BASE_FILE, "_init_csv_logger", 273)),
             (0.753, "INFO", "base_controller_node", "Events CSV      : /workspaces/amr_base/src/amr_base_hw/base_motor_controller/exp/"
              "base_motor_controller_odom_straight_exp/events_20261017_093012.csv", (BASE_FILE, "_init_csv_logger", 274)),
             (0.754, "INFO", "base_controller_node", "BaseControllerNode V3 started", (BASE_FILE, "__init__", 181))]
        for dt, lvl, node, msg, src in L:
            sim.log(t + dt, lvl, node, msg, src)

    def _expect(self, state):
        sim = self.sim
        for t, a, b in state.changes():
            if t > 0.05:
                sim.expect_value("/base_state", t, b, key=b == "fault", what=f"/base_state {a} → {b}")
        for t, a, b in self.alarm.changes():
            if b is not None:
                sim.expect_value("/hardware_alarm", t, "has_alarm=true", key=True, what=f"驅動器警報 {b}")
        ha = sim.streams["/hardware_alarm"].explicit
        sim.change_times["/hardware_alarm"] = [ha[i][0] for i in range(1, len(ha)) if ha[i][1]["data"] != ha[i - 1][1]["data"]]
        for a, b, text, dt in self.flood:
            sim.expect_log(a + 0.0005, "WARN", "FC17h transceive failed", key=True, what="序列埠通訊失敗")
            sim.expect_stop("/wheel_rpm", a, key=True, what="底盤的回授停止") if b == float("inf") else \
                sim.expect_gap("/wheel_rpm", a, b - a, key=True, what="底盤的回授中斷")
        for side, alive in self.lidar.items():
            for (a1, b1), (a2, _) in zip(alive.iv, alive.iv[1:]):
                for topic in (f"/sick/{side}/lidar", "/scan_merged", "/scan"):
                    sim.expect_gap(topic, b1, a2 - b1, key=topic.startswith("/sick"), what=f"{topic} 中斷")
            if alive.iv and alive.iv[-1][1] < sim.duration:
                sim.expect_stop(f"/sick/{side}/lidar", alive.iv[-1][1], key=True)
        if self.imu.iv and self.imu.iv[-1][1] < sim.duration:
            sim.expect_stop("/imu_data", self.imu.iv[-1][1], key=True, what="IMU 停止發布")
            sim.expect_log(self.imu.iv[-1][1] + 0.004, "FATAL", "IMU serial connection failed", key=True)
        if self.bumps:
            sim.expect_tags("/imu_data", has=("尖峰",))
        elif not (self.imu.iv and self.imu.iv[-1][1] < sim.duration):
            sim.expect_tags("/imu_data", not_=("尖峰", "訊息中斷"))
        if not self.flood:
            sim.expect_tags("/odom", not_=("訊息中斷", "尖峰"))
