"""ROS2_topic_pub：對 topic 發布訊息（ros2 topic pub）。會影響正在跑的系統（例如手動回交握、發指令），執行前由 harness
請使用者確認（parse_cli 給 guard 顯示解析後的容器、topic、型別）。預設只發一次（--once）；--times N 每秒一次、共 N 次（上限 30）。

- 參數：[容器名稱] <topic> <訊息型別> '<YAML 內容>' [--times N] [--qos 設定]。第一個參數是不是容器，看訊息型別在第幾個
  （型別一定是 套件/msg/型別、最後一段大寫開頭）：在第二個＝沒有給容器；在第三個＝第一個是容器（對不到附相近的名稱）。
  topic 少了開頭的 / 會自動補（以前 `chatter std_msgs/msg/String …` 會把 chatter 當成容器）。
- 發布前先 `ros2 topic info -v` 看訂閱者：等配對（-w 1）最多 PUB_WAIT 秒（容器內的 timeout，不會卡到整個技能逾時）；
  等不到時依訂閱者的數量說是「沒有訂閱者」還是「QoS 不相容」。訂閱端要求 TRANSIENT_LOCAL 而沒有指定 --qos 時，自動用
  transient_local 發布（Humble 的 ros2 topic pub 預設 VOLATILE，跟這種訂閱端永遠配對不上）。
- ros2 的錯誤（型別不認得、內容對不上欄位）是 stderr＋exit code 1，翻成原因與下一步（explain_error）。"""
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (clip, describe_failure, domain_text, ros2_run, split_container_arg,  # noqa: E402
                            with_target_marker)

TIMEOUT_SECONDS = 60
PUB_WAIT = 20          # 等訂閱者配對最多幾秒（--times N 時再加 N 秒）
MAX_TIMES = 30
TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*/(msg/)?[A-Z][A-Za-z0-9_]*$")
QOS = {"transient_local": ["--qos-durability", "transient_local"], "volatile": ["--qos-durability", "volatile"],
       "reliable": ["--qos-reliability", "reliable"], "best_effort": ["--qos-reliability", "best_effort"],
       "sensor_data": ["--qos-profile", "sensor_data"]}
USAGE = ("用法: scripts/ROS2_topic_pub_cmd.py [容器名稱] <topic> <訊息型別> '<YAML 內容>' [--times N] [--qos 設定]\n"
         "  例：ROS2_topic_pub rmf_sim /tb2/handshake_states fih_rmf_msgs/msg/HandshakeState '{is_authored: \"yes\"}'\n"
         f"  預設發一次；--times N 每秒一次共 N 次（上限 {MAX_TIMES}）；--qos {'、'.join(QOS)}（可用逗號合併）。會先請使用者確認。")
SUBS_TAG, AUTO_TAG = "@@CAH_SUBS@@", "@@CAH_AUTOQOS@@"
TYPE_TAG = "@@CAH_PUB_TYPE@@"       # ros2 topic info 的 Type（訂閱端的型別；跟要發布的不同就配對不上）


def parse_cli(argv, resolve=True, names=None):
    """→ {"container", "container_arg", "topic", "type", "data", "times", "qos"（清單）, "error"}。resolve=False 時不查 docker。"""
    res = {"container": None, "container_arg": "", "topic": None, "type": None, "data": None, "times": 1, "qos": [], "error": None}
    args, pos, i = [a for a in argv if a.strip()], [], 0
    while i < len(args):
        a = args[i]
        key, val = (a.split("=", 1) if a.startswith("--") and "=" in a else (a, None))
        if key in ("--times", "--qos", "-t"):
            if val is None:
                if i + 1 >= len(args):
                    return dict(res, error=f"[ERROR] {key} 後面需要值。\n{USAGE}")
                val, i = args[i + 1], i + 2
            else:
                i += 1
            if key in ("--times", "-t"):
                if not str(val).isdigit() or int(val) < 1:
                    return dict(res, error=f"[ERROR] --times 後面要是正整數的次數，收到 {val!r}。\n{USAGE}")
                if int(val) > MAX_TIMES:
                    return dict(res, error=(f"[ERROR] --times 最多 {MAX_TIMES} 次（每秒一次，要在 {TIMEOUT_SECONDS} 秒的逾時內做完），"
                                            f"收到 {val}。這次沒有發布。下一步：改成 {MAX_TIMES} 以內，或分幾次發"))
                res["times"] = int(val)
            else:
                for q in [x.strip().lower() for x in val.split(",") if x.strip()]:
                    if q not in QOS:
                        return dict(res, error=f"[ERROR] 不認得的 --qos {q!r}（可用：{'、'.join(QOS)}）。\n{USAGE}")
                    res["qos"].append(q)
            continue
        if a in ("--once", "-1"):
            i += 1
            continue
        if a.startswith("--"):
            return dict(res, error=f"[ERROR] 不認識的選項 {a}（選項只有 --times、--qos）。\n{USAGE}")
        pos.append(a)
        i += 1
    idx = next((k for k, a in enumerate(pos[:3]) if TYPE_RE.match(a)), None)
    if idx is None:
        return dict(res, error=(f"[ERROR] 找不到訊息型別：要寫完整的型別，例如 std_msgs/msg/String、fih_rmf_msgs/msg/HandshakeState。"
                                f"下一步：ROS2_topic_list --types 看 topic 實際的型別。\n{USAGE}"))
    if idx not in (1, 2):
        return dict(res, error=f"[ERROR] 參數的順序是 [容器名稱] <topic> <訊息型別> '<內容>'，收到：{' '.join(pos)}。\n{USAGE}")
    container_arg = pos[0] if idx == 2 else ""
    topic, mtype, data = pos[idx - 1], pos[idx], " ".join(pos[idx + 1:])
    if not data.strip():
        return dict(res, error=f"[ERROR] 需要訊息內容（YAML，用單引號包住，例如 '{{data: hi}}'；要發預設值就寫 '{{}}'）。這次沒有發布。\n{USAGE}")
    if topic.startswith("-") or " " in topic:
        return dict(res, error=f"[ERROR] topic 名稱不對：{topic!r}。\n{USAGE}")
    res.update(container_arg=container_arg, topic=topic if topic.startswith("/") else "/" + topic, type=mtype, data=data)
    if not resolve:
        return res
    container, _rest, err = split_container_arg([container_arg] if container_arg else [], USAGE, must=bool(container_arg), names=names)
    if err:
        return dict(res, error=err)
    return dict(res, container=container)


