#!/usr/bin/env python3
"""host_runcmd：在本機目前的工作目錄用 bash 執行一行指令，回傳 exit code 與輸出（stdout＋stderr 合在一起，順序跟終端機一樣）。

以前的問題（2026-10 稽核）：指令後面接 `&& pwd` 取工作目錄——`echo hi # note` 的輸出不見、回報 [HOST_CWD] hi；`printf abc` 的輸出被當成路徑；
結尾的 & 變成語法錯誤；而且 harness 根本不認 [HOST_CWD]。失敗時只回 stderr 或 stdout 其中一個；grep 沒找到（exit 1）被當成錯誤、
原因空白；逾時沒有部分輸出、背景程序留著（sleep 孤兒）；標準輸入繼承自 harness（sudo／apt／git 的提示會卡住）；
結尾的 `--timeout 300` 被接進指令裡。

現在：指令原樣交給 bash（不加任何東西）；不讀標準輸入、不開分頁器與編輯器（要互動的指令直接失敗並說明）；逾時或指令結束時
結束整個程序群組、保留已經收到的輸出；--timeout 放在最前面或最後面都可以；exit code 1 的 grep／diff／test 照實說是「沒找到／
有差異／條件不成立」；常見的失敗（找不到指令、權限、要互動、語法錯誤）附下一步。指令裡的 cd 只在這一次有效。
"""
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_common import protect_tail, rejoin_args, run_shell  # noqa: E402

DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 570  # 低於 Harness 的 600 秒總逾時
HEAD_BYTES, TAIL_BYTES = 12 * 1024, 28 * 1024   # 輸出太長時保留開頭與結尾（錯誤通常在最後）
LINE_CHARS = 2000                                # 單行超過就截斷（minified JSON）

USAGE = (
    "用法: scripts/host_runcmd_cmd.py [--timeout 秒數] \"<指令>\" [--timeout 秒數]\n"
    f"  --timeout 預設 {DEFAULT_TIMEOUT_SECONDS} 秒，上限 {MAX_TIMEOUT_SECONDS} 秒（放最前面或最後面）；長時間建置請明確加大。\n"
    "  指令請用引號包住，多個指令用 && 串接；不能互動（不讀標準輸入），指令裡的 cd 不會改變之後的工作目錄（請用 change_dir）。"
)
_NO_MATCH = {
    "grep": "沒有找到符合的內容", "egrep": "沒有找到符合的內容", "fgrep": "沒有找到符合的內容", "zgrep": "沒有找到符合的內容",
    "rg": "沒有找到符合的內容", "pgrep": "沒有符合的程序", "diff": "兩邊有差異（輸出就是差異）", "cmp": "兩個檔案不同",
    "test": "條件不成立", "[": "條件不成立", "which": "找不到這個指令（沒有安裝或不在 PATH 裡）",
}
_INTERACTIVE = re.compile(r"a terminal is required|password is required|no tty present|Inappropriate ioctl for device|"
                          r"terminal prompts disabled|could not read (Username|Password)|Input is not from a terminal|"
                          r"\[Y/n\]|\[y/N\]|Do you want to continue|Abort\.|empty commit message", re.I)


def parse_timeout(val):
    try:
        t = int(val)
    except (ValueError, TypeError):
        return None, f"[ERROR] --timeout 要是秒數（整數），收到「{val}」。下一步：例如 --timeout 300。\n{USAGE}"
    if not 1 <= t <= MAX_TIMEOUT_SECONDS:
        return None, (f"[ERROR] --timeout 要在 1～{MAX_TIMEOUT_SECONDS} 秒之間，收到 {t}。"
                      f"下一步：更久的工作請拆成幾段，或請使用者自己在終端機執行。\n{USAGE}")
    return t, None


