
#!/usr/bin/env python3
"""Host-side entry point; parse ROS 2 log files inside the selected container."""

import argparse
import base64
import json
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
    import re
    from collections import Counter

    p = argparse.ArgumentParser(description="Parse a rosout.log file.")
    p.add_argument("input", help="rosout.log file or directory containing it")
    p.add_argument("--level", action="append",
                   choices=["DEBUG", "INFO", "WARN", "ERROR", "FATAL"])
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.limit < 1:
        p.error("--limit must be >= 1")

    path = Path(args.input).expanduser()
    if path.is_dir():
        path = path / "rosout.log"
    if not path.is_file():
        print(f"[ERROR] rosout file not found: {path}")
        return 2

    # Support ROS console output and common ros2 topic echo representations.
    patterns = [
        re.compile(
            r"(?P<stamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
            r"(?:[.,]\d+)?)\s+"
            r"(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s*"
            r"(?P<message>.*)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<key>level)\s*:\s*(?P<level>\d+).*?"
            r"(?P<message>(?:msg|message)\s*:\s*.*)",
            re.IGNORECASE,
        ),
    ]
    level_map = {
        "0": "UNSET", "10": "DEBUG", "20": "INFO",
        "30": "WARN", "40": "ERROR", "50": "FATAL",
        "WARNING": "WARN",
    }

    events = []
    unparsed = 0
    counts = Counter()
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_no, raw in enumerate(stream, 1):
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            match = patterns[0].search(line)
            if match:
                level = match.group("level").upper()
                level = level_map.get(level, level)
                event = {
                    "event_id": line_no,
                    "source_line": line_no,
                    "timestamp_text": match.group("stamp"),
                    "timestamp_basis": "text_from_log; clock basis not inferred",
                    "level": level,
                    "message": match.group("message").strip(),
                    "raw": line,
                }
            else:
                # For YAML-like ros2 topic echo output, retain the block as raw text.
                if re.search(r"^\s*(level|stamp|msg|name)\s*:", line):
                    event = {
                        "event_id": line_no,
                        "source_line": line_no,
                        "timestamp_text": None,
                        "timestamp_basis": None,
                        "level": "UNKNOWN",
                        "message": line.strip(),
                        "raw": line,
                    }
                else:
                    unparsed += 1
                    continue
            counts[event["level"]] += 1
            events.append(event)

    selected_levels = {x.upper() for x in args.level} if args.level else None
    selected = [
        e for e in events
        if selected_levels is None or e["level"] in selected_levels
    ]
    report = {
        "source": str(path),
        "total_parsed_events": len(events),
        "unparsed_nonempty_lines": unparsed,
        "level_counts": dict(sorted(counts.items())),
        "returned_events": min(len(selected), args.limit),
        "events": selected[:args.limit],
        "note": (
            "event_id is the 1-based source line number. Timestamp strings are "
            "preserved as written; no clock alignment with MCAP log_time is assumed."
        ),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Source: {path}")
        print(f"Parsed events: {len(events)}")
        print(f"Unparsed non-empty lines: {unparsed}")
        print("Levels:")
        for level, count in sorted(counts.items()):
            print(f"  {level}: {count}")
        print(f"Events shown: {min(len(selected), args.limit)}")
        for event in selected[:args.limit]:
            print(
                f"[event_id={event['event_id']}] "
                f"[{event['timestamp_text'] or 'no timestamp'}] "
                f"[{event['level']}] {event['message']}"
            )
    return 0


def host_main(argv):
    p = argparse.ArgumentParser(
        description="Run rosout parser inside a Docker container."
    )
    p.add_argument("--container")
    p.add_argument("--timeout", default=str(DEFAULT_TIMEOUT))
    p.add_argument("--level", action="append",
                   choices=["DEBUG", "INFO", "WARN", "ERROR", "FATAL"])
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--json", action="store_true")
    p.add_argument("input", help="Container path to rosout.log or its directory")
    args = p.parse_args(argv)

    if args.limit < 1:
        p.error("--limit must be >= 1")
    timeout, error = parse_timeout(args.timeout, DEFAULT_TIMEOUT, MAX_TIMEOUT)
    if error:
        print(error)
        return 2
    container, error = resolve_container(args.container)
    if error:
        print(error)
        return 2

    source = base64.b64encode(Path(__file__).read_bytes()).decode("ascii")
    remote = f"/tmp/rosout_parser_{uuid.uuid4().hex}.py"
    worker_args = [args.input, "--limit", str(args.limit)]
    for level in args.level or []:
        worker_args += ["--level", level]
    if args.json:
        worker_args.append("--json")

    command = (
        f"printf %s {shlex.quote(source)} | base64 -d > {shlex.quote(remote)}"
        f" && ROS2_TOOL_WORKER=1 python3 {shlex.quote(remote)} {shlex.join(worker_args)}"
        f"; rc=$?; rm -f {shlex.quote(remote)}; exit $rc"
    )
    ok, stdout, error_message = docker_exec(
        container, ROS2_ENV_FALLBACK + command, timeout,
        interactive=True, what="ROS 2 rosout parser",
    )
    if not ok:
        print(error_message)
        if stdout.strip():
            print(stdout.rstrip())
        return 1
    print(with_target_marker(stdout.strip() or "[PASS] No parser output.", container))
    return 0


if __name__ == "__main__":
    if os.environ.get("ROS2_TOOL_WORKER") == "1":
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
