"""docker_runcmd：在容器（或目前的目標容器）裡執行一行 shell 指令（bash -c；容器裡沒有 bash 時用 sh）。

- 參數（parse_args，純函式：guard 用同一套判斷決定要不要請使用者確認）：[--timeout 秒] [容器名稱] "<指令>"。
  只有一個參數＝指令、容器用目標容器；兩個以上時，第一個是現有容器的名稱（完全相同，不分大小寫）才當容器；
  是常見的指令字（ls、mkdir、ros2…）或路徑就整串當指令（模型常忘記加引號）；唯一的部分名稱也當容器（輸出會註明）；
  其他回 [ERROR] 附相近的名稱——不會把打錯的容器名稱接進指令、在別的容器裡執行。
- 不會自己結束的指令（ros2 topic echo 沒有 --once、ros2 topic hz、tail -f、ros2 launch…）沒有包 timeout 時直接回 [ERROR] 與替代做法。
- 起始目錄＝CURRENT_CONTAINER_DIRECTORY（harness 的環境變數 CONTAINER_CWD，限目標容器；目錄不在就從容器的預設目錄開始）；
  結束時的目錄印成最後兩行的 [CONTAINER_CWD] 標記，所以指令裡的 cd 會保留到下一次。前後加的指令以換行接在後面，
  指令以 `;`、`&`（背景執行）或註解結尾都可以。
- exit code 124 而且還沒到 --timeout：是指令自己的 `timeout N` 時間到（`timeout 5 ros2 topic hz`），回 [PASS] 並註明。
- 成功時 stderr 附在「## stderr」一節（最後 15 行）；輸出太長只留頭尾並說明。
"""
import os
import re
import secrets
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_common import rejoin_args  # noqa: E402
from _docker_common import (NO_TARGET_HINT, clip, current_target_container, describe_failure, endless_command,  # noqa: E402
                            exact_container, exec_in_container, existing_list_text, failure_reason, list_container_names,
                            neutralize_markers, parse_timeout, similar_names, tail, with_cwd_marker, with_target_marker)

DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 570   # 必須低於 harness 的 TOOL_EXEC_TIMEOUT (600)，否則會先被 harness 殺掉
MAX_OUTPUT_CHARS = 150_000  # 輸出超過這麼多字只留頭尾
HEAD_CHARS, TAIL_CHARS = 100_000, 30_000
STDERR_LINES = 15

USAGE = (
    "用法: scripts/docker_runcmd_cmd.py [--timeout 秒數] [容器名稱] \"<指令>\"\n"
    f"  --timeout 預設 {DEFAULT_TIMEOUT_SECONDS} 秒，上限 {MAX_TIMEOUT_SECONDS} 秒；長時間建置（colcon build）請加大。\n"
    "  容器名稱省略＝目前的目標容器。指令用一對雙引號包住整串（指令裡要用引號時用單引號）。"
)

DOCKER_CLI_HINT = ("docker_runcmd 是在容器『裡面』執行指令（容器裡沒有 docker）；要看、啟動、停止、重新啟動容器本身，"
                   "請用 docker_ctl（status／logs／start／stop／restart），其他 docker 指令用 host_runcmd 在主機上執行"
                   "（會先請使用者確認）。")


def docker_cli_misuse(command):
    """模型想用 docker_runcmd 跑 docker CLI（docker start／restart／ps…）：回提示文字，否則 None。評測的對照組用
    AGENT_ABLATE=docker_hint 關掉。"""
    if "docker_hint" in os.environ.get("AGENT_ABLATE", ""):
        return None
    words = (command or "").strip().split()
    return DOCKER_CLI_HINT if words[:1] == ["docker"] or words[:2] == ["sudo", "docker"] else None


