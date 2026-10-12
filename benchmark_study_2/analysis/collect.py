"""把第二次評測的原始結果（results/raw/<目錄>/runs.jsonl，原本在 evals/results/）整理成表格：results/tables/*.csv。

    python3 benchmark_study_2/analysis/collect.py

- DevBench（從規格從零寫出專案）：*_devbench_<worker>[_plan-<規劃>]（harness）、*_devbench-bare_<模型>（不用 harness）。
  第一次研究（../benchmark_study）的 gemma4:26b v4 結果（E1／E2，隱藏測試）一起列進來當比較基準，study=1。
- SWE-bench 子集（既有專案的 issue 修正）：*_swebench_<worker>[_plan-<規劃>]（harness）、*_swebench-bare_<模型>（不用 harness）。
  多算一欄「patch 有沒有改到參考解答改的檔案」（定位對不對）與失敗類型。
每個目錄的版本、伺服器設定、備註照 experiments.json；沒有列的依名稱自動分類。只用標準庫。
"""
import argparse
import csv
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
STUDY1 = os.path.join(os.path.dirname(STUDY), "benchmark_study")
INSTANCES = os.path.join(STUDY, "datasets", "swebench_subset", "instances.json")
SHORT = {"qwen2.5-coder:32b": "Qwen2.5-Coder-32B", "deepseek-r1:32b": "DeepSeek-R1-32B", "gemma4:26b": "gemma4:26b", "gemma4:e4b": "gemma4:e4b"}


def load_jsonl(path):
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
    return out


def model_name(tag):
    """目錄名稱裡的模型（gemma4-26b、qwen2.5-coder-32b、deepseek-r1-32b）→ Ollama 的名稱：評測程式把 : 換成 -，
    而這些模型的 tag（26b、32b、e4b）本身沒有 -，所以最後一個 - 換回 :。"""
    return ":".join(tag.rsplit("-", 1)) if "-" in tag else tag


def config_label(condition, planner, worker):
    if condition == "bare":
        return f"不用 harness：{SHORT.get(worker, worker)}"
    if planner and planner != worker:
        return f"harness：{SHORT.get(planner, planner)} 規劃＋{SHORT.get(worker, worker)} worker"
    return f"harness：{SHORT.get(worker, worker)}"


def classify(name, manifest):
    meta = dict(manifest.get(name) or {})
    if name.endswith(("_smoke", "_aborted")):   # 流程的冒煙測試（--tag smoke）、中途停掉重跑的（見 experiments.json），不算進結果
        return None
    m = re.match(r"\d{8}_\d{6}_(devbench|swebench)(-bare)?_(.+)$", name)
    if not m:
        return None
    bench, bare, rest = m.group(1), bool(m.group(2)), m.group(3)
    tag = rest.split("_tag-")[0]
    visible = tag.endswith("_visible-tests")
    tag = tag.replace("_visible-tests", "")
    parts = tag.split("_plan-")
    worker = model_name(parts[0].split("_")[0])
    planner = model_name(parts[1].split("_")[0]) if len(parts) > 1 else (None if bare else worker)
    extra = parts[0].split("_", 1)[1] if "_" in parts[0] else ""
    meta.setdefault("note", extra)
    meta.update(bench=bench, condition="bare" if bare else "harness", worker=worker, planner=planner, visible=visible)
    if "_v411" in name:
        meta.setdefault("version", "v4.1.1")
    if "_v42" in name:
        meta.setdefault("version", "v4.2")
    return meta


FAILURE_ORDER = ["全部通過", "介面不符", "實作編譯失敗", "缺實作（連結失敗）", "依賴或資料缺少", "邏輯錯誤（斷言失敗）", "其他執行錯誤"]


