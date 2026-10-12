"""自建 coding 情境的「不用 harness」對照組（benchmark_study 的實驗 E4）：同一個模型、同樣的任務文字，加上專案裡所有檔案的
內容，呼叫一次模型，請它輸出要新增或修改的每個檔案的完整內容——沒有工具、沒有規劃、沒有測試回饋、沒有重試（像在聊天視窗裡把
專案貼給模型）。寫進工作區之後，用跟 run_coding_evals.py 一樣的檢查計分：hidden tests、整個專案的測試（真的 pytest／gtest）、
不准改的檔案（unchanged）、改名後舊名稱不能再出現（absent）、檔案內容要符合（contains）。

    python3 evals/bare_coding_baseline.py --model gemma4:e4b
    python3 evals/bare_coding_baseline.py --model gemma4:26b --runs 2 --lang cpp
    python3 evals/bare_coding_baseline.py --only feature_restock,cpp_perimeter

模型參數跟 coding worker 的內容通道一樣（temperature 0.2、num_ctx、think=False；一次要輸出好幾個檔案，num_predict 放寬到 12000）。
結果在 evals/results/<時間>_coding-bare_<模型>/：report.md、runs.jsonl（模型的原始回覆、寫了哪些檔案、測試輸出）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)
from agent_core.config import NUM_CTX  # noqa: E402
from evals.coding_scenarios import SCENARIOS  # noqa: E402
from skills_system.scripts import _code_common as cc  # noqa: E402

SCRIPTS = os.path.join(PROJECT, "skills_system", "scripts")
CODE_EXTS = {".py", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh"}
FILES_BUDGET = 60000
NUM_PREDICT = 12000
SYSTEM = "你是資深的軟體工程師。照使用者的要求修改專案：輸出要新增或修改的每個檔案的完整內容，格式照指示，不要省略任何一行。"
FILE_BLOCK_RE = re.compile(r"^#{2,4}\s*(?:檔案|File)?[:：]?\s*`?([\w./+-]+)`?\s*\n+```[^\n`]*\n(.*?)```", re.S | re.M)


def chat(model, prompt):
    import ollama
    last = None
    for i in range(3):
        t0 = time.time()
        try:
            res = ollama.chat(model=model, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                              options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT}, think=False)
            return res["message"]["content"], round(time.time() - t0, 1)
        except Exception as e:      # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"呼叫模型失敗：{last}")


def project_text(ws):
    parts, total = [], 0
    for p, rel in cc.iter_files(ws):
        text = cc.read_text(p)
        piece = f"## {rel}\n```\n{text.rstrip()}\n```"
        if total + len(piece) > FILES_BUDGET:
            parts.append("## （其餘的檔案為了長度省略）")
            break
        parts.append(piece)
        total += len(piece)
    return "\n\n".join(parts)


def code_test(ws, args_):
    env = dict(os.environ, CODE_WORKSPACE=ws, PYTHONDONTWRITEBYTECODE="1")
    env.pop("CODE_BACKUP_DIR", None)
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "code_test_cmd.py")] + list(args_), cwd=ws, env=env,
                       capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
    return (r.stdout + r.stderr).strip()


def run_one(sc, model):
    tmp = tempfile.mkdtemp(prefix="coding_bare_")
    ws = os.path.join(tmp, "workspace")
    shutil.copytree(os.path.join(HERE, "coding_fixtures", sc["fixture"]), ws,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "build"))
    originals = {rel: cc.read_text(os.path.join(ws, rel)) for rel in sc.get("unchanged") or []}
    prompt = (f"# 任務\n{sc['task']}\n\n# 專案裡的檔案（路徑都相對於專案根目錄）\n{project_text(ws)}\n\n"
              "# 輸出格式\n照任務修改專案。每個要新增或修改的檔案都用下面的格式輸出**完整內容**（不是只有改的部分）：\n"
              "### 檔案：<相對路徑>\n```<語言>\n（完整內容）\n```\n沒有改的檔案不要輸出。除了這些區塊不要寫其他文字。")
    t0 = time.time()
    reply, secs = chat(model, prompt)
    written = []
    for rel, body in FILE_BLOCK_RE.findall(reply or ""):
        rel = rel.strip().lstrip("./")
        full = os.path.realpath(os.path.join(ws, rel))
        if not full.startswith(os.path.realpath(ws) + os.sep) or "/.git/" in full:
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(body.rstrip() + "\n")
        written.append(rel)
    for rel, body in (sc.get("hidden_tests") or {}).items():
        p = os.path.join(ws, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
    tests_out = code_test(ws, [])
    hidden_out = code_test(ws, list(sc["hidden_tests"])) if sc.get("hidden_tests") else ""
    checks = {"all_tests": tests_out.startswith("[PASS]")}
    if sc.get("hidden_tests"):
        checks["hidden_tests"] = hidden_out.startswith("[PASS]")
    if originals:
        checks["unchanged"] = all(os.path.isfile(os.path.join(ws, rel)) and cc.read_text(os.path.join(ws, rel)) == body
                                  for rel, body in originals.items())
    if sc.get("absent"):
        pat, hits = re.compile(sc["absent"]["pattern"]), []
        for d in sc["absent"]["dirs"]:
            for dirpath, _, files in os.walk(os.path.join(ws, d)):
                for fn in files:
                    if os.path.splitext(fn)[1] in CODE_EXTS and not fn.startswith("test_hidden"):
                        if pat.search(cc.read_text(os.path.join(dirpath, fn))):
                            hits.append(fn)
        checks["absent"] = not hits
    if sc.get("contains"):
        checks["contains"] = all(os.path.isfile(os.path.join(ws, rel)) and re.search(pat, cc.read_text(os.path.join(ws, rel)))
                                 for rel, pat in sc["contains"].items())
    shutil.rmtree(tmp, ignore_errors=True)
    return {"scenario": sc["id"], "model": model, "passed": all(checks.values()), "checks": checks, "written": written,
            "model_seconds": secs, "seconds": round(time.time() - t0, 1), "reply": reply[:30000],
            "tests_head": tests_out.split("\n", 1)[0], "tests_out": tests_out[:5000], "hidden_out": hidden_out[:3000]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:e4b")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--only", default="")
    ap.add_argument("--lang", choices=["py", "cpp", "all"], default="all")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    scenarios = [s for s in SCENARIOS if (not only or s["id"] in only)
                 and (args.lang == "all" or (s.get("lang", "py") in ("c", "cpp")) == (args.lang == "cpp"))]
    out_dir = os.path.join(HERE, "results", time.strftime("%Y%m%d_%H%M%S") + f"_coding-bare_{args.model.replace(':', '-')}")
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for sc in scenarios:
        for i in range(args.runs):
            print(f"▶ {sc['id']}（第 {i + 1}/{args.runs} 次，不用 harness，{args.model}）…", flush=True)
            try:
                r = run_one(sc, args.model)
            except Exception as e:      # noqa: BLE001
                r = {"scenario": sc["id"], "model": args.model, "passed": False, "checks": {}, "error": str(e)[:500]}
            r["run"] = i + 1
            results.append(r)
            print(f"  {'✅' if r['passed'] else '❌'} {r.get('seconds')} 秒，寫了 {len(r.get('written') or [])} 個檔案，檢查 {r['checks']}"
                  + (f"，錯誤：{r['error']}" if r.get("error") else ""), flush=True)
            with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    lines = [f"# 自建 coding 情境：不用 harness 的對照組（{args.model}）", "",
             f"- 時間：{time.strftime('%Y-%m-%d %H:%M')}；每個情境呼叫一次模型（任務＋專案全部檔案的內容），直接寫回它輸出的檔案；"
             "沒有工具、規劃、測試回饋與重試。檢查跟 run_coding_evals.py 一樣（hidden tests 驗收）。",
             f"- **通過 {sum(1 for r in results if r['passed'])}/{len(results)}**", "",
             "| 情境 | 通過 | 檢查 | 寫了哪些檔案 | 秒數 |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['scenario']} | {'✅' if r['passed'] else '❌'} | {r['checks']} | {'、'.join(r.get('written') or []) or '—'} | "
                     f"{r.get('seconds', '—')} |")
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
