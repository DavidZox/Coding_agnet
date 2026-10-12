"""非編碼情境（ops suite）的評測：目錄與文件、Docker、ROS 2、調度交握、複合任務。情境、沙盒與計分在
benchmark_study_3/datasets/ops_suite/（scenarios.py、sandbox/、checks.py）。

    python3 evals/ops_suite/run.py --model gemma4:26b
    python3 evals/ops_suite/run.py --model gemma4:e4b --domain handshake,complex
    python3 evals/ops_suite/run.py --only hs_lost_fin_fix --tag try1

每個情境：沙盒重建（容器、rmf_sim 的機器人行為與預設工作包、新的檔案沙盒）→ 記下開始時的狀態 → 在臨時的 harness 副本裡
跑主對話（worker.py：工具都真的在沙盒裡執行；DOCKER_HOST 指到沙盒 daemon，碰不到主機上真的容器）→ 讀回最後的狀態 →
checks.py 計分（狀態＋回覆＋禁止動作）。結果在 evals/results/<時間>_ops_<模型>[_<tag>]/：runs.jsonl、report.md。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT)
from evals.devbench import run as devrun  # noqa: E402

DATASET = os.environ.get("OPS_DATASET") or os.path.expanduser("~/Coding_agent_harness/benchmark_study_3/datasets/ops_suite")
sys.path.insert(0, DATASET)
sys.path.insert(0, os.path.join(DATASET, "sandbox"))
import checks      # noqa: E402
import fs_world    # noqa: E402
import sandbox     # noqa: E402
import scenarios   # noqa: E402
import scenarios_holdout   # noqa: E402


def run_one(sc, args, urls):
    tmp = devrun.make_copy()
    fs_root = os.path.join(tempfile.mkdtemp(prefix="ops_fs_"), "ops_home")
    try:
        sandbox.reset(sc["world"])
        fs_world.build(fs_root, sc.get("fs_extra"), urls)
        dk0 = sandbox.containers_state()
        sim0 = sandbox.sim_state() if sc["world"].get("sim") is not None else None
        fs0 = sandbox.fs_snapshot(fs_root)
        sc_path = os.path.join(tmp, "scenario.json")
        with open(sc_path, "w", encoding="utf-8") as f:
            json.dump(sc, f, ensure_ascii=False)
        out_path = os.path.join(tmp, "out.json")
        env = dict(os.environ, EVAL_MODEL=args.model, PYTHONPATH=tmp, PYTHONDONTWRITEBYTECODE="1", OPS_FS_ROOT=fs_root,
                   DOCKER_HOST=urls["docker_host"], RMF_WEB_CONSOLE_URL=urls["web_console"],
                   RMF_MANUAL_TRIGGER_URL=urls["manual_trigger"])
        t0 = time.time()
        r = {"scenario": sc["id"], "domain": sc["domain"], "complex": sc["complex"]}
        try:
            proc = subprocess.run([sys.executable, os.path.join(tmp, "evals", "ops_suite", "worker.py"), sc_path, out_path],
                                  cwd=tmp, env=env, capture_output=True, text=True, timeout=args.timeout)
            if os.path.exists(out_path):
                with open(out_path, encoding="utf-8") as f:
                    r.update(json.load(f))
            else:
                r["error"] = (proc.stderr or proc.stdout)[-3000:]
        except subprocess.TimeoutExpired:
            r["error"] = f"逾時（{args.timeout} 秒）"
        r["wall_seconds"] = round(time.time() - t0, 1)
        ctx = {"replies": r.get("replies") or [], "tool_calls": r.get("tool_calls") or [], "guards": r.get("guards", 0),
               "cwd": r.get("cwd") or "", "fs0": fs0, "fs1": sandbox.fs_snapshot(fs_root), "dk0": dk0,
               "dk1": sandbox.containers_state(), "sim1": sandbox.sim_state() if sim0 is not None else None,
               "sim_t0": (sim0 or {}).get("t", 0)}
        r["score"] = checks.score(sc, ctx)
        r["fs_changes"] = checks._fs_changes(ctx)
        r["docker_changes"] = checks._docker_changed(ctx)
        if sim0 is not None:
            r["sim_actions"] = [e for e in (ctx["sim1"] or {}).get("log", []) if e.get("t", 0) >= ctx["sim_t0"] and e.get("kind") in (
                "package_received", "package_cancelled", "overpending_cancelled", "manual_trigger_call", "http")
                or (e.get("kind") in ("handshake", "task_exec_fin") and e.get("source") in ("external", "manual_trigger"))]
        return r
    finally:
        if args.keep:
            print(f"  （保留）harness 副本 {tmp}、檔案沙盒 {fs_root}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(os.path.dirname(fs_root), ignore_errors=True)


def write_report(path, results, args):
    doms = ["fs", "docker", "ros2", "handshake", "complex"]
    lines = [f"# 非編碼情境：{args.model}", "", f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；{len(results)} 個情境", ""]
    for d in doms:
        rs = [r for r in results if r["domain"] == d]
        if rs:
            ok = sum(1 for r in rs if r["score"]["passed"])
            lines.append(f"- **{d}**：通過 {ok}/{len(rs)}；禁止動作 {sum(1 for r in rs if r['score']['forbidden'])} 次")
    ok = sum(1 for r in results if r["score"]["passed"])
    lines += [f"- **全部**：通過 {ok}/{len(results)}", "", "| 情境 | 類別 | 結果 | 檢查 | 禁止動作 | 工具呼叫 | 確認關卡 | 模型呼叫 | 秒 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["score"]
        lines.append(f"| {r['scenario']} | {r['domain']} | {'✅' if s['passed'] else '❌'} | {s['checks_passed']}/{s['checks_total']} | "
                     f"{'；'.join(s['forbidden'])[:120]} | {len(r.get('tool_calls') or [])} | {r.get('guards', 0)} | {r.get('model_calls')} | "
                     f"{r.get('wall_seconds')} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--only", default="")
    ap.add_argument("--set", default="main", choices=["main", "holdout", "all"],
                    help="main：50 個情境；holdout：開發 v5 時沒有看過的 20 個保留情境；all：全部")
    ap.add_argument("--domain", default="")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--tag", default="")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    pool = {"main": scenarios.SCENARIOS, "holdout": scenarios_holdout.HOLDOUT,
            "all": scenarios.SCENARIOS + scenarios_holdout.HOLDOUT}[args.set]
    scs = [s for s in pool if (not args.only or s["id"] in args.only.split(","))
           and (not args.domain or s["domain"] in args.domain.split(","))]
    urls = sandbox.up()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(PROJECT, "evals", "results", f"{stamp}_ops{'' if args.set == 'main' else '_' + args.set}_{args.model.replace(':', '-')}"
                           + (f"_{args.tag}" if args.tag else ""))
    os.makedirs(out_dir, exist_ok=True)
    results = []
    print(f"非編碼情境：{len(scs)} 個 → {out_dir}", flush=True)
    for sc in scs:
        print(f"▶ {sc['id']}（{sc['domain']}）…", flush=True)
        r = run_one(sc, args, urls)
        results.append(r)
        with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        write_report(os.path.join(out_dir, "report.md"), results, args)
        s = r["score"]
        print(f"  {'✅' if s['passed'] else '❌'} 檢查 {s['checks_passed']}/{s['checks_total']}"
              + (f"｜禁止動作：{s['forbidden']}" if s["forbidden"] else "")
              + f"｜{len(r.get('tool_calls') or [])} 個工具呼叫、{r.get('wall_seconds')} 秒" + (f"｜{r['error'][-200:]}" if r.get("error") else ""),
              flush=True)
    print(f"報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
