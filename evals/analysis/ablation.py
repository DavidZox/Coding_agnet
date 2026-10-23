#!/usr/bin/env python3
"""三個版本的比較：模型到底有沒有幫上忙。同一份數據、同一份程式量的事實，只換「重點」是誰寫的——
- P＝只有程式：照規則寫每個重要的時間點（Log 的則數與層級、每個事件的第一個變化）、到最後跟開頭不同的值、沒有變化的 Topic；
- S＝只呼叫一次模型：Synthesizer（沒有 Orchestrator、沒有 Worker；核對、交回、程式補寫照舊）；
- F＝現在的三個角色：已經跑過的 job（evals/analysis/regression.py 的 runs.json，每份數據取第一次）。
量的東西：
1. 句子的意思（agent_core/claims.py）：模型第一版的重點與說明有幾則跟事實對不上（交回之前）、交回之後還有幾則沒列；
2. 讀者答題：另一次模型呼叫只看主對話收到的報告（_report_for_main，跟使用者的問題無關的部分都一樣），回答從事實自動出的題目
   （到最後的值、有沒有回到開頭的值、什麼時候變的、有沒有變化、有沒有 ERROR 以上的 Log、什麼時候開始／停止發布），程式依事實評分；
3. 成本：模型呼叫次數、秒數；
4. 給人看的對照（rating/）：挑幾份數據，三個版本的重點並排、標籤打亂，對照表另外存（key.json）。

    python3 evals/analysis/ablation.py --runs-file evals/results/analysis_r12a_real/runs.json [--runs-file …] \\
        [--model gemma4:26b] [--reader gemma4:26b] [--rating lidar,overheat,…] --out evals/results/ablation_<名稱>
結果：<out>/ablation.md、ablation.json、questions.json（每一題、三個版本的答案與對錯）、rating/。"""
import argparse
import json
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT)
JOBS = os.path.join(PROJECT, "logs", "analysis_jobs")
MEANING = "照引用的事實改寫這一句"   # analysis_job._check_note 給「意思對不上」的問題接的字

READER_SYSTEM = ("你是讀數據分析報告的人。只根據使用者給的報告回答問題：不要用報告以外的知識、不要推測。報告沒有寫的，answer 寫「報告沒有寫」。\n"
                 "欄位：answer＝一兩句話的回答；value＝問的是值的時候，照報告寫那個值（只寫值本身，例如 ESTOP_LATCHED、0.1、True），其他題目留空字串；"
                 "time＝問的是時間的時候，寫距離數據開頭的秒數（例如 +16.53s），其他題目留空字串；yes_no＝是非題寫「是」或「否」，"
                 "報告沒有寫就寫「報告沒有寫」，不是是非題也寫「報告沒有寫」。所有文字用繁體中文。")
READER_SCHEMA = {"type": "object", "properties": {
    "answer": {"type": "string", "maxLength": 300}, "value": {"type": "string", "maxLength": 160}, "time": {"type": "string", "maxLength": 40},
    "yes_no": {"type": "string", "enum": ["是", "否", "報告沒有寫"]}}, "required": ["answer", "value", "time", "yes_no"]}
_TIME = re.compile(r"[+＋]?\s?(\d{1,4}(?:\.\d+)?)\s?(?:s|秒)")


# ---------------------------------------------------------------- P：只有程式
def _first_change(text):
    """事件的內容「k1：a → b；k2：c → d」→ 第一個變化與其他還有幾項。"""
    parts = [p for p in str(text).split("；") if p.strip()]
    return (parts[0] if parts else str(text)), max(0, len(parts) - 1)


