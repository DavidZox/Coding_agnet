"""ROS 2 數據分析技能（mcap_recorder／rosout_parser／mcap_slicer／mcap_analyzer／mcap_feature_measure）的共用層。

移植自 diagnostics_package/toolkit 的人工工具（rosout_formatter.py、mcap_slicer.py 的 Log 去重與時間切片、
mcap_analyzer.py 的欄位維度、mcap_feature_measure.py 的特徵量測），改成非互動、由 agent 呼叫、數字一律由程式算好。

分兩半：
1. 主機端（harness 執行的入口腳本）：run_in_container() 把入口腳本連同本模組（與附檔）打包，經 stdin 送進目標容器的
   暫存目錄，載入 ROS 2 環境（/opt/ros、Workspace overlay）後以 ROS2_TOOL_WORKER=1 執行、結束後刪掉暫存目錄——主機不需要
   ROS 2。主機路徑依容器的 bind mount 換成容器內路徑（to_container_path）。
2. 容器端（入口腳本的 worker_main）：實驗資料的定位（resolve_data）、MCAP 讀取、rosout 解析與去重（Log 智慧過濾）、
   全域 Topic Metadata 索引（每個 Key 的型別、維度與資料類別，快取成 topic_metadata.json）、時間窗、特徵量測。

資料類別（對應數據解析 agent 的職責分派，見 analysis_agents/）：
- log（/rosout）與 text（自由文字）：只給 Orchestrator（去重後的 Log），worker 不量測；
- numeric（純量）、vector（向量分量）、matrix、array：worker 做數值統計（極值、均值、變異數、斜率、尖峰）；
- state（uint8／bool／列舉字串／代碼集合）、kv（DiagnosticStatus 的 key-value）：worker 做狀態變遷偵測（Edge Detection）。
- time（時間戳欄位）：不量測。
"""
import base64
import glob
import io
import json
import math
import os
import re
import shlex
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER_ENV = "ROS2_TOOL_WORKER"
ANALYSIS_DATA_MARKER = "[ANALYSIS_DATA]"   # 末行狀態標記：harness 據此同步「目前分析的數據」（比照 [TARGET_CONTAINER]）
INDEX_NAME = "topic_metadata"             # 全域 Topic Metadata 索引的檔名（.json 給程式、.yaml 給人看），放在 bag 資料夾
INDEX_VERSION = 3                         # Key 分類規則改了就加一（舊的快取自動重建）
LOG_TOPICS = ("/rosout", "/rosout_agg")
SAMPLES_PER_TOPIC = 120                   # 建索引時每個 Topic 反序列化幾筆來判斷 Key 的類別（平均分散在整段錄製裡）
STATE_MAX_DISTINCT = 12                   # 字串欄位相異值不超過這個數、而且都很短 → 當列舉（state），否則是自由文字（text）
STATE_MAX_LEN = 64
STATE_FEW_DISTINCT = 8                    # 相異值只有這麼少的字串（即使是長句子，例如 winning_reason）也當狀態：變了就是一次狀態變遷
INT_STATE_MAX_DISTINCT = 10               # 整數欄位相異值不超過這個數 → 量測時當狀態跳轉（同 toolkit 的判斷）
STEP_MAX_LEVELS = 4                       # 浮點數只有這麼少種值（速度指令 0／0.1、設定值）→ 另外列每次切換的時間（像狀態跳轉）
SET_MAX_LEN = 16                          # 整數／字串序列平均長度不超過這個數 → 當集合狀態（例如 active_error_codes）
SPIKE_SIGMA = 2.5                         # 尖峰：離均值超過 2.5 個標準差（同 toolkit）
MAX_DEPTH = 4
NAME_FIELDS = ("name", "child_frame_id", "key", "id", "label", "frame_id")
TIME_TYPES = {"builtin_interfaces/msg/Time", "builtin_interfaces/msg/Duration"}
LEVEL_NAMES = {10: "DEBUG", 20: "INFO", 30: "WARN", 40: "ERROR", 50: "FATAL"}
LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "UNKNOWN": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
WORKER_CATEGORIES = ("numeric", "vector", "state", "kv", "matrix", "array")
CATEGORY_LABELS = {"numeric": "數值", "vector": "向量", "state": "狀態", "kv": "鍵值", "matrix": "矩陣", "array": "陣列",
                   "text": "文字", "time": "時間"}
CORE_TOPICS = ["/sensor_scan", "/cmd_vel", "/cmd_vel_raw", "/diagnostics", "/diagnostics_agg", "/system/safety_command",
               "/tf", "/tf_static"]   # toolkit 的「預設核心 Topic 組合」


def in_worker():
    return os.environ.get(WORKER_ENV) == "1"


# =====================================================================================================================
# 主機端
# =====================================================================================================================
def container_mounts(container):
    """容器的 bind mount：[(主機路徑, 容器路徑)]，主機路徑長的在前（最精確的先比對）。查不到回空清單。"""
    try:
        r = subprocess.run(["docker", "inspect", container, "--format", "{{json .Mounts}}"],
                           capture_output=True, text=True, timeout=15)
        data = json.loads(r.stdout or "[]") if r.returncode == 0 else []
    except Exception:   # noqa: BLE001
        data = []
    pairs = [(m.get("Source", ""), m.get("Destination", "")) for m in data or []
             if isinstance(m, dict) and m.get("Source") and m.get("Destination")]
    return sorted(pairs, key=lambda p: -len(p[0]))


def to_container_path(path, mounts):
    """主機路徑 → 容器內路徑：在某個 bind mount 底下才換；不在主機上（本來就是容器路徑、實驗名稱、latest）的原樣傳回。"""
    if not path:
        return path
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded) or not os.path.exists(expanded):
        return path
    real = os.path.realpath(expanded)
    for src, dst in mounts:
        src_r = os.path.realpath(src).rstrip("/")
        if real == src_r or real.startswith(src_r + "/"):
            return dst.rstrip("/") + real[len(src_r):]
    return path


def to_host_path(path, mounts):
    """容器內路徑 → 主機路徑（給人看、給主機上的技能用）；不在任何 mount 底下回 None。"""
    for src, dst in mounts:
        d = dst.rstrip("/")
        if path == d or path.startswith(d + "/"):
            return src.rstrip("/") + path[len(d):]
    return None


def _workspace_source(container):
    """harness 記錄的 ROS 2 Workspace（ROS2_workspace_env 確認過、而且屬於這個容器）→ 載入它的 setup.bash（自訂訊息型別才讀得到）。"""
    ws = (os.environ.get("ROS2_WORKSPACE") or "").strip()
    ws_container = (os.environ.get("ROS2_WORKSPACE_CONTAINER") or "").strip()
    if not ws or ws_container != container:
        return ""
    setup = ws.rstrip("/") + ("/setup.bash" if ws.rstrip("/").endswith("/install") else "/install/setup.bash")
    return f"[ -f {shlex.quote(setup)} ] && source {shlex.quote(setup)} >/dev/null 2>&1; "


def run_in_container(script_file, worker_args, *, container=None, timeout=120, what="ROS 2 數據工具",
                     timeout_hint=None, extra_files=()):
    """在目標容器內執行 script_file 的 worker_main（ROS2_TOOL_WORKER=1），回傳 (rc, 輸出文字)。
    腳本、本模組與 extra_files 打包成 tar.gz、base64 後經 stdin 送進容器的暫存目錄（不寫主機暫存檔、沒有參數長度限制），
    執行完一律刪掉暫存目錄。成功時輸出末行附目標容器標記（with_target_marker）。"""
    sys.path.insert(0, HERE)
    from _docker_common import ROS2_ENV_FALLBACK, docker_exec, resolve_container, with_target_marker
    container, err = resolve_container(container)
    if err:
        return 2, err
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in (script_file, os.path.join(HERE, "_ros2_data_common.py"), *extra_files):
            tar.add(f, arcname=os.path.basename(f))
    payload = base64.b64encode(buf.getvalue()).decode("ascii")
    name = os.path.basename(script_file)
    command = (ROS2_ENV_FALLBACK + _workspace_source(container)
               + 'd=$(mktemp -d /tmp/agent_tool.XXXXXX) && base64 -d | tar -xz -C "$d" && '
               + f'{WORKER_ENV}=1 PYTHONDONTWRITEBYTECODE=1 python3 "$d/{name}" {shlex.join(worker_args)}'
               + '; rc=$?; rm -rf "$d"; exit $rc')
    ok, stdout, error_message = docker_exec(container, command, timeout, interactive=True, what=what,
                                            timeout_hint=timeout_hint, input_text=payload)
    if not ok:
        out = (stdout or "").strip()
        if out.startswith("[ERROR]"):   # 工具自己判斷的錯誤（參數、找不到數據…）：原樣交回，不加 docker 的外框
            return 1, out
        body = error_message
        if out and out not in body:
            body += "\n--- 工具輸出 ---\n" + out[-4000:]
        return 1, body
    return 0, with_target_marker((stdout or "").strip() or "[PASS] 完成（沒有輸出）。", container)


