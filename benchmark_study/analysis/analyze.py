"""從 results/tables/*.csv 算出報告用的統計：results/summary.json 與 results/tables/*.md（可以直接貼進報告的表格）。

    python3 benchmark_study/analysis/analyze.py

統計方法（只用標準庫，固定亂數種子，可重現）：
- 通過率的 95% 信賴區間：二項比例用 Wilson score interval；DevBench 的測試通過率（同一個 repo 的測試彼此相關）用
  「以 repo 為單位重抽樣」的 bootstrap（B=10000），算合併通過率（通過的測試數 ÷ 測試總數）的 2.5%／97.5% 分位數。
- 兩種條件的差：同一個 repo（或同一個情境）配對，bootstrap 差值的信賴區間；勝負用符號檢定（雙尾、精確二項）。
- DevBench 另外列出依程式碼行數加權的平均通過率（DevBench 論文的算法），只當參考。
"""
import csv
import json
import math
import os
import random
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
TABLES = os.path.join(STUDY, "results", "tables")
B = 10000
SEED = 20261008


# ---------------------------------------------------------------- 統計工具
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pooled(groups):
    t = sum(g[1] for g in groups)
    return sum(g[0] for g in groups) / t if t else 0.0


def bootstrap_ci(groups, seed=SEED):
    """groups：[(通過數, 總數)]（每個 repo 一組）→ 合併通過率的 95% bootstrap 區間。"""
    if not groups:
        return (0.0, 0.0)
    rnd, n, vals = random.Random(seed), len(groups), []
    for _ in range(B):
        vals.append(pooled([groups[rnd.randrange(n)] for _ in range(n)]))
    vals.sort()
    return (vals[int(0.025 * B)], vals[int(0.975 * B) - 1])


def paired_diff_ci(pairs, seed=SEED):
    """pairs：[((通過A, 總數), (通過B, 總數))] → A−B 合併通過率差的 95% bootstrap 區間。"""
    if not pairs:
        return (0.0, 0.0)
    rnd, n, vals = random.Random(seed), len(pairs), []
    for _ in range(B):
        idx = [rnd.randrange(n) for _ in range(n)]
        vals.append(pooled([pairs[i][0] for i in idx]) - pooled([pairs[i][1] for i in idx]))
    vals.sort()
    return (vals[int(0.025 * B)], vals[int(0.975 * B) - 1])


def sign_test(wins, losses):
    """雙尾精確符號檢定（平手不算）。"""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def pct(x):
    return f"{100 * x:.1f}%"


def ci_txt(ci):
    return f"[{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]"


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


