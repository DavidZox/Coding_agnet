"""中階的真模型評測（新架構 D10 第 3 步；標記在 evals/mid/cases.py）：真實專案評測的 30 題（evals/repo/），每一題交給中階
（agent_core/mid.py：挑技能 → 合約 → 排圖 → 低階 → 第 2 級 → 報告），每一層分開量：
- 挑技能：選的複合技能對不對（第一版還沒有技能做得到的題目要說 none）；
- 合約：抽出的參數對不對（cases.py 寫的那幾個）；
- 最後的報告：該用的技能不是 none 的題目，用 evals/repo/checks.py 對答案；
另外記用了哪些回退、要問使用者的、熔斷。

    python3 evals/mid/run.py --model gemma4:26b               # 主要的 25 題
    python3 evals/mid/run.py --model gemma4:e4b --set all     # 加上保留組
    python3 evals/mid/run.py --only py_fleet_msg,cnt_hw_params --runs 3
    python3 evals/mid/run.py --rescore evals/results/<結果目錄>   # 不跑模型：標記或核對改了之後，用存下來的 job 重新計分

工作目錄是真實專案評測的快照（evals/repo/snapshot.py，解開成唯讀）；harness 在臨時的副本裡跑（不碰正式的 logs/）。
結果在 evals/results/<時間>_mid_<模型>[_<set>][_<tag>]/：runs.jsonl、report.md、logs/<題目>_<第幾次>/（中階的 job、報告、模型呼叫，
與它用到的低階工作：edg_jobs/<編號>/）。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(PROJECT, "evals", "repo"))
import cases       # noqa: E402
import checks      # noqa: E402
import questions   # noqa: E402
import snapshot    # noqa: E402

COPY_ITEMS = ["agent_core", "skills_system", "prompts"]


def make_copy():
    tmp = tempfile.mkdtemp(prefix="mid_run_")
    for item in COPY_ITEMS:
        shutil.copytree(os.path.join(PROJECT, item), os.path.join(tmp, item), ignore=shutil.ignore_patterns("__pycache__"))
    return tmp


def score(q, job):
    """每一層的結果：挑技能、合約、最後的報告（該用的技能是 none 的題目不算報告：final 是 None）。"""
    lab = cases.LABELS[q["id"]]
    s = cases.layers(lab, job)
    s["final"] = None
    if any(x != "none" for x in cases.wanted(lab)):
        report = (job.get("result") or {}).get("report") or ""
        s["final"] = checks.score(q, report) if job.get("status") == "done" else dict(checks.score(q, report), passed=False)
    return s


def summary(results, qset):
    rs = [r for r in results if r["set"] == qset]
    fin = [r for r in rs if r["score"]["final"] is not None]
    return {"n": len(rs), "skill": sum(r["score"]["skill"] for r in rs), "params": sum(r["score"]["params"] for r in rs),
            "final": sum(r["score"]["final"]["passed"] for r in fin), "final_n": len(fin)}


def write_report(path, results, model, note=""):
    lines = [f"# 中階的真模型評測：{model}", "",
             f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；快照 {snapshot.COMMIT[:8]}；{len(results)} 次" + (f"；{note}" if note else ""), ""]
    for qset, label in (("main", "主要"), ("holdout", "保留組")):
        s = summary(results, qset)
        if s["n"]:
            lines.append(f"- **{label}**：挑技能 {s['skill']}/{s['n']}、合約 {s['params']}/{s['n']}、最後的報告 {s['final']}/{s['final_n']}"
                         "（只算該用技能的題目）")
    lines += ["", "| 題目 | 組 | 要的技能 | 選的 | 合約 | 報告 | 狀態 | 第 2 級 | 沒對的 | 秒 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["score"]
        fin = "—" if s["final"] is None else ("✅" if s["final"]["passed"] else f"❌ {s['final']['checks_passed']}/{s['final']['checks_total']}")
        miss = s["param_misses"] + ([x["label"] for x in s["final"]["items"] if not x["ok"]] if s["final"] else [])
        miss += [f"🚫{x}" for x in (s["final"] or {}).get("forbidden", [])]
        if r.get("need_user"):
            miss.append(f"問使用者：{r['need_user'][:60]}")
        lines.append(f"| {r['id']} | {r['set']} | {'／'.join(cases.wanted(cases.LABELS[r['id']]))} | {s['got']}{'' if s['skill'] else ' ❌'} | "
                     f"{'✅' if s['params'] else '❌' if s['skill'] and s['got'] != 'none' else '—'} | {fin} | {r['status']} | "
                     f"{'、'.join(r['fallbacks']) or '—'} | {'；'.join(miss)[:200]} | {r['seconds']} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def record(q, job, model, k, seconds):
    return {"id": q["id"], "set": q["set"], "kind": q["kind"], "run": k, "model": model, "job": job["id"], "status": job["status"],
            "skill": job.get("skill"), "selection": job.get("selection"), "params": job.get("params"), "rejected": job.get("rejected"),
            "auto_filled": job.get("auto_filled"), "fallbacks": [f["fallback"] for f in job.get("fallbacks") or []],
            "replans": job.get("replans"), "need_user": (job.get("need_user") or {}).get("question"), "score": score(q, job),
            "seconds": seconds}


def rescore(out_dir):
    """不跑模型：用結果目錄存下來的中階 job 照現在的 cases.py 與 answers.json 重新計分。"""
    answers = {q["id"]: q for q in questions.load()["questions"]}
    with open(os.path.join(out_dir, "runs.jsonl"), encoding="utf-8") as f:
        old = [json.loads(ln) for ln in f if ln.strip()]
    results = []
    for r in old:
        with open(os.path.join(out_dir, "logs", f"{r['id']}_{r['run']}", "mid_jobs", r["job"], "job.json"), encoding="utf-8") as f:
            job = json.load(f)
        results.append(record(answers[r["id"]], job, r["model"], r["run"], r["seconds"]))
    with open(os.path.join(out_dir, "runs.jsonl"), "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in results)
    write_report(os.path.join(out_dir, "report.md"), results, results[0]["model"] if results else "",
                 note=f"{time.strftime('%Y-%m-%d %H:%M')} 照現在的標記重新計分")
    return results


def keep_logs(tmp, job, dest):
    """中階的 job 與它用到的低階工作（排圖的、查參數的）搬到結果目錄。"""
    logs = os.path.join(tmp, "logs")
    shutil.copytree(os.path.join(logs, "mid_jobs", job["id"]), os.path.join(dest, "mid_jobs", job["id"]))
    for eid in {job.get("edg_job")} | {f["edg_job"] for f in job.get("fetches") or []}:
        if eid and os.path.isdir(os.path.join(logs, "edg_jobs", eid)):
            shutil.copytree(os.path.join(logs, "edg_jobs", eid), os.path.join(dest, "edg_jobs", eid))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--set", default="main", choices=["main", "holdout", "all"])
    ap.add_argument("--only", default="")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--tag", default="")
    ap.add_argument("--rescore", default="", help="不跑模型：用這個結果目錄存下來的 job 照現在的標記重新計分")
    args = ap.parse_args()
    if args.rescore:
        results = rescore(args.rescore)
        for qset in ("main", "holdout"):
            s = summary(results, qset)
            if s["n"]:
                print(f"{qset}：挑技能 {s['skill']}/{s['n']}、合約 {s['params']}/{s['n']}、最後的報告 {s['final']}/{s['final_n']}")
        print(f"報表：{os.path.join(args.rescore, 'report.md')}")
        return
    answers = questions.load()
    if answers["digest"] != snapshot.DIGEST:
        sys.exit("answers.json 不是這份快照算的（python3 evals/repo/questions.py --write）")
    qs = [q for q in answers["questions"] if (args.set == "all" or q["set"] == args.set) and (not args.only or q["id"] in args.only.split(","))]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(PROJECT, "evals", "results", f"{stamp}_mid_{args.model.replace(':', '-')}"
                           + ("" if args.set == "main" else f"_{args.set}") + (f"_{args.tag}" if args.tag else ""))
    os.makedirs(out_dir, exist_ok=True)
    snap_dir, tmp = tempfile.mkdtemp(prefix="mid_snapshot_"), make_copy()
    results = []
    try:
        src_root = snapshot.extract(snap_dir)
        sys.path.insert(0, tmp)
        from agent_core import mid
        from agent_core.agent import SkillAgent
        agent = SkillAgent(model=args.model)
        print(f"中階的評測：{len(qs)} 題 × {args.runs} 次 → {out_dir}", flush=True)
        for q in qs:
            for k in range(1, args.runs + 1):
                agent.current_cwd = src_root
                t0 = time.time()
                job = mid.Worker(agent).start(q["question"])
                r = record(q, job, args.model, k, round(time.time() - t0, 1))
                results.append(r)
                keep_logs(tmp, job, os.path.join(out_dir, "logs", f"{q['id']}_{k}"))
                with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                write_report(os.path.join(out_dir, "report.md"), results, args.model)
                s = r["score"]
                fin = "" if s["final"] is None else f"｜報告 {'✅' if s['final']['passed'] else '❌'}"
                print(f"{'✅' if s['skill'] else '❌'} {q['id']} #{k}：選 {s['got']}｜合約 {'✅' if s['params'] else '—' if not s['skill'] else '❌'}{fin}"
                      f"｜{job['status']}" + (f"｜{'；'.join(s['param_misses'])[:160]}" if s["param_misses"] else ""), flush=True)
    finally:
        snapshot.remove(snap_dir)
        shutil.rmtree(tmp, ignore_errors=True)
    for qset in ("main", "holdout"):
        s = summary(results, qset)
        if s["n"]:
            print(f"{qset}：挑技能 {s['skill']}/{s['n']}、合約 {s['params']}/{s['n']}、最後的報告 {s['final']}/{s['final_n']}")
    print(f"報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
