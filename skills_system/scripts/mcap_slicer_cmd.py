
#!/usr/bin/env python3
"""Host-side entry point; slice MCAP inside the selected ROS 2 container."""

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

DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 570


def worker_main(argv):
    import json
    import statistics
    import yaml
    from collections import Counter, defaultdict
    from mcap.reader import make_reader
    from mcap.writer import Writer

    p = argparse.ArgumentParser(description="Slice an MCAP around a verified timestamp.")
    p.add_argument("--input", required=True, help="Input .mcap path inside the container")
    p.add_argument("--output-dir", required=True, help="New output directory")
    p.add_argument("--timestamp-ns", required=True, type=int,
                   help="Verified timestamp in MCAP log_time nanoseconds")
    p.add_argument("--event-id", type=int,
                   help="Source rosout line number; stored for traceability")
    p.add_argument("--before", type=float, default=5.0,
                   help="Seconds before timestamp")
    p.add_argument("--after", type=float, default=5.0,
                   help="Seconds after timestamp")
    args = p.parse_args(argv)

    if args.timestamp_ns < 0:
        p.error("--timestamp-ns must be >= 0")
    if args.before < 0 or args.after < 0:
        p.error("--before and --after must be >= 0")

    input_path = Path(args.input).expanduser()
    out_dir = Path(args.output_dir).expanduser()
    if not input_path.is_file() or input_path.suffix.lower() != ".mcap":
        print(f"[ERROR] Input must be an existing .mcap file: {input_path}")
        return 2
    if out_dir.exists():
        print(f"[ERROR] Output path already exists; refusing to overwrite: {out_dir}")
        return 2
    out_dir.mkdir(parents=True)
    output_path = out_dir / input_path.name

    start_ns = max(0, args.timestamp_ns - int(args.before * 1_000_000_000))
    end_ns = args.timestamp_ns + int(args.after * 1_000_000_000)

    topic_counts = Counter()
    topic_times = defaultdict(list)
    field_keys = defaultdict(set)
    schemas_by_id = {}
    channels_by_id = {}
    written = 0
    available_start = None
    available_end = None

    try:
        with input_path.open("rb") as src, output_path.open("wb") as dst:
            reader = make_reader(src)
            writer = Writer(dst)
            writer.start(profile="ros2")
            for schema, channel, message in reader.iter_messages():
                schemas_by_id[schema.id if schema else 0] = schema
                channels_by_id[channel.id] = channel
                if message.log_time < start_ns or message.log_time > end_ns:
                    continue

                schema_id = 0
                if schema is not None:
                    schema_id = writer.register_schema(
                        name=schema.name,
                        encoding=schema.encoding,
                        data=schema.data,
                    )
                channel_id = writer.register_channel(
                    topic=channel.topic,
                    message_encoding=channel.message_encoding,
                    schema_id=schema_id,
                    metadata=channel.metadata or {},
                )
                writer.add_message(
                    channel_id=channel_id,
                    log_time=message.log_time,
                    publish_time=message.publish_time,
                    sequence=message.sequence,
                    data=message.data,
                )
                written += 1
                topic_counts[channel.topic] += 1
                topic_times[channel.topic].append(message.log_time)
                available_start = message.log_time if available_start is None else min(
                    available_start, message.log_time
                )
                available_end = message.log_time if available_end is None else max(
                    available_end, message.log_time
                )
            writer.finish()

        if written == 0:
            print(
                "[ERROR] No messages found in the requested time window. "
                "Check timestamp basis and input file."
            )
            return 3

        # rclpy is imported only inside the container. If a message type cannot be
        # loaded, the topic remains in metadata with a diagnostic rather than aborting.
        try:
            import rclpy.serialization
            from rosidl_runtime_py.utilities import get_message
        except Exception:
            rclpy = None
            get_message = None

        if get_message is not None:
            try:
                with input_path.open("rb") as src:
                    reader = make_reader(src)
                    for schema, channel, message in reader.iter_messages(
                        start_time=start_ns, end_time=end_ns
                    ):
                        if schema is None:
                            continue
                        try:
                            cls = get_message(schema.name)
                            obj = rclpy.serialization.deserialize_message(message.data, cls)
                            keys = []
                            if hasattr(obj, "get_fields_and_field_types"):
                                keys = list(obj.get_fields_and_field_types().keys())
                            elif hasattr(obj, "__slots__"):
                                keys = [x.lstrip("_") for x in obj.__slots__]
                            field_keys[channel.topic].update(keys)
                        except Exception:
                            # A topic-specific deserialization failure is recorded below.
                            continue
            except Exception as exc:
                print(f"[WARN] Field extraction incomplete: {exc}")

        topic_summary = {}
        for topic, count in sorted(topic_counts.items()):
            times = sorted(topic_times[topic])
            frequency = None
            if len(times) >= 2 and times[-1] > times[0]:
                frequency = round((len(times) - 1) / ((times[-1] - times[0]) / 1e9), 6)
            topic_summary[topic] = {
                "message_count": count,
                "approx_frequency_hz": frequency,
                "available_keys": sorted(field_keys.get(topic, set())),
            }

        metadata = {
            "input_mcap": str(input_path),
            "output_mcap": str(output_path),
            "window": {
                "start_log_time_ns": start_ns,
                "end_log_time_ns": end_ns,
                "center_log_time_ns": args.timestamp_ns,
                "timestamp_basis": "MCAP log_time nanoseconds; must be verified by caller",
                "before_seconds": args.before,
                "after_seconds": args.after,
            },
            "source_event_id": args.event_id,
            "message_count": written,
            "actual_message_time_range_ns": {
                "start": available_start,
                "end": available_end,
            },
            "topics": topic_summary,
            "warnings": [
                "Timestamp alignment with rosout is not inferred automatically.",
                "available_keys may be empty when ROS message types cannot be loaded.",
            ],
        }
        (out_dir / "metadata.yaml").write_text(
            yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        (out_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[PASS] Sliced {written} messages into {output_path}")
        print(f"Topics: {len(topic_summary)}")
        print(f"Metadata: {out_dir / 'metadata.yaml'}")
        return 0
    except Exception as exc:
        print(f"[ERROR] MCAP slicing failed: {type(exc).__name__}: {exc}")
        return 1


def host_main(argv):
    p = argparse.ArgumentParser(
        description="Run MCAP slicing inside a Docker container."
    )
    p.add_argument("--container")
    p.add_argument("--timeout", default=str(DEFAULT_TIMEOUT))
    p.add_argument("--input", required=True, help="Container path to source .mcap")
    p.add_argument("--output-dir", required=True, help="New container output directory")
    p.add_argument("--timestamp-ns", type=int, required=True)
    p.add_argument("--event-id", type=int)
    p.add_argument("--before", type=float, default=5.0)
    p.add_argument("--after", type=float, default=5.0)
    args = p.parse_args(argv)

    if args.timestamp_ns < 0 or args.before < 0 or args.after < 0:
        p.error("timestamp and window values must be non-negative")
    timeout, error = parse_timeout(args.timeout, DEFAULT_TIMEOUT, MAX_TIMEOUT)
    if error:
        print(error)
        return 2
    container, error = resolve_container(args.container)
    if error:
        print(error)
        return 2

    source = base64.b64encode(Path(__file__).read_bytes()).decode("ascii")
    remote = f"/tmp/mcap_slicer_{uuid.uuid4().hex}.py"
    worker_args = [
        "--input", args.input, "--output-dir", args.output_dir,
        "--timestamp-ns", str(args.timestamp_ns),
        "--before", str(args.before), "--after", str(args.after),
    ]
    if args.event_id is not None:
        worker_args += ["--event-id", str(args.event_id)]
    command = (
        f"printf %s {shlex.quote(source)} | base64 -d > {shlex.quote(remote)}"
        f" && ROS2_TOOL_WORKER=1 python3 {shlex.quote(remote)} {shlex.join(worker_args)}"
        f"; rc=$?; rm -f {shlex.quote(remote)}; exit $rc"
    )
    ok, stdout, error_message = docker_exec(
        container, ROS2_ENV_FALLBACK + command, timeout,
        interactive=True, what="ROS 2 MCAP slicer",
        timeout_hint="請確認時間戳記是 MCAP log_time 的奈秒值，且輸出目錄尚不存在。",
    )
    if not ok:
        print(error_message)
        if stdout.strip():
            print(stdout.rstrip())
        return 1
    print(with_target_marker(stdout.strip() or "[PASS] Slicer completed.", container))
    return 0


if __name__ == "__main__":
    if os.environ.get("ROS2_TOOL_WORKER") == "1":
        raise SystemExit(worker_main(sys.argv[1:]))
    raise SystemExit(host_main(sys.argv[1:]))
