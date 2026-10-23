"""docker / docker exec 共用層：統一逾時機制、錯誤回報格式、容器名稱的判斷與 ROS 2 環境。

所有容器相關的技能腳本（docker_* / ROS2_* / 數據技能）都透過這裡執行 docker CLI，確保：

1. 每一次呼叫都有逾時上限；宿主機端的 docker CLI 在自己的程序群組裡跑，逾時結束整個群組（host_run）。
   在容器內執行指令時，優先用容器內的 `timeout` 包住指令：逾時時對容器內的程序送 TERM（KILL_AFTER_SECONDS 秒後補 KILL），
   真正終止容器內的程序；宿主機端另設 timeout + HOST_GRACE_SECONDS 作為 daemon 沒有回應時的後盾。
   容器內沒有 `timeout` 就只用宿主機端的逾時；沒有 bash（alpine／busybox）就改用 sh（exec_in_container）。
2. exit code 124 分兩種（classify_exit）：花的時間到了上限＝我們的逾時；沒到＝指令自己的 `timeout N` 時間到
   （`timeout 5 ros2 topic hz` 這類用法，是正常結束）。
3. 失敗一律回 `[ERROR] 原因。下一步：…`：常見的 docker／ros2 錯誤翻成可以採取的行動（explain_error），
   其他的附上 stderr 的結尾（太長截尾）；輸出一律以 UTF-8（errors="replace"）解碼，容器的二進位輸出不會讓腳本當掉。
4. 容器名稱：lookup_container（完全相同 > 不分大小寫相同 > 唯一的部分名稱，對不到附相近的名稱）、
   split_container_arg（「第一個參數是不是容器」的共用判斷）、省略＝目前的目標容器（resolve_container，只認完全相同的名稱）。
5. ROS 2 環境（ros2_env_prefix）：shell 沒有 ros2 就 source /opt/ros；載入 ROS2_workspace_env 確認過的 Workspace
   （workspace_source，沒有才找常見位置的第一個）；shell 沒有 ROS_DOMAIN_ID 就沿用正在跑的節點的設定；
   report=True 時印一行實際用的 domain（parse_ros_env 取出來，技能寫在標頭）。

狀態標記（[TARGET_CONTAINER]、[CONTAINER_CWD]…）只放在輸出的最後幾行（with_target_marker／with_cwd_marker）；
原樣轉出的內容（容器的 log、指令的輸出）先經過 neutralize_markers，裡面剛好出現的標記字樣不會被當成標記。

回傳慣例（docker_exec／run_docker／ros2_exec）：(ok: bool, stdout: str, error_message: str)
  ok=True  -> stdout 為指令輸出，error_message 為空字串（stderr 不附，要看 stderr 用 exec_in_container）
  ok=False -> error_message 以 [ERROR] 開頭；stdout 可能含逾時／失敗前的部分輸出

腳本由 harness 以 `python3 scripts/<name>_cmd.py` 執行，sys.path[0] 即為本目錄，可直接 `import _docker_common`。只用標準庫。
"""
import datetime
import difflib
import os
import re
import shlex
import signal
import subprocess
import time

# 沒有 tty 時 bash -ic 一定會印出的雜訊，對診斷沒有幫助，一律過濾
_STDERR_NOISE = (
    "cannot set terminal process group",
    "no job control in this shell",
    "tcsetattr: Inappropriate ioctl for device",
)

HOST_GRACE_SECONDS = 10   # 宿主機端 subprocess 逾時 = 容器內逾時 + 此緩衝
KILL_AFTER_SECONDS = 2    # 容器內 timeout 送出 TERM 後多久補 KILL
OUTER_TIMEOUT_SLACK = 0.5  # exit code 124 時，花的時間離上限不到這麼多秒＝我們的逾時（否則是指令自己的 timeout）

# ---------------------------------------------------------------- ROS 2 環境
# 有些容器的 .bashrc 不會 source ROS 的 setup.bash，導致 `bash -ic` 找不到 ros2；實測 fih_rmf_system 容器：節點以
# ROS_DOMAIN_ID=98 啟動，但 bash -ic 既沒有 ros2 也沒有 domain，只 source /opt/ros 會讓 ros2 topic list 空白。
ROS_SOURCE = (
    'command -v ros2 >/dev/null 2>&1 || { if [ -n "$ROS_DISTRO" ] && [ -f "/opt/ros/$ROS_DISTRO/setup.bash" ]; then '
    'source "/opt/ros/$ROS_DISTRO/setup.bash"; else for _d in /opt/ros/*/setup.bash; do [ -f "$_d" ] && '
    '{ source "$_d"; break; }; done; fi; }; '
)
# 常見位置的第一個 colcon Workspace（輸出丟掉，避免 overlay 的 hook 印 banner 污染工具結果）
WS_GLOB = (
    'for _ws in /workspaces/*/install/setup.bash /workspace/install/setup.bash /workspace/*/install/setup.bash '
    '"$HOME"/*_ws/install/setup.bash /root/*_ws/install/setup.bash /opt/*_ws/install/setup.bash; do '
    '[ -f "$_ws" ] && { source "$_ws" >/dev/null 2>&1; _cah_ws="${_ws%/install/setup.bash}"; break; }; done; '
)
# shell 沒有 ROS_DOMAIN_ID 時，從容器內「正在跑的 ROS 節點」的 /proc/<pid>/environ 複製 domain／RMW／discovery 相關變數：
# 診斷工具要看到的是節點所在的那個 domain，不是 shell 預設的 0。_cah_dsrc 記下來源（shell／node:<pid>:<程式>／default）。
_DOMAIN_ENV_RE = "^(ROS_DOMAIN_ID|RMW_IMPLEMENTATION|CYCLONEDDS_URI|ROS_AUTOMATIC_DISCOVERY_RANGE|ROS_LOCALHOST_ONLY|ROS_STATIC_PEERS)="
DOMAIN_COPY = (
    '_cah_dsrc=shell; if [ -z "$ROS_DOMAIN_ID" ]; then _cah_dsrc=default; for _e in /proc/[0-9]*/environ; do '
    'if tr "\\0" "\\n" < "$_e" 2>/dev/null | grep -q "^ROS_DOMAIN_ID="; then '
    f'while IFS= read -r _kv; do export "$_kv"; done < <(tr "\\0" "\\n" < "$_e" 2>/dev/null | grep -E "{_DOMAIN_ENV_RE}"); '
    '_p="${_e%/environ}"; _p="${_p#/proc/}"; _cah_dsrc="node:$_p:$(cat "/proc/$_p/comm" 2>/dev/null)"; '
    'break; fi; done; fi; '
)
ROS_ENV_TAG = "@@CAH_ROS_ENV@@"
ENV_REPORT = f'printf "%s|%s|%s|%s|%s\\n" "{ROS_ENV_TAG}" "${{ROS_DOMAIN_ID-}}" "$_cah_dsrc" "${{ROS_DISTRO-}}" "${{_cah_ws-}}"; '

