"""提煉（工具回傳的任務導向提煉、result_recall）的真模型評測：程式產生已知答案的長輸出（evals/extract/cases.py），看提煉後的重點
找到幾個、多列了幾個、說的數量對不對，以及切了幾段、讀了幾段、模型呼叫幾次、程式核對拿掉幾條、花了幾秒。

    python3 evals/extract/run.py --model gemma4:26b
    python3 evals/extract/run.py --model gemma4:e4b --only fleet_80,log_200k --runs 3

每一次都在臨時目錄複製一份專案來跑（不動正式的 logs/）；結果在 evals/results/<時間>_extract_<模型>[_<tag>]/：runs.jsonl、report.md，
以及每一次的提煉存檔 logs/<情境>_<第幾次>/（logs/extract_jobs/<編號>/ 的 job.json、calls.jsonl、events.jsonl 與工具原文）。
跟基準比用 evals/phase_check.py（基準在 evals/baselines/extract.json）。"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT)
from evals.extract.cases import all_cases  # noqa: E402

COPY_ITEMS = ["agent_core", "skills_system", "prompts", "evals"]
_COUNT_RE = re.compile(r"(?:總共|共計|合計|一共|共)\s*(?:有\s*)?(\d+)\s*(?:台|筆|則|個|次|項|輛)")
_NAME_RE = re.compile(r"amr_\d+")


def make_copy():
    tmp = tempfile.mkdtemp(prefix="extract_eval_")
    ignore = shutil.ignore_patterns("__pycache__", "results", "drafts", "dataset")
    for item in COPY_ITEMS:
        shutil.copytree(os.path.join(PROJECT, item), os.path.join(tmp, item), ignore=ignore)
    os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
    return tmp


def _name_pat(name):
    return re.compile(rf"(?<![\w]){re.escape(name)}(?!\d)")


def _value_pat(v):
    return re.compile(rf"(?<![\d.]){re.escape(str(v))}(?![\d])")


def score(case, text):
    """回覆原文對正確答案：found（找到幾個）、missing（漏了哪些）、extra（多列的名稱）、count_claims（回覆裡「共 N 台」這類說法）、count_ok。"""
    text = text or ""
    lines = text.splitlines()
    truth = case["truth"]
    found, missing = [], []
    for t in truth:
        if case["match"] == "fleet":
            ok = any(_name_pat(t["key"]).search(ln) and _value_pat(t["value"]).search(ln) for ln in lines)
        elif case["match"] == "name":
            ok = bool(_name_pat(t["key"]).search(text))
        else:
            ok = t["key"] in text
        (found if ok else missing).append(t["key"])
    extra = []
    if case["match"] in ("fleet", "name"):
        keys = {t["key"] for t in truth}
        extra = sorted({m for m in _NAME_RE.findall(text) if m not in keys})
    claims = [int(n) for n in _COUNT_RE.findall(text)]
    return {"found": len(found), "total": len(truth), "missing": missing, "extra": extra, "count_claims": claims,
            "count_ok": (all(n == len(truth) for n in claims) if claims else None)}


def job_info(logs_dir):
    """這一次提煉的存檔（logs/extract_jobs/*）：模式、段數、讀了幾段、程式拿掉幾條、整合有沒有修正、模型呼叫幾次。"""
    jobs = []
    for d in sorted(glob.glob(os.path.join(logs_dir, "extract_jobs", "*"))):
        try:
            with open(os.path.join(d, "job.json"), encoding="utf-8") as f:
                job = json.load(f)
        except (OSError, ValueError):
            continue
        try:
            with open(os.path.join(d, "calls.jsonl"), encoding="utf-8") as f:
                calls = sum(1 for ln in f if ln.strip())
        except OSError:
            calls = 0
        synth = job.get("synth") or {}
        jobs.append({"kind": job.get("kind"), "mode": job.get("mode"), "chunks": len(job.get("chunks") or []), "read": len(job.get("workers") or []),
                     "dropped": sum(len(w.get("dropped") or []) for w in job.get("workers") or []) + len(synth.get("dropped") or []),
                     "repaired": bool(synth.get("repaired")), "calls": calls, "status": job.get("status"), "seconds": job.get("seconds")})
    return jobs


def run_one(case, args, out_dir, k):
    tmp = make_copy()
    try:
        case_path, out_path = os.path.join(tmp, "case.json"), os.path.join(tmp, "out.json")
        with open(case_path, "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False)
        env = dict(os.environ, EVAL_MODEL=args.model, PYTHONPATH=tmp, PYTHONDONTWRITEBYTECODE="1")
        t0 = time.time()
        r = {"case": case["id"], "model": args.model, "run": k}
        try:
            proc = subprocess.run([sys.executable, os.path.join(tmp, "evals", "extract", "worker.py"), case_path, out_path],
                                  cwd=tmp, env=env, capture_output=True, text=True, timeout=args.timeout)
            if os.path.exists(out_path):
                with open(out_path, encoding="utf-8") as f:
                    r.update(json.load(f))
            else:
                r["error"] = (proc.stderr or proc.stdout)[-2000:]
        except subprocess.TimeoutExpired:
            r["error"] = f"逾時（{args.timeout} 秒）"
        r["wall_seconds"] = round(time.time() - t0, 1)
        r["jobs"] = job_info(os.path.join(tmp, "logs"))
        answer = r.get("recall") if case.get("recall") else r.get("summary")
        r["score"] = score(case, answer)
        if os.path.isdir(os.path.join(tmp, "logs")):
            shutil.copytree(os.path.join(tmp, "logs"), os.path.join(out_dir, "logs", f"{case['id']}_{k}"), dirs_exist_ok=True)
        return r
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_report(path, results, args):
    lines = [f"# 提煉的真模型評測：{args.model}", "", f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；{len(results)} 次", "",
             "| 情境 | 第幾次 | 找到 | 漏了 | 多列的 | 數量的說法 | 模式 | 段數（讀了） | 模型呼叫 | 程式拿掉 | 整合修正 | 秒 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["score"]
        jobs = r.get("jobs") or []
        j = jobs[-1] if jobs else {}
        claims = "、".join(map(str, s["count_claims"])) or "—"
        secs = r.get("recall_seconds") if r["case"].startswith("recall") else r.get("summary_seconds")
        lines.append(f"| {r['case']} | {r['run']} | {s['found']}/{s['total']} | {'、'.join(s['missing'][:6]) or '—'} | {'、'.join(s['extra'][:6]) or '—'} | "
                     f"{claims}{'' if s['count_ok'] in (None, True) else ' ❌'} | {j.get('mode', '—')} | {j.get('chunks', '—')}（{j.get('read', '—')}） | "
                     f"{sum(x.get('calls', 0) for x in jobs)} | {sum(x.get('dropped', 0) for x in jobs)} | {'是' if any(x.get('repaired') for x in jobs) else '否'} | "
                     f"{secs if secs is not None else '—'}{'（' + r['error'][:60] + '）' if r.get('error') else ''} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--only", default="")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--tag", default="")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    cases = [c for c in all_cases() if not args.only or c["id"] in args.only.split(",")]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(PROJECT, "evals", "results", f"{stamp}_extract_{args.model.replace(':', '-')}" + (f"_{args.tag}" if args.tag else ""))
    os.makedirs(out_dir, exist_ok=True)
    print(f"提煉評測：{len(cases)} 個情境 × {args.runs} 次 → {out_dir}", flush=True)
    results = []
    for case in cases:
        for k in range(1, args.runs + 1):
            r = run_one(case, args, out_dir, k)
            results.append(r)
            with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({x: v for x, v in r.items() if x != "last"}, ensure_ascii=False) + "\n")
            write_report(os.path.join(out_dir, "report.md"), results, args)
            s = r["score"]
            print(f"  {'✅' if s['found'] == s['total'] and not s['extra'] and s['count_ok'] is not False else '⚠️'} {case['id']} #{k}：找到 "
                  f"{s['found']}/{s['total']}、多列 {len(s['extra'])}、{r.get('wall_seconds')} 秒" + (f"｜{r['error'][:200]}" if r.get("error") else ""), flush=True)
    print(f"報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
