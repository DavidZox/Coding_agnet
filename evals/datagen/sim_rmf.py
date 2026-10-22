"""fih_rmf_system 的模擬（registry、distribute、orchestrtor、adapter 與機器人端的 robot_state／握手），照目錄：
- 機器人每台 10 Hz 發 /{rid}/robot_state（fih_rmf_msgs/RobotState），這是唯一的心跳；registry 1 Hz 發 /fleet_states、/all_fleet_states，
  3 秒沒收到就 REG_ROBOT_OFFLINE；每秒印一張狀態表（4＋N 行 INFO，佔 /rosout 的六成以上）。
- 派工：orchestrtor 收工作包 → distribute 指派 → /{rid}/allocator_status authorize（每 0.5 秒一次直到 yes）→ confirm → 機器人
  running → 到站 → /{rid}/task_exec_fin；adapter 對有限速的機器人 20 Hz 發 /{rid}/speed_limit（之後一直發，不會停）。
- Log 是 event 行（`CODE key=value`，logger `<node>.event`，function emit、line 70／72／74）。"""
import math

from sim_core import Alive, Signal, header

ROOT = "/workspaces/amr_base/install/fih_rmf_system/lib/python3.12/site-packages/fih_rmf_system"
EVENT = f"{ROOT}/event_log.py"
REG = f"{ROOT}/registry/registry.py"
STATIONS = {"1": (2.1, -1.03), "2": (8.07, -1.03), "3": (8.12, -2.86), "4": (5.1, -2.86), "13": (8.116, -2.855), "7": (-0.29, -0.453)}
LINE = {"INFO": 70, "WARN": 72, "ERROR": 74}


def _v(x):
    """event 行的值（event_log.py）：None → -，bool → true/false，浮點最多 3 位小數，空字串或有空白 → JSON 字串。"""
    if x is None:
        return "-"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, float):
        return f"{x:.3f}".rstrip("0").rstrip(".")
    if isinstance(x, (list, tuple)):
        return ",".join(str(i) for i in x) or '""'
    s = str(x)
    return '"' + s + '"' if s == "" or any(c.isspace() or c in '"=' for c in s) else s


