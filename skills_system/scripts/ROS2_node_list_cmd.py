"""ROS2_node_list：容器內執行中的 node（ros2 node list），標頭算好總數與實際用的 ROS_DOMAIN_ID，依命名空間分節。

一個 node 都沒有時明說可能是 domain 不對並建議 ROS2_domain_id；剛啟動的 ros2 daemon 有時第一次查不到，會等 2 秒再查一次。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (describe_failure, domain_text, grouped_lines, parse_filter_args, ros2_run,  # noqa: E402
                            split_container_arg, with_target_marker)

TIMEOUT_SECONDS = 30
USAGE = ("用法: scripts/ROS2_node_list_cmd.py [container_name] [--filter 關鍵字]...\n"
         "  container_name 省略＝目前的目標容器；--filter 只列名稱含關鍵字的 node 並在標頭計數（不分大小寫，可重複）。")
COMMAND = ('_o=$(ros2 node list); _rc=$?; if [ $_rc -eq 0 ] && [ -z "$_o" ]; then sleep 2; _o=$(ros2 node list); _rc=$?; fi; '
           'printf "%s\\n" "$_o"; exit $_rc')


def report(out, container, env, keywords=()):
    items = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    dom = domain_text(env) or "ROS_DOMAIN_ID 不明"
    if not items:
        return (f"[PASS] 容器 '{container}' 在 {dom} 沒有看到任何 node：可能 ROS_DOMAIN_ID 不對（節點在別的 domain）、"
                f"節點沒在跑，或 DDS 探索不到。下一步：ROS2_domain_id 看 shell 與正在跑的節點各在哪個 domain；"
                f"docker_ctl logs 看節點有沒有啟動失敗。")
    head = f"[PASS] 容器 '{container}' 的 node：共 {len(items)} 個"
    shown = items
    if keywords:
        kws = [k.lower() for k in keywords]
        shown = [x for x in items if any(k in x.lower() for k in kws)]
        head += f"，其中含「{'／'.join(keywords)}」的 {len(shown)} 個"
        if not shown:
            return f"{head}（沒有符合的；不加 --filter 可列出全部 {len(items)} 個）；{dom}"
    return "\n".join([f"{head}；{dom}"] + grouped_lines(shown))


def run_node_list(argv):
    container, keywords, err = parse_filter_args(argv, USAGE)
    if err:
        return err
    arg = container
    container, _rest, err = split_container_arg([arg] if arg else [], must=bool(arg))
    if err:
        return (f"{err}（如果「{arg}」是要找的 node 名稱關鍵字，請寫成 --filter {arg}）" if arg else err) + f"\n{USAGE}"
    res = ros2_run(container, COMMAND, TIMEOUT_SECONDS)
    if res["kind"] != "ok":
        return describe_failure(res, f"容器 '{container}' 內的 `ros2 node list`", TIMEOUT_SECONDS, container=container,
                                timeout_hint="ros2 discovery 沒有回應：確認容器內的 ROS 2 daemon 與 DDS 網路設定（ROS2_domain_id 看 domain）。")
    return with_target_marker(report(res["out"], container, res.get("env"), keywords), container)


if __name__ == "__main__":
    try:
        print(run_node_list(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_node_list 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
