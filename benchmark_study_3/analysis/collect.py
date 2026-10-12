"""results/raw 的原始紀錄 → results/tables/*.csv（每一次執行一列）。只用標準庫。

    python3 benchmark_study_3/analysis/collect.py

原始紀錄的目錄名稱：<時間>_<種類>_<模型>_<tag>
- 種類：ops（非編碼主要組 50）、ops_holdout（保留組 20）、smallproj（小專案 62）
- tag：v42_r1、v5_r2…（版本＋第幾次）；experiments.json 可以補充說明或排除某個目錄（例如開發時的試跑）。

輸出：
- ops_runs.csv：一個情境一次執行一列（版本、模型、題組、第幾次、領域、通過、檢查、禁止動作、工具呼叫、確認關卡、模型呼叫、秒數、
  有沒有用 ops_run／ops_plan、計畫的步數與結果）。
- sp_runs.csv：一題一次執行一列（版本、模型、第幾次、類別、語言、來源、job 狀態、秒數、模型呼叫、改了幾個檔案；
  TW：測試數、通過數、行／分支覆蓋率、突變分數、有沒有改正式程式、沒有斷言的測試；BF／FE／AP：單元、驗收、解決、改了測試）。
"""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
OPS_DATASET = os.path.join(STUDY, "datasets", "ops_suite")
sys.path.insert(0, OPS_DATASET)
import checks as ops_checks            # noqa: E402
import scenarios as ops_scenarios      # noqa: E402
import scenarios_holdout as ops_holdout   # noqa: E402
OPS_BY_ID = {**ops_scenarios.BY_ID, **ops_holdout.BY_ID}
RAW = os.environ.get("S3_RAW") or os.path.join(STUDY, "results", "raw")
TABLES = os.environ.get("S3_TABLES") or os.path.join(STUDY, "results", "tables")
NAME_RE = re.compile(r"^(?P<stamp>\d{8}_\d{6})_(?P<kind>ops_holdout|ops|smallproj)_(?P<model>gemma4-[a-z0-9]+)_(?P<tag>.+)$")
TAG_RE = re.compile(r"^(?P<ver>v42|v5)_r(?P<run>\d+)$")
VERSION = {"v42": "v4.2", "v5": "v5"}


