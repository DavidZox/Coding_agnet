"""第一版領域的技能的收據（skills_system/scripts/_receipt_common.py）：search_text、find_file、list_dir、view_file、
code_ast_reader、result_list、result_grep、result_view，與 code_defs、py_refs（領域 session 用）。

每一種出口都記收據（pass、empty、error 與錯誤的種類）；數量跟給模型的文字一致；收據比文字完整（文字只列前幾筆，收據記全部）；
給模型的文字有沒有寫收據都一模一樣；規格的 parameters、receipt 欄位跟腳本寫的一致，而且載入給模型時拿掉。

    python3 evals/skills/selftest.py receipt
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile

from selftest import PROJECT, SCRIPTS, Skip, run_script

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
V1 = {"search_text": "grep_cmd.py", "find_file": "find_file_cmd.py", "list_dir": "ls_cmd.py", "view_file": "cat_cmd.py",
      "code_ast_reader": "code_ast_reader_cmd.py", "result_list": "result_list_cmd.py", "result_grep": "result_grep_cmd.py",
      "result_view": "result_view_cmd.py", "code_defs": "code_defs_cmd.py", "py_refs": "py_refs_cmd.py"}
COMMON = {"version", "tool", "cwd", "status", "error_kind", "counts", "items", "truncated"}
SEEN = {}            # 技能 → 這一組測試收到的收據（最後一個情境核對規格用）
RECEIPTS = tempfile.mkdtemp(prefix="skills_receipt_out_")   # 收據寫在被測的目錄外面（不然 search_text 會搜到收據本身）


def _tmp():
    d = tempfile.mkdtemp(prefix="skills_receipt_")
    os.makedirs(os.path.join(d, "_logs"), exist_ok=True)
    return d


def _w(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w" if isinstance(text, str) else "wb") as f:
        f.write(text)
    return p


def run(skill, *args, d, **env):
    """執行腳本、讀收據 → (給模型的文字, 收據)。另外不寫收據再跑一次：給模型的文字要一模一樣。"""
    path = os.path.join(RECEIPTS, "receipt.json")
    if os.path.exists(path):
        os.remove(path)
    base = {"HARNESS_LOGS_DIR": os.path.join(d, "_logs"), "TARGET_CONTAINER": "", **env}
    _, out = run_script(V1[skill], *args, cwd=d, env={**base, "AGENT_RECEIPT_PATH": path})
    _, plain = run_script(V1[skill], *args, cwd=d, env={**base, "AGENT_RECEIPT_PATH": ""})
    assert out == plain, f"{skill} 寫收據時給模型的文字變了：\n{out[:300]}\n---\n{plain[:300]}"
    with open(path, encoding="utf-8") as f:
        r = json.load(f)
    assert r["tool"] == skill and r["version"] == 1 and r["status"] in ("pass", "empty", "error"), r
    assert (r["status"] == "error") == out.startswith("[ERROR]"), (r, out[:200])
    SEEN.setdefault(skill, []).append(r)
    return out, r


def _error(skill, kind, *args, d, **env):
    out, r = run(skill, *args, d=d, **env)
    assert r["status"] == "error" and r["error_kind"] == kind, (skill, args, r, out[:200])
    return out


# ---------------------------------------------------------------- search_text
def t_search_text():
    """search_text：數量跟標頭一致；每個檔案的筆數與命中的行全部記（文字每檔只列 20 筆）；0 筆＝empty；參數、路徑錯＝args"""
    d = _tmp()
    _w(d, "a/x.py", "foo\nfoo bar\nbaz\nfoo\n")
    _w(d, "a/y.md", "nothing\nFOO here\n")
    _w(d, "b/z.py", "".join(f"foo {k}\n" for k in range(25)))
    _w(d, "build/skip.py", "foo\n")                      # 預設略過的目錄
    out, r = run("search_text", "foo", ".", d=d)
    m = re.search(r"共 (\d+) 筆命中，分布在 (\d+) 個檔案", out)
    assert m and r["status"] == "pass" and r["counts"] == {"hits": int(m.group(1)), "files": int(m.group(2))}, (out[:200], r["counts"])
    assert r["counts"] == {"hits": 29, "files": 3} and sum(r["per_file"].values()) == 29, r["per_file"]
    z = os.path.join(d, "b", "z.py")
    assert r["per_file"][z] == 25 and [i["line"] for i in r["items"] if i["path"] == z] == list(range(1, 26)), "收據要有全部 25 行"
    assert "只列前 20 筆" in out and not r["truncated"]
    assert [i["line"] for i in r["items"] if i["path"].endswith("x.py")] == [1, 2, 4]
    assert "build" in r["excluded_dirs"] and r["pattern"] == "foo" and r["paths"] == [d]
    _, r = run("search_text", "foo", ".", "--include", "*.py", "-w", d=d)
    assert set(r["per_file"]) == {os.path.join(d, "a", "x.py"), z} and r["options"]["word"] and r["options"]["include"] == ["*.py"]
    out, r = run("search_text", "foo", ".", "--include", "*.md|*.py", d=d)
    assert r["options"]["include"] == ["*.md", "*.py"] and r["counts"] == {"hits": 29, "files": 3}, ("用 | 寫在一起的幾種檔名拆開搜", r["options"], r["counts"])
    assert "--include 一次一種寫法：「*.md|*.py」拆成 *.md、*.py" in out, out[-400:]
    _, r = run("search_text", "foo|bar", "a", "--rank", d=d)
    assert r["options"]["rank"] and [(i["line"], i["words"]) for i in r["items"] if i["path"].endswith("x.py")] == [(1, 1), (2, 2), (4, 1)], r["items"]
    _, r = run("search_text", "foo", "a", "--rank", d=d)
    assert all("words" not in i for i in r["items"]), "只有一個字：不記 words"
    _, r = run("search_text", "zzz_not_here", ".", d=d)
    assert r["status"] == "empty" and r["counts"] == {"hits": 0, "files": 0} and r["items"] == []
    _error("search_text", "args", "foo", "nope_dir", d=d)
    _error("search_text", "args", "foo", ".", "--bogus", d=d)
    _error("search_text", "args", d=d)


# ---------------------------------------------------------------- find_file
def t_find_file():
    """find_file：總數、檔案數、目錄數跟標頭一致；每個項目的路徑與種類；0 個＝empty；路徑與選項錯＝args"""
    d = _tmp()
    for rel in ("src/launch/a.launch.py", "src/launch/b.launch.py", "src/x.py", "docs/launch.md"):
        _w(d, rel, "x\n")
    out, r = run("find_file", "launch", ".", d=d)
    m = re.search(r"找到 (\d+) 個.*?（(\d+) 個檔案、(\d+) 個目錄", out)
    assert m and r["counts"] == {"total": int(m.group(1)), "files": int(m.group(2)), "dirs": int(m.group(3))}, (out[:200], r)
    assert r["counts"] == {"total": 4, "files": 3, "dirs": 1} and r["match"] == "contains" and r["root"] == d
    assert {(os.path.relpath(i["path"], d), i["kind"]) for i in r["items"]} == {
        ("src/launch", "dir"), ("src/launch/a.launch.py", "file"), ("src/launch/b.launch.py", "file"), ("docs/launch.md", "file")}
    _, r = run("find_file", "*.py", "src", "--type", "f", d=d)
    assert r["match"] == "glob" and r["type"] == "f" and r["counts"]["total"] == 3
    _, r = run("find_file", "nothing_like_this", ".", d=d)
    assert r["status"] == "empty" and r["counts"] == {"total": 0, "files": 0, "dirs": 0}
    _error("find_file", "args", "launch", "nope_dir", d=d)
    _error("find_file", "args", "launch", ".", "--type", "x", d=d)


# ---------------------------------------------------------------- list_dir
def t_list_dir():
    """list_dir：數量跟標頭一致；收據列全部的項目（不受 200 行限制）；--filter 記符合的數量；空目錄＝empty；錯誤的種類"""
    d = _tmp()
    for k in range(205):
        _w(d, f"big/f{k:03d}.txt", "x")
    _w(d, "big/sub/inner.txt", "x")
    os.symlink(os.path.join(d, "big", "f000.txt"), os.path.join(d, "big", "link.txt"))
    os.makedirs(os.path.join(d, "empty"))
    out, r = run("list_dir", "big", d=d)
    m = re.search(r"共 (\d+) 項（(\d+) 個檔案、(\d+) 個目錄", out)
    c = r["counts"]
    assert m and (c["total"], c["files"], c["dirs"]) == tuple(int(x) for x in m.groups()), (out[:200], c)
    assert c == {"total": 207, "files": 206, "dirs": 1, "links": 1, "unreadable": 0} and len(r["items"]) == 207, c
    assert "只列前 200 行" in out and r["items"][0]["name"] == "sub" and r["items"][0]["kind"] == "dir"
    assert any(i["link"] for i in r["items"]) and r["path"] == os.path.join(d, "big")
    _, r = run("list_dir", "big", "--filter", "f00", d=d)
    assert r["counts"]["matched"] == 10 and len(r["items"]) == 10 and r["filter"] == "f00"
    _, r = run("list_dir", "big", "--newest", "3", d=d)
    assert len(r["items"]) == 3 and r["newest"] == 3
    _, r = run("list_dir", "empty", d=d)
    assert r["status"] == "empty" and r["counts"]["total"] == 0
    _error("list_dir", "args", "nope_dir", d=d)
    _error("list_dir", "args", "big/f000.txt", d=d)          # 是檔案不是目錄
    _error("list_dir", "args", "big", "--bogus", d=d)
    if not IS_ROOT:
        locked = os.path.join(d, "locked")
        os.makedirs(locked)
        os.chmod(locked, 0)
        try:
            _error("list_dir", "env", "locked", d=d)
        finally:
            os.chmod(locked, 0o755)


# ---------------------------------------------------------------- view_file
def t_view_file():
    """view_file：總行數與顯示的範圍；沒看完＝truncated；空檔案＝empty；二進位檔、超出範圍、目錄、找不到＝args"""
    d = _tmp()
    _w(d, "ten.txt", "".join(f"line {k}\n" for k in range(1, 11)))
    _w(d, "empty.txt", "")
    _w(d, "bin.dat", b"\x00\x01\x02binary")
    out, r = run("view_file", "ten.txt", d=d)
    size = os.path.getsize(os.path.join(d, "ten.txt"))
    assert r["status"] == "pass" and r["counts"] == {"total_lines": 10, "from": 1, "to": 10, "bytes": size} and not r["truncated"], r
    assert r["items"] == [{"path": os.path.join(d, "ten.txt"), "from": 1, "to": 10}] and r["encoding"] == "utf-8"
    _, r = run("view_file", "ten.txt", "--from", "3", "--lines", "2", d=d)
    assert (r["counts"]["from"], r["counts"]["to"]) == (3, 4) and r["truncated"], r
    _, r = run("view_file", "ten.txt", "--tail", "3", d=d)
    assert (r["counts"]["from"], r["counts"]["to"]) == (8, 10) and r["tail"] and r["around"] is None
    _, r = run("view_file", "ten.txt", "--around", "5", "-C", "1", d=d)
    assert (r["counts"]["from"], r["counts"]["to"], r["around"]) == (4, 6, 5) and r["truncated"], r
    _error("view_file", "args", "ten.txt", "--around", "11", d=d)
    _, r = run("view_file", "empty.txt", d=d)
    assert r["status"] == "empty" and r["counts"]["total_lines"] == 0
    _error("view_file", "args", "bin.dat", d=d)
    _error("view_file", "args", "ten.txt", "--from", "99", d=d)
    _error("view_file", "args", ".", d=d)
    _error("view_file", "args", "nope.txt", d=d)


def t_near_paths():
    """找不到路徑：收據記相近的路徑（near，低階執行器的第 1 級照它判斷：好幾個時不替上一層選）；給模型的文字照舊列「相近的路徑」；
    沒有相近的不記"""
    d = _tmp()
    for rel in ("proj_x/specs/a.md", "proj_y/specs/b.md", "solo/notes/c.md"):
        _w(d, rel, "spec\n")
    out, r = run("search_text", "spec", "specs", d=d)
    assert r["status"] == "error" and r["error_kind"] == "args" and sorted(r["near"]) == ["proj_x/specs", "proj_y/specs"], r
    assert "相近的路徑：" in out and "proj_x/specs" in out and "proj_y/specs" in out, out
    _, r = run("list_dir", "notes", d=d)
    assert r["status"] == "error" and r["near"] == ["solo/notes"], r
    _, r = run("view_file", "zzz_nothing.md", d=d)
    assert r["status"] == "error" and r["error_kind"] == "args" and "near" not in r, r


# ---------------------------------------------------------------- code_ast_reader
_PY = '''"""模組"""
LIMIT = 3
_HIDDEN = 1


class Box(Base):
    def open(self):
        def helper():
            return 1
        return helper()

    def _secret(self):
        return 2

    @staticmethod
    async def fetch():
        return 3


def top(a, b=1):
    return a
'''


def t_code_ast_reader():
    """code_ast_reader：收據列全部的定義（含私有、巢狀；文字預設不列私有）——qualname、所在的類別或函式、行號範圍（從 def 那一行算，
    裝飾器另記 decorator，文字另寫一行）；拿行號查得到在哪個函式裡；不是 Python、語法錯誤＝args"""
    d = _tmp()
    _w(d, "m.py", _PY)
    _w(d, "bad.py", "def broken(:\n")
    _w(d, "notes.txt", "x")
    out, r = run("code_ast_reader", "m.py", d=d)
    assert "_secret" not in out and r["status"] == "pass", "文字預設不列私有的，收據要列"
    defs = {i["qualname"]: i for i in r["items"]}
    assert set(defs) == {"Box", "Box.open", "Box.open.helper", "Box._secret", "Box.fetch", "top"}, set(defs)
    assert defs["Box._secret"]["private"] and defs["Box._secret"]["kind"] == "method" and defs["Box._secret"]["parent"] == "Box"
    assert defs["Box.open.helper"]["kind"] == "function" and defs["Box.open.helper"]["parent"] == "open"
    assert defs["Box.fetch"]["async"] and (defs["Box.fetch"]["line"], defs["Box.fetch"]["decorator"], defs["Box.fetch"]["end"]) == (16, 15, 17), \
        ("定義的行號是 def 那一行，裝飾器另記", defs["Box.fetch"])
    assert "decorator" not in defs["Box.open"] and "start" not in defs["Box.open"], defs["Box.open"]
    assert "\n  @staticmethod  行 15\n  async def fetch()  行 16-17\n" in out, out
    assert r["counts"] == {"lines": len(_PY.splitlines()), "classes": 1, "functions": 5, "constants": 2}, r["counts"]
    assert {c["name"] for c in r["constants"]} == {"LIMIT", "_HIDDEN"}
    line = 9                                              # helper 的 return：最內層的函式是 helper
    inner = [i for i in r["items"] if i["kind"] != "class" and i["line"] <= line <= i["end"]]
    assert min(inner, key=lambda i: i["end"] - i["line"])["qualname"] == "Box.open.helper"
    _error("code_ast_reader", "args", "bad.py", d=d)
    _error("code_ast_reader", "args", "notes.txt", d=d)
    _error("code_ast_reader", "args", "m.py", "--bogus", d=d)


def t_code_ast_reader_refs():
    """code_ast_reader --refs：收據一處一筆（種類、行號、所在的函式、檔案的路徑；定義另有 qualname、in_class、行號範圍——從 def 那一行算，
    裝飾器另記 decorator、文字另寫）；數量跟標頭一致；沒有＝empty"""
    d = _tmp()
    _w(d, "m.py", _PY + "\n\nBox().open()\nx = top\nfrom m import top\n")
    out, r = run("code_ast_reader", "m.py", "--refs", "open", d=d)
    assert r["status"] == "pass" and r["refs"] == "open" and r["path"] == os.path.join(d, "m.py"), r
    assert r["counts"] == {"lines": len(_PY.splitlines()) + 5, "refs": 2, "defs": 1, "calls": 1, "imports": 0, "assigns": 0, "others": 0}
    defn = [i for i in r["items"] if i["kind"] == "def"][0]
    assert defn["qualname"] == "Box.open" and defn["in_class"] == "Box" and defn["line"] == 7 and defn["end"] == 10 and "decorator" not in defn, defn
    call = [i for i in r["items"] if i["kind"] == "call"][0]
    assert call["scope"] is None and call["path"] == r["path"] and call["text"] == "Box().open()", call
    out, r = run("code_ast_reader", "m.py", "--refs", "top", d=d)
    assert {i["kind"] for i in r["items"]} == {"def", "ref", "import"} and r["counts"]["refs"] == 3, r["items"]
    assert "出現 3 處" in out
    out, r = run("code_ast_reader", "m.py", "--refs", "fetch", d=d)
    defn = [i for i in r["items"] if i["kind"] == "def"][0]
    assert (defn["line"], defn["decorator"], defn["end"]) == (16, 15, 17) and "- 行 16-17（在 Box；裝飾器在行 15）：async def fetch():" in out, (defn, out)
    out, r = run("code_ast_reader", "m.py", "--refs", "absent_name", d=d)
    assert r["status"] == "empty" and r["items"] == [] and r["counts"]["refs"] == 0, r
    _error("code_ast_reader", "args", "m.py", "--refs", "a.b", d=d)


# ---------------------------------------------------------------- code_defs、py_refs（領域 session 用）
def t_code_defs():
    """code_defs：數量跟標頭一致；每一個定義一筆（路徑、行號、結束的行、種類、名稱、qualname；行號從 def 那一行算，裝飾器另記），
    每份檔案的行數與數量（per_file）；文字只列前幾個時收據照樣全部記；沒有符合的檔案＝empty；路徑、選項錯＝args"""
    d = _tmp()
    _w(d, "p/a.py", "class A:\n    def m(self):\n        pass\n\n\ndef f():\n    pass\n")
    _w(d, "p/b.cpp", "struct S { int x; };\nint S2::get() const {\n  return 1;\n}\n")
    _w(d, "p/doc.md", "x\ny\n")
    out, r = run("code_defs", "p", d=d)
    m = re.search(r"(\d+) 份檔案、共 (\d+) 行；定義：類別 (\d+)、函式／方法 (\d+)", out)
    assert m and r["status"] == "pass" and r["counts"] == {"files": int(m.group(1)), "lines": int(m.group(2)), "classes": int(m.group(3)),
                                                           "functions": int(m.group(4))}, (out[:200], r["counts"])
    assert r["counts"] == {"files": 3, "lines": 13, "classes": 2, "functions": 3}, r["counts"]
    by = {(os.path.basename(i["path"]), i["qualname"]): i for i in r["items"]}
    assert set(by) == {("a.py", "A"), ("a.py", "A.m"), ("a.py", "f"), ("b.cpp", "S"), ("b.cpp", "S2::get")}, set(by)
    assert by[("a.py", "A.m")]["kind"] == "method" and by[("a.py", "A.m")]["line"] == 2 and by[("b.cpp", "S2::get")]["end"] == 4
    assert [(os.path.basename(x["path"]), x["lines"]) for x in r["per_file"]] == [("a.py", 7), ("b.cpp", 4), ("doc.md", 2)], r["per_file"]
    assert r["paths"] == [os.path.join(d, "p")] and "build" in r["exclude_dirs"]
    _w(d, "big/many.py", "".join(f"def f{k}():\n    pass\n" for k in range(700)))
    out, r = run("code_defs", "big", d=d)
    assert "定義只列前 600 個" in out and len(r["items"]) == 700 and r["counts"]["functions"] == 700, "收據要有全部的定義"
    _w(d, "q/k.py", "class K:\n    @classmethod\n    def make(cls):\n        return cls()\n")
    out, r = run("code_defs", "q", d=d)
    make = [i for i in r["items"] if i["qualname"] == "K.make"][0]
    assert (make["line"], make["decorator"], make["end"]) == (3, 2, 4) and "  - def K.make（行 3-4；裝飾器在行 2）" in out, ("定義從 def 那一行算", make, out)
    _, r = run("code_defs", "p", "--include", "*.cpp|*.md", d=d)
    assert r["include"] == ["*.cpp", "*.md"] and r["counts"]["files"] == 2, ("用 | 寫在一起的幾種檔名拆開", r["include"], r["counts"])
    out, r = run("code_defs", "p", "--include", "*.rs", d=d)
    assert r["status"] == "empty" and r["counts"]["files"] == 0 and r["items"] == [] and "has" not in r
    out, r = run("code_defs", "p", "--has", "s2", d=d)
    assert r["has"] == ["s2"] and [i["qualname"] for i in r["items"]] == ["S2::get"] and r["counts"]["functions"] == 1, ("--has 記篩選的字", r)
    _error("code_defs", "args", "nope_dir", d=d)
    _error("code_defs", "args", "p", "--kind", "x", d=d)


def t_py_refs():
    """py_refs：數量跟標頭一致；每一處一筆（路徑、行號、種類、所在的函式、原始碼；定義另有 qualname、in_class、行號範圍——從 def 那一行算，
    裝飾器另記），每個檔案的數量（per_file）；Python 沒有、C++ 檔有時記 cpp_files；沒有＝empty；名稱、路徑錯＝args"""
    d = _tmp()
    _w(d, "p/a.py", "def run():\n    pass\n\n\nclass B:\n    def go(self):\n        return run()\n")
    _w(d, "p/c.py", "from p.a import run\nrun()\nrun()\n")
    _w(d, "p/x.hpp", "void only_cpp();\n")
    out, r = run("py_refs", "run", "p", d=d)
    m = re.search(r"出現 (\d+) 處、(\d+) 份檔案", out)
    assert m and r["status"] == "pass" and r["counts"]["refs"] == int(m.group(1)) and r["counts"]["files"] == int(m.group(2)), (out[:200], r)
    assert r["counts"] == {"refs": 5, "files": 2, "defs": 1, "calls": 3, "imports": 1, "assigns": 0, "others": 0, "scanned": 2}, r["counts"]
    defn = [i for i in r["items"] if i["kind"] == "def"][0]
    assert defn["qualname"] == "run" and defn["line"] == 1 and defn["end"] == 2 and "decorator" not in defn and defn["path"] == os.path.join(d, "p", "a.py"), defn
    call = [i for i in r["items"] if i["kind"] == "call" and i["path"].endswith("a.py")][0]
    assert call["scope"] == "B.go" and call["line"] == 7 and call["text"] == "return run()", call
    assert [(os.path.basename(x["path"]), x["refs"], x["call"]) for x in r["per_file"]] == [("a.py", 2, 1), ("c.py", 3, 2)], r["per_file"]
    _w(d, "q/k.py", "class K:\n    @classmethod\n    def make(cls):\n        return cls()\n\n\nK.make()\n")
    out, r = run("py_refs", "make", "q", d=d)
    defn = [i for i in r["items"] if i["kind"] == "def"][0]
    assert (defn["line"], defn["decorator"], defn["end"]) == (3, 2, 4) and "  - 定義 行 3-4（在 K；裝飾器在行 2）：def make(cls):" in out, \
        ("定義的行號是 def 那一行（不是裝飾器那一行），裝飾器另外寫", defn, out)
    _, r = run("py_refs", "run", "p", "--include", "a.py|c.py", d=d)
    assert r["counts"]["refs"] == 5 and r["counts"]["scanned"] == 2, ("用 | 寫在一起的幾種檔名拆開", r["counts"])
    out, r = run("py_refs", "only_cpp", "p", d=d)
    assert r["status"] == "empty" and r["cpp_files"] == [os.path.join(d, "p", "x.hpp")] and r["counts"]["refs"] == 0, r
    _error("py_refs", "args", "a.b", "p", d=d)
    _error("py_refs", "args", "run", "nope_dir", d=d)


# ---------------------------------------------------------------- result_list／result_grep／result_view
def _archive(d, session, rid, stem, body):
    name = f"{session}_{rid:03d}_{stem}.md"
    head = f"---\nid: {rid}\nsession: {session}\nscript: {stem}_cmd.py\ncommand: x\nstatus: PASS\n---\n"
    _w(d, os.path.join("results", name), head + body)
    with open(os.path.join(d, "results", "index.md"), "a", encoding="utf-8") as f:
        f.write(f"#{rid} | 2026-11-18 12:00 | {stem}_cmd.py | PASS | {len(body)} 字 | {name} | 任務：t | 回答：\n")


def t_results():
    """result_list／result_grep／result_view：存檔的編號、命中的行、看的範圍；沒有存檔＝empty；編號不存在、起始行超過＝args"""
    d = _tmp()
    os.makedirs(os.path.join(d, "results"))
    env = {"TOOL_RESULTS_DIR": os.path.join(d, "results"), "HARNESS_SESSION": "20261118_120000"}
    _, r = run("result_list", d=d, **env)
    assert r["status"] == "empty" and r["counts"]["total"] == 0
    _error("result_view", "args", "5", d=d, **env)
    _archive(d, "20261118_120000", 5, "grep", "[PASS] 搜尋：共 3 筆\n## a.py（2 筆）\n    3→ timeout here\n    9→ TIMEOUT again\n## b.py\n    1→ fine\n")
    _archive(d, "20261118_120000", 6, "ls", "".join(f"row {k}\n" for k in range(1, 101)))
    _, r = run("result_list", d=d, **env)
    assert r["status"] == "pass" and [i["id"] for i in r["items"]] == [6, 5] and r["counts"]["total"] == 2
    _, r = run("result_grep", "5", "timeout", d=d, **env)
    assert r["counts"] == {"hits": 2, "files": 1} and [(i["id"], i["line"]) for i in r["items"]] == [(5, 3), (5, 4)], r
    assert r["per_file"] == {"5": 2}
    _, r = run("result_grep", "5", "nothing_here", d=d, **env)
    assert r["status"] == "empty"
    _, r = run("result_view", "6", "--from", "10", "--lines", "5", d=d, **env)
    assert r["counts"] == {"total_lines": 100, "from": 10, "to": 14} and r["truncated"] and r["mode"] == "lines" and r["id"] == 6
    _, r = run("result_view", "5", "--outline", d=d, **env)
    assert r["mode"] == "outline" and [i["line"] for i in r["items"]] == [2, 5], r["items"]
    _error("result_view", "args", "99", d=d, **env)
    _error("result_view", "args", "6", "--from", "500", d=d, **env)
    _error("result_grep", "args", "99", "x", d=d, **env)


# ---------------------------------------------------------------- 收據的進入點
def t_receipt_main():
    """_receipt_common.main：未預期的例外＝parse（exit code 1、[ERROR] 到 stderr）；回 [ERROR] 卻沒記收據＝parse；
    共用層的 ToolError 帶著種類；沒有 AGENT_RECEIPT_PATH 不寫"""
    sys.path.insert(0, SCRIPTS)
    import _receipt_common as rc
    d = _tmp()
    path = os.path.join(d, "r.json")

    def go(execute):
        if os.path.exists(path):
            os.remove(path)
        out, err = io.StringIO(), io.StringIO()
        code = 0
        old = os.environ.get(rc.ENV)
        os.environ[rc.ENV] = path
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc.main(execute, "t")
        except SystemExit as e:
            code = e.code
        finally:
            if old is None:
                os.environ.pop(rc.ENV, None)
            else:
                os.environ[rc.ENV] = old
        with open(path, encoding="utf-8") as f:
            return code, out.getvalue(), err.getvalue(), json.load(f)

    def boom(argv):
        raise ValueError("bad")
    code, _, err, r = go(boom)
    assert code == 1 and "未預期的例外" in err and r["error_kind"] == "parse", (code, err, r)
    _, out, _, r = go(lambda argv: "[ERROR] 沒有記收據")
    assert out.startswith("[ERROR]") and r["status"] == "error" and r["error_kind"] == "parse" and "沒有記收據" in r["note"]
    _, _, _, r = go(lambda argv: rc.ToolError("[ERROR] 沒有權限", "env"))
    assert r["error_kind"] == "env"

    def recorded_pass_but_error(argv):
        rc.result("pass", counts={"n": 1})
        return "[ERROR] 後來失敗了"
    _, _, _, r = go(recorded_pass_but_error)
    assert r["error_kind"] == "parse", "記成 pass 卻回 [ERROR]：當成腳本的錯"
    _, _, _, r = go(lambda argv: (rc.result("pass", items=list(range(rc.ITEMS_MAX + 5))), "[PASS] ok")[1])
    assert len(r["items"]) == rc.ITEMS_MAX and r["truncated"]
    os.environ.pop(rc.ENV, None)
    os.remove(path)
    with contextlib.redirect_stdout(io.StringIO()):
        rc.main(lambda argv: (rc.result("empty"), "[PASS] 0 筆")[1], "t")
    assert not os.path.exists(path), "沒有 AGENT_RECEIPT_PATH 就不寫"


# ---------------------------------------------------------------- 規格（放最後：用上面收到的收據）
def t_spec_matches_receipts():
    """規格的 parameters（必填的一定寫 fetch 或 ask）與 receipt 跟腳本寫的收據一致；載入給模型時拿掉這兩個欄位"""
    sys.path.insert(0, PROJECT)
    from agent_core import skill_spec
    if not SEEN:
        raise Skip("這一組的其他情境沒有跑（單獨跑這一個情境沒有收據可以核對）")
    for skill in V1:
        with open(os.path.join(PROJECT, "skills_system", "tools", f"{skill}.md"), encoding="utf-8") as f:
            text = f.read()
        spec = skill_spec.contract(text)
        model = skill_spec.for_model(text)
        assert "\nparameters:" not in model and "\nreceipt:" not in model and model.startswith("---\ntype: Tool"), skill
        params = spec["parameters"]
        assert len({p["name"] for p in params}) == len(params), skill
        for p in params:
            if p["required"]:
                assert ("fetch" in p) != ("ask" in p), (skill, p, "必填的參數要寫 fetch 或 ask（只寫一個）")
        want = spec["receipt"]
        oks = [r for r in SEEN.get(skill, []) if r["status"] in ("pass", "empty")]
        assert any(r["status"] == "pass" for r in oks), f"{skill} 這一組沒有測到 pass 的收據"

        def check(got, declared, what):
            names = {x.rstrip("?") for x in declared}
            required = {x for x in declared if not x.endswith("?")}
            assert set(got) <= names, (skill, what, "規格沒寫的", set(got) - names)
            assert required <= set(got), (skill, what, "規格寫了、收據沒有的", required - set(got))
        for r in oks:
            check(r["counts"], want["counts"], "counts")
            check({k: v for k, v in r.items() if k not in COMMON}, want["fields"], "fields")
            for item in r["items"]:
                assert set(item) <= {x.rstrip("?") for x in want["items"]}, (skill, "items", set(item))
        if not any(x.endswith("?") for x in want["items"]):
            for r in oks:
                for item in r["items"]:
                    check(item, want["items"], "items")


def t_parse_args_contract():
    """寫收據的腳本都有純函式 parse_args（最後一個回傳值是錯誤；低階執行器執行前用它檢查參數）；規格的 narrow 寫的是 parse_args 結果的鍵；
    規格的腳本（skill_spec.script）就是這支；載入給模型時 narrow 也拿掉。規格寫了 listing 的（程式整理好的清單，放得進一段時直接給原文；
    設計筆記 2.68）只有六個清單型的技能、值是 true、載入給模型時拿掉"""
    import importlib
    sys.path.insert(0, PROJECT)
    from agent_core import skill_spec
    ok_args = {"search_text": ["x", "."], "find_file": ["x", "."], "list_dir": ["."], "view_file": ["a.txt"],
               "code_ast_reader": ["a.py", "--refs", "x"], "result_list": [], "result_grep": ["latest", "x"], "result_view": ["latest"],
               "code_defs": ["."], "py_refs": ["x", "."]}
    narrowed, listed = [], []
    for skill, script in V1.items():
        with open(os.path.join(PROJECT, "skills_system", "tools", f"{skill}.md"), encoding="utf-8") as f:
            text = f.read()
        assert skill_spec.script(text, skill) == script, (skill, skill_spec.script(text, skill))
        mod = importlib.import_module(f"skills_system.scripts.{script[:-3]}")
        out = mod.parse_args(ok_args[skill])
        assert isinstance(out, tuple) and out[-1] is None, (skill, out)
        bad = mod.parse_args(ok_args[skill] + ["--no-such-option"])
        assert isinstance(bad, tuple) and str(bad[-1]).startswith("[ERROR]"), (skill, bad)
        narrow = skill_spec.contract(text).get("narrow")
        if narrow:
            narrowed.append(skill)
            assert isinstance(out[0], dict) and set(narrow) <= set(out[0]), (skill, set(narrow) - set(out[0] or {}))
            assert all(r["rule"] in ("inside", "added") and r.get("arg") for r in narrow.values()), (skill, narrow)
            assert "\nnarrow:" not in skill_spec.for_model(text), skill
        if "listing" in skill_spec.contract(text):
            listed.append(skill)
            assert skill_spec.contract(text)["listing"] is True and "\nlisting:" not in skill_spec.for_model(text), skill
    assert sorted(narrowed) == ["code_defs", "find_file", "py_refs", "search_text"], narrowed
    assert sorted(listed) == ["code_defs", "find_file", "list_dir", "py_refs", "result_grep", "search_text"], listed
