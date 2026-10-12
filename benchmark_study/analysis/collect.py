"""把評測的原始結果（results/raw/<目錄>/runs.jsonl，原本在 evals/results/）整理成表格：results/tables/*.csv。

    python3 benchmark_study/analysis/collect.py                 # 讀 benchmark_study/results/raw
    python3 benchmark_study/analysis/collect.py --raw evals/results

每個目錄屬於哪個實驗、版本、條件，照 experiments.json；清單沒有列的目錄依名稱自動分類（v4 之後新增的：*_devbench-bare_*、
*_coding-bare_*、*_robust_guards-on／off、主對話的回歸）。只用標準庫。
"""
import argparse
import csv
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
V4_FROM = "20261008_1437"          # 程式碼雜湊 1ff704a72cdc0733 凍結的時間；之後的目錄都是 v4


def load_jsonl(path):
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def manifest():
    with open(os.path.join(HERE, "experiments.json"), encoding="utf-8") as f:
        data = json.load(f)
    return {kind: {e["dir"]: e for e in data[kind]} for kind in ("devbench", "coding", "main")}


def repo_lines():
    """DevBench 每個 repo 的程式碼行數（論文依行數加權）。"""
    with open(os.path.join(STUDY, "datasets", "devbench_subset", "repos.json"), encoding="utf-8") as f:
        repos = json.load(f)["repos"]
    return {name: cfg.get("lines") for name, cfg in repos.items()}


def classify(name, man):
    """目錄名稱 → (類別, 欄位 dict) 或 None。"""
    for kind in ("devbench", "coding", "main"):
        if name in man[kind]:
            return kind, dict(man[kind][name])
    ts = name[:13]
    after = ts >= V4_FROM
    m = re.match(r"\d{8}_\d{6}_devbench-bare_([\w.-]+?)(_visible-tests)?$", name)
    if m:
        return "devbench", {"exp": "E3" if m.group(2) else "E2", "version": "v4", "model": m.group(1).replace("-", ":", 1),
                            "condition": "bare", "visible": bool(m.group(2))}
    m = re.match(r"\d{8}_\d{6}_devbench_([\w.-]+?)(_visible-tests)?$", name)
    if m and after:
        return "devbench", {"exp": "E3" if m.group(2) else "E1", "version": "v4", "model": m.group(1).replace("-", ":", 1),
                            "condition": "harness", "visible": bool(m.group(2))}
    if re.match(r"\d{8}_\d{6}_coding-bare_", name):
        return "coding", {"version": "v4", "condition": "bare"}
    if re.match(r"\d{8}_\d{6}_coding_", name) and after:
        return "coding", {"version": "v4", "condition": "harness"}
    m = re.match(r"\d{8}_\d{6}_robust_guards-(on|off)$", name)
    if m:
        return "main", {"exp": "E6", "version": "v4", "suite": "robust", "condition": f"guards-{m.group(1)}"}
    m = re.match(r"\d{8}_\d{6}_robust_(v41-on|v4rule-on|v41-off)$", name)
    if m:
        cond = {"v41-on": "v4.1 把關開啟", "v4rule-on": "v4 的規則（對照）", "v41-off": "把關全部關閉"}[m.group(1)]
        return "main", {"exp": "E7", "version": "v4.1", "suite": "robust", "condition": cond}
    if re.match(r"\d{8}_\d{6}_v41$", name):
        return "main", {"exp": "E7", "version": "v4.1", "suite": "main", "condition": "guards-on"}
    if re.match(r"\d{8}_\d{6}$", name) and after:
        return "main", {"exp": "E5", "version": "v4", "suite": "main", "condition": "guards-on"}
    return None


FAILURE_ORDER = ["全部通過", "介面不符", "實作編譯失敗", "缺實作（連結失敗）", "依賴或資料缺少", "邏輯錯誤（斷言失敗）", "其他執行錯誤"]


def failure_mode(tail, passed, total):
    """測試輸出的結尾（最多 3000 字）→ 主要的失敗類型（近似：只看得到結尾）。先看會讓整批測試都跑不了的原因。"""
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