# 舊的組合（_ros2_data_common 等直接拼接的呼叫端還在用）：/opt/ros → 第一個找到的 Workspace → domain
ROS2_ENV_FALLBACK = ROS_SOURCE + WS_GLOB + DOMAIN_COPY


def workspace_source(container):
    """harness 記錄的 ROS 2 Workspace（ROS2_workspace_env 確認過、而且屬於這個容器）→ 載入它的 setup.bash 的指令片段；
    沒有記錄或屬於別的容器回空字串。路徑可以是 Workspace 根目錄或它的 install（兩種都認）。"""
    ws = (os.environ.get("ROS2_WORKSPACE") or "").strip().rstrip("/")
    ws_container = (os.environ.get("ROS2_WORKSPACE_CONTAINER") or "").strip()
    if not ws or not ws.startswith("/") or ws_container != (container or "").strip():
        return ""
    if ws.endswith("/install/setup.bash"):
        ws = ws[: -len("/install/setup.bash")]
    elif ws.endswith("/install"):
        ws = ws[: -len("/install")]
    setup = shlex.quote(f"{ws}/install/setup.bash")
    return f"[ -f {setup} ] && {{ source {setup} >/dev/null 2>&1; _cah_ws={shlex.quote(ws)}; }}; "


def ros2_env_prefix(container, report=False):
    """在容器內跑 ros2 之前的環境載入（接在 bash -ic 的指令前面）：/opt/ros → 確認過的 Workspace（沒有才找常見位置）→ domain。
    report=True 時多印一行實際用的 domain、來源、ROS_DISTRO、Workspace（parse_ros_env 取出、從輸出拿掉）。"""
    ws = workspace_source(container)
    parts = [ROS_SOURCE]
    if ws:
        parts += [ws, f'[ -n "${{_cah_ws-}}" ] || {{ {WS_GLOB}}}; ']
    else:
        parts.append(WS_GLOB)
    parts.append(DOMAIN_COPY)
    if report:
        parts.append(ENV_REPORT)
    return "".join(parts)


def parse_ros_env(out):
    """輸出裡 ros2_env_prefix(report=True) 印的那一行 → (拿掉那一行的輸出, {domain, source, distro, workspace})；沒有就回 (原文, {})。"""
    text = out or ""
    env = {}
    keep = []
    for ln in text.split("\n"):
        if ln.startswith(ROS_ENV_TAG + "|") and not env:
            parts = (ln.split("|") + [""] * 5)[1:5]
            env = {"domain": parts[0].strip(), "source": parts[1].strip(), "distro": parts[2].strip(), "workspace": parts[3].strip()}
            continue
        keep.append(ln)
    return "\n".join(keep), env


def domain_text(env, short=False):
    """parse_ros_env 的結果 → 「ROS_DOMAIN_ID 42（shell 的設定…）」這種一句話（short＝只有「ROS_DOMAIN_ID 42」）；沒有資訊回空字串。"""
    if not env:
        return ""
    dom = env.get("domain") or ""
    src = env.get("source") or ""
    if short:
        return f"ROS_DOMAIN_ID {dom or '0'}"
    if src.startswith("node:"):
        _, pid, comm = (src.split(":", 2) + ["", ""])[:3]
        how = f"沿用正在跑的節點 pid {pid}{(' ' + comm) if comm else ''} 的設定"
    elif src == "shell":
        how = "shell 的設定：容器的環境變數或 ~/.bashrc"
    else:
        how = "沒有設定、也沒有找到帶 domain 的節點，用預設值"
    return f"ROS_DOMAIN_ID {dom or '0'}（{how}）"


# ---------------------------------------------------------------- 文字整理
def clean_stderr(text):
    lines = [ln for ln in (text or "").splitlines() if not any(n in ln for n in _STDERR_NOISE)]
    return "\n".join(lines).strip()


# bash -ic 載入 /etc/bash.bashrc：Ubuntu 對 sudo 群組、還沒用過 sudo 的使用者每次都在 stdout 開頭印這段提示，不是指令的輸出
_STDOUT_BANNER = ('To run a command as administrator (user "root"), use "sudo <command>".',
                  'See "man sudo_root" for details.')


def strip_banner(text):
    """去掉 stdout 開頭的 sudo 提示（連同它後面的空行）；沒有提示就原樣傳回。"""
    if not text or not text.lstrip().startswith(_STDOUT_BANNER[0]):
        return text
    lines = text.split("\n")
    while lines and (lines[0].strip() in _STDOUT_BANNER or not lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines)


def tail(text, max_lines=20, max_chars=2000):
    """只保留輸出結尾，避免把大量原始輸出塞回 Agent（有截掉就標「前面省略」）。"""
    text = (text or "").strip()
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) > max_lines:
        text = f"...(前面省略 {len(lines) - max_lines} 行)...\n" + "\n".join(lines[-max_lines:])
    if len(text) > max_chars:
        text = "...(前面省略)..." + text[-max_chars:]
    return text


def clip(text, n=120):
    """一行文字（指令、訊息）太長時截斷並標「…」。"""
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


_MARKER_LINE_RE = re.compile(r"^(\[(?:TARGET_CONTAINER|CWD_CHANGED|CONTAINER_CWD|ANALYSIS_DATA|ROS2_WORKSPACE)\])", re.M)


def neutralize_markers(text):
    """原樣轉出的內容（指令輸出、容器 log）裡剛好以狀態標記開頭的行，前面加一個空白：只有腳本自己附在最後的才是標記。"""
    return _MARKER_LINE_RE.sub(r" \1", text or "")


def format_table(rows, headers):
    """欄位對齊的純文字表格（第一行是欄名）。"""
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]

    def line(cols):
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cols)).rstrip()

    return "\n".join([line(headers)] + [line(r) for r in rows])


# ---------------------------------------------------------------- 時間（docker 回的是 UTC，顯示成主機的本地時間並標時區）
def tz_label():
    off = time.strftime("%z")   # +0800
    return f"UTC{off[:3]}:{off[3:]}" if re.fullmatch(r"[+-]\d{4}", off or "") else "本地時區"


