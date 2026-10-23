#!/usr/bin/env python3
"""mcap_feature_measure：對一個 Topic 的一個或幾個 Key，在指定的時間窗內按需量測特徵（Lazy Evaluation）。

- 數值（scalar）：筆數、極值（與時間）、均值、變異數、標準差、趨勢斜率、尖峰（單獨幾筆跳出去又回來：跟前後 9 筆的中位數差超過
  殘差 MAD 的 6 倍）、最大跳變；只有幾種值的列每次切換；
- 向量（vector [n]）：每個分量各自量（x、y、z…）；矩陣、陣列：形狀與元素統計；
- 狀態（uint8／bool／列舉字串／代碼集合）：狀態跳轉（Edge Detection：時間、從哪個值到哪個值、集合的增減）、各狀態的時間占比；
  整數而且相異值 ≤10 也當狀態（同 toolkit）；
- 依名稱展開的項目（DiagnosticArray 的 status.level、status.values…）：每個名稱各自量，只列有變化的；
- 字串裡的 JSON（std_msgs/String 裝的狀態）：欄位展開成 Key（data.status、data.robots.battery），跟一般的欄位一樣量；
- 每個時間窗另外量訊息流：發布方式（固定頻率／狀態改變時才發布／不定期，由內容與時間判斷，同 analysis_run 的全部 Topic 量測）；
  固定頻率的才判斷中斷（間隔超過週期 3 倍、且 ≥0.5 秒）與中途開始／停止發布；
- 門檻條件（--where 欄位<值）：幾筆符合、第一筆符合的時間與值、它的前一筆、符合的時段與時間長度（同 ROS2_topic_echo 的 --where）。
文字（自由文字）與時間欄位不量測：Log 用 rosout_parser 看（去重後的唯一訊號）。

移植自 diagnostics_package/toolkit 的 mcap_feature_measure.py（compute_features）。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ros2_data_common as rd  # noqa: E402

DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 570
USAGE = ("scripts/mcap_feature_measure_cmd.py [數據] --topic TOPIC --key KEY [--key KEY]... "
         "[--window 開始,結束]... [--around 時間 --before 秒 --after 秒] [--where 欄位<值]... [--filter 名稱關鍵字] [--all-entries] [--json] "
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
            .add("--where", action="append", default=[])
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
    conds = []
    for expr in args.where:
        c, err = rd.parse_where(expr)
        if err:
            print(f"[ERROR] --where {err}。\n用法：{USAGE}")
            return 2
        conds.append(c)
    if not args.topic or not (args.key or conds):
        print(f"[ERROR] 要指定 --topic 與至少一個 --key 或 --where（Key 名稱用 mcap_analyzer --topic <名稱> 查）。\n用法：{USAGE}")
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
        print(f"[ERROR] {entry['topic']} 是 Log：Log 的字串用 rosout_parser 看（去重後的唯一訊號），不做特徵量測。")
        return 2
    if entry["role"] in ("undecodable", "empty"):
        print(f"[ERROR] {entry['topic']} 沒辦法量測：{entry.get('error') or '沒有任何訊息'}"
              + ("（自訂訊息型別要先用 ROS2_workspace_env 確認 Workspace）" if entry["role"] == "undecodable" else ""))
        return 2
    keys, descs, skipped, unknown = [], [], [], []
    avail = "、".join(x["key"] for x in entry.get("keys", []) if x["category"] in rd.WORKER_CATEGORIES)
    for k in args.key:
        d = rd.find_key(entry, k)
        head, _, rest = k.partition(".")
        if d is None and head in rd.CATEGORY_LABELS and rest and rd.find_key(entry, rest):
            k, d = rest, rd.find_key(entry, rest)   # 「類別.Key」（實測 26b：state.primary_reaction）：類別不是 Key 的一部分
        if d is None:   # 不存在的 Key：認得的照量、最後說明（唯讀工具，比回錯誤讓模型重送一次省一輪；全部都不認得才回錯誤）
            unknown.append(k)
            skipped.append(f"{k}（沒有這個 Key" + (f"：{k} 是 Key 的類別（{rd.CATEGORY_LABELS[k]}），不是 Key" if k in rd.CATEGORY_LABELS else "")
                           + "）")
            continue
        if k in keys:
            continue
        if d["category"] in ("text", "time"):
            subs = [x["key"] for x in entry.get("keys", []) if x["key"].startswith(k + ".")]
            skipped.append(f"{k}（JSON 字串：量它的欄位，例如 {'、'.join(subs[:4])}）" if d.get("json") and subs else
                           f"{k}（{rd.CATEGORY_LABELS[d['category']]}：不量測" + ("，自由文字不量測" if d["category"] == "text" else "") + "）")
            continue
        keys.append(k)
        descs.append(d)
    for c in conds:   # 條件用到、--key 沒列的 Key 自動加進來量（「status.level[motor]」「linear.x」用前面的 Key）
        field = c["field"].split("[")[0]
        d = next((x for x in (rd.find_key(entry, f) for f in dict.fromkeys((field, field.rsplit(".", 1)[0]))) if x), None)
        if d is None or d["category"] in ("text", "time"):
            import difflib
            names = [x["key"] for x in entry.get("keys", []) if x["category"] in rd.WORKER_CATEGORIES]
            near = difflib.get_close_matches(field, names, n=6, cutoff=0.3)
            print(f"[ERROR] --where {c['text']}：{entry['topic']} 沒有可以量測的 Key「{field}」"
                  + (f"（相近的：{'、'.join(near)}）" if near else "") + f"。可以量測的 Key：{'、'.join(names[:30])}")
            return 2
        if d["key"] not in keys:
            keys.append(d["key"])
            descs.append(d)
    if not keys:
        if unknown:   # 實測 26b 把 Key 目錄的類別欄當成 Key（--key state）：點名類別，列出可以量測的 Key
            print(f"[ERROR] {entry['topic']} 沒有 Key「{'」「'.join(unknown)}」"
                  + ("（state、numeric 這些是 Key 的類別，不是 Key）" if any(u in rd.CATEGORY_LABELS for u in unknown) else "")
                  + f"。可以量測的 Key：{avail}")
            return 2
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

    all_flags, anomalies, results, lines = [], [], [], []   # anomalies：程式判斷的異常（只有訊息中斷）；其餘 flags 是量到的變化
    lines.append(f"[PASS] 特徵量測：{entry['topic']}（{entry['type']}）｜數據 {idx['label']}"
                 f"（{rd.fmt_t(idx['start_ns'])} ～ {rd.fmt_t(idx['end_ns'])}）")
    for w in windows:
        rel_base = base   # [+秒] 一律是距離數據開頭（跟 rosout_parser、mcap_analyzer、analysis_run 同一個基準）；錨點另外標
        src = data
        # 發布方式要看這個 Topic 全部的狀態與數值（每一則是不是都帶著改變），跟 analysis_run 的全部 Topic 量測同一個判斷
        extra = [k["key"] for k in entry.get("keys", []) if k["category"] in rd.SCAN_CATEGORIES and not k["key"].startswith("header.")
                 and k["key"] not in keys]
        all_descs = {k["key"]: k for k in entry.get("keys", [])}
        all_descs.update(dict(zip(keys, descs)))
        times, series, errors = rd.collect_series(src["mcap_files"], entry["topic"], entry["type"], keys + extra, w, descs=all_descs)
        pattern_feats = []
        for k in keys + extra:
            pattern_feats += list(rd.measure_key(series[k], all_descs[k], w, k)[0].values())
        rate = rd.rate_features(times, w, data_start_ns=idx["start_ns"], change_times=rd.change_times(pattern_feats))
        wname = w.get("label") or "時間窗"
        lines.append(f"{wname}：{rd.window_text(w, base)}" + ("（已限制在數據範圍內）" if w.get("clamped") else "")
                     + "；[+秒] 是距離數據開頭的時間")
        if not times:
            carry = (rd.carry_in_values(src["mcap_files"], entry["topic"], entry["type"], keys, w["start_ns"])
                     if w["start_ns"] > idx["start_ns"] else {})
            held = [(k, lab, t, v) for k in keys for lab, (t, v) in carry.get(k, {}).items()]
            if held:   # 只在狀態改變時才發布的 Topic：沒有新訊息＝狀態沒變，照之前的最後一則
                t_last = held[0][2]
                lines.append(f"  時間窗內沒有新訊息；最後一則在 {rd.fmt_t(t_last)}[{rd.fmt_rel(t_last, rel_base)}]"
                             "（只在狀態改變時才發布的 Topic，這段期間的狀態就是那一則的值）：")
                for k, lab, t, v in held[:12]:
                    lines.append(f"     {rd.entry_name(k, lab, rd.find_key(entry, k))} = {rd.short(rd.state_text(v), 80)}")
                all_flags.append(f"{wname} 沒有新訊息（最後一則在 {rd.fmt_rel(t_last, rel_base)}）")
            else:
                lines.append("  時間窗內沒有這個 Topic 的訊息（Topic 沒有在發布，或時間窗不在數據範圍內）")
                all_flags.append(f"{wname} 沒有訊息")
            results.append({"window": rd.jsonable(w), "rate": rate, "keys": {}})
            continue
        first, last = rd.fmt_rel(times[0], rel_base), rd.fmt_rel(times[-1], rel_base)
        r = f"  訊息 {rate['messages']} 筆（第一筆 {first}、最後一筆 {last}）；發布方式：{rd.pattern_text(rate)}"
        if rate.get("avg_hz"):
            r += f"，平均 {rate['avg_hz']} Hz，最大間隔 {rate['max_gap_sec']} 秒"
        if rate.get("gaps"):
            r += "；中斷 " + "、".join(f"{rd.fmt_t(int(g['start_sec'] * 1e9))}[{rd.fmt_rel(int(g['start_sec'] * 1e9), rel_base)}] 起 "
                                     f"{g['duration_sec']} 秒" for g in rate["gaps"][:6])
            if rate["gap_count"] > 6:
                r += f"…共 {rate['gap_count']} 次"
            all_flags.append(f"{wname} 訊息中斷 {rate['gap_count']} 次（最長 {max(g['duration_sec'] for g in rate['gaps'])} 秒）")
            anomalies.append(all_flags[-1])
        if rate.get("single_session"):   # 一段連續的發布寫成一句（分開寫，模型會讀成「間歇性」）；寫明是完整的發布（實測會被說成「指令中斷」）
            span = (times[-1] - times[0]) / 1e9
            r += (f"；只在 {first}～{last} 連續發布 {span:.2f} 秒（一段完整的發布，中間沒有中斷；之前 {rate['starts_after_window_sec']} 秒、"
                  f"之後 {rate['ends_before_window_sec']} 秒都沒有訊息）")
            all_flags.append(f"{wname} 只在 {first}～{last} 連續發布 {span:.1f} 秒（一段完整的發布，中間沒有中斷，之前與之後都沒有訊息）")
        elif rate.get("started_late"):
            r += f"；{first} 才開始發布（時間窗開始後 {rate['starts_after_window_sec']} 秒）"
            all_flags.append(f"{wname} {first} 才開始發布（時間窗開始後 {rate['starts_after_window_sec']} 秒沒有訊息）")
        elif rate.get("warmup_start"):
            r += f"；錄製開始後 {rate['starts_after_window_sec']} 秒才有第一筆（錄製工具訂閱的延遲或節點剛啟動，不算中途才開始）"
        elif rate.get("starts_after_window_sec", 0) > 1.0:
            r += f"；時間窗開始後 {rate['starts_after_window_sec']} 秒才有第一筆"
        if rate.get("stopped_early") and not rate.get("single_session"):
            r += f"；{last} 之後停止發布（到時間窗結束 {rate['ends_before_window_sec']} 秒沒有訊息）"
            all_flags.append(f"{wname} {last} 之後停止發布（到時間窗結束 {rate['ends_before_window_sec']} 秒沒有訊息）")
        if rate.get("pattern") != "periodic":
            r += "；不是固定頻率：不判斷中斷與開始／停止發布（隔很久沒有訊息不代表中斷）"
            if rate.get("times_sec"):
                r += "；每一則：" + "、".join(rd.fmt_rel(int(x * 1e9), rel_base) for x in rate["times_sec"])
        lines.append(r)
        # 狀態沿用時間窗開始前的最後一則（只在改變時才發布的 Topic）；時間窗從數據開頭起算就沒有「之前」
        carry = (rd.carry_in_values(src["mcap_files"], entry["topic"], entry["type"], keys, w["start_ns"])
                 if w["start_ns"] > idx["start_ns"] else {})
        wkeys = {}
        for k, d in zip(keys, descs):
            entries = series[k]
            is_map = bool(d.get("map_by")) or d["category"] == "kv"
            if args.filter and is_map:   # --filter 只篩「依名稱展開」的項目；一般的 Key 照常量（實測 worker 對一般 Key 也加 --filter）
                entries = {lab: pts for lab, pts in entries.items() if args.filter.lower() in lab.lower()}
            feats, flags = rd.measure_key(entries, d, w, k, carry=carry.get(k))
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
                        "map_by": d.get("map_by"), "entries": {lab: rd.trim_changes(f) for lab, f in feats.items()}, "flags": flags}
        wconds = []
        for c in conds:
            res = rd.where_on_series(c, keys, descs, series, w["end_ns"], rel_base)
            lines.append("  ▸ " + res["line"])
            wconds.append(res)
        results.append({"window": w, "rate": rate, "keys": wkeys, "errors": errors, "source": src["bag_dir"],
                        **({"where": wconds} if wconds else {})})
    if skipped:
        lines.append("沒有量測：" + "；".join(skipped) + (f"（可以量測的 Key：{avail}）" if unknown else ""))
    # 異常與變化分開寫：開始／停止發布、一段完整的發布、狀態跳轉、尖峰都是量到的變化，不代表異常。舊版全部列在「異常指標」底下，
    # 實測 26b 的 worker 把 /cmd_vel_raw 一次完整的指令標成異常 40/40、寫成「中斷」32/40（工具量到的是中間沒有中斷）
    changes = [f for f in all_flags if f not in anomalies]
    lines.append("程式判斷的異常（訊息中斷）：" + ("；".join(anomalies) if anomalies else "沒有"))
    lines.append("量到的變化（事實，不代表異常）：" + ("；".join(changes) if changes else "沒有尖峰、沒有狀態跳轉、沒有中途開始或停止發布"))
    if args.json:
        print(json.dumps(rd.jsonable({"data": idx["label"], "topic": entry["topic"], "type": entry["type"],
                                      "data_start_ns": idx["start_ns"], "windows": results, "flags": all_flags, "anomalies": anomalies,
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
    err = rd.not_recording(args.data or args.data_opt, "mcap_feature_measure")   # 主機上的一般檔案：先指到對的技能，不要先叫人開容器
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
    for k in args.key:
        wargs += ["--key", k]
    for w in args.window:
        wargs += ["--window", w]
    for c in args.where:
        wargs += ["--where", c]
    if args.around:
        wargs += ["--around", args.around, "--before", str(args.before), "--after", str(args.after)]
    if args.filter:
        wargs += ["--filter", args.filter]
    wargs += [f for f, on in (("--all-entries", args.all_entries), ("--json", args.json)) if on]
    rc, out = rd.run_in_container(os.path.abspath(__file__), wargs, container=container, timeout=timeout,
                                  what="mcap_feature_measure（特徵量測）",
                                  timeout_hint="時間窗很長、訊息很多時，縮短時間窗或少量測幾個 Key。")
    print(rd.finalize_output(out, cli.ignored_note()))
    return rc


if __name__ == "__main__":
    if rd.in_worker():
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
