"""ProjectTest（arXiv 2502.06556，MIT）的 Python 專案 → 「幫多檔專案寫測試」的任務（6 個，3～11 個檔案）。

    python3 build_projecttest.py            # 產生工作區與任務
    python3 build_projecttest.py mutants    # 產生 mutant（沒有官方測試可以篩，全部保留；mutation score 用絕對值、只做條件之間的比較）

ProjectTest 沒有附官方測試（它評的是模型產生的測試：能不能跑、對不對、覆蓋率），所以這裡的 mutation score 分母是全部的 mutant
（含行為不變的等價 mutant），只能用來比較不同版本、不同模型，不能跟 DevBench 的「相對於官方測試」直接比。
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C          # noqa: E402
import mutate as M          # noqa: E402

SRC = os.path.join(C.STUDY, "datasets", "source", "ProjectTest", "dataset", "Python")
TASK_DIR = os.path.join(C.DATASET, "tasks")
WS_DIR = os.path.join(C.DATASET, "workspaces")
MUTANT_DIR = os.path.join(C.DATASET, "mutants")
SEED = 20261010
# 專案 → (工作區裡的佈局, 覆蓋率的 source)。mahjong、bridge 的 import 要同時把套件目錄與上一層放進 sys.path，換成 leducholdem、limitholdem
PROJECTS = {
    "slugify": ("package", ["slugify"]),
    "stock2": ("flat", ["."]),
    "structly": ("root", ["structly", "."]),
    "blackjack": ("package", ["blackjack"]),
    "leducholdem": ("package", ["leducholdem"]),
    "limitholdem": ("package", ["limitholdem"]),
}


def ws_of(name):
    return os.path.join(WS_DIR, f"tw_pt_{name}")


def build(name):
    layout, sources = PROJECTS[name]
    ws = ws_of(name)
    shutil.rmtree(ws, ignore_errors=True)
    os.makedirs(ws)
    src = os.path.join(SRC, name)
    ign = shutil.ignore_patterns(".DS_Store", "__pycache__")
    if layout == "package":
        shutil.copytree(src, os.path.join(ws, name), ignore=ign)
    else:                                    # flat：模組直接在根目錄；root：根目錄有模組＋子套件
        shutil.copytree(src, ws, ignore=ign, dirs_exist_ok=True)
    os.makedirs(os.path.join(ws, "tests"), exist_ok=True)
    prod = sorted(os.path.relpath(os.path.join(dp, fn), ws) for dp, dns, fns in os.walk(ws) for fn in fns
                  if fn.endswith(".py") and not dp.endswith("tests"))
    cov = " ".join(f"--cov={s}" for s in sources)
    with open(os.path.join(ws, ".coding_agent.md"), "w", encoding="utf-8") as f:
        f.write("# 開發環境說明\n\n- Python 3，套件已經裝好（pytest、coverage、pytest-cov、numpy、text_unidecode）。\n"
                "- 測試放在 `tests/`，從專案根目錄跑：`python -m pytest -q tests`\n"
                f"- 量覆蓋率（行＋分支）：`python -m pytest {cov} --cov-branch --cov-report=term-missing tests`\n")
    files = "、".join(f"`{p}`" for p in prod if not p.endswith("__init__.py"))
    task = (f"這個專案（{name}）目前沒有任何測試，請幫我補上，最後我會看過才合併：\n"
            f"1. 用 pytest 在 `tests/` 寫單元測試，涵蓋 {files} 裡的公開類別與函式，包含正常情況、邊界條件與錯誤處理。\n"
            "2. 測試要能在目前的程式上全部通過。不要修改正式程式；如果覺得程式本身有 bug，寫在回報裡就好。\n"
            "3. 完成後量測覆蓋率（行與分支），回報數字，並列出還沒涵蓋到、值得補測試的部分。")
    return {"id": f"tw_pt_{name}", "family": "tw", "source": "projecttest", "repo": name, "lang": "python",
            "workspace": os.path.relpath(ws, C.DATASET), "task": task, "test_dir": "tests", "prod_files": prod,
            "cov_sources": sources, "mutants": f"mutants/pt_{name}.json", "python": "devbench_venv"}


def mutants(name, limit=60):
    ws = ws_of(name)
    task = json.load(open(os.path.join(TASK_DIR, f"tw_pt_{name}.json"), encoding="utf-8"))
    points = {}
    for rel in task["prod_files"]:
        if rel.endswith("__init__.py"):
            continue
        with open(os.path.join(ws, rel), encoding="utf-8") as f:
            points[rel] = M.points_for(rel, f.read())
    chosen = M.sample(points, limit, seed=SEED)
    out = [{"id": f"pt_{name}#m{i}", "file": rel, "line": pt["line"], "desc": pt["desc"], "point": pt, "killed": None, "invalid": False}
           for i, (rel, pt) in enumerate(chosen)]
    os.makedirs(MUTANT_DIR, exist_ok=True)
    with open(os.path.join(MUTANT_DIR, f"pt_{name}.json"), "w", encoding="utf-8") as f:
        json.dump({"repo": name, "seed": SEED, "official_tests": 0, "mutants": out}, f, ensure_ascii=False, indent=1)
    print(f"{name}：{len(out)} 個 mutant")


def main():
    os.makedirs(TASK_DIR, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "mutants":
        for name in PROJECTS:
            mutants(name)
        return
    for name in PROJECTS:
        t = build(name)
        with open(os.path.join(TASK_DIR, f"{t['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, indent=1)
        print(t["id"], len(t["prod_files"]), "個檔案")


if __name__ == "__main__":
    main()