def parse_docker_time(text):
    """docker 的 RFC 3339 時間（2026-10-23T06:52:36.617075387Z）→ aware datetime；空的或 0001 年（沒有發生過）回 None。"""
    s = (text or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$", s)
    if not m or m.group(1) == "0001":
        return None
    us = int((m.group(7) or "0")[:6].ljust(6, "0"))
    tz = m.group(8) or "Z"
    if tz == "Z":
        tzinfo = datetime.timezone.utc
    else:
        sign = 1 if tz[0] == "+" else -1
        tzinfo = datetime.timezone(sign * datetime.timedelta(hours=int(tz[1:3]), minutes=int(tz[-2:])))
    return datetime.datetime(*(int(m.group(i)) for i in range(1, 7)), us, tzinfo=tzinfo)


def local_time(text, with_date=True):
    """docker 的時間 → 主機本地時間「10-23 14:52:36」（不是今年時加年份）；沒有發生過回「（沒有）」。"""
    dt = parse_docker_time(text)
    if dt is None:
        return "（沒有）"
    loc = dt.astimezone()
    if not with_date:
        return loc.strftime("%H:%M:%S")
    fmt = "%m-%d %H:%M:%S" if loc.year == datetime.datetime.now().year else "%Y-%m-%d %H:%M:%S"
    return loc.strftime(fmt)


def human_duration(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分 {seconds % 60} 秒"
    if seconds < 86400:
        return f"{seconds // 3600} 小時 {seconds % 3600 // 60} 分"
    return f"{seconds // 86400} 天 {seconds % 86400 // 3600} 小時"


# ---------------------------------------------------------------- 錯誤訊息
def explain_error(stderr, container=None):
    """常見的 docker／ros2 錯誤 → 「原因。下一步：…」；認不出來回 None。ros2 CLI 的使用錯誤（找不到 node、參數、訊息型別）
    是印在 stderr、exit code 1 的一句話，也在這裡翻。"""
    s = (stderr or "").lower()
    c = container or "<容器>"
    if "cannot connect to the docker daemon" in s or "is the docker daemon running" in s:
        return ("無法連線到 Docker daemon（服務沒有啟動，或目前的帳號沒有 docker 權限）。下一步：請使用者確認 Docker 服務在跑"
                "（systemctl status docker）；這不是參數的問題，不要原樣重試")
    if "permission denied" in s and "docker.sock" in s:
        return "沒有存取 docker socket 的權限。下一步：請使用者把目前的帳號加入 docker 群組，或改用有權限的帳號"
    if "no such container" in s:
        return (f"找不到容器 '{c}'（名稱錯誤、已被刪除或改名）。下一步：用 docker_containers 查現有容器的完整名稱；"
                f"目前的目標容器不見了就用 docker_open 重新選定")
    if "is paused" in s:
        return (f"容器 '{c}' 被暫停（paused），暫停中不能執行指令。下一步：請使用者確認後在主機上 docker unpause {c}"
                f"（host_runcmd，會先請使用者確認）")
    if "is restarting" in s:
        return f"容器 '{c}' 一直在重新啟動（啟動後馬上結束又被重啟）。下一步：docker_ctl logs {c} 看它為什麼一啟動就結束"
    if "is not running" in s:
        return (f"容器 '{c}' 存在但沒有在運行。下一步：docker_ctl status {c} 看它為什麼停了；"
                f"使用者同意後 docker_ctl start {c}（會先請使用者確認）")
    if "invalid container name" in s:
        return "容器名稱不合法（只能用英數字、底線、點、減號，開頭要是英數字，至少 2 個字）。下一步：用 --name 換一個合法的名稱"
    if "invalid reference format" in s:
        return "映像檔名稱的格式不對（要全部小寫、不能有空白；tag 寫在冒號後面）。下一步：用 docker_images 看正確的名稱"
    if "pull access denied" in s or "repository does not exist" in s or "manifest unknown" in s \
            or ("unable to find image" in s and "error response from daemon" in s):
        return ("本機沒有這個映像檔，而且拉不到（名稱或 tag 錯、沒有登入 registry、或沒有網路）。"
                "下一步：用 docker_images 確認本機有哪些映像檔，改用本機有的「名稱:tag」")
    if "is already in use by container" in s:
        return ("同名的容器已經存在。下一步：docker_containers <名稱> 看它的狀態——在跑就用 docker_open 進入；"
                "停了的話用 docker_ctl start 啟動它，或換一個 --name（要刪掉舊的請先問使用者）")
    if "no space left on device" in s:
        return "磁碟空間不足。下一步：請使用者清出空間（例如移除不用的映像檔或容器）；不要原樣重試"
    if "ros2: command not found" in s or "ros2: not found" in s:
        return ("容器內找不到 ros2 指令（沒有安裝 ROS 2，或 shell 沒有載入 /opt/ros/<distro>/setup.bash）。"
                "下一步：docker_runcmd 的指令前面加上 `source /opt/ros/$ROS_DISTRO/setup.bash && `；"
                "先 docker_runcmd \"ls /opt/ros\" 確認有沒有安裝")
    if "unable to find node" in s or "node not found" in s:
        return ("找不到這個 ROS 2 node（名稱不對、node 沒在跑，或不在同一個 ROS_DOMAIN_ID）。"
                "下一步：ROS2_node_list 確認完整名稱（含命名空間，例如 /nav_node）；列表是空的就用 ROS2_domain_id 看 domain")
    if "parameter not set" in s:
        return "這個 node 沒有這個參數。下一步：ROS2_param list <node> 看有哪些參數（名稱要完全一樣）"
    if "setting parameter failed" in s:
        return "設定參數失敗（原因在下面的訊息）。下一步：唯讀的參數只能改設定檔後重啟 node；型別不對時值要跟原本的型別一樣（例如 10.0 而不是 10）"
    if "the passed message type is invalid" in s or "unknown message type" in s \
            or ("the message type" in s and "is invalid" in s):
        return ("不認得這個訊息型別。下一步：ROS2_topic_list --types 看 topic 實際的型別（寫完整，例如 std_msgs/msg/String）；"
                "自訂的型別（例如 fih_rmf_msgs）先用 ROS2_workspace_env 確認 Workspace，之後會自動載入")
    if "failed to populate field" in s or "needs to be in yaml" in s:
        return ("訊息內容跟型別的欄位對不上（欄位名稱或 YAML 寫法錯）。下一步：docker_runcmd \"source /opt/ros/$ROS_DISTRO/setup.bash "
                "&& ros2 interface show <型別>\" 看欄位，內容寫成 '{欄位: 值}'")
    if "could not determine the type for the passed topic" in s:
        return "找不到這個 topic，或目前沒有任何 publisher（ros2 判斷不出型別）。下一步：ROS2_topic_list 確認名稱（含開頭的 /）"
    if "executable file not found" in s or "oci runtime exec failed" in s:
        return "容器內找不到要執行的程式。下一步：確認指令名稱，或用 docker_runcmd \"which <程式>\" 查它在哪裡"
    return None


def _no_message_reason(rc):
    return (f"指令以 exit code {rc} 結束，沒有印出錯誤訊息（grep 沒找到、test 不成立、diff 有差異時也會回非 0，不一定是錯誤）。"
            "下一步：看標準輸出判斷是不是預期的結果；要確認是哪一段失敗，指令後面加 `; echo rc=$?`")


def failure_reason(err, container=None, rc=None):
    """非 0 結束時的原因：認得的錯誤翻成「原因。下一步」並附 stderr 的結尾；認不得就是 stderr 的結尾（太長截尾）。"""
    err = clean_stderr(err)
    explained = explain_error(err, container)
    if explained:
        return explained + (f"\n--- stderr ---\n{tail(err, 15, 1500)}" if err else "")
    if err:
        return tail(err, 15, 1500)
    return _no_message_reason(rc)


def _fail(what, reason, rc=None, stdout=""):
    msg = f"[ERROR] {what} 失敗" + (f"（exit code {rc}）" if rc is not None else "") + f"：{reason}"
    out = tail(stdout)
    if out:
        msg += f"\n--- 部分標準輸出 ---\n{neutralize_markers(out)}"
    return msg


# ---------------------------------------------------------------- 執行
def _decode(data):
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def host_run(cmd, timeout, input_text=None):
    """在宿主機執行一個指令（docker CLI）：自己的程序群組、不讀標準輸入（除非給 input_text）、逾時結束整個群組。
    回傳 {rc, out, err, elapsed, host_timeout, missing}；out／err 以 UTF-8（errors=replace）解碼，逾時時是已經收到的部分。"""
    start = time.monotonic()
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    except FileNotFoundError:
        return {"rc": None, "out": "", "err": "", "elapsed": 0.0, "host_timeout": False, "missing": True}
    data = input_text.encode("utf-8", errors="replace") if input_text is not None else None
    timed_out = False
    try:
        out_b, err_b = p.communicate(input=data, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        out_b, err_b = p.communicate()
    return {"rc": p.returncode, "out": _decode(out_b), "err": _decode(err_b), "elapsed": time.monotonic() - start,
            "host_timeout": timed_out, "missing": False}


DOCKER_MISSING = "[ERROR] 找不到 docker 指令。下一步：請使用者確認 Docker 已安裝而且在 PATH 中；這不是參數的問題，不要原樣重試。"


def run_docker(cmd, timeout, what="docker 指令"):
    """執行宿主機端的 docker CLI（不進入容器內 shell），例如 docker run / docker ps。回傳 (ok, stdout, error_message)。"""
    r = host_run(cmd, timeout)
    if r["missing"]:
        return False, "", DOCKER_MISSING
    if r["host_timeout"]:
        return False, r["out"], (f"[ERROR] {what} 逾時（超過 {timeout} 秒沒有回應）：Docker daemon 沒有回應，或映像檔拉取太慢。"
                                 f"下一步：稍後再試一次；一直逾時就請使用者檢查 Docker 服務與網路")
    if r["rc"] != 0:
        return False, r["out"], _fail(what, failure_reason(r["err"], rc=r["rc"]), r["rc"], r["out"])
    return True, r["out"], ""


def _missing_launcher(rc, err):
    """docker exec 的啟動失敗：容器內沒有 timeout 回 "timeout"、沒有 bash 回 "bash"，其他回 None。"""
    if rc not in (126, 127):
        return None
    if re.search(r'exec: "timeout": executable file not found', err):
        return "timeout"
    if re.search(r'exec: "bash": executable file not found', err) or \
            re.search(r"timeout: (failed to run command|can't execute) .bash.: No such file", err):
        return "bash"
    return None


def classify_exit(rc, elapsed, limit, inner=True):
    """exit code 的意思（純函式，可測）："ok"、"timeout"（我們的逾時：花的時間到了上限）、"own_timeout"（指令自己的
    `timeout N` 時間到，例如 `timeout 5 ros2 topic hz`）、"killed"（137：逾時後補 KILL，或被 OOM 終止）、"error"。"""
    if rc == 0:
        return "ok"
    if rc == 124:
        return "timeout" if inner and elapsed >= limit - OUTER_TIMEOUT_SLACK else "own_timeout"
    if rc == 137:
        return "killed"
    return "error"


def exec_in_container(container, command, timeout, *, interactive=False, input_text=None, need_bash=False):
    """在容器內以 bash（沒有 bash 時改用 sh）執行 shell 指令，含容器內 timeout 與宿主機端後盾逾時。
    interactive=True 用 `bash -ic`（會載入 .bashrc，ROS 2 指令需要）；input_text 經 stdin 送進指令（docker exec -i）。
    need_bash=True（指令用了 bash 的語法，例如 ROS 2 的環境載入）時沒有 bash 直接回錯誤，不改用 sh。
    回傳 dict：rc、out（stdout，interactive 時去掉 sudo 提示）、err（去掉 bash -ic 雜訊的 stderr）、elapsed、
    kind（classify_exit 的結果，或 "host_timeout"／"launch_error"）、shell、inner（有沒有用容器內的 timeout）、
    launch_error（docker 本身不能執行時的 [ERROR] 訊息，否則 None）。"""
    head = ["docker", "exec"] + (["-i"] if input_text is not None else []) + [container]
    use_inner, shell = True, "bash"
    while True:
        flag = "-ic" if (interactive and shell == "bash") else "-c"
        cmd = head + (["timeout", "-k", str(KILL_AFTER_SECONDS), str(timeout)] if use_inner else []) + [shell, flag, command]
        r = host_run(cmd, timeout + HOST_GRACE_SECONDS, input_text)
        base = {"rc": r["rc"], "out": "", "err": "", "elapsed": r["elapsed"], "shell": shell, "inner": use_inner,
                "launch_error": None}
        if r["missing"]:
            return dict(base, kind="launch_error", launch_error=DOCKER_MISSING)
        out = strip_banner(r["out"]) if interactive else r["out"]
        err = clean_stderr(r["err"])
        if interactive and shell == "bash" and err.endswith("exit") and (err == "exit" or err.endswith("\nexit")):
            err = err[:-4].rstrip("\n")   # 互動式 bash 執行 exit 時會在 stderr 印一行 exit，不是指令的輸出
        base.update(out=out, err=err)
        if r["host_timeout"]:
            return dict(base, kind="host_timeout")
        missing = _missing_launcher(r["rc"], err)
        if missing == "timeout" and use_inner:
            use_inner = False   # 容器內沒有 coreutils timeout：只用宿主機端的逾時再執行一次
            continue
        if missing == "bash" and shell == "bash":
            if need_bash:
                return dict(base, kind="launch_error", launch_error=(
                    f"[ERROR] 容器 '{container}' 裡沒有 bash（alpine／busybox 這類精簡映像）：這個技能需要 bash（ROS 2 的環境也需要）。"
                    f"下一步：用 docker_containers 確認這是不是你要的容器；容器內的一般指令用 docker_runcmd（會改用 sh）"))
            shell = "sh"
            continue
        return dict(base, kind=classify_exit(r["rc"], r["elapsed"], timeout, use_inner))


def describe_failure(res, what, timeout, timeout_hint=None, container=None, next_step=None):
    """exec_in_container 不成功（kind 不是 ok）時的 [ERROR] 訊息：逾時、被 KILL、自己的 timeout、一般的錯誤；附部分輸出。"""
    if res.get("launch_error"):
        return res["launch_error"]
    kind, rc, out = res.get("kind"), res.get("rc"), res.get("out") or ""
    partial = neutralize_markers(tail(out))
    if kind == "host_timeout":
        msg = (f"[ERROR] {what} 逾時（超過 {timeout} 秒沒有結束），宿主機端已強制結束 docker exec；容器內的程序可能還在跑。"
               f"下一步：docker_runcmd \"ps aux\" 確認；Docker 沒有回應時請使用者檢查 Docker 服務")
    elif kind == "timeout":
        msg = f"[ERROR] {what} 逾時（超過 {timeout} 秒），容器內的程序已被終止。"
        if not timeout_hint:
            msg += "下一步：確定只是需要更久才加大逾時；不會自己結束的指令要在前面加 timeout N 或放到背景"
    elif kind == "killed":
        msg = _fail(what, f"程序被 KILL 強制終止（逾時 {timeout} 秒後 TERM 沒有用而補 KILL，或記憶體不足被系統 OOM 終止）。"
                          "下一步：docker_ctl status 看 OOMKilled；長時間的工作改到背景執行", rc)
    elif kind == "own_timeout":
        msg = _fail(what, "指令裡的 timeout 時間到，結束了它（exit code 124；不是這個技能的逾時）。"
                          "下一步：要看更久就把指令裡 timeout 的秒數加大", rc)
    else:
        reason = failure_reason(res.get("err"), container, rc)
        if next_step and "下一步" not in reason:
            reason += f"。下一步：{next_step}"
        msg = _fail(what, reason, rc)
    if timeout_hint and kind in ("host_timeout", "timeout", "killed"):
        msg += f"\n{timeout_hint}"
    if partial:
        label = "逾時前的部分輸出" if kind in ("host_timeout", "timeout", "killed") else "部分標準輸出"
        msg += f"\n--- {label} ---\n{partial}"
    return msg


def docker_exec(container, command, timeout, interactive=False, what=None, timeout_hint=None, input_text=None):
    """在容器內以 bash 執行 shell 指令（相容舊的呼叫端）：回傳 (ok, stdout, error_message)。成功時 stderr 不附；
    要看 stderr、exit code、花的時間就用 exec_in_container。"""
    what = what or f"容器 '{container}' 內的指令"
    # interactive（bash -ic）的呼叫端都是 ROS 2 的指令（bash 的語法）：沒有 bash 時直接說清楚，不改用 sh 跑出語法錯誤
    res = exec_in_container(container, command, timeout, interactive=interactive, input_text=input_text, need_bash=interactive)
    if res["kind"] == "ok":
        return True, res["out"], ""
    return False, res["out"], describe_failure(res, what, timeout, timeout_hint, container)


def ros2_run(container, ros2_command, timeout):
    """在容器內執行 ros2 指令（bash -ic＋ros2_env_prefix，回報實際用的 domain）：回傳 exec_in_container 的 dict，
    多一個 env（parse_ros_env 的結果；out 裡那一行已拿掉）。"""
    res = exec_in_container(container, ros2_env_prefix(container, report=True) + ros2_command, timeout,
                            interactive=True, need_bash=True)
    res["out"], res["env"] = parse_ros_env(res.get("out"))
    return res


def ros2_exec(container, ros2_command, timeout, timeout_hint=None):
    """在容器內執行 ros2 指令（相容舊的呼叫端）：互動式 shell＋ROS 2 環境（含確認過的 Workspace）。回傳 (ok, stdout, error_message)。"""
    what = f"容器 '{container}' 內的 `{clip(ros2_command, 160)}`"
    res = exec_in_container(container, ros2_env_prefix(container) + ros2_command, timeout, interactive=True, need_bash=True)
    if res["kind"] == "ok":
        return True, res["out"], ""
    return False, res["out"], describe_failure(res, what, timeout, timeout_hint, container)


# ---------------------------------------------------------------- 不會自己結束的指令
_SEG_OPS = {"&&", "||", ";", "|", "&", "|&", ";;", "(", ")", "{", "}"}
_WRAPPERS = {"sudo", "nohup", "exec", "env", "nice", "stdbuf", "time", "command", "unbuffer"}


def _short_flags(toks):
    return "".join(t[1:] for t in toks if t.startswith("-") and not t.startswith("--"))


def _endless_hint(toks):
    cmd = os.path.basename(toks[0])
    args = toks[1:]
    if cmd == "ros2" and len(args) >= 2:
        group, verb = args[0], args[1]
        if group == "topic" and verb == "echo" and "--once" not in args:
            return ("`ros2 topic echo` 沒有加 --once，會一直印到逾時。下一步：只看一筆就加 --once；要看一段時間用 "
                    "ROS2_topic_echo <topic> --duration 10（會算頻率與欄位變化）；一定要用 docker_runcmd 就在前面加 timeout，"
                    "例如 \"timeout -s INT 10 ros2 topic echo /odom\"（時間到被結束是正常的，會回 [PASS]）")
        if group == "topic" and verb in ("hz", "bw", "delay"):
            return (f"`ros2 topic {verb}` 不會自己結束。下一步：前面加 timeout，例如 "
                    f"\"timeout -s INT 10 ros2 topic {verb} /odom\"（時間到被結束是正常的，會回 [PASS]）；"
                    "ROS2_topic_echo <topic> --duration 10 也會算頻率")
        if group == "bag" and verb == "record":
            return ("`ros2 bag record` 不會自己結束。下一步：錄製用 mcap_recorder（有時長）；一定要用 docker_runcmd 就加 "
                    "timeout -s INT <秒數>")
    if cmd == "ros2" and args[:1] == ["launch"]:
        return ("`ros2 launch` 會一直跑。下一步：要在背景啟動就寫成 \"nohup ros2 launch … > /tmp/launch.log 2>&1 &\"，"
                "之後用 docker_runcmd \"tail -n 50 /tmp/launch.log\" 看輸出；只看前幾秒的輸出就在前面加 timeout -s INT 20")
    if cmd == "tail" and (any(t in ("-f", "-F") or t.startswith("--follow") for t in args) or re.search(r"[fF]", _short_flags(args))):
        return ("`tail -f` 不會自己結束。下一步：改用 tail -n 100 <檔案>；容器本身的輸出 log 用 docker_ctl logs"
                "（--since 接著看新的）")
    if cmd == "journalctl" and (any(t.startswith("--follow") for t in args) or "f" in _short_flags(args)):
        return "`journalctl -f` 不會自己結束。下一步：改用 journalctl -n 100 --no-pager"
    if cmd == "watch":
        return "`watch` 會一直重複執行。下一步：直接執行一次要看的指令；要隔一段時間再看就分兩次執行"
    if cmd == "top" and not ("b" in _short_flags(args) and "n" in _short_flags(args)):
        return "`top` 是互動式畫面、不會自己結束。下一步：改用 top -b -n 1（或 ps aux --sort=-%cpu | head）"
    if cmd in ("vi", "vim", "nvim", "nano", "emacs", "htop", "mc"):
        return (f"`{cmd}` 是互動式程式，沒有終端機可以操作。下一步：看檔案用 cat 或 sed -n '1,80p' <檔案>；"
                "改檔案用 sed -i，或請使用者自己改")
    if cmd == "ping" and "-c" not in args and "c" not in _short_flags(args) and not any(t.startswith("--count") for t in args):
        return "`ping` 沒有 -c 會一直跑。下一步：ping -c 3 <主機>"
    if cmd == "rostopic" and args[:1] and args[0] in ("echo", "hz", "bw"):
        return "`rostopic` 是 ROS 1 的指令而且不會自己結束。下一步：ROS 2 用 ROS2_topic_echo <topic> --duration 10"
    if cmd == "sleep" and args[:1] == ["infinity"]:
        return "`sleep infinity` 不會結束。下一步：要讓容器一直跑是 docker_est 的 --cmd \"sleep infinity\"，不是在容器裡執行"
    return None


def endless_command(command):
    """不會自己結束（或要終端機互動）的指令 → 提示文字；包了 timeout、放到背景（&）或認不出來 → None。"""
    try:
        lex = shlex.shlex(str(command or "").replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return None
    segs, cur = [], []
    for t in toks + [";"]:
        if t in _SEG_OPS:
            if cur:
                segs.append((cur, t))
            cur = []
        else:
            cur.append(t)
    for seg, op in segs:
        if op == "&":            # 放到背景：不會卡住這次的執行
            continue
        i = 0
        while i < len(seg):
            w = os.path.basename(seg[i])
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i]):
                i += 1
            elif w in _WRAPPERS:
                i += 1
                while i < len(seg) and (seg[i].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i])):
                    i += 1
            else:
                break
        rest = seg[i:]
        if not rest:
            continue
        if os.path.basename(rest[0]) == "timeout":   # 有時間上限：時間到被結束（exit code 124）是預期的
            continue
        hint = _endless_hint(rest)
        if hint:
            return hint
    return None


