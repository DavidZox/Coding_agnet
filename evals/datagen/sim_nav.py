"""amr_base_sw 的模擬（導航：task_agent → GlobalPlanner → RouteExecutor → LocalNav／旋轉、直線伺服 → VelocityMux；
RobotStateBroadcaster、Diagnostics 監看），照目錄的 Topic、Log 原文（file／function／line）與情境（正常任務、卡住放棄、暫時阻擋、
現場停止、定位跳動、監看的 Topic 斷訊）。字串 Topic 很多：/lp_state、/local_replanner/formal_state、/cmd_vel_source…（狀態），
/robot_state、/amr_diagnostics、/current_station 是 JSON 字串。"""
import json
import math

from sim_core import Alive, Motion, Signal, header, quat_yaw, twist

ROOT = "/workspaces/amr_base/install/amr_base_sw/lib/python3.12/site-packages/amr_base_sw"
F = {"TA": f"{ROOT}/TaskAgent/task_agent.py", "GP": f"{ROOT}/GlobalPlanner/GlobalPlannerNode.py", "MG": f"{ROOT}/GlobalPlanner/MapGraph.py",
     "RE": f"{ROOT}/GlobalPlanner/RouteExecutorNode.py", "LN": f"{ROOT}/LocalPlanner_Controller/navigation/ros_nodes/LocalNavNode.py",
     "TICK": f"{ROOT}/LocalPlanner_Controller/navigation/ros_nodes/nav_fsm/tick.py",
     "HOLD": f"{ROOT}/LocalPlanner_Controller/navigation/ros_nodes/nav_fsm/holding.py",
     "SEG": f"{ROOT}/LocalPlanner_Controller/navigation/ros_nodes/nav_fsm/segment.py",
     "FOL": f"{ROOT}/LocalPlanner_Controller/navigation/ros_nodes/nav_fsm/following.py",
     "PRE": f"{ROOT}/LocalPlanner_Controller/navigation/ros_nodes/nav_fsm/pre_spin.py",
     "FIN": f"{ROOT}/LocalPlanner_Controller/navigation/ros_nodes/nav_fsm/final.py",
     "MONI": f"{ROOT}/LocalPlanner_Controller/navigation/ros_nodes/nav_fsm/monitors.py",
     "AW": f"{ROOT}/LocalPlanner_Controller/common/ros_nodes/ActionWrapper.py",
     "SPIN": f"{ROOT}/LocalPlanner_Controller/common/ros_nodes/ClosedLoopSpinServer.py",
     "DRV": f"{ROOT}/LocalPlanner_Controller/common/ros_nodes/StraightLineDriveServer.py",
     "FT": f"{ROOT}/LocalPlanner_Controller/docking/ros_nodes/FinetuneController.py",
     "RSB": f"{ROOT}/AsyncToRealtimeAdapter/RobotStateBroadcaster.py", "DIAG": f"{ROOT}/Diagnostic/Diagnostic.py"}
# 預設地圖（fih_humanoid_amrScene）的節點座標
NODES = {7: (-0.29, -0.453), 10: (-0.874, -2.855), 11: (2.729, -2.855), 12: (5.097, -2.855), 13: (8.116, -2.855), 2: (8.066, -1.026),
         0: (9.334, -1.026)}
ROUTES = {13: [7, 10, 11, 12, 13], 2: [7, 10, 11, 12, 13, 2], 0: [7, 10, 11, 12, 13, 2, 0], 10: [7, 10]}


