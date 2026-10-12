"""code_run：在專案目錄（coding job 時是工作區）執行一個 shell 指令——跑程式、跑測試、看版本、git 查詢。

跟 host_runcmd 的差別：
- 執行前有安全檢查（_code_common.check_command）：sudo、刪檔、搬檔、改權限、網路、安裝套件、會改版本紀錄的 git、
  寫到工作區以外的轉向一律擋下並說明該怎麼做（coding worker 在使用者核准的計畫裡自動執行，沒有人逐一確認）。
- 逾時會終止整個程序群組（不會留下孤兒程序）；stdin 接 /dev/null（等輸入的程式不會卡住）。
- 輸出太長保留頭尾，但編譯錯誤（gcc 的 檔案:行號: error）與連結錯誤會另外整理在最前面（不會被截掉）；
  測試指令（pytest、unittest、ctest、gtest）的通過與失敗數由腳本算好放在標頭。
- 執行環境（_code_common.toolchain_env）：指令裡的 python3／pytest／cmake／ninja 用專案的虛擬環境或 harness 的 venv，
  gtest 等 C／C++ 函式庫的 include／lib 路徑已經設好（g++ … -lgtest 直接可以用）。
"""
import os
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc
from _shell_common import rejoin_args

DEFAULT_TIMEOUT, MAX_TIMEOUT = 120, 570     # 低於 harness 的 600 秒總逾時
MAX_OUTPUT_CHARS = 8000
USAGE = ("用法: scripts/code_run_cmd.py [--timeout 秒] \"<指令>\"\n"
         f"  在專案目錄執行；--timeout 預設 {DEFAULT_TIMEOUT} 秒、上限 {MAX_TIMEOUT}。刪檔請用 code_write --delete、改檔請用 code_edit。")


def parse_args(argv):
    args = list(argv)
    timeout = DEFAULT_TIMEOUT
    if args and args[0] == "--timeout":
        if len(args) < 2 or not args[1].isdigit():
            return None, None, f"[ERROR] --timeout 後面需要秒數。\n{USAGE}"
        timeout = max(1, min(MAX_TIMEOUT, int(args[1])))
        args = args[2:]
    if not args:
        return None, None, f"[ERROR] 沒有要執行的指令。\n{USAGE}"
    return timeout, rejoin_args(args), None   # 模型沒有把整個指令包在一組引號裡：拆開的參數接回一行（需要的重新加引號）


def run_shell(command, cwd, timeout, env=None):
    """回傳 (exit code 或 None（逾時）, 輸出, 秒數)。command 是字串時用 bash 執行，是 list 時直接執行（不經過 shell）。
    env 預設是 toolchain_env（專案的 Python、venv 裡的 pytest／cmake、C／C++ 函式庫路徑）。逾時終止整個程序群組。"""
    env = dict(env if env is not None else cc.toolchain_env(cwd), PYTHONUNBUFFERED="1")
    argv = ["/bin/bash", "-c", command] if isinstance(command, str) else list(command)
    t0 = time.time()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
    except OSError as e:          # list 形式的指令不存在（例如沒有安裝 cmake）
        return 127, f"{argv[0]}: {e.strerror or e}", time.time() - t0
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", time.time() - t0
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            time.sleep(1)
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        out, _ = proc.communicate()
        return None, out or "", time.time() - t0


def main(argv):
    timeout, command, err = parse_args(argv)
    if err:
        return err
    root = cc.base_root()
    blocked = cc.check_command(command, root)
    if blocked:
        return blocked
    code, out, secs = run_shell(command, root, timeout)
    counts = cc.summarize_test_counts(out)
    tests = f"；測試：{cc.format_counts(counts)}" if counts else ""
    compile_note = ""
    if code not in (0, None) and re.search(r": (?:fatal )?error: |undefined reference to|multiple definition of", out):
        import _cpp_common as cp
        compile_note = cp.format_diagnostics(cp.diagnostics(out, roots=[root]))
    out = cc.clip_middle(out.rstrip(), MAX_OUTPUT_CHARS - min(len(compile_note), 3000))
    if compile_note:
        out = f"{cc.clip_middle(compile_note, 3000, '錯誤摘要')}\n── 完整輸出 ──\n{out}"
    where = cc.rel_to_root(root) if root != os.path.realpath(os.getcwd()) else root
    if code is None:
        return (f"[ERROR] 指令逾時（超過 {timeout} 秒，已終止）：{command}\n{out}\n"
                f"（真的需要更久就加大 --timeout，上限 {MAX_TIMEOUT}；程式在等輸入或無窮迴圈時要修程式）")
    zero = cc.zero_tests(out) if code in (0, 5) else None   # pytest 沒收集到測試時 exit 5
    if zero:
        # 測試指令跑完了，但一個測試都沒有跑到（測試標籤／路徑寫錯、-k 篩不到）：不能當成驗證通過
        # （SWE-bench 評測：django 的 runtests 拿到不存在的標籤會回報「Ran 0 tests … OK」、exit 0）
        return (f"[ERROR] 沒有收集到任何測試：指令完成（exit {code}，{secs:.1f} 秒），但{zero}——測試的名稱、路徑或標籤可能寫錯"
                f"（django 的 runtests 用 tests/ 底下的目錄名稱，例如 forms_tests；pytest 用檔案路徑或 -k 關鍵字）：{command}\n"
                f"{out or '（沒有輸出）'}")
    if code != 0:
        hint = ""
        if re.search(r"No module named (pytest|['\"]?pytest)", out):
            py = cc.project_python(root)
            hint = (f"\n（這個 Python 沒有安裝 pytest：{py}。不能自己安裝套件，請在報告裡請使用者執行 "
                    f"{py} -m pip install pytest）")
        elif "undefined reference to `__gcov" in out:
            hint = ("\n（有些 .o 是用 coverage 旗標（--coverage／-fprofile-arcs）編的，多半是測試用的 makefile 留下的、"
                    "不是程式寫錯：用 make -B 全部重新編譯）")
        elif "command not found" in out:
            hint = "\n（這台機器沒有這個指令；不能安裝套件，請改用其他做法或在報告裡請使用者安裝）"
        return f"[ERROR] 指令失敗（exit {code}，{secs:.1f} 秒{tests}）：{command}\n{out or '（沒有輸出）'}{hint}"
    return f"[PASS] 指令完成（exit 0，{secs:.1f} 秒{tests}，在 {where}）：{command}\n{out or '（沒有輸出）'}"


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_run 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
