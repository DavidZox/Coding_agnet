"""本機檔案與指令類技能的離線測試：list_dir、search_text、find_file、code_ast_reader、code_defs、py_refs、change_dir、view_file、host_runcmd、csv_query、
file_ops、modify_memory、stt_engine、image_inspect（規範見 doc/技能撰寫規範.md）。

每個情境在新的臨時目錄跑（cwd＝臨時目錄）；會寫檔的技能用 HARNESS_LOGS_DIR／HARNESS_MEMORY_FILE 指到臨時目錄，不碰正式的 logs/ 與
prompts/Memory.md。外部的東西用假的：faster-whisper 用假的套件（PYTHONPATH）、Ollama 用本機的假 HTTP 服務（OLLAMA_HOST）、
docker inspect 用 PATH 前面的假 docker。以 root 執行時（權限擋不住 root）略過權限的情境。

    python3 evals/skills/selftest.py fs
"""
import base64
import io
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import threading
import time

from selftest import SCRIPTS, Skip, assert_error, first_line, run_script

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


# ---------------------------------------------------------------- 共用
def _tmp():
    d = tempfile.mkdtemp(prefix="skills_fs_")
    os.makedirs(os.path.join(d, "_logs"), exist_ok=True)
    return d


def _w(d, rel, text="", mode=None):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w" if isinstance(text, str) else "wb", **({"encoding": "utf-8"} if isinstance(text, str) else {})) as f:
        f.write(text)
    if mode is not None:
        os.chmod(p, mode)
    return p


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _env(d, **extra):
    e = {"HARNESS_LOGS_DIR": os.path.join(d, "_logs"), "HARNESS_MEMORY_FILE": os.path.join(d, "Memory.md"),
         "HARNESS_RAW_ARGS": "", "TARGET_CONTAINER": "", "AGENT_ABLATE": ""}
    e.update(extra)
    return e


def run(name, *args, d, **extra):
    rc, out = run_script(name, *args, cwd=d, env=_env(d, **extra), timeout=120)
    return out


def run_raw(name, raw, d, **extra):
    """跟 harness 一樣：action.args 原文用 shlex 拆成參數（空字串丟掉），原文另外放在 HARNESS_RAW_ARGS。"""
    try:
        argv = [a for a in shlex.split(raw) if a != ""]
    except ValueError:
        argv = [a.strip("\"'") for a in raw.split()]
    rc, out = run_script(name, *argv, cwd=d, env=_env(d, HARNESS_RAW_ARGS=raw, **extra), timeout=120)
    return out


class _Locked:
    """chmod 000 的目錄（離開時改回來，臨時目錄才刪得掉）。"""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        if IS_ROOT:
            raise Skip("以 root 執行，權限擋不住 root")
        os.makedirs(self.path, exist_ok=True)
        os.chmod(self.path, 0)
        return self.path

    def __exit__(self, *a):
        os.chmod(self.path, 0o755)


# ================================================================ list_dir（ls_cmd.py）
def t_list_dir_sections():
    """list_dir：目錄與檔案分兩節、數量、最新修改、每行的欄位（大小寫明單位：位元組，不是行數）、連結寫指向哪裡"""
    d = _tmp()
    _w(d, "a.txt", "x")
    _w(d, "b.py", "y")
    os.makedirs(os.path.join(d, "sub"))
    os.symlink("sub", os.path.join(d, "lnk"))
    out = run("ls_cmd.py", ".", d=d)
    assert first_line(out).startswith("[PASS] 目錄列表 (.)：共 5 項（2 個檔案、3 個目錄，其中 1 個是連結）"), out
    assert "\n最新修改：" in out and "## 目錄（3 項）" in out and "## 檔案（2 項）" in out, out
    assert "lnk@ → sub/" in out and "sub/" in out, out
    lines = out.split("\n")
    assert lines[2] == "（每行：權限、大小（位元組，B）、修改時間、名稱；大小不是行數）", ("最新修改的下一行寫明每行的欄位", lines[:4])
    row = next(ln for ln in lines if ln.endswith(" a.txt"))
    assert " 1 B " in row, ("大小寫成 <數字> B", row)


def t_list_dir_cap():
    """list_dir：超過 200 行只列前 200 行，並說用 --filter／--newest 縮小"""
    d = _tmp()
    for i in range(250):
        _w(d, f"many/f{i:03d}.log", "x")
    out = run("ls_cmd.py", "many", d=d)
    assert "共 250 項" in first_line(out) and "只列前 200 行" in first_line(out), first_line(out)
    assert "## 檔案（250 項，只列前 200 項）" in out and "--filter" in out.splitlines()[-1], out[-300:]
    assert len([ln for ln in out.splitlines() if ln.startswith("-rw")]) == 200
    out = run("ls_cmd.py", "many", "--newest", "2", d=d)
    assert "依修改時間新→舊只列前 2 項" in first_line(out) and "## 依修改時間新→舊（2 項）" in out, out


def t_list_dir_tilde_and_errors():
    """list_dir：~ 展開；不存在（相近的路徑）、是檔案、好幾個路徑、不認識的選項都是 [ERROR] 加下一步"""
    d = _tmp()
    _w(d, "home/proj/x.txt", "x")
    _w(d, "scripts/a.py", "x")
    out = run("ls_cmd.py", "~/proj", d=d, HOME=os.path.join(d, "home"))
    assert out.startswith("[PASS]") and "共 1 項" in out, out
    out = run("ls_cmd.py", "script", d=d)
    assert_error(out, "找不到目錄", "相近的路徑：scripts")
    out = run("ls_cmd.py", "~/nope_dir", d=d, HOME=os.path.join(d, "home"))
    assert_error(out, "找不到目錄", "展開為", "下一步")
    assert_error(run("ls_cmd.py", "scripts/a.py", d=d), "不是目錄", "view_file")
    assert_error(run("ls_cmd.py", "scripts", "home", d=d), "一次只能列一個目錄", "下一步")
    assert_error(run("ls_cmd.py", "--bogus", d=d), "不認識的選項", "用法")


def t_list_dir_permission():
    """list_dir：沒有權限的目錄回 [ERROR] 與下一步（不會用 sudo）"""
    d = _tmp()
    with _Locked(os.path.join(d, "locked")):
        assert_error(run("ls_cmd.py", "locked", d=d), "沒有權限", "下一步")


# ================================================================ search_text（grep_cmd.py）
def _grep_tree(d):
    _w(d, "src/a.py", "error one\nok\nfail two\n--timeout 5\nprint(a[0])\n")
    _w(d, "src/pkg/many.log", "".join(f"error {i}\n" for i in range(1, 31)))
    _w(d, "src/long.txt", "error " + "x" * 1000 + "\n")
    _w(d, "build/gen.txt", "error in build\n")
    _w(d, "tree2/t.txt", "grep is a tool\n")


def t_search_grouped_and_caps():
    """search_text：依檔案分組（## 路徑（N 筆）、行號→內容）、每檔 20 筆、單行 300 字截斷，第一行說只列前幾筆"""
    d = _tmp()
    _grep_tree(d)
    out = run("grep_cmd.py", "error", "src", d=d)
    head = first_line(out)
    assert head.startswith("[PASS] 搜尋「error」：共 32 筆命中，分布在 3 個檔案"), head
    assert "只列前 22 筆" in head and "截斷" in head, head
    assert "## src/pkg/many.log（30 筆，只列前 20 筆）" in out and "## src/a.py（1 筆）" in out, out
    assert "     1→error one" in out and "這一行共 1006 字，截斷" in out, out


def t_search_alternation_regression():
    """search_text：a|b 是同義詞（以前是 BRE，error|fail 被當成字面、回「找不到」）"""
    d = _tmp()
    _grep_tree(d)
    out = run("grep_cmd.py", "error|fail", "src/a.py", d=d)
    assert "共 2 筆命中" in first_line(out) and "→fail two" in out, out
    out = run("grep_cmd.py", "error\\|fail", "src/a.py", d=d)       # BRE 的寫法也接受
    assert "共 2 筆命中" in first_line(out), out


def t_search_invalid_regex_falls_back():
    """search_text：不合法的正規表示式改成照字面搜並註明（以前回 grep: Unmatched [ 的原文）"""
    d = _tmp()
    _grep_tree(d)
    out = run("grep_cmd.py", "a[0", "src", d=d)
    assert out.startswith("[PASS]") and "照字面" in out and "print(a[0])" in out, out


def t_search_exclude_dir_keeps_recursion():
    """search_text：--exclude-dir 不會讓遞迴消失（以前變成 grep: src: Is a directory）；預設略過 build，--all-dirs 才搜"""
    d = _tmp()
    _grep_tree(d)
    out = run("grep_cmd.py", "error", "--exclude-dir=pkg", ".", d=d)
    assert out.startswith("[PASS]") and "src/a.py" in out and "many.log" not in out, out
    assert "build/gen.txt" not in out and "--all-dirs" in out.splitlines()[-1], out
    out = run("grep_cmd.py", "error", ".", "--all-dirs", d=d)
    assert "## build/gen.txt（1 筆）" in out, out


