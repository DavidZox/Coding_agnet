
#!/usr/bin/env python3
"""Host-side entry point; inspect and deserialize MCAP inside the ROS 2 container."""

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
    import json
    from collections import Counter
    import yaml
    from mcap.reader import make_reader

    p = argparse.ArgumentParser(description="Inspect MCAP data using ROS 2 message types.")
    p.add_argument("--input", required=True, help="An .mcap file or directory containing one")
    p.add_argument("--topic", help="Topic to inspect")
    p.add_argument("--field", help="Field path, e.g. pose.position.x")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--list-topics", action="store_true")
    p.add_argument("--list-fields", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.limit < 1 or args.offset < 0:
        p.error("--limit must be >= 1 and --offset must be >= 0")

    path = Path(args.input).expanduser()
    if path.is_dir():
        candidates = sorted(path.rglob("*.mcap"))
        if len(candidates) != 1:
            print(
                f"[ERROR] Expected exactly one .mcap under {path}; found "
                f"{len(candidates)}. Pass --input with an explicit file path."
            )
            return 2
        path = candidates[0]
    if not path.is_file() or path.suffix.lower() != ".mcap":
        print(f"[ERROR] Input is not an existing .mcap file: {path}")
        return 2

    try:
        with path.open("rb") as stream:
            reader = make_reader(stream)
            summary = Counter()
            channel_types = {}
            schema_names = {}
            for schema, channel, message in reader.iter_messages():
                summary[channel.topic] += 1
                channel_types[channel.topic] = channel.message_encoding
                if schema is not None:
                    schema_names[channel.topic] = schema.name

        if args.list_topics or (not args.topic and not args.field):
            result = {
                "input": str(path),
                "total_messages": sum(summary.values()),
                "topics": [
                    {
                        "topic": topic,
                        "message_count": count,
                        "message_encoding": channel_types.get(topic),
                        "schema": schema_names.get(topic),
                    }
                    for topic, count in sorted(summary.items())
                ],
            }
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else
                  "\n".join(
                      [f"MCAP: {path}", f"Total messages: {sum(summary.values())}",
                       f"Topics: {len(summary)}"] +
                      [f"{x['topic']}: {x['message_count']} messages "
                       f"(schema={x['schema'] or 'unknown'})" for x in result["topics"]]
                  ))
            return 0

        if not args.topic:
            p.error("--topic is required when using --field or --list-fields")

        # Find a schema for the selected topic.
        selected_schema = None
        with path.open("rb") as stream:
            reader = make_reader(stream)
            for schema, channel, _ in reader.iter_messages(topics=[args.topic]):
                if schema is not None:
                    selected_schema = schema
                    break
        if selected_schema is None:
            print(f"[ERROR] No message/schema found for topic: {args.topic}")
            return 3

        try:
            from rosidl_runtime_py.utilities import get_message
            import rclpy.serialization
            msg_class = get_message(selected_schema.name)
        except Exception as exc:
            print(
                f"[ERROR] Cannot load ROS 2 message type {selected_schema.name!r}: "
                f"{type(exc).__name__}: {exc}"
            )
            return 4

        # Determine available field names from the ROS message class, not raw __slots__.
        try:
            prototype = msg_class()
            if hasattr(prototype, "get_fields_and_field_types"):
                field_names = list(prototype.get_fields_and_field_types().keys())
            else:
                field_names = [
                    name.lstrip("_") for name in getattr(prototype, "__slots__", [])
                ]
        except Exception:
            field_names = []

        if args.list_fields:
            result = {
                "topic": args.topic,
                "schema": selected_schema.name,
                "available_fields": field_names,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else
                  "\n".join(
                      [f"Topic: {args.topic}", f"Schema: {selected_schema.name}",
                       f"Fields ({len(field_names)}):"] +
                      [f"- {name}" for name in field_names]
                  ))
            return 0

        if not args.field:
            p.error("provide --field or --list-fields")

        def get_path(obj, field_path):
            current = obj
            for part in field_path.split("."):
                if not part or part.startswith("_"):
                    raise ValueError(f"invalid field component: {part!r}")
                if isinstance(current, dict):
                    if part not in current:
                        raise AttributeError(f"no key {part!r}")
                    current = current[part]
                elif isinstance(current, (list, tuple)):
                    current = current[int(part)]
                else:
                    if not hasattr(current, part):
                        raise AttributeError(
                            f"{type(current).__name__} has no field {part!r}"
                        )
                    current = getattr(current, part)
            return current

        values = []
        failures = Counter()
        seen = 0
        with path.open("rb") as stream:
            reader = make_reader(stream)
            for schema, channel, message in reader.iter_messages(topics=[args.topic]):
                if seen < args.offset:
                    seen += 1
                    continue
                if len(values) >= args.limit:
                    break
                try:
                    ros_msg = rclpy.serialization.deserialize_message(
                        message.data, msg_class
                    )
                    value = get_path(ros_msg, args.field)
                    values.append({
                        "log_time_ns": message.log_time,
                        "publish_time_ns": message.publish_time,
                        "sequence": message.sequence,
                        "value": value,
                    })
                except Exception as exc:
                    failures[f"{type(exc).__name__}: {exc}"] += 1
                seen += 1

        result = {
            "input": str(path),
            "topic": args.topic,
            "schema": selected_schema.name,
            "field": args.field,
            "offset": args.offset,
            "returned": len(values),
            "failures": sum(failures.values()),
            "failure_reasons": dict(failures),
            "timestamp_basis": "MCAP log_time/publish_time nanoseconds",
            "values": values,
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(
                f"Topic: {args.topic}\nSchema: {selected_schema.name}\n"
                f"Field: {args.field}\nReturned: {len(values)}\n"
                f"Failures: {sum(failures.values())}"
            )
            for item in values:
                print(
                    f"log_time_ns={item['log_time_ns']} "
                    f"publish_time_ns={item['publish_time_ns']} "
                    f"value={item['value']}"
                )
            for reason, count in failures.most_common():
                print(f"[WARN] {count} failures: {reason}")
        return 0
    except Exception as exc:
        print(f"[ERROR] MCAP analysis failed: {type(exc).__name__}: {exc}")
        return 1


def host_main(argv):
    p = argparse.ArgumentParser(
        description="Run MCAP analysis inside a Docker container."
    )
    p.add_argument("--container")
    p.add_argument("--timeout", default=str(DEFAULT_TIMEOUT))
    p.add_argument("--input", required=True, help="Container path to .mcap or directory")
    p.add_argument("--topic")
    p.add_argument("--field")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--list-topics", action="store_true")
    p.add_argument("--list-fields", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.limit < 1 or args.offset < 0:
        p.error("--limit must be >= 1 and --offset must be >= 0")
    timeout, error = parse_timeout(args.timeout, DEFAULT_TIMEOUT, MAX_TIMEOUT)
    if error:
        print(error)
        return 2
    container, error = resolve_container(args.container)
    if error:
        print(error)
        return 2

    source = base64.b64encode(Path(__file__).read_bytes()).decode("ascii")
    remote = f"/tmp/mcap_analyzer_{uuid.uuid4().hex}.py"
    worker_args = ["--input", args.input, "--limit", str(args.limit),
                   "--offset", str(args.offset)]
    if args.topic:
        worker_args += ["--topic", args.topic]
    if args.field:
        worker_args += ["--field", args.field]
    if args.list_topics:
        worker_args.append("--list-topics")
    if args.list_fields:
        worker_args.append("--list-fields")
    if args.json:
        worker_args.append("--json")

    command = (
        f"printf %s {shlex.quote(source)} | base64 -d > {shlex.quote(remote)}"
        f" && ROS2_TOOL_WORKER=1 python3 {shlex.quote(remote)} {shlex.join(worker_args)}"
        f"; rc=$?; rm -f {shlex.quote(remote)}; exit $rc"
    )
    ok, stdout, error_message = docker_exec(
        container, ROS2_ENV_FALLBACK + command, timeout,
        interactive=True, what="ROS 2 MCAP analyzer",
        timeout_hint="請確認容器已載入自訂 ROS 2 message package，且輸入路徑存在於容器內。",
    )
    if not ok:
        print(error_message)
        if stdout.strip():
            print(stdout.rstrip())
        return 1
    print(with_target_marker(stdout.strip() or "[PASS] Analyzer completed.", container))
    return 0


if __name__ == "__main__":
    if os.environ.get("ROS2_TOOL_WORKER") == "1":
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