def program_highlights(facts):
    """只有程式寫的重點（傳統的做法：規則）：每個重要的時間點一則——Log 的則數與層級、每個 Topic 的事件（開始／停止發布、中斷、
    第一個變化的項目，最多 3 個 Topic）；到最後跟開頭不同的值一則；反覆切換的 Topic、沒有變化的 Topic 各一則。"""
    from agent_core.analysis_job import _LEVEL_RANK, _moments
    ev, sig = facts["events"], facts["signals"]
    moments, flap = _moments(facts)
    out = []
    for m in moments:
        logs = [r for r in m["refs"] if r in sig]
        evs = [r for r in m["refs"] if r in ev]
        parts = []
        if logs:
            levels = {}
            for r in logs:
                levels[sig[r]["level"]] = levels.get(sig[r]["level"], 0) + 1
            order = sorted(levels.items(), key=lambda kv: -_LEVEL_RANK.get(kv[0], 1))
            parts.append(f"同一時間 {len(logs)} 則 Log（{'、'.join(f'{k} {v}' for k, v in order)}）")
        for r in evs[:3]:
            e = ev[r]
            first, more = _first_change(e["text"]) if e["kind"] == "change" else (e["text"].split("（")[0], 0)
            parts.append(f"{e['topic']} {first}" + (f"（另 {more} 項）" if more else ""))
        if len(evs) > 3:
            parts.append(f"另 {len(evs) - 3} 個事件")
        out.append({"refs": m["refs"][:10], "text": "；".join(parts)})
    for r in flap:
        out.append({"refs": [r["id"]], "text": f"{r['topic']} 反覆切換 {r['flap']} 次"})
    ends = [(r, x) for r in facts["topics"] for x in r["end"] if "（開頭 " in x]
    if ends:
        tids = list(dict.fromkeys(r["id"] for r, _ in ends))
        out.append({"refs": tids[:10], "text": "到數據結束時跟開頭不同：" + "；".join(f"{r['topic']} 的 {x}" for r, x in ends[:6])
                    + (f"…等 {len(ends)} 項" if len(ends) > 6 else "")})
    quiet = [r for r in facts["topics"] if not (r["events"] or "數值變動" in r["tags"])]
    if quiet:
        out.append({"refs": [r["id"] for r in quiet][:10], "text": "整段沒有變化：" + "、".join(r["topic"] for r in quiet[:8])
                    + ("…" if len(quiet) > 8 else "")})
    return out


def render(notes, facts):
    """重點 → 報告的樣子（同一刻其他的編號掛上、時間與引用的內容由程式列出，跟分析程式一樣）。"""
    from agent_core.analysis_job import _attach_moments, _moments, _render_note
    kept = _attach_moments(notes, _moments(facts)[0], facts)
    return sorted((_render_note(n, facts, details=True) for n in kept), key=lambda h: (h["t"] is None, h["t"] or 0))


# ---------------------------------------------------------------- 題目（依事實自動出，答案也是事實）
def make_questions(facts, limit=10):
    from agent_core.claims import _equal
    from agent_core.analysis_job import _LEVEL_RANK
    qs = []
    rows = [r for r in facts["topics"] if r.get("values")]
    states = [(r, k, v) for r in rows for k, v in r["values"].items()
              if v.get("varies") and not v.get("late") and not v.get("continuous") and v.get("changes") and not r.get("flap")]
    used = set()
    for r, k, v in states:   # 1. 到最後的值（跟開頭不同）：最多 2 題、不同的 Topic
        if r["id"] not in used and not _equal(v["last"], v["first"]) and sum(q["kind"] == "end" for q in qs) < 2:
            alt = [n for val, names in (r.get("aliases") or {}).items() if _equal(val, v["last"]) for n in names]   # 定義的常數名稱（OK＝0）也算對
            qs.append({"kind": "end", "type": "value", "q": f"到數據結束時，{r['topic']} 的 {k} 是什麼值？", "truth": v["last"], "alt": alt})
            used.add(r["id"])
    back = [(r, k, v) for r, k, v in states if _equal(v["last"], v["first"])]
    stay = [(r, k, v) for r, k, v in states if not _equal(v["last"], v["first"])]
    for pool, truth in ((back, True), (stay, False)):   # 2. 有沒有回到開頭的值：回到的、沒回到的各一題
        for r, k, v in pool:
            if r["id"] not in used:
                qs.append({"kind": "back", "type": "yesno", "truth": truth,
                           "q": f"到數據結束時，{r['topic']} 的 {k} 有沒有回到數據開頭時的值（{v['first']}）？"})
                used.add(r["id"])
                break
    for r, k, v in states:   # 3. 什麼時候變的：第一個狀態跳轉
        t, a, b = v["changes"][0]
        qs.append({"kind": "when", "type": "time", "truth": t, "q": f"{r['topic']} 的 {k} 什麼時候從 {a} 變成 {b}（第一次）？"})
        break
    changed = [r for r in facts["topics"] if r["events"]]
    quiet = [r for r in facts["topics"] if not (r["events"] or "數值變動" in r["tags"]) and "沒有訊息" not in r["tags"]]
    for pool, truth in ((changed[-1:], True), (quiet[:1], False)):   # 4. 有沒有變化：有事件的一個、沒有變化的一個
        for r in pool:
            qs.append({"kind": "changed", "type": "yesno", "truth": truth, "q": f"{r['topic']} 在這段數據裡有沒有任何變化（狀態、數值或發布）？"})
    errs = sorted((x for x in facts["logs"] if _LEVEL_RANK.get(x["level"], 1) >= 3), key=lambda x: x["t"])   # 5. ERROR 以上的 Log
    qs.append({"kind": "error_log", "type": "yesno", "truth": bool(errs), "q": "這段數據有沒有 ERROR（含）以上等級的 Log？"})
    if errs:
        qs.append({"kind": "error_node", "type": "value", "truth": errs[0]["node"], "q": "第一則 ERROR（含）以上等級的 Log 是哪個節點印的？"})
    for e in sorted(facts["events"].values(), key=lambda e: e["t"]):   # 6. 開始／停止發布的時間
        if e["kind"] in ("start", "stop"):
            word = "開始發布" if e["kind"] == "start" else "停止發布"
            qs.append({"kind": "publish", "type": "time", "truth": e["t"], "q": f"{e['topic']} 什麼時候{word}？"})
            break
    return qs[:limit]


