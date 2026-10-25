"""rmf_handshake：調度系統（distribute）與機器人之間的授權交握——看某台機器人的交握狀況並自動判斷原因，必要時手動回交握或
補發完成訊號（manual_trigger）。

交握流程（resource_allocator.py、TaskAgent）：distribute 每 0.5 秒對選中的機器人發 /{rid}/allocator_status（AllocatorCommand
authorize），機器人回 /{rid}/handshake_states（HandshakeState is_authored：yes／no，沒有 task_id）；看到 yes 就 confirm、工作項移出
distribute；機器人做完發 /{rid}/task_exec_fin（TaskExecutionFinished），orchestrtor 收到才派下一站。授權逾時（預設 10 秒）→
OverPending，冷卻後重試。

  status <機器人或工作包> [--seconds N] [--container 容器]
      唯讀：web_console 的快照（欄位同 msg_codec：ONLINE／OFFLINE、顯示狀態、自報狀態、最後領取的工作項；工作包目前的工作項與它在
      distribute 的哪個佇列；distribute 事件裡提到的機器人）＋在 ROS 2 容器裡等訂閱配對上之後聽 N 秒（預設 4，1～60）/{rid}/allocator_status 與
      /{rid}/handshake_states（rclpy；載入 ROS 環境與 Workspace：自訂型別 fih_rmf_msgs 才收得到；記下 graph 上的發布者數與每一則的時間，聽完再讀一次快照），判斷：離線、沒有回應授權、
      一直回 no、完成訊號遺失、在等忙碌的機器人、交握正常。什麼都觀察不到時寫「無法判斷（原因）」，不會說「看不出異常」。
  yes|no <機器人> [<機器人> …]   手動回交握（manual_trigger POST /batch_handshake）——會先請使用者確認。
  fin <機器人> [<task_id>]        補發完成訊號（POST /batch_task_exec_fin）；task_id 省略＝那台機器人目前在等完成訊號的工作項，
                                  也可以給工作包 id（換成它目前的工作項）——會先請使用者確認。
yes／no／fin 送出前核對機器人名冊（/api/robots＋快照）；fin 的 task_id 要是某個工作包目前在等的工作項。拿不到名冊／快照時不送
（--no-check 才照原樣送）。送出後讀快照確認效果（confirm、工作包往下一站）。
位址：--url web_console（預設 RMF_WEB_CONSOLE_URL 或 http://localhost:8020）、--trigger manual_trigger（預設
RMF_MANUAL_TRIGGER_URL 或 http://localhost:8002；它不在 rmf_launch.py 裡，要另外 `ros2 run fih_rmf_system manual_trigger`）。
parse_args(argv) 是純函式（guard 用它判斷 status 是唯讀的）。
"""
import json
import os
import re
import shlex
import signal
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rmf_common as rc   # noqa: E402

ACTIONS = ("status", "yes", "no", "fin")
DEFAULT_SECONDS, MAX_SECONDS = 4, 60
MAP_WATCH_SECONDS = 12             # 工作包的機器人在第一幀看不出來時，持續看快照的上限（等它進 processing 或事件提到）
LISTEN_STARTUP_SECONDS = 25        # docker exec＋ros2 CLI 啟動的餘裕（容器內的逾時＝秒數＋這個）
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
LISTEN_DISCOVERY_SECONDS = 3.0      # 等兩個 topic 的發布者出現在 graph 上（看不到就照實記 0 個）
LISTEN_MATCH_SECONDS = 2.0          # 等訂閱跟發布者配對上；之後才開始計時，聽滿 --seconds
TIMELINE_SHOW = 12                  # 聽到的訊息在輸出裡列幾則（時間＋內容），其餘寫另有幾則

USAGE = ("用法: scripts/rmf_handshake_cmd.py status <機器人或工作包> [--seconds N] [--container 容器] [--url 位址]\n"
         "      scripts/rmf_handshake_cmd.py yes|no <機器人> [<機器人> …] [--trigger 位址] [--url 位址] [--no-check]\n"
         "      scripts/rmf_handshake_cmd.py fin <機器人> [<task_id 或工作包>] [--trigger 位址] [--url 位址] [--no-check]\n"
         f"  --seconds 聽 topic 的秒數（預設 {DEFAULT_SECONDS}，1～{MAX_SECONDS}）；--container 跑 ROS 2 的容器（預設目前的目標容器）")

try:                                # 目標容器標記：用共用層的（另一支程式維護）；拿不到就用同樣的格式
    from _docker_common import with_target_marker   # noqa: E402
except ImportError:                 # pragma: no cover
    def with_target_marker(output, container):
        container = (container or "").strip()
        if not container or container == (os.environ.get("TARGET_CONTAINER") or "").strip():
            return output
        return f"{output.rstrip()}\n[TARGET_CONTAINER] {container}"


