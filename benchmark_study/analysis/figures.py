"""從 results/summary.json 畫報告用的圖（SVG，只用標準庫）：results/figures/*.svg。

    python3 benchmark_study/analysis/figures.py

SVG 用系統的 Noto Sans CJK TC 顯示中文；瀏覽器、VS Code 的 Markdown 預覽與 build_reports.py 產生的 PDF 都看得到。
"""
import json
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
OUT = os.path.join(STUDY, "results", "figures")
FONT = "Noto Sans CJK TC, Noto Sans CJK, Microsoft JhengHei, sans-serif"
COLORS = ["#2b6cb0", "#dd6b20", "#38a169", "#805ad5", "#d53f8c", "#718096"]


def bar_chart(path, title, cats, series, ylabel="通過率（%）", ymax=100, note="", width=None, height=420, font=12):
    """cats：x 軸的類別；series：[(名稱, 值 list(0~100), 誤差 list[(低, 高)] 或 None)]。"""
    n_cat, n_ser = len(cats), len(series)
    longest = max((len(ln) for c in cats for ln in c.split("\n")), default=4)
    group_w = max(70, 26 * n_ser + 30, int(font * 0.62 * longest) + 24)
    left, right, top, bottom = 70, 20, 60, 70 + (font + 3) * max(len(c.split("\n")) for c in cats)
    width = width or left + right + group_w * n_cat
    plot_h = height - top - bottom
    bar_w = (group_w - 24) / n_ser
    y = lambda v: top + plot_h * (1 - min(max(v, 0), ymax) / ymax)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
         f'font-family="{FONT}" font-size="{font}">', '<rect width="100%" height="100%" fill="white"/>',
         f'<text x="{width / 2}" y="24" text-anchor="middle" font-size="{font + 5}" font-weight="bold">{escape(title)}</text>']
    for t in range(0, ymax + 1, 20 if ymax >= 60 else 10):
        s.append(f'<line x1="{left}" y1="{y(t)}" x2="{width - right}" y2="{y(t)}" stroke="#e2e8f0"/>')
        s.append(f'<text x="{left - 8}" y="{y(t) + 4}" text-anchor="end" fill="#4a5568">{t}</text>')
    s.append(f'<text x="18" y="{top + plot_h / 2}" transform="rotate(-90 18 {top + plot_h / 2})" text-anchor="middle" '
             f'fill="#4a5568">{escape(ylabel)}</text>')
    for i, cat in enumerate(cats):
        gx = left + i * group_w + 12
        for j, (name, vals, errs) in enumerate(series):
            v = vals[i]
            if v is None:
                continue
            x = gx + j * bar_w
            s.append(f'<rect x="{x:.1f}" y="{y(v):.1f}" width="{bar_w - 4:.1f}" height="{y(0) - y(v):.1f}" fill="{COLORS[j % len(COLORS)]}"/>')
            s.append(f'<text x="{x + (bar_w - 4) / 2:.1f}" y="{y(v) - 4:.1f}" text-anchor="middle" font-size="{font - 2}">{v:.0f}</text>')
            if errs and errs[i]:
                lo, hi = errs[i]
                cx = x + (bar_w - 4) / 2
                s.append(f'<line x1="{cx:.1f}" y1="{y(lo):.1f}" x2="{cx:.1f}" y2="{y(hi):.1f}" stroke="#1a202c" stroke-width="1.2"/>')
                for yy in (lo, hi):
                    s.append(f'<line x1="{cx - 4:.1f}" y1="{y(yy):.1f}" x2="{cx + 4:.1f}" y2="{y(yy):.1f}" stroke="#1a202c" stroke-width="1.2"/>')
        lines = cat.split("\n")
        for k, ln in enumerate(lines):
            s.append(f'<text x="{gx + (group_w - 24) / 2:.1f}" y="{top + plot_h + 18 + (font + 3) * k}" text-anchor="middle" '
                     f'font-size="{font - 1}">{escape(ln)}</text>')
    lx = left
    for j, (name, _, _) in enumerate(series):
        s.append(f'<rect x="{lx}" y="{height - 34}" width="12" height="12" fill="{COLORS[j % len(COLORS)]}"/>')
        s.append(f'<text x="{lx + 16}" y="{height - 24}">{escape(name)}</text>')
        lx += 30 + 13 * len(name)
    if note:
        s.append(f'<text x="{width - right}" y="{height - 8}" text-anchor="end" font-size="10" fill="#718096">{escape(note)}</text>')
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(s))


