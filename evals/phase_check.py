"""每個階段結束時的持續驗證：跑一組固定的檢查，跟 evals/baselines/ 的基準逐項比，列出退步、變慢、禁止動作。

    python3 evals/phase_check.py                  # 離線（約 5 分鐘）：技能、主對話、提煉、維運、數據分析的自我測試
    python3 evals/phase_check.py --live           # 再加上要容器／沙盒、不呼叫模型的（約 10 分鐘）：技能接沙盒、數據技能實機、數據分析回歸
    python3 evals/phase_check.py --model          # 再加上真模型（約 1 小時）：提煉（26b、e4b）、主對話（e4b 11 個情境 ×3）、
                                                  #   工作流沙盒（26b、e4b 各 7 個案例 ×2）、維運（26b 70 個）
    python3 evals/phase_check.py --live --model   # 全部
    python3 evals/phase_check.py --only ops,extract --model     # 只跑某幾項（名稱見 summary.md 的第一欄括號）
    python3 evals/phase_check.py --compare <結果目錄> [...]      # 不跑，只拿已經跑好的結果跟基準比（維運、主對話、提煉、數據分析回歸）
    python3 evals/phase_check.py --save-baseline <結果目錄> [...]  # 階段 commit 之後，用這幾次的結果更新基準（同一種的多個目錄合成一份）
    python3 evals/phase_check.py --save-baseline <phase_check 目錄> --only skills,workflow    # 只更新這幾項（其他的基準不動）

結果在 evals/results/<時間>_phase_check/：summary.md（每一項一行：結果、基準、判定；要注意的逐項列出）、summary.json。
容器與沙盒用完就關；logs/analysis_settings.json 測試前後比對，有變就還原。基準的格式與來源見 evals/baselines/README.md。"""
import argparse
import glob
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
BASE = os.path.join(HERE, "baselines")
PY = sys.executable
SETTINGS = os.path.join(PROJECT, "logs", "analysis_settings.json")

OFFLINE = [("skills", "技能自我測試", ["evals/skills/selftest.py"]),
           ("chat_selftest", "主對話自我測試", ["evals/chat/selftest.py"]),
           ("extract_selftest", "提煉自我測試", ["evals/chat/extract_selftest.py"]),
           ("ops_selftest", "維運自我測試", ["evals/ops/selftest.py"]),
           ("analysis_selftest", "數據分析自我測試", ["evals/analysis/selftest.py"]),
           ("workflow_selftest", "工作流自我測試", ["evals/workflow/selftest.py"])]
TEST_CONTAINER = "cah_analysis_test"
LIVE_DATA = ["/workspace/experiment_logs/gen/s1/gen_s1_005", "/workspace/experiment_logs/exp_5090_overheat"]
CHAT_SCENARIOS = ("fleet_battery,fleet_followup,followup_in_context,cross_session_recall,compare_two_archives,count_from_script,"
                  "current_state_rerun,memory_stale_state,error_recovery,guard_dispatch,containers_basic")
EXTRACT_MODELS = ("gemma4:26b", "gemma4:e4b")
WORKFLOW_MODELS = ("gemma4:26b", "gemma4:e4b")
OPS_MODEL, CHAT_MODEL = "gemma4:26b", "gemma4:e4b"
_COUNTS = re.compile(r"(\d+)/(\d+) 通過(?:，(\d+) 個略過)?")
_REPORT = re.compile(r"報表：(\S+)/report\.md")


