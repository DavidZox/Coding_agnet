"""ROS2_domain_id：查看或設定容器裡的 ROS_DOMAIN_ID。

v2（2026-10-23）重寫：
- 查詢：同時列出「新開的 shell」（bash -ic：容器的環境變數＋~/.bashrc＋Workspace）的 domain、容器的環境變數、~/.bashrc 裡的設定，
  以及正在跑的 ROS 程序各自的 domain（pid、指令），並算出 ROS2_* 技能實際會用哪一個——兩邊不一樣時明說看不到節點、要怎麼辦。
  舊版把 $ROS_DOMAIN_ID 寫在外層 bash -c 的雙引號裡，查到的是外層 shell 的值；容器目前的目錄沒有 install/setup.bash 時還會
  回「沒有任何錯誤訊息」。
- 設定（set，會先請使用者確認）是交易式的：先備份 ~/.bashrc → 換掉 export ROS_DOMAIN_ID 那一行 → 開一個新的 shell 驗證 →
  不對就還原備份、回 [ERROR]（狀態沒有改變）。只影響之後新開的 shell（ROS2_* 技能、終端機）；正在跑的節點不受影響。
- 參數（parse_cli，純函式，guard 用 action 判斷）：[容器名稱] [get]｜[容器名稱] set <N>｜舊寫法 [容器名稱] <N>（＝set）。"""
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (ROS_SOURCE, WS_GLOB, clip, describe_failure, exec_in_container,  # noqa: E402
                            inspect_container, split_container_arg, with_target_marker, workspace_source)

TIMEOUT_SECONDS = 20
MAX_DOMAIN = 232
SAFE_DOMAIN = 101       # Linux 上建議的上限（更大的值算出來的 port 可能跟系統的臨時 port 衝突）
PROC_MAX = 20
USAGE = (
    "用法: scripts/ROS2_domain_id_cmd.py [容器名稱] [get]｜[容器名稱] set <0-232>\n"
    "  省略動作＝查詢（shell 與正在跑的節點各在哪個 domain）；set 寫入容器的 ~/.bashrc（會先請使用者確認），只影響之後新開的 shell。\n"
    "  容器名稱省略＝目前的目標容器。"
)
_SKIP_COMM = {"bash", "sh", "dash", "zsh", "timeout", "sleep", "tail", "cat", "tr", "sed", "grep", "cut", "ps", "head", "sort"}


def parse_cli(argv):
    """→ {"container_arg", "action"（get／set）, "domain"（int 或 None）, "error"}；不查 docker。"""
    res = {"container_arg": "", "action": "get", "domain": None, "error": None}
    args = [a.strip() for a in argv if a.strip()]
    if any(a.startswith("-") and not a.lstrip("-").isdigit() for a in args):
        bad = next(a for a in args if a.startswith("-"))
        return dict(res, error=f"[ERROR] 不認識的選項 {bad}（這個技能沒有選項）。\n{USAGE}")
    if args and args[0].lower() not in ("get", "set") and not args[0].lstrip("-").isdigit():
        res["container_arg"], args = args[0], args[1:]
    if args and args[0].lower() in ("get", "set"):
        res["action"], args = args[0].lower(), args[1:]
    elif args:
        res["action"] = "set"     # 舊寫法：[容器名稱] <N>
    if res["action"] == "get":
        if args:
            return dict(res, error=f"[ERROR] 查詢不需要其他參數，收到 {' '.join(args)}。\n{USAGE}")
        return res
    if len(args) != 1:
        return dict(res, error=f"[ERROR] set 後面要一個 domain（0～{MAX_DOMAIN} 的整數）。\n{USAGE}")
    try:
        dom = int(args[0])
    except ValueError:
        return dict(res, error=f"[ERROR] ROS_DOMAIN_ID 必須是整數（0～{MAX_DOMAIN}），收到 {args[0]!r}。\n{USAGE}")
    if not 0 <= dom <= MAX_DOMAIN:
        return dict(res, error=f"[ERROR] ROS_DOMAIN_ID 超出範圍（0～{MAX_DOMAIN}），收到 {dom}。\n{USAGE}")
    return dict(res, domain=dom)