def parse_args(argv):
    """→ (timeout, command, error)。--timeout 可以在最前面或最後面（獨立的參數）。"""
    args = list(argv)
    timeout = DEFAULT_TIMEOUT_SECONDS
    for where in ("front", "back"):
        if not args:
            break
        if where == "front" and args[0] == "--timeout":
            if len(args) < 2:
                return None, None, f"[ERROR] --timeout 後面需要秒數。\n{USAGE}"
            val, args = args[1], args[2:]
        elif where == "front" and args[0].startswith("--timeout="):
            val, args = args[0].split("=", 1)[1], args[1:]
        elif where == "back" and len(args) >= 3 and args[-2] == "--timeout" and args[-1].isdigit():
            val, args = args[-1], args[:-2]
        elif where == "back" and len(args) >= 2 and args[-1].startswith("--timeout="):
            val, args = args[-1].split("=", 1)[1], args[:-1]
        else:
            continue
        timeout, err = parse_timeout(val)
        if err:
            return None, None, err
    if not args or not " ".join(args).strip():
        return None, None, f"[ERROR] 沒有給要執行的指令。下一步：給一行指令，例如 \"ls -la\"。\n{USAGE}"
    # 模型忘記加引號把指令拆散時重新接回（需要的重新加引號，見 _shell_common）
    return timeout, rejoin_args(args), None


def _last_command(command):
    """單一指令或管線（沒有 && || ; 換行）時，最後一段的指令名稱；看不出來回 None。"""
    if re.search(r"&&|\|\||;|\n", command):
        return None
    seg = command.split("|")[-1].strip()
    try:
        toks = shlex.split(seg)
    except ValueError:
        return None
    while toks and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
        toks = toks[1:]
    if toks and toks[0] in ("sudo", "nice", "time", "command") and len(toks) > 1:
        toks = toks[1:]
    return os.path.basename(toks[0]) if toks else None


def _clip_lines(text):
    out = []
    for ln in text.split("\n"):
        out.append(ln if len(ln) <= LINE_CHARS else f"{ln[:LINE_CHARS]}…（這一行共 {len(ln)} 字，截斷）")
    return "\n".join(out)


def _output_block(r, title):
    if not r.out_bytes:
        return ["（沒有輸出）"]
    body = _clip_lines(r.out.rstrip("\n"))
    if r.out_omitted or r.out_tail:
        body += (f"\n…（中間省略 {r.out_omitted} 行，共 {r.out_lines} 行；要看完整的輸出：把輸出導到檔案"
                 f"（指令 > out.log 2>&1），再用 view_file out.log --from <行號> 或 search_text 看）…\n") + _clip_lines(r.out_tail.rstrip("\n"))
    return [f"## {title}（{r.out_lines} 行）", body]


def _diagnose(rc, text, command):
    """常見的失敗 → (原因, 下一步)。"""
    if _INTERACTIVE.search(text):
        return ("這個指令要互動輸入（密碼、確認或編輯器），host_runcmd 不讀標準輸入、沒有終端機",
                "改用不互動的寫法（apt-get -y、git commit -m \"…\"、加 --yes／-y）；需要 sudo 密碼的指令請使用者自己在終端機執行")
    if rc == 127 or "command not found" in text:
        return ("找不到指令（沒有安裝或不在 PATH 裡）",
                "確認拼字、用 which <指令> 檢查；沒有安裝就告訴使用者需要安裝什麼，不要自己用 sudo 安裝")
    if rc == 126:
        return ("指令沒有執行權限或不是可執行檔", "改用 bash <腳本> 或 python3 <腳本> 執行，或請使用者處理權限")
    if rc == 2 and ("syntax error" in text or "unexpected EOF" in text):
        return ("bash 語法錯誤", "檢查引號、括號是否成對；整串指令用引號包住，裡面的引號改用另一種")
    if rc in (130, 137, 143) or (rc is not None and rc < 0):
        sig = {130: "SIGINT", 137: "SIGKILL", 143: "SIGTERM"}.get(rc, f"訊號 {-rc}" if rc and rc < 0 else "")
        return (f"程序被 {sig} 結束" + ("（常見原因是記憶體不足）" if rc in (137, -9) else ""),
                "確認資源是否足夠、或有沒有別的程序結束了它；需要的話縮小工作量再試")
    if "Permission denied" in text or "Operation not permitted" in text:
        return ("權限不足", "改用有權限的路徑；需要 root 的動作請使用者自己執行（技能不會用 sudo 輸入密碼）")
    if "No such file or directory" in text:
        return ("路徑或檔案不存在", f"先用 list_dir／find_file 確認路徑（目前工作目錄 {os.getcwd()}）")
    return ("", "看下面的輸出找原因、修正指令再試；看不出原因就把錯誤訊息告訴使用者")


