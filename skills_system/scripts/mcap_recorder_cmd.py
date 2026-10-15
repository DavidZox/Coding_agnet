#!/usr/bin/env python3
"""mcap_recorder：在目標容器內錄製 ROS 2 Topic，產生跟 diagnostics_package/toolkit 相同的實驗資料夾，並在錄完時建立全域 Topic
Metadata 索引（之後的分析直接用，不用再掃一次）。

<數據根目錄>/exp_YYYYmmdd_HHMMSS/
├── bag/                 ros2 bag record -s mcap 的輸出（*.mcap、metadata.yaml）＋ topic_metadata.json／.yaml（本工具建立的索引）
├── rosout.log           ros2 topic echo /rosout 經 rosout_formatter.py 整理成一行一則（[LEVEL] [sec.nanosec] [node]: msg）
├── terminal.log         錄製程序的終端輸出
└── recording_info.json  錄製參數、時間、Topic 與檔案清單

移植自 toolkit 的 mcap_recorder.py 與 ros2_toolkit.sh 的錄製流程（預設核心 Topic 組合、同步錄 /rosout、SIGINT 安全停止並封裝），
改成非互動、一定要指定時長（agent 不能靠 Ctrl+C 停）。"""
import glob
import json
import os
import shlex
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ros2_data_common as rd  # noqa: E402

MAX_DURATION = 480
MAX_TIMEOUT = 570
USAGE = ("scripts/mcap_recorder_cmd.py (--topics TOPIC... | --preset core | --all) --duration 秒 [--out-root 數據根目錄] "
         "[--name 實驗名稱] [--no-rosout] [--no-index] [--container 名稱] [--timeout 秒]")


def build_parser():
    return (rd.CliParser(USAGE)
            .add("--topics", nargs="+", default=[])
            .add("--preset", default="", choices=["", "core"])
            .add("--all", action="store_true")
            .add("--duration", type=float, default=0)
            .add("--out-root", default="")
            .add("--data-root", default="")
            .add("--name", default="")
            .add("--no-rosout", action="store_true")
            .add("--no-index", action="store_true")
            .add("--container", default="")
            .add("--timeout", default=""))


def _stop_group(proc, first=signal.SIGINT, wait=20):
    """同 toolkit 的 stop_recording：先 SIGINT（rosbag2 收到會把快取寫完、封裝 mcap），等不到再 SIGTERM，最後才 SIGKILL。"""
    if proc is None or proc.poll() is not None:
        return
    for sig, w in ((first, wait), (signal.SIGTERM, 5), (signal.SIGKILL, 3)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=w)
            return
        except subprocess.TimeoutExpired:
            continue


