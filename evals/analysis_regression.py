"""數據解析 agent 的回歸測試：同一套數據＋ground truth，自動評分每一次分析的報告。
這是另一個做回歸的方法——原本的產物（logs/analysis_jobs/<job>/ 的 job.json、report.md、workers/*.md、transcript）照舊產生、
照舊保留，評分只讀不改。評分標準在 analysis_regression_cases.json（ground truth 見 test_data/ground_truth/）。

    # 跑分析再評分：每份數據 N 次；模型可以分角色指定（換到 DGX Spark／5090 跑 26b 時用同一套）
    python3 evals/analysis_regression.py --run --runs 3 [--model gemma4:26b] [--synthesizer deepseek-r1:8b] [--think-roles synthesizer] [--cases cmdvel,fault]
    # 只評分已經跑過的 job（不跑模型）
    python3 evals/analysis_regression.py --score 20261015_094317 20261015_094154
    python3 evals/analysis_regression.py --score-file test_data/repeat_runs.json

數據：cases 檔的 data_root（容器內路徑）＋實驗名稱；換機器時把 test_data/recordings/ 複製到那台的數據根目錄，或用 --data-root。
結果：evals/results/analysis_<時間>/scorecard.md、scorecard.json、runs.json（evals/results/ 不進 git）。

評分是關鍵字與時間的比對，不是人工判讀：抓得到「時間線缺了哪個事件」「根因拿背景條件當原因」「說成間歇性」這類錯，
措辭換了的對錯仍要人看報告（scorecard 列出每一項沒過的原因，方便對照）。"""
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
QUESTION = "這 {} 秒系統發生了什麼？有沒有異常或狀態變化？如果有，根因是什麼？"
COLUMNS = [("timeline", "(a) 時間線"), ("cause", "(b) 根因"), ("clean", "(c) 沒有錯誤說法"), ("character", "(d) 定性"),
           ("upstream", "上游"), ("slice", "切片"), ("no_event", "沒有事件")]
_PROGRAM_NOTE = re.compile(r"（程式(?:更正|檢查|判斷)：[^）]*）")

sys.path.insert(0, PROJECT)


def model_text(report):
    """結論＋根因＋因果鏈裡模型自己寫的部分（拿掉程式附的更正、檢查說明）。第八輪起因果推論把細節（代碼、L#、源碼位置）寫在因果鏈，
    結論與根因比較精簡（實測 long 的 SAFETY_COMMAND_TIMEOUT、lifecycle 的初始化都只在因果鏈裡）；因果鏈也是報告的根因推理，一起評。"""
    chain = "\n".join(str(x.get("event") or "") for x in report.get("chain") or [] if isinstance(x, dict))
    return _PROGRAM_NOTE.sub("", f"{report.get('conclusion') or ''}\n{report.get('root_cause') or ''}\n{chain}")


_NEG = ("沒有", "未", "無", "不", "沒", "非", "如果", "若", "是否", "排除", "還是", "當")   # 「還是…中斷」「當…停止發布時」是假設


_TIMED_DELAY = re.compile(r"\d+(?:\.\d+)?\s*(?:s|秒)[^，。；]{0,4}延遲")


def _has(text, k):
    """關鍵字比對；「re:」開頭的是正規表示式（例如 INITIALIZING 不算 MON_INITIALIZING 裡的）。"""
    return bool(re.search(k[3:], text)) if k.startswith("re:") else k in text


