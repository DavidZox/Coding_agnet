"""DevBench 的「不用 harness」對照組（benchmark_study 的實驗 E2／E3）：同一個模型、同樣的規格文件與檔案清單，
一個檔案呼叫一次模型、直接寫出整份檔案——沒有工具、沒有編譯與測試的回饋、沒有重試，就像在聊天視窗裡請模型照規格寫。
清單寫完後再呼叫一次，請它補上架構設計裡列出、但清單沒有的檔案（__init__.py、makefile…）。計分跟 run.py 完全一樣
（evaluate.evaluate：官方測試換回原本的版本、required_files 換回原本的、照 setup 建目錄，再跑 pytest／gtest／驗收腳本）。

    python3 evals/devbench/bare.py --model gemma4:26b
    python3 evals/devbench/bare.py --model gemma4:26b --visible-tests    # 官方測試的內容也放進提示（看得到、不能執行）
    python3 evals/devbench/bare.py --only readtime,area_calculation

模型參數跟 coding worker 的內容通道一樣（temperature 0.2、num_ctx、num_predict、think=False）。結果在
evals/results/<時間>_devbench-bare_<模型>[_visible-tests]/：report.md、runs.jsonl、workspaces/<repo>/。
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT)
from agent_core.config import CODING_CONTENT_MAX_PREDICT, NUM_CTX  # noqa: E402
from evals.devbench import evaluate as ev  # noqa: E402
from evals.devbench import run as devrun  # noqa: E402
from evals.devbench.repos import REPOS  # noqa: E402
from skills_system.scripts import _code_common as cc  # noqa: E402

SYSTEM = ("你是資深的軟體工程師。依照規格文件寫出指定檔案的完整內容：類別與函式的名稱、參數、回傳值、命令列用法與輸出格式"
          "都要完全照文件。只輸出程式碼區塊，不要解釋。")
DOC_BUDGET = 40000      # 規格文件最多幾個字元（DevBench 的文件多半 1～2 萬字）
FILES_BUDGET = 30000    # 已經寫好的檔案最多幾個字元（超過時留最近寫的）
TESTS_BUDGET = 20000    # --visible-tests：官方測試最多幾個字元
FENCE_RE = re.compile(r"```[^\n`]*\n(.*?)```", re.S)
FILE_BLOCK_RE = re.compile(r"^#{2,4}\s*(?:檔案|File)?[:：]?\s*`?([\w./+-]+)`?\s*\n+```[^\n`]*\n(.*?)```", re.S | re.M)
SKIP_DIRS = ("unit_tests", "acceptance_tests", "tests", "test", "examples", "docs")


def chat(model, prompt):
    """呼叫一次模型 → (回覆文字, 統計)。Ollama 斷線時等一下再試（最多 3 次）。"""
    import ollama
    last = None
    for i in range(3):
        t0 = time.time()
        try:
            res = ollama.chat(model=model, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                              options={"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": CODING_CONTENT_MAX_PREDICT}, think=False)
        except Exception as e:      # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
            continue

        def field(name):
            try:
                return res[name]
            except (KeyError, TypeError):
                return getattr(res, name, None)

        return res["message"]["content"], {"seconds": round(time.time() - t0, 1), "prompt_tokens": field("prompt_eval_count") or 0,
                                           "eval_tokens": field("eval_count") or 0}
    raise RuntimeError(f"呼叫模型失敗：{last}")


def code_of(reply):
    """回覆裡最長的程式碼區塊（沒有區塊時用整段文字）。"""
    blocks = FENCE_RE.findall(reply or "")
    return (max(blocks, key=len) if blocks else (reply or "")).rstrip() + "\n"


def clip_files(files, budget):
    """{路徑: 內容} → 提示裡的「已經寫好的檔案」；超過 budget 時從最早寫的開始省略。"""
    out, total = [], 0
    for rel, text in reversed(list(files.items())):
        piece = f"## {rel}\n```\n{text.rstrip()}\n```"
        if total + len(piece) > budget:
            out.append(f"## （另外還有 {len(files) - len(out)} 個比較早寫好的檔案，為了長度省略）")
            break
        out.append(piece)
        total += len(piece)
    return "\n\n".join(reversed(out))


def read_tree(ws, rel_dirs, budget):
    """官方測試目錄裡的文字檔 → 提示裡的一段（--visible-tests）。"""
    parts, total = [], 0
    for d in rel_dirs:
        full = os.path.join(ws, d)
        if not os.path.isdir(full):
            continue
        for p, rel in cc.iter_files(full):
            text = cc.read_text(p)
            piece = f"## {os.path.join(d, rel)}\n```\n{text.rstrip()}\n```"
            if total + len(piece) > budget:
                parts.append("## （其餘的測試檔為了長度省略）")
                return "\n\n".join(parts)
            parts.append(piece)
            total += len(piece)
    return "\n\n".join(parts)


def run_repo(name, args, out_dir):
    cfg = ev.config(name)
    tmp = tempfile.mkdtemp(prefix="devbench_bare_")
    ws = os.path.join(tmp, "workspace")
    ev.make_workspace(name, ws, args.visible_tests)
    docs = "\n\n".join(f"## {rel}\n{cc.read_text(os.path.join(ws, rel))}" for rel in ev.doc_paths(cfg))[:DOC_BUDGET]
    tests = ""
    if args.visible_tests:
        tests = read_tree(ws, [cfg[k] for k in ("unit_tests", "acceptance_tests") if cfg.get(k)], TESTS_BUDGET)
    intro = ev.task_text(name, False)
    written, stats, t0 = {}, [], time.time()
    for rel in ev.dag_order(cfg):
        prompt = (f"{intro}\n\n# 規格文件\n{docs}\n\n"
                  + (f"# 官方測試（只能看、不能執行；最後用它們計分）\n{tests}\n\n" if tests else "")
                  + (f"# 已經寫好的檔案\n{clip_files(written, FILES_BUDGET)}\n\n" if written else "")
                  + f"# 現在要寫：{rel}\n寫出 {rel} 的完整內容（照架構設計裡這個檔案該有的類別、函式與介面）。只輸出一個程式碼區塊。")
        reply, st = chat(args.model, prompt)
        stats.append(dict(st, file=rel))
        written[rel] = code_of(reply)
        full = os.path.join(ws, rel)
        os.makedirs(os.path.dirname(full) or ws, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(written[rel])
    # 清單以外的檔案（套件的 __init__.py、makefile…）：再問一次
    prompt = (f"{intro}\n\n# 規格文件\n{docs}\n\n# 已經寫好的檔案\n{clip_files(written, FILES_BUDGET)}\n\n"
              "# 還缺的檔案\n架構設計的檔案結構裡列出、但上面還沒寫的原始檔或建置檔（例如套件的 __init__.py、makefile），"
              "每個檔案用下面的格式輸出完整內容：\n### 檔案：<路徑>\n```\n（完整內容）\n```\n"
              "不要輸出已經寫好的檔案、測試、範例或文件；沒有缺的檔案就只回「無」。")
    reply, st = chat(args.model, prompt)
    stats.append(dict(st, file="（補檔案）"))
    extra = []
    for rel, body in FILE_BLOCK_RE.findall(reply or ""):
        rel = rel.strip().lstrip("./")
        full = os.path.realpath(os.path.join(ws, rel))
        if (not full.startswith(os.path.realpath(ws) + os.sep) or os.path.exists(full) or rel in written
                or rel.split("/")[0] in SKIP_DIRS or rel.endswith((".md", ".txt"))):
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(body.rstrip() + "\n")
        extra.append(rel)
    seconds = round(time.time() - t0, 1)
    devrun.snapshot(ws, os.path.join(out_dir, "workspaces", name))
    score = ev.evaluate(name, ws)
    shutil.rmtree(tmp, ignore_errors=True)
    return {"repo": name, "lang": REPOS[name]["lang"], "job_status": "bare", "items": [], "seconds": seconds, "wall_seconds": seconds,
            "model_calls": len(stats), "prompt_tokens": sum(s["prompt_tokens"] for s in stats),
            "eval_tokens": sum(s["eval_tokens"] for s in stats), "calls": stats, "files": list(written), "extra_files": extra,
            "score": score}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:e4b")
    ap.add_argument("--only", default="")
    ap.add_argument("--lang", choices=["python", "cpp", "all"], default="all")
    ap.add_argument("--visible-tests", action="store_true", help="官方測試的內容也放進提示（模型看得到、但不能執行）")
    args = ap.parse_args()
    args.planner, args.bare = None, True
    if not os.path.exists(ev.VENV_PY) or not os.path.isdir(ev.DATA):
        raise SystemExit("先執行 python3 evals/devbench/prepare.py（下載資料、建立 .venv、檢查 gtest）")
    only = [n.strip() for n in args.only.split(",") if n.strip()]
    names = [n for n in (only or list(REPOS)) if args.lang == "all" or REPOS[n]["lang"] == args.lang]
    tag = args.model.replace(":", "-") + ("_visible-tests" if args.visible_tests else "")
    out_dir = os.path.join(PROJECT, "evals", "results", time.strftime("%Y%m%d_%H%M%S") + f"_devbench-bare_{tag}")
    os.makedirs(out_dir, exist_ok=True)
    title = (f"# DevBench 實作任務：不用 harness 的對照組（{args.model}，一個檔案呼叫一次模型，沒有工具與測試回饋）"
             + ("；官方測試的內容放在提示裡" if args.visible_tests else ""))
    results = []
    for name in names:
        print(f"▶ {name}（{REPOS[name]['lang']}，不用 harness，{args.model}）…", flush=True)
        try:
            r = run_repo(name, args, out_dir)
        except Exception as e:      # noqa: BLE001
            r = {"repo": name, "lang": REPOS[name]["lang"], "job_status": "error", "items": [], "error": str(e)[:500],
                 "wall_seconds": 0, "score": {"unit": 0, "unit_total": REPOS[name]["unit"], "acceptance": 0,
                                              "acceptance_total": REPOS[name]["acceptance"], "unit_tail": "", "acceptance_tail": ""}}
        results.append(r)
        s = r["score"]
        print(f"  單元 {s['unit']}/{s['unit_total']}、驗收 {s['acceptance']}/{s['acceptance_total']}；"
              f"{(r.get('seconds') or 0) / 60:.1f} 分鐘，模型呼叫 {r.get('model_calls')} 次"
              + (f"；錯誤：{r['error'][:200]}" if r.get("error") else ""), flush=True)
        with open(os.path.join(out_dir, "runs.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        devrun.write_report(os.path.join(out_dir, "report.md"), results, args, title=title)
    print(f"\n報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
