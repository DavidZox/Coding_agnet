"""隨機情境錄製產生器的模擬核心（純 Python，不需要 ROS；ROS 型別只在容器端寫 bag 時用，見 sim_main.py）。

- 時間一律是秒，0＝錄製開始；寫進 MCAP 時加上 t0（epoch 秒）。
- Signal：分段常數的值（狀態、設定值、指令）：set(t, v) 之後發布的訊息帶新值。
- Alive：一個 Topic 有在發布的時段（節點活著、連線正常）：stop／start／gap。
- Stream：一個 Topic 的訊息。periodic＝固定頻率（加抖動），onchange／events＝明確的發布時間。build(t) 回傳訊息內容（dict，
  容器端用 set_message_fields 轉成 ROS 訊息）。
- Log：/rosout 的一則（rcl_interfaces/msg/Log：等級、節點、訊息、file、function、line——錄製時就在 MCAP 裡，跟真的一樣）。
- Truth（評分標準）：注入的事件在數據裡「看得到」的時間——固定頻率 Topic 的狀態改變＝改變之後的第一則、停止發布＝最後一則、
  中斷＝停之前最後一則；分析程式定義上看得到的才列（中斷、開始／停止發布的門檻照 _ros2_data_common 的常數），不然評分會冤枉它。
"""
import bisect
import math
import re

# 分析程式的定義（_ros2_data_common）：產生器只列「照定義看得到」的事件。容器端執行時跟本檔放在同一個暫存目錄
try:
    import _ros2_data_common as rd
    GAP_PERIODS, GAP_MIN_SEC = rd.GAP_PERIODS, rd.GAP_MIN_SEC
    EDGE_SILENCE_PERIODS, RECORDING_WARMUP_SEC = rd.EDGE_SILENCE_PERIODS, rd.RECORDING_WARMUP_SEC
    STEP_MAX_LEVELS = rd.STEP_MAX_LEVELS
except ImportError:   # 單獨測試模擬時
    GAP_PERIODS, GAP_MIN_SEC, EDGE_SILENCE_PERIODS, RECORDING_WARMUP_SEC, STEP_MAX_LEVELS = 3, 0.5, 10, 5.0, 4

INF = float("inf")
LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40, "FATAL": 50}
_NUM_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?")   # 同 _ros2_data_common.dedup_events：只差在數字的 Log 算同一句


def fmt_val(v):
    """事實裡一個值的寫法（同 analysis_job._val）：數字 6 位有效數字，布林 True/False。"""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(float(f"{v:.6g}"))
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(sorted(str(x) for x in v)) + "]"
    return '""' if v == "" else str(v)


class Signal:
    """分段常數的值。points 依時間排序；at(t) 是 t 當下（含 t）的值。"""

    def __init__(self, v0):
        self.ts, self.vs = [-INF], [v0]

    def set(self, t, v):
        i = bisect.bisect_right(self.ts, t)
        self.ts.insert(i, t)
        self.vs.insert(i, v)

    def at(self, t):
        return self.vs[bisect.bisect_right(self.ts, t) - 1]

    def values(self):
        return list(self.vs)

    def changes(self):
        out = []
        for i in range(1, len(self.ts)):
            if self.vs[i] != self.vs[i - 1]:
                out.append((self.ts[i], self.vs[i - 1], self.vs[i]))
        return out


class Alive:
    """有在發布的時段：[(開始, 結束)]，結束是 INF＝到錄製結束。"""

    def __init__(self, start=0.0, end=INF):
        self.iv = [(start, end)] if start < end else []

    def stop(self, t):
        self.iv = [(a, min(b, t)) for a, b in self.iv if a < t]

    def start(self, t, end=INF):
        self.iv.append((t, end))
        self.iv.sort()

    def gap(self, t, d):
        out = []
        for a, b in self.iv:
            if b <= t or a >= t + d:
                out.append((a, b))
                continue
            if a < t:
                out.append((a, t))
            if b > t + d:
                out.append((t + d, b))
        self.iv = out

    def contains(self, t):
        return any(a <= t < b for a, b in self.iv)


