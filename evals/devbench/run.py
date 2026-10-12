"""DevBench 實作任務的評測：每個 repo 交給 coding orchestrator 從規格文件寫出整個專案，再用官方的單元／驗收測試計分。

    python3 evals/devbench/run.py                                   # gemma4:e4b × 12 個 repo
    python3 evals/devbench/run.py --model gemma4:26b
    python3 evals/devbench/run.py --model gemma4:e4b --planner gemma4:26b    # 規劃 26b、worker e4b
    python3 evals/devbench/run.py --only readtime,area_calculation --keep
    python3 evals/devbench/run.py --lang cpp

先跑一次 prepare.py（下載資料、建立 .venv、檢查 gtest）。每個 repo 都在臨時目錄複製一份 harness（agent_core、skills_system、
coding_agents…）＋工作區（規格文件與 required_files）來跑，不碰正式的 logs/。結果在 evals/results/<時間>_devbench_<模型>/：
report.md（彙整表）、runs.jsonl（每個 repo 的完整紀錄：計畫、每一項的嘗試與步數、事件流、測試輸出）、workspaces/<repo>/
（agent 寫出來的程式碼，可以直接看）。
分數：單元測試與驗收測試的通過率（DevBench 實作任務的指標）；另外列不加權平均與依程式碼行數加權的平均（論文用後者）。
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
from evals.devbench import evaluate as ev  # noqa: E402
from evals.devbench.repos import PAPER_IMPLEMENTATION, REPOS  # noqa: E402

COPY_ITEMS = ["agent_core", "skills_system", "coding_agents", "context_modes", "evals", "AGENT.md", "Memory.md"]
_SKIP_SNAPSHOT = {"build", "obj", "__pycache__", ".pytest_cache", "outputs", "test_outputs"}


def make_copy():
    tmp = tempfile.mkdtemp(prefix="devbench_run_")
    for item in COPY_ITEMS:
        src = os.path.join(PROJECT, item)
        if os.path.isdir(src):
            def ignore(d, names):
                skip = {n for n in names if n in ("__pycache__", "results", "drafts")}
                if os.path.realpath(d) == os.path.realpath(HERE):
                    skip |= {"data", ".venv"}
                return skip
            shutil.copytree(src, os.path.join(tmp, item), ignore=ignore)
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(tmp, item))
    os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
    return tmp


def snapshot(ws, dst):
    """agent 寫出來的程式（不含建置產物與官方測試）存到結果目錄。超過 5 MB 的檔案不存（實測：chakin 的程式在測試時
    真的從網路下載了 268 MB 的詞向量檔；g++ 編譯標頭留下 17 MB 的 .gch）。"""
    def ignore(d, names):
        return {n for n in names if n in _SKIP_SNAPSHOT or n.endswith((".o", ".gcda", ".gcno", ".gcov", ".a", ".so", ".gch", ".pch"))
                or (os.path.isfile(os.path.join(d, n)) and os.access(os.path.join(d, n), os.X_OK) and "." not in n)
                or (os.path.isfile(os.path.join(d, n)) and os.path.getsize(os.path.join(d, n)) > 5 * 1024 * 1024)}
    shutil.copytree(ws, dst, ignore=ignore, dirs_exist_ok=True)


def run_repo(name, args, out_dir):
    tmp = make_copy()
    ws = os.path.join(tmp, "workspace")
    ev.make_workspace(name, ws, args.visible_tests)
    task_file = os.path.join(tmp, "task.txt")
    with open(task_file, "w", encoding="utf-8") as f:
        f.write(ev.task_text(name, args.visible_tests))
    out_path = os.path.join(tmp, "job.json")
    env = dict(os.environ, EVAL_MODEL=args.model, EVAL_PLANNER_MODEL=args.planner or args.model, PYTHONPATH=tmp,
               PYTHONDONTWRITEBYTECODE="1", EVAL_JOB_TIMEOUT=str(args.timeout - 120), CODE_PYTHON=ev.VENV_PY)
    t0 = time.time()
    result = {"repo": name, "lang": REPOS[name]["lang"]}
    try:
        proc = subprocess.run([sys.executable, os.path.join(tmp, "evals", "devbench", "job.py"), ws, task_file, out_path],
                              cwd=tmp, env=env, capture_output=True, text=True, timeout=args.timeout)
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                result.update(json.load(f))
        else:
            result["error"] = (proc.stderr or proc.stdout)[-3000:]
    except subprocess.TimeoutExpired:
        result["error"] = f"逾時（{args.timeout} 秒）"
    result["wall_seconds"] = round(time.time() - t0, 1)
    snapshot(ws, os.path.join(out_dir, "workspaces", name))
    result["score"] = ev.evaluate(name, ws)
    if args.keep:
        result["tmp_dir"] = tmp
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def _rates(results, key, weighted):
    num = den = 0.0
    for r in results:
        s = r["score"]
        rate = s[key] / s[f"{key}_total"] if s[f"{key}_total"] else 0.0
        w = REPOS[r["repo"]]["lines"] if weighted else 1
        num += rate * w
        den += w
    return 100.0 * num / den if den else 0.0


def write_report(path, results, args, title=None):
    lines = [title or f"# DevBench 實作任務：worker {args.model}、規劃 {args.planner or args.model}", "",
             f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；{len(results)} 個 repo；每個 repo 從規格文件（PRD、UML、架構設計）寫出整個專案，"
             "用官方的單元測試與驗收測試計分（Python：pytest；C++：GoogleTest＋驗收腳本）。"
             + (("**官方測試的內容放在提示裡（看得到、不能執行）**。" if getattr(args, "bare", False)
                 else "**官方測試放在工作區、agent 可以跑**（DevBench 基準 agent 的設定）。") if args.visible_tests
                else "agent 看不到官方測試。"), ""]
    for title, group in (("全部", results), ("Python", [r for r in results if r["lang"] == "python"]),
                         ("C++", [r for r in results if r["lang"] == "cpp"])):
        if not group:
            continue
        u = sum(r["score"]["unit"] for r in group)
        ut = sum(r["score"]["unit_total"] for r in group)
        a = sum(r["score"]["acceptance"] for r in group)
        at = sum(r["score"]["acceptance_total"] for r in group)
        lines.append(f"- **{title}**（{len(group)} 個 repo）：單元測試 {u}/{ut}（{100 * u / max(1, ut):.1f}%）、驗收測試 {a}/{at}"
                     f"（{100 * a / max(1, at):.1f}%）；每個 repo 通過率的平均：單元 {_rates(group, 'unit', False):.1f}%、"
                     f"驗收 {_rates(group, 'acceptance', False):.1f}%；依程式碼行數加權：單元 {_rates(group, 'unit', True):.1f}%、"
                     f"驗收 {_rates(group, 'acceptance', True):.1f}%")
    lines += ["", "| repo | 語言 | 單元測試 | 驗收測試 | job 狀態 | 完成項目 | 分鐘 | 模型呼叫 |", "|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["score"]
        items = r.get("items") or []
        done = sum(1 for it in items if it["status"] == "done")
        lines.append(f"| {r['repo']} | {r['lang']} | {s['unit']}/{s['unit_total']} | {s['acceptance']}/{s['acceptance_total']} | "
                     f"{r.get('job_status', '?')} | {done}/{len(items)} | {(r.get('seconds') or r['wall_seconds']) / 60:.1f} | "
                     f"{r.get('model_calls') or '—'} |")
    lines += ["", "參考（DevEval README，全部 22 個 repo、四種語言、依程式碼行數加權，agent 也不同，只能當量級參考）："
              + "；".join(f"{m} 驗收 {a}%、單元 {u}%" for m, (a, u) in PAPER_IMPLEMENTATION.items()), "", "## 每個 repo"]
    for r in results:
        s = r["score"]
        lines.append(f"\n### {r['repo']}：單元 {s['unit']}/{s['unit_total']}、驗收 {s['acceptance']}/{s['acceptance_total']}"
                     f"（{r.get('job_status', '?')}，{(r.get('seconds') or r['wall_seconds']) / 60:.1f} 分鐘）")
        if r.get("error"):
            lines.append(f"- 錯誤：{str(r['error'])[:500]}")
        if r.get("final_head"):
            lines.append(f"- 整體驗證（agent 自己的）：{r['final_head'][:300]}")
        for it in r.get("items") or []:
            lines.append(f"  - {it['n']}. {it['status']}（{it['attempts']} 次、{it['steps']} 步）{it['title']}；檔案 {it['files']}")
        for key, label in (("unit_tail", "單元測試輸出（尾巴）"), ("acceptance_tail", "驗收測試輸出（尾巴）")):
            tail = "\n".join(s[key].strip().splitlines()[-8:])
            lines.append(f"- {label}：\n```\n{tail}\n```")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:e4b")
    ap.add_argument("--planner", default=None)
    ap.add_argument("--only", default="")
    ap.add_argument("--lang", choices=["python", "cpp", "all"], default="all")
    ap.add_argument("--timeout", type=int, default=3600, help="每個 repo 的上限（秒）")
    ap.add_argument("--keep", action="store_true", help="保留每個 repo 的臨時目錄（看 worker 的完整紀錄）")
    ap.add_argument("--visible-tests", action="store_true",
                    help="官方測試也放進工作區、agent 可以跑（DevBench 基準 agent 的設定）；預設 agent 看不到官方測試")
    args = ap.parse_args()
    if not os.path.exists(ev.VENV_PY) or not os.path.isdir(ev.DATA):
        raise SystemExit("先執行 python3 evals/devbench/prepare.py（下載資料、建立 .venv、檢查 gtest）")
    only = [n.strip() for n in args.only.split(",") if n.strip()]
    names = [n for n in (only or list(REPOS)) if args.lang == "all" or REPOS[n]["lang"] == args.lang]
    tag = args.model.replace(":", "-") + (f"_plan-{args.planner.replace(':', '-')}" if args.planner else "") \
        + ("_visible-tests" if args.visible_tests else "")
    out_dir = os.path.join(PROJECT, "evals", "results", time.strftime("%Y%m%d_%H%M%S") + f"_devbench_{tag}")
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for name in names:
        print(f"▶ {name}（{REPOS[name]['lang']}，worker {args.model}）…", flush=True)
        r = run_repo(name, args, out_dir)
        results.append(r)
        s = r["score"]
        print(f"  單元 {s['unit']}/{s['unit_total']}、驗收 {s['acceptance']}/{s['acceptance_total']}；job {r.get('job_status', '?')}，"
              f"{(r.get('seconds') or r['wall_seconds']) / 60:.1f} 分鐘，模型呼叫 {r.get('model_calls')} 次"
              + (f"；錯誤：{str(r.get('error'))[:200]}" if r.get("error") else ""), flush=True)
        with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        write_report(os.path.join(out_dir, "report.md"), results, args)
    print(f"\n報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