def analysis_windows():
    """analysis worker 的時間窗：analysis_job 以環境變數 ANALYSIS_WINDOWS 傳入（JSON：[{id, start_ns, end_ns, anchor_ns, slice}]；
    slice＝這個時間窗的切片（容器內路徑），沒有切片時省略）。"""
    raw = (os.environ.get("ANALYSIS_WINDOWS") or "").strip()
    try:
        data = json.loads(raw) if raw else []
    except ValueError:
        return []
    return [w for w in data if isinstance(w, dict) and w.get("id")]


def resolve_window_ids(text):
    """--window 的值是 W1 這種編號時換成「開始,結束,錨點,W1[,切片]」（奈秒精度，模型不必抄 19 位數的時間）；其他原樣傳回。"""
    t = str(text).strip()
    for w in analysis_windows():
        if t.upper() == str(w["id"]).upper():
            return f"{w['start_ns']},{w['end_ns']},{w.get('anchor_ns') or ''},{w['id']}" + (f",{w['slice']}" if w.get("slice") else "")
    return t


def slice_for_window(w, tol_ns=100_000_000):
    """沒有指定切片的時間窗（worker 自己寫的 +3.37,+31.79）：落在某個有切片的 analysis 時間窗裡（容許 0.1 秒的四捨五入），
    就用那個切片；超出切片的範圍要讀原本的數據（切片裡沒有那一段）。"""
    for aw in analysis_windows():
        if aw.get("slice") and int(aw["start_ns"]) - tol_ns <= w["start_ns"] and w["end_ns"] <= int(aw["end_ns"]) + tol_ns:
            return aw["slice"]
    return ""


def matching_analysis_window(w, tol_ns=500_000_000):
    """worker 自己抄的時間窗跟某個 analysis 時間窗兩端都差不到 0.5 秒＝就是那個時間窗（模型抄的數字有四捨五入；
    實測 e4b 寫 +140.82s,+175.31s、140.82s_175.31s）。"""
    for aw in analysis_windows():
        if abs(int(aw["start_ns"]) - w["start_ns"]) <= tol_ns and abs(int(aw["end_ns"]) - w["end_ns"]) <= tol_ns:
            return aw
    return None


def host_common_args(argv_container, data_path, mounts, data_root=None):
    """主機端：把「數據」路徑（省略時用 harness 傳入的目前分析數據 ANALYSIS_DATA）與數據根目錄換成容器內路徑。
    回傳要接在 worker 參數最前面的清單。"""
    out = []
    data = data_path or (os.environ.get("ANALYSIS_DATA") or "").strip()
    if data:
        out += ["--data", to_container_path(data, mounts)]
    root = data_root or (os.environ.get("ANALYSIS_DATA_ROOT") or "").strip()
    if root:
        out += ["--data-root", to_container_path(root, mounts)]
    return out


# =====================================================================================================================
# 容器端：時間
# =====================================================================================================================
def parse_time(text, base_ns=None):
    """時間參數 → 奈秒整數。可以是：epoch 秒（1791967507.719913285，保留到奈秒、不經過 float）、奈秒整數（16 位以上）、
    或「+12.5」＝數據開頭之後 12.5 秒（需要 base_ns）。"""
    s = str(text).strip()
    s = re.sub(r"(s|sec|秒)$", "", s, flags=re.I).strip()   # 「+0.75s」「12秒」：模型常照抄畫面上的寫法
    if s.startswith("+"):
        if base_ns is None:
            raise ValueError(f"相對時間 {s} 需要數據的開頭時間")
        return base_ns + int(round(float(s[1:] or 0) * 1e9))
    if re.fullmatch(r"\d{16,}", s):
        return int(s)
    m = re.fullmatch(r"(\d+)(?:\.(\d*))?", s)
    if not m:
        raise ValueError(f"看不懂的時間：{text}（用 epoch 秒，例如 1791967507.72，或 +12.5 表示數據開頭之後 12.5 秒）")
    if int(m.group(1)) < 1_000_000_000 and base_ns is not None:
        return base_ns + int(round(float(s) * 1e9))   # 小於 10 億秒（2001 年以前）不可能是 epoch：當成距離數據開頭的秒數
    frac = (m.group(2) or "")[:9].ljust(9, "0")
    return int(m.group(1)) * 1_000_000_000 + int(frac)


def fmt_t(ns):
    """奈秒 → 「1791967507.720」（毫秒精度）。"""
    if ns is None:
        return "-"
    return f"{ns // 1_000_000_000}.{(ns % 1_000_000_000) // 1_000_000:03d}"


def fmt_rel(ns, base_ns):
    if ns is None or base_ns is None:
        return ""
    d = (ns - base_ns) / 1e9
    return f"{'+' if d >= 0 else '-'}{abs(d):.2f}s"


def sec(ns):
    return None if ns is None else round(ns / 1e9, 6)


def fmt_num(v):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:
            return "nan"
        a = abs(v)
        if a != 0 and (a >= 1e6 or a < 1e-3):
            return f"{v:.4g}"
        return f"{v:.4f}".rstrip("0").rstrip(".") if "." in f"{v:.4f}" else f"{v:.4f}"
    return str(v)


def short(text, n=160):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


# =====================================================================================================================
# 容器端：數據定位
# =====================================================================================================================
def autodetect_data_root():
    """沒有設定數據根目錄時：在 /workspace（及家目錄）底下 4 層內找名為 experiment_logs 的資料夾（toolkit 的慣例）。"""
    skip = {"build", "install", "log", "node_modules", "__pycache__", ".git"}
    for base in ("/workspace", os.path.expanduser("~"), "/data"):
        if not os.path.isdir(base):
            continue
        found = []
        for dirpath, dirnames, _ in os.walk(base):
            depth = dirpath[len(base):].count(os.sep)
            if os.path.basename(dirpath) == "experiment_logs":
                found.append(dirpath)
                dirnames[:] = []
                continue
            if depth >= 4:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in skip and not d.startswith("sliced_bag_")]
        if found:
            return sorted(found)[0]
    return None


def list_experiments(root):
    """數據根目錄底下的實驗（有 .mcap 的子資料夾），新的在前：[(路徑, mtime)]。"""
    out = []
    if not root or not os.path.isdir(root):
        return out
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if os.path.isdir(p) and (glob.glob(os.path.join(p, "*.mcap")) or glob.glob(os.path.join(p, "*", "*.mcap"))):
            out.append((p, os.path.getmtime(p)))
    return sorted(out, key=lambda x: -x[1])


def _mcaps_in(d):
    return sorted(glob.glob(os.path.join(d, "*.mcap")))


def resolve_data(path, data_root=None):
    """實驗資料夾／bag 資料夾／切片資料夾（sliced_bag_*）／黑盒子快照（incident_*）／.mcap 檔／實驗名稱（相對於數據根目錄）／
    latest → {"input", "exp_dir", "bag_dir", "mcap_files", "rosout_log", "kind", "data_root"}。找不到回 (None, 錯誤說明)。"""
    root = data_root or autodetect_data_root()
    p = (path or "").strip()
    if not p:
        return None, "沒有指定數據：給實驗資料夾、bag 資料夾、切片資料夾或 .mcap 檔的路徑（或 latest＝最新的實驗）"
    if p in ("latest", "最新", "newest"):
        exps = list_experiments(root)
        if not exps:
            return None, f"數據根目錄 {root or '（沒有找到）'} 底下沒有任何實驗"
        p = exps[0][0]
    elif not os.path.isabs(p):
        cands = [os.path.join(root, p)] if root else []
        cands.append(os.path.abspath(p))
        p = next((c for c in cands if os.path.exists(c)), cands[0])
    p = os.path.normpath(p)
    if os.path.isfile(p):
        if not p.endswith(".mcap"):
            return None, f"{p} 不是 .mcap 檔"
        mcaps, bag_dir = [p], os.path.dirname(p)
    elif os.path.isdir(p):
        mcaps, bag_dir = _mcaps_in(p), p
        if not mcaps:
            subs = [d for d in sorted(glob.glob(os.path.join(p, "*"))) if os.path.isdir(d) and _mcaps_in(d)
                    and not os.path.basename(d).startswith("sliced_bag_")]
            pref = [d for d in subs if os.path.basename(d) in ("bag", "mcap")]
            pick = pref or subs
            if len(pick) != 1:
                hint = f"（有 {len(pick)} 個子資料夾有 .mcap：{', '.join(os.path.basename(d) for d in pick[:6])}，請指定其中一個）" if pick else ""
                return None, f"{p} 底下找不到 .mcap{hint}"
            bag_dir = pick[0]
            mcaps = _mcaps_in(bag_dir)
    else:
        hint = f"；數據根目錄 {root} 底下的實驗：{', '.join(os.path.basename(e[0]) for e in list_experiments(root)[:8])}" if root else ""
        return None, f"找不到 {p}（路徑要是容器內看得到的路徑{hint}）"
    parent = os.path.dirname(bag_dir)
    if os.path.exists(os.path.join(bag_dir, "rosout.log")):
        exp_dir = bag_dir
    elif (os.path.basename(bag_dir) in ("bag", "mcap") or os.path.basename(bag_dir).startswith("sliced_bag_")
          or os.path.exists(os.path.join(parent, "rosout.log"))):
        exp_dir = parent
    else:
        exp_dir = bag_dir
    base = os.path.basename(bag_dir)
    kind = ("slice" if base.startswith("sliced_bag_") else "incident" if os.path.basename(exp_dir).startswith("incident_")
            else "experiment" if exp_dir != bag_dir else "bag")
    rosout_log = os.path.join(exp_dir, "rosout.log") if kind != "slice" else os.path.join(bag_dir, "rosout.log")
    return {"input": p, "exp_dir": exp_dir, "bag_dir": bag_dir, "mcap_files": mcaps, "kind": kind,
            "rosout_log": rosout_log if os.path.isfile(rosout_log) else None, "data_root": root}, None


