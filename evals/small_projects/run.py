"""小而有測試的專案（small projects）的評測：寫測試＋覆蓋率（tw）、修多個 bug（bf）、補回跨檔功能（fe）、Aider polyglot（ap）。
任務與計分在 benchmark_study_3/datasets/small_projects/（tasks/*.json、workspaces/、tools/score.py）。

    python3 evals/small_projects/run.py --model gemma4:26b
    python3 evals/small_projects/run.py --model gemma4:26b --family tw,bf --lang cpp
    python3 evals/small_projects/run.py --only tw_readtime,bf_lice --keep --tag try1

每一題：任務的工作區範本複製到臨時目錄 → 在臨時的 harness 副本裡跑 coding job（跟 DevBench 同一個 job.py：自動核准、
某一項失敗就跳過）→ 存下 agent 改了什麼（patches/<任務>.diff）→ 計分在背景執行緒（不擋下一題的 agent）。
結果在 evals/results/<時間>_smallproj_<模型>[_<tag>]/：runs.jsonl、report.md、patches/。
"""
import argparse
import difflib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT)
from evals.devbench import run as devrun  # noqa: E402
from evals.swebench.run import salvage_job  # noqa: E402

DATASET = os.environ.get("SP_DATASET") or os.path.expanduser("~/Coding_agent_harness/benchmark_study_3/datasets/small_projects")
sys.path.insert(0, os.path.join(DATASET, "tools"))
import common as SPC  # noqa: E402
import score as SPS   # noqa: E402

SKIP = {"build", "build_test", "obj", "__pycache__", ".pytest_cache", ".coverage", "htmlcov", "outputs", "test_outputs", "data"}


def load_tasks(args):
    out = []
    for fn in sorted(os.listdir(os.path.join(DATASET, "tasks"))):
        t = SPS.load_task(fn[:-5])
        if args.only and t["id"] not in args.only.split(","):
            continue
        if args.family and t["family"] not in args.family.split(","):
            continue
        if args.lang and t["lang"] != args.lang:
            continue
        out.append(t)
    return out


def _text_files(root):
    files = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP and not d.startswith(".")]
        for fn in fns:
            if fn.endswith((".o", ".gcda", ".gcno", ".gcov", ".pyc", ".a", ".so")) or fn.startswith(".coverage"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root)
            if os.path.getsize(p) > 512 * 1024 or (os.access(p, os.X_OK) and "." not in fn):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    files[rel] = f.read()
            except (UnicodeDecodeError, OSError):
                pass
    return files


def make_diff(template, ws):
    """agent 改了什麼：統一 diff＋統計（新增／修改／刪除的檔案、增減行數）。"""
    a, b = _text_files(template), _text_files(ws)
    chunks, added, modified, deleted, plus, minus = [], [], [], [], 0, 0
    for rel in sorted(set(a) | set(b)):
        old, new = a.get(rel), b.get(rel)
        if old == new:
            continue
        (added if old is None else deleted if new is None else modified).append(rel)
        diff = list(difflib.unified_diff((old or "").splitlines(True), (new or "").splitlines(True),
                                         fromfile=f"a/{rel}", tofile=f"b/{rel}"))
        plus += sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        minus += sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        chunks.append("".join(diff))
    return "\n".join(chunks), {"added": added, "modified": modified, "deleted": deleted, "plus": plus, "minus": minus}


def run_task(task, args):
    tmp = devrun.make_copy()
    ws = os.path.join(tmp, "workspace")
    SPC.copytree(os.path.join(DATASET, task["workspace"]), ws)
    task_file = os.path.join(tmp, "task.txt")
    with open(task_file, "w", encoding="utf-8") as f:
        f.write(task["task"])
    out_path = os.path.join(tmp, "job.json")
    env = dict(os.environ, EVAL_MODEL=args.model, EVAL_PLANNER_MODEL=args.planner or args.model, PYTHONPATH=tmp,
               PYTHONDONTWRITEBYTECODE="1", EVAL_JOB_TIMEOUT=str(args.timeout - 120), CODE_PYTHON=SPC.VENV_PY)
    t0 = time.time()
    result = {"task_id": task["id"], "family": task["family"], "source": task["source"], "repo": task["repo"], "lang": task["lang"]}
    try:
        proc = subprocess.run([sys.executable, os.path.join(tmp, "evals", "devbench", "job.py"), ws, task_file, out_path],
                              cwd=tmp, env=env, capture_output=True, text=True, timeout=args.timeout)
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                result.update(json.load(f))
        else:
            result["error"] = (proc.stderr or proc.stdout)[-3000:]
            result.update(salvage_job(tmp))
    except subprocess.TimeoutExpired:
        result["error"] = f"逾時（{args.timeout} 秒）"
        result.update(salvage_job(tmp))
    result["wall_seconds"] = round(time.time() - t0, 1)
    diff, stats = make_diff(os.path.join(DATASET, task["workspace"]), ws)
    result["diff_stats"] = stats
    result["patch"] = diff
    result["_ws"] = ws
    result["_tmp"] = tmp
    return result