# ---------------------------------------------------------------- 參數（純函式）
def parse_args(argv):
    """純函式（不連線、不印），guard 也用它。回傳 dict：error（None 或 [ERROR] 訊息；有錯時腳本在任何連線之前就回這個錯誤）、
    action（status／yes／no／fin）、readonly（status＝True）、target（status 的機器人或工作包）、robots（yes／no／fin）、
    task_id（fin，可省略）、seconds、container（None＝沒指定）、url、trigger、no_check。"""
    if not argv or argv[0] not in ACTIONS:
        got = argv[0] if argv else "（沒有參數）"
        hint = ""
        if argv and any(a in ACTIONS for a in argv[1:]):
            hint = f"（動作要放第一個，例如 {next(a for a in argv if a in ACTIONS)} {argv[0]}）"
        return {"error": f"[ERROR] 第一個參數要是動作 status／yes／no／fin，收到 {got!r}{hint}。\n{USAGE}", "action": None, "readonly": False}
    action = argv[0]
    out = {"error": None, "action": action, "readonly": action == "status", "ignored": []}
    pos, opts, err = rc.parse_cli(argv[1:], values={"--seconds": f"秒數（1～{MAX_SECONDS}）", "--container": "ROS 2 容器名稱",
                                                    "--url": "web_console 位址（例如 http://localhost:8020）",
                                                    "--trigger": "manual_trigger 位址（例如 http://localhost:8002）"},
                                  flags=("--no-check",), elsewhere={"--watch": "workpackage_status", "--until-done": "workpackage_status",
                                                                     "--wait": "overpending_cancel"},
                                  usage=USAGE)
    if err:
        return dict(out, error=err)
    # 用不到的選項（status 的 --trigger、yes／no／fin 的 --seconds／--container）不影響送出的內容：略過，輸出最後一行說明
    unused = ("--trigger", "--no-check") if action == "status" else ("--seconds", "--container")
    ignored = [f"{o} {opts.pop(o)}" if opts.get(o) is not True else o for o in unused if o in opts]
    out["ignored"] = ignored
    seconds = DEFAULT_SECONDS
    if "--seconds" in opts:
        seconds, err = rc.parse_seconds(opts["--seconds"], "--seconds", 1, MAX_SECONDS)
        if err:
            return dict(out, error=err)
    container = opts.get("--container")
    if container is not None and not CONTAINER_RE.match(container.strip()):
        return dict(out, error=f"[ERROR] --container {container!r} 不是合法的容器名稱。下一步：用 docker_containers 查完整名稱。")
    url, err = rc.resolve_url(opts.get("--url"))
    if err:
        return dict(out, error=err)
    trigger, err = rc.resolve_url(opts.get("--trigger"), "manual_trigger")
    if err:
        return dict(out, error=err)
    out.update(seconds=seconds, container=container.strip() if container else None, url=url, trigger=trigger,
               no_check=bool(opts.get("--no-check")), target=None, robots=[], task_id=None)
    if action == "status":
        if len(pos) != 1:
            return dict(out, error=f"[ERROR] status 要 1 個機器人或工作包，收到 {len(pos)} 個（一次查一個；多台就分開執行）。\n{USAGE}")
        target = pos[0].strip()
        if not target or re.search(r"[\s,]", target):
            return dict(out, error=f"[ERROR] status 的對象 {target!r} 不能是空的或含空白、逗號（一次查一個機器人或工作包）。\n{USAGE}")
        return dict(out, target=target)
    names = [x.strip() for p in pos for x in p.split(",") if x.strip()]
    if action == "fin":
        if not 1 <= len(names) <= 2:
            return dict(out, error=f"[ERROR] fin 要 <機器人> [<task_id>]，收到 {len(names)} 個參數（{'、'.join(names) or '沒有'}）。\n{USAGE}")
        err = rc.robot_id_error(names[0])
        if err:
            return dict(out, error=err + "（fin 的第一個參數是機器人，第二個才是 task_id）")
        return dict(out, robots=names[:1], task_id=names[1] if len(names) > 1 else None)
    if not names:
        return dict(out, error=f"[ERROR] {action} 要指定至少一台機器人（例如 {action} amr_07 amr_12，或 {action} amr_07,amr_12）。\n{USAGE}")
    for rid in names:
        err = rc.robot_id_error(rid)
        if err:
            return dict(out, error=err)
    return dict(out, robots=list(dict.fromkeys(names)))


# ---------------------------------------------------------------- 快照裡找關係
def _mentions(text, rid):
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(rid)}(?![A-Za-z0-9_])", str(text)) is not None


def _event_robots(data, item_id, names):
    """distribute／orchestrtor 的事件裡跟這個工作項一起出現的機器人（快照沒有 assign_amr，只能從事件看出指定給誰）。"""
    found = []
    for e in (data.get("events") or []) + ((data.get("orchestrtor") or {}).get("events") or []):
        if item_id and item_id in str(e):
            for rid in names:
                if _mentions(e, rid) and rid not in found:
                    found.append(rid)
    return found


def _package_robots(data, pkg, names):
    """工作包目前的工作項對到的機器人：目前顯示的 robot_id → processing 的機器人 → 最後領取它的機器人 → 事件裡提到的。"""
    cur = (pkg or {}).get("current_item") or {}
    iid = cur.get("item_id")
    out = []
    if cur.get("robot_id"):
        out.append(cur["robot_id"])
    for t in data.get("processing_tasks") or []:
        if t.get("id") == iid and t.get("robot"):
            out.append(t["robot"])
    for rid, info in (data.get("robots") or {}).items():
        if iid and (info or {}).get("last_task_id") == iid:
            out.append(rid)
    out += _event_robots(data, iid, names)
    return list(dict.fromkeys(r for r in out if r))


def _watch_for_robot(url, pkg_id, names, seconds=MAP_WATCH_SECONDS):
    """第一幀看不出工作包的機器人時（工作項在 raw／OverPending，快照沒有 assign_amr），持續看快照：工作項進 processing 的那一刻
    distribute 對誰授權、或事件裡跟它一起出現的機器人。回傳 (機器人清單或 None, 那一幀, 看了幾秒)。"""
    data, t = None, 0.0
    try:
        with rc.WsStream(url) as ws:
            for t, data in ws.frames(duration=seconds):
                pkg = rc.find_package(data, pkg_id)
                if not pkg or pkg.get("status") != "RUNNING":
                    return None, data, t
                cands = _package_robots(data, pkg, names)
                if cands:
                    return cands, data, t
    except rc._WsError:
        pass
    return None, data, t


def _robot_items(data, rid, names):
    """這台機器人相關的：正在授權的工作項、目前工作項對到它的工作包、事件裡跟它一起出現而且還在 raw／OverPending 的工作項。"""
    processing = [t for t in data.get("processing_tasks") or [] if t.get("robot") == rid]
    pkgs = [p for p in rc.packages(data) if p.get("status") == "RUNNING" and rid in _package_robots(data, p, names)]
    waiting = []
    for key in ("raw_tasks", "overpending_tasks"):
        for t in data.get(key) or []:
            if rid in _event_robots(data, t.get("id"), names):
                waiting.append((key, t))
    return processing, pkgs, waiting


