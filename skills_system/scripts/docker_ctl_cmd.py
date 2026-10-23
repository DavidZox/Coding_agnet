"""docker_ctl：容器本身的狀態與控制——看狀態、看 log、看設定（環境變數、掛載、網路）、啟動、停止、重新啟動。

docker_runcmd 是在容器「裡面」執行指令；這個技能操作的是容器本身（等同主機上的 docker start／stop／logs／inspect）。
start／stop／restart 會改變狀態，執行前由 harness 請使用者確認；status／logs／inspect／env 是唯讀的（parse_args 回 readonly）。

- logs：stdout 與 stderr 都收（`docker logs -t`，依時間合併；非 TTY 的容器 ROS 2 的 log 與 Python 的 traceback 都在 stderr），
  時間換成主機的本地時間並標時區；--since／--until 取一段時間（最後一行附「下次接著看」的 --since 游標，心跳可以接著看新的）；
  行數多（超過 DEDUP_AUTO）或加 --dedup 時用 _ros2_data_common 的 parse_log_lines＋dedup_events 整理成唯一訊號
  （ROS 的 [LEVEL] [秒] [node]、launch 的 [talker-1]、Python traceback 合成一則 ERROR），再附最後幾行原文。
- 啟動或重新啟動之後等 START_WAIT 秒、回報新的狀態與這次啟動以來的 log（一啟動就結束時看得到原因）。
- 容器名稱可省略＝目前的目標容器（只認完全相同的名稱：舊的目標不見了不會改去操作名稱相近的別的容器）；
  有寫名稱時，不分大小寫、只寫部分名稱而剛好對到一個也可以（對到好幾個就列出來請使用者指定）。
- 目標容器的標記只在容器操作後是執行中時才附（停掉的容器不會變成目標）。
"""
import datetime
import os
import re
import shlex
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _docker_common import (MAX_LOG_FETCH, clean_log_line, clip, current_target_container, existing_list_text,  # noqa: E402
                            fetch_container_logs, fmt_log_time, format_log_rows, human_duration, inspect_container,
                            list_container_names, local_time, log_multi_day, lookup_container, neutralize_markers,
                            parse_docker_time, run_docker, strip_ansi, tz_label, with_target_marker)

ACTIONS = ("status", "logs", "inspect", "env", "start", "stop", "restart")
READONLY_ACTIONS = ("status", "logs", "inspect", "env")
DEFAULT_TAIL = 40
MAX_FETCH = MAX_LOG_FETCH  # logs 一次最多取幾行
GREP_SCAN = 5000          # --grep 掃描最後幾行（或 --since 之後的，同樣上限）
DEDUP_AUTO = 80           # 取得的行數超過這個數（沒有 --raw）就自動整理成唯一訊號
RAW_WITH_DEDUP = 30       # 整理成唯一訊號時，附的最後幾行原文
SIGNALS_MAX = 40          # 唯一訊號最多列幾個
INSPECT_ENV_MAX = 40
ENV_MAX = 300
TIMEOUT = 60
STOP_WAIT = 10            # docker stop／restart 等程式自己結束的秒數（之後 KILL）
START_WAIT = 2            # start／restart 後等幾秒再看狀態
AFTER_START_LOG_LINES = 20

USAGE = ("用法: scripts/docker_ctl_cmd.py <status|logs|inspect|env|start|stop|restart> [容器名稱] [選項]\n"
         f"  logs 的選項：--tail N（預設 {DEFAULT_TAIL}，上限 {MAX_FETCH}）、--since 時間／--until 時間（10m、2h、14:05、"
         "2026-10-23T14:05:00、上次輸出的游標）、--grep 關鍵字（不分大小寫，可重複＝任一個）、--dedup（整理成唯一訊號）、--raw（不整理）。\n"
         "  env 的選項：--grep 關鍵字。容器名稱省略＝目前的目標容器。start／stop／restart 會先請使用者確認。")

