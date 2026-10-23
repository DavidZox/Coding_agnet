#!/usr/bin/env python3
"""rmf_sim：fih_rmf_system 的沙盒替身（評測用）——一個程序模擬 orchestrtor、distribute（resource_allocator）、
每台機器人的 TaskAgent、web_console（port 8020）與 manual_trigger（port 8002）。交握走真的 ROS 2 topic 與
fih_rmf_msgs 的型別，agent 可以用 ROS2_* 技能觀察，也可以用 ros2 topic pub 或 manual_trigger 介入。

行為照 amr_base/src/fih_rmf_system 的程式（orchestrator.py、resource_allocator.py、msg_codec.py、web_console/*）：
- web_console 收到 work package（POST /api/send_tasks）→ 以 WorkPackage 發到 /incoming_work_packages（外部直接發布的
  WorkPackage 也收）→ orchestrtor 對目前這一站產生 work item（item_id＝{package}::{輪次}::{站序}::{run_id}-{序號}）以
  StationTask 交給 distribute（/incoming_tasks）。工作項只有 DISPATCHED／CONFIRMED：收到 /{rid}/task_exec_fin（task_id 逐字
  等於 item_id）才 CONFIRMED、派下一站；工作包 RUNNING／COMPLETED（完成的一直留在清單）。重複的 package_id 忽略（記一則事件），
  刪除過的 id 可以再送。刪除工作包只讓 orchestrtor 停止派下一站（已經送到 distribute 或機器人正在做的那一站照樣會做完）。
- distribute 每 0.5 秒對配到的機器人發 /{rid}/allocator_status（AllocatorCommand authorize）；機器人回 /{rid}/handshake_states
  （HandshakeState is_authored "yes"/"no"，沒有 task_id，distribute 只看最後一則）；看到 yes 就發 confirm、任務移出 distribute。
  授權逾時（authorize_timeout_sec，預設 10 秒）→ OverPending；待滿 threshold_recovery_sec（預設 10 秒）回 raw 重新配對。
  指定的機器人離線（沒有 /{rid}/robot_state 心跳）就一直等。刪除 OverPending 任務（CancelOverpendingTask）只刪「此刻在
  OverPending」的，而且只把它移出 distribute——orchestrtor 不知道，那一站永遠等不到完成訊號（跟真系統一樣）。
- 站點：拓譜圖節點的 name 可以是空字串（真的 fih_humanoid_amrScene_v2、BadaMap02 都是）；站點值先當名稱查、查不到再當整數 id
  （同 TaskAgent._resolve_station_id）。
- /api/ws 的快照欄位同 msg_codec.distribute_ui_state_to_dict／orchestrator_ui_state_to_dict（沒有模擬器專用的欄位；params 是 {}，
  同真的 web_console）；伺服器每 --ws-ping-interval 秒（預設 20，同 uvicorn）ping 一次，--ws-ping-timeout 秒內沒有 pong 就以
  close 1011 斷線。
- manual_trigger：POST /batch_handshake [{robot_name, is_authored}]、POST /batch_task_exec_fin [{robot_name, task_id}]。

機器人的行為（config 的 behavior）：
  normal         照 R1：閒置且站點有效就接下、回 yes；正在做這筆或做過這筆也回 yes；忙別的回 no。做完發 task_exec_fin。
  busy           一律回 no（例如定位異常、手動模式）。
  silent         不回應授權（TaskAgent 沒有在跑）；心跳照常。
  lost_fin       照常接單、移動到站，但沒有發 task_exec_fin（工作包會停在這一站）。
  lost_fin_once  只有第一次完成時沒有發 task_exec_fin（訊息遺失一次），之後照常。
  lost_yes_once  每筆任務的第一次授權不回應，之後照常。
  slow           照常，但移動非常慢（做不完）。
  offline        沒有心跳、不回應。

設定（--config 的 JSON）：robots、packages（預先放的工作包，可帶 _preset_items）、nodes／edges（拓譜圖）、params（含
cancel_latency_sec：DELETE 之後過多久才生效，預設 0；測 OverPending 刪除的時序用）、done_ids。
評測用的額外端點（真的 web_console 沒有）：GET /api/sim_state（完整狀態、每一則 topic 訊息的紀錄與來源；packages 的 stations
換成站點名稱，同一個 id 刪除後再送的寫成 id#2）、GET /api/received。

    python3 rmf_sim.py --config config.json            # 容器裡（ROS 2 Jazzy＋fih_rmf_msgs）
    python3 rmf_sim.py --config config.json --no-ros   # 主機上測狀態機與 HTTP（不發 ROS topic）
"""
import argparse
import base64
import copy
import hashlib
import json
import math
import os
import socket
import struct
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WS_PUSH_SECONDS = 0.5
WS_PING = {"interval": 20.0, "timeout": 20.0}       # uvicorn（websockets）的預設

DEFAULT_NODES = [
    {"id": 0, "name": "home", "label": "充電待命區", "description": "【拓譜代號 home】機器人待命與充電位置。", "x": 0.0, "y": 0.0},
    {"id": 1, "name": "a0", "label": "加工線通道-6", "description": "【拓譜代號 a0／角色：轉角銜接點】", "x": 2.0, "y": 0.0},
    {"id": 2, "name": "a3", "label": "組裝線區-1", "description": "【拓譜代號 a3】組裝線第一個取料點。", "x": 4.0, "y": 0.0},
    {"id": 3, "name": "a4", "label": "a4", "description": "", "x": 6.0, "y": 0.0},
    {"id": 4, "name": "a6", "label": "a6", "description": "", "x": 6.0, "y": 2.0},
    {"id": 5, "name": "a7", "label": "組裝線區-2", "description": "【拓譜代號 a7】卸料點，旁有輸送帶。", "x": 4.0, "y": 2.0},
    {"id": 6, "name": "a8", "label": "a8", "description": "", "x": 2.0, "y": 2.0},
]
DEFAULT_EDGES = [
    {"id": 34, "start_id": 1, "end_id": 2, "label": "加工線通道：a0↔a3", "description": "【路段 a0→a3】主要雙向通道。", "points": [[2, 0], [4, 0]]},
    {"id": 35, "start_id": 2, "end_id": 5, "label": "", "description": "", "points": [[4, 0], [4, 2]]},
]
DEFAULT_ROBOTS = [
    {"id": "tb1", "station": "home", "battery": 82.0, "behavior": "normal"},
    {"id": "tb2", "station": "a0", "battery": 76.5, "behavior": "normal"},
    {"id": "tb3", "station": "a8", "battery": 64.0, "behavior": "normal"},
]
BEHAVIORS = {"normal", "busy", "silent", "lost_fin", "lost_fin_once", "lost_yes_once", "slow", "offline"}
UI_EVENTS = {"distribute": 10, "orchestrtor": 20}   # 真的 dashboard 只留最近 10／20 則


def now():
    return time.time()


def hhmmss(ts=None):
    return time.strftime("%H:%M:%S", time.localtime(ts or now()))