def said(text, word):
    """text 有沒有「肯定地」說 word：同一個子句裡（從前一個逗號、句號到這個字）有否定或假設（沒有、未、無、不、如果、是否…）的不算
    （實測：「沒有觸發保護或中斷」「這表示如果 /cmd_vel_raw 確實中斷，則…」都不是在說有中斷）。"""
    hits = ([(m.start(), m.end()) for m in re.finditer(word[3:], text)] if word.startswith("re:") else
            [(i, i + len(word)) for i in range(len(text)) if text.startswith(word, i)])
    for i, e in hits:
        start = max(text.rfind(p, 0, i) for p in "，。；;,、\n")
        ends = [k for k in (text.find(p, i) for p in "，。；;,\n") if k >= 0]
        after = text[e:min(ends) if ends else len(text)]
        inside = word.startswith("re:") and any(n in text[i:e] for n in _NEG)   # 正規表示式比對到的範圍裡有否定（「系統並未自動恢復」）
        if not any(n in text[start + 1:i] for n in _NEG) and not inside and "還是" not in after:   # 「（是正常結束還是意外中斷）無法判定」是假設
            return True
    return False


def _num(t):
    m = re.search(r"[+-]?\d+(?:\.\d+)?", str(t or ""))
    return float(m.group()) if m else None


