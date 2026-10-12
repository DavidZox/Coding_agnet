"""DevBench 的工作區準備與計分（prepare.py --verify 與 run.py 共用）。

- make_workspace：agent 開始時的工作區＝規格文件（PRD、UML 類別圖與循序圖、架構設計）＋ repo_config 的 required_files
  （資料檔、第三方程式庫、測試用的 makefile_test）——跟 DevBench 實作任務給模型的一樣，原始碼與測試都不在裡面。
- task_text：交給 coding orchestrator 的任務：規格文件的路徑＋依 code_file_DAG 排好的「要寫的檔案」。
- evaluate：計分前把官方的單元／驗收測試放回去（agent 自己在同名目錄寫的測試換掉）、required_files 換回原本的（agent 可能改過
  makefile_test 或預期輸出）、照 setup_shell_script 建目錄，再用真的 pytest／gtest 跑：
  Python：pytest <unit_tests>、pytest <acceptance_tests>（數通過的測試）；
  C++：make -B -f makefile_test test（數 gtest 的 [       OK ]）、acceptance_tests/test.sh（數通過的標記）或 pytest 驗收測試。
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(HERE, "data")
VENV = os.path.join(HERE, ".venv")
VENV_PY = os.path.join(VENV, "bin", "python")
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)
from evals.devbench.repos import REPOS  # noqa: E402
from skills_system.scripts import _code_common as cc  # noqa: E402

DOC_KEYS = {"PRD": "PRD.md", "UML_class": "UML_class.md", "UML_sequence": "UML_sequence.md",
            "architecture_design": "architecture_design.md"}
TEST_TIMEOUT = 600


def repo_dir(name):
    return os.path.join(DATA, REPOS[name]["lang"], name)


def config(name):
    with open(os.path.join(repo_dir(name), "repo_config.json"), encoding="utf-8") as f:
        return json.load(f)


def doc_paths(cfg):
    return [cfg.get(k) or default for k, default in DOC_KEYS.items()]


def _expand(src, pattern):
    return [os.path.relpath(p, src) for p in sorted(glob.glob(os.path.join(src, pattern)))]


def _copy(src_root, dst_root, rel):
    s, d = os.path.join(src_root, rel), os.path.join(dst_root, rel)
    if os.path.isdir(s):
        shutil.copytree(s, d, dirs_exist_ok=True)
    elif os.path.isfile(s):
        os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
        shutil.copy2(s, d)


def _required(src, ws, cfg):
    """required_files 複製到工作區。「data/*」這種樣式在資料裡是空的（git 不存空目錄）時，建立空的 data 目錄：
    repo 要的是那個目錄（logistic_system 的單元測試會寫 data/account.txt）。"""
    for pat in cfg.get("required_files") or []:
        rels = _expand(src, pat)
        for rel in rels:
            _copy(src, ws, rel)
        if not rels and pat.endswith("/*"):
            os.makedirs(os.path.join(ws, pat[:-2]), exist_ok=True)


def make_workspace(name, ws, visible_tests=False):
    """visible_tests：官方的單元／驗收測試也放進工作區（DevBench 基準 agent 的做法：它的 prepare_required_files 一開始就把
    測試目錄複製進去，--review execution 時把測試結果回饋給模型）。預設不放：agent 從頭到尾看不到官方測試。"""
    src, cfg = repo_dir(name), config(name)
    os.makedirs(ws, exist_ok=True)
    for rel in doc_paths(cfg):
        _copy(src, ws, rel)
    _required(src, ws, cfg)
    if visible_tests:
        for key in ("unit_tests", "acceptance_tests"):
            if cfg.get(key):
                _copy(src, ws, cfg[key])
        for rel in _setup_dirs(src, cfg):
            os.makedirs(os.path.join(ws, rel), exist_ok=True)


def dag_order(cfg):
    """code_file_DAG（檔案 → 它依賴的檔案）→ 依賴的在前面的順序（同一層照出現的順序）。"""
    dag = cfg.get("code_file_DAG") or {}
    nodes = []
    for k, deps in dag.items():
        for x in list(deps) + [k]:
            if x not in nodes:
                nodes.append(x)
    done, order = set(), []
    while len(order) < len(nodes):
        progressed = False
        for n in nodes:
            if n not in done and all(d in done for d in dag.get(n, [])):
                done.add(n)
                order.append(n)
                progressed = True
        if not progressed:                     # 有環（不應該發生）：剩下的照順序
            order += [n for n in nodes if n not in done]
            break
    return order


def task_text(name, visible_tests=False):
    cfg, lang = config(name), REPOS[name]["lang"]
    docs = doc_paths(cfg)
    files = dag_order(cfg)
    listed = "\n".join(f"{i}. {f}" for i, f in enumerate(files, 1))
    if lang == "python":
        extra = ("架構設計的檔案結構裡列出、但工作區還沒有的其他原始檔（例如套件的 __init__.py）也要建立，套件要能照文件裡的用法 import 與使用。"
                 "需要的第三方套件已經裝好（docs 或根目錄的 requirements.txt）。")
        lang_name = "Python"
    else:
        extra = ("用 C++17。建置檔 makefile 要照文件寫，`make` 要編出文件裡的執行檔；makefile_test 是測試用的建置檔（已經寫好，不要改），"
                 "執行檔名稱、原始檔的路徑與檔名都要跟它一致（文件沒寫執行檔名稱時就照 makefile_test 的 TARGET）。"
                 "架構設計裡列出、但上面沒有列的原始檔也要建立。")
        lang_name = "C++"
    if visible_tests:
        tests = "、".join(cfg[k] for k in ("unit_tests", "acceptance_tests") if cfg.get(k))
        test_line = (f"官方的單元測試與驗收測試已經在工作區（{tests}）：不要修改它們；用 code_test 跑它們確認實作，最後也是用它們計分。")
    else:
        test_line = ("測試（unit_tests、acceptance_tests、tests）與範例不用寫，另外有官方的測試會檢查——可以自己寫測試確認，"
                     "但不要放在那幾個目錄。")
    return (f"依照工作區裡的規格文件，實作這個 {lang_name} 專案（DevBench 的實作任務）。\n"
            f"規格文件：{docs[0]}（需求）、{docs[1]}（UML 類別圖）、{docs[2]}（UML 循序圖）、{docs[3]}（架構設計：檔案結構與每個檔案的內容）。\n"
            f"要寫的原始碼檔案（照這個順序，被依賴的先寫）：\n{listed}\n"
            f"{extra}\n"
            f"類別與函式的名稱、參數、回傳值、命令列用法與輸出格式都要完全照文件；{test_line}")


def _setup_dirs(src, cfg):
    """setup_shell_script 裡建目錄的指令（安裝 googletest、pip install 那些這裡已經處理好，不照做）。"""
    path = os.path.join(src, cfg.get("setup_shell_script") or "setup_shell_script.sh")
    try:
        lines = cc.read_text(path).splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        m = re.match(r"^\s*mkdir\s+(?:-p\s+)?([^\s;&|]+)\s*$", ln)
        if m and m.group(1).strip("\"'") != "build":
            out.append(m.group(1).strip("\"'"))
    return out


def prepare_eval(name, ws):
    src, cfg = repo_dir(name), config(name)
    for key in ("unit_tests", "acceptance_tests"):
        rel = cfg.get(key)
        if rel:
            target = os.path.join(ws, rel)
            if os.path.isdir(target):
                shutil.rmtree(target)
            elif os.path.exists(target):
                os.remove(target)
            _copy(src, ws, rel)
    _required(src, ws, cfg)
    for rel in _setup_dirs(src, cfg):
        os.makedirs(os.path.join(ws, rel), exist_ok=True)


def _clean_objects(ws):
    """C++ 的每個計分步驟前清掉建置產物（.o、coverage 的 .gcda／.gcno）：makefile_test 用 coverage 旗標編的 .o 留著，
    agent 的 makefile 會直接拿去連結（少了 -lgcov 就連結失敗）——那是計分流程的問題，不是 agent 的。"""
    for dirpath, dirnames, filenames in os.walk(ws):
        for fn in filenames:
            if fn.endswith((".o", ".gcda", ".gcno")):
                try:
                    os.remove(os.path.join(dirpath, fn))
                except OSError:
                    pass


def eval_env(ws):
    env = cc.toolchain_env(ws, base=dict(os.environ, CODE_PYTHON=VENV_PY))
    env["PATH"] = os.path.dirname(VENV_PY) + os.pathsep + env.get("PATH", "")    # 測試裡的 python 指令用 DevBench 的 .venv
    env["LC_MESSAGES"] = "C"
    env["GTEST_COLOR"] = "no"
    env.pop("GTEST_FILTER", None)
    if not shutil.which("cc", path=env["PATH"]) and shutil.which("gcc", path=env["PATH"]):
        env["CC"] = "gcc"
    return env


def _run(cmd, ws, env, timeout=TEST_TIMEOUT):
    try:
        p = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True, errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL, shell=isinstance(cmd, str), start_new_session=True)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return None, out + f"\n（逾時：超過 {timeout} 秒）"


def _pytest_passed(out):
    return cc.summarize_test_counts(out).get("passed", 0)


def evaluate(name, ws):
    """回傳 dict：unit／unit_total、acceptance／acceptance_total（通過數與預期數）、unit_tail／acceptance_tail（輸出的尾巴）、seconds。"""
    t0 = time.time()
    meta, cfg = REPOS[name], config(name)
    prepare_eval(name, ws)
    env = eval_env(ws)
    if meta["lang"] == "python":
        code_u, out_u = _run([VENV_PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--color=no", cfg["unit_tests"]], ws, env)
        unit = _pytest_passed(out_u)
        code_a, out_a = _run([VENV_PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--color=no", cfg["acceptance_tests"]], ws, env)
        acc = _pytest_passed(out_a)
    else:
        _clean_objects(ws)
        code_u, out_u = _run("make -B -f makefile_test test", ws, env)
        unit = len(re.findall(r"^\[       OK \] ", out_u, re.M))       # 跑到一半當掉時，前面通過的也算
        _clean_objects(ws)
        if meta.get("acceptance_pytest"):
            _, out_b = _run("make", ws, env)
            code_a, out_a = _run([VENV_PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--color=no", meta["acceptance_pytest"]], ws, env)
            out_a = out_b[-1500:] + "\n" + out_a
            acc = _pytest_passed(out_a)
        else:
            code_a, out_a = _run(["bash", "acceptance_tests/test.sh"], ws, env)
            acc = len(re.findall(meta["marker"], out_a, re.M))
    return {"unit": min(unit, meta["unit"]), "unit_total": meta["unit"], "acceptance": min(acc, meta["acceptance"]),
            "acceptance_total": meta["acceptance"], "unit_exit": code_u, "acceptance_exit": code_a,
            "unit_tail": out_u[-3000:], "acceptance_tail": out_a[-3000:], "seconds": round(time.time() - t0, 1)}


def verify_reference(names, log=print):
    """參考實作（完整的 repo）跑一次計分：全部通過才表示環境與計分方式是對的。回傳 [(名稱, 結果)]。"""
    import tempfile
    out = []
    for name in names:
        tmp = tempfile.mkdtemp(prefix=f"devbench_ref_{name}_")
        try:
            shutil.copytree(repo_dir(name), tmp, dirs_exist_ok=True)
            r = evaluate(name, tmp)
            ok = r["unit"] == r["unit_total"] and r["acceptance"] == r["acceptance_total"]
            log(f"  {'✅' if ok else '❌'} {name:30s} 單元 {r['unit']}/{r['unit_total']}  驗收 {r['acceptance']}/{r['acceptance_total']}"
                f"（{r['seconds']} 秒）")
            if not ok:
                log("    單元測試輸出（尾巴）：\n" + "\n".join("      " + x for x in r["unit_tail"][-1200:].splitlines()))
                log("    驗收測試輸出（尾巴）：\n" + "\n".join("      " + x for x in r["acceptance_tail"][-1200:].splitlines()))
            out.append((name, r))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return out