def failure_mode(tail, passed, total):
    """DevBench 測試輸出的結尾 → 主要的失敗類型（跟第一次研究同一套規則）。"""
    if total and passed >= total:
        return "全部通過"
    t = tail or ""
    if re.search(r"cannot import name|has no attribute|does not have the attribute|is not a namespace-name|"
                 r"(unit_tests?|tests?|acceptance_tests?)/[^\s:]+:\d+:\d+: error|TypeError: .*(argument|positional)|"
                 r"no matching function|has no member named|is private within|was not declared in this scope.*\n.*(unit_tests?|tests?)/", t):
        return "介面不符"
    if re.search(r"(^|\s)(src|include)/[^\s:]+:\d+:\d+: error|\.(cpp|cc|h|hpp):\d+:\d+: error", t):
        return "實作編譯失敗"
    if re.search(r"undefined reference|ld returned \d+ exit status", t):
        return "缺實作（連結失敗）"
    if re.search(r"ModuleNotFoundError|FileNotFoundError|No such file or directory", t):
        return "依賴或資料缺少"
    if re.search(r"AssertionError|assert .*==|Expected equality|Value of:|Failure\b|Which is:", t):
        return "邏輯錯誤（斷言失敗）"
    return "其他執行錯誤"


SWE_FAILURE_ORDER = ["解決", "沒有改任何東西", "patch 套不上", "改錯地方（沒改到該改的檔案）", "改對檔案但沒修好", "修好了但弄壞既有測試"]


def swe_failure(score, touched_gold, patch_files):
    if score.get("resolved"):
        return "解決"
    if score.get("empty_patch") or not patch_files:
        return "沒有改任何東西"
    if score.get("applied") is False and "f2p_pass" not in score:
        return "patch 套不上"
    f2p_total = score.get("f2p_pass", 0) + score.get("f2p_fail", 0)
    f2p_ok = f2p_total > 0 and score.get("f2p_pass", 0) == f2p_total
    if f2p_ok and score.get("p2p_fail", 0) > 0:
        return "修好了但弄壞既有測試"
    return "改對檔案但沒修好" if touched_gold else "改錯地方（沒改到該改的檔案）"


def gold_files():
    with open(INSTANCES, encoding="utf-8") as f:
        rows = json.load(f)
    return {r["instance_id"]: [l.split(" b/", 1)[-1] for l in r["patch"].splitlines() if l.startswith("diff --git ")] for r in rows}


PLAN_KINDS = {"code_scout", "code_plan", "code_revise"}


def perf_split(r):
    """一次 job 的模型呼叫依角色分開算：規劃（scout／plan）與 worker（決定／內容）各幾次、幾秒；載入模型（換模型）花了幾秒。"""
    out = {"plan_calls": 0, "plan_seconds": 0.0, "worker_calls": 0, "worker_seconds": 0.0, "load_seconds": 0.0, "eval_tokens": 0}
    if not r.get("perf"):     # 沒有效能紀錄（逾時被結束、事件是從 job 的紀錄撈回來的）：當作缺值，不是 0
        return {k: "" for k in out}
    for x in r.get("perf") or []:
        role = "plan" if x.get("kind") in PLAN_KINDS else "worker"
        out[f"{role}_calls"] += 1
        out[f"{role}_seconds"] += (x.get("wall_ms") or 0) / 1000
        out["load_seconds"] += (x.get("load_ms") or 0) / 1000
        out["eval_tokens"] += x.get("eval_tokens") or 0
    return {k: round(v, 1) if isinstance(v, float) else v for k, v in out.items()}


SIMILAR_RE = re.compile(r"最像的是第 (\d+)～(\d+) 行")
NO_TESTS_RE = re.compile(r"Ran 0 tests|collected 0 items|no tests ran|沒有收集到任何測試|Running 0 tests|No tests were found")


def final_no_tests(r):
    """整體驗證判定通過，但其實沒有跑到任何測試（django 的測試標籤寫錯「Ran 0 tests」、pytest -k 篩不到測試而改用靜態檢查…）→ 1。"""
    fin = [e for e in r.get("events") or [] if e.get("type") == "verify" and "整體驗證" in str(e.get("text") or "")]
    if not fin or not fin[-1].get("ok"):
        return 0
    return int(bool(NO_TESTS_RE.search(str(fin[-1].get("detail") or ""))))