# ---------------------------------------------------------------- 聽 topic（在容器裡）
_LISTEN_PY = r"""
import json, os, sys, time
rid, seconds, discovery, match = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
out = {"domain": os.environ.get("ROS_DOMAIN_ID", "")}
try:
    import rclpy
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
except Exception as e:
    out.update(error="NO_ROS2", detail=str(e)[:200]); print(json.dumps(out)); sys.exit(0)
try:
    from fih_rmf_msgs.msg import AllocatorCommand, HandshakeState
except Exception as e:
    out.update(error="NO_MSGS", detail=str(e)[:200]); print(json.dumps(out)); sys.exit(0)
rclpy.init()
node = rclpy.create_node("agent_handshake_listen")
spec = {"A": ("/%s/allocator_status" % rid, AllocatorCommand, "command"),
        "H": ("/%s/handshake_states" % rid, HandshakeState, "is_authored")}
start, events = [None], []
def make_cb(tag, field):
    def cb(msg):
        if start[0] is not None:
            events.append([round(time.monotonic() - start[0], 2), tag, str(getattr(msg, field, ""))])
    return cb
def spin_until(cond, sec):
    end = time.monotonic() + sec
    while time.monotonic() < end and not cond():
        rclpy.spin_once(node, timeout_sec=0.05)
spin_until(lambda: all(node.count_publishers(t) for t, _, _ in spec.values()), discovery)
pubs, subs = {}, {}
for tag, (topic, cls, field) in spec.items():
    infos = node.get_publishers_info_by_topic(topic)
    pubs[tag] = len(infos)
    rel = (ReliabilityPolicy.BEST_EFFORT if any(i.qos_profile.reliability == ReliabilityPolicy.BEST_EFFORT for i in infos)
           else ReliabilityPolicy.RELIABLE)
    subs[tag] = node.create_subscription(cls, topic, make_cb(tag, field),
                                         QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=100, reliability=rel,
                                                    durability=DurabilityPolicy.VOLATILE))
can_ask = all(hasattr(x, "get_publisher_count") for x in subs.values())
if can_ask:
    spin_until(lambda: all(subs[t].get_publisher_count() >= min(1, pubs[t]) for t in subs), match)
else:
    spin_until(lambda: False, 0.5)
start[0] = time.monotonic()
spin_until(lambda: False, seconds)
out.update(publishers=pubs, events=events, seconds=seconds,
           matched={t: (x.get_publisher_count() if can_ask else None) for t, x in subs.items()})
print(json.dumps(out))
node.destroy_node()
try:
    rclpy.shutdown()
except Exception:
    pass
"""


def _listen_command(rid, seconds):
    """容器裡的 rclpy 小程式：等兩個 topic 的發布者出現、訂閱配對上之後才開始計時，聽滿 seconds 秒；每一則記下時間，最後印一行 JSON。
    以前用兩個 `ros2 topic echo`，從程序啟動就開始算秒數——CLI 啟動加上配對常吃掉大半，偶爾一則都收不到，「回 no」被判成「沒有回應」、
    什麼都沒聽到被判成「容器或 ROS_DOMAIN_ID 不對」（2026-10-23 維運評測：忙碌的 tb3 在 hs_busy_diag／cx_reassign 被判錯 8 次）。"""
    return ("command -v python3 >/dev/null 2>&1 || { echo '{\"error\": \"NO_PY\"}'; exit 0; }; "
            f"python3 -c {shlex.quote(_LISTEN_PY)} {rid} {seconds} {LISTEN_DISCOVERY_SECONDS} {LISTEN_MATCH_SECONDS}")


def _listen(container, rid, seconds):
    """回傳 dict：ok、error（無法觀察的原因）、authorize、confirm、other、yes、no、publishers（{"A": n, "H": n}，graph 上的發布者數）、
    timeline（[(秒, 標記, 值)]，從開始計時算起）、domain、noise（看不懂的輸出）。"""
    if rc.robot_id_error(rid):          # 機器人 id 會進容器的 shell：一定要先驗證
        return {"ok": False, "error": f"{rid!r} 不是合法的機器人 id"}
    from _docker_common import ros2_exec
    budget = seconds + LISTEN_STARTUP_SECONDS + LISTEN_DISCOVERY_SECONDS + LISTEN_MATCH_SECONDS
    ok, out, err = ros2_exec(container, _listen_command(rid, seconds), int(budget) + 1)
    if not ok and not out:
        err = re.sub(r"`[^`]*`", "`python3`（聽交握 topic）", err[8:] if err.startswith("[ERROR]") else err)
        return {"ok": False, "error": rc.clip(err, 300)}
    found, noise = None, []
    for ln in (out or "").splitlines():
        ln = ln.strip()
        if ln.startswith("{") and ln.endswith("}"):
            try:
                found = json.loads(ln)
                continue
            except ValueError:
                pass
        if ln and not re.search(r"KeyboardInterrupt|Traceback|^\s*File |rclpy|^\^C", ln):
            noise.append(ln)
    if found is None:
        return {"ok": False, "error": rc.clip("聽 topic 的程式沒有回報結果：" + (" ｜ ".join(noise[:3]) or err or "沒有輸出"), 300)}
    if found.get("error") == "NO_PY":
        return {"ok": False, "error": f"容器 {container} 裡沒有 python3，聽不了交握 topic"}
    if found.get("error") == "NO_ROS2":
        return {"ok": False, "error": f"容器 {container} 裡載不到 rclpy（不是 ROS 2 容器，或沒有 source /opt/ros）"}
    if found.get("error") == "NO_MSGS":
        return {"ok": False, "error": (f"容器 {container} 載不到 fih_rmf_msgs（沒有 source fih_rmf_system 的 Workspace），聽不了交握 topic。"
                                       f"下一步：先用 ROS2_workspace_env 設定這個容器的 Workspace，或 --container 換到跑 fih_rmf_system 的那個容器（名稱先用 docker_containers 查）")}
    res = {"ok": True, "error": None, "authorize": 0, "confirm": 0, "other": 0, "yes": 0, "no": 0, "domain": found.get("domain") or "",
           "publishers": {k: int(v) for k, v in (found.get("publishers") or {}).items()}, "timeline": [], "noise": noise}
    for t, tag, val in found.get("events") or []:
        val = str(val).strip()
        res["timeline"].append((float(t), tag, val))
        if tag == "A" and val in ("authorize", "confirm"):
            res[val] += 1
        elif tag == "H" and val in ("yes", "no"):
            res[val] += 1
        else:
            res["other"] += 1
    if not ok:
        res["partial_error"] = rc.clip(re.sub(r"`[^`]*`", "`python3`", err), 200)
    return res


