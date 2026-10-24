"""docker_est：用映像檔建立並在背景啟動一個容器（docker run -d），在跑的話成為目前的目標容器。

v3（2026-10-23）：
- 參數（parse，純函式）：<映像檔[:tag]> [--name 名稱] [--cmd "指令"] [--network 網路] [-e K=V]...。
  ROS 2 的 DDS 常要 --network host 與 -e ROS_DOMAIN_ID=…，所以支援這兩個；其他 docker run 的選項（-v、-p、--gpus…）
  明說不支援、不建任何東西（-d／-it 這類對背景容器沒有意義的，略過並註明）。
- --cmd 含 shell 語法（&& ; | $ source…）時包成 `bash -lc "<指令>"`（以前直接拆成 exec 的參數，`source … && ros2 run …` 會失敗、
  留下一個 Created 的容器，之後一直撞「同名容器已存在」）；映像裡沒有 bash 時改用 sh -c。
- 同名的容器已經存在：先查好，說它的狀態與下一步（在跑→docker_open；停了→docker_ctl start 或換名稱），不呼叫 docker run。
- 交易式：docker run 失敗、或啟動後 SETTLE_SECONDS 秒內以非 0 結束碼結束時，把這次建立的容器移除（先附上它的 log），
  不留下會擋住下一次重試的空殼。結束碼 0（一次性的工作跑完了）保留。
- 目標容器的標記只在容器確定在跑時才附（同時附容器內的目錄 [CONTAINER_CWD]）。
"""
import os
import re
import shlex
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (TARGET_CONTAINER_MARKER, clip, fetch_container_logs, format_log_rows, inspect_container,  # noqa: E402
                            list_container_names, run_docker, tz_label, with_cwd_marker)

TIMEOUT_SECONDS = 120     # docker run -d 對本機已有的映像檔幾秒就完成；需要拉映像時較久
SETTLE_SECONDS = 2        # 建好後等幾秒確認還在跑
LOG_LINES = 15
USAGE = ("用法: scripts/docker_est_cmd.py <映像檔[:tag]> [--name 容器名稱] [--cmd \"要執行的指令\"] [--network 網路] [-e 變數=值]...\n"
         "  --name 省略：沒有 tag 的映像檔用映像檔名稱當容器名稱；有 tag 或路徑時一定要給 --name（英數字、_ . -，至少 2 個字）。\n"
         "  --cmd 省略：tail -f /dev/null（一直跑著）；含 && ; | $ source 等 shell 語法時自動包成 bash -lc \"…\"。\n"
         "  例：scripts/docker_est_cmd.py ros:humble-ros-core --name ros_box --network host -e ROS_DOMAIN_ID=15 --cmd \"sleep infinity\"")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]+$")
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_SYNTAX_RE = re.compile(r"&&|\|\||[;|<>$`*~(){}\n]|^\s*(source|\.|export|cd)\s")
UNSUPPORTED = {
    "-v": "掛載主機目錄", "--volume": "掛載主機目錄", "--mount": "掛載", "-p": "對外開 port", "--publish": "對外開 port",
    "-P": "對外開 port", "--publish-all": "對外開 port", "--gpus": "GPU", "--privileged": "特權模式", "--device": "主機的裝置",
    "--rm": "結束後自動刪除", "--restart": "重新啟動政策", "--entrypoint": "換 entrypoint", "-u": "指定使用者",
    "--user": "指定使用者", "-w": "工作目錄", "--workdir": "工作目錄", "--ipc": "IPC 設定", "--pid": "PID 設定",
    "--cap-add": "Linux capability", "--shm-size": "共享記憶體大小", "--runtime": "runtime", "--add-host": "hosts 設定",
    "-h": "主機名稱", "--hostname": "主機名稱", "-l": "標籤", "--label": "標籤", "-m": "記憶體上限", "--memory": "記憶體上限",
    "--cpus": "CPU 上限", "--env-file": "環境變數檔", "--platform": "平台", "--pull": "拉取政策",
}
IGNORED = {"-d", "--detach", "-i", "--interactive", "-t", "--tty", "-it", "-ti", "-itd", "-dit", "-td", "-dt", "-id", "-di"}


