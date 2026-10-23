"""執行外部指令的技能共用：rejoin_args（host_runcmd、docker_runcmd）與 run_shell（host_runcmd、search_text、find_file、stt_engine）。

rejoin_args：harness 用 shlex 把 action.args 拆成參數（_parse_script_args）。模型常常寫 `python3 -c "a; print(b)"`（外層沒有再包一層
引號），拆開後 `a; print(b)` 是一個參數；以前直接用空白接回去，引號就不見了，bash 把 `;` 當成指令分隔、括號變成語法錯誤
（實測 coding worker 同一個指令跑三次都失敗，模型怎麼改都不會過）。這裡把有空白或 shell 特殊字元的參數重新加引號；
運算子（&& | ;）、重導向（2>&1）、萬用字元（tests/*.py）保持原樣，所以 `make && ./run 2>&1`、`ls tests/*.py` 照常運作。

run_shell：可以自己用（不需要人在旁邊）的執行方式，規範見 doc/技能撰寫規範.md 第 4 節——
- 不讀標準輸入（stdin=DEVNULL；會問密碼、確認、開編輯器的指令會直接失敗而不是卡住），環境變數關掉分頁器與 git 的提示；
- 新的程序群組（start_new_session）：逾時結束整個群組（SIGTERM，1 秒後 SIGKILL），不留背景程序；主程序結束後還留在群組裡的
  背景程序（指令結尾的 &）也一併結束並註明；
- 逾時保留已經收到的輸出；stdout／stderr 都收（或合併成一條，順序跟終端機一樣）；大小有上限（頭＋尾），解碼用 errors="replace"；
- 也可以逐行交給呼叫端處理（search_text 依檔案分組計數，輸出再多記憶體也不會爆）。
只用標準庫。
"""
import os
import re
import selectors
import shlex
import signal
import subprocess
import time

_SHELL_OPS = {"&&", "||", ";", "|", "&", "|&", ">", ">>", "<", "<<", "2>", "2>>", "&>", "(", ")"}
_REDIRECT_RE = re.compile(r"^\d*[<>]{1,2}&?\d*$|^\d*>&\d+$")
_NEEDS_QUOTE_RE = re.compile(r"[\s;&|()<>$`\"'\\]")

# 不互動的環境：分頁器直接輸出、git 不問帳密也不開編輯器、apt 不問問題
NONINTERACTIVE_ENV = {"PAGER": "cat", "GIT_PAGER": "cat", "SYSTEMD_PAGER": "", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true",
                      "DEBIAN_FRONTEND": "noninteractive", "PIP_NO_INPUT": "1"}
MAX_LINE_BYTES = 1 << 20      # 逐行處理時單行最多保留 1MB（一行 50MB 的 minified JSON 不會吃光記憶體）


# harness 認得的狀態標記（agent_core/dispatch.py 的 STATE_MARKERS）：只認輸出最後連續的標記行
STATE_MARKERS = ("[CWD_CHANGED]", "[CONTAINER_CWD]", "[ANALYSIS_DATA]", "[TARGET_CONTAINER]", "[ROS2_WORKSPACE]")


def protect_tail(text):
    """輸出最後一行是原文（指令的輸出、模型的回覆）而剛好像狀態標記時（例如 cat 一份 change_dir 的存檔），後面補一行，
    harness 才不會把它當成標記、改掉工作目錄或目標容器。"""
    lines = text.rstrip().splitlines()
    if lines and lines[-1].strip().startswith(STATE_MARKERS):
        return text.rstrip() + "\n（輸出結束：上一行是原文，不是狀態標記）"
    return text


def rejoin_args(args):
    """參數 list → 一行指令；只有一個參數時原樣傳回（那是模型用引號包好的整串指令）。
    評測的對照組用 AGENT_ABLATE=rejoin 換回舊的接法（直接用空白接起來，引號會不見；平常不要設）。"""
    args = list(args)
    if len(args) == 1:
        return args[0]
    if "rejoin" in os.environ.get("AGENT_ABLATE", ""):
        return " ".join(args)
    out = []
    for a in args:
        if a in _SHELL_OPS or _REDIRECT_RE.match(a) or not _NEEDS_QUOTE_RE.search(a):
            out.append(a)
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*=)(.*)$", a, re.S)       # FOO="a b" → FOO='a b'
        out.append(m.group(1) + shlex.quote(m.group(2)) if m else shlex.quote(a))
    return " ".join(out)


