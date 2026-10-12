"""SWE-bench 子集（既有專案的 issue 修正，Python／C／C++）的評測：每一題交給 coding orchestrator，在題目的開發環境裡修正，
再用官方的 swebench 套件計分（resolved＝評分用的 FAIL_TO_PASS 測試全部通過、PASS_TO_PASS 仍然全部通過）。

    python3 evals/swebench/run.py --model gemma4:26b
    python3 evals/swebench/run.py --model qwen2.5-coder:32b --planner deepseek-r1:32b
    python3 evals/swebench/run.py --only django__django-12276 --keep

每一題：用題目的官方映像起一個開發環境（env.py：容器、工作區掛在同一個路徑、python／pytest／make／cmake／gcc 的包裝指令）→
工作區根目錄放開發環境說明（.coding_agent.md：怎麼建置、怎麼跑測試）→ 在臨時的 harness 副本裡跑 coding job（跟 DevBench
用同一個 job.py：自動核准、某一項失敗就跳過）→ 工作區相對於 base_commit 的改動就是 patch → 關掉環境 → 官方計分（背景執行，
不擋下一題）。agent 從頭到尾看不到評分用的測試（test_patch）。

先跑一次 prepare.py（下載映像、用參考解答驗證計分）。結果在 evals/results/<時間>_swebench_<模型>/：report.md、runs.jsonl、
patches/<題目>.diff。
"""
import argparse
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
from evals.swebench import env, evaluate, tasks  # noqa: E402


