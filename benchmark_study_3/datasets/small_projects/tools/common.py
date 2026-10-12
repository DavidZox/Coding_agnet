"""小專案任務（small_projects）的共用工具：路徑、執行指令、複製工作區、跑 pytest／gtest 並逐一取得每個測試的結果、
覆蓋率（coverage.py／gcovr＋gcov-11）、C++ 的統一測試 makefile。只用標準庫（coverage、gcovr 由評測的虛擬環境提供）。"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.dirname(HERE)                                    # benchmark_study_3/datasets/small_projects
STUDY = os.path.dirname(os.path.dirname(DATASET))                  # benchmark_study_3
HARNESS = os.path.dirname(STUDY)                                   # Coding_agent_harness
DEVBENCH_DATA = os.path.join(HARNESS, "evals", "devbench", "data")
VENV_PY = os.path.join(HARNESS, "evals", "devbench", ".venv", "bin", "python")   # pytest、coverage、numpy、text_unidecode
HARNESS_VENV_BIN = os.path.expanduser("~/aiagent_venv_env/.venv/bin")             # gcovr、cmake、ninja
LOCAL_PREFIX = os.path.expanduser("~/.local")                                     # gtest、sqlite3
GCOV = shutil.which("gcov") or shutil.which("gcov-11") or "gcov"
TEST_TIMEOUT = 120


def env_for(ws):
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([os.path.dirname(VENV_PY), HARNESS_VENV_BIN, env.get("PATH", "")])
    for var, sub in (("CPATH", "include"), ("LIBRARY_PATH", "lib"), ("LD_LIBRARY_PATH", "lib")):
        env[var] = os.pathsep.join(p for p in (os.path.join(LOCAL_PREFIX, sub), env.get(var, "")) if p)
    env["GTEST_COLOR"] = "no"
    env["LC_ALL"] = "C.UTF-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("GTEST_FILTER", None)
    return env


def run(cmd, cwd, env=None, timeout=TEST_TIMEOUT):
    """回傳 (exit code 或 None＝逾時, 輸出)。逾時時結束整個程序群組（不留孤兒）。"""
    import signal
    p = subprocess.Popen(cmd, cwd=cwd, env=env or env_for(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         errors="replace", stdin=subprocess.DEVNULL, shell=isinstance(cmd, str), start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        out, _ = p.communicate()
        return None, (out or "") + f"\n（逾時：超過 {timeout} 秒）"


def copytree(src, dst, ignore_names=()):
    ign = shutil.ignore_patterns("__pycache__", "*.pyc", "*.o", "*.gcda", "*.gcno", "*.gcov", ".pytest_cache", *ignore_names)
    shutil.copytree(src, dst, ignore=ign, dirs_exist_ok=True)


def file_hashes(root, rels=None):
    out = {}
    paths = rels if rels is not None else [os.path.relpath(os.path.join(dp, fn), root) for dp, dns, fns in os.walk(root)
                                           for fn in fns if "__pycache__" not in dp and not fn.endswith((".pyc", ".o", ".gcda", ".gcno"))]
    for rel in paths:
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                out[rel] = hashlib.sha1(f.read()).hexdigest()
    return out


# ================================================================ Python：pytest 逐一取得結果、覆蓋率
def pytest_cases(ws, test_paths, extra=(), timeout=TEST_TIMEOUT):
    """跑 pytest，回傳 (每個測試的結果 {nodeid: passed/failed/error/skipped}, exit code, 輸出)。"""
    fd, xml_path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    cmd = [VENV_PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml_path}", "--rootdir", ws, *extra, *test_paths]
    code, out = run(cmd, ws, timeout=timeout)
    cases = {}
    try:
        tree = ET.parse(xml_path)
        for tc in tree.iter("testcase"):
            cls, name = tc.get("classname", ""), tc.get("name", "")
            node = f"{cls}::{name}"
            status = "passed"
            for child in tc:
                if child.tag in ("failure", "error"):
                    status = "failed"
                elif child.tag == "skipped":
                    status = "skipped"
            cases[node] = status
    except (ET.ParseError, FileNotFoundError):
        pass
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass
    return cases, code, out


def junit_to_nodeids(ws, cases):
    """junit 的 classname（unit_tests.test_x.TestY）＋name → pytest 的 nodeid（unit_tests/test_x.py::TestY::name）。"""
    ids = {}
    for key, status in cases.items():
        cls, name = key.split("::", 1)
        parts = cls.split(".")
        for cut in range(len(parts), 0, -1):
            rel = os.path.join(*parts[:cut]) + ".py"
            if os.path.exists(os.path.join(ws, rel)):
                node = rel + "::" + "::".join(parts[cut:] + [name])
                ids[node] = status
                break
        else:
            ids[key] = status
    return ids


def pytest_coverage(ws, test_paths, sources, nodeids=None, timeout=TEST_TIMEOUT * 2):
    """只用通過的測試量覆蓋率：回傳 {"line": %, "branch": %, "files": {檔案: {line, missing}}}；sources 是要量的套件或檔案。"""
    data_file = os.path.join(ws, ".coverage_sp")
    rc = os.path.join(ws, ".coveragerc_sp")
    with open(rc, "w", encoding="utf-8") as f:
        f.write("[run]\nbranch = True\ndata_file = " + data_file + "\nsource =\n" + "".join(f"    {s}\n" for s in sources)
                + "omit =\n    */unit_tests/*\n    */tests/*\n    */test_*.py\n    *_test.py\n    */conftest.py\n")
    targets = nodeids if nodeids is not None else test_paths
    if not targets:
        return {"line": 0.0, "branch": 0.0, "files": {}, "covered_lines": 0, "num_statements": 0}
    code, out = run([VENV_PY, "-m", "coverage", "run", f"--rcfile={rc}", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                     "--rootdir", ws, *targets], ws, timeout=timeout)
    jpath = os.path.join(ws, ".coverage_sp.json")
    run([VENV_PY, "-m", "coverage", "json", f"--rcfile={rc}", "-o", jpath], ws)
    try:
        with open(jpath, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"line": 0.0, "branch": 0.0, "files": {}, "error": out[-800:]}
    finally:
        for p in (data_file, rc, jpath):
            try:
                os.remove(p)
            except OSError:
                pass
    tot = data.get("totals", {})
    files = {os.path.relpath(os.path.abspath(os.path.join(ws, k)), ws): {"line": round(v["summary"].get("percent_covered", 0.0), 1),
                                                                       "missing": v.get("missing_lines", [])}
             for k, v in (data.get("files") or {}).items()}
    nb = tot.get("num_branches", 0)
    return {"line": round(100.0 * tot.get("covered_lines", 0) / max(1, tot.get("num_statements", 0)), 1),
            "branch": round(100.0 * tot.get("covered_branches", 0) / nb, 1) if nb else None,
            "covered_lines": tot.get("covered_lines", 0), "num_statements": tot.get("num_statements", 0),
            "covered_branches": tot.get("covered_branches", 0), "num_branches": nb, "files": files}


# ================================================================ C++：統一的測試 makefile、gtest 逐一結果、gcovr 覆蓋率
TW_MAKEFILE = """# 測試用的 makefile（評測產生）：自動收集 {test_dir}/*.cpp，跟正式程式（main.cpp 以外）一起連結 gtest 執行。
# make -f makefile_test test     建置並執行全部測試（GTEST 參數可以用 ARGS="--gtest_filter=..."）
# make -f makefile_test coverage 加上 coverage 旗標重新建置、執行，再用 gcovr 印出覆蓋率
CXX = g++
CC = gcc
CXXFLAGS ?= -std=c++17 -g -O0
INCLUDES = -Iinclude -I. {extra_includes}
PROD_SRCS = {prod_srcs}
PROD_C_SRCS = {prod_c_srcs}
TEST_SRCS = $(wildcard {test_dir}/*.cpp)
BUILD = build_test
PROD_OBJS = $(patsubst %.cpp,$(BUILD)/%.o,$(PROD_SRCS)) $(patsubst %.c,$(BUILD)/%.c.o,$(PROD_C_SRCS))
TEST_OBJS = $(patsubst %.cpp,$(BUILD)/%.o,$(TEST_SRCS))
LIBS = -lgtest -lgtest_main -pthread {extra_libs}
COV ?=

.PHONY: test coverage clean
test: $(BUILD)/run_tests
\t./$(BUILD)/run_tests $(ARGS)

$(BUILD)/run_tests: $(PROD_OBJS) $(TEST_OBJS)
\t$(CXX) $(CXXFLAGS) $(COV) -o $@ $^ $(LIBS)

$(BUILD)/%.o: %.cpp
\t@mkdir -p $(dir $@)
\t$(CXX) $(CXXFLAGS) $(COV) $(INCLUDES) -MMD -MP -c -o $@ $<

$(BUILD)/%.c.o: %.c
\t@mkdir -p $(dir $@)
\t$(CC) -O0 $(INCLUDES) -c -o $@ $<

coverage:
\trm -rf $(BUILD)
\t$(MAKE) -f makefile_test COV=--coverage test
\tgcovr -r . --gcov-executable {gcov} {gcovr_filters} --exclude-throw-branches --exclude-unreachable-branches --print-summary --txt

clean:
\trm -rf $(BUILD)

-include $(shell find $(BUILD) -name '*.d' 2>/dev/null)
"""


def tw_makefile(prod_srcs, prod_c_srcs=(), test_dir="unit_tests", extra_includes="", extra_libs="", cov_filters=()):
    filters = " ".join(f"--filter '{f}'" for f in cov_filters)
    return TW_MAKEFILE.format(test_dir=test_dir, prod_srcs=" ".join(prod_srcs), prod_c_srcs=" ".join(prod_c_srcs),
                              extra_includes=extra_includes, extra_libs=extra_libs, gcov=GCOV, gcovr_filters=filters)


def gtest_cases(ws, args="", cov=False, timeout=TEST_TIMEOUT * 2):
    """建置並執行 makefile_test 的 test 目標，用 --gtest_output 取得每個測試的結果。回傳 (結果, exit code, 輸出)。
    建置失敗時結果是空的、輸出含編譯錯誤。"""
    fd, xml_path = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    os.remove(xml_path)
    gargs = f"--gtest_output=xml:{xml_path} {args}".strip()
    cmd = ["make", "-s", "-f", "makefile_test", "test", f"ARGS={gargs}"] + (["COV=--coverage"] if cov else [])
    code, out = run(cmd, ws, timeout=timeout)
    cases = {}
    try:
        tree = ET.parse(xml_path)
        for tc in tree.iter("testcase"):
            node = f"{tc.get('classname')}.{tc.get('name')}"
            status = "failed" if any(ch.tag == "failure" for ch in tc) else ("skipped" if tc.get("result") == "skipped" else "passed")
            cases[node] = status
    except (ET.ParseError, FileNotFoundError):
        pass
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass
    return cases, code, out


def gcovr_summary(ws, filters, excludes=()):
    """gcovr 的 JSON 摘要（先跑過 coverage 建置的測試）。回傳 {"line": %, "branch": %, "files": {...}}。"""
    jpath = os.path.join(ws, ".gcovr_sp.json")
    cmd = [os.path.join(HARNESS_VENV_BIN, "gcovr"), "-r", ".", "--gcov-executable", GCOV, "--exclude-throw-branches",
           "--exclude-unreachable-branches", "--json-summary", jpath]
    for f in filters:
        cmd += ["--filter", f]
    for e in excludes:
        cmd += ["--exclude", e]
    code, out = run(cmd, ws)
    try:
        with open(jpath, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"line": 0.0, "branch": 0.0, "files": {}, "error": out[-800:]}
    finally:
        try:
            os.remove(jpath)
        except OSError:
            pass
    files = {f["filename"]: {"line": f.get("line_percent"), "branch": f.get("branch_percent")} for f in data.get("files", [])}
    return {"line": data.get("line_percent", 0.0), "branch": data.get("branch_percent", 0.0),
            "covered_lines": data.get("line_covered"), "num_statements": data.get("line_total"),
            "covered_branches": data.get("branch_covered"), "num_branches": data.get("branch_total"), "files": files}


def clean_build(ws):
    shutil.rmtree(os.path.join(ws, "build_test"), ignore_errors=True)
    for dp, dns, fns in os.walk(ws):
        for fn in fns:
            if fn.endswith((".gcda", ".gcno", ".gcov")):
                try:
                    os.remove(os.path.join(dp, fn))
                except OSError:
                    pass


def count_assertions(path):
    """一個測試檔裡每個測試函式有沒有斷言（衛生檢查）：回傳 (測試數, 沒有斷言的測試數)。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
    except OSError:
        return 0, 0
    if path.endswith(".py"):
        blocks = re.split(r"\n(?=\s*def test_)", src)
        tests = [b for b in blocks if re.match(r"\s*def test_", b)]
        bare = [b for b in tests if not re.search(r"\bassert\b|pytest\.raises|self\.assert|pytest\.approx|\.assert_", b)]
        return len(tests), len(bare)
    blocks = re.split(r"\n(?=\s*TEST(?:_F|_P)?\s*\()", src)
    tests = [b for b in blocks if re.match(r"\s*TEST(?:_F|_P)?\s*\(", b)]
    bare = [b for b in tests if not re.search(r"\b(EXPECT|ASSERT)_[A-Z_]+\s*\(", b)]
    return len(tests), len(bare)
