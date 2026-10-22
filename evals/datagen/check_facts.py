#!/usr/bin/env python3
"""只驗程式那一層（不呼叫模型）：產生器的每一份錄製，用分析程式量全部的事實（mcap_analyzer --facts、rosout_parser，
analysis_job.build_facts），跟產生器的評分標準比——時間線該有的事件、Topic 的類別、穩定的錄製沒有事件（背景的 Topic 除外）。
大量數據時先跑這個（快、結果固定），程式的事實對了，再跑有模型的回歸（evals/analysis_regression.py）。

    python3 evals/datagen/check_facts.py test_data/recordings/gen/s1/cases.json [--container cah_analysis_test] [--only id1,id2] [-v]"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "skills_system", "scripts"))


def run(script, args, container):
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(PROJECT, "skills_system", "scripts", script)] + args + ["--container", container],
                       capture_output=True, text=True, timeout=900)
    return r.stdout


def match(ev, rows):
    from evals.analysis_regression import _rows_for
    return _rows_for(ev, rows)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("cases")
    p.add_argument("--container", default="cah_analysis_test")
    p.add_argument("--only", default="")
    p.add_argument("-v", action="store_true")
    args = p.parse_args()
    from agent_core.analysis_job import build_facts, split_json_output
    spec = json.load(open(args.cases, encoding="utf-8"))
    only = set(filter(None, args.only.split(",")))
    tot = {"timeline": [0, 0], "tags": [0, 0], "cases": 0, "clean_cases": 0}
    for case in spec["cases"]:
        if only and case["id"] not in only:
            continue
        data = f"{spec['data_root'].rstrip('/')}/{case['data']}"
        idx, _ = split_json_output(run("mcap_analyzer_cmd.py", [data, "--json"], args.container))
        scan, _ = split_json_output(run("mcap_analyzer_cmd.py", [data, "--facts", "--json", "--timeout", "570"], args.container))
        logs, _ = split_json_output(run("rosout_parser_cmd.py", [data, "--json", "--top", "2000", "--all-nodes"], args.container))
        if not idx or not scan:
            print(f"❌ {case['id']}：讀不到事實")
            continue
        job = {"index": idx, "scan": scan, "signals": (logs or {}).get("signals") or [], "plan": {"related": []}}
        facts = build_facts(job)
        rows = [{"time": r["time"], "source": r["source"], "event": r["event"], "ref": r["ref"]} for r in facts["timeline"]]
        miss = [ev for ev in case.get("timeline") or [] if not match(ev, rows)]
        tags = {r["topic"]: set(r["tags"]) for r in facts["topics"]}
        bad_tags = []
        for t in case.get("topics") or []:
            got = tags.get(t["topic"])
            if got is None:
                bad_tags.append(f"{t['topic']} 不在事實裡")
                continue
            bad_tags += [f"{t['topic']} 沒有「{x}」（{'、'.join(sorted(got))}）" for x in t["has"] if x not in got]
            bad_tags += [f"{t['topic']} 不該有「{x}」" for x in t["not"] if x in got]
        quiet = []
        if case.get("no_event") is not None:   # 穩定的錄製：背景以外的 Topic 都不該有事件（同 analysis_regression 的「沒有事件」）
            from evals.analysis_regression import EVENT_TAGS
            bg = set(case["no_event"].get("background") or [])
            quiet = [f"{r['topic']}（{'、'.join(x for x in r['tags'] if x in EVENT_TAGS)}）" for r in facts["topics"]
                     if r["topic"] not in bg and any(x in EVENT_TAGS for x in r["tags"])]
            bad_tags += [f"穩定的錄製卻有事件：{q}" for q in quiet]
            n_tag_extra = 1
        else:
            n_tag_extra = 0
        n_tl, n_tag = len(case.get("timeline") or []), sum(len(t["has"]) + len(t["not"]) for t in case.get("topics") or []) + n_tag_extra
        tot["timeline"][0] += n_tl - len(miss)
        tot["timeline"][1] += n_tl
        tot["tags"][1] += n_tag
        tot["tags"][0] += n_tag - len(bad_tags) + (len(quiet) - 1 if len(quiet) > 1 else 0)   # 穩定的錄製算一項
        tot["cases"] += 1
        ok = not miss and not bad_tags
        tot["clean_cases"] += ok
        got_tag = n_tag - len(bad_tags) + (len(quiet) - 1 if len(quiet) > 1 else 0)
        print(f"{'✅' if ok else '❌'} {case['id']}（{case['seconds']}s，{'+'.join(case.get('systems') or [])}）時間線 {n_tl - len(miss)}/{n_tl}、"
              f"類別{'（含沒有事件）' if n_tag_extra else ''} {got_tag}/{n_tag}；掃描 {scan.get('seconds', '快取')} 秒" + ("" if ok else f" — {case['title'][:80]}"))
        for ev in miss:
            near = [f"{r['time']} {r['source']}｜{r['event'][:70]}" for r in rows if abs(float(r['time'].strip('+s')) - ev["t"]) <= 1.0]
            print(f"   缺 +{ev['t']}s {ev.get('all') or ev.get('any')}（{ev.get('what', '')}）" + ("；附近：" + "；".join(near[:4]) if near else "；附近沒有任何列"))
        for b in bad_tags:
            print(f"   類別：{b}")
        if args.v:
            for r in rows[:40]:
                print(f"     {r['time']} {r['source']}｜{r['event'][:90]}")
    print(f"\n合計：{tot['clean_cases']}/{tot['cases']} 份全對；時間線 {tot['timeline'][0]}/{tot['timeline'][1]}；類別 {tot['tags'][0]}/{tot['tags'][1]}")


if __name__ == "__main__":
    main()
