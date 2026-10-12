"""從 results/summary.json 畫報告用的圖（SVG，只用標準庫）：results/figures/*.svg。

    python3 benchmark_study_3/analysis/figures.py

畫圖的函式沿用第二次研究（benchmark_study_2/analysis/figures.py）。SVG 用系統的 Noto Sans CJK TC 顯示中文。
"""
import json
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
OUT = os.environ.get("S3_FIGURES") or os.path.join(STUDY, "results", "figures")
SUMMARY = os.environ.get("S3_SUMMARY") or os.path.join(STUDY, "results", "summary.json")
FONT = "Noto Sans CJK TC, Noto Sans CJK, Microsoft JhengHei, sans-serif"
COLORS = ["#a0aec0", "#2b6cb0", "#dd6b20", "#38a169", "#805ad5", "#d53f8c"]
DOMAINS = ["fs", "docker", "ros2", "handshake", "complex"]
DOMAIN_NAME = {"fs": "目錄與文件", "docker": "Docker", "ros2": "ROS 2", "handshake": "調度交握", "complex": "複合任務"}
MODELS = ["gemma4:26b", "gemma4:e4b"]
VERSIONS = ["v4.2", "v5"]


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




def _rate(b):
    return 100 * b["rate"], (100 * b["ci"][0], 100 * b["ci"][1])


def main():
    with open(SUMMARY, encoding="utf-8") as f:
        S = json.load(f)
    os.makedirs(OUT, exist_ok=True)
    made = []
    ops = S.get("ops", {})
    for st, title in (("main", "非編碼情境（主要組 50 個）"), ("holdout", "非編碼情境（保留組 20 個）")):
        block = ops.get(st) or {}
        for model in MODELS:
            m = block.get(model) or {}
            if not any(v in m for v in VERSIONS):
                continue
            cats = [DOMAIN_NAME[d] for d in DOMAINS] + ["全部"]
            series = []
            for ver in VERSIONS:
                if ver not in m:
                    continue
                vals, errs = [], []
                for d in DOMAINS:
                    b = (m[ver].get("domains") or {}).get(d)
                    if b:
                        v, e = _rate(b)
                        vals.append(v)
                        errs.append(e)
                    else:
                        vals.append(None)
                        errs.append(None)
                v, e = _rate(m[ver])
                vals.append(v)
                errs.append(e)
                series.append((f"{ver}", vals, errs))
            path = os.path.join(OUT, f"ops_{st}_{model.replace(':', '-')}.svg")
            bar_chart(path, f"{title}：{model} 的通過率", cats, series, note="誤差線：Wilson 95% 區間（所有執行合併）")
            made.append(path)
    sp = S.get("small_projects", {})
    for model in MODELS:
        cats, series = [], {ver: ([], []) for ver in VERSIONS}
        for fam, name in (("bf", "BF 修 bug"), ("fe", "FE 補功能"), ("ap", "AP 練習題")):
            m = (sp.get(fam) or {}).get(model) or {}
            if not any(v in m for v in VERSIONS):
                continue
            cats.append(name)
            for ver in VERSIONS:
                if ver in m:
                    v, e = _rate(m[ver])
                    series[ver][0].append(v)
                    series[ver][1].append(e)
                else:
                    series[ver][0].append(None)
                    series[ver][1].append(None)
        if cats:
            path = os.path.join(OUT, f"sp_resolved_{model.replace(':', '-')}.svg")
            bar_chart(path, f"小專案：{model} 的解決率", cats, [(ver, series[ver][0], series[ver][1]) for ver in VERSIONS],
                      ylabel="解決率（%）", note="誤差線：Wilson 95% 區間")
            made.append(path)
        tw = (sp.get("tw") or {}).get(model) or {}
        if any(v in tw for v in VERSIONS):
            cats = ["測試全過（%）", "行覆蓋率", "分支覆蓋率", "突變分數"]
            ser = []
            for ver in VERSIONS:
                if ver not in tw:
                    continue
                t = tw[ver]
                ser.append((ver, [100 * t["tests_ok"]["rate"], t["line_cov_mean"], t["branch_cov_mean"], t["mut_score_mean"]], None))
            path = os.path.join(OUT, f"sp_tw_{model.replace(':', '-')}.svg")
            bar_chart(path, f"寫測試（TW 18 題）：{model}", cats, ser, ylabel="%（各題平均）", note="覆蓋率只算正式程式；突變分數＝改壞一處、測試抓得到的比例")
            made.append(path)
    print("\n".join(made))


if __name__ == "__main__":
    main()
