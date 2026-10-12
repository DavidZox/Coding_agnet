"""code_test：跑專案的測試——Python 用 pytest，C／C++ 用 GoogleTest（gtest）。通過／失敗數由腳本算好放在標頭；
失敗時附每個失敗測試的細節（pytest 的 assert 實際值與 traceback、gtest 的期望值與實際值），編譯失敗時附整理過的編譯錯誤
（檔案:行號: 訊息＋那一行原始碼），不會被長長的建置輸出淹沒。coding job 每一項的驗證與最後的整體驗證都用它。

不給路徑＝整個專案：有 Python 測試（test_*.py／*_test.py）就跑 pytest，有 C／C++ 測試就建置後跑 gtest，兩種都有就兩種都跑。
C／C++ 怎麼跑（依序找第一個符合的，跟一般人手動跑的方式一樣）：
1. 根目錄的 CMakeLists.txt 註冊了測試（add_test／gtest_discover_tests）：cmake 設定 build/（第一次才設定，有 ninja 用 Ninja）
   → cmake --build → ctest --output-on-failure。
2. Makefile（或 makefile_test 這類專門的測試 makefile）有 test／check 目標：make [-f 檔名] test。makefile 沒有自動追蹤標頭的
   相依（-MMD）時加 -B 全部重新編譯，避免用到改標頭之前編出來的 .o。
3. 沒有建置檔但有 C／C++ 測試原始檔（test_*.cpp、*_test.cpp、tests／ 底下）：每個原始檔各自用 gcc／g++ 編譯，連結 gtest
   （測試檔自己沒有 main 時加 gtest_main），執行。不用 gtest 的測試檔各自連成一個程式，結束碼 0 算通過。
Python 用 _code_common.project_python()（CODE_PYTHON → 工作區的 .venv／venv → harness 的直譯器）；那個 Python 沒有 pytest 時
回報要怎麼安裝——不會改用別的方式假裝跑過。指令的執行環境見 _code_common.toolchain_env（venv 裡的 pytest／cmake、~/.local 的 gtest）。
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _code_common as cc
import _cpp_common as cp
import _coverage as cov
import code_run_cmd

DEFAULT_TIMEOUT, MAX_TIMEOUT = 300, 570
ENV_ONLY_HEAD = "[ERROR] 沒辦法在這台主機跑這些測試"     # coding job 認這個開頭：不是程式的錯，改用靜態檢查（見 coding_worker.verify）
MAX_SECTION_CHARS = 7000
USAGE = ("用法: scripts/code_test_cmd.py [測試檔、目錄、檔案::測試名稱 ...] [-k 關鍵字] [--lang python|cpp] [--coverage] [--timeout 秒] [pytest 的選項]\n"
         "  不給路徑＝整個專案（Python 跑 pytest，C／C++ 建置後跑 gtest）；tests/test_x.py::test_y、tests/test_shape.cpp::ShapeTest.Area "
         f"只跑一個測試；-k 只跑名稱含關鍵字的測試；--coverage 另外量覆蓋率（行／分支，列出每個檔案還沒測到的行）；"
         f"--timeout 預設 {DEFAULT_TIMEOUT} 秒、上限 {MAX_TIMEOUT}。")
_VALUE_OPTS = {"-m", "-p", "-c", "-o", "-W", "-r", "--maxfail", "--tb", "--deselect", "--ignore", "--rootdir", "--durations",
               "--log-level", "--import-mode"}
_PY_TEST_RE = re.compile(r"^(test_.*|.*_test)\.py$")
# ROS 2 的 Python 模組（這台主機沒有 ROS 2 時 import 不到）：rclpy、ament_flake8 這類 linter 測試、launch、各種 *_msgs
_ROS_PY_MODULE_RE = re.compile(r"^(rclpy|ament_\w+|launch(?:_ros|_testing\w*)?|rosidl_\w+|rosbag2_\w+|tf2_\w+|message_filters|"
                               r"\w+_msgs|\w+_srvs|\w+_interfaces)$")
_COLLECT_ERR_RE = re.compile(r"(?m)^_+ ERROR collecting (\S+) _+$")
_NO_MODULE_RE = re.compile(r"No module named '([\w.]+)'")
_EXTRA_LIBS = [(r"<sqlite3\.h>", "-lsqlite3"), (r"<(?:math\.h|cmath)>", "-lm"), (r"<(?:pthread\.h|thread|future|mutex)>", "-pthread"),
               (r"<zlib\.h>", "-lz"), (r"<curl/curl\.h>", "-lcurl"), (r"<(?:filesystem|experimental/filesystem)>", "")]


def parse_args(argv):
    opts = {"targets": [], "keyword": None, "timeout": DEFAULT_TIMEOUT, "lang": None, "pytest_args": [], "coverage": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-k", "--timeout", "--lang", "--runner"):
            if i + 1 >= len(argv):
                return None, f"[ERROR] {a} 後面需要值。\n{USAGE}"
            v = argv[i + 1]
            if a == "-k":
                opts["keyword"] = v
            elif a == "--timeout":
                if not v.isdigit():
                    return None, f"[ERROR] --timeout 後面需要秒數。\n{USAGE}"
                opts["timeout"] = max(5, min(MAX_TIMEOUT, int(v)))
            elif a == "--lang":
                v = {"py": "python", "c": "cpp", "c++": "cpp", "cxx": "cpp", "gtest": "cpp", "pytest": "python"}.get(v.lower(), v.lower())
                if v not in ("python", "cpp"):
                    return None, f"[ERROR] --lang 只能是 python 或 cpp。\n{USAGE}"
                opts["lang"] = v
            i += 2                                  # --runner：舊版的選項（已經沒有內建 runner），忽略
            continue
        if a.startswith("--timeout="):
            v = a.split("=", 1)[1]
            if v.isdigit():
                opts["timeout"] = max(5, min(MAX_TIMEOUT, int(v)))
        elif a.startswith("-k") and len(a) > 2 and not a.startswith("--"):
            opts["keyword"] = a[2:]
        elif a in ("-q", "--quiet"):
            pass
        elif a in ("--coverage", "--cov"):
            opts["coverage"] = True
        elif a.startswith("-"):                    # 其他 pytest 選項照傳（-x、--maxfail=1、-m "not slow"…）
            opts["pytest_args"].append(a)
            if a in _VALUE_OPTS and i + 1 < len(argv):
                opts["pytest_args"].append(argv[i + 1])
                i += 1
        else:
            opts["targets"].append(a)
        i += 1
    return opts, None


def _home(path):
    h = os.path.expanduser("~")
    return "~" + path[len(h):] if path.startswith(h + os.sep) else path


def _run(cmd, root, deadline, env):
    """回傳 (exit code 或 None（逾時）, 輸出, 秒數)；逾時以整體的 deadline 計算。"""
    return code_run_cmd.run_shell(cmd, root, max(5, int(deadline - time.time())), env)


def _result(name, status, counts=None, summary="", text="", secs=0.0):
    return {"name": name, "status": status, "counts": counts or {}, "summary": summary, "text": text, "secs": secs}


def has_python_tests(path):
    if os.path.isfile(path):
        return path.endswith(".py")
    return any(_PY_TEST_RE.match(os.path.basename(rel)) for _, rel in cc.iter_files(path, exts={".py"}))


# ---------------------------------------------------------------- Python：pytest
def run_pytest(root, targets, opts, env, deadline):
    py = opts.get("py") or cc.project_python(root)
    name = f"pytest（{_home(py)}）"
    code, out, _ = _run([py, "-c", "import pytest"], root, min(deadline, time.time() + 60), env)
    if code != 0:
        # 環境問題，不是程式的錯：改程式也不會好（SWE-bench 評測：django、sympy 的環境本來就沒有 pytest，它們有自己的測試程式）。
        # 標成 env：只有這種結果時第一行是 ENV_ONLY_HEAD，coding job 改用靜態檢查，不會派 worker 去「修」
        return _result(name, "env", summary="這個 Python 沒有安裝 pytest", text=(
            f"這個 Python 沒有安裝 pytest：{py}\n{out.strip()[-500:]}\n"
            f"專案有自己的測試程式時（例如 python3 tests/runtests.py、python3 bin/test、make check），請改用它（code_run）。"
            f"不能自己安裝套件：需要 pytest 時請在報告裡請使用者安裝（{py} -m pip install pytest；虛擬環境不需要 sudo），"
            f"或用環境變數 CODE_PYTHON 指定有 pytest 的 Python。"))
    runner = [py, "-m", "pytest"]
    if opts.get("cov_data"):                    # --coverage：用 coverage.py 跑 pytest（量覆蓋率的暫存副本裡）
        code_c, out_c, _ = _run([py, "-c", "import coverage"], root, min(deadline, time.time() + 60), env)
        if code_c == 0:
            runner = [py, "-m", "coverage", "run", "--append", "--branch", f"--data-file={opts['cov_data']}", "--source=.",
                      "--omit", cov.PY_OMIT, "-m", "pytest"]
        else:
            opts["cov_missing"] = py
    cmd = runner + ["-q", "-p", "no:cacheprovider", "--color=no", "--tb=short"] + opts["pytest_args"] + targets
    if env.get("CODE_TEST_CASES_DIR"):
        cmd.append(f"--junitxml={os.path.join(env['CODE_TEST_CASES_DIR'], f'pytest_{time.time_ns()}.xml')}")
    if opts["keyword"]:
        cmd += ["-k", opts["keyword"]]
    code, out, secs = _run(cmd, root, deadline, env)
    out = out.rstrip()
    counts = cc.summarize_test_counts(out)
    shown = cc.clip_middle(out, MAX_SECTION_CHARS, "pytest 輸出")
    if code is None:
        r = _result(name, "timeout", counts, "逾時", shown + "\n（測試卡住多半是程式在等輸入或無窮迴圈）", secs)
    elif code == 5 or (not counts and "no tests ran" in out):
        r = _result(name, "no_tests", summary="沒有收集到測試", text=shown, secs=secs)
    elif code == 0:
        r = _result(name, "pass", counts, cc.format_counts(counts) or "通過", shown, secs)
    elif code in (2, 4) and not counts.get("failed"):
        why = "測試收集失敗（import 錯誤或語法錯誤，測試一個都沒有跑）" if code == 2 else "pytest 的參數或路徑錯誤"
        r = _result(name, "fail", counts, f"{why}" + (f"：{cc.format_counts(counts)}" if counts else ""), shown, secs)
    else:
        r = _result(name, "fail", counts, cc.format_counts(counts) or f"exit {code}", shown, secs)
    r["raw"] = out
    return r


def _ros_package_of(root, path):
    """path（檔案或目錄，絕對路徑）所在的 ROS 套件目錄：往上找 package.xml，最多找到 root；不在套件裡回 None。"""
    d, root = os.path.abspath(path if os.path.isdir(path) else os.path.dirname(path)), os.path.abspath(root)
    while True:
        if os.path.isfile(os.path.join(d, "package.xml")):
            return d
        if d == root or os.path.dirname(d) == d or not d.startswith(root):
            return None
        d = os.path.dirname(d)


def run_pytest_projects(root, args, opts, env, deadline):
    """ROS 2 套件裡的 Python 測試：每個套件在自己的目錄跑 pytest（colcon test 也是這樣）——套件的模組才 import 得到，不同套件
    同名的 test_copyright.py／test_flake8.py 也不會互相衝突；import 時缺外部依賴（這台主機沒有的 rclpy、ament_flake8…）的
    測試檔排除後重跑、說明原因，不算程式的錯誤。沒有測試在 ROS 套件裡：照舊在工作區根目錄跑一次。"""
    groups, plain = {}, []
    for a in args or ["."]:
        path, sep, sel = a.partition("::")
        full = os.path.join(root, path)
        files = [full] if os.path.isfile(full) else \
            [p for p, rel in cc.iter_files(full, exts={".py"}) if _PY_TEST_RE.match(os.path.basename(rel))]
        pkgs = [(f, _ros_package_of(root, f)) for f in files]
        if not any(pkg for _, pkg in pkgs):
            plain.append(a)
            continue
        for f, pkg in pkgs:
            if pkg:
                groups.setdefault(pkg, []).append(os.path.relpath(f, pkg) + (sep + sel if sep else ""))
            else:
                plain.append(os.path.relpath(f, root))
    if not groups:
        return [run_pytest(root, args, opts, env, deadline)]
    suites = [run_pytest(root, plain, opts, env, deadline)] if plain else []
    for pkg, files in groups.items():
        base = os.path.relpath(pkg, root)
        popts = dict(opts, pytest_args=opts["pytest_args"] + ["--rootdir", pkg])
        r = run_pytest(pkg, files, popts, env, deadline)
        missing = _missing_py_modules(r.get("raw", ""), pkg) if r["status"] == "fail" else {}
        if missing:
            rest = [f for f in files if f.split("::")[0] not in missing]
            if rest:
                r = run_pytest(pkg, rest, dict(popts, pytest_args=popts["pytest_args"] + [f"--ignore={f}" for f in missing]),
                               env, deadline)
                r["summary"] += f"（跳過 {len(missing)} 個缺外部依賴的測試檔）"
                r["text"] = (r["text"] + "\n" if r["text"] and r["status"] != "pass" else "") + _py_env_text(pkg, missing)
            else:
                r = _result(r["name"], "env", summary="缺外部依賴、沒辦法在這台主機跑", text=_py_env_text(pkg, missing), secs=r["secs"])
        if base not in (".", ""):
            r["name"] += f"：{base}"
            r["text"] = _prefix_paths(r["text"], base, pkg)
        suites.append(r)
    return suites


def _missing_py_modules(out, pkg):
    """pytest 收集測試時的 ModuleNotFoundError → {測試檔: 缺的模組}，只算外部依賴：package.xml 宣告的、或 ROS 2 的模組。"""
    deps = cp.declared_deps(pkg)
    parts = _COLLECT_ERR_RE.split(out or "")
    found = {}
    for i in range(1, len(parts) - 1, 2):
        mods = _NO_MODULE_RE.findall(parts[i + 1])
        if mods:
            top = mods[-1].split(".")[0]
            if top.lower() in deps or _ROS_PY_MODULE_RE.match(top):
                found[parts[i]] = top
    return found


def _py_env_text(pkg, missing):
    m = cp._PKG_NAME_RE.search(cp._read(os.path.join(pkg, "package.xml")))
    name = m.group(1) if m else os.path.basename(pkg)
    lines = "\n".join(f"- {f}：import {mod}" for f, mod in list(missing.items())[:8])
    return (f"下面的測試檔 import 時缺外部依賴、沒有跑：\n{lines}\n這些是 package.xml 宣告的依賴或 ROS 2 的模組，這台主機沒有安裝"
            + ("（沒有載入 ROS 2）" if not cp.ros_sourced() else "") + "——不是程式的錯誤，不要為了這個改程式或測試、也不要安裝套件。"
            f"要跑它們：在有 ROS 2 的環境 colcon test --packages-select {name} && colcon test-result --verbose。")


# ---------------------------------------------------------------- C／C++：gtest
def _cpp_env(env, gtest_filter=None):
    env = dict(env, GTEST_COLOR="no", LC_MESSAGES="C")    # 編譯器的訊息用英文（錯誤的格式才認得）
    if not env.get("CC") and not shutil.which("cc", path=env.get("PATH")) and shutil.which("gcc", path=env.get("PATH")):
        env["CC"] = "gcc"                                  # make 預設的 C 編譯器是 cc，有些機器只有 gcc
    if env.get("LC_ALL"):
        env["LC_ALL"] = "C.UTF-8"
    if gtest_filter:
        env["GTEST_FILTER"] = gtest_filter
    else:
        env.pop("GTEST_FILTER", None)
    if env.get("CODE_TEST_CASES_DIR"):          # 每個測試的結果（coding job 的回歸檢查用）：gtest 寫 XML 到這個目錄
        env["GTEST_OUTPUT"] = "xml:" + env["CODE_TEST_CASES_DIR"].rstrip("/") + "/"
    return env


def _build_failed(name, what, out, root, secs):
    d = cp.diagnostics(out, roots=[root])
    detail = cp.format_diagnostics(d)
    n = d["n_errors"]
    summary = f"{what}（{n} 個錯誤）" if n else (f"{what}（連結錯誤）" if d["link"] else what)
    if not detail:                                 # 認不出 gcc 的格式（CMake 設定錯誤、make 的錯誤）：給輸出的尾巴
        detail = cc.clip_middle(out.rstrip(), 4000, "建置輸出")
    return _result(name, "build_error", summary=summary, text=detail, secs=secs)


def _glob_to_regex(pattern):
    rx = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return rx[2:] if rx.startswith(".*") else "^" + rx


def _gtest_detail(out, counts, failed_names=()):
    blocks, nfail, crashed = cp.gtest_failures(out)
    parts = []
    if blocks:
        parts.append(f"失敗的測試（{nfail} 個）：\n" + "\n".join(blocks))
    elif failed_names:
        parts.append("失敗的測試：" + "、".join(f"{n}（{why}）" for n, why in failed_names))
    if crashed:
        parts.append(f"⚠️ 測試程式在跑 {crashed} 的時候當掉了（沒有跑完、也沒有結果）：多半是存取了無效的記憶體"
                     "（空指標、越界、用了已經釋放的物件）或無窮遞迴。")
    if re.search(r"Segmentation fault|SEGFAULT|core dumped|Subprocess aborted|\(Child aborted\)", out) and not crashed:
        parts.append("⚠️ 有測試程式異常結束（Segmentation fault／abort）。")
    return "\n".join(parts)


def _cmake(root, info, patterns, env, deadline, t0):
    name = "gtest（CMake＋ctest）"
    bdir = "build"
    cache = os.path.join(root, bdir, "CMakeCache.txt")
    if os.path.isfile(cache):
        try:
            m = re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.*)$", cc.read_text(cache), re.M)
        except OSError:
            m = None
        if m and os.path.realpath(m.group(1).strip()) != os.path.realpath(root):
            bdir = "build-code_test"           # build/ 是從別的目錄複製來的：另外建一個，不動它
            cache = os.path.join(root, bdir, "CMakeCache.txt")
    if not shutil.which("cmake", path=env.get("PATH")):
        return _result(name, "error", summary="沒有 cmake", text="找不到 cmake：請使用者安裝（pip install cmake 或 sudo apt install cmake）。")
    if not os.path.isfile(cache):
        gen = ["-G", "Ninja"] if shutil.which("ninja", path=env.get("PATH")) else []
        code, out, _ = _run(["cmake", "-S", ".", "-B", bdir] + gen + ["-DCMAKE_BUILD_TYPE=Debug", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"],
                            root, deadline, env)
        if code is None:
            return _result(name, "timeout", summary="CMake 設定逾時", text=cc.clip_middle(out, 3000), secs=time.time() - t0)
        if code != 0:
            errs = re.findall(r"(CMake Error.*?)(?=\n\S|\Z)", out, re.S)
            text = "\n".join(e.strip() for e in errs[:4]) or cc.clip_middle(out, 4000)
            return _result(name, "build_error", summary="CMake 設定失敗", text=cc.clip_middle(text, 4000), secs=time.time() - t0)
    jobs = str(max(1, min(8, (os.cpu_count() or 2))))
    code, out, _ = _run(["cmake", "--build", bdir, "-j", jobs], root, deadline, env)
    if code is None:
        return _result(name, "timeout", summary="建置逾時", text=cc.clip_middle(out, 3000), secs=time.time() - t0)
    if code != 0:
        return _build_failed(name, "編譯失敗", out, root, time.time() - t0)
    regex, gfilter = None, None
    if patterns:
        _, listing, _ = _run(["ctest", "--test-dir", bdir, "-N"], root, deadline, env)
        names = re.findall(r"Test\s+#\d+:\s+(\S+)", listing)
        if any("." in n for n in names):       # gtest_discover_tests：每個 TEST 是一個 ctest 測試
            regex = "|".join(_glob_to_regex(p) for p in patterns)
        else:                                  # add_test(整個測試程式)：用 GTEST_FILTER 傳給 gtest
            gfilter = ":".join(patterns)
    cmd = ["ctest", "--test-dir", bdir, "--output-on-failure", "--timeout", str(max(10, int(deadline - time.time()) - 5))]
    if regex:
        cmd += ["-R", regex]
    code, out, _ = _run(cmd, root, deadline, _cpp_env(env, gfilter))
    secs = time.time() - t0
    if code is None:
        return _result(name, "timeout", summary="ctest 逾時", text=cc.clip_middle(out, MAX_SECTION_CHARS), secs=secs)
    counts = cc.ctest_counts(out)
    if "No tests were found" in out or not counts:
        return _result(name, "no_tests", summary="沒有收集到測試", text=cc.clip_middle(out, 2000), secs=secs)
    if code == 0 and not counts.get("failed"):
        return _result(name, "pass", counts, cc.format_counts(counts), "", secs)
    detail = _gtest_detail(out, counts, cp.ctest_failed(out)) or cc.clip_middle(out, MAX_SECTION_CHARS)
    return _result(name, "fail", counts, cc.format_counts(counts) or f"exit {code}", detail, secs)


def _make(root, info, patterns, env, deadline, t0):
    mf, target = info["make"]
    name = f"gtest（make{'' if mf in ('Makefile', 'makefile', 'GNUmakefile') else ' -f ' + mf} {target}）"
    cmd = ["make"] + ([] if mf in ("Makefile", "makefile", "GNUmakefile") else ["-f", mf])
    try:
        text = cc.read_text(os.path.join(root, mf))
    except OSError:
        text = ""
    if not re.search(r"-MM?D\b", text):
        cmd.append("-B")
    code, out, _ = _run(cmd + [target], root, deadline, _cpp_env(env, ":".join(patterns) if patterns else None))
    secs = time.time() - t0
    if code is None:
        return _result(name, "timeout", summary="逾時", text=cc.clip_middle(out, MAX_SECTION_CHARS), secs=secs)
    raw = cc.gtest_counts(out)
    counts = {k: v for k, v in raw.items() if v}
    missing = re.search(r"No rule to make target [`']([^']+)', needed by", out)
    if code != 0 and not counts and missing:      # 測試目標要的測試檔還不存在（例如 makefile_test 列的測試另外提供）
        return _result(name, "no_tests", summary=f"{mf} 的 {target} 需要的 {missing.group(1)} 不存在",
                       text=cc.clip_middle(out.rstrip(), 1500), secs=secs)
    if code == 0 and raw and not counts:          # gtest 跑了 0 個測試
        return _result(name, "no_tests", summary="gtest 沒有任何測試", text=cc.clip_middle(out.rstrip(), 1500), secs=secs)
    d = cp.diagnostics(out, roots=[root])
    if code != 0 and not counts and not info["tests"] and d["link"] and not d["errors"]:
        # 專案裡一個 C／C++ 測試檔都沒有，測試目標只剩 gtest_main 可以連結：是沒有測試，不是程式寫錯
        return _result(name, "no_tests", summary=f"專案裡沒有 C／C++ 測試檔（{mf} 的 {target} 沒有東西可以測）",
                       text=cc.clip_middle(out.rstrip(), 1500), secs=secs)
    if code != 0 and not counts and (d["errors"] or d["link"]):
        return _build_failed(name, "編譯失敗", out, root, secs)
    if code == 0 and not counts.get("failed"):
        if not counts:
            return _result(name, "pass", {}, f"make {target} 成功（輸出裡沒有 gtest 的摘要，看不出跑了幾個測試）",
                           cc.clip_middle(out.rstrip(), 2000), secs)
        return _result(name, "pass", counts, cc.format_counts(counts), "", secs)
    detail = _gtest_detail(out, counts) or cc.clip_middle(out.rstrip(), MAX_SECTION_CHARS)
    return _result(name, "fail", counts, cc.format_counts(counts) or f"make {target} 失敗（exit {code}）", detail, secs)


def _direct(root, info, tests, patterns, env, deadline, t0):
    cxx = os.environ.get("CXX", "g++")
    ccomp = os.environ.get("CC", "gcc")
    texts = {}
    for rel in set(info["sources"]) | set(tests):
        try:
            texts[rel] = cc.read_text(os.path.join(root, rel))
        except OSError:
            texts[rel] = ""
    if any(cp.uses_gtest(texts[t]) for t in tests):
        name = f"gtest（{cxx} 直接編譯）"
    else:
        name = f"C／C++ 測試程式（{ccomp if all(cp.ext_of(f) == '.c' for f in tests) else cxx} 直接編譯，結束碼 0 算通過）"
    if not tests:
        return _result(name, "no_tests", summary="沒有 C／C++ 測試檔")
    lib = [f for f in info["sources"] if not cp.has_main(texts[f])]
    dirs = cp.include_dirs(root, info)
    std = info.get("std") or "c++17"
    tmp = tempfile.mkdtemp(prefix="code_test_build_")
    env = _cpp_env(env)
    try:
        def compile_one(rel):
            obj = os.path.join(tmp, rel.replace(os.sep, "__") + ".o")
            inc = cp.include_flags(root, dirs + [d for d in cp.needed_include_dirs(root, rel, info["headers"]) if d not in dirs])
            cmd = ([ccomp, "-c", "-g"] if cp.ext_of(rel) == ".c" else [cxx, "-c", "-g", f"-std={std}"]) + inc + [rel, "-o", obj]
            code, out, _ = _run(cmd, root, deadline, env)
            return rel, obj, code, out

        with ThreadPoolExecutor(max_workers=max(1, min(8, os.cpu_count() or 2))) as ex:
            built = list(ex.map(compile_one, lib + [t for t in tests if t not in lib]))
        if any(code is None for _, _, code, _ in built):
            return _result(name, "timeout", summary="編譯逾時", secs=time.time() - t0)
        missing, bad = {}, []          # 只因為缺外部依賴（這台主機沒裝的 rclcpp 之類）編不過的檔案：跳過，不算程式的錯
        for b in built:
            if b[2] == 0:
                continue
            ext = [h for h in cp.missing_headers(b[3]) if cp.external_header(h, info)]
            other = [e for e in cp.diagnostics(b[3], roots=[root])["errors"]
                     if not any(f"fatal error: {h}:" in e.split("\n", 1)[0] for h in ext)]
            if ext and not other:
                missing[b[0]] = ext
            else:
                bad.append(b)
        if bad:
            return _build_failed(name, "編譯失敗", "\n".join(b[3] for b in bad), root, time.time() - t0)
        if missing:
            lib = [f for f in lib if f not in missing]
            tests = [t for t in tests if t not in missing]
            if not tests:
                return _result(name, "env", summary="缺外部依賴、沒辦法在這台主機建置", text=_env_text(root, info, missing),
                               secs=time.time() - t0)
        skipped = (f"（跳過 {sum(1 for f in missing if cp.is_test_source(f))} 個缺外部依賴的測試檔）"
                   if any(cp.is_test_source(f) for f in missing) else "")
        objs = {rel: obj for rel, obj, _, _ in built}
        libs = []
        for rx, flag in _EXTRA_LIBS:
            if flag and any(re.search(rx, texts[f]) for f in lib + tests) and flag not in libs:
                libs.append(flag)
        linker = cxx if any(cp.ext_of(f) != ".c" for f in lib + tests) else ccomp
        gtests = [t for t in tests if cp.uses_gtest(texts[t])]
        plain = [t for t in tests if t not in gtests]
        results, counts, details, failed = [], {}, [], False
        if gtests:
            binary = os.path.join(tmp, "gtest_bin")
            need_main = not any(cp.has_main(texts[t]) for t in gtests)
            gmock = any(re.search(r"#\s*include\s*[<\"]gmock/", texts[t]) for t in gtests)
            link = [cxx, "-o", binary] + [objs[f] for f in lib + gtests] + (["-lgmock"] if gmock else []) + ["-lgtest"] \
                + (["-lgtest_main"] if need_main else []) + ["-pthread"] + libs
            code, out, _ = _run(link, root, deadline, env)
            if code != 0:
                if "cannot find -lgtest" in out:
                    out += "\n（找不到 gtest 函式庫：請使用者安裝 GoogleTest，例如 sudo apt install libgtest-dev，或裝到 ~/.local）"
                r = _build_failed(name, "連結失敗", out, root, time.time() - t0)
                if missing:
                    r["text"] += "\n\n" + _env_text(root, info, missing, linked=True)
                return r
            run = [binary, "--gtest_color=no"] + ([f"--gtest_filter={':'.join(patterns)}"] if patterns else [])
            code, out, _ = _run(run, root, deadline, env)
            if code is None:
                return _result(name, "timeout", summary="測試逾時", text=cc.clip_middle(out, MAX_SECTION_CHARS), secs=time.time() - t0)
            counts = {k: v for k, v in cc.gtest_counts(out).items() if v}
            if code != 0 or counts.get("failed"):
                failed = True
                details.append(_gtest_detail(out, counts) or cc.clip_middle(out.rstrip(), 4000))
            results.append(f"{len(gtests)} 個 gtest 測試檔")
        for t in plain:                                # 不用 gtest 的測試：各自連成一個程式，結束碼 0 算通過
            binary = os.path.join(tmp, t.replace(os.sep, "__") + ".bin")
            code, out, _ = _run([linker, "-o", binary] + [objs[f] for f in lib] + [objs[t]] + libs, root, deadline, env)
            if code != 0:
                return _build_failed(name, f"連結失敗（{t}）", out, root, time.time() - t0)
            code, out, _ = _run([binary], root, deadline, env)
            ok = code == 0
            counts["passed" if ok else "failed"] = counts.get("passed" if ok else "failed", 0) + 1
            if not ok:
                failed = True
                why = "逾時" if code is None else f"exit {code}"
                details.append(f"✗ {t}（{why}）\n" + cc.clip_middle(out.rstrip(), 2000))
        secs = time.time() - t0
        if not counts:
            return _result(name, "no_tests", summary="沒有收集到測試", secs=secs)
        summary = cc.format_counts(counts) + skipped
        note = ("\n" + _env_text(root, info, missing)) if missing else ""
        if failed:
            return _result(name, "fail", counts, summary, "\n".join(details) + note, secs)
        return _result(name, "pass", counts, summary, f"（編譯了 {len(lib)} 個原始檔＋{len(tests)} 個測試檔）" + note, secs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _env_text(root, info, missing, linked=False):
    """缺外部依賴的檔案 → 說明：缺什麼、不是程式的錯、在哪裡才跑得了。"""
    heads = list(dict.fromkeys(h for hs in missing.values() for h in hs))
    lines = [f"- {f}：需要 {'、'.join(hs[:4])}" for f, hs in list(missing.items())[:8]]
    ros = info.get("ros")
    if ros:
        pkg = info.get("name") or os.path.basename(info.get("base") or root)
        how = (f"在有 ROS 2 的環境（例如 ROS 2 的容器）：colcon build --packages-select {pkg} && colcon test --packages-select {pkg}"
               " && colcon test-result --verbose")
    else:
        how = "在裝好這些函式庫的環境建置與測試"
    head = ("下面的檔案缺外部依賴或建置時才產生的標頭、沒有編譯（連結錯誤可能是因為少了它們）" if linked
            else f"{len(missing)} 個檔案缺外部依賴或建置時才產生的標頭（{'、'.join(heads[:5])}{'…' if len(heads) > 5 else ''}），沒有編譯")
    return (f"{head}：\n" + "\n".join(lines) + "\n外部依賴是 package.xml／CMakeLists.txt 宣告的，這台主機沒有安裝"
            + ("（沒有載入 ROS 2）" if ros and not cp.ros_sourced() else "") + "；產生的標頭（ROS 2 介面、建置檔產生的檔案）"
            "要建置之後才有——不是程式的錯誤，不要為了這個改程式。"
            f"要跑依賴它們的測試：{how}。")


def _prefix_paths(text, base, sub):
    """子專案裡跑出來的輸出（路徑相對於子專案）→ 路徑改成相對於工作區（模型才找得到檔案）。"""
    def fix(m):
        path = m.group(2)
        return m.group(1) + (os.path.join(base, path) if os.path.exists(os.path.join(sub, path)) else path) + m.group(3)
    return re.sub(r"(?m)(^|[\s(])([\w.\-/]+\.(?:c|cc|cpp|cxx|h|hpp|hh|hxx|py))(:\d+|\b)", fix, text)


def run_cpp_projects(root, info, selected, explicit, keyword, env, deadline):
    """工作區根目錄有自己的建置檔、或測試都不在子專案裡：照舊整個工作區一起跑。測試檔分屬不同的子專案（colcon 工作區的套件）
    時每個套件分開跑——各自的 include 目錄、原始檔、C++ 標準、建置檔，不會把整個工作區的原始檔編在一起。ROS 套件在沒有載入
    ROS 2 的機器上不用它的 CMake（find_package(ament_cmake) 就失敗），直接用 g++ 編譯跑得動的測試。"""
    tests = selected if selected is not None else info["tests"]
    groups = {}
    for t in tests:
        groups.setdefault(cp.project_dir(root, t), []).append(t)
    if info["cmake"] or info["make"] or list(groups) in ([], [""]):
        return [run_cpp(root, info, selected, explicit, keyword, env, deadline)]
    out = []
    for base, ts in groups.items():
        t0 = time.time()
        if not base:
            ginfo = dict(info, sources=[f for f in info["sources"] if not cp.project_dir(root, f)],
                         headers=[f for f in info["headers"] if not cp.project_dir(root, f)])
            r = _direct(root, ginfo, ts, _patterns(explicit, keyword), env, deadline, t0)
        else:
            ginfo = cp.detect(root, base)
            sub = os.path.join(root, base)
            if (ginfo["cmake"] and ginfo["cmake"]["tests"] or ginfo["make"]) and not (ginfo.get("ros") and not cp.ros_sourced()):
                sinfo = cp.detect(sub)
                r = run_cpp(sub, sinfo, [os.path.relpath(t, base) for t in ts] if selected is not None else None,
                            explicit, keyword, env, deadline)
                r["text"] = _prefix_paths(r["text"], base, sub)
            else:
                r = _direct(root, ginfo, ts, _patterns(explicit, keyword), env, deadline, t0)
        r["name"] += f"：{base or '工作區根目錄'}"
        out.append(r)
    return out


def _patterns(explicit, keyword):
    return list(explicit) or ([f"*{keyword.strip('*')}*"] if keyword else [])


def run_cpp(root, info, selected, explicit, keyword, env, deadline):
    """selected：要跑的 C／C++ 測試檔（None＝全部）；explicit：檔案::後面指定的 gtest 名稱。"""
    t0 = time.time()
    patterns = list(explicit)
    if not patterns and selected is not None and set(selected) != set(info["tests"]):
        for rel in selected:
            try:
                suites = cp.gtest_suites(cc.read_text(os.path.join(root, rel)))
            except OSError:
                suites = []
            patterns += [f"{s}.*" for s in suites] + [f"*/{s}.*" for s in suites]
    if keyword:
        kw = keyword.strip("*")
        patterns = [p.rstrip("*") + f"*{kw}*" for p in patterns] if patterns else [f"*{kw}*"]
    if info["cmake"] and info["cmake"]["tests"]:
        return _cmake(root, info, patterns, env, deadline, t0)
    if info["make"]:
        r = _make(root, info, patterns, env, deadline, t0)
        if r["status"] != "no_tests" or not info["tests"]:
            return r
        # makefile 的測試目標沒有測試可跑，但專案裡另外有 C／C++ 測試檔：直接編譯那些
    tests = selected if selected is not None else info["tests"]
    return _direct(root, info, tests, list(explicit) or ([f"*{keyword.strip('*')}*"] if keyword else []), env, deadline, t0)


def cpp_available(info):
    return bool((info["cmake"] and info["cmake"]["tests"]) or info["make"] or info["tests"])


# ---------------------------------------------------------------- 主程式
def main(argv):
    opts, err = parse_args(argv)
    if err:
        return err
    root = cc.base_root()
    py_targets, cpp_files, explicit, dirs = [], [], [], []
    for t in opts["targets"]:
        p, err = cc.resolve_path(t.split("::")[0])
        if err:
            return err
        if not os.path.exists(p):
            return f"[ERROR] 找不到測試路徑：{t}（相對於 {root}）。測試檔還沒建立的話，先建立再跑；看有哪些測試用 repo_map。"
        rel = os.path.relpath(p, root)
        if os.path.isdir(p):
            dirs.append((t, p, rel))
        elif cp.is_c_family(p):
            cpp_files.append(rel)
            if "::" in t:
                explicit.append(t.split("::", 1)[1])
        else:
            py_targets.append(t)
    env = cc.toolchain_env(root)
    deadline = time.time() + opts["timeout"]
    suites = []
    has_targets = bool(opts["targets"])
    cases_json = os.environ.get("CODE_TEST_JSON")      # coding job 的回歸檢查：每個測試的結果寫到這個 JSON 檔
    cases_dir = tempfile.mkdtemp(prefix="code_test_cases_") if cases_json else None
    if cases_dir:
        env = dict(env, CODE_TEST_CASES_DIR=cases_dir)
    run_root, cov_tmp = root, None
    if opts["coverage"]:                         # 在暫存副本裡跑（工作區不留 .coverage、.gcda、用 coverage 旗標編的 .o）
        cov_tmp, run_root = cov.make_copy(root)
        opts["py"] = cc.project_python(root)
        opts["cov_data"] = os.path.join(cov_tmp, ".coverage_ct")
        wrap = cov.compiler_wrappers(cov_tmp)
        env = dict(env, PATH=wrap + os.pathsep + env.get("PATH", ""), CXX=os.path.join(wrap, "g++"), CC=os.path.join(wrap, "gcc"))
        py_targets = [t if not os.path.isabs(t) else os.path.join(run_root, os.path.relpath(t, root)) for t in py_targets]
    try:
        out = _run_suites(opts, root, run_root, cov_tmp, py_targets, cpp_files, explicit, dirs, env, deadline, has_targets, suites)
        if cases_json:
            _write_cases(cases_dir, cases_json, out)
        return out
    finally:
        if cov_tmp:
            shutil.rmtree(cov_tmp, ignore_errors=True)
        if cases_dir:
            shutil.rmtree(cases_dir, ignore_errors=True)


def _write_cases(cases_dir, path, out):
    """pytest 的 junit XML 與 gtest 的 XML → {"cases": {"套件::名稱": passed／failed／skipped}, "head": 第一行}。"""
    import xml.etree.ElementTree as ET
    cases = {}
    for fn in sorted(os.listdir(cases_dir)):
        if not fn.endswith(".xml"):
            continue
        try:
            tree = ET.parse(os.path.join(cases_dir, fn))
        except ET.ParseError:
            continue
        for tc in tree.iter("testcase"):
            key = f"{tc.get('classname', '')}::{tc.get('name', '')}"
            status = "passed"
            for child in tc:
                if child.tag in ("failure", "error"):
                    status = "failed"
                elif child.tag == "skipped" or tc.get("result") == "skipped" or tc.get("status") == "notrun":
                    status = "skipped"
            if cases.get(key) != "failed":
                cases[key] = status
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"cases": cases, "head": out.split("\n", 1)[0][:300]}, f, ensure_ascii=False)


def _run_suites(opts, root, run_root, cov_tmp, py_targets, cpp_files, explicit, dirs, env, deadline, has_targets, suites):
    if opts["lang"] in (None, "python"):
        py_args = py_targets + [t for t, p, _ in dirs if has_python_tests(p)]
        if py_args or (not has_targets and has_python_tests(root)):
            suites += run_pytest_projects(run_root, py_args, opts, env, deadline)
    note = ""
    ran_cpp = False
    if opts["lang"] in (None, "cpp"):
        info = cp.detect(run_root)
        selected = None
        if has_targets:
            in_dirs = [f for f in info["tests"] for _, _, d in dirs if d in (".", "") or f.startswith(d.rstrip("/") + "/")]
            selected = list(dict.fromkeys([f for f in cpp_files if cp.is_test_source(f)] + in_dirs))
            if cpp_files and not selected and cpp_available(info):
                selected = None                         # 指定的是一般原始檔（不是測試檔）：跑全部 C／C++ 測試
                note = f"（{'、'.join(cpp_files)} 不是測試檔，改跑全部 C／C++ 測試）"
        if (selected is None and (not has_targets or cpp_files) and cpp_available(info)) or selected:
            suites += run_cpp_projects(run_root, info, selected, explicit, opts["keyword"], env, deadline)
            ran_cpp = True
    what = f"（{' '.join(opts['targets']) or '整個專案'}" + (f"，-k {opts['keyword']}" if opts["keyword"] else "") + f"）{note}"
    ran = [s for s in suites if s["status"] != "no_tests"]
    if not ran:
        detail = "\n".join(f"── {s['name']} ──\n{s['text']}" for s in suites if s["text"])
        return (f"[ERROR] 沒有收集到任何測試{what}：Python 測試檔名要是 test_*.py 或 *_test.py、測試函式名稱要以 test 開頭；"
                f"C／C++ 測試檔要叫 test_*.cpp／*_test.cpp 或放在 tests／ 目錄（或在 CMakeLists.txt 註冊、Makefile 加 test 目標）。"
                + (f"\n{detail}" if detail else ""))
    for s in suites:      # CMake 用絕對路徑編譯，gtest 的失敗訊息、連結錯誤裡的路徑換成相對於專案的
        for r in dict.fromkeys([root, os.path.abspath(root), run_root]):
            s["text"] = s["text"].replace(r.rstrip(os.sep) + os.sep, "")
    secs = sum(s["secs"] for s in suites)
    env_only = [s for s in ran if s["status"] == "env"]       # 缺外部依賴（這台主機沒有 ROS 2 之類），一個測試都跑不了
    tested = [s for s in ran if s["status"] != "env"]
    heads = "；".join(f"{s['name']} {s['summary']}" for s in tested)
    also = (f"（另外 {len(env_only)} 組缺外部依賴、沒辦法在這台主機跑：{'、'.join(s['name'] for s in env_only)}，見下面）"
            if env_only else "")
    if tested and all(s["status"] == "pass" for s in tested):
        first = f"[PASS] 測試全部通過：{heads}{also}（{secs:.1f} 秒）{what}"
    elif not tested:
        first = (f"{ENV_ONLY_HEAD}（缺外部依賴，不是程式的錯誤）：{'；'.join(s['name'] for s in env_only)}"
                 f"（{secs:.1f} 秒）{what}")
    else:
        first = f"[ERROR] 測試失敗：{heads}{also}（{secs:.1f} 秒）{what}"
    body = []
    if cov_tmp:                                  # --coverage：覆蓋率表放在最前面（測試的細節在後面）
        if opts.get("cov_data") and os.path.exists(opts["cov_data"]):
            body.append(cov.format_report("Python", cov.python_report(opts["py"], run_root, opts["cov_data"], env)))
        elif opts.get("cov_missing"):
            body.append(f"── 覆蓋率（Python）：沒有量到 ──\n{opts['cov_missing']} 沒有安裝 coverage（{opts['cov_missing']} -m pip install coverage）")
        if ran_cpp:
            body.append(cov.format_report("C／C++", cov.cpp_report(run_root, env)))
    for s in suites:
        if s["status"] == "no_tests":
            body.append(f"── {s['name']}：沒有收集到測試 ──")
        elif s["text"]:
            body.append(f"── {s['name']}：{s['summary']} ──\n{s['text']}")
    return first + ("\n" + "\n".join(body) if body else "")


if __name__ == "__main__":
    try:
        print(main(sys.argv[1:]))
    except Exception as e:
        print(f"[ERROR] code_test 未預期的例外: {e}", file=sys.stderr)
        sys.exit(1)
