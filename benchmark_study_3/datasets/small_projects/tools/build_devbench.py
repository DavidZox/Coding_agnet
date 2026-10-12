"""從 DevBench 的 12 個 repo（參考實作＋官方測試）產生「既有小專案」的任務。

    python3 build_devbench.py mutants [--only readtime,...]   # 1. 產生 mutant、用官方單元測試判定哪些抓得到（較久）
    python3 build_devbench.py tasks                            # 2. 產生任務：寫測試（tw）、修 bug（bf）
    python3 build_devbench.py verify                           # 3. 檢查：tw 的參考答案（官方測試）、bf 的參考解（原始碼）都要拿滿分

- tw（寫測試＋覆蓋率）：工作區＝參考實作＋文件，拿掉官方測試；請 agent 在 unit_tests/ 寫測試並量覆蓋率。
- bf（修多個 bug）：工作區＝參考實作＋官方單元測試，植入 2～3 個「官方單元測試抓得到」的 mutant（盡量分在不同檔案），
  驗收測試拿掉（計分時才放回）。
- 功能任務（fe）是人工設計的，見 fe_specs.py。

輸出：../mutants/<repo>.json、../tasks/<任務>.json、../workspaces/<任務>/（工作區範本）。
"""
import argparse
import json
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C          # noqa: E402
import mutate as M          # noqa: E402

MUTANT_DIR = os.path.join(C.DATASET, "mutants")
TASK_DIR = os.path.join(C.DATASET, "tasks")
WS_DIR = os.path.join(C.DATASET, "workspaces")
SEED = 20261010
MUTANTS_PER_REPO = 60

PY = {
    "readtime": {"pkg": ["readtime"], "prod": ["readtime/api.py", "readtime/result.py", "readtime/utils.py"]},
    "particle-swarm-optimization": {"pkg": ["pso"], "prod": ["pso/cost_functions.py", "pso/pso_simple.py"]},
    "chakin": {"pkg": ["chakin"], "prod": ["chakin/downloader.py"]},
    "stocktrends": {"pkg": ["stocktrends"], "prod": ["stocktrends/indicators.py"]},
    "geotext": {"pkg": ["geotext"], "prod": ["geotext/geotext.py"]},
    "hone": {"pkg": ["hone"], "prod": ["hone/hone.py", "hone/utils/csv_utils.py", "hone/utils/json_utils.py"]},
    "lice": {"pkg": ["lice"], "prod": ["lice/core.py"]},
}
CPP = {
    "area_calculation": {"srcs": ["src/Shape.cpp", "src/Rectangle.cpp"],
                         "prod": ["src/Shape.cpp", "src/Rectangle.cpp", "include/Circle.hpp", "include/Square.hpp"],
                         "cov": ["src/", "include/"]},
    "graph-cpp": {"srcs": [], "prod": ["include/al_graph.hpp", "include/am_graph.hpp", "include/queue.hpp", "include/stack.hpp"],
                  "cov": ["include/"]},
    "logistic_system": {"srcs": ["src/account.cpp", "src/expressage.cpp", "src/logistics.cpp"],
                        "prod": ["src/account.cpp", "src/expressage.cpp", "src/logistics.cpp"], "cov": ["src/", "include/"]},
    "people_management": {"srcs": ["src/people_management.cpp", "src/utils.cpp"], "prod": ["src/people_management.cpp", "src/utils.cpp"],
                          "test_dir": "tests", "libs": "-lsqlite3", "cov": ["src/", "include/"]},
    "xlsx2csv": {"srcs": ["src/archive.cpp", "src/utils.cpp", "src/workbook.cpp", "src/worksheet.cpp", "src/tinyxml2.cpp"],
                 "c_srcs": ["src/miniz.c"], "prod": ["src/archive.cpp", "src/utils.cpp", "src/workbook.cpp", "src/worksheet.cpp"],
                 "cov": ["src/archive", "src/utils", "src/workbook", "src/worksheet", "include/archive", "include/utils",
                         "include/workbook", "include/worksheet", "include/types"]},
}
DROP = {"repo_config.json", "setup_shell_script.sh", "test_outputs", "temp_report.json"}


def repo_path(name):
    lang = "python" if name in PY else "cpp"
    return os.path.join(C.DEVBENCH_DATA, lang, name)


def spec(name):
    return PY.get(name) or CPP[name]


def test_dir(name):
    return spec(name).get("test_dir", "unit_tests")