# ================================================================ 狀態機（純 Python，不依賴 ROS）
class Robot:
    def __init__(self, spec, sim):
        self.id = spec["id"]
        self.behavior = spec.get("behavior", "normal")
        if self.behavior not in BEHAVIORS:
            raise ValueError(f"未知的 behavior：{self.behavior}")
        st = sim.resolve_station(spec.get("station", "home")) or sim.nodes[0]
        self.station = st["_ref"]
        self.x, self.y, self.theta = float(spec.get("x", st["x"])), float(spec.get("y", st["y"])), 0.0
        self.battery = float(spec.get("battery", 80.0))
        self.speed = float(spec.get("speed", 0.02 if self.behavior == "slow" else 0.8))
        self.priority = int(spec.get("priority", 0))
        self.state = "IDLE"                 # TaskAgent 自己的狀態：IDLE／RUNNING
        self.task_id = None                 # 正在做的 task（item_id）
        self.target = None                  # 目標站（節點的 ref）
        self.done_ids = list(spec.get("done_ids", []))   # 最近做完的 task_id（R3）
        self.seen_auth = set()              # lost_yes_once：已經看過一次授權的 task
        self.fin_lost = 0                   # lost_fin_once：已經遺失過幾次
        self.v = 0.0

    @property
    def online(self):
        return self.behavior != "offline"

    @property
    def seq_state(self):
        """RobotState.sequence.state（真的機器人：running／standby／fail）。"""
        return "running" if self.state == "RUNNING" else "standby"


class Item:
    def __init__(self, item_id, station, description, pkg):
        self.item_id, self.station, self.description = item_id, station, description
        self.status = "DISPATCHED"          # DISPATCHED → CONFIRMED（收到 task_exec_fin）
        self.dispatched_at, self.confirmed_at = now(), None
        self.robot_id = None
        self.waiting_for_robot = True
        self.package_id = pkg.package_id


class Package:
    def __init__(self, req):
        self.package_id = req["task_id"]
        self.task_type = req.get("task_type", "regular") or "regular"
        self.level = req.get("level", "normal") or "normal"
        self.weight = req.get("weight", 0) or 0
        self.assign_amr = req.get("assign_amr") or ""
        self.loop = bool(req.get("loop", False))
        self.loop_count = req.get("loop_count")
        self.stations = [(s.get("station", "home"), s.get("description") or "") for s in req.get("stops", []) if s.get("station")]
        self.status = "RUNNING"
        self.iteration, self.station_index = 0, 0
        self.items = []
        self.cancelled = False
        self.created_at = self.updated_at = now()

    @property
    def current_item(self):
        return self.items[-1] if self.items else None


class DTask:
    """distribute 裡的一筆單站任務。"""

    def __init__(self, task_id, task_type, level, weight, assign, station):
        self.id, self.type, self.level, self.weight, self.assign, self.station = task_id, task_type, level, weight, assign, station
        self.created = now()
        self.robot = None
        self.auth_start = None
        self.last_auth = 0.0
        self.ovp_start = None
        self.auth_count = 0
        self.blocked = None                 # 指定的機器人不能接的原因（offline／busy）
        self.blocked_at = 0.0               # 上一次記「攔截」事件的時間


