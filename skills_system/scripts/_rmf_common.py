"""fih_rmf_system 調度技能的共用層：參數與位址、HTTP、WebSocket 快照（會回 pong）、拓譜圖與站點對應、快照查詢、送出後的確認。

workpackage_send／workpackage_status／workpackage_cancel／overpending_cancel／semantic_map／rmf_handshake 都經過這裡跟
web_console 溝通（對齊 amr_base/src/fih_rmf_system 的 web_console/app.py、task_routes.py、allocator_routes.py、map_routes.py、
distribute_task/task_fastapi_to_distribute.py 與 msg_codec.py）；技能不讀任何地圖檔，站點、語意、機器人位置都問 web_console：
  發送 work package      POST   /api/send_tasks              → WorkPackage 發到 incoming_work_packages（orchestrtor 逐站派給 distribute）
  取消 work package      DELETE /api/work_packages/{id}      → CancelWorkPackage；不論有沒有這個 id 都回 200
  刪除 OverPending 任務  DELETE /api/overpending_tasks/{id}  → CancelOverpendingTask；都回 200，distribute 只刪「此刻在 OverPending」的
  狀態快照               WebSocket /api/ws：每 0.5 秒一幀（distribute 佇列與機器人；"orchestrtor" 鍵是 work package，欄位見 msg_codec.py）
  語義地圖               GET /api/topology（拓譜圖 + semantics.yaml 的語意名稱／說明）、/api/stations、/api/robots（robots.yaml 名冊）
  手動觸發               manual_trigger（另外 `ros2 run fih_rmf_system manual_trigger`，port 8002）：POST /batch_handshake、/batch_task_exec_fin

要注意的事：
  * DELETE 一律回 200、POST 只代表 web_console 轉發了：送出前用快照確認對象存在，送出後用 confirm_after() 讀快照確認結果。
  * web_console 是 uvicorn：每 20 秒 ping、20 秒內沒有 pong 就斷線。WsStream 會回 pong，連線提早結束時 end_text() 說明原因。
  * 拓譜圖節點的 name 可能是空字串（fih_humanoid_amrScene_v2、BadaMap02 全部都是）：站點參照 ref＝name，沒有 name 就用 id 字串；
    機器人端（TaskAgent）收到站點時先當名稱查、查不到再當整數 id，所以兩種都派得動。
  * OverPending 不是終點：raw 等超過 threshold_ovp_sec（預設 10 秒）進 OverPending，待滿 threshold_recovery_sec（預設 10 秒）回流 raw。
位址：--url（web_console，預設環境變數 RMF_WEB_CONSOLE_URL 或 http://localhost:8020）、--trigger（manual_trigger，預設
RMF_MANUAL_TRIGGER_URL 或 http://localhost:8002）；沒寫 http:// 自動補上。純標準庫（urllib + 迷你 WebSocket 客戶端）。
"""
import base64
import difflib
import http.client
import json
import math
import os
import re
import socket
import struct
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

HTTP_TIMEOUT_SECONDS = 10
WS_TIMEOUT_SECONDS = 6           # 連線＋握手＋第一幀的上限
WS_IDLE_SECONDS = 10             # 收幀途中超過這麼久沒有新的一幀＝web_console 停止推送（正常每 0.5 秒一幀）
MAX_WATCH_SECONDS = 300          # --watch／--wait 的上限（低於 harness 的 600 秒總逾時）
CONFIRM_SECONDS = 4.0            # 送出後讀快照確認的時間（web_console 的快照約 0.5～1.5 秒反映變化）
NEAR_STATION_DISTANCE = 1.0      # 機器人與站點座標距離小於此值視為「在該站」（與拓譜圖同單位，isaacsim 場景為公尺）
MAX_WS_FRAME_BYTES = 32 * 1024 * 1024
ROBOT_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")   # ROS 2 的名稱規則：/{rid}/handshake_states 要是合法的 topic

SERVICES = {
    "web_console": {"opt": "--url", "env": "RMF_WEB_CONSOLE_URL", "default": "http://localhost:8020",
                    "how": "web_console 是 fih_rmf_system 的網頁控制台，由 rmf_launch.py 帶起（port 8020，容器 network_mode: host）"},
    "manual_trigger": {"opt": "--trigger", "env": "RMF_MANUAL_TRIGGER_URL", "default": "http://localhost:8002",
                       "how": ("manual_trigger 不在 rmf_launch.py 裡，要另外在 ROS 2 容器裡 `ros2 run fih_rmf_system manual_trigger` "
                               "啟動（port 8002）")},
}