def _docker_ps():
    """執行中的容器名稱（猜 ROS 2 容器用）；docker 不能用就回空清單。整個程序群組有逾時。"""
    try:
        p = subprocess.Popen(["docker", "ps", "--format", "{{.Names}}"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, start_new_session=True, text=True, errors="replace")
    except OSError:
        return []
    try:
        out, _ = p.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        return []
    return [n.strip() for n in (out or "").splitlines() if n.strip()] if p.returncode == 0 else []


def _pick_container(explicit):
    """回傳 (容器, 來源)：--container ＞ 目前的目標容器 ＞ 猜（執行中的容器裡名稱含 rmf／ros／amr 的剛好一個；猜的不設成目標容器）。"""
    if explicit:
        return explicit, "explicit"
    target = (os.environ.get("TARGET_CONTAINER") or "").strip()
    if target:
        return target, "target"
    hits = [n for n in _docker_ps() if re.search(r"rmf|ros|amr", n, re.I)]
    return (hits[0], "guess") if len(hits) == 1 else ("", "none")


# ---------------------------------------------------------------- status
def _robot_line(rid, info, topo):
    info = info or {}
    pos = ""
    if isinstance(info.get("x"), (int, float)) and isinstance(info.get("y"), (int, float)):
        pos = f"｜位置 ({info['x']:.2f}, {info['y']:.2f})"
        if info.get("target_id"):
            pos += f"｜目標 {rc.station_text(info['target_id'], topo, True)}"
    return (f"- {rid}：{info.get('status', '?')}｜顯示 {info.get('state', '?')}｜自報 {info.get('real_state') or '?'}"
            f"｜最後領取 {info.get('last_task_id') or 'None'}" + (f"｜{info['delay']} 秒前的心跳" if info.get("status") == "OFFLINE" and info.get("delay") is not None else "")
            + pos)


def _diagnose(rid, info, data, topo, lis, processing, pkgs, waiting):
    """回傳 [(重要度, 標題, 判斷文字)]；重要度越小越前面，第一行寫前幾個標題。"""
    diag = []
    if data is not None and info is None:
        diag.append((1, "快照裡沒有它的狀態", f"快照裡沒有 {rid} 的狀態（distribute 的機隊清單沒有它，或還沒收到它的狀態）：distribute 不會對它授權。"
                        f"下一步：確認 robots.yaml 有 {rid}、機器人有在發 /{rid}/robot_state。"))
    if info and info.get("status") == "OFFLINE":
        diag.append((0, "離線（OFFLINE）", f"{rid} 離線（OFFLINE：distribute 收不到它的心跳" + (f"，最後一次是 {info['delay']} 秒前" if info.get("delay") is not None else "")
                        + "）：不會對它授權，指定給它的工作項會一直等（distribute 不會改派指定的機器人）。下一步：讓機器人上線；"
                          "或經使用者同意取消工作包、改派別台。"))
    if lis and lis.get("ok"):
        auth, yes, no = lis["authorize"], lis["yes"], lis["no"]
        hp = (lis.get("publishers") or {}).get("H")
        if auth and not yes and not no:
            evidence = ("graph 上沒有任何 /{0}/handshake_states 的發布者".format(rid) if hp == 0 else
                        f"/{rid}/handshake_states 有 {hp} 個發布者，但這 {lis.get('seconds')} 秒都沒有回" if hp else "")
            diag.append((0, "沒有回應授權", f"{rid} 沒有回應授權：distribute 送了 {auth} 次 authorize，/{rid}/handshake_states 沒有任何回覆"
                            + (f"（{evidence}）" if evidence else "") + "——機器人的 TaskAgent "
                            f"可能沒在跑、沒有訂閱 allocator_status，或站點解析不出來（TaskAgent 不受理就不回）。除非使用者已經跟機器人端確認可以接、"
                            f"明確要你回 yes，**不要**自己手動回 yes（TaskAgent 沒在跑時，回了 yes distribute 會 confirm，但機器人不會真的去執行，"
                            f"工作包會卡住）；請機器人端確認 TaskAgent。使用者要回的話：rmf_handshake yes {rid}（會先請使用者確認）。"))
        elif no and not yes:
            diag.append((0, "對授權一直回 no", f"{rid} 對授權一直回 no（{no} 則；交握規則 R1：忙碌、站點無效或定位異常）→ 每次授權逾時進 OverPending、冷卻後重試，"
                            f"不會成功。下一步：請機器人端確認狀態；或經使用者同意取消工作包、改派別台。"))
        elif lis["confirm"] or (auth and yes):
            diag.append((5, "交握正常", f"交握正常：聽到 authorize {auth} 次、yes {yes} 次、confirm {lis['confirm']} 次。"))
        elif not auth and processing:
            iid = processing[0].get("id")
            ap = (lis.get("publishers") or {}).get("A")
            after = (lis.get("after") or {}).get(iid, "processing")
            if ap == 0:
                diag.append((2, "看不到 distribute 的授權 topic（容器或 ROS_DOMAIN_ID 不對？）",
                             f"快照顯示 distribute 正在對 {rid} 授權 {iid}，但聽的容器在 graph 上看不到 /{rid}/allocator_status 的發布者："
                             f"聽的容器可能不在同一個 ROS_DOMAIN_ID（這次用 {lis.get('domain') or '預設 0'}），或不是同一個網路。"
                             f"下一步：--container 換成跑 fih_rmf_system 的那個容器（名稱先用 docker_containers 查）。"))
            elif after != "processing":
                where = {"OverPending": "OverPending 冷卻（授權逾時）", "raw": "raw 等待"}.get(after, after or "離開 distribute")
                diag.append((3, "這幾秒剛好沒有授權（工作項在冷卻／等待）",
                             f"這 {lis.get('seconds')} 秒剛好沒有授權：聽之前 {iid} 正在對 {rid} 授權，聽完的快照它在 {where}，那段時間 distribute 本來就不送 "
                             f"authorize。最近的事件：{_event_text(data, iid)}。下一步：要分辨「沒回應」還是「回 no」就加 --seconds 15 再聽一次（跨過冷卻時間）。"))
            else:
                diag.append((2, "有發布者但聽不到 authorize",
                             f"distribute 有在發布 /{rid}/allocator_status（graph 上 {ap} 個發布者），聽之前與聽完 {iid} 都在對 {rid} 授權，但這 "
                             f"{lis.get('seconds')} 秒沒有收到 authorize。下一步：加 --seconds 15 再聽一次；還是一樣就請使用者看 distribute（resource_allocator）的 log。"))
        elif not auth and waiting and not (info and info.get("status") == "OFFLINE"):
            key, t = waiting[0]
            where = "OverPending 冷卻" if key == "overpending_tasks" else "raw 等待"
            diag.append((3, "這幾秒剛好沒有授權（工作項在冷卻／等待）", f"這 {lis.get('seconds')} 秒剛好沒有授權：{t.get('id')} 在 {where}（事件顯示它指定給 {rid}）。最近的事件："
                            f"{_event_text(data, t.get('id'))}。下一步：要分辨「沒回應」還是「回 no」就加 --seconds 15 再聽一次（跨過冷卻時間）。"))
    if data is not None and not (lis and lis.get("ok")):
        timeouts = [e for e in data.get("events") or [] if re.search(rf"授權逾時[（(]\s*{re.escape(rid)}(?![A-Za-z0-9_])", str(e))]
        if timeouts:
            diag.append((3, "授權逾時（沒有在時限內回 yes）", f"事件顯示對 {rid} 的授權逾時 {len(timeouts)} 次（{rid} 沒有在時限內回 yes）：可能沒回應，"
                            f"也可能一直回 no，沒聽 topic 分不出來。最近一則：{timeouts[-1]}。下一步：加 --container <容器名稱>（跑 fih_rmf_system 的那個，名稱先用 docker_containers 查） "
                            f"--seconds 15 聽交握 topic 分辨。"))
    for p in pkgs:
        cur = p.get("current_item") or {}
        iid = cur.get("item_id")
        if cur.get("status") != "DISPATCHED" or rc.queue_of(data, iid)[0]:
            continue
        if rc.robot_idle(info):
            lost = rc.fin_lost(data, p, topo, rid)            # 同 workpackage_status --until-done 提早結束的判斷
            station = rc.station_text(cur.get("station"), topo)
            if lost:
                dist = lost["distance"]
                where = f"已經在 {station}（距 {dist:.2f}）" if dist is not None else f"已經閒置（座標對不到 {station}）"
                diag.append((0, "完成訊號多半遺失了（task_exec_fin）", f"完成訊號多半遺失了：工作包 {p.get('package_id')} 的工作項 {iid} 已經 confirm 給 {rid}，{rid} {where}、自報 standby，"
                                f"但 orchestrtor 還在等 /{rid}/task_exec_fin。使用者要你處理的話，下一步直接執行 `rmf_handshake fin {rid} {iid}` 補發"
                                f"（系統會請使用者確認，不用先問），再用 workpackage_status {p.get('package_id')} --until-done 等它跑完；只要查原因就回報。"))
            else:
                dist = rc.distance_to(info, cur.get("station"), topo)
                diag.append((1, "領了工作項但沒有在動（不是完成訊號遺失）", f"{rid} 領了 {iid}（{station}）但自報 standby、離那一站還有 {dist:.2f}：可能還沒出發或導航失敗，不是完成訊號遺失；"
                                f"不要補發 fin。下一步：觀察一下（workpackage_status {p.get('package_id')} --watch 20），沒有動靜就請機器人端確認導航。"))
        elif info and info.get("real_state") == "running":
            diag.append((4, "正在執行工作項", f"{rid} 正在執行 {iid}（自報 running），工作包 {p.get('package_id')} 等它做完——還沒到站不是異常。"))
    if info and info.get("status") == "ONLINE" and waiting and info.get("real_state") == "running" and not processing:
        key, t = waiting[0]
        diag.append((2, "工作項在等它，但它正在忙", f"{t.get('id')} 在等 {rid}，但 {rid} 正在忙（自報 running，最後領取 {info.get('last_task_id')}）：distribute 不會改派指定的機器人，"
                        f"等它做完就會授權。"))
    return sorted(diag, key=lambda d: d[0])


def _event_text(data, item_id, n=2):
    evs = [e for e in (data.get("events") or []) if item_id and item_id in str(e)]
    return "；".join(evs[-n:]) or "（沒有）"


def status(p):
    url, target = p["url"], p["target"]
    data, serr = rc.ws_read_json(url)
    topo, _ = rc.fetch_topology(url) if data is not None else (None, None)
    names = []
    if data is not None:
        names, _ = rc.fetch_roster(url, data)
    lines, prefix = [], ""
    rid = None
    if data is not None and target in names:
        rid = target
    elif data is not None:
        pkg = rc.find_package(data, target) or (rc.item_package(data, target) if "::" in target else None)
        if pkg:
            cur = pkg.get("current_item") or {}
            cands = _package_robots(data, pkg, names)
            label, t = rc.queue_of(data, cur.get("item_id"))
            where = f"distribute {rc.queue_text(label, t)}" if label else ("不在 distribute（已 confirm 給機器人）" if cur.get("robot_id") else "不在 distribute")
            lines.append(f"- 工作包 {pkg.get('package_id')} {pkg.get('status')}：第 {(pkg.get('station_index') or 0) + 1}/{pkg.get('station_count')} 站 "
                         f"{rc.station_text(cur.get('station'), topo)}，工作項 {cur.get('item_id')} {cur.get('status')}（{where}）")
            if pkg.get("status") == "COMPLETED":
                return f"[PASS] 工作包 {pkg.get('package_id')} 已經 COMPLETED，沒有進行中的交握。\n" + "\n".join(lines)
            if not cands:
                cands, fresh, waited = _watch_for_robot(url, pkg.get("package_id"), names)
                if cands:
                    data = fresh
                    lines.append(f"- 看了 {waited:.1f} 秒快照才看出它的機器人（工作項在 raw／OverPending 時快照沒有 assign_amr）")
                else:
                    return (f"[PASS] {target}：目前的工作項還沒配到機器人；看了 {waited:.1f} 秒快照都看不出指定給哪台"
                            f"（快照不含 assign_amr，這段時間它沒進 processing、事件裡也沒提到）。\n"
                            + "\n".join(lines) + "\n## 判斷\n"
                            + f"- {cur.get('item_id')} 在 {where}，還在等可以接的機器人。最近的事件：{_event_text(data, cur.get('item_id'))}。"
                            + "下一步：問使用者這個工作包指定哪台機器人，再用 rmf_handshake status <機器人> 查；或用 workpackage_status --watch 20 看它有沒有被配出去。")
            rid = cands[0]
            prefix = f"{target} → "
            if len(cands) > 1:
                lines.append(f"- 跟這個工作項有關的機器人：{'、'.join(cands)}（先看 {rid}）")
        elif not names and not rc.robot_id_error(target):
            rid = target
            lines.append(f"- ⚠️ 機器人名冊是空的（robots.yaml 沒有載入、distribute 也沒有機器人），沒辦法核對 {target}")
        else:
            ids = [x.get("package_id") for x in rc.packages(data)]
            close = rc.close_matches(target, names + ids)
            return (f"[ERROR] 機器人名冊裡沒有 {target}，它也不是工作包或工作項"
                    + (f"（相近的：{'、'.join(close)}）" if close else "")
                    + f"。機器人：{'、'.join(names) or '（沒有）'}；工作包：{'、'.join(map(str, ids[:15])) or '（沒有）'}。"
                    + "下一步：改用名冊上的機器人 id 或現有的工作包 id；使用者給的對不上就問使用者。")
    else:
        if rc.robot_id_error(target):
            return (f"{serr}\n（讀不到快照，沒辦法把 {target!r} 對到機器人；status 的對象要是機器人 id 才能直接聽 topic。）")
        rid = target
    info = ((data or {}).get("robots") or {}).get(rid) if data is not None else None
    processing, pkgs, waiting = _robot_items(data, rid, names) if data is not None else ([], [], [])
    # 聽 topic
    container, how = _pick_container(p["container"])
    lis = None
    if container:
        lis = _listen(container, rid, p["seconds"])
        lis["seconds"] = p["seconds"]
        if lis.get("ok") and data is not None and processing:
            after, _ = rc.ws_read_json(url)          # 聽完再看一次：工作項在聽的期間可能逾時進了 OverPending（那段時間本來就沒有授權）
            if after is not None:
                lis["after"] = {t.get("id"): rc.queue_of(after, t.get("id"))[0] for t in processing}
    # 輸出
    out = [f"## 快照（web_console {url}）"]
    if data is None:
        out.append(f"- ⚠️ 讀不到：{rc.clip(serr[8:], 200)}")
    else:
        out += lines
        out.append(_robot_line(rid, info, topo) if info else f"- {rid}：快照裡沒有它的狀態")
        for t in processing:
            out.append(f"- 正在對 {rid} 授權：{t.get('id')}（站點 {rc.station_text(t.get('station'), topo)}）")
        for key, t in waiting:
            what = f"OverPending（已在逾時區 {t.get('wait')}s）" if key == "overpending_tasks" else f"raw（已等 {t.get('age')}s）"
            out.append(f"- 在等 {rid} 的工作項：{t.get('id')} 在 {what}；事件：{_event_text(data, t.get('id'))}")
        for pk in pkgs:
            if prefix and pk.get("package_id") in (target, target.split("::", 1)[0]):
                continue                                  # 上面已經列過
            cur = pk.get("current_item") or {}
            out.append(f"- 工作包 {pk.get('package_id')} {pk.get('status')}：第 {(pk.get('station_index') or 0) + 1}/{pk.get('station_count')} 站 "
                       f"{rc.station_text(cur.get('station'), topo)}，工作項 {cur.get('item_id')} {cur.get('status')}")
    marker = None
    if not container:
        out.append("## 聽 topic\n- 沒有聽：沒有指定 --container、沒有目標容器，也猜不到跑 ROS 2 的容器（執行中的容器裡沒有剛好一個名稱含 rmf／ros／amr 的）；要聽交握 topic 請加 --container <容器>")
    elif not lis["ok"]:
        out.append(f"## 聽 topic（容器 {container}{'，自動選的' if how == 'guess' else ''}）\n- 無法觀察：{lis['error']}")
    else:
        dom = f"，ROS_DOMAIN_ID {lis['domain'] or '0（預設）'}" if lis.get("domain") is not None else ""
        out.append(f"## 聽 topic（容器 {container}{'，自動選的：要固定用它請加 --container ' + container if how == 'guess' else ''}，"
                   f"訂閱配對上之後聽 {p['seconds']} 秒{dom}）")
        pubs = lis.get("publishers") or {}
        out.append(f"- /{rid}/allocator_status：authorize {lis['authorize']}、confirm {lis['confirm']}" + (f"、其他 {lis['other']}" if lis["other"] else "")
                   + (f"（graph 上的發布者 {pubs['A']} 個）" if "A" in pubs else ""))
        out.append(f"- /{rid}/handshake_states：yes {lis['yes']}、no {lis['no']}" + (f"（graph 上的發布者 {pubs['H']} 個）" if "H" in pubs else ""))
        tl = lis.get("timeline") or []
        if tl:
            words = [f"+{t:.1f}s {v if tag == 'A' else '回 ' + v}" for t, tag, v in tl[:TIMELINE_SHOW]]
            out.append("- 時間線（從開始聽算起）：" + "、".join(words) + (f"…另有 {len(tl) - TIMELINE_SHOW} 則" if len(tl) > TIMELINE_SHOW else ""))
        for iid, label in (lis.get("after") or {}).items():
            if label != "processing":
                out.append(f"- 聽完的快照：{iid} " + (f"在 {label}" if label else "已離開 distribute"))
        if lis["noise"] and not (lis["authorize"] or lis["yes"] or lis["no"]):
            out.append(f"- ros2 的訊息：{rc.clip(' ｜ '.join(lis['noise'][:3]), 300)}")
        if lis.get("partial_error"):
            out.append(f"- ⚠️ 聽的指令沒有正常結束：{lis['partial_error']}")
        if how != "guess":
            marker = container
    observed = data is not None or (lis is not None and lis.get("ok"))
    if not observed:
        why = [f"快照：{rc.clip(serr[8:], 160)}"]
        why.append("聽 topic：" + (lis["error"] if lis else "沒有可以聽的 ROS 2 容器"))
        return (f"[ERROR] 看不到 {rid} 的任何資料，無法判斷交握狀況：{'；'.join(why)}。下一步：先讓 web_console 恢復（或用 --url 指到正確的位址），"
                f"或加 --container <容器名稱>（跑 fih_rmf_system 的那個，名稱先用 docker_containers 查） 直接聽 topic。")
    diag = _diagnose(rid, info, data, topo, lis, processing, pkgs, waiting)
    if not diag:
        gaps = []
        if data is None:
            gaps.append("快照讀不到")
        if not lis or not lis.get("ok"):
            gaps.append("沒有聽到 topic" if not lis else f"聽 topic 失敗（{rc.clip(lis['error'], 80)}）")
        if data is not None and info and info.get("status") == "ONLINE" and not (processing or pkgs or waiting):
            diag = [(8, "目前沒有它的工作項", f"快照裡沒有正在對 {rid} 授權、也沒有在等它的工作項（自報 {info.get('real_state') or '?'}）"
                        + ("；沒有聽交握 topic（" + ("沒有可以聽的容器" if not lis else rc.clip(lis['error'], 80)) + "）" if gaps else "")
                        + "。要查某個工作包為什麼沒動，改用 rmf_handshake status <工作包>。")]
        elif gaps:
            diag = [(9, "無法判斷（只看得到一半的資料）", f"無法判斷：{'、'.join(gaps)}，只看得到一半的資料（上面列的就是全部）。下一步："
                        + ("加 --container <容器名稱>（跑 fih_rmf_system 的那個，名稱先用 docker_containers 查） 聽交握 topic。" if not lis or not lis.get("ok") else "先讓 web_console 恢復再查一次。"))]
        else:
            diag = [(9, "看不出異常", f"看不出異常：{rid} 目前沒有正在授權的工作項，這 {p['seconds']} 秒也沒有交握訊息。要觀察久一點加 --seconds 15。")]
    titles = list(dict.fromkeys(title for _, title, _ in diag))
    head = f"[PASS] {prefix}{rid} 的交握狀況：{'；'.join(titles[:3])}"
    text = head + "\n" + "\n".join(out) + "\n## 判斷\n" + "\n".join(f"- {d}" for _, _, d in diag)
    return with_target_marker(text, marker) if marker else text


# ---------------------------------------------------------------- yes／no／fin
def _verify_robots(p, data):
    names, err = rc.fetch_roster(p["url"], data)
    if err:
        if p["no_check"]:
            return None, f"⚠️ 沒有核對機器人名冊（--no-check；{rc.clip(err[8:], 80)}）"
        return (f"[ERROR] 拿不到機器人名冊，沒辦法確認 {'、'.join(p['robots'])} 是這個場域的機器人；沒有送出。原因：{err[8:]}\n"
                f"下一步：先讓 web_console 恢復（或用 --url 指到正確的位址）；使用者確定 id 正確時才加 --no-check。"), None
    bad = [r for r in p["robots"] if r not in names]
    if bad:
        close = rc.close_matches(bad[0], names)
        return (f"[ERROR] 機器人名冊裡沒有 {'、'.join(bad)}" + (f"（相近的：{'、'.join(close)}）" if close else "")
                + f"：現有 {len(names)} 台：{'、'.join(names)}；沒有送出。下一步：改用名冊上的 id，或問使用者是哪一台。"), None
    return None, ""


def handshake(p):
    data, serr = rc.ws_read_json(p["url"])
    if serr and not p["no_check"]:
        return (f"{serr}\n（手動回交握前要先從快照確認機器人與正在授權的工作項；沒有送出。使用者確定要直接送才加 --no-check。）")
    err, note = _verify_robots(p, data)
    if err:
        return err
    kind = p["action"]
    effects, pending = [], {}
    for rid in p["robots"]:
        proc = [t for t in (data or {}).get("processing_tasks") or [] if t.get("robot") == rid]
        if proc:
            pending[rid] = proc[0].get("id")
            effects.append(f"- {rid}：distribute 正在對它授權 {proc[0].get('id')}" + ("，yes 會讓 distribute 送出 confirm" if kind == "yes"
                                                                                     else "，no 只會讓這次授權繼續等到逾時、進 OverPending"))
        elif data is not None:
            effects.append(f"- {rid}：目前沒有正在對它授權的工作項" + ("——distribute 會留著這個 yes，下一筆派給它的工作項會直接 confirm"
                                                                   "（機器人不一定真的接）" if kind == "yes" else "（no 沒有作用）"))
    status, body, err = rc.http_json("POST", p["trigger"], "/batch_handshake",
                                     [{"robot_name": r, "is_authored": kind} for r in p["robots"]], service="manual_trigger")
    if err:
        return err
    count = body.get("count", len(p["robots"])) if isinstance(body, dict) else len(p["robots"])
    head = f"[PASS] 已經由 manual_trigger 對 {'、'.join(p['robots'])} 送出 handshake {kind}（HTTP {status}，{count} 則）"
    lines = []
    if kind == "yes" and pending:
        def check(d):
            still = [r for r, iid in pending.items()
                     if any(t.get("id") == iid and t.get("robot") == r for t in d.get("processing_tasks") or [])]
            return "done" if not still else None
        verdict, last, t, cerr = rc.confirm_after(p["url"], check)
        if verdict == "done":
            lines.append(f"快照確認：{'、'.join(f'{iid}（{r}）' for r, iid in pending.items())} 已離開 processing（distribute 已 confirm，{rc.fmt_s(t)}）。")
        elif cerr:
            lines.append(f"（讀不到快照確認：{rc.clip(cerr[8:], 120)}）")
        else:
            lines.append(f"⚠️ {rc.CONFIRM_SECONDS:g} 秒內快照中它們還在 processing：distribute 可能沒收到（manual_trigger 與 distribute 不在同一個 "
                         f"ROS_DOMAIN_ID？）。下一步：rmf_handshake status {p['robots'][0]} 再看一次。")
    if note:
        lines.append(note)
    return head + "\n" + "\n".join(effects + lines)


def _fin_candidates(data, rid):
    out = []
    info = (data.get("robots") or {}).get(rid) or {}
    for pk in rc.packages(data):
        cur = pk.get("current_item") or {}
        if pk.get("status") != "RUNNING" or cur.get("status") != "DISPATCHED":
            continue
        if cur.get("robot_id") == rid or (info.get("last_task_id") and info.get("last_task_id") == cur.get("item_id")):
            out.append((pk, cur))
    return out


def fin(p):
    rid, task_id = p["robots"][0], p["task_id"]
    data, serr = rc.ws_read_json(p["url"])
    if serr and not (p["no_check"] and task_id):
        return (f"{serr}\n（補發完成訊號前要先從快照找到 {rid} 在等的工作項；沒有送出。"
                + ("使用者確定 task_id 正確時才加 --no-check 直接送。）" if task_id else "讀不到快照時一定要給 task_id，並加 --no-check。）"))
    err, note = _verify_robots(p, data)
    if err:
        return err
    pkg, notes = None, [note] if note else []
    if data is not None:
        if task_id and "::" not in task_id and rc.find_package(data, task_id):
            pk = rc.find_package(data, task_id)
            iid = (pk.get("current_item") or {}).get("item_id")
            notes.append(f"「{task_id}」是工作包，換成它目前的工作項 {iid}")
            task_id = iid
        if task_id:
            pkg = rc.item_package(data, task_id)
            cur = (pkg or {}).get("current_item") or {}
            if not pkg or pkg.get("status") != "RUNNING" or cur.get("status") != "DISPATCHED":
                if not p["no_check"]:
                    cands = _fin_candidates(data, rid)
                    return (f"[ERROR] {task_id} 不是任何工作包目前在等完成訊號的工作項（orchestrtor 只認「目前的工作項、狀態 DISPATCHED」），"
                            f"補發不會有作用；沒有送出。"
                            + (f"{rid} 目前在等的是：{'、'.join(c.get('item_id') for _, c in cands)}。" if cands else "")
                            + "下一步：用 workpackage_status <工作包> 查目前的工作項 id 再補發。")
                notes.append(f"⚠️ 沒有核對 {task_id}（--no-check）")
        else:
            cands = _fin_candidates(data, rid)
            if len(cands) != 1:
                running = [f"{pk.get('package_id')}：{(pk.get('current_item') or {}).get('item_id')}（機器人 {(pk.get('current_item') or {}).get('robot_id') or '未定'}）"
                           for pk in rc.packages(data) if pk.get("status") == "RUNNING"]
                return (f"[ERROR] 找不到 {rid} 唯一一個在等完成訊號的工作項（找到 {len(cands)} 個"
                        + (f"：{'、'.join(c.get('item_id') for _, c in cands)}" if cands else "") + "）；沒有送出。"
                        + (f"進行中的工作包：{'；'.join(running)}。" if running else "目前沒有進行中的工作包。")
                        + f"下一步：用 rmf_handshake status {rid} 確認，再明確給 task_id。")
            pkg, cur = cands[0]
            task_id = cur.get("item_id")
            notes.append(f"task_id 省略：用 {rid} 目前在等的工作項 {task_id}（工作包 {pkg.get('package_id')}）")
        if pkg:
            cur = pkg.get("current_item") or {}
            label, t = rc.queue_of(data, task_id)
            if label and not p["no_check"]:
                return (f"[ERROR] {task_id} 還在 distribute（{rc.queue_text(label, t)}），機器人還沒領走：現在補發完成訊號，工作包會往下一站走，"
                        f"但 distribute 還會把這一站派給機器人；沒有送出。fin 是補發「完成訊號」（task_exec_fin），不是回應授權。下一步：用 rmf_handshake "
                        f"status {rid} 看交握卡在哪裡；使用者要的是替機器人回應授權（handshake yes）的話，用 rmf_handshake yes {rid}（會先請使用者確認）。")
            info = (data.get("robots") or {}).get(rid) or {}
            busy_on_it = info.get("real_state") == "running" and task_id in (info.get("last_task_id"), cur.get("item_id") if cur.get("robot_id") == rid else None)
            if busy_on_it and not p["no_check"]:
                return (f"[ERROR] {rid} 自報 running、還在執行 {task_id}（還沒到站）：現在補發完成訊號，工作包會提前往下一站走；沒有送出。"
                        f"下一步：等它到站再看（rmf_handshake status {rid}）；使用者確定要提前推進才加 --no-check。")
            if cur.get("robot_id") and cur.get("robot_id") != rid:
                notes.append(f"⚠️ 這個工作項目前顯示的機器人是 {cur['robot_id']}，不是 {rid}（orchestrtor 不核對機器人，會照樣往下走）")
    before = (pkg or {}).get("station_index"), (pkg or {}).get("iteration")
    status, body, err = rc.http_json("POST", p["trigger"], "/batch_task_exec_fin", [{"robot_name": rid, "task_id": task_id}],
                                     service="manual_trigger")
    if err:
        return err
    head = f"[PASS] 已經由 manual_trigger 補發 /{rid}/task_exec_fin（task_id={task_id}，HTTP {status}）"
    lines = list(notes)
    if pkg is not None:
        pid = pkg.get("package_id")

        def check(d):
            now = rc.find_package(d, pid)
            if not now:
                return "gone"
            cur = now.get("current_item") or {}
            if now.get("status") == "COMPLETED" or cur.get("item_id") != task_id or cur.get("status") == "CONFIRMED":
                return now
            return None
        verdict, last, t, cerr = rc.confirm_after(p["url"], check)
        topo, _ = rc.fetch_topology(p["url"])
        if isinstance(verdict, dict):
            cur = verdict.get("current_item") or {}
            state = ("已完成（COMPLETED）" if verdict.get("status") == "COMPLETED" else
                     f"往下走了：第 {(verdict.get('station_index') or 0) + 1}/{verdict.get('station_count')} 站 {rc.station_text(cur.get('station'), topo)}"
                     if cur.get("item_id") != task_id else "這一站已標成完成（下一個週期派下一站）")
            lines.append(f"快照確認：工作包 {pid} {state}（{rc.fmt_s(t)}）。" + ("" if verdict.get("status") == "COMPLETED" else
                         f"下一步：workpackage_status {pid} --until-done 等後面的站跑完（看到完成就結束）。"))
        elif verdict == "gone":
            lines.append(f"快照：工作包 {pid} 已不在清單（被刪除）。")
        elif cerr:
            lines.append(f"（讀不到快照確認：{rc.clip(cerr[8:], 120)}；用 workpackage_status {pid} 確認）")
        else:
            head = (f"[ERROR] 已補發 /{rid}/task_exec_fin（task_id={task_id}，HTTP {status}），但 {rc.CONFIRM_SECONDS:g} 秒內工作包 {pid} 沒有往下走："
                    f"orchestrtor 可能沒收到（manual_trigger 與 orchestrtor 不在同一個 ROS_DOMAIN_ID？）。下一步：workpackage_status {pid} 再確認；"
                    f"不要一直重送")
    return head + ("\n" + "\n".join(lines) if lines else "")


def main(argv):
    p = parse_args(argv)
    if p["error"]:
        return p["error"]
    run = {"status": status, "fin": fin}.get(p["action"], handshake)
    text = run(p)
    if p["ignored"]:
        note = f"（已略過 {'、'.join(p['ignored'])}：{p['action']} 用不到）"
        lines = text.rstrip().split("\n")
        if lines[-1].startswith("[TARGET_CONTAINER]"):     # 狀態標記要留在最後一行
            return "\n".join(lines[:-1] + [note, lines[-1]])
        return f"{text.rstrip()}\n{note}"
    return text


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] rmf_handshake 未預期的例外：{type(e).__name__}: {e}")
        sys.exit(1)