# ---------------------------------------------------------------- 參數
def parse_filter_args(argv, usage, flags=()):
    """`[container_name] [--filter 關鍵字]... [旗標]` → (container, keywords, error) 或 flags 非空時 (container, keywords, 旗標集合, error)。
    關鍵字可重複，不分大小寫的子字串比對；flags＝這個技能認得的無值旗標（例如 --types）。"""
    container, keywords, seen = "", [], set()
    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--filter" or a.startswith("--filter="):
            val = a.split("=", 1)[1] if "=" in a else (args[i + 1] if i + 1 < len(args) else None)
            if not val:
                err = f"[ERROR] --filter 後面需要關鍵字。\n{usage}"
                return (None, None, None, err) if flags else (None, None, err)
            keywords.append(val)
            i += 1 if "=" in a else 2
            continue
        if a in flags:
            seen.add(a)
            i += 1
            continue
        if a.startswith("-"):
            known = "、".join(["--filter", *flags])
            err = f"[ERROR] 不認識的選項 {a}（這個技能的選項只有 {known}）。\n{usage}"
            return (None, None, None, err) if flags else (None, None, err)
        if container:
            err = (f"[ERROR] 只接受一個容器名稱，收到 {container!r} 與 {a!r}（過濾請用 --filter 關鍵字）。\n{usage}")
            return (None, None, None, err) if flags else (None, None, err)
        container = a
        i += 1
    return (container, keywords, seen, None) if flags else (container, keywords, None)