def t_search_permission_keeps_results():
    """search_text：有一個目錄沒有權限時保留其他結果、計數略過的路徑（以前 exit 2 → 全部丟掉）"""
    d = _tmp()
    _grep_tree(d)
    with _Locked(os.path.join(d, "src", "locked")):
        out = run("grep_cmd.py", "error", "src", d=d)
    assert out.startswith("[PASS]") and "共 32 筆命中" in out and "1 個路徑沒有權限（略過）" in out, out


def t_search_keyword_regressions():
    """search_text：關鍵字 grep 不會被刪掉、-- 開頭的關鍵字（"--timeout" 或 -e）可以搜"""
    d = _tmp()
    _grep_tree(d)
    out = run("grep_cmd.py", "grep", "tree2", d=d)
    assert "## tree2/t.txt（1 筆）" in out, out
    for args in (("--timeout", "src"), ("-e", "--timeout", "src")):
        out = run("grep_cmd.py", *args, d=d)
        assert out.startswith("[PASS]") and "→--timeout 5" in out, out


def t_search_files_mode_and_context():
    """search_text：-l 只列檔名與筆數；-C 前後行（命中行標 >）"""
    d = _tmp()
    _grep_tree(d)
    out = run("grep_cmd.py", "error", "src", "-l", d=d)
    assert "## 有命中的檔案（3 項）" in out and "- src/pkg/many.log（30 筆）" in out, out
    out = run("grep_cmd.py", "fail", "src/a.py", "-C", "1", d=d)
    assert ">    3→fail two" in out and "     2→ok" in out, out


def t_search_include_path():
    """search_text --include 含 / 時比對整個路徑，不分大小寫，跟 find_file 的名稱關鍵字同一條規則（_path_common.path_glob）。
    待辦 4l ②：以前原樣交給 grep 的 --include，只比對檔名，「<目錄>/*.py」一份都對不到、回 0 筆。不含 / 的照舊只比對檔名；兩種可以一起用"""
    d = _tmp()
    _grep_tree(d)
    out = run("grep_cmd.py", "error", ".", "--include", "pkg/*.log", d=d)
    assert first_line(out).startswith("[PASS] 搜尋「error」：共 30 筆命中，分布在 1 個檔案") and "## src/pkg/many.log" in out, out
    assert "只搜路徑符合 pkg/*.log 的檔案" in out, out
    out = run("grep_cmd.py", "error", ".", "--include", "SRC/*.py", "-l", d=d)
    assert "共 1 筆命中" in first_line(out) and "- src/a.py（1 筆）" in out, out
    out = run("grep_cmd.py", "error", ".", "--include", "*.txt", "--include", "pkg/*.log", d=d)
    assert "共 31 筆命中，分布在 2 個檔案" in first_line(out) and "只搜檔名符合 *.txt、路徑符合 pkg/*.log 的檔案" in out, out
    out = run("grep_cmd.py", "error", ".", "--include", "*.log", d=d)
    assert "共 30 筆命中" in first_line(out), "不含 / 的照舊只比對檔名"
    found = run("find_file_cmd.py", "pkg/*.log", ".", "--type", "f", d=d)
    assert found.startswith("[PASS] 找到 1 個路徑含「pkg/*.log」"), found


def t_search_rank():
    """search_text --rank：命中超過上限時先列同一行含最多個不同的字的行（照檔案順序會截掉檔尾的答案）；檔案照最多的那一行排；
    只有一個字時照檔案順序並說明；沒挑到的命中在前後行的範圍裡當前後行列（不標 >）"""
    d = _tmp()
    rows = [f"row {i}: " + ("alpha beta both" if i in (70, 72) else "alpha only" if i % 2 else "beta only") for i in range(1, 81)]
    _w(d, "doc/spec.md", "\n".join(rows) + "\n")
    _w(d, "doc/other.md", "beta and ALPHA\nnothing\n")
    out = run("grep_cmd.py", "alpha|beta", "doc/spec.md", "-C", "1", d=d)
    assert "只列前 50 筆" in first_line(out) and "row 70:" not in out, "沒有 --rank：照檔案順序，檔尾的被截掉"
    out = run("grep_cmd.py", "alpha|beta", "doc/spec.md", "-C", "1", "--rank", d=d)
    head = first_line(out)
    assert "--rank" in head and "只列 50 筆" in head, head
    assert ">   70→row 70: alpha beta both" in out and ">   72→row 72: alpha beta both" in out, out
    assert "    71→row 71: alpha only" in out, "71 沒挑到、在前後行的範圍裡：當前後行列"
    out = run("grep_cmd.py", "alpha|beta", "doc", "--rank", d=d)
    assert out.index("## doc/other.md") < out.index("## doc/spec.md"), "檔案照它最多的那一行排（other.md 的第 1 行有兩個字）"
    out = run("grep_cmd.py", "-w", "alpha|beta", "doc", "--rank", "-l", d=d)
    assert "-l 只列檔名，--rank 沒有作用" in out, out
    out = run("grep_cmd.py", "alpha", "doc", "--rank", d=d)
    assert "--rank 要有好幾個字" in out and "--rank）" not in first_line(out), out


def t_search_errors():
    """search_text：找不到路徑、/、不支援的選項、只給路徑都是 [ERROR] 加下一步；找不到內容是 [PASS] 並建議同義詞"""
    d = _tmp()
    _grep_tree(d)
    assert_error(run("grep_cmd.py", "error", "nope_dir", d=d), "找不到路徑", "下一步")
    assert_error(run("grep_cmd.py", "error", "/", d=d), "不搜 /", "下一步")
    assert_error(run("grep_cmd.py", "error", "-v", "src", d=d), "不支援的選項 -v", "-e")
    assert_error(run("grep_cmd.py", ".", d=d), "缺少要搜的關鍵字", "list_dir")
    out = run("grep_cmd.py", "zzz_nothing", "src", d=d)
    assert out.startswith("[PASS] 找不到符合「zzz_nothing」的內容（0 筆") and "|" in out, out


def t_search_tilde():
    """search_text：路徑可以用 ~"""
    d = _tmp()
    _w(d, "home/notes.txt", "remember me\n")
    out = run("grep_cmd.py", "remember", "~", d=d, HOME=os.path.join(d, "home"))
    assert "共 1 筆命中" in first_line(out), out


# ================================================================ find_file（find_file_cmd.py）
def _find_tree(d):
    _w(d, "launch/nav.launch.py", "x")
    _w(d, "src/launch/x.launch.py", "x")
    _w(d, "build/nav.launch.py", "x")
    _w(d, "README.md", "x")


def t_find_keyword_that_is_dirname():
    """find_file：關鍵字剛好也是目錄名稱（launch .）照樣找（以前回「缺少檔名關鍵字」）；依目錄分組、附最新修改"""
    d = _tmp()
    _find_tree(d)
    out = run("find_file_cmd.py", "launch", ".", d=d)
    assert first_line(out).startswith("[PASS] 找到 4 個名稱含「launch」的項目（2 個檔案、2 個目錄"), out
    assert "\n最新修改：" in out and "## src/launch（1 項）" in out and "- x.launch.py" in out, out
    assert "build/" not in out.split("\n（")[0] and "--all-dirs" in out, out
    out = run("find_file_cmd.py", ".", "launch", d=d)        # 順序反了：註明後照找
    assert out.startswith("[PASS] 找到 4 個") and "參數順序" in out, out


def t_find_path_errors_no_fallback():
    """find_file：路徑不存在回 [ERROR] 與相近的路徑，不會改搜 .（以前默默回 0 個）；~ 會展開"""
    d = _tmp()
    _find_tree(d)
    out = run("find_file_cmd.py", "nav", "lanch", d=d)
    assert_error(out, "找不到搜尋的目錄", "相近的路徑：launch")
    out = run("find_file_cmd.py", "nav", "~/proj", d=d, HOME=d)
    assert_error(out, "找不到搜尋的目錄", "展開為")
    _w(d, "proj/nav_params.yaml", "x")
    out = run("find_file_cmd.py", "nav", "~/proj", d=d, HOME=d)
    assert out.startswith("[PASS] 找到 1 個"), out


def t_find_slash_and_glob():
    """find_file：關鍵字含 / 時比對整個路徑（以前 -iname 永遠是 0）；含 * 時照萬用字元；--type f"""
    d = _tmp()
    _find_tree(d)
    out = run("find_file_cmd.py", "launch/nav", ".", d=d)
    assert out.startswith("[PASS] 找到 1 個路徑含「launch/nav」"), out
    out = run("find_file_cmd.py", "*.md", ".", d=d)
    assert out.startswith("[PASS] 找到 1 個名稱符合「*.md」"), out
    out = run("find_file_cmd.py", "launch", ".", "--type", "f", d=d)
    assert "（2 個檔案、0 個目錄" in first_line(out), out