# ---------------------------------------------------------------- DevBench
def devbench(summary, md):
    rows = [r for r in read_csv("devbench_runs.csv") if r["exp"] != "trial"]
    for r in rows:
        for k in ("unit", "unit_total", "acceptance", "acceptance_total", "lines"):
            r[k] = int(r[k] or 0)
        r["minutes"] = float(r["minutes"] or 0)
    runs = defaultdict(list)
    for r in rows:
        runs[r["run_dir"]].append(r)
    table, out = [], []
    order = sorted(runs, key=lambda d: (runs[d][0]["visible"], runs[d][0]["model"], runs[d][0]["condition"], runs[d][0]["version"], d))
    for d in order:
        rs = runs[d]
        if len(rs) < 12:
            continue                        # 還沒跑完的
        m = rs[0]
        ug = [(r["unit"], r["unit_total"]) for r in rs]
        ag = [(r["acceptance"], r["acceptance_total"]) for r in rs]
        mu = sum(r["unit"] / r["unit_total"] for r in rs if r["unit_total"]) / len(rs)
        ma = sum(r["acceptance"] / r["acceptance_total"] for r in rs if r["acceptance_total"]) / len(rs)
        w = sum(r["lines"] for r in rs)
        wu = sum(r["lines"] * r["unit"] / r["unit_total"] for r in rs if r["unit_total"]) / w
        wa = sum(r["lines"] * r["acceptance"] / r["acceptance_total"] for r in rs if r["acceptance_total"]) / w
        item = {"run_dir": d, "exp": m["exp"], "version": m["version"], "model": m["model"], "condition": m["condition"],
                "visible": m["visible"] == "1", "unit": sum(g[0] for g in ug), "unit_total": sum(g[1] for g in ug),
                "unit_rate": pooled(ug), "unit_ci": bootstrap_ci(ug), "acceptance": sum(g[0] for g in ag),
                "acceptance_total": sum(g[1] for g in ag), "acceptance_rate": pooled(ag), "acceptance_ci": bootstrap_ci(ag),
                "weighted_unit": wu, "weighted_acceptance": wa, "macro_unit": mu, "macro_acceptance": ma,
                "minutes": round(sum(r["minutes"] for r in rs), 1),
                "per_repo": {r["repo"]: [r["unit"], r["unit_total"], r["acceptance"], r["acceptance_total"]] for r in rs}}
        out.append(item)
        cond = "harness" if m["condition"] == "harness" else "不用 harness"
        vis = "看得到" if item["visible"] else "看不到"
        table.append([m["exp"], m["version"], m["model"], cond, vis, f"{item['unit']}/{item['unit_total']}",
                      f"{pct(item['unit_rate'])} {ci_txt(item['unit_ci'])}", f"{item['acceptance']}/{item['acceptance_total']}",
                      f"{pct(item['acceptance_rate'])} {ci_txt(item['acceptance_ci'])}", f"{pct(mu)}／{pct(ma)}", f"{pct(wu)}／{pct(wa)}",
                      item["minutes"], d])
    summary["devbench_runs"] = out
    md["devbench_runs"] = md_table(["實驗", "版本", "模型", "條件", "官方測試", "單元", "單元通過率 [95% CI]", "驗收",
                                    "驗收通過率 [95% CI]", "每個 repo 的平均 單元／驗收", "行數加權 單元／驗收", "分鐘", "結果目錄"], table)
    # 配對：同一個模型、同樣的測試可見度，harness（最新版本）對不用 harness
    pairs_out, ptable = [], []
    latest = {}
    for it in out:
        key = (it["model"], it["visible"], it["condition"])
        latest.setdefault(key, []).append(it)
    for (model, visible, cond), its in sorted(latest.items()):
        if cond != "harness":
            continue
        bare = latest.get((model, visible, "bare"))
        if not bare:
            continue
        b = bare[-1]
        v4 = [i for i in its if i["version"] == "v4"] or its[-1:]
        for h in v4:
            repos = sorted(set(h["per_repo"]) & set(b["per_repo"]))
            res = {"model": model, "visible": visible, "harness_run": h["run_dir"], "harness_version": h["version"],
                   "bare_run": b["run_dir"]}
            for metric, i in (("unit", 0), ("acceptance", 2)):
                pr = [((h["per_repo"][r][i], h["per_repo"][r][i + 1]), (b["per_repo"][r][i], b["per_repo"][r][i + 1])) for r in repos]
                diff = pooled([p[0] for p in pr]) - pooled([p[1] for p in pr])
                wins = sum(1 for p in pr if p[0][0] > p[1][0])
                losses = sum(1 for p in pr if p[0][0] < p[1][0])
                res[metric] = {"diff": diff, "ci": paired_diff_ci(pr), "wins": wins, "losses": losses,
                               "ties": len(pr) - wins - losses, "sign_p": sign_test(wins, losses)}
            pairs_out.append(res)
            ptable.append([model, "看得到" if visible else "看不到", f"{h['version']}（{h['run_dir'][:13]}）"]
                          + [f"{100 * res[m]['diff']:+.1f} 個百分點 {ci_txt(res[m]['ci'])}；勝 {res[m]['wins']}／負 {res[m]['losses']}"
                             f"／平 {res[m]['ties']}（p={res[m]['sign_p']:.2f}）" for m in ("unit", "acceptance")])
    summary["devbench_harness_vs_bare"] = pairs_out
    md["devbench_harness_vs_bare"] = md_table(["模型", "官方測試", "harness 的那一次", "單元：harness − 不用 harness",
                                               "驗收：harness − 不用 harness"], ptable)
    # 同一個模型、同樣的條件，任兩次之間的差：同一版本重跑（純隨機變異）與不同版本（可能是改動的效果）放在一起看
    vtab, vout = [], []
    by = defaultdict(list)
    for it in out:
        by[(it["model"], it["condition"], it["visible"])].append(it)
    for (model, cond, visible), its in sorted(by.items()):
        for i in range(len(its)):
            for j in range(i + 1, len(its)):
                a, b = its[i], its[j]
                repos = sorted(set(a["per_repo"]) & set(b["per_repo"]))
                res = {"model": model, "condition": cond, "visible": visible, "a": a["run_dir"], "a_version": a["version"],
                       "b": b["run_dir"], "b_version": b["version"], "same_version": a["version"] == b["version"]}
                for metric, k in (("unit", 0), ("acceptance", 2)):
                    pr = [((b["per_repo"][r][k], b["per_repo"][r][k + 1]), (a["per_repo"][r][k], a["per_repo"][r][k + 1])) for r in repos]
                    changed = sum(1 for p_ in pr if p_[0][0] != p_[1][0])
                    res[metric] = {"diff": pooled([p_[0] for p_ in pr]) - pooled([p_[1] for p_ in pr]), "ci": paired_diff_ci(pr),
                                   "repos_changed": changed}
                vout.append(res)
                vtab.append([model, "harness" if cond == "harness" else "不用 harness", "看得到" if visible else "看不到",
                             f"{a['version']}（{a['run_dir'][4:13]}）→ {b['version']}（{b['run_dir'][4:13]}）",
                             "同一版本重跑" if res["same_version"] else "不同版本"]
                            + [f"{100 * res[m]['diff']:+.1f} 個百分點 {ci_txt(res[m]['ci'])}；{res[m]['repos_changed']} 個 repo 有變"
                               for m in ("unit", "acceptance")])
    summary["devbench_run_pairs"] = vout
    md["devbench_run_pairs"] = md_table(["模型", "條件", "官方測試", "比較（前 → 後）", "類型", "單元的差（後 − 前）", "驗收的差（後 − 前）"], vtab)
    # 失敗的類型（單元測試；collect.py 依測試輸出的結尾分類，近似）
    order = ["全部通過", "介面不符", "實作編譯失敗", "缺實作（連結失敗）", "依賴或資料缺少", "邏輯錯誤（斷言失敗）", "其他執行錯誤"]
    fm = defaultdict(lambda: defaultdict(int))
    for r in rows:
        key = f"{r['model'].split(':')[1]} {'harness' if r['condition'] == 'harness' else '不用 harness'}{'・測試可見' if r['visible'] == '1' else ''}"
        fm[key][r.get("unit_failure") or "其他執行錯誤"] += 1
    summary["devbench_unit_failure_modes"] = {k: dict(v) for k, v in fm.items()}
    md["devbench_failure_modes"] = ("單元測試的主要失敗類型（每個 repo、每一次算一筆；依測試輸出的結尾自動分類，近似）。\n\n"
                                    + md_table(["條件（全部版本合併）", "筆數"] + order,
                                               [[k, sum(v.values())] + [v.get(o, 0) for o in order] for k, v in sorted(fm.items())]))
    # 每個 repo
    repos = sorted({r for it in out for r in it["per_repo"]})
    cols = [it for it in out]
    head = ["repo"] + [f"{it['model'].split(':')[1]} {('H' if it['condition'] == 'harness' else 'B')}{it['version']}"
                       f"{'·見' if it['visible'] else ''}" for it in cols]
    rows_ = []
    for r in repos:
        rows_.append([r] + [f"{it['per_repo'][r][0]}/{it['per_repo'][r][1]}・{it['per_repo'][r][2]}/{it['per_repo'][r][3]}"
                            if r in it["per_repo"] else "—" for it in cols])
    md["devbench_per_repo"] = ("每格是「單元 通過/總數・驗收 通過/總數」；H＝harness、B＝不用 harness，v1／v2／v4 是版本，「見」＝官方測試看得到。\n\n"
                               + md_table(head, rows_))