class Nav:
    """情境：mission(t, goal, outcome)；outcome＝done／blocked_fail（卡住 15 秒放棄）／temp_block（暫停幾秒再走）／
    operator_stop（現場停止）／loc_jump（定位跳動、停車等穩定）。watch_lost(topic, t0, t1)：Diagnostics 監看的 Topic 斷訊。"""

    def __init__(self, sim, own_sensors=True):
        self.sim, self.rng = sim, sim.rng
        self.v, self.w = Signal(0.0), Signal(0.0)
        self.missions = []
        self.own_sensors = own_sensors
        self.watch = {}      # topic → [(t0, t1)] 斷訊
        self.unseen = None   # ([topic], 第一次收到的時間)：之前一直沒收到過
        self.mid = 1792202400 + sim.rng.randint(0, 9000)

    def mission(self, t, goal=13, outcome="done", **kw):
        self.missions.append((t, goal, outcome, kw))

    def watch_lost(self, topic, t0, t1):
        self.watch.setdefault(topic, []).append((t0, t1))

    def watch_unseen(self, topics, t_seen):
        """監看的 Topic 到 t_seen 之前一次都沒收到過（例如 Isaac Sim 還沒開）：/diagnostic_status＝未收到完整車輛資訊，每 3 秒一則
        「⏳ 等待訊號初始化」；收到之後一則「訊號恢復」。"""
        self.unseen = (list(topics), t_seen)

    def log(self, t, lvl, node, msg, f, func, line):
        self.sim.log(t, lvl, node, msg, (F[f], func, line))

    # ---- 一個任務
    def _run(self, t0, goal, outcome, kw, st):
        sim, rng = self.sim, self.rng
        route = ROUTES[goal]
        mid = self.mid
        self.mid += rng.randint(30, 400)
        cur = route[0]
        st["target"].publish(t0, {"data": json.dumps({"target_station": str(goal)})})
        self.log(t0 + 0.001, "INFO", "task_agent", f"🎯 目標: {goal}，目前站點: {cur} ()", "TA", "_start_navigation_to", 357)
        self.log(t0 + 0.002, "INFO", "task_agent", f"🗺️ 請求算路: {{'start': {cur}, 'goal': {goal}}}", "TA", "_request_path", 711)
        self.log(t0 + 0.003, "INFO", "task_agent", "🔀 狀態切換: IDLE → WAITING_PATH", "TA", "transition", 261)
        st["display"].publish(t0 + 0.003, {"data": "MOVING"})
        self.log(t0 + 0.012, "INFO", "GlobalPlanner", f"[GP] 收到路徑請求 mission={mid} goal_node={goal} goal_xy=(None,None)", "GP", "_on_request_path", 720)
        skip = [n for n in route[2:-1]]
        if skip:
            self.log(t0 + 0.015, "INFO", "GlobalPlanner", f"[GP] 共線跳過節點: {skip}", "GP", "_plan_and_send", 879)
        self.log(t0 + 0.016, "INFO", "GlobalPlanner", "[GP] 移除零長度終點 T 段（站點目標）", "MG", "_plan_and_send", 1507)
        segs = [route[1], route[-1]] if len(route) > 2 else [route[-1]]
        segs = [route[0]] + segs
        self.log(t0 + 0.018, "INFO", "GlobalPlanner", f"[GP] 路徑規劃完成 mission={mid} segments={len(segs)} nodes={route}", "GP", "_plan_and_send", 919)
        st["planned"].publish(t0 + 0.018, {"layout": {"dim": [], "data_offset": 0}, "data": route})
        self.log(t0 + 0.021, "INFO", "task_agent", f"📬 收到規劃路徑: {route}，GP 已直接下達 RE，切換執行狀態", "TA", "planned_path_callback", 580)
        self.log(t0 + 0.022, "INFO", "task_agent", "🔀 狀態切換: WAITING_PATH → EXECUTING", "TA", "transition", 261)
        self.log(t0 + 0.023, "INFO", "RobotStateBroadcaster", f"📋 station_sequence 更新: {[10000] + route}", "RSB", "_station_sequence_callback", 200)
        self.log(t0 + 0.024, "INFO", "RouteExecutor", f"[RE] 收到 route_plan mission={mid} replan=0 segments={len(segs)}", "RE", "_on_route_plan", 172)
        st["seq_state"].set(t0 + 0.023, "running")
        st["bt"].publish(t0 + 0.041, {"data": "RunAllSegments"})
        self.log(t0 + 0.041, "INFO", "RouteExecutor", "[BT] → RunAllSegments", "RE", "_bt_tick", 270)
        t = t0 + 0.04
        pos = NODES[route[0]]
        for i, node in enumerate(segs):
            final = i == len(segs) - 1
            target = NODES[node]
            dist = math.hypot(target[0] - pos[0], target[1] - pos[1])
            self.log(t, "INFO", "RouteExecutor", f"[RE] 發送段落 →#{node} 給 LP，{2 + i} poses → 加密後 {max(7, int(dist / 0.1) + 1)} poses",
                     "RE", "_send_segment_to_lp", 353)
            spin = rng.choice([0.0, 0.0, rng.uniform(25, 125)]) * rng.choice([-1, 1])
            t += 0.01
            if abs(spin) > 20:
                self.log(t, "INFO", "LocalNav", f"🔄 偏航超標，先 Spin {spin:.1f}°", "PRE", "attempt_route_spin_or_follow", 120)
                st["lp"].publish(t + 0.001, {"data": "STATE_ROUTE_SPINNING"})
                self.log(t + 0.003, "INFO", "ClosedLoopSpinServer",
                         f"[旋轉控制] 目標: {spin:+.1f}°  ({math.radians(spin):+.4f} rad)  最大角速度: 0.60 rad/s", "SPIN", "_execute_callback", 104)
                st["source"].publish(t + 0.06, {"data": "spin"})
                d = abs(math.radians(spin)) / 0.55 + 0.6
                self.w.set(t + 0.05, 0.6 if spin > 0 else -0.6)
                self.w.set(t + d - 0.3, 0.0)
                t += d
                self.log(t, "INFO", "ClosedLoopSpinServer", f"[旋轉控制] 完成  目標: {spin:+.1f}°  實際: {spin - 0.2:+.1f}°  誤差: 0.2°",
                         "SPIN", "_execute_callback", 173)
            st["lp"].publish(t + 0.002, {"data": "STATE_ROUTE_FOLLOWING"})
            st["source"].publish(t + 0.05, {"data": "nav"})
            st["segment"].append((t, None))
            self.v.set(t + 0.05, 0.35)
            dur = dist / 0.35 + 0.6
            # 情境在這一段中間發生
            if i == len(segs) - 1 and outcome != "done":
                tb = t + max(1.5, dur * rng.uniform(0.3, 0.6))
                stop = self._incident(tb, outcome, kw, st, mid, i, node)
                if stop is not None:
                    st["segment"][-1] = (st["segment"][-1][0], stop)
                    return stop
                dur += kw.get("hold", 6.0) + 2.1 if outcome in ("temp_block", "loc_jump") else 0
            t += dur
            self.v.set(t - 0.4, 0.0)
            st["segment"][-1] = (st["segment"][-1][0], t)
            self.log(t, "INFO", "LocalNav", "⚙️ 限速已歸零（100%）", "AW", "reset_speed_limit", 146)
            if final:
                self.log(t + 0.01, "INFO", "LocalNav", "🎯 [FinalApproach] 殘餘距離 0.152m，補走 0.102m 後留 5cm 容差", "FIN", "compute_final_approach_drive", 39)
                st["lp"].publish(t + 0.012, {"data": "STATE_ALIGNING"})
                self.log(t + 0.014, "INFO", "StraightLineDriveServer", "[直線控制] 目標: +0.102 m  最大速度: 0.25 m/s", "DRV", "_execute_callback", 113)
                st["source"].publish(t + 0.07, {"data": "drive"})
                self.v.set(t + 0.06, 0.1)
                self.v.set(t + 1.1, 0.0)
                t += 1.2
                self.log(t, "INFO", "StraightLineDriveServer", "[直線控制] 完成  目標: +0.102 m  實際: +0.099 m  誤差: 0.3 cm  (煞停補償 0.0 cm)",
                         "DRV", "_execute_callback", 179)
            st["seg_result"].publish(t + 0.002, {"data": "DONE"})
            st["lp"].publish(t + 0.003, {"data": "STATE_IDLE"})
            self.log(t + 0.02, "INFO", "GlobalPlanner", f"[GP] 段落 {i} 完成", "GP", "_on_segment_status", 979)
            pos = target
            t += 0.03
        st["route_status"].publish(t, {"data": "DONE"})
        self.log(t, "INFO", "RouteExecutor", "[RE] ✅ 任務完成 → DONE", "RE", "_notify_gp", 508)
        st["bt"].publish(t + 0.001, {"data": "NotifyDone"})
        self.log(t + 0.001, "INFO", "RouteExecutor", "[BT] → NotifyDone", "RE", "_bt_tick", 270)
        self.log(t + 0.003, "INFO", "GlobalPlanner", f"[GP] 任務 {mid} 全段完成", "GP", "_on_segment_status", 1011)
        self.log(t + 0.004, "INFO", "task_agent", f"✅ 任務完成，到達站點 {goal}", "TA", "route_status_callback", 647)
        self.log(t + 0.005, "INFO", "task_agent", "🔀 狀態切換: EXECUTING → IDLE", "TA", "transition", 261)
        st["display"].publish(t + 0.005, {"data": "IDLE"})
        st["seq_state"].set(t + 0.006, "standby")
        self.log(t + 0.006, "INFO", "RobotStateBroadcaster", "🔄 sequence.state → standby", "RSB", "_route_status_callback", 222)
        self.log(t + 0.1, "INFO", "LocalNav", "[LR][DIAG] STATE_IDLE: 尚未收到路徑，等待 /global_route_execute", "TICK", "_skip_tick", 80)
        st["source"].publish(t + 1.5, {"data": "none"})
        return t

    def _incident(self, tb, outcome, kw, st, mid, seg_i, node):
        """回傳任務提早結束的時間（None＝之後繼續走）。"""
        sim, rng = self.sim, self.rng
        x, y = rng.uniform(1, 6), -2.86
        trig = (f"[LR][TRIGGER] replan#1/10  robot=({x - 3.6:.2f},{y:.2f})  path=91pts  start_idx=7  is_last=True  碰撞=14pts [#38..#51]  "
                f"首碰距robot={rng.uniform(2.6, 3.8):.2f}m  碰撞距路徑終點=4.23m  路徑終點=(8.12,-2.85)  cost樣本=[83, 99, 100, 100]  threshold=80")
        if outcome == "blocked_fail":
            self.log(tb, "WARN", "LocalNav", trig, "TICK", "_log_trigger", 348)
            self.log(tb + 0.004, "INFO", "LocalNav", f"[LR] 路徑全堵，垂直採樣側方目標 centroid=({x:.2f},{y:.2f})", "LN", "_log_planner_event", 546)
            self.log(tb + 0.006, "INFO", "LocalNav", "[LR] 垂直採樣失敗，3m 內無自由空間（其中2個候選點因為隔著牆被排除）", "LN", "_log_planner_event", 552)
            self.log(tb + 0.008, "WARN", "LocalNav", "[LR][BLOCKED] 進入自救模式（reason=plan_failed），主動命令停止  15.0s內未脫困則轉發FAIL給RE/GP",
                     "HOLD", "enter_blocked", 219)
            st["lp"].publish(tb + 0.009, {"data": "STATE_IDLE"})
            st["blocked"].append((tb, tb + 15.0))
            self.v.set(tb + 0.01, 0.0)
            st["source"].publish(tb + 1.5, {"data": "none"})
            tg = tb + 15.0
            self.log(tg, "ERROR", "LocalNav", f"[LR][GIVEUP] 自救15.0s逾時仍未脫困，轉發FAIL給RE/GP  robot=({x - 3.6:.2f},{y:.2f})",
                     "SEG", "give_up_and_report_fail", 164)
            st["lp"].publish(tg + 0.001, {"data": "STATE_IDLE"})
            st["seg_result"].publish(tg + 0.002, {"data": "FAIL"})
            st["failed"].append(tg)
            self.log(tg + 0.02, "WARN", "RouteExecutor", f"[RE] ⚠️ 段落 {seg_i} 失敗 reason=lp_fail，通知 GP 決定是否重試", "RE", "_notify_gp", 510)
            st["bt"].publish(tg + 0.021, {"data": "NotifyFail"})
            self.log(tg + 0.021, "INFO", "RouteExecutor", "[BT] → NotifyFail", "RE", "_bt_tick", 270)
            self.log(tg + 0.022, "WARN", "GlobalPlanner", f"[GP] 段落 {seg_i} 失敗 reason=lp_fail", "GP", "_on_segment_status", 983)
            self.log(tg + 0.023, "ERROR", "GlobalPlanner", f"[GP] 任務 {mid} 失敗，replan 已關閉（enable_replan=false）", "GP", "_on_segment_status", 993)
            self.log(tg + 0.024, "WARN", "GlobalPlanner", "[GP] ⚠️ 任務失敗（replan 已關閉）", "GP", "_publish_warning", 1268)
            st["route_status"].publish(tg + 0.025, {"data": "FAIL"})
            self.log(tg + 0.026, "ERROR", "task_agent", "❌ RE 路網導航失敗，任務中止", "TA", "_fail_and_idle", 303)
            st["display"].publish(tg + 0.026, {"data": "FAIL"})
            self.log(tg + 0.027, "INFO", "task_agent", "🔀 狀態切換: EXECUTING → IDLE", "TA", "transition", 261)
            st["display"].publish(tg + 0.027, {"data": "IDLE"})
            st["seq_state"].set(tg + 0.028, "fail")
            self.log(tg + 0.028, "INFO", "RobotStateBroadcaster", "🔄 sequence.state → fail", "RSB", "_route_status_callback", 222)
            self.log(tg + 0.1, "INFO", "LocalNav", "[LR][DIAG] STATE_IDLE: 尚未收到路徑，等待 /global_route_execute", "TICK", "_skip_tick", 80)
            sim.expect_log(tg, "ERROR", "[LR][GIVEUP]", key=True, what="LocalNav 放棄這一段")
            sim.expect_value("/route_status", tg + 0.025, "FAIL", key=True, what="任務失敗")
            return tg
        if outcome == "temp_block":
            hold = kw.get("hold", rng.uniform(4, 9))
            kw["hold"] = hold
            self.log(tb, "WARN", "LocalNav", trig, "TICK", "_log_trigger", 348)
            self.log(tb + 0.004, "WARN", "LocalNav", "[LR][BLOCKED] 進入自救模式（reason=space_insufficient），主動命令停止  15.0s內未脫困則轉發FAIL給RE/GP",
                     "HOLD", "enter_blocked", 219)
            self.log(tb + 0.005, "WARN", "LocalNav", f"[LR] 側方空間預檢查不足 目標點外型淨空0.02m<0.05m，跳過規劃直接停  goal=({x:.2f},{y:.2f})",
                     "TICK", "_plan_failed", 396)
            st["lp"].publish(tb + 0.006, {"data": "STATE_IDLE"})
            st["blocked"].append((tb, tb + hold))
            self.v.set(tb + 0.01, 0.0)
            tr = tb + hold
            self.log(tr, "INFO", "LocalNav", "[LR] 路徑恢復通暢，接回原路線", "FOL", "resume_following", 81)
            st["lp"].publish(tr + 0.002, {"data": "STATE_ROUTE_FOLLOWING"})
            self.v.set(tr + 0.05, 0.35)
            st["recover"].append(tr)
            sim.expect_value("/lp_state", tb + 0.006, "STATE_IDLE", key=True, what="暫停")
            sim.expect_value("/lp_state", tr + 0.002, "STATE_ROUTE_FOLLOWING", key=True, what="恢復")
            return None
        if outcome == "operator_stop":
            self.log(tb, "WARN", "task_agent", "🛑 收到 cmd_stop，中止任務 (當前狀態: EXECUTING)", "TA", "cmd_stop_callback", 625)
            st["cmd_stop"].publish(tb - 0.001, {"data": True})
            st["display"].publish(tb + 0.001, {"data": "STOP"})
            self.log(tb + 0.001, "INFO", "task_agent", "🔀 狀態切換: EXECUTING → IDLE", "TA", "transition", 261)
            st["display"].publish(tb + 0.002, {"data": "IDLE"})
            self.log(tb + 0.002, "WARN", "RouteExecutor", "[RE] cmd_stop=True → STOPPING", "RE", "_on_cmd_stop", 250)
            st["lp"].publish(tb + 0.003, {"data": "STATE_IDLE"})
            self.log(tb + 0.003, "INFO", "LocalNav", "[LR] 收到 cmd_stop，結束這個段落（SEGMENT/FOLLOWING/ROUTE），不回報", "SEG", "on_cmd_stop", 107)
            self.log(tb + 0.004, "INFO", "LocalDock", "[FinetuneCtrl] 外部停止", "FT", "stop", 105)
            self.log(tb + 0.005, "INFO", "LocalDock", "⚙️ 限速已歸零（100%）", "AW", "reset_speed_limit", 146)
            self.v.set(tb + 0.01, 0.0)
            self.log(tb + 0.1, "INFO", "LocalNav", "[LR][DIAG] STATE_IDLE: 尚未收到路徑，等待 /global_route_execute", "TICK", "_skip_tick", 80)
            st["source"].publish(tb + 1.5, {"data": "none"})
            sim.expect_log(tb, "WARN", "收到 cmd_stop", key=True, what="現場停止")
            return tb
        if outcome == "loc_jump":
            self.log(tb, "WARN", "LocalNav", "[LR][LOC_JUMP] 定位跳動0.35m/1.2°，先停車等定位穩定", "LN", "_check_localization_jump", 596)
            self.log(tb + 0.001, "WARN", "LocalNav", "[LR][DATA_STALE] 定位剛大幅跳動，等穩定，停車等資料恢復（15s內沒恢復就回報FAIL）",
                     "MONI", "data_safety_hold", 53)
            st["lp"].publish(tb + 0.002, {"data": "STATE_IDLE"})
            st["hold_nostatus"].append((tb, tb + 2.1))
            self.v.set(tb + 0.01, 0.0)
            self.log(tb + 1.0, "INFO", "LocalNav", "[LR][DATA_STALE] 資料已恢復，確認穩定中（1.0s、2張新costmap、車子完全停住）", "MONI", "data_safety_hold", 66)
            self.log(tb + 2.1, "INFO", "LocalNav", "[LR] [DATA_STALE] 確認完畢（共停2.1s），接回原路線", "FOL", "resume_following", 81)
            st["lp"].publish(tb + 2.102, {"data": "STATE_ROUTE_FOLLOWING"})
            self.v.set(tb + 2.15, 0.35)
            kw["hold"] = 0.0
            st["jumps"].append(tb)
            return None
        return None

    # ---- 全部的 Topic
    def build(self):
        sim, rng, D = self.sim, self.rng, self.sim.duration
        st = {"target": sim.events("/target_station", "std_msgs/msg/String"),
              "display": sim.events("/navigation_display", "std_msgs/msg/String"),
              "planned": sim.events("/planned_path", "std_msgs/msg/Int32MultiArray"),
              "bt": sim.onchange("/bt_active_node", "std_msgs/msg/String"),
              "lp": sim.onchange("/lp_state", "std_msgs/msg/String"),
              "source": sim.onchange("/cmd_vel_source", "std_msgs/msg/String", latched=True),
              "seg_result": sim.events("/local_replanner/segment_result", "std_msgs/msg/String"),
              "route_status": sim.events("/route_status", "std_msgs/msg/String"),
              "cmd_stop": sim.events("/cmd_stop", "std_msgs/msg/Bool"),
              "seq_state": Signal("standby"), "segment": [], "blocked": [], "recover": [], "failed": [], "hold_nostatus": [], "jumps": []}
        st["source"].publish(0.0011, {"data": "none"})
        st["bt"].publish(0.0013, {"data": "IDLE"})
        st["lp"].publish(0.0015, {"data": "STATE_IDLE"}) if rng.random() < 0.5 else None
        ends = []
        for t, goal, outcome, kw in sorted(self.missions):
            ends.append(self._run(t, goal, outcome, kw, st))
        motion = Motion(self.v, self.w, x0=-0.29, y0=-0.453, acc=1.0, wacc=2.0)
        jumps = st["jumps"]

        def pose(t):
            x, y, yaw, v, w = motion.at(t)
            dx = 0.35 if any(t >= j for j in jumps) else 0.0
            return x + dx, y, yaw, v, w

        rp = sim.events("/robot_pose_odom", "nav_msgs/msg/Odometry")
        formal = sim.events("/local_replanner/formal_state", "std_msgs/msg/String")
        status = sim.events("/local_replanner/status", "std_msgs/msg/String")
        bstat = sim.events("/base_status", "std_msgs/msg/String")
        bact = sim.events("/base_action_status", "std_msgs/msg/String")
        rstate = sim.events("/robot_state", "std_msgs/msg/String")
        dstat = sim.events("/diagnostic_status", "std_msgs/msg/String")
        adiag = sim.events("/amr_diagnostics", "std_msgs/msg/String")
        mux = sim.events("/cmd_vel_mux", "geometry_msgs/msg/Twist")
        for s, r in ((rp, 10), (formal, 10), (status, 10), (bstat, 2), (bact, 10), (rstate, 10), (dstat, 1), (adiag, 1), (mux, 20)):
            s.rate = r
        segs, blocked, recover, failed, nost = st["segment"], st["blocked"], st["recover"], st["failed"], st["hold_nostatus"]

        def in_any(t, ivs):
            return any(a <= t < (b if b is not None else D) for a, b in ivs)

        t = rng.uniform(0, 0.1)
        while t < D:
            x, y, yaw, v, w = pose(t)
            rp.publish(t, {"header": header(sim, t, "map"), "child_frame_id": "L_BASE_FOOTPRINT",
                           "pose": {"pose": {"position": {"x": round(x, 4), "y": round(y, 4), "z": 0.0}, "orientation": quat_yaw(yaw)},
                                    "covariance": [0.0] * 36}, "twist": {"twist": twist(round(v, 4), round(w, 4)), "covariance": [0.0] * 36}})
            if in_any(t, blocked):
                fs = "HOLDING"
            elif any(0 <= t - r < 0.1 for r in recover):
                fs = "RECOVERING"
            elif any(f <= t < f + 0.1 for f in failed):
                fs = "FAILED"
            elif in_any(t, segs):
                fs = "TRACKING"
            else:
                fs = "IDLE"
            formal.publish(t + 0.0003, {"data": fs})
            if in_any(t, segs) and not in_any(t, nost):
                status.publish(t + 0.0004, {"data": "BLOCKED" if in_any(t, blocked) else "CLEAR"})
            seq = st["seq_state"].at(t)
            bact.publish(t + 0.0005, {"data": "following" if seq == "running" else "standby"})
            rstate.publish(t + 0.0006, {"data": json.dumps({"robot_id": "tb1", "priority": 10, "current_state": {
                "x": round(x, 4), "y": round(y, 4), "theta": round(yaw, 4), "v": round(v, 4), "omega": round(w, 4),
                "sim_timestamp": round(sim.t0 + t, 2), "current_edge": "", "target_id": "", "is_arrived": False, "distance_to_target": None,
                "battery_level": 0.85, "is_charging": False}, "sequence": {"robot_name": "tb1", "workstations": [], "priority": 10,
                                                                           "state": seq, "timestamp": 0}}, ensure_ascii=False)})
            if abs(v) > 0.01 or abs(w) > 0.01:
                mux.publish(t + 0.001, twist(round(v, 3), round(w, 3)))
            t += 0.1 * (1 + rng.gauss(0, 0.003))
        t = rng.uniform(0, 0.5)
        while t < D:
            bstat.publish(t, {"data": "DONE"})
            t += 0.5 * (1 + rng.gauss(0, 0.003))
        # Diagnostics：監看的 Topic 斷訊 0.5 秒（wall）就 ERROR；每 3 秒印一次；恢復時一則「訊號恢復」
        t, prev, warned = rng.uniform(0, 1.0), "OK", -10.0
        while t < D:
            lost = [tp for tp, ivs in self.watch.items() if any(a + 0.5 <= t < b for a, b in ivs)]
            if self.unseen and t < self.unseen[1]:
                cur = "未收到完整車輛資訊"
                if t - warned >= 3.0:
                    self.log(t + 0.001, "WARN", "Diagnostics", f"⏳ 等待訊號初始化: {', '.join(self.unseen[0])}", "DIAG", "health_check_loop", 176)
                    warned = t
            elif lost:
                cur = "ERROR"
                if t - warned >= 3.0:
                    self.log(t + 0.001, "WARN", "Diagnostics", f"❌ 訊號丟失: {', '.join(lost)}", "DIAG", "health_check_loop", 181)
                    warned = t
            else:
                cur = "訊號恢復" if prev == "ERROR" else "OK"
                if prev == "ERROR":
                    self.log(t + 0.001, "INFO", "Diagnostics", "🔄 訊號恢復正常", "DIAG", "health_check_loop", 189)
            dstat.publish(t, {"data": cur})
            adiag.publish(t + 0.0005, {"data": json.dumps({"status": "OK", "code": "", "description": "All checks nominal"})})
            prev = "ERROR" if cur in ("ERROR", "未收到完整車輛資訊") else "OK"
            t += 1.0 * (1 + rng.gauss(0, 0.002))
        if self.own_sensors:
            odom = sim.events("/odom", "nav_msgs/msg/Odometry")
            odom.rate = 30
            t = rng.uniform(0, 0.03)
            while t < D:
                x, y, yaw, v, w = motion.at(t)
                odom.publish(t, {"header": header(sim, t, "odom"), "child_frame_id": "L_BASE_FOOTPRINT",
                                 "pose": {"pose": {"position": {"x": x, "y": y, "z": 0.0}, "orientation": quat_yaw(yaw)}, "covariance": [0.0] * 36},
                                 "twist": {"twist": twist(round(v, 4), round(w, 4)), "covariance": [0.0] * 36}})
                t += 1 / 30 * (1 + rng.gauss(0, 0.01))
        self._expect(st)
        return self

    def _expect(self, st):
        sim = self.sim
        for t, f in st["display"].explicit:
            sim.expect_value("/navigation_display", t, f["data"], key=f["data"] in ("FAIL", "STOP"), what=f"導航顯示 {f['data']}")
        for t, f in st["route_status"].explicit:
            sim.expect_value("/route_status", t, f["data"], key=True, what=f"任務結果 {f['data']}")
        prev = None
        for t, f in sorted(st["lp"].explicit, key=lambda x: x[0]):
            if prev is not None and f["data"] != prev and t > 0.01:
                sim.expect_value("/lp_state", t, f["data"], what=f"LocalNav {f['data']}")
            prev = f["data"]
        for a, b in sorted({iv for ivs in self.watch.values() for iv in ivs}):   # 同時斷的幾個 Topic 是同一次 ERROR
            sim.expect_value("/diagnostic_status", a + 0.5, "ERROR", key=True,
                             what=f"Diagnostics 偵測到 {'、'.join(tp for tp, ivs in self.watch.items() if (a, b) in ivs)} 斷訊")
        if self.unseen and self.unseen[1] < sim.duration:
            sim.expect_value("/diagnostic_status", self.unseen[1], "訊號恢復", key=True, what="Diagnostics 收到全部監看的 Topic")
        for key in ("display", "route_status", "lp"):   # 變化事件＝值跟前一則不同（第一則是「第一則訊息」，不算）
            ms = sorted(st[key].explicit, key=lambda x: x[0])
            sim.change_times[st[key].topic] = [ms[i][0] for i in range(1, len(ms)) if ms[i][1]["data"] != ms[i - 1][1]["data"]]
        sim.expect_tags("/cmd_vel_source", not_=("訊息中斷",))
        sim.expect_tags("/lp_state", not_=("訊息中斷",))