def write_makefile(name, ws):
    s = spec(name)
    with open(os.path.join(ws, "makefile_test"), "w", encoding="utf-8") as f:
        f.write(C.tw_makefile(s["srcs"], s.get("c_srcs", ()), test_dir(name), extra_libs=s.get("libs", ""),
                              cov_filters=s["cov"]))


def ref_workspace(name, dst):
    """參考實作＋官方單元測試（C++ 換成統一的 makefile_test），拿來判定 mutant。"""
    C.copytree(repo_path(name), dst)
    make_setup_dirs(name, dst)
    if name in CPP:
        write_makefile(name, dst)
    return dst


def make_setup_dirs(name, ws):
    """setup_shell_script.sh 裡只照做 mkdir（腳本還會 git clone、sudo make install 之類的，不能直接執行）。"""
    sys.path.insert(0, os.path.join(C.HARNESS, "evals", "devbench"))
    import evaluate as ev                    # noqa: E402
    cfg = ev.config(name)
    for rel in ev._setup_dirs(repo_path(name), cfg):
        os.makedirs(os.path.join(ws, rel), exist_ok=True)
    for pat in cfg.get("required_files") or []:     # 「data/*」這種樣式：git 沒存空目錄，要自己建
        if pat.endswith("/*"):
            os.makedirs(os.path.join(ws, pat[:-2]), exist_ok=True)


def run_official_unit(name, ws, timeout=120):
    """回傳 (全部通過?, 結果, 輸出)。"""
    if name in PY:
        cases, code, out = C.pytest_cases(ws, [test_dir(name)], extra=["-x"], timeout=timeout)
        return code == 0, cases, out
    cases, code, out = C.gtest_cases(ws, timeout=timeout)
    return code == 0 and bool(cases), cases, out