class Rmf:
    """情境：task(t, rid, stations)、heartbeat_lost(rid, t, d)、auth_timeout(t, rid)。"""

    def __init__(self, sim, robots=("tb1", "tb2")):
        self.sim, self.rng = sim, sim.rng
        self.robots = list(robots)
        self.alive = {r: Alive() for r in robots}
        self.seq = {r: Signal("standby") for r in robots}
        self.edge = {r: Signal("") for r in robots}
        self.target = {r: Signal("") for r in robots}
        self.pos = {r: (self.rng.uniform(-1, 9), self.rng.uniform(-3, -1)) for r in robots}
        self.moves = {r: [] for r in robots}   # (t0, t1, from_xy, to_xy)
        self.tasks, self.lost, self.auth_to = [], [], []

    def ev(self, t, lvl, node, code, **kw):
        self.sim.log(t, lvl, f"{node}.event", code + "".join(f" {k}={_v(v)}" for k, v in kw.items()), (EVENT, "emit", LINE[lvl]))

    def task(self, t, rid, stations):
        self.tasks.append((t, rid, list(stations)))

    def heartbeat_lost(self, rid, t, d=None):
        if d is None:
            self.alive[rid].stop(t)
        else:
            self.alive[rid].gap(t, d)
        self.lost.append((rid, t, d))

    def auth_timeout(self, t, rid):
        self.auth_to.append((t, rid))

    def _xy(self, rid, t):
        x, y = self.pos[rid]
        for t0, t1, a, b in self.moves[rid]:
            if t >= t1:
                x, y = b
            elif t >= t0:
                f = (t - t0) / (t1 - t0)
                x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        return x, y

    def build(self):
        sim, rng, D = self.sim, self.rng, self.sim.duration
        pkg = f"WP-{rng.randint(100, 999)}"
        for t, rid, stations in sorted(self.tasks):
            task_id = f"{pkg}::0::{rng.randint(0, 9)}"
            self.ev(t, "INFO", "fastapi_resource_bridge", "WEB_PACKAGE_SENT", package=pkg, stations=stations, loop=False, loop_count=None,
                    task_type="regular", task_level="normal", assign=rid)
            self.ev(t + 0.003, "INFO", "orchestrtor", "ORC_PACKAGE_RECEIVED", package=pkg, stations=stations, loop=False, loop_count=None,
                    task_type="regular", task_level="normal", assign=rid)
            td = t + rng.uniform(0.1, 0.5)
            self.ev(td, "INFO", "orchestrtor", "ORC_ITEM_DISPATCHED", item=task_id, package=pkg, station=stations[0], iteration=1)
            self.ev(td + 0.004, "INFO", "distribute", "DST_TASK_RECEIVED", task=task_id, task_type="regular", task_level="normal",
                    station=stations[0], assign=rid, weight=1)
            ta = td + rng.uniform(0.5, 2.0)
            self.ev(ta, "INFO", "distribute", "DST_TASK_ASSIGNED", task=task_id, robot=rid, mode="manual")
            self.ev(ta + 0.5, "INFO", "distribute", "DST_AUTH_START", task=task_id, robot=rid, station=stations[0])
            self.sim.streams.setdefault(f"/{rid}/allocator_status", sim.events(f"/{rid}/allocator_status", "fih_rmf_msgs/msg/AllocatorCommand"))
            alloc = sim.streams[f"/{rid}/allocator_status"]
            hs = sim.streams.get(f"/{rid}/handshake_states") or sim.events(f"/{rid}/handshake_states", "fih_rmf_msgs/msg/HandshakeState")
            fin = sim.streams.get(f"/{rid}/task_exec_fin") or sim.events(f"/{rid}/task_exec_fin", "fih_rmf_msgs/msg/TaskExecutionFinished")
            alloc.publish(ta + 0.5, {"command": "authorize", "task_id": task_id, "type": "regular", "action": "move", "station": f"a{stations[0]}"})
            hs.publish(ta + 0.51, {"is_authored": "yes"})
            self.ev(ta + 0.511, "INFO", "distribute", "DST_HANDSHAKE", robot=rid, is_authored="yes")
            tc = ta + 1.0
            self.ev(tc, "INFO", "distribute", "DST_TASK_CONFIRMED", task=task_id, robot=rid, station=stations[0])
            alloc.publish(tc + 0.001, {"command": "confirm", "task_id": task_id, "type": "", "action": "", "station": ""})
            hs.publish(tc + 0.003, {"is_authored": "no"})
            self.ev(tc + 0.004, "INFO", "distribute", "DST_HANDSHAKE", robot=rid, is_authored="no")
            t_run = tc + rng.uniform(0.05, 0.2)
            self.seq[rid].set(t_run, "running")
            x0 = self._xy(rid, t_run)
            dest = STATIONS.get(stations[0], (rng.uniform(0, 9), -2.86))
            dur = math.hypot(dest[0] - x0[0], dest[1] - x0[1]) / 0.48 + 1.0
            self.moves[rid].append((t_run, t_run + dur, x0, dest))
            self.edge[rid].set(t_run, f"{rng.choice(['0', '2', '7'])}->{stations[0]}")
            self.target[rid].set(t_run, stations[0])
            sp = sim.streams.get(f"/{rid}/speed_limit") or sim.events(f"/{rid}/speed_limit", "nav2_msgs/msg/SpeedLimit")
            sp.rate = 20
            pct = round(rng.uniform(35, 45), 3)
            ts = t_run + rng.uniform(0.5, 1.0)
            self.ev(ts, "INFO", "adapter", "ADP_SPEED_CHANGED", robot=rid, pct=pct, prev=None, edge=self.edge[rid].at(t_run), limit_mps=round(pct * 0.012, 3),
                    stop=False)
            self.ev(ts + 0.026, "INFO", "adapter", "ADP_ROBOT_ADDED", robot=rid, topic=f"/{rid}/speed_limit")
            tt = ts + 0.026
            while tt < D:   # 一直發，任務做完也不停
                sp.publish(tt, {"header": header(sim, tt), "percentage": True, "speed_limit": pct})
                tt += 0.05 * (1 + rng.gauss(0, 0.005))
            t_arr = t_run + dur
            self.edge[rid].set(t_arr, "")
            t_fin = t_arr + rng.uniform(1.8, 2.3)
            if t_fin < D and self.alive[rid].contains(t_fin):
                fin.publish(t_fin, {"task_id": task_id})
                self.ev(t_fin + 0.002, "INFO", "orchestrtor", "ORC_TASK_FIN_RECEIVED", task=task_id, robot=rid)
                self.ev(t_fin + 0.003, "INFO", "orchestrtor", "ORC_ITEM_DONE", item=task_id, robot=rid, package=pkg, station=stations[0],
                        index=f"1/{len(stations)}")
                self.seq[rid].set(t_fin + 2.0, "standby")
                self.target[rid].set(t_fin + 2.0, "")
            sim.expect_value(f"/{rid}/handshake_states", ta + 0.51, "yes", what="機器人接受派工")
            sim.expect_start(f"/{rid}/speed_limit", ts + 0.026, what="開始發限速")
        for t, rid in self.auth_to:
            task_id = f"{pkg}::1::{rng.randint(0, 9)}"
            self.ev(t, "INFO", "distribute", "DST_AUTH_START", task=task_id, robot=rid, station="4")
            alloc = sim.streams.get(f"/{rid}/allocator_status") or sim.events(f"/{rid}/allocator_status", "fih_rmf_msgs/msg/AllocatorCommand")
            k = 0.0
            while k <= 10.0 and t + k < D:
                alloc.publish(t + k, {"command": "authorize", "task_id": task_id, "type": "regular", "action": "move", "station": "a4"})
                k += 0.5
            if t + 10.5 < D:
                self.ev(t + 10.5, "WARN", "distribute", "DST_AUTH_TIMEOUT", task=task_id, robot=rid, timeout_sec=10)
                sim.expect_log(t + 10.5, "WARN", "DST_AUTH_TIMEOUT", key=True, what="機器人沒有回應派工")
        self._robot_streams()
        self._registry()
        return self

    def _robot_streams(self):
        sim, rng, D = self.sim, self.rng, self.sim.duration
        for rid in self.robots:
            s = sim.events(f"/{rid}/robot_state", "fih_rmf_msgs/msg/RobotState")
            s.rate = 10
            t = rng.uniform(0, 0.1)
            while t < D:
                if self.alive[rid].contains(t):
                    x, y = self._xy(rid, t)
                    seq = self.seq[rid].at(t)
                    tgt = self.target[rid].at(t)
                    moving = any(a <= t < b for a, b, _, _ in self.moves[rid])
                    s.publish(t, {"robot_id": rid, "priority": 10, "current_state": {
                        "x": round(x, 4), "y": round(y, 4), "theta": 0.0, "v": 0.48 if moving else 0.0, "omega": 0.0,
                        "sim_timestamp": round(sim.t0 + t, 2), "current_edge": self.edge[rid].at(t), "target_id": tgt,
                        "is_arrived": bool(tgt) and not moving, "distance_to_target": 0.0, "has_distance_to_target": bool(tgt),
                        "battery_level": 0.85, "is_charging": False},
                        "sequence": {"robot_name": rid, "workstations": [tgt] if tgt else [], "priority": 10, "state": seq,
                                     "timestamp": int((sim.t0 + t) * 1000) if seq == "running" else 0}})
                t += 0.1 * (1 + rng.gauss(0, 0.004))
            s.times = [x for x, _ in s.explicit]   # registry 要用（finalize 之前）
            key = lambda m: (m["current_state"]["v"], m["current_state"]["current_edge"], m["current_state"]["target_id"],  # noqa: E731
                             m["current_state"]["is_arrived"], m["current_state"]["has_distance_to_target"],
                             tuple(m["sequence"]["workstations"]), m["sequence"]["state"])
            ex = s.explicit
            sim.change_times[s.topic] = [ex[i][0] for i in range(1, len(ex)) if key(ex[i][1]) != key(ex[i - 1][1])]
            for t0, d in [(t0, d) for r, t0, d in self.lost if r == rid]:
                if d is None:
                    sim.expect_stop(f"/{rid}/robot_state", t0, key=True, what=f"{rid} 的心跳停止")
                else:
                    sim.expect_gap(f"/{rid}/robot_state", t0, d, key=True, what=f"{rid} 的心跳中斷")
            for t, a, b in self.seq[rid].changes():
                if t > 0.05:
                    sim.expect_value(f"/{rid}/robot_state", t, b, key=b == "running", what=f"{rid} sequence.state {a} → {b}")

    def _registry(self):
        """registry 1 Hz：/fleet_states（在線而且 running）、/all_fleet_states、狀態表（INFO）、狀態改變的 event。"""
        sim, rng, D = self.sim, self.rng, self.sim.duration
        fs = sim.events("/fleet_states", "fih_rmf_msgs/msg/FleetStates")
        afs = sim.events("/all_fleet_states", "fih_rmf_msgs/msg/AllFleetStates")
        fs.rate = afs.rate = 1
        rs = {rid: sim.streams[f"/{rid}/robot_state"] for rid in self.robots}
        label = {rid: "WAITING" for rid in self.robots}
        t = rng.uniform(0, 1.0)
        while t < D:
            states, tracked, rows = [], [], []
            for rid in self.robots:
                last = rs[rid].last_before(t)
                age = t - last if last is not None else None
                if last is None:
                    new = "WAITING"
                else:
                    i = rs[rid].times.index(last)
                    msg = rs[rid].explicit[i][1]
                    online = age < 3.0
                    seq = msg["sequence"]["state"]
                    new = "OFFLINE" if not online else {"running": "RUNNING", "standby": "STANDBY", "fail": "FAIL"}[seq]
                    tracked.append({"state": msg, "online": online, "age_sec": round(age, 3)})
                    if online and seq == "running":
                        states.append(msg)
                if new != label[rid]:
                    if new == "OFFLINE":
                        self.ev(t + 0.001, "WARN", "registry", "REG_ROBOT_OFFLINE", robot=rid, prev=label[rid])
                        sim.expect_log(t + 0.001, "WARN", "REG_ROBOT_OFFLINE", key=True, what=f"{rid} 離線")
                    else:
                        self.ev(t + 0.001, "INFO", "registry", "REG_ROBOT_STATUS", robot=rid, prev=label[rid], next=new)
                    label[rid] = new
                color = {"RUNNING": "\x1b[92m", "STANDBY": "\x1b[94m", "OFFLINE": "\x1b[91m"}.get(new, "\x1b[93m")
                if last is None:
                    rows.append(f"{rid:<12} | \x1b[93mWAITING   \x1b[0m |    -     |    -     |        -        |    -    ")
                else:
                    cs = msg["current_state"]
                    rows.append(f"{rid:<12} | {color}{new:<10}\x1b[0m | {cs['x']:>8.2f} | {cs['y']:>8.2f} | {cs['current_edge'] or '-':^15} | "
                                f"{('YES' if cs['is_arrived'] else 'MOVING'):^8}")
            fs.publish(t, {"robots": states})
            afs.publish(t + 0.0002, {"robots": tracked})
            lines = ["\n" + "=" * 90, f"{'Robot ID':<12} | {'Status':<10} | {'X':^8} | {'Y':^8} | {'Edge':^15} | {'Arrived':^8}", "-" * 90] + rows + ["=" * 90]
            for k, ln in enumerate(lines):
                sim.log(t + 0.0005 + k * 0.00002, "INFO", "registry", ln, (REG, "_print_status_table", 111 + min(k, 4)))
            t += 1.0 * (1 + rng.gauss(0, 0.001))