def stacked_chart(path, title, cats, stacks, note="", height=440):
    """cats：類別；stacks：[(名稱, 顏色, 每個類別的百分比 list)]，由下往上疊。"""
    left, right, top, bottom = 70, 230, 60, 90
    group_w = 120
    width = left + right + group_w * len(cats)
    plot_h = height - top - bottom
    y = lambda v: top + plot_h * (1 - v / 100)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
         f'font-family="{FONT}" font-size="12">', '<rect width="100%" height="100%" fill="white"/>',
         f'<text x="{(width - right) / 2 + 20}" y="24" text-anchor="middle" font-size="16" font-weight="bold">{escape(title)}</text>']
    for t in range(0, 101, 20):
        s.append(f'<line x1="{left}" y1="{y(t)}" x2="{width - right}" y2="{y(t)}" stroke="#e2e8f0"/>')
        s.append(f'<text x="{left - 8}" y="{y(t) + 4}" text-anchor="end" fill="#4a5568">{t}%</text>')
    for i, cat in enumerate(cats):
        x, base = left + i * group_w + 20, 0
        for name, color, vals in stacks:
            v = vals[i]
            if v <= 0:
                continue
            s.append(f'<rect x="{x}" y="{y(base + v):.1f}" width="{group_w - 40}" height="{y(base) - y(base + v):.1f}" fill="{color}"/>')
            if v >= 7:
                s.append(f'<text x="{x + (group_w - 40) / 2}" y="{y(base + v / 2) + 4:.1f}" text-anchor="middle" font-size="10" '
                         f'fill="white">{v:.0f}%</text>')
            base += v
        for k, ln in enumerate(cat.split("\n")):
            s.append(f'<text x="{x + (group_w - 40) / 2}" y="{top + plot_h + 18 + 14 * k}" text-anchor="middle" font-size="11">{escape(ln)}</text>')
    ly = top
    for name, color, _ in reversed(stacks):
        s.append(f'<rect x="{width - right + 20}" y="{ly}" width="12" height="12" fill="{color}"/>')
        s.append(f'<text x="{width - right + 38}" y="{ly + 10}">{escape(name)}</text>')
        ly += 20
    if note:
        s.append(f'<text x="{width - 10}" y="{height - 8}" text-anchor="end" font-size="10" fill="#718096">{escape(note)}</text>')
    s.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(s))


