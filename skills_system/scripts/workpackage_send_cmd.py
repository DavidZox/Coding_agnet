"""workpackage_send：對任務協調器（orchestrtor）發送多站點 work package。

走 web_console POST /api/send_tasks（→ WorkPackage 發到 incoming_work_packages，orchestrtor 逐站派給 distribute）。送出前核對：
  * 站點對到 /api/topology 的節點：名稱完全相同 → 節點 id（純數字只當 id，不做部分比對）→ 語意名稱（完全相同、再來是唯一的部分比對）。
    送出的值＝節點名稱；沒有名稱的節點（name 是空字串的地圖）送 id 字串——機器人端兩種都認。
  * task_id 不能跟 orchestrtor 清單裡的重複：orchestrtor 會默默忽略重複的 id（COMPLETED 的也一直留在清單），送了等於沒送。
  * --amr 要在機器人名冊裡（/api/robots＋快照）。
送出後讀快照確認 orchestrtor 收到了。拿不到拓譜圖／快照／名冊時不送，除非加 --no-check（照原樣送、不核對）。
--ros2 [容器]：web_console 沒在跑時，在 ROS 2 容器裡 `ros2 topic pub --once` 直接發布 fih_rmf_msgs/msg/WorkPackage（同 web_console）。
parse_args(argv) 是純函式（不連線、不印）：guard 用它判斷這次是不是 --dry-run。查狀態／取消／地圖是 workpackage_status、
workpackage_cancel、semantic_map；共用層見 _rmf_common.py。
"""
import json
import os
import re
import shlex
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rmf_common as rc   # noqa: E402

SEND_PATH = "/api/send_tasks"
TOPIC = "/incoming_work_packages"
MSG_TYPE = "fih_rmf_msgs/msg/WorkPackage"
ROS2_WAIT_SUBSCRIBER_SECONDS = 10
ROS2_TIMEOUT_SECONDS = 30
TASK_TYPES = ("regular", "charge", "park")
LEVELS = ("normal", "middle", "emergency")
INT64_MAX = 2 ** 63 - 1

USAGE = (
    "用法: scripts/workpackage_send_cmd.py <task_id|auto> <站點1,站點2,...> [--amr 機器人] [--type regular|charge|park]\n"
    "      [--level normal|middle|emergency] [--weight 整數] [--loop [輪數]] [--desc 描述1,描述2,...] [--dry-run]\n"
    "      [--ros2 [容器]] [--no-check] [--url 位址]\n"
    "  站點寫名稱（a3）、節點 id（3）或語意名稱（加工線通道-6）。循環：--loop（不接數字）＝無限循環；--loop 3＝3 輪；不加＝一輪。\n"
    "  範例: scripts/workpackage_send_cmd.py WP001 home,a3,a7 --amr tb1　　scripts/workpackage_send_cmd.py 巡邏 home,a3 --amr tb1 --loop"
)

_VALUE_OPTS = {"--amr": "機器人 id（例如 --amr tb1；名冊用 semantic_map --robots 查）", "--type": "任務類型（regular／charge／park）",
               "--level": "等級（normal／middle／emergency）", "--weight": "權重整數（0＝自動計算）",
               "--desc": "每一站的描述（逗號分隔）", "--url": "web_console 位址（例如 http://localhost:8020）"}
# 這些是別的技能的選項；小模型記得舊的合併版技能時會帶進來，直接指路
_OTHER_SKILL_OPTS = {"--status": "workpackage_status", "--watch": "workpackage_status", "--until-done": "workpackage_status",
                     "--cancel": "workpackage_cancel",
                     "--cancel-overpending": "overpending_cancel", "--wait": "overpending_cancel",
                     "--map": "semantic_map", "--stations": "semantic_map", "--robots": "semantic_map"}

