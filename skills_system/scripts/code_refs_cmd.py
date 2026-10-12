"""code_refs：找某個名稱（函式、類別、方法、變數）在整個專案的定義、匯入與使用處——跨檔修改（改名、改參數、改回傳值）前用它列出
「哪些地方要一起改」。

Python 檔用 AST 判斷（不會把註解、字串裡的同名文字算進來）：定義＝def／class／模組層級的指派；匯入＝from … import 名稱、
import 路徑.名稱；使用＝讀取這個名稱、或 物件.名稱 的屬性存取、以及 名稱= 的關鍵字參數。
C／C++ 檔用 _cpp_common 的掃描器（同樣不算註解與字串）：定義＝class／struct／enum、有本體的函式與方法（Circle::area 的實作）、
typedef、#define；宣告＝標頭裡的函式原型與類別裡的方法宣告——改簽名時宣告與定義都要改。
其他類型的檔案（設定檔、文件、其他語言）用完整識別字的文字比對另外列出。數量由腳本算好，直接引用。
"""
import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc
import _cpp_common as cp

MAX_LIST = 60
MAX_OUTPUT_CHARS = 12000
USAGE = ("用法: scripts/code_refs_cmd.py <名稱> [路徑]\n"
         "  名稱可以是 load_config、Inventory、Inventory.remove、Circle::area（只看最後一段的名稱比對）；"
         "路徑預設目前工作目錄（coding job 時是工作區）。")


def scan_python(text, name, cls=None):
    """回傳 {"def": [...], "import": [...], "use": [...]}，每項 (行號, 說明)。cls 有值時（Class.method），定義只認那個類別裡的。"""
    found = {"def": [], "import": [], "use": []}
    tree = ast.parse(text)

    def visit_defs(body, owner):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == name and (cls is None or owner == cls):
                    kind = "class" if isinstance(node, ast.ClassDef) else ("method" if owner else "def")
                    found["def"].append((node.lineno, kind + (f" in {owner}" if owner else "")))
                if isinstance(node, ast.ClassDef):
                    visit_defs(node.body, node.name)
            elif owner is None and isinstance(node, (ast.Assign, ast.AnnAssign)) and cls is None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        found["def"].append((node.lineno, "assign"))

    visit_defs(tree.body, None)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == name:
                    found["import"].append((node.lineno, f"from {'.' * node.level}{node.module or ''}"))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[-1] == name:
                    found["import"].append((node.lineno, "import"))
        elif isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Load, ast.Del)) and cls is None:
            found["use"].append((node.lineno, "直接使用"))   # 類別.方法 只會以屬性存取，同名的區域變數不算
        elif isinstance(node, ast.Attribute) and node.attr == name:
            found["use"].append((node.lineno, f"屬性 .{name}"))
        elif isinstance(node, ast.keyword) and node.arg == name and cls is None:
            found["use"].append((getattr(node, "lineno", 0) or 0, f"關鍵字參數 {name}="))
    for k in found:   # 同一行只列一次
        seen, uniq = set(), []
        for ln, why in sorted(found[k]):
            if ln not in seen:
                seen.add(ln)
                uniq.append((ln, why))
        found[k] = uniq
    return found


