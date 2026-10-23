"""ROS2_param：查詢或修改 ROS 2 node 的參數（ros2 param list／get／set）。list 與 get 是唯讀的；set 會改變執行中 node 的
行為，執行前由 harness 請使用者確認（parse_cli 回 readonly）。容器名稱可省略＝目前的目標容器；node 名稱要含命名空間
（/resource_allocator，少了開頭的 / 會自動補）。

ros2 的錯誤分兩種，以前都沒接好：找不到 node、沒有這個參數是 stderr＋exit code 1（以前被當成 docker 的錯誤，自訂的提示永遠到不了）；
設定失敗（型別不對、唯讀、沒有宣告）是 stderr「Setting parameter failed: 原因」但 exit code 0（以前回「設定失敗：」沒有原因）。
現在 set 之後在同一次執行裡再 get 一次，回報實際的值；找不到 node／參數時順便列出現有的 node／參數與相近的名稱。

設定檔（yaml）寫的是啟動時的值；執行中的實際值以這裡查到的為準（例如 launch 參數或之後被 set 改過）。"""
import difflib
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (clip, describe_failure, domain_text, ros2_run, split_container_arg,  # noqa: E402
                            with_target_marker)

TIMEOUT_SECONDS = 40
ACTIONS = ("list", "get", "set")
USAGE = ("用法: scripts/ROS2_param_cmd.py [容器名稱] list <node>｜get <node> <參數>｜set <node> <參數> <值>\n"
         "  例：ROS2_param list /resource_allocator　ROS2_param rmf_sim get /resource_allocator authorize_timeout_sec\n"
         "  容器名稱省略＝目前的目標容器；set 會先請使用者確認；值照原本的型別寫（小數 10.0、整數 10、true／false、字串）。")
NODES_TAG, PARAMS_TAG = "@@CAH_NODES@@", "@@CAH_PARAMS@@"
GROUP_MIN = 20     # 參數超過這麼多、而且有好幾個前綴時，依前綴（第一個 . 之前）分節


def parse_cli(argv, resolve=True, names=None):
    """→ {"container", "container_arg", "action", "node", "param", "value", "readonly", "error"}。
    resolve=False 時不查 docker（guard 只要 action／readonly）；動作可以在第一或第二個參數（前面是容器名稱）。"""
    res = {"container": None, "container_arg": "", "action": None, "node": None, "param": None, "value": None,
           "readonly": False, "error": None}
    args = [a.strip() for a in argv if a.strip()]
    idx = next((i for i, a in enumerate(args[:2]) if a.lower() in ACTIONS), None)
    if idx is None:
        return dict(res, error=f"[ERROR] 要指定動作 list／get／set（容器名稱放在動作前面，可省略）。\n{USAGE}")
    act = args[idx].lower()
    rest = args[idx + 1:]
    res.update(action=act, readonly=act in ("list", "get"), container_arg=args[0] if idx == 1 else "")
    need = {"list": 1, "get": 2, "set": 3}[act]
    if len(rest) < need:
        what = {"list": "node 名稱", "get": "node 名稱與參數名稱", "set": "node 名稱、參數名稱與值"}[act]
        return dict(res, error=f"[ERROR] {act} 需要 {what}。下一步：不知道名稱先用 ROS2_node_list、ROS2_param list <node>。\n{USAGE}")
    if act != "set" and len(rest) > need:
        return dict(res, error=f"[ERROR] {act} 多了參數 {' '.join(rest[need:])}（一次查一個參數）。\n{USAGE}")
    node = rest[0] if rest[0].startswith("/") else "/" + rest[0]
    res.update(node=node, param=rest[1] if len(rest) > 1 else None, value=" ".join(rest[2:]) if act == "set" else None)
    if not resolve:
        return res
    container, _rest, err = split_container_arg([res["container_arg"]] if res["container_arg"] else [], USAGE,
                                                must=bool(res["container_arg"]), names=names)
    if err:
        return dict(res, error=err)
    return dict(res, container=container)


def _names_after(out, tag, end_tag=None):
    if tag not in out:
        return []
    part = out.split(tag, 1)[1]
    if end_tag and end_tag in part:
        part = part.split(end_tag, 1)[0]
    return [ln.strip() for ln in part.splitlines() if ln.strip()]


def _suggest(name, names, label):
    close = difflib.get_close_matches(name, names, n=3, cutoff=0.6)
    shown = "、".join(names[:20]) + (f"…（共 {len(names)} 個）" if len(names) > 20 else f"（共 {len(names)} 個）")
    return (f"相近的：{'、'.join(close)}。" if close else "") + (f"目前的{label}：{shown}。" if names else "")


def build_command(p):
    q = shlex.quote
    node = q(p["node"])
    if p["action"] == "list":
        return f"ros2 param list {node}; _rc=$?; if [ $_rc -ne 0 ]; then echo {NODES_TAG}; ros2 node list 2>/dev/null; fi; exit $_rc"
    get = f"ros2 param get {node} {q(p['param'])}"
    fallback = (f"echo {NODES_TAG}; ros2 node list 2>/dev/null; echo {PARAMS_TAG}; ros2 param list {node} 2>/dev/null")
    if p["action"] == "get":
        return f"{get}; _rc=$?; if [ $_rc -ne 0 ]; then {fallback}; fi; exit $_rc"
    # set 之後馬上再讀一次：回報執行中真正的值（失敗時也看得到目前的值）
    return (f"ros2 param set {node} {q(p['param'])} {q(p['value'])}; _rc=$?; echo @@CAH_GET@@; {get} 2>&1; "
            f"if [ $_rc -ne 0 ]; then {fallback}; fi; exit $_rc")