# 循環：orchestrtor 的 loop_count None＝循環到手動刪除、正整數＝跑 N 輪（web 介面也是「留空＝無限」）。
# 小模型表達「無限循環」的寫法很多（--loop 不接數字、--loop 0、--loop 無限、--forever…），全部收下；
# 實測舊措辭「不接＝循環到取消」被讀成「不加 --loop」而送出單輪任務，所以規格與 USAGE 改成正面寫法。
_LOOP_FLAGS = ("--loop", "--loops", "--loop-count", "--repeat", "--cycle")
_INFINITE_FLAGS = ("--infinite", "--forever", "--endless", "--loop-forever", "--infinite-loop")
_INFINITE_WORDS = {"0", "-1", "inf", "infinite", "infinity", "forever", "endless", "always", "unlimited", "none", "null",
                   "true", "yes", "on", "∞", "無限", "無限循環", "不停", "永久", "一直", "是"}
_NO_LOOP_WORDS = {"false", "no", "off", "否", "不"}
_STATION_SPLIT = re.compile(r"[,，、]")


def _loop_value(tok):
    v = tok.strip().lower()
    return v.isdigit() or v in _INFINITE_WORDS or v in _NO_LOOP_WORDS


# ---------------------------------------------------------------- 參數（純函式）
def parse_args(argv):
    """純函式：解析參數、檢查格式（不連線、不印），guard 也用它。回傳 dict：
    error（None 或 [ERROR] 訊息；有錯時腳本在任何連線之前就回這個錯誤）、dry_run、task_id、auto_id、stations（輸入的站點）、
    amr、type、level、weight、loop、loop_count、desc（每站的描述）、ros2（None＝走 web_console；""＝目前的目標容器；或容器名稱）、
    no_check、url。"""
    out = {"error": None, "dry_run": False}
    pos, opts, err = rc.parse_cli(argv, values=_VALUE_OPTS, flags=("--dry-run", "--no-check") + _INFINITE_FLAGS,
                                  optional=dict({f: _loop_value for f in _LOOP_FLAGS}, **{"--ros2": lambda v: True}),
                                  elsewhere=_OTHER_SKILL_OPTS, usage=USAGE)
    if err:
        return dict(out, error=err)
    out["dry_run"] = bool(opts.get("--dry-run"))
    if len(pos) != 2:
        hint = ""
        if len(pos) == 5:
            hint = "（看起來是舊版 workitem_est 的 5 個位置參數；現在只有 task_id 與站點兩個位置參數，其餘改用選項）"
        elif opts.get("--ros2") and len(pos) == 1:
            hint = f"（--ros2 後面的 {opts['--ros2']!r} 被當成容器名稱了；--ros2 請放在最後，或寫 --ros2 容器名稱）"
        elif len(pos) == 1:
            hint = "（第一個參數是 task_id（或 auto），第二個是逗號分隔的站點清單）"
        elif len(pos) > 2:
            hint = f"（站點清單要用逗號分隔、中間不能有空白，例如 {pos[0]} {','.join(pos[1:])}）"
        return dict(out, error=f"[ERROR] 發送需要 2 個位置參數 <task_id> <站點清單>，收到 {len(pos)} 個{hint}。\n{USAGE}")
    task_id, station_arg = pos[0].strip(), pos[1]
    auto = task_id.lower() == "auto"
    if not task_id:
        return dict(out, error=f"[ERROR] task_id 不可為空（可以寫 auto 自動產生）。\n{USAGE}")
    if not auto:
        bad = ("含空白" if re.search(r"\s", task_id) else "含 ::（那是工作項 id 的分隔）" if "::" in task_id
               else "含 /（web_console 的刪除網址會對不到）" if "/" in task_id else "太長（最多 80 字）" if len(task_id) > 80 else "")
        if bad:
            return dict(out, error=f"[ERROR] task_id {task_id!r} {bad}。下一步：換一個只有英數字、- 或 _ 的 id（或寫 auto 自動產生）。")
    stations = [s.strip() for s in _STATION_SPLIT.split(station_arg) if s.strip()]
    if not stations:
        return dict(out, error=f"[ERROR] 至少要一個站點（逗號分隔，例如 home,a3,a7；站點用 semantic_map --stations 查）。\n{USAGE}")
    amr = (opts.get("--amr") or "").strip()
    if amr:
        amr_err = rc.robot_id_error(amr, "--amr")
        if amr_err:
            return dict(out, error=amr_err)
    task_type = (opts.get("--type") or "regular").strip().lower()
    if task_type not in TASK_TYPES:
        return dict(out, error=f"[ERROR] --type 要是 {'／'.join(TASK_TYPES)} 之一，收到 {task_type!r}。")
    level = (opts.get("--level") or "normal").strip().lower()
    if level not in LEVELS:
        return dict(out, error=f"[ERROR] --level 要是 {'／'.join(LEVELS)} 之一，收到 {level!r}。")
    try:
        weight = int(str(opts.get("--weight", "0")).strip())
    except ValueError:
        return dict(out, error=f"[ERROR] --weight 要是整數（0＝依類型與等級自動計算），收到 {opts.get('--weight')!r}。")
    if not 0 <= weight <= INT64_MAX:
        return dict(out, error="[ERROR] --weight 要介於 0 到 2^63-1（0＝自動計算；distribute 只採用大於 0 的值）。")
    descs = [d.strip() for d in opts["--desc"].split(",")] if opts.get("--desc") else []
    if len(descs) > len(stations):
        return dict(out, error=f"[ERROR] --desc 有 {len(descs)} 筆描述，但只有 {len(stations)} 站；描述數不可多於站點數（描述裡不能有逗號）。")
    descs += [""] * (len(stations) - len(descs))
    # 循環
    loop, loop_count, seen = False, None, []
    for flag in _LOOP_FLAGS + _INFINITE_FLAGS:
        if flag not in opts:
            continue
        val = opts[flag] if flag in _LOOP_FLAGS else ""
        v = str(val).strip().lower()
        if v in _NO_LOOP_WORDS:
            setting = (False, None)
        elif v.isdigit() and int(v) > 0:
            setting = (True, int(v))
        else:
            setting = (True, None)
        seen.append((flag, setting))
    if len({s for _, s in seen}) > 1:
        return dict(out, error=f"[ERROR] 循環設定互相矛盾（{'、'.join(f for f, _ in seen)}）：無限循環寫 --loop，N 輪寫 --loop N，只跑一輪就不加。")
    if seen:
        loop, loop_count = seen[0][1]
    url, uerr = rc.resolve_url(opts.get("--url"))
    if uerr:
        return dict(out, error=uerr)
    ros2 = opts.get("--ros2")
    return dict(out, task_id=task_id, auto_id=auto, stations=stations, amr=amr, type=task_type, level=level, weight=weight,
                loop=loop, loop_count=loop_count, desc=descs, ros2=None if ros2 is None else str(ros2).strip(),
                no_check=bool(opts.get("--no-check")), url=url)