def namespace_of(name):
    """ROS 名稱的第一層命名空間：/tb1/odom → /tb1；/odom → /（根）。"""
    parts = [p for p in str(name).split()[0].split("/") if p] if str(name).strip() else []
    return "/" + parts[0] if len(parts) >= 2 else "/"


def group_by_namespace(items):
    """依第一層命名空間分組：[(命名空間, [項目…])]，根命名空間在前，其他照字母。"""
    groups = {}
    for it in items:
        groups.setdefault(namespace_of(it), []).append(it)
    return sorted(groups.items(), key=lambda kv: (kv[0] != "/", kv[0]))


def grouped_lines(items):
    """清單依命名空間分節：兩個以上的命名空間時每節一行「## /tb1（4 項）」；只有一個就原樣（不加標題）。"""
    groups = group_by_namespace(items)
    if len(groups) <= 1:
        return list(items)
    out = []
    for ns, its in groups:
        out.append(f"## {ns}（根命名空間，{len(its)} 項）" if ns == "/" else f"## {ns}（{len(its)} 項）")
        out += its
    return out


def pass_or_empty(stdout, empty_hint):
    """成功但沒有輸出時，給 Agent 一個明確的 [PASS] 訊息。
    空字串會被 Agent_Runner 誤判成「沒有工具需要執行」，絕對不能回傳空字串。"""
    text = (stdout or "").strip()
    return text if text else f"[PASS] 指令執行成功，但沒有任何輸出（{empty_hint}）。"


