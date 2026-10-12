"""Web Console 的瀏覽器自動化測試：用 headless Chrome（DevTools Protocol）真的點畫面上的按鈕，檢查畫面與後端的狀態一致。

    python3 evals/web_ui_test.py            # 需要 google-chrome（或 chromium）；模型用假的（照劇本回答），不需要 Ollama

為什麼要有它：Coding 面板的「⚙️ 設定 → 套用」曾經有一個只有在瀏覽器裡才看得到的 bug（先送出規劃模型、畫面重畫後才讀 worker 的
下拉選單，讀到的是舊值，worker 永遠被設回 e4b）；後端的測試都過，只有真的點按鈕才抓得到。這支測試在臨時的專案副本裡啟動一個
Web Console（假模型），再用 headless Chrome 操作：設定模型並重新整理（設定要存檔）、thinking 開關只在支援的模型出現、
標題列的「🧠 模型」設定（主對話換模型、thinking、存檔）、Code 模式、送出任務 → 計畫 → 核准 → 完成、
左欄的通知、diff 視窗、只還原一個檔案。DevTools Protocol 走 WebSocket，這裡用標準庫自己做最小的 client（不必安裝套件）。
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)


# ================================================================ 最小的 WebSocket client（RFC 6455，夠 DevTools Protocol 用）
class WebSocket:
    def __init__(self, url, timeout=30):
        assert url.startswith("ws://")
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket 握手失敗")
            resp += chunk
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise ConnectionError(resp.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.buf = resp.split(b"\r\n\r\n", 1)[1]

    def send(self, text):
        data = text.encode()
        head = bytearray([0x81])
        n = len(data)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        head += mask
        self.sock.sendall(bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("WebSocket 中斷")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        parts = []
        while True:
            b1, b2 = self._read(2)
            fin, opcode, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 8:
                raise ConnectionError("WebSocket 被關閉")
            if opcode in (0, 1, 2):
                parts.append(payload)
                if fin:
                    return b"".join(parts).decode(errors="replace")


class Browser:
    """headless Chrome＋DevTools Protocol：navigate、evaluate（執行 JS 拿回結果）。"""

    def __init__(self, port):
        exe = next((e for e in ("google-chrome", "chromium", "chromium-browser") if shutil.which(e)), None)
        if not exe:
            raise RuntimeError("找不到 google-chrome／chromium")
        self.profile = tempfile.mkdtemp(prefix="ui_test_chrome_")
        self.proc = subprocess.Popen([exe, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={port}",
                                      f"--user-data-dir={self.profile}", "--window-size=1600,1100", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2).read())
                page = next(t for t in targets if t.get("type") == "page")
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("Chrome 的 DevTools 沒有起來")
        self.ws = WebSocket(page["webSocketDebuggerUrl"])
        self.msg_id = 0
        self.call("Runtime.enable")
        self.call("Page.enable")

    def call(self, method, **params):
        self.msg_id += 1
        mid = self.msg_id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        res = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if res.get("exceptionDetails"):
            raise RuntimeError(f"JS 例外：{res['exceptionDetails'].get('exception', {}).get('description') or res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    def goto(self, url):
        self.call("Page.navigate", url=url)
        time.sleep(1.0)
        self.wait("document.readyState === 'complete'")

    def wait(self, expr, timeout=20, what=None):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.js(expr):
                    return True
            except RuntimeError:
                pass
            time.sleep(0.25)
        raise AssertionError(f"等不到：{what or expr}")

    def screenshot(self, path):
        data = self.call("Page.captureScreenshot", format="png")["data"]
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            pass
        shutil.rmtree(self.profile, ignore_errors=True)


# ================================================================ 測試用的 Web Console（假模型）
SERVER_BOOT = r'''
import os, sys
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.join(os.getcwd(), "evals"))
import ollama
from coding_selftest import FakeModel, edit, DONE, current_file, GOOD_STORE_ADDITION, TEST_ADDITION
ollama.chat = FakeModel([edit("scripts/code_edit_cmd.py", "inventory/store.py"), edit("code_edit", "tests/test_store.py"), DONE],
                        [lambda t: "```python\n" + current_file(t).rstrip("\n") + "\n" + GOOD_STORE_ADDITION + "```",
                         lambda t: "```python\n" + current_file(t).rstrip("\n") + TEST_ADDITION + "```"])
ollama.list = lambda: {"models": [{"model": "gemma4:e4b"}, {"model": "gemma4:26b"}, {"model": "qwen2.5-coder:32b"}]}
ollama.show = lambda m: {"capabilities": ["completion", "thinking"] if str(m).startswith("gemma4") else ["completion", "tools", "insert"]}
from web_app.server import main
main()
'''


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(tmp, port):
    env = dict(os.environ, WEB_CONSOLE_PORT=str(port), AGENT_PERF_LOG="0", PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen([sys.executable, "-c", SERVER_BOOT], cwd=tmp, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2)
            return proc
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError("測試用的 Web Console 沒有起來：" + proc.stderr.read().decode(errors="replace")[-2000:])


def api(port, path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10).read())


def make_copy():
    tmp = tempfile.mkdtemp(prefix="ui_test_")
    for item in ["agent_core", "skills_system", "coding_agents", "context_modes", "web_app", "vision", "evals", "AGENT.md", "Memory.md",
                 "web_console.py"]:
        src = os.path.join(PROJECT, item)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(tmp, item), ignore=lambda d, names: {
                n for n in names if n in ("__pycache__", "results") or (os.path.basename(d) == "devbench" and n in ("data", ".venv"))})
        else:
            shutil.copy2(src, os.path.join(tmp, item))
    ws = os.path.join(tmp, "workspace")
    shutil.copytree(os.path.join(HERE, "coding_fixtures", "inventory_app"), ws, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp, ws


# ================================================================ 測試
def run_tests(b, port, ws, shots):
    base = f"http://127.0.0.1:{port}/#code"
    tmp_root = os.path.dirname(ws)     # 測試用的專案副本（Web Console 的 logs/ 在這裡）
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
            print(f"✅ {name}")
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"❌ {name}：{e}")
            try:
                b.screenshot(os.path.join(shots, f"fail_{len(results)}.png"))
            except Exception:
                pass

    def settings_apply():
        b.goto(base)
        b.wait("document.getElementById('code-panel').style.display === 'block'", what="Coding 面板打開")
        b.js("code.settingsOpen = true; code.lastKey = ''; renderCodePanel(); true")
        b.wait("!!document.getElementById('set-worker')", what="設定的下拉選單")
        b.js("document.getElementById('set-planner').value = 'gemma4:26b'; document.getElementById('set-worker').value = 'gemma4:26b'; true")
        b.js("[...document.querySelectorAll('.code-settings button')].find(x => x.textContent.includes('套用') && x.getAttribute('onclick').includes('saveModels')).click(); true")
        time.sleep(1.5)
        models = api(port, "/api/code/state")["models"]
        assert (models["planner"], models["worker"]) == ("gemma4:26b", "gemma4:26b"), f"後端的模型是 {models}"
        b.goto(base)   # 重新整理：畫面要顯示存檔後的值
        b.js("code.settingsOpen = true; code.lastKey = ''; renderCodePanel(); true")
        b.wait("document.getElementById('set-worker') && document.getElementById('set-worker').value === 'gemma4:26b'",
               what="重新整理後 worker 仍是 gemma4:26b")

    def code_think_toggle():
        # Coding 面板：worker 換成不支援 thinking 的模型 → 開關藏起來、顯示「不支援」；規劃（26b，支援）打開 thinking 套用
        b.js("code.settingsOpen = true; code.lastKey = ''; renderCodePanel(); true")
        b.wait("!!document.getElementById('set-planner-think')", what="規劃模型旁的 thinking 開關")
        b.js("(() => { const w = document.getElementById('set-worker'); w.value = 'qwen2.5-coder:32b'; w.dispatchEvent(new Event('change')); return true; })()")
        assert b.js("document.getElementById('set-worker-think-wrap').style.display") == "none", "不支援 thinking 的模型不該有開關"
        assert b.js("document.getElementById('set-worker-think-na').style.display") == "", "要顯示「不支援 thinking」"
        assert b.js("document.getElementById('set-planner-think-wrap').style.display") == "", "26b 支援 thinking，要有開關"
        b.js("document.getElementById('set-planner-think').checked = true; saveModels(); true")
        time.sleep(1.5)
        models = api(port, "/api/code/state")["models"]
        assert models["worker"] == "qwen2.5-coder:32b" and models["planner_think"] is True and models["worker_think"] is False, models
        b.js("code.settingsOpen = true; code.lastKey = ''; renderCodePanel(); true")
        b.wait("document.getElementById('set-planner-think') && document.getElementById('set-planner-think').checked", what="重畫後 thinking 仍勾著")
        b.js("(() => { const w = document.getElementById('set-worker'); w.value = 'gemma4:26b'; document.getElementById('set-planner-think').checked = false; saveModels(); return true; })()")
        time.sleep(1.0)

    def model_panel():
        # 標題列 🧠：主對話換 26b、打開 thinking；worker 選 qwen（不支援）時沒有開關；套用後後端、標題列、存檔都對
        b.goto(base)
        b.wait("document.getElementById('stat-model').textContent.includes('gemma4:e4b')", what="標題列顯示主對話的模型")
        b.js("document.getElementById('stat-model').click(); true")
        b.wait("!!document.getElementById('mp-main') && !!document.getElementById('mp-worker')", what="🧠 模型設定面板")
        assert b.js("document.getElementById('mp-main-think-wrap').style.display") == "", "e4b 支援 thinking，要有開關"
        b.js("(() => { const m = document.getElementById('mp-main'); m.value = 'gemma4:26b'; m.dispatchEvent(new Event('change')); "
             "document.getElementById('mp-main-think').checked = true; "
             "const w = document.getElementById('mp-worker'); w.value = 'qwen2.5-coder:32b'; w.dispatchEvent(new Event('change')); return true; })()")
        assert b.js("document.getElementById('mp-worker-think-wrap').style.display") == "none", "qwen 不支援 thinking，不該有開關"
        b.js("[...document.querySelectorAll('#model-panel button')].find(x => x.textContent.includes('套用')).click(); true")
        b.wait("document.getElementById('stat-model').textContent.includes('gemma4:26b · thinking')", what="標題列變成 26b · thinking")
        view = api(port, "/api/models")
        assert (view["main"], view["main_think"], view["worker"]) == ("gemma4:26b", True, "qwen2.5-coder:32b"), view
        assert view["summary_model"] == "gemma4:26b", f"摘要模型要跟著主對話換：{view['summary_model']}"
        saved = json.load(open(os.path.join(tmp_root, "logs", "model_settings.json"), encoding="utf-8"))
        assert saved == {"main": "gemma4:26b", "main_think": True}, saved
        b.goto(base)
        b.js("document.getElementById('stat-model').click(); true")
        b.wait("document.getElementById('mp-main') && document.getElementById('mp-main').value === 'gemma4:26b' && "
               "document.getElementById('mp-main-think').checked", what="重新整理後設定還在")
        b.js("toggleModelPanel(false); true")

    def python_setting():
        py = sys.executable
        b.wait("!!document.getElementById('set-python')", what="測試用的 Python 欄位")
        placeholder = b.js("document.getElementById('set-python').placeholder")
        assert placeholder.startswith("自動："), f"留空時應該顯示自動偵測到的 Python：{placeholder}"
        b.js(f"document.getElementById('set-python').value = {json.dumps(py)}; "
             "[...document.querySelectorAll('.code-settings button')].find(x => (x.getAttribute('onclick') || '').includes(\"'python'\")).click(); true")
        time.sleep(1.5)
        assert api(port, "/api/code/state")["python"] == py, "後端沒有存到測試用的 Python"
        b.goto(base)
        b.js("code.settingsOpen = true; code.lastKey = ''; renderCodePanel(); true")
        b.wait(f"document.getElementById('set-python') && document.getElementById('set-python').value === {json.dumps(py)}",
               what="重新整理後測試用的 Python 還在")
        b.js("document.getElementById('set-python').value = ''; "
             "[...document.querySelectorAll('.code-settings button')].find(x => (x.getAttribute('onclick') || '').includes(\"'python'\")).click(); true")
        time.sleep(1.0)
        assert api(port, "/api/code/state")["python"] == "", "清空後應該改回自動"

    def workspace_and_code_mode():
        b.js(f"document.getElementById('set-ws').value = {json.dumps(ws)}; saveWorkspace(); true")
        time.sleep(1.0)
        assert api(port, "/api/code/state")["workspace"] == os.path.realpath(ws)
        b.js("document.getElementById('code-btn').click(); true")
        b.wait("document.getElementById('code-btn').textContent.includes('✓')", what="Code 按鈕變成開啟")
        assert api(port, "/api/status")["code_mode"] is True

    def submit_approve_done():
        b.js("document.getElementById('msg').value = '在 Inventory 新增 restock_below(threshold, amount)，並加測試'; sendMessage(); true")
        b.wait("[...document.querySelectorAll('#chat-log .entry.code')].some(e => e.textContent.includes('計畫列好了'))", timeout=30,
               what="左欄出現「計畫列好了」")
        b.wait("[...document.querySelectorAll('#code-panel button')].some(x => x.textContent.includes('核准並開始'))", what="核准按鈕")
        b.screenshot(os.path.join(shots, "plan.png"))
        b.js("[...document.querySelectorAll('#code-panel button')].find(x => x.textContent.includes('核准並開始')).click(); true")
        b.wait("[...document.querySelectorAll('#chat-log .entry.code')].some(e => e.textContent.includes('完成'))", timeout=60,
               what="左欄出現 job 完成的通知")
        state = api(port, "/api/code/state")
        assert state["job"]["status"] == "done", state["job"]["status"]
        assert "def restock_below" in open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read()
        b.screenshot(os.path.join(shots, "done.png"))

    def diff_modal():
        b.wait("document.querySelectorAll('#code-panel .chg').length >= 2", what="變更的檔案清單")
        b.js("document.querySelector('#code-panel .chg').click(); true")
        b.wait("document.getElementById('diff-modal').classList.contains('show') && document.querySelectorAll('#diff-body .dl.a').length > 0",
               what="diff 視窗出現、有新增的行")
        b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'})); true")
        b.wait("!document.getElementById('diff-modal').classList.contains('show')", what="Esc 關掉 diff 視窗")

    def revert_one_file():
        orig = open(os.path.join(HERE, "coding_fixtures", "inventory_app", "tests", "test_store.py"), encoding="utf-8").read()
        b.js("window.confirm = () => true; true")
        b.js("[...document.querySelectorAll('#code-panel .chg')].find(e => e.textContent.includes('tests/test_store.py')).querySelector('button').click(); true")
        time.sleep(1.5)
        assert open(os.path.join(ws, "tests/test_store.py"), encoding="utf-8").read() == orig, "tests/test_store.py 沒有被還原"
        assert "def restock_below" in open(os.path.join(ws, "inventory/store.py"), encoding="utf-8").read(), "其他檔案不該被還原"

    check("⚙️ 設定：兩個模型都設 26b → 套用 → 後端與重新整理後都是 26b（存檔）", settings_apply)
    check("⚙️ 設定：thinking 開關只在支援的模型出現，套用後存檔", code_think_toggle)
    check("🧠 模型設定：主對話換模型、thinking 開關、標題列與存檔", model_panel)
    check("⚙️ 設定：測試用的 Python（留空自動偵測、套用後存檔、清空改回自動）", python_setting)
    check("工作區設定、🧑‍💻 Code 按鈕", workspace_and_code_mode)
    check("Code 模式送出任務 → 計畫 → 核准 → 完成，左欄有通知", submit_approve_done)
    check("點變更的檔案打開 diff、Esc 關閉", diff_modal)
    check("只還原一個檔案（↩）", revert_one_file)
    return results


def main():
    tmp, ws = make_copy()
    shots = os.path.join(tmp, "screenshots")
    os.makedirs(shots, exist_ok=True)
    port, cdp_port = free_port(), free_port()
    server = start_server(tmp, port)
    browser = None
    try:
        browser = Browser(cdp_port)
        results = run_tests(browser, port, ws, shots)
    finally:
        if browser:
            browser.close()
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} 通過" + (f"；截圖在 {shots}" if failed else ""))
    if not failed:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