class Sim:
    def __init__(self, cfg, bus=None):
        self.lock = threading.RLock()
        self.cfg = cfg
        self.bus = bus
        self.t0 = now()
        self.run_id = uuid.uuid4().hex[:8]      # 同 orchestrator._run_id：item_id 的代號
        self.nodes = [dict(n) for n in (cfg.get("nodes") or DEFAULT_NODES)]
        for n in self.nodes:
            n["name"] = (n.get("name") or "").strip()
            n["_ref"] = n["name"] or str(n.get("id"))
        self.edges = cfg.get("edges") if cfg.get("edges") is not None else DEFAULT_EDGES
        self.stations = {n["_ref"]: n for n in self.nodes}          # ref（名稱，沒有名稱用 id）→ 節點
        self.by_name = {n["name"]: n for n in self.nodes if n["name"]}
        self.by_id = {str(n.get("id")): n for n in self.nodes}
        self.params = {"authorize_period_sec": 0.5, "authorize_timeout_sec": 10.0, "threshold_ovp_sec": 10.0,
                       "threshold_recovery_sec": 10.0, "heartbeat_timeout_sec": 3.0, "cancel_latency_sec": 0.0}
        self.params.update(cfg.get("params") or {})
        self.robots = {r["id"]: Robot(r, self) for r in (cfg.get("robots") or DEFAULT_ROBOTS)}
        self.packages = {}                  # orchestrtor 的清單（RUNNING 與 COMPLETED；刪除的移出）
        self.history = []                   # 每一個收過的工作包（含刪除的），/api/sim_state 用
        self.raw, self.processing, self.overpending = [], {}, []   # processing: rid → DTask
        self.flags = {rid: "" for rid in self.robots}             # distribute 每台一個 is_authored 旗標
        self.last_heartbeat = {rid: 0.0 for rid in self.robots}
        self.duty = {rid: None for rid in self.robots}             # distribute 眼中的 duty（確認過、還沒做完的 task）
        self.display = {rid: {"state": "standby", "last": "None"} for rid in self.robots}   # 網頁的虛擬顯示狀態（confirm 後鎖成 duty）
        self.seq = 0
        self.step = 0
        self.events, self.orch_events = [], []
        self.log = []                       # 評測用：每一則訊息／HTTP 呼叫（含來源）
        self.expect_own = {}                # (topic) → 自己（機器人／manual_trigger）發出、還沒收到的則數
        self.own_msgs = {}                  # topic → 自己發的內容（web_console 轉發的 WorkPackage／Cancel*）：收到時略過
        self.pending = []                   # 還沒生效的刪除：(生效時間, 種類, id, 來源)
        self.last_tick = {"auth": 0.0, "hb": 0.0, "ui": 0.0}
        self.received = []                  # send_tasks／incoming_work_packages 收到的原始請求
        for req in cfg.get("packages") or []:   # 預先放進來的工作包（例如已經卡住的）
            self._new_package(req, source="preset")
        for rid, ids in (cfg.get("done_ids") or {}).items():
            if rid in self.robots:
                self.robots[rid].done_ids.extend(ids)

    # ------------------------------------------------ 站點
    def resolve_station(self, ref):
        """同 TaskAgent._resolve_station_id：先當名稱查，查不到再當整數 id。"""
        s = str(ref if ref is not None else "").strip()
        if not s or s.lower() == "none":
            return None
        if s in self.by_name:
            return self.by_name[s]
        try:
            return self.by_id.get(str(int(s)))
        except ValueError:
            return None

    def station_label(self, ref):
        """同 distribute 的 _station_label：id 換成名稱，對不到就原樣。"""
        n = self.by_id.get(str(ref).strip())
        return n["name"] if n is not None and n["name"] else ref

    # ------------------------------------------------ 紀錄
    def event(self, text, orch=False):
        line = f"[{hhmmss()}] {text}"
        (self.orch_events if orch else self.events).append(line)
        del (self.orch_events if orch else self.events)[:-200]

    def record(self, kind, **fields):
        self.log.append({"t": round(now() - self.t0, 2), "kind": kind, **fields})
        del self.log[:-5000]

    # ------------------------------------------------ 發布（經 bus；bus 為 None 時只記錄）
    def _publish(self, topic, mtype, fields, own=True, via=None):
        if own:
            self.expect_own[topic] = self.expect_own.get(topic, 0) + 1
        if self.bus:
            self.bus.publish(topic, mtype, fields, via)
        else:   # 沒有 ROS：直接送回自己的訂閱（模擬 DDS 迴圈）
            self.on_message(topic, mtype, fields)

    def _bridge_publish(self, topic, mtype, fields, key):
        """web_console 轉發的訊息：自己的訂閱收到時依內容認出來略過（外部發的同一種訊息照常處理）。"""
        self.own_msgs.setdefault(topic, []).append(key)
        self._publish(topic, mtype, fields, own=False, via="fastapi_resource_bridge")

    def _is_own(self, topic, key):
        keys = self.own_msgs.get(topic) or []
        if key in keys:
            keys.remove(key)
            return True
        return False

    # ------------------------------------------------ orchestrtor
    def _new_package(self, req, source="web_console"):
        pid = req["task_id"]
        if not pid or not [s for s in req.get("stops") or [] if s.get("station")]:
            return False                    # 同 orchestrator.add_package：沒有 id 或沒有站點就略過
        if pid in self.packages:
            self.event(f"⚠️ 忽略重複 package_id: {pid}", orch=True)
            self.record("package_duplicate", package_id=pid, source=source)
            return False                    # 同 orchestrator.add_package：清單裡已有（含 COMPLETED）就忽略
        pkg = Package(req)
        self.packages[pid] = pkg
        self.history.append(pkg)
        self.received.append({k: v for k, v in req.items() if k != "_preset_items"})
        stops = " → ".join(s for s, _ in pkg.stations)
        self.event(f"📦 收到 work package {pid}（{len(pkg.stations)} 站{'，循環' if pkg.loop else ''}：{stops}）", orch=True)
        self.record("package_received", package_id=pid, source=source, stops=[s for s, _ in pkg.stations], assign=pkg.assign_amr)
        if req.get("_preset_items"):        # 預設情境：直接放到某一站、某個狀態
            self._apply_preset(pkg, req["_preset_items"])
        return True

    def _apply_preset(self, pkg, preset):
        pkg.station_index = int(preset.get("station_index", 0))
        pkg.iteration = int(preset.get("iteration", 0))
        self._dispatch(pkg, to_distribute=preset.get("in_distribute", True))
        item = pkg.current_item
        if preset.get("robot"):
            item.robot_id = preset["robot"]
            item.waiting_for_robot = False
            if preset.get("confirmed_by_distribute"):
                self._remove_from_distribute(item.item_id)
                self.duty[preset["robot"]] = item.item_id
                self.display[preset["robot"]] = {"state": "duty", "last": item.item_id}

    def _dispatch(self, pkg, to_distribute=True):
        station, desc = pkg.stations[pkg.station_index]
        self.seq += 1
        item_id = f"{pkg.package_id}::{pkg.iteration}::{pkg.station_index}::{self.run_id}-{self.seq}"
        item = Item(item_id, station, desc, pkg)
        pkg.items.append(item)
        pkg.updated_at = now()
        if to_distribute:
            self._publish("/incoming_tasks", "StationTask", {"task_id": item_id, "task_type": pkg.task_type, "level": pkg.level,
                                                              "weight": int(pkg.weight or 0), "assign_amr": pkg.assign_amr or "",
                                                              "station": station or ""})
            self.event(f"➡️ 派工 {item_id} → distribute（站點 {station}）", orch=True)

    def _orch_tick(self):
        for pkg in list(self.packages.values()):
            if pkg.status != "RUNNING":
                continue
            item = pkg.current_item
            if item is None:
                self._dispatch(pkg)
                continue
            if item.status == "DISPATCHED":
                # 同 orchestrator.update_distribute_tasks：processing 裡是哪台就顯示哪台；raw／OverPending 顯示「等待機器人」
                rid = next((r for r, t in self.processing.items() if t.id == item.item_id), None)
                if rid:
                    item.robot_id, item.waiting_for_robot = rid, False
                elif any(t.id == item.item_id for t in self.raw + self.overpending):
                    item.robot_id, item.waiting_for_robot = None, True
                continue
            pkg.station_index += 1
            if pkg.station_index >= len(pkg.stations):
                pkg.station_index = 0
                pkg.iteration += 1
                should_loop = pkg.loop and (pkg.loop_count is None or pkg.iteration < int(pkg.loop_count))
                if not should_loop:
                    pkg.status = "COMPLETED"
                    pkg.updated_at = now()
                    self.event(f"🏁 work package {pkg.package_id} 完成（共 {pkg.iteration} 輪）", orch=True)
                    self.record("package_completed", package_id=pkg.package_id)
                    continue
            self._dispatch(pkg)

    def cancel_package(self, pid, source="web_console"):
        pkg = self.packages.pop((pid or "").strip(), None)
        if not pkg:
            self.record("package_cancel_miss", package_id=pid, source=source)
            return False
        pkg.cancelled = True
        self.event(f"🗑️ work package {pkg.package_id} 已被使用者刪除", orch=True)
        self.record("package_cancelled", package_id=pkg.package_id, source=source)
        return True

    def _on_task_exec_fin(self, rid, task_id, source):
        self.record("task_exec_fin", robot=rid, task_id=task_id, source=source)
        for pkg in self.packages.values():
            item = pkg.current_item
            if item and item.item_id == task_id and item.status == "DISPATCHED":
                item.status, item.confirmed_at, item.robot_id, item.waiting_for_robot = "CONFIRMED", now(), rid, False
                pkg.updated_at = now()
                self.event(f"✅ {item.item_id}（{pkg.package_id} 第 {pkg.station_index + 1}/{len(pkg.stations)} 站）由 {rid} 回報執行完成", orch=True)
                return
        self.event(f"ℹ️ 收到 {rid} 的 task_exec_fin {task_id}，但沒有對應的進行中工作項", orch=True)

    # ------------------------------------------------ distribute
    def _on_incoming_task(self, fields):
        task_id = str(fields.get("task_id") or "")
        if not task_id or any(t.id == task_id for t in self.raw + self.overpending + list(self.processing.values())):
            return
        assign = str(fields.get("assign_amr") or "").strip()
        station = str(fields.get("station") or "").strip() or "none"
        self.raw.append(DTask(task_id, fields.get("task_type") or "regular", fields.get("level") or "normal",
                              int(fields.get("weight") or 0), assign, station))
        if assign in self.display:          # 同 resource_allocator.submit_task：指定的機器人顯示狀態重置成 standby
            self.display[assign]["state"] = "standby"
        self.event(f"📥 收到任務 {task_id}（站點 {self.station_label(station)}，指定 {assign or '不指定'}）")

    def robot_online(self, rid):
        return now() - self.last_heartbeat.get(rid, 0.0) <= self.params["heartbeat_timeout_sec"]

    def _robot_free(self, rid):
        return self.robot_online(rid) and rid not in self.processing and not self.duty.get(rid)

    def _remove_from_distribute(self, task_id):
        self.raw = [t for t in self.raw if t.id != task_id]
        self.overpending = [t for t in self.overpending if t.id != task_id]
        for rid, t in list(self.processing.items()):
            if t.id == task_id:
                del self.processing[rid]

    def _dist_tick(self):
        t = now()
        # duty 結束：機器人回到 IDLE（真的 distribute 看 robot_state；這裡直接看機器人）
        for rid, task in list(self.duty.items()):
            if task and self.robots[rid].state == "IDLE" and self.robots[rid].task_id is None:
                self.duty[rid] = None
        # OverPending 冷卻完回 raw（同 resource_allocator：等待時間從回流時重新算）
        for task in list(self.overpending):
            if t - task.ovp_start >= self.params["threshold_recovery_sec"]:
                self.overpending.remove(task)
                task.ovp_start, task.robot, task.auth_start, task.created = None, None, None, t
                self.raw.append(task)
                self.event(f"♻️ {task.id} 冷卻結束，回到待派")
        # raw 等太久（threshold_ovp_sec）→ OverPending（同 resource_allocator 的 REPORT）
        expired = [x for x in self.raw if t - x.created > self.params["threshold_ovp_sec"]]
        if expired:
            for task in expired:
                self.raw.remove(task)
                task.ovp_start = t
                self.overpending.append(task)
            self.event(f"!! {len(expired)} 件任務等待過久進入 OverPending（{'、'.join(x.id for x in expired)}）")
        # raw → 配對機器人
        for task in list(self.raw):
            if task.assign:
                if task.assign in self.robots and self._robot_free(task.assign):
                    cands = [task.assign]
                else:
                    reason = "offline" if task.assign not in self.robots or not self.robot_online(task.assign) else "busy"
                    # 同 resource_allocator：每一輪配對（EVALUATION）都在網頁的事件列表記一次「攔截」；這裡限成每 2 秒一次
                    if task.blocked != reason or t - task.blocked_at >= 2.0:
                        task.blocked, task.blocked_at = reason, t
                        what = "已離線，等待恢復" if reason == "offline" else "忙碌中"
                        self.event(f"攔截: 指定機器人 {task.assign} {what} ({task.id})")
                    cands = []
            else:
                cands = sorted(r for r in self.robots if self._robot_free(r))
            if not cands:
                continue
            rid = cands[0]
            self.raw.remove(task)
            task.robot, task.auth_start, task.last_auth, task.auth_count, task.blocked = rid, t, 0.0, 0, None
            self.processing[rid] = task
            self.flags[rid] = ""
            self.event(f"🎯 {task.id} 配對 {rid}，開始授權")
        # 授權迴圈
        for rid, task in list(self.processing.items()):
            if self.flags.get(rid) == "yes":
                del self.processing[rid]
                self.flags[rid] = ""
                self.duty[rid] = task.id
                self.display[rid] = {"state": "duty", "last": task.id}
                self._publish(f"/{rid}/allocator_status", "AllocatorCommand", {"command": "confirm", "task_id": task.id,
                              "type": "", "action": "", "station": ""})
                self.event(f"🤝 {rid} 回 yes → confirm {task.id}")
                self.record("confirm", robot=rid, task_id=task.id)
                continue
            if t - task.auth_start >= self.params["authorize_timeout_sec"]:
                del self.processing[rid]
                task.ovp_start = t
                self.overpending.append(task)
                self.event(f"⏰ {task.id} 授權逾時（{rid} 沒有回 yes）→ OverPending")
                self.record("authorize_timeout", robot=rid, task_id=task.id, attempts=task.auth_count)
                continue
            if t - task.last_auth >= self.params["authorize_period_sec"]:
                task.last_auth = t
                task.auth_count += 1
                self._publish(f"/{rid}/allocator_status", "AllocatorCommand", {"command": "authorize", "task_id": task.id,
                              "type": task.type, "action": "move", "station": task.station})

    def cancel_overpending(self, task_id, source="web_console"):
        task_id = (task_id or "").strip()
        hit = next((t for t in self.overpending if t.id == task_id), None)
        if not hit:
            where = ("raw" if any(t.id == task_id for t in self.raw) else
                     "processing" if any(t.id == task_id for t in self.processing.values()) else None)
            self.record("overpending_cancel_miss", task_id=task_id, source=source, where=where)
            return False
        self.overpending.remove(hit)
        self.event(f"🗑️ OverPending 任務 {task_id} 已刪除")
        self.record("overpending_cancelled", task_id=task_id, source=source)
        return True

    # ------------------------------------------------ 刪除的請求（web_console 轉發成 topic；可設定延遲，模擬 DELETE 晚到）
    def request_cancel(self, kind, ident, source="web_console"):
        topic, mtype, field = (("/cancel_work_package", "CancelWorkPackage", "package_id") if kind == "package"
                               else ("/cancel_overpending_task", "CancelOverpendingTask", "task_id"))
        self._bridge_publish(topic, mtype, {field: ident}, ident)
        latency = float(self.params.get("cancel_latency_sec") or 0.0)
        if latency <= 0:
            self._apply_cancel(kind, ident, source)
        else:
            self.pending.append((now() + latency, kind, ident, source))

    def _apply_cancel(self, kind, ident, source):
        if kind == "package":
            self.cancel_package(ident, source)
        else:
            self.cancel_overpending(ident, source)

    # ------------------------------------------------ 機器人（TaskAgent）
    def _robot_on_command(self, rid, cmd):
        r = self.robots[rid]
        if not r.online or r.behavior == "silent":
            return
        if cmd.get("command") == "confirm":
            return                          # R6：confirm 不用回應
        task_id, station = cmd.get("task_id"), cmd.get("station")
        if r.behavior == "lost_yes_once" and task_id not in r.seen_auth:
            r.seen_auth.add(task_id)
            return
        if r.behavior == "busy":
            return self._handshake(rid, "no")
        if task_id == r.task_id or task_id in r.done_ids:       # R1／R3
            if task_id in r.done_ids and r.behavior not in ("lost_fin", "lost_fin_once"):
                self._publish(f"/{rid}/task_exec_fin", "TaskExecutionFinished", {"task_id": task_id})
            return self._handshake(rid, "yes")
        node = self.resolve_station(station)
        if r.state == "IDLE" and node is not None:             # R4（站點解析不出來：不受理、不回 yes，同 TaskAgent）
            r.state, r.task_id, r.target = "RUNNING", task_id, node["_ref"]
            self.event(f"🚚 {rid} 接下 {task_id}，前往 {node['_ref']}")
            return self._handshake(rid, "yes")
        if node is None:
            return
        return self._handshake(rid, "no")

    def _handshake(self, rid, value):
        self._publish(f"/{rid}/handshake_states", "HandshakeState", {"is_authored": value})

    def _robots_tick(self, dt):
        for rid, r in self.robots.items():
            if r.state != "RUNNING" or not r.target:
                r.v = 0.0
                continue
            st = self.stations[r.target]
            dx, dy = st["x"] - r.x, st["y"] - r.y
            dist = math.hypot(dx, dy)
            step = r.speed * dt
            r.battery = max(0.0, r.battery - 0.02 * dt)
            if dist <= step or dist < 1e-6:
                r.x, r.y, r.v = st["x"], st["y"], 0.0
                r.station = r.target
                done, r.task_id, r.target, r.state = r.task_id, None, None, "IDLE"
                r.done_ids = (r.done_ids + [done])[-100:]
                self.event(f"📍 {rid} 抵達 {r.station}，{done} 完成")
                if r.behavior == "lost_fin" or (r.behavior == "lost_fin_once" and r.fin_lost == 0):
                    r.fin_lost += 1
                    self.record("fin_suppressed", robot=rid, task_id=done)
                else:
                    self._publish(f"/{rid}/task_exec_fin", "TaskExecutionFinished", {"task_id": done})
            else:
                r.x += step * dx / dist
                r.y += step * dy / dist
                r.theta = math.atan2(dy, dx)
                r.v = r.speed

    def _heartbeat(self):
        for rid, r in self.robots.items():
            if not r.online:
                continue
            st = self.stations.get(r.target or r.station)
            dist = math.hypot(st["x"] - r.x, st["y"] - r.y) if st else 0.0
            self._publish(f"/{rid}/robot_state", "RobotState", {
                "robot_id": rid, "priority": r.priority,
                "current_state": {"x": round(r.x, 3), "y": round(r.y, 3), "theta": round(r.theta, 3), "v": round(r.v, 3),
                                  "omega": 0.0, "sim_timestamp": round(now() - self.t0, 2),
                                  "current_edge": f"{r.station}->{r.target}" if r.target else "",
                                  "target_id": r.target or "", "is_arrived": r.state == "IDLE",
                                  "distance_to_target": round(dist, 3), "has_distance_to_target": bool(r.target),
                                  "battery_level": round(r.battery, 1), "is_charging": r.station == "home" and r.state == "IDLE"},
                "sequence": {"robot_name": rid, "workstations": [r.target] if r.target else [], "priority": r.priority,
                             "state": r.seq_state, "timestamp": int(now())}})

    # ------------------------------------------------ 收到 topic（ROS 訂閱或 no-ros 的迴圈）
    def on_message(self, topic, mtype, fields):
        with self.lock:
            own = self.expect_own.get(topic, 0) > 0
            if own:
                self.expect_own[topic] -= 1
            if topic == "/incoming_tasks":
                return self._on_incoming_task(fields)
            if topic == "/incoming_work_packages":
                return self._on_work_package(fields)
            if topic in ("/cancel_work_package", "/cancel_overpending_task"):
                kind, key = ("package", "package_id") if topic == "/cancel_work_package" else ("overpending", "task_id")
                ident = str(fields.get(key) or "")
                if not self._is_own(topic, ident):
                    self.record("ros_cancel", topic=topic, id=ident)
                    self._apply_cancel(kind, ident, "ros2")
                return
            parts = topic.strip("/").split("/")
            rid = parts[0] if len(parts) == 2 else None
            if rid not in self.robots:
                return
            leaf = parts[1]
            if leaf == "robot_state":
                self.last_heartbeat[rid] = now()
            elif leaf == "allocator_status":
                if own:
                    self.record("allocator_status", robot=rid, command=fields.get("command"), task_id=fields.get("task_id"))
                self._robot_on_command(rid, fields)
            elif leaf == "handshake_states":
                value = str(fields.get("is_authored", ""))
                src = self._source(topic, own)
                self.record("handshake", robot=rid, value=value, source=src)
                self.flags[rid] = value
            elif leaf == "task_exec_fin":
                self._on_task_exec_fin(rid, str(fields.get("task_id", "")), self._source(topic, own))

    def _on_work_package(self, fields):
        """/incoming_work_packages（WorkPackage）：web_console 自己轉發的略過（已經處理過），外部直接發布的當成新的工作包。"""
        pid = str(fields.get("task_id") or "")
        if self._is_own("/incoming_work_packages", pid):
            return
        req = {"task_id": pid, "task_type": fields.get("task_type"), "level": fields.get("level"), "weight": fields.get("weight"),
               "assign_amr": fields.get("assign_amr"), "loop": bool(fields.get("loop")),
               "loop_count": fields.get("loop_count") if fields.get("has_loop_count") else None,
               "stops": [{"station": s.get("station"), "description": s.get("description") or ""} for s in fields.get("stops") or []]}
        self._new_package(req, source="ros2")

    def _source(self, topic, own):
        if not own:
            return "external"               # agent 自己 ros2 topic pub 的
        bridge = self.expect_own.get("bridge:" + topic, 0)
        if bridge > 0:
            self.expect_own["bridge:" + topic] = bridge - 1
            return "manual_trigger"
        return "robot"

    # ------------------------------------------------ web_console（HTTP 進來的）
    def web_send(self, tasks):
        """POST /api/send_tasks：每個工作包以 WorkPackage 發到 /incoming_work_packages（同 FastAPIBridgeNode.publish_work_package），
        回傳 details（每個工作包的 JSON 文字）。"""
        details = []
        with self.lock:
            self.record("http", method="POST", path="/api/send_tasks", body=tasks)
            for t in tasks:
                data = {"task_id": t.get("task_id"), "task_type": t.get("task_type", "regular"), "level": t.get("level", "normal"),
                        "weight": t.get("weight", 0), "assign_amr": t.get("assign_amr", "tb1"), "loop": bool(t.get("loop", False)),
                        "loop_count": t.get("loop_count"),
                        "stops": [{"station": s.get("station", "home"), "description": s.get("description") or ""}
                                  for s in t.get("stops", [])]}
                self._new_package(dict(data, _preset_items=t.get("_preset_items")) if t.get("_preset_items") else data)
                msg = {k: v for k, v in data.items() if k not in ("loop_count", "stops")}
                msg.update({"weight": int(data["weight"] or 0), "loop_count": int(data["loop_count"] or 0),
                            "has_loop_count": data["loop_count"] is not None, "stops": [dict(x) for x in data["stops"]]})
                self._bridge_publish("/incoming_work_packages", "WorkPackage", msg, str(data["task_id"]))
                details.append(json.dumps(data, ensure_ascii=False))
        return details

    # ------------------------------------------------ manual_trigger
    def manual_handshake(self, rid, value):
        with self.lock:
            self.expect_own["bridge:" + f"/{rid}/handshake_states"] = self.expect_own.get("bridge:" + f"/{rid}/handshake_states", 0) + 1
            self.record("manual_trigger_call", api="batch_handshake", robot=rid, value=value)
            self._publish(f"/{rid}/handshake_states", "HandshakeState", {"is_authored": value}, via="fastapi_handshake_bridge")

    def manual_fin(self, rid, task_id):
        with self.lock:
            self.expect_own["bridge:" + f"/{rid}/task_exec_fin"] = self.expect_own.get("bridge:" + f"/{rid}/task_exec_fin", 0) + 1
            self.record("manual_trigger_call", api="batch_task_exec_fin", robot=rid, task_id=task_id)
            self._publish(f"/{rid}/task_exec_fin", "TaskExecutionFinished", {"task_id": task_id}, via="fastapi_handshake_bridge")

    # ------------------------------------------------ 主迴圈
    def tick(self):
        with self.lock:
            t = now()
            due = [p for p in self.pending if p[0] <= t]
            if due:
                self.pending = [p for p in self.pending if p[0] > t]
                for _, kind, ident, source in due:
                    self._apply_cancel(kind, ident, source)
            dt = min(0.5, t - self.last_tick.get("robot", t)) if self.last_tick.get("robot") else 0.0
            self.last_tick["robot"] = t
            self._robots_tick(dt)
            if t - self.last_tick["hb"] >= 0.5:
                self.last_tick["hb"] = t
                self._heartbeat()
            if t - self.last_tick["auth"] >= 0.1:
                self.last_tick["auth"] = t
                self._dist_tick()
                self._orch_tick()
                self.step += 1
            if self.bus and t - self.last_tick["ui"] >= 1.0:
                self.last_tick["ui"] = t
                self.bus.publish("/distribute_ui_state", "String", {"data": json.dumps(self._dist_snapshot(), ensure_ascii=False)}, None)

    def run(self, stop):
        while not stop.is_set():
            self.tick()
            time.sleep(0.05)

    # ------------------------------------------------ 快照（欄位同 msg_codec 轉出來的 dict，也就是真的 web_console 的 /api/ws）
    def _robot_view(self, rid, r, t):
        online = self.robot_online(rid)
        seen = self.last_heartbeat.get(rid, 0.0) > 0
        disp = self.display[rid]
        view = {"state": disp["state"], "real_state": "OFFLINE", "last_known_state": r.seq_state if seen else None,
                "last_task_id": disp["last"], "status": "OFFLINE",
                "delay": round(t - self.last_heartbeat[rid], 1) if seen else None,
                "x": None, "y": None, "theta": None, "current_edge": None, "target_id": None}
        if online:
            view.update({"real_state": r.seq_state, "status": "ONLINE", "x": round(r.x, 2), "y": round(r.y, 2), "theta": round(r.theta, 2),
                         "current_edge": f"{r.station}->{r.target}" if r.target else "", "target_id": r.target or ""})
        return view

    def _dist_snapshot(self):
        t = now()
        return {
            "step_counter": self.step, "state": "AUTHORIZATION" if self.processing else "REPORT",
            "events": self.events[-UI_EVENTS["distribute"]:],
            "buffer_tasks": [],
            "raw_tasks": [{"id": x.id, "age": round(t - x.created, 1)} for x in self.raw],
            "overpending_tasks": [{"id": x.id, "wait": round(t - x.ovp_start, 1)} for x in self.overpending],
            "processing_tasks": [{"id": x.id, "type": x.type, "robot": rid, "station": self.station_label(x.station)}
                                 for rid, x in self.processing.items()],
            "robots": {rid: self._robot_view(rid, r, t) for rid, r in self.robots.items()},
            "params": {},
        }

    def snapshot(self):
        with self.lock:
            snap = self._dist_snapshot()
            snap["orchestrtor"] = {"step_counter": self.step, "events": self.orch_events[-UI_EVENTS["orchestrtor"]:],
                                   "packages": [self._pkg_view(p) for p in self.packages.values()]}
            return snap

    def _pkg_view(self, p):
        item = p.current_item
        return {"package_id": p.package_id, "status": p.status, "loop": p.loop, "loop_count": p.loop_count,
                "iteration": p.iteration, "station_index": p.station_index, "station_count": len(p.stations),
                "stations": [s for s, _ in p.stations],
                "current_item": None if not item else {"item_id": item.item_id, "station": item.station, "status": item.status,
                                                       "robot_id": item.robot_id, "waiting_for_robot": item.waiting_for_robot},
                "items_done": sum(1 for it in p.items if it.status == "CONFIRMED"), "items_total": len(p.items),
                "updated_at": p.updated_at}

    def state(self):
        """評測用的完整狀態。"""
        with self.lock:
            pk, seen = {}, {}
            for p in self.history:
                seen[p.package_id] = seen.get(p.package_id, 0) + 1
                key = p.package_id if seen[p.package_id] == 1 else f"{p.package_id}#{seen[p.package_id]}"
                pk[key] = self._pkg_full(p)
            return {"t": round(now() - self.t0, 2), "snapshot": self.snapshot(), "packages": pk,
                    "robots": {rid: {"behavior": r.behavior, "state": r.state, "task_id": r.task_id, "station": r.station,
                                     "x": round(r.x, 2), "y": round(r.y, 2), "battery": round(r.battery, 1),
                                     "done_ids": r.done_ids[-20:], "online": self.robot_online(rid)} for rid, r in self.robots.items()},
                    "distribute": {"raw": [x.id for x in self.raw], "overpending": [x.id for x in self.overpending],
                                   "processing": {rid: x.id for rid, x in self.processing.items()}, "duty": dict(self.duty),
                                   "flags": dict(self.flags)},
                    "log": list(self.log), "received": list(self.received)}

    def _pkg_full(self, p):
        v = self._pkg_view(p)
        v["stations_raw"] = v["stations"]
        v["stations"] = [(self.resolve_station(s) or {}).get("_ref", s) for s in v["stations"]]   # 送 id 或名稱都比得到
        v["assign_amr"] = p.assign_amr or None
        v["cancelled"] = p.cancelled
        v["items"] = [{"item_id": it.item_id, "station": it.station, "status": it.status, "robot_id": it.robot_id} for it in p.items]
        return v


