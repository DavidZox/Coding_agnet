"""從 results/tables/*.csv 算出第二次評測的統計：results/summary.json 與 results/tables/*.md（可以直接貼進報告的表格）。

    python3 benchmark_study_2/analysis/analyze.py

統計方法跟第一次研究一樣（只用標準庫，固定亂數種子，可重現）：
- DevBench 的測試通過率：同一個 repo 的測試彼此相關，用「以 repo 為單位重抽樣」的 bootstrap（B=10000）算合併通過率的 95% 區間；
  同一個條件跑了好幾次時，每個 repo 先把幾次的通過數與總數加起來（重抽樣的單位仍然是 repo）。
- 兩個條件的差：同一個 repo 配對，bootstrap 差值的 95% 區間；勝負用符號檢定（雙尾、精確二項，平手不算）。
- SWE-bench 子集：resolved 是每一題對或錯，用 Wilson 95% 區間；兩個條件同一題配對，用精確 McNemar 檢定（只看一對一錯的題目，
  等同符號檢定）。
"""
import csv
import json
import math
import os
import random
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
TABLES = os.path.join(STUDY, "results", "tables")
B = 10000
SEED = 20261009
FAILURE_ORDER = ["全部通過", "介面不符", "實作編譯失敗", "缺實作（連結失敗）", "依賴或資料缺少", "邏輯錯誤（斷言失敗）", "其他執行錯誤"]
SWE_FAILURE_ORDER = ["解決", "沒有改任何東西", "patch 套不上", "改錯地方（沒改到該改的檔案）", "改對檔案但沒修好", "修好了但弄壞既有測試"]


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
    if not groups:
        return (0.0, 0.0)
    rnd, n, vals = random.Random(seed), len(groups), []
    for _ in range(B):
        vals.append(pooled([groups[rnd.randrange(n)] for _ in range(n)]))
    vals.sort()
    return (vals[int(0.025 * B)], vals[int(0.975 * B) - 1])


def paired_diff_ci(pairs, seed=SEED):
    if not pairs:
        return (0.0, 0.0)
    rnd, n, vals = random.Random(seed), len(pairs), []
    for _ in range(B):
        idx = [rnd.randrange(n) for _ in range(n)]
        vals.append(pooled([pairs[i][0] for i in idx]) - pooled([pairs[i][1] for i in idx]))
    vals.sort()
    return (vals[int(0.025 * B)], vals[int(0.975 * B) - 1])


