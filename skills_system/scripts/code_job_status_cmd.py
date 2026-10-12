"""code_job_status：查 coding job 的狀態——計畫的每一項做到哪、改了哪些檔案、驗證結果、現在是不是在等使用者決定；
list 列出最近的 job。數量與狀態由腳本整理好，直接引用。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _coding_jobs_common as cj

USAGE = "用法: scripts/code_job_status_cmd.py [編號|latest|list] [--log N]（--log 附上最近 N 筆事件）"


def render_job(job, log):
    items = job.get("items") or []
    done = sum(1 for it in items if it.get("status") == "done")
    label = cj.STATUS_LABELS.get(job.get("status"), job.get("status"))
    lines = [f"[PASS] coding job #{job['id']}：{label}（{done}/{len(items)} 項完成）",
             f"任務：{job.get('task')}", f"工作區：{job.get('workspace')}",
             f"模型：規劃 {job.get('models', {}).get('planner')}、worker {job.get('models', {}).get('worker')}"]
    if job.get("needs"):
        lines.append(f"⚠️ 等使用者：{job['needs'].get('message')}")
    if job.get("error"):
        lines.append(f"錯誤：{job['error']}")
    if items:
        lines.append("計畫：")
        for it in items:
            mark = cj.ITEM_MARKS.get(it.get("status"), "")
            extra = f"（嘗試 {it.get('attempts')} 次、{it.get('steps')} 步）" if it.get("attempts") else ""
            lines.append(f"  {it['n']}. {mark} {it['title']}{extra}")
            if it.get("summary"):
                lines.append(f"     {it['summary']}")
            if it.get("changed"):
                lines.append(f"     改了：{'、'.join(it['changed'])}")
    if job.get("final_output"):
        lines.append(f"整體驗證（{job.get('final_verify') or '靜態檢查'}）：{job['final_output'].splitlines()[0]}")
    if job.get("report_id"):
        lines.append(f"報告存檔 #{job['report_id']}（要問細節用 result_recall {job['report_id']} \"<問題>\"；看改了什麼用 code_diff --job {job['id']}）")
    if log:
        evs = cj.read_events(job["id"], log)
        if evs:
            lines.append(f"最近 {len(evs)} 筆事件：")
            lines += [f"  {e.get('ts')} {e.get('text', '')[:160]}" for e in evs]
    return "\n".join(lines)


def main(argv):
    ref, log = "latest", 0
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--log" and i + 1 < len(argv) and argv[i + 1].isdigit():
            log = min(50, int(argv[i + 1]))
            i += 2
            continue
        if a.startswith("--"):
            return f"[ERROR] 不認識的選項 {a}。\n{USAGE}"
        ref = a
        i += 1
    if ref.lower() == "list":
        ids = cj.job_ids()[-15:]
        if not ids:
            return "[PASS] 目前還沒有任何 coding job。"
        rows = []
        for jid in reversed(ids):
            job, err = cj.load_job(str(jid))
            if job:
                items = job.get("items") or []
                done = sum(1 for it in items if it.get("status") == "done")
                rows.append(f"  #{jid} {cj.STATUS_LABELS.get(job.get('status'), job.get('status'))}（{done}/{len(items)}）"
                            f"{job.get('created', '')[5:16]}：{job.get('task', '')[:70]}")
        alive = "orchestrator 執行中" if cj.service_alive() else "orchestrator 目前沒有在執行（要開著 Web Console 或 CLI）"
        return f"[PASS] 最近 {len(rows)} 個 coding job（{alive}）：\n" + "\n".join(rows)
    job, err = cj.load_job(ref)
    if err:
        return err
    return render_job(job, log)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_job_status 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
