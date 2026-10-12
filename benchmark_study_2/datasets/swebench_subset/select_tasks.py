"""從 SWE-bench Verified（Python）與 SWE-bench Multilingual（C／C++）抽出這次評測用的 24 題，結果寫到 instances.json。

    python3 select_tasks.py            # 用固定的種子重新抽一次（結果應該跟 instances.json 一模一樣）
    python3 select_tasks.py --replace django__django-11099   # 某一題的環境驗證不過時，從同一層換一題

抽樣規則（事先定好、不看題目內容）：
- Python 16 題：專案配額大致照 Verified 的分布（django 46%、sympy 15%…，小專案合併成一層），
  難度配額照 Verified 標註的分布（<15 分鐘 39%、15 分鐘～1 小時 52%、1 小時以上 9%）→ 6／8／2。
  做法：用種子打亂全部 500 題，依序挑「專案與難度配額都還有剩」的題目；挑不滿就換下一個種子重來。
- C／C++ 8 題：C 4 題（redis 2、jq 1、micropython 1）、C++ 4 題（fmt 3、nlohmann/json 1），各專案內用種子隨機挑。
  Multilingual 沒有難度標註。
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261009
PY_REPO_QUOTA = {"django/django": 6, "sympy/sympy": 2, "sphinx-doc/sphinx": 2, "matplotlib/matplotlib": 1,
                 "scikit-learn/scikit-learn": 1, "astropy/astropy": 1, "pydata/xarray": 1, "pytest-dev/pytest": 1,
                 "small": 1}
SMALL = {"pylint-dev/pylint", "psf/requests", "mwaskom/seaborn", "pallets/flask"}
DIFF_QUOTA = {"easy": 6, "medium": 8, "hard": 2}
C_QUOTA = {"redis/redis": 2, "jqlang/jq": 1, "micropython/micropython": 1, "fmtlib/fmt": 3, "nlohmann/json": 1}
LANG = {"redis/redis": "C", "jqlang/jq": "C", "micropython/micropython": "C", "fmtlib/fmt": "C++", "nlohmann/json": "C++"}


def diff_class(d):
    return {"<15 min fix": "easy", "15 min - 1 hour": "medium"}.get(d, "hard")


def repo_class(repo):
    return "small" if repo in SMALL else repo


def pick_python(rows, exclude):
    for attempt in range(1000):
        rng = random.Random(SEED + attempt)
        order = [r for r in rows if r["instance_id"] not in exclude]
        rng.shuffle(order)
        rq, dq, chosen = dict(PY_REPO_QUOTA), dict(DIFF_QUOTA), []
        for r in order:
            rc, dc = repo_class(r["repo"]), diff_class(r["difficulty"])
            if rq.get(rc, 0) > 0 and dq[dc] > 0:
                chosen.append(r)
                rq[rc] -= 1
                dq[dc] -= 1
        if not any(rq.values()) and not any(dq.values()):
            return chosen, SEED + attempt
    raise SystemExit("抽不滿配額")


def pick_c(rows, exclude):
    rng = random.Random(SEED)
    chosen = []
    for repo, n in C_QUOTA.items():
        pool = sorted((r for r in rows if r["repo"] == repo and r["instance_id"] not in exclude), key=lambda r: r["instance_id"])
        rng.shuffle(pool)
        chosen += pool[:n]
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", default="", help="逗號分隔：環境驗證不過、要排除的題目")
    args = ap.parse_args()
    exclude = {x.strip() for x in args.replace.split(",") if x.strip()}
    with open(os.path.join(HERE, "source", "SWE-bench_Verified.json"), encoding="utf-8") as f:
        verified = json.load(f)
    with open(os.path.join(HERE, "source", "SWE-bench_Multilingual.json"), encoding="utf-8") as f:
        multi = json.load(f)
    py, seed_used = pick_python(verified, exclude)
    cc = pick_c(multi, exclude)
    out = []
    for r in py:
        out.append(dict(r, lang="Python", source="SWE-bench_Verified", difficulty_class=diff_class(r["difficulty"])))
    for r in cc:
        out.append(dict(r, lang=LANG[r["repo"]], source="SWE-bench_Multilingual", difficulty="", difficulty_class=""))
    with open(os.path.join(HERE, "instances.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    lines = ["# 抽到的題目", "", f"Python 用的種子：{seed_used}（{SEED} 起第一個能填滿配額的）；排除：{', '.join(sorted(exclude)) or '無'}", "",
             "| # | 題目 | 語言 | 專案 | 難度（Verified 標註） | F2P 測試數 | P2P 測試數 |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(out, 1):
        f2p = r["FAIL_TO_PASS"] if isinstance(r["FAIL_TO_PASS"], list) else json.loads(r["FAIL_TO_PASS"])
        p2p = r["PASS_TO_PASS"] if isinstance(r["PASS_TO_PASS"], list) else json.loads(r["PASS_TO_PASS"])
        lines.append(f"| {i} | `{r['instance_id']}` | {r['lang']} | {r['repo']} | {r['difficulty'] or '—'} | {len(f2p)} | {len(p2p)} |")
    with open(os.path.join(HERE, "instances.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
