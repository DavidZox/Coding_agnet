"""隨機情境的組合：每一份錄製挑 1～3 個子系統（diagnostics、底盤、導航、RMF、VSLAM、bridge），每個子系統 0～2 個事件（時間、參數隨機），
有一成是「沒有事件」的穩定錄製、一成多是錄製中途才啟動（開機）。子系統之間照真的接法連動：導航的速度指令 → /cmd_vel_raw →
GATE → /cmd_vel → 底盤；底盤的 LiDAR 斷線 → /scan 停 → 導航的 Diagnostics 監看到斷訊。沒有底盤時 bridge 可能是 Isaac Sim 的設定：
感測器 Topic 從模擬器經 bridge 進來（Isaac 裡的機器人照速度指令動），模擬器中途才開／中途關掉 → bridge 的稽核 WARN、導航的
Diagnostics 等待初始化或斷訊。
評分標準（cases.json）由注入的事件在數據裡看得到的時間產生（sim_core.Sim._resolve），不用人工標註。
（2026-10-22 加了 bridge：子系統的抽法變了，同一個 seed 產生的數據跟加之前不同——gen/s1 是加之前產生的。）"""
import random

from sim_base import Base
from sim_bridge import Bridge
from sim_core import INF, Sim, Signal, twist
from sim_diag import FAULTS, Diagnostics
from sim_nav import Nav
from sim_rmf import Rmf
from sim_vslam import Vslam

GENERIC = "這 {} 秒系統發生了什麼？有哪些狀態變化？"


class Slots:
    """事件的時間：彼此不重疊（前後留 1 秒），也不要太靠近錄製的頭尾（事件的影響要看得到）。"""

    def __init__(self, rng, duration, start=3.0, tail=6.0):
        self.rng, self.lo, self.hi, self.used = rng, start, duration - tail, []

    def take(self, need, latest=None, earliest=None):
        """一段 need 秒的時間；latest／earliest：開始的時間最晚／最早到哪裡（有先後的事件，例如模擬器要先開、導航才能跑任務）。"""
        hi = self.hi - need if latest is None else min(self.hi - need, latest)
        lo = self.lo if earliest is None else max(self.lo, earliest)
        for _ in range(40):
            if hi <= lo:
                return None
            t = round(self.rng.uniform(lo, hi), 3)
            if all(t + need + 1.0 < a or t > b + 1.0 for a, b in self.used):
                self.used.append((t, t + need))
                return t
        return None


