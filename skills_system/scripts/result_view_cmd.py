"""result_view：讀某個工具結果存檔的一段原文（第 N 行起 M 行），或列出原文的大綱（章節標題與行號）。行號是原文的行號（工具輸出的第 1 行＝行 1，
不含存檔的檔頭），跟 result_grep、提煉結果引用的行號、claude_code 模式的截斷說明同一套。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _results_common import clip, describe, numbered, outline, read_body, resolve_result

DEFAULT_LINES, MAX_LINES = 80, 300
MAX_OUTPUT_CHARS = 12000
USAGE = (f"用法: scripts/result_view_cmd.py <編號|latest> [--from 行號] [--lines 行數] [--outline]\n"
         f"  --from 預設原文第 1 行；--lines 預設 {DEFAULT_LINES}（上限 {MAX_LINES}）；行號是原文的行號（result_grep、提煉結果引用的同一套）。\n"
         f"  --outline：只列原文的大綱（每個章節標題的行號與行數），再用 --from 看要的那一節。")


def parse_args(argv):
    args = list(argv)
    ref, start, count, show_outline = None, None, DEFAULT_LINES, False
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--from", "--lines"):
            if i + 1 >= len(args) or not args[i + 1].isdigit():
                return None, f"[ERROR] {a} 後面需要數字。\n{USAGE}"
            if a == "--from":
                start = max(1, int(args[i + 1]))
            else:
                count = max(1, min(MAX_LINES, int(args[i + 1])))
            i += 2
            continue
        if a == "--outline":
            show_outline = True
            i += 1
            continue
        if a.startswith("-") and len(a) > 1:
            return None, f"[ERROR] 不認識的選項 {a!r}。\n{USAGE}"
        if ref is not None:
            return None, f"[ERROR] 只接受一個編號，收到 {ref!r} 與 {a!r}。\n{USAGE}"
        ref = a
        i += 1
    if ref is None:
        return None, f"[ERROR] 需要結果編號（或 latest）。\n{USAGE}"
    return {"ref": ref, "start": start, "count": count, "outline": show_outline}, None


def main(argv):
    opts, err = parse_args(argv)
    if err:
        return err
    path, err = resolve_result(opts["ref"])
    if err:
        return err
    meta, lines = read_body(path)
    total = len(lines)
    title = f"{describe(meta, os.path.basename(path))}｜{meta.get('command') or ''}｜原文共 {total} 行"
    if opts["outline"]:
        ol = outline(lines)
        if not ol:
            return (f"[PASS] {title}；沒有章節標題（一行一筆的輸出），用 --from／--lines 分段看，"
                    f"或 result_grep <編號> \"<關鍵字>\" 找要的那幾行。")
        return "\n".join([f"[PASS] {title}；大綱（{len(ol)} 節，章節標題的行號與行數；用 --from <行號> 看那一節）："]
                         + [f"- 行 {n}：{t}（{k} 行）" for n, t, k in ol])
    start = opts["start"] or 1
    if start > total:
        return f"[ERROR] 起始行 {start} 超過原文的總行數 {total}。下一步：改小 --from（原文從行 1 開始），或用 --outline 看各節的行號。"
    end = min(total, start + opts["count"] - 1)
    head = (f"[PASS] {title}；顯示第 {start}～{end} 行"
            + (f"，之後還有 {total - end} 行（--from {end + 1} 繼續）" if end < total else "，已到最後一行") + "：")
    out = [head]
    if meta.get("task"):
        out.append(f"當時的任務：{meta['task']}")
    out += [numbered(j, clip(lines[j - 1])) for j in range(start, end + 1)]
    text = "\n".join(out)
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n（輸出達上限 {MAX_OUTPUT_CHARS} 字：減少 --lines，或從後面的行號用 --from 接著看）"
    return text


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] result_view 未預期的例外: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