EXIT_MEANINGS = {
    0: "正常結束，指令跑完了", 1: "程式自己回報錯誤", 2: "參數或用法錯誤", 125: "docker 無法執行這個容器",
    126: "指令不能執行（權限或不是執行檔）", 127: "找不到要執行的指令", 130: "被 Ctrl-C（SIGINT）中斷",
    134: "程式異常中止（SIGABRT）", 137: "被 SIGKILL 強制終止（記憶體不足 OOM，或 docker stop 等太久）",
    139: "程式存取記憶體錯誤（SIGSEGV）", 143: "被 SIGTERM 終止（docker stop 或關機）",
}
_OPT_ACTIONS = {"--tail": ("logs",), "--since": ("logs",), "--until": ("logs",), "--dedup": ("logs",), "--raw": ("logs",),
                "--grep": ("logs", "env")}


# ---------------------------------------------------------------- 參數
def parse_time_arg(text, now=None):
    """--since／--until 的值 → docker 認得的寫法；看不懂回 (None, 錯誤)。認得：epoch 秒、10m／2h／1h30m、今天的 14:05[:30]、
    MM-DD HH:MM:SS（輸出裡的寫法，今年）、2026-10-23[T| ]14:05:00[.ns][Z|+08:00]（沒有時區＝本地時間）。"""
    s = (text or "").strip()
    now = now or datetime.datetime.now()
    if re.fullmatch(r"\d{9,}(\.\d+)?", s):
        return s, None
    if re.fullmatch(r"(\d+(\.\d+)?(ns|us|ms|s|m|h))+", s):
        return s, None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if m:
        dt = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=int(m.group(3) or 0), microsecond=0)
        return dt.strftime("%Y-%m-%dT%H:%M:%S"), None
    m = re.fullmatch(r"(\d{2})-(\d{2}) (\d{1,2}):(\d{2}):(\d{2})(\.\d+)?", s)
    if m:
        return f"{now.year}-{m.group(1)}-{m.group(2)}T{int(m.group(3)):02d}:{m.group(4)}:{m.group(5)}{m.group(6) or ''}", None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?", s):
        return s.replace(" ", "T"), None
    return None, (f"[ERROR] 看不懂的時間「{s}」。下一步：用 10m／2h（多久以前）、14:05（今天）、2026-10-23T14:05:00，"
                  f"或上一次輸出最後的 --since 游標。\n{USAGE}")


