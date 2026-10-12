"""code_test --coverage 的覆蓋率量測（Python：coverage.py；C／C++：--coverage 編譯＋gcovr）。

在專案的暫存副本裡量（不在工作區留下 .coverage、.gcda／.gcno，也不會留下用 coverage 旗標編的 .o——那種 .o 之後一般建置
連結時會出現 __gcov 的 undefined reference）。C／C++ 用編譯器包裝（g++／gcc／c++／cc 都自動加上 --coverage）照專案原本的
方式建置與執行測試，所以 CMake、Makefile、直接編譯三種都適用。量完把結果的路徑換回相對於專案的路徑。

回傳的資料：{"files": {相對路徑: {"lines": 已涵蓋/總數, "line_pct", "branch_pct", "missing": [沒測到的行]}}, "line_pct", "branch_pct", …}
"""
import glob
import json
import os
import shutil
import stat
import subprocess
import tempfile

_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "env", "node_modules", "build", "build_test", "build_cov",
              "cmake-build-debug", "cmake-build-release", "obj", "htmlcov", ".mypy_cache", ".tox", "install", "log"}
TEST_RE = r"(^|/)(tests?|unit_tests|testing)/|(^|/)test_[^/]*$|_test\.[^/]+$|(^|/)conftest\.py$"
PY_OMIT = "*/tests/*,*/test/*,*/unit_tests/*,*/testing/*,*test_*.py,*_test.py,*/conftest.py,*/.venv/*,*/venv/*,*/site-packages/*"


def make_copy(root):
    """專案的暫存副本（略過建置產物、虛擬環境、git）。回傳 (暫存目錄, 副本的根目錄)。"""
    tmp = tempfile.mkdtemp(prefix="code_cov_")
    dst = os.path.join(tmp, os.path.basename(os.path.abspath(root)) or "project")

    def ignore(d, names):
        return {n for n in names if n in _SKIP_DIRS or n.endswith((".o", ".gcda", ".gcno", ".gcov", ".pyc"))
                or n.startswith(".coverage")}
    shutil.copytree(root, dst, ignore=ignore, symlinks=True)
    return tmp, dst


def compiler_wrappers(tmp):
    """bin 目錄：g++／gcc／c++／cc 的包裝，每次呼叫都加上 --coverage（找真的編譯器時跳過這個目錄）。"""
    bindir = os.path.join(tmp, "covbin")
    os.makedirs(bindir, exist_ok=True)
    path = os.environ.get("PATH", "")
    real = {}
    for name in ("g++", "gcc", "c++", "cc"):
        found = shutil.which(name, path=os.pathsep.join(p for p in path.split(os.pathsep) if os.path.abspath(p) != bindir))
        if found:
            real[name] = found
    if "c++" not in real and "g++" in real:
        real["c++"] = real["g++"]
    if "cc" not in real and "gcc" in real:
        real["cc"] = real["gcc"]
    for name, target in real.items():
        p = os.path.join(bindir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/sh\nexec "{target}" "$@" --coverage\n')
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def gcov_executable():
    return shutil.which("gcov") or next((p for p in sorted(glob.glob("/usr/bin/gcov-[0-9]*"), reverse=True)
                                          if os.path.basename(p).replace("gcov-", "").isdigit()), None)


def gcovr_executable():
    import sys
    here = os.path.dirname(sys.executable)
    for cand in (os.path.join(here, "gcovr"), shutil.which("gcovr"), os.path.expanduser("~/aiagent_venv_env/.venv/bin/gcovr")):
        if cand and os.path.exists(cand):
            return cand
    return None


def ranges(lines):
    """[1,2,3,7,9,10] → "1-3、7、9-10"。"""
    out, start, prev = [], None, None
    for n in sorted(set(lines)):
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}" if prev > start else f"{start}")
            start = prev = n
    if start is not None:
        out.append(f"{start}-{prev}" if prev > start else f"{start}")
    return "、".join(out)


def python_report(py, copy_root, data_file, env, timeout=120):
    jpath = data_file + ".json"
    r = subprocess.run([py, "-m", "coverage", "json", f"--data-file={data_file}", "-o", jpath, "--omit", PY_OMIT],
                       cwd=copy_root, env=env, capture_output=True, text=True, timeout=timeout)
    try:
        with open(jpath, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"error": (r.stdout + r.stderr).strip()[-400:] or "沒有覆蓋率資料（測試可能一個都沒跑）"}
    files = {}
    for path, v in (data.get("files") or {}).items():
        rel = os.path.relpath(os.path.join(copy_root, path), copy_root) if not os.path.isabs(path) else os.path.relpath(path, copy_root)
        s = v.get("summary", {})
        nb = s.get("num_branches", 0)
        files[rel] = {"lines": f"{s.get('covered_lines', 0)}/{s.get('num_statements', 0)}",
                      "line_pct": round(s.get("percent_covered", 0.0) if not nb else 100.0 * s.get("covered_lines", 0) / max(1, s.get("num_statements", 0)), 1),
                      "branch_pct": round(100.0 * s.get("covered_branches", 0) / nb, 1) if nb else None,
                      "missing": v.get("missing_lines", []),
                      "partial": sorted({b[0] for b in v.get("missing_branches", []) if b and b[0] > 0})}
    t = data.get("totals", {})
    nb = t.get("num_branches", 0)
    return {"files": files, "line_pct": round(100.0 * t.get("covered_lines", 0) / max(1, t.get("num_statements", 0)), 1),
            "branch_pct": round(100.0 * t.get("covered_branches", 0) / nb, 1) if nb else None,
            "lines": f"{t.get('covered_lines', 0)}/{t.get('num_statements', 0)}",
            "branches": f"{t.get('covered_branches', 0)}/{nb}" if nb else None}


