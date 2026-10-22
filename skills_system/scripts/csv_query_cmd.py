"""csv_query：查 CSV／TSV 表格——欄位與筆數、篩選、整體或每一組的最大／最小／平均／總和／筆數、排序；數字由腳本算好。

小模型自己用 host_runcmd 寫 python 單行指令分析資料時常出錯（猜錯欄位名稱、引號跳脫、pandas 沒裝），錯了還會反問使用者
（多步驟維運評測 evals/ops/ 的情境）。這個技能只讀檔：先不帶選項看欄位、型態與前幾筆，再依問題組合選項。
--markdown 把結果排成 Markdown 表格，可以直接用 file_ops 寫進報告。
"""
import csv
import math
import os
import re
import sys

USAGE = ("用法: scripts/csv_query_cmd.py <檔案> [--where 欄位<運算子>值]... [--group 欄位] "
         "[--min 欄位|--max 欄位|--avg 欄位|--sum 欄位|--count] [--sort 欄位 [--desc]] [--head N] [--cols 欄位1,欄位2] [--markdown]\n"
         "  不帶選項：欄位、型態、筆數、數值欄位的範圍、前 5 筆。\n"
         "  --where：運算子 = != < <= > >= ~（~＝包含，不分大小寫），可以重複（全部都要符合）；例：--where robot=tb3 --where battery<25\n"
         "  --min／--max 欄位：最小／最大的那一筆（整筆資料都列出）；加 --group 欄位：每一組各一筆。\n"
         "  --avg／--sum 欄位、--count：整體或每一組（--group）的平均、總和、筆數。\n"
         "  --sort 欄位 [--desc]、--head N：排序後列出前 N 筆（預設 20）。--cols：只列這些欄位。--markdown：結果排成 Markdown 表格。")
MAX_ROWS_SHOWN = 60
_WHERE_RE = re.compile(r"^\s*([^<>=!~]+?)\s*(<=|>=|!=|=|<|>|~)\s*(.*?)\s*$")


def _num(v):
    try:
        x = float(str(v).strip())
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _fmt(v):
    x = _num(v)
    if x is None:
        return str(v)
    return str(int(x)) if x == int(x) and "." not in str(v) else f"{x:.4f}".rstrip("0").rstrip(".")