def parse(argv):
    """→ ({"image", "name", "cmd", "network", "env", "notes"}, None) 或 (None, [ERROR]…)。純函式（不查 docker）。"""
    o = {"image": "", "name": "", "cmd": "", "network": "", "env": [], "notes": []}
    extra = []
    i = 0
    while i < len(argv):
        a = argv[i]
        key, val = (a.split("=", 1) if a.startswith("--") and "=" in a else (a, None))
        if key == "--net":
            key = "--network"
        if key in ("--name", "--cmd", "--network", "-e", "--env"):
            if val is None:
                if i + 1 >= len(argv):
                    return None, f"[ERROR] {key} 後面需要值。這次沒有建立任何容器。\n{USAGE}"
                val, i = argv[i + 1], i + 2
            else:
                i += 1
            if key == "--name":
                o["name"] = val.strip()
            elif key == "--cmd":
                o["cmd"] = val.strip()
            elif key == "--network":
                o["network"] = val.strip()
            else:
                if not _ENV_RE.match(val):
                    return None, f"[ERROR] {key} 要寫成 變數=值（例如 -e ROS_DOMAIN_ID=42），收到 {val!r}。這次沒有建立任何容器。\n{USAGE}"
                o["env"].append(val)
            continue
        if key in UNSUPPORTED:
            return None, (f"[ERROR] docker_est 不支援 {key}（{UNSUPPORTED[key]}）。這次沒有建立任何容器。下一步：不需要就拿掉；"
                          f"一定要的話請使用者在主機上用 host_runcmd \"docker run …\" 建立（會先請使用者確認）。\n{USAGE}")
        if a in IGNORED:
            o["notes"].append(f"已略過 {a}（容器一律在背景跑；進去執行指令用 docker_runcmd）")
            i += 1
            continue
        if a.startswith("-"):
            return None, f"[ERROR] 不認識的選項 {a}（選項只有 --name、--cmd、--network、-e）。這次沒有建立任何容器。\n{USAGE}"
        if not o["image"]:
            o["image"] = a.strip()
        else:
            extra.append(a)
        i += 1
    image = o["image"]
    if not image:
        return None, f"[ERROR] 請提供映像檔名稱。下一步：先用 docker_images 看本機有哪些映像檔。\n{USAGE}"
    if re.search(r"\s", image):
        return None, f"[ERROR] 映像檔名稱不能有空白：{image!r}。\n{USAGE}"
    if extra:
        hint = ""
        if re.match(r"^\d+(\.\d+)*$", extra[0]) or extra[0] in ("latest", "jazzy", "humble", "iron", "rolling"):
            hint = f"（tag 要跟映像檔寫在一起：{image}:{extra[0]}）"
        else:
            hint = f"（要執行的指令用 --cmd \"{clip(' '.join(extra), 60)}\"）"
        return None, (f"[ERROR] 多了參數 {' '.join(extra)}{hint}：容器名稱用 --name、要執行的指令用 --cmd \"…\"。"
                      f"這次沒有建立任何容器。\n{USAGE}")
    if not o["name"]:
        if ":" in image or "/" in image or "@" in image:
            base = re.sub(r"[^A-Za-z0-9_.-]+", "_", image.split("@")[0].split("/")[-1]).strip("_.-")
            return None, (f"[ERROR] 映像檔 {image} 帶了 tag 或路徑，請用 --name 指定容器名稱（例如 --name {base or 'my_box'}）。"
                          f"這次沒有建立任何容器。\n{USAGE}")
        o["name"] = image
    if not _NAME_RE.match(o["name"]):
        return None, (f"[ERROR] 容器名稱「{o['name']}」不合法：只能用英數字、底線、點、減號，開頭要是英數字，至少 2 個字。"
                      f"這次沒有建立任何容器。\n{USAGE}")
    if o["cmd"]:
        try:
            shlex.split(o["cmd"])
        except ValueError as e:
            return None, f"[ERROR] --cmd 的引號不成對（{e}）：{o['cmd']!r}。這次沒有建立任何容器。\n{USAGE}"
    return o, None


def run_argv(cmd, shell="bash"):
    """--cmd → docker run 最後面的參數：省略＝tail -f /dev/null；有 shell 語法＝[bash, -lc, 指令]（沒有 bash 時 [sh, -c, 指令]）；
    其他照 shlex 拆開（exec 形式，跟 docker run 一樣）。回傳 (參數, 是否包了 shell)。"""
    if not cmd:
        return ["tail", "-f", "/dev/null"], False
    if _SHELL_SYNTAX_RE.search(cmd):
        return ([shell, "-lc", cmd] if shell == "bash" else ["sh", "-c", cmd]), True
    return shlex.split(cmd), False


def _remove(name):
    ok, _, _ = run_docker(["docker", "rm", "-f", name], 30, what=f"docker rm {name}")
    return ok


def _logs_block(name):
    rows, _ = fetch_container_logs(name, LOG_LINES)
    if not rows:
        return ["（沒有任何 log）"]
    return [f"## 最後的 log（{len(rows)} 行，2>＝stderr；時間＝本地時間 {tz_label()}）"] + format_log_rows(rows, False)


