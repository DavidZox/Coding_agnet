"""從 results/tables/*.csv 算出第三次評測的統計：results/summary.json 與 results/tables/*.md（可以直接貼進報告的表格）。

    python3 benchmark_study_3/analysis/analyze.py

統計方法（只用標準庫，固定亂數種子，可重現；跟前兩次研究一致）：
- 通過率（非編碼情境、BF／FE／AP 的解決率）：把同一個條件的所有執行合起來，Wilson 95% 區間。
  同一題跑了好幾次，次與次之間不獨立，所以區間只是參考；版本之間的比較用下面的配對檢定。
- pass^k：k 次都通過的題目比例（τ-bench 的可靠度指標）；pass@k：k 次裡至少一次通過。
- 版本比較（同一個模型）：每一題先算各版本的平均通過率，以「題」為單位配對——勝／負／平手，符號檢定（雙尾、精確二項，平手不算）；
  差值的 95% 區間用以題為單位的 bootstrap（B=10000）。
- TW 的覆蓋率與突變分數：每一題先平均各次，再以題為單位配對，同樣用 bootstrap 與符號檢定。
"""
import csv
import json
import math
import os
import random
import statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
TABLES = os.environ.get("S3_TABLES") or os.path.join(STUDY, "results", "tables")
B = 10000
SEED = 20261010
VERSIONS = ["v4.2", "v5"]
MODELS = ["gemma4:26b", "gemma4:e4b"]
DOMAINS = ["fs", "docker", "ros2", "handshake", "complex"]
DOMAIN_NAME = {"fs": "目錄與文件", "docker": "Docker", "ros2": "ROS 2", "handshake": "調度交握", "complex": "複合任務"}
FAMILY_NAME = {"tw": "TW 寫測試", "bf": "BF 修 bug", "fe": "FE 補功能", "ap": "AP 練習題"}