def parse_args(argv, target=None, names=None):
    """docker_ctl 的參數 → {"action", "container"（真實名稱）, "container_arg", "readonly", "tail", "since", "until", "grep"（清單）,
    "dedup", "raw", "notes", "error", "error_kind"}。target：目前的目標容器（None＝讀環境變數；""＝沒有）；names：現有容器的名稱清單
    （None＝向 docker 查）。guard 用 readonly 判斷要不要確認、用 container 顯示實際會操作的容器。error 不是 None 時不要執行；
    error_kind：usage（參數本身的問題）、container（對不到容器，跟 docker 的現況有關）、docker（查不到容器清單）。"""
    res = {"action": None, "container": None, "container_arg": "", "readonly": False, "tail": None, "since": None, "until": None,
           "grep": [], "dedup": False, "raw": False, "notes": [], "error": None, "error_kind": "usage"}
    args = [a for a in argv if a != ""]
    if args and args[0].lower() not in ACTIONS and len(args) > 1 and args[1].lower() in ACTIONS:
        args[0], args[1] = args[1], args[0]          # 「docker_ctl nav2 status」：動作寫在第二個
    if not args or args[0].lower() not in ACTIONS:
        got = f"（收到 {args[0]!r}）" if args else ""
        return dict(res, error=f"[ERROR] 第一個參數要是動作：{'／'.join(ACTIONS)}{got}。\n{USAGE}")
    act = args[0].lower()
    res.update(action=act, readonly=act in READONLY_ACTIONS)
    positional, used = [], []
    i = 1
    while i < len(args):
        a = args[i]
        key, val = (a.split("=", 1) + [None])[:2] if a.startswith("--") and "=" in a else (a, None)
        if key in ("-n",):
            key = "--tail"
        if key in ("--dedup", "--raw"):
            res[key[2:]] = True
            used.append(key)
            i += 1
            continue
        if key in ("--tail", "--since", "--until", "--grep"):
            if val is None:
                if i + 1 >= len(args):
                    return dict(res, error=f"[ERROR] {key} 後面需要值。\n{USAGE}")
                val, i = args[i + 1], i + 2
            else:
                i += 1
            used.append(key)
            if key == "--tail":
                if not str(val).isdigit() or int(val) < 1:
                    return dict(res, error=f"[ERROR] --tail 後面要是正整數的行數，收到 {val!r}。\n{USAGE}")
                if int(val) > MAX_FETCH:
                    res["notes"].append(f"--tail {val} 超過上限，只取最後 {MAX_FETCH} 行")
                res["tail"] = min(MAX_FETCH, int(val))
            elif key == "--grep":
                res["grep"].append(val)
            else:
                t, err = parse_time_arg(val)
                if err:
                    return dict(res, error=err)
                res[key[2:]] = t
            continue
        if a.startswith("-"):
            return dict(res, error=f"[ERROR] 不認識的選項 {a}（選項只有 --tail、--since、--until、--grep、--dedup、--raw）。\n{USAGE}")
        positional.append(a)
        i += 1
    if len(positional) > 1:
        return dict(res, error=(f"[ERROR] 只接受一個容器名稱，收到 {'、'.join(map(repr, positional))}。"
                                f"要過濾 log 用 --grep 關鍵字。\n{USAGE}"))
    for key in dict.fromkeys(used):
        if act not in _OPT_ACTIONS[key]:
            res["notes"].append(f"{key} 只對 {'／'.join(_OPT_ACTIONS[key])} 有用，這次沒有用到")
    if res["dedup"] and res["raw"]:
        return dict(res, error=f"[ERROR] --dedup 與 --raw 只能選一個。\n{USAGE}")
    res["container_arg"] = positional[0] if positional else ""
    target = current_target_container() if target is None else (target or "").strip()
    if names is None:
        names, err = list_container_names()
        if names is None:
            return dict(res, error=err, error_kind="docker")
    if res["container_arg"]:
        real, err = lookup_container(res["container_arg"], names, partial=True)
        if err:
            return dict(res, error=err, error_kind="container")
        if real != res["container_arg"]:
            res["notes"].append(f"「{res['container_arg']}」＝容器 {real}")
        res["container"] = real
    elif not target:
        return dict(res, error=(f"[ERROR] 沒有指定容器，也沒有目標容器。下一步：docker_containers 看有哪些容器，再把名稱放在動作後面"
                                f"（例如 docker_ctl {act} <容器名稱>）。\n{USAGE}"))
    elif target not in names:
        return dict(res, error_kind="container", error=(f"[ERROR] 目前的目標容器「{target}」已經不存在（被刪除或改名）；為了不操作到別的容器，不會改用名稱相近的。"
                                f"現有的容器：{existing_list_text(names)}。下一步：指定完整的容器名稱，或用 docker_open 重新選定目標容器"))
    else:
        res["container"] = target
    return dict(res, error_kind=None)


# ---------------------------------------------------------------- 狀態
def _cmd_text(cfg):
    ep = cfg.get("Entrypoint") or []
    cmd = cfg.get("Cmd") or []
    text = clip(shlex.join(cmd), 300) if cmd else "（無）"
    return text + (f"（Entrypoint：{clip(shlex.join(ep), 120)}）" if ep else "")


def _running(info):
    st = info.get("State", {})
    return bool(st.get("Running")) and not st.get("Paused") and not st.get("Restarting")