# ---------------------------------------------------------------- 文字
def loop_text(pkg):
    if not pkg["loop"]:
        return "否（只跑一輪）"
    return f"是（{pkg['loop_count']} 輪）" if pkg["loop_count"] else "是（無限，直到手動刪除）"


def stops_text(pkg, picks):
    if picks:
        return " → ".join(rc.node_detail(node) for _, node, _ in picks)
    return " → ".join(s["station"] for s in pkg["stops"]) + "（未核對拓譜圖）"


def mapping_text(picks):
    how = {"id": "節點 id", "label": "語意名稱", "partial": "語意名稱的一部分"}
    notes = [f"「{tok}」＝{how[kind]} → {node['ref']}" for tok, node, kind in picks or [] if kind != "name"]
    return f"站點對應：{'；'.join(notes)}\n" if notes else ""


def params_text(pkg):
    return (f"task_type: {pkg['task_type']}｜level: {pkg['level']}｜weight: {pkg['weight'] if pkg['weight'] else '0（自動計算）'}"
            f"｜loop: {loop_text(pkg)}")


def follow_up(pid):
    return (f"後續：workpackage_status {pid} 看進度、workpackage_status {pid} --until-done 等它跑完（看到完成就結束）、"
            f"workpackage_status {pid} --watch 30 觀察一段時間、workpackage_cancel {pid} 取消；"
            f"沒有機器人可承接時停在當前站等待（⏳），不是錯誤。")


def amr_text(pkg, robot_note):
    return (pkg["assign_amr"] or "交給 distribute 挑") + robot_note


