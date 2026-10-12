"""code_edit：修改既有的檔案——套用 SEARCH/REPLACE 區塊（預設），或用 --whole 整份換成新內容。

內容不放在 args：harness（coding worker）先讓模型決定「改哪個檔」，再請它用一般文字輸出區塊或整份檔案，存成 payload 檔後以
--payload 交給這支腳本（人工使用時可以用 --payload - 從 stdin 給）。為什麼不放 JSON 參數見 _code_common「編輯」一節。

安全網（都由程式保證，不靠模型自律）：
- 比對：逐字 → 忽略行尾空白 → 忽略縮排（找到後把 REPLACE 的縮排平移成檔案實際的縮排）；被抄進來的行號前綴自動剝掉；
  對到多個位置、或完全對不到時不改檔，回傳最像的那一段（帶行號）讓模型照實際內容重寫。
- --whole：新內容裡有「其餘不變／...」這類省略、或原本 30 行以上的檔案一下少了四成以上，視為偷懶的省略，不寫入（--allow-shrink 放行）。
- 原本語法正確、改完變成語法錯誤（Python／JSON／TOML／YAML）時不寫入，回傳錯誤位置（--allow-broken 放行）。
- 路徑邊界與備份：見 _code_common（CODE_WORKSPACE、CODE_BACKUP_DIR）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc

SHRINK_MIN_LINES, SHRINK_RATIO = 30, 0.6
USAGE = ("用法: scripts/code_edit_cmd.py <檔案> [--payload 內容檔] [--whole] [--allow-shrink] [--allow-broken] [--dry-run]\n"
         "  內容（預設是 SEARCH/REPLACE 區塊；--whole 時是整份新檔案）由 --payload 指定的檔案提供（--payload - 讀 stdin）。\n"
         "  SEARCH/REPLACE 格式（可以有多個區塊，依序套用）：\n"
         "  <<<<<<< SEARCH\n  （要被取代的原文，逐字照抄，不要帶行號）\n  =======\n  （新的內容）\n  >>>>>>> REPLACE")


def parse_args(argv):
    opts = {"path": None, "payload": None, "whole": False, "allow_shrink": False, "allow_broken": False, "dry_run": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--payload":
            if i + 1 >= len(argv):
                return None, f"[ERROR] --payload 後面需要內容檔的路徑。\n{USAGE}"
            opts["payload"] = argv[i + 1]
            i += 2
            continue
        flag = {"--whole": "whole", "--allow-shrink": "allow_shrink", "--allow-broken": "allow_broken", "--dry-run": "dry_run"}.get(a)
        if flag:
            opts[flag] = True
        elif a.startswith("--"):
            return None, f"[ERROR] 不認識的選項 {a}。\n{USAGE}"
        elif opts["path"] is None:
            opts["path"] = a
        else:
            return None, f"[ERROR] 一次只能改一個檔案（收到 {opts['path']} 與 {a}）。\n{USAGE}"
        i += 1
    if not opts["path"]:
        return None, f"[ERROR] 沒有給要修改的檔案。\n{USAGE}"
    return opts, None


def compute_new(old, payload, whole):
    """回傳 (新內容, 說明, 錯誤)。"""
    if whole:
        body, _ = cc.extract_fenced(payload)
        body = cc.strip_line_numbers(body)
        return body, "整份檔案", None
    blocks = cc.parse_search_replace(payload)
    if not blocks:
        body, fenced = cc.extract_fenced(payload)
        if fenced and body.strip() and "<<<<<<<" not in body:
            return None, None, ("沒有找到 SEARCH/REPLACE 區塊（收到的是一整段程式碼）。要整份換掉請用 --whole；"
                                "只改一部分請用 <<<<<<< SEARCH / ======= / >>>>>>> REPLACE 區塊。")
        return None, None, "沒有找到 SEARCH/REPLACE 區塊。格式：<<<<<<< SEARCH、原文、=======、新內容、>>>>>>> REPLACE。"
    text, modes = old, []
    for n, (o, nw) in enumerate(blocks, 1):
        text, mode, err = cc.apply_block(text, o, nw)
        if err:
            done = f"（前 {n - 1} 個區塊對得到，但整批沒有寫入）" if n > 1 else ""
            return None, None, f"第 {n} 個區塊：{err}{done}"
        modes.append(mode)
    loose = sum(1 for m in modes if m in ("trailing_ws", "indent"))
    desc = f"套用 {len(blocks)} 個區塊" + (f"，其中 {loose} 個是忽略空白／縮排後才對到的" if loose else "")
    return text, desc, None


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
    if not os.path.exists(path):
        import _path_common
        hint = _path_common.suggest(path, want="file")
        return (f"[ERROR] {rel} 不存在。{hint}——要改的是那個檔案就用那個路徑（路徑一律相對於專案根目錄）；確定要建立新檔才用 code_write。"
                if hint else f"[ERROR] {rel} 不存在：建立新檔請用 code_write。")
    if cc.is_binary(path):
        return f"[ERROR] {rel} 是二進位檔，不能用文字修改。"
    try:
        payload = cc.read_payload(opts["payload"])
    except OSError as e:
        return f"[ERROR] 讀不到內容檔 {opts['payload']}：{e}"
    if payload is None or not payload.strip():
        return f"[ERROR] 沒有收到要修改的內容（--payload 內容檔）。\n{USAGE}"
    old = cc.read_text(path)
    new, desc, err = compute_new(old, payload, opts["whole"])
    if err:
        return f"[ERROR] {rel} 沒有修改：{err}"
    if old.endswith("\n") and not new.endswith("\n"):
        new += "\n"
    if new == old:
        return (f"[ERROR] {rel} 沒有修改：新內容跟檔案目前的內容完全一樣——你要的修改可能已經在檔案裡了（例如建立檔案時就寫好了）。"
                f"先用 code_view 確認；已經做好就不要再改，這一項完成了就回報完成（action 填 null）。")

    old_lines, new_lines = old.split("\n"), new.split("\n")
    old_set = set(x.strip() for x in old_lines)
    added = [x for x in new_lines if x.strip() and x.strip() not in old_set]
    elided = cc.find_elisions(added)
    if elided and not opts["allow_shrink"]:
        sample = "；".join(x.strip()[:60] for _, x in elided[:3])
        return (f"[ERROR] {rel} 沒有修改：新內容裡有像是省略原本程式碼的行（{sample}）。檔案會被這一行取代、原本的程式碼就不見了。"
                + ("請輸出完整的檔案，沒改的部分要原封不動照抄。" if opts["whole"] else "REPLACE 要寫出完整的新程式碼，不要用「…」或「其餘不變」代替。"))
    if opts["whole"] and not opts["allow_shrink"] and len(old_lines) >= SHRINK_MIN_LINES \
            and len(new_lines) < len(old_lines) * SHRINK_RATIO:
        return (f"[ERROR] {rel} 沒有修改：原本 {len(old_lines)} 行，新內容只有 {len(new_lines)} 行（少了 "
                f"{100 - round(len(new_lines) / len(old_lines) * 100)}%），看起來漏掉了原本的程式碼。請輸出完整的檔案；"
                f"確定要大量刪除時改用 SEARCH/REPLACE 只刪那一段（或加 --allow-shrink）。")
    was_ok, _ = cc.syntax_check(path, old)
    now_ok, check_msg = cc.syntax_check(path, new)
    if was_ok and not now_ok and not opts["allow_broken"]:
        import re
        m = re.search(r"第 (\d+) 行", check_msg or "")
        ctx = ""
        if m:
            ln = int(m.group(1))
            lo, hi = max(1, ln - 4), min(len(new_lines), ln + 3)
            ctx = f"\n修改後（未寫入）的第 {lo}～{hi} 行：\n" + cc.numbered(new_lines[lo - 1:hi], lo)
        return f"[ERROR] {rel} 沒有修改：改完會變成{check_msg}{ctx}\n請修正內容後再改一次（{desc}）。"
    report, n_add, n_del = cc.edit_report(rel, old, new)
    if opts["dry_run"]:
        return f"[PASS] （試算，沒有寫入）{rel}：+{n_add} −{n_del} 行（{desc}）\n{report}"
    newline = cc.detect_newline(path)   # 保留原本的換行（CRLF 的檔案寫回 CRLF）
    cc.backup_before_write(path)
    cc.write_text(path, new, newline=newline)
    check = f"；{check_msg}" if check_msg else ""
    warn = "" if now_ok else "\n⚠️ 修改後仍有語法問題（原本就有，或用了 --allow-broken）：" + check_msg
    return f"[PASS] 已修改 {rel}：+{n_add} −{n_del} 行（{desc}）{check}{warn}\n{report}"


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_edit 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
