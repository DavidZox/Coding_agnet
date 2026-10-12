"""coding job 技能（code_job_send／code_job_status／code_job_cancel）的共用層：logs/coding_jobs/ 的位置、讀 job 狀態、服務是否在執行。

coding orchestrator（agent_core/coding_job.py）是 Web Console／CLI 裡常駐的背景服務，跟 fih_rmf_system 的 orchestrator 一樣只透過
檔案溝通：送任務＝寫進 inbox/、查狀態＝讀 <編號>/state.json 與 events.jsonl、停止＝寫 <編號>/control.json。
所以這幾支腳本不需要跟 harness 在同一個程序裡，單獨在終端機執行也可以。
"""
import json
import os
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JOBS_DIR = os.path.join(_PROJECT_ROOT, "logs", "coding_jobs")
INBOX = os.path.join(JOBS_DIR, "inbox")
STATUS_LABELS = {
    "queued": "排隊中", "planning": "規劃中", "awaiting_approval": "等使用者核准計畫", "running": "執行中", "paused": "已暫停",
    "needs_attention": "需要使用者決定", "verifying": "整體驗證中", "done": "完成", "partial": "部分完成", "failed": "失敗",
    "cancelled": "已停止", "reverted": "已還原",
}
ACTIVE = {"queued", "planning", "awaiting_approval", "running", "paused", "needs_attention", "verifying"}
ITEM_MARKS = {"pending": "⬜", "running": "🔄", "done": "✅", "failed": "❌", "skipped": "⏭️"}


def service_alive(max_age=15):
    """orchestrator 服務最近有沒有心跳（Web Console／CLI 執行中才會有）。"""
    try:
        with open(os.path.join(JOBS_DIR, "service.json"), encoding="utf-8") as f:
            beat = json.load(f)
        return time.time() - float(beat.get("ts", 0)) <= max_age
    except (OSError, ValueError):
        return False


def job_ids():
    if not os.path.isdir(JOBS_DIR):
        return []
    return sorted(int(n) for n in os.listdir(JOBS_DIR) if n.isdigit())


def load_job(ref):
    """'3'／'#3'／'latest' → (state dict, 錯誤)。"""
    ids = job_ids()
    if not ids:
        return None, "[ERROR] 目前還沒有任何 coding job（用 code_job_send 送出任務）。"
    ref = str(ref or "latest").strip().lstrip("#").lower()
    if ref in ("", "latest", "last", "最新"):
        jid = ids[-1]
    elif ref.isdigit():
        jid = int(ref)
        if jid not in ids:
            return None, f"[ERROR] 找不到 coding job #{jid}（現有：{'、'.join(f'#{i}' for i in ids[-10:])}）。"
    else:
        return None, f"[ERROR] 看不懂 job 編號「{ref}」：請給數字或 latest。"
    try:
        with open(os.path.join(JOBS_DIR, f"{jid:03d}", "state.json"), encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, ValueError) as e:
        return None, f"[ERROR] coding job #{jid} 的狀態檔讀不到：{e}"


def read_events(jid, last=10):
    out = []
    try:
        with open(os.path.join(JOBS_DIR, f"{int(jid):03d}", "events.jsonl"), encoding="utf-8") as f:
            for ln in f:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        pass
    return out[-last:] if last else out
