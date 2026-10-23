"""ROS2_workspace_env：確認容器裡的 ROS 2 Workspace（install/setup.bash 載入得了）並記錄成目前的 Workspace（末行
[ROS2_WORKSPACE] 標記，之後 ROS2_*、數據技能會自動載入它）；可在同一個 shell 執行一個指令（--command）；
--discover 列出容器裡有 install/setup.bash 的 Workspace（不知道路徑時自己找，不必先問使用者）。

- 參數（parse_args，純函式；guard 用 command 判斷要不要請使用者確認）：--workspace <路徑>（根目錄或它的 install 都可以，
  也接受只寫一個絕對路徑）、--command、--container、--timeout、--discover。錯誤一律是中文的 [ERROR]＋用法，exit code 0。
- 環境跟其他 ROS2_* 技能一樣：shell 沒有 ros2 就 source /opt/ros；shell 沒有 ROS_DOMAIN_ID 就沿用正在跑的節點的設定。
- --command 失敗時 Workspace 仍然記錄（載入是成功的），第一行是 [ERROR] 說明指令失敗的原因。"""
import json
import os
import re
import secrets
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (ROS_SOURCE, DOMAIN_COPY, ENV_REPORT, clip, describe_failure, domain_text,  # noqa: E402
                            endless_command, exec_in_container, failure_reason, neutralize_markers, parse_ros_env,
                            parse_timeout, split_container_arg, tail, with_target_marker)

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 570
DISCOVER_DEPTH = 5
DISCOVER_MAX = 30
USAGE = (
    "用法: scripts/ROS2_workspace_env_cmd.py --workspace <容器內的路徑> [--command \"指令\"] [--container 容器名稱] [--timeout 秒數]\n"
    "      scripts/ROS2_workspace_env_cmd.py --discover [--container 容器名稱]\n"
    "  --workspace 是 Workspace 的根目錄或它的 install（/ws 或 /ws/install 都可以）；不知道路徑就先 --discover。\n"
    f"  --command 在載入 Workspace 的同一個 shell 執行；--timeout 預設 {DEFAULT_TIMEOUT_SECONDS} 秒，上限 {MAX_TIMEOUT_SECONDS}。"
    "容器名稱省略＝目前的目標容器。"
)
WS_MARKER = "[ROS2_WORKSPACE]"


def normalize_workspace(path):
    """/ws/、/ws/install、/ws/install/setup.bash → /ws（~ 開頭的保留，由容器內的 $HOME 展開）。"""
    ws = (path or "").strip()
    for suffix in ("/install/setup.bash", "/install/setup.sh", "/install/local_setup.bash", "/install/"):
        if ws.endswith(suffix):
            ws = ws[: -len(suffix)]
    ws = ws.rstrip("/") or "/"
    if ws.endswith("/install"):
        ws = ws[: -len("/install")] or "/"
    return ws


def parse_args(argv):
    """→ {"container_arg", "workspace", "command", "timeout", "discover", "error"}。不查 docker。"""
    res = {"container_arg": "", "workspace": "", "command": "", "timeout": DEFAULT_TIMEOUT_SECONDS, "discover": False, "error": None}
    args = [a for a in argv if a != ""]
    raw_timeout = None
    i = 0
    while i < len(args):
        a = args[i]
        key, val = (a.split("=", 1) if a.startswith("--") and "=" in a else (a, None))
        if key in ("--discover", "-h", "--help"):
            if key != "--discover":
                return dict(res, error=f"[ERROR] 這個技能沒有 {key}，用法如下（規格在 ROS2_workspace_env）。\n{USAGE}")
            res["discover"] = True
            i += 1
            continue
        if key in ("--workspace", "--command", "--container", "--timeout"):
            if val is None:
                if i + 1 >= len(args):
                    return dict(res, error=f"[ERROR] {key} 後面需要值。\n{USAGE}")
                val, i = args[i + 1], i + 2
            else:
                i += 1
            if key == "--timeout":
                raw_timeout = val
            else:
                res[{"--workspace": "workspace", "--command": "command", "--container": "container_arg"}[key]] = val.strip()
            continue
        if a.startswith("-"):
            return dict(res, error=f"[ERROR] 不認識的選項 {a}（選項只有 --workspace、--command、--container、--timeout、--discover）。\n{USAGE}")
        if a.startswith(("/", "~")) and not res["workspace"]:
            res["workspace"] = a.strip()        # 只寫一個路徑：當成 --workspace
            i += 1
            continue
        return dict(res, error=f"[ERROR] 多了參數 {a!r}：Workspace 用 --workspace、指令用 --command \"…\"（整串用引號包住）。\n{USAGE}")
    timeout, err = parse_timeout(raw_timeout, DEFAULT_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS, name="--timeout")
    if err:
        return dict(res, error=f"{err}\n{USAGE}")
    res["timeout"] = timeout
    if res["workspace"]:
        ws = normalize_workspace(res["workspace"])
        if not ws.startswith(("/", "~")):
            return dict(res, error=(f"[ERROR] Workspace 要寫容器內的絕對路徑（/ 開頭），收到 {res['workspace']!r}。"
                                    f"下一步：不知道路徑就用 --discover 列出容器裡的 Workspace。\n{USAGE}"))
        if ws == "/":
            return dict(res, error=f"[ERROR] Workspace 不能是根目錄 /。下一步：用 --discover 找。\n{USAGE}")
        res["workspace"] = ws
    if res["discover"] and (res["workspace"] or res["command"]):
        return dict(res, error=f"[ERROR] --discover 只列出候選，不能跟 --workspace／--command 一起用。\n{USAGE}")
    if res["command"]:
        hint = endless_command(res["command"])
        if hint:
            return dict(res, error=f"[ERROR] {hint}（這次沒有執行）")
    return res


