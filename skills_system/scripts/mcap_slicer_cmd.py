#!/usr/bin/env python3
"""mcap_slicer：依 Log 訊號（rosout_parser 的 L#）或指定的時間點，前後各取幾秒，切出局部的 MCAP。

輸出跟 diagnostics_package/toolkit 的 mcap_slicer.py 相同：實驗資料夾底下的 sliced_bag_<序號>_<秒>_<奈秒>/，內含 rosbag2.mcap、
metadata.yaml（rosbag2_bagfile_information＋每個 Topic 的 available_keys 與 ai_features，toolkit 的 mcap_analyzer.py 讀得懂）、
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
USAGE = ("scripts/mcap_slicer_cmd.py [數據] (--signal L#... | --at 時間...) [--before 秒] [--after 秒] [--all-occurrences] "
         "[--source auto|bag|log] [--exact] [--out 輸出資料夾] [--container 名稱] [--timeout 秒]")


def build_parser():
    return (rd.CliParser(USAGE)
            .add("data", nargs="?", default="")
            .add("--data", dest="data_opt", default="")
            .add("--data-root", default="")
            .add("--signal", action="append", default=[])
            .add("--at", action="append", default=[])
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


def _write_slice(data, idx, t_ns, start_ns, end_ns, trigger, out_dir):
    """把 [start_ns, end_ns] 的訊息寫成 out_dir/rosbag2.mcap（同 toolkit：所有 schema 與 channel 都註冊、只複製時間窗內的訊息），
    再寫 toolkit 格式的 metadata.yaml 與本系統的 topic_metadata.json。回傳 (訊息數, 每個 Topic 的筆數)。"""
    from mcap.reader import make_reader
    from mcap.writer import Writer
    os.makedirs(out_dir)
    out_file = os.path.join(out_dir, "rosbag2.mcap")
    counts = {}
    total = 0
    with open(out_file, "wb") as f_out:
        writer = Writer(f_out)
        writer.start(profile="ros2", library="agent mcap_slicer")
        schema_map, channel_map = {}, {}
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
                    sc = summ.schemas.get(ch.schema_id)
                    key = (ch.topic, ch.message_encoding)
                    if key not in channel_map:
                        sid = schema_map.get((sc.name, sc.encoding, sc.data), 0) if sc else 0
                        channel_map[key] = writer.register_channel(topic=ch.topic, message_encoding=ch.message_encoding,
                                                                   schema_id=sid, metadata=dict(ch.metadata or {}))
                        counts.setdefault(ch.topic, 0)
                    local[ch.id] = channel_map[key]
                for schema, ch, m in reader.iter_messages(start_time=start_ns, end_time=end_ns + 1, log_time_order=True):
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
                    counts[ch.topic] = counts.get(ch.topic, 0) + 1
                    total += 1
        duration = (end_ns - start_ns) / 1e9
        writer.add_metadata(name="ai_slice_diagnostic_summary", data={
            "trigger_timestamp": f"{t_ns // 1_000_000_000}.{t_ns % 1_000_000_000:09d}",
            "trigger_signal": trigger.get("id", ""), "trigger_level": trigger.get("level", ""),
            "trigger_message": trigger.get("message", ""), "trigger_node": trigger.get("node", ""),
            "window_start": f"{start_ns / 1e9:.9f}", "window_end": f"{end_ns / 1e9:.9f}",
            "window_duration_sec": str(duration), "total_messages": str(total), "source": idx["label"]})
        writer.finish()
    # toolkit 格式的 metadata.yaml（toolkit 的 mcap_analyzer.py 讀 available_keys「名稱: 型別 [維度]」）
    slice_data, _ = rd.resolve_data(out_dir)
    sidx = rd.build_index(slice_data, refresh=True)
    topics_info = []
    for t in sidx["topics"]:
        if not counts.get(t["topic"]):
            continue
        keys = [f"{k['key']}: {k['type']} [{k['dim'] if k['category'] in ('vector', 'matrix') else k['category']}]"
                for k in t.get("keys", [])]
        topics_info.append({"topic_metadata": {
            "name": t["topic"], "type": t["type"], "message_count": counts[t["topic"]], "available_keys": keys,
            "ai_features": {"avg_frequency_hz": round(counts[t["topic"]] / duration, 2) if duration > 0 else 0.0,
                            "active_in_slice": True, "role": t["role"]}}})
    meta = {"rosbag2_bagfile_information": {
        "version": 9, "storage_identifier": "mcap", "duration": {"nanoseconds": end_ns - start_ns},
        "starting_time": {"nanoseconds_since_epoch": start_ns}, "message_count": total,
        "topics_with_message_count": topics_info, "files": [{"path": "rosbag2.mcap", "message_count": total}]}}
    try:
        import yaml
        with open(os.path.join(out_dir, "metadata.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False, width=200)
    except ImportError:
        with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    return total, counts


def worker_main(argv):
    args = build_parser().parse(argv)
    if not args.signal and not args.at:
        print(f"[ERROR] 要指定 --signal（rosout_parser 的 L#）或 --at（時間點）。\n用法：{USAGE}")
        return 2
    if args.before < 0 or args.after < 0 or args.before + args.after <= 0:
        print("[ERROR] --before／--after 要是 0 以上的秒數，而且不能都是 0")
        return 2
    data, err = rd.resolve_data(args.data or args.data_opt, args.data_root or None)
    if err:
        print(f"[ERROR] {err}")
        return 2
    idx = rd.build_index(data)
    base = idx["start_ns"]
    points = []   # (t_ns, trigger)
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
    if len(points) > MAX_SLICES:
        print(f"[ERROR] 要切 {len(points)} 片，超過上限 {MAX_SLICES}：少選幾個訊號，或不要加 --all-occurrences")
        return 2
    parent = args.out or data["exp_dir"]
    os.makedirs(parent, exist_ok=True)
    counter = _next_counter(parent)
    results, lines = [], []
    for t, trig in points:
        start = max(0, t - int(args.before * 1e9))
        end = t + int(args.after * 1e9)
        if end < idx["start_ns"] or start > idx["end_ns"]:
            lines.append(f"✗ {trig['id'] or rd.fmt_t(t)}：時間 {rd.fmt_t(t)} 不在數據範圍內（{rd.fmt_t(idx['start_ns'])} ～ "
                         f"{rd.fmt_t(idx['end_ns'])}），沒有切片（Log 的時鐘可能跟錄製的不同）")
            continue
        name = f"sliced_bag_{counter}_{t // 1_000_000_000}_{t % 1_000_000_000:09d}"
        out_dir = os.path.join(parent, name)
        total, counts = _write_slice(data, idx, t, start, end, trig, out_dir)
        counter += 1
        active = sorted((c, tp) for tp, c in counts.items() if c)
        results.append({"dir": out_dir, "trigger": trig, "t_sec": rd.sec(t), "start_sec": rd.sec(start), "end_sec": rd.sec(end),
                        "messages": total, "topics": {tp: c for c, tp in active}})
        what = f"{trig['id']} {trig['level']} {trig['node']}：{rd.short(trig['message'], 60)}" if trig["id"] else trig["message"]
        lines.append(f"✓ {name}：{what}\n   時間窗 {rd.fmt_t(start)} ～ {rd.fmt_t(end)}（{rd.fmt_rel(start, base)} ～ {rd.fmt_rel(end, base)}），"
                     f"{total} 則訊息、{len(active)} 個 Topic 有資料\n   {out_dir}")
    if not results:
        print("[ERROR] 沒有切出任何切片：\n" + "\n".join(lines))
        return 3
    head = f"[PASS] 切片完成：{len(results)} 個（前 {args.before:g} 秒、後 {args.after:g} 秒）｜來源數據 {idx['label']}"
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
    wargs += ["--before", str(args.before), "--after", str(args.after), "--source", args.source]
    if args.out:
        wargs += ["--out", rd.to_container_path(args.out, mounts)]
    wargs += [f for f, on in (("--all-occurrences", args.all_occurrences), ("--exact", args.exact), ("--json", args.json)) if on]
    rc, out = rd.run_in_container(os.path.abspath(__file__), wargs, container=container, timeout=timeout,
                                  what="mcap_slicer（時間切片）",
                                  timeout_hint="來源 bag 很大時切片要讀完整份資料；可以加大 --timeout。")
    print(rd.finalize_output(out) + cli.ignored_note())
    return rc


if __name__ == "__main__":
    if rd.in_worker():
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