def run_host_cmd(command, timeout=DEFAULT_TIMEOUT_SECONDS):
    one_line = command.replace("\r", "").replace("\n", " ↵ ")      # 多行的指令（heredoc）在標頭裡排成一行
    shown = one_line if len(one_line) <= 200 else one_line[:200] + "…"
    r = run_shell(command, timeout, cwd=os.getcwd(), merge_stderr=True, head_bytes=HEAD_BYTES, tail_bytes=TAIL_BYTES)
    if r.spawn_error:
        return f"[ERROR] 沒辦法啟動 bash：{r.spawn_error}。下一步：把這個錯誤告訴使用者。"
    notes = []
    if re.search(r"(^|&&|\|\||;|\n)\s*cd(\s|$)", command):
        notes.append("指令裡的 cd 只在這一次有效，之後的工作目錄沒有改變；要切換請用 change_dir")
    if r.killed_background:
        notes.append("指令結束時還有背景程序（例如結尾的 &），已一併結束：host_runcmd 不留背景程序；"
                     "要讓程式持續執行請使用者自己啟動，或寫成 setsid nohup 指令 > 檔案.log 2>&1 &")
    tail = [f"（{x}）" for x in notes]
    secs = f"{r.elapsed:.1f} 秒"
    if r.timed_out:
        head = (f"[ERROR] 指令逾時（超過 {timeout} 秒），已結束整個程序群組：`{shown}`。下一步：確實需要更久就加大 --timeout（上限 "
                f"{MAX_TIMEOUT_SECONDS}）再試一次；不會自己結束的指令（tail -f、watch、ros2 topic echo、伺服器）不能用 host_runcmd 跑，"
                f"改用有時長的技能，或在指令前加 timeout 秒數")
        return "\n".join([head] + _output_block(r, "逾時前收到的輸出") + tail)
    text = r.out + r.out_tail
    if r.rc == 0:
        head = f"[PASS] 指令執行完成（exit code 0，{secs}）：`{shown}`"
        return "\n".join([head] + _output_block(r, "輸出") + tail)
    last = _last_command(command)
    if r.rc == 1 and last in _NO_MATCH and not _INTERACTIVE.search(text):
        head = f"[PASS] 指令執行完成：{last} 的 exit code 1 代表{_NO_MATCH[last]}，不是執行錯誤（{secs}）：`{shown}`"
        return "\n".join([head] + _output_block(r, "輸出") + tail)
    reason, step = _diagnose(r.rc, text, command)
    head = f"[ERROR] 指令失敗（exit code {r.rc}，{secs}）：`{shown}`。" + (f"{reason}。" if reason else "") + f"下一步：{step}"
    if r.rc == 1 and last is None and re.search(r"\b(grep|diff|test)\b", command):
        head += "（如果失敗的是 grep／diff／test，exit code 1 只是沒找到／有差異／條件不成立）"
    return "\n".join([head] + _output_block(r, "輸出") + tail)


if __name__ == "__main__":
    try:
        timeout, command, err = parse_args(sys.argv[1:])
        if err:
            print(err)
            sys.exit(0)
        print(protect_tail(run_host_cmd(command, timeout)))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] host_runcmd 未預期的例外：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