# ---------------------------------------------------------------- 自建 coding 情境
def coding(summary, md):
    rows = read_csv("coding_runs.csv")
    groups = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["condition"], r["version"])].append(r)
    table, out = [], []
    for (model, cond, ver), rs in sorted(groups.items()):
        k, n = sum(int(r["passed"]) for r in rs), len(rs)
        hk = sum(int(r["hidden_tests"]) for r in rs if r["hidden_tests"] != "")
        hn = sum(1 for r in rs if r["hidden_tests"] != "")
        secs = [float(r["seconds"]) for r in rs if r["seconds"] not in ("", None)]
        calls = [float(r["model_calls"]) for r in rs if r["model_calls"] not in ("", None)]
        item = {"model": model, "condition": cond, "version": ver, "passed": k, "n": n, "rate": k / n, "ci": wilson(k, n),
                "hidden_passed": hk, "hidden_n": hn, "hidden_ci": wilson(hk, hn) if hn else None,
                "mean_seconds": sum(secs) / len(secs) if secs else None, "mean_calls": sum(calls) / len(calls) if calls else None}
        out.append(item)
        table.append([model, "harness" if cond == "harness" else "不用 harness", ver, f"{k}/{n}", f"{pct(k / n)} {ci_txt(wilson(k, n))}",
                      (f"{hk}/{hn}（{pct(hk / hn)}）" if hn else "—"),
                      f"{item['mean_seconds']:.0f}" if secs else "—", f"{item['mean_calls']:.0f}" if calls else ("1" if cond == "bare" else "—")])
    summary["coding_groups"] = out
    md["coding_groups"] = md_table(["模型", "條件", "版本", "通過（全部檢查）", "通過率 [Wilson 95% CI]", "hidden tests 通過",
                                    "平均秒數", "平均模型呼叫"], table)
    # v4：harness 對不用 harness（每個情境配對）
    ptab, pout = [], []
    for model in sorted({r["model"] for r in rows}):
        h = [r for r in rows if r["model"] == model and r["condition"] == "harness" and r["version"] == "v4"]
        b = [r for r in rows if r["model"] == model and r["condition"] == "bare"]
        if not h or not b:
            continue
        scen = sorted({r["scenario"] for r in h} & {r["scenario"] for r in b})
        hr = {s: [int(r["passed"]) for r in h if r["scenario"] == s] for s in scen}
        br = {s: [int(r["passed"]) for r in b if r["scenario"] == s] for s in scen}
        hrate = {s: sum(v) / len(v) for s, v in hr.items()}
        brate = {s: sum(v) / len(v) for s, v in br.items()}
        wins = sum(1 for s in scen if hrate[s] > brate[s])
        losses = sum(1 for s in scen if hrate[s] < brate[s])
        hk, hn = sum(sum(v) for v in hr.values()), sum(len(v) for v in hr.values())
        bk, bn = sum(sum(v) for v in br.values()), sum(len(v) for v in br.values())
        item = {"model": model, "scenarios": len(scen), "harness": [hk, hn], "bare": [bk, bn], "wins": wins, "losses": losses,
                "ties": len(scen) - wins - losses, "sign_p": sign_test(wins, losses),
                "per_scenario": {s: {"harness": hr[s], "bare": br[s]} for s in scen}}
        pout.append(item)
        ptab.append([model, len(scen), f"{hk}/{hn}（{pct(hk / hn)}）", f"{bk}/{bn}（{pct(bk / bn)}）",
                     f"{wins}／{losses}／{len(scen) - wins - losses}", f"{item['sign_p']:.3f}"])
    summary["coding_harness_vs_bare"] = pout
    md["coding_harness_vs_bare"] = md_table(["模型", "情境數", "harness v4 通過", "不用 harness 通過", "情境勝／負／平", "符號檢定 p"], ptab)
    # 每個情境
    scen = sorted({r["scenario"] for r in rows})
    cols = [(m, c) for m in sorted({r["model"] for r in rows}) for c in ("harness", "bare")]
    head = ["情境"] + [f"{m.split(':')[1]} {'harness v4' if c == 'harness' else '不用 harness'}" for m, c in cols]
    trs = []
    for s in scen:
        cells = []
        for m, c in cols:
            rs = [r for r in rows if r["scenario"] == s and r["model"] == m and r["condition"] == c and (c == "bare" or r["version"] == "v4")]
            cells.append(f"{sum(int(r['passed']) for r in rs)}/{len(rs)}" if rs else "—")
        trs.append([s] + cells)
    md["coding_per_scenario"] = md_table(head, trs)
    # 失敗的類型（不用 harness）：hidden tests 過了但整個專案的測試沒過＝模型自己寫的測試錯了
    fail = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if r["condition"] != "bare" or r["passed"] == "1":
            continue
        f = fail[r["model"]]
        if r["hidden_tests"] == "0":
            f[0] += 1
        elif r["all_tests"] == "0":
            f[1] += 1
        else:
            f[2] += 1
    summary["coding_bare_failures"] = {m: {"hidden_fail": v[0], "own_tests_fail_only": v[1], "other": v[2]} for m, v in fail.items()}