# ================================================================ ROS 2 介面
class RosBus:
    """把 Sim 的 publish 變成真的 ROS 2 topic，訂閱同樣的 topic 回呼 Sim.on_message（含外部發的）。"""

    def __init__(self, sim_ref):
        import rclpy
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String
        from fih_rmf_msgs.msg import (AllocatorCommand, CancelOverpendingTask, CancelWorkPackage, HandshakeState, RobotState,
                                      StationTask, TaskExecutionFinished, WorkPackage)
        self.rclpy = rclpy
        rclpy.init()
        self.types = {"String": String, "AllocatorCommand": AllocatorCommand, "HandshakeState": HandshakeState,
                      "RobotState": RobotState, "TaskExecutionFinished": TaskExecutionFinished, "StationTask": StationTask,
                      "WorkPackage": WorkPackage, "CancelWorkPackage": CancelWorkPackage, "CancelOverpendingTask": CancelOverpendingTask}
        self.sim_ref = sim_ref
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.qos = qos
        self.nodes = {name: Node(name) for name in ("resource_allocator", "orchestrtor", "fastapi_resource_bridge",
                                                     "fastapi_handshake_bridge")}
        alloc = self.nodes["resource_allocator"]
        for name, default in (("authorize_period_sec", 0.5), ("authorize_timeout_sec", 10.0), ("threshold_ovp_sec", 10.0),
                              ("threshold_recovery_sec", 10.0)):
            alloc.declare_parameter(name, default)
        self.pubs = {}
        self.lock = threading.Lock()
        self.executor = MultiThreadedExecutor()
        for n in self.nodes.values():
            self.executor.add_node(n)

    def setup_robots(self, robot_ids, params):
        alloc, orch = self.nodes["resource_allocator"], self.nodes["orchestrtor"]
        from rclpy.parameter import Parameter
        alloc.set_parameters([Parameter(k, value=float(v)) for k, v in params.items()
                              if k in ("authorize_period_sec", "authorize_timeout_sec", "threshold_ovp_sec", "threshold_recovery_sec")])
        for rid in robot_ids:
            agent = self.rclpy.node.Node(f"{rid}_task_agent")
            self.nodes[agent.get_name()] = agent
            self.executor.add_node(agent)
            self._pub_node[f"/{rid}/handshake_states"] = agent
            self._pub_node[f"/{rid}/task_exec_fin"] = agent
            self._pub_node[f"/{rid}/robot_state"] = agent
            self._pub_node[f"/{rid}/allocator_status"] = alloc
            alloc.create_subscription(self.types["HandshakeState"], f"/{rid}/handshake_states",
                                      lambda m, t=f"/{rid}/handshake_states": self._cb(t, "HandshakeState", m), self.qos)
            alloc.create_subscription(self.types["RobotState"], f"/{rid}/robot_state",
                                      lambda m, t=f"/{rid}/robot_state": self._cb(t, "RobotState", m), self.qos)
            agent.create_subscription(self.types["AllocatorCommand"], f"/{rid}/allocator_status",
                                      lambda m, t=f"/{rid}/allocator_status": self._cb(t, "AllocatorCommand", m), self.qos)
            orch.create_subscription(self.types["TaskExecutionFinished"], f"/{rid}/task_exec_fin",
                                     lambda m, t=f"/{rid}/task_exec_fin": self._cb(t, "TaskExecutionFinished", m), self.qos)
        alloc.create_subscription(self.types["StationTask"], "/incoming_tasks", lambda m: self._cb("/incoming_tasks", "StationTask", m), self.qos)
        alloc.create_subscription(self.types["CancelOverpendingTask"], "/cancel_overpending_task",
                                  lambda m: self._cb("/cancel_overpending_task", "CancelOverpendingTask", m), self.qos)
        orch.create_subscription(self.types["WorkPackage"], "/incoming_work_packages",
                                 lambda m: self._cb("/incoming_work_packages", "WorkPackage", m), self.qos)
        orch.create_subscription(self.types["CancelWorkPackage"], "/cancel_work_package",
                                 lambda m: self._cb("/cancel_work_package", "CancelWorkPackage", m), self.qos)
        orch.create_subscription(self.types["String"], "/distribute_ui_state", lambda m: None, self.qos)
        self._pub_node["/incoming_tasks"] = orch
        self._pub_node["/distribute_ui_state"] = alloc
        for topic in ("/incoming_work_packages", "/cancel_work_package", "/cancel_overpending_task"):
            self._pub_node[topic] = self.nodes["fastapi_resource_bridge"]

    _pub_node = {}

    def _cb(self, topic, mtype, msg):
        sim = self.sim_ref()
        if sim:
            sim.on_message(topic, mtype, self._to_dict(msg))

    def _to_dict(self, msg):
        from rosidl_runtime_py import message_to_ordereddict
        return json.loads(json.dumps(message_to_ordereddict(msg)))

    def publish(self, topic, mtype, fields, via=None):
        with self.lock:
            pub = self.pubs.get((topic, via))
            if pub is None:
                node = self.nodes.get(via) if via else (self._pub_node.get(topic) or self.nodes["resource_allocator"])
                pub = node.create_publisher(self.types[mtype], topic, self.qos)
                self.pubs[(topic, via)] = pub
        msg = self.types[mtype]()
        if any(isinstance(v, list) and v and isinstance(v[0], dict) for v in fields.values()):
            from rosidl_runtime_py import set_message_fields   # 巢狀陣列（WorkPackage.stops）；它會改掉傳進去的 list，給它一份複本
            set_message_fields(msg, copy.deepcopy(fields))
        else:
            _fill(msg, fields)
        pub.publish(msg)

    def spin(self):
        self.executor.spin()