# 第一個參數是這些字（或路徑、VAR=值）時，整串都是指令（模型忘記加引號：docker_runcmd mkdir test）
COMMAND_WORDS = {
    "ls", "cat", "cd", "pwd", "echo", "printf", "mkdir", "rmdir", "rm", "cp", "mv", "touch", "ln", "chmod", "chown", "find",
    "grep", "egrep", "fgrep", "rg", "sed", "awk", "head", "tail", "wc", "sort", "uniq", "cut", "tr", "xargs", "tee", "diff",
    "stat", "file", "du", "df", "free", "ps", "top", "kill", "pkill", "pgrep", "killall", "env", "printenv", "export", "source",
    ".", "bash", "sh", "python", "python3", "pip", "pip3", "apt", "apt-get", "dpkg", "ros2", "colcon", "rosdep", "make", "cmake",
    "git", "curl", "wget", "tar", "zip", "unzip", "gzip", "gunzip", "sleep", "timeout", "nohup", "which", "whereis", "type",
    "whoami", "id", "uname", "hostname", "date", "test", "[", "true", "false", "systemctl", "service", "journalctl", "ip",
    "ifconfig", "ping", "netstat", "ss", "lsof", "mount", "umount", "sudo", "nano", "vim", "vi", "less", "more", "watch",
    "tree", "realpath", "readlink", "basename", "dirname", "md5sum", "sha256sum", "jq", "node", "npm", "gcc", "g++", "ldd",
    "nproc", "lscpu", "lsusb", "lspci", "lsblk", "set", "unset", "exec", "for", "while", "if", "uptime", "column", "yes",
    "ros2cli", "rqt", "rviz2", "gazebo", "ign", "gz", "dmesg", "history", "alias", "clear", "time", "nice", "chgrp", "sync",
}
_SHELL_OPS = {"&&", "||", ";", "|", "&", "|&", ">", ">>", "<", "2>", "2>>", "&>", "2>&1"}


def looks_like_command(word, rest=()):
    w = (word or "").strip()
    if not w:
        return False
    if w in COMMAND_WORDS or "/" in w or w.startswith(("./", "~")) or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
        return True
    return any(a in _SHELL_OPS for a in rest)


# ---------------------------------------------------------------- 參數
def _take_timeout(args):
    """--timeout 秒數（或 --timeout=秒數）：可以放在最前面、容器名稱後面，或最後面。回傳 (值或 None, 其餘參數, 錯誤)。"""
    out, val, i, n = [], None, 0, len(args)
    while i < n:
        a = args[i]
        m = re.fullmatch(r"--timeout(?:=(.*))?", a)
        if m and (i <= 1 or i >= n - 2) and val is None:
            if m.group(1) is not None:
                val, i = m.group(1), i + 1
                continue
            if i + 1 >= n:
                return None, None, f"[ERROR] --timeout 後面需要秒數。\n{USAGE}"
            val, i = args[i + 1], i + 2
            continue
        out.append(a)
        i += 1
    return val, out, None


