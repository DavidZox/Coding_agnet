"""docker_est：用映像檔建立並在背景啟動一個容器（docker run -d），成為目前的目標容器。

v2（2026-10，benchmark_study_3）：可以指定容器名稱（--name）與要執行的指令（--cmd），映像檔可以帶 tag（ubuntu:24.04）。
舊版容器名稱固定等於映像檔名稱、也不能帶 tag：實測使用者要「用 ubuntu:24.04 建一個叫 scratch_box 的容器」時，模型只能建出叫
ubuntu 的容器，再自己用 host_runcmd 補建、留下多餘的容器。參數不清楚（例如 tag 被拆成另一個參數）時先回錯誤、不建任何東西。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import run_docker, with_target_marker

# docker run -d 對本機已有的映像檔幾秒就完成；若需從 registry 拉取會久一點，
# 但仍需要上限，否則沒有網路時 Agent 會卡住。
TIMEOUT_SECONDS = 120
USAGE = ("用法: scripts/docker_est_cmd.py <映像檔[:tag]> [--name 容器名稱] [--cmd \"要執行的指令\"]\n"
         "  --name 省略：沒有 tag 的映像檔用映像檔名稱當容器名稱（ros2_humble → ros2_humble）；有 tag 時一定要給 --name。\n"
         "  --cmd 省略：tail -f /dev/null（讓容器一直跑著）。例：scripts/docker_est_cmd.py ubuntu:24.04 --name scratch_box --cmd \"sleep infinity\"")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def parse(argv):
    image, name, cmd, extra = "", "", "", []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--name", "--cmd"):
            if i + 1 >= len(argv):
                return None, f"[ERROR] {a} 後面需要值。\n{USAGE}"
            if a == "--name":
                name = argv[i + 1].strip()
            else:
                cmd = argv[i + 1].strip()
            i += 2
            continue
        if not image:
            image = a.strip()
        else:
            extra.append(a)
        i += 1
    if not image:
        return None, f"[ERROR] 請提供映像檔名稱。\n{USAGE}"
    if extra:
        hint = ""
        if re.match(r"^\d+(\.\d+)*$", extra[0]) or extra[0] in ("latest", "jazzy", "humble"):
            hint = f"（tag 要跟映像檔寫在一起：{image}:{extra[0]}）"
        return None, (f"[ERROR] 多了參數 {' '.join(extra)}{hint}：容器名稱用 --name、要執行的指令用 --cmd \"…\"。這次沒有建立任何容器。\n{USAGE}")
    if not name:
        if ":" in image or "/" in image:
            return None, f"[ERROR] 映像檔 {image} 帶了 tag 或路徑，請用 --name 指定容器名稱。這次沒有建立任何容器。\n{USAGE}"
        name = image
    if not _NAME_RE.match(name):
        return None, f"[ERROR] 容器名稱「{name}」只能用英數字、底線、點、減號。\n{USAGE}"
    return {"image": image, "name": name, "cmd": cmd}, None


def execute(argv):
    o, err = parse(argv)
    if err:
        return err
    import shlex
    run_cmd = shlex.split(o["cmd"]) if o["cmd"] else ["tail", "-f", "/dev/null"]
    cmd = ["docker", "run", "-d", "--name", o["name"], o["image"]] + run_cmd
    ok, out, err = run_docker(cmd, TIMEOUT_SECONDS, what=f"以映像檔 '{o['image']}' 建立容器 '{o['name']}'")
    if not ok:
        return err
    container_id = out.strip()[:12]
    ok2, state, _ = run_docker(["docker", "inspect", "-f", "{{.State.Status}}", o["name"]], 30, what="docker inspect")
    status = state.strip() if ok2 else "?"
    note = "" if status == "running" else f"；⚠️ 目前狀態是 {status}（指令執行完就結束了，要一直跑著可以用 --cmd \"sleep infinity\"）"
    # 新建的容器順理成章成為目前的目標容器（比照 docker_open），之後容器技能可省略名稱
    return with_target_marker(f"[PASS] 容器 '{o['name']}'（映像檔 {o['image']}，指令：{' '.join(run_cmd)}）已在背景啟動（ID: {container_id}），"
                              f"狀態：{status}{note}；已設為目前的目標容器。", o["name"])


if __name__ == "__main__":
    try:
        print(execute(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] docker_est 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