def t_find_permission_and_cap():
    """find_file：沒有權限的目錄略過並計數（以前 exit 1 → 結果全丟）；超過 200 個只列前 200 個"""
    d = _tmp()
    for i in range(230):
        _w(d, f"data/d{i % 3}/rec_{i:03d}.csv", "x")
    with _Locked(os.path.join(d, "data", "locked")):
        out = run("find_file_cmd.py", "rec_", "data", d=d)
    assert out.startswith("[PASS] 找到 230 個") and "只列前 200 個" in first_line(out), first_line(out)
    assert "1 個目錄沒有權限（略過）" in out and "## data/d0（" in out, out[-400:]


def t_find_errors():
    """find_file：只給路徑、參數太多、不支援的選項、從 / 開始都是 [ERROR] 加下一步；找不到是 [PASS]（0 個）"""
    d = _tmp()
    _find_tree(d)
    assert_error(run("find_file_cmd.py", ".", d=d), "缺少名稱關鍵字", "list_dir")
    assert_error(run("find_file_cmd.py", "a", "b", "c", d=d), "參數太多", "下一步")
    assert_error(run("find_file_cmd.py", "nav", ".", "-v", d=d), "不支援的選項", "用法")
    assert_error(run("find_file_cmd.py", "nav", "/", d=d), "不從 / 開始找", "下一步")
    assert_error(run("find_file_cmd.py", "nav", "README.md", d=d), "不是目錄", "view_file")
    out = run("find_file_cmd.py", "zzz_none", ".", d=d)
    assert out.startswith("[PASS] 找不到名稱含「zzz_none」") and "search_text" in out, out


# ================================================================ code_ast_reader
SIG_SRC = '''"""測試模組。"""
X: int = 5
NAME = "%s"
_P = 1


def f(a, b=2, /, c=3, *args, d, e=5, **kw):
    """f 的說明"""
    return 1


def g(*, k: int = 1) -> int:
    pass


class Foo(Base, metaclass=Meta):
    """Foo doc"""

    @property
    def bar(self) -> str:
        return ""

    def _hidden(self):
        pass
''' % ("a" * 300)


def t_ast_signature_and_ranges():
    """code_ast_reader：完整簽名（/、預設值、* 之後的參數）、有型別標註的常數、每個 def／class 的行號範圍（從 def 那一行算，裝飾器另寫一行）、
    長的值截斷"""
    d = _tmp()
    _w(d, "sig.py", SIG_SRC)
    out = run("code_ast_reader_cmd.py", "sig.py", d=d)
    assert first_line(out).startswith("[PASS] sig.py 的結構：共 24 行；1 個類別、3 個函式／方法；2 個 _ 開頭"), first_line(out)
    assert "_P = 1" not in out and "_hidden" not in out, out
    assert "def f(a, b=2, /, c=3, *args, d, e=5, **kw)  行 7-9" in out, out
    assert "def g(*, k: int = 1) -> int  行 12-13" in out and "class Foo(Base, metaclass=Meta):  行 16-24" in out, out
    assert "  @property  行 19\n  def bar(self) -> str  行 20-21\n" in out and "- X: int = 5（行 2）" in out, ("def 的行號不算裝飾器", out)
    assert "NAME = 'aaaa" in out and "…（行 3）" in out and "a" * 200 not in out, out
    out = run("code_ast_reader_cmd.py", "sig.py", "--private", "--no-docstrings", d=d)
    assert "def _hidden(self)  行 23-24" in out and "- _P = 1（行 4）" in out and '"""' not in out, out


REFS_SRC = '''"""helper 在 docstring 裡提到不算"""
from pkg.util import helper
import pkg.helper as hp


def helper(msg, helper=None):  # helper 註解不算
    return msg


class Box:
    helper = 3

    @wrap(helper)
    def run(self):
        self.helper = 1
        cb = self.helper
        return helper("a") + self.other.helper(
            "b")


def outer():
    def helper():
        pass
    return helper()
'''


def t_ast_refs():
    """code_ast_reader --refs：每一處分成定義、呼叫、import、指定、其他用到，附行號與所在的函式；註解與字串不算；import 不算呼叫；
    同一行兩個呼叫算兩處；沒有＝[PASS] 沒有；名稱不合法、沒給名稱＝[ERROR]"""
    d = _tmp()
    _w(d, "m.py", REFS_SRC)
    out = run("code_ast_reader_cmd.py", "m.py", "--refs", "helper", d=d)
    assert first_line(out) == "[PASS] m.py 裡「helper」出現 12 處（AST）：定義 2、呼叫 3、import 2、指定 3、其他用到 2", first_line(out)
    assert "## 呼叫（3）\n- 行 17（在 Box.run）：" in out and out.count("- 行 17（在 Box.run）") == 2, out
    assert "- 行 24（在 outer）：return helper()" in out and "- 行 22-23（在 outer）：def helper():" in out, out
    assert "- 行 6-7（模組層）：def helper(msg, helper=None)" in out and "- 行 6（在 helper）：def helper(" in out, "參數屬於那個函式"
    assert "- 行 13（在 Box）：@wrap(helper)" in out and "- 行 11（在 Box）：helper = 3" in out, "decorator 屬於外面那一層"
    assert "## import（2）\n- 行 2（模組層）：from pkg.util import helper\n- 行 3（模組層）：import pkg.helper as hp" in out, out
    assert "- 行 1（" not in out, "docstring 不算"
    assert run("code_ast_reader_cmd.py", "m.py", "--refs=run", d=d).startswith("[PASS] m.py 裡「run」出現 1 處（AST）：定義 1、呼叫 0")
    out = run("code_ast_reader_cmd.py", "m.py", "--refs", "nothing_here", d=d)
    assert out.startswith("[PASS] m.py 裡沒有「nothing_here」") and "search_text" in out, out
    assert_error(run("code_ast_reader_cmd.py", "m.py", "--refs", "a.b", d=d), "Python 的名稱", "只寫最後一段")
    assert_error(run("code_ast_reader_cmd.py", "m.py", "--refs", d=d), "--refs 後面需要一個名稱")


def t_ast_errors():
    """code_ast_reader：找不到（相近的路徑）、目錄（指向 find_file）、不是 Python、語法錯誤（指向 view_file --from）、沒給檔案"""
    d = _tmp()
    _w(d, "sig.py", SIG_SRC)
    _w(d, "bad.py", "def broken(:\n  pass\n")
    _w(d, "notes.txt", "hello")
    _w(d, "tool", "#!/usr/bin/env python3\ndef run():\n    pass\n")
    assert_error(run("code_ast_reader_cmd.py", "Sig.py", d=d), "找不到檔案", "相近的路徑：sig.py")
    assert_error(run("code_ast_reader_cmd.py", ".", d=d), "是目錄", "find_file")
    assert_error(run("code_ast_reader_cmd.py", "notes.txt", d=d), "不是 Python 檔", "view_file")
    assert_error(run("code_ast_reader_cmd.py", "bad.py", d=d), "語法錯誤", "第 1 行", "view_file bad.py --from 1")
    assert_error(run("code_ast_reader_cmd.py", d=d), "沒有給要解析的檔案", "用法")
    assert_error(run("code_ast_reader_cmd.py", "sig.py", "--x", d=d), "不支援的選項")
    assert run("code_ast_reader_cmd.py", "tool", d=d).startswith("[PASS] tool 的結構"), "python 的 #! 腳本也可以"


# ================================================================ change_dir（cd_cmd.py）
# ================================================================ code_defs（程式列舉）、py_refs（範圍裡名稱的每一處）
CPP_SRC = """// class Fake { 註解裡的不算 void fake() {
#include "engine.hpp"
namespace demo {
class Engine : public Base<int> {
 public:
  Engine() : rate_(10), name_{"x"} { start(); }
  void run() override { if (ok()) { go(); } }
  int value() const;
 private:
  int rate_;
};
enum class Mode { A, B };
struct Point { double x; double y; };
int Engine::value() const
{
  return rate_;
}
template <typename T>
void Holder<T>::put(const T& v) {
  items_.push_back(v);
}
static int helper(int a,
                  int b) {
  auto f = [](int x) { return x; };
  return f(a) + b;
}
void declared_only(int);
}  // namespace demo
"""
TEST_SRC = "def test_one():\n    pass\n\n\nclass TestBox:\n    def test_two(self):\n        pass\n\n    def helper(self):\n        pass\n"