def _fill(msg, fields):
    for k, v in fields.items():
        if isinstance(v, dict):
            _fill(getattr(msg, k), v)
        else:
            setattr(msg, k, v)


# ================================================================ HTTP（web_console 8020、manual_trigger 8002）
SIM = None


def _ws_frame(opcode, payload=b""):
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += b"\x7e" + struct.pack("!H", n)
    else:
        head += b"\x7f" + struct.pack("!Q", n)
    return head + payload


def _ws_parse(buf):
    """客戶端的幀（有遮罩）：回傳 ((opcode, payload), 用掉的位元組數) 或 None（資料不夠）。"""
    if len(buf) < 2:
        return None
    opcode, masked, n, off = buf[0] & 0x0F, buf[1] & 0x80, buf[1] & 0x7F, 2
    if n == 126:
        if len(buf) < 4:
            return None
        n, off = struct.unpack("!H", buf[2:4])[0], 4
    elif n == 127:
        if len(buf) < 10:
            return None
        n, off = struct.unpack("!Q", buf[2:10])[0], 10
    mask = b""
    if masked:
        if len(buf) < off + 4:
            return None
        mask, off = buf[off:off + 4], off + 4
    if len(buf) < off + n:
        return None
    payload = buf[off:off + n]
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return (opcode, payload), off + n