# ---------------------------------------------------------------- 送出前的核對（要連線）
def _check_env(p):
    """拿拓譜圖、快照、名冊；回傳 (topo, snapshot, roster, notes, error)。--no-check 時拿不到的照原樣略過。"""
    base, notes = p["url"], []
    topo, terr = rc.fetch_topology(base)
    snap, serr = rc.ws_read_json(base) if not terr or p["no_check"] else (None, None)
    if terr and not p["no_check"]:
        why = "web_console 沒有 /api/topology（版本太舊）" if "HTTP 404" in terr else "拿不到 web_console 的拓譜圖"
        ros2 = "（--ros2 也一樣：站點與 id 都要先核對）" if p["ros2"] is not None else ""
        return None, None, None, None, (
            f"[ERROR] {why}，沒辦法核對站點「{','.join(p['stations'])}」是不是這個場域的站、task_id 有沒有重複{ros2}；沒有送出。"
            f"原因：{terr[8:]}\n下一步：先讓 web_console 恢復（或用 --url 指到正確的位址）再送；確定站點值就是拓譜圖的節點名稱或 id、"
            f"而且使用者同意不核對時，才加 --no-check 照原樣送出。")
    if serr and not p["no_check"]:
        return None, None, None, None, (f"[ERROR] 讀不到 web_console 的狀態快照，沒辦法確認 task_id 有沒有重複、送出後也沒辦法確認 orchestrtor 收到；"
                                        f"沒有送出。原因：{serr[8:]}")
    if terr:
        notes.append(f"⚠️ 沒有核對站點（--no-check；拓譜圖：{rc.clip(terr[8:], 80)}）")
    if serr and p["no_check"] and not terr:
        notes.append("⚠️ 沒有核對 task_id 是否重複（--no-check；快照讀不到）")
    roster = None
    if p["amr"]:
        roster, rerr = rc.fetch_roster(base, snap)
        if rerr and not p["no_check"]:
            return None, None, None, None, (f"[ERROR] 拿不到機器人名冊，沒辦法確認 --amr {p['amr']} 是這個場域的機器人；沒有送出。原因：{rerr[8:]}\n"
                                            f"下一步：先讓 web_console 恢復；使用者確定機器人 id 正確時才加 --no-check。")
        if rerr:
            notes.append(f"⚠️ 沒有核對 --amr {p['amr']}（--no-check；名冊拿不到）")
            roster = None
    return topo, snap, roster, notes, None


def _robot_note(amr, snap):
    info = ((snap or {}).get("robots") or {}).get(amr) if amr else None
    if info and info.get("status") == "OFFLINE":
        return "（⚠️ 目前 OFFLINE：工作包會停在第一站等它上線，distribute 不會改派指定的機器人）"
    return ""


def build_payload(p, refs):
    task_id = p["task_id"]
    return {"task_id": task_id, "task_type": p["type"], "level": p["level"], "weight": p["weight"], "assign_amr": p["amr"],
            "loop": bool(p["loop"]), "loop_count": p["loop_count"] if p["loop"] else None,
            "stops": [{"station": s, "description": d} for s, d in zip(refs, p["desc"])]}


# ---------------------------------------------------------------- 送出
def ros2_message(pkg):
    """WorkPackage 的欄位（同 msg_codec.work_package_to_msg：loop_count 是 None 時 has_loop_count false）。"""
    return {"task_id": pkg["task_id"], "task_type": pkg["task_type"], "level": pkg["level"], "weight": int(pkg["weight"] or 0),
            "assign_amr": pkg["assign_amr"], "loop": bool(pkg["loop"]), "loop_count": int(pkg["loop_count"] or 0),
            "has_loop_count": pkg["loop_count"] is not None,
            "stops": [{"station": s["station"], "description": s["description"]} for s in pkg["stops"]]}


def ros2_pub_command(pkg):
    body = json.dumps(ros2_message(pkg), ensure_ascii=False)     # JSON 也是合法的 YAML
    return (f"ros2 topic pub --once -w 1 --max-wait-time-secs {ROS2_WAIT_SUBSCRIBER_SECONDS} "
            f"{TOPIC} {MSG_TYPE} {shlex.quote(body)}")


def _arrived(pid):
    """送出前已確認清單裡沒有這個 id，所以清單裡出現它（RUNNING，或很快就跑完的 COMPLETED）就是這次送的。"""
    def check(data):
        return rc.find_package(data, pid)
    return check