def t_code_defs():
    """code_defs：每份檔案的行數與數量由腳本算；Python 照 AST（含方法、巢狀）、C++ 照定義的寫法（建構子的初始化、類別外的方法、樣板、
    多行參數；註解、enum class、只有宣告、lambda 不算）；--include／--name／--kind 篩選（--name 寫成萬用字元的樣子回 [ERROR]、附對應的正規表示式，
    跳脫的 \\w* 不算）；--files 每份一行、--sort lines 照行數；預設略過 build"""
    d = _tmp()
    _w(d, "src/engine.cpp", CPP_SRC)
    _w(d, "src/tests/test_box.py", TEST_SRC)
    _w(d, "src/notes.md", "# 標題\n\n一行\n")
    _w(d, "src/build/skip.py", "def hidden():\n    pass\n")
    _w(d, "src/blob.bin", b"\x00\x01\x02")
    out = run("code_defs_cmd.py", "src", d=d)
    assert first_line(out) == "[PASS] 範圍 src：3 份檔案、共 41 行；定義：類別 3、函式／方法 8", first_line(out)
    assert "## src/engine.cpp（28 行；類別 2、函式 5）" in out and "- class Engine（行 4-11）" in out and "- class Point（行 13）" in out, out
    for want in ("- def Engine::Engine（行 6）", "- def Engine::run（行 7）", "- def Engine::value（行 14-17）", "- def Holder::put（行 19-21）",
                 "- def helper（行 22-26）"):
        assert want in out, (want, out)
    assert "Fake" not in out and "Mode" not in out and "declared_only" not in out and "hidden" not in out, out
    assert "- def TestBox.test_two（行 6-7）" in out and "## src/notes.md（3 行）" in out and "1 份二進位檔" in out, out
    out = run("code_defs_cmd.py", ".", "--include", "test_*.py", "--name", "^test", "--kind", "def", d=d)
    assert first_line(out).startswith("[PASS] 範圍 .：1 份檔案、共 10 行；定義：類別 0、函式／方法 2（檔名 test_*.py、名稱符合「^test」、只算函式與方法）")
    assert "- def test_one（行 1-2）" in out and "helper" not in out, out
    out = run("code_defs_cmd.py", "src", "--files", "--sort", "lines", d=d)
    rows = [ln for ln in out.split("\n") if ln.startswith("- ")]
    assert rows == ["- src/engine.cpp：28 行；類別 2、函式 5", "- src/tests/test_box.py：10 行；類別 1、函式 3", "- src/notes.md：3 行"], rows
    out = run("code_defs_cmd.py", "src", "--include", "*.rs", d=d)
    assert out.startswith("[PASS] 範圍 src 裡沒有符合的檔案（0 份；檔名 *.rs）"), out
    out = run("code_defs_cmd.py", ".", "--include", "tests/*.py", d=d)
    assert first_line(out).startswith("[PASS] 範圍 .：1 份檔案、共 10 行") and "路徑符合 tests/*.py" in first_line(out), \
        ("--include 含 / 時比對整個路徑（同 search_text、find_file）", first_line(out))
    assert_error(run("code_defs_cmd.py", "nope", d=d), "找不到")
    assert_error(run("code_defs_cmd.py", "src", "--kind", "method", d=d), "--kind 要是 class")
    assert_error(run("code_defs_cmd.py", "src", "--name", "(", d=d), "正規表示式")
    out = run("code_defs_cmd.py", "src", "--name", "test*", "--kind", "def", d=d)
    assert_error(out, "萬用字元的寫法")
    assert '寫成 --name "^test"' in out, ("--name 寫成萬用字元的樣子：擋下、附對應的正規表示式", out)
    for glob, rx in (("*box", '"box$"'), ("*Box*", '"Box"'), ("test_*_two", '"^test_.*_two$"')):
        assert rx in run("code_defs_cmd.py", "src", "--name", glob, d=d), (glob, rx)
    assert "改成正規表示式的寫法" in run("code_defs_cmd.py", "src", "--name", "(test)|one*", d=d), "換不出來的：只說明寫法"
    out = run("code_defs_cmd.py", "src", "--name", r"^test_\w*", "--kind", "def", d=d)
    assert first_line(out).startswith("[PASS]") and "test_two" in out, ("跳脫的 \\w* 是正規表示式，不擋", out)
    assert_error(run("code_defs_cmd.py", "/", d=d), "不列 /")


GRABBER_H = """#pragma once
namespace cam {
class FrameGrabber {
 public:
  void grabFrame();
  int count() const { return n_; }
 private:
  int n_ = 0;
};
void resetAll();
}  // namespace cam
"""
GRABBER_CPP = """#include "frame_grabber.h"
namespace cam {
// FrameGrabber::grabFrame 在註解裡不算
void FrameGrabber::grabFrame()
{
  ++n_;
}
void resetAll() {}
}  // namespace cam
void cam::Shutter::open() {
}
"""


def t_code_defs_has():
    """code_defs --has：名稱或所屬的類別（qualname 的最後兩段）有這個字的定義——類別的名稱列出它的成員（標頭檔的類別與寫在類別裡的、
    .cpp 寫成 類別::方法 的；; 結尾的宣告不列），命名空間的字不算、不分大小寫、a|b 是任一個、Python 的 類別.方法 也一樣；
    只列有符合的定義的檔案（其他幾份寫在最後）；--has 是空的回 [ERROR]"""
    d = _tmp()
    _w(d, "src/cam/frame_grabber.h", GRABBER_H)
    _w(d, "src/cam/frame_grabber.cpp", GRABBER_CPP)
    _w(d, "src/cam/notes.md", "# FrameGrabber\n")
    _w(d, "src/other/util.cpp", "int add(int a, int b) { return a + b; }\n")
    out = run("code_defs_cmd.py", "src", "--include", "*.h", "--include", "*.cpp", "--has", "framegrabber", d=d)
    head = first_line(out)
    assert head.startswith("[PASS] 範圍 src：3 份檔案") and "定義：類別 1、函式／方法 2" in head and "名稱或所屬的類別有「framegrabber」" in head, head
    assert "## src/cam/frame_grabber.cpp（" in out and "  - def FrameGrabber::grabFrame（行 4-7）" in out, out
    assert "## src/cam/frame_grabber.h（" in out and "  - class FrameGrabber（行 3-9）" in out and "  - def FrameGrabber::count（行 6）" in out, out
    assert "resetAll" not in out and "Shutter" not in out and "util.cpp" not in out and "（其他 1 份檔案沒有符合的定義，不列）" in out, out
    out = run("code_defs_cmd.py", "src", "--has", "Shutter|COUNT", d=d)
    assert "定義：類別 0、函式／方法 2" in first_line(out) and "  - def cam::Shutter::open（行 10-11）" in out and "FrameGrabber::count" in out, out
    out = run("code_defs_cmd.py", "src", "--has", "cam", d=d)
    assert "定義：類別 0、函式／方法 0" in first_line(out) and "## " not in out and "其他 4 份檔案沒有符合的定義" in out, ("命名空間的字不算", out)
    _w(d, "src/py/box.py", TEST_SRC)
    out = run("code_defs_cmd.py", "src", "--include", "*.py", "--has", "testbox", d=d)
    assert "  - class TestBox（行 5-10）" in out and "  - def TestBox.test_two（行 6-7）" in out and "  - def TestBox.helper（行 9-10）" in out, out
    assert "test_one" not in out, out
    assert_error(run("code_defs_cmd.py", "src", "--has", "|", d=d), "--has 後面要寫名稱")


def t_py_refs():
    """py_refs：整個範圍一次分出每一處（AST：定義、呼叫、import…；註解與字串不算、同一行兩個呼叫算兩處），各檔案的數量由腳本算；
    --exclude-dir、--kind；Python 沒有、C++ 檔有時寫出那幾份；名稱不合法、沒給名稱＝[ERROR]"""
    d = _tmp()
    _w(d, "pkg/m.py", REFS_SRC)
    _w(d, "pkg/use.py", "from pkg.m import helper\n\n\ndef go():\n    return helper(1)  # helper\n")
    _w(d, "pkg/tests/t.py", "from pkg.m import helper\nhelper(2)\n")
    _w(d, "pkg/engine.cpp", CPP_SRC)
    out = run("py_refs_cmd.py", "helper", "pkg", d=d)
    assert first_line(out) == "[PASS] 「helper」在 pkg 的 Python 程式裡出現 16 處、3 份檔案（AST）：定義 2、呼叫 5、import 4、指定 3、其他用到 2", first_line(out)
    assert "## pkg/m.py（12 處：定義 2、呼叫 3、import 2、指定 3、其他用到 2）" in out and "## pkg/use.py（2 處：呼叫 1、import 1）" in out, out
    assert "- 呼叫 行 5（在 go）：return helper(1) # helper" in out and out.count("- 呼叫 行 17（在 Box.run）") == 2, out
    assert "- 定義 行 6-7（模組層）：def helper(msg, helper=None):" in out, out
    out = run("py_refs_cmd.py", "helper", "pkg", "--exclude-dir", "tests", "--kind", "call", d=d)
    assert first_line(out).startswith("[PASS] 「helper」在 pkg 的 Python 程式裡出現 4 處、2 份檔案（AST）（只算呼叫）"), first_line(out)
    out = run("py_refs_cmd.py", "helper", "pkg", "--exclude-dir", "tests", "--kind", "def|call", d=d)
    assert first_line(out).startswith("[PASS] 「helper」在 pkg 的 Python 程式裡出現 6 處、2 份檔案（AST）（只算定義、呼叫）"), first_line(out)
    assert_error(run("py_refs_cmd.py", "helper", "pkg", "--kind", "def|calls", d=d), "--kind 要是", "def|call")
    out = run("py_refs_cmd.py", "helper", "pkg", "--include", "tests/*.py", d=d)
    assert first_line(out).startswith("[PASS] 「helper」在 pkg 的 Python 程式裡出現 2 處、1 份檔案"), \
        ("--include 含 / 時比對整個路徑（同 search_text、find_file）", first_line(out))
    out = run("py_refs_cmd.py", "rate_", "pkg", d=d)
    assert out.startswith("[PASS] 範圍 pkg 的 Python 程式裡沒有「rate_」") and "C／C++ 檔有這個名稱（照字面）：pkg/engine.cpp" in out, out
    out = run("py_refs_cmd.py", "nothing_here", "pkg", d=d)
    assert "沒有「nothing_here」" in out and "search_text" in out, out
    assert_error(run("py_refs_cmd.py", "a.helper", "pkg", d=d), "只寫最後一段")
    assert_error(run("py_refs_cmd.py", "not a name", "pkg", d=d), "Python 的名稱")
    assert_error(run("py_refs_cmd.py", d=d), "沒有給要找的名稱")
    assert_error(run("py_refs_cmd.py", "helper", "nope", d=d), "找不到")