def parse_timeout(value, default, max_seconds, name="timeout"):
    """解析使用者傳入的逾時秒數；回傳 (seconds, error_message_or_None)。"""
    if value is None or str(value).strip() == "":
        return default, None
    try:
        seconds = int(str(value).strip())
    except ValueError:
        return None, f"[ERROR] {name} 必須是整數秒數，收到: {value!r}"
    if not 1 <= seconds <= max_seconds:
        return None, f"[ERROR] {name} 需介於 1～{max_seconds} 秒（上限低於系統總逾時 600 秒），收到: {seconds}"
    return seconds, None


# ---------------------------------------------------------------- 目標容器（比照當前工作目錄）
# harness（Agent_Runner.run_tool）把目前的目標容器放在環境變數 TARGET_CONTAINER 傳給每支腳本，容器技能省略 <container_name>
# 時就用它。腳本成功操作某個（執行中的）容器後，在輸出末行印「[TARGET_CONTAINER] <名稱>」，harness 的
# _sync_state_from_tool_output 會同步；所以目標容器＝最近一次成功操作的容器，docker_open 則是刻意選定／切換用。
# 與目前目標相同時不印，避免每次都多一行噪音。
TARGET_CONTAINER_ENV = "TARGET_CONTAINER"
TARGET_CONTAINER_MARKER = "[TARGET_CONTAINER]"
CONTAINER_CWD_MARKER = "[CONTAINER_CWD]"     # harness 讀它的「下一行」當容器內的目前目錄（CURRENT_CONTAINER_DIRECTORY）
NO_TARGET_HINT = ("沒有指定容器，目前也沒有目標容器。下一步：先用 docker_containers 查看名稱，再用 docker_open <名稱> 選定目標容器"
                  "（之後可省略容器名稱），或直接把容器名稱放在第一個參數。")