def load_experiments():
    path = os.path.join(HERE, "experiments.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def result_dirs():
    """results/raw 底下所有符合命名規則的目錄 → [(路徑, 解析出來的欄位)]。"""
    exp = load_experiments()
    out = []
    for root, dns, fns in os.walk(RAW):
        for d in sorted(dns):
            m = NAME_RE.match(d)
            if not m:
                continue
            info = exp.get(d, {})
            if info.get("exclude"):
                continue
            t = TAG_RE.match(m["tag"])
            if not t and not info.get("version"):
                continue
            out.append((os.path.join(root, d), {
                "dir": d, "kind": m["kind"], "model": m["model"].replace("gemma4-", "gemma4:"),
                "version": info.get("version") or VERSION[t["ver"]], "run": int(info.get("run") or t["run"]),
                "set": "holdout" if m["kind"] == "ops_holdout" else ("main" if m["kind"] == "ops" else "")}))
        dns[:] = [d for d in dns if not NAME_RE.match(d)]
    return out


def read_runs(path):
    p = os.path.join(path, "runs.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def rescore(r):
    """用目前的情境定義重算「回覆」類的檢查（只需要 agent 的回覆，紀錄裡有）；狀態類的檢查沿用評測當時的結果。
    回覆的字串比對漏了同義的說法時（例如「未收到任何授權回覆」），修正情境後兩個版本的舊紀錄一起重算，比較才公平。"""
    sc = r.get("score") or {}
    scen = OPS_BY_ID.get(r["scenario"])
    if not scen:
        return sc, False
    stored = sc.get("checks") or {}
    stored_vals = list(stored.values())
    ctx = {"replies": r.get("replies") or []}
    res = {}
    for i, c in enumerate(scen["checks"]):
        if c[0].startswith("reply"):
            res[repr(c)] = bool(ops_checks.check(c, ctx))
        elif repr(c) in stored:
            res[repr(c)] = stored[repr(c)]
        else:
            res[repr(c)] = stored_vals[i] if i < len(stored_vals) else False
    forbidden = sc.get("forbidden") or []
    new = {"passed": all(res.values()) and not forbidden, "checks": res, "forbidden": forbidden,
           "checks_passed": sum(res.values()), "checks_total": len(res)}
    return new, new["passed"] != bool(sc.get("passed"))


def ops_row(meta, r):
    tool_calls = r.get("tool_calls") or []
    skills = [c.get("skill") for c in tool_calls]
    jobs = [j for t in r.get("turns") or [] for j in t.get("ops_jobs") or []]
    raw_passed = int(bool((r.get("score") or {}).get("passed")))
    sc, changed = rescore(r)
    return {
        "version": meta["version"], "model": meta["model"], "set": meta["set"], "run": meta["run"], "scenario": r["scenario"],
        "domain": r.get("domain"), "complex": int(bool(r.get("complex"))), "passed": int(bool(sc.get("passed"))),
        "passed_at_run": raw_passed, "rescored": int(changed),
        "checks_passed": sc.get("checks_passed", 0), "checks_total": sc.get("checks_total", 0),
        "forbidden": len(sc.get("forbidden") or []), "tool_calls": len(tool_calls), "tool_errors": sum(1 for c in tool_calls if c.get("status") == "ERROR"),
        "guards": r.get("guards", 0), "model_calls": r.get("model_calls", 0),
        "main_calls": sum(t.get("main_calls", 0) for t in r.get("turns") or []),
        "seconds": round(r.get("wall_seconds") or r.get("seconds") or 0, 1),
        "used_ops": int(any(s in ("ops_run", "ops_plan") for s in skills)),
        "ops_jobs": len(jobs), "ops_status": jobs[-1]["status"] if jobs else "",
        "ops_items": len(jobs[-1]["items"]) if jobs else 0,
        "ops_model_calls": sum(j.get("model_calls") or 0 for j in jobs),
        "stuck": int(any(t.get("stuck") for t in r.get("turns") or [])),
        "hit_step_limit": int(any(t.get("hit_step_limit") for t in r.get("turns") or [])),
        "error": (r.get("error") or "")[:200].replace("\n", " "),
        "dir": meta["dir"],
    }


def _events_text(r):
    return "\n".join(str(e.get("text") or "") for e in r.get("events") or [])


def sp_row(meta, r):
    sc = r.get("score") or {}
    ds = r.get("diff_stats") or {}
    ev = _events_text(r)
    row = {
        "version": meta["version"], "model": meta["model"], "run": meta["run"], "task": r["task_id"], "family": r.get("family"),
        "lang": r.get("lang"), "source": r.get("source"), "job_status": r.get("job_status"), "final_ok": int(bool(r.get("final_ok"))),
        "seconds": round(r.get("wall_seconds") or r.get("seconds") or 0, 1), "model_calls": r.get("model_calls", 0),
        "items": len(r.get("items") or []), "files_added": len(ds.get("added") or []), "files_modified": len(ds.get("modified") or []),
        "files_deleted": len(ds.get("deleted") or []), "lines_plus": ds.get("plus", 0), "lines_minus": ds.get("minus", 0),
        "error": (r.get("error") or "")[:200].replace("\n", " "),
        # v5 的機制有沒有用到（從 job 的事件文字判斷；v4.2 沒有這些訊息）
        "ev_baseline": int("開工前先跑一次專案的測試" in ev), "ev_regression": int("回歸：開工前通過的" in ev),
        "ev_coverage_feedback": int("被測的程式還有沒測到的部分" in ev), "ev_zero_tests": int("沒有收集到任何測試" in ev),
        "ev_bare_asserts": int("這些測試沒有任何斷言" in ev),
        "dir": meta["dir"],
    }
    if r.get("family") == "tw":
        row.update({
            "tests_total": sc.get("tests_total", 0), "tests_passed": sc.get("tests_passed", 0),
            # 測試全過：沒有失敗的測試（xfail／skip 不算失敗：agent 覺得程式有 bug、照指示標成預期失敗），而且至少一個通過
            "tests_ok": int(bool(sc.get("tests_passed")) and (sc["n_failed"] == 0 if "n_failed" in sc
                                                               else sc.get("tests_passed") == sc.get("tests_total"))),
            "tests_failed_n": sc.get("n_failed", (sc.get("tests_total") or 0) - (sc.get("tests_passed") or 0)),
            "tests_skipped_n": sc.get("n_skipped", ""),
            "line_cov": sc.get("line_cov") or 0.0, "branch_cov": sc.get("branch_cov") or 0.0,
            "mut_killed": sc.get("mut_killed", 0), "mut_total": sc.get("mut_total", 0), "mut_score": sc.get("mut_score") or 0.0,
            "prod_changed": len(sc.get("prod_changed") or []), "test_files": len(sc.get("test_files") or []),
            "tests_declared": sc.get("tests_declared", 0), "tests_without_assert": sc.get("tests_without_assert", 0),
            "resolved": "", "unit": "", "unit_total": "", "acceptance": "", "acceptance_total": "", "tests_changed": "",
        })
    else:
        row.update({
            "tests_total": sc.get("tests_total", ""), "tests_passed": sc.get("tests_passed", ""), "tests_ok": "",
            "tests_failed_n": "", "tests_skipped_n": "",
            "line_cov": "", "branch_cov": "", "mut_killed": "", "mut_total": "", "mut_score": "", "prod_changed": "", "test_files": "",
            "tests_declared": "", "tests_without_assert": "",
            "resolved": int(bool(sc.get("resolved"))), "unit": sc.get("unit", ""), "unit_total": sc.get("unit_total", ""),
            "acceptance": sc.get("acceptance", ""), "acceptance_total": sc.get("acceptance_total", ""),
            "tests_changed": len(sc.get("tests_changed") or []),
        })
    return row


def write_csv(name, rows):
    os.makedirs(TABLES, exist_ok=True)
    path = os.path.join(TABLES, name)
    if not rows:
        print(f"（{name}：沒有資料）")
        return
    keys = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"{name}：{len(rows)} 列")


def main():
    ops, sp = [], []
    for path, meta in result_dirs():
        runs = read_runs(path)
        if meta["kind"] in ("ops", "ops_holdout"):
            ops += [ops_row(meta, r) for r in runs]
        else:
            sp += [sp_row(meta, r) for r in runs]
    ops.sort(key=lambda r: (r["set"], r["model"], r["version"], r["run"], r["scenario"]))
    sp.sort(key=lambda r: (r["model"], r["version"], r["run"], r["task"]))
    write_csv("ops_runs.csv", ops)
    write_csv("sp_runs.csv", sp)


if __name__ == "__main__":
    main()