def t_cd_pass_marker_last():
    """change_dir：[PASS] 與最後一行的 [CWD_CHANGED]；~ 展開"""
    d = _tmp()
    os.makedirs(os.path.join(d, "proj"))
    out = run("cd_cmd.py", "proj", d=d)
    assert out.startswith("[PASS] 已切換工作目錄") and out.splitlines()[-1] == f"[CWD_CHANGED] {os.path.join(d, 'proj')}", out
    out = run("cd_cmd.py", "~/proj", d=d, HOME=d)
    assert out.splitlines()[-1] == f"[CWD_CHANGED] {os.path.join(d, 'proj')}", out


def t_cd_permission_regression():
    """change_dir：進不去的目錄（以前 cd /root 回 [PASS]，之後每個腳本都失敗）回 [ERROR]、工作目錄不變"""
    d = _tmp()
    with _Locked(os.path.join(d, "locked")):
        out = run("cd_cmd.py", "locked", d=d)
    assert_error(out, "沒有權限進入目錄", "工作目錄沒有改變")
    assert "[CWD_CHANGED]" not in out


def t_cd_errors():
    """change_dir：不存在（相近的路徑）、是檔案、好幾個參數、選項都是 [ERROR]"""
    d = _tmp()
    os.makedirs(os.path.join(d, "agent_core"))
    _w(d, "f.txt", "x")
    assert_error(run("cd_cmd.py", "Agent_core", d=d), "找不到目錄", "相近的路徑：agent_core")
    assert_error(run("cd_cmd.py", "f.txt", d=d), "是檔案", "所在的目錄")
    assert_error(run("cd_cmd.py", "a", "b", d=d), "一次只能切換到一個目錄")
    assert_error(run("cd_cmd.py", "-P", "agent_core", d=d), "沒有選項")


# ================================================================ view_file（cat_cmd.py）
def t_view_numbered_and_ranges():
    """view_file：每行附行號（  1→）、--from／--lines、--tail；第一行是 [PASS] 檔案內容"""
    d = _tmp()
    _w(d, "big.txt", "".join(f"line {i}\n" for i in range(1, 51)))
    out = run("cat_cmd.py", "big.txt", d=d)
    assert first_line(out) == "[PASS] 檔案內容 (big.txt)：共 50 行，顯示第 1-50 行", out[:200]
    assert "     1→line 1" in out and "    50→line 50" in out
    out = run("cat_cmd.py", "big.txt", "--from", "10", "--lines", "3", d=d)
    assert "顯示第 10-12 行" in first_line(out) and "--from 13" in first_line(out) and "    12→line 12" in out, out
    assert "還有 38 行沒有顯示" in out.splitlines()[-1], out
    out = run("cat_cmd.py", "big.txt", "--tail", "2", d=d)
    assert "顯示第 49-50 行" in first_line(out) and "    50→line 50" in out, out
    out = run("cat_cmd.py", "-n", "big.txt", d=d)
    assert out.startswith("[PASS] 檔案內容 (big.txt)"), "cat -n 的 -n 不會被當成路徑"


def t_view_around():
    """view_file --around N [-C M]：第 N 行前後各 M 行（預設 10），那一行標 >；超過總行數、跟 --from 一起用、-C 沒有 --around 都是 [ERROR]"""
    d = _tmp()
    _w(d, "big.txt", "".join(f"line {i}\n" for i in range(1, 51)))
    out = run("cat_cmd.py", "big.txt", "--around", "20", "-C", "2", d=d)
    assert first_line(out).startswith("[PASS] 檔案內容 (big.txt)：共 50 行，顯示第 18-22 行（第 20 行的前後"), first_line(out)
    assert ">   20→line 20" in out and "    19→line 19" in out and "    23→" not in out, out
    out = run("cat_cmd.py", "big.txt", "--around", "3", d=d)
    assert "顯示第 1-13 行" in first_line(out) and ">    3→line 3" in out, first_line(out)
    out = run("cat_cmd.py", "big.txt", "--around", "50", "-C", "0", d=d)
    assert "顯示第 50-50 行" in first_line(out) and ">   50→line 50" in out, out
    assert_error(run("cat_cmd.py", "big.txt", "--around", "51", d=d), "只有 50 行", "--around 51")
    assert_error(run("cat_cmd.py", "big.txt", "--around", "5", "--from", "2", d=d), "--around 不能跟")
    assert_error(run("cat_cmd.py", "big.txt", "-C", "3", d=d), "要跟 --around N 一起用")


def t_view_truncation_and_big_file():
    """view_file：超過 2000 行截斷並說 --from 2001；超過 1MB 的檔案也能看（以前直接拒絕）"""
    d = _tmp()
    _w(d, "log.txt", "".join(f"{i:07d} " + "x" * 600 + "\n" for i in range(1, 2501)))
    assert os.path.getsize(os.path.join(d, "log.txt")) > 1024 * 1024
    out = run("cat_cmd.py", "log.txt", d=d)
    head = first_line(out)
    assert head.startswith("[PASS] 檔案內容 (log.txt)：共 2500 行") and "上限 60000 字" in head and "--from" in head, head
    out = run("cat_cmd.py", "log.txt", "--from", "2490", d=d)
    assert "顯示第 2490-2500 行" in first_line(out), first_line(out)


def t_view_binary_and_errors():
    """view_file：二進位檔指向 image_inspect；沒給檔案、好幾個檔案、目錄、--from 超過、不認識的選項、找不到都是 [ERROR]"""
    d = _tmp()
    _w(d, "shot.png", b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR")
    _w(d, "a.txt", "a\nb\n")
    assert_error(run("cat_cmd.py", "shot.png", d=d), "二進位檔", "image_inspect")
    out = run("cat_cmd.py", d=d)
    assert_error(out, "沒有給要看的檔案", "用法")
    assert_error(run("cat_cmd.py", "a.txt", "shot.png", d=d), "一次只能看一個檔案")
    assert_error(run("cat_cmd.py", ".", d=d), "是目錄", "list_dir")
    assert_error(run("cat_cmd.py", "a.txt", "--from", "9", d=d), "只有 2 行", "--tail")
    assert_error(run("cat_cmd.py", "a.txt", "-x", d=d), "不認識的選項")
    assert_error(run("cat_cmd.py", "A.txt", d=d), "找不到檔案", "相近的路徑：a.txt")
    assert run("cat_cmd.py", "a.txt", d=d).startswith("[PASS]")
    _w(d, "empty.txt", "")
    assert "空檔案" in run("cat_cmd.py", "empty.txt", d=d)


# ================================================================ host_runcmd
def t_host_raw_command_regressions():
    """host_runcmd：指令原樣執行（以前接 && pwd：# 註解吃掉輸出、printf 被當路徑、結尾 & 語法錯誤），沒有 [HOST_CWD]"""
    d = _tmp()
    out = run("host_runcmd_cmd.py", "echo hi # note", d=d)
    assert out.startswith("[PASS] 指令執行完成（exit code 0") and "\nhi" in out and "HOST_CWD" not in out, out
    out = run("host_runcmd_cmd.py", "printf abc", d=d)
    assert out.splitlines()[-1] == "abc", out
    out = run("host_runcmd_cmd.py", "sleep 7.123 &", d=d)
    assert out.startswith("[PASS]") and "背景程序" in out, out
    left = subprocess.run(["pgrep", "-f", "^sleep 7.123"], capture_output=True, text=True).stdout.strip()
    assert not left, f"背景程序沒有結束：{left}"
    out = run("host_runcmd_cmd.py", "cd / && pwd", d=d)
    assert "\n/" in out and "change_dir" in out.splitlines()[-1], out


def t_host_exit1_and_failure_output():
    """host_runcmd：grep 的 exit 1 是「沒有找到」不是錯誤；失敗時 stdout 與 stderr 都在（以前只回其中一個）"""
    d = _tmp()
    _w(d, "f.txt", "hello\n")
    out = run("host_runcmd_cmd.py", "grep nomatch f.txt", d=d)
    assert out.startswith("[PASS]") and "沒有找到符合的內容" in first_line(out), out
    out = run("host_runcmd_cmd.py", "echo to_stdout; echo to_stderr >&2; exit 3", d=d)
    assert_error(out, "exit code 3", "下一步")
    assert "to_stdout" in out and "to_stderr" in out, out
    assert_error(run("host_runcmd_cmd.py", "nonexistent_cmd_zz9", d=d), "找不到指令", "which")
    assert_error(run("host_runcmd_cmd.py", "echo 'unclosed", d=d), "語法錯誤")


def t_host_no_stdin():
    """host_runcmd：不讀標準輸入——harness 的 stdin 一直開著也不會卡住（read x 立刻拿到 EOF）；要互動的指令說明不支援"""
    d = _tmp()
    p = subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "host_runcmd_cmd.py"), "read x; echo got=[$x]"], cwd=d,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=dict(os.environ, **_env(d)))
    t0 = time.monotonic()
    try:
        out, _ = p.communicate(timeout=20)        # 故意不關 stdin：繼承的話 read 會一直等
    except subprocess.TimeoutExpired:
        p.kill()
        raise AssertionError("host_runcmd 讀了繼承的標準輸入，卡住了")
    finally:
        if p.stdin:
            p.stdin.close()
    assert time.monotonic() - t0 < 10 and "got=[]" in out, out
    out = run("host_runcmd_cmd.py", "python3 -c \"import sys; sys.stdout.write('Continue? [Y/n] '); sys.stdout.flush(); input()\"", d=d)
    assert_error(out, "要互動輸入", "-y")