def _arrival_text(p, topo):
    if p.get("status") == "COMPLETED":
        return f"orchestrtor 已收到，而且已經跑完（COMPLETED，共 {p.get('iteration', 0)} 輪）"
    cur = p.get("current_item") or {}
    station = cur.get("station") or (p.get("stations") or ["?"])[0]
    return (f"orchestrtor 已收到（{p.get('status')}，第 {(p.get('station_index') or 0) + 1}/{p.get('station_count')} 站 "
            f"{rc.station_text(station, topo)}）")


def send_http(p, pkg, topo, picks, notes, robot_note):
    base = p["url"]
    status, data, err = rc.http_json("POST", base, SEND_PATH, [pkg])
    if err:
        hint = "\n（web_console 連不上時，可以加 --ros2 [容器] 在 ROS 2 容器裡直接發布）" if status is None else ""
        return err + hint
    if not isinstance(data, dict) or data.get("count") != 1:
        return (f"[ERROR] web_console 回應 HTTP {status}，但內容不像 /api/send_tasks 的回應（{rc.clip(json.dumps(data, ensure_ascii=False), 160)}）："
                f"--url 可能指到別的服務。下一步：確認 --url 指的是 web_console，再用 workpackage_status {pkg['task_id']} 確認有沒有收到。")
    verdict, last, t, cerr = rc.confirm_after(base, _arrived(pkg["task_id"]))
    head = f"work package「{pkg['task_id']}」"
    body = (f"stops: {stops_text(pkg, picks)}\n{mapping_text(picks)}{params_text(pkg)}\n"
            + "".join(n + "\n" for n in notes) + follow_up(pkg["task_id"]))
    if verdict is None:
        why = f"讀不到快照（{cerr[8:]}）" if cerr else f"{rc.CONFIRM_SECONDS:g} 秒內 orchestrtor 的清單裡還看不到它"
        return (f"[ERROR] web_console 收下了{head}（HTTP {status}），但{why}：orchestrtor 可能沒在跑（web_console 只負責轉發）。"
                f"下一步：用 workpackage_status {pkg['task_id']} 再確認一次；還是沒有就請使用者檢查 orchestrtor 節點（ROS2_node_list 找 /orchestrtor）。"
                f"不要用同一個 id 重送（重複的 id 會被忽略）。\n{body}")
    return (f"[PASS] {head}已送出：{len(pkg['stops'])} 站，循環：{loop_text(pkg)}，機器人：{amr_text(pkg, robot_note)}；"
            f"{_arrival_text(verdict, topo)}（{rc.fmt_s(t)}）\n{body}")


def send_ros2(p, pkg, topo, picks, notes, robot_note):
    from _docker_common import resolve_container, ros2_exec
    container, err = resolve_container(p["ros2"], "用法: --ros2 [容器名稱]（省略＝目前的目標容器）")
    if err:
        return err
    ok, out, err = ros2_exec(container, ros2_pub_command(pkg), ROS2_TIMEOUT_SECONDS,
                             timeout_hint=(f"最可能是 {TOPIC} 沒有訂閱者（orchestrtor 沒在跑），ros2 topic pub 等不到訂閱者。"
                                           f"下一步：用 ROS2_node_list 確認 /orchestrtor 有在跑。"))
    if not ok:
        return err
    if "publishing #1" not in (out or ""):
        return (f"[ERROR] 在容器 {container} 執行 ros2 topic pub 沒有看到「publishing #1」：可能沒有發布出去"
                f"（{rc.clip(out, 200) or '沒有輸出'}）。下一步：用 ROS2_topic_list 確認 {TOPIC} 與 {MSG_TYPE}（容器要載入 fih_rmf_msgs）。")
    confirm = "（web_console 讀不到，沒辦法用快照確認 orchestrtor 收到；用 workpackage_status 或 ROS2_topic_echo /orchestrtor_ui_state 確認）"
    verdict, last, t, cerr = rc.confirm_after(p["url"], _arrived(pkg["task_id"])) if topo is not None else (None, None, 0, "x")
    if verdict is not None:
        confirm = f"；{_arrival_text(verdict, topo)}（{rc.fmt_s(t)}）"
    elif not cerr:
        confirm = f"（⚠️ {rc.CONFIRM_SECONDS:g} 秒內 orchestrtor 的清單裡還看不到它：orchestrtor 可能沒在跑或 id 重複被忽略）"
    return (f"[PASS] work package「{pkg['task_id']}」已直接發布到 {TOPIC}（容器 {container}，{MSG_TYPE}，未經 web_console）："
            f"{len(pkg['stops'])} 站，循環：{loop_text(pkg)}，機器人：{amr_text(pkg, robot_note)}{confirm}\n"
            f"stops: {stops_text(pkg, picks)}\n{mapping_text(picks)}{params_text(pkg)}\n" + "".join(n + "\n" for n in notes)
            + follow_up(pkg["task_id"]))