def compose(seed, idx, require=()):
    """一份隨機的錄製（模擬已經跑完）→ (sim, 說明)。require：一定要有的子系統（例如只測 bridge 的一組；沒給時抽法照舊）。"""
    rng = random.Random(seed * 100003 + idx)
    D = rng.choice([30, 40, 45, 60, 60, 75, 90, 120, 150, 178])
    t0 = 1792300000 + (seed * 1000 + idx) * 307 + round(rng.uniform(0, 1), 6)
    label = f"gen_s{seed}_{idx:03d}"
    sim = Sim(rng, D, t0, label)
    pool = ["diagnostics"] * 5 + ["base"] * 3 + ["nav"] * 3 + ["rmf"] * 2 + ["vslam"] * 2 + ["bridge"] * 2
    k = rng.choice([1, 1, 2, 2, 2, 3])
    systems = list(require)
    while len(systems) < max(k, len(systems)):
        s = rng.choice(pool)
        if s not in systems:
            systems.append(s)
    steady = rng.random() < 0.1
    boot = (not steady) and rng.random() < 0.15 and any(s in systems for s in ("diagnostics", "base", "vslam"))
    slots = Slots(rng, D, start=(18.0 if boot else 3.0))
    notes, questions = [], []

    # Isaac Sim 的設定：沒有真的底盤時，感測器（/scan、/odom、/imu…）從模擬器經 bridge 進來，導航不自己模擬 /odom
    isaac = "bridge" in systems and "base" not in systems and rng.random() < 0.6
    dg = Diagnostics(sim, raw_rate=rng.choice([10, 20]), naming=rng.choice(["bare", "node"])) if "diagnostics" in systems else None
    nav = Nav(sim, own_sensors="base" not in systems and not isaac) if "nav" in systems else None
    rmf = Rmf(sim, robots=rng.choice([("tb1", "tb2"), ("tb1", "tb2", "tb3")])) if "rmf" in systems else None
    vs = Vslam(sim) if "vslam" in systems else None
    base_cmd = None
    if dg is not None:
        base_cmd = dg.cmd_out
    elif nav is not None:
        base_cmd = (nav.v, nav.w)
    base = Base(sim, cmd=base_cmd, scan_points=rng.choice([180, 270])) if "base" in systems else None
    br = Bridge(sim, isaac=isaac, cmd=base_cmd) if "bridge" in systems else None

    if boot:
        tb = round(rng.uniform(0.5, 3.0), 3)
        for x in (dg, base, vs):
            if x is not None:
                x.boot(tb)
        notes.append(f"+{tb:.1f}s 系統啟動（錄製開始時還沒有在跑）")
        questions.append("系統啟動的過程中發生了什麼？什麼時候進入正常狀態？")

    if not steady:
        if dg is not None:
            _diag_events(rng, sim, dg, slots, notes, questions, with_nav=nav is not None)
        if base is not None:
            _base_events(rng, sim, base, slots, notes, questions, nav)
        # Isaac Sim 的設定：模擬器要先開，導航才有感測器可以跑任務；關模擬器放在任務之後
        bkind = rng.choice(["up", "up", "down"]) if br is not None and isaac else None
        if bkind == "up":
            _bridge_events(rng, sim, br, slots, notes, questions, nav, kind="up")
        if nav is not None:
            _nav_events(rng, sim, nav, slots, notes, questions)
        if rmf is not None:
            _rmf_events(rng, sim, rmf, slots, notes, questions)
        if vs is not None:
            _vslam_events(rng, sim, vs, slots, notes, questions)
        if br is not None and bkind != "up":
            after = max((b for a, b in slots.used), default=None) if nav is not None and bkind == "down" else None
            _bridge_events(rng, sim, br, slots, notes, questions, nav, kind=bkind, earliest=after)
    else:
        notes.append("穩定運作，沒有注入事件")

    # 建模擬：導航先（速度指令）→ diagnostics（GATE）→ 底盤 → 其他
    if nav is not None:
        nav.build()
        if dg is not None:   # 導航的速度指令是 GATE 的 /cmd_vel_raw
            for a, b, v, w in _pieces(nav.v, nav.w, D):
                dg.raw_session(a, b, v, w)
        else:
            cv = sim.events("/cmd_vel", "geometry_msgs/msg/Twist")   # collision_monitor 的輸出（沒有 GATE 時）：導航在動的時候 20 Hz
            cv.rate = 20
            t = rng.uniform(0, 0.05)
            while t < D:
                if abs(nav.v.at(t)) > 1e-6 or abs(nav.w.at(t)) > 1e-6:
                    cv.publish(t, twist(nav.v.at(t), nav.w.at(t)))
                t += 0.05
    made = {}
    for name, x in (("diagnostics", dg), ("base", base), ("rmf", rmf), ("vslam", vs), ("bridge", br)):
        if x is not None:
            before = set(sim.streams)
            x.build()
            made[name] = set(sim.streams) - before
    # 發布者在錄製中途才出現的 Topic：錄製工具要等發現了才訂閱，最前面的一兩則錄不到（真的 ros2 bag record -a 就是這樣）
    if boot:
        for name in ("diagnostics", "base", "vslam"):
            for topic in made.get(name, ()):
                if topic not in ("/diagnostics",):
                    sim.streams[topic].appears = tb
    for topic, s in sim.streams.items():
        lazy = topic == "/cmd_vel_raw" or topic.endswith(("/allocator_status", "/speed_limit")) or \
            (topic == "/diagnostics" and "base" not in systems)
        if lazy and s.explicit:
            s.appears = min(t for t, _ in s.explicit)
    timeline = sim.finalize()
    q = rng.choice(questions) if questions and rng.random() < 0.5 else GENERIC.format(int(D))
    return sim, {"systems": systems, "notes": notes, "question": q, "timeline": timeline, "steady": steady, "boot": boot}


