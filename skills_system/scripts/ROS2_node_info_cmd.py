"""ROS2_node_info：一個 node 的訂閱、發布、服務、Action（ros2 node info），標頭算好每一類的數量與實際用的 ROS_DOMAIN_ID。

- node 名稱少了開頭的 / 會自動補；名稱加引號（含特殊字元也不會壞掉）。
- 每個 node 都有的 6 個參數服務（describe_parameters…set_parameters_atomically）與 get_type_description 不列出，標頭註明個數。
- 找不到 node 時順便列出目前的 node 與相近的名稱（同一次 docker exec），不必再呼叫一次 ROS2_node_list。
- 參數：[容器名稱] <node>；兩個參數時第一個一定是容器（對不到附相近的名稱，不會把它當成 node）。"""
import difflib
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (clip, describe_failure, domain_text, ros2_run, split_container_arg,  # noqa: E402
                            with_target_marker)

TIMEOUT_SECONDS = 30
USAGE = ("用法: scripts/ROS2_node_info_cmd.py [container_name] <node_name>"
         "（container_name 省略＝目前的目標容器；node 名稱含命名空間，如 /nav_node，少了開頭的 / 會自動補）")
SECTIONS = {"Subscribers": "訂閱", "Publishers": "發布", "Service Servers": "服務", "Service Clients": "服務客戶端",
            "Action Servers": "Action 伺服器", "Action Clients": "Action 客戶端"}
STANDARD_SERVICES = ("describe_parameters", "get_parameter_types", "get_parameters", "list_parameters", "set_parameters",
                     "set_parameters_atomically", "get_type_description")
NODES_TAG = "@@CAH_NODES@@"


def parse_cli(argv):
    """回傳 (container, node, error)。一個參數＝node（容器用目標容器）；兩個＝容器＋node（容器要對得到）。"""
    args = [a.strip() for a in argv if a.strip()]
    if not args:
        return None, None, f"[ERROR] 參數不足，需要節點名稱。下一步：不知道名稱就先用 ROS2_node_list。\n{USAGE}"
    flags = [a for a in args if a.startswith("-")]
    if flags:
        return None, None, f"[ERROR] 不認識的選項 {flags[0]}（這個技能沒有選項）。\n{USAGE}"
    if len(args) > 2:
        return None, None, f"[ERROR] 參數太多：{' '.join(args)}。一次查一個 node。\n{USAGE}"
    if len(args) == 2 and args[0].startswith("/"):
        return None, None, f"[ERROR] 兩個參數時第一個要是容器名稱，收到 {args[0]!r}（一次查一個 node）。\n{USAGE}"
    container, rest, err = split_container_arg(args, USAGE, must=len(args) == 2)
    if err:
        return None, None, err
    node = rest[0]
    return container, node if node.startswith("/") else "/" + node, None


def parse_info(text):
    """ros2 node info 的輸出 → {英文節名: [項目…]}（項目是「名稱: 型別」）。"""
    sections, cur = {}, None
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.endswith(":") and s[:-1] in SECTIONS:
            cur = s[:-1]
            sections.setdefault(cur, [])
        elif cur and ln.startswith("    "):
            sections[cur].append(s)
    return sections


def is_standard_service(node, item):
    name = item.split(":", 1)[0].strip()
    return any(name == f"{node.rstrip('/')}/{svc}" for svc in STANDARD_SERVICES)


def report(node, container, out, env):
    sections = parse_info(out)
    hidden = 0
    if "Service Servers" in sections:
        keep = [it for it in sections["Service Servers"] if not is_standard_service(node, it)]
        hidden = len(sections["Service Servers"]) - len(keep)
        sections["Service Servers"] = keep
    dom = domain_text(env, short=True)
    counts = "、".join(f"{label} {len(sections.get(key, []))}" for key, label in SECTIONS.items())
    head = (f"[PASS] 節點 {node}（容器 '{container}'" + (f"，{dom}" if dom else "") + f"）：{counts}"
            + (f"（另有 {hidden} 個每個 node 都有的參數／型別服務沒有列出）" if hidden else ""))
    lines = [head]
    for key, label in SECTIONS.items():
        items = sections.get(key) or []
        if items:
            lines.append(f"## {label}（{key}，{len(items)} 項）")
            lines += items
    if not sections:
        lines.append(clip(out, 2000) or "（ros2 node info 沒有輸出）")
    return "\n".join(lines)


def not_found(node, container, nodes_text, env, err_text):
    nodes = [ln.strip() for ln in (nodes_text or "").splitlines() if ln.strip().startswith("/")]
    dom = domain_text(env, short=True)
    where = f"容器 '{container}'" + (f"，{dom}" if dom else "")
    if not nodes:
        return (f"[ERROR] 找不到 node {node}（{where}），而且這個 domain 目前沒有任何 node。"
                f"下一步：ROS2_domain_id 看節點在哪個 domain；docker_ctl logs 看節點有沒有啟動。\n--- stderr ---\n{clip(err_text, 300)}")
    close = difflib.get_close_matches(node, nodes, n=3, cutoff=0.6)
    shown = "、".join(nodes[:15]) + (f"…（共 {len(nodes)} 個，ROS2_node_list 看全部）" if len(nodes) > 15 else f"（共 {len(nodes)} 個）")
    return (f"[ERROR] 找不到 node {node}（{where}）。" + (f"相近的：{'、'.join(close)}。" if close else "")
            + f"目前的 node：{shown}。下一步：用正確的完整名稱（含命名空間）重試，不要猜名稱")


def run_node_info(container, node):
    container = (container or "").strip()
    node = (node or "").strip()
    if not container or not node:
        return f"[ERROR] 參數不足，需要容器名稱與節點名稱。\n{USAGE}"
    q = shlex.quote(node)
    cmd = (f"ros2 node info {q}; _rc=$?; if [ $_rc -ne 0 ]; then echo {NODES_TAG}; ros2 node list 2>/dev/null; fi; exit $_rc")
    res = ros2_run(container, cmd, TIMEOUT_SECONDS)
    out = res.get("out") or ""
    if res["kind"] == "error" and NODES_TAG in out and "unable to find node" in (res.get("err") or "").lower():
        return not_found(node, container, out.split(NODES_TAG, 1)[1], res.get("env"), res.get("err"))
    if res["kind"] != "ok":
        res["out"] = out.split(NODES_TAG, 1)[0]
        return describe_failure(res, f"容器 '{container}' 內的 `ros2 node info {node}`", TIMEOUT_SECONDS, container=container,
                                timeout_hint="ros2 discovery 沒有回應：確認容器內的 ROS 2 daemon 與 DDS 網路設定（ROS2_domain_id 看 domain）。")
    return with_target_marker(report(node, container, out, res.get("env")), container)


if __name__ == "__main__":
    try:
        container, node, err = parse_cli(sys.argv[1:])
        if err:
            print(err)
            sys.exit(0)
        print(run_node_info(container, node))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_node_info 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