def _existing(name):
    """同名的容器已經存在 → [ERROR] 說明它的狀態與下一步；不存在回 None。"""
    names, err = list_container_names()
    if names is None:
        return err
    if name not in names:
        return None
    info, _ = inspect_container(name)
    st = (info or {}).get("State") or {}
    image = ((info or {}).get("Config") or {}).get("Image", "?")
    if st.get("Running"):
        return (f"[ERROR] 同名的容器 '{name}' 已經存在而且在跑（映像 {image}）。這次沒有建立任何容器。"
                f"下一步：要用它就 docker_open {name}；要新建一個請換 --name")
    status = st.get("Status", "?")
    return (f"[ERROR] 同名的容器 '{name}' 已經存在但沒有在跑（狀態 {status}，結束碼 {st.get('ExitCode')}，映像 {image}）。"
            f"這次沒有建立任何容器。下一步：要用它就 docker_ctl start {name}（會先請使用者確認）；要重建就換一個 --name，"
            f"或請使用者確認後先刪掉舊的（host_runcmd \"docker rm {name}\"）")


def execute(argv):
    o, err = parse(argv)
    if err:
        return err
    err = _existing(o["name"])
    if err:
        return err
    head = ["docker", "run", "-d", "--name", o["name"]] + (["--network", o["network"]] if o["network"] else [])
    for kv in o["env"]:
        head += ["-e", kv]
    notes = list(o["notes"])
    shell = "bash"
    what = f"以映像檔 '{o['image']}' 建立容器 '{o['name']}'"
    while True:
        tail_args, wrapped = run_argv(o["cmd"], shell)
        ok, out, err = run_docker(head + [o["image"]] + tail_args, TIMEOUT_SECONDS, what=what)
        if ok:
            break
        names, _ = list_container_names()
        leftover = bool(names) and o["name"] in names
        if leftover:
            _remove(o["name"])   # 這次建立、但沒有啟動成功的空殼：移除，不擋下一次重試
        if wrapped and shell == "bash" and 'exec: "bash"' in err and "executable file not found" in err:
            shell = "sh"
            notes.append("映像裡沒有 bash，--cmd 改用 sh -c 執行")
            continue
        return err + ("\n（已移除這次建立、沒有啟動成功的容器，沒有留下東西；修正後可以用同一個 --name 重試）" if leftover else "")
    container_id = out.strip()[:12]
    info = None
    for _ in range(SETTLE_SECONDS * 2):
        time.sleep(0.5)
        info, _ = inspect_container(o["name"])
        if not ((info or {}).get("State") or {}).get("Running"):
            break
    st = (info or {}).get("State") or {}
    cmd_text = " ".join(shlex.quote(a) for a in tail_args) if wrapped else " ".join(tail_args)
    desc = f"容器 '{o['name']}'（映像檔 {o['image']}，指令：{clip(cmd_text, 160)}" + (f"，網路 {o['network']}" if o["network"] else "") \
        + (f"，環境變數 {'、'.join(o['env'])}" if o["env"] else "") + f"，ID {container_id}）"
    note = ("\n（" + "；".join(notes) + "）") if notes else ""
    if st.get("Running"):
        cwd = ((info or {}).get("Config") or {}).get("WorkingDir") or "/"
        body = (f"[PASS] {desc}已在背景啟動，{SETTLE_SECONDS} 秒後確認還在跑；已設為目前的目標容器"
                f"（之後 docker_runcmd／ROS2_* 可省略容器名稱）。{note}\n{TARGET_CONTAINER_MARKER} {o['name']}")
        return with_cwd_marker(body, cwd)
    code = st.get("ExitCode")
    logs = _logs_block(o["name"])
    if st.get("Status") == "exited" and code == 0:
        return "\n".join([f"[PASS] {desc}已建立，但指令跑完就結束了（結束碼 0），容器停在 Exited、沒有設為目標容器。"
                          f"要一直跑著的容器用 --cmd \"sleep infinity\"（或省略 --cmd）。{note}"] + logs)
    removed = _remove(o["name"])
    gone = "已移除這次建立的容器（沒有留下東西；修正後可以用同一個 --name 重試）" if removed else f"移除失敗，容器 {o['name']} 還在"
    return "\n".join([f"[ERROR] {desc}啟動後 {SETTLE_SECONDS} 秒內就結束了（狀態 {st.get('Status', '?')}，結束碼 {code}）；{gone}。"
                      f"下一步：看下面的 log 修正 --cmd（指令找不到、參數錯、缺環境變數…）再建一次{note}"] + logs)


if __name__ == "__main__":
    try:
        print(execute(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] docker_est 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