class Stream:
    """一個 Topic。kind：periodic（rate Hz、抖動比例 jitter）、onchange／events（publish(t, fields) 指定時間）。"""

    def __init__(self, sim, topic, type_name, kind, build=None, rate=None, jitter=0.02, alive=None, latched=False, burst=None):
        self.sim, self.topic, self.type, self.kind, self.build = sim, topic, type_name, kind, build
        self.rate, self.jitter = rate, jitter
        self.alive = alive or Alive()
        self.latched = latched          # TRANSIENT_LOCAL：錄製開始時重播最後一則（log_time≈錄製開始）
        self.burst = burst              # 一次收到好幾則（USB 輪詢）：(每幾則一包)
        self.explicit = []              # onchange／events：[(t, fields 或 None)]
        self.times = None
        self.appears = None             # 發布者在錄製中途才出現的時間（新節點、延遲建立的 publisher、ros2 topic pub）；None＝錄製前就在

    def publish(self, t, fields=None):
        self.explicit.append((t, fields))

    def finalize(self, duration, rng):
        if self.kind != "periodic":
            pts = sorted(((t, f) for t, f in self.explicit if 0 <= t <= duration), key=lambda x: x[0])
            self.explicit = pts
            self.times = [t for t, _ in pts]
            return
        period = 1.0 / self.rate
        times = []
        for a, b in self.alive.iv:
            b = min(b, duration)
            # 錄製開始時已經在發的：第一則落在第一個週期裡的任一點；中途才開始的：開始後很快就有第一則
            start = max(a + rng.uniform(0, period), 0.0005) if a <= 0 else a + rng.uniform(0.0, 0.3) * period
            k = 0
            while start + k * period < b:
                jt = rng.gauss(0, self.jitter * period) if self.jitter else 0.0
                tt = start + k * period + max(-0.4 * period, min(0.4 * period, jt))
                if a <= tt < b and 0 < tt <= duration:
                    times.append(tt)
                k += 1
        self.times = sorted(times)

    def fields_at(self, i):
        if self.kind == "periodic":
            return self.build(self.times[i])
        t, f = self.explicit[i]
        return f if f is not None else self.build(t)

    # ---- 看得到的時間
    def first_at_or_after(self, t):
        i = bisect.bisect_left(self.times, t - 1e-9)
        return self.times[i] if i < len(self.times) else None

    def last_before(self, t):
        i = bisect.bisect_left(self.times, t - 1e-9)
        return self.times[i - 1] if i > 0 else None

    def period(self):
        return 1.0 / self.rate if self.rate else None