def t_host_timeout_partial_no_orphan():
    """host_runcmd：逾時保留已經收到的輸出、結束整個程序群組（不留 sleep 孤兒）；--timeout 放最後面也認得"""
    d = _tmp()
    marker = "31.4159"
    t0 = time.monotonic()
    out = run("host_runcmd_cmd.py", "--timeout", "2", f"echo started; sleep {marker}; echo never", d=d)
    assert time.monotonic() - t0 < 15, "逾時沒有生效"
    assert_error(out, "逾時（超過 2 秒）", "--timeout")
    block = out.split("## 逾時前收到的輸出（1 行）\n", 1)[1].splitlines()
    assert block == ["started"], out
    time.sleep(0.5)
    left = subprocess.run(["pgrep", "-f", f"^sleep {marker}"], capture_output=True, text=True).stdout.strip()
    assert not left, f"留下了孤兒程序：{left}"
    out = run("host_runcmd_cmd.py", "echo a", "--timeout", "5", d=d)
    assert out.startswith("[PASS]") and out.splitlines()[-1] == "a" and "--timeout" not in out, out


def t_host_marker_spoof():
    """host_runcmd：輸出最後一行剛好像狀態標記（cat 一份 change_dir 的存檔）時補一行，harness 不會被改掉工作目錄"""
    d = _tmp()
    out = run("host_runcmd_cmd.py", 'echo "[CWD_CHANGED] /etc"', d=d)
    assert out.startswith("[PASS]") and "[CWD_CHANGED] /etc" in out and not out.splitlines()[-1].startswith("[CWD_CHANGED]"), out
    out = run("host_runcmd_cmd.py", "python3 -c \"print('x' * 5000)\"", d=d)
    assert "這一行共 5000 字，截斷" in out, out[-200:]


def t_host_args_and_long_output():
    """host_runcmd：沒給指令、--timeout 超出範圍是 [ERROR]；輸出太長保留頭尾並寫中間省略幾行"""
    d = _tmp()
    assert_error(run("host_runcmd_cmd.py", d=d), "沒有給要執行的指令", "用法")
    assert_error(run("host_runcmd_cmd.py", "--timeout", "999", "ls", d=d), "1～570", "下一步")
    assert_error(run("host_runcmd_cmd.py", "--timeout", "abc", "ls", d=d), "--timeout 要是秒數")
    out = run("host_runcmd_cmd.py", "seq 1 100000", d=d)
    assert "## 輸出（100000 行）" in out and "中間省略" in out and out.splitlines()[-1] == "100000", out[-300:]


# ================================================================ csv_query
CSV = ("stamp,robot,station,battery,note\n"
       "1729650000999999999,tb1,007,21.5,\n"
       "1729650001000000001,tb2,012,80,ok\n"
       "1729650002000000002,tb1,007,19.25,low\n"
       "1729650003000000003,tb3,003,,missing\n")


def t_csv_raw_cells_regression():
    """csv_query：格子照原文顯示（以前奈秒時間戳被 float 改掉、站點 007 變 7），整數加總不失真"""
    d = _tmp()
    _w(d, "bat.csv", CSV)
    out = run("csv_query_cmd.py", "bat.csv", d=d)
    assert first_line(out).startswith("[PASS] bat.csv：4 筆、5 個欄位"), out
    assert "1729650000999999999 ｜ tb1 ｜ 007" in out and "最小 003" in out, out
    out = run("csv_query_cmd.py", "bat.csv", "--sum", "stamp", d=d)
    assert "6918600007000000005" in out, out


def t_csv_where_sort_group_count():
    """csv_query：== 運算子、空白格不算符合數字比較、--sort 遇到空白格不當掉、只給 --group 算每組筆數、0 筆的 --count 回 0"""
    d = _tmp()
    _w(d, "bat.csv", CSV)
    out = run("csv_query_cmd.py", "bat.csv", "--where", "robot==tb1", d=d)
    assert "符合 robot=tb1 的有 2 筆" in first_line(out), out
    out = run("csv_query_cmd.py", "bat.csv", "--where", "battery<25", d=d)
    assert "的有 2 筆" in first_line(out) and "tb3" not in out.split("\n", 1)[1], out
    out = run("csv_query_cmd.py", "bat.csv", "--sort", "note", d=d)
    assert out.startswith("[PASS]") and "空白排最後" in out and out.splitlines()[-1].startswith("1729650000999999999"), out
    out = run("csv_query_cmd.py", "bat.csv", "--group", "robot", d=d)
    assert "每一組（robot）的筆數，共 3 組" in out and "tb1 ｜ 2" in out, out
    out = run("csv_query_cmd.py", "bat.csv", "--where", "robot=tb9", "--count", d=d)
    assert "的有 0 筆" in first_line(out) and "筆數：0" in out and "tb1、tb2、tb3" in out, out


def t_csv_head_cap_and_errors():
    """csv_query：--head 上限 60 並說還有幾筆；欄位不存在、--where 格式、不認識的參數、找不到檔案、空檔案、非數值欄位都是 [ERROR]"""
    d = _tmp()
    _w(d, "big.csv", "n,v\n" + "".join(f"{i},{i * 2}\n" for i in range(100)))
    out = run("csv_query_cmd.py", "big.csv", "--sort", "v", "--desc", "--head", "80", d=d)
    assert "列出 60／100 筆" in out and "--head 上限 60" in out and "還有 40 筆" in out.splitlines()[-1], out[-300:]
    _w(d, "bat.csv", CSV)
    _w(d, "empty.csv", "")
    assert_error(run("csv_query_cmd.py", "bat.csv", "--max", "nope", d=d), "沒有欄位「nope」", "欄位有：", "下一步")
    assert_error(run("csv_query_cmd.py", "bat.csv", "--where", "robot", d=d), "--where 的格式", "下一步")
    assert_error(run("csv_query_cmd.py", "bat.csv", "--bogus", d=d), "不認識的參數", "用法")
    assert_error(run("csv_query_cmd.py", "bat.csv", "--head", "x", d=d), "--head")
    assert_error(run("csv_query_cmd.py", "bt.csv", d=d), "找不到檔案", "bat.csv")
    assert_error(run("csv_query_cmd.py", "empty.csv", d=d), "是空的", "下一步")
    assert_error(run("csv_query_cmd.py", "bat.csv", "--avg", "robot", d=d), "沒有數值", "下一步")


# ================================================================ file_ops
def t_fileops_option_order_no_corruption():
    """file_ops：--new 在 --old 前面也對（以前把 `0.3" --old "max_vel_x: 0.5` 寫進檔案）；內容在路徑前面也對（以前建出名為 --text 的檔案）"""
    d = _tmp()
    _w(d, "cfg.yaml", "controller:\n  max_vel_x: 0.5\n  min_vel_x: 0.0\n")
    out = run_raw("file_ops_cmd.py", 'replace cfg.yaml --new "max_vel_x: 0.3" --old "max_vel_x: 0.5"', d)
    assert out.startswith("[PASS] 已修改 cfg.yaml 第 2 行附近"), out
    assert _read(os.path.join(d, "cfg.yaml")) == "controller:\n  max_vel_x: 0.3\n  min_vel_x: 0.0\n"
    bk = out.rsplit("備份在 ", 1)[1].strip()
    assert bk.startswith(os.path.join(d, "_logs", "file_backups")) and "0.5" in _read(bk), bk
    out = run_raw("file_ops_cmd.py", 'write --text "hello" notes.md', d)
    assert out.startswith("[PASS] 已建立 notes.md（1 行）"), out
    assert _read(os.path.join(d, "notes.md")) == "hello\n" and not os.path.exists(os.path.join(d, "--text"))


