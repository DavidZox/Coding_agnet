"""rmf_handshake：調度系統（distribute）與機器人之間的授權交握——看某台機器人的交握狀況並自動判斷原因，必要時手動回
交握或補發完成訊號（manual_trigger）。

交握流程（amr_base_sw/RMF_Integration_Report.md 1.3 節）：distribute 每 0.5 秒對選中的機器人發 /{rid}/allocator_status
（authorize），機器人回 /{rid}/handshake_states（is_authored：yes／no，沒有 task_id）；看到 yes 就 confirm、任務移出 distribute；
機器人做完發 /{rid}/task_exec_fin，orchestrtor 收到才派下一站。授權逾時（預設 10 秒）→ OverPending 冷卻後重試。

  status <機器人> [--seconds N]   唯讀：web_console 的快照（機器人在線與否、正在授權的任務、OverPending、它的工作包）＋
                                  在 ROS 2 容器裡聽 N 秒（預設 4）/{rid}/allocator_status 與 /{rid}/handshake_states，自動判斷：
                                  離線、沒有回應授權（TaskAgent 沒在跑）、一直回 no（忙碌／站點無效／定位異常）、
                                  完成訊號遺失（機器人已經閒置、工作項還在等）、或交握正常。
  yes|no <機器人> [<機器人> …]    手動回交握（manual_trigger 的 /batch_handshake）——會先請使用者確認。
  fin <機器人> [<task_id>]         補發完成訊號（/batch_task_exec_fin）；task_id 省略＝那台機器人目前在等完成訊號的工作項——會先請使用者確認。

位址：--url web_console（預設 RMF_WEB_CONSOLE_URL 或 http://localhost:8020）、--trigger manual_trigger（預設 RMF_MANUAL_TRIGGER_URL
或 http://localhost:8002）、--container 跑 ROS 2 的容器（預設目前的目標容器；沒有就只看 web_console 的快照）。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rmf_common as rc                                   # noqa: E402
from _docker_common import current_target_container, docker_exec, list_container_names, run_docker, with_target_marker  # noqa: E402

USAGE = ("用法: scripts/rmf_handshake_cmd.py status <機器人或工作包> [--seconds N] [--container 容器]\n"
         "      scripts/rmf_handshake_cmd.py yes|no <機器人> [<機器人> …]\n"
         "      scripts/rmf_handshake_cmd.py fin <機器人> [<task_id>]\n"
         "  共用：--url web_console 位址、--trigger manual_trigger 位址、--container ROS 2 容器")
TRIGGER_URL = os.environ.get("RMF_MANUAL_TRIGGER_URL", "http://localhost:8002").rstrip("/")


def _opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            val = args[i + 1]
            del args[i:i + 2]
            return val
    return default


def _snapshot(url):
    data, err = rc.ws_read_json(url)
    return data, err


def _robot_view(data, rid):
    robots = (data or {}).get("robots") or {}
    r = robots.get(rid)
    processing = [t for t in (data or {}).get("processing_tasks") or [] if t.get("robot") == rid]
    raw = (data or {}).get("raw_tasks") or []
    ovp = (data or {}).get("overpending_tasks") or []
    pkgs = []
    for p in ((data or {}).get("orchestrtor") or {}).get("packages") or []:
        cur = p.get("current_item") or {}
        if cur.get("robot_id") == rid or p.get("assign_amr") == rid:
            pkgs.append(p)
    return r, processing, raw, ovp, pkgs


def _listen(container, rid, seconds):
    """在容器裡同時聽 allocator_status（command）與 handshake_states（is_authored）N 秒。回傳 (allocator 指令清單, 回覆清單, 錯誤)。"""
    cmd = (f"(timeout {seconds} ros2 topic echo /{rid}/allocator_status --field command 2>/dev/null | sed 's/^/A:/') & "
           f"(timeout {seconds} ros2 topic echo /{rid}/handshake_states --field is_authored 2>/dev/null | sed 's/^/H:/'); wait")
    ok, out, err = docker_exec(container, cmd, seconds + 25, interactive=True, what=f"容器 '{container}' 聽 /{rid} 的交握 topic")
    if not ok and not out:
        return None, None, err
    cmds = [ln[2:].strip().strip("'\"") for ln in (out or "").splitlines() if ln.startswith("A:") and ln[2:].strip() not in ("---", "")]
    reps = [ln[2:].strip().strip("'\"") for ln in (out or "").splitlines() if ln.startswith("H:") and ln[2:].strip() not in ("---", "")]
    return cmds, reps, None


def _guess_ros_container():
    """沒有指定容器、也沒有目標容器時，猜跑 ROS 2 的容器：只有一個執行中的容器就用它；不然名稱含 rmf／ros／amr 的剛好一個才用。
    聽 topic 是唯讀的（ros2 topic echo），猜錯只是聽不到。"""
    ok, out, _ = run_docker(["docker", "ps", "--format", "{{.Names}}"], 20, what="docker ps")
    names = [n.strip() for n in (out or "").splitlines() if n.strip()] if ok else []
    if len(names) == 1:
        return names[0]
    hits = [n for n in names if re.search(r"rmf|ros|amr", n, re.I)]
    return hits[0] if len(hits) == 1 else ""


def _package_robot(data, target):
    """target 是工作包編號時，回傳 (機器人, 說明)；不是就回傳 (None, None)。"""
    for p in ((data or {}).get("orchestrtor") or {}).get("packages") or []:
        if p.get("package_id") == target:
            cur = p.get("current_item") or {}
            rid = cur.get("robot_id") or p.get("assign_amr")
            return rid, f"- 工作包 {target} 目前的工作項 {cur.get('item_id')}（站點 {cur.get('station')}）指派給 {rid or '（還沒有指派）'}"
    return None, None


def status(rid, args):
    args, url, err = rc.split_url(args)
    if err:
        return err
    seconds = int(_opt(args, "--seconds", "4") or 4)
    container = _opt(args, "--container", "") or current_target_container()
    guessed = False
    if not container:
        container = _guess_ros_container()
        guessed = bool(container)
    data, err = _snapshot(url)
    lines, diag = [], []
    r = processing = pkgs = None
    if err:
        lines.append(f"（web_console 快照讀不到：{err}）")
    else:
        if rid not in (data.get("robots") or {}):
            # 給的是工作包編號（實測 e4b 常這樣用）：換成那個工作包目前指派的機器人
            prid, note = _package_robot(data, rid)
            if prid:
                lines.append(note)
                rid = prid
        r, processing, raw, ovp, pkgs = _robot_view(data, rid)
        if r is None:
            known = "、".join(sorted((data.get("robots") or {}).keys()))
            pk = "、".join(p.get("package_id", "") for p in ((data.get("orchestrtor") or {}).get("packages") or []))
            return f"[ERROR] web_console 的機器人名冊沒有 {rid}（機器人：{known}；工作包：{pk or '（沒有）'}）"
        lines.append(f"- distribute：{rid} {r.get('status')}、{r.get('state')}（機器人自己的狀態 {r.get('real_state')}；最後的任務 {r.get('last_task_id')}）"
                     + (f"；位置 ({r.get('x')}, {r.get('y')})" if r.get("x") is not None else ""))
        for t in processing:
            lines.append(f"- 正在對 {rid} 授權：{t.get('id')}（站點 {t.get('station')}；已送 authorize {t.get('authorize_sent', '?')} 次、"
                         f"{t.get('elapsed', '?')} 秒）")
        mine_ovp = [t for t in ovp if any(t.get("id") == (p.get("current_item") or {}).get("item_id") for p in pkgs)]
        for t in mine_ovp:
            lines.append(f"- OverPending：{t.get('id')}（已等 {t.get('wait')} 秒，冷卻後會再派）")
        mine_raw = [t for t in raw if t.get("assign") == rid]
        for t in mine_raw:
            lines.append(f"- 待派（等 {rid}）：{t.get('id')}（{t.get('age')} 秒）")
        for p in pkgs:
            cur = p.get("current_item") or {}
            lines.append(f"- 工作包 {p.get('package_id')} {p.get('status')}：第 {p.get('station_index', 0) + 1}/{p.get('station_count')} 站 "
                         f"{cur.get('station')}，工作項 {cur.get('item_id')} {cur.get('status')}"
                         + (f"（{cur.get('dispatched_sec_ago')} 秒前派出）" if cur.get("dispatched_sec_ago") is not None else ""))
    cmds = reps = None
    if container:
        cmds, reps, lerr = _listen(container, rid, seconds)
        if lerr:
            lines.append(f"（在容器 {container} 聽 topic 失敗：{lerr[:200]}）")
        else:
            lines.append(f"- 在 {container}{'（自動選的 ROS 2 容器）' if guessed else ''} 聽 {seconds} 秒：/{rid}/allocator_status 收到 {len(cmds)} 則（authorize {cmds.count('authorize')}、"
                         f"confirm {cmds.count('confirm')}）；/{rid}/handshake_states 收到 {len(reps)} 則（yes {reps.count('yes')}、no {reps.count('no')}）")
    else:
        lines.append("（沒有指定 ROS 2 容器，沒有聽交握的 topic；要更確定請加 --container <容器>）")
    # 判斷
    if r is not None and r.get("status") == "OFFLINE":
        diag.append(f"{rid} 離線（distribute 收不到它的 /{rid}/robot_state 心跳）：不會對它授權，指定給它的任務會一直等、不會改派。"
                    f"要先讓機器人上線，或取消後改派別台。")
    elif cmds is not None and cmds.count("authorize") > 0 and not reps:
        diag.append(f"{rid} 沒有回應授權：distribute 一直送 authorize，但 /{rid}/handshake_states 沒有任何回覆——機器人的 TaskAgent "
                    f"可能沒在跑或沒有訂閱 allocator_status。**不要**手動回 yes（機器人不會真的去執行，工作包會卡住）；請機器人端確認 TaskAgent。")
    elif reps and reps.count("no") > 0 and reps.count("yes") == 0:
        diag.append(f"{rid} 對授權一直回 no（交握規則 R1：忙碌、站點無效或定位異常）→ 每次授權逾時進 OverPending、冷卻後重試，"
                    f"不會成功。可以請機器人端確認狀態，或取消後改派別台機器人。")
    elif cmds is not None and "confirm" in cmds and reps and reps[-1] == "yes":
        diag.append("交握正常：機器人回 yes、distribute 已經 confirm。")
    if r is not None and pkgs:
        for p in pkgs:
            cur = p.get("current_item") or {}
            if (cur.get("status") == "DISPATCHED" and not processing and r.get("state") == "standby"
                    and r.get("real_state") == "IDLE" and cur.get("robot_id") == rid
                    and not any(t.get("id") == cur.get("item_id") for t in ((data or {}).get("raw_tasks") or []) + ((data or {}).get("overpending_tasks") or []))):
                diag.append(f"工作包 {p.get('package_id')} 的工作項 {cur.get('item_id')} 已經授權給 {rid}、{rid} 也已經閒置，"
                            f"但工作項還在等完成訊號——多半是 /{rid}/task_exec_fin 遺失。確認機器人真的到了 {cur.get('station')} 之後，"
                            f"使用者要你處理的話，下一步直接執行 `rmf_handshake fin {rid} {cur.get('item_id')}` 補發（系統會請使用者確認，不用先問），"
                            f"再用 workpackage_status 確認工作包往下走；使用者只要查原因時就回報。")
    if not diag:
        diag.append("看不出異常（沒有正在授權的任務，或交握還在進行）；要觀察久一點可以加 --seconds 10。")
    out = f"[PASS] {rid} 的交握狀況：\n" + "\n".join(lines) + "\n判斷：\n" + "\n".join(f"- {d}" for d in diag)
    return with_target_marker(out, container) if container else out


def trigger(kind, robots, args, task_id=None):
    trig = (_opt(args, "--trigger", TRIGGER_URL) or TRIGGER_URL).rstrip("/")
    if kind in ("yes", "no"):
        body = [{"robot_name": r, "is_authored": kind} for r in robots]
        path = "/batch_handshake"
    else:
        body = [{"robot_name": robots[0], "task_id": task_id}]
        path = "/batch_task_exec_fin"
    code, text, err = rc._http("POST", trig, path, body)
    if err:
        return err.replace("web_console", "manual_trigger").replace("port 8020", "port 8002")
    try:
        data = json.loads(text or "{}")
    except ValueError:
        data = {}
    if kind == "fin":
        return f"[PASS] 已補發 /{robots[0]}/task_exec_fin（task_id={task_id}）：{data.get('status', code)}"
    return f"[PASS] 已手動對 {'、'.join(robots)} 回 handshake {kind}：{data.get('status', code)}（{data.get('count', len(robots))} 則）"


def main(argv):
    args = list(argv)
    if len(args) < 2 or args[0] not in ("status", "yes", "no", "fin"):
        return f"[ERROR] 參數不對。\n{USAGE}"
    kind = args.pop(0)
    if kind == "status":
        rid = args.pop(0)
        return status(rid, args)
    rest, url, err = rc.split_url(args)
    if err:
        return err
    trig_args = list(rest)
    robots = [a for a in rest if not a.startswith("--") and a not in (_opt(list(rest), "--trigger") or "",)]
    if kind in ("yes", "no"):
        robots = [r for r in robots if re.match(r"^[A-Za-z][\w-]*$", r)]
        if not robots:
            return f"[ERROR] 要指定機器人。\n{USAGE}"
        return trigger(kind, robots, trig_args)
    rid = robots[0] if robots else ""
    task_id = robots[1] if len(robots) > 1 else None
    if not task_id:
        data, err = _snapshot(url)
        if err:
            return f"[ERROR] 沒有給 task_id，又讀不到 web_console 的快照找 {rid} 目前的工作項：{err}"
        _, _, _, _, pkgs = _robot_view(data, rid)
        cands = [(p.get("current_item") or {}).get("item_id") for p in pkgs
                 if (p.get("current_item") or {}).get("status") == "DISPATCHED" and (p.get("current_item") or {}).get("robot_id") == rid]
        if len(cands) != 1:
            return (f"[ERROR] 找不到 {rid} 唯一一個在等完成訊號的工作項（找到 {len(cands)} 個：{'、'.join(c for c in cands if c) or '無'}）；"
                    f"請指定 task_id（用 workpackage_status 看目前工作項）。")
        task_id = cands[0]
    return trigger("fin", [rid], trig_args, task_id)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] rmf_handshake 未預期的例外：{e}")