def short(model):
    return model.split(":")[-1]


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(STUDY, "results", "summary.json"), encoding="utf-8") as f:
        sm = json.load(f)
    made = []
    # F1：DevBench 各條件的單元／驗收通過率（bootstrap 95% CI）
    runs = sm.get("devbench_runs") or []
    if runs:
        cats, u, uc, a, ac = [], [], [], [], []
        for r in runs:
            cond = "harness" if r["condition"] == "harness" else "不用 harness"
            cats.append(f"{short(r['model'])}\n{cond}\n{r['version'] if r['condition'] == 'harness' else '—'}\n"
                        f"{'測試看得到' if r['visible'] else '看不到測試'}\n{r['run_dir'][4:8]}-{r['run_dir'][9:13]}")
            u.append(100 * r["unit_rate"])
            uc.append([100 * x for x in r["unit_ci"]])
            a.append(100 * r["acceptance_rate"])
            ac.append([100 * x for x in r["acceptance_ci"]])
        bar_chart(os.path.join(OUT, "devbench_overview.svg"), "DevBench（12 個 repo）：官方測試的通過率",
                  cats, [("單元測試", u, uc), ("驗收測試", a, ac)], note="誤差線：以 repo 為單位重抽樣的 95% bootstrap 信賴區間",
                  height=600, font=15)
        made.append("devbench_overview.svg")
    # F2：自建情境 harness 對不用 harness
    pairs = sm.get("coding_harness_vs_bare") or []
    if pairs:
        from math import sqrt   # noqa: F401

        def wil(k, n, z=1.96):
            if not n:
                return (0, 0)
            p = k / n
            d = 1 + z * z / n
            c = (p + z * z / (2 * n)) / d
            h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
            return (100 * max(0, c - h), 100 * min(1, c + h))
        cats = [short(p["model"]) for p in pairs]
        hv = [100 * p["harness"][0] / p["harness"][1] for p in pairs]
        bv = [100 * p["bare"][0] / p["bare"][1] for p in pairs]
        bar_chart(os.path.join(OUT, "coding_harness_vs_bare.svg"), "自建 14 個情境：harness 對「不用 harness」",
                  cats, [("harness v4", hv, [wil(*p["harness"]) for p in pairs]), ("不用 harness（一次輸出）", bv, [wil(*p["bare"]) for p in pairs])],
                  note="誤差線：Wilson 95% 信賴區間；全部檢查（hidden tests＋整個專案的測試＋其他條件）都過才算通過", width=520)
        made.append("coding_harness_vs_bare.svg")
    # F3：穩健性情境（E6：v4 的把關開／關；E7：v4.1、v4 的規則、全部關閉），每個情境與合計的通過率、主模型呼叫
    rb = sm.get("robust") or {}
    for exp, data in sorted(rb.items()):
        scen = [x for x in sorted(data) if x != "合計"] + (["合計"] if "合計" in data else [])
        conds = list(dict.fromkeys(c for x in scen for c in data[x]))
        series, calls = [], []
        for c in conds:
            vals = [100 * data[x][c]["passed"] / data[x][c]["n"] if c in data[x] else None for x in scen]
            errs = [[100 * v for v in data[x][c]["ci"]] if c in data[x] else None for x in scen]
            series.append((c, vals, errs))
            calls.append((c, [data[x][c]["main_calls_mean"] if c in data[x] else None for x in scen], None))
        n = max(data[x][c]["n"] for x in scen for c in data[x] if x != "合計")
        labels = [x.replace("robust_", "") for x in scen]
        bar_chart(os.path.join(OUT, f"robust_{exp}.svg"), f"主對話的穩健性情境（{exp}，e4b，每格 {n} 次）：通過率",
                  labels, series, note="誤差線：Wilson 95% 信賴區間", width=max(640, 110 * len(labels) + 120))
        top = max([v for _, vs, _ in calls for v in vs if v] + [1])
        bar_chart(os.path.join(OUT, f"robust_{exp}_calls.svg"), f"穩健性情境（{exp}）：每個情境的主模型呼叫次數（越少越省）",
                  labels, calls, ylabel="主模型呼叫（次）", ymax=int(top + 4 - top % 2), width=max(640, 110 * len(labels) + 120))
        made += [f"robust_{exp}.svg", f"robust_{exp}_calls.svg"]
    # F4：主對話 14 個情境的通過率（各版本）
    mg = [g for g in sm.get("main_groups") or [] if g["suite"] == "main" and g["n"] >= 14]
    if mg:
        cats = [f"{g['version']}\n{g['mode']}・{short(g['model'])}" for g in mg]
        bar_chart(os.path.join(OUT, "main_suite.svg"), "主對話 14 個情境（非 coding）：各版本的通過率", cats,
                  [("通過率", [100 * g["rate"] for g in mg], [[100 * x for x in g["ci"]] for g in mg])],
                  note="誤差線：Wilson 95% 信賴區間")
        made.append("main_suite.svg")
    # F5：DevBench 單元測試的失敗類型（每個 repo、每一次一筆）
    fm = sm.get("devbench_unit_failure_modes") or {}
    if fm:
        order = [("全部通過", "#38a169"), ("介面不符", "#e53e3e"), ("實作編譯失敗", "#dd6b20"), ("缺實作（連結失敗）", "#d69e2e"),
                 ("依賴或資料缺少", "#805ad5"), ("邏輯錯誤（斷言失敗）", "#3182ce"), ("其他執行錯誤", "#a0aec0")]
        cats = sorted(fm)
        stacks = [(name, color, [100 * fm[c].get(name, 0) / max(1, sum(fm[c].values())) for c in cats]) for name, color in order]
        stacked_chart(os.path.join(OUT, "devbench_failure_modes.svg"), "DevBench 單元測試：每個 repo 的主要失敗類型",
                      [c.replace(" ", "\n", 1) for c in cats], stacks, note="依測試輸出的結尾自動分類（近似）；全部版本合併")
        made.append("devbench_failure_modes.svg")
    print("results/figures：", "、".join(made))


if __name__ == "__main__":
    main()