class _Sink:
    """一條輸出管道：逐行交給 on_line，或只留開頭 head 個 bytes＋最後 tail 個 bytes（中間丟掉，記下總量）。"""

    def __init__(self, head, tail=0, on_line=None):
        self.head_limit, self.tail_limit, self.on_line = head, tail, on_line
        self.head, self.tail, self.partial = bytearray(), bytearray(), bytearray()
        self.total = self.newlines = 0
        self.last = b""
        self.dropped = False
        self._skip_rest_of_line = False

    def feed(self, data):
        self.total += len(data)
        self.newlines += data.count(b"\n")
        self.last = data[-1:]
        if self.on_line:
            self._feed_lines(data)
            return
        if len(self.head) < self.head_limit:
            take = self.head_limit - len(self.head)
            self.head += data[:take]
            data = data[take:]
        if data:
            if self.tail_limit:
                self.tail += data
                if len(self.tail) > self.tail_limit:
                    del self.tail[:len(self.tail) - self.tail_limit]
                    self.dropped = True
            else:
                self.dropped = True

    def _feed_lines(self, data):
        while data:
            nl = data.find(b"\n")
            chunk, data = (data, b"") if nl < 0 else (data[:nl], data[nl + 1:])
            if not self._skip_rest_of_line:
                room = MAX_LINE_BYTES - len(self.partial)
                self.partial += chunk[:max(0, room)]
                if len(chunk) > room:
                    self._skip_rest_of_line = True
            if nl >= 0:
                self.on_line(bytes(self.partial))
                self.partial.clear()
                self._skip_rest_of_line = False

    def close(self):
        if self.on_line and (self.partial or self._skip_rest_of_line):
            self.on_line(bytes(self.partial))
            self.partial.clear()

    def lines(self):
        """總行數（最後一行沒有換行也算一行）。"""
        return self.newlines + (1 if self.total and self.last != b"\n" else 0)

    def text(self):
        """(開頭的文字, 結尾的文字, 中間丟掉的行數)；沒有丟東西時結尾是空字串。"""
        head = bytes(self.head).decode("utf-8", errors="replace")
        if not self.dropped and not self.tail:
            return head, "", 0
        tail = bytes(self.tail)
        if self.tail_limit and self.dropped and b"\n" in tail:
            tail = tail[tail.index(b"\n") + 1:]      # 從完整的一行開始
        if b"\n" in self.head:                     # 開頭停在完整的一行
            head = bytes(self.head[:self.head.rindex(b"\n") + 1]).decode("utf-8", errors="replace")
        kept = head.count("\n") + tail.count(b"\n")
        omitted = max(0, self.newlines - kept)
        return head, tail.decode("utf-8", errors="replace"), omitted


class ShellResult:
    """run_shell 的結果。rc：exit code（逾時被結束時是 None）；out／err：文字（逾時時是已經收到的部分；超過上限時是開頭、
    out_tail 是結尾、out_omitted 是中間省略的行數）；timed_out；killed_background：主程序結束後還有背景程序、已結束它們；
    spawn_error：指令根本沒辦法啟動（找不到執行檔、沒有權限）。"""

    def __init__(self):
        self.rc = None
        self.out = self.err = self.out_tail = ""
        self.out_omitted = self.out_bytes = self.err_bytes = self.out_lines = 0
        self.timed_out = self.killed_background = False
        self.spawn_error = None
        self.elapsed = 0.0