class WebConsole(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(length) or b"null")

    def _websocket(self):
        """同 allocator_routes.websocket_endpoint：每 0.5 秒推一幀；另外同 uvicorn 的 keepalive：每 interval 秒 ping，
        timeout 秒內沒有 pong 就以 close 1011 斷線。客戶端送 close 就結束。"""
        key = self.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                          f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        self.wfile.flush()
        sock = self.connection
        sock.settimeout(0.05)
        interval, timeout = WS_PING["interval"], WS_PING["timeout"]
        buf, next_push, next_ping, waiting = b"", 0.0, time.monotonic() + interval, None
        try:
            while True:
                t = time.monotonic()
                if t >= next_push:
                    payload = json.dumps(SIM.snapshot(), ensure_ascii=False).encode("utf-8")
                    sock.sendall(_ws_frame(0x1, payload))
                    next_push = t + WS_PUSH_SECONDS
                if interval > 0 and waiting is None and t >= next_ping:
                    waiting = (os.urandom(4), t)
                    sock.sendall(_ws_frame(0x9, waiting[0]))
                if waiting is not None and t - waiting[1] > timeout:
                    sock.sendall(_ws_frame(0x8, struct.pack("!H", 1011) + b"keepalive ping timeout"))
                    break
                try:
                    data = sock.recv(65536)
                except socket.timeout:
                    continue
                if not data:
                    break
                buf += data
                closed = False
                while True:
                    parsed = _ws_parse(buf)
                    if parsed is None:
                        break
                    (opcode, payload), used = parsed
                    buf = buf[used:]
                    if opcode == 0xA and waiting is not None and payload == waiting[0]:
                        waiting, next_ping = None, time.monotonic() + interval
                    elif opcode == 0x9:
                        sock.sendall(_ws_frame(0xA, payload))
                    elif opcode == 0x8:
                        sock.sendall(_ws_frame(0x8, payload[:2]))
                        closed = True
                        break
                if closed:
                    break
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        self.close_connection = True

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/ws" and "websocket" in (self.headers.get("Upgrade") or "").lower():
            return self._websocket()
        if path == "/api/robots":
            return self._json({"robots": sorted(SIM.robots)})
        if path == "/api/stations":       # 同 task_routes._load_stations_from_map：id 是節點 id 字串，label 是 name（沒有就 id）
            return self._json({"stations": [{"id": str(n.get("id")), "label": n["name"] or str(n.get("id"))} for n in SIM.nodes]})
        if path == "/api/topology":       # 同 map_routes.get_topology：label＝語意名稱，沒設定過就是 name
            nodes = []
            for n in SIM.nodes:
                sem = n.get("label") if n.get("label") and n.get("label") != n["name"] else ""
                nodes.append({"id": n.get("id"), "name": n["name"], "label": sem or n["name"], "description": n.get("description") or "",
                              "has_semantic": bool(sem or n.get("description")), "x": n.get("x"), "y": n.get("y")})
            edges = [dict(e, has_semantic=bool(e.get("label") or e.get("description"))) for e in SIM.edges]
            return self._json({"nodes": nodes, "edges": edges, "image": None})
        if path == "/api/received":
            with SIM.lock:
                return self._json({"received": SIM.received, "cancelled": sorted({p.package_id for p in SIM.history if p.cancelled}),
                                   "overpending": [{"id": t.id} for t in SIM.overpending]})
        if path == "/api/sim_state":
            return self._json(SIM.state())
        self._json({"detail": "Not Found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        with SIM.lock:
            if path.startswith("/api/work_packages/") and len(path) > len("/api/work_packages/"):
                pid = unquote(path[len("/api/work_packages/"):])
                SIM.record("http", method="DELETE", path=path)
                SIM.request_cancel("package", pid)
                return self._json({"status": "success", "package_id": pid})
            if path.startswith("/api/overpending_tasks/") and len(path) > len("/api/overpending_tasks/"):
                tid = unquote(path[len("/api/overpending_tasks/"):])
                SIM.record("http", method="DELETE", path=path)
                SIM.request_cancel("overpending", tid)
                return self._json({"status": "success", "task_id": tid})
        self._json({"detail": "Not Found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/send_tasks":
            return self._json({"detail": "Not Found"}, 404)
        try:
            tasks = self._body()
        except ValueError:
            return self._json({"detail": [{"msg": "body 不是合法 JSON"}]}, 422)
        if not isinstance(tasks, list) or not all(isinstance(t, dict) and t.get("task_id") for t in tasks):
            return self._json({"detail": [{"loc": ["body"], "msg": "expected a list of TaskRequest with task_id"}]}, 422)
        details = SIM.web_send(tasks)
        self._json({"status": "success", "count": len(tasks), "details": details})


class ManualTrigger(WebConsole):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/handshake_panel", "/task_exec_fin_panel"):
            body = "<html><body><h3>manual_trigger（沙盒）</h3><p>POST /batch_handshake、POST /batch_task_exec_fin</p></body></html>"
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json({"detail": "Not Found"}, 404)

    def do_DELETE(self):
        self._json({"detail": "Method Not Allowed"}, 405)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            reqs = self._body()
        except ValueError:
            return self._json({"detail": "body 不是合法 JSON"}, 422)
        if not isinstance(reqs, list):
            return self._json({"detail": [{"loc": ["body"], "msg": "value is not a valid list"}]}, 422)
        results = []
        try:
            if path == "/batch_handshake":
                for r in reqs:
                    rid, val = str(r.get("robot_name", "")), str(r.get("is_authored", "yes"))
                    if not rid:
                        return self._json({"detail": [{"loc": ["body", "robot_name"], "msg": "field required"}]}, 422)
                    SIM.manual_handshake(rid, val)
                    results.append({"topic": f"/{rid}/handshake_states", "payload": {"is_authored": val}})
                return self._json({"status": "success", "count": len(reqs), "details": results})
            if path == "/batch_task_exec_fin":
                for r in reqs:
                    rid, tid = str(r.get("robot_name", "")), str(r.get("task_id", ""))
                    if not rid or not tid:
                        return self._json({"detail": [{"loc": ["body"], "msg": "robot_name 與 task_id 都要填"}]}, 422)
                    SIM.manual_fin(rid, tid)
                    results.append({"topic": f"/{rid}/task_exec_fin", "payload": {"task_id": tid}})
                return self._json({"status": "success", "count": len(reqs), "details": results})
        except Exception as e:      # noqa: BLE001  同真的 manual_trigger：發布失敗（例如不合法的 topic 名稱）回 500
            what = "手訊發送失敗" if path == "/batch_handshake" else "任務完成訊號發送失敗"
            return self._json({"detail": f"{what}: {e}"}, 500)
        self._json({"detail": "Not Found"}, 404)


def serve(handler, port, host="0.0.0.0"):
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    global SIM
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default="")
    ap.add_argument("--no-ros", action="store_true")
    ap.add_argument("--host", default="0.0.0.0", help="HTTP 綁定的位址（主機上測試用 127.0.0.1）")
    ap.add_argument("--web-port", type=int, default=8020)
    ap.add_argument("--trigger-port", type=int, default=8002)
    ap.add_argument("--ws-ping-interval", type=float, default=WS_PING["interval"], help="WebSocket ping 間隔秒數（0＝不 ping）")
    ap.add_argument("--ws-ping-timeout", type=float, default=WS_PING["timeout"], help="ping 之後多久沒有 pong 就斷線")
    args = ap.parse_args()
    WS_PING.update(interval=args.ws_ping_interval, timeout=args.ws_ping_timeout)
    cfg = {}
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
    bus = None
    if not args.no_ros:
        holder = {}
        bus = RosBus(lambda: holder.get("sim"))
        SIM = Sim(cfg, bus)
        holder["sim"] = SIM
        bus.setup_robots(sorted(SIM.robots), SIM.params)
    else:
        SIM = Sim(cfg, None)
    stop = threading.Event()
    threading.Thread(target=SIM.run, args=(stop,), daemon=True).start()
    serve(WebConsole, args.web_port, args.host)
    serve(ManualTrigger, args.trigger_port, args.host)
    print(f"🧪 rmf_sim 啟動：web_console :{args.web_port}、manual_trigger :{args.trigger_port}、機器人 "
          f"{', '.join(f'{r.id}({r.behavior})' for r in SIM.robots.values())}{'（no-ros）' if args.no_ros else ''}", flush=True)
    try:
        if bus:
            bus.spin()
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == "__main__":
    main()
