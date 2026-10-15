#!/usr/bin/env python3
"""rosout_parser：Log 智慧過濾——解析 /rosout（bag 裡的 /rosout 或實驗資料夾的 rosout.log），把重複出現的 Log 合併成
「唯一訊號」（L1、L2…：層級、Node、次數、每一次的時間戳），給 Orchestrator 與使用者看全局。

移植自 diagnostics_package/toolkit 的 rosout_parser.py（層級檢視）與 mcap_slicer.py 步驟 3（字串去重、整合為單一訊號），
改成非互動：篩選用參數、編號依第一次出現的時間排序而且在篩選前就編好（mcap_slicer --signal 與 analysis_run 用同一份編號）。
主機端只負責把工作送進目標容器（_ros2_data_common.run_in_container），解析在容器內做。"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ros2_data_common as rd  # noqa: E402

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 570
USAGE = ("scripts/rosout_parser_cmd.py [數據] [--level 層級]... [--node 關鍵字] [--grep 關鍵字] [--top N] [--exact] "
         "[--events] [--all-nodes] [--source auto|bag|log] [--json] [--container 名稱] [--timeout 秒]")


def build_parser():
    return (rd.CliParser(USAGE)
            .add("data", nargs="?", default="")
            .add("--data", dest="data_opt", default="")
            .add("--data-root", default="")
            .add("--level", action="append", type=str.upper, choices=["DEBUG", "INFO", "WARN", "ERROR", "FATAL"])
            .add("--node", default="")
            .add("--grep", default="")
            .add("--top", type=int, default=60)
            .add("--exact", action="store_true")
            .add("--events", action="store_true")
            .add("--all-nodes", action="store_true")
            .add("--source", default="auto", choices=["auto", "bag", "log"])
            .add("--json", action="store_true")
            .add("--container", default="")
            .add("--timeout", default=str(DEFAULT_TIMEOUT)))


def _match(g, args):
    if not args.all_nodes and rd.is_recorder_node(g["node"]):
        return False
    if args.level and g["level"] not in args.level:
        return False
    if args.node and args.node.lower() not in g["node"].lower():
        return False
    if args.grep:
        try:
            return re.search(args.grep, g.get("message") or g.get("msg", ""), re.I) is not None
        except re.error:
            return args.grep.lower() in (g.get("message") or g.get("msg", "")).lower()
    return True


def worker_main(argv):
    args = build_parser().parse(argv)
    target = args.data or args.data_opt
    data = None
    if target.endswith(".log") and os.path.isfile(target):
        events, unparsed = rd.parse_rosout_file(target)
        source = f"{target}（時間＝Log 的 stamp）" + (f"；{unparsed} 行無法解析" if unparsed else "")
        data, _ = rd.resolve_data(os.path.dirname(target), args.data_root or None)
    else:
        data, err = rd.resolve_data(target, args.data_root or None)
        if err:
            print(f"[ERROR] {err}")
            return 2
        events, source, err = rd.load_log_events(data, args.source)
        if err:
            print(f"[ERROR] {err}")
            return 3
    ov = rd.bag_overview(data["mcap_files"]) if data else None
    base = ov["start_ns"] if ov and ov["start_ns"] is not None else (min(e["t_ns"] for e in events) if events else None)
    groups = rd.dedup_events(events, merge_numbers=not args.exact)
    levels = {}
    for e in events:
        levels[e["level"]] = levels.get(e["level"], 0) + 1
    level_text = "、".join(f"{lv} {levels[lv]}" for lv in sorted(levels, key=lambda x: rd.LEVEL_RANK.get(x, 1)))
    shown = [g for g in groups if _match(g, args)]
    top = max(1, args.top)

    if args.json:
        out = {"source": source, "data": rd.data_label(data) if data else None,
               "time_range_sec": [rd.sec(ov["start_ns"]), rd.sec(ov["end_ns"])] if ov else None,
               "total_events": len(events), "signals_total": len(groups), "level_counts": levels,
               "signals": [rd.signal_json(g, base) for g in shown[:top]]}
        if args.events:
            id_of = {}
            for g in groups:
                for t in g["times_ns"]:
                    id_of.setdefault((t, g["level"], g["node"]), g["id"])
            out["events"] = [{"signal": id_of.get((e["t_ns"], e["level"], e["node"])), "t_sec": rd.sec(e["t_ns"]),
                              "level": e["level"], "node": e["node"], "msg": e["msg"]}
                             for e in sorted(events, key=lambda x: x["t_ns"]) if _match(e, args)][:top]
        print(json.dumps(out, ensure_ascii=False, indent=1))
        if data:
            print(rd.marker_line(data).strip())
        return 0

    if not events:
        print(f"[PASS] 來源 {source} 沒有任何 Log。")
        return 0
    lines = [f"[PASS] Log 智慧過濾：{len(events)} 則 Log → {len(groups)} 個唯一訊號"
             + (f"（符合篩選 {len(shown)} 個）" if len(shown) != len(groups) else "") + f"；層級：{level_text}",
             f"來源：{source}"]
    if data and ov:
        lines.append(f"數據：{rd.data_label(data)}（{rd.fmt_t(ov['start_ns'])} ～ {rd.fmt_t(ov['end_ns'])}，"
                     f"{(ov['end_ns'] - ov['start_ns']) / 1e9:.1f} 秒）；[+秒] 是距離數據開頭的時間")
    lines.append("編號 L# 依第一次出現的時間排序（mcap_slicer --signal L# 依它切片）；×N 是出現次數，只差在數字的訊息算同一個訊號"
                 + ("（--exact：逐字比對）" if args.exact else ""))
    if args.events:
        id_of = {}
        for g in groups:
            for t in g["times_ns"]:
                id_of.setdefault((t, g["level"], g["node"]), g["id"])
        evs = [e for e in sorted(events, key=lambda x: x["t_ns"]) if _match(e, args)]
        for e in evs[:top]:
            lines.append(f"{id_of.get((e['t_ns'], e['level'], e['node']), '?'):<4} {e['level']:<5} "
                         f"{rd.fmt_t(e['t_ns'])}[{rd.fmt_rel(e['t_ns'], base)}] {e['node']}：{rd.short(e['msg'], 220)}")
        if len(evs) > top:
            lines.append(f"…還有 {len(evs) - top} 則（--top 調整）")
    else:
        for g in shown[:top]:
            when = f"{rd.fmt_t(g['first_ns'])}[{rd.fmt_rel(g['first_ns'], base)}]"
            if g["count"] > 1:
                when += f" ～ {rd.fmt_t(g['last_ns'])}[{rd.fmt_rel(g['last_ns'], base)}]"
            var = f"（{len(g['variants'])} 種寫法）" if len(g["variants"]) > 1 else ""
            lines.append(f"{g['id']:<4} {g['level']:<5} ×{g['count']:<4} {when}  {g['node']}：{rd.short(g['message'], 200)}{var}")
        if len(shown) > top:
            lines.append(f"…還有 {len(shown) - top} 個訊號（--top 調整，或用 --level／--node／--grep 篩選）")
        rec = 0 if args.all_nodes else sum(1 for g in groups if rd.is_recorder_node(g["node"]))
        hidden = len(groups) - len(shown) - rec
        if rec:
            lines.append(f"（略過錄製工具 rosbag2 自己的 Log {rec} 個訊號；--all-nodes 顯示）")
        if hidden > 0:
            lines.append(f"（另有 {hidden} 個訊號不符合篩選條件）")
    print("\n".join(lines) + (rd.marker_line(data) if data else ""))
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
    target = args.data or args.data_opt
    wargs = rd.host_common_args(container, target, mounts)
    for lv in args.level or []:
        wargs += ["--level", lv]
    for opt in ("node", "grep"):
        if getattr(args, opt):
            wargs += [f"--{opt}", getattr(args, opt)]
    wargs += ["--top", str(args.top), "--source", args.source]
    wargs += [f for f, on in (("--exact", args.exact), ("--events", args.events), ("--all-nodes", args.all_nodes),
                              ("--json", args.json)) if on]
    rc, out = rd.run_in_container(os.path.abspath(__file__), wargs, container=container, timeout=timeout,
                                  what="rosout_parser（Log 智慧過濾）",
                                  timeout_hint="Log 很多時可以先用 --level WARN、--node 縮小範圍。")
    print(rd.finalize_output(out) + cli.ignored_note())
    return rc


if __name__ == "__main__":
    if rd.in_worker():
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
