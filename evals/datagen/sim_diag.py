"""diagnostics_package 的模擬（照 docs、源碼與 14 份實錄整理的目錄：aggregator 10 Hz、MON 每收到一則 /diagnostics_agg 發一則
/system/safety_command、GATE 20 Hz 的 /cmd_vel 與狀態改變時的 /system/safety_gate_status、BBX、LCM）。

情境只設定時間線（故障、指令、凍結、重啟、復位…），build() 依時間一步一步算出每一則訊息與 Log，跟真的節點一樣互相影響：
故障 → /diagnostics（元件的 producer）→ aggregator 的下一個 tick → MON 的反應（矩陣、閂鎖）→ GATE 的模式與 /cmd_vel。"""
from sim_core import INF, Alive, Signal, fmt_val, header, stamp, twist

MON_FILE = "/workspace/ws/src/diagnostics_package/src/system_health_monitor_node.cpp"
GATE_FILE = "/workspace/ws/install/diagnostics_package/lib/diagnostics_package/safety_motion_controller.py"
BBX_FILE = "/workspace/ws/src/diagnostics_package/src/blackbox_recorder_node.cpp"
LCM_FILE = "/workspace/ws/src/diagnostics_package/src/diagnostics_lifecycle_manager.cpp"
MON, GATE, BBX, LCM = "system_health_monitor", "safety_motion_controller", "blackbox_recorder", "diagnostics_lifecycle_manager"
PRIORITY = {"NONE": 0, "LIMIT_SPEED": 1, "SMOOTH_PAUSE": 2, "HARD_STOP": 3, "EMERGENCY_STOP": 4}
DEFAULT_REACTION = {1: "LIMIT_SPEED", 2: "SMOOTH_PAUSE", 3: "HARD_STOP"}
RULES = {   # config/fault_reaction_matrix.yaml：code → (min_level, reaction, params, description)
    0x04100101: (2, "HARD_STOP", {"max_decel": 1.5}, "LiDAR 數據中斷，視覺失明，採取硬煞停"),
    0x03402901: (1, "LIMIT_SPEED", {"speed_ratio": 0.5}, "馬達發熱，降速運轉保護硬體"),
    0x02100201: (2, "SMOOTH_PAUSE", {"retry_count": 3.0}, "視覺感測器異常，暫停並嘗試重新初始化"),
    0x03201502: (1, "LIMIT_SPEED", {"retry_count": 2.0}, "導航執行時間過長，限制速度以確保安全"),
    0x02302101: (1, "LIMIT_SPEED", {"speed_ratio": 0.2}, "輪速計數據異常，限制速度以確保安全"),
    0x01500000: (1, "LIMIT_SPEED", {"retry_count": 1.0}, "系統未定義/通用異常"),
}
# 元件 → (hardware_id, aggregator 的分析器路徑（依 agg 順序；重疊的 contains 會出現在兩個路徑）)
COMPONENTS = {
    "act_motor_left": ("motor_left", ["/Actuators/Drivetrain & Base Control/Motors"]),
    "act_motor_right": ("motor_right", ["/Actuators/Drivetrain & Base Control/Motors"]),
    "pwr_bms": ("bms", ["/Actuators/Energy System/BMS", "/Actuators/Energy System/Charger & Dock"]),
    "loc_wheel_odometry": ("wheel_odom", ["/Localization/Odometry/Wheel Odometry", "/Localization/Other Localization"]),
    "nav_global_planner": ("nav_global_planner", ["/Navigation/Other Navigation", "/Navigation/Motion Planning/Global Planners"]),
    "sensor_camera_front": ("camera_front", ["/Sensors/Other Sensors", "/Sensors/Perception/Camera"]),
    "sensor_lidar_front": ("lidar_front", ["/Sensors/Other Sensors", "/Sensors/Perception/LiDAR"]),
    "sensor_imu": ("imu", ["/Sensors/Other Sensors", "/Sensors/Inertial & Safety/IMU"]),
}
# 故障的種類：元件 → [(level, code, message)]
FAULTS = {
    "act_motor_left": [(1, 0x03402901, "Motor overheat"), (2, 0x03402901, "Motor overtemperature!")],
    "act_motor_right": [(1, 0x03402901, "Motor overheat"), (2, 0x03402901, "Motor overtemperature!")],
    "pwr_bms": [(1, 0x02402A01, "Battery low")],
    "loc_wheel_odometry": [(1, 0x02302101, "Wheel slip detected")],
    "nav_global_planner": [(1, 0x03201502, "Global planning execution slow")],
    "sensor_camera_front": [(2, 0x02100201, "Camera frame drop"), (1, 0x02100201, "Camera frame rate low")],
    "sensor_lidar_front": [(2, 0x04100101, "LiDAR disconnected"), (1, 0x04100101, "LiDAR frequency too low")],
    "sensor_imu": [(2, 0x03100301, "IMU calibration error")],
}
# /diagnostics_agg 沒有輸入時的 44 個狀態（agg 順序）：(名稱, 子項目的 key)；子項目＝分析器（key 是名稱）或子群組（key 是完整路徑）
_TREE = [
    ("/Actuators/Drivetrain & Base Control/Base Drivers & Control", None), ("/Actuators/Drivetrain & Base Control/Motors", None),
    ("/Actuators/Drivetrain & Base Control", ["Base Drivers & Control", "Motors"]),
    ("/Actuators/Energy System/BMS", None), ("/Actuators/Energy System/Charger & Dock", None),
    ("/Actuators/Energy System", ["BMS", "Charger & Dock"]),
    ("/Actuators", ["/Actuators/Drivetrain & Base Control", "/Actuators/Energy System"]),
    ("/Localization/Absolute Localization/AMCL & Pose Publisher", None), ("/Localization/Absolute Localization/SLAM & Mapping", None),
    ("/Localization/Absolute Localization", ["AMCL & Pose Publisher", "SLAM & Mapping"]),
    ("/Localization/Odometry/Visual / LiDAR Odom", None), ("/Localization/Odometry/Wheel Odometry", None),
    ("/Localization/Odometry", ["Visual / LiDAR Odom", "Wheel Odometry"]),
    ("/Localization/Other Localization", None),
    ("/Localization", ["/Localization/Absolute Localization", "/Localization/Odometry", "Other Localization"]),
    ("/Navigation/Control & Arbitration/Arbitration", None), ("/Navigation/Control & Arbitration/Controllers", None),
    ("/Navigation/Control & Arbitration/Recovery Behaviors", None),
    ("/Navigation/Control & Arbitration", ["Arbitration", "Controllers", "Recovery Behaviors"]),
    ("/Navigation/Other Navigation", None),
    ("/Navigation/Motion Planning/Global Planners", None), ("/Navigation/Motion Planning/Local Planners & Restraint", None),
    ("/Navigation/Motion Planning", ["Global Planners", "Local Planners & Restraint"]),
    ("/Navigation", ["/Navigation/Control & Arbitration", "Other Navigation", "/Navigation/Motion Planning"]),
    ("/Sensors/Other Sensors", None),
    ("/Sensors/Perception/Camera", None), ("/Sensors/Perception/LiDAR", None),
    ("/Sensors/Perception", ["Camera", "LiDAR"]),
    ("/Sensors/Inertial & Safety/IMU", None), ("/Sensors/Inertial & Safety/Safety Sensors", None),
    ("/Sensors/Inertial & Safety", ["IMU", "Safety Sensors"]),
    ("/Sensors", ["Other Sensors", "/Sensors/Perception", "/Sensors/Inertial & Safety"]),
    ("/System/AI & Upper Body/Upper Body Interface", None), ("/System/AI & Upper Body/VLM Brain Interface", None),
    ("/System/AI & Upper Body", ["Upper Body Interface", "VLM Brain Interface"]),
    ("/System/Compute & Communication/Internal Communications", None), ("/System/Compute & Communication/IPC & Compute Hardware", None),
    ("/System/Compute & Communication", ["Internal Communications", "IPC & Compute Hardware"]),
    ("/System/Other System", None),
    ("/System/Task & External Interfaces/Realtime / Async Bridge", None),
    ("/System/Task & External Interfaces/Fleet & External System", None), ("/System/Task & External Interfaces/Task Agent", None),
    ("/System/Task & External Interfaces", ["Realtime / Async Bridge", "Fleet & External System", "Task Agent"]),
    ("/System", ["/System/AI & Upper Body", "/System/Compute & Communication", "Other System", "/System/Task & External Interfaces"]),
]
_WORD = {0: "OK", 1: "Warning", 2: "Error", 3: "Stale"}
TRIGGERS = ("SMOOTH_PAUSE", "HARD_STOP", "EMERGENCY_STOP")