def sign_test(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def pct(x):
    return f"{100 * x:.1f}%"


def ci_txt(ci):
    return f"[{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]"


def pp(x):
    return f"{100 * x:+.1f}"


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


# ---------------------------------------------------------------- DevBench（E8）
CONFIG_ORDER = ["harness：gemma4:26b", "harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker", "harness：Qwen2.5-Coder-32B",
                "不用 harness：gemma4:26b", "不用 harness：Qwen2.5-Coder-32B", "不用 harness：gemma4:e4b", "harness：gemma4:e4b",
                "harness：gemma4:26b（v4.1，C++ 掃描器 bug）", "harness：gemma4:26b（v4.2）", "harness：Qwen2.5-Coder-32B（v4.2）"]


def order_key(cfg):
    return (CONFIG_ORDER.index(cfg) if cfg in CONFIG_ORDER else 99, cfg)


def per_repo(rows, key):
    """rows（同一個條件、可能好幾次）→ {repo: (通過數, 總數)}（幾次加總）。"""
    out = defaultdict(lambda: [0, 0])
    for r in rows:
        out[r["repo"]][0] += int(r[key])
        out[r["repo"]][1] += int(r[f"{key}_total"])
    return {k: tuple(v) for k, v in out.items()}


def devbench(summary, md):
    rows = read_csv("devbench_runs.csv")
    if not rows:
        return
    by_cfg = defaultdict(list)
    for r in rows:
        by_cfg[r["config"]].append(r)
    cfgs = sorted(by_cfg, key=order_key)
    # 每一次（run）的結果
    run_rows, runs_out = [], []
    by_run = defaultdict(list)
    for r in rows:
        by_run[(r["config"], r["run_dir"])].append(r)
    for (cfg, rd), g in sorted(by_run.items(), key=lambda kv: (order_key(kv[0][0]), kv[0][1])):
        ug = [(int(r["unit"]), int(r["unit_total"])) for r in g]
        ag = [(int(r["acceptance"]), int(r["acceptance_total"])) for r in g]
        u, a = pooled(ug), pooled(ag)
        minutes = sum(num(r["minutes"]) for r in g)
        calls = sum(num(r["model_calls"]) for r in g)
        runs_out.append({"config": cfg, "run_dir": rd, "study": int(g[0]["study"]), "repos": len(g), "unit": sum(x[0] for x in ug),
                         "unit_total": sum(x[1] for x in ug), "unit_rate": u, "unit_ci": bootstrap_ci(ug),
                         "acceptance": sum(x[0] for x in ag), "acceptance_total": sum(x[1] for x in ag), "acceptance_rate": a,
                         "acceptance_ci": bootstrap_ci(ag), "minutes": minutes, "model_calls": calls})
        run_rows.append([cfg, rd.replace("../benchmark_study/", "（第一次研究）"), len(g), f"{runs_out[-1]['unit']}/{runs_out[-1]['unit_total']}（{pct(u)}）",
                         f"{runs_out[-1]['acceptance']}/{runs_out[-1]['acceptance_total']}（{pct(a)}）", f"{minutes:.0f}", f"{calls:.0f}" if calls else "—"])
    summary["devbench_runs"] = runs_out
    md["devbench_runs"] = md_table(["條件", "結果目錄", "repo 數", "單元測試", "驗收測試", "總分鐘", "模型呼叫"], run_rows)
    # 每個條件（幾次合併）
    cfg_out, cfg_rows = [], []
    for cfg in cfgs:
        g = by_cfg[cfg]
        nruns = len({r["run_dir"] for r in g})
        ur, ar = per_repo(g, "unit"), per_repo(g, "acceptance")
        ug, ag = list(ur.values()), list(ar.values())
        run_rates = [x["unit_rate"] for x in runs_out if x["config"] == cfg]
        mins = [x["minutes"] / max(1, x["repos"]) for x in runs_out if x["config"] == cfg]
        calls = [x["model_calls"] / max(1, x["repos"]) for x in runs_out if x["config"] == cfg and x["model_calls"]]
        d = {"config": cfg, "runs": nruns, "unit_rate": pooled(ug), "unit_ci": bootstrap_ci(ug), "acceptance_rate": pooled(ag),
             "acceptance_ci": bootstrap_ci(ag), "unit_run_min": min(run_rates), "unit_run_max": max(run_rates),
             "minutes_per_repo": sum(mins) / len(mins), "calls_per_repo": (sum(calls) / len(calls)) if calls else None}
        cfg_out.append(d)
        cfg_rows.append([cfg, nruns, f"{pct(d['unit_rate'])} {ci_txt(d['unit_ci'])}",
                         f"{pct(d['unit_run_min'])}～{pct(d['unit_run_max'])}" if nruns > 1 else "—",
                         f"{pct(d['acceptance_rate'])} {ci_txt(d['acceptance_ci'])}", f"{d['minutes_per_repo']:.1f}",
                         f"{d['calls_per_repo']:.0f}" if d["calls_per_repo"] else "1 個檔案 1 次"])
    summary["devbench_configs"] = cfg_out
    md["devbench_configs"] = md_table(["條件", "次數", "單元測試（95% CI）", "各次的單元通過率", "驗收測試（95% CI）", "每個 repo 的分鐘",
                                       "每個 repo 的模型呼叫"], cfg_rows)
    # 兩兩比較（同一個 repo 配對；幾次合併）
    comps = [("harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker", "harness：gemma4:26b", "換成「coding 很強」的模型組合（同樣用 harness）"),
             ("harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker", "harness：Qwen2.5-Coder-32B", "規劃換成 R1（worker 一樣是 Qwen）"),
             ("harness：Qwen2.5-Coder-32B", "不用 harness：Qwen2.5-Coder-32B", "Qwen 用 harness 對不用 harness"),
             ("harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker", "不用 harness：Qwen2.5-Coder-32B", "R1＋Qwen 的 harness 對 Qwen 直接寫"),
             ("不用 harness：Qwen2.5-Coder-32B", "不用 harness：gemma4:26b", "不用 harness 時，Qwen 對 gemma4:26b"),
             ("harness：gemma4:26b", "不用 harness：gemma4:26b", "gemma4:26b 用 harness 對不用 harness（含第一次研究）"),
             ("harness：gemma4:26b（v4.2）", "harness：gemma4:26b", "改版：gemma4:26b 的 v4.2 對 v4／v4.1"),
             ("harness：Qwen2.5-Coder-32B（v4.2）", "harness：Qwen2.5-Coder-32B", "改版：Qwen 自己規劃的 v4.2 對 v4.1")]
    comp_out, comp_rows = [], []
    for a, b, label in comps:
        if a not in by_cfg or b not in by_cfg:
            continue
        for key, kname in (("unit", "單元"), ("acceptance", "驗收")):
            ra, rb = per_repo(by_cfg[a], key), per_repo(by_cfg[b], key)
            common = sorted(set(ra) & set(rb))
            pairs = [(ra[k], rb[k]) for k in common if ra[k][1] and rb[k][1]]
            if not pairs:
                continue
            diff = pooled([p[0] for p in pairs]) - pooled([p[1] for p in pairs])
            ci = paired_diff_ci(pairs)
            w = sum(1 for x, y in pairs if x[0] / x[1] > y[0] / y[1])
            l_ = sum(1 for x, y in pairs if x[0] / x[1] < y[0] / y[1])
            t = len(pairs) - w - l_
            p = sign_test(w, l_)
            comp_out.append({"a": a, "b": b, "label": label, "metric": key, "diff": diff, "ci": ci, "wins": w, "losses": l_,
                             "ties": t, "p": p, "repos": len(pairs)})
            comp_rows.append([label, kname, f"{pp(diff)} 個百分點", ci_txt(ci), f"{w}／{l_}／{t}", f"{p:.3f}"])
    summary["devbench_compare"] = comp_out
    md["devbench_compare"] = md_table(["比較（A 對 B）", "測試", "A−B", "95% CI", "repo 勝／負／平", "符號檢定 p"], comp_rows)
    # 失敗類型（單元測試，每個 repo、每一次一筆）
    fm = {}
    for cfg in cfgs:
        c = Counter(r["unit_failure"] for r in by_cfg[cfg])
        fm[cfg] = {k: c.get(k, 0) for k in FAILURE_ORDER}
    summary["devbench_unit_failure_modes"] = fm
    md["devbench_failure_modes"] = md_table(["條件"] + FAILURE_ORDER, [[cfg] + [fm[cfg][k] for k in FAILURE_ORDER] for cfg in cfgs])
    # 每個 repo（每個條件幾次合併的單元通過率）
    repos = sorted({r["repo"] for r in rows})
    pr = []
    for repo in repos:
        line = [repo]
        for cfg in cfgs:
            u = per_repo([r for r in by_cfg[cfg] if r["repo"] == repo], "unit").get(repo)
            line.append(f"{u[0]}/{u[1]}" if u else "—")
        pr.append(line)
    md["devbench_per_repo"] = md_table(["repo"] + cfgs, pr)
    # 時間花在哪裡（第二次研究的 harness：規劃與 worker 的呼叫、秒數、換模型的載入時間）
    tr = []
    for cfg in cfgs:
        g = [r for r in by_cfg[cfg] if r.get("plan_calls") not in (None, "") and r["condition"] == "harness"]
        if not g:
            continue
        tot = {k: sum(num(r.get(k)) for r in g) for k in ("plan_calls", "plan_seconds", "worker_calls", "worker_seconds", "load_seconds",
                                                          "plan_warnings", "items")}
        n = len(g)
        tr.append([cfg, n, f"{tot['plan_calls'] / n:.1f}", f"{tot['plan_seconds'] / n / 60:.1f}", f"{tot['worker_calls'] / n:.1f}",
                   f"{tot['worker_seconds'] / n / 60:.1f}", f"{tot['load_seconds'] / n:.0f}", f"{tot['items'] / n:.1f}",
                   f"{sum(1 for r in g if num(r.get('plan_warnings')) > 0)}/{n}"])
    summary["devbench_behavior"], md["devbench_behavior"] = behavior_table(by_cfg, cfgs)
    summary["devbench_edit_waste"], md["devbench_edit_waste"] = edit_waste_table(by_cfg, cfgs)
    if tr:
        md["devbench_time_split"] = md_table(["條件", "job 數", "規劃呼叫", "規劃分鐘", "worker 呼叫", "worker 分鐘", "載入模型秒數", "計畫項數",
                                              "計畫被程式修補"], tr)


def behavior_table(rows_by_cfg, cfgs):
    """worker 的行為指標（每個 job 的平均；工具錯誤率＝錯誤÷工具呼叫）：比較不同模型照格式、用工具穩不穩。"""
    out, data = [], {}
    for cfg in cfgs:
        g = [r for r in rows_by_cfg[cfg] if r["condition"] == "harness" and r.get("steps") not in (None, "")]
        if not g:
            continue
        n = len(g)
        t = {k: sum(num(r.get(k)) for r in g) for k in ("steps", "tool_calls", "tool_errors", "verify_pass", "verify_fail", "stuck_workers",
                                                      "blank_replies", "no_change_claims", "worker_retries")}
        data[cfg] = dict(t, jobs=n)
        out.append([cfg, n, f"{t['steps'] / n:.1f}", f"{t['tool_calls'] / n:.1f}", pct(t["tool_errors"] / max(1, t["tool_calls"])),
                    f"{t['verify_fail'] / n:.1f}", f"{t['stuck_workers'] / n:.2f}", f"{t['blank_replies'] / n:.2f}",
                    f"{t['no_change_claims'] / n:.2f}", f"{t['worker_retries'] / n:.2f}"])
    return data, md_table(["條件", "job 數", "worker 步數", "工具呼叫", "工具錯誤率", "驗證失敗", "卡住被結束的 worker", "空白回覆",
                           "沒改檔案就回報完成", "換新 worker 重試"], out)


def edit_waste_table(rows_by_cfg, cfgs):
    """寫檔的白工：空轉（內容通道送回跟檔案一模一樣的內容）、SEARCH 對不上原文（其中最像的段落在第 800 行之後、
    或檔案裡找不到相似的段落）。每次至少花掉兩次模型呼叫（決策＋內容通道），所以「佔模型呼叫」＝2×次數÷模型呼叫，是下限。"""
    out, data = [], {}
    for cfg in cfgs:
        g = [r for r in rows_by_cfg[cfg] if r["condition"] == "harness" and r.get("steps") not in (None, "")]
        if not g:
            continue
        n = len(g)
        t = {k: sum(num(r.get(k)) for r in g) for k in ("noop_edits", "search_mismatch", "search_beyond_800", "search_no_similar",
                                                      "model_calls")}
        data[cfg] = dict(t, jobs=n)
        calls = max(1, t["model_calls"])
        out.append([cfg, n, f"{t['noop_edits']:.0f}", pct(2 * t["noop_edits"] / calls), f"{t['search_mismatch']:.0f}",
                    f"{t['search_beyond_800']:.0f}", f"{t['search_no_similar']:.0f}", pct(2 * t["search_mismatch"] / calls)])
    return data, md_table(["條件", "job 數", "空轉（內容一模一樣）", "空轉佔模型呼叫（下限）", "SEARCH 對不上", "其中目標在第 800 行之後",
                           "其中找不到相似的段落", "SEARCH 對不上佔模型呼叫（下限）"], out)


# ---------------------------------------------------------------- SWE-bench 子集（E9）
def swebench(summary, md):
    rows = read_csv("swebench_runs.csv")
    if not rows:
        return
    by_cfg = defaultdict(list)
    for r in rows:
        by_cfg[r["config"]].append(r)
    cfgs = sorted(by_cfg, key=order_key)
    out, trows = [], []
    for cfg in cfgs:
        g = by_cfg[cfg]
        k, n = sum(int(r["resolved"]) for r in g), len(g)
        d = {"config": cfg, "resolved": k, "n": n, "rate": k / n if n else 0, "ci": wilson(k, n),
             "by_lang": {}, "minutes_mean": sum(num(r["minutes"]) for r in g) / n,
             "calls_mean": (sum(num(r["model_calls"]) for r in g) / n) if any(r["model_calls"] for r in g) else None,
             "touched_gold": sum(int(r["touched_gold_file"]) for r in g), "empty": sum(int(r["empty_patch"]) for r in g),
             "viewed_gold": sum(int(r["viewed_gold_file"]) for r in g if r.get("viewed_gold_file") not in (None, "")),
             "failures": dict(Counter(r["failure"] for r in g))}
        for lang in ("Python", "C", "C++"):
            gl = [r for r in g if r["lang"] == lang]
            if gl:
                d["by_lang"][lang] = [sum(int(r["resolved"]) for r in gl), len(gl)]
        out.append(d)
        langs = "；".join(f"{l} {v[0]}/{v[1]}" for l, v in d["by_lang"].items())
        viewed = f"{d['viewed_gold']}/{n}" if g[0]["condition"] == "harness" else "—"
        trows.append([cfg, f"{k}/{n}（{pct(d['rate'])}）", ci_txt(d["ci"]), langs, viewed, f"{d['touched_gold']}/{n}", f"{d['empty']}/{n}",
                      f"{d['minutes_mean']:.1f}", f"{d['calls_mean']:.0f}" if d["calls_mean"] else "1"])
    summary["swebench_configs"] = out
    md["swebench_configs"] = md_table(["條件", "resolved", "95% CI（Wilson）", "各語言", "看過該改的檔案", "改到該改的檔案", "沒有改任何東西", "每題分鐘",
                                       "每題模型呼叫"], trows)
    # 失敗類型
    md["swebench_failures"] = md_table(["條件"] + SWE_FAILURE_ORDER,
                                       [[d["config"]] + [d["failures"].get(k, 0) for k in SWE_FAILURE_ORDER] for d in out])
    # 每一題
    insts = sorted({r["instance"] for r in rows}, key=lambda x: ({"Python": 0, "C": 1, "C++": 2}.get(
        next(r["lang"] for r in rows if r["instance"] == x), 3), x))
    cell = {(r["config"], r["instance"]): r for r in rows}
    per = []
    for iid in insts:
        r0 = next(r for r in rows if r["instance"] == iid)
        line = [iid, r0["lang"], r0["difficulty"] or "—"]
        for cfg in cfgs:
            r = cell.get((cfg, iid))
            line.append("—" if not r else ("✅" if r["resolved"] == "1" else ("∅" if r["empty_patch"] == "1" else
                                                                            ("○" if r["touched_gold_file"] == "1" else "✗"))))
        per.append(line)
    md["swebench_per_instance"] = md_table(["題目", "語言", "難度"] + cfgs, per) + \
        "\n\n✅ 解決；○ 改到該改的檔案但沒有通過評分測試；✗ 改了別的檔案；∅ 沒有改任何東西"
    # 配對比較（同一題）
    comps = [("harness：gemma4:26b", "不用 harness：gemma4:26b", "gemma4:26b：harness 對不用 harness"),
             ("harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker", "不用 harness：Qwen2.5-Coder-32B", "R1＋Qwen 的 harness 對 Qwen 直接寫"),
             ("harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker", "harness：gemma4:26b", "R1＋Qwen 對 gemma4:26b（都用 harness）"),
             ("harness：Qwen2.5-Coder-32B", "不用 harness：Qwen2.5-Coder-32B", "Qwen：harness 對不用 harness"),
             ("harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker", "harness：Qwen2.5-Coder-32B", "規劃換成 R1（worker 一樣是 Qwen）"),
             ("不用 harness：Qwen2.5-Coder-32B", "不用 harness：gemma4:26b", "不用 harness：Qwen 對 gemma4:26b"),
             ("harness：gemma4:26b（v4.2）", "harness：gemma4:26b", "改版：gemma4:26b 的 v4.2 對 v4.1／v4.1.1"),
             ("harness：gemma4:26b（v4.2）", "不用 harness：gemma4:26b", "gemma4:26b：v4.2 的 harness 對不用 harness")]
    cr, co = [], []
    for a, b, label in comps:
        if a not in by_cfg or b not in by_cfg:
            continue
        ra = {r["instance"]: int(r["resolved"]) for r in by_cfg[a]}
        rb = {r["instance"]: int(r["resolved"]) for r in by_cfg[b]}
        common = sorted(set(ra) & set(rb))
        w = sum(1 for i in common if ra[i] and not rb[i])
        l_ = sum(1 for i in common if rb[i] and not ra[i])
        both = sum(1 for i in common if ra[i] and rb[i])
        p = sign_test(w, l_)
        co.append({"a": a, "b": b, "label": label, "n": len(common), "a_only": w, "b_only": l_, "both": both, "p": p,
                   "a_rate": sum(ra[i] for i in common) / max(1, len(common)), "b_rate": sum(rb[i] for i in common) / max(1, len(common))})
        cr.append([label, len(common), f"{sum(ra[i] for i in common)}／{sum(rb[i] for i in common)}", f"{w}／{l_}", both, f"{p:.3f}"])
    # 依難度（只有 Verified 的 Python 題目有人工標註）與語言分組
    groups = [("Python：<15 分鐘", lambda r: r["lang"] == "Python" and r["difficulty"] == "<15 min fix"),
              ("Python：15 分鐘～1 小時", lambda r: r["lang"] == "Python" and r["difficulty"] == "15 min - 1 hour"),
              ("Python：1 小時以上", lambda r: r["lang"] == "Python" and r["difficulty"] in ("1-4 hours", ">4 hours")),
              ("C", lambda r: r["lang"] == "C"), ("C++", lambda r: r["lang"] == "C++")]
    grows, gsum = [], {}
    for gname, pred in groups:
        line = [gname]
        for cfg in cfgs:
            g = [r for r in by_cfg[cfg] if pred(r)]
            line.append(f"{sum(int(r['resolved']) for r in g)}/{len(g)}" if g else "—")
            if g:
                gsum.setdefault(gname, {})[cfg] = [sum(int(r["resolved"]) for r in g), len(g)]
        grows.append(line)
    summary["swebench_by_group"] = gsum
    md["swebench_by_group"] = md_table(["題目（難度依 Verified 的人工標註：修正大約要花多久）"] + cfgs, grows)
    summary["swebench_behavior"], md["swebench_behavior"] = behavior_table(by_cfg, cfgs)
    summary["swebench_edit_waste"], md["swebench_edit_waste"] = edit_waste_table(by_cfg, cfgs)
    tr = []
    for cfg in cfgs:
        g = [r for r in by_cfg[cfg] if r["condition"] == "harness" and r.get("plan_calls") not in (None, "")]
        if g:
            n = len(g)
            tot = {k: sum(num(r.get(k)) for r in g) for k in ("plan_calls", "plan_seconds", "worker_calls", "worker_seconds", "load_seconds", "items")}
            tr.append([cfg, n, f"{tot['plan_calls'] / n:.1f}", f"{tot['plan_seconds'] / n / 60:.1f}", f"{tot['worker_calls'] / n:.1f}",
                       f"{tot['worker_seconds'] / n / 60:.1f}", f"{tot['load_seconds'] / n:.0f}", f"{tot['items'] / n:.1f}",
                       f"{sum(1 for r in g if num(r.get('plan_warnings')) > 0)}/{n}"])
    if tr:
        md["swebench_time_split"] = md_table(["條件", "題數", "規劃呼叫", "規劃分鐘", "worker 呼叫", "worker 分鐘", "載入模型秒數", "計畫項數",
                                              "計畫被程式修補"], tr)
    # patch 的大小（原始碼／測試分開）與參考解答比較；harness 自己的整體驗證跟官方結果一不一致
    import json as _json
    gold = {}
    gpath = os.path.join(STUDY, "datasets", "swebench_subset", "instances.json")
    if os.path.exists(gpath):
        with open(gpath, encoding="utf-8") as f:
            for inst in _json.load(f):
                src = sum(1 for l in inst["patch"].splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))
                gold[inst["instance_id"]] = src
    prow = []
    for cfg in cfgs:
        g = [r for r in by_cfg[cfg] if r["empty_patch"] == "0"]
        if not g:
            continue
        med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0   # noqa: E731
        prow.append([cfg, len(g), med([int(r["src_lines"]) for r in g]), med([gold.get(r["instance"], 0) for r in g]),
                     med([int(r["test_lines"]) for r in g]), f"{sum(1 for r in g if int(r['new_test_files']) > 0)}/{len(g)}",
                     f"{sum(1 for r in g if int(r.get('new_root_files') or 0) > 0)}/{len(g)}"])
    md["swebench_patch_size"] = md_table(["條件", "有改東西的題數", "原始碼改的行數（中位數）", "參考解答（同幾題的中位數）", "測試改的行數（中位數）",
                                          "新增測試檔的題數", "在專案根目錄留下新檔案的題數"], prow)
    vrow = []
    for cfg in cfgs:
        g = [r for r in by_cfg[cfg] if r.get("final_ok") not in (None, "")]
        if not g:
            continue
        a = sum(1 for r in g if r["final_ok"] == "1" and r["resolved"] == "1")
        b = sum(1 for r in g if r["final_ok"] == "1" and r["resolved"] == "0")
        c = sum(1 for r in g if r["final_ok"] == "0" and r["resolved"] == "1")
        d = sum(1 for r in g if r["final_ok"] == "0" and r["resolved"] == "0")
        z = sum(1 for r in g if r["final_ok"] == "1" and r.get("final_no_tests") == "1")
        vrow.append([cfg, len(g), a, b, c, d, z, f"{a}/{a + b}" if a + b else "—", f"{d}/{c + d}" if c + d else "—"])
    if vrow:
        md["swebench_self_verify"] = md_table(["條件", "題數", "自己驗證通過、官方也解決", "自己驗證通過、官方沒解決", "自己驗證沒過、官方解決",
                                               "都沒過", "通過的題目中沒有跑到任何測試", "「通過」可信的比例", "「沒過」可信的比例"], vrow)
    summary["swebench_compare"] = co
    md["swebench_compare"] = md_table(["比較（A 對 B）", "題數", "A／B 解決", "只有 A 解決／只有 B 解決", "都解決", "McNemar p"], cr)


def main():
    global TABLES
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default=TABLES, help="表格的目錄（summary.json 寫在它的上一層）")
    TABLES = ap.parse_args().tables
    summary, md = {}, {}
    devbench(summary, md)
    swebench(summary, md)
    with open(os.path.join(os.path.dirname(TABLES), "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    for name, text in md.items():
        with open(os.path.join(TABLES, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print("summary.json；tables：", "、".join(f"{n}.md" for n in md))


if __name__ == "__main__":
    main()