# ---------------------------------------------------------------- 主對話
def main_session(summary, md):
    rows = read_csv("main_session_runs.csv")
    groups = defaultdict(list)
    for r in rows:
        if r["error"] == "1":
            continue
        groups[(r["suite"], r["version"], r["condition"], r["mode"], r["model"])].append(r)
    table, out = [], []
    for key, rs in sorted(groups.items()):
        suite, ver, cond, mode, model = key
        k, n = sum(int(r["passed"]) for r in rs), len(rs)
        item = {"suite": suite, "version": ver, "condition": cond, "mode": mode, "model": model, "passed": k, "n": n,
                "rate": k / n, "ci": wilson(k, n), "main_calls_mean": sum(int(r["main_calls"]) for r in rs) / n,
                "tool_calls_mean": sum(int(r["tool_calls"]) for r in rs) / n,
                "repeats": sum(int(r["consecutive_repeats"]) for r in rs), "step_limit": sum(int(r["hit_step_limit"]) for r in rs),
                "stuck_stops": sum(int(r["stuck_stop"]) for r in rs), "claim_nudges": sum(int(r["claim_nudges"]) for r in rs)}
        out.append(item)
        table.append([suite, ver, cond, mode, model, f"{k}/{n}", f"{pct(k / n)} {ci_txt(item['ci'])}", f"{item['main_calls_mean']:.1f}",
                      item["repeats"], item["step_limit"], item["stuck_stops"], item["claim_nudges"]])
    summary["main_groups"] = out
    md["main_groups"] = md_table(["情境組", "版本", "把關", "上下文模式", "模型", "通過", "通過率 [Wilson 95% CI]", "每個情境的主模型呼叫",
                                  "連續重複的工具呼叫", "撞到步數上限", "卡住偵測停下", "宣稱完成的提醒"], table)
    # 穩健性：每個實驗、每個情境 × 條件
    rb = [r for r in rows if r["suite"] == "robust" and r["error"] != "1"]
    rout, parts = {}, []
    for exp in sorted({r.get("exp", "E6") for r in rb}):
        er = [r for r in rb if r.get("exp", "E6") == exp]
        conds = list(dict.fromkeys(r["condition"] for r in er))
        scen = sorted({r["scenario"] for r in er})
        head = ["情境"] + [f"{c}：通過" for c in conds] + [f"{c}：主模型呼叫" for c in conds]
        trs = []
        for s_ in scen + ["合計"]:
            pas, calls = [], []
            for cond in conds:
                rs = [r for r in er if r["condition"] == cond and (s_ == "合計" or r["scenario"] == s_)]
                if not rs:
                    pas.append("—")
                    calls.append("—")
                    continue
                k = sum(int(r["passed"]) for r in rs)
                checks = defaultdict(lambda: [0, 0])
                for r in rs:
                    for kv in filter(None, r["checks"].split(";")):
                        name, v = kv.split("=")
                        checks[name][0] += int(v)
                        checks[name][1] += 1
                mc = sum(int(r["main_calls"]) for r in rs) / len(rs)
                rout.setdefault(exp, {}).setdefault(s_, {})[cond] = {
                    "passed": k, "n": len(rs), "ci": wilson(k, len(rs)), "checks": {c: v for c, v in checks.items()},
                    "main_calls_mean": mc, "repeats": sum(int(r["consecutive_repeats"]) for r in rs),
                    "step_limit": sum(int(r["hit_step_limit"]) for r in rs), "stuck_stops": sum(int(r["stuck_stop"]) for r in rs)}
                detail = "" if s_ == "合計" else "（" + "、".join(f"{c} {v[0]}/{v[1]}" for c, v in checks.items()) + "）"
                pas.append(f"{k}/{len(rs)}{detail}" if s_ != "合計" else f"**{k}/{len(rs)}**（{pct(k / len(rs))} {ci_txt(wilson(k, len(rs)))}）")
                calls.append(f"{mc:.1f}")
            trs.append([s_] + pas + calls)
        parts.append(f"**{exp}**\n\n" + md_table(head, trs))
    summary["robust"] = rout
    md["robust"] = "\n\n".join(parts)


def main():
    summary, md = {}, {}
    devbench(summary, md)
    coding(summary, md)
    main_session(summary, md)
    with open(os.path.join(STUDY, "results", "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    for name, text in md.items():
        with open(os.path.join(TABLES, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print("results/summary.json、results/tables/*.md：", "、".join(md))


if __name__ == "__main__":
    main()
