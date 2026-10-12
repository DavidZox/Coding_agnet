"""SWE-bench 子集的「不用 harness」對照組：同一個模型、同樣的 issue，用關鍵字檢索（BM25，跟 SWE-bench 論文的 RAG 基準一樣）
找出可能相關的原始檔放進提示，模型一次寫出修改（SEARCH/REPLACE 區塊）——沒有工具、沒有探索、不能建置或跑測試、沒有重試。
修改套到 repo 後的 git diff 就是 patch，計分跟 run.py 完全一樣（官方 swebench 套件）。

    python3 evals/swebench/bare.py --model gemma4:26b
    python3 evals/swebench/bare.py --model qwen2.5-coder:32b --only django__django-12276

檢索：issue 文字當查詢，對 repo 的原始檔（不含測試、文件、範例、第三方程式）算 BM25（k1=1.2、b=0.75；識別字會拆開 snake_case
與 camelCase）；依分數放進提示，總長度上限 FILES_BUDGET 字元；單一檔案太長時只放跟 issue 最相關的段落（每段 150 行，取前兩段）。
模型參數跟 coding worker 的內容通道一樣（temperature 0.2、num_ctx、num_predict、think=False）。
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT)
from agent_core.config import CODING_CONTENT_MAX_PREDICT, NUM_CTX  # noqa: E402
from evals.swebench import env, tasks  # noqa: E402
from skills_system.scripts import _code_common as cc  # noqa: E402
from evals.swebench.run import Scorer, patch_stats, write_report  # noqa: E402

SYSTEM = ("你是資深的軟體工程師。根據 issue 修改專案的原始碼來解決問題。只輸出 SEARCH/REPLACE 區塊，不要解釋。")
FILES_BUDGET = 60000     # 提示裡原始檔的總字元數上限（約 1.8 萬 tokens；num_ctx 32768 還留得下輸出）
BIG_FILE = 20000         # 超過這麼多字元的檔案只放最相關的段落
CHUNK_LINES = 150
EXTS = {"Python": {".py"}, "C": {".c", ".h"}, "C++": {".h", ".hpp", ".hh", ".hxx", ".cc", ".cpp", ".cxx", ".ipp", ".inl"}}
SKIP_PARTS = {"tests", "test", "testing", "docs", "doc", "examples", "example", "benchmarks", "asv_bench", "deps", "modules",
              "3rdparty", "third_party", "vendor", "single_include", "build", ".git", "node_modules"}
WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BLOCK_RE = re.compile(r"<<<<<<< SEARCH\n(.*?)\n?=======\n(.*?)\n?>>>>>>> REPLACE", re.S)
FILE_LINE_RE = re.compile(r"^\s*(?:#+\s*)?(?:\*\*)?(?:檔案|File|file|Path|path)?\s*[:：]?\s*`?([\w./+-]+\.\w+)`?(?:\*\*)?\s*$")


def tokens(text):
    out = []
    for w in WORD_RE.findall(text):
        lw = w.lower()
        out.append(lw)
        parts = [p for p in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", w) if p]
        if len(parts) > 1:
            out += [p.lower() for p in parts]
    return out


def source_files(root, lang):
    exts = EXTS[lang] | (EXTS["C"] if lang == "C++" else set())
    for dirpath, dirnames, files in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = [d for d in dirnames if d not in SKIP_PARTS and not d.startswith(".")]
        if rel_dir != "." and any(p in SKIP_PARTS for p in rel_dir.split(os.sep)):
            continue
        for fn in files:
            if os.path.splitext(fn)[1] not in exts:
                continue
            if fn.startswith("test_") or fn.endswith(("_test.py", "_tests.py")) or fn == "conftest.py":
                continue
            yield os.path.normpath(os.path.join(rel_dir, fn))


class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.docs = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = sum(self.len) / max(1, len(self.len))
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.k1, self.b = k1, b

    def score(self, i, query):
        d, L = self.docs[i], self.len[i]
        s = 0.0
        for t in query:
            f = d.get(t)
            if f:
                s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / self.avg))
        return s


def retrieve(root, lang, issue):
    """→ (提示裡的檔案段落, 放進去的檔案清單)。"""
    paths = list(source_files(root, lang))
    texts = {}
    for rel in paths:
        try:
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                texts[rel] = f.read()
        except OSError:
            pass
    paths = [p for p in paths if p in texts]
    bm = BM25([tokens(p) * 3 + tokens(texts[p][:200000]) for p in paths])
    q = set(tokens(issue))
    ranked = sorted(range(len(paths)), key=lambda i: -bm.score(i, q))
    parts, used, total = [], [], 0
    for i in ranked[:40]:
        rel, text = paths[i], texts[paths[i]]
        if len(text) > BIG_FILE:
            lines = text.split("\n")
            chunks = [(s, "\n".join(lines[s:s + CHUNK_LINES])) for s in range(0, len(lines), CHUNK_LINES)]
            cb = BM25([tokens(c) for _, c in chunks])
            best = sorted(sorted(range(len(chunks)), key=lambda j: -cb.score(j, q))[:2])
            piece = "\n\n".join(f"## {rel}（第 {chunks[j][0] + 1}～{min(len(lines), chunks[j][0] + CHUNK_LINES)} 行，節錄）\n"
                                f"```\n{chunks[j][1]}\n```" for j in best)
        else:
            piece = f"## {rel}\n```\n{text.rstrip()}\n```"
        if total + len(piece) > FILES_BUDGET:
            continue
        parts.append(piece)
        used.append(rel)
        total += len(piece)
        if total > FILES_BUDGET * 0.95:
            break
    return "\n\n".join(parts), used


def parse_blocks(reply):
    """回覆 → [(檔案, search, replace)]：每個 SEARCH 區塊往前找最近一行看起來像路徑的字串當檔案；找不到就沿用前一個區塊的檔案
    （模型對同一個檔案連續寫好幾個區塊時，常常只在第一個前面寫路徑）。"""
    out = []
    text = reply or ""
    last_path = None
    prev_end = 0
    for m in BLOCK_RE.finditer(text):
        before = text[prev_end:m.start()].rstrip("\n` \t").split("\n")
        path = None
        for line in reversed(before[-6:]):
            fm = FILE_LINE_RE.match(line.strip().strip("`"))
            if fm:
                path = fm.group(1).lstrip("./")
                break
        path = path or last_path
        last_path = path
        prev_end = m.end()
        out.append((path, m.group(1), m.group(2)))
    return out


def apply_blocks(root, blocks, default_file=None):
    """把 SEARCH/REPLACE 套到檔案上，比對方式跟 harness 的 code_edit 一樣（_code_common.apply_block：逐字 → 忽略行尾空白 →
    忽略縮排，對到多個位置不改）→ 失敗的說明清單。檔案不存在而 SEARCH 是空的：當成新檔案。"""
    failures = []
    for path, search, replace in blocks:
        path = path or default_file
        if not path:
            failures.append("區塊沒有寫檔案路徑")
            continue
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            if not search.strip():      # 新檔案
                os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(replace.rstrip("\n") + "\n")
                continue
            failures.append(f"{path}：檔案不存在")
            continue
        with open(full, encoding="utf-8", errors="replace") as f:
            text = f.read()
        new_text, _mode, err = cc.apply_block(text, cc.strip_line_numbers(search), replace)
        if err:
            failures.append(f"{path}：{err.splitlines()[0][:200]}")
            continue
        with open(full, "w", encoding="utf-8") as f:
            f.write(new_text)
    return failures


def chat(model, prompt):
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


def run_instance(inst, args, work):
    iid = inst["instance_id"]
    root = os.path.join(work, iid)
    t0 = time.time()
    r = {"instance_id": iid, "repo": inst["repo"], "lang": inst["lang"], "difficulty": inst.get("difficulty", ""), "bare": True}
    try:
        env.copy_testbed(inst["image"], root)
        pre = [u for u in env.sh(["git", "-C", root, "ls-files", "--others", "--exclude-standard", "-z"]).split("\0") if u]
        files_text, used = retrieve(root, inst["lang"], inst["problem_statement"])
        prompt = (f"請修正這個既有專案（{inst['repo']}，{inst['lang']}）的問題。GitHub issue 的原文：\n\n"
                  f"<issue>\n{inst['problem_statement'].strip()}\n</issue>\n\n"
                  f"# 用關鍵字檢索找到、可能相關的原始檔（不一定包含全部需要的檔案；長的檔案只節錄相關段落）\n\n{files_text}\n\n"
                  "# 輸出格式\n每一處修改寫一個區塊，區塊前一行寫檔案路徑（相對於 repo 根目錄）：\n"
                  "### 檔案：path/to/file\n<<<<<<< SEARCH\n（原本的程式碼：要跟檔案裡的完全一樣，包含縮排；多帶幾行讓它在檔案裡唯一）\n"
                  "=======\n（修改後的程式碼）\n>>>>>>> REPLACE\n\n"
                  "可以有多個區塊。修改原始碼來解決 issue；不要修改測試，也不要改跟問題無關的程式。")
        reply, st = chat(args.model, prompt)
        blocks = parse_blocks(reply)
        failures = apply_blocks(root, blocks, used[0] if len(used) == 1 else None)
        patch, notes = env.make_patch(root, inst["base_commit"], pre)
        gold = [l.split(" b/", 1)[-1] for l in inst["patch"].splitlines() if l.startswith("diff --git ")]
        r.update(gold_files=gold, retrieval_hit=sorted(set(gold) & set(used)), retrieved=used, blocks=len(blocks), apply_failures=failures, reply=reply[-12000:], patch=patch,
                 patch_notes=notes, patch_stats=patch_stats(patch), model_calls=1, **st)
    except Exception as e:      # noqa: BLE001
        r.update(error=str(e)[-2000:], patch="")
    r["wall_seconds"] = round(time.time() - t0, 1)
    shutil.rmtree(root, ignore_errors=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:26b")
    ap.add_argument("--only", default="")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    args.planner = None
    only = [x.strip() for x in args.only.split(",") if x.strip()]
    insts = [i for i in tasks.load() if not only or i["instance_id"] in only]
    tag = args.model.replace(":", "-") + (f"_{args.tag}" if args.tag else "")
    out_dir = os.path.join(PROJECT, "evals", "results", time.strftime("%Y%m%d_%H%M%S") + f"_swebench-bare_{tag}")
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(env.ROOT, "bare", os.path.basename(out_dir))
    title = f"# SWE-bench 子集：不用 harness（BM25 檢索＋一次寫出修改），模型 {args.model}"
    scorer = Scorer(out_dir, "bare_" + tag, lambda results: write_report(os.path.join(out_dir, "report.md"), results, args,
                                                                          title=title, bare=True))
    for inst in insts:
        print(f"▶ {inst['instance_id']}（{inst['lang']}，{args.model}，不用 harness）…", flush=True)
        r = run_instance(inst, args, work)
        st = r.get("patch_stats") or {}
        print(f"  {r.get('seconds', '?')} 秒、{r.get('blocks', 0)} 個區塊、套用失敗 {len(r.get('apply_failures') or [])}、"
              f"patch {len(st.get('files') or [])} 個檔案" + (f"；錯誤：{r['error'][:200]}" if r.get("error") else ""), flush=True)
        scorer.put(r)
    scorer.close()
    shutil.rmtree(work, ignore_errors=True)
    print(f"\n報表：{os.path.join(out_dir, 'report.md')}")


if __name__ == "__main__":
    main()