def judge(q, ans):
    from agent_core.claims import same
    ans = ans or {}
    if q["type"] == "value":   # 讀者常附說明：「HARD_STOP（硬煞停）」——括號前的第一個詞、或包含正確的值（3 個字以上的文字）也算
        v = str(ans.get("value") or "").strip() or str(ans.get("answer") or "").strip()   # 讀者有時只寫在 answer
        first = re.split(r"[（(，,；;、\s]", v)[0] if v else ""
        truth = str(q["truth"])
        return bool(v) and (same(v, truth) or same(first, truth) or any(same(first, a) for a in q.get("alt") or []) or
                            (len(truth) >= 3 and not re.fullmatch(r"[0-9.+-]+", truth) and truth.lower() in v.lower()))
    if q["type"] == "time":
        for text in (ans.get("time"), ans.get("answer")):
            m = _TIME.search(str(text or "")) or re.fullmatch(r"\s*[+＋]?(\d{1,4}(?:\.\d+)?)\s*", str(text or ""))
            if m:
                return abs(float(m.group(1)) - float(q["truth"])) <= 0.35
        return False
    return ans.get("yes_no") == ("是" if q["truth"] else "否")


# ---------------------------------------------------------------- 執行
def first_pass_meaning(job):
    """job 第一版（交回之前）有幾則因為意思被交回、交回之後還有幾則沒列（重點＋worker 的說明）。"""
    sums, ws = job.get("summary_checks") or [], job.get("workers") or []
    first = sum(MEANING in x for c in sums for x in c.get("issues") or []) + sum(MEANING in x for w in ws for x in w.get("issues") or [])
    left = sum(MEANING in x for c in sums for x in c.get("left") or []) + sum(MEANING in x for w in ws for x in w.get("dropped") or [])
    return first, left


def run_single(agent, job, facts, out_dir):
    """S：只呼叫 Synthesizer（沒有 Orchestrator、沒有 Worker）。job 資料夾放在 <out>/single_jobs/（不進 logs/analysis_jobs）。"""
    sj = {"id": job["id"] + "_S", "question": job.get("question"), "data_label": job.get("data_label"), "duration_sec": job.get("duration_sec"),
          "workers": [], "plan": {"related": [], "assignments": []}, "model_calls": 0}
    t0 = time.time()
    summary = agent._analysis_summary(sj, 1, facts)
    return sj, summary, round(time.time() - t0, 1)


