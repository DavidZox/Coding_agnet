"""把報告的 Markdown 轉成 HTML，再用 Chrome（無頭）印成 PDF：benchmark_study_3/*.md → *.html、*.pdf。
報告裡用 <!-- table:名稱 --> … <!-- /table --> 標出的表，先換成 results/tables/名稱.md 的最新內容。

    python3 benchmark_study_3/analysis/build_reports.py                  # 技術報告.md、評估報告.md
    python3 benchmark_study_3/analysis/build_reports.py 技術報告.md

只用標準庫：內建一個小的 Markdown 轉換器（標題、段落、清單、表格、程式碼區塊、引用、圖片、連結、粗體、行內程式碼），
夠報告用就好。PDF 需要 google-chrome（或 chromium）。
"""
import html
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
DEFAULT = ["技術報告.md", "評估報告.md"]

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "Noto Serif CJK TC", "Noto Sans CJK TC", serif; font-size: 10.5pt; line-height: 1.65; color: #1a202c;
       max-width: 860px; margin: 0 auto; padding: 24px; }
h1 { font-family: "Noto Sans CJK TC", sans-serif; font-size: 20pt; text-align: center; margin: 0.4em 0 0.2em; }
h2 { font-family: "Noto Sans CJK TC", sans-serif; font-size: 14pt; border-bottom: 1.5px solid #2d3748; padding-bottom: 3px;
     margin-top: 1.6em; }