class Sim:
    """一份錄製的模擬：streams、Log、評分標準。duration 秒，t0 epoch 秒。"""

    def __init__(self, rng, duration, t0, label):
        self.rng, self.duration, self.t0, self.label = rng, duration, t0, label
        self.streams = {}
        self.logs = []
        self.expect = []        # 時間線該有的事件（解析前）
        self.tag_expect = {}    # {topic: {"has": set, "not": set}}
        self.forbid = set()     # 模型寫的文字不該有的說法
        self.notes = []         # 情境說明（給人看的 title）
        self.key_steps = []
        self.question = None
        self.systems = {}
        self.change_times = {}  # topic → 分析程式會算成「變化事件」的每一個時間（同一則訊息裡的改變算一個）：時間線反覆切換的取捨用
        self.background = {}    # topic → 說明：沒有注入事件也會有事件的 Topic（例如 EKF 診斷的計數抖動）；穩定錄製的「沒有事件」不算它們

    # ---- Topic 與 Log
    def periodic(self, topic, type_name, rate, build, jitter=0.02, alive=None):
        s = Stream(self, topic, type_name, "periodic", build=build, rate=rate, jitter=jitter, alive=alive)
        self.streams[topic] = s
        return s

    def onchange(self, topic, type_name, build=None, latched=False):
        s = Stream(self, topic, type_name, "onchange", build=build, latched=latched)
        self.streams[topic] = s
        return s

    def events(self, topic, type_name):
        s = Stream(self, topic, type_name, "events")
        self.streams[topic] = s
        return s

    def log(self, t, level, node, msg, src):
        """src＝(file, function, line)：印出這則 Log 的程式位置（rcl_interfaces/msg/Log 的欄位）。"""
        if 0 <= t <= self.duration:
            self.logs.append((t, level, node, msg, src))

    # ---- 評分標準（解析成看得到的時間在 finalize）
    def expect_value(self, topic, t, token, key=False, what=""):
        """Topic 的值在 t 改變：看得到的是 t 之後的第一則（onchange 就是發布的那一則）。token＝新的值。"""
        self.expect.append({"kind": "value", "topic": topic, "t": t, "token": token, "key": key, "what": what})

    def expect_start(self, topic, t, key=False, what="", tag=False):
        """開始發布；tag＝看得到的話（照分析程式的定義：不在錄製剛開始、之前沒有訊息）這個 Topic 也該有「開始或停止發布」的類別。"""
        self.expect.append({"kind": "start", "topic": topic, "t": t, "key": key, "what": what, "tag": tag})

    def expect_stop(self, topic, t, key=False, what=""):
        self.expect.append({"kind": "stop", "topic": topic, "t": t, "key": key, "what": what})

    def expect_gap(self, topic, t, d, key=False, what=""):
        self.expect.append({"kind": "gap", "topic": topic, "t": t, "d": d, "key": key, "what": what})

    def expect_log(self, t, level, code, key=False, what=""):
        self.expect.append({"kind": "log", "t": t, "level": level, "token": code, "key": key, "what": what})

    def expect_background(self, topic, why):
        """這個 Topic 本來就會有分析程式定義的事件（沒有注入任何事件也會）：穩定的錄製判定「沒有事件」時不算它。"""
        self.background[topic] = why

    def expect_tags(self, topic, has=(), not_=()):
        d = self.tag_expect.setdefault(topic, {"has": set(), "not": set()})
        d["has"] |= set(has)
        d["not"] |= set(not_)

    # ---- 收尾
    def finalize(self):
        for s in self.streams.values():
            s.finalize(self.duration, self.rng)
        self._recorder()
        rosout = Stream(self, "/rosout", "rcl_interfaces/msg/Log", "events")
        self.logs.sort(key=lambda x: x[0])
        for t, level, node, msg, src in self.logs:
            rosout.publish(t, {"level": LEVELS[level], "name": node, "msg": msg, "file": src[0], "function": src[1], "line": int(src[2])})
        rosout.finalize(self.duration, self.rng)
        self.streams["/rosout"] = rosout
        first = min((s.times[0] for s in self.streams.values() if s.times), default=0.0)
        self.base = first   # 分析程式的 +秒 從第一則訊息算
        return self._resolve()

    def _recorder(self):
        """ros2 bag record -a 的樣子：錄製工具自己的 Log（rosbag2_recorder），一開始就有的 Topic 一次訂閱；中途才出現的 Topic
        要等發現（0.03～0.12 秒）才訂閱，之前的訊息錄不到（TRANSIENT_LOCAL 的會重播最後一則，不會少）。"""
        rec, f = "rosbag2_recorder", "./src/rosbag2_transport/recorder.cpp"
        t = 0.0002
        for msg, func, line in (("Press SPACE for pausing/resuming", "RecorderImpl", 190), ("Listening for topics...", "record", 353),
                                ("Event publisher thread: Starting", "event_publisher_thread_main", 371)):
            self.log(t, "INFO", rec, msg, (f, func, line))
            t += 0.0001
        late = []
        for topic, s in sorted(self.streams.items()):
            if s.appears is None or s.appears < 0.5:
                self.log(t, "INFO", rec, f"Subscribed to topic '{topic}'", (f, "subscribe_topic", 574))
                t += 0.0001
            else:
                late.append((topic, s))
        self.log(t + 0.0003, "INFO", rec, "Recording...", (f, "record", 365))
        self.log(t + 0.0002, "INFO", rec, "Subscribed to topic '/rosout'", (f, "subscribe_topic", 574))
        for topic, s in late:
            first = max(s.appears, s.times[0] if s.times else s.appears)
            delay = self.rng.uniform(0.03, 0.12)
            self.log(first + delay - 0.001, "INFO", rec, f"Subscribed to topic '{topic}'", (f, "subscribe_topic", 574))
            if s.latched or not s.times:
                continue
            keep = [i for i, t1 in enumerate(s.times) if t1 >= first + delay]
            if s.kind == "periodic":
                s.times = [s.times[i] for i in keep]
            else:
                s.explicit = [s.explicit[i] for i in keep]
                s.times = [s.times[i] for i in keep]
        self.streams.setdefault("/events/write_split", Stream(self, "/events/write_split", "rosbag2_interfaces/msg/WriteSplitEvent", "events"))
        self.streams["/events/write_split"].times = self.streams["/events/write_split"].times or []

    def _rel(self, t):
        return round(t - self.base, 3)

    def _resolve(self):
        """評分標準：每一個注入的事件 → 分析程式定義上看得到的時間與關鍵字（cases.json 的 timeline）。"""
        timeline = []
        log_counts = {}
        for t, level, node, msg, _ in self.logs:
            k = (level, node, _NUM_RE.sub("#", msg))
            log_counts.setdefault(k, []).append(t)
        per_topic = {}
        for e in self.expect:
            item = self._resolve_one(e, log_counts)
            if item:
                timeline.append(item)
                if e.get("tag"):   # 類別跟著同一個定義：看得到的開始才期望「開始或停止發布」
                    self.expect_tags(e["topic"], has=("開始或停止發布",))
                if e["kind"] == "value":
                    per_topic.setdefault(e["topic"], []).append(item)
        for topic, items in per_topic.items():   # 同一個 Topic 的變化太多：分析程式的時間線只列前 5 個與最後 2 個
            if topic in self.change_times:
                times = sorted({round(t - self.base, 3) for t in self.change_times[topic]})
            else:
                times = sorted({round(it["t"], 3) for it in items})
            if len(times) > 7:
                keep = times[:5] + times[-2:]
                drop = {id(it) for it in items if not any(abs(it["t"] - k) < 0.002 for k in keep)}
                timeline = [it for it in timeline if id(it) not in drop]
        # 同一個時間、同一組關鍵字只留一個
        seen, out = set(), []
        for it in sorted(timeline, key=lambda x: x["t"]):
            k = (round(it["t"], 2), tuple(it["all"]))
            if k not in seen:
                seen.add(k)
                out.append(it)
        return out

    def _resolve_one(self, e, log_counts):
        if e["kind"] == "log":
            for (level, node, key), ts in log_counts.items():
                if level == e["level"] and e["token"] in key and any(abs(t - e["t"]) < 1e-6 for t in ts):
                    if len(ts) > 3 and not (abs(ts[0] - e["t"]) < 1e-6 or abs(ts[-1] - e["t"]) < 1e-6):
                        return None   # 出現很多次的 Log 時間線只列第一次與最後一次
                    return {"t": self._rel(e["t"]), "tol": 0.05, "all": [e["level"], e["token"]], "key": e["key"], "what": e["what"]}
            return None
        s = self.streams.get(e["topic"])
        if s is None or not s.times:
            return None
        if e["kind"] == "value":
            t = s.first_at_or_after(e["t"])
            if t is None or (s.rate and t - e["t"] > 3.0 / s.rate):
                return None
            if t == s.times[0]:   # 這個 Topic 的第一則：分析程式寫成「第一則訊息（項目＝值）」，錄製剛開始的不算事件
                if s.kind == "periodic" or (s.rate and len(s.times) > 20) or t - self.base <= RECORDING_WARMUP_SEC + 0.2:
                    return None
                return {"t": self._rel(t), "tol": 0.05, "all": [e["topic"], "第一則訊息", "＝" + e["token"]], "key": e["key"], "what": e["what"]}
            return {"t": self._rel(t), "tol": 0.05, "all": [e["topic"], "→ " + e["token"]], "key": e["key"], "what": e["what"]}
        if not s.rate:
            return None
        p = s.period()
        if e["kind"] == "stop":
            last = s.times[-1]   # 停止＝最後一則（處理延遲讓最後一則晚於停止的時間也照實算）
            if last < e["t"] - 1.0 or last > e["t"] + 1.0 or self.duration - last <= max(EDGE_SILENCE_PERIODS * p, 1.0) + 0.2:
                return None
            return {"t": self._rel(last), "tol": 0.05, "all": [e["topic"], "停止發布"], "key": e["key"], "what": e["what"]}
        if e["kind"] == "start":
            first = s.first_at_or_after(e["t"])
            if first is None or first <= max(EDGE_SILENCE_PERIODS * p, 1.0) + 0.2 or first - self.base <= RECORDING_WARMUP_SEC + 0.2:
                return None
            if s.last_before(e["t"]) is not None:   # 之前有訊息：這是恢復，不是開始
                return None
            return {"t": self._rel(first), "tol": 0.05, "all": [e["topic"], "開始發布"], "key": e["key"], "what": e["what"]}
        if e["kind"] == "gap":   # 中斷＝那段時間附近最長的間隔（處理延遲讓最後一則晚於中斷的時間也照實算）
            ts = [t for t in s.times if e["t"] - 1.0 <= t <= e["t"] + e["d"] + 1.0]
            if len(ts) < 2:
                return None
            g, before = max((b - a, a) for a, b in zip(ts, ts[1:]))
            if g <= max(GAP_PERIODS * p, GAP_MIN_SEC) + 0.05:
                return None
            return {"t": self._rel(before), "tol": 0.05, "all": [e["topic"], "訊息中斷"], "key": e["key"], "what": e["what"]}
        return None

    def messages(self):
        """全部訊息依時間：(t, topic, type, index)；內容在容器端用 stream.fields_at(index) 產生（省記憶體）。"""
        items = []
        for topic, s in self.streams.items():
            items.extend((t, topic, i) for i, t in enumerate(s.times))
        items.sort()
        return items


