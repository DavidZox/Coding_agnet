"""coding orchestrator 的評測：同一組程式開發任務（evals/coding_scenarios.py）用指定的模型跑，比較成功率、時間、模型呼叫次數。

    python3 evals/run_coding_evals.py                                  # gemma4:e4b × 全部情境 × 1 次
    python3 evals/run_coding_evals.py --model gemma4:26b --runs 2
    python3 evals/run_coding_evals.py --model gemma4:e4b --planner gemma4:26b    # 規劃用 26b、worker 用 e4b
    python3 evals/run_coding_evals.py --only rename_cross_file,bugfix_textstats
    python3 evals/run_coding_evals.py --lang cpp                       # 只跑 C／C++ 的情境（真的 gtest）

每一次都在臨時目錄複製一份專案（agent_core、skills_system、coding_agents、evals…）＋ fixture 當工作區來跑，不碰正式的 logs/。
結果寫到 evals/results/<時間>_coding_<模型>/：runs.jsonl（每一次的完整紀錄：每一項的嘗試與步數、事件流、diff、測試輸出）
與 report.md（彙整表）。改了 coding_agents/*.md、worker／規劃的流程或門檻之後重跑，跟上一次的 report.md 比。"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)
from evals.coding_scenarios import SCENARIOS  # noqa: E402

COPY_ITEMS = ["agent_core", "skills_system", "coding_agents", "context_modes", "evals", "AGENT.md", "Memory.md"]


def _ignore(d, names):
    """不複製：__pycache__、評測結果、DevBench 下載的資料與虛擬環境（evals/devbench/data、.venv，幾百 MB）。"""
    skip = {n for n in names if n in ("__pycache__", "results", "drafts")}
    if os.path.basename(os.path.normpath(d)) == "devbench":
        skip |= {n for n in names if n in ("data", ".venv")}
    return skip


def make_copy():
    tmp = tempfile.mkdtemp(prefix="coding_eval_")
    ignore = _ignore
    for item in COPY_ITEMS:
        src = os.path.join(PROJECT, item)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(tmp, item), ignore=ignore)
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(tmp, item))
    os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
    return tmp


def run_one(scenario_id, args):
    tmp = make_copy()
    out_path = os.path.join(tmp, "result.json")
    env = dict(os.environ, EVAL_MODEL=args.model, EVAL_PLANNER_MODEL=args.planner or args.model, PYTHONPATH=tmp,
               PYTHONDONTWRITEBYTECODE="1", EVAL_JOB_TIMEOUT=str(args.timeout - 60))
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, os.path.join(tmp, "evals", "coding_eval_job.py"), scenario_id, out_path],
                              cwd=tmp, env=env, capture_output=True, text=True, timeout=args.timeout)
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                result = json.load(f)
        else:
            result = {"scenario": scenario_id, "passed": False, "error": (proc.stderr or proc.stdout)[-3000:]}
    except subprocess.TimeoutExpired:
        result = {"scenario": scenario_id, "passed": False, "error": f"逾時（{args.timeout} 秒）"}
    result["wall_seconds"] = round(time.time() - t0, 1)
    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        result["tmp_dir"] = tmp
    return result


def write_report(path, results, args):
    by = {}
    for r in results:
        by.setdefault(r["scenario"], []).append(r)
    total = sum(1 for r in results if r.get("passed"))
    lines = [f"# coding 評測：worker {args.model}、規劃 {args.planner or args.model}", "",
             f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；每個情境 {args.runs} 次；通過 {total}/{len(results)}", "",
             "| 情境 | 通過 | job 狀態 | 平均秒數 | 平均模型呼叫 | 沒通過的條件 |", "|---|---|---|---|---|---|"]
    for sc in SCENARIOS:
        rs = by.get(sc["id"])
        if not rs:
            continue
        ok = sum(1 for r in rs if r.get("passed"))
        statuses = "、".join(r.get("job_status", "?") for r in rs)
        secs = sum(r.get("seconds") or r.get("wall_seconds") or 0 for r in rs) / len(rs)
        calls = sum(r.get("model_calls") or 0 for r in rs) / len(rs)
        failed = sorted({k for r in rs for k, v in (r.get("checks") or {}).items() if not v} | ({"error"} if any(r.get("error") for r in rs) else set()))
        lines.append(f"| {sc['id']} | {ok}/{len(rs)} | {statuses} | {secs:.0f} | {calls:.0f} | {'、'.join(failed) or '—'} |")
    lines += ["", "## 每一次"]
    for r in results:
        lines.append(f"\n### {r['scenario']}：{'✅' if r.get('passed') else '❌'}（{r.get('job_status', '?')}，{r.get('seconds', r.get('wall_seconds'))} 秒）")
        if r.get("error"):
            lines.append(f"- 錯誤：{str(r['error'])[:500]}")
        lines.append(f"- 檢查：{json.dumps(r.get('checks'), ensure_ascii=False)}；測試：{r.get('tests_head', '')}")
        for it in r.get("items") or []:
            lines.append(f"  - {it['n']}. {it['status']}（{it['attempts']} 次、{it['steps']} 步）{it['title']}；檔案 {it['files']}；驗證 {it['verify'] or '—'}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:e4b")
    ap.add_argument("--planner", default=None)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--only", default="")
    ap.add_argument("--lang", choices=["py", "cpp", "all"], default="all", help="只跑 Python（py）或 C／C++（cpp）的情境")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--keep", action="store_true", help="保留每一次的臨時目錄（看 worker 的完整紀錄）")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    scenarios = [s for s in SCENARIOS if (not only or s["id"] in only)
                 and (args.lang == "all" or (s.get("lang", "py") in ("c", "cpp")) == (args.lang == "cpp"))]
    tag = args.model.replace(":", "-") + (f"_plan-{args.planner.replace(':', '-')}" if args.planner else "")
    out_dir = os.path.join(HERE, "results", time.strftime("%Y%m%d_%H%M%S") + f"_coding_{tag}")
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for sc in scenarios:
        for i in range(args.runs):
            print(f"▶ {sc['id']}（第 {i + 1}/{args.runs} 次，worker {args.model}）…", flush=True)
            r = run_one(sc["id"], args)
            results.append(r)
            print(f"  {'✅' if r.get('passed') else '❌'} {r.get('job_status', '?')}，{r.get('seconds', r.get('wall_seconds'))} 秒，"
                  f"模型呼叫 {r.get('model_calls')} 次，檢查 {r.get('checks')}" + (f"，錯誤：{str(r.get('error'))[:200]}" if r.get("error") else ""),
                  flush=True)
            with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            write_report(os.path.join(out_dir, "report.md"), results, args)
    print(f"\n報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