# ---------------------------------------------------------------- 統計工具
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def sign_test(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def bootstrap_mean_ci(values, seed=SEED):
    if not values:
        return (0.0, 0.0)
    rnd, n, out = random.Random(seed), len(values), []
    for _ in range(B):
        out.append(sum(values[rnd.randrange(n)] for _ in range(n)) / n)
    out.sort()
    return (out[int(0.025 * B)], out[int(0.975 * B) - 1])


def pct(x):
    return f"{100 * x:.1f}%"


def ci_txt(ci, scale=100):
    return f"[{scale * ci[0]:.1f}, {scale * ci[1]:.1f}]"


def read_csv(name):
    path = os.path.join(TABLES, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def write_md(name, text):
    with open(os.path.join(TABLES, name), "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


# ---------------------------------------------------------------- 共用：通過率、pass^k、配對比較
def rate_block(rows, key="passed"):
    k, n = sum(int(num(r[key])) for r in rows), len(rows)
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": k / n if n else 0.0, "ci": (lo, hi)}


def per_item(rows, item_key, key="passed"):
    """{題目: [各次的 0/1]}"""
    out = defaultdict(list)
    for r in rows:
        out[r[item_key]].append(int(num(r[key])))
    return out


def pass_k(rows, item_key, key="passed"):
    items = per_item(rows, item_key, key)
    runs = sorted({int(r["run"]) for r in rows})
    if not items:
        return {}
    k = min(len(v) for v in items.values())
    return {"runs": len(runs), "k": k, "pass_all": sum(1 for v in items.values() if all(v[:k])) / len(items),
            "pass_any": sum(1 for v in items.values() if any(v[:k])) / len(items), "items": len(items)}


def paired(rows_a, rows_b, item_key, key="passed"):
    """以題為單位比較 b 對 a：每一題先平均各次。回傳勝負、符號檢定、差值與 bootstrap 區間。"""
    a, b = per_item(rows_a, item_key, key), per_item(rows_b, item_key, key)
    common = sorted(set(a) & set(b))
    diffs = [statistics.mean(b[t]) - statistics.mean(a[t]) for t in common]
    wins, losses = sum(1 for d in diffs if d > 1e-9), sum(1 for d in diffs if d < -1e-9)
    return {"items": len(common), "wins": wins, "losses": losses, "ties": len(common) - wins - losses,
            "p": sign_test(wins, losses), "diff": statistics.mean(diffs) if diffs else 0.0, "ci": bootstrap_mean_ci(diffs),
            "better": [t for t, d in zip(common, diffs) if d > 1e-9], "worse": [t for t, d in zip(common, diffs) if d < -1e-9]}


def select(rows, **kw):
    return [r for r in rows if all(str(r.get(k)) == str(v) for k, v in kw.items())]


# ---------------------------------------------------------------- 非編碼（ops suite）
def ops(summary, md):
    rows = read_csv("ops_runs.csv")
    if not rows:
        return
    S = summary["ops"] = {}
    for st in ("main", "holdout"):
        srows = select(rows, set=st)
        if not srows:
            continue
        lines, dom_lines, pair_lines = [], [], []
        for model in MODELS:
            for ver in VERSIONS:
                rr = select(srows, model=model, version=ver)
                if not rr:
                    continue
                rb = rate_block(rr)
                pk = pass_k(rr, "scenario")
                secs = [num(r["seconds"]) for r in rr]
                calls = [num(r["model_calls"]) for r in rr]
                S.setdefault(st, {}).setdefault(model, {})[ver] = {
                    **rb, **{f"pass_{k}": v for k, v in pk.items()}, "seconds_median": statistics.median(secs),
                    "seconds_mean": statistics.mean(secs), "model_calls_median": statistics.median(calls),
                    "forbidden": sum(1 for r in rr if int(r["forbidden"])), "used_ops": sum(int(r["used_ops"]) for r in rr)}
                lines.append([model, ver, pk.get("runs", 0), f"{rb['k']}/{rb['n']}", pct(rb["rate"]), ci_txt(rb["ci"]),
                              pct(pk.get("pass_all", 0)), pct(pk.get("pass_any", 0)),
                              f"{statistics.median(secs):.0f}", f"{statistics.median(calls):.0f}",
                              sum(1 for r in rr if int(r["forbidden"]))])
                for d in DOMAINS:
                    dr = select(rr, domain=d)
                    if dr:
                        b = rate_block(dr)
                        S[st][model][ver].setdefault("domains", {})[d] = b
                dom_lines.append([model, ver] + [(lambda b: f"{pct(b['rate'])}（{b['k']}/{b['n']}）")(rate_block(select(rr, domain=d)))
                                                 if select(rr, domain=d) else "—" for d in DOMAINS])
            a, b = select(srows, model=model, version="v4.2"), select(srows, model=model, version="v5")
            if a and b:
                pr = paired(a, b, "scenario")
                S[st][model]["paired"] = pr
                pair_lines.append([model, pr["items"], pr["wins"], pr["losses"], pr["ties"], f"{100 * pr['diff']:+.1f}",
                                   ci_txt(pr["ci"]), f"{pr['p']:.3g}"])
                for d in DOMAINS:
                    pd = paired(select(a, domain=d), select(b, domain=d), "scenario")
                    S[st][model].setdefault("paired_domains", {})[d] = pd
        name = "主要組 50 個情境" if st == "main" else "保留組 20 個情境"
        md.append(f"## 非編碼：{name}\n")
        md.append(md_table(["模型", "版本", "次數", "通過", "通過率", "95% 區間", "pass^k（每次都過）", "pass@k（至少一次）",
                            "秒數（中位數）", "模型呼叫（中位數）", "禁止動作"], lines))
        md.append("\n" + md_table(["模型", "版本"] + [DOMAIN_NAME[d] for d in DOMAINS], dom_lines))
        if pair_lines:
            md.append("\n版本比較（同一個模型，以情境為單位配對；v5 對 v4.2）：\n")
            md.append(md_table(["模型", "情境", "v5 較好", "v5 較差", "一樣", "差（百分點）", "95% 區間", "符號檢定 p"], pair_lines))
        write_md(f"ops_{st}.md", "\n".join(md[-(3 if not pair_lines else 5):]))
        md.append("")
    # 每個情境：各模型、各版本通過幾次（附錄用）
    for st in ("main", "holdout"):
        srows = select(rows, set=st)
        if not srows:
            continue
        conds = [(m, v) for m in MODELS for v in VERSIONS if select(srows, model=m, version=v)]
        lines = []
        for sc in sorted({r["scenario"] for r in srows}, key=lambda x: (DOMAINS.index(select(srows, scenario=x)[0]["domain"]), x)):
            row = [sc, DOMAIN_NAME[select(srows, scenario=sc)[0]["domain"]]]
            for m, v in conds:
                rr = select(srows, scenario=sc, model=m, version=v)
                row.append(f"{sum(int(r['passed']) for r in rr)}/{len(rr)}" if rr else "—")
            lines.append(row)
        write_md(f"ops_{st}_matrix.md", md_table(["情境", "領域"] + [f"{m.replace('gemma4:', '')} {v}" for m, v in conds], lines))
    # v5 的 orchestrator 用了多少、成功率
    v5 = select(rows, version="v5")
    if v5:
        lines = []
        for model in MODELS:
            for st in ("main", "holdout"):
                rr = select(v5, model=model, set=st)
                if not rr:
                    continue
                used = [r for r in rr if int(r["used_ops"])]
                notused = [r for r in rr if not int(r["used_ops"])]
                for d in DOMAINS + ["全部"]:
                    dr = rr if d == "全部" else select(rr, domain=d)
                    du = [r for r in dr if int(r["used_ops"])]
                    if not dr:
                        continue
                    lines.append([model, st, DOMAIN_NAME.get(d, d), f"{len(du)}/{len(dr)}",
                                  pct(rate_block(du)["rate"]) if du else "—",
                                  pct(rate_block([r for r in dr if not int(r["used_ops"])])["rate"]) if len(du) < len(dr) else "—",
                                  f"{statistics.median([num(r['seconds']) for r in du]):.0f}" if du else "—",
                                  f"{statistics.median([num(r['seconds']) for r in dr if not int(r['used_ops'])]):.0f}" if len(du) < len(dr) else "—"])
                S.setdefault("ops_usage", {}).setdefault(model, {})[st] = {
                    "used": len(used), "n": len(rr), "pass_used": rate_block(used)["rate"] if used else None,
                    "pass_not_used": rate_block(notused)["rate"] if notused else None}
        md.append("## v5：主對話什麼時候用了 ops_run（非編碼的 orchestrator）\n")
        md.append(md_table(["模型", "題組", "領域", "用了 ops 的次數", "用了時的通過率", "沒用時的通過率", "用了時的秒數（中位數）",
                            "沒用時的秒數（中位數）"], lines))
        write_md("ops_usage.md", md[-1])
        md.append("")


# ---------------------------------------------------------------- 小專案
def small_projects(summary, md):
    rows = read_csv("sp_runs.csv")
    if not rows:
        return
    S = summary["small_projects"] = {}
    # BF／FE／AP：解決率
    lines, pair_lines = [], []
    for fam in ("bf", "fe", "ap"):
        for model in MODELS:
            for ver in VERSIONS:
                rr = select(rows, family=fam, model=model, version=ver)
                if not rr:
                    continue
                rb = rate_block(rr, "resolved")
                pk = pass_k(rr, "task", "resolved")
                secs = [num(r["seconds"]) for r in rr]
                S.setdefault(fam, {}).setdefault(model, {})[ver] = {**rb, **{f"pass_{k}": v for k, v in pk.items()},
                                                                     "seconds_median": statistics.median(secs)}
                by_lang = {lang: rate_block(select(rr, lang=lang), "resolved") for lang in ("python", "cpp") if select(rr, lang=lang)}
                S[fam][model][ver]["by_lang"] = by_lang
                lines.append([FAMILY_NAME[fam], model, ver, pk.get("runs", 0), f"{rb['k']}/{rb['n']}", pct(rb["rate"]), ci_txt(rb["ci"]),
                              " ／ ".join(f"{lang} {pct(b['rate'])}" for lang, b in by_lang.items()),
                              pct(pk.get("pass_all", 0)), f"{statistics.median(secs) / 60:.1f}",
                              sum(1 for r in rr if num(r.get("tests_changed")) > 0)])
            a, b = select(rows, family=fam, model=model, version="v4.2"), select(rows, family=fam, model=model, version="v5")
            if a and b:
                pr = paired(a, b, "task", "resolved")
                S[fam][model]["paired"] = pr
                pair_lines.append([FAMILY_NAME[fam], model, pr["items"], pr["wins"], pr["losses"], pr["ties"],
                                   f"{100 * pr['diff']:+.1f}", ci_txt(pr["ci"]), f"{pr['p']:.3g}"])
    if lines:
        md.append("## 小專案：修 bug（BF）、補功能（FE）、練習題（AP）的解決率\n")
        md.append(md_table(["類別", "模型", "版本", "次數", "解決", "解決率", "95% 區間", "Python ／ C++", "pass^k", "分鐘（中位數）",
                            "改了測試的次數"], lines))
        if pair_lines:
            md.append("\n版本比較（以題為單位配對；v5 對 v4.2）：\n")
            md.append(md_table(["類別", "模型", "題數", "v5 較好", "v5 較差", "一樣", "差（百分點）", "95% 區間", "符號檢定 p"], pair_lines))
        write_md("sp_bf_fe_ap.md", "\n".join(md[-(3 if pair_lines else 1):]))
        md.append("")
    # 每一題：解決幾次（附錄用）
    conds = [(m, v) for m in MODELS for v in VERSIONS if select(rows, model=m, version=v)]
    lines = []
    for fam in ("bf", "fe", "ap"):
        for t in sorted({r["task"] for r in rows if r["family"] == fam}):
            row = [t, select(rows, task=t)[0]["lang"]]
            for m, v in conds:
                rr = select(rows, task=t, model=m, version=v)
                row.append(f"{sum(int(num(r['resolved'])) for r in rr)}/{len(rr)}" if rr else "—")
            lines.append(row)
    if lines:
        write_md("sp_tasks_matrix.md", md_table(["題目", "語言"] + [f"{m.replace('gemma4:', '')} {v}" for m, v in conds], lines))
    # TW：寫測試
    tw = select(rows, family="tw")
    if tw:
        lines, pair_lines = [], []
        for model in MODELS:
            for ver in VERSIONS:
                rr = select(tw, model=model, version=ver)
                if not rr:
                    continue
                ok = rate_block(rr, "tests_ok")
                vals = {k: [num(r[k]) for r in rr] for k in ("line_cov", "branch_cov", "mut_score")}
                S.setdefault("tw", {}).setdefault(model, {})[ver] = {
                    "tests_ok": ok, **{f"{k}_mean": statistics.mean(v) for k, v in vals.items()},
                    "prod_changed": sum(1 for r in rr if num(r["prod_changed"]) > 0),
                    "bare_tests": sum(int(num(r["tests_without_assert"])) for r in rr),
                    "seconds_median": statistics.median([num(r["seconds"]) for r in rr])}
                by_src = {}
                for src in ("devbench", "projecttest"):
                    sr = select(rr, source=src)
                    if sr:
                        by_src[src] = statistics.mean(num(r["mut_score"]) for r in sr)
                S["tw"][model][ver]["mut_by_source"] = by_src
                lines.append([model, ver, len({r['run'] for r in rr}), f"{ok['k']}/{ok['n']}",
                              f"{statistics.mean(vals['line_cov']):.1f}", f"{statistics.mean(vals['branch_cov']):.1f}",
                              f"{statistics.mean(vals['mut_score']):.1f}",
                              " ／ ".join(f"{s} {v:.1f}" for s, v in by_src.items()),
                              sum(1 for r in rr if num(r["prod_changed"]) > 0), sum(int(num(r["tests_without_assert"])) for r in rr),
                              f"{statistics.median([num(r['seconds']) for r in rr]) / 60:.1f}"])
            a, b = select(tw, model=model, version="v4.2"), select(tw, model=model, version="v5")
            if a and b:
                for k, name in (("mut_score", "突變分數"), ("line_cov", "行覆蓋率"), ("branch_cov", "分支覆蓋率"), ("tests_ok", "測試全過")):
                    pa, pb = defaultdict(list), defaultdict(list)
                    for r in a:
                        pa[r["task"]].append(num(r[k]))
                    for r in b:
                        pb[r["task"]].append(num(r[k]))
                    common = sorted(set(pa) & set(pb))
                    scale = 100 if k == "tests_ok" else 1
                    diffs = [(statistics.mean(pb[t]) - statistics.mean(pa[t])) * scale for t in common]
                    w, l_ = sum(1 for d in diffs if d > 1e-9), sum(1 for d in diffs if d < -1e-9)
                    ci = bootstrap_mean_ci(diffs)
                    S["tw"][model].setdefault("paired", {})[k] = {"items": len(common), "wins": w, "losses": l_, "diff": statistics.mean(diffs) if diffs else 0,
                                                                  "ci": ci, "p": sign_test(w, l_)}
                    pair_lines.append([model, name, len(common), w, l_, len(common) - w - l_,
                                       f"{statistics.mean(diffs) if diffs else 0:+.1f}", f"[{ci[0]:.1f}, {ci[1]:.1f}]", f"{sign_test(w, l_):.3g}"])
        md.append("## 小專案：寫測試（TW）\n")
        md.append(md_table(["模型", "版本", "次數", "測試全過", "行覆蓋率（平均）", "分支覆蓋率（平均）", "突變分數（平均）",
                            "突變分數：DevBench ／ ProjectTest", "改了正式程式", "沒有斷言的測試", "分鐘（中位數）"], lines))
        if pair_lines:
            md.append("\n版本比較（以題為單位配對；v5 減 v4.2，覆蓋率與突變分數是百分點）：\n")
            md.append(md_table(["模型", "指標", "題數", "v5 較好", "v5 較差", "一樣", "差", "95% 區間", "符號檢定 p"], pair_lines))
        write_md("sp_tw.md", "\n".join(md[-(3 if pair_lines else 1):]))
        md.append("")
        # 每一題
        task_lines = []
        for t in sorted({r["task"] for r in tw}):
            row = [t, select(tw, task=t)[0]["lang"]]
            for model in MODELS:
                for ver in VERSIONS:
                    rr = select(tw, task=t, model=model, version=ver)
                    row.append(f"{statistics.mean(num(r['mut_score']) for r in rr):.0f}／{statistics.mean(num(r['line_cov']) for r in rr):.0f}"
                               if rr else "—")
            task_lines.append(row)
        hdr = ["題目", "語言"] + [f"{m} {v}" for m in MODELS for v in VERSIONS]
        write_md("sp_tw_tasks.md", "每一題的突變分數／行覆蓋率（各次平均）\n\n" + md_table(hdr, task_lines))


def main():
    summary, md = {}, []
    ops(summary, md)
    small_projects(summary, md)
    with open(os.environ.get("S3_SUMMARY") or os.path.join(STUDY, "results", "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=lambda o: list(o) if isinstance(o, tuple) else str(o))
    write_md("all.md", "\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