def _cd(ws):
    if ws == "~":
        return 'cd -- "$HOME"'
    if ws.startswith("~/"):
        return f'cd -- "$HOME"/{shlex.quote(ws[2:])}'
    return f"cd -- {shlex.quote(ws)}"


_PKG_LIST = ("ls -d install/*/share/*/package.xml install/share/*/package.xml 2>/dev/null "
             "| sed 's#.*/share/\\([^/]*\\)/package.xml#\\1#' | sort -u")


def build_command(ws, command, tag):
    """載入 Workspace（失敗時印出原因的標籤）→ 沿用節點的 domain → 印出狀態 → 執行指令（前後加標籤分開輸出）。"""
    parts = [
        ROS_SOURCE,
        f'{_cd(ws)} 2>/dev/null || {{ echo "@@WS|nodir"; exit 3; }}; ',
        '[ -f install/setup.bash ] || { echo "@@WS|nosetup|$PWD"; ls -d */ 2>/dev/null | head -20 | sed "s/^/@@LS|/"; exit 4; }; ',
        'source install/setup.bash >/dev/null; _src=$?; ',
        f'_pk=$({_PKG_LIST}); ',
        'case ":${COLCON_PREFIX_PATH-}:${AMENT_PREFIX_PATH-}:" in *":$PWD/install"*) _onpath=1;; *) _onpath=0;; esac; ',
        'printf "@@WS|ok|%s|%s|%s|%s|%s|%s\\n" "$PWD" "${ROS_DISTRO-}" "$(printf "%s\\n" "$_pk" | grep -c .)" '
        '"$(printf "%s\\n" "$_pk" | head -12 | tr "\\n" " ")" "$([ -d src ] && echo 1 || echo 0)" "$_src/$_onpath"; ',
        DOMAIN_COPY, '_cah_ws="$PWD"; ', ENV_REPORT,
    ]
    script = "".join(parts)
    if command:
        script += (f"\nprintf '%s\\n' '__CAH_CMD_{tag}__'\n{command.rstrip(chr(92) + ' ' + chr(10))}\n"
                   f"__cah_rc=$?; printf '\\n%s\\n' '__CAH_END_{tag}__'; exit $__cah_rc")
    return script


def parse_ws(out):
    info = {"state": None, "ls": []}
    for ln in (out or "").splitlines():
        if ln.startswith("@@WS|"):
            parts = ln.split("|")
            info["state"] = parts[1] if len(parts) > 1 else None
            if parts[1:2] == ["ok"]:
                vals = (parts[2:] + [""] * 6)[:6]
                info.update(path=vals[0], distro=vals[1], npkg=vals[2], pkgs=vals[3].split(), src=vals[4] == "1",
                            src_rc=vals[5])
            elif parts[1:2] == ["nosetup"]:
                info["path"] = parts[2] if len(parts) > 2 else ""
        elif ln.startswith("@@LS|"):
            info["ls"].append(ln[5:].strip())
    return info


def _marker(container, path):
    return f"{WS_MARKER} " + json.dumps({"container": container, "path": path}, ensure_ascii=False)