def event_counts(r):
    """worker 的行為指標（從 job 的事件流算）：步數、工具呼叫與錯誤、驗證通過／失敗、卡住被結束的 worker、空白回覆、
    沒改檔案就回報完成、換新 worker 重試。用來比較不同模型「照格式、用工具」穩不穩。"""
    c = {"steps": 0, "tool_calls": 0, "tool_errors": 0, "verify_pass": 0, "verify_fail": 0, "stuck_workers": 0, "blank_replies": 0,
         "no_change_claims": 0, "worker_retries": 0, "noop_edits": 0, "search_mismatch": 0, "search_beyond_800": 0, "search_no_similar": 0}
    if not r.get("events"):   # 逾時被結束、也撈不回事件：缺值
        return {k: "" for k in c}
    for e in r.get("events") or []:
        t, text = e.get("type"), str(e.get("text") or "")
        if t == "step":
            c["steps"] += 1
            c["blank_replies"] += text == "（空白回覆）"
        elif t == "tool":
            c["tool_calls"] += 1
            c["tool_errors"] += e.get("status") == "ERROR"
            if e.get("status") == "ERROR":   # 寫檔的兩種白工：內容通道送回一模一樣的內容（空轉）、SEARCH 對不上原文
                full = str(e.get("detail") or text)
                c["noop_edits"] += "新內容跟檔案目前的內容完全一樣" in full
                if "SEARCH 的內容在檔案裡找不到" in full:
                    c["search_mismatch"] += 1
                    m = SIMILAR_RE.search(full)
                    if not m:
                        c["search_no_similar"] += 1
                    elif int(m.group(1)) > 800:   # v4.1 的修改視窗只有檔案的前 800 行（v4.2 改成以目標為中心）
                        c["search_beyond_800"] += 1
        elif t == "verify":
            c["verify_pass" if e.get("ok") else "verify_fail"] += 1
        elif t == "note":
            c["stuck_workers"] += text.startswith("⛔")
            c["no_change_claims"] += text.startswith("↩️")
        elif t == "item":
            c["worker_retries"] += text.startswith("🔁")
    return c


TEST_PATH_RE = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]*$|_test\.[^/]+$|(^|/)tests\.py$")


def patch_split(patch):
    """patch → 原始碼改了幾行、測試改了幾行、新增了幾個測試檔（測試檔：路徑在 test／tests／testing 目錄、檔名 test_* 或 *_test.*）、
    在專案根目錄新增了幾個檔案。"""
    src = test = new_tests = new_root = 0
    cur_test, cur_path = False, ""
    for line in (patch or "").splitlines():
        if line.startswith("diff --git "):
            cur_path = line.split(" b/", 1)[-1]
            cur_test = bool(TEST_PATH_RE.search(cur_path))
        elif line.startswith("new file mode"):
            new_tests += cur_test
            new_root += "/" not in cur_path   # 專案根目錄的新檔案：多半是 agent 自己的除錯或重現腳本
        elif line[:1] in "+-" and not line.startswith(("+++", "---")):
            if cur_test:
                test += 1
            else:
                src += 1
    return {"src_lines": src, "test_lines": test, "new_test_files": new_tests, "new_root_files": new_root}


