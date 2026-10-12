"""ROS2_param：查詢或修改 ROS 2 node 的參數（ros2 param list／get／set）。list 與 get 是唯讀的；set 會改變執行中 node 的
行為，執行前由 harness 請使用者確認。容器名稱可省略＝目前的目標容器；node 名稱要含命名空間（/resource_allocator）。

設定檔（yaml）寫的是啟動時的值；執行中的實際值以這裡查到的為準（例如 launch 參數或之後被 set 改過）。"""
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import pass_or_empty, resolve_container, ros2_exec, with_target_marker  # noqa: E402

TIMEOUT_SECONDS = 40
USAGE = ("用法: scripts/ROS2_param_cmd.py [容器名稱] list <node>｜get <node> <參數>｜set <node> <參數> <值>\n"
         "  例：ROS2_param list /resource_allocator　ROS2_param rmf_sim get /resource_allocator authorize_timeout_sec\n"
         "  容器名稱省略＝目前的目標容器；set 會先請使用者確認。")


def parse_cli(argv):
    args = [a for a in argv if a.strip()]
    if args and args[0] not in ("list", "get", "set"):
        container, args = args[0], args[1:]
    else:
        container = ""
    if not args or args[0] not in ("list", "get", "set"):
        return None, None, f"[ERROR] 要指定動作 list／get／set。\n{USAGE}"
    need = {"list": 2, "get": 3, "set": 4}[args[0]]
    if len(args) < need:
        return None, None, f"[ERROR] {args[0]} 的參數不足。\n{USAGE}"
    if not args[1].startswith("/"):
        args[1] = "/" + args[1]
    container, err = resolve_container(container, USAGE)
    return container, args, err


def main(argv):
    container, args, err = parse_cli(argv)
    if err:
        return err
    cmd = "ros2 param " + " ".join(shlex.quote(a) for a in args)
    ok, out, err = ros2_exec(container, cmd, TIMEOUT_SECONDS,
                             timeout_hint="node 可能不存在或 DDS 探索沒有回應；先用 ROS2_node_list 確認 node 名稱。")
    if not ok:
        return err
    text = (out or "").strip()
    if "Node not found" in text or "not found" in text.lower() and args[0] != "set":
        return f"[ERROR] 找不到 node {args[1]}（容器 {container}）。先用 ROS2_node_list 確認名稱與 ROS_DOMAIN_ID。\n{text}"
    if args[0] == "get":
        if "Parameter not set" in text:
            return f"[ERROR] {args[1]} 沒有參數 {args[2]}。用 `ROS2_param list {args[1]}` 看有哪些參數。"
        return with_target_marker(f"[PASS] {args[1]} 的 {args[2]}（執行中的值）：{text}", container)
    if args[0] == "set":
        if "Set parameter successful" in text:
            return with_target_marker(f"[PASS] 已設定 {args[1]} 的 {args[2]} = {args[3]}（只影響執行中的 node；重啟後回到設定檔的值）", container)
        return f"[ERROR] 設定失敗：{text}"
    names = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().endswith(":")]
    return with_target_marker(f"[PASS] {args[1]} 有 {len(names)} 個參數：\n" + pass_or_empty(text, "（沒有參數）"), container)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_param 未預期的例外：{e}")