def _shell_probe(container):
    """新開的互動式 shell（跟 ROS2_* 技能一樣載入 /opt/ros 與 Workspace，但不沿用節點的 domain）印出的 ROS_DOMAIN_ID。"""
    ws = workspace_source(container) or WS_GLOB
    return ROS_SOURCE + ws + 'printf "@@V%s@@\\n" "${ROS_DOMAIN_ID-}"'


def _probe_value_cmd(container):
    inner = shlex.quote(_shell_probe(container))
    return f"bash -ic {inner} 2>/dev/null </dev/null | sed -n 's/^.*@@V\\(.*\\)@@.*$/\\1/p' | tail -1"


QUERY_TAIL = (
    'grep -n "ROS_DOMAIN_ID" "$HOME/.bashrc" 2>/dev/null | head -5 | sed "s/^/@@RC|/"; '
    'for _p in /proc/[0-9]*; do _pid=${_p#/proc/}; [ "$_pid" = "$$" ] && continue; [ "$_pid" = "$PPID" ] && continue; '
    '_env=$(tr "\\0" "\\n" < "$_p/environ" 2>/dev/null) || continue; '
    'case "$_env" in *AMENT_PREFIX_PATH=*|*ROS_DOMAIN_ID=*) ;; *) continue;; esac; '
    '_cmd=$(tr "\\0" " " < "$_p/cmdline" 2>/dev/null | cut -c1-160); [ -n "$_cmd" ] || continue; '
    '_comm=$(cat "$_p/comm" 2>/dev/null); '
    '_dom=$(printf "%s\\n" "$_env" | sed -n "s/^ROS_DOMAIN_ID=//p" | head -1); '
    'printf "@@P|%s|%s|%s|%s\\n" "$_pid" "$_dom" "$_comm" "$_cmd"; done'
)


def query_command(container):
    return f'printf "@@SHELL|%s\\n" "$({_probe_value_cmd(container)})"; ' + QUERY_TAIL


def set_command(container, dom):
    probe = _probe_value_cmd(container)
    line = f"export ROS_DOMAIN_ID={dom}  # set by ROS2_domain_id"
    return (
        f'_old=$({probe}); printf "@@OLD|%s\\n" "$_old"; _f="$HOME/.bashrc"; '
        f'[ -e "$_f" ] || : > "$_f" || {{ echo "@@E|無法建立 $_f"; exit 3; }}; '
        f'cp -p "$_f" "$_f.cah_bak" || {{ echo "@@E|無法備份 $_f（沒有寫入權限？）"; exit 4; }}; '
        f'if sed -i "/^[[:space:]]*export[[:space:]]\\+ROS_DOMAIN_ID=/d" "$_f" && '
        f'{{ [ ! -s "$_f" ] || [ -z "$(tail -c1 "$_f")" ] || echo >> "$_f"; }} && echo {shlex.quote(line)} >> "$_f"; then :; '
        f'else cp -p "$_f.cah_bak" "$_f"; rm -f "$_f.cah_bak"; echo "@@E|寫入 $_f 失敗"; exit 5; fi; '
        f'_got=$({probe}); '
        f'if [ "$_got" = "{dom}" ]; then rm -f "$_f.cah_bak"; echo "@@OK|$_got"; '
        f'else cp -p "$_f.cah_bak" "$_f"; rm -f "$_f.cah_bak"; echo "@@FAIL|$_got"; exit 6; fi; ' + QUERY_TAIL
    )


def parse_probe(out):
    data = {"shell": None, "old": None, "rc": [], "procs": [], "ok": None, "fail": None, "err": None}
    for ln in (out or "").splitlines():
        if ln.startswith("@@SHELL|"):
            data["shell"] = ln.split("|", 1)[1].strip()
        elif ln.startswith("@@OLD|"):
            data["old"] = ln.split("|", 1)[1].strip()
        elif ln.startswith("@@RC|"):
            data["rc"].append(ln.split("|", 1)[1].strip())
        elif ln.startswith("@@OK|"):
            data["ok"] = ln.split("|", 1)[1].strip()
        elif ln.startswith("@@FAIL|"):
            data["fail"] = ln.split("|", 1)[1].strip()
        elif ln.startswith("@@E|"):
            data["err"] = ln.split("|", 1)[1].strip()
        elif ln.startswith("@@P|"):
            parts = (ln.split("|", 4) + [""] * 5)[1:5]
            pid, dom, comm, cmd = (p.strip() for p in parts)
            if comm in _SKIP_COMM or not cmd:
                continue
            data["procs"].append({"pid": pid, "domain": dom, "comm": comm, "cmd": cmd,
                                  "daemon": "ros2-daemon" in cmd or "_ros2_daemon" in cmd or "ros2cli.daemon" in cmd})
    data["procs"].sort(key=lambda p: int(p["pid"]) if p["pid"].isdigit() else 0)
    return data


