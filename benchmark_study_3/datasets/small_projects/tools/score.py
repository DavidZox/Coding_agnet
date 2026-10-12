"""小專案任務的計分（run.py 在 job 結束後呼叫；也可以單獨對一個工作區計分）。

    python3 score.py <任務 id> <工作區>            # 印出 JSON
    python3 score.py verify [--only id,...]        # 用參考答案驗證每個任務：tw＝官方測試、bf/fe＝原始程式、ap＝.meta 的參考解
    python3 score.py reference                     # 算 DevBench 官方測試的覆蓋率（寫進 mutants/<repo>.json，tw 的參考值）

- tw（寫測試）：正式程式先還原成原樣（agent 改過的記成違規），只跑 agent 的測試：
  有效性（在原本的程式上通過幾個）→ 只用通過的測試量行／分支覆蓋率 → 逐一套用 mutant，只跑通過的測試，看抓到幾個。
  DevBench 的 mutant 只取「官方單元測試抓得到的」，mutation score 是相對於官方測試；ProjectTest 沒有官方測試，用全部 mutant（絕對值）。
- bf／fe：官方單元＋驗收測試放回去（evals/devbench/evaluate.py，跟前兩次研究同一套），全部通過才算解決；也記錄 agent 有沒有改測試。
- ap：原本的測試檔放回去，Python 跑 pytest、C++ 用 CMake 建置（建置時會跑測試）＋ctest；全部通過才算解決。
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C          # noqa: E402
import mutate as M          # noqa: E402

TASK_DIR = os.path.join(C.DATASET, "tasks")
AIDER_SRC = os.path.join(C.STUDY, "datasets", "source", "polyglot-benchmark")


def load_task(tid):
    with open(os.path.join(TASK_DIR, f"{tid}.json"), encoding="utf-8") as f:
        return json.load(f)


def template(task):
    return os.path.join(C.DATASET, task["workspace"])


# ================================================================ tw
def _agent_tests(task, ws):
    tdir = os.path.join(ws, task["test_dir"])
    files = []
    for dp, dns, fns in os.walk(tdir):
        for fn in fns:
            if (task["lang"] == "python" and fn.endswith(".py") and (fn.startswith("test_") or fn.endswith("_test.py"))) or \
               (task["lang"] == "cpp" and fn.endswith((".cpp", ".cc"))):
                files.append(os.path.relpath(os.path.join(dp, fn), ws))
    return sorted(files)


def _run_tests(task, ws, selected=None, cov=False, fail_fast=False, timeout=180):
    """回傳 (每個測試的結果, exit code, 輸出)。selected：只跑這些（Python 的 nodeid、gtest 的名稱）。"""
    if task["lang"] == "python":
        targets = selected if selected is not None else [task["test_dir"]]
        cases, code, out = C.pytest_cases(ws, targets, extra=["-x"] if fail_fast else [], timeout=timeout)
        return C.junit_to_nodeids(ws, cases), code, out
    args = ""
    if selected is not None:
        args = "--gtest_filter=" + ":".join(selected)
    if fail_fast:
        args = (args + " --gtest_break_on_failure").strip()
    return C.gtest_cases(ws, args=args, cov=cov, timeout=timeout)


def score_tw(task, agent_ws, mutant_limit=None):
    tmp = tempfile.mkdtemp(prefix=f"sp_score_{task['id']}_")
    ws = os.path.join(tmp, "ws")
    try:
        C.copytree(agent_ws, ws, ignore_names=("build_test", "build", ".coverage*", "htmlcov"))
        tpl = template(task)
        # 正式程式還原；agent 改過的記下來
        prod_changed = []
        keep = set(task["prod_files"]) | {"makefile_test", "makefile", "CMakeLists.txt"}
        for rel in sorted(keep):
            src = os.path.join(tpl, rel)
            if not os.path.exists(src):
                continue
            dst = os.path.join(ws, rel)
            if not os.path.exists(dst) or C.file_hashes(tpl, [rel]) != C.file_hashes(ws, [rel]):
                if rel in task["prod_files"]:
                    prod_changed.append(rel)
                shutil.copy2(src, dst)
        tests = _agent_tests(task, ws)
        n_tests = n_bare = 0
        for rel in tests:
            a, b = C.count_assertions(os.path.join(ws, rel))
            n_tests += a
            n_bare += b
        out = {"test_files": tests, "prod_changed": prod_changed, "tests_declared": n_tests, "tests_without_assert": n_bare}
        if not tests:
            out.update(tests_total=0, tests_passed=0, line_cov=0.0, branch_cov=0.0, mut_killed=0, mut_total=_mut_total(task),
                       mut_score=0.0, note="沒有測試檔")
            return out
        C.clean_build(ws)
        cases, code, log = _run_tests(task, ws)
        passed = sorted(k for k, v in cases.items() if v == "passed")
        failed = sorted(k for k, v in cases.items() if v not in ("passed", "skipped"))
        skipped = sorted(k for k, v in cases.items() if v == "skipped")      # 含 xfail（agent 覺得程式有 bug、標成預期失敗的測試）
        out.update(tests_total=len(cases), tests_passed=len(passed), n_failed=len(failed), n_skipped=len(skipped),
                   tests_failed=failed[:30], tests_skipped=skipped[:30],
                   build_error=(log[-1500:] if task["lang"] == "cpp" and not cases else None))
        if not passed:
            out.update(line_cov=0.0, branch_cov=0.0, mut_killed=0, mut_total=_mut_total(task), mut_score=0.0)
            return out
        # 覆蓋率：只用通過的測試
        if task["lang"] == "python":
            cov = C.pytest_coverage(ws, [task["test_dir"]], task["cov_sources"], nodeids=passed)
        else:
            C.clean_build(ws)
            _run_tests(task, ws, selected=passed, cov=True)
            cov = C.gcovr_summary(ws, task["cov_filters"])
            C.clean_build(ws)
        out.update(line_cov=cov.get("line"), branch_cov=cov.get("branch"), cov_detail={k: v for k, v in cov.items() if k != "files"})
        # mutation
        killed, total, detail = _mutation(task, ws, passed, mutant_limit)
        out.update(mut_killed=killed, mut_total=total, mut_score=round(100.0 * killed / total, 1) if total else None,
                   mut_detail=detail)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _mutants(task):
    with open(os.path.join(C.DATASET, task["mutants"]), encoding="utf-8") as f:
        data = json.load(f)
    if task["source"] == "devbench":           # 官方測試抓得到、而且參考解的測試在計分程序裡也穩定抓得到的（verify --fix 標記 unstable）
        return [m for m in data["mutants"] if m["killed"] and not m.get("unstable")]
    return [m for m in data["mutants"] if not m.get("invalid")]


def _mut_total(task):
    return len(_mutants(task))


def _mutation(task, ws, passed, limit=None):
    muts = _mutants(task)
    if limit:
        muts = muts[:limit]
    killed, detail = 0, []
    for m in muts:
        path = os.path.join(ws, m["file"])
        with open(path, encoding="utf-8") as f:
            orig = f.read()
        pts = M.points_for(m["file"], orig)
        # 同一行常有好幾個同樣的突變點（兩個 +、兩個 True）：先用建立突變體時的節點／token 編號找（正式程式已還原成範本，
        # 編號一致）；只用行號＋描述會套到另一個點，官方測試抓得到的突變體就變成抓不到（tw_stocktrends 3 個、tw_xlsx2csv 1 個）
        key = "node" if "node" in m["point"] else ("tok" if "tok" in m["point"] else None)
        hit = next((p for p in pts if key and p.get(key) == m["point"][key] and p["line"] == m["line"] and p["desc"] == m["desc"]), None) \
            or next((p for p in pts if p["line"] == m["line"] and p["desc"] == m["desc"] and p.get("kind") == m["point"].get("kind")), None)
        if hit is None:
            detail.append({"id": m["id"], "status": "missing"})
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(M.apply_for(m["file"], orig, hit))
        try:
            cases, code, log = _run_tests(task, ws, selected=passed, fail_fast=True, timeout=90)
            dead = code != 0
            killed += dead
            detail.append({"id": m["id"], "killed": dead})
        finally:
            with open(path, "w", encoding="utf-8") as f:
                f.write(orig)
    return killed, len(muts), detail


# ================================================================ bf／fe
def score_devbench_suite(task, agent_ws):
    sys.path.insert(0, os.path.join(C.HARNESS, "evals", "devbench"))
    import evaluate as ev                     # noqa: E402
    tmp = tempfile.mkdtemp(prefix=f"sp_score_{task['id']}_")
    ws = os.path.join(tmp, "ws")
    try:
        C.copytree(agent_ws, ws, ignore_names=("build_test",))
        tests_changed = []
        tdir = task.get("test_dir", "unit_tests")
        base = template(task) if task.get("workspace") else ev.repo_dir(task["repo"])   # 範本裡看得到的測試（fe 已拿掉一部分）
        for dp, dns, fns in os.walk(os.path.join(base, tdir)):
            for fn in fns:
                rel = os.path.relpath(os.path.join(dp, fn), base)
                if C.file_hashes(base, [rel]) != C.file_hashes(agent_ws, [rel]):
                    tests_changed.append(rel)
        res = ev.evaluate(task["repo"], ws)
        out = {k: res.get(k) for k in ("unit", "unit_total", "acceptance", "acceptance_total")}
        out["tests_changed"] = tests_changed
        out["resolved"] = bool(res.get("unit_total")) and res.get("unit") == res.get("unit_total") and \
            res.get("acceptance") == res.get("acceptance_total")
        out["unit_tail"] = (res.get("unit_tail") or "")[-800:]
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================================ ap
def score_ap(task, agent_ws):
    tmp = tempfile.mkdtemp(prefix=f"sp_score_{task['id']}_")
    ws = os.path.join(tmp, "ws")
    try:
        C.copytree(agent_ws, ws, ignore_names=("build",))
        tpl = template(task)
        changed = []
        for t in task["test_files"] + (["CMakeLists.txt"] if task["lang"] == "cpp" else []):
            src = os.path.join(tpl, t)
            dst = os.path.join(ws, t)
            if os.path.isdir(src):
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
            else:
                if C.file_hashes(tpl, [t]) != C.file_hashes(ws, [t]):
                    changed.append(t)
                shutil.copy2(src, dst)
        if task["lang"] == "python":
            cases, code, log = C.pytest_cases(ws, ["."])
            passed = sum(1 for v in cases.values() if v == "passed")
            return {"tests_total": len(cases), "tests_passed": passed, "resolved": code == 0 and passed == len(cases) > 0,
                    "tests_changed": changed, "tail": log[-600:]}
        code1, log1 = C.run(["cmake", "-S", ".", "-B", "build"], ws, timeout=180)
        code2, log2 = C.run(["cmake", "--build", "build", "-j", "4"], ws, timeout=300)
        code3, log3 = C.run(["ctest", "--test-dir", "build", "--output-on-failure"], ws, timeout=180)
        ok = code1 == 0 and code2 == 0 and code3 == 0
        return {"resolved": ok, "tests_changed": changed, "tail": (log2 + log3)[-800:]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def score(task, ws, **kw):
    if task["family"] == "tw":
        return score_tw(task, ws, **kw)
    if task["family"] in ("bf", "fe"):
        return score_devbench_suite(task, ws)
    if task["family"] == "ap":
        return score_ap(task, ws)
    raise ValueError(task["family"])


# ================================================================ 驗證（參考答案要拿滿分）
def reference_ws(task, dst):
    """參考答案：tw＝範本＋官方測試（DevBench）；bf＝原始的參考實作；ap＝範本＋.meta 的參考解。"""
    sys.path.insert(0, os.path.join(C.HARNESS, "evals", "devbench"))
    C.copytree(template(task), dst)
    if task["family"] == "tw" and task["source"] == "devbench":
        import evaluate as ev                 # noqa: E402
        src = os.path.join(ev.repo_dir(task["repo"]), task["test_dir"])
        shutil.copytree(src, os.path.join(dst, task["test_dir"]), dirs_exist_ok=True)
    elif task["family"] in ("bf", "fe"):
        import evaluate as ev                 # noqa: E402
        for rel in task.get("ref_files") or sorted({m["file"] for m in task.get("injected", [])}):
            shutil.copy2(os.path.join(ev.repo_dir(task["repo"]), rel), os.path.join(dst, rel))
    elif task["family"] == "ap":
        lang = "python" if task["lang"] == "python" else "cpp"
        meta = os.path.join(AIDER_SRC, lang, "exercises", "practice", task["repo"], ".meta")
        stem = task["repo"].replace("-", "_")
        for fn in os.listdir(meta):
            if fn.startswith("example"):
                ext = fn.split(".", 1)[1]
                shutil.copy2(os.path.join(meta, fn), os.path.join(dst, f"{stem}.{ext}"))
    return dst


def _mark_unstable(task, res):
    """參考解（官方測試）在計分程序裡抓不到的突變體標成 unstable（建立時的「抓到」多半是當掉或逾時之類的偶發結果），之後不計分。"""
    surv = {d["id"] for d in res.get("mut_detail") or [] if d.get("killed") is False}
    if not surv:
        return []
    path = os.path.join(C.DATASET, task["mutants"])
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for m in data["mutants"]:
        if m["id"] in surv:
            m["unstable"] = True
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return sorted(surv)


def verify(only=None, fix=False):
    rows = []
    for fn in sorted(os.listdir(TASK_DIR)):
        tid = fn[:-5]
        if only and tid not in only:
            continue
        task = load_task(tid)
        if task["family"] == "tw" and task["source"] != "devbench":
            continue                           # ProjectTest 沒有參考測試
        tmp = tempfile.mkdtemp(prefix="sp_verify_")
        try:
            ws = reference_ws(task, os.path.join(tmp, "ws"))
            res = score(task, ws)
            ok = (res.get("mut_score") == 100.0 and res.get("tests_passed") == res.get("tests_total")) if task["family"] == "tw" \
                else res.get("resolved")
            rows.append((tid, ok, {k: res.get(k) for k in ("tests_passed", "tests_total", "line_cov", "branch_cov", "mut_score",
                                                             "unit", "unit_total", "acceptance", "acceptance_total") if k in res}))
            print(("✅" if ok else "❌"), tid, rows[-1][2], flush=True)
            if fix and task["family"] == "tw" and not ok and res.get("tests_passed") == res.get("tests_total"):
                print("   標成 unstable：", _mark_unstable(task, res), flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return rows


def main():
    if sys.argv[1] == "verify":
        only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
        verify(only, fix="--fix" in sys.argv)
        return
    task = load_task(sys.argv[1])
    print(json.dumps(score(task, sys.argv[2]), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