def state_line(info):
    st = info.get("State", {})
    now = datetime.datetime.now(datetime.timezone.utc)
    started, finished = parse_docker_time(st.get("StartedAt")), parse_docker_time(st.get("FinishedAt"))
    if st.get("Paused"):
        return f"Paused（暫停中，{local_time(st.get('StartedAt'))} 啟動）"
    if st.get("Restarting"):
        code = st.get("ExitCode")
        return f"Restarting（一直在重新啟動：啟動後馬上結束又被重啟；上一次結束碼 {code}：{EXIT_MEANINGS.get(code, '見 log')}）"
    if st.get("Running"):
        up = f"，已執行 {human_duration((now - started).total_seconds())}" if started else ""
        return f"Up（執行中，{local_time(st.get('StartedAt'))} 啟動{up}）"
    status = st.get("Status", "?")
    if status == "created":
        return "Created（建立了但從來沒有啟動過）"
    code = st.get("ExitCode")
    meaning = EXIT_MEANINGS.get(code, "")
    ran = f"，執行了 {human_duration((finished - started).total_seconds())}" if started and finished and finished >= started else ""
    text = (f"{status.capitalize()}（結束碼 {code}" + (f"：{meaning}" if meaning else "")
            + f"；{local_time(st.get('FinishedAt'))} 結束{ran}）")
    if st.get("OOMKilled"):
        text += "；OOMKilled（記憶體不足被系統終止）"
    if st.get("Error"):
        text += f"；錯誤：{clip(st['Error'], 200)}"
    return text


def _health_text(info):
    h = (info.get("State") or {}).get("Health")
    if not h:
        return "沒有設定"
    text = h.get("Status", "?")
    if h.get("FailingStreak"):
        text += f"（連續失敗 {h['FailingStreak']} 次）"
    logs = h.get("Log") or []
    if logs and h.get("Status") != "healthy":
        text += f"；最後一次檢查的輸出：{clip(logs[-1].get('Output', ''), 160)}"
    return text


def _policy_text(info):
    rp = (info.get("HostConfig") or {}).get("RestartPolicy") or {}
    name = rp.get("Name") or "no"
    if name == "on-failure" and rp.get("MaximumRetryCount"):
        name += f"（最多 {rp['MaximumRetryCount']} 次）"
    return name


def status_text(name, info):
    cfg = info.get("Config", {})
    st = info.get("State", {})
    lines = [f"[PASS] {name}：{state_line(info)}",
             f"- 映像：{cfg.get('Image')}",
             f"- 執行的指令：{_cmd_text(cfg)}",
             f"- 啟動：{local_time(st.get('StartedAt'))}；結束：{local_time(st.get('FinishedAt'))}；建立：{local_time(info.get('Created'))}"
             f"（本地時間 {tz_label()}）",
             f"- 重新啟動政策：{_policy_text(info)}；重新啟動次數：{info.get('RestartCount', 0)}；"
             f"OOMKilled：{'是' if st.get('OOMKilled') else '否'}；健康檢查：{_health_text(info)}"]
    if st.get("Status") == "created":
        lines.append(f"下一步：它從來沒有啟動過（沒有 log）；使用者要啟動就 docker_ctl start {name}（會先請使用者確認）")
    elif not _running(info):
        lines.append(f"下一步：使用者要啟動／重啟就直接 docker_ctl restart {name}（會先請使用者確認；回報附這次啟動的 log，又停了會寫原因）；"
                     f"只問為什麼停了就 docker_ctl logs {name} 看結束前的輸出（stdout 與 stderr 都會列），不要自己啟動")
    return "\n".join(lines)


def inspect_text(name, info):
    cfg = info.get("Config", {})
    hc = info.get("HostConfig") or {}
    ns = info.get("NetworkSettings") or {}
    nets = ns.get("Networks") or {}
    net_text = "、".join(f"{k}（IP {v.get('IPAddress') or '無'}）" for k, v in nets.items()) or str(hc.get("NetworkMode"))
    ports = ns.get("Ports") or {}
    port_text = "；".join(f"{k} → " + "、".join(f"{b.get('HostIp') or '0.0.0.0'}:{b.get('HostPort')}" for b in v)
                         for k, v in ports.items() if v) or "（沒有對外）"
    mounts = info.get("Mounts") or []
    mount_text = "；".join(f"{m.get('Source')} → {m.get('Destination')}（{'可寫' if m.get('RW') else '唯讀'}）" for m in mounts) or "（沒有）"
    env = cfg.get("Env") or []
    lines = [status_text(name, info).split("\n下一步")[0],
             f"- 工作目錄：{cfg.get('WorkingDir') or '/'}；使用者：{cfg.get('User') or 'root（映像的預設）'}；TTY：{'是' if cfg.get('Tty') else '否'}",
             f"- 網路：{net_text}；對外的 port：{port_text}",
             f"- 掛載（{len(mounts)} 個）：{mount_text}"]
    head = f"## 環境變數（{len(env)} 個" + (f"，只列前 {INSPECT_ENV_MAX} 個；docker_ctl env {name} --grep 關鍵字 篩選）" if len(env) > INSPECT_ENV_MAX else "）")
    lines += [head] + [neutralize_markers(e) for e in env[:INSPECT_ENV_MAX]]
    return "\n".join(lines)