def _rc_text(r):
    """grep -n 的「101:export ROS_DOMAIN_ID=7」→「第 101 行 export ROS_DOMAIN_ID=7」。"""
    no, _, text = r.partition(":")
    return f"第 {no} 行 {clip(text.strip(), 100)}" if no.isdigit() else clip(r, 100)


def _d(v):
    return v if v not in (None, "") else "0（沒有設定，用預設值）"


def domain_report(container, data, env_dom, header=None):
    """查詢的內容（set 成功後也附上）：shell 的設定與正在跑的 ROS 程序。回傳 (第一行的結論, 各節的行)。"""
    shell = data.get("shell") if data.get("shell") is not None else data.get("ok")
    nodes = [p for p in data["procs"] if not p["daemon"]]
    node_doms = sorted({p["domain"] or "0" for p in nodes})
    # 跟 ros2_env_prefix 一樣：shell 沒有設定時沿用 /proc 裡第一個（字典順序）帶 ROS_DOMAIN_ID 的程序
    copy_from = next((p["domain"] for p in sorted(data["procs"], key=lambda p: p["pid"]) if p["domain"]), "")
    skill = shell if shell else (copy_from or "0")
    rc_lines = data["rc"]
    lines = ["## shell 的設定（3 項）",
             f"新開的 shell（bash -ic，含 ~/.bashrc 與 Workspace）：{_d(shell)}",
             f"容器的環境變數（docker run -e／映像的 ENV）：{_d(env_dom)}",
             "~/.bashrc：" + ("；".join(_rc_text(r) for r in rc_lines) if rc_lines else "沒有設定 ROS_DOMAIN_ID")]
    if data["procs"]:
        lines.append(f"## 正在跑的 ROS 程序（{len(data['procs'])} 個" + (f"，只列前 {PROC_MAX} 個" if len(data["procs"]) > PROC_MAX else "") + "）")
        for p in data["procs"][:PROC_MAX]:
            tag = "（ros2 daemon：ros2 CLI 的探索快取）" if p["daemon"] else ""
            lines.append(f"pid {p['pid']:<6} domain {(p['domain'] or '0'):<4} {clip(p['cmd'], 140)}{tag}")
    else:
        lines.append("## 正在跑的 ROS 程序（0 個）")
        lines.append("（沒有找到：節點可能在別的容器、還沒啟動，或用不同的使用者執行）")
    if not nodes:
        concl = f"新開的 shell＝{_d(shell)}；沒有找到正在跑的 ROS 節點；ROS2_* 技能會用 {skill}"
    elif len(node_doms) == 1:
        concl = f"新開的 shell＝{_d(shell)}；正在跑的 ROS 節點都在 {node_doms[0]}（{len(nodes)} 個）；ROS2_* 技能會用 {skill}"
    else:
        counts = "、".join(f"{d}：{sum(1 for p in nodes if (p['domain'] or '0') == d)} 個" for d in node_doms)
        concl = f"新開的 shell＝{_d(shell)}；正在跑的 ROS 節點分在不同的 domain（{counts}）；ROS2_* 技能會用 {skill}"
    if nodes and skill not in node_doms:
        target = node_doms[0]
        concl += (f"。注意：技能用的 {skill} 跟節點的 {'／'.join(node_doms)} 不同，ROS2_* 技能看不到這些節點。"
                  f"下一步：ROS2_domain_id set {target}（寫入 ~/.bashrc，會先請使用者確認），或請使用者確認節點該在哪個 domain")
    return concl, lines


