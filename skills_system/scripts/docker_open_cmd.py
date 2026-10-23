"""docker_open：找出容器真實名稱、確認它在跑、驗證連線，並把它設為目前的目標容器。

「目標容器」跟當前工作目錄是同一套機制（見 _docker_common 檔尾）：成功後輸出最後幾行印 [TARGET_CONTAINER] <真實名稱>
與容器內的目錄（[CONTAINER_CWD]，docker_runcmd 從這裡開始），harness 同步狀態，之後 docker_runcmd／ROS2_*／docker_ctl 可省略
容器名稱。要換容器就再用一次 docker_open。名稱比對：完全相同 > 不分大小寫相同 > 唯一的部分名稱；對到好幾個不猜。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (TARGET_CONTAINER_MARKER, describe_failure, exec_in_container, inspect_container,  # noqa: E402
                            lookup_container, with_cwd_marker)

EXEC_TIMEOUT_SECONDS = 15   # docker exec 驗證連線
USAGE = "用法: scripts/docker_open_cmd.py <容器名稱>（可以是部分名稱，不分大小寫；剛好對到一個容器才會用它）"


def find_container(display_name, names=None):
    """在所有容器（含未運行）中找出真實名稱。回傳 (real_name, error_message)。"""
    return lookup_container(display_name, names, partial=True)


def enter_container(target_name, names=None):
    target_name = (target_name or "").strip()
    if not target_name:
        return f"[ERROR] 請提供容器名稱（可為部分名稱）。下一步：不知道名稱就先用 docker_containers 查。\n{USAGE}"
    real_name, err = find_container(target_name, names)
    if err:
        return err
    info, err = inspect_container(real_name)
    if err:
        return err
    st = info.get("State") or {}
    status = st.get("Status", "?")
    if st.get("Paused"):
        return (f"[ERROR] 容器 '{real_name}' 被暫停（paused），不能進入。下一步：請使用者確認後在主機上 docker unpause {real_name}"
                f"（host_runcmd，會先請使用者確認），再 docker_open {real_name}")
    if not st.get("Running") or st.get("Restarting"):
        why = "一直在重新啟動（啟動後馬上結束）" if st.get("Restarting") else f"沒有在運行（狀態 {status}，結束碼 {st.get('ExitCode')}）"
        return (f"[ERROR] 容器 '{real_name}' {why}，不能進入。下一步：docker_ctl status {real_name} 看原因；"
                f"使用者同意後 docker_ctl start {real_name}（會先請使用者確認），再 docker_open {real_name}")
    res = exec_in_container(real_name, "pwd; id -un 2>/dev/null || id -u", EXEC_TIMEOUT_SECONDS)
    if res["kind"] != "ok":
        return describe_failure(res, f"連線至容器 '{real_name}'", EXEC_TIMEOUT_SECONDS, container=real_name)
    lines = [ln.strip() for ln in (res["out"] or "").splitlines() if ln.strip()]
    cwd = lines[0] if lines else "/"
    user = lines[1] if len(lines) > 1 else "?"
    image = (info.get("Config") or {}).get("Image", "?")
    note = f"（「{target_name}」＝容器 {real_name}）" if real_name != target_name else ""
    body = (f"[PASS] 已成功連線至 '{real_name}'，並設為目前的目標容器{note}：執行中，映像 {image}；容器內目錄 {cwd}，使用者 {user}"
            + ("（容器裡沒有 bash，指令會用 sh 執行）" if res.get("shell") == "sh" else "") + "。\n"
            f"之後 docker_runcmd／ROS2_*／docker_ctl 可省略容器名稱（docker_runcmd 從 {cwd} 開始）；要換容器再用一次 docker_open。\n"
            f"{TARGET_CONTAINER_MARKER} {real_name}")
    return with_cwd_marker(body, cwd)


def main(argv):
    args = [a for a in argv if a.strip()]
    if len(args) > 1:
        return (f"[ERROR] docker_open 只接受一個容器名稱，收到 {len(args)} 個：{'、'.join(map(repr, args))}。"
                f"下一步：只給一個名稱；要在容器裡執行指令用 docker_runcmd。\n{USAGE}")
    return enter_container(args[0] if args else "")


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] docker_open 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