def _pieces(v, w, D):
    """速度指令的分段（v、w 都不變的一段，至少一個不是 0）→ [(開始, 結束, v, w)]。"""
    ts = sorted({t for t in v.ts + w.ts if 0 <= t < D} | {0.0})
    out = []
    for a, b in zip(ts, ts[1:] + [D]):
        vv, ww = v.at(a), w.at(a)
        if abs(vv) > 1e-6 or abs(ww) > 1e-6:
            out.append((a, b, round(vv, 3), round(ww, 3)))
    return out


# ---------------------------------------------------------------- 各子系統的事件
def _diag_events(rng, sim, dg, slots, notes, qs, with_nav=False):
    menu = ["cmd", "warn", "warn", "error", "critical", "critical_reset", "agg_freeze", "agg_kill", "mon_kill", "lcm", "multi", "stale"]
    for _ in range(rng.choice([1, 1, 2])):
        kind = rng.choice(menu)
        if kind == "cmd" and not with_nav:
            d = round(rng.uniform(4, 12), 2)
            t = slots.take(d + 2)
            if t is None:
                continue
            v = rng.choice([0.1, 0.15, 0.2, 0.25, 0.3])
            dg.raw_session(t, t + d, v, rng.choice([0.0, 0.0, 0.2]))
            notes.append(f"+{t:.1f}s /cmd_vel_raw {v} m/s 約 {d:.0f} 秒")
            qs.append("速度指令什麼時候開始、什麼時候結束？/cmd_vel 有沒有跟著變化？")
        elif kind == "warn":
            comp = rng.choice(["act_motor_left", "act_motor_right", "loc_wheel_odometry", "pwr_bms", "nav_global_planner"])
            level, code, msg = FAULTS[comp][0]
            hold = rng.random() < 0.3
            d = round(rng.uniform(4, 12), 2)
            t = slots.take((d if not hold else 4) + 4)
            if t is None:
                continue
            dg.fault(comp, level, code, msg, t, INF if hold else t + d, rate=rng.choice([5.0, 1.0]))
            if not with_nav and rng.random() < 0.7:
                dg.raw_session(t - 2.5, (t + d + 3) if not hold else sim.duration - 3, rng.choice([0.2, 0.3]))
            notes.append(f"+{t:.1f}s {comp} {msg}（WARN，{code:#010x}）" + ("，到錄製結束都沒解除" if hold else f"，{d:.0f} 秒後解除"))
            qs.append(f"{comp} 出問題的前後，安全閘與速度指令怎麼變化？")
        elif kind == "error":
            level, code, msg = FAULTS["sensor_camera_front"][0]
            d = round(rng.uniform(3, 8), 2)
            t = slots.take(d + 12)
            if t is None:
                continue
            dg.fault("sensor_camera_front", level, code, msg, t, t + d, rate=5.0)
            if not with_nav:
                dg.raw_session(t - 3, t + d + 4, 0.2)
            notes.append(f"+{t:.1f}s 相機掉幀 ERROR {d:.0f} 秒（SMOOTH_PAUSE）")
            qs.append("相機出錯之後發生了什麼？什麼時候恢復？")
        elif kind in ("critical", "critical_reset"):
            level, code, msg = FAULTS["sensor_lidar_front"][0]
            d = round(rng.uniform(0.5, 4), 2)
            need = d + (9 if kind == "critical_reset" else 3)
            t = slots.take(need)
            if t is None:
                continue
            dg.fault("sensor_lidar_front", level, code, msg, t, t + d, rate=5.0)
            notes.append(f"+{t:.1f}s LiDAR 斷線 ERROR {d:.1f} 秒（HARD_STOP，閂鎖）")
            if kind == "critical_reset":
                dg.reset(t + d + 1.5)
                dg.unlatch(t + d + 5.0)
                dg.reset(t + d + 5.1)
                notes.append("復位：先被拒絕（閂鎖中），解除閂鎖後再復位成功")
                qs.append("LiDAR 斷線後安全閘怎麼變化？復位成功了嗎？")
            else:
                qs.append("為什麼安全閘一直鎖著？")
        elif kind == "agg_freeze":
            d = round(rng.uniform(3, 12), 2)
            t = slots.take(d + 2)
            if t is None:
                continue
            dg.freeze_aggregator(t, d)
            notes.append(f"+{t:.1f}s aggregator 凍結 {d:.0f} 秒")
            qs.append("診斷資料有沒有中斷？安全閘怎麼反應？")
        elif kind == "agg_kill":
            t = slots.take(8)
            if t is None:
                continue
            dg.kill_aggregator(t)
            slots.used.append((t, sim.duration))
            notes.append(f"+{t:.1f}s aggregator 被結束、不重啟")
            qs.append("後半段為什麼一直停在保護停止？")
        elif kind == "mon_kill":
            t = slots.take(8)
            if t is None:
                continue
            dg.kill_mon(t)
            if rng.random() < 0.5 and t + 4 < sim.duration - 4:
                dg.lcm_restart(t + rng.uniform(2, 4))
                notes.append("之後 LCM 要求重啟 MON（MON 已經不在，一直等）")
            slots.used.append((t, sim.duration))
            notes.append(f"+{t:.1f}s system_health_monitor 被結束")
            qs.append("system_health_monitor 停了之後發生了什麼？")
        elif kind == "lcm":
            t = slots.take(17)
            if t is None:
                continue
            dg.lcm_restart(t)
            notes.append(f"+{t:.1f}s LCM 重啟 system_health_monitor（15 秒初始化）")
            qs.append("重啟 system_health_monitor 之後，安全閘什麼時候恢復正常？")
        elif kind == "multi":
            t = slots.take(14)
            if t is None:
                continue
            dg.fault("act_motor_left", 1, 0x03402901, "Motor overheat", t, t + 12)
            dg.fault("loc_wheel_odometry", 1, 0x02302101, "Wheel slip detected", t + 3, t + 12)
            dg.fault("sensor_lidar_front", 2, 0x04100101, "LiDAR disconnected", t + 6, t + 12)
            if not with_nav:
                dg.raw_session(t - 2, t + 13, 0.3)
            notes.append(f"+{t:.1f}s 馬達過熱、+{t + 3:.1f}s 輪子打滑、+{t + 6:.1f}s LiDAR 斷線（三個故障疊在一起）")
            qs.append("這幾個故障的先後順序是什麼？安全閘每一步怎麼變化？")
        elif kind == "stale":
            t = slots.take(12)
            if t is None:
                continue
            dg.fault("act_motor_right", 1, 0x03402901, "Motor overheat", t, INF, rate=5.0)
            dg.stop_producer("act_motor_right", t + 3.0)
            notes.append(f"+{t:.1f}s 右馬達過熱，+{t + 3:.1f}s 回報的節點停止發布（5 秒後項目被移除）")
            qs.append("右馬達的過熱後來怎麼了？")


