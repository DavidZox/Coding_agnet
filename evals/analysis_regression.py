"""數據分析 agent 的回歸測試：同一套數據＋ground truth，自動評分每一次分析的事實報告。
原本的產物（logs/analysis_jobs/<job>/ 的 job.json、report.md、workers/*.md、transcript）照舊產生、照舊保留，評分只讀不改。
評分標準在 analysis_regression_cases.json（ground truth 見 test_data/ground_truth/；這台的數據用 test_data/cases_5090.json）。

    # 跑分析再評分：每份數據 N 次；模型可以分角色指定
    python3 evals/analysis_regression.py --run --runs 3 [--model gemma4:26b] [--synthesizer deepseek-r1:8b] [--think-roles synthesizer] [--cases cmdvel,fault]
    # 只評分已經跑過的 job（不跑模型）
    python3 evals/analysis_regression.py --score 20261015_094317 20261015_094154
    python3 evals/analysis_regression.py --score-file test_data/repeat_runs.json

數據：cases 檔的 data_root（容器內路徑）＋實驗名稱；換機器時把 test_data/recordings/ 複製到那台的數據根目錄，或用 --data-root。
結果：evals/results/analysis_<時間>/scorecard.md、scorecard.json、runs.json（evals/results/ 不進 git）。

只評事實，全部由程式判，不需要人工判讀：
(a) 時間線：該有的事件（ground truth 的時間 ± 容許誤差、關鍵字）有沒有出現在報告的時間線；
(b) 用詞：摘要（報告裡唯一由模型寫的事實文字）有沒有寫原因、推測（_NOT_FACT_WORDS）或這份數據不該有的說法（forbid）；
(c) 時間有根據：摘要寫的每一個 +秒，都對得上報告裡程式整理的事實（時間線、各 Topic 的變化）；
沒有事件（steady）：每個 Topic 都是「沒有變化」，摘要也沒有寫不存在的事件。
同一份數據跑好幾次時另外列一致性：指派的 Topic 有幾種組合、同一個 Topic 的事實（類別、變化、到最後的值）有幾種。"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
CASES = os.path.join(HERE, "analysis_regression_cases.json")
JOBS = os.path.join(PROJECT, "logs", "analysis_jobs")
QUESTION = "這 {} 秒系統發生了什麼？有哪些狀態變化？"
COLUMNS = [("timeline", "(a) 時間線"), ("clean", "(b) 用詞"), ("grounded", "(c) 時間有根據"), ("no_event", "沒有事件")]
TOL = 0.35   # 摘要的時間跟事實的時間差多少以內算同一個（同 test_data/tools/fact_check.py）
_T = re.compile(r"\+\s?(\d{1,4}(?:\.\d+)?)\s?(?:s|秒)")

sys.path.insert(0, PROJECT)

_NEG = ("沒有", "未", "無", "不", "沒", "非", "如果", "若", "是否", "排除", "還是", "當")   # 「還是…中斷」「當…停止發布時」是假設
_TIMED_DELAY = re.compile(r"\d+(?:\.\d+)?\s*(?:s|秒)[^，。；]{0,4}延遲")


def said(text, word):
    """text 有沒有「肯定地」說 word：同一個子句裡（從前一個逗號、句號到這個字）有否定或假設（沒有、未、無、不、如果、是否…）的不算
    （實測：「沒有觸發保護或中斷」「這表示如果 /cmd_vel_raw 確實中斷，則…」都不是在說有中斷）。「re:」開頭的是正規表示式。"""
    hits = ([(m.start(), m.end()) for m in re.finditer(word[3:], text)] if word.startswith("re:") else
            [(i, i + len(word)) for i in range(len(text)) if text.startswith(word, i)])
    for i, e in hits:
        start = max(text.rfind(p, 0, i) for p in "，。；;,、\n")
        ends = [k for k in (text.find(p, i) for p in "，。；;,\n") if k >= 0]
        after = text[e:min(ends) if ends else len(text)]
        inside = word.startswith("re:") and any(n in text[i:e] for n in _NEG)   # 正規表示式比對到的範圍裡有否定（「系統並未自動恢復」）
        if not any(n in text[start + 1:i] for n in _NEG) and not inside and "還是" not in after:
            return True
    return False


def _num(t):
    m = re.search(r"[+-]?\d+(?:\.\d+)?", str(t or ""))
    return float(m.group()) if m else None


def fact_times(rep):
    """報告裡程式整理的事實的時間：時間線的每一列、各 Topic 的發布與變化裡寫到的 +秒。"""
    ts = [_num(r.get("time")) for r in rep.get("timeline") or [] if isinstance(r, dict)]
    for row in rep.get("topics") or []:
        for text in [row.get("publish")] + list(row.get("changes") or []):
            ts += [float(m.group(1)) for m in _T.finditer(str(text or ""))]
    return [t for t in ts if t is not None]


def score_job(job_id, case):
    """一個 job 對一個 case 評分 → {欄位: True/False/None, "why": {欄位: 沒過的原因}, …}。"""
    from agent_core.analysis_job import _not_fact_words
    d = os.path.join(JOBS, job_id)
    job = json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))
    rep = job.get("report") or {}
    text = str(rep.get("summary") or "")
    rows = [r for r in rep.get("timeline") or [] if isinstance(r, dict)]
    checks = job.get("checks") or []
    res = {"job": job_id, "case": case["id"], "status": job.get("status"), "seconds": job.get("seconds"), "calls": job.get("model_calls"),
           "models": job.get("models"), "topics": sorted(w["topic"] for w in job.get("workers") or []),
           "unresolved": len(rep.get("unresolved") or []), "asked": any(c.get("asked") for c in checks),
           "followups": [a["topic"] for c in checks for a in c.get("followups") or []], "why": {}}
    if job.get("status") != "done":
        res["why"]["status"] = job.get("error") or job.get("status")
        return res
    if case.get("timeline"):
        miss = []
        for ev in case["timeline"]:
            ok = any(_num(r.get("time")) is not None and abs(_num(r.get("time")) - ev["t"]) <= ev["tol"]
                     and any(k.lower() in f"{r.get('source')} {r.get('event')}".lower() for k in ev["any"]) for r in rows)
            if not ok:
                miss.append(f"+{ev['t']}s（{'／'.join(ev['any'][:3])}）")
        res["timeline"] = not miss
        if miss:
            res["why"]["timeline"] = "缺：" + "、".join(miss)
    quoted = " ".join(str(s.get("message") or "") for s in job.get("signals") or [])   # Log 原文照抄不算
    plain = _TIMED_DELAY.sub("", text)   # 「約 0.52s 延遲」是時間差，不是傳輸延遲的說法（第六輪人工複核）
    bad = [f"「{f}」" for f in case.get("forbid") or [] if said(plain, f)] + [f"「{w}」" for w in _not_fact_words(text, quoted)]
    res["clean"] = not bad
    if bad:
        res["why"]["clean"] = "摘要寫了" + "、".join(bad)
    ref = fact_times(rep) + [0.0, float(job.get("duration_sec") or 0)]
    loose = [m.group(0) for m in _T.finditer(text) if not any(abs(float(m.group(1)) - r) <= TOL for r in ref)]
    res["grounded"] = not loose
    if loose:
        res["why"]["grounded"] = "摘要的時間對不上事實：" + "、".join(loose[:4])
    if case.get("no_event") is not None:
        tags = {t for row in rep.get("topics") or [] for t in row.get("tags") or []}
        hit = [f for f in case["no_event"].get("forbid") or [] if said(text, f)]
        res["no_event"] = tags <= {"沒有變化"} and not hit
        if not res["no_event"]:
            res["why"]["no_event"] = "；".join(([f"量到 {'、'.join(sorted(tags - {'沒有變化'}))}"] if tags - {"沒有變化"} else [])
                                              + ([f"摘要寫了 {'、'.join(hit)}"] if hit else []))
    return res


def facts_signature(job_id):
    """同一個 Topic 的事實（類別、變化、到最後的值）：比較好幾次的結果是否一樣用。"""
    job = json.load(open(os.path.join(JOBS, job_id, "job.json"), encoding="utf-8"))
    return {r["topic"]: json.dumps([r.get("tags"), r.get("changes"), r.get("end")], ensure_ascii=False)
            for r in (job.get("report") or {}).get("topics") or []}


def consistency(results):
    """每份數據跑好幾次的一致性：指派的 Topic 組合有幾種；每次都量到的 Topic，事實有幾種寫法（程式整理的，應該只有一種）。"""
    out = {}
    for cid in dict.fromkeys(r["case"] for r in results):
        rs = [r for r in results if r["case"] == cid and r.get("status") == "done"]
        if len(rs) < 2:
            continue
        sigs = [facts_signature(r["job"]) for r in rs]
        common = set.intersection(*(set(s) for s in sigs))
        out[cid] = {"runs": len(rs), "topic_sets": len({tuple(r["topics"]) for r in rs}),
                    "fact_variants": {t: len({s[t] for s in sigs}) for t in sorted(common)}}
    return out


def case_of(job_id, cases):
    job = json.load(open(os.path.join(JOBS, job_id, "job.json"), encoding="utf-8"))
    label = job.get("data_label") or os.path.basename(str(job.get("data") or "").rstrip("/"))
    return next((c for c in cases if c["data"] == label), None)


def run_cases(cases, args, root):
    from agent_core.agent import SkillAgent
    os.chdir(PROJECT)
    agent = SkillAgent(model=args.model or "gemma4:e4b")
    agent.target_container = args.container
    for role in ("orchestrator", "worker", "synthesizer"):   # 只改這次執行的設定（不寫回 logs/analysis_settings.json）
        m = getattr(args, role) or args.model
        if m:
            agent.analysis_cfg[role] = m
    for role in filter(None, args.think_roles.split(",")):   # 這些角色開 thinking（模型支援才會真的開）
        agent.analysis_cfg[f"{role.strip()}_think"] = True
    for item in args.ctx:   # 角色的上下文長度（例如 synthesizer=12288：8 GB 顯卡上讓 deepseek-r1:8b 大部分放進 GPU）
        role, _, n = item.partition("=")
        agent.analysis_cfg[f"{role.strip()}_ctx"] = int(n)
    if args.rounds:
        agent.analysis_cfg["rounds"] = args.rounds
    if args.workers:
        agent.analysis_cfg["max_workers"] = args.workers
    runs = []
    for case in cases:
        for i in range(args.runs):
            t0 = time.time()
            agent.analysis_run(f'--data {root.rstrip("/")}/{case["data"]} "{QUESTION.format(case["seconds"])}"')
            jid = (agent.analysis_last or {}).get("id")
            runs.append({"case": case["id"], "data": case["data"], "run": i + 1, "job": jid, "seconds": round(time.time() - t0, 1)})
            print(f"{case['id']} #{i + 1}: job {jid}（{time.time() - t0:.0f} 秒）", flush=True)
    return runs


def mark(v):
    return "—" if v is None else ("✅" if v else "❌")


def write_scorecard(results, out_dir, title):
    os.makedirs(out_dir, exist_ok=True)
    used = [k for k, _ in COLUMNS if any(r.get(k) is not None for r in results)]
    cons = consistency(results)
    lines = [f"# {title}", "", f"產生時間：{time.strftime('%Y-%m-%d %H:%M:%S')}", "",
             "## 各數據的通過數", "", "| 數據 | 次數 | " + " | ".join(lab for k, lab in COLUMNS if k in used)
             + " | 平均秒數 | 問了要不要補量 | 補量 | Topic 組合 | 事實不一致的 Topic |", "|---|---|" + "---|" * len(used) + "---|---|---|---|---|"]
    for cid in dict.fromkeys(r["case"] for r in results):
        rs = [r for r in results if r["case"] == cid]
        cells = []
        for k in used:
            vals = [r.get(k) for r in rs if r.get(k) is not None]
            cells.append(f"{sum(vals)}/{len(vals)}" if vals else "—")
        secs = [r["seconds"] for r in rs if r.get("seconds")]
        c = cons.get(cid) or {}
        uneven = [t for t, n in (c.get("fact_variants") or {}).items() if n > 1]
        lines.append(f"| {cid} | {len(rs)} | " + " | ".join(cells)
                     + f" | {sum(secs) / len(secs):.1f} | {sum(1 for r in rs if r['asked'])} | {sum(len(r['followups']) for r in rs)} | "
                     + f"{c.get('topic_sets', '—')} | {'、'.join(uneven) or '—'} |")
    tot = {k: [r.get(k) for r in results if r.get(k) is not None] for k in used}
    lines.append("| **合計** | " + str(len(results)) + " | " + " | ".join(f"**{sum(v)}/{len(v)}**" for v in tot.values()) + " | | | | | |")
    lines += ["", "## 每一次", "", "| 數據 | job | 秒 | " + " | ".join(lab for k, lab in COLUMNS if k in used) + " | 補量 | 未修正 | 沒過的原因 |",
              "|---|---|---|" + "---|" * len(used) + "---|---|---|"]
    for r in results:
        why = "；".join(f"{k}：{v}" for k, v in r["why"].items())
        lines.append(f"| {r['case']} | {r['job']} | {r.get('seconds')} | " + " | ".join(mark(r.get(k)) for k in used)
                     + f" | {'、'.join(r['followups'])} | {r['unresolved'] or ''} | {why} |")
    md = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, "scorecard.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(out_dir, "scorecard.json"), "w", encoding="utf-8") as f:
        json.dump({"results": results, "consistency": cons}, f, ensure_ascii=False, indent=1)
    return md


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--run", action="store_true", help="跑分析再評分")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--cases", default="", help="只跑這些 case（逗號分隔），省略＝全部")
    p.add_argument("--model", default="", help="三個角色都用這個模型")
    p.add_argument("--orchestrator", default="")
    p.add_argument("--worker", default="")
    p.add_argument("--synthesizer", default="")
    p.add_argument("--think-roles", default="", help="開 thinking 的角色（逗號分隔，例如 synthesizer 或 orchestrator,synthesizer）")
    p.add_argument("--ctx", nargs="*", default=[], help="角色的上下文長度，例如 synthesizer=12288（省略＝NUM_CTX）")
    p.add_argument("--rounds", type=int, default=0, help="最多幾輪（1＝不補量、2＝可以補量一輪；省略＝照設定）")
    p.add_argument("--workers", type=int, default=0, help="worker 上限（省略＝照設定）")
    p.add_argument("--container", default="ros2_web_container")
    p.add_argument("--data-root", default="")
    p.add_argument("--score", nargs="*", default=None, help="只評分這些 job 編號")
    p.add_argument("--score-file", default="", help="只評分 runs.json／repeat_runs.json 裡的 job")
    p.add_argument("--title", default="")
    p.add_argument("--out", default="")
    args = p.parse_args()
    spec = json.load(open(CASES, encoding="utf-8"))
    cases = spec["cases"]
    if args.cases:
        want = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in want]
    out_dir = args.out or os.path.join(HERE, "results", "analysis_" + time.strftime("%Y%m%d_%H%M%S"))
    if args.run:
        runs = run_cases(cases, args, args.data_root or spec["data_root"])
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "runs.json"), "w", encoding="utf-8") as f:
            json.dump(runs, f, ensure_ascii=False, indent=1)
        jobs = [r["job"] for r in runs if r["job"]]
    elif args.score_file:
        jobs = [r["job"] for r in json.load(open(args.score_file, encoding="utf-8")) if r.get("job")]
    elif args.score is not None:
        jobs = args.score
    else:
        p.error("要 --run、--score 或 --score-file 其中一個")
    results = []
    for jid in jobs:
        case = case_of(jid, spec["cases"])
        if case is None:
            print(f"（{jid} 的數據不在 cases 裡，略過）")
            continue
        results.append(score_job(jid, case))
    print(write_scorecard(results, out_dir, args.title or "數據分析回歸測試（事實報告）"))
    print(f"→ {out_dir}/scorecard.md")


if __name__ == "__main__":
    main()