def _group_alive(pgid):
    """程序群組裡還有活著的程序（殭屍不算：沒有人收的殭屍在容器裡會一直留著，killpg(0) 會誤判）。"""
    if not os.path.isdir("/proc"):
        try:
            os.killpg(pgid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as f:
                data = f.read()
        except OSError:
            continue
        fields = data[data.rfind(b")") + 2:].split()      # state ppid pgrp …（程式名稱可能含空白，從最後一個括號之後算）
        if len(fields) > 2 and fields[2] == str(pgid).encode() and fields[0] not in (b"Z", b"X"):
            return True
    return False


def kill_group(proc, grace=1.0):
    """結束 proc 的整個程序群組：SIGTERM，等 grace 秒，還在就 SIGKILL。"""
    pgid = proc.pid
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 1.0)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            break
        end = time.monotonic() + wait
        while time.monotonic() < end:
            proc.poll()
            if not _group_alive(pgid):
                return
            time.sleep(0.05)


def run_shell(cmd, timeout, cwd=None, env=None, merge_stderr=False, head_bytes=256 * 1024, tail_bytes=0,
              on_stdout_line=None, on_stderr_line=None, kill_background=True, grace=1.0):
    """執行 cmd（字串＝交給 bash -c；list＝直接執行），最多 timeout 秒。回傳 ShellResult（不丟例外）。
    merge_stderr：stderr 併進 stdout（順序跟終端機一樣）。on_stdout_line／on_stderr_line：逐行（bytes，不含換行）交給呼叫端，
    那一條就不另外保存。head_bytes／tail_bytes：保存的上限（開頭＋結尾）。"""
    argv = ["/bin/bash", "-c", cmd] if isinstance(cmd, str) else [str(a) for a in cmd]
    full_env = dict(os.environ if env is None else env)
    full_env.pop("HARNESS_RAW_ARGS", None)       # 這次技能呼叫的原始參數不要漏給子程序（裡面再跑 file_ops 會讀錯）
    full_env.update({k: v for k, v in NONINTERACTIVE_ENV.items() if k not in (env or {})})
    r = ShellResult()
    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=full_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE, start_new_session=True)
    except OSError as e:
        r.spawn_error = e
        return r
    out_sink = _Sink(head_bytes, tail_bytes, on_stdout_line)
    err_sink = None if merge_stderr else _Sink(64 * 1024, 16 * 1024, on_stderr_line)
    sinks = {proc.stdout.fileno(): out_sink}
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    if err_sink is not None:
        sinks[proc.stderr.fileno()] = err_sink
        sel.register(proc.stderr, selectors.EVENT_READ)

    def pump(wait):
        for key, _ in sel.select(timeout=wait):
            try:
                data = os.read(key.fd, 65536)
            except OSError:
                data = b""
            if not data:
                sel.unregister(key.fileobj)
            else:
                sinks[key.fd].feed(data)

    deadline = t0 + timeout
    exited_at = None
    held_by_background = False
    while sel.get_map():
        now = time.monotonic()
        if now >= deadline:
            r.timed_out = True
            break
        if exited_at is None and proc.poll() is not None:
            exited_at = now
        if exited_at is not None and now - exited_at > grace:
            held_by_background = True        # 主程序結束了，管道還被背景程序拿著（例如結尾的 &）
            break
        pump(min(0.25, deadline - now))
    if not r.timed_out and not held_by_background:
        try:
            proc.wait(timeout=max(0.05, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            r.timed_out = True
    if r.timed_out:
        kill_group(proc)
    elif kill_background and (held_by_background or _group_alive(proc.pid)):
        r.killed_background = True
        kill_group(proc, grace=0.5)
    # 收掉被結束的程序最後留在管道裡的輸出（最多 1 秒）
    end = time.monotonic() + 1.0
    while sel.get_map() and time.monotonic() < end:
        pump(0.1)
    for f in list(sel.get_map().values()):
        sel.unregister(f.fileobj)
    sel.close()
    for f in (proc.stdout, proc.stderr):
        if f:
            f.close()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    out_sink.close()
    if err_sink is not None:
        err_sink.close()
    r.rc = None if r.timed_out else proc.returncode
    r.out, r.out_tail, r.out_omitted = out_sink.text()
    r.out_bytes, r.out_lines = out_sink.total, out_sink.lines()
    if err_sink is not None:
        head, tail, omitted = err_sink.text()
        r.err = head + (f"…（中間省略 {omitted} 行）…\n" if omitted else "") + tail
        r.err_bytes = err_sink.total
    r.elapsed = time.monotonic() - t0
    return r
