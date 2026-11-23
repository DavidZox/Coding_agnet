"""真實專案評測：五種題目各 5 題，另外各 1 題當保留組；答案由程式從固定版本的快照算
（evals/repo/questions.py → answers.json）。

    python3 evals/repo/run.py --model gemma4:26b                # 主要的 25 題
    python3 evals/repo/run.py --model gemma4:e4b --set all      # 加上保留組（30 題）
    python3 evals/repo/run.py --only cnt_rmf_publishers,py_fleet_msg --tag try1
    python3 evals/repo/run.py --rescore evals/results/<結果目錄>   # 不跑模型：核對改了之後，用存下來的回覆重新計分

每一題：快照解開一次（唯讀，所有題目共用）→ 在臨時的 harness 副本裡跑主對話（evals/ops/worker.py：比照 CLI 的自動模式，
工作目錄是快照的 amr_base/src）→ checks.py 對最後的回覆計分。題目都是唯讀的：確認關卡一律拒絕（碰到就算錯），Docker 與
調度系統的位址指到不存在的地方，模型誤用那些工具也碰不到主機上真的容器與調度系統。
結果在 evals/results/<時間>_repo_<模型>[_<set>][_<tag>]/：runs.jsonl、report.md、logs/<題目>/（提煉的切段與模型呼叫、工具的完整原文）。
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
sys.path.insert(0, HERE)
import checks      # noqa: E402
import questions   # noqa: E402
import snapshot    # noqa: E402

COPY_ITEMS = ["agent_core", "skills_system", "prompts", "evals"]
UNREACHABLE = {"DOCKER_HOST": "tcp://127.0.0.1:9", "RMF_WEB_CONSOLE_URL": "http://127.0.0.1:9",
               "RMF_MANUAL_TRIGGER_URL": "http://127.0.0.1:9"}


def make_copy():
    tmp = tempfile.mkdtemp(prefix="repo_run_")
    ignore = shutil.ignore_patterns("__pycache__", "results", "drafts", "dataset")
    for item in COPY_ITEMS:
        shutil.copytree(os.path.join(PROJECT, item), os.path.join(tmp, item), ignore=ignore)
    os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
    return tmp


def worker_env(model, tmp, src_root):
    """worker 的環境變數：外部系統的位址都指到不存在的地方；HOME 指到 harness 副本旁邊的空目錄（run_one 建、跑完刪）——照抄主機的 HOME 時
    `cd ~` 會跑到真的家目錄（維運評測曾在那裡寫出檔案，待辦 4f ③）；不放在副本裡面，副本裡有題目與答案（scenario.json）。"""
    return dict(os.environ, EVAL_MODEL=model, PYTHONPATH=tmp, PYTHONDONTWRITEBYTECODE="1", OPS_FS_ROOT=src_root,
                HOME=tmp.rstrip(os.sep) + "_home", **UNREACHABLE)


def scenario(q):
    return {"id": q["id"], "turns": [{"user": q["question"]}], "guard": "deny"}


def run_one(q, args, src_root, out_dir):
    tmp = make_copy()
    env = worker_env(args.model, tmp, src_root)
    os.makedirs(env["HOME"], exist_ok=True)
    try:
        sc_path, out_path = os.path.join(tmp, "scenario.json"), os.path.join(tmp, "out.json")
        with open(sc_path, "w", encoding="utf-8") as f:
            json.dump(scenario(q), f, ensure_ascii=False)
        r = {"id": q["id"], "kind": q["kind"], "set": q["set"], "package": q["package"], "model": args.model}
        t0 = time.time()
        out = {}
        try:
            proc = subprocess.run([sys.executable, os.path.join(tmp, "evals", "ops", "worker.py"), sc_path, out_path],
                                  cwd=tmp, env=env, capture_output=True, text=True, timeout=args.timeout)
            if os.path.exists(out_path):
                with open(out_path, encoding="utf-8") as f:
                    out = json.load(f)
            else:
                r["error"] = (proc.stderr or proc.stdout)[-3000:]
        except subprocess.TimeoutExpired:
            r["error"] = f"逾時（{args.timeout} 秒）"
        r["wall_seconds"] = round(time.time() - t0, 1)
        r["reply"] = checks.final_reply(out)
        r["score"] = checks.score(q, r["reply"], out.get("guards", 0))
        turn = (out.get("turns") or [{}])[-1]
        r.update(tool_calls=out.get("tool_calls") or [], model_calls=out.get("model_calls"), guards=out.get("guards", 0),
                 hit_step_limit=turn.get("hit_step_limit", False), stuck=turn.get("stuck"))
        # 依報告回答（4-2）：每一次的 answers 與沒過核對的項目、交回修了幾次（看核對擋了什麼、修好了沒）
        r["answers"] = [{"answers": st.get("answers"), "problems": st.get("answer_problems")} for st in turn.get("steps") or [] if "answers" in st]
        r["claim_nudges"] = turn.get("claim_nudges", 0)
        return r
    finally:
        if os.path.isdir(os.path.join(tmp, "logs")):
            shutil.copytree(os.path.join(tmp, "logs"), os.path.join(out_dir, "logs", q["id"]), dirs_exist_ok=True)
        if args.keep:
            print(f"  （保留）harness 副本 {tmp}、家目錄 {env['HOME']}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(env["HOME"], ignore_errors=True)


def write_report(path, results, model, note=""):
    lines = [f"# 真實專案評測：{model}", "",
             f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；快照 {snapshot.COMMIT[:8]}；{len(results)} 題" + (f"；{note}" if note else ""), ""]
    for qset in ("main", "holdout"):
        rs = [r for r in results if r["set"] == qset]
        if not rs:
            continue
        per = "、".join(f"{questions.KINDS[k]} {sum(r['score']['passed'] for r in rs if r['kind'] == k)}/{sum(1 for r in rs if r['kind'] == k)}"
                       for k in questions.KINDS if any(r["kind"] == k for r in rs))
        lines.append(f"- **{'主要' if qset == 'main' else '保留組'}**：通過 {sum(r['score']['passed'] for r in rs)}/{len(rs)}（{per}）")
    lines += ["", "| 題目 | 種類 | 組 | 結果 | 事實 | 沒對到的、禁止的 | 工具呼叫 | 模型呼叫 | 秒 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["score"]
        miss = [x["label"] for x in s["items"] if not x["ok"]] + [f"🚫{x}" for x in s["forbidden"]]
        note = "；".join(miss)[:160] + (f"｜{r['error'][-80:]}" if r.get("error") else "") + ("｜用完步數" if r.get("hit_step_limit") else "")
        lines.append(f"| {r['id']} | {r['kind']} | {r['set']} | {'✅' if s['passed'] else '❌'} | {s['checks_passed']}/{s['checks_total']} | "
                     f"{note} | {len(r['tool_calls'])} | {r.get('model_calls')} | {r['wall_seconds']} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def rescore(out_dir):
    """用 out_dir 存下來的回覆照現在的 answers.json 重新計分（回覆不變，只有核對改了），改寫 runs.jsonl 與 report.md。"""
    answers = {q["id"]: q for q in questions.load()["questions"]}
    path = os.path.join(out_dir, "runs.jsonl")
    with open(path, encoding="utf-8") as f:
        results = [json.loads(line) for line in f if line.strip()]
    for r in results:
        r["score"] = checks.score(answers[r["id"]], r["reply"], r.get("guards", 0))
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in results)
    model = results[0].get("model") if results else None
    if not model:        # 2026-11-18 以前的結果沒有存模型：從報表的標題讀
        with open(os.path.join(out_dir, "report.md"), encoding="utf-8") as f:
            model = f.readline().split("：", 1)[-1].strip()
    write_report(os.path.join(out_dir, "report.md"), results, model, note=f"{time.strftime('%Y-%m-%d %H:%M')} 照現在的核對重新計分")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--set", default="main", choices=["main", "holdout", "all"])
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--tag", default="")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--rescore", default="", help="不跑模型：用這個結果目錄存下來的回覆照現在的 answers.json 重新計分")
    args = ap.parse_args()
    if args.rescore:
        results = rescore(args.rescore)
        print(f"重新計分：{sum(r['score']['passed'] for r in results)}/{len(results)} 題通過\n報表：{os.path.join(args.rescore, 'report.md')}")
        return
    answers = questions.load()
    if answers["digest"] != snapshot.DIGEST:
        sys.exit("answers.json 不是這份快照算的（python3 evals/repo/questions.py --write）")
    qs = [q for q in answers["questions"] if (args.set == "all" or q["set"] == args.set) and (not args.only or q["id"] in args.only.split(","))]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(PROJECT, "evals", "results", f"{stamp}_repo_{args.model.replace(':', '-')}"
                           + ("" if args.set == "main" else f"_{args.set}") + (f"_{args.tag}" if args.tag else ""))
    os.makedirs(out_dir, exist_ok=True)
    snap_dir = tempfile.mkdtemp(prefix="repo_snapshot_")
    results = []
    try:
        src_root = snapshot.extract(snap_dir)
        print(f"真實專案評測：{len(qs)} 題 → {out_dir}", flush=True)
        for q in qs:
            print(f"▶ {q['id']}（{q['kind']}、{q['set']}）…", flush=True)
            r = run_one(q, args, src_root, out_dir)
            results.append(r)
            with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            write_report(os.path.join(out_dir, "report.md"), results, args.model)
            s = r["score"]
            print(f"  {'✅' if s['passed'] else '❌'} 事實 {s['checks_passed']}/{s['checks_total']}"
                  + (f"｜禁止：{s['forbidden']}" if s["forbidden"] else "")
                  + f"｜{len(r['tool_calls'])} 個工具呼叫、{r['wall_seconds']} 秒" + (f"｜{r['error'][-200:]}" if r.get("error") else ""), flush=True)
    finally:
        snapshot.remove(snap_dir)
    print(f"報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
