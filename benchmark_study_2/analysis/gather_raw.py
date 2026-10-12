"""把評測的原始紀錄收進 results/raw/（評測跑在 ~/cah_eval 的凍結副本裡，結果與官方計分紀錄都在那邊）。

    python3 benchmark_study_2/analysis/gather_raw.py

- ~/cah_eval/<版本>/evals/results/2026*_{devbench,swebench}* → results/raw/<目錄>/（runs.jsonl、report.md、DevBench 的 workspaces/、
  SWE-bench 的 patches/）；冒煙測試（_smoke）與中途停掉的（_aborted）也收，collect.py 不算它們。
- SWE-bench 每一題的官方計分紀錄（report.json、test_output.txt、patch.diff、eval.sh、run_instance.log）→ results/raw/<目錄>/official_eval/<題目>/；
  重新計分過的（rescored.json）一起收。超過 3 MB 的測試輸出只留頭尾各 1 MB。
- 參考解答的計分驗證（evaluate.py --gold）→ results/raw/gold_check/。
- 每個結果目錄是用哪一份凍結副本跑的，寫進 results/raw/<目錄>/HARNESS_VERSION.txt（agent 程式的雜湊）。
"""
import argparse
import glob
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
RAW = os.path.join(STUDY, "results", "raw")
EVAL = os.path.expanduser("~/cah_eval")
LOG_FILES = ("report.json", "test_output.txt", "patch.diff", "eval.sh", "run_instance.log")
MAX_LOG = 3 * 1024 * 1024


def copy_log(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.getsize(src) <= MAX_LOG:
        shutil.copy2(src, dst)
        return
    with open(src, "rb") as f:
        data = f.read()
    keep = MAX_LOG // 3
    with open(dst, "wb") as f:
        f.write(data[:keep] + f"\n…（中間省略 {len(data) - 2 * keep} 位元組）…\n".encode() + data[-keep:])


def copy_eval_logs(log_dir, dst_dir):
    if not log_dir or not os.path.isdir(log_dir):
        return 0
    n = 0
    for name in LOG_FILES:
        p = os.path.join(log_dir, name)
        if os.path.isfile(p):
            copy_log(p, os.path.join(dst_dir, name))
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw", default=RAW, help="收到哪裡（預設 results/raw）")
    raw = ap.parse_args().raw
    os.makedirs(raw, exist_ok=True)
    copied = []
    for version_dir in sorted(glob.glob(os.path.join(EVAL, "v4*"))):
        version = os.path.basename(version_dir)
        try:
            with open(os.path.join(version_dir, "AGENT_CODE_HASH.txt"), encoding="utf-8") as f:
                code_hash = f.read().strip()
        except OSError:
            code_hash = "?"
        for d in sorted(glob.glob(os.path.join(version_dir, "evals", "results", "2026*"))):
            name = os.path.basename(d)
            if not ("_devbench" in name or "_swebench" in name):
                continue
            dst = os.path.join(raw, name)
            shutil.copytree(d, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
            with open(os.path.join(dst, "HARNESS_VERSION.txt"), "w", encoding="utf-8") as f:
                f.write(f"凍結副本：~/cah_eval/{version}\nagent 程式的雜湊：{code_hash}\n")
            logs = 0
            runs = os.path.join(d, "runs.jsonl")
            if "_swebench" in name and os.path.exists(runs):
                with open(runs, encoding="utf-8") as f:
                    for line in f:
                        r = json.loads(line)
                        logs += copy_eval_logs((r.get("score") or {}).get("log_dir"), os.path.join(dst, "official_eval", r["instance_id"]))
                resc = os.path.join(d, "rescored.json")
                if os.path.exists(resc):
                    with open(resc, encoding="utf-8") as f:
                        for iid, res in json.load(f).items():
                            logs += copy_eval_logs(res.get("log_dir"), os.path.join(dst, "official_eval_rescored", iid))
            copied.append((name, version, logs))
    gold_dst = os.path.join(raw, "gold_check")
    for run_dir in sorted(glob.glob(os.path.join(EVAL, "swe", "eval", "logs", "run_evaluation", "gold*"))):
        for inst_dir in glob.glob(os.path.join(run_dir, "gold", "*")):
            copy_eval_logs(inst_dir, os.path.join(gold_dst, os.path.basename(run_dir), os.path.basename(inst_dir)))
    for js in glob.glob(os.path.join(EVAL, "swe", "eval", "gold*.json")):
        os.makedirs(gold_dst, exist_ok=True)
        shutil.copy2(js, gold_dst)
    for name, version, logs in copied:
        print(f"{name}（{version}）" + (f"：官方計分紀錄 {logs} 個檔" if logs else ""))
    print(f"參考解答的計分驗證 → {os.path.relpath(gold_dst, STUDY)}")


if __name__ == "__main__":
    main()
