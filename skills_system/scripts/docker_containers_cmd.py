"""docker_containers：列出主機上的容器（docker ps -a），第一行算好總數與各狀態的數量。

狀態以 docker 的 {{.State}} 判斷（running／paused／restarting／exited／created／dead）：暫停的容器 STATUS 也是「Up … (Paused)」，
不能用字頭 Up 當作執行中（暫停中不能執行指令）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import format_table, run_docker  # noqa: E402

TIMEOUT_SECONDS = 15   # docker ps 通常一秒內完成；超過代表 daemon 無回應
USAGE = (
    "用法: scripts/docker_containers_cmd.py [--running] [keyword]\n"
    "  --running：只列執行中的容器（預設含已停止的）。\n"
    "  keyword：以子字串過濾容器名稱（不分大小寫），只能給一個。"
)
FORMAT = "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.ID}}\t{{.State}}"
HEADERS = ("NAME", "STATUS", "IMAGE", "CONTAINER ID")
STATE_LABELS = (("running", "運行中"), ("paused", "暫停"), ("restarting", "不斷重啟"), ("exited", "已停止"),
                ("created", "建立後沒啟動過"), ("dead", "dead"))


def parse_args(argv):
    """回傳 (running_only, keyword, error_message)。"""
    running_only = False
    keyword = ""
    for arg in argv:
        if arg == "--running":
            running_only = True
        elif arg.startswith("-"):
            return None, None, f"[ERROR] 不支援的選項: {arg}（選項只有 --running）\n{USAGE}"
        elif keyword:
            return None, None, f"[ERROR] 關鍵字只能有一個，收到: {keyword!r} 與 {arg!r}\n{USAGE}"
        else:
            keyword = arg
    return running_only, keyword, None


def summarize(rows, states):
    """各狀態的數量 → 「運行中 2 個、暫停 1 個、已停止 3 個」（運行中一定列，其他有才列）。"""
    counts = {}
    for st in states:
        counts[st] = counts.get(st, 0) + 1
    parts = [f"運行中 {counts.get('running', 0)} 個"]
    parts += [f"{label} {counts[st]} 個" for st, label in STATE_LABELS[1:] if counts.get(st)]
    return "、".join(parts)


def execute(running_only=False, keyword=""):
    cmd = ["docker", "ps", "--format", FORMAT]
    if not running_only:
        cmd.insert(2, "-a")
    ok, out, err = run_docker(cmd, TIMEOUT_SECONDS, what="查詢容器清單 (docker ps)")
    if not ok:
        return err
    rows, states = [], []
    for ln in out.splitlines():
        if not ln.strip():
            continue
        cols = ln.split("\t")
        cols += [""] * (len(HEADERS) + 1 - len(cols))
        if keyword and keyword.lower() not in cols[0].lower():
            continue
        rows.append(tuple(cols[:len(HEADERS)]))
        states.append(cols[len(HEADERS)].strip().lower())
    scope = "執行中的容器" if running_only else "容器（含已停止）"
    filt = f"，名稱含 '{keyword}'" if keyword else ""
    if not rows:
        hint = "（不加關鍵字可列出全部）" if keyword else ""
        return f"[PASS] 目前沒有任何{scope}{filt}{hint}。"
    note = ""
    if "paused" in states:
        note = "\n（暫停的容器不能執行指令：請使用者確認後在主機上 docker unpause）"
    return f"[PASS] {scope}{filt}：共 {len(rows)} 個，{summarize(rows, states)}\n{format_table(rows, HEADERS)}{note}"


if __name__ == "__main__":
    try:
        running_only, keyword, err = parse_args(sys.argv[1:])
        if err:
            print(err)
            sys.exit(0)
        print(execute(running_only, keyword))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] docker_containers 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