def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def study1_devbench():
    """第一次研究的 gemma4:26b／e4b（v4，官方測試看不到）DevBench 結果：harness 兩次、不用 harness 各一次。分數與失敗類型照第一次
    研究的表格；規劃／worker 的呼叫與時間、worker 的行為指標從第一次研究的原始紀錄（runs.jsonl 的 perf 與事件流）算。"""
    path = os.path.join(STUDY1, "results", "tables", "devbench_runs.csv")
    out = []
    if not os.path.exists(path):
        return out
    raw = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["version"] == "v4" and r["visible"] == "0" and r["exp"] in ("E1", "E2") and r["model"] == "gemma4:26b" and r["run_dir"] not in raw:
                raw[r["run_dir"]] = {x["repo"]: x for x in load_jsonl(os.path.join(STUDY1, "results", "raw", r["run_dir"], "runs.jsonl"))}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["version"] != "v4" or r["visible"] != "0" or r["exp"] not in ("E1", "E2") or r["model"] != "gemma4:26b":
                continue
            cond = "bare" if r["condition"] == "bare" else "harness"
            out.append({"run_dir": "../benchmark_study/" + r["run_dir"], "study": 1, "version": "v4", "server": "11434（KV f16）",
                        "condition": cond, "planner": "" if cond == "bare" else r["model"], "worker": r["model"],
                        "config": config_label(cond, r["model"], r["model"]), "repo": r["repo"], "lang": r["lang"],
                        "lines": r["lines"], "unit": int(r["unit"]), "unit_total": int(r["unit_total"]),
                        "acceptance": int(r["acceptance"]), "acceptance_total": int(r["acceptance_total"]),
                        "minutes": float(r["minutes"] or 0), "model_calls": r["model_calls"], "job_status": r["job_status"],
                        "unit_failure": r["unit_failure"], "acceptance_failure": r["acceptance_failure"]})
            rr = raw.get(r["run_dir"], {}).get(r["repo"])
            if rr and cond == "harness":
                out[-1].update(plan_warnings=len(rr.get("warnings") or []), items=len(rr.get("items") or []),
                               items_done=sum(1 for it in rr.get("items") or [] if it.get("status") == "done"),
                               **perf_split(rr), **event_counts(rr))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(STUDY, "results", "raw"))
    ap.add_argument("--out", default=os.path.join(STUDY, "results", "tables"), help="表格的目錄（INDEX.md 寫在它的上一層）")
    args = ap.parse_args()
    raw, out_dir = args.raw, args.out
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(HERE, "experiments.json"), encoding="utf-8") as f:
        manifest = {e["dir"]: e for e in json.load(f)["runs"]}
    with open(os.path.join(STUDY1, "datasets", "devbench_subset", "repos.json"), encoding="utf-8") as f:
        lines = {k: v.get("lines") for k, v in json.load(f)["repos"].items()}
    gold = gold_files()
    dev, swe, index, skipped = study1_devbench(), [], [], []
    for d in sorted(glob.glob(os.path.join(raw, "*"))):
        name = os.path.basename(d)
        meta = classify(name, manifest)
        if not meta or meta.get("exclude"):
            skipped.append(name)
            continue
        if "version" not in meta:                              # gather_raw.py 記下的凍結副本（~/cah_eval/<版本>）
            try:
                with open(os.path.join(d, "HARNESS_VERSION.txt"), encoding="utf-8") as f:
                    m = re.search(r"cah_eval/(v[\d.]+)", f.read())
                if m:
                    meta["version"] = m.group(1)
            except OSError:
                pass
        runs = load_jsonl(os.path.join(d, "runs.jsonl"))
        rescored = {}
        if os.path.exists(os.path.join(d, "rescored.json")):   # evals/swebench/recheck.py：計分紀錄被輸出交錯弄亂、單獨重新計分過的題目
            with open(os.path.join(d, "rescored.json"), encoding="utf-8") as f:
                rescored = json.load(f)
        cfg = config_label(meta["condition"], meta["planner"], meta["worker"])
        if str(meta.get("version", "")).startswith("v4.2"):      # 這次研究後的改版（E10），跟 v4.1 分開比較
            cfg += "（v4.2）"
        index.append([name, "DevBench" if meta["bench"] == "devbench" else "SWE-bench 子集", meta.get("exp", ""), cfg,
                      meta.get("version", "v4.1"), len(runs), meta.get("note", "")])
        common = {"run_dir": name, "study": 2, "version": meta.get("version", "v4.1"), "server": meta.get("server", "11435（KV q8_0）"),
                  "condition": meta["condition"], "planner": meta["planner"] or "", "worker": meta["worker"], "config": cfg}
        if meta["bench"] == "devbench":
            for r in runs:
                s = r["score"]
                dev.append(dict(common, repo=r["repo"], lang=r["lang"], lines=lines.get(r["repo"]), unit=s["unit"],
                                unit_total=s["unit_total"], acceptance=s["acceptance"], acceptance_total=s["acceptance_total"],
                                minutes=round((r.get("seconds") or r.get("wall_seconds") or 0) / 60, 2),
                                model_calls=r.get("model_calls") or "", job_status=r.get("job_status", "bare" if meta["condition"] == "bare" else ""),
                                unit_failure=failure_mode(s.get("unit_tail"), s["unit"], s["unit_total"]),
                                acceptance_failure=failure_mode(s.get("acceptance_tail"), s["acceptance"], s["acceptance_total"]),
                                plan_warnings=len(r.get("warnings") or []), items=len(r.get("items") or []),
                                items_done=sum(1 for it in r.get("items") or [] if it.get("status") == "done"), **perf_split(r),
                                **event_counts(r)))
        else:
            affected = set(meta.get("affected_instances") or [])
            for r in runs:
                s = rescored.get(r["instance_id"]) or r.get("score") or {}
                files = (r.get("patch_stats") or {}).get("files") or []
                row_common = common
                if r["instance_id"] in affected:   # 受 C++ 掃描器 bug 影響的題目：另外一個條件（修正前後的比較用），不算進正式的結果
                    row_common = dict(common, config=meta["affected_config"], version=meta.get("version", "v4.1"))
                g = gold.get(r["instance_id"], [])
                touched = bool(set(files) & set(g))
                acts = " ".join(str(e.get("action") or "") for e in r.get("events") or [] if e.get("type") == "step")
                seen = any(x in acts for x in g) if meta["condition"] == "harness" else None
                swe.append(dict(row_common, instance=r["instance_id"], repo=r["repo"], lang=r["lang"], difficulty=r.get("difficulty") or "",
                                resolved=int(bool(s.get("resolved"))), applied=int(bool(s.get("applied"))),
                                empty_patch=int(bool(s.get("empty_patch")) or not files),
                                f2p_pass=s.get("f2p_pass", ""), f2p_total=(s.get("f2p_pass", 0) + s.get("f2p_fail", 0)) if "f2p_pass" in s else "",
                                p2p_pass=s.get("p2p_pass", ""), p2p_total=(s.get("p2p_pass", 0) + s.get("p2p_fail", 0)) if "p2p_pass" in s else "",
                                minutes=round((r.get("seconds") or r.get("wall_seconds") or 0) / 60, 2), model_calls=r.get("model_calls") or "",
                                job_status=r.get("job_status", "bare" if meta["condition"] == "bare" else ""),
                                viewed_gold_file="" if seen is None else int(seen),
                                patch_files=len(files), added=(r.get("patch_stats") or {}).get("added", 0),
                                removed=(r.get("patch_stats") or {}).get("removed", 0), touched_gold_file=int(touched),
                                retrieval_hit="" if meta["condition"] != "bare" else int(bool(r.get("retrieval_hit"))),
                                failure=swe_failure(s, touched, files), error=str(r.get("error") or "")[:200],
                                rescored=int(r["instance_id"] in rescored), **patch_split(r.get("patch")),
                                final_ok="" if meta["condition"] != "harness" or r.get("final_ok") is None else int(bool(r.get("final_ok"))),
                                final_verify=str(r.get("final_verify") or "")[:80],
                                final_no_tests="" if meta["condition"] != "harness" else final_no_tests(r),
                                plan_warnings=len(r.get("warnings") or []), items=len(r.get("items") or []),
                                items_done=sum(1 for it in r.get("items") or [] if it.get("status") == "done"), **perf_split(r),
                                **event_counts(r)))
    with open(os.path.join(os.path.dirname(out_dir), "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("# 原始紀錄的索引\n\n`raw/<目錄>/` 是評測輸出（`evals/results/`）的副本：`runs.jsonl`（每一次的完整紀錄）、`report.md`（當時的報表）；"
                "DevBench 另有 `workspaces/<repo>/`（agent 寫出來的程式），SWE-bench 另有 `patches/<題目>.diff`（agent 的修改）與 "
                "`official_eval/<題目>/`（官方計分的紀錄：report.json、test_output.txt）。由 `analysis/collect.py` 產生。\n\n"
                "| 目錄 | 基準 | 實驗 | 條件 | harness 版本 | 紀錄數 | 備註 |\n|---|---|---|---|---|---|---|\n")
        for row in index:
            f.write("| " + " | ".join(str(x) for x in row) + " |\n")
    write_csv(os.path.join(out_dir, "devbench_runs.csv"), dev)
    write_csv(os.path.join(out_dir, "swebench_runs.csv"), swe)
    print(f"DevBench {len(dev)} 列（含第一次研究 {sum(1 for r in dev if r['study'] == 1)} 列）、SWE-bench {len(swe)} 列 → {out_dir}"
          + (f"\n略過：{', '.join(skipped)}" if skipped else ""))


if __name__ == "__main__":
    main()