_VALUE_RE = re.compile(r"^(\w+) values? (?:is|are):\s?(.*)$", re.S)


def parse_value(text):
    """「Double value is: 10.0」→ ("Double", "10.0")；看不懂回 (None, 原文)。"""
    t = (text or "").strip()
    m = _VALUE_RE.match(t)
    return (m.group(1), m.group(2).strip()) if m else (None, t)


def set_failure_hint(reason, value):
    r = reason.lower()
    if "wrong parameter type" in r:
        m = re.search(r"expected '?Type\.(\w+)", reason)
        want = m.group(1) if m else ""
        sample = {"DOUBLE": f"{value}.0" if re.fullmatch(r"-?\d+", value or "") else "10.0", "INTEGER": "10", "BOOL": "true／false",
                  "STRING": "'文字'"}.get(want, "")
        return f"型別不對：這個參數是 {want or '另一種型別'}，值要照它的型別寫" + (f"（例如 {sample}）" if sample else "")
    if "read-only" in r:
        return "這是唯讀參數（read_only），執行中不能改：要改就改設定檔（yaml／launch 參數）後重啟 node，先問使用者"
    if "undeclared" in r:
        return "這個 node 沒有宣告這個參數（名稱不對）：先用 ROS2_param list <node> 看正確的名稱"
    return "node 拒絕了這個值（範圍或條件不符）：照原因修正值；不確定就問使用者"


def main(argv):
    p = parse_cli(argv)
    if p["error"]:
        return p["error"]
    container, act, node = p["container"], p["action"], p["node"]
    res = ros2_run(container, build_command(p), TIMEOUT_SECONDS)
    out, err = res.get("out") or "", res.get("err") or ""
    dom = domain_text(res.get("env"), short=True)
    where = f"容器 '{container}'" + (f"，{dom}" if dom else "")
    low = err.lower()
    if res["kind"] == "error" and "node not found" in low:
        nodes = [n for n in _names_after(out, NODES_TAG, PARAMS_TAG) if n.startswith("/")]
        why = _suggest(node, nodes, " node") if nodes else "這個 domain 目前沒有任何 node（ROS2_domain_id 看節點在哪個 domain）。"
        return f"[ERROR] 找不到 node {node}（{where}）。{why}下一步：用正確的完整名稱（含命名空間）重試，不要猜名稱"
    if res["kind"] == "error" and act == "get" and "parameter not set" in low:
        params = _names_after(out, PARAMS_TAG)
        return (f"[ERROR] node {node} 沒有參數 {p['param']}（{where}）。{_suggest(p['param'], params, '參數')}"
                f"下一步：用正確的參數名稱重試（ROS2_param list {node} 看全部）")
    if res["kind"] != "ok":
        res["out"] = out.split(NODES_TAG, 1)[0]
        return describe_failure(res, f"容器 '{container}' 內的 `ros2 param {act} {node}`", TIMEOUT_SECONDS, container=container,
                                timeout_hint=f"node 沒有回應（可能卡住，或 DDS 探索不到）。下一步：ROS2_node_list 確認 {node} 在跑；ROS2_domain_id 看 domain。")
    if act == "get":
        typ, val = parse_value(out)
        return with_target_marker(f"[PASS] {node} 的 {p['param']}（執行中的值；{where}）：{val}" + (f"（{typ}）" if typ else ""), container)
    if act == "set":
        before_get, _, after = out.partition("@@CAH_GET@@")
        typ, now = parse_value(after.split(NODES_TAG, 1)[0])
        m = re.search(r"Setting parameter failed:?\s*(.*)", err + "\n" + before_get)
        if "Set parameter successful" in before_get and not m:
            return with_target_marker(f"[PASS] 已設定 {node} 的 {p['param']} = {p['value']}（{where}）；再讀一次的值：{now}"
                                      + (f"（{typ}）" if typ else "") + "。只影響執行中的 node，重啟後回到設定檔的值。", container)
        reason = ((m.group(1).strip() if m else clip(err or before_get, 300)) or "ros2 沒有說原因").rstrip("。.")
        current = f"{now}（{typ}）" if typ else ("（沒有這個參數）" if "not set" in now.lower() else now)
        return (f"[ERROR] 設定 {node} 的 {p['param']} = {p['value']} 失敗（{where}）：{reason}。目前的值：{current}。"
                f"下一步：{set_failure_hint(reason, p['value'])}")
    names = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.strip().endswith(":")]
    head = f"[PASS] {node} 有 {len(names)} 個參數（執行中的 node；{where}）"
    if not names:
        return with_target_marker(head + "：這個 node 沒有任何參數。", container)
    prefixes = sorted({n.split(".", 1)[0] if "." in n else "" for n in names})
    lines = [head + f"；要看值用 ROS2_param get {node} <參數>"]
    if len(names) > GROUP_MIN and len(prefixes) > 1:
        for pre in prefixes:
            group = [n for n in names if (n.split(".", 1)[0] if "." in n else "") == pre]
            lines.append(f"## {pre or '（沒有前綴）'}（{len(group)} 項）")
            lines += group
    else:
        lines += names
    return with_target_marker("\n".join(lines), container)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_param 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
