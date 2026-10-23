"""ROS2_topic_list：容器內的 topic 清單（ros2 topic list，--types 加型別），標頭算好總數、實際用的 ROS_DOMAIN_ID，依命名空間分節。

只看到 /parameter_events 與 /rosout（每個 ROS 2 系統都有）時明說「沒有任何節點自己的 topic」並建議查 domain——以前這是一個
看起來正常的 [PASS]，模型會以為系統沒有 topic。剛啟動的 ros2 daemon 有時第一次查不到，這種情況會等 2 秒再查一次。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (describe_failure, domain_text, grouped_lines, parse_filter_args, ros2_run,  # noqa: E402
                            split_container_arg, with_target_marker)

# ROS2 探索（discovery）通常幾秒內完成；daemon 冷啟動時會慢一點
TIMEOUT_SECONDS = 30
USAGE = ("用法: scripts/ROS2_topic_list_cmd.py [container_name] [--types] [--filter 關鍵字]...\n"
         "  container_name 省略＝目前的目標容器；--types 每個 topic 附訊息型別（ROS2_topic_pub 要用的完整型別）；\n"
         "  --filter 只列名稱（或型別）含關鍵字的 topic 並在標頭計數（不分大小寫，可重複）。")
SYSTEM_TOPICS = ("/parameter_events", "/rosout")
_SYS_RE = "^(/parameter_events|/rosout)( |$)|^$"


def build_command(types):
    cmd = "ros2 topic list" + (" -t" if types else "")
    # 只有系統 topic（或空的）時等 2 秒再查一次：剛啟動的 daemon 可能還沒探索到
    return (f'_o=$({cmd}); _rc=$?; if [ $_rc -eq 0 ] && ! printf "%s\\n" "$_o" | grep -qvE "{_SYS_RE}"; then '
            f'sleep 2; _o=$({cmd}); _rc=$?; fi; printf "%s\\n" "$_o"; exit $_rc')


def report(out, container, env, keywords=(), types=False):
    items = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    dom = domain_text(env) or "ROS_DOMAIN_ID 不明"
    names = [it.split()[0] for it in items]
    if not items or all(n in SYSTEM_TOPICS for n in names):
        seen = "、".join(names) if names else "任何 topic"
        return "\n".join([f"[PASS] 容器 '{container}' 在 {dom} 只看到 {seen}（每個 ROS 2 系統都有的），沒有任何節點自己的 topic："
                          "可能 ROS_DOMAIN_ID 不對（節點在別的 domain）、節點沒在跑，或 DDS 探索不到。"
                          "下一步：ROS2_domain_id 看 shell 與正在跑的節點各在哪個 domain；ROS2_node_list 看有沒有節點。"] + items)
    head = f"[PASS] 容器 '{container}' 的 topic：共 {len(items)} 個"
    shown = items
    if keywords:
        kws = [k.lower() for k in keywords]
        shown = [x for x in items if any(k in x.lower() for k in kws)]
        head += f"，其中含「{'／'.join(keywords)}」的 {len(shown)} 個"
        if not shown:
            return f"{head}（沒有符合的；不加 --filter 可列出全部 {len(items)} 個）；{dom}"
    head += f"；{dom}" + ("；每行「topic [訊息型別]」" if types else "")
    return "\n".join([head] + grouped_lines(shown))


def run_ros2_topic_list(argv):
    """在指定的 Docker 容器內執行 `ros2 topic list`（bash -ic + ROS 2 環境），標頭給總數、符合關鍵字的數量與 domain。"""
    container, keywords, flags, err = parse_filter_args(["--types" if a == "-t" else a for a in argv], USAGE, flags=("--types",))
    if err:
        return err
    arg = container
    container, _rest, err = split_container_arg([arg] if arg else [], must=bool(arg))
    if err:
        return (f"{err}（如果「{arg}」是要找的 topic 名稱關鍵字，請寫成 --filter {arg}）" if arg else err) + f"\n{USAGE}"
    res = ros2_run(container, build_command("--types" in flags), TIMEOUT_SECONDS)
    if res["kind"] != "ok":
        return describe_failure(res, f"容器 '{container}' 內的 `ros2 topic list`", TIMEOUT_SECONDS, container=container,
                                timeout_hint="ros2 discovery 沒有回應：確認容器內的 ROS 2 daemon 與 DDS 網路設定（ROS2_domain_id 看 domain）。")
    return with_target_marker(report(res["out"], container, res.get("env"), keywords, "--types" in flags), container)


if __name__ == "__main__":
    try:
        print(run_ros2_topic_list(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_topic_list 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