def build_command(p):
    q = shlex.quote
    mode = "--once" if p["times"] == 1 else f"-t {p['times']} -r 1"
    user_qos = " ".join(" ".join(QOS[x]) for x in p["qos"])
    wait = PUB_WAIT + (p["times"] if p["times"] > 1 else 0)
    return (f"_info=$(ros2 topic info -v {q(p['topic'])} 2>&1); "
            f"printf '{SUBS_TAG}%s\\n' \"$(printf '%s\\n' \"$_info\" | sed -n 's/^Subscription count: //p')\"; "
            f"printf '{TYPE_TAG}%s\\n' \"$(printf '%s\\n' \"$_info\" | sed -n 's/^Type: //p' | head -3 | tr '\\n' ' ')\"; "
            f"_q={q(user_qos)}; "
            f"if [ -z \"$_q\" ] && printf '%s\\n' \"$_info\" | sed -n '/^Subscription count/,$p' | grep -q 'Durability: TRANSIENT_LOCAL'; "
            f"then _q='--qos-durability transient_local'; echo {AUTO_TAG}; fi; "
            f"timeout -s INT {wait} ros2 topic pub {mode} -w 1 $_q {q(p['topic'])} {q(p['type'])} {q(p['data'])}")


def main(argv):
    p = parse_cli(argv)
    if p["error"]:
        return p["error"]
    container, topic, mtype = p["container"], p["topic"], p["type"]
    res = ros2_run(container, build_command(p), TIMEOUT_SECONDS)
    out = res.get("out") or ""
    m = re.search(rf"^{SUBS_TAG}(\d*)\s*$", out, re.M)
    subs = int(m.group(1)) if m and m.group(1) else 0
    tm = re.search(rf"^{TYPE_TAG}(.*)$", out, re.M)
    types = tm.group(1).split() if tm else []
    auto = AUTO_TAG in out
    qos_text = ("、".join(p["qos"]) if p["qos"] else ("transient_local（訂閱端要求，自動選的）" if auto else "預設"))
    dom = domain_text(res.get("env"), short=True)
    where = f"容器 '{container}'" + (f"，{dom}" if dom else "")
    sent = len(re.findall(r"^publishing #", out, re.M))
    wait = PUB_WAIT + (p["times"] if p["times"] > 1 else 0)
    if res.get("rc") == 124 and res["kind"] == "own_timeout":
        if sent:
            return with_target_marker(f"[PASS] 已對 {topic}（{mtype}）發布 {sent} 次（原本要 {p['times']} 次，{wait} 秒到了停止；{where}）："
                                      f"{clip(p['data'], 200)}", container)
        if subs == 0:
            return (f"[ERROR] {topic} 目前沒有訂閱者（ros2 topic info：Subscription count 0；{where}），等了 {wait} 秒沒有人接收，"
                    f"這次沒有發布。下一步：確認接收端的 node 在跑、topic 名稱正確（ROS2_topic_list --filter、ROS2_node_info）；"
                    f"ROS_DOMAIN_ID 不對時看 ROS2_domain_id")
        if types and mtype not in types:
            return (f"[ERROR] {topic} 有 {subs} 個訂閱者，但它們的型別是 {'、'.join(types)}，跟你給的 {mtype} 不同——型別不同不會配對，"
                    f"等了 {wait} 秒沒有發布（{where}）。下一步：改用 {types[0]} 的欄位重新發布（欄位用 docker_runcmd \"source /opt/ros/$ROS_DISTRO/"
                    f"setup.bash && ros2 interface show {types[0]}\" 看）；topic 名稱寫錯的話用 ROS2_topic_list --filter 確認")
        return (f"[ERROR] {topic} 有 {subs} 個訂閱者，但 {wait} 秒內沒有配對成功（QoS：{qos_text}；{where}），這次沒有發布。"
                f"最可能是 QoS 不相容（訂閱端要求 reliable 或 transient_local）。下一步：加 --qos transient_local 或 --qos reliable 重試；"
                f"還是不行就用 docker_runcmd \"source /opt/ros/$ROS_DISTRO/setup.bash && ros2 topic info -v {topic}\" 看訂閱端的 QoS")
    if res["kind"] != "ok":
        res["out"] = "\n".join(ln for ln in out.splitlines() if not ln.startswith((SUBS_TAG, AUTO_TAG, TYPE_TAG)))
        return describe_failure(res, f"對 {topic} 發布 {mtype}", TIMEOUT_SECONDS, container=container,
                                timeout_hint="ros2 沒有回應：確認容器內的 ROS 2 與 DDS 網路設定。")
    return with_target_marker(f"[PASS] 已對 {topic}（{mtype}）發布 {sent or p['times']} 次（訂閱者 {subs} 個；QoS：{qos_text}；{where}）："
                              f"{clip(p['data'], 200)}", container)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_topic_pub 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
