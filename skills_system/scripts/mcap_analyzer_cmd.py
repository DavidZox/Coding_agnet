#!/usr/bin/env python3
"""mcap_analyzer：全域 Topic Metadata 索引與 Key 檢視。

- 不帶 --topic：整份數據的索引——時間範圍、每個 Topic 的型別、筆數、頻率、起訖、角色（worker＝可以量測的 Topic／log＝/rosout，用 rosout_parser 看／
  text_only／empty／undecodable）與 Key 摘要。第一次建立後快取在 bag 資料夾的 topic_metadata.json（.yaml 給人看），之後直接讀。
- --topic：這個 Topic 每個 Key 的型別、維度（scalar／vector [n]／matrix／set／map）、資料類別（數值／向量／狀態／鍵值／文字／時間）
  與抽樣看到的值。
- --topic --key：原始值預覽（前 N 筆，可限時間窗）。
- --facts：全部 Topic 的事實（程式一次讀完整份數據量的：每個 Topic 的發布方式、中斷、開始／停止發布，每個 Key 的狀態跳轉、
  數值切換、尖峰、範圍）；快取成 bag 資料夾的 topic_facts.json。analysis_run 的事實就是這一份。

移植自 diagnostics_package/toolkit 的 mcap_analyzer.py（Metadata 摘要、檔案級 Metadata、Topic 與欄位維度、原始時序預覽）；
特徵量測另外是 mcap_feature_measure。主機端只負責把工作送進目標容器，讀檔與反序列化在容器內做。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ros2_data_common as rd  # noqa: E402

DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 570
USAGE = ("scripts/mcap_analyzer_cmd.py [數據] [--topic TOPIC] [--key KEY [--preview N] [--window 開始,結束]] [--facts] "
         "[--refresh] [--json] [--container 名稱] [--timeout 秒]")
ROLE_TEXT = {"worker": "可分析", "log": "Log（用 rosout_parser）", "text_only": "只有文字欄位", "empty": "沒有訊息",
             "undecodable": "無法解碼"}


def build_parser():
    return (rd.CliParser(USAGE)
            .add("data", nargs="?", default="")
            .add("--data", dest="data_opt", default="")
            .add("--data-root", default="")
            .add("--topic", default="")
            .add("--key", default="")
            .add("--preview", type=int, default=15)
            .add("--window", default="")
            .add("--facts", action="store_true")
            .add("--refresh", action="store_true")
            .add("--json", action="store_true")
            .add("--container", default="")
            .add("--timeout", default=str(DEFAULT_TIMEOUT)))


def _file_metadata(files):
    from mcap.reader import make_reader
    out = []
    for f in files:
        try:
            with open(f, "rb") as s:
                for m in make_reader(s).iter_metadata():
                    if m.name != "rosbag2":      # rosbag2 自己寫的 serialized_metadata（就是 metadata.yaml），不重複列
                        out.append({"name": m.name, "metadata": dict(m.metadata)})
        except Exception:   # noqa: BLE001
            continue
    return out


def _overview_text(data, idx):
    topics = idx["topics"]
    workers = [t for t in topics if t["role"] == "worker"]
    lines = [f"[PASS] Topic Metadata：{idx['label']}（{len(data['mcap_files'])} 個 mcap，"
             f"{sum(os.path.getsize(f) for f in data['mcap_files']) / 1e6:.1f} MB）",
             f"時間範圍：{rd.fmt_t(idx['start_ns'])} ～ {rd.fmt_t(idx['end_ns'])}（{idx['duration_sec']} 秒），"
             f"共 {idx['message_count']} 則訊息、{len(topics)} 個 Topic（worker 可分析 {len(workers)} 個）",
             f"索引：{idx.get('index_file') or '（沒有寫入權限，沒有快取）'}" + ("（讀快取）" if idx.get("cached") else "（剛建立）")]
    if data.get("rosout_log"):
        lines.append(f"rosout.log：{data['rosout_log']}")
    lines.append("Topic｜型別｜訊息數｜頻率 Hz｜起訖（距離開頭）｜角色｜Key（類別；×N＝依名稱展開的項目數）")
    base = idx["start_ns"]
    for t in topics:
        span = ""
        if t.get("first_sec") is not None:
            span = f"{rd.fmt_rel(int(t['first_sec'] * 1e9), base)}～{rd.fmt_rel(int(t['last_sec'] * 1e9), base)}"
        hz = t.get("avg_frequency_hz")
        role = ROLE_TEXT.get(t["role"], t["role"])
        keys = rd.key_summary(t) if t["role"] in ("worker", "text_only") else (t.get("error", "")[:80])
        lines.append(f"- {t['topic']}｜{t['type']}｜{t['message_count']}｜{hz if hz is not None else '-'}｜{span}｜{role}｜{keys}")
    meta = _file_metadata(data["mcap_files"])
    for m in meta:
        body = "；".join(f"{k}={rd.short(v, 120)}" for k, v in m["metadata"].items())
        lines.append(f"檔案級 Metadata「{m['name']}」：{body}")
    lines.append("（看某個 Topic 的 Key：--topic <名稱>；量測特徵：mcap_feature_measure；Log 去重：rosout_parser）")
    return "\n".join(lines)


def _topic_text(idx, entry):
    lines = [f"[PASS] {entry['topic']}（{entry['type']}）：{entry['message_count']} 則，"
             f"{entry.get('avg_frequency_hz', '-')} Hz，角色：{ROLE_TEXT.get(entry['role'], entry['role'])}"]
    if entry["role"] == "log":
        lines.append("這是 Log Topic：用 rosout_parser 看去重後的唯一訊號（Log 只交給 Orchestrator，worker 不量測）。")
        return "\n".join(lines)
    if entry["role"] == "undecodable":
        lines.append(f"無法解碼：{entry.get('error')}。自訂訊息型別要先用 ROS2_workspace_env 確認 Workspace，再加 --refresh 重建索引。")
        return "\n".join(lines)
    lines.append("Key｜ROS 型別｜維度｜類別｜抽樣看到的值（worker 只量測 數值／向量／狀態／鍵值／矩陣／陣列；文字與時間不量測）")
    for k in entry.get("keys", []):
        cat = rd.CATEGORY_LABELS.get(k["category"], k["category"])
        info = []
        if k.get("map_by"):
            if k.get("entries"):
                info.append(f"依 {k['map_by'][-1]} 展開 {k['entries']} 項（例：{'、'.join(k.get('examples', []))}）")
            else:
                info.append(f"依 {k['map_by'][-1]} 展開（抽樣的訊息裡都是空的）")
        if k.get("components"):
            info.append("分量 " + ",".join(k["components"]))
        if k.get("values"):
            info.append("值：" + "、".join(k["values"]))
        if k.get("range"):
            info.append(f"範圍 {rd.fmt_num(k['range'][0])}～{rd.fmt_num(k['range'][1])}")
        if k.get("distinct"):
            info.append(f"相異值 {k['distinct']} 種")
        if k.get("numeric_entries") is not None:
            info.append(f"其中數值項目 {k['numeric_entries']} 個")
        if k.get("note"):
            info.append(k["note"])
        lines.append(f"- {k['key']}｜{k['type']}｜{k['dim']}｜{cat}｜{'；'.join(info)}")
    lines.append("（量測：mcap_feature_measure --topic <名稱> --key <Key>；原始值：本工具加 --key <Key> --preview N）")
    return "\n".join(lines)


def _preview(data, idx, entry, key, n, window_arg):
    base = idx["start_ns"]
    w = rd.parse_window(window_arg, base) if window_arg else {"start_ns": idx["start_ns"], "end_ns": idx["end_ns"]}
    cls, err = rd.msg_class(entry["type"])
    if cls is None:
        return 3, f"[ERROR] 載入 {entry['type']} 失敗：{err}"
    rows, errors = [], {}
    for schema, ch, m in rd.iter_messages(data["mcap_files"], topics=[entry["topic"]], start_ns=w["start_ns"], end_ns=w["end_ns"]):
        try:
            v = rd.extract(rd.deserialize(m.data, cls), key)
        except Exception as e:   # noqa: BLE001
            errors[f"{type(e).__name__}: {e}"] = errors.get(f"{type(e).__name__}: {e}", 0) + 1
            continue
        rows.append((m.log_time, v))
        if len(rows) >= n:
            break
    if not rows:
        reason = "；".join(f"{k}（{c} 次）" for k, c in errors.items()) or "時間窗內沒有訊息"
        keys = "、".join(k["key"] for k in entry.get("keys", [])[:25])
        return 3, f"[ERROR] {entry['topic']} 的 {key} 沒有取到任何值：{reason}。可用的 Key：{keys}"
    lines = [f"[PASS] {entry['topic']} 的 {key}：前 {len(rows)} 筆（{rd.window_text(w, base)}）"]
    for t, v in rows:
        val = json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list, tuple)) else str(v)
        lines.append(f"{rd.fmt_t(t)}[{rd.fmt_rel(t, base)}] {rd.short(val, 300)}")
    if errors:
        lines.append("取值失敗：" + "；".join(f"{k}（{c} 次）" for k, c in errors.items()))
    return 0, "\n".join(lines)


def _facts_text(data, idx, scan):
    """--facts 的文字輸出：每個 Topic 一行（發布方式、則數、中斷、開始／停止發布、有變化的項目）。"""
    base = idx["start_ns"]
    rel = lambda t: rd.fmt_rel(int(round(float(t) * 1e9)), base)  # noqa: E731
    lines = [f"[PASS] 全部 Topic 的事實：{idx['label']}（{idx['duration_sec']} 秒；" + ("讀快取" if scan.get("cached") else
             f"剛量完，{scan.get('seconds')} 秒") + "）", "Topic｜發布｜事件與變化（時間＝距離數據開頭）"]
    for t, e in sorted(scan["topics"].items()):
        r = e["rate"]
        pub = f"{r['messages']} 則，{rd.pattern_text(r)}" if r.get("messages") else "沒有訊息"
        ev = []
        if r.get("single_session"):
            ev.append(f"只在 {rel(r['first_sec'])}～{rel(r['last_sec'])} 發布")
        else:
            if r.get("started_late"):
                ev.append(f"{rel(r['first_sec'])} 才開始發布")
            if r.get("stopped_early"):
                ev.append(f"{rel(r['last_sec'])} 之後停止發布")
        if r.get("gaps"):
            ev.append(f"訊息中斷 {r['gap_count']} 次（" + "、".join(f"{rel(g['start_sec'])} 起 {g['duration_sec']} 秒" for g in r["gaps"][:3]) + "）")
        for it in e["items"]:
            if it.get("changes"):
                ev.append(f"{it['name']}：{rd.short(str(it['changes'][0]['from']), 30)} → " + " → ".join(
                    f"{rd.short(str(c['to']), 30)}（{rel(c['t'])}）" for c in it["changes"][:3]) + (f" …共 {it['count']} 次" if it["count"] > 3 else ""))
            if it.get("spike_count"):
                ev.append(f"{it['name']} 尖峰 {it['spike_count']} 個（第一個 {rel(it['spikes'][0]['t'])}）")
        lines.append(f"- {t}｜{pub}｜{'；'.join(ev) or '沒有事件'}")
    lines.append("（--json 看完整的事實：每個項目的開頭與最後的值、範圍、跳轉的時間）")
    return "\n".join(lines)


def worker_main(argv):
    args = build_parser().parse(argv)
    data, err = rd.resolve_data(args.data or args.data_opt, args.data_root or None)
    if err:
        print(f"[ERROR] {err}")
        return 2
    idx = rd.build_index(data, refresh=args.refresh)
    if args.facts:
        scan = rd.scan_facts(data, idx, refresh=args.refresh)
        print(json.dumps(scan, ensure_ascii=False) if args.json else _facts_text(data, idx, scan))
        print(rd.marker_line(data).strip())
        return 0
    if not args.topic:
        if args.json:
            print(json.dumps(idx, ensure_ascii=False, indent=1))
        else:
            print(_overview_text(data, idx))
        print(rd.marker_line(data).strip())
        return 0
    entry = rd.find_topic(idx, args.topic)
    if entry is None:
        names = "、".join(t["topic"] for t in idx["topics"])
        print(f"[ERROR] 數據 {idx['label']} 裡沒有 Topic {args.topic}。有的 Topic：{names}")
        return 2
    if args.key:
        rc, text = _preview(data, idx, entry, args.key, max(1, min(args.preview, 200)), args.window)
        print(text + rd.marker_line(data))
        return rc
    if args.json:
        print(json.dumps(entry, ensure_ascii=False, indent=1))
    else:
        print(_topic_text(idx, entry))
    print(rd.marker_line(data).strip())
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
    if args.topic:
        wargs += ["--topic", args.topic]
    if args.key:
        wargs += ["--key", args.key, "--preview", str(args.preview)]
    if args.window:
        wargs += ["--window", rd.resolve_window_ids(args.window)]
    wargs += [f for f, on in (("--facts", args.facts), ("--refresh", args.refresh), ("--json", args.json)) if on]
    rc, out = rd.run_in_container(os.path.abspath(__file__), wargs, container=container, timeout=timeout,
                                  what="mcap_analyzer（Topic Metadata）",
                                  timeout_hint="第一次建立大型 bag 的索引要讀完整份資料；可以加大 --timeout，建好之後會讀快取。")
    print(rd.finalize_output(out) + cli.ignored_note())
    return rc


if __name__ == "__main__":
    if rd.in_worker():
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
