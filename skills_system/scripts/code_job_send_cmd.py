"""code_job_send：把程式開發任務交給 coding orchestrator——它會探索專案、列出計畫，等使用者在畫面上核准後，
才派 coding worker 一項一項修改程式並驗證（語法、跨檔一致性、測試），最後產生報告；全程可以暫停、停止、還原。

主對話的 AI 遇到「要修改／新增／重構程式碼」的請求時用這個（主對話本身不直接改檔案）。腳本只把任務寫進
logs/coding_jobs/inbox/，由常駐的 orchestrator 接手（見 _coding_jobs_common）。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _coding_jobs_common as cj

USAGE = ("用法: scripts/code_job_send_cmd.py [--workspace 專案路徑] \"<任務描述>\"\n"
         "  --workspace 預設是 coding 工作區（/code_ws 設定的），沒有設定就是目前工作目錄；任務描述要寫清楚要做什麼（原話照抄）。")
_FORBIDDEN = {"/", "/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/root", "/sbin", "/sys", "/usr", "/var", "/home", "/tmp"}


def main(argv):
    args = list(argv)
    workspace = None
    if args and args[0] == "--workspace":
        if len(args) < 2:
            return f"[ERROR] --workspace 後面需要路徑。\n{USAGE}"
        workspace, args = args[1], args[2:]
    args = [a for a in args if a not in ("--task", "--prompt", "--desc")]   # 模型常自己加這類旗標：任務就是剩下的文字
    task = " ".join(args).strip()
    if not task:
        return f"[ERROR] 沒有任務描述。\n{USAGE}"
    if len(task) < 6:
        return f"[ERROR] 任務描述太短（「{task}」）：請寫清楚要改什麼、改成怎樣。"
    ws = os.path.realpath(os.path.expanduser(workspace or os.environ.get("CODING_DEFAULT_WORKSPACE") or os.getcwd()))
    if not os.path.isdir(ws):
        return f"[ERROR] 工作區不存在：{ws}。請確認專案路徑（--workspace），或先用 change_dir 切到專案目錄。"
    if ws in _FORBIDDEN or ws == os.path.realpath(os.path.expanduser("~")):
        return f"[ERROR] 不能把 {ws} 整個當成工作區，請指定專案目錄（--workspace <專案路徑>）。"
    os.makedirs(cj.INBOX, exist_ok=True)
    name = f"{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.json"
    path = os.path.join(cj.INBOX, name)
    before = set(cj.job_ids())
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"task": task, "workspace": ws, "source": "code_job_send", "ts": time.time()}, f, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    alive = cj.service_alive()
    for _ in range(16):   # 等 orchestrator 接手（服務每秒看一次收件匣），拿到 job 編號
        if not os.path.exists(path):
            break
        time.sleep(0.25)
    new = sorted(set(cj.job_ids()) - before)
    if new:
        return (f"[PASS] 已交給 coding orchestrator：job #{new[-1]}（工作區 {ws}）。orchestrator 會先探索專案、列出計畫，"
                f"等使用者在畫面上（Coding 面板）核准後才開始修改檔案；進度用 code_job_status {new[-1]} 查。")
    if not alive:
        return (f"[PASS] 任務已放進收件匣（工作區 {ws}），但 coding orchestrator 目前沒有在執行（要開著 Web Console 或 CLI）；"
                f"啟動後會自動接手。")
    return f"[PASS] 任務已放進收件匣（工作區 {ws}），orchestrator 接手後會出現在 Coding 面板；進度用 code_job_status latest 查。"


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_job_send 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
