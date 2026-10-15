#!/usr/bin/env python3
"""mcap_feature_measure：對一個 Topic 的一個或幾個 Key，在指定的時間窗內按需量測特徵（Lazy Evaluation）。

- 數值（scalar）：筆數、極值、均值、變異數、標準差、趨勢斜率、尖峰（離均值 >2.5σ，同 toolkit）、最大跳變；
- 向量（vector [n]）：每個分量各自量（x、y、z…）；矩陣、陣列：形狀與元素統計；
- 狀態（uint8／bool／列舉字串／代碼集合）：狀態跳轉（Edge Detection：時間、從哪個值到哪個值、集合的增減）、各狀態的時間占比；
  整數而且相異值 ≤10 也當狀態（同 toolkit）；
- 依名稱展開的項目（DiagnosticArray 的 status.level、status.values…）：每個名稱各自量，只列有變化的；
- 每個時間窗另外量訊息頻率與中斷（間隔超過中位數週期 3 倍）。
文字（自由文字）與時間欄位不量測：文字屬於 Orchestrator 的 Log 分析範圍。

移植自 diagnostics_package/toolkit 的 mcap_feature_measure.py（compute_features）。analysis_run 的 worker 呼叫時，數據、Topic 與
時間窗由系統帶入（環境變數 ANALYSIS_DATA／ANALYSIS_TOPIC／ANALYSIS_WINDOWS），worker 只要選 Key。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ros2_data_common as rd  # noqa: E402

DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 570
USAGE = ("scripts/mcap_feature_measure_cmd.py [數據] --topic TOPIC --key KEY [--key KEY]... "
         "[--window 開始,結束|W1]... [--around 時間 --before 秒 --after 秒] [--filter 名稱關鍵字] [--all-entries] [--json] "
         "[--container 名稱] [--timeout 秒]")


def build_parser():
    return (rd.CliParser(USAGE)
            .add("data", nargs="?", default="")
            .add("--data", dest="data_opt", default="")
            .add("--data-root", default="")
            .add("--topic", default="")
            .add("--key", action="append", default=[])
            .add("--window", action="append", default=[])
            .add("--around", default="")
            .add("--before", type=float, default=5.0)
            .add("--after", type=float, default=5.0)
            .add("--filter", default="")
            .add("--all-entries", action="store_true")
            .add("--json", action="store_true")
            .add("--container", default="")
            .add("--timeout", default=str(DEFAULT_TIMEOUT)))


def _unchanged_summary(feats):
    counts = {}
    for f in feats:
        v = f.get("first") if f["kind"] in ("state", "numeric") else f["kind"]
        v = rd.short(rd.fmt_num(v) if isinstance(v, float) else v, 24)
        counts[v] = counts.get(v, 0) + 1
    return "、".join(f"{v}×{c}" for v, c in sorted(counts.items(), key=lambda x: -x[1])[:5])


def worker_main(argv):
    args = build_parser().parse(argv)
    if not args.topic or not args.key:
        print(f"[ERROR] 要指定 --topic 與至少一個 --key（Key 名稱用 mcap_analyzer --topic <名稱> 查）。\n用法：{USAGE}")
        return 2
    data, err = rd.resolve_data(args.data or args.data_opt, args.data_root or None)
    if err:
        print(f"[ERROR] {err}")
        return 2
    idx = rd.build_index(data)
    entry = rd.find_topic(idx, args.topic)
    if entry is None:
        print(f"[ERROR] 數據 {idx['label']} 裡沒有 Topic {args.topic}。有的 Topic：{'、'.join(t['topic'] for t in idx['topics'])}")
        return 2
    if entry["role"] == "log":
        print(f"[ERROR] {entry['topic']} 是 Log：Log 的字串由 rosout_parser 去重後交給 Orchestrator 看，不做特徵量測。")
        return 2
    if entry["role"] in ("undecodable", "empty"):
        print(f"[ERROR] {entry['topic']} 沒辦法量測：{entry.get('error') or '沒有任何訊息'}"
              + ("（自訂訊息型別要先用 ROS2_workspace_env 確認 Workspace）" if entry["role"] == "undecodable" else ""))
        return 2
    keys, descs, skipped = [], [], []
    for k in args.key:
        d = rd.find_key(entry, k)
        if d is None:
            avail = "、".join(x["key"] for x in entry.get("keys", []) if x["category"] in rd.WORKER_CATEGORIES)
            print(f"[ERROR] {entry['topic']} 沒有 Key「{k}」。可以量測的 Key：{avail}")
            return 2
        if d["category"] in ("text", "time"):
            skipped.append(f"{k}（{rd.CATEGORY_LABELS[d['category']]}：不量測"
                           + ("，自由文字屬於 Orchestrator 的 Log 分析範圍" if d["category"] == "text" else "") + "）")
            continue
        keys.append(k)
        descs.append(d)
    if not keys:
        print("[ERROR] 沒有可以量測的 Key：" + "；".join(skipped))
        return 2
    base = idx["start_ns"]
    try:
        if args.window:
            windows = [rd.parse_window(w, base) for w in args.window]
        elif args.around:
            t = rd.parse_time(args.around, base)
            windows = [{"start_ns": t - int(args.before * 1e9), "end_ns": t + int(args.after * 1e9), "anchor_ns": t, "label": ""}]
        else:
            windows = [{"start_ns": idx["start_ns"], "end_ns": idx["end_ns"], "anchor_ns": None, "label": "整份數據"}]
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 2
    clamped = [rd.clamp_window(w, idx["start_ns"], idx["end_ns"]) for w in windows]
    if not any(clamped):
        print(f"[ERROR] 時間窗都不在數據範圍內（數據：{rd.fmt_t(idx['start_ns'])} ～ {rd.fmt_t(idx['end_ns'])}；"
              f"時間窗：{'、'.join(rd.window_text(w) for w in windows)}）。時間可以用 +秒（距離數據開頭）表示。")
        return 2
    windows = [w for w in clamped if w]

    all_flags, results, lines = [], [], []
    lines.append(f"[PASS] 特徵量測：{entry['topic']}（{entry['type']}）｜數據 {idx['label']}"
                 f"（{rd.fmt_t(idx['start_ns'])} ～ {rd.fmt_t(idx['end_ns'])}）")
    for w in windows:
        rel_base = base   # [+秒] 一律是距離數據開頭（跟 rosout_parser、mcap_analyzer、analysis_run 同一個基準）；錨點另外標
        times, series, errors = rd.collect_series(data["mcap_files"], entry["topic"], entry["type"], keys, w)
        rate = rd.rate_features(times, w)
        wname = w.get("label") or "時間窗"
        lines.append(f"{wname}：{rd.window_text(w, base)}" + ("（已限制在數據範圍內）" if w.get("clamped") else "")
                     + "；[+秒] 是距離數據開頭的時間")
        if not times:
            lines.append("  時間窗內沒有這個 Topic 的訊息（Topic 沒有在發布，或時間窗不在數據範圍內）")
            all_flags.append(f"{wname} 沒有訊息")
            results.append({"window": rd.jsonable(w), "rate": rate, "keys": {}})
            continue
        r = f"  訊息 {rate['messages']} 筆"
        if rate.get("avg_hz"):
            r += f"，平均 {rate['avg_hz']} Hz，最大間隔 {rate['max_gap_sec']} 秒"
        if rate.get("gaps"):
            r += "；中斷 " + "、".join(f"{rd.fmt_t(int(g['start_sec'] * 1e9))}[{rd.fmt_rel(int(g['start_sec'] * 1e9), rel_base)}] 起 "
                                     f"{g['duration_sec']} 秒" for g in rate["gaps"])
            all_flags.append(f"{wname} 訊息中斷 {len(rate['gaps'])} 次（最長 {rate['max_gap_sec']} 秒）")
        if rate.get("starts_after_window_sec", 0) > 1.0:
            r += f"；時間窗開始後 {rate['starts_after_window_sec']} 秒才有第一筆"
        lines.append(r)
        wkeys = {}
        for k, d in zip(keys, descs):
            entries = series[k]
            is_map = bool(d.get("map_by")) or d["category"] == "kv"
            if args.filter and is_map:   # --filter 只篩「依名稱展開」的項目；一般的 Key 照常量（實測 worker 對一般 Key 也加 --filter）
                entries = {lab: pts for lab, pts in entries.items() if args.filter.lower() in lab.lower()}
            feats, flags = rd.measure_key(entries, d, w, k)
            all_flags += [f"{wname} {x}" for x in flags]
            dim = d.get("dim", "scalar")
            lines.append(f"  ▸ {k}（{dim}，{rd.CATEGORY_LABELS.get(d['category'], d['category'])}，{d['type']}）")
            if errors.get(k):
                lines.append(f"     取值失敗：{errors[k]}")
            if not feats:
                lines.append("     時間窗內沒有取到值" + (f"（--filter {args.filter} 沒有符合的項目）" if args.filter and is_map else ""))
            shown, quiet = [], []
            for lab, f in feats.items():
                (shown if (not is_map or args.all_entries or rd.changed(f)) else quiet).append((lab, f))
            for lab, f in shown[:30]:
                lines += rd.feature_lines(lab if lab != "value" else k, f, rel_base)
            if len(shown) > 30:
                lines.append(f"     …還有 {len(shown) - 30} 個有變化的項目（--filter 縮小、--json 看全部）")
            if quiet:
                lines.append(f"     其餘 {len(quiet)} 項在時間窗內沒有變化（{_unchanged_summary([f for _, f in quiet])}）")
            wkeys[k] = {"category": d["category"], "dim": dim, "type": d["type"], "data_type": rd.data_type_of(d),
                        "map_by": d.get("map_by"), "entries": feats, "flags": flags}
        results.append({"window": w, "rate": rate, "keys": wkeys, "errors": errors})
    if skipped:
        lines.append("沒有量測：" + "；".join(skipped))
    lines.append("異常指標（程式判斷）：" + ("；".join(all_flags) if all_flags else "沒有尖峰、沒有狀態跳轉、沒有訊息中斷"))
    if args.json:
        print(json.dumps(rd.jsonable({"data": idx["label"], "topic": entry["topic"], "type": entry["type"],
                                      "data_start_ns": idx["start_ns"], "windows": results, "flags": all_flags,
                                      "skipped": skipped}), ensure_ascii=False, indent=1, default=str))
        print(rd.marker_line(data).strip())
    else:
        print("\n".join(lines) + rd.marker_line(data))
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
    topic = args.topic or (os.environ.get("ANALYSIS_TOPIC") or "").strip()   # analysis worker：系統帶入指派的 Topic
    if topic:
        wargs += ["--topic", topic]
    for k in args.key:
        wargs += ["--key", k]
    windows = [rd.resolve_window_ids(w) for w in args.window]
    if not windows and not args.around:   # analysis worker 沒指定時間窗：用 Orchestrator 指派的全部時間窗
        windows = [rd.resolve_window_ids(w["id"]) for w in rd.analysis_windows()]
    for w in windows:
        wargs += ["--window", w]
    if args.around:
        wargs += ["--around", args.around, "--before", str(args.before), "--after", str(args.after)]
    if args.filter:
        wargs += ["--filter", args.filter]
    wargs += [f for f, on in (("--all-entries", args.all_entries), ("--json", args.json)) if on]
    rc, out = rd.run_in_container(os.path.abspath(__file__), wargs, container=container, timeout=timeout,
                                  what="mcap_feature_measure（特徵量測）",
                                  timeout_hint="時間窗很長、訊息很多時，縮短時間窗或少量測幾個 Key。")
    print(rd.finalize_output(out) + cli.ignored_note())
    return rc


if __name__ == "__main__":
    if rd.in_worker():
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
