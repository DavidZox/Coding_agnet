"""找出「計分紀錄被輸出交錯弄亂」的題目，在機器空閒時單獨重新計分。

官方評分腳本用 `set -x`，追蹤行（stderr）跟測試輸出（stdout）是兩條管道；機器負載高時，`: '>>>>> End Test Output'` 這一行可能
比後面的測試結果更早寫進紀錄，官方的 log parser 只讀起訖標記之間的內容，後面的測試就被當成沒通過。實測：fmt-1683 的參考解答在
同時跑 harness＋3 個平行計分時 P2P 只有 22/42，單獨重跑 42/42。

這支程式對每個結果目錄的每一題檢查 test_output.txt：結束標記之後還有測試結果（gtest 的 [ OK ]／[ FAILED ]、pytest 的 PASSED／FAILED、
django 的 ... ok／FAIL、redis 的 [ok]／[err]、doctest、jq 與 micropython 的 PASS／FAIL）就算可疑；可疑的題目用 1 個 worker 重新計分，
結果寫到 <結果目錄>/rescored.json（collect.py 會用它取代原本的分數，並記錄重新計分過）。所有條件用同一條規則。

    python3 evals/swebench/recheck.py <結果目錄> [<結果目錄> …]            # 只列出可疑的題目
    python3 evals/swebench/recheck.py --rescore <結果目錄> [<結果目錄> …]  # 重新計分
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from evals.swebench import evaluate  # noqa: E402

END_RE = re.compile(r"^\+ : '>>>>> End Test Output'")
RESULT_RE = re.compile(r"\[\s+OK\s+\]|\[\s+FAILED\s+\]|\bPASSED\b|\bFAILED\b|\.\.\. ok$|\.\.\. FAIL|\.\.\. ERROR|\[ok\]|\[err\]|^PASS:|^FAIL:|"
                       r"test cases?:|Status: (SUCCESS|FAILURE)")


def suspicious(test_output):
    """結束標記之後還有測試結果的行 → True。"""
    try:
        with open(test_output, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return False
    for i, line in enumerate(lines):
        if END_RE.match(line):
            return any(RESULT_RE.search(x) for x in lines[i + 1:] if not x.startswith("+ "))
    return False


def scan(result_dir):
    out = []
    path = os.path.join(result_dir, "runs.jsonl")
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            s = r.get("score") or {}
            d = s.get("log_dir")
            if d and suspicious(os.path.join(d, "test_output.txt")):
                out.append((r["instance_id"], r.get("patch") or "", s))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--rescore", action="store_true")
    args = ap.parse_args()
    for d in args.dirs:
        d = os.path.abspath(d)
        bad = scan(d)
        print(f"{os.path.basename(d)}：可疑 {len(bad)} 題 {[b[0] for b in bad]}")
        if not args.rescore or not bad:
            continue
        rescored_path = os.path.join(d, "rescored.json")
        rescored = {}
        if os.path.exists(rescored_path):
            with open(rescored_path, encoding="utf-8") as f:
                rescored = json.load(f)
        for iid, patch, old in bad:
            res = evaluate.evaluate_patch(iid, patch, "recheck", os.path.basename(d) + "_recheck")
            res["original"] = {k: old.get(k) for k in ("resolved", "f2p_pass", "f2p_fail", "p2p_pass", "p2p_fail")}
            rescored[iid] = res
            print(f"  {iid}：原本 resolved={old.get('resolved')} P2P {old.get('p2p_pass')}/{(old.get('p2p_pass') or 0) + (old.get('p2p_fail') or 0)}"
                  f" → 重新計分 resolved={res.get('resolved')} P2P {res.get('p2p_pass')}/{(res.get('p2p_pass') or 0) + (res.get('p2p_fail') or 0)}"
                  + ("（重新計分也可疑）" if res.get("log_dir") and suspicious(os.path.join(res["log_dir"], "test_output.txt")) else ""))
        with open(rescored_path, "w", encoding="utf-8") as f:
            json.dump(rescored, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
