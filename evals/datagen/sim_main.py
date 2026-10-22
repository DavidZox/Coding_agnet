"""容器端：產生一組隨機情境的錄製（rosbag2 的 MCAP，跟 ros2 bag record 同一個格式）＋每份的評分標準，最後彙整成 cases.json。
需要 ROS 2（rosbag2_py、rclpy）與自訂的訊息型別（diagnostics_package、base_motor_controller、fih_rmf_msgs）。由 generate.py 送進容器執行。

    python3 sim_main.py --seed 1 --n 40 --out /workspace/experiment_logs/gen/s1 [--only 3,7] [--require bridge]"""
import argparse
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sim_scenarios import compose  # noqa: E402

_SEQ = re.compile(r"^sequence<(.+?)(?:,\s*\d+)?>$|^(.+?)\[\d*\]$")
_CLS = {}


def _cls(type_name):
    if type_name not in _CLS:
        from rosidl_runtime_py.utilities import get_message
        parts = type_name.split("/")
        _CLS[type_name] = get_message(type_name if len(parts) == 3 else f"{parts[0]}/msg/{parts[1]}")
    return _CLS[type_name]


def fill(msg, d):
    """dict → ROS 訊息：巢狀訊息、訊息的序列；byte 欄位的整數轉成 bytes（DiagnosticStatus.level），整數給浮點欄位時轉 float。"""
    types = msg.get_fields_and_field_types()
    for k, v in d.items():
        t = types[k]
        if isinstance(v, dict):
            fill(getattr(msg, k), v)
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):
            m = _SEQ.match(t)
            elem = (m.group(1) or m.group(2)) if m else t
            setattr(msg, k, [fill(_cls(elem)(), x) for x in v])
            continue
        if t in ("byte", "octet") and isinstance(v, int):
            v = bytes([v])
        elif t in ("float", "double") and isinstance(v, int) and not isinstance(v, bool):
            v = float(v)
        elif isinstance(v, list) and v and t.startswith("sequence<") and ("float" in t or "double" in t):
            v = [float(x) for x in v]
        setattr(msg, k, v)
    return msg


def write_bag(sim, exp_dir):
    import rosbag2_py
    from rclpy.serialization import serialize_message
    bag_dir = os.path.join(exp_dir, "bag")
    if os.path.exists(exp_dir):
        shutil.rmtree(exp_dir)
    os.makedirs(exp_dir)
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=bag_dir, storage_id="mcap"), rosbag2_py.ConverterOptions("cdr", "cdr"))
    for i, (topic, s) in enumerate(sorted(sim.streams.items())):
        writer.create_topic(rosbag2_py.TopicMetadata(i, topic, s.type, "cdr"))
    n = 0
    for t, topic, i in sim.messages():
        s = sim.streams[topic]
        fields = s.fields_at(i)
        if topic == "/rosout":
            ns = int(round((sim.t0 + t) * 1e9))
            fields = dict(fields, stamp={"sec": ns // 1_000_000_000, "nanosec": ns % 1_000_000_000})
            t = t + 0.0002   # 錄製工具收到的時間比 Log 的 stamp 晚一點
        msg = fill(_cls(s.type)(), fields)
        writer.write(topic, serialize_message(msg), int(round((sim.t0 + t) * 1e9)))
        n += 1
    del writer
    with open(os.path.join(exp_dir, "recording_info.json"), "w", encoding="utf-8") as f:
        json.dump({"created": time.strftime("%Y-%m-%d %H:%M:%S"), "generator": "evals/datagen（隨機情境產生器）",
                   "duration_requested_sec": sim.duration, "topics": ["<all>"], "rosout_log": False}, f, ensure_ascii=False, indent=1)
    return n


def make_case(sim, info):
    """一份錄製的評分標準（cases.json 的一項）。refresh_truth.py 也用它（評分標準的定義改了、數據不變時只重算這一份）。"""
    case = {"id": sim.label, "data": sim.label, "seconds": int(sim.duration), "title": "；".join(info["notes"]),
            "question": info["question"], "systems": info["systems"], "timeline": info["timeline"],
            "topics": [{"topic": k, "has": sorted(v["has"]), "not": sorted(v["not"])} for k, v in sorted(sim.tag_expect.items())
                       if k in sim.streams and sim.streams[k].times]}
    if info["steady"]:
        case["no_event"] = {"forbid": ["中斷", "停止發布", "開始發布"]}
        if sim.background:   # 本來就會有事件的 Topic（不是注入的）：判定「沒有事件」時不算
            case["no_event"]["background"] = sorted(sim.background)
    return case


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--out", required=True)
    p.add_argument("--only", default="")
    p.add_argument("--require", default="", help="一定要有的子系統（逗號分隔，例如 bridge）")
    args = p.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()}
    require = [x.strip() for x in args.require.split(",") if x.strip()]
    os.makedirs(args.out, exist_ok=True)
    cases = []
    for idx in range(args.n):
        if only and idx not in only:
            continue
        t0 = time.time()
        sim, info = compose(args.seed, idx, require=require)
        exp = os.path.join(args.out, sim.label)
        n = write_bag(sim, exp)
        case = make_case(sim, info)
        with open(os.path.join(exp, "truth.json"), "w", encoding="utf-8") as f:
            json.dump(dict(case, base_offset=round(sim.base, 6), t0=sim.t0, messages=n,
                           topics_all={k: len(s.times) for k, s in sorted(sim.streams.items())}), f, ensure_ascii=False, indent=1)
        cases.append(case)
        print(f"{sim.label}: {sim.duration:.0f}s {'+'.join(info['systems'])} {n} msgs, {len(info['timeline'])} expected events "
              f"({time.time() - t0:.1f}s) — {case['title'][:120]}", flush=True)
    path = os.path.join(args.out, "cases.json" if not only else f"cases_only_{'_'.join(map(str, sorted(only)))}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"_說明": f"隨機情境產生器（evals/datagen）seed={args.seed}" + (f"、一定要有 {'、'.join(require)}" if require else "")
                   + "：評分標準由注入的事件在數據裡看得到的時間產生", "seed": args.seed, "require": require,
                   "data_root": args.out, "cases": cases}, f, ensure_ascii=False, indent=1)
    print(f"→ {path}")


if __name__ == "__main__":
    main()