def _env_domain(container):
    info, _ = inspect_container(container)
    for kv in ((info or {}).get("Config") or {}).get("Env") or []:
        if kv.startswith("ROS_DOMAIN_ID="):
            return kv.split("=", 1)[1]
    return ""


def run_domain_id(container, action="get", dom=None):
    what = f"容器 '{container}' 的 ROS_DOMAIN_ID"
    if action == "get":
        res = exec_in_container(container, query_command(container), TIMEOUT_SECONDS, need_bash=True)
        if res["kind"] != "ok":
            return describe_failure(res, f"查詢{what}", TIMEOUT_SECONDS, container=container)
        data = parse_probe(res["out"])
        concl, lines = domain_report(container, data, _env_domain(container))
        return with_target_marker("\n".join([f"[PASS] {what}：{concl}"] + lines), container)
    res = exec_in_container(container, set_command(container, dom), TIMEOUT_SECONDS + 10, need_bash=True)
    data = parse_probe(res.get("out"))
    if res["kind"] in ("launch_error", "host_timeout", "timeout", "killed"):
        return describe_failure(res, f"設定{what}", TIMEOUT_SECONDS + 10, container=container) + \
            "\n（逾時發生在寫入前或驗證中：~/.bashrc 可能留有備份 ~/.bashrc.cah_bak，請用 docker_runcmd 確認）"
    old = data.get("old")
    if data.get("err"):
        return (f"[ERROR] 設定{what}失敗：{data['err']}；~/.bashrc 沒有改變（原本新開的 shell＝{_d(old)}）。"
                f"下一步：用 docker_runcmd \"ls -l ~/.bashrc; id\" 看權限；沒有寫入權限就請使用者處理")
    if data.get("fail") is not None or res["kind"] != "ok":
        got = data.get("fail")
        return (f"[ERROR] 已把 ~/.bashrc 改成 export ROS_DOMAIN_ID={dom}，但新開的 shell 驗證出來是 {_d(got)}："
                f"~/.bashrc 後面的設定、/etc/bash.bashrc 或 Workspace 又設了別的值；已還原 ~/.bashrc，狀態沒有改變"
                f"（仍是 {_d(old)}）。下一步：docker_runcmd \"grep -n ROS_DOMAIN_ID ~/.bashrc /etc/bash.bashrc\" 找是誰設的，"
                f"告訴使用者")
    concl, lines = domain_report(container, dict(data, shell=data.get("ok")), _env_domain(container))
    nodes = [p for p in data["procs"] if not p["daemon"]]
    warn = f"注意：{dom} 大於 {SAFE_DOMAIN}，Linux 上可能跟系統的臨時 port 衝突。" if dom > SAFE_DOMAIN else ""
    running = ""
    if nodes:
        doms = sorted({p["domain"] or "0" for p in nodes})
        if doms != [str(dom)]:
            running = (f"正在跑的節點不受影響（仍在 {'／'.join(doms)}）——這是正常的：ROS2_* 技能用 {dom} 看得到 domain {dom} 的節點。"
                       f"要讓這些節點也換 domain 只能重啟它們或整個容器（容器的環境變數也要改），會中斷容器裡正在跑的服務："
                       f"只有使用者明確要求才做，不要為了讀到別的 domain 的訊息而重啟。")
    head = (f"[PASS] 已把{what} 設成 {dom}：寫入 ~/.bashrc（export ROS_DOMAIN_ID={dom}），新開的 shell 驗證是 {data.get('ok')}"
            f"（原本 {_d(old)}）。之後的 ROS2_* 技能與新開的終端機用 {dom}；docker_runcmd 的 bash -c 不讀 ~/.bashrc。{running}{warn}")
    return with_target_marker("\n".join([head] + lines), container)


def main(argv):
    p = parse_cli(argv)
    if p["error"]:
        return p["error"]
    container, _rest, err = split_container_arg([p["container_arg"]] if p["container_arg"] else [], USAGE,
                                                must=bool(p["container_arg"]))
    if err:
        return err
    return run_domain_id(container, p["action"], p["domain"])


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] ROS2_domain_id 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