# ================================================================ 1. mutants
def build_mutants(name):
    import tempfile
    tmp = tempfile.mkdtemp(prefix=f"sp_mut_{name}_")
    ws = ref_workspace(name, os.path.join(tmp, "ws"))
    ok, cases, out = run_official_unit(name, ws)
    if not ok:
        raise SystemExit(f"{name}：參考實作的官方單元測試沒有全過\n{out[-2000:]}")
    points = {}
    for rel in spec(name)["prod"]:
        with open(os.path.join(ws, rel), encoding="utf-8") as f:
            points[rel] = M.points_for(rel, f.read())
    chosen = M.sample(points, MUTANTS_PER_REPO, seed=SEED)
    results = []
    for i, (rel, pt) in enumerate(chosen):
        path = os.path.join(ws, rel)
        with open(path, encoding="utf-8") as f:
            orig = f.read()
        mutated = M.apply_for(rel, orig, pt)
        if mutated == orig:
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(mutated)
        try:
            ok, cases, out = run_official_unit(name, ws, timeout=60)
            invalid = name in CPP and not cases and ("error" in out.lower())
            results.append({"id": f"{name}#m{i}", "file": rel, "line": pt["line"], "desc": pt["desc"], "point": pt,
                            "killed": (not ok) and not invalid, "invalid": invalid,
                            "failed_tests": sorted(k for k, v in cases.items() if v != "passed")[:20]})
        finally:
            with open(path, "w", encoding="utf-8") as f:
                f.write(orig)
        print(f"  {name} {i + 1}/{len(chosen)} {rel}:{pt['line']} {pt['desc']} → "
              f"{'無效' if results[-1]['invalid'] else ('抓到' if results[-1]['killed'] else '沒抓到')}", flush=True)
    os.makedirs(MUTANT_DIR, exist_ok=True)
    with open(os.path.join(MUTANT_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump({"repo": name, "seed": SEED, "official_tests": len(cases), "mutants": results}, f, ensure_ascii=False, indent=1)
    shutil.rmtree(tmp, ignore_errors=True)
    k = sum(1 for r in results if r["killed"])
    print(f"{name}：{len(results)} 個 mutant，官方單元測試抓到 {k} 個、無效 {sum(1 for r in results if r['invalid'])} 個", flush=True)


# ================================================================ 2. tasks
def coding_notes(name):
    if name in PY:
        pkg = " ".join(spec(name)["pkg"])
        return ("# 開發環境說明\n\n- Python 3，套件已經裝好（pytest、coverage、pytest-cov）。\n"
                f"- 跑測試：`python -m pytest -q {test_dir(name)}`\n"
                f"- 量覆蓋率（行＋分支）：`python -m pytest --cov={pkg} --cov-branch --cov-report=term-missing {test_dir(name)}`\n")
    return ("# 開發環境說明\n\n- C++17、GoogleTest（已經裝好）。正式程式用 `make` 建置；測試用 `makefile_test`，"
            f"它會自動收集 `{test_dir(name)}/*.cpp`。\n"
            "- 跑測試：`make -f makefile_test test`（只跑某些測試：`make -f makefile_test test ARGS=--gtest_filter=Suite.*`）\n"
            "- 量覆蓋率（行＋分支，gcovr）：`make -f makefile_test coverage`\n")


def tw_task_text(name):
    s = spec(name)
    files = "、".join(f"`{p}`" for p in s["prod"])
    fw = "pytest" if name in PY else "GoogleTest（gtest）"
    return (f"這個專案（{name}）目前沒有單元測試，請幫我補上，最後我會看過才合併：\n"
            f"1. 用 {fw} 在 `{test_dir(name)}/` 寫單元測試，涵蓋 {files} 裡的公開類別與函式，"
            "包含正常情況、邊界條件與錯誤處理；文件（PRD、架構設計）可以參考，但以目前的程式為準。\n"
            "2. 測試要能在目前的程式上全部通過。不要修改正式程式；如果覺得程式本身有 bug，寫在回報裡就好。\n"
            "3. 完成後量測覆蓋率（行與分支），回報數字，並列出還沒涵蓋到、值得補測試的部分。")


def make_tw(name):
    tid = f"tw_{name}"
    ws = os.path.join(WS_DIR, tid)
    shutil.rmtree(ws, ignore_errors=True)
    C.copytree(repo_path(name), ws)
    for rel in (test_dir(name), "acceptance_tests", *DROP):
        p = os.path.join(ws, rel)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    os.makedirs(os.path.join(ws, test_dir(name)), exist_ok=True)
    make_setup_dirs(name, ws)
    if name in CPP:
        write_makefile(name, ws)
    with open(os.path.join(ws, ".coding_agent.md"), "w", encoding="utf-8") as f:
        f.write(coding_notes(name))
    s = spec(name)
    task = {"id": tid, "family": "tw", "source": "devbench", "repo": name, "lang": "python" if name in PY else "cpp",
            "workspace": os.path.relpath(ws, C.DATASET), "task": tw_task_text(name), "test_dir": test_dir(name),
            "prod_files": s["prod"], "cov_sources": s.get("pkg"), "cov_filters": s.get("cov"),
            "mutants": f"mutants/{name}.json", "python": "devbench_venv"}
    return task


def pick_bf_mutants(name, rng, k=3):
    with open(os.path.join(MUTANT_DIR, f"{name}.json"), encoding="utf-8") as f:
        # 只挑單獨植入時「測試正常回報失敗」的（有失敗的測試名稱；當掉或卡住的沒有），組合起來的任務才看得到症狀
        muts = [m for m in json.load(f)["mutants"] if m["killed"] and m.get("failed_tests")]
    by_file = {}
    for m in muts:
        by_file.setdefault(m["file"], []).append(m)
    files = sorted(by_file)
    rng.shuffle(files)
    picked = []
    for fpath in files:                       # 先每個檔案一個
        if len(picked) >= k:
            break
        cands = by_file[fpath]
        picked.append(rng.choice(cands))
    pool = [m for m in muts if m not in picked]
    rng.shuffle(pool)
    for m in pool:                            # 檔案不夠多時，同一檔案但相隔 5 行以上
        if len(picked) >= k:
            break
        if all(m["file"] != p["file"] or abs(m["line"] - p["line"]) > 5 for p in picked):
            picked.append(m)
    return picked


def apply_mutants(ws, muts):
    """依檔案分組，同一檔案的多個 mutant 由後往前（行號大的先）套用；point 的位置是對原始檔算的，
    所以同一檔案每次都重新找變異點（同樣的描述與行號）。"""
    by_file = {}
    for m in muts:
        by_file.setdefault(m["file"], []).append(m)
    for rel, ms in by_file.items():
        path = os.path.join(ws, rel)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        if rel.endswith(".py"):               # Python：全部一次套用（unparse 會改行號）
            pts = M.points_for(rel, src)
            hits = []
            for m in ms:
                hit = next((p for p in pts if p["line"] == m["line"] and p["desc"] == m["desc"] and p["kind"] == m["point"]["kind"]), None)
                if hit is None:
                    raise RuntimeError(f"找不到變異點 {m['id']}")
                hits.append(hit)
            with open(path, "w", encoding="utf-8") as f:
                f.write(M.py_apply_many(src, hits))
            continue
        for m in sorted(ms, key=lambda x: -x["line"]):
            pts = M.points_for(rel, src)
            hit = next((p for p in pts if p["line"] == m["line"] and p["desc"] == m["desc"]
                        and p.get("kind") == m["point"].get("kind")), None)
            if hit is None:
                raise RuntimeError(f"找不到變異點 {m['id']}")
            src = M.apply_for(rel, src, hit)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)


def bf_task_text(name, failing, total):
    cmd = f"python -m pytest -q {test_dir(name)}" if name in PY else "make -f makefile_test test"
    shown = "\n".join(f"- {t}" for t in failing[:6]) + (f"\n- …（共 {len(failing)} 個）" if len(failing) > 6 else "")
    return (f"這個專案（{name}）最近有幾個改動之後，單元測試（`{cmd}`）有 {len(failing)} 個失敗：\n{shown}\n"
            "請找出原因並修正程式，讓測試全部通過。測試本身是對的，不要修改測試；問題可能不只一個、也可能不在同一個檔案。"
            "修完請說明每個問題在哪裡、怎麼修的。")


def make_bf(name, rng, tries=5):
    """最多抽 tries 組：組合後要能編譯、跑得完（不是當掉），而且有測試失敗。"""
    for attempt in range(tries):
        t = _make_bf_once(name, rng)
        if t:
            return t
        print(f"  {name}：第 {attempt + 1} 組不合用，重抽")
    return None


def _make_bf_once(name, rng):
    import tempfile
    tid = f"bf_{name}"
    muts = pick_bf_mutants(name, rng)
    if len(muts) < 2:
        print(f"  {name}：抓得到的 mutant 不夠，略過 bf")
        return None
    ws = os.path.join(WS_DIR, tid)
    shutil.rmtree(ws, ignore_errors=True)
    C.copytree(repo_path(name), ws)
    for rel in ("acceptance_tests", *DROP):
        p = os.path.join(ws, rel)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    make_setup_dirs(name, ws)
    if name in CPP:
        write_makefile(name, ws)
    apply_mutants(ws, muts)
    tmp = tempfile.mkdtemp(prefix=f"sp_bf_{name}_")
    probe = os.path.join(tmp, "ws")
    C.copytree(ws, probe)
    make_setup_dirs(name, probe)
    if name in PY:
        cases, code, out = C.pytest_cases(probe, [test_dir(name)])
    else:
        cases, code, out = C.gtest_cases(probe)
    shutil.rmtree(tmp, ignore_errors=True)
    failing = sorted(k for k, v in cases.items() if v != "passed")
    if code == 0 or not failing:
        print(f"  {name}：組合後測試沒有失敗（或沒有編譯出來），略過 bf\n{out[-500:]}")
        shutil.rmtree(ws, ignore_errors=True)
        return None
    with open(os.path.join(ws, ".coding_agent.md"), "w", encoding="utf-8") as f:
        f.write(coding_notes(name))
    return {"id": tid, "family": "bf", "source": "devbench", "repo": name, "lang": "python" if name in PY else "cpp",
            "workspace": os.path.relpath(ws, C.DATASET), "task": bf_task_text(name, failing, len(cases)),
            "test_dir": test_dir(name), "injected": [{k: m[k] for k in ("id", "file", "line", "desc")} for m in muts],
            "visible_failing": failing, "python": "devbench_venv"}


def build_tasks():
    os.makedirs(TASK_DIR, exist_ok=True)
    rng = random.Random(SEED)
    made = []
    for name in list(PY) + list(CPP):
        for t in (make_tw(name), make_bf(name, rng)):
            if t:
                with open(os.path.join(TASK_DIR, f"{t['id']}.json"), "w", encoding="utf-8") as f:
                    json.dump(t, f, ensure_ascii=False, indent=1)
                made.append(t["id"])
    print("任務：", ", ".join(made))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["mutants", "tasks"])
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    names = [n for n in list(PY) + list(CPP) if not args.only or n in args.only.split(",")]
    if args.cmd == "mutants":
        for n in names:
            build_mutants(n)
    else:
        build_tasks()


if __name__ == "__main__":
    main()
