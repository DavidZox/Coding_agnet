"""ROS2_topic_echo：讀取 topic 的一筆訊息，或用 --duration 觀察一段時間、量測每個欄位——跟錄好的數據（mcap_feature_measure、analysis_run）
用同一套 Key 目錄與量測（_ros2_data_common）。

在目標容器內執行（_ros2_data_common.run_in_container：載入 /opt/ros、Workspace overlay 與執行中節點的 ROS_DOMAIN_ID），用 rclpy 直接訂閱：
- 型別：從 ROS 圖查（不用使用者給）；自訂訊息讀不到時回 [ERROR] 並指向 ROS2_workspace_env。
- QoS：照目前的 publisher 配（有 BEST_EFFORT 的就用 BEST_EFFORT；全部是 TRANSIENT_LOCAL 才用 TRANSIENT_LOCAL，拿得到最後一則）；
  QoS 不相容、沒有 publisher 都會寫在結果裡。
- 一筆（預設）：等第一則訊息（timeout_seconds），印完整的 YAML（字串不截斷，JSON 狀態看得到全部）。
- 一段時間（--duration）：每一則的到達時間＋每個 Key 的值 → 發布方式（固定頻率／狀態改變時才發布／不定期）與中斷、狀態跳轉（時間、
  前後的值、占比）、數值的極值（與時間）／均值／標準差／斜率／尖峰／切換、字串裡的 JSON 欄位、依名稱展開的項目（DiagnosticArray）；
  --where 條件由程式判斷（幾則符合、第一則符合 #k 與它的前一則、符合的時段）；最後附前後幾則原始訊息（--- #序號 +秒）。
主機不需要 ROS 2 與 PyYAML（以前在主機解析 ros2 topic echo 的 YAML，主機沒有 PyYAML 時欄位統計整個不見、還回 [PASS]）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ros2_data_common as rd  # noqa: E402

DEFAULT_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 570        # 低於 harness 的 TOOL_EXEC_TIMEOUT（600）
MIN_DURATION_SECONDS = 2
MAX_DURATION_SECONDS = 300
DISCOVERY_SECONDS = 4.0          # 找 topic 與 publisher（DDS discovery）最多等幾秒
GRACE_SECONDS = 40               # 容器內啟動 Python、載入 ROS 2 的餘裕（加在 duration／timeout 上當作外層逾時）
SAMPLE_MESSAGES = 60             # 前幾則訊息用來判斷每個 Key 的類別（同 mcap_analyzer 的抽樣）
DEFAULT_RAW, MAX_RAW = 10, 100   # --duration 附幾則原始訊息（前一半、後一半）
MAX_RAW_CHARS = 12000            # 原始訊息區的篇幅上限
USAGE = ("用法: scripts/ROS2_topic_echo_cmd.py [container_name] <topic_name> [timeout_seconds] [--duration 秒] [--where 欄位<值]... [--raw N]\n"
         "  container_name 可省略＝目前的目標容器；topic 以 / 開頭。\n"
         f"  不加 --duration：等第一則訊息（timeout_seconds 預設 {DEFAULT_TIMEOUT_SECONDS}，上限 {MAX_TIMEOUT_SECONDS}；低頻 topic 加大），印完整的 YAML。\n"
         f"  --duration 秒（{MIN_DURATION_SECONDS}～{MAX_DURATION_SECONDS}）：觀察這段時間，量測發布方式與每個欄位的變化。"
         "--where 欄位<值（可重複，要搭配 --duration）：幾則符合、第一則符合 #k；運算子 < <= > >= == !=，欄位名稱同量測結果"
         f"（voltage、pose.pose.position.x、status.level[motor_left]、data.mode）。--raw N：附幾則原始訊息（預設 {DEFAULT_RAW}，上限 {MAX_RAW}）。")


# =====================================================================================================================
# 主機端：參數 → 送進容器
# =====================================================================================================================
def _seconds(v):
    """「5s」「5秒」「5 sec」→「5」（模型常照抄畫面上的寫法）；不是「數字＋單位」的（topic 名稱 /status）原樣傳回。"""
    import re
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds|秒)", str(v).strip(), flags=re.I)
    return m.group(1) if m else str(v).strip()


def parse_cli(argv):
    """→ (opts, error)。opts：container、topic、timeout、duration、wheres、raw。第一個位置參數是現有的容器名稱才當容器，
    否則是 topic（沒有 / 開頭時補上）。"""
    sys.path.insert(0, rd.HERE)
    from _docker_common import lookup_container, parse_timeout, split_container_arg
    args, wheres, duration, raw = list(argv), [], None, DEFAULT_RAW
    i, pos, named = 0, [], {}
    while i < len(args):
        a = args[i]
        if a in ("--where", "--duration", "--raw", "--timeout", "--topic", "--container"):
            if i + 1 >= len(args):
                return None, f"[ERROR] {a} 後面要接值。\n{USAGE}"
            val = _seconds(args[i + 1]) if a in ("--duration", "--timeout") else args[i + 1]
            if a in ("--topic", "--container"):   # 跟 mcap_* 一樣的寫法（--topic /odom）也接受
                named[a] = val
            elif a == "--where":
                c, err = rd.parse_where(val)
                if err:
                    return None, f"[ERROR] --where {err}。\n{USAGE}"
                wheres.append(val)
            elif a == "--duration":
                v, err = parse_timeout(val, None, MAX_DURATION_SECONDS, name="--duration")
                if err or v is None or v < MIN_DURATION_SECONDS:
                    return None, f"[ERROR] --duration 要介於 {MIN_DURATION_SECONDS}～{MAX_DURATION_SECONDS} 秒，收到 {val!r}。\n{USAGE}"
                duration = v
            elif a == "--raw":
                if not val.isdigit():
                    return None, f"[ERROR] --raw 要是整數（附幾則原始訊息），收到 {val!r}。\n{USAGE}"
                raw = max(0, min(MAX_RAW, int(val)))
            else:
                named["--timeout"] = val
            i += 2
            continue
        if a.startswith("--"):
            return None, (f"[ERROR] 不認識的選項 {a!r}：位置參數依序是 [container_name] <topic_name> [timeout_seconds]，"
                          f"選項只有 --duration、--where、--raw（--topic、--container 也可以）。\n{USAGE}")
        pos.append(a)
        i += 1
    if wheres and not duration:
        return None, f"[ERROR] --where 要搭配 --duration（要有一段時間的訊息才判斷得了）。\n{USAGE}"
    pos = [_seconds(p) for p in pos]
    if "--topic" in named:
        pos = ([named["--container"]] if "--container" in named else []) + [named["--topic"]] + pos
    elif "--container" in named:
        pos = [named["--container"]] + pos
    if "--timeout" in named and len([p for p in pos if not p.isdigit()]) == len(pos):
        pos.append(named["--timeout"])
    if not pos:
        return None, f"[ERROR] 需要 topic 名稱（例如 /odom；不知道名稱先用 ROS2_topic_list）。\n{USAGE}"
    # 第一個參數是不是容器：跟其他 ROS 2 技能同一個判斷（_docker_common.split_container_arg）——完全相同（不分大小寫）的容器名稱才算，
    # 否則是 topic；--container 一定是容器（允許唯一的部分名稱）。沒給容器＝目前的目標容器
    if "--container" in named:
        container, pos, err = split_container_arg(pos, USAGE, must=True)
    else:
        container, pos, err = split_container_arg(pos, USAGE, maybe=True)
    if err:
        return None, err
    if len(pos) >= 2 and not pos[1].isdigit():   # 「X /topic」：X 不是容器名稱（多半打錯了）
        _, err = lookup_container(pos[0])
        return None, (err or f"[ERROR] 多了參數 {pos[1:]}：位置參數依序是 [container_name] <topic_name> [timeout_seconds]") + f"\n{USAGE}"
    topic = pos[0] if pos[0].startswith("/") else "/" + pos[0]
    timeout, err = parse_timeout(pos[1] if len(pos) > 1 else None, DEFAULT_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS, name="timeout_seconds")
    if err:
        return None, f"{err}\n{USAGE}"
    if len(pos) > 2:
        return None, f"[ERROR] 多了參數 {pos[2:]}。\n{USAGE}"
    return {"container": container, "topic": topic, "timeout": timeout, "duration": duration, "wheres": wheres, "raw": raw}, None


def host_main(argv):
    opts, err = parse_cli(argv)
    if err:
        print(err)
        return 0
    wargs = ["--topic", opts["topic"], "--timeout", str(opts["timeout"]), "--raw", str(opts["raw"])]
    if opts["duration"]:
        wargs += ["--duration", str(opts["duration"])]
    for w in opts["wheres"]:
        wargs += ["--where", w]
    limit = (opts["duration"] or opts["timeout"]) + DISCOVERY_SECONDS + GRACE_SECONDS
    rc, out = rd.run_in_container(os.path.abspath(__file__), wargs, container=opts["container"], timeout=limit,
                                  what="ROS2_topic_echo",
                                  timeout_hint="容器內的 Python／ROS 2 沒有在時間內結束：縮短 --duration，或先用 ROS2_topic_list 確認 ROS 2 正常。")
    print(rd.finalize_output(out))
    return 0 if out.lstrip().startswith(("[PASS]", "[ERROR]")) else rc


# =====================================================================================================================
# 容器端：rclpy 訂閱
# =====================================================================================================================
def _worker_args(argv):
    a = {"wheres": []}
    i = 0
    while i < len(argv):
        k, v = argv[i], argv[i + 1]
        if k == "--where":
            a["wheres"].append(v)
        else:
            a[k.lstrip("-")] = v
        i += 2
    return a


def _close_names(topic, names, n=6):
    import difflib
    return difflib.get_close_matches(topic, names, n=n, cutoff=0.4) or [x for x in names if topic.strip("/").split("/")[-1] in x][:n]


def _qos_for(infos):
    """依目前的 publisher 配 QoS：有 BEST_EFFORT 的就用 BEST_EFFORT（兩種 publisher 都收得到）；全部是 TRANSIENT_LOCAL 才用 TRANSIENT_LOCAL
    （訂閱時拿得到最後一則）。回傳 (QoSProfile, 說明)。"""
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    rel = ReliabilityPolicy.BEST_EFFORT if any(i.qos_profile.reliability == ReliabilityPolicy.BEST_EFFORT for i in infos) \
        else ReliabilityPolicy.RELIABLE
    dur = DurabilityPolicy.TRANSIENT_LOCAL if infos and all(i.qos_profile.durability == DurabilityPolicy.TRANSIENT_LOCAL for i in infos) \
        else DurabilityPolicy.VOLATILE
    text = f"{'BEST_EFFORT' if rel == ReliabilityPolicy.BEST_EFFORT else 'RELIABLE'}／{'TRANSIENT_LOCAL' if dur == DurabilityPolicy.TRANSIENT_LOCAL else 'VOLATILE'}"
    return QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=100, reliability=rel, durability=dur), text


class _Capture:
    """訂閱的 callback：記每一則的到達時間；前 SAMPLE_MESSAGES 則留著判斷 Key 的類別，之後每一則直接取值（不留整則訊息，高頻、大的
    訊息也不會吃光記憶體）；前後幾則原始訊息另外轉成 YAML 留著。"""

    def __init__(self, cls, raw_keep):
        from collections import deque
        self.cls, self.times, self.samples, self.descs, self.series, self.errors = cls, [], [], None, {}, {}
        self.head, self.tail = [], deque(maxlen=max(0, raw_keep - raw_keep // 2))
        self.head_n = raw_keep // 2 if raw_keep > 1 else raw_keep

    def _yaml(self, msg):
        from rosidl_runtime_py import message_to_yaml
        try:
            return message_to_yaml(msg).rstrip()
        except Exception as e:   # noqa: BLE001
            return f"（轉成 YAML 失敗：{type(e).__name__}: {e}）"

    def keys(self):
        return [d["key"] for d in self.descs or []]

    def ready(self):
        self.descs = [d for d in rd.describe_keys(self.cls, self.samples)
                      if d["category"] in rd.SCAN_CATEGORIES and not d["key"].startswith("header.")]
        self.series = {d["key"]: {} for d in self.descs}
        dmap = {d["key"]: d for d in self.descs}
        for t, msg in zip(self.times, self.samples):
            rd._collect(msg, t, self.keys(), dmap, self.series, self.errors)
        self.samples = []

    def __call__(self, msg):
        t = time.time_ns()
        self.times.append(t)
        n = len(self.times)
        if len(self.head) < self.head_n:
            self.head.append((n, t, self._yaml(msg)))
        elif self.tail.maxlen:
            self.tail.append((n, t, msg))
        if self.descs is None:
            self.samples.append(msg)
            if len(self.samples) >= SAMPLE_MESSAGES:
                self.ready()
        else:
            rd._collect(msg, t, self.keys(), {d["key"]: d for d in self.descs}, self.series, self.errors)


def worker_main(argv):
    a = _worker_args(argv)
    topic, timeout, raw_keep = a["topic"], float(a["timeout"]), int(a["raw"])
    duration = float(a["duration"]) if a.get("duration") else None
    try:
        import rclpy
        from rclpy.node import Node
    except ImportError as e:
        print(f"[ERROR] 容器裡載入不到 rclpy（{e}）：這個容器沒有 ROS 2 的 Python 環境。下一步：用 docker_containers 換一個有 ROS 2 的容器"
              f"（docker_open <名稱>），或用 ROS2_workspace_env 確認環境。")
        return 0
    rclpy.init()
    node = Node(f"agent_topic_echo_{os.getpid()}")
    try:
        return _observe(node, rclpy, topic, timeout, duration, a["wheres"], raw_keep)
    finally:
        node.destroy_node()
        rclpy.try_shutdown() if hasattr(rclpy, "try_shutdown") else rclpy.shutdown()


def _observe(node, rclpy, topic, timeout, duration, wheres, raw_keep):
    domain = os.environ.get("ROS_DOMAIN_ID") or "0（預設）"
    deadline = time.time() + DISCOVERY_SECONDS
    types = {}
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
        types = dict(node.get_topic_names_and_types())
        if topic in types:
            break
    if topic not in types:
        names = sorted(types)
        near = _close_names(topic, names)
        print(f"[ERROR] ROS 圖上沒有 topic {topic}（ROS_DOMAIN_ID={domain}，{DISCOVERY_SECONDS:g} 秒內看到 {len(names)} 個 topic）"
              + (f"；名稱相近的：{'、'.join(near)}" if near else "")
              + "。下一步：用 ROS2_topic_list 確認名稱；只看得到 /rosout、/parameter_events 時用 ROS2_domain_id 確認 domain。")
        return 0
    type_name = types[topic][0]
    cls, err = rd.msg_class(type_name)
    if cls is None:
        print(f"[ERROR] 載入不到 {topic} 的訊息型別 {type_name}（{err}）：自訂訊息要先載入它的 Workspace。下一步：用 ROS2_workspace_env "
              f"確認這個容器的 Workspace（--discover 找候選），之後再觀察。")
        return 0
    infos = node.get_publishers_info_by_topic(topic)
    qos, qos_text = _qos_for(infos)
    cap = _Capture(cls, raw_keep if duration else 1)
    incompatible = []
    try:
        from rclpy.qos_event import SubscriptionEventCallbacks
        events = SubscriptionEventCallbacks(incompatible_qos=lambda e: incompatible.append(e.total_count))
        sub = node.create_subscription(cls, topic, cap, qos, event_callbacks=events)
    except (ImportError, TypeError):
        sub = node.create_subscription(cls, topic, cap, qos)
    start = time.time_ns()
    end_at = time.time() + (duration if duration else timeout)
    while time.time() < end_at:
        rclpy.spin_once(node, timeout_sec=0.1)
        if not duration and cap.times:
            break
    end = time.time_ns()
    node.destroy_subscription(sub)
    pubs = f"publisher {len(infos)} 個，QoS {qos_text}"
    if not cap.times:
        why = ["目前沒有 publisher" if not infos else f"有 {len(infos)} 個 publisher 但沒有送出訊息（低頻或只在狀態改變時才發布）"]
        if incompatible:
            why.append("QoS 不相容（publisher 跟訂閱的設定對不上）")
        wait = duration or timeout
        print(f"[PASS] {topic}（{type_name}）在 {wait:g} 秒內沒有收到任何訊息：{'；'.join(why)}（{pubs}）。"
              + ("下一步：低頻的 topic 加大秒數再試一次；確定應該要有訊息時用 ROS2_node_list／ROS2_node_info 看發布它的 node。"))
        return 0
    if not duration:
        n, t, text = cap.head[0]
        print(f"[PASS] {topic}（{type_name}）的一筆訊息（等了 {(t - start) / 1e9:.2f} 秒；{pubs}）：\n{text}")
        return 0
    if cap.descs is None:
        cap.ready()
    _report(topic, type_name, cap, start, end, duration, wheres, pubs, incompatible)
    return 0


def _report(topic, type_name, cap, start, end, duration, wheres, pubs, incompatible):
    window = {"start_ns": start, "end_ns": end}
    dmap = {d["key"]: d for d in cap.descs}
    feats_by_key, flags, all_feats = {}, [], []
    for k in cap.keys():
        feats, fl = rd.measure_key(cap.series.get(k, {}), dmap[k], window, k)
        feats_by_key[k] = feats
        flags += fl
        all_feats += list(feats.values())
    rate = rd.rate_features(cap.times, window, data_start_ns=start, change_times=rd.change_times(all_feats))
    changed, constant = [], []
    for k, feats in feats_by_key.items():
        for lab, f in feats.items():
            name = rd.entry_name(k, lab, dmap[k])
            (changed if rd.changed(f) else constant).append((name, f))
    n = rate["messages"]
    head = (f"[PASS] 觀察 '{topic}'（{type_name}）{duration:g} 秒：收到 {n} 則，{rd.pattern_text(rate)}"
            + (f"，平均 {rate['avg_hz']} Hz" if rate.get("avg_hz") else "")
            + f"；有變化的欄位 {len(changed)} 個、固定不變 {len(constant)} 個")
    lines = [head, f"觀察：{rd.fmt_t(start)} ～ {rd.fmt_t(end)}（{(end - start) / 1e9:.1f} 秒）；[+秒] 是距離開始觀察的時間；{pubs}"
             + ("；⚠️ QoS 不相容的事件 " + str(incompatible[-1]) + " 次" if incompatible else "")]
    r = f"訊息 {n} 則（第一則 {rd.fmt_rel(cap.times[0], start)}、最後一則 {rd.fmt_rel(cap.times[-1], start)}）；發布方式：{rd.pattern_text(rate)}"
    if rate.get("max_gap_sec") is not None:
        r += f"，最大間隔 {rate['max_gap_sec']} 秒"
    if rate.get("gaps"):
        r += "；中斷 " + "、".join(f"{rd.fmt_rel(int(g['start_sec'] * 1e9), start)} 起 {g['duration_sec']} 秒" for g in rate["gaps"][:6]) \
             + (f"…共 {rate['gap_count']} 次" if rate["gap_count"] > 6 else "")
    if rate.get("warmup_start") or (rate.get("starts_after_window_sec", 0) > 1.0 and not rate.get("started_late")):
        r += f"；開始觀察後 {rate['starts_after_window_sec']} 秒才收到第一則（訂閱與 discovery 的時間，或低頻）"
    elif rate.get("started_late"):
        r += f"；{rd.fmt_rel(cap.times[0], start)} 才開始發布（觀察開始後 {rate['starts_after_window_sec']} 秒）"
    if rate.get("stopped_early"):
        r += f"；{rd.fmt_rel(cap.times[-1], start)} 之後停止發布（到觀察結束 {rate['ends_before_window_sec']} 秒沒有訊息）"
    if rate.get("pattern") != "periodic" and rate.get("times_sec"):
        r += "；每一則：" + "、".join(rd.fmt_rel(int(x * 1e9), start) for x in rate["times_sec"])
    lines += ["## 訊息流", r]
    lines.append(f"## 有變化的欄位（{len(changed)} 個）")
    for name, f in changed[:60]:
        lines += rd.feature_lines(name, f, start, indent="  ", more="（--where 或縮短 --duration 看細節）")
    if len(changed) > 60:
        lines.append(f"…還有 {len(changed) - 60} 個有變化的欄位沒有列（用 --where 指定要看的欄位）")
    if not changed:
        lines.append("（觀察期間所有欄位都沒有變化）")
    if constant:
        lines.append(f"## 固定不變（{len(constant)} 個）")
        lines += [f"- {name} = {rd.short(rd.fmt_num(f['first']) if f['kind'] == 'numeric' else (rd.state_text(f.get('first')) if f['kind'] == 'state' else f['kind']), 80)}"
                  for name, f in constant[:40]]
        if len(constant) > 40:
            lines.append(f"…還有 {len(constant) - 40} 個固定不變的欄位")
    if cap.errors:
        lines.append("取值失敗：" + "；".join(f"{k}：{v}" for k, v in list(cap.errors.items())[:5]))
    if wheres:
        index_of = {t: i + 1 for i, t in enumerate(cap.times)}
        lines.append(f"## 條件（{len(wheres)} 個）")
        for expr in wheres:
            c, _ = rd.parse_where(expr)
            lines.append(rd.where_on_series(c, cap.keys(), cap.descs, cap.series, end, start, index_of)["line"])
    raw = [(i, t, txt) for i, t, txt in cap.head] + [(i, t, cap._yaml(m)) for i, t, m in cap.tail if i > len(cap.head)]
    if raw:
        lines.append(f"## 原始訊息（共 {n} 則；列出 {len(raw)} 則：" + ("全部" if len(raw) == n else f"前 {len(cap.head)} 則與最後 {len(raw) - len(cap.head)} 則；"
                                                                        f"其他的 --raw 加大或縮短 --duration") + "）")
        used = 0
        for i, t, txt in raw:
            block = f"--- #{i} {rd.fmt_rel(t, start)}\n{txt}"
            if used + len(block) > MAX_RAW_CHARS:
                lines.append(f"…（原始訊息的篇幅上限 {MAX_RAW_CHARS} 字，其餘沒有列；上面的欄位統計涵蓋全部 {n} 則）")
                break
            lines.append(block)
            used += len(block)
    print("\n".join(lines))


if __name__ == "__main__":
    try:
        if rd.in_worker():
            raise SystemExit(worker_main(sys.argv[1:]))
        raise SystemExit(host_main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:   # noqa: BLE001
        print(f"[ERROR] ROS2_topic_echo 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
