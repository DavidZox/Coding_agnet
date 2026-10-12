"""docker_ctl：容器本身的狀態與控制——看狀態、看 log、看設定（環境變數、掛載、網路）、啟動、停止、重新啟動。

docker_runcmd 是在容器「裡面」執行指令；這個技能操作的是容器本身（等同主機上的 docker start／stop／logs／inspect）。
start／stop／restart 會改變狀態，執行前由 harness 請使用者確認；status／logs／inspect／env 是唯讀的，直接執行。
啟動或重新啟動之後會等 2 秒、回報新的狀態與最後幾行 log（容器一啟動就結束時看得到原因）。

容器名稱可省略＝目前的目標容器；名稱不完整時，只有剛好對到一個容器才用它（對到好幾個就列出來請使用者指定）。
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import current_target_container, list_container_names, run_docker, with_target_marker  # noqa: E402

USAGE = ("用法: scripts/docker_ctl_cmd.py <status|logs|inspect|env|start|stop|restart> [容器名稱] [--tail N] [--grep 關鍵字]\n"
         "  status：狀態（Up／Exited 與結束碼、啟動與結束時間、映像）；logs：最後 N 行 log（預設 40，--grep 只看含關鍵字的行）；\n"
         "  inspect：映像、指令、環境變數、掛載、網路、port；env：環境變數（--grep 篩選）；start／stop／restart：會先請使用者確認。\n"
         "  容器名稱可省略＝目前的目標容器。")
ACTIONS = ("status", "logs", "inspect", "env", "start", "stop", "restart")
TIMEOUT = 60


def _parse(argv):
    if not argv or argv[0] not in ACTIONS:
        return None, f"[ERROR] 第一個參數要是動作（{'／'.join(ACTIONS)}）。\n{USAGE}"
    opts = {"action": argv[0], "container": "", "tail": 40, "grep": None}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ("--tail", "--grep") and i + 1 < len(argv):
            if a == "--tail":
                if not argv[i + 1].isdigit():
                    return None, f"[ERROR] --tail 後面要是行數。\n{USAGE}"
                opts["tail"] = max(1, min(500, int(argv[i + 1])))
            else:
                opts["grep"] = argv[i + 1]
            i += 2
            continue
        if not opts["container"]:
            opts["container"] = a
        i += 1
    return opts, None


def _resolve(name):
    names, err = list_container_names()
    if names is None:
        return None, err or "[ERROR] 查不到容器清單（docker 沒有回應）"
    name = (name or "").strip() or current_target_container()
    if not name:
        return None, "[ERROR] 沒有指定容器，也沒有目標容器。先用 docker_containers 看有哪些容器，再指定名稱。"
    if name in names:
        return name, None
    hits = [n for n in names if name.lower() in n.lower()]
    if len(hits) == 1:
        return hits[0], None
    if hits:
        return None, f"[ERROR] 「{name}」對到好幾個容器：{'、'.join(hits)}。請指定完整名稱（或先問使用者是哪一個）。"
    return None, f"[ERROR] 沒有叫「{name}」的容器。現有的容器：{'、'.join(names) or '（沒有）'}"


def _inspect(name):
    ok, out, err = run_docker(["docker", "inspect", name], TIMEOUT, what=f"docker inspect {name}")
    if not ok:
        return None, err
    try:
        return json.loads(out)[0], None
    except (ValueError, IndexError):
        return None, f"[ERROR] docker inspect {name} 的輸出看不懂"


def _state_line(info):
    st = info.get("State", {})
    if st.get("Running"):
        return f"Up（執行中，{st.get('StartedAt', '')[:19].replace('T', ' ')} 啟動）"
    status = st.get("Status", "?")
    return (f"{status}（結束碼 {st.get('ExitCode')}，{st.get('FinishedAt', '')[:19].replace('T', ' ')} 結束）"
            + (f"；錯誤：{st['Error']}" if st.get("Error") else ""))


def _logs(name, tail, grep=None):
    ok, out, err = run_docker(["docker", "logs", "--tail", str(tail if not grep else max(tail, 500)), name], TIMEOUT,
                              what=f"docker logs {name}")
    text = out if ok else err
    lines = [ln for ln in (text or "").splitlines()]
    if grep:
        hit = [ln for ln in lines if grep.lower() in ln.lower()]
        return hit, len(lines)
    return lines[-tail:], len(lines)


def main(argv):
    opts, err = _parse(argv)
    if err:
        return err
    name, err = _resolve(opts["container"])
    if err:
        return err
    act = opts["action"]
    if act in ("start", "stop", "restart"):
        before, err = _inspect(name)
        if err:
            return err
        cmd = ["docker", act] + (["-t", "5"] if act in ("stop", "restart") else []) + [name]
        ok, out, err = run_docker(cmd, TIMEOUT + 30, what=f"docker {act} {name}")
        if not ok:
            return err
        time.sleep(2)
        after, err = _inspect(name)
        if err:
            return err
        logs, _ = _logs(name, 8)
        verb = {"start": "啟動", "stop": "停止", "restart": "重新啟動"}[act]
        out = (f"[PASS] 已{verb} {name}：{_state_line(before)} → {_state_line(after)}\n"
               + ("最後幾行 log：\n" + "\n".join(logs) if logs and act != "stop" else ""))
        return with_target_marker(out.rstrip(), name)
    info, err = _inspect(name)
    if err:
        return err
    cfg = info.get("Config", {})
    if act == "status":
        out = (f"[PASS] {name}：{_state_line(info)}\n- 映像：{cfg.get('Image')}\n- 指令：{' '.join(cfg.get('Cmd') or [])[:200]}\n"
               f"- 重新啟動次數：{info.get('RestartCount', 0)}；建立時間：{info.get('Created', '')[:19].replace('T', ' ')}")
        return with_target_marker(out, name)
    if act == "logs":
        lines, total = _logs(name, opts["tail"], opts["grep"])
        if opts["grep"]:
            head = (f"[PASS] {name} 最近 {total} 行 log 裡，含「{opts['grep']}」的有 {len(lines)} 行"
                    + (f"；最後一行：{lines[-1][:200]}" if lines else ""))
            return with_target_marker(head + ("\n" + "\n".join(lines[-opts["tail"]:]) if lines else ""), name)
        return with_target_marker(f"[PASS] {name} 最後 {len(lines)} 行 log（狀態：{_state_line(info)}）：\n" + "\n".join(lines), name)
    env = cfg.get("Env") or []
    if act == "env":
        shown = [e for e in env if not opts["grep"] or opts["grep"].lower() in e.lower()]
        return with_target_marker(f"[PASS] {name} 的環境變數（{len(shown)} 個" + (f"，含「{opts['grep']}」" if opts["grep"] else "")
                                  + "）：\n" + "\n".join(shown), name)
    mounts = [f"{m.get('Source')} → {m.get('Destination')}（{'唯讀' if not m.get('RW') else '可寫'}）" for m in info.get("Mounts") or []]
    nets = info.get("HostConfig", {}).get("NetworkMode")
    ports = info.get("NetworkSettings", {}).get("Ports") or {}
    out = (f"[PASS] {name}：{_state_line(info)}\n- 映像：{cfg.get('Image')}\n- 指令：{' '.join(cfg.get('Cmd') or [])[:300]}\n"
           f"- 工作目錄：{cfg.get('WorkingDir') or '/'}\n- 網路：{nets}；port：{', '.join(f'{k}→{v}' for k, v in ports.items() if v) or '（沒有對外）'}\n"
           f"- 掛載：{'；'.join(mounts) or '（沒有）'}\n- 環境變數（{len(env)} 個）：\n  " + "\n  ".join(env[:40]))
    return with_target_marker(out, name)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] docker_ctl 未預期的例外：{e}")
