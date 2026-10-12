"""Aider polyglot benchmark（Exercism 的題目）→ 能力對照用的小任務：Python 10 題、C++ 10 題（固定種子抽樣）。

    python3 build_aider.py

- 工作區＝題目目錄（說明、待完成的檔案、測試），不含 .meta（參考解答）。測試留在工作區（跟「小而有測試的專案」一樣看得到）——
  Aider 原本的規則是看不到測試、失敗後給一次測試輸出，所以這裡的數字只能跟公開成績比量級。
- C++：CMakeLists.txt 開啟 EXERCISM_RUN_ALL_TESTS（Aider 跑分時也開，不然大部分測試是關的），並加上 enable_testing／add_test
  讓 ctest 找得到測試；建置本身就會跑測試（題目原本的設計）。
- 計分：把原本的測試檔放回去（agent 改過也不算），全部通過才算解決。
"""
import json
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C          # noqa: E402

SRC = os.path.join(C.STUDY, "datasets", "source", "polyglot-benchmark")
TASK_DIR = os.path.join(C.DATASET, "tasks")
WS_DIR = os.path.join(C.DATASET, "workspaces")
SEED = 20261010
PER_LANG = 10


def exercises(lang):
    root = os.path.join(SRC, lang, "exercises", "practice")
    return sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_one(lang, name):
    src = os.path.join(SRC, lang, "exercises", "practice", name)
    tid = f"ap_{lang}_{name.replace('-', '_')}"
    ws = os.path.join(WS_DIR, tid)
    shutil.rmtree(ws, ignore_errors=True)
    shutil.copytree(src, ws, ignore=shutil.ignore_patterns(".meta"))
    docs = [os.path.join(".docs", fn) for fn in ("introduction.md", "instructions.md", "instructions.append.md")
            if os.path.exists(os.path.join(ws, ".docs", fn))]
    stem = name.replace("-", "_")
    if lang == "python":
        impl = [f"{stem}.py"]
        tests = [fn for fn in os.listdir(ws) if fn.endswith("_test.py")]
        notes = "# 開發環境說明\n\n- Python 3、pytest 已經裝好。\n- 跑測試：`python -m pytest -q`\n"
    else:
        impl = [fn for fn in (f"{stem}.h", f"{stem}.cpp") if os.path.exists(os.path.join(ws, fn))]
        tests = [f"{stem}_test.cpp", "test"]
        cm = os.path.join(ws, "CMakeLists.txt")
        text = read(cm)
        # 題目名稱原本取自所在目錄的名稱（工作區的目錄名不一樣就找不到檔案）→ 直接寫死
        text = text.replace("get_filename_component(exercise ${CMAKE_CURRENT_SOURCE_DIR} NAME)", f"set(exercise {name})")
        text = "set(EXERCISM_RUN_ALL_TESTS ON)\n" + text + "\n# 評測加上的：讓 ctest 找得到測試\nenable_testing()\nadd_test(NAME ${exercise} COMMAND ${exercise})\n"
        with open(cm, "w", encoding="utf-8") as f:
            f.write(text)
        notes = ("# 開發環境說明\n\n- C++17、CMake（Catch2 測試已經附在 test/）。\n"
                 "- 建置並跑測試：`cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure`"
                 "（建置時也會自動跑一次測試，測試失敗會讓建置失敗）\n")
    with open(os.path.join(ws, ".coding_agent.md"), "w", encoding="utf-8") as f:
        f.write(notes)
    doc_list = "、".join(f"`{d}`" for d in docs)
    impl_list = "、".join(f"`{p}`" for p in impl)
    test_list = "、".join(f"`{t}`" for t in tests if not t == "test")
    task = (f"請照 {doc_list} 的說明完成 {impl_list}（目前只有空的骨架）。測試在 {test_list}，"
            "要全部通過；測試是對的，不要修改測試。")
    return {"id": tid, "family": "ap", "source": "aider_polyglot", "repo": name, "lang": "python" if lang == "python" else "cpp",
            "workspace": os.path.relpath(ws, C.DATASET), "task": task, "impl_files": impl, "test_files": tests,
            "python": "devbench_venv"}


def main():
    rng = random.Random(SEED)
    os.makedirs(TASK_DIR, exist_ok=True)
    made = []
    for lang in ("python", "cpp"):
        names = exercises(lang)
        for name in sorted(rng.sample(names, PER_LANG)):
            t = build_one(lang, name)
            with open(os.path.join(TASK_DIR, f"{t['id']}.json"), "w", encoding="utf-8") as f:
                json.dump(t, f, ensure_ascii=False, indent=1)
            made.append(t["id"])
    print("Aider polyglot 任務：", ", ".join(made))


if __name__ == "__main__":
    main()