def data_label(data):
    """給人看的數據名稱：實驗資料夾名稱（切片再加上切片名）。"""
    exp = os.path.basename(data["exp_dir"])
    if data["kind"] == "slice":
        return f"{exp}/{os.path.basename(data['bag_dir'])}"
    return exp if data["exp_dir"] != data["bag_dir"] else os.path.basename(data["bag_dir"])


# =====================================================================================================================
# 容器端：MCAP 與 ROS 型別
# =====================================================================================================================
def iter_messages(mcap_files, topics=None, start_ns=None, end_ns=None):
    """依時間順序讀訊息（分割成多個檔案的 bag 一個接一個讀）；end_ns 包含在內。"""
    from mcap.reader import make_reader
    for f in mcap_files:
        with open(f, "rb") as stream:
            reader = make_reader(stream)
            yield from reader.iter_messages(topics=topics, start_time=start_ns,
                                            end_time=None if end_ns is None else end_ns + 1, log_time_order=True)


def last_record_before(mcap_files, topic, t_ns):
    """t_ns 之前（不含）這個 Topic 的最後一則：(schema, channel, message)，沒有就 None。從後往前讀（mcap 的 reverse），
    讀到一則就停；舊版 mcap 沒有 reverse 時從頭讀到 t_ns。"""
    from mcap.reader import make_reader
    for f in reversed(mcap_files):
        with open(f, "rb") as stream:
            reader = make_reader(stream)
            try:
                for rec in reader.iter_messages(topics=[topic], end_time=t_ns, log_time_order=True, reverse=True):
                    return rec
            except TypeError:
                last = None
                for rec in reader.iter_messages(topics=[topic], end_time=t_ns, log_time_order=True):
                    last = rec
                if last is not None:
                    return last
    return None


def last_message_before(mcap_files, topic, t_ns):
    """t_ns 之前（不含）這個 Topic 的最後一則原始訊息，沒有就 None。"""
    rec = last_record_before(mcap_files, topic, t_ns)
    return rec[2] if rec else None


def bag_overview(mcap_files):
    """不反序列化：{start_ns, end_ns, message_count, topics: {topic: {type, encoding, count}}}（有 summary 就用 summary）。"""
    from mcap.reader import make_reader
    topics, start, end, total, need_scan = {}, None, None, 0, False
    for f in mcap_files:
        with open(f, "rb") as stream:
            summ = make_reader(stream).get_summary()
        if summ is None or summ.statistics is None:
            need_scan = True
            continue
        st = summ.statistics
        for ch in summ.channels.values():
            sc = summ.schemas.get(ch.schema_id)
            t = topics.setdefault(ch.topic, {"type": sc.name if sc else None, "encoding": ch.message_encoding, "count": 0})
            t["count"] += st.channel_message_counts.get(ch.id, 0)
        if st.message_count:
            start = st.message_start_time if start is None else min(start, st.message_start_time)
            end = st.message_end_time if end is None else max(end, st.message_end_time)
        total += st.message_count
    if need_scan:
        topics, start, end, total = {}, None, None, 0
        for schema, ch, m in iter_messages(mcap_files):
            t = topics.setdefault(ch.topic, {"type": schema.name if schema else None, "encoding": ch.message_encoding, "count": 0})
            t["count"] += 1
            start = m.log_time if start is None else min(start, m.log_time)
            end = m.log_time if end is None else max(end, m.log_time)
            total += 1
    return {"start_ns": start, "end_ns": end, "message_count": total, "topics": topics}


_CLASS_CACHE = {}


def full_type(t):
    """'pkg/Name' → 'pkg/msg/Name'（get_fields_and_field_types 給的巢狀型別沒有 msg/）。"""
    parts = t.split("/")
    return t if len(parts) == 3 else (f"{parts[0]}/msg/{parts[1]}" if len(parts) == 2 else t)


def msg_class(type_name):
    """ROS 2 訊息類別（rosidl_runtime_py）；載入失敗回 (None, 原因)。"""
    type_name = full_type(type_name)
    if type_name not in _CLASS_CACHE:
        try:
            from rosidl_runtime_py.utilities import get_message
            _CLASS_CACHE[type_name] = (get_message(type_name), None)
        except Exception as e:   # noqa: BLE001
            _CLASS_CACHE[type_name] = (None, f"{type(e).__name__}: {e}")
    return _CLASS_CACHE[type_name]


def deserialize(data, cls):
    from rclpy.serialization import deserialize_message
    return deserialize_message(data, cls)


_FLOATS = {"float", "double", "float32", "float64", "long double"}
_INTS = {"int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64", "octet", "byte", "char", "wchar",
         "boolean", "bool"}
_STATE_INTS = {"uint8", "int8", "octet", "byte", "char", "wchar", "boolean", "bool"}


def parse_type(t):
    t = str(t).strip()
    m = re.match(r"^sequence<(.+?)(?:,\s*(\d+))?>$", t)
    if m:
        return {"kind": "sequence", "elem": m.group(1).strip(), "size": None}
    m = re.match(r"^(.+)\[(\d+)\]$", t)
    if m:
        return {"kind": "sequence", "elem": m.group(1).strip(), "size": int(m.group(2))}
    if t.startswith(("string", "wstring")):
        return {"kind": "string"}
    if t in _FLOATS:
        return {"kind": "float"}
    if t in _INTS:
        return {"kind": "int", "name": t}
    if "/" in t:
        return {"kind": "msg", "name": full_type(t)}
    return {"kind": "unknown", "name": t}


def _fields(cls):
    try:
        return dict(cls.get_fields_and_field_types())
    except Exception:   # noqa: BLE001
        return {}


def _is_vector_cls(cls):
    f = _fields(cls)
    return 2 <= len(f) <= 4 and all(parse_type(t)["kind"] == "float" for t in f.values())


def _is_kv_cls(cls):
    f = _fields(cls)
    return set(f) == {"key", "value"} and all(parse_type(t)["kind"] == "string" for t in f.values())


def _map_field(cls):
    f = _fields(cls)
    for n in NAME_FIELDS:
        if n in f and parse_type(f[n])["kind"] == "string":
            return n
    return None


class MapDict(dict):
    """序列裡的訊息依名稱（name／child_frame_id／key…）展開成的對照表（DiagnosticArray.status、TFMessage.transforms）。"""


def _is_msg(v):
    return hasattr(v, "get_fields_and_field_types")


def leaf_value(v):
    """ROS 值 → 純 Python：訊息→dict（Time→秒）、bytes(1)→int、numpy／array→tuple。"""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (bytes, bytearray)):
        return v[0] if len(v) == 1 else tuple(v)
    if _is_msg(v):
        f = list(v.get_fields_and_field_types())
        if set(f) == {"sec", "nanosec"}:
            return v.sec + v.nanosec * 1e-9
        return {n: leaf_value(getattr(v, n)) for n in f}
    if hasattr(v, "tolist"):
        v = v.tolist()
    if isinstance(v, (list, tuple)):
        return tuple(leaf_value(x) for x in v)
    return str(v)


def _seq_value(seq, rest):
    items = list(seq)
    if items and _is_msg(items[0]):
        cls = type(items[0])
        if _is_kv_cls(cls) and not rest:
            return MapDict((str(kv.key), str(kv.value)) for kv in items)
        mf = _map_field(cls)
        if mf:
            out = MapDict()
            for e in items:
                out[str(getattr(e, mf))] = _extract(e, rest)
            return out
        return tuple(_extract(e, rest) for e in items)
    if rest:
        raise KeyError(".".join(rest))
    return leaf_value(seq)