def _base_events(rng, sim, base, slots, notes, qs, nav):
    menu = ["alarm", "usb", "power", "lidar", "lidar", "imu", "checksum", "push", "bump"] + (["teleop", "teleop"] if base.own_cmd else [])
    for _ in range(rng.choice([1, 1, 2])):
        kind = rng.choice(menu)
        if kind == "teleop":
            d = round(rng.uniform(3, 10), 2)
            t = slots.take(d + 2)
            if t is None:
                continue
            v = rng.choice([0.3, 0.3, -0.2, 0.0])
            w = 0.0 if v else 0.8
            base.teleop(t, t + d, v, w)
            notes.append(f"+{t:.1f}s 鍵盤遙控 v={v} w={w} 約 {d:.0f} 秒")
            qs.append("遙控的時候底盤的狀態怎麼變化？")
        elif kind == "alarm":
            t = slots.take(8)
            if t is None:
                continue
            code = rng.choice([2, 6, 12])
            base.alarm_on(t, rng.choice(["R", "L"]), code)
            base.alarm_reset(t + rng.uniform(3, 6))
            notes.append(f"+{t:.1f}s 驅動器警報 alarm={code} → FAULT，之後 alarm_reset")
            qs.append("底盤為什麼進入 fault？什麼時候回到 idle？")
        elif kind == "usb":
            t = slots.take(6)
            if t is None:
                continue
            base.usb_unplug(t)
            slots.used.append((t, sim.duration))
            notes.append(f"+{t:.1f}s 底盤的 USB-RS485 被拔掉（WARN 每個迴圈一則）")
            qs.append("底盤的回授為什麼停了？")
        elif kind == "power":
            d = round(rng.uniform(4, 10), 2)
            t = slots.take(d + 8)
            if t is None:
                continue
            base.power_cut(t, d)
            base.alarm_reset(t + d + 3.0)
            notes.append(f"+{t:.1f}s 馬達斷電 {d:.0f} 秒，恢復後 alarm=21，再 alarm_reset")
            qs.append("馬達斷電的前後，底盤的 Topic 與 Log 怎麼變化？")
        elif kind == "lidar":
            side = rng.choice(["back", "front"])
            d = round(rng.uniform(3, 25), 2)
            t = slots.take(d + 2)
            if t is None:
                continue
            base.lidar_unplug(side, t, d)
            if nav is not None:
                nav.watch_lost("/scan", t, t + d)
            notes.append(f"+{t:.1f}s {side} LiDAR 斷線 {d:.0f} 秒（/rosout 沒有 Log）")
            qs.append("LiDAR 的數據有沒有中斷？哪些 Topic 受影響？")
        elif kind == "imu":
            t = slots.take(6)
            if t is None:
                continue
            base.imu_unplug(t)
            notes.append(f"+{t:.1f}s IMU USB 拔掉（FATAL、程序結束）")
            qs.append("IMU 發生了什麼事？")
        elif kind == "checksum":
            d = round(rng.uniform(10, 20), 2)
            t = slots.take(d)
            if t is None:
                continue
            base.imu_checksum(t, t + d)
            notes.append(f"+{t:.1f}s IMU 封包 checksum 錯誤（WARN，每 5 秒）")
        elif kind == "push":
            d = round(rng.uniform(5, 12), 2)
            t = slots.take(d + 2)
            if t is None:
                continue
            base.push_mode(t, t + d)
            notes.append(f"+{t:.1f}s 推車模式 {d:.0f} 秒")
            qs.append("推車模式的前後底盤狀態怎麼變化？")
        elif kind == "bump":
            t = slots.take(2)
            if t is None:
                continue
            base.bump(t, rng.uniform(2.5, 4.0))
            notes.append(f"+{t:.1f}s 碰撞（IMU 加速度尖峰）")
            qs.append("IMU 有沒有量到異常的數值？")