# ================================================================ 執行
def run(cmd, env=None, timeout=7200):
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    e.update(env or {})
    try:
        p = subprocess.run(cmd, cwd=PROJECT, env=e, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as ex:
        return -1, f"逾時（{timeout} 秒）：{(ex.stdout or '')[-500:] if isinstance(ex.stdout, str) else ''}"


def counts(text):
    m = None
    for m in _COUNTS.finditer(text or ""):
        pass
    if not m:
        return None
    return {"passed": int(m.group(1)), "total": int(m.group(2)), "skipped": int(m.group(3) or 0),
            "failed": [ln.strip() for ln in (text or "").splitlines() if ln.startswith("❌")][:20]}


def report_dir(text):
    m = None
    for m in _REPORT.finditer(text or ""):
        pass
    return m.group(1) if m else None


def docker(*args, timeout=60):
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None


def container_exists(name):
    r = docker("inspect", name, "--format", "{{.State.Running}}")
    return r is not None and r.returncode == 0


def selftest(key, title, script, env=None, timeout=1800):
    t0 = time.time()
    rc, out = run([PY, *script], env=env, timeout=timeout)
    c = counts(out)
    return {"key": key, "title": title, "kind": "selftest", "result": c, "seconds": round(time.time() - t0),
            "error": None if c else out[-800:]}


def suite_offline(only):
    return [selftest(k, t, s) for k, t, s in OFFLINE if not only or k in only]


def suite_live(only):
    res = []
    want = lambda k: not only or k in only   # noqa: E731
    if want("skills_sandbox"):
        rc, out = run([PY, "evals/ops/dataset/sandbox/sandbox.py", "up"], timeout=1800)
        r = selftest("skills_sandbox", "調度技能接沙盒（RMF_TEST_SANDBOX=1）", ["evals/skills/selftest.py", "rmf"], env={"RMF_TEST_SANDBOX": "1"})
        docker("stop", "cah_ops_dind")
        res.append(r if rc == 0 else dict(r, error=f"沙盒起不來：{out[-400:]}"))
    if want("containers_sandbox"):
        if container_exists("cah_dev_dind"):
            env = {"OPS_SANDBOX_DIND": "cah_dev_dind", "OPS_SANDBOX_PORT": "23751"}
            run([PY, "evals/ops/dataset/sandbox/sandbox.py", "up"], env=env, timeout=1800)
            res.append(selftest("containers_sandbox", "容器技能接開發用沙盒", ["evals/skills/selftest.py", "containers"]))
            docker("stop", "cah_dev_dind")
        else:
            res.append({"key": "containers_sandbox", "title": "容器技能接開發用沙盒", "kind": "selftest", "result": None, "skipped": "沒有 cah_dev_dind"})
    need_tc = [k for k in ("data_live", "tools_live", "analysis_regression") if want(k)]
    if need_tc:
        if not container_exists(TEST_CONTAINER):
            for k in need_tc:
                res.append({"key": k, "title": k, "kind": "skip", "skipped": f"沒有測試容器 {TEST_CONTAINER}"})
            return res
        docker("start", TEST_CONTAINER)
        time.sleep(2)
        try:
            if want("data_live"):
                res.append(selftest("data_live", "數據技能接測試容器", ["evals/skills/selftest.py", "data"]))
            if want("tools_live"):
                for data in LIVE_DATA:
                    t0 = time.time()
                    rc, out = run([PY, "evals/analysis/tools_live.py", "--container", TEST_CONTAINER, "--data", data], timeout=1800)
                    res.append({"key": f"tools_live:{os.path.basename(data)}", "title": f"數據技能實機（{os.path.basename(data)}）", "kind": "selftest",
                                "result": counts(out), "seconds": round(time.time() - t0), "error": None if counts(out) else out[-600:]})
            if want("analysis_regression"):
                res += analysis_regression()
        finally:
            docker("stop", TEST_CONTAINER)
    return res


def analysis_regression():
    """數據分析的回歸（不呼叫模型）：產生器 s1／s2／s3 各 1 次、這台的實錄 14 份 ×2（加產物穩定性與時間的根據）。test_data 不在就略過。"""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = []
    for s in ("s1", "s2", "s3"):
        cases = os.path.join(PROJECT, "test_data", "recordings", "gen", s, "cases.json")
        if not os.path.exists(cases):
            out.append({"key": f"analysis:gen_{s}", "title": f"數據分析回歸 gen_{s}", "kind": "skip", "skipped": "沒有 test_data"})
            continue
        d = os.path.join("evals", "results", f"analysis_phase_{stamp}_gen_{s}")
        run([PY, "evals/analysis/regression.py", "--run", "--runs", "1", "--cases-file", cases, "--container", TEST_CONTAINER, "--out", d,
             "--title", f"phase_check {s}"], timeout=3600)
        out.append(analysis_result(f"gen_{s}", os.path.join(PROJECT, d)))
    tool = os.path.join(PROJECT, "test_data", "tools", "run_regression.py")
    if os.path.exists(tool):
        d = os.path.join(PROJECT, "evals", "results", f"analysis_phase_{stamp}_real")
        run([PY, tool, "--run", "--runs", "2", "--container", TEST_CONTAINER, "--data-root", "/workspace/experiment_logs", "--out", d], timeout=3600)
        for name, script in (("stability.txt", "stability.py"), ("fact_check.txt", "fact_check.py")):
            rc, txt = run([PY, os.path.join("test_data", "tools", script), os.path.join(d, "runs.json")], timeout=600)
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(txt)
        out.append(analysis_result("real", d))
    return out


def suite_model(only):
    res = []
    want = lambda k: not only or k in only   # noqa: E731
    if want("extract"):
        for model in EXTRACT_MODELS:
            rc, out = run([PY, "evals/extract/run.py", "--model", model, "--tag", "phase"], timeout=3600)
            res.append(extract_result(report_dir(out), model) if report_dir(out) else
                       {"key": f"extract:{model}", "title": f"提煉（{model}）", "kind": "extract", "error": out[-600:]})
    if want("chat"):
        rc, out = run([PY, "evals/chat/run.py", "--modes", "harness", "--runs", "3", "--only", CHAT_SCENARIOS, "--model", CHAT_MODEL,
                       "--tag", "phase"], timeout=7200)
        res.append(chat_result([report_dir(out)]) if report_dir(out) else {"key": "chat", "title": "主對話", "kind": "chat", "error": out[-600:]})
    if want("workflow"):
        try:
            for model in WORKFLOW_MODELS:
                rc, out = run([PY, "evals/workflow/sandbox.py", "--model", model, "--runs", "2", "--tag", "phase"], timeout=3600)
                res.append(workflow_result(report_dir(out), model) if report_dir(out) else
                           {"key": f"workflow:{model}", "title": f"工作流沙盒（{model}）", "kind": "workflow", "error": out[-600:]})
        finally:
            docker("stop", "cah_ops_dind")
    if want("ops"):
        try:
            rc, out = run([PY, "evals/ops/run.py", "--model", OPS_MODEL, "--set", "all", "--tag", "phase"], timeout=3 * 3600)
        finally:
            docker("stop", "cah_ops_dind")
        res.append(ops_result([report_dir(out)]) if report_dir(out) else {"key": "ops", "title": "維運", "kind": "ops", "error": out[-600:]})
    return res


# ================================================================ 讀結果
def _jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def ops_stats(dirs):
    """每個情境：runs、passed、forbidden、每次的秒數（中位數）。"""
    per = {}
    for d in dirs:
        for r in _jsonl(os.path.join(d, "runs.jsonl")):
            s = per.setdefault(r["scenario"], {"runs": 0, "passed": 0, "forbidden": 0, "seconds": []})
            s["runs"] += 1
            s["passed"] += int(bool(r["score"]["passed"]))
            s["forbidden"] += int(bool(r["score"]["forbidden"]))
            s["seconds"].append(r.get("wall_seconds") or r.get("seconds") or 0)
    for s in per.values():
        s["median_s"] = round(statistics.median(s["seconds"]), 1) if s["seconds"] else 0
        del s["seconds"]
    return per


def ops_result(dirs):
    return {"key": "ops", "title": f"維運（{OPS_MODEL}，主要 50＋保留 20）", "kind": "ops", "dirs": dirs, "per": ops_stats(dirs)}


def chat_result(dirs):
    dirs = [dirs] if isinstance(dirs, str) else dirs
    per = {}
    for d in dirs:
        for r in _jsonl(os.path.join(d, "runs.jsonl")):
            s = per.setdefault(r["scenario"], {"runs": 0, "passed": 0})
            s["runs"] += 1
            s["passed"] += int(bool(r.get("passed")))
    return {"key": "chat", "title": f"主對話（{CHAT_MODEL}，{len(per)} 個情境）", "kind": "chat", "dirs": dirs, "per": per}


def workflow_result(d, model=None):
    """工作流的沙盒測試（evals/workflow/sandbox.py）：每個案例的次數、通過（情境的檢查＋結束的狀態）、禁止動作、秒數中位數、判斷點的模型呼叫。"""
    per = {}
    for r in _jsonl(os.path.join(d, "runs.jsonl")):
        model = model or r.get("model")
        s = per.setdefault(r["case"], {"runs": 0, "passed": 0, "forbidden": 0, "model_calls": 0, "seconds": []})
        s["runs"] += 1
        s["passed"] += int(bool(r.get("passed")))
        s["forbidden"] += int(bool((r.get("score") or {}).get("forbidden")))
        s["model_calls"] += int(r.get("model_calls") or 0)
        s["seconds"].append(r.get("wall_seconds") or 0)
    for s in per.values():
        s["median_s"] = round(statistics.median(s["seconds"]), 1) if s["seconds"] else 0
        del s["seconds"]
    return {"key": f"workflow:{model}", "title": f"工作流沙盒（{model}，{len(per)} 個案例）", "kind": "workflow", "model": model,
            "dirs": [d], "per": per}


def extract_result(d, model=None):
    per = {}
    for r in _jsonl(os.path.join(d, "runs.jsonl")):
        model = model or r.get("model")
        s = r["score"]
        per[r["case"]] = {"found": s["found"], "total": s["total"], "extra": len(s["extra"]), "count_ok": s["count_ok"],
                          "seconds": r.get("recall_seconds") if r["case"].startswith("recall") else r.get("summary_seconds")}
    return {"key": f"extract:{model}", "title": f"提煉（{model}）", "kind": "extract", "model": model, "dirs": [d], "per": per}


def analysis_result(name, d):
    """數據分析回歸：每份數據的評分項目（時間線、Topic 類別、用詞、時間有根據、重點涵蓋…，scorecard.json）；實錄另有穩定性與時間的根據。"""
    res = {"key": f"analysis:{name}", "title": f"數據分析回歸（{name}）", "kind": "analysis", "dirs": [d], "per": {}}
    try:
        with open(os.path.join(d, "scorecard.json"), encoding="utf-8") as f:
            card = json.load(f)
    except (OSError, ValueError) as e:
        res["error"] = f"讀不到 scorecard.json：{e}"
        return res
    keys = ("timeline", "tags", "clean", "grounded", "covered", "no_event")
    for r in card.get("results") or []:
        s = res["per"].setdefault(r["case"], {"runs": 0, "done": 0})
        s["runs"] += 1
        s["done"] += int(r.get("status") == "done")
        for k in keys:
            if k in r:                                   # 只記有評的項目：[過了幾次, 評了幾次]（實錄沒有 Topic 類別的評分）
                got = s.setdefault(k, [0, 0])
                got[0] += int(bool(r[k]))
                got[1] += 1
    for name_, pat in (("stability.txt", r"程式產物每次相同 (\d+)/(\d+)"), ("fact_check.txt", r"程式整理的 (\d+)/(\d+) 個時間沒有根據")):
        p = os.path.join(d, name_)
        if os.path.exists(p):
            m = re.search(pat, open(p, encoding="utf-8").read())
            if m:
                res[name_.split(".")[0]] = [int(m.group(1)), int(m.group(2))]
    return res


def classify(d):
    """結果目錄是哪一種（--compare／--save-baseline 用）。"""
    base = os.path.basename(d.rstrip("/"))
    if base.endswith("_phase_check"):
        return "phase_check"
    if "_ops_" in base:
        return "ops"
    if "_extract_" in base:
        return "extract"
    if "_workflow_sandbox_" in base:
        return "workflow"
    if base.startswith("analysis_"):
        return "analysis"
    p = os.path.join(d, "runs.jsonl")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            first = json.loads(f.readline() or "{}")
        if "mode" in first and "scenario" in first:
            return "chat"
    return None


def from_dirs(dirs):
    """結果目錄 → 比對用的結果：同一種的維運、主對話目錄合成一份；phase_check 的目錄讀它的 summary.json（自我測試的數字也在裡面）。"""
    groups = {}
    for d in dirs:
        groups.setdefault(classify(d), []).append(os.path.abspath(d))
    res = []
    for d in groups.get("phase_check", []):
        with open(os.path.join(d, "summary.json"), encoding="utf-8") as f:
            for r in json.load(f):
                if r["kind"] == "ops":
                    groups.setdefault("ops", []).extend(r.get("dirs") or [])
                elif r["kind"] == "chat":
                    groups.setdefault("chat", []).extend(r.get("dirs") or [])
                else:
                    res.append(r)
    if groups.get("ops"):
        res.append(ops_result(groups["ops"]))
    if groups.get("chat"):
        res.append(chat_result(groups["chat"]))
    for d in groups.get("extract", []):
        res.append(extract_result(d))
    for d in groups.get("workflow", []):
        res.append(workflow_result(d))
    for d in groups.get("analysis", []):
        name = os.path.basename(d.rstrip("/")).split("_")[-1]
        name = f"gen_{name}" if name.startswith("s") else name
        res.append(analysis_result(name, d))
    if groups.get(None):
        print(f"看不出是哪一種的結果目錄（略過）：{groups[None]}")
    return res


# ================================================================ 基準
def load_baseline(name):
    p = os.path.join(BASE, f"{name}.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def compare(r):
    """回傳 (結果文字, 基準文字, 判定, [要注意的])。判定：✅ 沒有退步／⚠️ 有要注意的／❌ 執行失敗或測試沒過。"""
    if r.get("skipped"):
        return "略過", "—", "⏭️", [r["skipped"]]
    if r.get("error"):
        return "執行失敗", "—", "❌", [r["error"][-300:]]
    kind = r["kind"]
    if kind == "selftest":
        c = r["result"]
        base = (load_baseline("offline") or {}).get(r["key"])
        notes = [f"沒過：{x}" for x in c["failed"]]
        if base and c["passed"] < base["passed"]:
            notes.append(f"通過的比基準少（{c['passed']} < {base['passed']}）：測試被拿掉了，或環境少了東西而略過")
        text = f"{c['passed']}/{c['total']}" + (f"（{c['skipped']} 略過）" if c["skipped"] else "")
        return text, (f"{base['passed']}/{base['total']}" if base else "（沒有基準）"), ("❌" if c["passed"] < c["total"] else "⚠️" if notes else "✅"), notes
    if kind == "ops":
        return compare_ops(r)
    if kind == "chat":
        return compare_chat(r)
    if kind == "extract":
        return compare_extract(r)
    if kind == "analysis":
        return compare_analysis(r)
    if kind == "workflow":
        return compare_workflow(r)
    return "—", "—", "?", []


def compare_ops(r):
    base = load_baseline(f"ops_{OPS_MODEL.replace(':', '-')}") or {}
    ref = base.get("current", {}).get("per", {})
    per = r["per"]
    notes = []
    for sc, s in sorted(per.items()):
        b = ref.get(sc)
        if s["forbidden"]:
            notes.append(f"{sc}：禁止動作 {s['forbidden']} 次")
        if b:
            rate_b = b["passed"] / b["runs"]
            rate = s["passed"] / s["runs"]
            # 只跑一次：基準大多會過（≥3/4）的這次沒過才列；跑好幾次：通過率比基準低超過 1/3 才列（模型有隨機性，單次的差別多半是波動）
            if (s["runs"] == 1 and s["passed"] == 0 and rate_b >= 0.75) or (s["runs"] > 1 and rate + 0.34 < rate_b):
                notes.append(f"{sc}：{s['passed']}/{s['runs']} 過（基準 {b['passed']}/{b['runs']}）")
            if s["median_s"] > max(2 * b["median_s"], b["median_s"] + 30):
                notes.append(f"{sc}：變慢 {s['median_s']} 秒（基準中位數 {b['median_s']} 秒）")
        else:
            notes.append(f"{sc}：基準裡沒有這個情境（新情境）")
    def tot(p, holdout):
        rs = [s for k, s in p.items() if k.startswith("ho_") == holdout]
        return sum(s["passed"] for s in rs), sum(s["runs"] for s in rs)
    mp, mr = tot(per, False)
    hp, hr = tot(per, True)
    text = f"主要 {mp}/{mr}、保留 {hp}/{hr}；禁止動作 {sum(s['forbidden'] for s in per.values())} 次"
    bt = base.get("current", {}).get("totals")
    btxt = (f"主要 {'、'.join(map(str, bt['main']))}／50、保留 {'、'.join(map(str, bt['holdout']))}／20（{base['current'].get('label', '')}）"
            if bt else "（沒有基準）")
    single_run = all(s["runs"] == 1 for s in per.values())
    if bt and single_run and (mp < min(bt["main"]) or hp < min(bt["holdout"])):
        notes.insert(0, f"總分低於基準的最低分（主要 {min(bt['main'])}、保留 {min(bt['holdout'])}）")
    return text, btxt, ("⚠️" if notes else "✅"), notes


def compare_chat(r):
    base = (load_baseline(f"chat_{CHAT_MODEL.replace(':', '-')}") or {}).get("per", {})
    notes = []
    for sc, s in sorted(r["per"].items()):
        b = base.get(sc)
        if not b:
            notes.append(f"{sc}：基準裡沒有")
        elif s["passed"] / s["runs"] + 0.34 < b["passed"] / b["runs"]:
            notes.append(f"{sc}：{s['passed']}/{s['runs']}（基準 {b['passed']}/{b['runs']}）")
    p, n = sum(s["passed"] for s in r["per"].values()), sum(s["runs"] for s in r["per"].values())
    bp, bn = sum(b["passed"] for b in base.values()), sum(b["runs"] for b in base.values())
    return f"{p}/{n}", (f"{bp}/{bn}" if base else "（沒有基準）"), ("⚠️" if notes else "✅"), notes


def compare_workflow(r):
    """工作流的步驟由程式推進，模型只在判斷點出手：通過率比基準低（跑好幾次時低超過 1/3；只跑一次時基準大多會過的這次沒過）、
    有禁止動作、變慢都列出來。"""
    base = ((load_baseline("workflow") or {}).get("models") or {}).get(r["model"], {})
    notes = []
    for case, s in sorted(r["per"].items()):
        b = base.get(case)
        if s["forbidden"]:
            notes.append(f"{case}：禁止動作 {s['forbidden']} 次")
        if not b:
            notes.append(f"{case}：基準裡沒有（新案例）")
            continue
        rate, rate_b = s["passed"] / s["runs"], b["passed"] / b["runs"]
        if (s["runs"] == 1 and not s["passed"] and rate_b >= 0.75) or (s["runs"] > 1 and rate + 0.34 < rate_b):
            notes.append(f"{case}：{s['passed']}/{s['runs']} 過（基準 {b['passed']}/{b['runs']}）")
        if s["median_s"] > max(2 * b["median_s"], b["median_s"] + 30):
            notes.append(f"{case}：變慢 {s['median_s']} 秒（基準中位數 {b['median_s']} 秒）")
    p, n = sum(s["passed"] for s in r["per"].values()), sum(s["runs"] for s in r["per"].values())
    calls = sum(s["model_calls"] for s in r["per"].values())
    bp, bn = sum(b["passed"] for b in base.values()), sum(b["runs"] for b in base.values())
    return (f"{p}/{n}；判斷點的模型呼叫 {calls} 次", (f"{bp}/{bn}；{sum(b['model_calls'] for b in base.values())} 次" if base else "（沒有基準）"),
            ("⚠️" if notes else "✅"), notes)


def compare_extract(r):
    base = ((load_baseline("extract") or {}).get("models") or {}).get(r["model"], {})
    notes = []
    for case, s in sorted(r["per"].items()):
        b = base.get(case)
        if not b:
            notes.append(f"{case}：基準裡沒有")
            continue
        if s["found"] < b["found"]:
            notes.append(f"{case}：找到 {s['found']}/{s['total']}（基準 {b['found']}/{b['total']}）")
        if s["extra"] > b["extra"]:
            notes.append(f"{case}：多列 {s['extra']} 個（基準 {b['extra']}）")
        if s["count_ok"] is False and b.get("count_ok") is not False:
            notes.append(f"{case}：回答說的數量不對")
    text = "、".join(f"{c} {s['found']}/{s['total']}" for c, s in sorted(r["per"].items()))
    btxt = "、".join(f"{c} {b['found']}/{b['total']}" for c, b in sorted(base.items())) or "（沒有基準）"
    return text, btxt, ("⚠️" if notes else "✅"), notes


def compare_analysis(r):
    name = r["key"].split(":", 1)[1]
    base = ((load_baseline("analysis") or {}).get("sets") or {}).get(name, {})
    bper = base.get("per", {})
    notes = []
    keys = ("timeline", "tags", "clean", "grounded", "covered", "no_event")
    rate = lambda v: v[0] / v[1] if isinstance(v, list) and v[1] else None   # noqa: E731
    for case, s in sorted(r["per"].items()):
        b = bper.get(case)
        if not b:
            notes.append(f"{case}：基準裡沒有")
            continue
        for k in keys:
            if rate(b.get(k)) is not None and rate(s.get(k)) is not None and rate(s[k]) < rate(b[k]):
                notes.append(f"{case}：{k} {s[k][0]}/{s[k][1]}（基準 {b[k][0]}/{b[k][1]}）")
    for k in ("stability", "fact_check"):
        if k in r and k in base and r[k] != base[k]:
            if (k == "stability" and r[k][0] < r[k][1]) or (k == "fact_check" and r[k][0] > 0):
                notes.append(f"{k}：{r[k][0]}/{r[k][1]}（基準 {base[k][0]}/{base[k][1]}）")
    ok_cases = sum(1 for s in r["per"].values() if all(s[k][0] == s[k][1] for k in keys if isinstance(s.get(k), list)))
    text = f"{len(r['per'])} 份數據、全部項目都過 {ok_cases} 份" + (f"；產物每次相同 {r['stability'][0]}/{r['stability'][1]}" if "stability" in r else "") \
        + (f"；沒有根據的時間 {r['fact_check'][0]}/{r['fact_check'][1]}" if "fact_check" in r else "")
    return text, (f"{len(bper)} 份數據" if bper else "（沒有基準）"), ("⚠️" if notes else "✅"), notes


def save_baseline(results, label):
    os.makedirs(BASE, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")

    def write(name, data):
        with open(os.path.join(BASE, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"基準已更新：evals/baselines/{name}.json")
    for r in results:
        if r.get("error") or r.get("skipped"):
            continue
        if r["kind"] == "ops":
            old = load_baseline(f"ops_{OPS_MODEL.replace(':', '-')}") or {}
            totals = {"main": [], "holdout": []}
            for d in r["dirs"]:
                rows = _jsonl(os.path.join(d, "runs.jsonl"))
                m = [x for x in rows if not x["scenario"].startswith("ho_")]
                h = [x for x in rows if x["scenario"].startswith("ho_")]
                if m:
                    totals["main"].append(sum(1 for x in m if x["score"]["passed"]))
                if h:
                    totals["holdout"].append(sum(1 for x in h if x["score"]["passed"]))
            old["current"] = {"label": label, "date": stamp, "dirs": [os.path.basename(d) for d in r["dirs"]], "totals": totals, "per": r["per"]}
            write(f"ops_{OPS_MODEL.replace(':', '-')}", old)
        elif r["kind"] == "chat":
            write(f"chat_{CHAT_MODEL.replace(':', '-')}", {"label": label, "date": stamp, "dirs": [os.path.basename(d) for d in r["dirs"]],
                                                           "per": r["per"]})
        elif r["kind"] == "extract":
            old = load_baseline("extract") or {"models": {}}
            old["models"][r["model"]] = r["per"]
            old.setdefault("labels", {})[r["model"]] = f"{label}（{stamp}，{os.path.basename(r['dirs'][0])}）"
            write("extract", old)
        elif r["kind"] == "workflow":
            old = load_baseline("workflow") or {"models": {}}
            old["models"][r["model"]] = r["per"]
            old.setdefault("labels", {})[r["model"]] = f"{label}（{stamp}，{os.path.basename(r['dirs'][0])}）"
            write("workflow", old)
        elif r["kind"] == "analysis":
            old = load_baseline("analysis") or {"sets": {}}
            name = r["key"].split(":", 1)[1]
            old["sets"][name] = {k: v for k, v in r.items() if k in ("per", "stability", "fact_check")}
            old["sets"][name]["label"] = f"{label}（{stamp}，{os.path.basename(r['dirs'][0])}）"
            write("analysis", old)
        elif r["kind"] == "selftest":
            old = load_baseline("offline") or {}
            old[r["key"]] = {"passed": r["result"]["passed"], "total": r["result"]["total"], "label": f"{label}（{stamp}）"}
            write("offline", old)


# ================================================================ 主程式
def write_summary(results, out_dir, args):
    rows, details, verdicts = [], [], []
    for r in results:
        text, btxt, verdict, notes = compare(r)
        verdicts.append(verdict)
        rows.append(f"| {r.get('title', r['key'])}（`{r['key']}`） | {text} | {btxt} | {verdict} |")
        if notes:
            details.append(f"### {r.get('title', r['key'])}\n" + "\n".join(f"- {n}" for n in notes[:40]))
    head = "✅ 沒有退步" if all(v in ("✅", "⏭️") for v in verdicts) else "⚠️ 有要注意的項目（見下面）" if "❌" not in verdicts else "❌ 有測試沒過或執行失敗"
    lines = [f"# 階段驗證（{time.strftime('%Y-%m-%d %H:%M')}）：{head}", "",
             f"- 跑了：{'離線' if not args.compare else '只比對已有的結果'}{'＋實機' if args.live else ''}{'＋真模型' if args.model else ''}"
             + (f"（只有 {args.only}）" if args.only else ""), "",
             "| 項目 | 結果 | 基準 | 判定 |", "|---|---|---|---|", *rows, ""]
    if details:
        lines += ["## 要注意的", "", *details]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(text)
    return 0 if "❌" not in verdicts else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--model", action="store_true")
    ap.add_argument("--no-offline", action="store_true", help="不跑離線的自我測試")
    ap.add_argument("--only", default="", help="只跑這幾項（逗號分隔，例如 skills,ops,extract）")
    ap.add_argument("--compare", nargs="+", help="不跑，拿這幾個結果目錄跟基準比")
    ap.add_argument("--save-baseline", nargs="+", metavar="DIR", help="用這幾個結果目錄更新基準")
    ap.add_argument("--label", default="", help="--save-baseline 時寫進基準的說明（例如「第 3 階段 commit 之後」）")
    args = ap.parse_args()
    if args.save_baseline:
        results = from_dirs(args.save_baseline)
        only = set(x for x in args.only.split(",") if x)
        if only:   # 只更新這幾項（名稱同 --only；workflow、extract、analysis、tools_live 這種有冒號的看冒號前面）
            results = [r for r in results if r["key"] in only or r["key"].split(":")[0] in only]
        save_baseline(results, args.label or "手動更新")
        return 0
    out_dir = os.path.join(PROJECT, "evals", "results", time.strftime("%Y%m%d_%H%M%S") + "_phase_check")
    os.makedirs(out_dir, exist_ok=True)
    if args.compare:
        return write_summary(from_dirs(args.compare), out_dir, args)
    only = set(x for x in args.only.split(",") if x)
    backup = open(SETTINGS, encoding="utf-8").read() if os.path.exists(SETTINGS) else None
    results = []
    try:
        if not args.no_offline:
            results += suite_offline(only)
        if args.live:
            results += suite_live(only)
        if args.model:
            results += suite_model(only)
    finally:
        if backup is not None and open(SETTINGS, encoding="utf-8").read() != backup:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                f.write(backup)
            print("logs/analysis_settings.json 被改過，已還原")
    return write_summary(results, out_dir, args)


if __name__ == "__main__":
    sys.exit(main())