def patch_stats(patch):
    files = [l.split(" b/", 1)[-1] for l in patch.splitlines() if l.startswith("diff --git ")]
    add = sum(1 for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
    rem = sum(1 for l in patch.splitlines() if l.startswith("-") and not l.startswith("---"))
    return {"files": files, "added": add, "removed": rem}


def salvage_job(tmp):
    """job.py 被逾時結束、沒有寫出 job.json 時，從 coding job 自己的紀錄（logs/coding_jobs/<編號>/state.json、events.jsonl）
    撈回狀態與事件流，逾時的題目也看得到它做了什麼（只影響紀錄，不影響計分）。"""
    import glob
    out = {}
    for d in sorted(glob.glob(os.path.join(tmp, "logs", "coding_jobs", "*", ""))):
        try:
            with open(os.path.join(d, "state.json"), encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            continue
        events = []
        try:
            with open(os.path.join(d, "events.jsonl"), encoding="utf-8") as f:
                events = [json.loads(line) for line in f if line.strip()]
        except (OSError, ValueError):
            pass
        items = [{"n": it.get("n"), "title": it.get("title"), "status": it.get("status"), "attempts": it.get("attempts"),
                  "steps": it.get("steps"), "files": it.get("files"), "verify": it.get("verify"), "summary": it.get("summary")}
                 for it in st.get("items") or []]
        out = {"job_status": st.get("status"), "model_calls": st.get("model_calls"), "items": items, "warnings": st.get("warnings"),
               "final_verify": st.get("final_verify"), "events": events, "salvaged": True}
    return out


def run_instance(inst, args, out_dir, tag):
    iid = inst["instance_id"]
    ws = os.path.join(env.ROOT, "ws", os.path.basename(out_dir), iid)
    result = {"instance_id": iid, "repo": inst["repo"], "lang": inst["lang"], "difficulty": inst.get("difficulty", "")}
    t0 = time.time()
    try:
        info = env.start(inst, ws, tag, bin_root=os.path.join(env.ROOT, "env", os.path.basename(out_dir)))
    except Exception as e:      # noqa: BLE001
        result.update(error=f"開發環境起不來：{e}", patch="", wall_seconds=round(time.time() - t0, 1))
        return result
    result["env"] = {k: info[k] for k in ("wrapped", "notes", "pythonpath", "pre_dirty")}
    env.write_rules(ws, tasks.rules_text(inst))
    tmp = devrun.make_copy()
    task_file = os.path.join(tmp, "task.txt")
    with open(task_file, "w", encoding="utf-8") as f:
        f.write(tasks.task_text(inst))
    out_path = os.path.join(tmp, "job.json")
    penv = dict(os.environ, EVAL_MODEL=args.model, EVAL_PLANNER_MODEL=args.planner or args.model, PYTHONPATH=tmp,
                PYTHONDONTWRITEBYTECODE="1", EVAL_JOB_TIMEOUT=str(args.timeout - 120), CODE_PYTHON=info["code_python"])
    try:
        proc = subprocess.run([sys.executable, os.path.join(tmp, "evals", "devbench", "job.py"), ws, task_file, out_path],
                              cwd=tmp, env=penv, capture_output=True, text=True, timeout=args.timeout)
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                result.update(json.load(f))
        else:
            result["error"] = (proc.stderr or proc.stdout)[-3000:]
    except subprocess.TimeoutExpired:
        result["error"] = f"逾時（{args.timeout} 秒）"
    if "events" not in result:
        result.update(salvage_job(tmp))
    result["wall_seconds"] = round(time.time() - t0, 1)
    try:
        patch, notes = env.make_patch(ws, inst["base_commit"], info["pre_untracked"])
    except Exception as e:      # noqa: BLE001
        patch, notes = "", [f"產生 patch 失敗：{e}"]
    result["patch"] = patch
    result["patch_notes"] = notes
    result["patch_stats"] = patch_stats(patch)
    env.stop(info, remove_workspace=not args.keep)
    if args.keep:
        result["tmp_dir"] = tmp
        result["workspace"] = ws
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def write_report(path, results, args, title=None, bare=False):
    done = [r for r in results if "score" in r]
    ok = sum(1 for r in done if r["score"].get("resolved"))
    lines = [title or f"# SWE-bench 子集（既有專案的 issue 修正）：worker {args.model}、規劃 {getattr(args, 'planner', None) or args.model}", "",
             f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；{len(done)} 題已計分；"
             + ("**不用 harness**：關鍵字檢索找出相關檔案、模型一次寫出修改（SEARCH/REPLACE）。" if bare else
                "coding orchestrator 在題目的開發環境（官方 Docker 映像）裡修正，agent 看不到評分用的測試。"),
             f"- **resolved {ok}/{len(done)}**（{100 * ok / max(1, len(done)):.1f}%）"]
    for lang in ("Python", "C", "C++"):
        g = [r for r in done if r["lang"] == lang]
        if g:
            lines.append(f"  - {lang}：{sum(1 for r in g if r['score'].get('resolved'))}/{len(g)}")
    lines += ["", "| 題目 | 語言 | 難度 | resolved | patch 套用 | F2P | P2P | job 狀態 | 改的檔案 | 分鐘 | 模型呼叫 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in done:
        s = r["score"]
        f2p = f"{s.get('f2p_pass', '—')}/{s.get('f2p_pass', 0) + s.get('f2p_fail', 0)}" if "f2p_pass" in s else "—"
        p2p = f"{s.get('p2p_pass', '—')}/{s.get('p2p_pass', 0) + s.get('p2p_fail', 0)}" if "p2p_pass" in s else "—"
        st = r.get("patch_stats") or {}
        lines.append(f"| {r['instance_id']} | {r['lang']} | {r.get('difficulty') or '—'} | {'✅' if s.get('resolved') else '❌'} | "
                     f"{'是' if s.get('applied') else ('空的' if s.get('empty_patch') else '否')} | {f2p} | {p2p} | {r.get('job_status', '—')} | "
                     f"{len(st.get('files') or [])} | {(r.get('seconds') or r.get('wall_seconds') or 0) / 60:.1f} | {r.get('model_calls') or '—'} |")
    lines += ["", "## 每一題"]
    for r in done:
        st = r.get("patch_stats") or {}
        lines.append(f"\n### {r['instance_id']}：{'✅ resolved' if r['score'].get('resolved') else '❌'}")
        if r.get("error"):
            lines.append(f"- 錯誤：{str(r['error'])[:500]}")
        if r["score"].get("error"):
            lines.append(f"- 計分：{str(r['score']['error'])[-300:]}")
        lines.append(f"- patch：{', '.join(st.get('files') or []) or '（空的）'}（+{st.get('added', 0)}／-{st.get('removed', 0)}）")
        if r.get("final_head"):
            lines.append(f"- 整體驗證（agent 自己的）：{r['final_head'][:300]}")
        for it in r.get("items") or []:
            lines.append(f"  - {it['n']}. {it['status']}（{it['attempts']} 次、{it['steps']} 步）{it['title']}；檔案 {it['files']}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class Scorer:
    """背景計分：一題的 patch 好了就丟進來，官方計分在另一條執行緒跑（不擋下一題的 agent），結果寫進 runs.jsonl 與 report.md。"""

    def __init__(self, out_dir, model_name, report):
        self.out_dir, self.model_name, self.report = out_dir, model_name, report
        self.q, self.results, self.lock = queue.Queue(), [], threading.Lock()
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def _loop(self):
        while True:
            r = self.q.get()
            if r is None:
                return
            try:
                r["score"] = evaluate.evaluate_patch(r["instance_id"], r.get("patch") or "", self.model_name,
                                                     os.path.basename(self.out_dir))
            except Exception as e:      # noqa: BLE001
                r["score"] = {"resolved": False, "applied": False, "error": f"計分失敗：{e}"}
            with self.lock:
                self.results.append(r)
                with open(os.path.join(self.out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                self.report(self.results)
            s = r["score"]
            print(f"  計分 {r['instance_id']}：{'✅ resolved' if s.get('resolved') else '❌'}"
                  + (f"（F2P {s.get('f2p_pass')}/{s.get('f2p_pass', 0) + s.get('f2p_fail', 0)}）" if "f2p_pass" in s else "")
                  + (f"；{str(s.get('error'))[-150:]}" if s.get("error") else ""), flush=True)

    def put(self, r):
        os.makedirs(os.path.join(self.out_dir, "patches"), exist_ok=True)
        with open(os.path.join(self.out_dir, "patches", f"{r['instance_id']}.diff"), "w", encoding="utf-8") as f:
            f.write(r.get("patch") or "")
        self.q.put(r)

    def close(self):
        self.q.put(None)
        self.t.join()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--planner", default=None)
    ap.add_argument("--only", default="")
    ap.add_argument("--lang", choices=["Python", "C", "C++", "all"], default="all")
    ap.add_argument("--timeout", type=int, default=3600, help="每一題 agent 的上限（秒）")
    ap.add_argument("--keep", action="store_true", help="保留工作區與臨時的 harness 副本")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    insts = tasks.load()
    only = [x.strip() for x in args.only.split(",") if x.strip()]
    insts = [i for i in insts if (not only or i["instance_id"] in only) and (args.lang == "all" or i["lang"] == args.lang)]
    tag = args.model.replace(":", "-") + (f"_plan-{args.planner.replace(':', '-')}" if args.planner else "") + (f"_{args.tag}" if args.tag else "")
    out_dir = os.path.join(PROJECT, "evals", "results", time.strftime("%Y%m%d_%H%M%S") + f"_swebench_{tag}")
    os.makedirs(out_dir, exist_ok=True)
    scorer = Scorer(out_dir, tag, lambda results: write_report(os.path.join(out_dir, "report.md"), results, args))
    for inst in insts:
        print(f"▶ {inst['instance_id']}（{inst['lang']}，worker {args.model}）…", flush=True)
        r = run_instance(inst, args, out_dir, "h" + str(int(time.time()) % 100000))
        st = r.get("patch_stats") or {}
        print(f"  job {r.get('job_status', '?')}，{(r.get('seconds') or r['wall_seconds']) / 60:.1f} 分鐘，模型呼叫 {r.get('model_calls')} 次，"
              f"patch {len(st.get('files') or [])} 個檔案" + (f"；錯誤：{str(r.get('error'))[:200]}" if r.get("error") else ""), flush=True)
        scorer.put(r)
    scorer.close()
    print(f"\n報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