# ---------------------------------------------------------------- 參數
def parse_cli(argv, values=None, flags=(), optional=None, elsewhere=None, usage=""):
    """嚴格的參數解析（純函式：不印、不結束程式，guard 也可以拿來判斷）。回傳 (位置參數, {選項: 值或 True}, error)。
    values：{選項: 值的說明}，要接一個值；值不能以 -- 開頭（`--desc --dry-run` 回錯，不會把 --dry-run 當成描述吞掉）。
    flags：不接值的選項。optional：{選項: 判斷函式}，下一個參數符合判斷才當成它的值（`--loop 3`、`--ros2 容器`），否則值是 ""。
    elsewhere：{選項: 技能}，別的技能的選項，回錯時指路。也接受 `--選項=值`；同一個選項給兩次回錯。"""
    values, optional, elsewhere = dict(values or {}), dict(optional or {}), dict(elsewhere or {})
    tail = f"\n{usage}" if usage else ""
    pos, opts, i = [], {}, 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--") and len(tok) > 2:
            name, eq, inline = tok.partition("=")
            if name in values or name in optional:
                if eq:
                    val, i = inline, i + 1
                elif name in values:
                    if i + 1 >= len(argv):
                        return None, None, f"[ERROR] {name} 後面要接{values[name]}。{tail}"
                    val, i = argv[i + 1], i + 2
                else:
                    nxt = argv[i + 1] if i + 1 < len(argv) else None
                    if nxt is not None and not nxt.startswith("--") and optional[name](nxt):
                        val, i = nxt, i + 2
                    else:
                        val, i = "", i + 1
                if val.startswith("--"):
                    return None, None, (f"[ERROR] {name} 後面要接{values.get(name, '值')}，收到的卻是另一個選項 {val}："
                                        f"選項的值不能以 -- 開頭（{name} 漏了值？）。{tail}")
                if name in opts:
                    return None, None, f"[ERROR] {name} 給了兩次（{opts[name]!r} 與 {val!r}），只能給一次。{tail}"
                opts[name] = val
                continue
            if name in flags and not eq:
                opts[name] = True
                i += 1
                continue
            if name in elsewhere:
                return None, None, f"[ERROR] {name} 不是這個技能的選項，那是 {elsewhere[name]} 技能的功能，請改用該技能。{tail}"
            return None, None, f"[ERROR] 不認識的選項 {tok}。{tail}"
        if re.match(r"^-[A-Za-z]", tok):
            return None, None, f"[ERROR] 不認識的選項 {tok}（這個技能的選項都是 -- 開頭）。{tail}"
        pos.append(tok)
        i += 1
    return pos, opts, None


# distribute 的快照（web_console）裡沒有電量：電量與充電狀態在每台機器人自己發的 /{rid}/robot_state（fih_rmf_msgs/RobotState 的
# current_state.battery_level、is_charging；msg_codec.robot_state_to_dict）。列機器人的地方附這一行，問電量時才知道去哪裡讀。
BATTERY_NOTE = ("（電量與充電狀態不在 web_console 的快照裡：看 /<機器人>/robot_state 的 current_state.battery_level、is_charging，"
                "例如 ROS2_topic_echo /tb1/robot_state）")

def resolve_url(raw=None, service="web_console"):
    """--url／--trigger 的值（沒給就用環境變數、再沒有用預設）→ (url, error)。沒寫 http:// 自動補上；去掉結尾的 / 與 /api。"""
    s = SERVICES[service]
    source = s["opt"]
    if raw is None:
        raw, source = os.environ.get(s["env"], ""), f"環境變數 {s['env']}"
        if not raw.strip():
            raw, source = s["default"], "預設值"
    text = str(raw).strip()
    fix = f"下一步：{s['opt']} 寫成 http://主機:port（例如 {s['default']}），或修正環境變數 {s['env']}。"
    if not text:
        return None, f"[ERROR] {source} 的 {service} 位址是空的。{fix}"
    if "://" not in text:
        text = "http://" + text
    try:
        u = urlparse(text)
        port = u.port
    except ValueError as e:
        return None, f"[ERROR] {source} 的 {service} 位址 {raw!r} 不合法（{e}）。{fix}"
    if u.scheme not in ("http", "https") or not u.hostname:
        return None, f"[ERROR] {source} 的 {service} 位址 {raw!r} 不合法（要 http://主機:port）。{fix}"
    path = u.path.rstrip("/")
    if path.endswith("/api"):
        path = path[:-4]
    netloc = u.hostname if ":" not in u.hostname else f"[{u.hostname}]"
    if port:
        netloc += f":{port}"
    return f"{u.scheme}://{netloc}{path}", None


