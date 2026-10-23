"""workpackage_status：查 work package 執行狀態——一幀快照，或 --watch 秒 觀察一段時間、整理每個對象的狀態變遷。

資料來自 web_console 的 WebSocket /api/ws 快照（"orchestrtor" 鍵＝work package；其餘＝distribute 佇列、機器人、事件；欄位同
msg_codec.py），站點以 /api/topology 附上語意名稱。一幀只是瞬間；「一段時間內有沒有變化」用 --watch：每個 work package
（狀態／第幾站／第幾輪／機器人）、每個工作項（在 distribute 的哪個佇列：raw／OverPending／processing→機器人／離開 distribute）、
每台機器人（ONLINE／顯示狀態／自報狀態）各是一條狀態序列，用 _ros2_data_common.state_features 算出每次變遷（從什麼到什麼、
什麼時候）、次數與時間占比，太多次只列頭尾（trim_changes）；摘要（結束時的狀態）在前。帶 task_id 時只看那個工作包、它的工作項
與相關的機器人。觀察提早結束（web_console 斷線、停止推送）會寫在第一行。--until-done（要帶工作包）：看到它 COMPLETED 或從
清單消失就結束，不用猜要看幾秒（最多 --watch 的秒數，沒給就 300 秒）；第一幀就沒有它、或它是無限循環（不會完成）立刻回 [ERROR]。
共用層見 _rmf_common.py。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rmf_common as rc   # noqa: E402
from _ros2_data_common import state_features, trim_changes   # noqa: E402

LIST_PACKAGES = 30        # 一幀最多列幾個 work package（RUNNING 一定全列）
LIST_QUEUE = 20           # 每個佇列最多列幾筆
LIST_EVENTS = 6           # 一幀列最近幾則事件（每個來源）
LIST_NEW_EVENTS = 40      # --watch 列期間新增事件的上限（最後 N 則）
LIST_UNCHANGED = 12
GONE_PKG = "（從清單消失：被刪除）"
GONE_ITEM = "（離開 distribute）"

USAGE = (
    "用法: scripts/workpackage_status_cmd.py [task_id] [--watch 秒] [--until-done] [--url 位址]\n"
    "  不帶 task_id：全部 work package、distribute 佇列、機器人、最近事件的一幀快照；task_id 可以是 work package 或工作項（含 ::）。\n"
    f"  --watch 秒（1～{rc.MAX_WATCH_SECONDS}）：持續收幀，整理這段時間每個工作包／工作項／機器人的狀態變遷（時間＝距觀察開始的秒數）。\n"
    f"  --until-done：等這個工作包跑完——看到 COMPLETED 或從清單消失就結束，最多 --watch 的秒數（沒給就 {rc.MAX_WATCH_SECONDS} 秒）；要帶工作包編號。"
)


def parse_args(argv):
    """純函式：回傳 dict（error、task_id、watch、url）。"""
    pos, opts, err = rc.parse_cli(argv, values={"--watch": "秒數（1～300）", "--url": "web_console 位址（例如 http://localhost:8020）"},
                                  flags=("--until-done",), elsewhere={"--cancel": "workpackage_cancel", "--wait": "overpending_cancel", "--amr": "workpackage_send",
                                             "--loop": "workpackage_send", "--stations": "semantic_map", "--robots": "semantic_map",
                                             "--seconds": "rmf_handshake"}, usage=USAGE)
    if err:
        return {"error": err}
    if len(pos) > 1:
        return {"error": f"[ERROR] 只接受一個 task_id，收到 {len(pos)} 個（{'、'.join(pos)}）；要看全部就不要帶 task_id。\n{USAGE}"}
    watch = None
    if "--watch" in opts:
        watch, err = rc.parse_seconds(opts["--watch"], "--watch")
        if err:
            return {"error": f"{err}要看一幀快照就不要加 --watch。"}
    task_id = pos[0].strip() if pos else None
    until_done = bool(opts.get("--until-done"))
    if until_done:
        if not task_id:
            return {"error": "[ERROR] --until-done 要指定工作包（等哪一個跑完）。下一步：workpackage_status <工作包> --until-done；"
                             f"要看全部的變化用 --watch 秒。\n{USAGE}"}
        if "::" in task_id:
            pid = task_id.split("::", 1)[0]
            return {"error": f"[ERROR] --until-done 要用工作包編號（{pid}），不是工作項 {task_id}：工作項會隨站點推進換成新的 id。"
                             f"下一步：workpackage_status {pid} --until-done。"}
        if watch is None:
            watch = rc.MAX_WATCH_SECONDS
    url, err = rc.resolve_url(opts.get("--url"))
    if err:
        return {"error": err}
    return {"error": None, "task_id": task_id, "watch": watch, "until_done": until_done, "url": url}


# ---------------------------------------------------------------- 文字
def _station(ref, topo):
    return rc.station_text(ref, topo)


def item_text(cur, data, topo):
    """目前工作項：id、站點、狀態、在 distribute 的哪裡、機器人。"""
    if not cur:
        return "還沒派出工作項"
    label, t = rc.queue_of(data, cur.get("item_id"))
    rid = cur.get("robot_id")
    if cur.get("status") == "CONFIRMED":
        where = f"這站已由 {rid or '機器人'} 回報完成，下一個週期派下一站"
    elif label:
        where = f"distribute {rc.queue_text(label, t)}" + ("" if label == "processing" else "，⏳ 等待機器人" if cur.get("waiting_for_robot") else "")
    elif rid:
        where = f"distribute 已 confirm 給 {rid}（不在佇列），等 {rid} 回報完成（task_exec_fin）"
    else:
        where = "不在 distribute 佇列" + ("，⏳ 等待機器人" if cur.get("waiting_for_robot") else "")
    return f"工作項 {cur.get('item_id')} {cur.get('status')}（{where}）"


def package_line(p, data, topo):
    stations = p.get("stations") or []
    idx, total = p.get("station_index", 0) or 0, p.get("station_count") or len(stations)
    loop = f"｜循環 {p.get('loop_count') or '∞'} 輪，目前第 {(p.get('iteration') or 0) + 1} 輪" if p.get("loop") else ""
    if p.get("status") == "COMPLETED":
        progress = f"已完成（共 {p.get('iteration', 0)} 輪）"
        loop = ""
    else:
        cur = p.get("current_item") or {}
        progress = f"第 {idx + 1}/{total} 站 {_station(cur.get('station') or (stations[idx] if idx < len(stations) else '?'), topo)}，" \
                   f"{item_text(cur, data, topo)}"
    return (f"- {p.get('package_id')} {p.get('status')}：{progress}{loop}｜完成 {p.get('items_done', 0)} 項（已派 {p.get('items_total', 0)} 項）"
            f"｜路線 {route_text(stations, topo)}")


def route_text(stations, topo):
    """路線：站太多時只列前 4 站與最後 3 站（一行留在 300 字內），中間寫幾站。"""
    names = [_station(s, topo) for s in stations]
    if len(names) <= 8:
        return " → ".join(names)
    return " → ".join(names[:4]) + f" → …（中間 {len(names) - 7} 站，共 {len(names)} 站）→ " + " → ".join(names[-3:])


def robot_line(rid, info, topo):
    info = info or {}
    extra = []
    if info.get("last_task_id") not in (None, "", "None"):
        extra.append(f"最後領取 {info['last_task_id']}")
    if info.get("target_id"):
        extra.append(f"目標 {rc.station_text(info['target_id'], topo, True)}")
    if info.get("status") == "OFFLINE" and info.get("delay") is not None:
        extra.append(f"{info['delay']} 秒沒有心跳")
    return (f"- {rid} {info.get('status', '?')}｜顯示 {info.get('state', '?')}｜自報 {info.get('real_state') or '?'}"
            + (f"｜{'｜'.join(extra)}" if extra else ""))


def queue_lines(data, topo, only=None):
    lines = []
    for key, label in rc.QUEUES:
        entries = [t for t in data.get(key) or [] if isinstance(t, dict) and (only is None or only(t.get("id")))]
        for t in entries[:LIST_QUEUE]:
            extra = (f"已等 {t.get('age')}s" if label == "raw" else f"已在逾時區 {t.get('wait')}s（可用 overpending_cancel 刪；超過 recovery 秒數會回流 raw）"
                     if label == "OverPending" else f"→ {t.get('robot') or '?'}（站點 {_station(t.get('station'), topo)}）" if label == "processing"
                     else f"站點 {_station(t.get('station'), topo)}")
            lines.append(f"- {label} {t.get('id')} {extra}")
        if len(entries) > LIST_QUEUE:
            lines.append(f"- …{label} 另有 {len(entries) - LIST_QUEUE} 筆沒列出")
    return lines


def queue_counts(data):
    return "、".join(f"{label} {len(data.get(key) or [])}" for key, label in rc.QUEUES)


def event_lines(data, keyword=None):
    lines = []
    for src, evs in (("orchestrtor", ((data.get("orchestrtor") or {}).get("events") or [])), ("distribute", data.get("events") or [])):
        evs = [e for e in evs if keyword is None or keyword in str(e)]
        lines += [f"- {src}：{e}" for e in evs[-LIST_EVENTS:]]
    return lines


# ---------------------------------------------------------------- 一幀快照
def render_all(data, topo):
    pk = rc.packages(data)
    running = [p for p in pk if p.get("status") == "RUNNING"]
    others = sorted((p for p in pk if p.get("status") != "RUNNING"), key=lambda p: -(p.get("updated_at") or 0))
    shown = running + others[:max(0, LIST_PACKAGES - len(running))]
    hidden = len(pk) - len(shown)
    robots = data.get("robots") or {}
    online = sum(1 for r in robots.values() if (r or {}).get("status") == "ONLINE")
    by_status = {}
    for p in pk:
        by_status[p.get("status")] = by_status.get(p.get("status"), 0) + 1
    st_text = "、".join(f"{k} {v}" for k, v in sorted(by_status.items(), key=lambda kv: kv[0] != "RUNNING")) or "沒有"
    head = (f"[PASS] 目前狀態：work package {len(pk)} 個（{st_text}）"
            + (f"，列出 {len(shown)} 個（RUNNING 全列，另有 {hidden} 個已完成的沒列）" if hidden else "")
            + f"；distribute {queue_counts(data)}；機器人 {len(robots)} 台（ONLINE {online}）")
    lines = [head, f"## work package（{len(pk)} 個：{st_text}）"]
    if not rc.orchestrtor_alive(data):
        lines.append("- orchestrtor 沒有回報過狀態（step_counter 0）：orchestrtor 可能沒在跑，或 web_console 剛啟動。")
    lines += [package_line(p, data, topo) for p in shown]
    if hidden:
        lines.append(f"- …另有 {hidden} 個已完成（COMPLETED）的沒列出：帶 task_id 看單一個")
    lines.append(f"## distribute 佇列（{queue_counts(data)}；狀態 {data.get('state', '?')}）")
    if not rc.distribute_alive(data):
        lines.append("- distribute 沒有回報過狀態（step_counter 0）：distribute 可能沒在跑。")
    lines += queue_lines(data, topo) or ["- 四個佇列都是空的"]
    lines.append(f"## 機器人（{len(robots)} 台：ONLINE {online}、OFFLINE {len(robots) - online}）")
    lines += [robot_line(rid, info, topo) for rid, info in sorted(robots.items())] or ["- 快照裡沒有機器人"]
    if robots:
        lines.append(rc.BATTERY_NOTE)
    ev = event_lines(data)
    if ev:
        lines.append(f"## 最近事件（每個來源最後 {LIST_EVENTS} 則）")
        lines += ev
    return "\n".join(lines)


def _package_robots(data, p):
    rids = set()
    cur = p.get("current_item") or {}
    if cur.get("robot_id"):
        rids.add(cur["robot_id"])
    for t in data.get("processing_tasks") or []:
        if str(t.get("id", "")).startswith(f"{p.get('package_id')}::") and t.get("robot"):
            rids.add(t["robot"])
    return rids


def render_one(data, topo, task_id):
    pk = rc.packages(data)
    if "::" in task_id:                                   # 工作項 id
        label, t = rc.queue_of(data, task_id)
        owner = rc.item_package(data, task_id)
        pid = task_id.split("::", 1)[0]
        parent = rc.find_package(data, pid)
        if not label and not owner:
            close = rc.close_matches(task_id, rc.item_ids(data) + [(p.get("current_item") or {}).get("item_id") for p in pk])
            return (f"[ERROR] 找不到工作項 {task_id}：不在 distribute 的任何佇列，也不是任何 work package 目前的工作項"
                    + (f"（相近的：{'、'.join(close)}）" if close else "")
                    + (f"；它所屬的 {pid} 目前是 {parent.get('status')}、目前的工作項是 {(parent.get('current_item') or {}).get('item_id')}"
                       if parent else "")
                    + "。下一步：工作項 id 會隨站點推進改變，用 workpackage_status <work package> 查目前的。")
        where = f"distribute {rc.queue_text(label, t)}" if label else "已離開 distribute（distribute 已 confirm 給機器人，orchestrtor 在等它的 task_exec_fin）"
        lines = [f"[PASS] 工作項 {task_id}：{where}" + (f"；是 {owner.get('package_id')}（{owner.get('status')}）目前的工作項" if owner else
                                                      f"；不是 {pid} 目前的工作項（已經是舊的一站）" if parent else "")]
        if owner:
            lines += ["## 所屬的 work package", package_line(owner, data, topo)]
        return "\n".join(lines)
    p = rc.find_package(data, task_id)
    related = lambda i: str(i or "").startswith(f"{task_id}::")   # noqa: E731
    if not p:
        close = rc.close_matches(task_id, [x.get("package_id") for x in pk])
        stray = queue_lines(data, topo, only=related)
        return (f"[ERROR] orchestrtor 的清單裡沒有 work package {task_id}"
                + (f"（相近的：{'、'.join(close)}）" if close else "")
                + f"：可能還沒送達、已被刪除（刪除後就從清單消失），或 id 打錯；目前清單 {len(pk)} 個"
                + (f"：{'、'.join(str(x.get('package_id')) for x in pk[:15])}{'…' if len(pk) > 15 else ''}" if pk else "")
                + ("" if rc.orchestrtor_alive(data) else "（orchestrtor 沒有回報過狀態，可能沒在跑）")
                + "。下一步：用不帶 task_id 的 workpackage_status 看全部的 id。"
                + (f"\ndistribute 裡還有它的工作項（工作包刪除後，已送出的那一站還在 distribute）：\n" + "\n".join(stray) if stray else ""))
    cur = p.get("current_item") or {}
    lines = [f"[PASS] work package {task_id}：{p.get('status')}" +
             ("" if p.get("status") == "COMPLETED" else
              f"，第 {(p.get('station_index') or 0) + 1}/{p.get('station_count')} 站 {_station(cur.get('station'), topo)}，{item_text(cur, data, topo)}"),
             f"## {task_id}", package_line(p, data, topo)]
    robots = data.get("robots") or {}
    for rid in sorted(_package_robots(data, p)):
        lines.append(robot_line(rid, robots.get(rid), topo))
    q = queue_lines(data, topo, only=related)
    lines.append(f"## distribute 佇列裡 {task_id} 的工作項（{len(q)} 筆）")
    lines += q or ["- 沒有（目前的工作項不在 distribute：還沒派出、或已 confirm 給機器人）"]
    ev = event_lines(data, keyword=task_id)
    if ev:
        lines.append(f"## 最近提到 {task_id} 的事件")
        lines += ev
    return "\n".join(lines)


# ---------------------------------------------------------------- 一段時間的變化
def pkg_state(p, topo):
    if p.get("status") == "COMPLETED":
        return f"COMPLETED（共 {p.get('iteration', 0)} 輪）"
    cur = p.get("current_item") or {}
    idx = (p.get("station_index") or 0) + 1
    s = f"{p.get('status')} 第{idx}/{p.get('station_count')}站 {_station(cur.get('station'), topo)}"
    if p.get("loop"):
        s += f" 第{(p.get('iteration') or 0) + 1}輪"
    if cur.get("status") == "CONFIRMED":
        s += " 這站已完成"
    elif cur.get("robot_id"):
        s += f" {cur['robot_id']}"
    elif cur.get("waiting_for_robot"):
        s += " ⏳等待機器人"
    return s


def robot_state(info):
    info = info or {}
    return f"{info.get('status', '?')} {info.get('state', '?')} 自報{info.get('real_state') or '?'}"


class Series:
    """每個對象的 (t_ns, 值)；只記改變的那一刻（占比照樣算得對）。"""

    def __init__(self):
        self.points, self.first_t, self.last, self.t_start = {}, {}, {}, None

    def put(self, key, t_ns, value):
        if self.t_start is None:
            self.t_start = t_ns
        if self.last.get(key) != value:
            self.points.setdefault(key, []).append((t_ns, value))
            self.first_t.setdefault(key, t_ns)
            self.last[key] = value

    def late(self, key):
        """觀察開始之後才出現的對象：回傳出現的時間（奈秒），否則 0。"""
        t = self.first_t.get(key, 0)
        return t if self.t_start is not None and t > self.t_start else 0


def _features(series, end_ns):
    out = {}
    for key, pts in series.points.items():
        out[key] = trim_changes(state_features(pts, end_ns))
    return out


def _block(n, key, f, late):
    lines = [f"--- #{n} {key}：變化 {f['transition_count']} 次（首 {f['first']} → 末 {f['last']}）"
             + (f"｜觀察開始後才出現（{rc.fmt_s(late / 1e9)}）" if late else "")]
    shown = f["transitions"]
    total = f["transition_count"]
    for i, tr in enumerate(shown):
        if total > len(shown) and i == len(shown) - 10:
            lines.append(f"  …中間 {total - len(shown)} 次省略（只列前 {len(shown) - 10} 次與最後 10 次）")
        lines.append(f"  {rc.fmt_s(tr['t_ns'] / 1e9)} {tr['from']} → {tr['to']}")
    share = "、".join(f"{v} {round(p * 100)}%" for v, p in f["time_share"][:4])
    lines.append(f"  時間占比：{share}")
    return lines


def _section(title, feats, series, unchanged_label):
    changed = [(k, f) for k, f in feats.items() if f["transition_count"] or series.late(k)]
    keys = {k for k, _ in changed}
    still = [k for k in feats if k not in keys]
    lines = [f"## {title}（{len(changed)} 個有變化" + (f"、{len(still)} 個沒變" if still else "") + "）"]
    order = sorted(changed, key=lambda kf: series.late(kf[0]) or (kf[1]["transitions"][0]["t_ns"] if kf[1]["transitions"] else 0))
    for n, (k, f) in enumerate(order, 1):
        lines += _block(n, k, f, series.late(k))
    if still:
        lines.append(f"- {unchanged_label}：" + "、".join(f"{k}（{feats[k]['last']}）" for k in still[:LIST_UNCHANGED])
                     + (f"…另有 {len(still) - LIST_UNCHANGED} 個" if len(still) > LIST_UNCHANGED else ""))
    if not feats:
        lines.append("- 觀察期間沒有")
    return lines, len(changed)


def _never_completes(p):
    """無限循環（loop、loop_count 是 None＝循環到手動停止，同 orchestrator.py）的工作包永遠不會 COMPLETED。"""
    return bool(p.get("loop")) and p.get("loop_count") is None and p.get("status") != "COMPLETED"


def watch_mode(base, seconds, task_id, topo=None, until_done=False):
    pk_s, it_s, rb_s = Series(), Series(), Series()
    seen_events, new_events = set(), []
    first = last = None
    done = None                                    # --until-done：(時間, 結束時的狀態, 是不是第一幀)
    related_robots = set()
    t = 0.0
    try:
        with rc.WsStream(base) as ws:              # 先連上（web_console 有問題時最快知道），再拿拓譜圖
            if topo is None:
                topo, _ = rc.fetch_topology(base)
            for t, data in ws.frames(duration=seconds):
                tn = int(t * 1e9)
                if first is None:
                    first = data
                last = data
                pids = set()
                for p in rc.packages(data):
                    pid = p.get("package_id")
                    if task_id and pid != task_id:
                        continue
                    pids.add(pid)
                    pk_s.put(pid, tn, pkg_state(p, topo))
                    related_robots |= _package_robots(data, p)
                for pid in list(pk_s.last):
                    if pid not in pids:
                        pk_s.put(pid, tn, GONE_PKG)
                present = set()
                for key, label in rc.QUEUES:
                    for e in data.get(key) or []:
                        iid = e.get("id") if isinstance(e, dict) else None
                        if not iid or (task_id and not str(iid).startswith(f"{task_id}::")):
                            continue
                        present.add(iid)
                        it_s.put(iid, tn, f"processing→{e.get('robot') or '?'}" if label == "processing" else label)
                        if task_id and label == "processing" and e.get("robot"):
                            related_robots.add(e["robot"])
                for iid in list(it_s.last):
                    if iid not in present:
                        it_s.put(iid, tn, GONE_ITEM)
                for rid, info in (data.get("robots") or {}).items():
                    rb_s.put(rid, tn, robot_state(info))
                for src, evs in (("orchestrtor", (data.get("orchestrtor") or {}).get("events") or []), ("distribute", data.get("events") or [])):
                    for e in evs:
                        if e in seen_events:
                            continue
                        seen_events.add(e)
                        if data is not first and (not task_id or task_id in str(e)):
                            new_events.append((t, src, e))
                if until_done:
                    state = pk_s.last.get(task_id)
                    if data is first and state is None:           # 第一幀就沒有它：馬上說，不等到最後
                        return render_one(data, topo, task_id)
                    if data is first and _never_completes(rc.find_package(data, task_id) or {}):
                        return (f"[ERROR] {task_id} 是無限循環的工作包（loop，沒有輪數上限），不會有 COMPLETED，--until-done 等不到。"
                                f"下一步：要看它跑到第幾輪、有沒有在動用 workpackage_status {task_id} --watch 秒；要停下來用 workpackage_cancel {task_id}"
                                f"（會改變狀態，系統會請使用者確認）。")
                    if state == GONE_PKG or str(state or "").startswith("COMPLETED"):
                        done = (t, state, data is first)
                        break
            frames, pings, end_text, span = ws.count, ws.pings, ws.end_text(), ws.elapsed
    except rc._WsError as e:
        return str(e)
    end_ns = int(t * 1e9)
    if task_id and not pk_s.points and not it_s.points:
        pk = rc.packages(last)
        close = rc.close_matches(task_id, [x.get("package_id") for x in pk])
        return (f"[ERROR] 觀察 {span:.1f} 秒（{frames} 幀），orchestrtor 的清單與 distribute 佇列裡一直沒有 {task_id}"
                + (f"（相近的：{'、'.join(close)}）" if close else "")
                + f"。目前清單 {len(pk)} 個：{'、'.join(str(x.get('package_id')) for x in pk[:15]) or '（空的）'}。"
                + "下一步：確認 id（不帶 task_id 的 workpackage_status 看全部）；工作包剛送出就先等幾秒再看。")
    # 只留這個工作包相關的機器人
    if task_id:
        for rid in list(rb_s.points):
            if rid not in related_robots:
                rb_s.points.pop(rid)
    pf, itf, rf = _features(pk_s, end_ns), _features(it_s, end_ns), _features(rb_s, end_ns)
    sec_p, n_p = _section("work package 的變化", pf, pk_s, "沒有變化")
    sec_i, n_i = _section("工作項（distribute 佇列）的變化", itf, it_s, "一直在同一個佇列")
    sec_r, n_r = _section("機器人的變化", rf, rb_s, "沒有變化")
    scope = f"{task_id}：" if task_id else ""
    counts = f"work package 有變化 {n_p} 個、工作項 {n_i} 個、機器人 {n_r} 台；期間新增事件 {len(new_events)} 則"
    again = f"workpackage_status {task_id} --until-done" if until_done else \
        f"workpackage_status{' ' + task_id if task_id else ''} --watch {seconds}"
    if done:
        t_done, state, at_first = done
        if state == GONE_PKG:
            head = (f"[PASS] {task_id} 在 {rc.fmt_s(t_done)} 從 orchestrtor 的清單消失（被刪除），沒有跑完；看到就結束觀察"
                    f"（最多 {seconds} 秒，收到 {frames} 幀）：{counts}")
        elif at_first:
            head = f"[PASS] {task_id} 已完成：{state}，觀察開始時就已經完成，不用再等；{counts}"
        else:
            head = (f"[PASS] {task_id} 已完成：{state}，在 {rc.fmt_s(t_done)} 看到完成就結束觀察（最多 {seconds} 秒，收到 {frames} 幀）；"
                    f"{counts}")
    elif end_text:
        head = (f"[PASS] ⚠️ 只觀察到 {span:.1f} 秒就中斷（要求 {seconds} 秒；{end_text}）"
                + (f"，還沒看到 {task_id} 完成" if until_done else "")
                + f"，以下是中斷前 {frames} 幀的整理：{scope}{counts}\n"
                f"下一步：再執行一次 {again} 接著看；一直中斷就請使用者檢查 web_console。")
    elif until_done:
        head = (f"[PASS] 觀察 {span:.1f} 秒（最多 {seconds} 秒，收到 {frames} 幀）{task_id} 還沒完成：結束時 {pk_s.last.get(task_id)}；{counts}\n"
                f"下一步：要繼續等就再執行一次 {again}；一直停在同一站就照卡住的情況查（rmf_handshake status <機器人或工作包>）。")
    else:
        head = (f"[PASS] 觀察 {span:.1f} 秒（要求 {seconds} 秒，收到 {frames} 幀；時間＝距觀察開始的秒數）：{scope}"
                f"work package 有變化 {n_p} 個、工作項 {n_i} 個、機器人 {n_r} 台；期間新增事件 {len(new_events)} 則"
                + (f"（web_console ping {pings} 次，都已回應）" if pings else ""))
    lines = [head, f"## 結束時（{rc.fmt_s(t)}）"]
    final_pk = [p for p in rc.packages(last) if not task_id or p.get("package_id") == task_id]
    lines += [package_line(p, last, topo) for p in final_pk[:LIST_PACKAGES]] or [f"- 沒有 work package{'（' + task_id + ' 已不在清單）' if task_id else ''}"]
    if len(final_pk) > LIST_PACKAGES:
        lines.append(f"- …另有 {len(final_pk) - LIST_PACKAGES} 個沒列出")
    lines.append(f"- distribute：{queue_counts(last)}")
    lines += sec_p + sec_i + sec_r
    if new_events:
        shown = new_events[-LIST_NEW_EVENTS:]
        lines.append(f"## 期間新增的事件（{len(new_events)} 則" + (f"，列最後 {len(shown)} 則" if len(shown) < len(new_events) else "") + "）")
        lines += [f"- {rc.fmt_s(tt)} {src}：{e}" for tt, src, e in shown]
    return "\n".join(lines)


def main(argv):
    p = parse_args(argv)
    if p["error"]:
        return p["error"]
    if p["watch"]:
        return watch_mode(p["url"], p["watch"], p["task_id"], until_done=p["until_done"])
    data, err = rc.ws_read_json(p["url"])      # 先讀快照：web_console 有問題時最快知道（6 秒）
    if err:
        return err
    topo, _ = rc.fetch_topology(p["url"])     # 拿不到語意就只顯示代號
    if p["task_id"]:
        return render_one(data, topo, p["task_id"])
    return render_all(data, topo)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] workpackage_status 未預期的例外：{type(e).__name__}: {e}")
        sys.exit(1)