def _nav_events(rng, sim, nav, slots, notes, qs):
    outcome = rng.choice(["done", "done", "blocked_fail", "temp_block", "operator_stop", "loc_jump"])
    goal = rng.choice([10, 13]) if sim.duration < 90 else rng.choice([13, 2, 0])
    need = {10: 14, 13: 45, 2: 52, 0: 58}[goal] + (16 if outcome == "blocked_fail" else 10)
    t = slots.take(min(need, sim.duration - 10))
    if t is None:
        return
    nav.mission(t, goal, outcome)
    notes.append(f"+{t:.1f}s 任務到站點 {goal}（{ {'done': '正常完成', 'blocked_fail': '路被擋住 15 秒後放棄、任務失敗', 'temp_block': '暫時被擋、之後繼續', 'operator_stop': '現場停止', 'loc_jump': '定位跳動、停車等穩定'}[outcome] }）")
    qs.append({"done": "任務執行的過程是什麼？", "blocked_fail": "任務為什麼失敗？", "temp_block": "機器人中途為什麼停下來？",
               "operator_stop": "任務為什麼中止？", "loc_jump": "導航中途為什麼停車？"}[outcome])


def _rmf_events(rng, sim, rmf, slots, notes, qs):
    for _ in range(rng.choice([1, 2])):
        kind = rng.choice(["task", "task", "lost", "lost_back", "auth"])
        rid = rng.choice(rmf.robots)
        if kind == "task":
            t = slots.take(26)
            if t is None:
                continue
            st = rng.choice(["2", "3", "4", "13"])
            rmf.task(t, rid, [st])
            notes.append(f"+{t:.1f}s 派工給 {rid} 到站點 {st}")
            qs.append(f"{rid} 的任務流程是什麼？")
        elif kind in ("lost", "lost_back"):
            d = None if kind == "lost" else round(rng.uniform(4, 15), 2)
            t = slots.take((d or 6) + 2)
            if t is None:
                continue
            rmf.heartbeat_lost(rid, t, d)
            notes.append(f"+{t:.1f}s {rid} 的 robot_state 停止" + (f" {d:.0f} 秒" if d else "（到結束）"))
            qs.append(f"{rid} 什麼時候離線？有沒有恢復？")
        elif kind == "auth":
            t = slots.take(12)
            if t is None:
                continue
            rmf.auth_timeout(t, rid)
            notes.append(f"+{t:.1f}s 派工給 {rid}，機器人一直沒回應（10 秒逾時）")
            qs.append("派工為什麼沒有成功？")