def parse_seconds(value, name, lo=1, hi=MAX_WATCH_SECONDS):
    """秒數選項：lo～hi 的整數。回傳 (秒, error)。"""
    try:
        val = int(str(value).strip())
    except (TypeError, ValueError):
        return None, f"[ERROR] {name} 要接秒數（整數 {lo}～{hi}），收到 {value!r}。"
    if not lo <= val <= hi:
        return None, f"[ERROR] {name} 要介於 {lo}～{hi} 秒（上限低於系統總逾時 600 秒），收到 {val}。"
    return val, None


def robot_id_error(rid, what="機器人"):
    """機器人 id 要是合法的 ROS 2 名稱（英文字母或底線開頭，只有英數字與底線）：會放進 topic 名稱與容器的指令。"""
    if ROBOT_ID_RE.match(rid or ""):
        return None
    return (f"[ERROR] {what} {rid!r} 不是合法的機器人 id（要像 tb1：英文字母或底線開頭、只有英數字與底線，最多 64 字）。"
            f"下一步：用 semantic_map --robots 查名冊上的 id。")


def close_matches(word, candidates, n=3):
    return difflib.get_close_matches(str(word), list(dict.fromkeys(str(c) for c in candidates if c)), n=n, cutoff=0.6)


def fmt_s(t):
    return f"+{t:.1f}s"


def clip(text, n):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n] + "…"


_clip = clip   # 舊名稱


# ---------------------------------------------------------------- HTTP
def _unreachable(service, url, reason):
    s = SERVICES[service]
    return (f"[ERROR] 連不上 {service} {url}（{reason}）。{s['how']}。下一步：確認它有在跑，或用 {s['opt']} 位址"
            f"（環境變數 {s['env']}）指到正確的位址；連不上時不要原樣重試。")