def _extract(obj, parts):
    if not parts:
        return leaf_value(obj)
    head, rest = parts[0], parts[1:]
    m = re.fullmatch(r"([A-Za-z_]\w*)\[(\d+)\]", head)
    if m:
        v = getattr(obj, m.group(1))
        v = list(v.tolist() if hasattr(v, "tolist") else v)[int(m.group(2))]
        return _extract(v, rest)
    if not hasattr(obj, head):
        raise KeyError(head)
    v = getattr(obj, head)
    if isinstance(v, (list, tuple)) or (hasattr(v, "tolist") and not isinstance(v, (str, bytes))):
        if len(v) == 0:
            return _empty_seq(obj, head, rest)
        return _seq_value(v, rest)
    return _extract(v, rest)


def _empty_seq(obj, field, rest):
    """空的序列要看宣告的型別：訊息的序列（依名稱展開的對照表、key-value）是「沒有任何項目」，基本型別的序列（stop_reasons）
    是「空集合」這個狀態值。"""
    pt = parse_type(_fields(type(obj)).get(field, ""))
    if pt["kind"] == "sequence" and parse_type(pt["elem"])["kind"] == "msg":
        sub, _ = msg_class(parse_type(pt["elem"])["name"])
        if sub is not None and (_is_kv_cls(sub) or _map_field(sub)):
            return MapDict()
        if rest:
            return ()
    if rest:
        raise KeyError(".".join(rest))
    return ()


def extract(msg, key):
    """訊息裡某個 Key 的值：a.b.c、ranges[3]；經過「依名稱展開的序列」時回 MapDict（status.level → {名稱: level}）。"""
    return _extract(msg, [p for p in key.split(".") if p])


def flatten(v, label=""):
    """量測用：把一個 Key 的值攤平成 {項目: 純量或 tuple}——向量分量用 .x，依名稱展開的對照表用 » 串起名稱。"""
    out = {}
    if isinstance(v, MapDict):
        for k, sub in v.items():
            out.update(flatten(sub, f"{label} » {k}" if label else str(k)))
    elif isinstance(v, dict):
        for k, sub in v.items():
            out.update(flatten(sub, f"{label}.{k}" if label else k))
    else:
        out[label or "value"] = v
    return out


# =====================================================================================================================
# 容器端：Key 目錄（型別、維度、資料類別）
# =====================================================================================================================
def _leaf(key, t, category, dim="scalar", **extra):
    d = {"key": key, "type": t, "category": category, "dim": dim}
    d.update({k: v for k, v in extra.items() if v not in (None, [], "")})
    return d


def _walk(cls, prefix, depth, out, map_by=(), skip=None):
    for name, t in _fields(cls).items():
        if name == skip:
            continue
        key = prefix + name
        pt = parse_type(t)
        mb = list(map_by)
        if pt["kind"] == "string":
            out.append(_leaf(key, t, "string?", map_by=mb))
        elif pt["kind"] == "float":
            out.append(_leaf(key, t, "numeric", map_by=mb))
        elif pt["kind"] == "int":
            out.append(_leaf(key, t, "state" if pt["name"] in _STATE_INTS else "integer", map_by=mb))
        elif pt["kind"] == "msg":
            if pt["name"] in TIME_TYPES:
                out.append(_leaf(key, t, "time", map_by=mb))
                continue
            sub, _ = msg_class(pt["name"])
            if sub is None:
                out.append(_leaf(key, t, "unknown", map_by=mb))
            elif _is_vector_cls(sub):
                comps = list(_fields(sub))
                out.append(_leaf(key, t, "vector", f"vector [{len(comps)}]", components=comps, map_by=mb))
            elif _is_kv_cls(sub):
                out.append(_leaf(key, t, "kv", "map", map_by=mb))
            elif depth < MAX_DEPTH:
                _walk(sub, key + ".", depth + 1, out, map_by)
        elif pt["kind"] == "sequence":
            et = parse_type(pt["elem"])
            if et["kind"] == "msg":
                sub, _ = msg_class(et["name"])
                if sub is None:
                    out.append(_leaf(key, t, "unknown", map_by=mb))
                elif _is_kv_cls(sub):
                    out.append(_leaf(key, t, "kv", "map", map_by=mb))
                elif _map_field(sub) and depth < MAX_DEPTH:
                    mf = _map_field(sub)
                    _walk(sub, key + ".", depth + 1, out, tuple(map_by) + (f"{key}.{mf}",), skip=mf)
                else:
                    out.append(_leaf(key, t, "array", "sequence", map_by=mb, note="訊息的序列（量測長度）"))
            elif et["kind"] == "float":
                n = pt["size"]
                if n and "covariance" in name and int(math.isqrt(n)) ** 2 == n and n >= 4:
                    r = int(math.isqrt(n))
                    out.append(_leaf(key, t, "matrix", f"matrix [{r}x{r}]", map_by=mb))
                elif n and n <= 4:
                    out.append(_leaf(key, t, "vector", f"vector [{n}]", components=[f"[{i}]" for i in range(n)], map_by=mb))
                else:
                    out.append(_leaf(key, t, "array", f"vector [{n}]" if n else "vector [dynamic]", map_by=mb))
            elif et["kind"] in ("int", "string"):
                out.append(_leaf(key, t, "set?", f"vector [{pt['size']}]" if pt["size"] else "vector [dynamic]", map_by=mb))
            else:
                out.append(_leaf(key, t, "unknown", map_by=mb))
        else:
            out.append(_leaf(key, t, "unknown", map_by=mb))


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def to_number(v):
    if _is_num(v):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if re.fullmatch(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?", s):
            return float(s)
    return None


def describe_keys(cls, samples):
    """訊息類別＋抽樣的訊息 → Key 目錄（每個 Key：型別、維度、類別、抽樣看到的值）。"""
    leaves = []
    _walk(cls, "", 0, leaves)
    for leaf in leaves:
        cat = leaf["category"]
        if cat in ("time", "unknown"):
            continue
        entries = {}
        for s in samples:
            try:
                flat = flatten(extract(s, leaf["key"]))
            except Exception:   # noqa: BLE001
                continue
            for k, v in flat.items():
                entries.setdefault(k, []).append(v)
        if leaf.get("map_by"):
            names = sorted({k.split(" » ")[0] for k in entries})
            leaf["entries"] = len(entries)
            if names:
                leaf["examples"] = [short(n, 60) for n in names[:3]]
        if cat == "string?":
            vals = [v for vs in entries.values() for v in vs if isinstance(v, str)]
            per_entry = max((len(set(vs)) for vs in entries.values()), default=0)
            maxlen = max((len(v) for v in vals), default=0)
            enum_like = per_entry <= STATE_FEW_DISTINCT or (per_entry <= STATE_MAX_DISTINCT and maxlen <= STATE_MAX_LEN)
            leaf["category"] = "state" if enum_like else "text"
            if leaf["category"] == "state":
                leaf["values"] = [short(v, 40) for v in _top_values(vals, 6)]
            else:
                leaf["distinct"] = len(set(vals))
        elif cat == "set?":
            lens = [len(v) for vs in entries.values() for v in vs if isinstance(v, tuple)]
            avg = sum(lens) / len(lens) if lens else 0
            leaf["category"] = "state" if avg <= SET_MAX_LEN else "array"
            if leaf["category"] == "state":
                leaf["dim"] = "set"
                items = [x for vs in entries.values() for v in vs if isinstance(v, tuple) for x in v]
                if items:
                    leaf["values"] = [short(x, 40) for x in _top_values(items, 6)]
        elif cat == "integer":
            nums = [v for vs in entries.values() for v in vs if _is_num(v)]
            leaf["category"] = "numeric"
            if nums and len(set(nums)) <= INT_STATE_MAX_DISTINCT:
                leaf["note"] = "整數、相異值少：量測時當狀態跳轉"
                leaf["values"] = [str(x) for x in _top_values(nums, 6)]
            elif nums:
                leaf["range"] = [min(nums), max(nums)]
        elif cat == "kv":
            nums = sum(1 for vs in entries.values() if vs and all(to_number(v) is not None for v in vs))
            leaf["numeric_entries"] = nums
        elif cat == "state":
            vals = [v for vs in entries.values() for v in vs]
            if vals:
                leaf["values"] = [str(x) for x in _top_values(vals, 6)]
        elif cat == "numeric":
            nums = [v for vs in entries.values() for v in vs if _is_num(v)]
            if nums:
                leaf["range"] = [round(min(nums), 6), round(max(nums), 6)]
    return [lf for lf in leaves if lf["category"] != "unknown"]


def _top_values(vals, n):
    counts = {}
    for v in vals:
        try:
            counts[v] = counts.get(v, 0) + 1
        except TypeError:
            continue
    return [v for v, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:n]]


# =====================================================================================================================
# 容器端：全域 Topic Metadata 索引（預先建立、快取）
# =====================================================================================================================
def _files_signature(files):
    return [{"path": f, "size": os.path.getsize(f), "mtime": int(os.path.getmtime(f))} for f in files]


def _index_paths(data):
    return (os.path.join(data["bag_dir"], INDEX_NAME + ".json"), os.path.join(data["bag_dir"], INDEX_NAME + ".yaml"))


