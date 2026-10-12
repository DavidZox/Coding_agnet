"""code_write：建立新檔案（整份內容），或 --delete 刪除檔案（先備份，可還原）。

內容跟 code_edit 一樣由 --payload 檔提供（--payload - 讀 stdin）：模型的原始回覆，有 ``` 區塊就取區塊內容、被抄進來的行號前綴自動剝掉。
檔案已存在時預設不覆寫（改既有檔案用 code_edit，才有 SEARCH/REPLACE 與省略偵測）；--overwrite 整份覆寫時套用跟
code_edit --whole 一樣的省略偵測。新內容語法錯誤（Python／JSON／TOML／YAML）時不寫入（--allow-broken 放行）。
路徑邊界與備份見 _code_common（CODE_WORKSPACE、CODE_BACKUP_DIR）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc
import code_edit_cmd

USAGE = ("用法: scripts/code_write_cmd.py <檔案> [--payload 內容檔] [--overwrite] [--allow-broken]\n"
         "       scripts/code_write_cmd.py <檔案> --delete\n"
         "  內容（完整的檔案）由 --payload 指定的檔案提供（--payload - 讀 stdin）；父目錄會自動建立。")


def parse_args(argv):
    opts = {"path": None, "payload": None, "overwrite": False, "allow_broken": False, "delete": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--payload":
            if i + 1 >= len(argv):
                return None, f"[ERROR] --payload 後面需要內容檔的路徑。\n{USAGE}"
            opts["payload"] = argv[i + 1]
            i += 2
            continue
        flag = {"--overwrite": "overwrite", "--allow-broken": "allow_broken", "--delete": "delete"}.get(a)
        if flag:
            opts[flag] = True
        elif a.startswith("--"):
            return None, f"[ERROR] 不認識的選項 {a}。\n{USAGE}"
        elif opts["path"] is None:
            opts["path"] = a
        else:
            return None, f"[ERROR] 一次只能寫一個檔案（收到 {opts['path']} 與 {a}）。\n{USAGE}"
        i += 1
    if not opts["path"]:
        return None, f"[ERROR] 沒有給檔案路徑。\n{USAGE}"
    return opts, None


def summary_of(path, text):
    """新檔案的簡介：Python 與 C／C++ 給結構大綱，其他給前 15 行。"""
    lines = text.split("\n")
    if cc.language_of(path) in ("C", "C++", "C/C++ 標頭"):
        import _cpp_common as cp
        items = cp.outline(text, max_items=30)
        if items:
            return "結構：\n" + "\n".join(f"  {'  ' * d}{t}" for d, t in items)
    if cc.language_of(path) == "Python":
        try:
            import ast
            tree = ast.parse(text)
            items = []
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    items.append(f"class {node.name} L{node.lineno}-{node.end_lineno}" + (f"：{', '.join(methods)}" if methods else ""))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    items.append(f"def {node.name} L{node.lineno}-{node.end_lineno}")
            if items:
                return "結構：\n" + "\n".join(f"  {x}" for x in items[:30])
        except SyntaxError:
            pass
    return "開頭：\n" + cc.numbered(lines[:15])


def main(argv):
    opts, err = parse_args(argv)
    if err:
        return err
    path, err = cc.resolve_path(opts["path"], for_write=True)
    if err:
        return err
    rel = cc.rel_to_root(path)
    if os.path.isdir(path):
        return f"[ERROR] {rel} 是目錄，不是檔案。"
    if opts["delete"]:
        if not os.path.exists(path):
            return f"[ERROR] {rel} 不存在，不用刪。"
        cc.backup_before_write(path)
        os.remove(path)
        return f"[PASS] 已刪除 {rel}（原檔已備份，可用 coding job 的還原找回）"
    exists = os.path.exists(path)
    if exists and not opts["overwrite"]:
        return (f"[ERROR] {rel} 已經存在，沒有寫入：修改既有檔案請用 code_edit（SEARCH/REPLACE 或 --whole），"
                f"確定要整份覆寫才加 --overwrite。")
    if exists:   # 整份覆寫＝code_edit --whole（同一套省略偵測、語法檢查與 diff）
        args = [opts["path"], "--whole"] + (["--payload", opts["payload"]] if opts["payload"] else []) \
            + (["--allow-broken"] if opts["allow_broken"] else [])
        return code_edit_cmd.main(args)
    try:
        payload = cc.read_payload(opts["payload"])
    except OSError as e:
        return f"[ERROR] 讀不到內容檔 {opts['payload']}：{e}"
    if payload is None:
        return f"[ERROR] 沒有收到檔案內容（--payload 內容檔）。\n{USAGE}"
    body, _ = cc.extract_fenced(payload)
    body = cc.strip_line_numbers(body)
    if not body.strip() and cc.language_of(path) not in ("Python", "文字", "Markdown", ""):
        return f"[ERROR] {rel} 沒有寫入：內容是空的。"
    if body and not body.endswith("\n"):
        body += "\n"
    elided = cc.find_elisions(body.split("\n"))
    if elided:
        sample = "；".join(x.strip()[:60] for _, x in elided[:3])
        return f"[ERROR] {rel} 沒有寫入：內容裡有像是省略的行（{sample}），請輸出完整的檔案內容。"
    ok, check_msg = cc.syntax_check(path, body)
    if not ok and not opts["allow_broken"]:
        return f"[ERROR] {rel} 沒有寫入：{check_msg}\n請修正內容後再寫一次。"
    cc.backup_before_write(path)
    cc.write_text(path, body)
    n = body.count("\n")
    check = f"；{check_msg}" if check_msg else ""
    return f"[PASS] 已建立 {rel}（{n} 行，{cc.language_of(path) or '文字'}）{check}\n{summary_of(path, body)}"


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_write 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