def main(argv):
    p = parse_args(argv)
    if p["error"]:
        return p["error"]
    topo, snap, roster, notes, err = _check_env(p)
    if err:
        return err
    # 站點
    picks = None
    if topo is not None:
        refs, picks, err = rc.resolve_stations(p["stations"], topo)
        if err:
            return err
    else:
        refs = list(p["stations"])
    # task_id
    if p["auto_id"]:
        base_id = "WP-" + time.strftime("%Y%m%d-%H%M%S")
        existing = {x.get("package_id") for x in rc.packages(snap)}
        p["task_id"] = base_id if base_id not in existing else next(f"{base_id}-{i}" for i in range(2, 999) if f"{base_id}-{i}" not in existing)
    elif snap is not None:
        dup = rc.find_package(snap, p["task_id"])
        if dup:
            return (f"[ERROR] orchestrtor 的清單裡已經有 work package {p['task_id']}（{dup.get('status')}）：orchestrtor 會忽略重複的 id，"
                    f"送了也不會跑。下一步：換一個 task_id（例如 {p['task_id']}-2，或寫 auto）；一定要用同一個 id 就先 workpackage_cancel {p['task_id']}"
                    f"（RUNNING 的會停止派下一站）再送。")
    if snap is not None and not rc.orchestrtor_alive(snap) and not p["no_check"]:
        return ("[ERROR] 快照裡 orchestrtor 沒有回報過狀態（step_counter 0、沒有工作包）：orchestrtor 可能沒在跑，送出的工作包不會有人處理；"
                "沒有送出。下一步：請使用者確認 orchestrtor 節點（ROS2_node_list 找 /orchestrtor）；確定它有在跑才加 --no-check 再送。")
    # 機器人
    if p["amr"] and roster is not None and p["amr"] not in roster:
        close = rc.close_matches(p["amr"], roster)
        return (f"[ERROR] 機器人名冊裡沒有 {p['amr']}"
                + (f"（相近的：{'、'.join(close)}）" if close else "")
                + f"：現有 {len(roster)} 台：{'、'.join(roster)}。下一步：改用名冊上的 id，或問使用者是哪一台。")
    pkg = build_payload(p, refs)
    robot_note = _robot_note(p["amr"], snap)
    if p["dry_run"]:
        if p["ros2"] is not None:
            target = f"ros2（容器 {p['ros2'] or '目前的目標容器'}）：{ros2_pub_command(pkg)}"
        else:
            target = f"POST {p['url']}{SEND_PATH}"
        return (f"[PASS] work package「{pkg['task_id']}」dry-run（尚未送出）：{len(pkg['stops'])} 站，循環：{loop_text(pkg)}，"
                f"機器人：{amr_text(pkg, robot_note)}\nstops: {stops_text(pkg, picks)}\n{mapping_text(picks)}{params_text(pkg)}\n"
                + "".join(n + "\n" for n in notes)
                + f"payload: {json.dumps(pkg, ensure_ascii=False)}\n目標: {target}\n拿掉 --dry-run 才會真正送出（系統會先請使用者確認）。")
    if p["ros2"] is not None:
        return send_ros2(p, pkg, topo, picks, notes, robot_note)
    return send_http(p, pkg, topo, picks, notes, robot_note)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] workpackage_send 未預期的例外：{type(e).__name__}: {e}")
        sys.exit(1)