def _read(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel_tab if path.endswith((".tsv", ".tab")) else csv.excel
        rows = list(csv.reader(f, dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return None, None
    header = [h.strip() for h in rows[0]]
    data = [dict(zip(header, [c.strip() for c in r])) for r in rows[1:]]
    return header, data


def _col(header, name):
    """欄位名稱：完全相同 → 不分大小寫 → 唯一的部分符合。回傳 (欄位, 錯誤)。"""
    if name in header:
        return name, None
    low = [h for h in header if h.lower() == name.lower()]
    if len(low) == 1:
        return low[0], None
    part = [h for h in header if name.lower() in h.lower()]
    if len(part) == 1:
        return part[0], None
    return None, f"[ERROR] 沒有欄位「{name}」。欄位有：{', '.join(header)}"


def _table(header, rows, markdown):
    if markdown:
        out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
        out += ["| " + " | ".join(_fmt(r.get(h, "")) for h in header) + " |" for r in rows]
        return out
    out = [" ｜ ".join(header)]
    out += [" ｜ ".join(_fmt(r.get(h, "")) for h in header) for r in rows]
    return out


def _parse(argv):
    if not argv or argv[0].startswith("--"):
        return None, f"[ERROR] 第一個參數要是檔案路徑。\n{USAGE}"
    o = {"file": argv[0], "where": [], "group": None, "agg": None, "agg_col": None, "sort": None, "desc": False, "head": None,
         "cols": None, "markdown": False}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ("--markdown", "--md"):
            o["markdown"] = True
        elif a == "--desc":
            o["desc"] = True
        elif a == "--count":
            o["agg"] = o["agg"] or "count"
        elif a in ("--where", "--group", "--min", "--max", "--avg", "--sum", "--sort", "--head", "--cols"):
            if i + 1 >= len(argv):
                return None, f"[ERROR] {a} 後面需要值。\n{USAGE}"
            v = argv[i + 1]
            if a == "--where":
                o["where"].append(v)
            elif a == "--group":
                o["group"] = v
            elif a in ("--min", "--max", "--avg", "--sum"):
                o["agg"], o["agg_col"] = a[2:], v
            elif a == "--sort":
                o["sort"] = v
            elif a == "--head":
                if not v.isdigit():
                    return None, f"[ERROR] --head 後面要是筆數。\n{USAGE}"
                o["head"] = int(v)
            else:
                o["cols"] = [c.strip() for c in v.split(",") if c.strip()]
            i += 1
        else:
            return None, f"[ERROR] 不認識的參數「{a}」。\n{USAGE}"
        i += 1
    return o, None


def _match(row, col, op, val):
    cell = row.get(col, "")
    if op == "~":
        return val.lower() in cell.lower()
    a, b = _num(cell), _num(val)
    if a is not None and b is not None:
        return {"=": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    if op in ("=", "!="):
        return (cell == val) == (op == "=")
    return {"<": cell < val, "<=": cell <= val, ">": cell > val, ">=": cell >= val}[op]


def main(argv):
    o, err = _parse(argv)
    if err:
        return err
    path = os.path.abspath(os.path.expanduser(o["file"]))
    if not os.path.isfile(path):
        d = os.path.dirname(path)
        near = [f for f in os.listdir(d) if f.endswith((".csv", ".tsv"))][:8] if os.path.isdir(d) else []
        return f"[ERROR] 找不到檔案：{o['file']}" + (f"（同一個目錄裡的表格：{'、'.join(near)}）" if near else "")
    header, data = _read(path)
    if header is None:
        return f"[ERROR] {o['file']} 是空的。"
    rel = os.path.relpath(path)
    head = f"[PASS] {rel}：{len(data)} 筆、{len(header)} 個欄位（{', '.join(header)}）"
    # 篩選
    conds = []
    for w in o["where"]:
        m = _WHERE_RE.match(w)
        if not m:
            return f"[ERROR] --where 的格式是 欄位<運算子>值（例如 robot=tb3、battery<25、status~error），收到「{w}」"
        col, e = _col(header, m.group(1).strip())
        if e:
            return e
        conds.append((col, m.group(2), m.group(3).strip().strip('"').strip("'")))
    rows = [r for r in data if all(_match(r, c, op, v) for c, op, v in conds)]
    if conds:
        head += f"；符合 {' 且 '.join(f'{c}{op}{v}' for c, op, v in conds)} 的有 {len(rows)} 筆"
    cols = header
    if o["cols"]:
        cols = []
        for c in o["cols"]:
            name, e = _col(header, c)
            if e:
                return e
            cols.append(name)
    group = None
    if o["group"]:
        group, e = _col(header, o["group"])
        if e:
            return e
    lines = [head]
    if o["agg"]:
        agg_col = None
        if o["agg"] != "count":
            agg_col, e = _col(header, o["agg_col"])
            if e:
                return e
            bad = [r for r in rows if _num(r.get(agg_col)) is None]
            rows_n = [r for r in rows if _num(r.get(agg_col)) is not None]
            if not rows_n:
                return f"[ERROR] 欄位「{agg_col}」沒有數值（例：{rows[0].get(agg_col) if rows else '—'}）。"
        else:
            rows_n, bad = rows, []
        groups = {}
        for r in rows_n:
            groups.setdefault(r.get(group, "") if group else "（全部）", []).append(r)
        what = {"min": "最小", "max": "最大", "avg": "平均", "sum": "總和", "count": "筆數"}[o["agg"]]
        lines.append(f"{'每一組（' + group + '）的' if group else '整體的'}{what}" + (f"（{agg_col}）" if agg_col else "")
                     + (f"；{len(bad)} 筆的 {agg_col} 不是數字，沒有算進去" if bad else "") + "：")
        if o["agg"] in ("min", "max"):
            pick = min if o["agg"] == "min" else max
            out = []
            for g, rs in groups.items():
                best = pick(rs, key=lambda r: _num(r[agg_col]))
                ties = [r for r in rs if _num(r[agg_col]) == _num(best[agg_col])]
                out.append(dict(best, **({"（同值筆數）": str(len(ties))} if len(ties) > 1 else {})))
            show = cols + (["（同值筆數）"] if any("（同值筆數）" in r for r in out) else [])
            lines += _table(show, out, o["markdown"])
        else:
            out = []
            for g, rs in groups.items():
                if o["agg"] == "count":
                    val = len(rs)
                else:
                    nums = [_num(r[agg_col]) for r in rs]
                    val = sum(nums) if o["agg"] == "sum" else sum(nums) / len(nums)
                out.append({group or "範圍": g, what: _fmt(round(val, 4)), "筆數": str(len(rs))})
            lines += _table([group or "範圍", what] + (["筆數"] if o["agg"] != "count" else []), out, o["markdown"])
        return "\n".join(lines)
    if o["sort"]:
        sc, e = _col(header, o["sort"])
        if e:
            return e
        numeric = all(_num(r.get(sc)) is not None for r in rows if r.get(sc, "") != "")
        rows = sorted(rows, key=lambda r: (_num(r.get(sc)) if numeric else r.get(sc, "")) or 0, reverse=o["desc"])
    if not (conds or o["sort"] or o["cols"] or o["head"]):
        # 不帶選項：欄位概況＋前 5 筆
        lines.append("欄位：")
        for h in header:
            vals = [r.get(h, "") for r in data if r.get(h, "") != ""]
            nums = [_num(v) for v in vals]
            if vals and all(x is not None for x in nums):
                lo = min(range(len(vals)), key=lambda k: nums[k])
                hi = max(range(len(vals)), key=lambda k: nums[k])
                lines.append(f"- {h}：數值，最小 {_fmt(vals[lo])}、最大 {_fmt(vals[hi])}")
            else:
                distinct = sorted(set(vals))
                lines.append(f"- {h}：文字，{len(distinct)} 種值" + (f"（{'、'.join(distinct[:8])}{'…' if len(distinct) > 8 else ''}）"
                                                                      if len(distinct) <= 30 else f"（例：{'、'.join(distinct[:3])}）"))
        lines.append("前 5 筆：")
        lines += _table(header, data[:5], o["markdown"])
        lines.append("（要算每一組的最大／最小值、篩選或排序，照用法加上選項）")
        return "\n".join(lines)
    n = o["head"] or 20
    shown = rows[:min(n, MAX_ROWS_SHOWN)]
    lines.append(f"列出 {len(shown)}／{len(rows)} 筆" + (f"（依 {o['sort']} {'由大到小' if o['desc'] else '由小到大'}）" if o["sort"] else "") + "：")
    lines += _table(cols, shown, o["markdown"])
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:      # noqa: BLE001
        print(f"[ERROR] csv_query 未預期的例外：{e}")