# ---- 小工具 --------------------------------------------------------------------------------------------------------
def stamp(sim, t):
    """header.stamp（epoch）"""
    ns = int(round((sim.t0 + t) * 1e9))
    return {"sec": ns // 1_000_000_000, "nanosec": ns % 1_000_000_000}


def header(sim, t, frame=""):
    return {"stamp": stamp(sim, t), "frame_id": frame}


def quat_yaw(yaw):
    return {"x": 0.0, "y": 0.0, "z": math.sin(yaw / 2), "w": math.cos(yaw / 2)}


def twist(v=0.0, w=0.0):
    return {"linear": {"x": float(v), "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": float(w)}}


class Motion:
    """平面上的運動（速度指令積分成位置）：給 odom、pose、IMU 用。v、w 是 Signal（m/s、rad/s），加速度有限。"""

    def __init__(self, v_sig, w_sig, x0=0.0, y0=0.0, yaw0=0.0, acc=1.0, wacc=2.0, dt=0.02):
        self.v_sig, self.w_sig, self.dt = v_sig, w_sig, dt
        self.acc, self.wacc = acc, wacc
        self.cache_t, self.state = [0.0], [(x0, y0, yaw0, 0.0, 0.0)]

    def at(self, t):
        while self.cache_t[-1] < t:
            t0 = self.cache_t[-1]
            x, y, yaw, v, w = self.state[-1]
            tv, tw = self.v_sig.at(t0), self.w_sig.at(t0)
            v += max(-self.acc * self.dt, min(self.acc * self.dt, tv - v))
            w += max(-self.wacc * self.dt, min(self.wacc * self.dt, tw - w))
            x += v * math.cos(yaw) * self.dt
            y += v * math.sin(yaw) * self.dt
            yaw += w * self.dt
            self.cache_t.append(t0 + self.dt)
            self.state.append((x, y, yaw, v, w))
        i = max(0, bisect.bisect_right(self.cache_t, t) - 1)
        return self.state[i]
