
#!/usr/bin/env python3
"""載入指定 Docker 容器內的 ROS 2 Workspace 環境並執行命令。"""

import argparse
import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _docker_common import (
    docker_exec,
    resolve_container,
    with_target_marker,
)

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 570

USAGE = (
    "用法: scripts/ros2_workspace_env_cmd.py "
    "[--timeout 秒數] [--container 容器名稱] "
    "--workspace <Workspace 絕對路徑> [--command <命令>]"
)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="載入容器內 ROS 2 Workspace 環境",
        usage=USAGE,
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"逾時秒數，預設 {DEFAULT_TIMEOUT_SECONDS}，"
             f"上限 {MAX_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--container",
        default="",
        help="Docker 容器名稱；省略時使用目前目標容器",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="容器內 Workspace 根目錄，必須為絕對路徑",
    )
    parser.add_argument(
        "--command",
        default="",
        help="載入環境後要執行的 Shell 命令",
    )
    return parser.parse_args(argv)


def build_command(workspace, command):
    """組合同一個 Bash Shell 內的 Workspace 載入與執行命令。"""
    workspace_q = shlex.quote(workspace)

    parts = [
        f"cd -- {workspace_q}",
        "test -f install/setup.bash",
        "source install/setup.bash",
        'printf "ROS2_WORKSPACE=%s\\n" "$PWD"',
        'printf "ROS_DISTRO=%s\\n" "${ROS_DISTRO:-未設定}"',
    ]

    if command:
        parts.append(command)

    # docker_exec 使用 bash -c 執行；source 與後續命令在同一個 Shell。
    return " && ".join(parts)


def run(args):
    if not 1 <= args.timeout <= MAX_TIMEOUT_SECONDS:
        return (
            f"[ERROR] --timeout 必須介於 1～{MAX_TIMEOUT_SECONDS} 秒，"
            f"收到：{args.timeout}"
        )

    workspace = args.workspace.strip()

    if not workspace:
        return "[ERROR] Workspace 路徑不可為空。"

    if not workspace.startswith("/"):
        return (
            "[ERROR] Workspace 必須使用容器內的絕對路徑，"
            f"收到：{workspace!r}"
        )

    container, error = resolve_container(args.container, USAGE)
    if error:
        return error

    command = build_command(workspace, args.command.strip())

    ok, stdout, error = docker_exec(
        container,
        command,
        args.timeout,
        what=f"載入容器 '{container}' 的 ROS 2 Workspace '{workspace}'",
        timeout_hint=(
            "若命令執行時間較長，可增加 --timeout；"
            "請勿超過系統限制。"
        ),
    )

    if not ok:
        return error

    body = (
        f"[PASS] 已在容器 '{container}' 載入 ROS 2 Workspace："
        f"{workspace}\n"
        f"{stdout.strip() or '環境載入完成，沒有額外輸出。'}"
    )

    # 保留現有的目標容器同步機制。
    body = with_target_marker(body, container)

    # 只有 docker_exec 成功後才輸出 Workspace 狀態標記。
    # dispatch.py 會解析它，供後續 System Prompt 使用。
    marker = "[ROS2_WORKSPACE] " + json.dumps(
        {
            "container": container,
            "path": workspace,
        },
        ensure_ascii=False,
    )

    return f"{body.rstrip()}\n{marker}"


def main():
    try:
        args = parse_args(sys.argv[1:])
    except SystemExit as exc:
        return int(exc.code or 0)

    try:
        result = run(args)
    except Exception as exc:
        print(f"[ERROR] ros2_workspace_env 未預期的例外：{exc}")
        return 1

    print(result)

    if result.startswith("[ERROR]"):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