def _ws_summary(info):
    pk = info.get("pkgs") or []
    npkg = info.get("npkg") or "0"
    names = f"：{'、'.join(pk[:8])}" + ("…" if len(pk) > 8 or (npkg.isdigit() and int(npkg) > len(pk[:8])) else "") if pk else ""
    rc, onpath = (info.get("src_rc") or "0/1").split("/") if "/" in (info.get("src_rc") or "") else ("0", "1")
    warn = ""
    if rc != "0":
        warn += f"；注意：source install/setup.bash 回傳 {rc}（上面的 stderr 可能有原因，例如底層的 /opt/ros 找不到）"
    if onpath != "1":
        warn += "；注意：載入後 COLCON_PREFIX_PATH／AMENT_PREFIX_PATH 裡沒有這個 install（可能是空的 install）"
    return (f"install/setup.bash 載入成功；ROS_DISTRO {info.get('distro') or '未設定'}；{npkg} 個套件{names}；"
            f"{'有 src' if info.get('src') else '沒有 src（只有 install）'}{warn}")


def confirm(container, ws, command, timeout):
    tag = secrets.token_hex(4)
    res = exec_in_container(container, build_command(ws, command, tag), timeout, interactive=True, need_bash=True)
    out, env = parse_ros_env(res.get("out") or "")
    info = parse_ws(out)
    where = f"容器 '{container}' "
    if info["state"] == "nodir":
        return (f"[ERROR] {where}裡沒有 {ws} 這個目錄。下一步：ROS2_workspace_env --discover 列出容器裡有 install/setup.bash 的"
                f" Workspace；找不到再問使用者路徑")
    if info["state"] == "nosetup":
        listing = "、".join(info["ls"][:12]) or "（空的）"
        return (f"[ERROR] {where}的 {info.get('path') or ws} 存在，但沒有 install/setup.bash（還沒 colcon build，或不是 Workspace 的"
                f"根目錄；底下有：{listing}）。下一步：--discover 找有 install/setup.bash 的路徑；要建置的話請使用者確認後用 "
                f"docker_runcmd --timeout 540 \"cd {ws} && source /opt/ros/$ROS_DISTRO/setup.bash && colcon build\"")
    if info["state"] != "ok":
        return describe_failure(res, f"載入{where}的 ROS 2 Workspace {ws}", timeout, container=container,
                                timeout_hint="載入或指令太久：指令需要更久就加大 --timeout（上限 570）。")
    path = info.get("path") or ws
    marker = _marker(container, path)
    dom = domain_text(env, short=True)
    summary = _ws_summary(info)
    if not command:
        body = (f"[PASS] 已確認{where}的 ROS 2 Workspace：{path}（{summary}；{dom}）。已記錄為目前的 Workspace："
                f"之後的 ROS2_*、數據技能會自動載入它（自訂訊息型別才讀得到）。")
        return f"{with_target_marker(body, container).rstrip()}\n{marker}"
    s_tag, e_tag = f"__CAH_CMD_{tag}__", f"__CAH_END_{tag}__"
    cmd_out = out.split(s_tag, 1)[1] if s_tag in out else ""
    if e_tag in cmd_out:
        cmd_out = cmd_out.rsplit(e_tag, 1)[0]
    cmd_out = neutralize_markers(cmd_out.strip("\n"))
    err = res.get("err") or ""
    kind = res["kind"]
    what = f"`{clip(command, 100)}`"
    if kind in ("host_timeout", "timeout", "killed", "launch_error"):
        res["out"] = cmd_out
        return (describe_failure(res, f"{where}載入 {path} 後執行 {what}", timeout, container=container,
                                 timeout_hint="指令需要更久就加大 --timeout（上限 570）。")
                + f"\n（Workspace 本身載入成功，已記錄）\n{marker}")
    own_timeout = kind == "own_timeout" and re.search(r"(^|[\s;&|(])timeout\s", command) is not None
    if kind == "ok" or own_timeout:
        lines = [f"[PASS] 已在{where}載入 {path} 並執行 {what}（exit code {res['rc']}；{dom}）"
                 + ("；指令自己的 timeout 時間到結束了它（正常）" if own_timeout else "") + "：",
                 cmd_out or "（沒有標準輸出）"]
        if err:
            n = len(err.splitlines())
            lines += [f"## stderr（{n} 行" + ("，只列最後 15 行" if n > 15 else "") + "）", neutralize_markers(tail(err, 15, 3000))]
        lines.append(f"（Workspace 已確認並記錄：{summary}）")
        return f"{with_target_marker(chr(10).join(lines), container).rstrip()}\n{marker}"
    reason = failure_reason(err, container, res["rc"])
    if "下一步" not in reason:
        reason += "\n下一步：依上面的錯誤修正指令再執行；同樣的指令不要原樣重送"
    lines = [f"[ERROR] 已在{where}載入 {path}（Workspace 已確認並記錄），但 {what} 失敗（exit code {res['rc']}；{dom}）：{reason}"]
    if cmd_out:
        lines += [f"## 標準輸出（{len(cmd_out.splitlines())} 行）", cmd_out]
    return "\n".join(lines) + f"\n{marker}"