def worker_main(argv):
    args = build_parser().parse(argv)
    modes = sum(bool(x) for x in (args.topics, args.preset, args.all))
    if modes != 1:
        print(f"[ERROR] --topics、--preset core、--all 三選一。\n用法：{USAGE}")
        return 2
    if not 0 < args.duration <= MAX_DURATION:
        print(f"[ERROR] --duration 要介於 0～{MAX_DURATION} 秒（agent 沒辦法手動按 Ctrl+C 停止，一定要定時）")
        return 2
    topics = rd.CORE_TOPICS[:] if args.preset == "core" else [t if t.startswith("/") else "/" + t for t in args.topics]
    root = args.out_root or args.data_root or rd.autodetect_data_root()
    if not root:
        print("[ERROR] 不知道要錄到哪裡：用 --out-root 指定數據根目錄（容器內路徑，建議放在已掛載到主機的資料夾，例如 "
              "…/toolkit/experiment_logs）。")
        return 2
    name = args.name or "exp_" + time.strftime("%Y%m%d_%H%M%S")
    target = os.path.join(root, name)
    if os.path.exists(target):
        print(f"[ERROR] {target} 已經存在，不覆寫；換一個 --name")
        return 2
    os.makedirs(target)
    bag_dir = os.path.join(target, "bag")
    record_topics = [] if args.all else list(dict.fromkeys(topics + ([] if args.no_rosout else ["/rosout", "/rosout_agg"])))

    try:
        live = subprocess.run(["ros2", "topic", "list"], capture_output=True, text=True, timeout=20).stdout.split()
    except Exception:   # noqa: BLE001
        live = []
    missing = [t for t in record_topics if live and t not in live and t != "/rosout_agg"]

    rosout_proc = None
    if not args.no_rosout:
        fmt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rosout_formatter.py")
        pipe = (f"ros2 topic echo /rosout 2>/dev/null | python3 -u {shlex.quote(fmt)} > {shlex.quote(os.path.join(target, 'rosout.log'))}"
                if os.path.exists(fmt) else f"ros2 topic echo /rosout > {shlex.quote(os.path.join(target, 'rosout.log'))} 2>/dev/null")
        rosout_proc = subprocess.Popen(["bash", "-c", pipe], start_new_session=True)
    cmd = ["ros2", "bag", "record", "-s", "mcap", "-o", bag_dir] + (["-a"] if args.all else record_topics)
    started = time.time()
    with open(os.path.join(target, "terminal.log"), "w", encoding="utf-8") as term:
        term.write("Command: " + shlex.join(cmd) + "\n")
        term.flush()
        rec = subprocess.Popen(cmd, stdout=term, stderr=subprocess.STDOUT, start_new_session=True)
        t0 = time.monotonic()
        while time.monotonic() - t0 < args.duration and rec.poll() is None:
            time.sleep(0.2)
        early = rec.poll() is not None
        _stop_group(rec)
    _stop_group(rosout_proc, first=signal.SIGINT, wait=5)
    elapsed = round(time.time() - started, 2)
    mcaps = sorted(glob.glob(os.path.join(bag_dir, "*.mcap")))
    with open(os.path.join(target, "terminal.log"), encoding="utf-8", errors="replace") as f:
        term_tail = "".join(f.readlines()[-15:])
    if not mcaps:
        print(f"[ERROR] ros2 bag record 沒有產生 .mcap（{'錄製程序提早結束' if early else '停止後沒有檔案'}）。"
              f"terminal.log 最後幾行：\n{term_tail}")
        return 3
    info = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "duration_requested_sec": args.duration,
            "duration_elapsed_sec": elapsed, "topics": ["<all>"] if args.all else record_topics,
            "preset": args.preset or None, "rosout_log": not args.no_rosout, "record_command": cmd,
            "mcap_files": mcaps, "recorder_exited_early": early, "missing_at_start": missing}
    with open(os.path.join(target, "recording_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    lines = [f"[PASS] 錄製完成：{name}（要求 {args.duration:g} 秒，實際 {elapsed} 秒）" + ("；⚠️ 錄製程序提早結束" if early else ""),
             f"資料夾：{target}（bag/ {len(mcaps)} 個 mcap、terminal.log"
             + ("、rosout.log" if not args.no_rosout else "") + "）"]
    if not args.no_rosout:
        try:
            with open(os.path.join(target, "rosout.log"), encoding="utf-8", errors="replace") as f:
                n = sum(1 for ln in f if ln.startswith("["))
            lines[-1] += f"；rosout.log {n} 則 Log"
        except OSError:
            pass
    data, err = rd.resolve_data(target)
    if data and not args.no_index:
        idx = rd.build_index(data, refresh=True)
        got = [f"{t['topic']} {t['message_count']}" for t in idx["topics"] if t["message_count"]]
        recorded = {t["topic"] for t in idx["topics"] if t["message_count"]}
        none = [t for t in (record_topics or [t["topic"] for t in idx["topics"]]) if t not in recorded]
        lines.append(f"錄到的 Topic（則數）：{'、'.join(got) or '（沒有）'}")
        if none:
            lines.append(f"沒有錄到訊息：{'、'.join(none)}（錄製期間沒有 publisher）")
        lines.append(f"全域 Topic Metadata 索引：{idx.get('index_file') or '（沒有寫入權限）'}（worker 可分析 "
                     f"{sum(1 for t in idx['topics'] if t['role'] == 'worker')} 個 Topic；mcap_analyzer 直接讀）")
    print("\n".join(lines) + (rd.marker_line(data) if data else ""))
    return 0


def host_main(argv):
    args = build_parser().parse(argv)
    sys.path.insert(0, rd.HERE)
    from _docker_common import parse_timeout, resolve_container
    if not 0 < args.duration <= MAX_DURATION:
        print(f"[ERROR] --duration 要介於 0～{MAX_DURATION} 秒（一定要定時）。\n用法：{USAGE}")
        return 2
    default_timeout = min(MAX_TIMEOUT, int(args.duration) + 90)
    timeout, err = parse_timeout(args.timeout or str(default_timeout), default_timeout, MAX_TIMEOUT)
    if err:
        print(err)
        return 2
    if timeout < args.duration + 30:
        print(f"[ERROR] --timeout {timeout} 秒太短：至少要錄製時長加 30 秒（停止、封裝與建立索引）")
        return 2
    container, err = resolve_container(args.container)
    if err:
        print(err)
        return 2
    mounts = rd.container_mounts(container)
    wargs = []
    root = (os.environ.get("ANALYSIS_DATA_ROOT") or "").strip()   # harness 設定的數據根目錄（/analysis_root）
    if root:
        wargs += ["--data-root", rd.to_container_path(root, mounts)]
    if args.topics:
        wargs += ["--topics", *args.topics]
    if args.preset:
        wargs += ["--preset", args.preset]
    if args.all:
        wargs.append("--all")
    wargs += ["--duration", str(args.duration)]
    if args.out_root:
        wargs += ["--out-root", rd.to_container_path(args.out_root, mounts)]
    if args.name:
        wargs += ["--name", args.name]
    wargs += [f for f, on in (("--no-rosout", args.no_rosout), ("--no-index", args.no_index)) if on]
    rc, out = rd.run_in_container(os.path.abspath(__file__), wargs, container=container, timeout=timeout,
                                  what="mcap_recorder（錄製）", extra_files=[os.path.join(rd.HERE, "rosout_formatter.py")],
                                  timeout_hint="確認錄製時長與 --timeout 相容；容器內的 ros2 bag record 可能仍在執行，請用 docker_runcmd 確認。")
    print(rd.finalize_output(out))
    return rc


if __name__ == "__main__":
    if rd.in_worker():
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
