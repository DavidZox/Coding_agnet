"""用官方的 swebench 套件（獨立的 venv：~/swebench_venv，pip install swebench）計分：把 patch 套到題目映像的新容器、
跑題目的評分腳本（eval_script：先換上 test_patch 裡的測試，再跑測試），用官方的 log parser 判斷 FAIL_TO_PASS 與 PASS_TO_PASS。
resolved＝FAIL_TO_PASS 全部通過、PASS_TO_PASS 全部仍然通過（SWE-bench 的標準指標）。

    python3 evals/swebench/evaluate.py --gold            # 用參考解答驗證計分環境（每一題都應該 resolved）
    python3 evals/swebench/evaluate.py --preds <predictions.jsonl> --run-id <名稱>
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from evals.swebench import tasks  # noqa: E402

SWEBENCH_PY = os.path.expanduser(os.environ.get("SWEBENCH_PY", "~/swebench_venv/bin/python"))
EVAL_DIR = os.path.expanduser("~/cah_eval/swe/eval")      # swebench 把紀錄寫在 cwd 的 logs/run_evaluation/ 底下


def run_official(preds_path, run_id, ids, workers=2, timeout=1800, instances=tasks.INSTANCES):
    """呼叫 swebench.harness.run_evaluation；回傳 {instance_id: 結果 dict}（沒有結果的題目不在裡面）。"""
    os.makedirs(EVAL_DIR, exist_ok=True)
    cmd = [SWEBENCH_PY, "-m", "swebench.harness.run_evaluation", "-d", instances, "-s", "test", "-p", preds_path,
           "-i", *ids, "--max_workers", str(workers), "-t", str(timeout), "-id", run_id, "--report_dir", EVAL_DIR]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=EVAL_DIR, capture_output=True, text=True, errors="replace")
    out = {}
    model_names = set()
    if preds_path == "gold":
        model_names.add("gold")
    else:
        with open(preds_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    model_names.add(json.loads(line)["model_name_or_path"])
    for model in model_names:
        for iid in ids:
            d = os.path.join(EVAL_DIR, "logs", "run_evaluation", run_id, model.replace("/", "__"), iid)
            rep = os.path.join(d, "report.json")
            if os.path.isfile(rep):
                with open(rep, encoding="utf-8") as f:
                    data = json.load(f).get(iid, {})
                ts = data.get("tests_status") or {}
                out[iid] = {"resolved": bool(data.get("resolved")), "applied": bool(data.get("patch_successfully_applied")),
                            "f2p_pass": len((ts.get("FAIL_TO_PASS") or {}).get("success") or []),
                            "f2p_fail": len((ts.get("FAIL_TO_PASS") or {}).get("failure") or []),
                            "p2p_pass": len((ts.get("PASS_TO_PASS") or {}).get("success") or []),
                            "p2p_fail": len((ts.get("PASS_TO_PASS") or {}).get("failure") or []),
                            "log_dir": d}
            elif os.path.isdir(d):
                tail = ""
                try:
                    with open(os.path.join(d, "run_instance.log"), encoding="utf-8", errors="replace") as f:
                        tail = f.read()[-1500:]
                except OSError:
                    pass
                out[iid] = {"resolved": False, "applied": "Patch Apply Failed" not in tail and "APPLY_PATCH_FAIL" not in tail,
                            "error": tail, "log_dir": d}
    for iid in ids:
        out.setdefault(iid, {"resolved": False, "applied": False, "error": "沒有評分紀錄（patch 是空的或評分失敗）\n"
                             + (proc.stdout + proc.stderr)[-1500:]})
        out[iid]["eval_seconds"] = round(time.time() - t0, 1)
    return out


def evaluate_patch(iid, patch, model_name, run_id, timeout=1800):
    """單一題目的 patch 計分（空的 patch 直接算沒有解決，不跑容器）。"""
    if not (patch or "").strip():
        return {"resolved": False, "applied": False, "empty_patch": True}
    d = os.path.join(EVAL_DIR, "preds")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{run_id}__{iid}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"instance_id": iid, "model_name_or_path": model_name, "model_patch": patch}) + "\n")
    return run_official(path, run_id, [iid], workers=1, timeout=timeout)[iid]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", action="store_true")
    ap.add_argument("--preds")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    ids = [x for x in args.only.split(",") if x] or [r["instance_id"] for r in tasks.load()]
    run_id = args.run_id or ("gold_check_" + time.strftime("%Y%m%d_%H%M%S") if args.gold else None)
    if not run_id:
        raise SystemExit("需要 --run-id")
    res = run_official("gold" if args.gold else args.preds, run_id, ids, workers=args.workers)
    ok = sum(1 for r in res.values() if r["resolved"])
    for iid in ids:
        r = res[iid]
        print(f"{'✅' if r['resolved'] else '❌'} {iid}  F2P {r.get('f2p_pass', '?')}/{r.get('f2p_pass', 0) + r.get('f2p_fail', 0)}  "
              f"P2P {r.get('p2p_pass', '?')}/{r.get('p2p_pass', 0) + r.get('p2p_fail', 0)}" + (f"  {r.get('error', '')[-200:]}" if r.get("error") else ""))
    print(f"resolved {ok}/{len(ids)}")
    with open(os.path.join(EVAL_DIR, f"{run_id}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
