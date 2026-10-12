"""從 results/summary.json 畫報告用的圖（SVG，只用標準庫）：results/figures/*.svg。

    python3 benchmark_study_2/analysis/figures.py

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




def label(cfg):
    """條件名稱 → 圖上分行的標籤。"""
    cfg = cfg.replace("harness：", "harness\n").replace("不用 harness：", "不用 harness\n")
    return cfg.replace(" 規劃＋", " 規劃\n＋").replace(" worker", "").replace("（v4.2）", "\n（v4.2）")


def main():
    global OUT
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default=os.path.join(STUDY, "results", "summary.json"))
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    OUT = args.out
    os.makedirs(OUT, exist_ok=True)
    with open(args.summary, encoding="utf-8") as f:
        sm = json.load(f)
    made = []
    cfgs = sm.get("devbench_configs") or []
    if cfgs:
        bar_chart(os.path.join(OUT, "devbench_configs.svg"), "DevBench（12 個 repo，從規格從零寫）：各模型組合的官方測試通過率",
                  [label(c["config"]) + f"\n（{c['runs']} 次）" for c in cfgs],
                  [("單元測試", [100 * c["unit_rate"] for c in cfgs], [[100 * x for x in c["unit_ci"]] for c in cfgs]),
                   ("驗收測試", [100 * c["acceptance_rate"] for c in cfgs], [[100 * x for x in c["acceptance_ci"]] for c in cfgs])],
                  note="誤差線：以 repo 為單位重抽樣的 95% bootstrap 信賴區間；同一個條件跑好幾次時合併計算", height=560, font=13)
        made.append("devbench_configs.svg")
    fm = sm.get("devbench_unit_failure_modes") or {}
    if fm:
        order = [("全部通過", "#38a169"), ("介面不符", "#e53e3e"), ("實作編譯失敗", "#dd6b20"), ("缺實作（連結失敗）", "#d69e2e"),
                 ("依賴或資料缺少", "#805ad5"), ("邏輯錯誤（斷言失敗）", "#3182ce"), ("其他執行錯誤", "#a0aec0")]
        cats = list(fm)
        stacks = [(name, color, [100 * fm[c].get(name, 0) / max(1, sum(fm[c].values())) for c in cats]) for name, color in order]
        stacked_chart(os.path.join(OUT, "devbench_failure_modes.svg"), "DevBench 單元測試：每個 repo（每一次）的主要失敗類型",
                      [label(c) for c in cats], stacks, note="依測試輸出的結尾自動分類（近似）", height=520)
        made.append("devbench_failure_modes.svg")
    sw = [c for c in sm.get("swebench_configs") or [] if "bug" not in c["config"]]   # 受 C++ 掃描器 bug 影響的 4 題另外列在表裡
    if sw:
        bar_chart(os.path.join(OUT, "swebench_configs.svg"), "SWE-bench 子集（24 題既有專案的 issue）：解決率",
                  [label(c["config"]) for c in sw],
                  [("resolved", [100 * c["rate"] for c in sw], [[100 * x for x in c["ci"]] for c in sw])],
                  note="誤差線：Wilson 95% 信賴區間；官方 swebench 套件計分；v4.1 受 C++ 掃描器 bug 影響的 4 題見表 2", ylabel="解決率（%）", ymax=100, height=520, font=13)
        made.append("swebench_configs.svg")
        order = [("解決", "#38a169"), ("修好了但弄壞既有測試", "#d69e2e"), ("改對檔案但沒修好", "#3182ce"),
                 ("改錯地方（沒改到該改的檔案）", "#e53e3e"), ("patch 套不上", "#805ad5"), ("沒有改任何東西", "#a0aec0")]
        cats = [c["config"] for c in sw]
        stacks = [(name, color, [100 * c["failures"].get(name, 0) / max(1, c["n"]) for c in sw]) for name, color in order]
        stacked_chart(os.path.join(OUT, "swebench_outcomes.svg"), "SWE-bench 子集：每一題的結果類型",
                      [label(c) for c in cats], stacks, note="「改到該改的檔案」＝patch 改到參考解答改的任何一個檔案", height=520)
        made.append("swebench_outcomes.svg")
    bg = sm.get("swebench_by_group") or {}
    if bg:
        groups = list(bg)
        cfg_names = [c["config"] for c in sw if "bug" not in c["config"]]
        series = []
        for cfg in cfg_names:
            vals = [100 * bg[g][cfg][0] / bg[g][cfg][1] if cfg in bg[g] else None for g in groups]
            series.append((label(cfg).replace("\n", " "), vals, None))
        bar_chart(os.path.join(OUT, "swebench_by_group.svg"), "SWE-bench 子集：依難度與語言的解決率",
                  [f"{g}\n（{next(iter(bg[g].values()))[1]} 題）" for g in groups], series,
                  note="難度是 SWE-bench Verified 的人工標註（修正大約要花多久），只有 Python 題目有；每格題數少，只看趨勢", ylabel="解決率（%）",
                  height=480, font=12)
        made.append("swebench_by_group.svg")
    print("results/figures：", "、".join(made))


if __name__ == "__main__":
    main()