def _http(method, base_url, path, body=None, timeout=HTTP_TIMEOUT_SECONDS, service="web_console"):
    """回傳 (status, text, error)。error 以 [ERROR] 開頭、寫原因與下一步：連線失敗、逾時、對方中途斷線、非 2xx 都接住。"""
    url = base_url.rstrip("/") + path
    try:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data is not None else {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:   # noqa: BLE001
            detail = ""
        if e.code == 503:
            return e.code, detail, (f"[ERROR] {service} 回應 HTTP 503：ROS 2 節點還沒就緒（剛啟動或 rclpy 還沒初始化）。"
                                    f"下一步：等 5 秒再試一次；還是 503 就請使用者檢查 {service}。{detail}")
        if e.code == 422:
            return e.code, detail, f"[ERROR] {service} 回應 HTTP 422（欄位驗證失敗）：{detail}。下一步：依 detail 修正參數，不要原樣重試。"
        if e.code in (404, 405):
            return e.code, detail, (f"[ERROR] {service} 回應 HTTP {e.code}：{url} 沒有這個端點（位址指到別的服務，或 {service} 版本不含它）。"
                                    f"下一步：確認 {SERVICES[service]['opt']} 指的是 {service}。{detail}")
        return e.code, detail, f"[ERROR] {service} 回應 HTTP {e.code}：{detail or e.reason}。下一步：稍後再試一次；持續發生請使用者檢查 {service} 的 log。"
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower():
            return None, "", (f"[ERROR] 等 {service} {url} 回應逾時（{timeout} 秒）：服務可能卡住或網路不通。"
                              f"下一步：確認 {service} 的狀態（主機能不能連到它）後再試一次。")
        if isinstance(reason, ConnectionRefusedError):
            return None, "", _unreachable(service, url, "連線被拒絕：這個 port 沒有服務在聽")
        if isinstance(reason, socket.gaierror):
            return None, "", _unreachable(service, url, f"找不到主機：{reason}")
        return None, "", _unreachable(service, url, reason)
    except (http.client.HTTPException, ConnectionError) as e:
        return None, "", _unreachable(service, url, f"對方中途關閉連線（{type(e).__name__}）：那個 port 不是 {service}，或服務當掉了")
    except (socket.timeout, TimeoutError):
        return None, "", f"[ERROR] 等 {service} {url} 回應逾時（{timeout} 秒）。下一步：確認 {service} 的狀態後再試一次。"
    except (OSError, ValueError) as e:
        return None, "", _unreachable(service, url, f"{type(e).__name__}: {e}")


def http_json(method, base_url, path, body=None, service="web_console", timeout=HTTP_TIMEOUT_SECONDS):
    """回傳 (status, data, error)；回應不是 JSON 也是 error。"""
    status, text, err = _http(method, base_url, path, body, timeout=timeout, service=service)
    if err:
        return status, None, err
    try:
        return status, json.loads(text or "null"), None
    except ValueError:
        return status, None, (f"[ERROR] {service} {path} 的回應不是 JSON（{clip(text, 120)}）：位址可能指到別的服務。"
                              f"下一步：確認 {SERVICES[service]['opt']} 指的是 {service}。")


# ---------------------------------------------------------------- 迷你 WebSocket 客戶端（/api/ws）
class _WsError(Exception):
    pass


class _WsEnd(Exception):
    pass


def _ws_connect(base_url, path="/api/ws", timeout=WS_TIMEOUT_SECONDS):
    """連線並完成 WebSocket 握手，回傳 (socket, 握手後已收到的資料)；失敗 raise _WsError（訊息含原因與下一步）。"""
    u = urlparse(base_url)
    where = f"{base_url}{path}"
    if u.scheme == "https":
        raise _WsError("[ERROR] 狀態快照只支援 http:// 的 web_console（WebSocket 沒有實作 TLS）。下一步：--url 改用 http:// 位址。")
    host, port = u.hostname or "localhost", u.port or 80
    full_path = (u.path.rstrip("/") + path) or "/"
    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (f"GET {full_path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                 f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode()
    deadline = time.monotonic() + timeout
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except socket.timeout:
        raise _WsError(_unreachable("web_console", where, f"{timeout} 秒內連不上")) from None
    except ConnectionRefusedError:
        raise _WsError(_unreachable("web_console", where, "連線被拒絕：這個 port 沒有服務在聽")) from None
    except OSError as e:
        raise _WsError(_unreachable("web_console", where, e)) from None
    buf = b""
    try:
        s.sendall(handshake)
        while b"\r\n\r\n" not in buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout()
            s.settimeout(remaining)
            chunk = s.recv(4096)
            if not chunk:
                raise _WsError(_unreachable("web_console", where, "WebSocket 握手時對方關閉了連線：那個 port 不是 web_console"))
            buf += chunk
            if len(buf) > 65536:
                raise _WsError(_unreachable("web_console", where, "握手的回應不是 HTTP：那個 port 不是 web_console"))
    except socket.timeout:
        s.close()
        raise _WsError(f"[ERROR] {where} 接受了連線，但 {timeout} 秒內沒有完成 WebSocket 握手：那個 port 不是 web_console，或 web_console 卡住了。"
                       f"下一步：確認 --url（環境變數 RMF_WEB_CONSOLE_URL）指的是 web_console；位址正確就請使用者檢查 web_console。") from None
    except _WsError:
        s.close()
        raise
    except OSError as e:
        s.close()
        raise _WsError(_unreachable("web_console", where, f"握手時連線中斷：{e}")) from None
    head, rest = buf.split(b"\r\n\r\n", 1)
    status_line = head.split(b"\r\n", 1)[0].decode(errors="replace")
    if " 101 " not in f"{status_line} ":
        s.close()
        raise _WsError(f"[ERROR] {where} 拒絕 WebSocket 升級（{status_line}）：位址不是 web_console，或這個版本沒有 /api/ws。"
                       f"下一步：確認 --url 指的是 web_console（瀏覽器開 {base_url}/ 看得到控制台）。")
    return s, rest


def _parse_frame(buf):
    """從 buf 解析一個完整的幀：回傳 ((fin, opcode, payload), 用掉的位元組數)，資料不夠回傳 None。"""
    if len(buf) < 2:
        return None
    b0, b1 = buf[0], buf[1]
    fin, opcode, masked, length = bool(b0 & 0x80), b0 & 0x0F, b1 & 0x80, b1 & 0x7F
    off = 2
    if length == 126:
        if len(buf) < 4:
            return None
        length, off = struct.unpack("!H", buf[2:4])[0], 4
    elif length == 127:
        if len(buf) < 10:
            return None
        length, off = struct.unpack("!Q", buf[2:10])[0], 10
    if length > MAX_WS_FRAME_BYTES:
        raise _WsEnd(f"收到超過 {MAX_WS_FRAME_BYTES // 1048576} MB 的幀，不像 web_console 的快照")
    mask = b""
    if masked:
        if len(buf) < off + 4:
            return None
        mask, off = buf[off:off + 4], off + 4
    if len(buf) < off + length:
        return None
    payload = buf[off:off + length]
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return (fin, opcode, payload), off + length


class WsStream:
    """一條 /api/ws 連線：frames() 逐幀產生 (距連線的秒數, 快照 dict)，收到 ping 回 pong（uvicorn 每 20 秒 ping，
    沒回就在 40 秒左右斷線）；結束後 end／end_text() 說明怎麼結束的：
      first（只要一幀）、duration（收滿要求的秒數）、close（web_console 關閉連線，close_code）、eof（連線中斷）、silent（太久沒有新的一幀）。
    建立失敗 raise _WsError（訊息含原因與下一步）。"""

    def __init__(self, base_url, path="/api/ws", timeout=WS_TIMEOUT_SECONDS):
        self.base_url, self.timeout = base_url, timeout
        self.sock, self.buf = _ws_connect(base_url, path, timeout)
        self.t0 = time.monotonic()
        self.pings, self.count, self.skipped, self.elapsed = 0, 0, 0, 0.0
        self.end, self.end_detail, self.close_code = None, "", None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _send(self, opcode, payload=b""):
        mask = os.urandom(4)
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack("!Q", n)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _next_message(self, deadline):
        """下一則文字訊息（bytes）；deadline 到了回傳 None；連線結束 raise _WsEnd。ping 回 pong、pong 忽略、close 回 close。"""
        message = b""
        while True:
            parsed = _parse_frame(self.buf)
            if parsed is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.sock.settimeout(min(remaining, 1.0))
                try:
                    chunk = self.sock.recv(65536)
                except socket.timeout:
                    continue
                except OSError as e:
                    self.end, self.end_detail = "eof", f"連線中斷（{type(e).__name__}）"
                    raise _WsEnd() from None
                if not chunk:
                    self.end, self.end_detail = "eof", "web_console 那端關閉了 TCP 連線（沒有送 close 幀）"
                    raise _WsEnd()
                self.buf += chunk
                continue
            (fin, opcode, payload), used = parsed
            self.buf = self.buf[used:]
            if opcode == 0x9:                       # ping → pong（同樣的內容）
                self.pings += 1
                try:
                    self._send(0xA, payload)
                except OSError:
                    pass
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else None
                reason = payload[2:].decode("utf-8", errors="replace") if len(payload) > 2 else ""
                self.close_code = code
                self.end, self.end_detail = "close", f"web_console 關閉了連線（close code {code}{'：' + reason if reason else ''}）"
                try:
                    self._send(0x8, payload[:2])
                except OSError:
                    pass
                raise _WsEnd()
            if opcode in (0x1, 0x2, 0x0):
                message += payload
                if fin:
                    if opcode == 0x2:
                        self.skipped += 1
                        message = b""
                        continue
                    return message

    def frames(self, duration=None, idle=WS_IDLE_SECONDS):
        """duration=None：只取第一幀；否則收到 duration 秒。第一幀 timeout 秒內沒來 raise _WsError；之後中斷就結束產生。"""
        first_deadline = self.t0 + self.timeout
        end_at = None if duration is None else self.t0 + duration
        last = None
        try:
            while True:
                now = time.monotonic()
                if end_at is not None and now >= end_at and self.count:
                    self.end = "duration"
                    return
                if last is None:                    # 第一幀：不管 duration 多短，都等到 timeout
                    deadline = first_deadline
                else:
                    deadline = last + idle if end_at is None else min(last + idle, end_at)
                try:
                    raw = self._next_message(deadline)
                except _WsEnd as e:
                    if str(e):
                        self.end, self.end_detail = "eof", str(e)
                    if not self.count:
                        raise _WsError(f"[ERROR] web_console 的 /api/ws 還沒送出任何快照就結束了：{self.end_detail}。"
                                       f"下一步：稍等幾秒再試一次；持續發生請使用者檢查 web_console。") from None
                    return
                now = time.monotonic()
                self.elapsed = now - self.t0
                if raw is None:
                    if not self.count:
                        raise _WsError(f"[ERROR] web_console 接受了 WebSocket，但 {self.timeout} 秒內沒有送出任何快照（/api/ws 異常或卡住）。"
                                       f"下一步：稍等幾秒再試一次；持續發生請使用者檢查 web_console。")
                    if end_at is not None and now >= end_at:
                        self.end = "duration"
                    else:
                        self.end, self.end_detail = "silent", f"web_console 超過 {idle} 秒沒有推送新的快照"
                    return
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self.skipped += 1
                    continue
                if not isinstance(data, dict):
                    self.skipped += 1
                    continue
                self.count += 1
                last = now
                yield now - self.t0, data
                if duration is None:
                    self.end = "first"
                    return
        finally:
            self.elapsed = time.monotonic() - self.t0

    def end_text(self):
        """提早結束時的說明（正常結束回空字串）。"""
        if self.end in (None, "first", "duration"):
            return ""
        return self.end_detail or self.end

    def close(self):
        if self.sock is None:
            return
        try:
            if self.end not in ("close", "eof"):
                self._send(0x8, struct.pack("!H", 1000))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = None


def ws_read_json(base_url):
    """讀一幀快照，回傳 (data, error)。"""
    try:
        with WsStream(base_url) as ws:
            for _, data in ws.frames():
                return data, None
    except _WsError as e:
        return None, str(e)
    return None, "[ERROR] web_console 沒有送出任何快照。下一步：稍等幾秒再試一次；持續發生請使用者檢查 web_console。"


def confirm_after(base_url, check, seconds=CONFIRM_SECONDS):
    """送出請求之後讀快照確認：check(data) 回傳不是 None 的結論就停，否則讀滿 seconds 秒。
    回傳 (結論或 None, 最後一幀或 None, 經過秒數, error)。"""
    verdict, last, t = None, None, 0.0
    try:
        with WsStream(base_url) as ws:
            for t, data in ws.frames(duration=seconds):
                last = data
                verdict = check(data)
                if verdict is not None:
                    break
    except _WsError as e:
        return None, None, 0.0, str(e)
    return verdict, last, t, None


# ---------------------------------------------------------------- 拓譜圖（/api/topology）與站點對應
def fetch_topology(base_url):
    """回傳 (topo, error)。topo：nodes（每個節點加上 ref＝站點參照、sid＝id 字串、sem＝語意名稱）、edges、
    by_ref、by_name（有名稱的）、by_id、labels（語意名稱 → [ref]）。name 是空字串的節點照樣保留（ref 用 id）。"""
    status, data, err = http_json("GET", base_url, "/api/topology")
    if err:
        return None, err
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        return None, (f"[ERROR] /api/topology 的回應沒有 nodes 清單（{clip(json.dumps(data, ensure_ascii=False), 120)}）："
                      f"位址可能不是 web_console。下一步：確認 --url 指的是 web_console。")
    nodes, by_ref, by_name, by_id, labels = [], {}, {}, {}, {}
    for raw in data.get("nodes") or []:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name").strip() if isinstance(raw.get("name"), str) else ""
        sid = "" if raw.get("id") is None else str(raw.get("id"))
        ref = name or sid
        if not ref:
            continue
        label = raw.get("label").strip() if isinstance(raw.get("label"), str) else ""
        node = dict(raw, ref=ref, sid=sid, name=name, sem=label if label and label != name else "")
        nodes.append(node)
        by_ref.setdefault(ref, node)
        if name:
            by_name.setdefault(name, node)
        if sid:
            by_id.setdefault(sid, node)
        if node["sem"]:
            labels.setdefault(node["sem"], []).append(ref)
    edges = [e for e in (data.get("edges") or []) if isinstance(e, dict)]
    return {"nodes": nodes, "edges": edges, "by_ref": by_ref, "by_name": by_name, "by_id": by_id, "labels": labels}, None


def node_by_ref(ref, topo, prefer_id=False):
    """站點參照（名稱或 id 字串）→ 節點。work package 的站點先當名稱查（跟機器人端一樣）；機器人的 target_id／current_edge 是 id，
    用 prefer_id=True。"""
    if not topo or ref is None:
        return None
    ref = str(ref).strip()
    if prefer_id:
        return topo["by_id"].get(ref) or topo["by_name"].get(ref)
    return topo["by_name"].get(ref) or topo["by_id"].get(ref)


def node_text(node):
    """a3（組裝線區-1）；沒有名稱的節點寫成 id 5（組裝線區-2）。"""
    head = node["name"] or f"id {node['sid']}"
    return f"{head}（{node['sem']}）" if node["sem"] else head


def node_detail(node):
    """發送前給人核對的寫法：a3（id 3｜組裝線區-1）；沒有名稱：id 5（組裝線區-2）。"""
    if node["name"]:
        return f"{node['name']}（id {node['sid']}" + (f"｜{node['sem']}）" if node["sem"] else "）")
    return node_text(node)


def station_text(ref, topo, prefer_id=False):
    """站點參照附語意名稱；對不到拓譜圖就原樣。"""
    if ref is None or ref == "":
        return "?"
    node = node_by_ref(ref, topo, prefer_id)
    return node_text(node) if node else str(ref)


def edge_text(edge_ref, topo):
    """current_edge 形如 "17->10" 或 "a3->a7"：兩端換成站點文字。"""
    if not edge_ref or "->" not in str(edge_ref):
        return str(edge_ref or "")
    a, b = str(edge_ref).split("->", 1)
    return f"{station_text(a, topo, True)}→{station_text(b, topo, True) if b else '?'}"


def _station_list(topo, n=12):
    refs = [node_text(x) for x in topo["nodes"]]
    return "、".join(refs[:n]) + (f"…（共 {len(refs)} 個）" if len(refs) > n else "")


def resolve_stations(tokens, topo):
    """站點輸入（名稱、節點 id、語意名稱）→ (refs, picks, error)。picks 是 [(輸入, 節點, 方式)]，方式：name／id／label／partial。
    順序：名稱完全相同 → 節點 id 完全相同（也接受 id5、#5）→ 語意名稱完全相同 → 語意名稱的一部分（純數字不做部分比對）。"""
    if not topo:
        return None, None, "[ERROR] 沒有拓譜圖，無法對應站點。"
    if not topo["nodes"]:
        return None, None, ("[ERROR] web_console 的拓譜圖沒有任何節點（/api/topology 回 0 個），沒辦法核對站點。"
                            "下一步：請使用者確認 web_console 載入的場域（map_scenario／map_filename）。")
    refs, picks = [], []
    lower_labels = {}
    for label, rs in topo["labels"].items():
        lower_labels.setdefault(label.lower(), []).extend(rs)
    for raw in tokens:
        tok = raw.strip()
        m = re.fullmatch(r"(?:id\s*|#)?(\d+)", tok, re.I)
        digits = m.group(1) if m else None
        by_name, by_id = topo["by_name"], topo["by_id"]
        if tok in by_name:
            node = by_name[tok]
            other = by_id.get(tok) if tok.isdigit() else None
            if other is not None and other is not node:
                return None, None, (f"[ERROR] 「{tok}」同時是站點 {node_detail(node)} 的名稱、也是另一個節點 {node_detail(other)} 的 id。"
                                    f"下一步：問使用者是哪一個，名稱寫 {node['name']}、節點 id 寫 id{tok}。")
            refs.append(node["ref"])
            picks.append((tok, node, "name"))
            continue
        if digits is not None and digits in by_id:
            node = by_id[digits]
            refs.append(node["ref"])
            picks.append((tok, node, "id"))
            continue
        exact = lower_labels.get(tok.lower(), [])
        if len(exact) == 1:
            node = topo["by_ref"][exact[0]]
            refs.append(node["ref"])
            picks.append((tok, node, "label"))
            continue
        if len(exact) > 1:
            return None, None, (f"[ERROR] 語意名稱「{tok}」對應到 {len(exact)} 個站點："
                                + "、".join(node_detail(topo["by_ref"][r]) for r in exact[:8])
                                + "。下一步：改用其中一個的站點名稱或 id，或問使用者是哪一個。")
        partial = []
        if digits is None and len(tok) >= 2:
            partial = [r for label, rs in topo["labels"].items() if tok.lower() in label.lower() for r in rs]
        if len(partial) == 1:
            node = topo["by_ref"][partial[0]]
            refs.append(node["ref"])
            picks.append((tok, node, "partial"))
            continue
        if len(partial) > 1:
            return None, None, (f"[ERROR] 「{tok}」符合 {len(partial)} 個站點的語意名稱："
                                + "、".join(node_detail(topo["by_ref"][r]) for r in partial[:8])
                                + (f"…另有 {len(partial) - 8} 個" if len(partial) > 8 else "")
                                + "。下一步：改用完整的語意名稱或站點名稱，或問使用者是哪一個。")
        hint = close_matches(tok, list(topo["by_name"]) + list(topo["labels"]))
        return None, None, (f"[ERROR] 這個場域沒有站點「{tok}」（站點名稱、節點 id、語意名稱都對不上）"
                            + (f"；相近的：{'、'.join(hint)}" if hint else "")
                            + f"。下一步：用 semantic_map --stations 查正確的站點，或問使用者是哪一站。現有站點：{_station_list(topo)}")
    return refs, picks, None


def _edge_endpoints(edge, topo):
    a = topo["by_id"].get(str(edge.get("start_id")))
    b = topo["by_id"].get(str(edge.get("end_id")))
    return (a["ref"] if a else str(edge.get("start_id"))), (b["ref"] if b else str(edge.get("end_id")))


def occupancy(snapshot, topo):
    """把即時快照對到站點：回傳 ({ref: [說明]}, [(機器人, 說明)])。"""
    per_station, robot_lines = {}, []
    nodes = [n for n in topo["nodes"] if isinstance(n.get("x"), (int, float)) and isinstance(n.get("y"), (int, float))]
    for rid, info in sorted((snapshot.get("robots") or {}).items()):
        info = info or {}
        parts = []
        x, y = info.get("x"), info.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and nodes:
            nearest = min(nodes, key=lambda n: math.hypot(n["x"] - x, n["y"] - y))
            dist = math.hypot(nearest["x"] - x, nearest["y"] - y)
            parts.append(f"座標 ({x:.2f}, {y:.2f}) 最近站 {node_text(nearest)}（距 {dist:.2f}）")
            if dist <= NEAR_STATION_DISTANCE:
                per_station.setdefault(nearest["ref"], []).append(f"{rid} 在此（距 {dist:.2f}）")
        if info.get("current_edge"):
            parts.append(f"路段 {edge_text(info['current_edge'], topo)}")
        if info.get("target_id"):
            parts.append(f"目標 {station_text(info['target_id'], topo, True)}")
            target = node_by_ref(info["target_id"], topo, True)
            if target:
                per_station.setdefault(target["ref"], []).append(f"{rid} 前往中")
        robot_lines.append((rid, f"{info.get('status', '?')}｜{info.get('state', '?')}｜自報 {info.get('real_state') or '?'}：" +
                            ("；".join(parts) if parts else "沒有座標（離線或還沒回報）")))
    for p in packages(snapshot):
        if p.get("status") != "RUNNING":
            continue
        cur = p.get("current_item") or {}
        st = cur.get("station")
        if st:
            node = node_by_ref(st, topo)
            who = f"機器人 {cur['robot_id']}" if cur.get("robot_id") else "等待機器人"
            per_station.setdefault(node["ref"] if node else st, []).append(
                f"{p.get('package_id')} 第 {p.get('station_index', 0) + 1}/{p.get('station_count')} 站派工中（{who}）")
    return per_station, robot_lines


# ---------------------------------------------------------------- 快照裡找東西（欄位對齊 msg_codec.py）
QUEUES = (("overpending_tasks", "OverPending"), ("raw_tasks", "raw"), ("processing_tasks", "processing"), ("buffer_tasks", "buffer"))


def packages(data):
    return [p for p in ((data or {}).get("orchestrtor") or {}).get("packages") or [] if isinstance(p, dict)]


def find_package(data, pid):
    return next((p for p in packages(data) if p.get("package_id") == pid), None)


def orchestrtor_alive(data):
    """web_console 剛啟動、orchestrtor 沒在跑時，"orchestrtor" 是預設值（step_counter 0、沒有工作包）。"""
    orch = (data or {}).get("orchestrtor") or {}
    return bool(orch.get("step_counter")) or bool(orch.get("packages"))


def distribute_alive(data):
    return bool((data or {}).get("step_counter")) or (data or {}).get("state") not in (None, "", "INIT")


def _ids(data, key):
    return [t.get("id") for t in (data or {}).get(key) or [] if isinstance(t, dict) and t.get("id")]


def queue_of(data, task_id):
    """工作項在 distribute 的哪個佇列：回傳 (佇列名稱, 那一筆) 或 (None, None)。"""
    for key, label in QUEUES:
        for t in (data or {}).get(key) or []:
            if isinstance(t, dict) and t.get("id") == task_id:
                return label, t
    return None, None


def queue_text(label, t):
    if label == "OverPending":
        return f"OverPending（已在逾時區 {t.get('wait')}s）"
    if label == "raw":
        return f"raw（已等 {t.get('age')}s）"
    if label == "processing":
        return f"processing（正在對 {t.get('robot') or '?'} 授權）"
    return label


def _locate_task(data, task_id):
    """舊介面：回傳 (佇列名稱, 補充說明)。"""
    label, t = queue_of(data, task_id)
    if not label:
        return None, ""
    return label, "，" + queue_text(label, t)


def item_package(data, item_id):
    """目前工作項是 item_id 的 work package。"""
    return next((p for p in packages(data) if (p.get("current_item") or {}).get("item_id") == item_id), None)


def item_ids(data):
    """distribute 各佇列裡全部的工作項 id。"""
    return [i for key, _ in QUEUES for i in _ids(data, key)]


def fetch_roster(base_url, data=None):
    """機器人名冊：/api/robots（robots.yaml）＋快照裡的機器人。回傳 (sorted 名單, error)；兩邊都拿不到才是 error。"""
    status, body, err = http_json("GET", base_url, "/api/robots")
    names = set()
    if not err and isinstance(body, dict):
        names |= {str(r) for r in body.get("robots") or [] if r}
    names |= set(((data or {}).get("robots") or {}).keys())
    if names:
        return sorted(names), None
    return [], err or "[ERROR] web_console 的機器人名冊是空的（robots.yaml 沒有載入，快照裡也沒有機器人）。"