def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(STUDY, "results", "raw"))
    ap.add_argument("--out", default=os.path.join(STUDY, "results", "tables"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    man, lines = manifest(), repo_lines()
    dev, cod, mai, skipped, index = [], [], [], [], []
    for d in sorted(glob.glob(os.path.join(args.raw, "*"))):
        name = os.path.basename(d)
        c = classify(name, man)
        if not c:
            skipped.append(name)
            continue
        kind, meta = c
        runs = load_jsonl(os.path.join(d, "runs.jsonl"))
        index.append([name, {"devbench": "DevBench", "coding": "自建 coding 情境", "main": "主對話"}[kind],
                      meta.get("exp") or ("E4" if kind == "coding" else ("E6／E7" if meta.get("suite") == "robust" else "E5")),
                      meta.get("version", ""), meta.get("model") or (runs[0].get("model") if runs else "") or "", meta.get("condition", "")
                      + ("・官方測試看得到" if meta.get("visible") else ""), len(runs), meta.get("note", "")])
        if kind == "devbench":
            for r in runs:
                s = r["score"]
                dev.append({"run_dir": name, "exp": meta["exp"], "version": meta["version"],
                            "model": meta.get("model") or r.get("model"), "condition": meta["condition"],
                            "visible": int(bool(meta.get("visible"))), "repo": r["repo"], "lang": r["lang"],
                            "lines": lines.get(r["repo"]), "unit": s["unit"], "unit_total": s["unit_total"],
                            "acceptance": s["acceptance"], "acceptance_total": s["acceptance_total"],
                            "minutes": round((r.get("seconds") or r.get("wall_seconds") or 0) / 60, 2),
                            "model_calls": r.get("model_calls") or "", "job_status": r.get("job_status", ""),
                            "unit_failure": failure_mode(s.get("unit_tail"), s["unit"], s["unit_total"]),
                            "acceptance_failure": failure_mode(s.get("acceptance_tail"), s["acceptance"], s["acceptance_total"])})
        elif kind == "coding":
            m = re.search(r"_coding(?:-bare)?_([\w.-]+)$", name)
            model = m.group(1).replace("-", ":", 1) if m else ""
            for i, r in enumerate(runs):
                ch = r.get("checks") or {}
                cod.append({"run_dir": name, "version": meta["version"], "model": r.get("model") or model, "condition": meta["condition"],
                            "scenario": r.get("scenario"), "run": r.get("run", ""), "passed": int(bool(r.get("passed"))),
                            "hidden_tests": "" if "hidden_tests" not in ch else int(ch["hidden_tests"]),
                            "all_tests": "" if "all_tests" not in ch else int(ch["all_tests"]),
                            "other_checks": ";".join(f"{k}={int(v)}" for k, v in ch.items() if k not in ("hidden_tests", "all_tests")),
                            "seconds": r.get("seconds") or r.get("wall_seconds") or "", "model_calls": r.get("model_calls") or "",
                            "job_status": r.get("job_status", "bare" if meta["condition"] == "bare" else "")})
        else:
            for r in runs:
                turns = r.get("turns") or []
                calls = [c for t in turns for c in t.get("tool_calls", [])]
                seq = [(c["script"], tuple(c["args"])) for c in calls]
                repeats = sum(1 for a, b in zip(seq, seq[1:]) if a == b)
                checks = {}
                for t in turns:
                    for k, v in (t.get("checks") or {}).items():
                        checks[k] = checks.get(k, True) and v
                mai.append({"run_dir": name, "exp": meta.get("exp") or "E5", "version": meta["version"], "suite": meta.get("suite", "main"),
                            "condition": meta["condition"], "mode": r.get("mode"), "model": r.get("model"),
                            "scenario": r.get("scenario"), "run": r.get("run", ""), "passed": int(bool(r.get("passed"))),
                            "checks": ";".join(f"{k}={int(v)}" for k, v in checks.items()),
                            "turns": len(turns), "main_calls": sum(t.get("main_calls", 0) for t in turns),
                            "tool_calls": len(calls), "consecutive_repeats": repeats,
                            "hit_step_limit": int(any(t.get("hit_step_limit") for t in turns)),
                            "stuck_stop": int(any(t.get("stuck") for t in turns)),
                            "claim_nudges": sum(t.get("claim_nudges", 0) for t in turns),
                            "seconds": r.get("seconds") or r.get("wall_seconds") or "", "error": int(bool(r.get("error")))})
    with open(os.path.join(os.path.dirname(args.out), "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("# 原始紀錄的索引\n\n`raw/<目錄>/` 是 `evals/results/` 的副本：`runs.jsonl`（每一次的完整紀錄）、`report.md`（當時的報表）、"
                "DevBench 另有 `workspaces/<repo>/`（agent 寫出來的程式）。由 `analysis/collect.py` 依 `analysis/experiments.json` 產生。\n\n"
                "| 目錄 | 基準 | 實驗 | 版本 | 模型 | 條件 | 紀錄數 | 備註 |\n|---|---|---|---|---|---|---|---|\n")
        for row in index:
            f.write("| " + " | ".join(str(x) for x in row) + " |\n")
    write_csv(os.path.join(args.out, "devbench_runs.csv"), dev)
    write_csv(os.path.join(args.out, "coding_runs.csv"), cod)
    write_csv(os.path.join(args.out, "main_session_runs.csv"), mai)
    print(f"DevBench {len(dev)} 列、coding {len(cod)} 列、主對話 {len(mai)} 列 → {args.out}"
          + (f"\n沒有分類（略過）：{', '.join(skipped)}" if skipped else ""))


if __name__ == "__main__":
    main()
