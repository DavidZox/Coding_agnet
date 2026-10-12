"""code_job_cancel：停止一個 coding job——目前這一步做完就停，還沒做的項目不做；已經改好的檔案保留（可以在 Coding 面板還原）。
寫 logs/coding_jobs/<編號>/control.json，orchestrator 每一步之前都會看（見 _coding_jobs_common）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _coding_jobs_common as cj

USAGE = "用法: scripts/code_job_cancel_cmd.py <編號|latest>"


def main(argv):
    if len(argv) != 1:
        return f"[ERROR] 要給一個 job 編號（或 latest）。\n{USAGE}"
    job, err = cj.load_job(argv[0])
    if err:
        return err
    if job.get("status") not in cj.ACTIVE:
        return f"[ERROR] coding job #{job['id']} 已經結束（{cj.STATUS_LABELS.get(job.get('status'), job.get('status'))}），不用停止。"
    path = os.path.join(cj.JOBS_DIR, f"{job['id']:03d}", "control.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"cancel": True, "ts": time.time(), "by": "code_job_cancel"}, f)
    return (f"[PASS] 已要求停止 coding job #{job['id']}（{job.get('task', '')[:60]}）：目前這一步做完就停，還沒做的項目不會做；"
            f"已經改好的檔案會保留，要復原請在 Coding 面板按「還原」或 /code revert {job['id']}。")


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_job_cancel 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