def main(argv):
    args = [a for a in argv if a.strip()]
    if not args or args[0].startswith("-"):
        return f"[ERROR] 沒有給要找的名稱。\n{USAGE}"
    if len(args) > 2:
        return f"[ERROR] 參數太多（一次找一個名稱）。\n{USAGE}"
    full = args[0].strip("`'\"()")
    parts = [p for p in full.replace("::", ".").split(".") if p]
    if not parts or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", parts[-1]):
        return f"[ERROR] 「{full}」不是合法的識別字名稱。\n{USAGE}"
    name = parts[-1]
    cls = parts[-2] if len(parts) >= 2 and parts[-2][:1].isupper() else None
    root, err = cc.resolve_path(args[1] if len(args) > 1 else ".")
    if err:
        return err
    if not os.path.exists(root):
        return f"[ERROR] 路徑不存在：{args[1]}"
    files = cc.iter_files(root)
    word = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")
    defs, decls, imps, uses, others, broken = [], [], [], [], [], []
    py_files_hit = set()
    for path, _ in files:
        rel = cc.rel_to_root(path)
        try:
            text = cc.read_text(path)
        except OSError:
            continue
        if name not in text:
            continue
        lines = text.split("\n")
        show = lambda ln: lines[ln - 1].strip()[:160] if 0 < ln <= len(lines) else ""
        if cc.language_of(path) == "Python":
            try:
                found = scan_python(text, name, cls)
            except SyntaxError as e:
                broken.append(f"{rel}（第 {e.lineno} 行語法錯誤，改用文字比對）")
                found = None
            if found is not None:
                for ln, why in found["def"]:
                    defs.append(f"  {rel} L{ln}（{why}）: {show(ln)}")
                for ln, why in found["import"]:
                    imps.append(f"  {rel} L{ln}: {show(ln)}")
                def_lines = {ln for ln, _ in found["def"]} | {ln for ln, _ in found["import"]}
                for ln, why in found["use"]:
                    if ln not in def_lines:
                        uses.append(f"  {rel} L{ln}（{why}）: {show(ln)}")
                if any(found.values()):
                    py_files_hit.add(rel)
                continue
        if cp.is_c_family(path):
            found = cp.refs(text, name, cls)
            for ln, why in found["def"]:
                defs.append(f"  {rel} L{ln}（{why}）: {show(ln)}")
            for ln, why in found["decl"]:
                decls.append(f"  {rel} L{ln}（{why}）: {show(ln)}")
            for ln, why in found["use"]:
                uses.append(f"  {rel} L{ln}: {show(ln)}")
            if any(found.values()):
                py_files_hit.add(rel)
            continue
        for i, ln in enumerate(lines, 1):
            if word.search(ln):
                others.append(f"  {rel} L{i}: {ln.strip()[:160]}")
    total_files = len(py_files_hit | {o.split(" L")[0].strip() for o in others})
    head = (f"[PASS] code_refs「{full}」：定義 {len(defs)} 處、" + (f"宣告 {len(decls)} 處、" if decls else "")
            + f"匯入 {len(imps)} 處、使用 {len(uses)} 處（Python 與 C／C++）"
            + (f"；其他檔案的文字提及 {len(others)} 處" if others else "") + f"，共 {total_files} 個檔案")
    if not (defs or decls or imps or uses or others):
        return (f"[PASS] code_refs「{full}」：整個專案找不到這個名稱（{len(files)} 個檔案）。"
                "確認拼字；要找部分字串用 code_search。")
    out = [head]
    if cls:
        out.append(f"（定義只認類別 {cls} 裡的；使用處以屬性名稱 .{name} 比對，可能包含其他類別的同名方法）")
    for title, items in (("定義", defs), ("宣告（標頭的原型、類別裡的方法宣告）", decls), ("匯入", imps), ("使用", uses),
                         ("其他檔案（文字比對）", others)):
        if not items:
            continue
        out.append(f"{title}：")
        out += items[:MAX_LIST]
        if len(items) > MAX_LIST:
            out.append(f"  …還有 {len(items) - MAX_LIST} 處沒有列出（用 code_search 搭配 --glob 縮小範圍）")
    if broken:
        out.append("注意：" + "；".join(broken))
    if defs and (uses or imps or decls):
        out.append("要改名或改參數時，上面列出的定義、" + ("宣告、" if decls else "") + "匯入與使用處都要一起改。")
    text = "\n".join(out)
    return text if len(text) <= MAX_OUTPUT_CHARS else text[:MAX_OUTPUT_CHARS] + "\n…（輸出達上限）"


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_refs 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