def t_fileops_escapes_and_quotes():
    """file_ops：\\n 換行、\\\\n 字面的 \\n、內容裡沒有跳脫的引號也保留；有真正換行時 \\n 照原樣"""
    d = _tmp()
    out = run_raw("file_ops_cmd.py", 'write a.md --text "第一行\\n他說 "hi" 了\\n路徑 C:\\\\new"', d)
    assert out.startswith("[PASS] 已建立 a.md（3 行）"), out
    assert _read(os.path.join(d, "a.md")) == '第一行\n他說 "hi" 了\n路徑 C:\\new\n', repr(_read(os.path.join(d, "a.md")))
    out = run_raw("file_ops_cmd.py", 'write code.py --text "print(\\"a\\\\nb\\")\nx = 1"', d)
    assert _read(os.path.join(d, "code.py")) == 'print("a\\\\nb")\nx = 1\n', repr(_read(os.path.join(d, "code.py")))
    out = run_raw("file_ops_cmd.py", 'append a.md --text "第四行"', d)
    assert out.startswith("[PASS] 已附加 a.md") and "備份在" in out and _read(os.path.join(d, "a.md")).endswith("C:\\new\n第四行\n"), out


def t_fileops_move_without_backup():
    """file_ops：move 不先備份整個來源（以前 bag 資料夾要多佔一倍空間）；目的已存在不覆蓋"""
    d = _tmp()
    _w(d, "bags/run1/data.mcap", "x" * 1000)
    os.makedirs(os.path.join(d, "archive"))
    out = run_raw("file_ops_cmd.py", "move bags/run1 archive", d)
    assert out.startswith("[PASS] 已移動 bags/run1 → archive/run1"), out
    assert os.path.exists(os.path.join(d, "archive/run1/data.mcap")) and not os.path.exists(os.path.join(d, "_logs", "file_backups"))
    _w(d, "bags/run1/data.mcap", "y")
    assert_error(run_raw("file_ops_cmd.py", "move bags/run1 archive", d), "目的已經存在", "下一步")
    out = run_raw("file_ops_cmd.py", "copy -r archive archive2", d)
    assert out.startswith("[PASS] 已複製 archive → archive2（1 個檔案）"), out


def t_fileops_replace_counts():
    """file_ops：原文出現好幾次時列出行號；0 次列出相關的行；--old 含 view_file 的行號時說明"""
    d = _tmp()
    _w(d, "cfg.yaml", "controller:\n  max_vel_x: 0.26\n  min_vel_x: 0.0\n")
    assert_error(run_raw("file_ops_cmd.py", 'replace cfg.yaml --old "_vel_x" --new "_v"', d), "出現 2 次（第 2、3 行）", "前後文")
    out = run_raw("file_ops_cmd.py", 'replace cfg.yaml --old "max_vel_x: 0.3" --new "max_vel_x: 0.5"', d)
    assert_error(out, "出現 0 次", "view_file", "2: ")
    assert "max_vel_x: 0.26" in out
    assert_error(run_raw("file_ops_cmd.py", 'replace cfg.yaml --old "     2→  max_vel_x: 0.26" --new "max_vel_x: 0.3"', d),
                 "行號", "下一步")


def t_fileops_set():
    """file_ops set：只改 --after 那一段的那一行（縮排、清單的 -、行尾註解保留，別台不動）；不給 --after 而出現好幾次、那一段找不到、
    錨點不存在都不改並說下一步；已經是那個值就不改；對照表的寫法（tb4:）也認得"""
    d = _tmp()
    yaml_list = ("robots:\n  - id: tb4\n    model: deliveryBot\n    battery_low: 15  # 低電量\n"
                 "  - id: tb5\n    model: deliveryBot\n    battery_low: 15\n")
    _w(d, "robots.yaml", yaml_list)
    out = run_raw("file_ops_cmd.py", 'set robots.yaml battery_low 18 --after "id: tb4"', d)
    assert out.startswith("[PASS] 已修改 robots.yaml 第 4 行（在「id: tb4」那一段）：「battery_low: 15  # 低電量」→「battery_low: 18  # 低電量」"), out
    assert _read(os.path.join(d, "robots.yaml")) == yaml_list.replace("battery_low: 15  #", "battery_low: 18  #"), "別台不動、縮排與註解保留"
    assert "備份在" in out
    assert run_raw("file_ops_cmd.py", 'set robots.yaml battery_low 18 --after "id: tb4"', d).startswith("[PASS] 沒有修改 robots.yaml：第 4 行已經是")
    assert_error(run_raw("file_ops_cmd.py", "set robots.yaml model x", d), "有 2 行「model: …」", "--after")
    assert_error(run_raw("file_ops_cmd.py", 'set robots.yaml battery 20 --after "id: tb5"', d), "那一段", "找不到「battery: …」", "battery_low")
    assert_error(run_raw("file_ops_cmd.py", 'set robots.yaml battery_low 20 --after "id: tb9"', d), "沒有含「id: tb9」的行", "view_file")
    assert_error(run_raw("file_ops_cmd.py", "set robots.yaml battery_low", d), "需要三個參數")
    _w(d, "map.yaml", "tb4:\n  max_speed: 1.0\ntb5:\n  max_speed: 1.0\n")
    out = run_raw("file_ops_cmd.py", 'set map.yaml max_speed 0.6 --after "tb5:"', d)
    assert out.startswith("[PASS] 已修改 map.yaml 第 4 行") and _read(os.path.join(d, "map.yaml")) == "tb4:\n  max_speed: 1.0\ntb5:\n  max_speed: 0.6\n", out


def t_fileops_errors():
    """file_ops：mkdir 在檔案上、非 UTF-8、二進位檔、路徑位置的不認識選項、系統目錄、刪除、缺內容都是 [ERROR] 加下一步"""
    d = _tmp()
    _w(d, "f.txt", "x\n")
    _w(d, "latin1.txt", "caf\xe9\n".encode("latin-1"))
    _w(d, "bin.dat", b"\0\1\2")
    assert_error(run_raw("file_ops_cmd.py", "mkdir f.txt", d), "已經是一個檔案", "下一步")
    assert run_raw("file_ops_cmd.py", "mkdir -p new/sub", d).startswith("[PASS] 已建立目錄：new/sub")
    assert_error(run_raw("file_ops_cmd.py", 'replace latin1.txt --old "caf" --new "x"', d), "不是 UTF-8", "下一步")
    assert_error(run_raw("file_ops_cmd.py", 'append bin.dat --text "x"', d), "二進位檔")
    assert_error(run_raw("file_ops_cmd.py", "write --force f.txt --text \"y\"", d), "不認識的選項 --force")
    assert_error(run_raw("file_ops_cmd.py", 'write /etc/agent_x.txt --text "x"', d), "不能在系統目錄操作", "下一步")
    assert_error(run_raw("file_ops_cmd.py", "delete f.txt", d), "第一個參數要是動作", "不提供刪除")
    assert_error(run_raw("file_ops_cmd.py", "write g.txt", d), "需要 --text")
    assert_error(run_raw("file_ops_cmd.py", 'replace f.txt --old "x"', d), "需要 --old", "--new")
    assert_error(run_raw("file_ops_cmd.py", 'replace nope.txt --old "a" --new "b"', d), "找不到檔案")