def _q(v):
    """event 行的值：空的或含空白、"、=、\\ 的用 "…" 包起來（src/core/event_log.cpp、safety_motion_controller.py）。"""
    s = str(v)
    if s == "" or any(c in s for c in ' "=\\'):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _codes(codes):
    return "[" + ",".join(f"0x{c:08X}" for c in codes) + "]"


def ev(name, **kw):
    return f"event={name}" + "".join(f" {k}={v}" for k, v in kw.items())


class Diagnostics:
    """情境用的時間線：fault()、raw_session()、freeze_aggregator()、kill_aggregator()、kill_mon()、lcm_restart()、reset()、
    unlatch()、boot()。build() 之後才有訊息。cmd_out：GATE 輸出的速度（給底盤的模擬用）。"""

    def __init__(self, sim, raw_rate=10, naming="bare"):
        self.sim, self.rng = sim, sim.rng
        self.raw_rate, self.naming = raw_rate, naming
        self.faults = []          # [comp, level, code, msg, t0, t1]
        self.producers = {}       # comp → (rate, t_start, t_end)
        self.raw_sessions = []    # (t0, t1, v, w)
        self.agg_alive = Alive()
        self.mon_alive = Alive()
        self.mon_activate = [-INF]   # MON 每次 activate 的時間（之後 15 秒是 INIT）
        self.lcm_events = []      # (t, kind)
        self.resets, self.unlatches = [], []
        self.boot_t = None
        self.cmd_out = (Signal(0.0), Signal(0.0))
        self.topics = ["/diagnostics_agg", "/diagnostics_toplevel_state", "/system/safety_command", "/system/safety_gate_status",
                       "/cmd_vel"]

    # ---- 情境的設定
    def boot(self, t):
        """整套系統在 t 啟動（錄製開始時還沒有在跑）。"""
        self.boot_t = t
        self.agg_alive = Alive(t + self.rng.uniform(0.05, 0.12))
        self.mon_alive = Alive(t + 0.02)
        self.mon_activate = [t + 0.02 + self.rng.uniform(0.0, 0.01)]

    def fault(self, comp, level, code, msg, t0, t1=INF, rate=5.0):
        self.faults.append([comp, level, code, msg, t0, t1])
        p = self.producers.get(comp)
        start = t0 if p is None else min(p[1], t0)
        self.producers[comp] = (rate, start, INF)

    def stop_producer(self, comp, t):
        rate, start, _ = self.producers[comp]
        self.producers[comp] = (rate, start, t)

    def raw_session(self, t0, t1, v, w=0.0):
        self.raw_sessions.append((t0, t1, v, w))

    def freeze_aggregator(self, t, d):
        self.agg_alive.gap(t, d)

    def kill_aggregator(self, t):
        self.agg_alive.stop(t)

    def kill_mon(self, t):
        self.mon_alive.stop(t)

    def lcm_restart(self, t):
        self.lcm_events.append((t, "restart"))

    def reset(self, t, source="field_operator"):
        self.resets.append((t, source))

    def unlatch(self, t, reset_all=True):
        self.unlatches.append((t, reset_all))

    # ---- 模擬
    def _producer_msg(self, comp, t):
        """元件的 producer 在 t 發的狀態（故障中＝故障的等級與訊息，否則 OK）。"""
        hw, _ = COMPONENTS[comp]
        name = comp if self.naming == "bare" else f"{hw}_driver: {comp}"
        for f in self.faults:
            if f[0] == comp and f[4] <= t < f[5]:
                return {"level": f[1], "name": name, "message": f[3], "hardware_id": hw,
                        "values": [{"key": "error_code", "value": f"0x{f[2]:08X}"}]}, f[2]
        return {"level": 0, "name": name, "message": "OK", "hardware_id": hw, "values": [{"key": "error_code", "value": "0x00000000"}]}, 0

    def _agg(self, inputs):
        """aggregator 的一個 tick：44 個狀態＋輸入的項目（插在分析器的 header 後面），header 的等級與 values 往上算。"""
        items = {}
        for st in inputs:
            comp = st["name"].split(": ")[-1]
            for path in COMPONENTS[comp][1]:
                items.setdefault(path, []).append(st)
        level, msg, values = {}, {}, {}
        for path, kids in _TREE:
            if kids is None:
                its = sorted(items.get(path, []), key=lambda s: s["name"])
                lv = max((s["level"] for s in its), default=0)
                level[path], msg[path] = lv, _WORD[min(lv, 2)] if lv < 3 else "Stale"
                values[path] = [{"key": s["name"], "value": s["message"]} for s in its]
            else:
                full = [k if k.startswith("/") else path + "/" + k for k in kids]
                lv = max(level[f] for f in full)
                level[path], msg[path] = lv, _WORD[min(lv, 2)]
                values[path] = [{"key": k, "value": msg[f]} for k, f in zip(kids, full)]
        out = []
        for path, kids in _TREE:
            out.append({"level": level[path], "name": path, "message": msg[path], "hardware_id": "", "values": values[path]})
            if kids is None:
                for s in sorted(items.get(path, []), key=lambda s: s["name"]):
                    out.append(dict(s, name=f"{path}/{s['name']}"))
        return out

    @staticmethod
    def _toplevel(statuses):
        bad = [s for s in statuses if s["level"] > 0]
        if not bad:
            return {"level": 0, "name": "toplevel_state", "message": "", "hardware_id": "", "values": []}
        deepest = max(bad, key=lambda s: s["name"].count("/"))
        return {"level": max(s["level"] for s in bad), "name": "toplevel_state", "message": f"{deepest['name']}: {deepest['message']}",
                "hardware_id": deepest["hardware_id"], "values": deepest["values"]}

    @staticmethod
    def _evaluate(statuses):
        """MON 的矩陣：狀態裡 level ≥ 1、有 error_code 而且不是 0 的項目 → 故障清單（agg 順序）與勝出的反應。"""
        faults = []
        for s in statuses:
            if s["level"] < 1:
                continue
            for kv in s["values"]:
                if "error_code" in kv["key"]:
                    try:
                        code = int(kv["value"], 16)
                    except ValueError:
                        code = 0
                    if code:
                        rule = RULES.get(code)
                        if rule and s["level"] >= rule[0]:
                            reaction, params, reason = rule[1], dict(rule[2]), rule[3]
                        else:
                            reaction, params = DEFAULT_REACTION[min(s["level"], 3)], {}
                            reason = f"Default reaction for level {s['level']} from task: {s['name']} ({kv['key']})"
                        faults.append({"task": s["name"], "code": code, "level": s["level"], "reaction": reaction, "params": params,
                                       "reason": reason, "sev": "ERROR" if s["level"] >= 2 else "WARN"})
        return faults

    def build(self):
        sim, rng, D = self.sim, self.rng, self.sim.duration
        agg = sim.events("/diagnostics_agg", "diagnostic_msgs/msg/DiagnosticArray")
        top = sim.events("/diagnostics_toplevel_state", "diagnostic_msgs/msg/DiagnosticStatus")
        sc = sim.events("/system/safety_command", "diagnostics_package/msg/SystemSafetyStatus")
        gs = sim.events("/system/safety_gate_status", "diagnostics_package/msg/SafetyGateStatus")
        cv = sim.events("/cmd_vel", "geometry_msgs/msg/Twist")
        for s, r in ((agg, 10), (top, 10), (sc, 10), (cv, 20)):
            s.rate = r
        gs.latched = True
        diag = sim.streams.get("/diagnostics") or sim.events("/diagnostics", "diagnostic_msgs/msg/DiagnosticArray")
        raw = sim.events("/cmd_vel_raw", "geometry_msgs/msg/Twist") if self.raw_sessions else None
        if raw is not None:
            raw.rate = self.raw_rate
        mon_tr = sim.events("/system_health_monitor/transition_event", "lifecycle_msgs/msg/TransitionEvent")

        # producer 的 /diagnostics：各元件自己的頻率；agg 看到的是每個元件最近一則（5 秒沒更新就拿掉）
        prod_msgs = {}
        for comp, (rate, t_s, t_e) in self.producers.items():
            t = t_s + rng.uniform(0, 1.0 / rate)
            ts = []
            while t < min(t_e, D):
                ts.append(t)
                st, _ = self._producer_msg(comp, t)
                diag.publish(t, {"header": header(sim, t), "status": [st]})
                t += 1.0 / rate * (1 + rng.gauss(0, 0.01))
            prod_msgs[comp] = ts
        if diag.explicit:
            diag.rate = max(r for r, _, _ in self.producers.values())

        # raw：/cmd_vel_raw 的時間（ros2 topic pub -r 10）
        raw_times = []
        for t0, t1, v, w in self.raw_sessions:
            t = t0
            while t < min(t1, D):
                raw_times.append((t, v, w))
                t += 1.0 / self.raw_rate * (1 + rng.gauss(0, 0.002))
        raw_times.sort()
        for t, v, w in raw_times:
            raw.publish(t, twist(v, w))

        # agg tick
        agg_ticks = []
        phase = rng.uniform(0, 0.1)
        for a, b in self.agg_alive.iv:
            t = max(a, 0.0) + (phase if a <= 0 else rng.uniform(0.0, 0.03))
            while t < min(b, D):
                agg_ticks.append(t)
                t += 0.1 * (1 + rng.gauss(0, 0.0005))

        # 事件時間表：agg tick、GATE 20 Hz tick、raw 收到、reset、unlatch、LCM
        gate_start = (self.boot_t + rng.uniform(0.12, 0.2)) if self.boot_t is not None else -INF
        gate_ticks, t = [], (gate_start if gate_start > -INF else rng.uniform(0, 0.05))
        while t < D:
            if t >= 0:
                gate_ticks.append(t)
            t += 0.05
        ev_list = [(t, 1, "agg") for t in agg_ticks] + [(t, 3, "tick") for t in gate_ticks]
        ev_list += [(t, 2, ("raw", v, w)) for t, v, w in raw_times]
        ev_list += [(t, 0, ("reset", src)) for t, src in self.resets] + [(t, 0, ("unlatch", ra)) for t, ra in self.unlatches]
        ev_list += [(t, 0, ("lcm", k)) for t, k in self.lcm_events]
        if self.boot_t is not None:
            ev_list.append((self.boot_t, -1, "boot"))
            ev_list.append((gate_start, -1, "gate_start"))
        for t_act in self.mon_activate:
            if 0 <= t_act + 15.0 < D:
                ev_list.append((t_act + 15.0, 0, "init_done"))
        ev_list.sort(key=lambda x: (x[0], x[1]))

        # 狀態
        mon = {"prev": "NONE" if self.boot_t is None else "", "latched": False, "latched_reaction": None, "latched_codes": [],
               "faults": {}, "act": [t for t in self.mon_activate]}
        gate = {"latched": False, "latest": "NONE" if self.boot_t is None else "", "last_sc": -INF if self.boot_t is not None else 0.0,
                "last_raw": -INF, "raw": (0.0, 0.0), "ratio": 1.0, "waiting_zero": False, "state": None, "count": 0,
                "src": "", "acc": False, "reason": "", "started": self.boot_t is None, "any_sc": self.boot_t is None}
        bbx = {"prev": "NONE", "pending_until": -INF}

        def gate_eval(t):
            reasons = []
            if gate["latched"] or gate["latest"] in ("HARD_STOP", "EMERGENCY_STOP"):
                reasons.append("ESTOP_LATCHED")
            if not gate["any_sc"]:
                reasons.append("NO_SAFETY_COMMAND_YET")
            elif t - gate["last_sc"] > 0.5:
                reasons.append("SAFETY_COMMAND_TIMEOUT")
            if gate["latest"] == "INIT":
                reasons.append("MON_INITIALIZING")
            if gate["latest"] == "SMOOTH_PAUSE":
                reasons.append("PAUSE_REQUESTED")
            if gate["waiting_zero"]:
                reasons.append("WAITING_ZERO_AFTER_RESET")
            if t - gate["last_raw"] > 0.5:
                reasons.append("NO_CMD_VEL_RAW")
            if "ESTOP_LATCHED" in reasons:
                mode = "ESTOP_LATCHED"
            elif set(reasons) & {"NO_SAFETY_COMMAND_YET", "SAFETY_COMMAND_TIMEOUT", "MON_INITIALIZING", "WAITING_ZERO_AFTER_RESET"}:
                mode = "PROTECTIVE_STOP"
            elif gate["latest"] == "SMOOTH_PAUSE":
                mode = "PAUSED"
            elif gate["latest"] == "LIMIT_SPEED":
                mode = "LIMITED"
            else:
                mode = "NORMAL"
            return mode, reasons

        def gate_publish(t, mode, reasons):
            gs.publish(t, {"header": header(sim, t), "mode": mode, "estop_latched": gate["latched"], "stop_reasons": reasons,
                           "latest_reaction": gate["latest"], "reset_request_count": gate["count"],
                           "last_reset_source": gate["src"], "last_reset_accepted": gate["acc"], "last_reset_reason": gate["reason"]})

        def gate_refresh(t, from_timer=False):
            if not gate["started"]:
                return
            mode, reasons = gate_eval(t)
            st = (mode, gate["latched"], tuple(reasons), gate["latest"])
            if st == gate["state"]:
                return
            prev = gate["state"]
            gate["state"] = st
            if prev is not None and not prev[2] and reasons:   # 放行 → 停止：立刻送一則零速（timer 偵測到的會同一毫秒兩則）
                cv.publish(t + 0.0001, twist())
                if from_timer:
                    cv.publish(t + 0.0002, twist())
                self.cmd_out[0].set(t, 0.0)
                self.cmd_out[1].set(t, 0.0)
            gate_publish(t + 0.0003, mode, reasons)
            level = "WARN" if [r for r in reasons if r != "NO_CMD_VEL_RAW"] else "INFO"
            sim.log(t + 0.0004, level, GATE, ev("GATE_STATE_CHANGED", mode=mode, latched=str(gate["latched"]).lower(),
                                                reasons="[" + ",".join(reasons) + "]", reaction=_q(gate["latest"])),
                    (GATE_FILE, "_refresh", 319 if level == "WARN" else 321))

        # 錄製開始時已經在跑：GATE 的狀態（TRANSIENT_LOCAL 重播的那一則）
        if self.boot_t is None:
            gate["last_raw"] = -INF
            mode, reasons = gate_eval(0.0)
            gate["state"] = (mode, gate["latched"], tuple(reasons), gate["latest"])
            gate_publish(0.0012, mode, reasons)
            sim.expect_tags("/system/safety_gate_status", not_=("訊息中斷", "開始或停止發布"))

        for t, _, kind in ev_list:
            if t < 0 or t >= D:
                continue
            if kind == "boot":
                self._boot_logs(t)
                continue
            if kind == "gate_start":
                gate["started"] = True
                sim.log(t, "INFO", GATE, ev("GATE_STARTED", safety_command_timeout_sec=0.5, cmd_vel_raw_timeout_sec=0.5, output_rate_hz=20.0),
                        (GATE_FILE, "__init__", 132))
                gate_refresh(t + 0.002)
                cv.publish(t + 0.0025, twist())
                continue
            if kind == "init_done":
                if self.mon_alive.contains(t):
                    sim.log(t, "INFO", MON, ev("MON_INIT_FINISHED"), (MON_FILE, "onInitTimeout", 109))
                continue
            if kind == "tick":
                if not gate["started"]:
                    continue
                if gate["waiting_zero"] and t - gate["last_raw"] > 0.5:
                    gate["waiting_zero"] = False
                gate_refresh(t, from_timer=True)
                mode, reasons = gate_eval(t)
                v, w = (gate["raw"][0] * gate["ratio"], gate["raw"][1] * gate["ratio"]) if not reasons else (0.0, 0.0)
                cv.publish(t, twist(round(v, 6), round(w, 6)))
                self.cmd_out[0].set(t, v)
                self.cmd_out[1].set(t, w)
                continue
            if isinstance(kind, tuple) and kind[0] == "raw":
                gate["last_raw"], gate["raw"] = t, (kind[1], kind[2])
                if gate["waiting_zero"] and kind[1] == 0 and kind[2] == 0:
                    gate["waiting_zero"] = False
                gate_refresh(t + 0.0002)
                continue
            if isinstance(kind, tuple) and kind[0] == "reset":
                self._reset(t, kind[1], gate, mon, gate_publish, gate_eval)
                gate_refresh(t + 0.002)
                continue
            if isinstance(kind, tuple) and kind[0] == "unlatch":
                if mon["latched"]:
                    codes = mon["latched_codes"]
                    sim.log(t, "INFO", MON, ev("MON_UNLATCH_REQUEST", result="accepted", codes=_codes(codes), latched="false", reaction="NONE",
                                                request_codes="[]", reset_all="true"), (MON_FILE, "logEvent", 159))
                    mon.update(latched=False, latched_reaction=None, latched_codes=[])
                else:
                    sim.log(t, "WARN", MON, ev("MON_UNLATCH_REQUEST", result="rejected", codes="[]", latched="false", reaction="NONE",
                                                request_codes="[]", reset_all="true"), (MON_FILE, "logEvent", 162))
                continue
            if isinstance(kind, tuple) and kind[0] == "lcm":
                act = self._lcm_restart(t, mon_tr)
                if act is not None:
                    mon["act"].append(act)
                    if act + 15.0 < D and self.mon_alive.contains(act + 15.0):
                        sim.log(act + 15.0, "INFO", MON, ev("MON_INIT_FINISHED"), (MON_FILE, "onInitTimeout", 109))
                continue
            # agg tick：aggregator → toplevel → MON → GATE（MON 只有活著、active 時才發）
            inputs = []
            for comp, ts in prod_msgs.items():
                i = _last_le(ts, t)
                if i is not None and t - ts[i] <= 5.0:
                    st, _ = self._producer_msg(comp, ts[i])
                    inputs.append(st)
            statuses = self._agg(inputs)
            agg.publish(t, {"header": header(sim, t), "status": statuses})
            top.publish(t + 0.00002, self._toplevel(statuses))
            if not self.mon_alive.contains(t) or not [a for a in mon["act"] if a <= t]:
                continue
            t_mon = t + rng.uniform(0.00005, 0.00015)
            acts = [a for a in mon["act"] if a <= t]
            in_init = acts and t < max(acts) + 15.0
            cmd = self._mon_step(t_mon, statuses, mon, in_init)
            sc.publish(t_mon, cmd)
            # BBX：進入觸發集合的上升緣
            r = cmd["primary_reaction"]
            if r in TRIGGERS and bbx["prev"] not in TRIGGERS:
                code_l = [int(c) for c in cmd["active_error_codes"]]
                sim.log(t_mon + 0.0001, "WARN", BBX, ev("BBX_TRIGGERED", reaction=r, winning_level=cmd["winning_level"],
                                                         error_codes=_codes(code_l), warn_codes=_codes([int(c) for c in cmd["active_warn_codes"]]),
                                                         winning_task=_q(cmd["winning_task"])), (BBX_FILE, "safetyCallback", 162))
                if bbx["pending_until"] < t_mon:
                    bbx["pending_until"] = t_mon + 10.0
                    tw = t_mon + rng.uniform(10.12, 10.14)
                    trig = int((sim.t0 + t_mon) * 1e9)
                    sim.log(tw, "INFO", BBX, ev("BBX_SNAPSHOT_WRITTEN", dir=f"/home/ubuntu/blackbox_logs/incident_{_local(sim, t_mon)}_{r}",
                                                frames=rng.randint(1200, 2000), trigger_ns=trig, window_start_ns=trig - 30_000_000_000,
                                                window_end_ns=trig + 10_000_000_000), (BBX_FILE, "operator()", 60))
            bbx["prev"] = r
            # GATE 收到 safety command
            t_g = t_mon + rng.uniform(0.0003, 0.0008)
            gate["last_sc"], gate["latest"], gate["any_sc"] = t_g, r, True
            if r in ("HARD_STOP", "EMERGENCY_STOP"):
                gate["latched"] = True
            ratio = 1.0
            if r == "LIMIT_SPEED":
                ps = {p["name"]: p["value"] for p in cmd["action_params"]}
                ratio = ps.get("speed_ratio", 0.5)
            elif r != "NONE":
                ratio = 0.0
            gate["ratio"] = ratio
            gate_refresh(t_g)
        self._expectations(gs, cv, agg)
        return self

    # ---- MON
    def _mon_step(self, t, statuses, mon, in_init):
        sim = self.sim
        if in_init:
            cmd = self._cmd(t, "INIT", "SystemHealthMonitor", 0, "System is in initialization phase. Diagnostic evaluation bypassed.", [], [], [])
            if mon["prev"] != "INIT":
                sim.log(t + 0.0001, "INFO", MON, ev("MON_REACTION_CHANGED", **{"from": _q(mon["prev"])}, to="INIT",
                                                     latched=str(mon["latched"]).lower(), latched_codes=_codes(mon["latched_codes"]),
                                                     winning_level=0, error_codes="[]", warn_codes="[]", winning_task="SystemHealthMonitor",
                                                     winning_reason=_q("System is in initialization phase. Diagnostic evaluation bypassed.")),
                        (MON_FILE, "logEvent", 159))
                mon["prev"] = "INIT"
            return cmd
        faults = self._evaluate(statuses)
        now = {(f["task"], f["code"]): f for f in faults}
        logs = []
        for k, f in mon["faults"].items():
            if k not in now:
                logs.append(("INFO", ev("MON_FAULT_CLEARED", code=f"0x{f['code']:08X}", severity=f["sev"], task=_q(f["task"])), 159))
        for k, f in sorted(now.items(), key=lambda kv: (kv[1]["sev"] != "ERROR", faults.index(kv[1]))):
            old = mon["faults"].get(k)
            lvl = "ERROR" if f["sev"] == "ERROR" else "WARN"
            if old is None:
                logs.append((lvl, ev("MON_FAULT_RAISED", code=f"0x{f['code']:08X}", severity=f["sev"], task=_q(f["task"])), 165 if lvl == "ERROR" else 162))
            elif old["sev"] != f["sev"]:
                logs.append((lvl, ev("MON_FAULT_SEVERITY_CHANGED", code=f"0x{f['code']:08X}", **{"from": old["sev"]}, to=f["sev"],
                                     task=_q(f["task"])), 165 if lvl == "ERROR" else 162))
        mon["faults"] = now
        win = None
        for f in faults:
            if win is None or PRIORITY[f["reaction"]] > PRIORITY[win["reaction"]]:
                win = f
        reaction = win["reaction"] if win else "NONE"
        if reaction in ("HARD_STOP", "EMERGENCY_STOP"):
            mon["latched"] = True
            mon["latched_reaction"] = max(filter(None, [mon["latched_reaction"], reaction]), key=lambda r: PRIORITY[r])
            mon["latched_codes"] = sorted(set(mon["latched_codes"]) | {f["code"] for f in faults if f["level"] >= 2})
        primary = mon["latched_reaction"] if mon["latched"] else reaction
        params = {}
        if primary != "NONE":
            for grp in ("WARN", "ERROR"):
                g = {}
                for f in faults:
                    if f["sev"] != grp:
                        continue
                    for k, v in f["params"].items():
                        if k == "speed_ratio" or k == "retry_count":
                            g[k] = min(g.get(k, v), v)
                        elif k == "max_decel":
                            g[k] = max(g.get(k, v), v)
                        else:
                            g[k] = v
                params.update(g)
        err = [f for f in faults if f["level"] >= 2]
        warn = [f for f in faults if f["level"] == 1]
        cmd = self._cmd(t, primary, win["task"] if win else "Unknown", win["level"] if win else 0, win["reason"] if win else "",
                        sorted(params.items()), err, warn, faults)
        if primary != mon["prev"]:
            lvl = "INFO" if primary in ("NONE", "INIT") else ("ERROR" if primary in ("HARD_STOP", "EMERGENCY_STOP") else "WARN")
            logs.append((lvl, ev("MON_REACTION_CHANGED", **{"from": _q(mon["prev"])}, to=primary, latched=str(mon["latched"]).lower(),
                                 latched_codes=_codes(mon["latched_codes"]), winning_level=cmd["winning_level"],
                                 error_codes=_codes([f["code"] for f in err]), warn_codes=_codes([f["code"] for f in warn]),
                                 winning_task=_q(cmd["winning_task"]), winning_reason=_q(cmd["winning_reason"])),
                         {"INFO": 159, "WARN": 162, "ERROR": 165}[lvl]))
            mon["prev"] = primary
        for i, (lvl, text, line) in enumerate(logs):
            sim.log(t + 0.00005 * (i + 1), lvl, MON, text, (MON_FILE, "logEvent", line))
        return cmd

    def _cmd(self, t, primary, task, level, reason, params, err, warn, faults=()):
        return {"header": header(self.sim, t), "primary_reaction": primary, "winning_task": task, "winning_level": level,
                "winning_reason": reason, "action_params": [{"name": k, "value": float(v)} for k, v in params],
                "active_error_tasks": [f["task"] for f in err], "active_error_codes": [f["code"] for f in err],
                "active_warn_tasks": [f["task"] for f in warn], "active_warn_codes": [f["code"] for f in warn],
                "active_reasons": [f"[{f['task']} -> error_code] {f['reason']}" for f in faults]}

    def _reset(self, t, source, gate, mon, gate_publish, gate_eval):
        sim = self.sim
        gate["count"] += 1
        gate["src"] = source or "(not provided)"
        if not gate["latched"]:
            why = "NOT_LATCHED"
        elif t - gate["last_sc"] > 0.5:
            why = "SAFETY_COMMAND_TIMEOUT"
        elif gate["latest"] in ("HARD_STOP", "EMERGENCY_STOP"):
            why = "ESTOP_CAUSE_ACTIVE"
        elif gate["latest"] == "INIT":
            why = "MON_INITIALIZING"
        else:
            why = "ACCEPTED"
        gate["acc"], gate["reason"] = why == "ACCEPTED", why
        if why == "ACCEPTED":
            gate["latched"] = False
            gate["waiting_zero"] = t - gate["last_raw"] <= 0.5
            sim.log(t + 0.001, "INFO", GATE, ev("GATE_RESET_ACCEPTED", source=_q(gate["src"])), (GATE_FILE, "reset_callback", 237))
        else:
            sim.log(t + 0.001, "WARN", GATE, ev("GATE_RESET_REJECTED", source=_q(gate["src"]), reason=why), (GATE_FILE, "reset_callback", 239))
        mode, reasons = gate_eval(t + 0.0015)
        gate_publish(t + 0.0015, mode, reasons)   # 每次 reset 都強制發一則

    def _lcm_restart(self, t, mon_tr):
        """LCM 重啟 MON：活著的 MON 10 ms 內走完 deactivate/cleanup/configure/activate（之後 15 秒 INIT）；MON 死了就一直等。"""
        sim = self.sim
        sim.log(t, "WARN", LCM, ev("LCM_RESTART_REQUESTED", nodes="[system_health_monitor]"), (LCM_FILE, "handleRestartNode", 122))
        sim.log(t + 0.0001, "INFO", LCM, ev("LCM_SEQUENCE_STARTED", nodes="[system_health_monitor]"), (LCM_FILE, "logInfo", 97))
        if not self.mon_alive.contains(t):
            sim.log(t + 2.0, "WARN", LCM, ev("LCM_SERVICE_UNAVAILABLE", service="/system_health_monitor/get_state"), (LCM_FILE, "getNodeState", 62))
            k = 3.0
            while t + k < sim.duration:
                sim.log(t + k + self.rng.uniform(0, 0.01), "WARN", LCM, ev("LCM_SERVICE_WAITING", service="/system_health_monitor/change_state"),
                        (LCM_FILE, "changeStateSync", 81))
                k += 1.0
            return None
        steps = [(0.0004, "INFO", LCM, ev("LCM_NODE_DEACTIVATING", node="system_health_monitor"), (LCM_FILE, "logInfo", 97), (3, 14)),
                 (0.0006, "INFO", MON, ev("MON_LIFECYCLE", transition="deactivate"), (MON_FILE, "on_deactivate", 77), (14, 2)),
                 (0.0017, "INFO", LCM, ev("LCM_NODE_CLEANING_UP", node="system_health_monitor"), (LCM_FILE, "logInfo", 97), (2, 11)),
                 (0.0019, "INFO", MON, ev("MON_LIFECYCLE", transition="cleanup"), (MON_FILE, "on_cleanup", 89), (11, 1)),
                 (0.006, "INFO", MON, ev("MON_LIFECYCLE", transition="configure",
                                         matrix_yaml_path="/workspace/ws/install/diagnostics_package/share/diagnostics_package/config/fault_reaction_matrix.yaml"),
                  (MON_FILE, "on_configure", 38), (1, 10)),
                 (0.0065, "INFO", LCM, ev("LCM_NODE_CONFIGURED", node="system_health_monitor"), (LCM_FILE, "logInfo", 97), (10, 2)),
                 (0.008, "INFO", MON, ev("MON_LIFECYCLE", transition="activate", init_buffer_sec=15), (MON_FILE, "on_activate", 63), (2, 13)),
                 (0.0095, "INFO", LCM, ev("LCM_NODE_ACTIVATED", node="system_health_monitor"), (LCM_FILE, "logInfo", 97), (13, 3)),
                 (0.0100, "INFO", LCM, ev("LCM_SEQUENCE_COMPLETED", nodes="[system_health_monitor]"), (LCM_FILE, "logInfo", 97), None)]
        labels = {1: "unconfigured", 2: "inactive", 3: "active", 10: "configuring", 11: "cleaningup", 13: "activating", 14: "deactivating"}
        for dt, lvl, node, text, src, tr in steps:
            sim.log(t + dt, lvl, node, text, src)
            if tr:
                mon_tr.publish(t + dt - 0.0001, {"timestamp": 0, "transition": {"id": 0, "label": ""},
                                                  "start_state": {"id": tr[0], "label": labels[tr[0]]},
                                                  "goal_state": {"id": tr[1], "label": labels[tr[1]]}})
        return t + 0.008

    def _boot_logs(self, t):
        sim, r = self.sim, self.rng
        a = t + r.uniform(0.0, 0.01)
        cfg = "/workspace/ws/install/diagnostics_package/share/diagnostics_package/config/fault_reaction_matrix.yaml"
        lines = [(0.000, "INFO", LCM, ev("LCM_SEQUENCE_STARTED", nodes="[system_health_monitor,blackbox_recorder]"), (LCM_FILE, "logInfo", 97)),
                 (0.015, "INFO", MON, ev("MON_LIFECYCLE", transition="configure", matrix_yaml_path=cfg), (MON_FILE, "on_configure", 38)),
                 (0.016, "INFO", LCM, ev("LCM_NODE_CONFIGURED", node="system_health_monitor"), (LCM_FILE, "logInfo", 97)),
                 (0.017, "INFO", MON, ev("MON_LIFECYCLE", transition="activate", init_buffer_sec=15), (MON_FILE, "on_activate", 63)),
                 (0.019, "INFO", LCM, ev("LCM_NODE_ACTIVATED", node="system_health_monitor"), (LCM_FILE, "logInfo", 97)),
                 (0.021, "INFO", BBX, ev("BBX_LIFECYCLE", transition="configure", log_dir="/home/ubuntu/blackbox_logs", pre_trigger_sec=30,
                                         post_trigger_sec=10, max_buffer_frames=200000,
                                         trigger_reactions="[SMOOTH_PAUSE,HARD_STOP,EMERGENCY_STOP]"), (BBX_FILE, "on_configure", 41)),
                 (0.023, "INFO", LCM, ev("LCM_NODE_CONFIGURED", node="blackbox_recorder"), (LCM_FILE, "logInfo", 97)),
                 (0.024, "INFO", BBX, ev("BBX_LIFECYCLE", transition="activate"), (BBX_FILE, "on_activate", 87)),
                 (0.025, "INFO", LCM, ev("LCM_NODE_ACTIVATED", node="blackbox_recorder"), (LCM_FILE, "logInfo", 97)),
                 (0.025, "INFO", LCM, ev("LCM_SEQUENCE_COMPLETED", nodes="[system_health_monitor,blackbox_recorder]"), (LCM_FILE, "logInfo", 97))]
        for dt, lvl, node, text, src in lines:
            sim.log(a + dt, lvl, node, text, src)

    # ---- 評分標準：GATE 的每次改變、/cmd_vel 的切換（只有幾種值時）、aggregator 的中斷
    def _expectations(self, gs, cv, agg):
        sim = self.sim
        prev = None
        fields = ("mode", "estop_latched", "latest_reaction", "reset_request_count", "last_reset_source", "last_reset_accepted",
                  "last_reset_reason")
        changes = []
        for t, f in sorted(gs.explicit, key=lambda x: x[0]):
            if prev is not None and (any(f[k] != prev[k] for k in fields) or sorted(f["stop_reasons"]) != sorted(prev["stop_reasons"])):
                changes.append(t)
                if f["mode"] != prev["mode"]:
                    token = f["mode"]
                elif sorted(f["stop_reasons"]) != sorted(prev["stop_reasons"]):
                    token = _reasons_text(f["stop_reasons"])
                elif f["reset_request_count"] != prev["reset_request_count"]:
                    token = str(f["reset_request_count"])
                elif f["latest_reaction"] != prev["latest_reaction"]:
                    token = f["latest_reaction"]
                else:
                    token = None
                if token and t >= 0.01:
                    sim.expect_value("/system/safety_gate_status", t, token, key=f["mode"] != prev["mode"],
                                     what=f"安全閘 {f['mode']} {f['stop_reasons']}")
            prev = f
        sim.change_times["/system/safety_gate_status"] = changes
        msgs = sorted(cv.explicit, key=lambda x: x[0])
        lx = [round(f["linear"]["x"], 6) for _, f in msgs]
        az = [round(f["angular"]["z"], 6) for _, f in msgs]
        steps_x, steps_z = 1 < len(set(lx)) <= 4, 1 < len(set(az)) <= 4   # 只有幾種值的才是「數值切換」的事件
        changes = []
        for i in range(1, len(msgs)):
            cx, cz = lx[i] != lx[i - 1], az[i] != az[i - 1]
            if (cx and steps_x) or (cz and steps_z):
                changes.append(msgs[i][0])
            if cx and steps_x:
                sim.expect_value("/cmd_vel", msgs[i][0], fmt_val(float(lx[i])), what=f"/cmd_vel linear.x {lx[i - 1]} → {lx[i]}")
        sim.change_times["/cmd_vel"] = changes


def _reasons_text(reasons):
    return "[" + ", ".join(sorted(reasons)) + "]"


def _last_le(ts, t):
    import bisect
    i = bisect.bisect_right(ts, t) - 1
    return i if i >= 0 else None


def _local(sim, t):
    import time
    return time.strftime("%Y%m%d_%H%M%S", time.localtime(sim.t0 + t))