def _vslam_events(rng, sim, vs, slots, notes, qs):
    kind = rng.choice(["lost", "lost", "gap", "reset"])
    d = round(rng.uniform(2, 10), 2)
    t = slots.take(d + 2)
    if t is None:
        return
    getattr(vs, {"lost": "lost", "gap": "image_gap", "reset": "reset"}[kind])(t, d)
    notes.append(f"+{t:.1f}s VSLAM " + {"lost": f"追蹤丟失 {d:.0f} 秒後重定位", "gap": f"相機影像中斷 {d:.0f} 秒", "reset": f"重新初始化 {d:.0f} 秒"}[kind])
    qs.append("VSLAM 的追蹤狀態有沒有變化？")


ISAAC_WATCHED = ["/scan", "/scan_b", "/imu", "/odom", "/joint_states_in"]   # 導航的 Diagnostics 監看的 Topic（Isaac 的設定時都經過 bridge）


def _bridge_events(rng, sim, br, slots, notes, qs, nav, kind=None, earliest=None):
    if br.isaac:
        if kind == "up":
            t = slots.take(8, latest=min(40.0, sim.duration / 3) if nav is not None else None)
            if t is None:
                return
            br.isaac_up(t)
            if t > 12 and rng.random() < 0.5:   # bridge 也在錄製中途才啟動：啟動後 5 秒的稽核發現 Isaac 還沒開
                tb = round(t - rng.uniform(6.5, min(15.0, t - 1.0)), 3)
                br.start(tb)
                notes.append(f"+{tb:.1f}s bridge 啟動（Isaac Sim 的設定）")
            if nav is not None:
                nav.watch_unseen(ISAAC_WATCHED, t + 0.15)
            notes.append(f"+{t:.1f}s Isaac Sim 開始執行，感測器 Topic 經 bridge 進來")
            qs.append("模擬器的感測器數據什麼時候開始進來？之前有哪些警告？")
        else:
            t = slots.take(6, earliest=earliest)
            if t is None:
                return
            br.isaac_down(t)
            slots.used.append((t, sim.duration))
            if nav is not None:
                for tp in ISAAC_WATCHED:
                    nav.watch_lost(tp, t, sim.duration + 1)
            notes.append(f"+{t:.1f}s Isaac Sim 關掉（感測器 Topic 停止，bridge 的稽核發現來源沒有 publisher）")
            qs.append("感測器的數據為什麼停了？")
        return
    kind = rng.choice(["start", "start_warn", "dup", "dup", "stop"])
    if kind in ("start", "start_warn"):
        t = slots.take(3)
        if t is None:
            return
        br.start(t, warn_env=kind == "start_warn")
        notes.append(f"+{t:.1f}s bridge 啟動" + ("（環境變數 ROBOT_NS 跟 .env 不同，WARN）" if kind == "start_warn" else "（只有 INFO）"))
        qs.append("bridge 啟動時的設定是什麼？有沒有警告？")
    elif kind == "dup":
        d = round(rng.uniform(6, 20), 2)
        t = slots.take(d + 6)
        if t is None:
            return
        br.duplicate(t, d)
        notes.append(f"+{t:.1f}s 同一台機器人又啟動一個 bridge，{d:.0f} 秒後停掉（重複的 publisher WARN）")
        qs.append("bridge 為什麼一直警告有兩個 publisher？什麼時候恢復？")
    else:
        t = slots.take(3)
        if t is None:
            return
        br.stop(t)
        slots.used.append((t, sim.duration))
        notes.append(f"+{t:.1f}s bridge 停止（只有 INFO）")
        qs.append("bridge 什麼時候停止的？轉送了多少則？")