def cpp_report(copy_root, env, timeout=180):
    import re
    gcovr, gcov = gcovr_executable(), gcov_executable()
    if not gcovr or not gcov:
        return {"error": "沒有 gcovr 或 gcov，量不到 C／C++ 的覆蓋率（gcovr：pip install gcovr；gcov 隨 gcc 安裝）"}
    if not glob.glob(os.path.join(copy_root, "**", "*.gcda"), recursive=True):
        return {"error": "沒有 .gcda（測試沒有執行，或是用了包裝以外的編譯器）"}
    jpath = os.path.join(os.path.dirname(copy_root), "gcovr.json")
    r = subprocess.run([gcovr, "-r", copy_root, "--gcov-executable", gcov, "--exclude-throw-branches", "--exclude-unreachable-branches",
                        "--exclude", r".*(^|/)(tests?|unit_tests|testing)/.*", "--exclude", r".*(/|^)test_[^/]*", "--exclude", r".*_test\.[^/]*",
                        "--gcov-ignore-errors=no_working_dir_found", "--json", jpath],
                       cwd=copy_root, env=env, capture_output=True, text=True, timeout=timeout)
    try:
        with open(jpath, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"error": (r.stdout + r.stderr).strip()[-400:] or "gcovr 沒有產生結果"}
    files, tl, tc, tb, tbc = {}, 0, 0, 0, 0
    for fe in data.get("files", []):
        rel = fe.get("file", "")
        if os.path.isabs(rel):
            rel = os.path.relpath(rel, copy_root)
        if rel.startswith("..") or re.search(TEST_RE, rel) or "CMakeFiles/" in rel or re.match(r"(build[^/]*|cmake-build[^/]*)/", rel):
            continue                                 # 測試檔、CMake 偵測編譯器用的檔案、建置目錄產生的程式
        lines = [ln for ln in fe.get("lines", []) if not ln.get("gcovr/noncode")]
        covered = [ln for ln in lines if ln.get("count", 0) > 0]
        nbr = sum(len(ln.get("branches", [])) for ln in lines)
        cbr = sum(1 for ln in lines for b in ln.get("branches", []) if b.get("count", 0) > 0)
        missing = [ln["line_number"] for ln in lines if ln.get("count", 0) == 0]
        partial = [ln["line_number"] for ln in lines if ln.get("count", 0) > 0 and any(b.get("count", 0) == 0 for b in ln.get("branches", []))]
        if not lines:
            continue
        files[rel] = {"lines": f"{len(covered)}/{len(lines)}", "line_pct": round(100.0 * len(covered) / len(lines), 1),
                      "branch_pct": round(100.0 * cbr / nbr, 1) if nbr else None, "missing": missing, "partial": sorted(set(partial))}
        tl, tc, tb, tbc = tl + len(lines), tc + len(covered), tb + nbr, tbc + cbr
    if not files:
        return {"error": "gcovr 沒有找到正式程式的覆蓋率資料"}
    return {"files": files, "line_pct": round(100.0 * tc / max(1, tl), 1), "branch_pct": round(100.0 * tbc / tb, 1) if tb else None,
            "lines": f"{tc}/{tl}", "branches": f"{tbc}/{tb}" if tb else None}


def format_report(title, rep, max_files=25):
    if rep.get("error"):
        return f"── 覆蓋率（{title}）：沒有量到 ──\n{rep['error']}"
    head = f"── 覆蓋率（{title}）：行 {rep['line_pct']}%（{rep['lines']}）" + \
        (f"、分支 {rep['branch_pct']}%（{rep['branches']}）" if rep.get("branch_pct") is not None else "") + " ──"
    rows = ["檔案｜行｜分支｜還沒測到的行（＊＝只測到部分分支的行）"]
    for rel, v in sorted(rep["files"].items(), key=lambda kv: kv[1]["line_pct"])[:max_files]:
        miss = ranges(v["missing"])
        part = ranges(v.get("partial") or [])
        detail = (miss or "（全部涵蓋）") + (f"；＊{part}" if part else "")
        rows.append(f"{rel}｜{v['line_pct']}%（{v['lines']}）｜{'—' if v['branch_pct'] is None else str(v['branch_pct']) + '%'}｜{detail}")
    if len(rep["files"]) > max_files:
        rows.append(f"…（另外 {len(rep['files']) - max_files} 個檔案，覆蓋率都比上面的高）")
    return head + "\n" + "\n".join(rows)