def parse_args(argv, target=None, names=None):
    """docker_runcmd 的參數 → {"container", "command", "timeout", "error", "error_kind", "via", "notes"}（guard 用同一個函式判斷）。
    target：目前的目標容器（None＝讀環境變數 TARGET_CONTAINER；""＝沒有目標）。names：現有容器的名稱清單
    （None＝需要判斷時才向 docker 查）。via：容器怎麼決定的（arg／partial／target）。error 不是 None 時不要執行；
    error_kind：usage（參數本身的問題）、refused（認得指令但不執行：不會結束、docker CLI）、container（對不到容器，跟 docker 的
    現況有關）、docker（查不到容器清單）。guard 只該對 usage／refused 放行，其他照指令內容判斷。"""
    res = {"container": None, "command": None, "timeout": None, "error": None, "error_kind": None, "via": None, "notes": []}
    target = current_target_container() if target is None else (target or "").strip()
    res["error_kind"] = "usage"
    raw_timeout, args, err = _take_timeout([a for a in argv if a != ""])
    if err:
        return dict(res, error=err)
    timeout, err = parse_timeout(raw_timeout, DEFAULT_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS, name="--timeout")
    if err:
        return dict(res, error=f"{err}\n{USAGE}")
    res["timeout"] = timeout
    if not args:
        return dict(res, error=f"[ERROR] 參數不足，需要要執行的指令（容器名稱可省略＝目標容器）。\n{USAGE}")
    if len(args) == 1:
        if not target:
            return dict(res, error=f"[ERROR] 只收到一個參數 {clip(args[0], 80)!r}，但目前沒有目標容器。{NO_TARGET_HINT}\n{USAGE}")
        container, command, via = target, args[0], "target"
    else:
        first = args[0]
        if names is None:
            names, err = list_container_names()
            if names is None:
                return dict(res, error=err, error_kind="docker")
        exact = exact_container(first, names)
        partial = [n for n in names if first.lower() in n.lower()]
        if exact:
            container, command, via = exact, rejoin_args(args[1:]), "arg"
        elif looks_like_command(first, args[1:]):
            if not target:
                return dict(res, error=(f"[ERROR] 「{first}」不是現有的容器，整串看起來是指令，但目前沒有目標容器。{NO_TARGET_HINT}\n"
                                        f"{USAGE}"))
            container, command, via = target, rejoin_args(args), "target"
        elif len(partial) == 1:
            container, command, via = partial[0], rejoin_args(args[1:]), "partial"
            res["notes"].append(f"「{first}」當成容器 {partial[0]}（唯一符合的部分名稱）")
        else:
            if partial:
                why = (f"[ERROR] 第一個參數「{first}」對到 {len(partial)} 個容器：{'、'.join(partial[:10])}。"
                       f"下一步：改用完整的容器名稱；不確定是哪一個就問使用者")
            else:
                close = similar_names(first, names)
                why = (f"[ERROR] 第一個參數「{first}」不是現有的容器" + (f"（相近的：{'、'.join(close)}）" if close else "")
                       + f"，也不像指令。現有的容器：{existing_list_text(names)}。下一步：容器名稱要完整（docker_containers 查）；"
                       f"整串是指令的話用一對雙引號包住：docker_runcmd \"{clip(rejoin_args(args), 60)}\"")
            return dict(res, error=f"{why}\n{USAGE}", error_kind="container")
    if not command.strip():
        return dict(res, error=f"[ERROR] 指令是空的。\n{USAGE}")
    hint = docker_cli_misuse(command)
    if hint:
        return dict(res, container=container, command=command, via=via, error=f"[ERROR] {hint}", error_kind="refused")
    hint = endless_command(command)
    if hint:
        return dict(res, container=container, command=command, via=via, error=f"[ERROR] {hint}（這次沒有執行）",
                    error_kind="refused")
    return dict(res, container=container, command=command, via=via, error_kind=None)


# ---------------------------------------------------------------- 執行
def build_script(command, start_dir, tag):
    """指令前後加上：Python 不緩衝輸出（被 timeout 結束時已印的看得到）、起始目錄、開始與結束的目錄標籤（隨機 tag，
    指令的輸出偽造不了）。結尾以換行接在指令後面，指令以 ; & 或註解結尾都不影響；exit code 照指令的。"""
    lines = ["export PYTHONUNBUFFERED=1"]
    if start_dir:
        lines.append(f"cd -- {shlex.quote(start_dir)} 2>/dev/null")
    lines.append(f"printf '%s%s\\n' '__CAH_START_{tag}__' \"$PWD\"")
    lines.append(command.rstrip("\\ \n"))
    lines.append(f"__cah_rc=$?; printf '\\n%s%s\\n' '__CAH_END_{tag}__' \"$PWD\"; exit $__cah_rc")
    return "\n".join(lines)


def split_trailer(out, tag):
    """拿掉 build_script 加的開始／結束目錄行 → (指令的輸出, 開始目錄, 結束目錄)；沒有的回空字串。"""
    s_tag, e_tag = f"__CAH_START_{tag}__", f"__CAH_END_{tag}__"
    start = end = ""
    i = out.find(s_tag)
    if i >= 0:
        j = out.find("\n", i)
        start = out[i + len(s_tag): j if j >= 0 else None]
        out = out[:i] + (out[j + 1:] if j >= 0 else "")
    k = out.rfind(e_tag)
    if k >= 0:
        j = out.find("\n", k)
        end = out[k + len(e_tag): j if j >= 0 else None]
        before = out[:k]
        out = (before[:-1] if before.endswith("\n") else before) + (out[j + 1:] if j >= 0 else "")
    return out, start.strip("\r"), end.strip("\r")