DISCOVER_CMD = (
    f"timeout 20 find / -maxdepth {DISCOVER_DEPTH} \\( -path /proc -o -path /sys -o -path /dev -o -path /usr -o -path /opt/ros "
    "-o -path /var/lib -o -path /snap -o -path '/tmp/agent_tool.*' \\) -prune -o -path '*/install/setup.bash' -print 2>/dev/null "
    f"| head -{DISCOVER_MAX} | while IFS= read -r _f; do _w=\"${{_f%/install/setup.bash}}\"; "
    f"_pk=$(cd \"$_w\" && {_PKG_LIST}); "
    "printf '@@C|%s|%s|%s|%s\\n' \"$_w\" \"$(printf '%s\\n' \"$_pk\" | grep -c .)\" \"$([ -d \"$_w/src\" ] && echo 1 || echo 0)\" "
    "\"$(printf '%s\\n' \"$_pk\" | head -6 | tr '\\n' ' ')\"; done"
)


def discover(container, timeout, reason=""):
    res = exec_in_container(container, DISCOVER_CMD, max(timeout, 30))
    if res["kind"] not in ("ok", "error"):
        return describe_failure(res, f"在容器 '{container}' 找 Workspace", max(timeout, 30), container=container)
    cands = []
    for ln in (res.get("out") or "").splitlines():
        if ln.startswith("@@C|"):
            ws, npkg, src, pkgs = (ln.split("|", 4) + [""] * 5)[1:5]
            cands.append((ws, npkg, src == "1", pkgs.split()))
    current = (os.environ.get("ROS2_WORKSPACE") or "").rstrip("/")
    current_c = (os.environ.get("ROS2_WORKSPACE_CONTAINER") or "").strip()
    scope = f"在 / 底下 {DISCOVER_DEPTH} 層內找，略過 /proc /sys /dev /usr /opt/ros"
    if not cands:
        return with_target_marker(
            f"[PASS] {reason}容器 '{container}' 裡沒有找到任何有 install/setup.bash 的 Workspace（{scope}）：可能還沒 colcon build、"
            f"Workspace 在更深的目錄，或這個容器只用 /opt/ros。下一步：問使用者 Workspace 的路徑（或要不要先建置）", container)
    lines = [f"[PASS] {reason}容器 '{container}' 裡找到 {len(cands)} 個 ROS 2 Workspace（有 install/setup.bash；{scope}"
             + (f"；只列前 {DISCOVER_MAX} 個" if len(cands) >= DISCOVER_MAX else "") + "）",
             f"## Workspace（{len(cands)} 項）"]
    for ws, npkg, src, pkgs in cands:
        mark = "  ← 目前記錄的 Workspace" if ws.rstrip("/") == current and current_c == container else ""
        names = f"（{'、'.join(pkgs)}{'…' if npkg.isdigit() and int(npkg) > len(pkgs) else ''}）" if pkgs else ""
        lines.append(f"{ws}  {npkg} 個套件{names}；{'有 src' if src else '沒有 src'}{mark}")
    lines.append("下一步：ROS2_workspace_env --workspace <路徑> 確認並記錄（之後的 ROS 2 技能會自動載入它）；"
                 "好幾個都像的話，選有 src、套件最多的，或問使用者")
    return with_target_marker("\n".join(lines), container)


def run(p):
    container, _rest, err = split_container_arg([p["container_arg"]] if p["container_arg"] else [], USAGE, must=bool(p["container_arg"]))
    if err:
        return err
    if p["discover"]:
        return discover(container, p["timeout"])
    ws = p["workspace"]
    if not ws and p["command"]:
        cur, cur_c = (os.environ.get("ROS2_WORKSPACE") or "").strip(), (os.environ.get("ROS2_WORKSPACE_CONTAINER") or "").strip()
        if cur and cur_c == container:
            ws = normalize_workspace(cur)
        else:
            return (f"[ERROR] --command 需要 --workspace（容器 '{container}' 還沒有記錄的 Workspace）。"
                    f"下一步：先 ROS2_workspace_env --discover 找路徑，再加上 --workspace <路徑>。\n{USAGE}")
    if not ws:
        return discover(container, p["timeout"], reason="沒有給 --workspace，先列出候選：")
    return confirm(container, ws, p["command"], p["timeout"])


def main(argv):
    p = parse_args(argv)
    if p["error"]:
        return p["error"]
    return run(p)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_workspace_env 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
