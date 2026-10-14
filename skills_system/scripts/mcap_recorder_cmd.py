
#!/usr/bin/env python3
"""Host-side entry point; execute ROS 2 recording inside the selected container."""

import argparse
import base64
import os
import shlex
import sys
import uuid
from pathlib import Path

if os.environ.get("ROS2_TOOL_WORKER") != "1":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _docker_common import (
        docker_exec,
        parse_timeout,
        resolve_container,
        with_target_marker,
        ROS2_ENV_FALLBACK,
    )

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 570


def worker_main(argv):
    """Runs only inside the ROS 2 container."""
    import json
    import subprocess
    import time
    from datetime import datetime, timezone

    p = argparse.ArgumentParser(
        description="Record ROS 2 topics and capture /rosout."
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--topics", nargs="+", help="Topics to record")
    mode.add_argument("--all", action="store_true", help="Record all topics")
    p.add_argument("--duration", type=float, required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--rosout", action="store_true",
                   help="Capture /rosout to a separate text file")
    args = p.parse_args(argv)

    if args.duration <= 0:
        p.error("--duration must be greater than zero")

    out_dir = Path(args.output_dir).expanduser()
    if out_dir.exists() and any(out_dir.iterdir()):
        p.error(f"output directory is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bag_dir = out_dir / f"bag_{stamp}"
    bag_dir.mkdir()

    topics = args.topics or []
    if topics:
        for topic in topics:
            if not topic.startswith("/"):
                p.error(f"topic must be absolute, got: {topic}")

    command = ["ros2", "bag", "record", "-o", str(bag_dir)]
    if args.all:
        command.append("-a")
    else:
        command.extend(topics)

    rosout_file = None
    rosout_proc = None
    if args.rosout:
        rosout_file = open(out_dir / "rosout.log", "w", encoding="utf-8")
        rosout_proc = subprocess.Popen(
            ["ros2", "topic", "echo", "/rosout"],
            stdout=rosout_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    terminal_path = out_dir / "terminal.log"
    started = time.monotonic()
    try:
        with open(terminal_path, "w", encoding="utf-8") as log:
            log.write("Command: " + shlex.join(command) + "\n")
            log.flush()
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            try:
                while True:
                    line = proc.stdout.readline()
                    if line:
                        print(line, end="", flush=True)
                        log.write(line)
                        log.flush()
                    elif proc.poll() is not None:
                        break
                    if time.monotonic() - started >= args.duration:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        break
                rc = proc.wait()
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()

        if rosout_proc is not None:
            rosout_proc.terminate()
            try:
                rosout_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                rosout_proc.kill()
                rosout_proc.wait()
        if rosout_file is not None:
            rosout_file.close()

        mcap_files = sorted(str(x) for x in bag_dir.rglob("*.mcap"))
        if not mcap_files:
            print("[ERROR] ros2 bag record ended without producing an MCAP file.")
            return 2

        metadata = {
            "created_utc": stamp,
            "duration_requested_seconds": args.duration,
            "duration_elapsed_seconds": round(time.monotonic() - started, 3),
            "topics": topics if topics else ["<all>"],
            "rosout_captured": bool(args.rosout),
            "record_command": command,
            "mcap_files": mcap_files,
            "recorder_exit_code": rc,
        }
        (out_dir / "recording_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[PASS] Recording output: {out_dir}")
        print(f"MCAP files: {len(mcap_files)}")
        print(f"Metadata: {out_dir / 'recording_metadata.json'}")
        return 0
    except KeyboardInterrupt:
        print("[ERROR] Recording interrupted.")
        return 130
    finally:
        if rosout_proc is not None and rosout_proc.poll() is None:
            rosout_proc.kill()
        if rosout_file is not None and not rosout_file.closed:
            rosout_file.close()


def host_main(argv):
    parser = argparse.ArgumentParser(
        description="Run the ROS 2 MCAP recorder inside a Docker container."
    )
    parser.add_argument("--container", help="Container name; defaults to current target")
    parser.add_argument("--timeout", default=str(DEFAULT_TIMEOUT),
                        help=f"Host tool timeout in seconds (1-{MAX_TIMEOUT})")
    parser.add_argument("--topics", nargs="+")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--output-dir", required=True,
                        help="Output path inside the container")
    parser.add_argument("--rosout", action="store_true")
    args = parser.parse_args(argv)

    if bool(args.topics) == bool(args.all):
        parser.error("specify exactly one of --topics or --all")
    if args.topics and any(not t.startswith("/") for t in args.topics):
        parser.error("every topic must start with '/'")
    if args.duration <= 0:
        parser.error("--duration must be greater than zero")

    timeout, error = parse_timeout(args.timeout, DEFAULT_TIMEOUT, MAX_TIMEOUT)
    if error:
        print(error)
        return 2
    container, error = resolve_container(args.container)
    if error:
        print(error)
        return 2

    # Transfer this same file into the container, then re-execute worker_main there.
    source = Path(__file__).read_bytes()
    payload = base64.b64encode(source).decode("ascii")
    remote = f"/tmp/mcap_recorder_{uuid.uuid4().hex}.py"
    worker_args = []
    if args.topics:
        worker_args += ["--topics", *args.topics]
    else:
        worker_args.append("--all")
    worker_args += [
        "--duration", str(args.duration),
        "--output-dir", args.output_dir,
    ]
    if args.rosout:
        worker_args.append("--rosout")

    command = (
        f"printf %s {shlex.quote(payload)} | base64 -d > {shlex.quote(remote)}"
        f" && ROS2_TOOL_WORKER=1 python3 {shlex.quote(remote)} "
        f"{shlex.join(worker_args)}; rc=$?; rm -f {shlex.quote(remote)}; exit $rc"
    )
    ok, stdout, error_message = docker_exec(
        container,
        ROS2_ENV_FALLBACK + command,
        timeout,
        interactive=True,
        what="ROS 2 MCAP recorder",
        timeout_hint="請確認錄製時長與工具逾時設定相容。",
    )
    if not ok:
        print(error_message)
        if stdout.strip():
            print(stdout.rstrip())
        return 1
    output = stdout.strip() or "[PASS] Recorder completed with no output."
    print(with_target_marker(output, container))
    return 0


if __name__ == "__main__":
    if os.environ.get("ROS2_TOOL_WORKER") == "1":
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