class Scorer:
    def __init__(self, out_dir, report, keep):
        self.out_dir, self.report, self.keep = out_dir, report, keep
        self.q, self.results, self.lock = queue.Queue(), [], threading.Lock()
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def _loop(self):
        while True:
            item = self.q.get()
            if item is None:
                return
            task, r = item
            try:
                r["score"] = SPS.score(task, r["_ws"])
            except Exception as e:      # noqa: BLE001
                r["score"] = {"error": f"計分失敗：{e!r}"}
            if self.keep:
                r["tmp_dir"] = r["_tmp"]
            else:
                shutil.rmtree(r["_tmp"], ignore_errors=True)
            r.pop("_ws", None)
            r.pop("_tmp", None)
            with self.lock:
                self.results.append(r)
                with open(os.path.join(self.out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                self.report(self.results)
            print(f"  計分 {r['task_id']}：{headline(r)}", flush=True)

    def put(self, task, r):
        os.makedirs(os.path.join(self.out_dir, "patches"), exist_ok=True)
        with open(os.path.join(self.out_dir, "patches", f"{r['task_id']}.diff"), "w", encoding="utf-8") as f:
            f.write(r.get("patch") or "")
        self.q.put((task, r))

    def close(self):
        self.q.put(None)
        self.t.join()


def headline(r):
    s = r.get("score") or {}
    if s.get("error"):
        return "計分失敗 " + str(s["error"])[-200:]
    if r["family"] == "tw":
        return (f"測試 {s.get('tests_passed')}/{s.get('tests_total')} 通過｜行 {s.get('line_cov')}%、分支 {s.get('branch_cov')}%｜"
                f"mutation {s.get('mut_killed')}/{s.get('mut_total')}（{s.get('mut_score')}%）"
                + (f"｜改了正式程式 {s['prod_changed']}" if s.get("prod_changed") else ""))
    if r["family"] in ("bf", "fe"):
        return (("✅ 解決" if s.get("resolved") else "❌") + f"（單元 {s.get('unit')}/{s.get('unit_total')}、"
                f"驗收 {s.get('acceptance')}/{s.get('acceptance_total')}）" + (f"｜改了測試 {s['tests_changed']}" if s.get("tests_changed") else ""))
    return ("✅ 解決" if s.get("resolved") else "❌") + (f"（{s.get('tests_passed')}/{s.get('tests_total')}）" if "tests_total" in s else "")


def write_report(path, results, args):
    fams = {"tw": "寫測試＋覆蓋率", "bf": "修多個 bug", "fe": "補回跨檔功能", "ap": "Aider polyglot"}
    lines = [f"# 小專案評測：worker {args.model}、規劃 {args.planner or args.model}", "",
             f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；已計分 {len(results)} 題", ""]
    for fam, label in fams.items():
        rs = [r for r in results if r["family"] == fam]
        if not rs:
            continue
        if fam == "tw":
            def avg(k):
                vals = [(r.get("score") or {}).get(k) for r in rs]
                vals = [v for v in vals if isinstance(v, (int, float))]
                return round(sum(vals) / len(vals), 1) if vals else None
            lines.append(f"- **{label}**（{len(rs)} 題）：平均行覆蓋率 {avg('line_cov')}%、分支 {avg('branch_cov')}%、"
                         f"mutation score {avg('mut_score')}%")
        else:
            ok = sum(1 for r in rs if (r.get("score") or {}).get("resolved"))
            lines.append(f"- **{label}**：解決 {ok}/{len(rs)}")
    lines += ["", "| 任務 | 類別 | 語言 | 結果 | job 狀態 | 改的檔案 | 分鐘 | 模型呼叫 |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: x["task_id"]):
        st = r.get("diff_stats") or {}
        nfiles = len(st.get("added", [])) + len(st.get("modified", [])) + len(st.get("deleted", []))
        lines.append(f"| {r['task_id']} | {r['family']} | {r['lang']} | {headline(r)} | {r.get('job_status')} | {nfiles} | "
                     f"{round((r.get('seconds') or r.get('wall_seconds') or 0) / 60, 1)} | {r.get('model_calls')} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--planner", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--family", default="")
    ap.add_argument("--lang", default="")
    ap.add_argument("--timeout", type=int, default=2400, help="每一題的上限（秒）")
    ap.add_argument("--tag", default="")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    tasks = load_tasks(args)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    name = f"{stamp}_smallproj_{args.model.replace(':', '-')}" + (f"_plan-{args.planner.replace(':', '-')}" if args.planner else "") \
        + (f"_{args.tag}" if args.tag else "")
    out_dir = os.path.join(PROJECT, "evals", "results", name)
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "report.md")
    scorer = Scorer(out_dir, lambda rs: write_report(report_path, rs, args), args.keep)
    print(f"小專案評測：{len(tasks)} 題 → {out_dir}", flush=True)
    for task in tasks:
        print(f"▶ {task['id']}（{task['family']}／{task['lang']}，worker {args.model}）…", flush=True)
        r = run_task(task, args)
        print(f"  job {r.get('job_status')}，{round((r.get('seconds') or r.get('wall_seconds') or 0) / 60, 1)} 分鐘，"
              f"模型呼叫 {r.get('model_calls')} 次，改了 {sum(len(v) for k, v in r['diff_stats'].items() if isinstance(v, list))} 個檔案",
              flush=True)
        scorer.put(task, r)
    scorer.close()
    print(f"報表：{report_path}")


if __name__ == "__main__":
    main()