LIST_TIMEOUT_SECONDS = 15
CONTAINER_LIST_MAX = 15   # 錯誤訊息裡列出的現有容器最多幾個


def current_target_container():
    return (os.environ.get(TARGET_CONTAINER_ENV) or "").strip()


def list_container_names(timeout=LIST_TIMEOUT_SECONDS):
    """所有容器（含未運行）的名稱清單；docker 不可用時回 (None, error)。"""
    ok, out, err = run_docker(["docker", "ps", "-a", "--format", "{{.Names}}"], timeout, what="查詢容器清單 (docker ps -a)")
    if not ok:
        return None, err
    return [n.strip() for n in out.splitlines() if n.strip()], None


def match_container(name, names):
    """名稱比對：完全相同 > 唯一的子字串符合；對不到或多個符合回 None（相容舊的呼叫端；新的用 lookup_container）。"""
    if name in names:
        return name
    matches = [n for n in names if name in n]
    return matches[0] if len(matches) == 1 else None


def exact_container(name, names):
    """完全相同的容器名稱；沒有時不分大小寫相同而且只有一個才算。都沒有回 None（不做部分比對）。"""
    if name in names:
        return name
    hits = [n for n in names if n.lower() == name.lower()]
    return hits[0] if len(hits) == 1 else None


def existing_list_text(names):
    if not names:
        return "（目前沒有任何容器）"
    shown = "、".join(names[:CONTAINER_LIST_MAX])
    more = f"…（共 {len(names)} 個，只列前 {CONTAINER_LIST_MAX} 個；docker_containers 看全部）" if len(names) > CONTAINER_LIST_MAX else f"（共 {len(names)} 個）"
    return shown + more


def similar_names(name, names, n=3):
    """拼字相近的名稱（不分大小寫）：給「找不到」的錯誤訊息附建議。"""
    low = {x.lower(): x for x in names}
    return [low[c] for c in difflib.get_close_matches((name or "").lower(), list(low), n=n, cutoff=0.6)]


def container_not_found(name, names):
    close = similar_names(name, names)
    hint = f"相近的：{'、'.join(close)}。" if close else ""
    return (f"[ERROR] 沒有叫「{name}」的容器。{hint}現有的容器：{existing_list_text(names)}。"
            f"下一步：改用正確的完整名稱重試（不確定就用 docker_containers 查，或問使用者是哪一個）")


def lookup_container(name, names=None, partial=True):
    """容器名稱 → (真實名稱, None) 或 (None, [ERROR]…)。比對順序：完全相同 > 不分大小寫相同（唯一）>（partial）唯一的部分名稱
    （不分大小寫）。對到好幾個時列出來請使用者指定；對不到時附相近的名稱與現有的容器。names=None 時向 docker 查（含未運行的）。"""
    name = (name or "").strip()
    if names is None:
        names, err = list_container_names()
        if names is None:
            return None, err
    if not name:
        return None, f"[ERROR] {NO_TARGET_HINT}"
    real = exact_container(name, names)
    if real:
        return real, None
    if partial:
        hits = [n for n in names if name.lower() in n.lower()]
        if len(hits) == 1:
            return hits[0], None
        if hits:
            listed = "、".join(hits[:CONTAINER_LIST_MAX]) + ("…" if len(hits) > CONTAINER_LIST_MAX else "")
            return None, (f"[ERROR] 「{name}」對到 {len(hits)} 個容器：{listed}。下一步：改用完整名稱；"
                          f"不確定是哪一個就問使用者，不要自己挑")
    return None, container_not_found(name, names)


def resolve_container(name, usage=None):
    """決定這次要操作的容器，回傳 (container, error)：name 非空就用它（不查證，相容舊的呼叫端）；
    空 → 目前的目標容器（原樣、完全相同的名稱）；兩者皆空 → [ERROR] 提示先用 docker_open 選定。"""
    name = (name or "").strip() or current_target_container()
    if name:
        return name, None
    return None, f"[ERROR] {NO_TARGET_HINT}" + (f"\n{usage}" if usage else "")