def t_fileops_permission():
    """file_ops：沒有寫入權限的目錄回 [ERROR] 與下一步"""
    if IS_ROOT:
        raise Skip("以 root 執行，權限擋不住 root")
    d = _tmp()
    ro = os.path.join(d, "ro")
    os.makedirs(ro)
    os.chmod(ro, stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert_error(run_raw("file_ops_cmd.py", 'write ro/x.txt --text "x"', d), "沒有權限", "下一步")
    finally:
        os.chmod(ro, 0o755)


# ================================================================ modify_memory
def t_memory_write_dup_and_cap():
    """modify_memory：寫入（不碰正式的 Memory.md）、重複不寫、超過 300 字回 [ERROR]（以前 5000 字的條目會擠掉所有舊記憶）"""
    d = _tmp()
    out = run_raw("modify_memory_cmd.py", '"技能用法 | 數檔案 | list_dir 用 --filter 計數"', d)
    assert out.startswith("[PASS] 成功寫入長期記憶") and "目前共 1 條" in out, out
    assert "list_dir 用 --filter 計數" in _read(os.path.join(d, "Memory.md"))
    assert "未重複寫入" in run_raw("modify_memory_cmd.py", '"技能用法 | 數檔案 | list_dir 用 --filter 計數"', d)
    assert_error(run_raw("modify_memory_cmd.py", '"' + "長" * 400 + '"', d), "超過上限 300 字", "精簡")


def t_memory_unquoted_option_word():
    """modify_memory：沒加引號、內容中間有 --filter 也照寫（以前整條被拒絕）；整個參數是選項時說要加引號"""
    d = _tmp()
    out = run_raw("modify_memory_cmd.py", "技能用法 | list_dir 要用 --filter | 照做", d)
    assert out.startswith("[PASS]") and "list_dir 要用 --filter" in _read(os.path.join(d, "Memory.md")), out
    assert_error(run_raw("modify_memory_cmd.py", "--skill list_dir", d), "沒有任何選項", "引號")
    assert_error(run("modify_memory_cmd.py", d=d), "不可為空")


# ================================================================ stt_engine
FAKE_WHISPER = '''import os, time
class _Seg:
    def __init__(self, a, b, t): self.start, self.end, self.text = a, b, t
class _Info:
    language = "zh"; duration = 4.2
class WhisperModel:
    def __init__(self, *a, **k): pass
    def transcribe(self, path, **k):
        if open(path, "rb").read(4) != b"RIFF":
            raise ValueError("Invalid data found when processing input")
        def gen():
            for i in range(3):
                if os.environ.get("FAKE_STT_SLOW"):
                    time.sleep(2)
                yield _Seg(i * 1.4, i * 1.4 + 1.4, f" 第{i + 1}段")
        return gen(), _Info()
'''


def _fake_whisper(d):
    _w(d, "fakepkg/faster_whisper/__init__.py", FAKE_WHISPER)
    return os.path.join(d, "fakepkg")


def t_stt_missing_dependency():
    """stt_engine：沒有 faster-whisper 時一開始就回 [ERROR]，寫明要請使用者執行的安裝指令"""
    import importlib.util
    if importlib.util.find_spec("faster_whisper") is not None:
        raise Skip("這台機器已經裝了 faster-whisper")
    d = _tmp()
    _w(d, "a.wav", b"RIFF0000WAVE")
    assert_error(run("stt_engine_cmd.py", "--file", "a.wav", d=d), "faster-whisper", "pip install faster-whisper", "不要自己安裝")


def t_stt_file_mode_writes_to_logs():
    """stt_engine：--file 辨識音檔（不需要麥克風），全文寫在 logs/stt/ 而不是工作目錄（以前寫 stt_output.txt 到 cwd）"""
    d = _tmp()
    _w(d, "a.wav", b"RIFF0000WAVE")
    out = run("stt_engine_cmd.py", "--file", "a.wav", "--lang", "zh", d=d, PYTHONPATH=_fake_whisper(d))
    assert first_line(out).startswith("[PASS] 語音辨識完成：a.wav（長度 4.2 秒，語言 zh），共 3 段"), out
    assert "[1.4-2.8] 第2段" in out and not os.path.exists(os.path.join(d, "stt_output.txt")), out
    saved = first_line(out).rsplit("全文存在 ", 1)[1]
    assert saved.startswith(os.path.join(d, "_logs", "stt")) and "第3段" in _read(saved), saved


def t_stt_timeout_partial_and_errors():
    """stt_engine：辨識逾時保留已經辨識出的段落（不是全部）；找不到音檔、無法解碼、不認識的參數是 [ERROR]"""
    d = _tmp()
    _w(d, "a.wav", b"RIFF0000WAVE")
    _w(d, "b.mp3", b"junk")
    fake = _fake_whisper(d)
    out = run("stt_engine_cmd.py", "--file", "a.wav", "--timeout", "3", d=d, PYTHONPATH=fake, FAKE_STT_SLOW="1")
    assert out.startswith("[PASS] 語音辨識逾時（3 秒）沒有做完") and "不是全部" in first_line(out) and "第1段" in out, out
    assert_error(run("stt_engine_cmd.py", "--file", "c.wav", d=d, PYTHONPATH=fake), "找不到音檔", "a.wav")
    assert_error(run("stt_engine_cmd.py", "--file", "b.mp3", d=d, PYTHONPATH=fake), "無法解碼", "下一步")
    assert_error(run("stt_engine_cmd.py", "--bogus", d=d), "不認識的參數", "用法")
    assert_error(run("stt_engine_cmd.py", "--record", "999", d=d), "--record")


# ================================================================ image_inspect
class _FakeOllama:
    """本機的假 Ollama：/api/chat 回固定文字，記下收到的影像尺寸。"""

    def __init__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        seen = self.seen = []

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                from PIL import Image
                for m in body.get("messages", []):
                    for im in m.get("images") or []:
                        seen.append(Image.open(io.BytesIO(base64.b64decode(im))).size)
                data = json.dumps({"model": body.get("model"), "created_at": "2026-10-23T00:00:00Z",
                                   "message": {"role": "assistant", "content": "畫面是一個紅色的方塊"}, "done": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _need_pil():
    try:
        import PIL  # noqa: F401
        import ollama  # noqa: F401
    except ImportError as e:
        raise Skip(f"缺少 {e.name}")


def t_image_pass_downscaled():
    """image_inspect：[PASS]（假的 Ollama）；送給模型的影像長邊縮到 1600"""
    _need_pil()
    from PIL import Image
    d = _tmp()
    Image.new("RGB", (3000, 1000), (200, 10, 10)).save(os.path.join(d, "big.png"))
    fake = _FakeOllama()
    try:
        out = run("image_inspect_cmd.py", "big.png", "這是什麼", d=d, OLLAMA_HOST=fake.url)
    finally:
        fake.close()
    assert first_line(out).startswith("[PASS] 影像分析結果（big.png，3000x1000，送給模型前縮小成 1600x533"), out
    assert "紅色的方塊" in out and fake.seen == [(1600, 533)], (out, fake.seen)


def t_image_container_path():
    """image_inspect：目標容器裡的路徑依 bind mount 換成主機路徑（以前回「不存在」）；不在 mount 底下時說怎麼複製出來"""
    _need_pil()
    from PIL import Image
    d = _tmp()
    os.makedirs(os.path.join(d, "mnt"))
    Image.new("RGB", (100, 50)).save(os.path.join(d, "mnt", "shot.png"))
    _w(d, "bin/docker", f"#!/bin/sh\necho '[{{\"Type\":\"bind\",\"Source\":\"{d}/mnt\",\"Destination\":\"/workspace\"}}]'\n", mode=0o755)
    path = os.path.join(d, "bin") + os.pathsep + os.environ.get("PATH", "")
    fake = _FakeOllama()
    try:
        out = run("image_inspect_cmd.py", "/workspace/shot.png", d=d, OLLAMA_HOST=fake.url, TARGET_CONTAINER="fakebox", PATH=path)
    finally:
        fake.close()
    assert out.startswith("[PASS]") and f"對應到主機的 {d}/mnt/shot.png" in out, out
    out = run("image_inspect_cmd.py", "/root/cam.png", d=d, TARGET_CONTAINER="fakebox", PATH=path)
    assert_error(out, "不在任何 bind mount 底下", "docker cp fakebox:/root/cam.png")


def t_image_errors():
    """image_inspect：像素太多（DecompressionBombError）、不是影像、找不到（相近的路徑）、沒給路徑都是 [ERROR] 加下一步"""
    _need_pil()
    from PIL import Image
    d = _tmp()
    Image.new("1", (15000, 15000)).save(os.path.join(d, "bomb.png"))
    _w(d, "notimg.png", "hello")
    Image.new("RGB", (10, 10)).save(os.path.join(d, "small.png"))
    assert_error(run("image_inspect_cmd.py", "bomb.png", d=d), "像素太多", "縮小")
    assert_error(run("image_inspect_cmd.py", "notimg.png", d=d), "不是可辨識的影像格式", "下一步")
    assert_error(run("image_inspect_cmd.py", "smal.png", d=d), "找不到影像檔", "相近的路徑：small.png")
    assert_error(run("image_inspect_cmd.py", d=d), "沒有給影像檔路徑", "用法")
    assert_error(run("image_inspect_cmd.py", "small.png", d=d, OLLAMA_HOST="http://127.0.0.1:9"), "Ollama", "不要重試")


# ================================================================ 共用層
def t_run_shell_unit():
    """_shell_common.run_shell：stdin 是 /dev/null、逐行交給呼叫端、stdout／stderr 分開收、找不到執行檔不丟例外"""
    sys.path.insert(0, SCRIPTS)
    from _shell_common import run_shell
    lines = []
    r = run_shell("echo a; echo b; echo err >&2; cat", 10, on_stdout_line=lines.append)
    assert r.rc == 0 and lines == [b"a", b"b"] and "err" in r.err and not r.timed_out, (r.rc, lines, r.err)
    r = run_shell(["definitely_not_a_cmd_zz"], 5)
    assert r.spawn_error is not None and r.rc is None