def env_text(name, info, greps):
    env = (info.get("Config") or {}).get("Env") or []
    kws = [g.lower() for g in greps]
    shown = [e for e in env if not kws or any(k in e.lower() for k in kws)]
    label = f"，含「{'／'.join(greps)}」的 {len(shown)} 個" if greps else ""
    more = f"；只列前 {ENV_MAX} 個" if len(shown) > ENV_MAX else ""
    head = (f"[PASS] {name} 的環境變數：共 {len(env)} 個{label}{more}（容器設定的：映像的 ENV 與 docker run -e；"
            f"~/.bashrc 或程式自己設的看不到，要看用 docker_runcmd \"printenv\"）")
    if greps and not shown:
        return head + f"\n（沒有符合的；不加 --grep 可列出全部 {len(env)} 個）"
    return "\n".join([head] + [neutralize_markers(e) for e in shown[:ENV_MAX]])


# ---------------------------------------------------------------- log
def cursor_text(rows):
    """最後一行之後的 --since 游標（UTC、奈秒，docker 的 --since 包含等於的那一筆，所以加 1 奈秒）。"""
    last = max((r[0] for r in rows), default=0)
    if not last:
        return ""
    ns = last + 1
    dt = datetime.datetime.fromtimestamp(ns // 1_000_000_000, datetime.timezone.utc)
    return f"下次接著看新的：--since {dt.strftime('%Y-%m-%dT%H:%M:%S')}.{ns % 1_000_000_000:09d}Z"


def dedup_section(rows, with_date):
    """rows → (第一行的摘要片段, 唯一訊號的行, 訊號數)。用 _ros2_data_common 的 parse_log_lines＋dedup_events。
    stdout 與 stderr 分開解析再合併：同時寫出的兩個 stream 依時間合併時會交錯，stderr 的 traceback 中間夾了 stdout 的行就會被拆開。"""
    import _ros2_data_common as rd
    events = []
    for stream in ("out", "err"):
        lines = []
        for ns, st, msg in rows:
            if st != stream:
                continue
            if ns:
                dt = datetime.datetime.fromtimestamp(ns // 1_000_000_000, datetime.timezone.utc)
                lines.append(f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{ns % 1_000_000_000:09d}Z {msg}")
            else:
                lines.append(msg)
        events += rd.parse_log_lines(lines)
    groups = rd.dedup_events(events)
    levels = {}
    for e in events:
        levels[e["level"]] = levels.get(e["level"], 0) + 1
    level_text = "、".join(f"{lv} {levels[lv]}" for lv in sorted(levels, key=lambda x: -rd.LEVEL_RANK.get(x, 1)))
    order = sorted(groups, key=lambda g: (-rd.LEVEL_RANK.get(g["level"], 1), g["id"] and int(g["id"][1:])))
    out = []
    for g in order[:SIGNALS_MAX]:
        when = fmt_log_time(g["first_ns"], with_date)
        if g["count"] > 1:
            when += f" ～ {fmt_log_time(g['last_ns'], with_date)}"
        out.append(f"{g['id']:<4} {g['level']:<5} ×{g['count']:<4} {when}  {g['node']}：{clean_log_line(rd.short(g['message'], 220))}")
    if len(order) > SIGNALS_MAX:
        out.append(f"…還有 {len(order) - SIGNALS_MAX} 個訊號（用 --grep 縮小範圍）")
    return f"{len(events)} 則 → {len(groups)} 個唯一訊號；層級：{level_text}", out, len(groups)


def logs_text(name, info, opts):
    greps = opts["grep"]
    tail = opts["tail"]
    requested = GREP_SCAN if greps else (tail or (MAX_FETCH if opts["since"] or opts["until"] else DEFAULT_TAIL))
    rows, err = fetch_container_logs(name, requested, opts["since"], opts["until"])
    if err:
        return err, False
    state = state_line(info)
    tty = (info.get("Config") or {}).get("Tty")
    n_out = sum(1 for r in rows if r[1] == "out")
    n_err = len(rows) - n_out
    streams = "TTY 容器：stdout 與 stderr 混在一起" if tty else f"stdout {n_out}／stderr {n_err}"
    multi, day = log_multi_day(rows)
    tz = f"時間＝本地時間 {tz_label()}" + ("" if multi or not day else f"，日期 {day}")
    window = "、".join(x for x in [f"--since {opts['since']}" if opts["since"] else "", f"--until {opts['until']}" if opts["until"] else ""] if x)
    window = f"（{window}）" if window else ""
    if not rows:
        return (f"[PASS] {name} 沒有任何 log{window}（狀態：{state}）。"
                + ("" if opts["since"] else "下一步：程式可能把 log 寫到檔案而不是 stdout／stderr，用 docker_runcmd 找 log 檔"), True)
    scanned = len(rows)
    capped = scanned >= requested      # 拿到的行數等於要的：更早的可能還有
    lines = []
    if greps:
        kws = [g.lower() for g in greps]
        hits = [r for r in rows if any(k in strip_ansi(r[2]).lower() for k in kws)]
        show = tail or DEFAULT_TAIL
        label = "／".join(greps)
        scope = f"最後 {scanned} 行" if capped else f"全部 {scanned} 行"
        head = f"[PASS] {name} 的 log：{scope}{window}裡含「{label}」的有 {len(hits)} 行"
        if hits and len(hits) > show:
            head += f"，列出最後 {show} 行（--tail 調整）"
        if capped:
            head += f"（只掃描最後 {GREP_SCAN} 行；更早的用 --since／--until 分段）"
        head += f"；{streams}；{tz}；狀態：{state}"
        lines.append(head)
        if not hits:
            lines.append("（沒有符合的行；換關鍵字，或不加 --grep 看最後幾行）")
        elif opts["dedup"] or (len(hits) > DEDUP_AUTO and not opts["raw"]):
            summary, sig, n = dedup_section(hits, multi)
            lines[0] += f"；{summary}"
            lines += [f"## 唯一訊號（{n} 個；L# 依第一次出現排序，×N 是次數，只差在數字的算同一個；ERROR／WARN 在前）"] + sig
            lines += [f"## 最後 {min(RAW_WITH_DEDUP, len(hits))} 行原文（2>＝stderr）"] + format_log_rows(hits[-RAW_WITH_DEDUP:], multi)
        else:
            lines += [f"## 含「{label}」的行（{min(show, len(hits))} 項，2>＝stderr）"] + format_log_rows(hits[-show:], multi)
        lines.append(cursor_text(rows))
        return "\n".join(ln for ln in lines if ln), True
    dedup = opts["dedup"] or (scanned > DEDUP_AUTO and not opts["raw"])
    more = f"（更早的還有：--tail 加大（上限 {MAX_FETCH}）或用 --since）" if capped and requested < MAX_FETCH else (
        f"（只取最後 {MAX_FETCH} 行；更早的用 --since／--until 分段）" if capped else "（這段時間的全部）" if window else "（全部）")
    head = f"[PASS] {name} 的 log{window}：最後 {scanned} 行{more}；{streams}；{tz}；狀態：{state}"
    if dedup:
        summary, sig, n = dedup_section(rows, multi)
        lines = [f"{head}；{summary}",
                 f"## 唯一訊號（{n} 個；L# 依第一次出現排序，×N 是次數，只差在數字的算同一個；ERROR／WARN 在前）"] + sig
        raw = rows[-RAW_WITH_DEDUP:]
        lines += [f"## 最後 {len(raw)} 行原文（2>＝stderr；全部原文用 --raw）"] + format_log_rows(raw, multi)
    else:
        lines = [head, f"## log（{scanned} 行，2>＝stderr）"] + format_log_rows(rows, multi)
    lines.append(cursor_text(rows))
    return "\n".join(ln for ln in lines if ln), True


# ---------------------------------------------------------------- 主程式
def control(name, act, before):
    verb = {"start": "啟動", "stop": "停止", "restart": "重新啟動"}[act]
    if act == "start" and _running(before):
        return with_target_marker(f"[PASS] {name} 本來就在執行中，沒有動作（{state_line(before)}；要重新啟動用 restart）。", name)
    if act == "stop" and before.get("State", {}).get("Status") in ("exited", "created", "dead"):
        return f"[PASS] {name} 本來就沒有在跑，沒有動作（{state_line(before)}）。"
    cmd = ["docker", act] + (["-t", str(STOP_WAIT)] if act in ("stop", "restart") else []) + [name]
    ok, _out, err = run_docker(cmd, TIMEOUT + STOP_WAIT + 20, what=f"docker {act} {name}")
    if not ok:
        return err
    if act == "stop":
        after, err = inspect_container(name)
        after_text = state_line(after) if after else "（查不到）"
        return f"[PASS] 已停止 {name}：{state_line(before)} → {after_text}"
    after = None
    for _ in range(START_WAIT * 2):
        time.sleep(0.5)
        after, err = inspect_container(name)
        if err:
            return err
        if not (after.get("State") or {}).get("Running"):
            break
    started = (after.get("State") or {}).get("StartedAt")
    rows, _err = fetch_container_logs(name, AFTER_START_LOG_LINES, since=started)
    rows = rows or []
    log_lines = [f"## 這次啟動以來的 log（{len(rows)} 行，最多 {AFTER_START_LOG_LINES} 行；2>＝stderr；時間＝本地時間 {tz_label()}）"] \
        + format_log_rows(rows, False) if rows else ["（這次啟動以來還沒有任何 log）"]
    st = after.get("State") or {}
    if _running(after):
        head = f"[PASS] 已{verb} {name}：{state_line(before)} → {state_line(after)}"
        return with_target_marker("\n".join([head] + log_lines), name)
    code = st.get("ExitCode")
    if st.get("Status") == "exited" and code == 0:
        head = (f"[PASS] 已{verb} {name}：它跑完就結束了，{state_line(after)}。這是一次性的工作才正常；"
                f"要一直跑著的服務，看下面的 log 找原因")
    else:
        head = (f"[PASS] 已執行 docker {act} {name}，但它啟動後 {START_WAIT} 秒內又停了：{state_line(after)}。"
                f"不要直接再 {act} 一次：先看下面的 log 找原因（修正設定或程式之後再啟動）")
    return "\n".join([head] + log_lines)


def main(argv):
    opts = parse_args(argv)
    if opts["error"]:
        return opts["error"]
    name, act = opts["container"], opts["action"]
    info, err = inspect_container(name)
    if err:
        return err
    if act in ("start", "stop", "restart"):
        out = control(name, act, info)
    elif act == "status":
        out = status_text(name, info)
        out = with_target_marker(out, name) if _running(info) else out
    elif act == "logs":
        out, ok = logs_text(name, info, opts)
        if ok and _running(info):
            out = with_target_marker(out, name)
    elif act == "env":
        out = env_text(name, info, opts["grep"])
        out = with_target_marker(out, name) if _running(info) else out
    else:
        out = inspect_text(name, info)
        out = with_target_marker(out, name) if _running(info) else out
    if opts["notes"]:
        note = "（" + "；".join(opts["notes"]) + "）"
        lines = out.split("\n")
        k = len(lines)
        while k > 0 and lines[k - 1].startswith("[TARGET_CONTAINER]"):
            k -= 1
        out = "\n".join(lines[:k] + [note] + lines[k:])
    return out


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] docker_ctl 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