def clip_output(text):
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    skipped = len(text) - HEAD_CHARS - TAIL_CHARS
    return (text[:HEAD_CHARS] + f"\n…（中間省略 {skipped} 字：輸出共 {len(text)} 字，只留前 {HEAD_CHARS} 與最後 {TAIL_CHARS} 字；"
            f"用 head／tail／grep／sed -n 縮小範圍）…\n" + text[-TAIL_CHARS:])


def run_in_container(container, command, timeout=DEFAULT_TIMEOUT_SECONDS, notes=()):
    notes = list(notes)
    cwd_env = (os.environ.get("CONTAINER_CWD") or "").strip()
    start_dir = cwd_env if cwd_env.startswith("/") and container == current_target_container() else ""
    tag = secrets.token_hex(4)
    res = exec_in_container(container, build_script(command, start_dir, tag), timeout)
    out, start_pwd, end_pwd = split_trailer(res.get("out") or "", tag)
    res["out"] = out
    what = f"容器 '{container}' 內 `{clip(command, 120)}`"
    kind = res["kind"]
    if kind in ("launch_error", "host_timeout", "timeout", "killed"):
        return describe_failure(res, what, timeout, container=container, timeout_hint=(
            f"若是長時間的建置或安裝，請用 --timeout 加大（上限 {MAX_TIMEOUT_SECONDS}）；不會自己結束的程式請放到背景"
            f"（nohup … > /tmp/x.log 2>&1 &）或在前面加 timeout N。"))
    if start_dir and start_pwd and start_pwd != start_dir:
        notes.append(f"CURRENT_CONTAINER_DIRECTORY 的 {start_dir} 在這個容器裡不存在，改從 {start_pwd} 開始")
    if res.get("shell") == "sh":
        notes.append("容器裡沒有 bash，這次用 sh 執行")
    rc = res["rc"]
    dirs = (f"目錄 {start_pwd} → {end_pwd}" if start_pwd and end_pwd and start_pwd != end_pwd
            else (f"目錄 {end_pwd or start_pwd}" if (end_pwd or start_pwd) else ""))
    body = clip_output(neutralize_markers(out.strip("\n")))
    err = res.get("err") or ""
    own_timeout = kind == "own_timeout" and re.search(r"(^|[\s;&|(])timeout\s", command) is not None
    if kind == "ok" or own_timeout:
        head = f"[PASS] {what} 執行完成（exit code {rc}" + (f"；{dirs}" if dirs else "") + "）"
        if own_timeout:
            head += "；指令自己的 timeout 時間到、結束了它（hz／echo 這類不會自己結束的指令是正常的）"
        lines = [head + "：", body or "（沒有標準輸出）"]
        if err:
            n = len(err.splitlines())
            lines += [f"## stderr（{n} 行" + (f"，只列最後 {STDERR_LINES} 行" if n > STDERR_LINES else "") + "）",
                      neutralize_markers(tail(err, STDERR_LINES, 3000))]
        if notes:
            lines.append("（" + "；".join(notes) + "）")
        return with_cwd_marker(with_target_marker("\n".join(lines), container), end_pwd)
    reason = failure_reason(err, container, rc)
    if "下一步" not in reason:
        reason += "\n下一步：依上面的錯誤修正指令再執行；同樣的指令不要原樣重送"
    lines = [f"[ERROR] {what} 失敗（exit code {rc}" + (f"；{dirs}" if dirs else "") + f"）：{reason}"]
    if body:
        lines += [f"## 標準輸出（{len(body.splitlines())} 行）", body]
    if notes:
        lines.append("（" + "；".join(notes) + "）")
    text = "\n".join(lines)
    # 失敗時不換目標容器；目錄只在操作的就是目標容器時同步（目錄屬於目標容器）
    return with_cwd_marker(text, end_pwd) if container == current_target_container() else text


def main(argv):
    p = parse_args(argv)
    if p["error"]:
        return p["error"]
    return run_in_container(p["container"], p["command"], p["timeout"], p["notes"])


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] docker_runcmd 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