def score_job(job_id, case):
    """一個 job 對一個 case 評分 → {欄位: True/False/None, "why": {欄位: 沒過的原因}, …}。"""
    from agent_core.analysis_job import _relies_on
    d = os.path.join(JOBS, job_id)
    job = json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))
    rep = job.get("report") or {}
    text = model_text(rep)
    rows = [r for r in rep.get("timeline") or [] if isinstance(r, dict)]
    res = {"job": job_id, "case": case["id"], "status": job.get("status"), "confidence": rep.get("confidence"),
           "seconds": job.get("seconds"), "calls": job.get("model_calls"), "models": job.get("models"),
           "corrected": bool(job.get("corrections")), "why": {}}
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
    relied = [c for c in case.get("not_cause") or [] if _relies_on(text, c)]
    if case.get("cause"):
        groups = case["cause"].get("all") or []
        lacking = [g for g in groups if not any(k.lower() in text.lower() for k in g)]
        hedged = [h for h in case["cause"].get("hedge") or [] if h in text]
        res["cause"] = not lacking and not hedged and not relied
        why = ([f"沒提到 {'／'.join(g[:3])}" for g in lacking] + [f"保留語氣「{h}」" for h in hedged]
               + [f"拿 {c} 當原因" for c in relied])
        if why:
            res["why"]["cause"] = "；".join(why)
    if case.get("forbid") is not None or case.get("not_cause"):
        plain = _TIMED_DELAY.sub("", text)   # 「約 0.52s 延遲」是逾時判斷的時間差，不是傳輸延遲的說法（第六輪人工複核）
        bad = [f for f in case.get("forbid") or [] if said(plain, f)]
        res["clean"] = not bad and not relied
        why = [f"「{b}」" for b in bad] + [f"拿 {c} 當原因" for c in relied]
        if why:
            res["why"]["clean"] = "、".join(why)
    if case.get("character"):
        wrong = [w for w in case.get("character_forbid") or [] if said(text, w)]   # 只根據事實的定性：肯定地說「異常」「故障」就不算
        res["character"] = any(_has(text, k) for k in case["character"]) and not wrong
        if not res["character"]:
            res["why"]["character"] = ("定性成「" + "、".join(wrong) + "」" if wrong else
                                       "沒有「" + "／".join(case["character"][:4]) + "」這類定性")
    if case.get("upstream"):   # 追到上游：寫在尚未確認也算（「發布者 system_health_monitor 為什麼停，看不出來」＝推到節點、原因照實說）
        up = (text + "\n" + "\n".join(str(u) for u in rep.get("unknowns") or [])).lower()
        res["upstream"] = any(k.lower() in up for k in case["upstream"])
        if not res["upstream"]:
            res["why"]["upstream"] = "沒有追到上游（共同的發布者／診斷彙整）"
    if case.get("slice"):
        slices = job.get("slices") or {}
        whole = job.get("data_messages") or 0
        if not whole:   # 較早的 job 沒有存：從切片的進度訊息讀「原本整份 N 則」
            for ln in open(os.path.join(d, "events.jsonl"), encoding="utf-8"):
                m = re.search(r"原本整份 (\d+) 則", ln)
                if m:
                    whole = int(m.group(1))
        sliced = sum((v.get("messages") or 0) + (v.get("state_messages") or 0) for v in slices.values())
        readers = []
        for w in job.get("workers") or []:
            path = os.path.join(d, w.get("file") or "")
            readers.append(os.path.exists(path) and "\ndata_slices:" in open(path, encoding="utf-8").read())
        ratio = sliced / whole if whole else 1.0
        res["slice"] = bool(slices) and all(readers) and ratio <= case["slice"]["max_ratio"]
        res["slice_ratio"] = round(ratio, 3)
        if not res["slice"]:
            res["why"]["slice"] = (f"切片 {len(slices)} 個、讀切片的 worker {sum(readers)}/{len(readers)}、"
                                   f"切片訊息占整份 {ratio:.0%}")
    if case.get("no_event"):
        ne = case["no_event"]
        hit = [f for f in ne.get("forbid") or [] if said(text, f)]
        res["no_event"] = any(k in text for k in ne["any"]) and not hit
        if not res["no_event"]:
            res["why"]["no_event"] = "沒有說沒有異常" if not hit else "說了不存在的事件：" + "、".join(hit)
    return res


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
    if args.slice in ("on", "off"):
        agent.analysis_cfg["slice"] = args.slice == "on"
    if args.source is not None:
        agent.analysis_cfg["source_root"] = "" if args.source == "-" else args.source
    if args.hints in ("on", "off"):
        agent.analysis_cfg["program_hints"] = args.hints == "on"
    if args.rounds:
        agent.analysis_cfg["rounds"] = args.rounds
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
    head = "| 數據 | job | 秒 | 信心 | " + " | ".join(lab for k, lab in COLUMNS if k in used) + " | 程式更正 | 沒過的原因 |"
    lines = [f"# {title}", "", f"產生時間：{time.strftime('%Y-%m-%d %H:%M:%S')}；評分標準：evals/analysis_regression_cases.json", "",
             "## 各數據的通過數", "", "| 數據 | 次數 | " + " | ".join(lab for k, lab in COLUMNS if k in used) + " |",
             "|---|---|" + "---|" * len(used)]
    for cid in dict.fromkeys(r["case"] for r in results):
        rs = [r for r in results if r["case"] == cid]
        cells = []
        for k in used:
            vals = [r.get(k) for r in rs if r.get(k) is not None]
            cells.append(f"{sum(vals)}/{len(vals)}" if vals else "—")
        lines.append(f"| {cid} | {len(rs)} | " + " | ".join(cells) + " |")
    lines += ["", "## 每一次", "", head, "|---|---|---|---|" + "---|" * len(used) + "---|---|"]
    for r in results:
        why = "；".join(f"{k}：{v}" for k, v in r["why"].items())
        lines.append(f"| {r['case']} | {r['job']} | {r.get('seconds')} | {r.get('confidence')} | "
                     + " | ".join(mark(r.get(k)) for k in used) + f" | {'有' if r.get('corrected') else ''} | {why} |")
    md = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, "scorecard.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(out_dir, "scorecard.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
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
    p.add_argument("--slice", default="", choices=["", "on", "off"])
    p.add_argument("--source", default=None, help="源碼目錄（受測系統的 ROS 2 工作區 src；- ＝不用；省略＝照設定）")
    p.add_argument("--hints", default="", choices=["", "on", "off"], help="程式的推理提示（off：只給數據與源碼的事實）")
    p.add_argument("--rounds", type=int, default=0, help="補分析最多幾輪（有源碼脈絡時；1＝不補；省略＝照設定）")
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
    print(write_scorecard(results, out_dir, args.title or "數據解析回歸測試"))
    print(f"→ {out_dir}/scorecard.md")


if __name__ == "__main__":
    main()
