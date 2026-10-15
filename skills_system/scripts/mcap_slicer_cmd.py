#!/usr/bin/env python3
"""mcap_slicer：依 Log 訊號（rosout_parser 的 L#）或指定的時間點，前後各取幾秒，切出局部的 MCAP。

輸出跟 diagnostics_package/toolkit 的 mcap_slicer.py 相同：實驗資料夾底下的 sliced_bag_<序號>_<秒>_<奈秒>/，內含 rosbag2.mcap、
metadata.yaml（rosbag2 的格式＋每個 Topic 的 available_keys 與 ai_features：rosbag2 與 toolkit 的 mcap_analyzer.py 都讀得懂）、
檔案級 Metadata「ai_slice_diagnostic_summary」（觸發的訊號、層級、Node、時間窗）；另外寫 topic_metadata.json（本系統的索引）。
改成非互動：訊號編號跟 rosout_parser 同一套（依第一次出現排序、篩選前編號），一個訊號預設切第一次出現（--all-occurrences 每一次都切）。
時間基準：bag 的 /rosout 用 MCAP log_time；rosout.log 用 Log 的 stamp（同一台機器的時鐘），時間點不在數據範圍內時回錯誤。"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ros2_data_common as rd  # noqa: E402

DEFAULT_TIMEOUT = 240
MAX_TIMEOUT = 570
MAX_SLICES = 20
USAGE = ("scripts/mcap_slicer_cmd.py [數據] (--signal L#... | --at 時間... | --window 開始,結束...) [--before 秒] [--after 秒] "
         "[--all-occurrences] [--topics TOPIC...] [--with-state] [--source auto|bag|log] [--exact] [--out 輸出資料夾] "
         "[--container 名稱] [--timeout 秒]")


def build_parser():
    return (rd.CliParser(USAGE)
            .add("data", nargs="?", default="")
            .add("--data", dest="data_opt", default="")
            .add("--data-root", default="")
            .add("--signal", action="append", default=[])
            .add("--at", action="append", default=[])
            .add("--window", action="append", default=[])
            .add("--topics", nargs="+", default=[])
            .add("--with-state", action="store_true")
            .add("--before", type=float, default=5.0)
            .add("--after", type=float, default=5.0)
            .add("--all-occurrences", action="store_true")
            .add("--source", default="auto", choices=["auto", "bag", "log"])
            .add("--exact", action="store_true")
            .add("--out", default="")
            .add("--json", action="store_true")
            .add("--container", default="")
            .add("--timeout", default=str(DEFAULT_TIMEOUT)))


def _next_counter(parent):
    nums = [int(m.group(1)) for n in os.listdir(parent) for m in [re.match(r"sliced_bag_(\d+)_", n)] if m]
    return max(nums, default=0) + 1


def _qos_profiles(ch_meta):
    """rosbag2 寫 MCAP 時，channel metadata 的 offered_qos_profiles 是 YAML 字串；metadata.yaml 要的是清單（解不開或沒有時是空清單，
    同 toolkit 的 mcap_slicer.py）。"""
    text = (ch_meta or {}).get("offered_qos_profiles", "")
    try:
        import yaml
        profiles = yaml.safe_load(text) if text else []
    except Exception:   # noqa: BLE001  沒有 PyYAML 或格式不對：照 rosbag2 的預設（空清單）
        profiles = []
    return profiles if isinstance(profiles, list) else []


def _write_slice(data, idx, t_ns, start_ns, end_ns, trigger, out_dir, topics=None, with_state=False):
    """把 [start_ns, end_ns] 的訊息寫成 out_dir/rosbag2.mcap（同 toolkit：所有 schema 與 channel 都註冊、只複製時間窗內的訊息），
    再寫 metadata.yaml（rosbag2 的格式＋toolkit 的 available_keys、ai_features）與本系統的 topic_metadata.json。
    回傳 (訊息數, 每個 Topic 的筆數, 狀態快照筆數)。
    topics：只切這些 Topic（analysis_run 只切指派的 Topic）。with_state：每個 Topic 另外帶上時間窗之前的最後一則（保留原本的
    時間戳），只在狀態改變時才發布的 Topic 在切片裡才接得上時間窗開始時的狀態（mcap_feature_measure 的沿用）。"""
    from mcap.reader import make_reader
    from mcap.writer import Writer
    os.makedirs(out_dir)
    out_file = os.path.join(out_dir, "rosbag2.mcap")
    counts = {}
    total = 0
    state_total = 0
    wanted = set(topics) if topics else None
    chan_meta = {}       # Topic → (message_encoding, channel metadata)：metadata.yaml 的 serialization_format、QoS、型別雜湊
    span = [None, None]  # 寫進切片的第一則、最後一則 log_time（rosbag2 的 starting_time／duration）

    def note(ch, m):
        chan_meta.setdefault(ch.topic, (ch.message_encoding, dict(ch.metadata or {})))
        span[0] = m.log_time if span[0] is None else min(span[0], m.log_time)
        span[1] = m.log_time if span[1] is None else max(span[1], m.log_time)
    with open(out_file, "wb") as f_out:
        writer = Writer(f_out)
        writer.start(profile="ros2", library="agent mcap_slicer")
        schema_map, channel_map = {}, {}

        def channel_for(schema, ch):
            key = (ch.topic, ch.message_encoding)
            if key not in channel_map:
                sid = 0
                if schema is not None:
                    sk = (schema.name, schema.encoding, schema.data)
                    if sk not in schema_map:
                        schema_map[sk] = writer.register_schema(name=schema.name, encoding=schema.encoding, data=schema.data)
                    sid = schema_map[sk]
                channel_map[key] = writer.register_channel(topic=ch.topic, message_encoding=ch.message_encoding,
                                                           schema_id=sid, metadata=dict(ch.metadata or {}))
                counts.setdefault(ch.topic, 0)
            return channel_map[key]

        if with_state:   # 時間窗之前的最後一則：依時間先寫（之後的時間窗訊息都比它們晚，檔案內的時間仍是遞增的）
            snaps = [rec for tp in sorted(wanted or {t["topic"] for t in idx["topics"]})
                     for rec in [rd.last_record_before(data["mcap_files"], tp, start_ns)] if rec]
            for schema, ch, m in sorted(snaps, key=lambda r: r[2].log_time):
                writer.add_message(channel_id=channel_for(schema, ch), log_time=m.log_time, data=m.data,
                                   publish_time=m.publish_time, sequence=m.sequence)
                note(ch, m)
                counts[ch.topic] = counts.get(ch.topic, 0) + 1
                state_total += 1
        for src in data["mcap_files"]:
            with open(src, "rb") as f_in:
                reader = make_reader(f_in)
                summ = reader.get_summary()
                for sc in (summ.schemas.values() if summ else []):
                    key = (sc.name, sc.encoding, sc.data)
                    if key not in schema_map:
                        schema_map[key] = writer.register_schema(name=sc.name, encoding=sc.encoding, data=sc.data)
                local = {}
                for ch in (summ.channels.values() if summ else []):
                    if wanted is not None and ch.topic not in wanted:
                        continue
                    sc = summ.schemas.get(ch.schema_id)
                    key = (ch.topic, ch.message_encoding)
                    if key not in channel_map:
                        sid = schema_map.get((sc.name, sc.encoding, sc.data), 0) if sc else 0
                        channel_map[key] = writer.register_channel(topic=ch.topic, message_encoding=ch.message_encoding,
                                                                   schema_id=sid, metadata=dict(ch.metadata or {}))
                        counts.setdefault(ch.topic, 0)
                    local[ch.id] = channel_map[key]
                for schema, ch, m in reader.iter_messages(topics=sorted(wanted) if wanted else None, start_time=start_ns,
                                                          end_time=end_ns + 1, log_time_order=True):
                    cid = local.get(ch.id)
                    if cid is None:
                        key = (ch.topic, ch.message_encoding)
                        if key not in channel_map:
                            sid = 0
                            if schema is not None:
                                sk = (schema.name, schema.encoding, schema.data)
                                if sk not in schema_map:
                                    schema_map[sk] = writer.register_schema(name=schema.name, encoding=schema.encoding,
                                                                            data=schema.data)
                                sid = schema_map[sk]
                            channel_map[key] = writer.register_channel(topic=ch.topic, message_encoding=ch.message_encoding,
                                                                       schema_id=sid, metadata=dict(ch.metadata or {}))
                        cid = local[ch.id] = channel_map[key]
                    writer.add_message(channel_id=cid, log_time=m.log_time, data=m.data, publish_time=m.publish_time,
                                       sequence=m.sequence)
                    note(ch, m)
                    counts[ch.topic] = counts.get(ch.topic, 0) + 1
                    total += 1
        duration = (end_ns - start_ns) / 1e9
        writer.add_metadata(name="ai_slice_diagnostic_summary", data={
            "trigger_timestamp": f"{t_ns // 1_000_000_000}.{t_ns % 1_000_000_000:09d}",
            "trigger_signal": trigger.get("id", ""), "trigger_level": trigger.get("level", ""),
            "trigger_message": trigger.get("message", ""), "trigger_node": trigger.get("node", ""),
            "window_start": f"{start_ns / 1e9:.9f}", "window_end": f"{end_ns / 1e9:.9f}",
            "window_duration_sec": str(duration), "total_messages": str(total), "source": idx["label"],
            "source_start": f"{idx['start_ns'] / 1e9:.9f}", "topics_filter": ",".join(sorted(wanted)) if wanted else "",
            "state_snapshot_messages": str(state_total)})
        writer.finish()
    # metadata.yaml：rosbag2 的格式（version 9：每個 Topic 有 serialization_format、offered_qos_profiles、type_description_hash，
    # message_count 跟 topic_metadata 同一層），`ros2 bag info／play <切片資料夾>` 讀得到；topic_metadata 另外帶 toolkit 的
    # available_keys（「名稱: 型別 [維度]」）與 ai_features（rosbag2 不讀這兩個鍵；toolkit 的 mcap_analyzer.py 兩種位置的 message_count 都讀）。
    # 同 toolkit 2026-10-15 的 mcap_slicer.py：starting_time／duration 是第一則到最後一則訊息，時間窗與觸發的訊號寫在 custom_data（值都是字串）。
    # 舊版只寫 name、type 與 topic_metadata 裡的 message_count，rosbag2 回「invalid node; first invalid key: serialization_format」。
    slice_data, _ = rd.resolve_data(out_dir)
    sidx = rd.build_index(slice_data, refresh=True)
    topics_info = []
    for t in sidx["topics"]:
        if not counts.get(t["topic"]):
            continue
        keys = [f"{k['key']}: {k['type']} [{k['dim'] if k['category'] in ('vector', 'matrix') else k['category']}]"
                for k in t.get("keys", [])]
        encoding, ch_meta = chan_meta.get(t["topic"], ("cdr", {}))
        topics_info.append({"topic_metadata": {
            "name": t["topic"], "type": t["type"], "serialization_format": encoding or "cdr",
            "offered_qos_profiles": _qos_profiles(ch_meta), "type_description_hash": ch_meta.get("topic_type_hash", ""),
            "available_keys": keys,
            "ai_features": {"avg_frequency_hz": round(counts[t["topic"]] / duration, 2) if duration > 0 else 0.0,
                            "active_in_slice": True, "role": t["role"]}},
            "message_count": counts[t["topic"]]})
    n_msgs = total + state_total
    first_ns = span[0] if n_msgs else start_ns
    dur_ns = (span[1] - span[0]) if n_msgs else 0
    custom = {"window_start_ns": str(start_ns), "window_end_ns": str(end_ns), "window_duration_sec": str(duration),
              "trigger_timestamp": f"{t_ns // 1_000_000_000}.{t_ns % 1_000_000_000:09d}", "trigger_signal": str(trigger.get("id", "")),
              "trigger_level": str(trigger.get("level", "")), "trigger_node": str(trigger.get("node", "")),
              "trigger_message": str(trigger.get("message", "")), "source": str(idx["label"]),
              "state_snapshot_messages": str(state_total)}
    meta = {"rosbag2_bagfile_information": {
        "version": 9, "storage_identifier": "mcap", "duration": {"nanoseconds": dur_ns},
        "starting_time": {"nanoseconds_since_epoch": first_ns}, "message_count": n_msgs,
        "topics_with_message_count": topics_info, "compression_format": "", "compression_mode": "",
        "relative_file_paths": ["rosbag2.mcap"],
        "files": [{"path": "rosbag2.mcap", "starting_time": {"nanoseconds_since_epoch": first_ns},
                   "duration": {"nanoseconds": dur_ns}, "message_count": n_msgs}],
        "custom_data": custom, "ros_distro": os.environ.get("ROS_DISTRO", "")}}
    try:
        import yaml
        with open(os.path.join(out_dir, "metadata.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False, width=200)
    except ImportError:
        with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    return total, counts, state_total


def worker_main(argv):
    args = build_parser().parse(argv)
    if not args.signal and not args.at and not args.window:
        print(f"[ERROR] 要指定 --signal（rosout_parser 的 L#）、--at（時間點）或 --window（開始,結束）。\n用法：{USAGE}")
        return 2
    if (args.signal or args.at) and (args.before < 0 or args.after < 0 or args.before + args.after <= 0):
        print("[ERROR] --before／--after 要是 0 以上的秒數，而且不能都是 0")
        return 2
    data, err = rd.resolve_data(args.data or args.data_opt, args.data_root or None)
    if err:
        print(f"[ERROR] {err}")
        return 2
    idx = rd.build_index(data)
    base = idx["start_ns"]
    topics = [t if t.startswith("/") else "/" + t for t in args.topics]
    have = {t["topic"] for t in idx["topics"]}
    missing = [t for t in topics if t not in have]
    if missing:
        print(f"[ERROR] 數據 {idx['label']} 裡沒有 Topic {'、'.join(missing)}。有的 Topic：{'、'.join(sorted(have))}")
        return 2
    points = []   # (t_ns, trigger) 或 (t_ns, trigger, start_ns, end_ns)
    if args.signal:
        events, source, err = rd.load_log_events(data, args.source)
        if err:
            print(f"[ERROR] {err}")
            return 3
        groups = {g["id"].upper(): g for g in rd.dedup_events(events, merge_numbers=not args.exact)}
        for sid in args.signal:
            g = groups.get(sid.strip().upper())
            if g is None:
                print(f"[ERROR] 沒有訊號 {sid}（Log 來源：{source}；共 {len(groups)} 個訊號，先用 rosout_parser 查編號，"
                      f"兩邊的 --source 要一樣）")
                return 2
            times = g["times_ns"] if args.all_occurrences else g["times_ns"][:1]
            for t in times:
                points.append((t, {"id": g["id"], "level": g["level"], "node": g["node"], "message": g["message"]}))
    for a in args.at:
        try:
            points.append((rd.parse_time(a, base), {"id": "", "level": "", "node": "", "message": f"指定時間 {a}"}))
        except ValueError as e:
            print(f"[ERROR] {e}")
            return 2
    for text in args.window:   # 明確的時間窗（analysis_run 用：合併過的、前後不對稱的時間窗）
        try:
            w = rd.parse_window(rd.resolve_window_ids(text), base)
        except ValueError as e:
            print(f"[ERROR] {e}")
            return 2
        label = w.get("label") or ""
        points.append((w.get("anchor_ns") or w["start_ns"], {"id": label, "level": "", "node": "", "message": f"時間窗 {label}".strip()},
                       w["start_ns"], w["end_ns"]))
    if len(points) > MAX_SLICES:
        print(f"[ERROR] 要切 {len(points)} 片，超過上限 {MAX_SLICES}：少選幾個訊號，或不要加 --all-occurrences")
        return 2
    parent = args.out or data["exp_dir"]
    os.makedirs(parent, exist_ok=True)
    counter = _next_counter(parent)
    results, lines = [], []
    for p in points:
        t, trig = p[0], p[1]
        start, end = (p[2], p[3]) if len(p) > 2 else (max(0, t - int(args.before * 1e9)), t + int(args.after * 1e9))
        if end < idx["start_ns"] or start > idx["end_ns"]:
            lines.append(f"✗ {trig['id'] or rd.fmt_t(t)}：時間 {rd.fmt_t(t)} 不在數據範圍內（{rd.fmt_t(idx['start_ns'])} ～ "
                         f"{rd.fmt_t(idx['end_ns'])}），沒有切片（Log 的時鐘可能跟錄製的不同）")
            continue
        name = f"sliced_bag_{counter}_{t // 1_000_000_000}_{t % 1_000_000_000:09d}"
        out_dir = os.path.join(parent, name)
        total, counts, state_n = _write_slice(data, idx, t, start, end, trig, out_dir, topics=topics or None,
                                              with_state=args.with_state)
        counter += 1
        active = sorted((c, tp) for tp, c in counts.items() if c)
        results.append({"dir": out_dir, "trigger": trig, "t_sec": rd.sec(t), "start_sec": rd.sec(start), "end_sec": rd.sec(end),
                        "messages": total, "state_messages": state_n, "topics": {tp: c for c, tp in active}})
        what = f"{trig['id']} {trig['level']} {trig['node']}：{rd.short(trig['message'], 60)}" if trig["id"] else trig["message"]
        lines.append(f"✓ {name}：{what}\n   時間窗 {rd.fmt_t(start)} ～ {rd.fmt_t(end)}（{rd.fmt_rel(start, base)} ～ {rd.fmt_rel(end, base)}），"
                     f"{total} 則訊息、{len(active)} 個 Topic 有資料" + (f"、狀態快照 {state_n} 則" if args.with_state else "")
                     + f"\n   {out_dir}")
    if not results:
        print("[ERROR] 沒有切出任何切片：\n" + "\n".join(lines))
        return 3
    span = f"前 {args.before:g} 秒、後 {args.after:g} 秒" if (args.signal or args.at) else "明確的時間窗"
    head = (f"[PASS] 切片完成：{len(results)} 個（{span}" + (f"；只切 {len(topics)} 個 Topic" if topics else "") + "）"
            + f"｜來源數據 {idx['label']}")
    if args.json:
        print(json.dumps({"slices": results}, ensure_ascii=False, indent=1))
    else:
        print("\n".join([head] + lines + ["（切片也是數據：mcap_analyzer／mcap_feature_measure 可以直接用切片資料夾）"]))
    return 0


def host_main(argv):
    cli = build_parser()
    args = cli.parse(argv, lenient=True)
    sys.path.insert(0, rd.HERE)
    from _docker_common import parse_timeout, resolve_container
    timeout, err = parse_timeout(args.timeout, DEFAULT_TIMEOUT, MAX_TIMEOUT)
    if err:
        print(err)
        return 2
    container, err = resolve_container(args.container)
    if err:
        print(err)
        return 2
    mounts = rd.container_mounts(container)
    wargs = rd.host_common_args(container, args.data or args.data_opt, mounts)
    for s in args.signal:
        wargs += ["--signal", s]
    for a in args.at:
        wargs += ["--at", a]
    for w in args.window:
        wargs += ["--window", rd.resolve_window_ids(w)]
    if args.topics:
        wargs += ["--topics", *args.topics]
    wargs += ["--before", str(args.before), "--after", str(args.after), "--source", args.source]
    if args.out:
        wargs += ["--out", rd.to_container_path(args.out, mounts)]
    wargs += [f for f, on in (("--all-occurrences", args.all_occurrences), ("--exact", args.exact), ("--json", args.json),
                              ("--with-state", args.with_state)) if on]
    rc, out = rd.run_in_container(os.path.abspath(__file__), wargs, container=container, timeout=timeout,
                                  what="mcap_slicer（時間切片）",
                                  timeout_hint="來源 bag 很大時切片要讀完整份資料；可以加大 --timeout。")
    if args.json and rc == 0:   # 切片在容器裡；附上主機路徑（有掛載時），給人看與 analysis_run 的產物紀錄用
        lines = out.rstrip().splitlines()
        tail = []
        while lines and lines[-1].startswith("["):   # 末行的狀態標記（[TARGET_CONTAINER] 等）
            tail.insert(0, lines.pop())
        try:
            body = "\n".join(lines)
            js = json.loads(body[body.index("{"):])
            for sl in js.get("slices", []):
                sl["host_dir"] = rd.to_host_path(sl["dir"], mounts)
            out = "\n".join([json.dumps(js, ensure_ascii=False, indent=1)] + tail)
        except (ValueError, KeyError):
            pass
    print(rd.finalize_output(out) + cli.ignored_note())
    return rc


if __name__ == "__main__":
    if rd.in_worker():
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
