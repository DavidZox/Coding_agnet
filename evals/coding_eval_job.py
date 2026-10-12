"""跑一個 coding 評測情境（run_coding_evals.py 在臨時的專案副本裡呼叫它；不要直接在正式專案目錄執行）。

    python3 evals/coding_eval_job.py <情境 id> <輸出 json>
環境變數：EVAL_MODEL（worker，預設 gemma4:e4b）、EVAL_PLANNER_MODEL（規劃，預設同 EVAL_MODEL）。

流程：把 fixture 複製成工作區 → 送出 coding job（自動核准、某一項失敗就跳過，不停下來問）→ 等它結束 → 放進 hidden tests、
跑整個專案的測試 → 檢查不准改的檔案、不該再出現的名稱 → 寫出結果（含每一項的嘗試次數、步數、事件流）。"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
CODE_EXTS = {".py", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh"}


def main():
    scenario_id, out_path = sys.argv[1], sys.argv[2]
    from evals.coding_scenarios import SCENARIO_BY_ID
    sc = SCENARIO_BY_ID[scenario_id]
    ws = os.path.join(ROOT, "workspace")
    shutil.copytree(os.path.join(ROOT, "evals", "coding_fixtures", sc["fixture"]), ws,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "build"))
    originals = {}
    for rel in sc.get("unchanged") or []:
        with open(os.path.join(ws, rel), encoding="utf-8") as f:
            originals[rel] = f.read()

    from agent_core.agent import SkillAgent
    from agent_core.coding_job import CodingOrchestrator
    model = os.environ.get("EVAL_MODEL", "gemma4:e4b")
    agent = SkillAgent(model=model)
    orch = CodingOrchestrator(agent)
    orch.models["planner"] = os.environ.get("EVAL_PLANNER_MODEL") or model
    orch.models["worker"] = model
    orch.auto_approve = True
    orch.on_fail = "skip"
    t0 = time.time()
    job, err = orch.submit(sc["task"], ws, "eval")
    if err:
        raise SystemExit(err)
    while not (job["status"] in ("done", "partial", "failed", "cancelled") and job.get("finished")):
        time.sleep(0.5)
        if time.time() - t0 > float(os.environ.get("EVAL_JOB_TIMEOUT", "1500")):
            orch.cancel(job["id"])
            while not job.get("finished"):
                time.sleep(1)
            break
    seconds = round(time.time() - t0, 1)

    for rel, body in (sc.get("hidden_tests") or {}).items():
        p = os.path.join(ws, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
    tests_out = orch.run_script(job, "code_test_cmd.py", [])
    hidden_out = orch.run_script(job, "code_test_cmd.py", list(sc["hidden_tests"])) if sc.get("hidden_tests") else ""
    checks = {"all_tests": tests_out.startswith("[PASS]")}
    if sc.get("hidden_tests"):
        checks["hidden_tests"] = hidden_out.startswith("[PASS]")
    if originals:
        changed = []
        for rel, body in originals.items():
            try:
                with open(os.path.join(ws, rel), encoding="utf-8") as f:
                    now = f.read()
            except OSError:
                now = None
            if now != body:
                changed.append(rel)
        checks["unchanged"] = not changed
    if sc.get("contains"):
        missing = []
        for rel, pat in sc["contains"].items():
            try:
                with open(os.path.join(ws, rel), encoding="utf-8") as f:
                    ok = re.search(pat, f.read())
            except OSError:
                ok = None
            if not ok:
                missing.append(rel)
        checks["contains"] = not missing
    if sc.get("absent"):
        pat, hits = re.compile(sc["absent"]["pattern"]), []
        for d in sc["absent"]["dirs"]:
            for dirpath, _, files in os.walk(os.path.join(ws, d)):
                for fn in files:
                    if os.path.splitext(fn)[1] in CODE_EXTS and not fn.startswith("test_hidden"):
                        with open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace") as f:
                            if pat.search(f.read()):
                                hits.append(os.path.relpath(os.path.join(dirpath, fn), ws))
        checks["absent"] = not hits
    items = [{"n": it["n"], "title": it["title"], "status": it["status"], "attempts": it["attempts"], "steps": it["steps"],
              "files": it["files"], "verify": it["verify"], "summary": it["summary"]} for it in job.get("items") or []]
    out = {"scenario": scenario_id, "model": model, "planner": orch.models["planner"], "job_status": job["status"],
           "passed": all(checks.values()), "checks": checks, "seconds": seconds, "model_calls": job.get("model_calls"),
           "items": items, "error": job.get("error"), "final_verify": job.get("final_verify"),
           "tests_head": tests_out.split("\n", 1)[0], "tests_out": tests_out[:6000], "hidden_out": hidden_out[:4000],
           "diff": orch.diff_text(job)[:20000], "events": orch.events(job["id"]), "perf": agent.perf_calls}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
