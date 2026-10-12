"""在臨時的 harness 副本裡跑一個 DevBench repo 的 coding job（run.py 呼叫；不要直接在正式專案目錄執行）。

    python3 evals/devbench/job.py <工作區> <任務檔> <輸出 json>
環境變數：EVAL_MODEL（worker）、EVAL_PLANNER_MODEL（規劃，預設同 worker）、CODE_PYTHON（跑 Python 測試的直譯器，
run.py 設成 DevBench 的 .venv）、EVAL_JOB_TIMEOUT（秒）。

跟一般使用一樣的流程（規劃 → 自動核准 → 每一項派 worker → 驗證 → 整體驗證），某一項失敗就跳過繼續（無人看管）。
計分不在這裡做：job 結束後由 run.py 把官方測試放進工作區再跑（agent 從頭到尾看不到官方測試）。"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def main():
    ws, task_file, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(task_file, encoding="utf-8") as f:
        task = f.read()
    from agent_core.agent import SkillAgent
    from agent_core.coding_job import CodingOrchestrator
    model = os.environ.get("EVAL_MODEL", "gemma4:e4b")
    agent = SkillAgent(model=model)
    orch = CodingOrchestrator(agent)
    orch.models["planner"] = os.environ.get("EVAL_PLANNER_MODEL") or model
    orch.models["worker"] = model
    orch.auto_approve = True
    orch.on_fail = "skip"
    orch.python = os.environ.get("CODE_PYTHON", "")
    t0 = time.time()
    job, err = orch.submit(task, ws, "devbench")
    if err:
        raise SystemExit(err)
    limit = float(os.environ.get("EVAL_JOB_TIMEOUT", "3600"))
    while not (job["status"] in ("done", "partial", "failed", "cancelled") and job.get("finished")):
        time.sleep(0.5)
        if time.time() - t0 > limit:
            orch.cancel(job["id"])
            while not job.get("finished"):
                time.sleep(1)
            break
    items = [{"n": it["n"], "title": it["title"], "status": it["status"], "attempts": it["attempts"], "steps": it["steps"],
              "files": it["files"], "changed": it.get("changed"), "verify": it["verify"], "summary": it["summary"]}
             for it in job.get("items") or []]
    out = {"model": model, "planner": orch.models["planner"], "job_status": job["status"], "seconds": round(time.time() - t0, 1),
           "model_calls": job.get("model_calls"), "items": items, "error": job.get("error"), "warnings": job.get("warnings"),
           "final_verify": job.get("final_verify"), "final_ok": job.get("final_ok"),
           "final_head": (job.get("final_output") or "").split("\n", 1)[0][:500],
           "events": orch.events(job["id"]), "perf": agent.perf_calls,
           "job_dir": orch.job_dir(job["id"])}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
