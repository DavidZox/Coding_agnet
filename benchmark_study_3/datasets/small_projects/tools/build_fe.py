"""「補回一個跨檔功能」（fe）的任務：從 DevBench 的參考實作拿掉一個跨 2～5 個檔案的功能（程式＋相關的單元測試），
請 agent 照需求補回來，計分用完整的官方單元＋驗收測試。

規格在 ../fe_specs.json（每個 repo 一個），格式：
  {"repo": "logistic_system",
   "feature": "簡短名稱",
   "request": "給 agent 的需求（像使用者寫的 issue／需求說明，寫清楚行為；不要貼程式碼）",
   "files": ["src/logistics.cpp", "include/logistics.h", "src/main.cpp"],      # 預期要改的檔案（只用來統計）
   "edits": [{"file": "src/logistics.cpp", "old": "<原文，必須剛好出現一次>", "new": "<替換後的內容，通常是空字串或骨架>"}, ...]}
edits 同時用在正式程式（拿掉功能）與單元測試檔（拿掉那個功能的測試，讓看得到的測試在拿掉功能後仍然全部通過）。

    python3 build_fe.py check [--only repo]   # 套用規格並檢查：拿掉後看得到的測試全過、完整的官方測試有失敗
    python3 build_fe.py tasks                  # 產生 ../tasks/fe_<repo>.json 與 ../workspaces/fe_<repo>/
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_devbench as B  # noqa: E402
import common as C          # noqa: E402

SPECS = os.path.join(C.DATASET, "fe_specs.json")


def load_specs():
    with open(SPECS, encoding="utf-8") as f:
        return json.load(f)


def apply_edits(ws, spec):
    for e in spec["edits"]:
        path = os.path.join(ws, e["file"])
        with open(path, encoding="utf-8") as f:
            text = f.read()
        n = text.count(e["old"])
        if n != 1:
            raise ValueError(f"{spec['repo']}：{e['file']} 裡要替換的原文出現 {n} 次（要剛好 1 次）：{e['old'][:80]!r}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(e["old"], e["new"], 1))


def make_ws(spec, dst):
    name = spec["repo"]
    shutil.rmtree(dst, ignore_errors=True)
    C.copytree(B.repo_path(name), dst)
    for rel in ("acceptance_tests", *B.DROP):
        p = os.path.join(dst, rel)
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    B.make_setup_dirs(name, dst)
    if name in B.CPP:
        B.write_makefile(name, dst)
    apply_edits(dst, spec)
    with open(os.path.join(dst, ".coding_agent.md"), "w", encoding="utf-8") as f:
        f.write(B.coding_notes(name))
    return dst


def visible_tests_pass(name, ws):
    if name in B.PY:
        cases, code, out = C.pytest_cases(ws, [B.test_dir(name)])
    else:
        cases, code, out = C.gtest_cases(ws)
    return code == 0 and bool(cases), len(cases), out


def check(spec):
    import score as S
    name = spec["repo"]
    tmp = tempfile.mkdtemp(prefix=f"sp_fe_{name}_")
    try:
        ws = make_ws(spec, os.path.join(tmp, "ws"))
        ok_vis, n_vis, out = visible_tests_pass(name, ws)
        full = S.score_devbench_suite({"repo": name, "test_dir": B.test_dir(name), "id": f"fe_{name}"}, ws)
        ref = S.score_devbench_suite({"repo": name, "test_dir": B.test_dir(name), "id": f"fe_{name}"}, B.repo_path(name))
        problems = []
        if not ok_vis:
            problems.append(f"拿掉功能後，看得到的測試沒有全過（{n_vis} 個）：{out[-1200:]}")
        if full["resolved"]:
            problems.append("拿掉功能後，完整的官方測試仍然全過——功能沒有真的被拿掉，或官方測試測不到它")
        if not ref["resolved"]:
            problems.append(f"參考實作的官方測試沒有全過：{ref}")
        status = "✅" if not problems else "❌"
        print(f"{status} {name}：看得到的測試 {n_vis} 個{'全過' if ok_vis else '沒有全過'}；拿掉功能後官方單元 "
              f"{full['unit']}/{full['unit_total']}、驗收 {full['acceptance']}/{full['acceptance_total']}", flush=True)
        for p in problems:
            print("   ", p[:1500])
        return not problems
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_tasks(only=None):
    os.makedirs(B.TASK_DIR, exist_ok=True)
    for spec in load_specs():
        name = spec["repo"]
        if only and name not in only:
            continue
        tid = f"fe_{name}"
        ws = make_ws(spec, os.path.join(B.WS_DIR, tid))
        cmd = f"python -m pytest -q {B.test_dir(name)}" if name in B.PY else "make -f makefile_test test"
        task = (f"{spec['request'].strip()}\n\n"
                f"要求：照這個專案現有的寫法與檔案結構實作（可能要改好幾個檔案）；同時在 `{B.test_dir(name)}/` 補上這個功能的單元測試。"
                f"既有的測試（`{cmd}`）要維持全部通過，不要修改既有的測試。")
        t = {"id": tid, "family": "fe", "source": "devbench", "repo": name, "lang": "python" if name in B.PY else "cpp",
             "workspace": os.path.relpath(ws, C.DATASET), "task": task, "test_dir": B.test_dir(name), "feature": spec["feature"],
             "expected_files": spec.get("files", []), "ref_files": sorted({e["file"] for e in spec["edits"]}),
             "python": "devbench_venv"}
        with open(os.path.join(B.TASK_DIR, f"{tid}.json"), "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, indent=1)
        print(tid, "→", ws)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "tasks"])
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = args.only.split(",") if args.only else None
    if args.cmd == "check":
        results = [check(s) for s in load_specs() if not only or s["repo"] in only]
        print(f"{sum(results)}/{len(results)} 通過")
    else:
        build_tasks(only)


if __name__ == "__main__":
    main()
