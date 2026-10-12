"""把第三次評測的原始紀錄收進 results/raw/（評測跑在 ~/cah_eval 的凍結副本裡）。

    python3 benchmark_study_3/analysis/gather_raw.py

- ~/cah_eval/<版本>/evals/results/2026*_{ops,ops_holdout,smallproj}_*_<tag> → results/raw/<版本>/<目錄>/（runs.jsonl、report.md、
  小專案的 patches/）；tag 是 v42_r<N>、v5_r<N>（正式的執行）。開發時的試跑（tag 不是這個格式）不收。
- 每個結果目錄是用哪一份凍結副本跑的，寫進 HARNESS_VERSION.txt（agent 程式的雜湊）。
- 小專案的 workspaces/（agent 最後的工作區）很大，不收；要重新計分用 patches/ 套回範本即可。
"""
import argparse
import glob
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
RAW = os.path.join(STUDY, "results", "raw")
EVAL = os.path.expanduser("~/cah_eval")
NAME_RE = re.compile(r"^2026\d{4}_\d{6}_(ops_holdout|ops|smallproj)_gemma4-[a-z0-9]+_(v42|v5)_r\d+$")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw", default=RAW, help="收到哪裡（預設 results/raw）")
    raw = ap.parse_args().raw
    copied = []
    for version in ("v4.2", "v5"):
        vdir = os.path.join(EVAL, version)
        try:
            with open(os.path.join(vdir, "AGENT_CODE_HASH.txt"), encoding="utf-8") as f:
                code_hash = f.read().strip()
        except OSError:
            code_hash = "?"
        for d in sorted(glob.glob(os.path.join(vdir, "evals", "results", "2026*"))):
            name = os.path.basename(d)
            if not NAME_RE.match(name):
                continue
            dst = os.path.join(raw, version, name)
            shutil.copytree(d, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "workspaces"))
            with open(os.path.join(dst, "HARNESS_VERSION.txt"), "w", encoding="utf-8") as f:
                f.write(f"凍結副本：~/cah_eval/{version}\nagent 程式的雜湊：{code_hash}\n")
            copied.append((version, name))
    for version, name in copied:
        print(f"{version}／{name}")
    print(f"共 {len(copied)} 個目錄 → {os.path.relpath(raw, STUDY)}")


if __name__ == "__main__":
    main()
