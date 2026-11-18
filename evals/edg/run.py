"""第 1 級修正的真模型評測（新架構 D10 第 2 步；題目在 evals/edg/cases.py）：一個工具節點故意錯一個參數，低階執行器
（agent_core/edg.py）照收據判斷、交給修正的模型（prompts/edg/）修一次、程式核對後重跑；看修得好的有沒有修好、修不好的有沒有往上交。

    python3 evals/edg/run.py --model gemma4:26b               # 主要的題目
    python3 evals/edg/run.py --model gemma4:e4b --set all     # 加上保留組
    python3 evals/edg/run.py --only view_typo_path --runs 3
    python3 evals/edg/run.py --rescore evals/results/<結果目錄>   # 不跑模型：核對改了之後，用存下來的 job 重新計分

工作目錄是真實專案評測的快照（evals/repo/snapshot.py，解開成唯讀）；harness 在臨時的副本裡跑（不碰正式的 logs/）。
結果在 evals/results/<時間>_edg_<模型>[_<set>][_<tag>]/：runs.jsonl、report.md、logs/<題目>_<第幾次>/（job.json、收據、修正的模型呼叫）。
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
import snapshot    # noqa: E402

COPY_ITEMS = ["agent_core", "skills_system", "prompts"]


def make_copy():
    tmp = tempfile.mkdtemp(prefix="edg_run_")
    for item in COPY_ITEMS:
        shutil.copytree(os.path.join(PROJECT, item), os.path.join(tmp, item), ignore=shutil.ignore_patterns("__pycache__"))
    return tmp


def judge(case, job):
    """(通過與否, 說明, 最後的參數)。"""
    st = job["nodes"]["n"]
    inst = (st.get("instances") or [{}])[0]
    fix = inst.get("fix") or {}
    last = (inst.get("attempts") or [{}])[-1]
    if case["want"] == "not_fixable":
        if fix.get("fixable") is False and len(inst.get("attempts", [])) == 1 and st["state"] == "failed":
            return True, f"修不好、往上交：{fix.get('reason', '')}", last.get("args")
        return False, f"應該往上交；結果 {st['state']}（{st.get('reason', '')}）", last.get("args")
    if st["state"] != "done" or not inst.get("fixed"):
        return False, f"沒有修好：{st['state']}（{st.get('reason', '')}）", last.get("args")
    return (*cases.receipt_ok(job.get("_receipt"), case.get("receipt")), last.get("args"))


def write_report(path, results, model):
    lines = [f"# 第 1 級修正的真模型評測：{model}", "",
             f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；快照 {snapshot.COMMIT[:8]}；{len(results)} 次", ""]
    for s in ("main", "holdout"):
        rs = [r for r in results if r["set"] == s]
        if rs:
            lines.append(f"- **{s}**：{sum(r['passed'] for r in rs)}/{len(rs)}")
    lines += ["", "| 題目 | 組 | 要的 | 結果 | 說明 | 原本的參數 → 最後的參數 | 秒 |", "|---|---|---|---|---|---|---|"]
    for r in results:
        args = f"`{json.dumps(r['args'], ensure_ascii=False)}` → `{json.dumps(r['final_args'], ensure_ascii=False)}`"
        lines.append(f"| {r['id']} | {r['set']} | {r['want']} | {'✅' if r['passed'] else '❌'} | {r['note'][:200]} | {args} | {r['seconds']} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def rescore(out_dir):
    """不跑模型：用結果目錄存下來的 job.json 與收據，照現在的 cases.py 重新核對，寫回 runs.jsonl 與 report.md。"""
    results = []
    with open(os.path.join(out_dir, "runs.jsonl"), encoding="utf-8") as f:
        old = [json.loads(ln) for ln in f if ln.strip()]
    for r in old:
        d = os.path.join(out_dir, "logs", f"{r['id']}_{r['run']}")
        with open(os.path.join(d, "job.json"), encoding="utf-8") as f:
            job = json.load(f)
        inst = (job["nodes"].get("n", {}).get("instances") or [{}])[0]
        rel = (inst.get("attempts") or [{}])[-1].get("receipt_file")
        if rel:
            with open(os.path.join(d, rel), encoding="utf-8") as f:
                job["_receipt"] = json.load(f)
        passed, note, final_args = judge(cases.BY_ID[r["id"]], job)
        results.append(dict(r, passed=passed, note=note, final_args=final_args))
    with open(os.path.join(out_dir, "runs.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results))
    write_report(os.path.join(out_dir, "report.md"), results, results[0]["model"] if results else "")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--set", default="main", choices=["main", "holdout", "all"])
    ap.add_argument("--only", default="")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--tag", default="")
    ap.add_argument("--rescore", default="", help="不跑模型：用這個結果目錄存下來的 job 照現在的 cases.py 重新核對")
    args = ap.parse_args()
    if args.rescore:
        results = rescore(args.rescore)
        for s in ("main", "holdout"):
            rs = [r for r in results if r["set"] == s]
            if rs:
                print(f"{s}：{sum(r['passed'] for r in rs)}/{len(rs)}")
        print(f"報表：{os.path.join(args.rescore, 'report.md')}")
        return
    todo = [c for c in cases.CASES if (args.set == "all" or c["set"] == args.set) and (not args.only or c["id"] in args.only.split(","))]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(PROJECT, "evals", "results", f"{stamp}_edg_{args.model.replace(':', '-')}"
                           + ("" if args.set == "main" else f"_{args.set}") + (f"_{args.tag}" if args.tag else ""))
    os.makedirs(out_dir, exist_ok=True)
    snap_dir, tmp = tempfile.mkdtemp(prefix="edg_snapshot_"), make_copy()
    results = []
    try:
        src_root = snapshot.extract(snap_dir)
        sys.path.insert(0, tmp)
        from agent_core import edg
        from agent_core.agent import SkillAgent
        agent = SkillAgent(model=args.model)
        print(f"第 1 級修正的評測：{len(todo)} 題 × {args.runs} 次 → {out_dir}", flush=True)
        for c in todo:
            for k in range(1, args.runs + 1):
                agent.current_cwd = src_root
                t0 = time.time()
                job = edg.Executor(agent).start({"goal": c["goal"], "nodes": [dict(c["node"], id="n")]})
                inst = (job["nodes"].get("n", {}).get("instances") or [{}])[0]
                rel = (inst.get("attempts") or [{}])[-1].get("receipt_file")
                if rel:
                    with open(os.path.join(tmp, "logs", "edg_jobs", job["id"], rel), encoding="utf-8") as f:
                        job["_receipt"] = json.load(f)
                passed, note, final_args = judge(c, job)
                r = {"id": c["id"], "set": c["set"], "want": c["want"], "run": k, "model": args.model, "passed": passed, "note": note,
                     "args": c["node"]["args"], "final_args": final_args, "status": job["status"], "fix": inst.get("fix"),
                     "attempts": inst.get("attempts"), "job": job["id"], "seconds": round(time.time() - t0, 1)}
                results.append(r)
                shutil.copytree(os.path.join(tmp, "logs", "edg_jobs", job["id"]), os.path.join(out_dir, "logs", f"{c['id']}_{k}"))
                with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                write_report(os.path.join(out_dir, "report.md"), results, args.model)
                print(f"{'✅' if passed else '❌'} {c['id']} #{k}：{note[:160]}", flush=True)
    finally:
        snapshot.remove(snap_dir)
        shutil.rmtree(tmp, ignore_errors=True)
    for s in ("main", "holdout"):
        rs = [r for r in results if r["set"] == s]
        if rs:
            print(f"{s}：{sum(r['passed'] for r in rs)}/{len(rs)}")
    print(f"報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
