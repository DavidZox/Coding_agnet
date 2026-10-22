#!/usr/bin/env python3
"""只重算評分標準：分析程式的定義或產生器登記評分標準的方式改了、數據沒變時，在主機上用同一個 seed 重跑模擬（不需要 ROS、
不重寫 bag），重算 cases.json 的 timeline、topics、no_event。重跑出來的情境（標題、子系統、長度）跟原本不同的那一份不動——
代表產生器的程式已經不是產生那份數據的版本，數據跟評分標準對不起來（例如加 bridge 之前產生的 gen/s1）。

    python3 evals/datagen/refresh_truth.py test_data/recordings/gen/s3/cases.json [--seed 3] [--require bridge] [--dry-run]"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sim_main import make_case  # noqa: E402
from sim_scenarios import compose  # noqa: E402

FIELDS = ("timeline", "topics", "no_event")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("cases")
    p.add_argument("--seed", type=int, default=None, help="省略＝cases.json 記的 seed")
    p.add_argument("--require", default=None, help="省略＝cases.json 記的 require")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    spec = json.load(open(args.cases, encoding="utf-8"))
    seed = args.seed if args.seed is not None else spec.get("seed")
    require = [x for x in (args.require.split(",") if args.require is not None else spec.get("require") or []) if x]
    if seed is None:
        sys.exit("cases.json 沒有記 seed：用 --seed 指定")
    changed = skipped = 0
    for case in spec["cases"]:
        idx = int(case["id"].rsplit("_", 1)[1])
        sim, info = compose(seed, idx, require=require)
        new = make_case(sim, info)
        if (new["id"], new["title"], new["systems"], new["seconds"]) != (case["id"], case["title"], case["systems"], case["seconds"]):
            print(f"⚠️ {case['id']}：重跑出來的情境不一樣（產生器的程式不是當時那一版），不動")
            skipped += 1
            continue
        diff = [k for k in FIELDS if new.get(k) != case.get(k)]
        if diff:
            changed += 1
            print(f"✏️ {case['id']}：{'、'.join(diff)}")
            for k in FIELDS:
                if k in new:
                    case[k] = new[k]
                else:
                    case.pop(k, None)
    spec["seed"], spec["require"] = seed, require
    if not args.dry_run and changed:
        json.dump(spec, open(args.cases, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"重算 {len(spec['cases']) - skipped} 份，改了 {changed} 份，情境不同沒動 {skipped} 份" + ("（--dry-run：沒有寫檔）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