h3 { font-family: "Noto Sans CJK TC", sans-serif; font-size: 12pt; margin-top: 1.3em; }
h4 { font-family: "Noto Sans CJK TC", sans-serif; font-size: 11pt; margin-top: 1.1em; }
p { margin: 0.5em 0; text-align: justify; }
.subtitle { text-align: center; color: #4a5568; margin: 0 0 1.2em; }
.abstract { border: 1px solid #a0aec0; background: #f7fafc; padding: 10px 14px; margin: 1em 0 1.4em; }
table { border-collapse: collapse; margin: 0.8em 0; font-size: 9pt; width: 100%; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #a0aec0; padding: 3px 6px; vertical-align: top; }
th { background: #edf2f7; font-family: "Noto Sans CJK TC", sans-serif; }
td:first-child, th:first-child { min-width: 4.5em; }
code { font-family: "Noto Sans Mono CJK TC", "DejaVu Sans Mono", monospace; font-size: 9pt; background: #f1f5f9; padding: 0 3px; }
pre { background: #f1f5f9; padding: 8px 10px; overflow-x: auto; font-size: 8.5pt; line-height: 1.45; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #a0aec0; margin: 0.8em 0; padding: 2px 12px; color: #2d3748; background: #f7fafc; }
img { display: block; max-width: 100%; margin: 0.8em auto 0.2em; page-break-inside: avoid; }
.caption { text-align: center; font-size: 9pt; color: #4a5568; margin-bottom: 1em; }
ul, ol { margin: 0.4em 0 0.4em 1.4em; padding-left: 0.6em; }
li { margin: 0.15em 0; }
li > p { margin: 0.35em 0; }
li > ul, li > ol { margin-top: 0.2em; }
hr { border: none; border-top: 1px solid #cbd5e0; margin: 1.4em 0; }
a { color: #2b6cb0; text-decoration: none; }
.pagebreak { page-break-after: always; }
"""


def inline(text):
    """行內語法：`code`、**粗體**、*斜體*、![圖](src)、[連結](url)。先把 code 換成佔位，避免裡面的符號被處理。"""
    codes = []

    def keep(m):
        codes.append(html.escape(m.group(1)))
        return f"\u0000{len(codes) - 1}\u0000"

    text = re.sub(r"`([^`]+)`", keep, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img src="\2" alt="\1">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*\s][^*]*)\*(?!\w)", r"<em>\1</em>", text)
    return re.sub("\u0000(\\d+)\u0000", lambda m: f"<code>{codes[int(m.group(1))]}</code>", text)


def slug(text):
    return re.sub(r"[^\w一-鿿-]+", "-", text).strip("-").lower()


def convert(md):
    lines = md.split("\n")
    out, i = [], 0
    para = []

    def flush():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s.startswith("```"):
            flush()
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            i = j + 1
            continue
        if not s:
            flush()
            i += 1
            continue
        if s.startswith("<") and not s.startswith("<http"):
            flush()
            out.append(ln)
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            level, text = len(m.group(1)), m.group(2)
            out.append(f'<h{level} id="{slug(text)}">{inline(text)}</h{level}>')
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", s):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            flush()
            head = [c.strip() for c in s.strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            t = ["<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
            t += ["<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows]
            out.append("".join(t) + "</tbody></table>")
            i = j
            continue
        if s.startswith(">"):
            flush()
            buf, j = [], i
            while j < len(lines) and lines[j].strip().startswith(">"):
                buf.append(lines[j].strip()[1:].strip())
                j += 1
            out.append("<blockquote>" + convert("\n".join(buf)) + "</blockquote>")
            i = j
            continue
        if LIST_RE.match(ln):
            flush()
            j, items = i, []
            base, ordered = indent_of(ln), bool(ORDERED_RE.match(ln))
            while j < len(lines):
                cur = lines[j]
                if not cur.strip():
                    # 空行：後面接的還是這個清單（同一種清單的下一項、更深的項目、縮排的續行）就留下，否則清單結束
                    k = j
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    nxt = lines[k] if k < len(lines) else ""
                    same_kind = LIST_RE.match(nxt) and (indent_of(nxt) > base or bool(ORDERED_RE.match(nxt)) == ordered)
                    if items and nxt.strip() and (indent_of(nxt) > base or (indent_of(nxt) == base and same_kind)):
                        items.append("")
                        j = k
                        continue
                    break
                if not (LIST_RE.match(cur) or (cur.startswith("  ") and items)):
                    break
                if indent_of(cur) == base and LIST_RE.match(cur) and bool(ORDERED_RE.match(cur)) != ordered:
                    break                   # 同一層換成另一種清單（- 換成 1.）：另起一個清單
                items.append(cur)
                j += 1
            out.append(render_list(items))
            i = j
            continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)\s]+)\)$", s)
        if m:
            flush()
            out.append(f'<img src="{m.group(2)}" alt="{html.escape(m.group(1))}"><div class="caption">{inline(m.group(1))}</div>')
            i += 1
            continue
        para.append(s)
        i += 1
    flush()
    return "\n".join(out)


LIST_RE = re.compile(r"^\s*([-*]|\d+\.)\s+")
ORDERED_RE = re.compile(r"^\s*\d+\.\s")


def indent_of(x):
    return len(x) - len(x.lstrip(" "))


def render_list(items):
    """清單：依縮排巢狀；緊接在項目後面的續行接到同一段；項目裡空一行之後的縮排段落、子清單依序放進那一項。
    編號清單照第一項的號碼開始（中間插了段落也接得上）。items 裡的空字串是原文的空行。"""
    def build(lines, base):
        m0 = re.match(r"^\s*(\d+)\.\s", lines[0])
        tag = "ol" if m0 else "ul"
        start = f' start="{m0.group(1)}"' if m0 and m0.group(1) != "1" else ""
        html_, k = [f"<{tag}{start}>"], 0
        while k < len(lines):
            m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[k])
            if not m or indent_of(lines[k]) != base:
                k += 1
                continue
            text, k2, child = m.group(3), k + 1, []
            while k2 < len(lines) and (lines[k2] == "" or indent_of(lines[k2]) > base):
                child.append(lines[k2])
                k2 += 1
            while child and child[-1] == "":
                child.pop()
            lead = []
            while child and child[0] != "" and not LIST_RE.match(child[0]):
                lead.append(child.pop(0).strip())
            html_.append(f"<li>{inline(' '.join([text] + lead))}{render_child(child)}</li>")
            k = k2
        html_.append(f"</{tag}>")
        return "".join(html_)

    def render_child(child):
        parts, para, k = [], [], 0

        def flush_para():
            if para:
                parts.append(f"<p>{inline(' '.join(para))}</p>")
                para.clear()

        while k < len(child):
            c = child[k]
            if c == "":
                flush_para()
                k += 1
                continue
            if LIST_RE.match(c):
                flush_para()
                sub_base, k2, sub = indent_of(c), k, []
                while k2 < len(child):
                    d = child[k2]
                    if d == "":
                        nxt = next((x for x in child[k2:] if x), "")
                        if not nxt or (indent_of(nxt) <= sub_base and not LIST_RE.match(nxt)):
                            break
                    elif not (indent_of(d) > sub_base or (indent_of(d) == sub_base and LIST_RE.match(d))):
                        break
                    sub.append(d)
                    k2 += 1
                parts.append(build(sub, sub_base))
                k = k2
                continue
            para.append(c.strip())
            k += 1
        flush_para()
        return "".join(parts)

    return build(items, indent_of(items[0]))


def chrome():
    for name in ("google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


TABLE_BLOCK_RE = re.compile(r"(<!-- table:([\w.-]+) -->\n)(.*?)(\n<!-- /table -->)", re.S)


def refresh_tables(src):
    """報告裡的 <!-- table:名稱 --> … <!-- /table --> 換成 results/tables/名稱.md 目前的內容（數字永遠跟分析結果一致）；
    沒有那個表時保留原文。回傳換了幾個。"""
    with open(src, encoding="utf-8") as f:
        md = f.read()
    count = 0

    def repl(m):
        nonlocal count
        path = os.path.join(STUDY, "results", "tables", m.group(2) + ".md")
        if not os.path.exists(path):
            return m.group(0)
        with open(path, encoding="utf-8") as f:
            table = f.read().strip()
        count += 1
        return m.group(1) + table + m.group(4)

    new = TABLE_BLOCK_RE.sub(repl, md)
    if new != md:
        with open(src, "w", encoding="utf-8") as f:
            f.write(new)
    return count


def build(name):
    src = os.path.join(STUDY, name)
    refresh_tables(src)
    with open(src, encoding="utf-8") as f:
        md = f.read()
    title = re.search(r"^#\s+(.*)$", md, re.M)
    body = convert(md)
    page = (f'<!DOCTYPE html>\n<html lang="zh-Hant"><head><meta charset="utf-8"><title>{html.escape(title.group(1) if title else name)}'
            f"</title><style>{CSS}</style></head><body>\n{body}\n</body></html>\n")
    out_html = os.path.splitext(src)[0] + ".html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(page)
    pdf = os.path.splitext(src)[0] + ".pdf"
    c = chrome()
    if c:
        subprocess.run([c, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer", "--virtual-time-budget=5000",
                        f"--print-to-pdf={pdf}", "file://" + out_html], capture_output=True, timeout=180)
    return out_html, pdf if os.path.exists(pdf) else None


def main():
    names = sys.argv[1:] or [n for n in DEFAULT if os.path.exists(os.path.join(STUDY, n))]
    for n in names:
        h, p = build(n)
        print(f"{n} → {os.path.relpath(h, STUDY)}" + (f"、{os.path.relpath(p, STUDY)}" if p else "（沒有 Chrome，沒產生 PDF）"))


if __name__ == "__main__":
    main()