def split_container_arg(args, usage=None, *, must=False, maybe=False, names=None):
    """「第一個參數是不是容器名稱」的共用判斷（各技能依自己參數的形狀決定 must／maybe）。回傳 (container, rest, error)：
    - must＝第一個參數一定是容器：要對到現有的容器（lookup_container：不分大小寫、允許唯一的部分名稱），對不到回 [ERROR]＋相近的名稱；
    - maybe＝兩種讀法都可能：完全相同（不分大小寫）的容器名稱才算容器，否則整串都是後面的參數；
    - 兩者皆否、或沒有參數：沒有給容器。
    沒有給容器時用目前的目標容器（resolve_container）；container 一定是真實名稱或目標容器。"""
    args = list(args)
    if args and must:
        real, err = lookup_container(args[0], names, partial=True)
        if err:
            return None, None, err + (f"\n{usage}" if usage else "")
        return real, args[1:], None
    if args and maybe:
        if names is None:
            names, _ = list_container_names()
        real = exact_container(args[0], names) if names else None
        if real:
            return real, args[1:], None
    container, err = resolve_container("", usage)
    return container, args, err


def with_target_marker(output, container):
    """成功輸出附上目標容器標記（末行），讓 harness 把它設為目前的目標容器；與目前目標相同時不附。"""
    container = (container or "").strip()
    if not container or container == current_target_container():
        return output
    return f"{output.rstrip()}\n{TARGET_CONTAINER_MARKER} {container}"


def with_cwd_marker(output, path):
    """附上容器內目前目錄的標記（harness 讀標記的下一行；放在輸出的最後兩行）。路徑不是單行的絕對路徑就不附。"""
    path = (path or "").rstrip("\r")
    if not path.startswith("/") or "\n" in path:
        return output
    return f"{output.rstrip()}\n{CONTAINER_CWD_MARKER}\n{path}"


# ---------------------------------------------------------------- 容器的 log（docker logs -t：stdout 與 stderr 依時間合併）
MAX_LOG_FETCH = 2000      # 一次最多取幾行
LOG_LINE_MAX = 500        # 單行 log 超過這麼多字截斷
LOG_TIMEOUT = 60
_LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2}) ?")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text):
    return _ANSI_RE.sub("", text or "")


def _log_ts_ns(m):
    dt = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
    tz = m.group(3)
    off = 0 if tz == "Z" else (1 if tz[0] == "+" else -1) * (int(tz[1:3]) * 3600 + int(tz[4:6]) * 60)
    base = int(dt.replace(tzinfo=datetime.timezone.utc).timestamp()) - off
    return base * 1_000_000_000 + int((m.group(2) or "")[:9].ljust(9, "0"))


def merge_log_streams(out, err):
    """docker logs -t 的 stdout 與 stderr → [(奈秒, "out"|"err", 訊息)]，依時間合併（同一個時間 stdout 在前）。
    非 TTY 的容器 ROS 2 的 log 與 Python 的 traceback 都在 stderr：只收 stdout 會什麼都看不到。"""
    rows = []
    for stream, text in (("out", out), ("err", err)):
        last = 0
        for ln in (text or "").splitlines():
            m = _LOG_TS_RE.match(ln)
            if m:
                last = _log_ts_ns(m)
                ln = ln[m.end():]
            rows.append((last, stream, ln))
    rows.sort(key=lambda r: r[0])
    return rows


def fetch_container_logs(name, tail=None, since=None, until=None, timeout=LOG_TIMEOUT):
    """容器的 log → (rows, None) 或 (None, [ERROR]…)；rows 見 merge_log_streams。tail=None 時取 MAX_LOG_FETCH 行
    （--since 之後的也一樣有上限）；since／until 照 docker logs 的寫法。"""
    cmd = ["docker", "logs", "-t", "--tail", str(tail or MAX_LOG_FETCH)]
    if since:
        cmd += ["--since", since]
    if until:
        cmd += ["--until", until]
    r = host_run(cmd + [name], timeout)
    if r["missing"]:
        return None, DOCKER_MISSING
    if r["host_timeout"]:
        return None, (f"[ERROR] docker logs {name} 逾時（超過 {timeout} 秒沒有回應）。下一步：縮小範圍（--tail、--since）再試；"
                      f"一直逾時請使用者檢查 Docker")
    if r["rc"] != 0:
        err = r["err"]
        if "does not support reading" in err:
            return None, (f"[ERROR] 容器 {name} 的 log driver 不能讀回 log（docker logs 失敗：{clip(err, 200)}）。"
                          f"下一步：程式自己寫的 log 檔用 docker_runcmd 讀；或請使用者改容器的 log 設定")
        return None, _fail(f"docker logs {name}", failure_reason(err, name, r["rc"]), r["rc"])
    return merge_log_streams(r["out"], r["err"]), None


def clean_log_line(msg):
    """一行 log 給模型看：去掉終端機顏色碼與 \\r、狀態標記字樣中和、太長截斷（並註明）。"""
    msg = neutralize_markers(strip_ansi(msg).replace("\r", ""))
    return msg if len(msg) <= LOG_LINE_MAX else msg[:LOG_LINE_MAX] + f"…（這一行共 {len(msg)} 字，截斷）"


def fmt_log_time(ns, with_date):
    """奈秒（epoch）→ 主機本地時間「14:52:36.617」（with_date 時前面加「10-23 」）。"""
    if not ns:
        return "（沒有時間）".ljust(12)
    dt = datetime.datetime.fromtimestamp(ns / 1e9)
    return dt.strftime("%m-%d %H:%M:%S.%f")[:-3] if with_date else dt.strftime("%H:%M:%S.%f")[:-3]


def log_multi_day(rows):
    """→ (是否跨日, 第一天的「MM-DD」)。"""
    days = {datetime.datetime.fromtimestamp(r[0] / 1e9).date() for r in rows if r[0]}
    return len(days) > 1, (min(days).strftime("%m-%d") if days else "")


def format_log_rows(rows, with_date):
    """rows → 「時間 2> 訊息」一行一筆（2> 標 stderr）。"""
    return [f"{fmt_log_time(ns, with_date)} {'2>' if stream == 'err' else '  '} {clean_log_line(msg)}" for ns, stream, msg in rows]


def inspect_container(name, timeout=30):
    """docker inspect 一個容器 → (dict, None) 或 (None, [ERROR]…)。"""
    import json
    ok, out, err = run_docker(["docker", "inspect", "--type", "container", name], timeout, what=f"docker inspect {name}")
    if not ok:
        return None, err
    try:
        return json.loads(out)[0], None
    except (ValueError, IndexError):
        return None, f"[ERROR] docker inspect {name} 的輸出看不懂。下一步：稍後再試；一直這樣請使用者檢查 Docker"
