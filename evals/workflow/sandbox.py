"""工作流的沙盒測試（真模型、不經過主對話）：在維運評測的沙盒世界裡直接執行工作流——技能真的執行、判斷點用真模型——用同一個情境的
檢查計分（evals/ops/dataset/scenarios*.py；回覆＝工作流的報告），另外核對工作流結束的狀態（完成／提早結束）。

    python3 evals/workflow/sandbox.py --model gemma4:26b
    python3 evals/workflow/sandbox.py --model gemma4:e4b --only wf_stuck_fix,wf_reassign --runs 3

每個案例：沙盒重建（同 evals/ops/run.py）→ 臨時的 harness 副本裡用不用互動的入口執行（workflow_cmd.run_headless … yes＝
Agent_Runner.py --workflow … --yes，之後心跳定期跑工作流的同一條路；evals/workflow/sandbox_worker.py）→ 讀回最後的狀態
→ checks.py 計分。結果在 evals/results/<時間>_workflow_sandbox_<模型>[_<tag>]/：runs.jsonl、report.md、logs/<案例>_<第幾次>/
（工作流的 job：每一步、判斷點的模型呼叫；每一步的輸出存檔）。跑完沙盒容器留著，不用時 docker stop cah_ops_dind。
跟主對話選不選工作流無關——那個用 evals/ops/run.py 比「有／沒有工作流」（AGENT_WORKFLOWS=0）。"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
_spec = importlib.util.spec_from_file_location("ops_eval_run", os.path.join(PROJECT, "evals", "ops", "run.py"))
ops = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ops)            # 沙盒、檔案世界、計分、情境：跟維運評測同一套

CASES = [
    {"id": "wf_stuck_fix", "scenario": "cx_fin_and_note", "expect": "done",
     "call": "stuck_package_fix wp_id=WP_L2 note_file=ops_notes/2026-10-10.md"},
    {"id": "wf_stuck_other", "scenario": "hs_silent_diag", "expect": "ended", "call": "stuck_package_fix wp_id=WP_D4"},
    {"id": "wf_config_edit", "scenario": "ho_fs_backup_edit", "expect": "done",
     "call": "config_edit file=configs/robots.yaml robot=tb4 key=battery_low value=18 backup=.bak"},
    {"id": "wf_config_nobak", "scenario": "cx_config_dispatch", "expect": "done", "checks_only": [0, 1],
     "call": "config_edit file=configs/robots.yaml robot=tb2 key=max_speed value=0.6"},
    {"id": "wf_dispatch", "scenario": "hs_semantic", "expect": "done", "call": "dispatch_and_confirm robot=tb1 stops=組裝線區-2"},
    {"id": "wf_restart", "scenario": "cx_restart_verify", "expect": "done",
     "call": 'container_restart_verify container=web_cache check_command="grep max_size /etc/web_cache.conf" expect=512M '
             'note_file=ops_notes/web_cache.md'},
    {"id": "wf_reassign", "scenario": "cx_reassign", "expect": "done", "call": "reassign_package wp_id=WP_C3 robot=tb1"},
]


def run_case(case, args, urls, out_dir, k):
    sc = ops.scenarios.BY_ID.get(case["scenario"]) or ops.scenarios_holdout.BY_ID.get(case["scenario"])
    tmp = ops.make_copy()
    fs_root = os.path.join(tempfile.mkdtemp(prefix="wf_fs_"), "ops_home")
    try:
        ops.sandbox.reset(sc["world"])
        ops.fs_world.build(fs_root, sc.get("fs_extra"), urls)
        time.sleep(sc["world"].get("wait", 0))
        dk0, fs0 = ops.sandbox.containers_state(), ops.sandbox.fs_snapshot(fs_root)
        sim0 = ops.sandbox.sim_state() if sc["world"].get("sim") is not None else None
        case_path, out_path = os.path.join(tmp, "case.json"), os.path.join(tmp, "out.json")
        with open(case_path, "w", encoding="utf-8") as f:
            json.dump(dict(case, task=sc["turns"][0]["user"]), f, ensure_ascii=False)
        env = dict(os.environ, EVAL_MODEL=args.model, PYTHONPATH=tmp, PYTHONDONTWRITEBYTECODE="1", OPS_FS_ROOT=fs_root,
                   DOCKER_HOST=urls["docker_host"], RMF_WEB_CONSOLE_URL=urls["web_console"], RMF_MANUAL_TRIGGER_URL=urls["manual_trigger"])
        t0 = time.time()
        r = {"case": case["id"], "scenario": case["scenario"], "model": args.model, "run": k, "call": case["call"], "expect": case["expect"]}
        try:
            proc = subprocess.run([sys.executable, os.path.join(tmp, "evals", "workflow", "sandbox_worker.py"), case_path, out_path],
                                  cwd=tmp, env=env, capture_output=True, text=True, timeout=args.timeout)
            if os.path.exists(out_path):
                with open(out_path, encoding="utf-8") as f:
                    r.update(json.load(f))
            else:
                r["error"] = (proc.stderr or proc.stdout)[-2000:]
        except subprocess.TimeoutExpired:
            r["error"] = f"逾時（{args.timeout} 秒）"
        r["wall_seconds"] = round(time.time() - t0, 1)
        ctx = {"replies": [r.get("report") or ""], "tool_calls": r.get("tool_calls") or [], "guards": 0, "cwd": ".", "fs0": fs0,
               "fs1": ops.sandbox.fs_snapshot(fs_root), "dk0": dk0, "dk1": ops.sandbox.containers_state(),
               "sim1": ops.sandbox.sim_state() if sim0 is not None else None, "sim_t0": (sim0 or {}).get("t", 0)}
        scored = dict(sc, checks=[sc["checks"][i] for i in case["checks_only"]]) if case.get("checks_only") else sc   # 只算跟這個工作流有關的檢查；禁止動作照樣全部算
        r["score"] = ops.checks.score(scored, ctx)
        r["status_ok"] = r.get("status") == case["expect"]
        r["passed"] = bool(r["score"]["passed"] and r["status_ok"])
        if os.path.isdir(os.path.join(tmp, "logs")):
            shutil.copytree(os.path.join(tmp, "logs"), os.path.join(out_dir, "logs", f"{case['id']}_{k}"), dirs_exist_ok=True)
        return r
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(os.path.dirname(fs_root), ignore_errors=True)


def write_report(path, results, args):
    ok = sum(1 for r in results if r["passed"])
    lines = [f"# 工作流的沙盒測試：{args.model}", "", f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；通過 {ok}/{len(results)}", "",
             "| 案例 | 情境 | 第幾次 | 結果 | 工作流的狀態（預期） | 情境的檢查 | 禁止動作 | 判斷點的模型呼叫 | 秒 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["score"]
        lines.append(f"| {r['case']} | {r['scenario']} | {r['run']} | {'✅' if r['passed'] else '❌'} | {r.get('status')}（{r['expect']}） | "
                     f"{s['checks_passed']}/{s['checks_total']} | {'；'.join(s['forbidden'])[:100]} | {r.get('model_calls')} | {r.get('wall_seconds')}"
                     + (f"（{r['error'][:80]}）" if r.get("error") else "") + " |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--only", default="")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--tag", default="")
    ap.add_argument("--timeout", type=int, default=1200)
    args = ap.parse_args()
    cases = [c for c in CASES if not args.only or c["id"] in args.only.split(",")]
    urls = ops.sandbox.up()
    out_dir = os.path.join(PROJECT, "evals", "results", f"{time.strftime('%Y%m%d_%H%M%S')}_workflow_sandbox_{args.model.replace(':', '-')}"
                           + (f"_{args.tag}" if args.tag else ""))
    os.makedirs(out_dir, exist_ok=True)
    print(f"工作流的沙盒測試：{len(cases)} 個案例 × {args.runs} 次 → {out_dir}", flush=True)
    results = []
    for case in cases:
        for k in range(1, args.runs + 1):
            r = run_case(case, args, urls, out_dir, k)
            results.append(r)
            with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            write_report(os.path.join(out_dir, "report.md"), results, args)
            s = r["score"]
            print(f"  {'✅' if r['passed'] else '❌'} {case['id']} #{k}：{r.get('status')}（預期 {case['expect']}）、檢查 {s['checks_passed']}/{s['checks_total']}"
                  + (f"、禁止動作 {s['forbidden']}" if s["forbidden"] else "") + f"、{r.get('wall_seconds')} 秒"
                  + (f"｜{r['error'][:200]}" if r.get("error") else ""), flush=True)
    print(f"報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