def load_index(data):
    path, _ = _index_paths(data)
    try:
        with open(path, encoding="utf-8") as f:
            idx = json.load(f)
    except (OSError, ValueError):
        return None
    if idx.get("version") != INDEX_VERSION or idx.get("source_files") != _files_signature(data["mcap_files"]):
        return None
    return idx


def build_index(data, refresh=False, write=True):
    """全域 Topic Metadata：時間範圍、每個 Topic 的型別、筆數、頻率、起訖、角色（worker／log／text_only／empty／undecodable）
    與 Key 目錄。結果快取在 bag 資料夾的 topic_metadata.json（.yaml 給人看）；來源檔案沒變就直接讀快取。"""
    if not refresh:
        cached = load_index(data)
        if cached:
            cached["cached"] = True
            return cached
    ov = bag_overview(data["mcap_files"])
    counts = {t: v["count"] for t, v in ov["topics"].items()}
    strides = {t: max(1, c // SAMPLES_PER_TOPIC) for t, c in counts.items()}
    seen, samples, first, last, decode_err = {}, {}, {}, {}, {}
    for schema, ch, m in iter_messages(data["mcap_files"]):
        t = ch.topic
        first.setdefault(t, m.log_time)
        last[t] = m.log_time
        i = seen.get(t, 0)
        seen[t] = i + 1
        if t in LOG_TOPICS or i % strides.get(t, 1) or len(samples.get(t, ())) >= SAMPLES_PER_TOPIC or t in decode_err:
            continue
        cls, err = msg_class(schema.name) if schema else (None, "沒有 schema")
        if cls is None:
            decode_err[t] = err
            continue
        try:
            samples.setdefault(t, []).append(deserialize(m.data, cls))
        except Exception as e:   # noqa: BLE001
            decode_err[t] = f"{type(e).__name__}: {e}"
    topics = []
    duration = (ov["end_ns"] - ov["start_ns"]) / 1e9 if ov["start_ns"] is not None else 0
    for t, info in sorted(ov["topics"].items()):
        n = info["count"]
        entry = {"topic": t, "type": info["type"], "message_count": n,
                 "first_sec": sec(first.get(t)), "last_sec": sec(last.get(t))}
        if n and duration > 0:
            entry["avg_frequency_hz"] = round(n / duration, 3)   # 同 toolkit：筆數 ÷ 整段時間（只有幾筆的 Topic 才不會算出幾千 Hz）
        if t in LOG_TOPICS:
            entry["role"] = "log"
        elif n == 0:
            entry["role"] = "empty"
        elif t in decode_err:
            entry["role"], entry["error"] = "undecodable", decode_err[t]
        else:
            cls, err = msg_class(info["type"])
            keys = describe_keys(cls, samples.get(t, [])) if cls else []
            entry["keys"] = keys
            usable = [k for k in keys if k["category"] in WORKER_CATEGORIES]
            entry["role"] = "worker" if usable else "text_only"
        topics.append(entry)
    idx = {"version": INDEX_VERSION, "created": time.strftime("%Y-%m-%d %H:%M:%S"), "label": data_label(data),
           "bag_dir": data["bag_dir"], "exp_dir": data["exp_dir"], "kind": data["kind"],
           "source_files": _files_signature(data["mcap_files"]), "rosout_log": data["rosout_log"],
           "start_ns": ov["start_ns"], "end_ns": ov["end_ns"], "start_sec": sec(ov["start_ns"]), "end_sec": sec(ov["end_ns"]),
           "duration_sec": round((ov["end_ns"] - ov["start_ns"]) / 1e9, 3) if ov["start_ns"] is not None else 0,
           "message_count": ov["message_count"], "topics": topics}
    if write:
        idx["index_file"] = write_index(data, idx)
    return idx


def write_index(data, idx):
    jpath, ypath = _index_paths(data)
    try:
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(idx, f, ensure_ascii=False, indent=1)
        try:
            import yaml
            with open(ypath, "w", encoding="utf-8") as f:
                yaml.safe_dump(idx, f, allow_unicode=True, sort_keys=False, width=140)
        except Exception:   # noqa: BLE001  沒有 PyYAML：只寫 json
            pass
        return jpath
    except OSError:
        return None


def key_summary(entry, limit=8):
    """一個 Topic 的 Key 一行摘要：linear(vector[3]) mode(state)…；Orchestrator 與 mcap_analyzer 的總表用。"""
    parts = []
    for k in entry.get("keys", []):
        if k["category"] in ("time",) or k["key"].startswith("header."):
            continue
        tag = k["category"]
        if k["category"] == "vector":
            tag = k["dim"].replace(" ", "")
        if k.get("map_by"):
            tag += f"×{k.get('entries', '?')}"
        parts.append(f"{k['key']}({tag})")
    more = f" …共 {len(parts)} 個" if len(parts) > limit else ""
    return " ".join(parts[:limit]) + more


def find_topic(idx, topic):
    for e in idx["topics"]:
        if e["topic"] == topic:
            return e
    # 容錯：少了開頭的 /、大小寫
    norm = "/" + topic.strip().lstrip("/")
    for e in idx["topics"]:
        if e["topic"].lower() == norm.lower():
            return e
    return None


def find_key(entry, key):
    for k in entry.get("keys", []):
        if k["key"] == key:
            return k
    # 向量分量（linear.x）、對照表的子項目：用最長的前綴找描述
    best = None
    for k in entry.get("keys", []):
        if key.startswith(k["key"] + ".") or key.startswith(k["key"] + "["):
            if best is None or len(k["key"]) > len(best["key"]):
                best = k
    if best:
        d = dict(best)
        d["key"] = key
        if best["category"] == "vector":
            d["category"], d["dim"] = "numeric", "scalar"
        return d
    return None


# =====================================================================================================================
# 容器端：rosout（Log 智慧過濾）
# =====================================================================================================================
_LINE_RE = re.compile(r"^\[(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\]\s+\[(?P<sec>\d+)(?:\.(?P<frac>\d+))?\]\s+"
                      r"\[(?P<node>[^\]]*)\]:\s?(?P<msg>.*)$")


def _yaml_block_event(block):
    """`ros2 topic echo /rosout` 的原始 YAML 區塊（舊版錄製工具沒有經過 rosout_formatter）→ 事件；同 toolkit 的 process_doc。"""
    secs, nsec, level, name, msg_lines, in_msg = None, 0, 20, "unknown", [], False
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("sec:") and secs is None:
            secs = int(s.split(":", 1)[1].strip() or 0)
        elif s.startswith("nanosec:"):
            nsec = int(s.split(":", 1)[1].strip() or 0)
        elif s.startswith("level:"):
            level = int(s.split(":", 1)[1].strip() or 20)
        elif s.startswith("name:"):
            name = s.split(":", 1)[1].strip().strip("'\"")
            in_msg = False
        elif s.startswith("msg:"):
            in_msg = True
            msg_lines.append(s.split(":", 1)[1].strip().strip("'\""))
        elif s.startswith(("file:", "function:", "line:", "stamp:")):
            in_msg = False
        elif in_msg:
            msg_lines.append(s)
    if secs is None:
        return None
    return {"t_ns": secs * 1_000_000_000 + nsec, "level": LEVEL_NAMES.get(level, "INFO"), "node": name,
            "msg": " ".join(msg_lines).strip()}


def parse_rosout_file(path):
    """rosout.log（toolkit 的 rosout_formatter 格式：[LEVEL] [sec.nanosec] [node]: msg；多行訊息接在後面）或原始的 YAML 區塊。
    回傳 (events, 無法解析的行數)。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    events, unparsed = [], 0
    if re.search(r"^---\s*$", text, re.M) and re.search(r"^\s*level:\s*\d+", text, re.M) and not _LINE_RE.search(text):
        for block in re.split(r"^---\s*$", text, flags=re.M):
            e = _yaml_block_event(block) if block.strip() else None
            if e:
                events.append(e)
        return events, 0
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _LINE_RE.match(line.strip())
        if m:
            frac = (m.group("frac") or "")[:9].ljust(9, "0")
            level = m.group("level").upper()
            events.append({"t_ns": int(m.group("sec")) * 1_000_000_000 + int(frac),
                           "level": "WARN" if level == "WARNING" else level,
                           "node": m.group("node"), "msg": m.group("msg").strip(), "line": line_no})
        elif events:
            events[-1]["msg"] = (events[-1]["msg"] + " " + line.strip()).strip()   # 多行訊息的續行
        else:
            unparsed += 1
    return events, unparsed


def rosout_from_bag(mcap_files):
    """bag 裡的 /rosout（沒有就用 /rosout_agg）→ 事件；時間用 MCAP log_time（跟其他 Topic 同一個時鐘）。"""
    cls, err = msg_class("rcl_interfaces/msg/Log")
    if cls is None:
        return None, f"載入 rcl_interfaces/msg/Log 失敗：{err}"
    for topic in LOG_TOPICS:
        events = []
        for schema, ch, m in iter_messages(mcap_files, topics=[topic]):
            try:
                log = deserialize(m.data, cls)
            except Exception:   # noqa: BLE001
                continue
            lv = log.level
            lv = lv[0] if isinstance(lv, (bytes, bytearray)) else int(lv)
            events.append({"t_ns": m.log_time, "level": LEVEL_NAMES.get(lv, "INFO"), "node": str(log.name),
                           "msg": " ".join(str(log.msg).split()), "stamp_ns": log.stamp.sec * 1_000_000_000 + log.stamp.nanosec})
        if events:
            return events, topic
    return [], None


def load_log_events(data, source="auto"):
    """Log 事件與來源說明。auto：bag 裡有 /rosout 就用它（最完整、時間跟其他 Topic 對齊），否則用 rosout.log。
    回傳 (events, 來源說明, 錯誤)。"""
    errors = []
    if source in ("auto", "bag"):
        events, topic = rosout_from_bag(data["mcap_files"])
        if events:
            return events, f"bag 的 {topic}（時間＝MCAP log_time，與其他 Topic 同一個時鐘）", None
        if events is None:
            errors.append(topic)
        if source == "bag":
            return [], "", "bag 裡沒有 /rosout 訊息" + (f"（{errors[0]}）" if errors else "")
    if data.get("rosout_log"):
        events, unparsed = parse_rosout_file(data["rosout_log"])
        note = f"{data['rosout_log']}（時間＝Log 的 stamp；與 MCAP log_time 同一台機器的時鐘）"
        if unparsed:
            note += f"；{unparsed} 行無法解析"
        return events, note, None
    return [], "", "找不到 Log：bag 裡沒有 /rosout，實驗資料夾也沒有 rosout.log（錄製時要加 /rosout）"


_NUM_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?")
RECORDER_NODES = re.compile(r"^(rosbag2(_\w+)?|ros2_bag\w*)$")


def is_recorder_node(node):
    """錄製工具自己的 Log（rosbag2_recorder 的 Subscribed to topic…）：跟受測系統無關，預設不列、不交給 Orchestrator。"""
    return bool(RECORDER_NODES.match(str(node or "").strip("/").split("/")[-1]))


def dedup_events(events, merge_numbers=True):
    """Log 去重：同一個 Node、同一層級、同一句話（merge_numbers＝只差在數字也算同一句）合成一個「唯一訊號」，
    依第一次出現的時間排序編號 L1、L2…（過濾之前編號，所以 --level／--node 不會改變編號）。"""
    groups, order = {}, []
    for e in sorted(events, key=lambda x: x["t_ns"]):
        msg = e["msg"]
        k = (e["level"], e["node"], _NUM_RE.sub("#", msg) if merge_numbers else msg)
        g = groups.get(k)
        if g is None:
            g = groups[k] = {"level": e["level"], "node": e["node"], "message": msg, "count": 0, "times_ns": [],
                             "variants": []}
            order.append(g)
        g["count"] += 1
        g["times_ns"].append(e["t_ns"])
        if msg not in g["variants"] and len(g["variants"]) < 4:
            g["variants"].append(msg)
    for i, g in enumerate(order, 1):
        g["id"] = f"L{i}"
        g["first_ns"], g["last_ns"] = g["times_ns"][0], g["times_ns"][-1]
    return order


def signal_json(g, base_ns=None, max_times=50):
    d = {"id": g["id"], "level": g["level"], "node": g["node"], "count": g["count"], "message": g["message"],
         "first_sec": sec(g["first_ns"]), "last_sec": sec(g["last_ns"]),
         "times_sec": [sec(t) for t in g["times_ns"][:max_times]]}
    if base_ns is not None:
        d["first_rel"] = round((g["first_ns"] - base_ns) / 1e9, 3)
    if len(g["variants"]) > 1:
        d["variants"] = g["variants"]
    return d


# =====================================================================================================================
# 容器端：時間窗
# =====================================================================================================================
def parse_window(text, base_ns=None):
    """--window S,E[,錨點[,標籤[,切片]]] → {start_ns, end_ns, anchor_ns, label, data}；S／E 可以是 epoch 秒或 +相對秒；
    切片＝這個時間窗要讀的切片資料夾（analysis_run 切好的），省略時讀原本的數據。"""
    raw = str(text).strip()
    if "," in raw:
        parts = [p.strip() for p in raw.split(",")]
    else:   # 「+0.00s～+30.54s」「0.00s_30.54s」「10 to 20」「3.37s-31.79s」：模型常照抄畫面上的寫法（負號不算分隔）
        parts = [p.strip() for p in re.split(r"\s*(?:～|~|_|\bto\b|至|到)\s*|(?<=[\ds])\s*-\s*(?=[+\d])", raw) if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"時間窗要寫成「開始,結束」（epoch 秒或 +相對秒，例如 +10,+20），收到：{text}")
    start, end = parse_time(parts[0], base_ns), parse_time(parts[1], base_ns)
    if end < start:
        start, end = end, start
    anchor = parse_time(parts[2], base_ns) if len(parts) > 2 and parts[2] else None
    label = parts[3] if len(parts) > 3 else ""
    return {"start_ns": start, "end_ns": end, "anchor_ns": anchor, "label": label, "data": parts[4] if len(parts) > 4 else ""}


def window_text(w, base_ns=None):
    rel = f"（數據開頭 {fmt_rel(w['start_ns'], base_ns)} ～ {fmt_rel(w['end_ns'], base_ns)}）" if base_ns is not None else ""
    anc = (f"；錨點 {fmt_t(w['anchor_ns'])}" + (f"[{fmt_rel(w['anchor_ns'], base_ns)}]" if base_ns is not None else "")) if w.get("anchor_ns") else ""
    return f"{fmt_t(w['start_ns'])} ～ {fmt_t(w['end_ns'])}（{(w['end_ns'] - w['start_ns']) / 1e9:.1f} 秒）{rel}{anc}"


def clamp_window(w, start_ns, end_ns):
    """時間窗限制在數據範圍內（錨點不動）；完全不重疊時回 None。"""
    if start_ns is None or w["end_ns"] < start_ns or w["start_ns"] > end_ns:
        return None
    out = dict(w)
    out["start_ns"], out["end_ns"] = max(w["start_ns"], start_ns), min(w["end_ns"], end_ns)
    if (out["start_ns"], out["end_ns"]) != (w["start_ns"], w["end_ns"]):
        out["clamped"] = True
    return out


# =====================================================================================================================
# 容器端：特徵量測
# =====================================================================================================================
def collect_series(mcap_files, topic, type_name, keys, window):
    """時間窗內這個 Topic 的訊息時間與每個 Key 攤平後的值：(times_ns, {key: {項目: [(t, v)]}}, {key: 錯誤})。"""
    cls, err = msg_class(type_name)
    if cls is None:
        raise RuntimeError(f"載入訊息型別 {type_name} 失敗：{err}（自訂訊息要先載入 Workspace，見 ROS2_workspace_env）")
    times, series, errors = [], {k: {} for k in keys}, {}
    for schema, ch, m in iter_messages(mcap_files, topics=[topic], start_ns=window["start_ns"], end_ns=window["end_ns"]):
        times.append(m.log_time)
        try:
            msg = deserialize(m.data, cls)
        except Exception as e:   # noqa: BLE001
            errors.setdefault("_deserialize", f"{type(e).__name__}: {e}")
            continue
        for k in keys:
            try:
                flat = flatten(extract(msg, k))
            except Exception as e:   # noqa: BLE001
                errors.setdefault(k, f"{type(e).__name__}: {e}")
                continue
            for entry, v in flat.items():
                series[k].setdefault(entry, []).append((m.log_time, v))
    return times, series, errors


def carry_in_values(mcap_files, topic, type_name, keys, t_ns):
    """時間窗開始前這個 Topic 最後一則訊息、每個 Key 攤平後的值：{key: {項目: (t, 值)}}（沒有就空的）。
    只在狀態改變時才發布的 Topic（例如 TRANSIENT_LOCAL 的狀態），時間窗開始時的狀態是之前的最後一則；不沿用的話，
    窗內第一則被當成起始狀態、少算一次跳轉（實測 /system/safety_gate_status：[NO_CMD_VEL_RAW] → [] 沒有算到）。"""
    m = last_message_before(mcap_files, topic, t_ns)
    cls, _ = msg_class(type_name)
    if m is None or cls is None:
        return {}
    try:
        msg = deserialize(m.data, cls)
    except Exception:   # noqa: BLE001
        return {}
    out = {}
    for k in keys:
        try:
            out[k] = {entry: (m.log_time, v) for entry, v in flatten(extract(msg, k)).items()}
        except Exception:   # noqa: BLE001
            continue
    return out


EDGE_MIN_MESSAGES = 5        # 至少這麼多筆才看得出固定頻率；更少的多半只在狀態改變時才發布，頭尾沒有訊息不代表停止
EDGE_SILENCE_PERIODS = 10    # 時間窗頭／尾沒有訊息超過「中位數週期 × 這個倍數」（且 ≥1 秒）＝中途才開始／中途停止發布
RECORDING_WARMUP_SEC = 5.0   # 錄製開始後這麼久內才出現的第一筆，多半是 rosbag2 發現、訂閱 Topic 的延遲或節點剛啟動，不算「中途才開始」


def rate_features(times, window, data_start_ns=None):
    """訊息頻率與中斷：筆數、平均 Hz、最大間隔；間隔超過中位數週期 3 倍（且 ≥0.5 秒）的列出來。
    固定頻率的 Topic（≥EDGE_MIN_MESSAGES 筆）再看時間窗的頭尾：started_late＝中途才開始發布、stopped_early＝中途停止發布。
    實測：/cmd_vel_raw 只在 +13～+21s 發布，只看相鄰訊息的間隔會得到「沒有訊息中斷」，worker 因此判斷指令整段持續發送。
    data_start_ns：時間窗從數據開頭起算、第一筆在錄製開始 RECORDING_WARMUP_SEC 秒內＝錄製剛開始（warmup_start），不算中途才開始
    （實測開機的範例：/cmd_vel 在 +1.15s 才有第一筆，被當成「速度指令缺失」的證據）。"""
    n = len(times)
    out = {"messages": n}
    if n == 0:
        return out
    out["first_sec"], out["last_sec"] = sec(times[0]), sec(times[-1])
    out["starts_after_window_sec"] = round((times[0] - window["start_ns"]) / 1e9, 3)
    out["ends_before_window_sec"] = round((window["end_ns"] - times[-1]) / 1e9, 3)
    if n >= 2:
        span = (times[-1] - times[0]) / 1e9
        out["avg_hz"] = round((n - 1) / span, 3) if span > 0 else None
        gaps = sorted(((times[i + 1] - times[i], times[i]) for i in range(n - 1)), reverse=True)
        periods = sorted(times[i + 1] - times[i] for i in range(n - 1))
        median = periods[len(periods) // 2]
        out["max_gap_sec"] = round(gaps[0][0] / 1e9, 3)
        thr = max(3 * median, 500_000_000)
        out["gaps"] = [{"start_sec": sec(t), "duration_sec": round(g / 1e9, 3)} for g, t in gaps[:3] if g > thr]
        if n >= EDGE_MIN_MESSAGES:
            edge = max(EDGE_SILENCE_PERIODS * median, 1_000_000_000)
            out["started_late"] = times[0] - window["start_ns"] > edge
            if (out["started_late"] and data_start_ns is not None and window["start_ns"] - data_start_ns < 1_000_000_000
                    and times[0] - data_start_ns <= RECORDING_WARMUP_SEC * 1e9):
                out["started_late"], out["warmup_start"] = False, True
            out["stopped_early"] = window["end_ns"] - times[-1] > edge
            # 中途開始又中途停止、中間沒有中斷＝一段連續的發布（實測 e4b 把分開的兩個指標讀成「間歇性」）
            out["single_session"] = out["started_late"] and out["stopped_early"] and not out["gaps"]
    return out


def numeric_features(points):
    ts = [t for t, _ in points]
    arr = [float(v) for _, v in points]
    n = len(arr)
    mn, mx = min(arr), max(arr)
    mean = sum(arr) / n
    var = sum((x - mean) ** 2 for x in arr) / n
    std = math.sqrt(var)
    slope = 0.0
    if n > 1:
        t0 = ts[0]
        tn = [(t - t0) / 1e9 for t in ts]
        st, sv = sum(tn), sum(arr)
        stv = sum(a * b for a, b in zip(tn, arr))
        stt = sum(a * a for a in tn)
        den = n * stt - st * st
        slope = (n * stv - st * sv) / den if den else 0.0
    spikes = []
    if std > 1e-9:
        spikes = [{"t_ns": t, "value": v} for t, v in zip(ts, arr) if abs(v - mean) > SPIKE_SIGMA * std]
    jump = None
    if n > 1:
        i = max(range(n - 1), key=lambda k: abs(arr[k + 1] - arr[k]))
        jump = {"t_ns": ts[i + 1], "from": arr[i], "to": arr[i + 1], "delta": arr[i + 1] - arr[i]}
    constant = std <= 1e-9 * max(1.0, abs(mean))
    out = {"kind": "numeric", "samples": n, "min": mn, "max": mx, "mean": mean, "variance": var, "std": std,
           "slope_per_sec": slope, "first": arr[0], "last": arr[-1], "constant": constant,
           "spike_count": len(spikes), "spikes": spikes[:8], "max_jump": None if constant else jump}
    # 只有幾種值的數值（實測 /cmd_vel 的 linear.x：0 → 0.1 → 0）：尖峰、最大跳變只看得到一次，回到 0 的時間看不到 → 列每次切換
    levels = len(set(arr))
    if not constant and levels <= STEP_MAX_LEVELS:
        steps = [{"t_ns": ts[i], "from": arr[i - 1], "to": arr[i]} for i in range(1, n) if arr[i] != arr[i - 1]]
        out.update(levels=levels, step_count=len(steps), steps=steps[:12])
    return out


def _state_key(v):
    if isinstance(v, tuple):
        return tuple(sorted(str(x) for x in v))
    return v


def state_text(v):
    """一個狀態值給人看的寫法（集合寫成 [a, b]、空字串寫成 ""），跟狀態跳轉的寫法一致。"""
    return _state_str(_state_key(v))


def state_features(points, window_end_ns, initial=None, window_start_ns=None):
    """狀態的跳轉與占比。initial＝時間窗開始前最後一則的 (t, 值)：當成時間窗開頭的狀態（跳轉、占比從時間窗開頭算），
    窗內第一則跟它不同就算一次跳轉。"""
    carried = None
    if initial is not None and window_start_ns is not None and initial[0] < points[0][0]:
        carried = initial[0]
        points = [(window_start_ns, initial[1])] + list(points)
    ts = [t for t, _ in points]
    vals = [_state_key(v) for _, v in points]
    transitions, dwell = [], {}
    seg_start, cur = ts[0], vals[0]
    for t, v in zip(ts[1:], vals[1:]):
        if v != cur:
            tr = {"t_ns": t, "from": _state_str(cur), "to": _state_str(v)}
            if isinstance(v, tuple) and isinstance(cur, tuple):
                tr["added"] = sorted(set(v) - set(cur))
                tr["removed"] = sorted(set(cur) - set(v))
            transitions.append(tr)
            dwell[cur] = dwell.get(cur, 0) + (t - seg_start)
            seg_start, cur = t, v
    end = max(window_end_ns, ts[-1])
    dwell[cur] = dwell.get(cur, 0) + (end - seg_start)
    total = sum(dwell.values()) or 1
    share = sorted(((_state_str(k), round(v / total, 3)) for k, v in dwell.items()), key=lambda x: -x[1])
    out = {"kind": "state", "samples": len(vals) - (carried is not None), "first": _state_str(vals[0]),
           "last": _state_str(vals[-1]), "distinct": len(dwell), "transition_count": len(transitions),
           "transitions": transitions[:12], "time_share": share[:6]}
    if carried is not None:
        out["carried_from_ns"] = carried
        out["carried_age_sec"] = round((window_start_ns - carried) / 1e9, 3)
    return out


def _state_str(v):
    if isinstance(v, tuple):
        return "[" + ", ".join(str(x) for x in v) + "]"
    return '""' if v == "" else str(v)


def array_features(points):
    lens = [(t, len(v)) for t, v in points if isinstance(v, tuple)]
    means = []
    for t, v in points:
        nums = [float(x) for x in v if _is_num(x)] if isinstance(v, tuple) else []
        nums = [x for x in nums if not math.isinf(x) and not math.isnan(x)]
        if nums:
            means.append((t, sum(nums) / len(nums)))
    out = {"kind": "array", "samples": len(points)}
    if lens:
        ls = [x for _, x in lens]
        out["length_min"], out["length_max"] = min(ls), max(ls)
    if means:
        out["element_mean"] = numeric_features(means)
    return out


def entry_kind(values, hint):
    """一個項目的值序列 → numeric／state／array（同 toolkit：整數而且相異值 ≤10 當狀態跳轉）。"""
    if hint == "array":
        return "array"
    if any(isinstance(v, tuple) for v in values):
        return "state" if hint in ("state", "set") or all(len(v) <= SET_MAX_LEN for v in values if isinstance(v, tuple)) else "array"
    if hint == "state" or any(isinstance(v, bool) for v in values):
        return "state"
    nums = [to_number(v) for v in values]
    if all(x is not None for x in nums):
        if hint in ("numeric", "vector", "matrix") and not all(_is_num(v) and isinstance(v, int) for v in values):
            return "numeric"
        if all(float(x).is_integer() for x in nums) and len(set(nums)) <= INT_STATE_MAX_DISTINCT:
            return "state"
        return "numeric"
    return "state"


def entry_name(key, label, desc):
    """項目的完整名稱：value → Key 本身；對照表的項目 → key[名稱]；向量分量 → key.x。"""
    if label == "value":
        return key
    if desc and (desc.get("map_by") or desc.get("category") == "kv"):
        return f"{key}[{label}]"
    return f"{key}.{label}"


def measure_key(entries, desc, window, key="", carry=None):
    """一個 Key 在一個時間窗的特徵：每個項目各自量（向量分量、對照表的每個名稱）。flags 是程式判斷的異常指標文字。
    carry＝carry_in_values 這個 Key 的部分（{項目: (t, 值)}）：狀態項目沿用成時間窗開頭的狀態。"""
    hint = desc.get("category") if desc else None
    out, flags = {}, []
    for label, points in entries.items():
        if not points:
            continue
        values = [v for _, v in points]
        kind = entry_kind(values, hint)
        if kind == "numeric":
            pts = [(t, to_number(v)) for t, v in points]
            f = numeric_features(pts)
            if f["spike_count"]:
                flags.append(f"{entry_name(key, label, desc)} 尖峰 {f['spike_count']} 個")
            if f.get("step_count"):
                flags.append(f"{entry_name(key, label, desc)} 數值切換 {f['step_count']} 次（只有 {f['levels']} 種值）")
        elif kind == "array":
            f = array_features(points)
        else:
            f = state_features(points, window["end_ns"], initial=(carry or {}).get(label), window_start_ns=window["start_ns"])
            if f["transition_count"]:
                flags.append(f"{entry_name(key, label, desc)} 狀態跳轉 {f['transition_count']} 次")
        out[label] = f
    return out, flags


def data_type_of(desc):
    """frontmatter 的 data_type：scalar／vector_3d／state／key_value／matrix／array。"""
    if not desc:
        return "unknown"
    c = desc.get("category")
    if c == "vector":
        m = re.search(r"\[(\d+)\]", desc.get("dim", ""))
        return f"vector_{m.group(1)}d" if m else "vector"
    return {"numeric": "scalar", "state": "state", "kv": "key_value", "matrix": "matrix", "array": "array"}.get(c, c or "unknown")


def changed(f):
    """這個項目在時間窗內有沒有變化（有變化的才列在文字輸出裡；對照表常有幾十個不變的項目）。"""
    if f["kind"] == "state":
        return f["transition_count"] > 0
    if f["kind"] == "numeric":
        return not f["constant"]
    return True


def feature_lines(label, f, base_ns, indent="     "):
    """一個項目的特徵 → 給模型看的一兩行（數字由程式算好）。"""
    if f["kind"] == "numeric":
        if f["constant"]:
            return [f"{indent}{label}：常數 {fmt_num(f['first'])}（{f['samples']} 筆）"]
        line = (f"{indent}{label}：min {fmt_num(f['min'])}  max {fmt_num(f['max'])}  mean {fmt_num(f['mean'])}  "
                f"std {fmt_num(f['std'])}  slope {fmt_num(f['slope_per_sec'])}/s  首 {fmt_num(f['first'])}→末 {fmt_num(f['last'])}"
                f"（{f['samples']} 筆）")
        lines = [line]
        if f["spike_count"]:
            sp = "、".join(f"{fmt_t(s['t_ns'])}[{fmt_rel(s['t_ns'], base_ns)}]={fmt_num(s['value'])}" for s in f["spikes"][:4])
            lines.append(f"{indent}  尖峰（離均值 >{SPIKE_SIGMA}σ）{f['spike_count']} 個：{sp}")
        j = f.get("max_jump")
        if f.get("step_count"):
            st = "、".join(f"{fmt_t(s['t_ns'])}[{fmt_rel(s['t_ns'], base_ns)}] {fmt_num(s['from'])}→{fmt_num(s['to'])}"
                          for s in f["steps"][:6])
            lines.append(f"{indent}  數值切換 {f['step_count']} 次（只有 {f['levels']} 種值）：{st}"
                         + (f"…其餘 {f['step_count'] - 6} 次見 --json" if f["step_count"] > 6 else ""))
        elif j and abs(j["delta"]) > 0:
            lines.append(f"{indent}  最大跳變 {fmt_num(j['from'])}→{fmt_num(j['to'])} @ {fmt_t(j['t_ns'])}[{fmt_rel(j['t_ns'], base_ns)}]")
        return lines
    if f["kind"] == "array":
        s = f"{indent}{label}：陣列（{f['samples']} 筆"
        if "length_min" in f:
            s += f"，長度 {f['length_min']}～{f['length_max']}"
        s += "）"
        lines = [s]
        if f.get("element_mean"):
            em = f["element_mean"]
            lines.append(f"{indent}  元素平均：min {fmt_num(em['min'])} max {fmt_num(em['max'])} mean {fmt_num(em['mean'])} "
                         f"std {fmt_num(em['std'])}" + (f"，尖峰 {em['spike_count']} 個" if em["spike_count"] else ""))
        return lines
    share = "、".join(f"{v} {round(p * 100)}%" for v, p in f["time_share"][:4])
    # 沿用的那一則比時間窗開頭早 1 秒以上才註明（固定頻率的 Topic 沿用的是前一則，不用講）
    carried = (f"；時間窗開始時的狀態沿用 {fmt_t(f['carried_from_ns'])}[{fmt_rel(f['carried_from_ns'], base_ns)}] 的最後一則"
               if f.get("carried_age_sec", 0) > 1.0 else "")
    if not f["transition_count"]:
        return [f"{indent}{label}：狀態不變 = {short(f['first'], 80)}（{f['samples']} 筆{carried}）"]
    lines = [f"{indent}{label}：狀態跳轉 {f['transition_count']} 次（首 {short(f['first'], 60)} → 末 {short(f['last'], 60)}；"
             f"占比 {share}{carried}）"]
    for tr in f["transitions"][:6]:
        extra = ""
        if "added" in tr:
            extra = "（" + "；".join(x for x in (f"+{', '.join(tr['added'])}" if tr["added"] else "",
                                                 f"-{', '.join(tr['removed'])}" if tr["removed"] else "") if x) + "）"
        lines.append(f"{indent}  {fmt_t(tr['t_ns'])}[{fmt_rel(tr['t_ns'], base_ns)}] {short(tr['from'], 50)} → {short(tr['to'], 50)}{extra}")
    if f["transition_count"] > 6:
        lines.append(f"{indent}  …其餘 {f['transition_count'] - 6} 次見 --json")
    return lines


def jsonable(obj):
    """量測結果 → 可以 json.dumps：奈秒時間另外附秒。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "t_ns":
                out["t_sec"] = sec(v)
            out[k] = jsonable(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [jsonable(x) for x in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return str(obj)
    return obj


def data_path(data):
    """狀態標記與 harness 記錄用的數據路徑：實驗／快照記資料夾，bag 與切片記 bag 資料夾。"""
    return data["exp_dir"] if data["kind"] in ("experiment", "incident") else data["bag_dir"]


def marker_line(data):
    """輸出末行的狀態標記（容器端一律印；主機端 finalize_output 跟目前的分析數據相同時拿掉）。"""
    return f"\n{ANALYSIS_DATA_MARKER} {data_path(data)}"


# =====================================================================================================================
# 兩端共用：參數解析
# =====================================================================================================================
class CliParser:
    """argparse 的包裝：參數錯誤時印 [ERROR]＋用法（中文、跟其他技能的回報一致），而不是 argparse 的英文訊息與 exit 2。"""

    def __init__(self, usage, description=""):
        import argparse

        class _P(argparse.ArgumentParser):
            def error(self, message):
                print(f"[ERROR] 參數錯誤：{message}\n用法：{usage}")
                raise SystemExit(2)

        self.p = _P(prog="", usage=usage, description=description, add_help=False)
        self.usage = usage

    def add(self, *a, **k):
        self.p.add_argument(*a, **k)
        return self

    def parse(self, argv, lenient=False):
        """lenient（主機端用）：不認識的參數不擋，記在 self.ignored、由 ignored_note() 附在輸出後面——實測小模型常自己加
        不存在的選項（--measure max），這些都是唯讀工具，照認得的參數做完比回錯誤、再讓模型重送一次省一輪。"""
        if not lenient:
            return self.p.parse_args(argv)
        args, extra = self.p.parse_known_args(argv)
        self.ignored = extra
        return args

    def ignored_note(self):
        extra = getattr(self, "ignored", None)
        return f"\n（已忽略不認識的參數：{' '.join(extra)}；用法：{self.usage}）" if extra else ""


def finalize_output(text):
    """主機端：容器輸出末行的 [ANALYSIS_DATA] 跟 harness 傳入的目前分析數據相同就拿掉（不同才讓 harness 同步）。"""
    current = (os.environ.get("ANALYSIS_DATA") or "").strip()
    lines = text.rstrip().splitlines()
    out = []
    for ln in lines:
        if ln.startswith(ANALYSIS_DATA_MARKER):
            path = ln[len(ANALYSIS_DATA_MARKER):].strip()
            if not path or path == current:
                continue
        out.append(ln)
    return "\n".join(out)
