"""ROS2_topic_pub：對 topic 發布訊息（ros2 topic pub）。會影響正在跑的系統（例如手動回交握、發指令），執行前由 harness
請使用者確認。預設只發一次（--once）；--times N 每秒一次、共 N 次。訊息內容用 YAML（例：'{is_authored: "yes"}'）。
容器名稱可省略＝目前的目標容器；不確定訊息型別時先用 ROS2_topic_list 或 ROS2_topic_echo 看。"""
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import resolve_container, ros2_exec, with_target_marker  # noqa: E402

TIMEOUT_SECONDS = 60
USAGE = ("用法: scripts/ROS2_topic_pub_cmd.py [容器名稱] <topic> <訊息型別> '<YAML 內容>' [--times N]\n"
         "  例：ROS2_topic_pub rmf_sim /tb2/handshake_states fih_rmf_msgs/msg/HandshakeState '{is_authored: \"yes\"}'\n"
         "  預設發一次；--times N 每秒一次共 N 次。會先請使用者確認。")


def parse_cli(argv):
    args = [a for a in argv if a.strip()]
    times = 1
    if "--times" in args:
        i = args.index("--times")
        if i + 1 >= len(args) or not args[i + 1].isdigit():
            return None, None, f"[ERROR] --times 後面要是次數。\n{USAGE}"
        times = max(1, min(30, int(args[i + 1])))
        del args[i:i + 2]
    if args and not args[0].startswith("/"):
        container, args = args[0], args[1:]
    else:
        container = ""
    if len(args) < 3:
        return None, None, f"[ERROR] 需要 topic、訊息型別與內容。\n{USAGE}"
    topic, mtype, data = args[0], args[1], " ".join(args[2:])
    if "/" not in mtype:
        return None, None, f"[ERROR] 訊息型別要寫完整，例如 std_msgs/msg/String、fih_rmf_msgs/msg/HandshakeState。\n{USAGE}"
    container, err = resolve_container(container, USAGE)
    return container, (topic, mtype, data, times), err


def main(argv):
    container, spec, err = parse_cli(argv)
    if err:
        return err
    topic, mtype, data, times = spec
    mode = "--once" if times == 1 else f"-t {times} -r 1"
    cmd = f"ros2 topic pub {mode} -w 1 {shlex.quote(topic)} {shlex.quote(mtype)} {shlex.quote(data)}"
    ok, out, err = ros2_exec(container, cmd, TIMEOUT_SECONDS,
                             timeout_hint="沒有人訂閱這個 topic 時會一直等（-w 1）；先用 ROS2_topic_list／ROS2_node_info 確認有訂閱者。")
    if not ok:
        return err
    text = (out or "").strip()
    sent = len(re.findall(r"^publishing #", text, re.M))
    if "Unknown message type" in text or "could not be loaded" in text or "The passed message type is invalid" in text:
        return f"[ERROR] 不認得訊息型別 {mtype}（容器裡沒有這個型別，或要先 source 工作區）：\n{text[-600:]}"
    if "Failed to populate" in text or "ERROR" in text and not sent:
        return f"[ERROR] 訊息內容跟型別對不上：\n{text[-600:]}"
    return with_target_marker(f"[PASS] 已對 {topic}（{mtype}）發布 {sent or times} 次：{data}", container)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_topic_pub 未預期的例外：{e}")