def ask(agent, model, report, q):
    res = agent._timed_chat("ablation_reader", model=model, format=READER_SCHEMA, options={"temperature": 0.2, "num_ctx": 32768, "num_predict": 600},
                            messages=[{"role": "system", "content": READER_SYSTEM},
                                      {"role": "user", "content": f"【報告】\n{report}\n\n【問題】{q['q']}"}], think=False)
    try:
        return json.loads(res["message"]["content"])
    except (ValueError, TypeError, KeyError):
        return {}


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--runs-file", action="append", required=True, help="evals/analysis/regression.py 的 runs.json（可以給好幾個）")
    p.add_argument("--model", default="gemma4:26b", help="S 版的 Synthesizer（F 版是 job 當時的設定）")
    p.add_argument("--reader", default="gemma4:26b", help="答題的模型")
    p.add_argument("--only", default="", help="只做這些 case（逗號分隔）")
    p.add_argument("--limit", type=int, default=0, help="每個 runs.json 最多幾份數據（0＝全部）")
    p.add_argument("--rating", default="", help="給人看的對照要放哪幾份數據（case，逗號分隔）")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    os.chdir(PROJECT)
    os.makedirs(args.out, exist_ok=True)
    os.environ["AGENT_PERF_LOG"] = "0"   # 比較用的呼叫不寫進 logs/perf.jsonl
    from agent_core.agent import SkillAgent
    from agent_core.analysis_job import _note_line
    from agent_core.claims import problems
    agent = SkillAgent(model=args.model)
    agent.analysis_cfg["synthesizer"] = args.model
    single_dir = os.path.join(os.path.abspath(args.out), "single_jobs")
    agent.analysis_jobs_dir = lambda: single_dir
    only = set(filter(None, args.only.split(",")))
    picks = []
    for path in args.runs_file:
        seen, n = set(), 0
        for r in json.load(open(path, encoding="utf-8")):
            if not r.get("job") or r["case"] in seen or (only and r["case"] not in only):
                continue
            if args.limit and n >= args.limit:
                break
            seen.add(r["case"])
            n += 1
            picks.append((os.path.basename(os.path.dirname(path)), r["case"], r["job"]))
    rows, qrows = [], []
    for k, (group, case, jid) in enumerate(picks, 1):
        job = json.load(open(os.path.join(JOBS, jid, "job.json"), encoding="utf-8"))
        facts = job.get("facts")
        if not facts or not any(r.get("values") for r in facts["topics"]) or job.get("status") != "done":
            print(f"[{k}/{len(picks)}] {case}：job {jid} 沒有新版的事實或沒有完成，略過", flush=True)
            continue
        versions = {}
        hl_f = job["report"]["highlights"]
        versions["F"] = {"highlights": hl_f, "calls": job.get("model_calls"), "seconds": job.get("seconds"),
                         "meaning": first_pass_meaning(job), "program": sum(1 for h in hl_f if h.get("program"))}
        sj, summ, secs = run_single(agent, job, facts, args.out)
        versions["S"] = {"highlights": summ["highlights"], "calls": sj["model_calls"], "seconds": secs, "meaning": first_pass_meaning(sj),
                         "program": sum(1 for h in summ["highlights"] if h.get("program")), "fallback": summ.get("fallback")}
        versions["P"] = {"highlights": render(program_highlights(facts), facts), "calls": 0, "seconds": 0.0, "meaning": (0, 0), "program": 0}
        qs = make_questions(facts)
        rec = {"group": group, "case": case, "job": jid, "questions": len(qs), "versions": {}}
        for name in ("P", "S", "F"):
            v = versions[name]
            report = agent._report_for_main(dict(job, workers=job.get("workers") if name == "F" else []), facts, {"highlights": v["highlights"]})
            left = [x for h in v["highlights"] for x in problems(h["text"], h["refs"], facts)] if name != "P" else []
            answers = []
            for q in qs:
                a = ask(agent, args.reader, report, q)
                ok = judge(q, a)
                answers.append(ok)
                qrows.append({"group": group, "case": case, "version": name, "kind": q["kind"], "q": q["q"], "truth": q["truth"], "answer": a, "ok": ok})
            rec["versions"][name] = {"correct": sum(answers), "highlights": len(v["highlights"]), "calls": v["calls"], "seconds": v["seconds"],
                                     "meaning_first": v["meaning"][0], "meaning_left": v["meaning"][1], "program_filled": v["program"],
                                     "claims_in_final": len(left), "report_chars": len(report)}
            v["report"] = report
        rows.append(rec)
        print(f"[{k}/{len(picks)}] {case}：題目 {len(qs)}；答對 P {rec['versions']['P']['correct']}、S {rec['versions']['S']['correct']}、"
              f"F {rec['versions']['F']['correct']}；意思第一版交回 S {rec['versions']['S']['meaning_first']}、F {rec['versions']['F']['meaning_first']}", flush=True)
        if case in set(filter(None, args.rating.split(","))):
            write_rating(args.out, case, jid, job, versions, _note_line)
        json.dump(rows, open(os.path.join(args.out, "ablation.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(qrows, open(os.path.join(args.out, "questions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    write_md(args.out, rows, qrows, args)
    print(f"→ {os.path.join(args.out, 'ablation.md')}")


def write_rating(out, case, jid, job, versions, note_line):
    """給人看的對照：三個版本的重點並排，標籤 A／B／C 打亂（每份數據固定的亂數），對照表寫進 key.json。"""
    d = os.path.join(out, "rating")
    os.makedirs(d, exist_ok=True)
    names = ["P", "S", "F"]
    random.Random(case).shuffle(names)
    labels = dict(zip("ABC", names))
    lines = [f"# {case}（{job.get('data_label')}，{job.get('duration_sec')} 秒）", "", f"問題：{job.get('question')}", "",
             "三個版本的「重點」（同一份數據、同一份程式量的事實；每則下面列的事件與 Log 是程式列的，三個版本一樣的規則）。", ""]
    for lab in "ABC":
        v = versions[labels[lab]]
        lines += [f"## 版本 {lab}", ""] + [note_line(h, n=110, bold=True, max_lines=6) for h in v["highlights"]] + [""]
    lines += ["## 評分（看完三個版本再填）", "", "| | A | B | C |", "|---|---|---|---|", "| 最快看懂發生了什麼（1～5） | | | |",
              "| 有沒有寫錯或誤導的句子（寫出哪一句） | | | |", "| 最想拿給同事看的是哪一個 | | | |", ""]
    open(os.path.join(d, f"{case}.md"), "w", encoding="utf-8").write("\n".join(lines))
    key_path = os.path.join(d, "key.json")
    key = json.load(open(key_path, encoding="utf-8")) if os.path.exists(key_path) else {}
    key[case] = {"labels": labels, "job": jid, "P": "只有程式", "S": "只呼叫一次模型（Synthesizer）", "F": "三個角色"}
    json.dump(key, open(key_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def write_md(out, rows, qrows, args):
    def tot(name, field):
        return sum(r["versions"][name][field] for r in rows)
    nq = sum(r["questions"] for r in rows)
    lines = [f"# 三個版本的比較（{time.strftime('%Y-%m-%d %H:%M')}）", "",
             f"數據 {len(rows)} 份（{', '.join(sorted({r['group'] for r in rows}))}）；題目 {nq} 題（依事實自動出）；讀者模型 {args.reader}；S 版的模型 {args.model}。", "",
             "| 版本 | 答對 | 重點平均則數 | 模型呼叫 | 平均秒數 | 第一版因意思被交回 | 交回後仍對不上（沒列） | 程式補寫的重點 |", "|---|---|---|---|---|---|---|---|"]
    for name, label in (("P", "P 只有程式"), ("S", "S 只呼叫一次模型"), ("F", "F 三個角色")):
        n = len(rows) or 1
        secs = [r["versions"][name]["seconds"] or 0 for r in rows]
        lines.append(f"| {label} | {tot(name, 'correct')}/{nq} | {tot(name, 'highlights') / n:.1f} | {tot(name, 'calls')} | "
                     f"{sum(secs) / n:.1f} | {tot(name, 'meaning_first')} | {tot(name, 'meaning_left')} | {tot(name, 'program_filled')} |")
    kinds = sorted({q["kind"] for q in qrows})
    lines += ["", "## 各類題目的答對數", "", "| 題目 | P | S | F |", "|---|---|---|---|"]
    for k in kinds:
        cells = []
        for name in "PSF":
            qs = [q for q in qrows if q["kind"] == k and q["version"] == name]
            cells.append(f"{sum(q['ok'] for q in qs)}/{len(qs)}")
        lines.append(f"| {k} | " + " | ".join(cells) + " |")
    lines += ["", "## 每份數據", "", "| 組 | 數據 | 題目 | P | S | F | S 交回（意思） | F 交回（意思） |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        v = r["versions"]
        lines.append(f"| {r['group']} | {r['case']} | {r['questions']} | {v['P']['correct']} | {v['S']['correct']} | {v['F']['correct']} | "
                     f"{v['S']['meaning_first']} | {v['F']['meaning_first']} |")
    wrong = [q for q in qrows if not q["ok"]]
    lines += ["", f"## 答錯的題目（{len(wrong)} 題，各版本分開）", ""]
    for q in wrong[:120]:
        a = q["answer"] or {}
        lines.append(f"- {q['version']}｜{q['case']}｜{q['q']}｜正確：{q['truth']}｜回答：{str(a.get('answer'))[:120]}"
                     f"（value={a.get('value')!r}、time={a.get('time')!r}、yes_no={a.get('yes_no')!r}）")
    open(os.path.join(out, "ablation.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
