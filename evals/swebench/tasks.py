"""SWE-bench 題目：讀題目檔、交給 harness 的任務文字、工作區的開發環境說明（.coding_agent.md）。

任務文字只有 issue 原文（problem_statement）＋固定的要求，跟 SWE-bench 的標準設定一樣不給 hints_text。
開發環境說明只寫「這個專案怎麼建置、怎麼跑測試」的通用格式（從官方評分腳本的指令歸納，例子刻意避開評分用的測試），
相當於開發者寫在 AGENTS.md／CLAUDE.md 裡的內容；評分用的測試（test_patch）agent 看不到。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
INSTANCES = os.path.join(HERE, "instances.json")

PY_TEST = "測試用 `python -m pytest <測試檔>`（例如 `python -m pytest {example}`；可以加 `-k <名稱>`）。"
HINTS = {
    "django/django": ("測試用 `python tests/runtests.py <測試模組>`（例如 `python tests/runtests.py utils_tests.test_text`；"
                      "設定預設是 tests/test_sqlite.py，可以加 `--parallel 1`）。這個專案的測試不是 pytest：測試在 tests/<模組>/ 底下。"),
    "sympy/sympy": ("測試用 `python bin/test <測試檔>`（例如 `python bin/test sympy/core/tests/test_basic.py`；可以加 `-k <名稱>`）。"
                    "這是 sympy 自己的測試程式。"),
    "sphinx-doc/sphinx": PY_TEST.format(example="tests/test_util_inspect.py"),
    "scikit-learn/scikit-learn": PY_TEST.format(example="sklearn/utils/tests/test_validation.py") + "C 擴充模組已經建好（沒有改 .pyx 就不用重新建置）。",
    "astropy/astropy": PY_TEST.format(example="astropy/utils/tests/test_misc.py") + "C 擴充模組已經建好。",
    "matplotlib/matplotlib": PY_TEST.format(example="lib/matplotlib/tests/test_colors.py") + "C 擴充模組已經建好。",
    "pydata/xarray": PY_TEST.format(example="xarray/tests/test_utils.py"),
    "pytest-dev/pytest": PY_TEST.format(example="testing/test_mark.py"),
    "pallets/flask": PY_TEST.format(example="tests/test_basic.py"),
    "psf/requests": PY_TEST.format(example="tests/test_utils.py"),
    "pylint-dev/pylint": PY_TEST.format(example="tests/test_self.py"),
    "mwaskom/seaborn": PY_TEST.format(example="tests/test_utils.py"),
    "redis/redis": ("建置：在根目錄執行 `make`（約 1～2 分鐘，產生 src/redis-server）。測試：`./runtest --single unit/<測試檔，不含 .tcl>`"
                    "（例如 `./runtest --single unit/type/incr`，要先 make；可以加 `--only \"<測試名稱的樣式>\"`）。測試是 Tcl 寫的，在 tests/ 底下。"),
    "jqlang/jq": ("已經 configure 過。建置：`make -j8`（產生 ./jq）。測試：`make check`（測試資料在 tests/*.test），"
                  "或用建好的 `./jq` 直接試運算式，例如 `echo '[1,2]' | ./jq '.[0]'`。"),
    "micropython/micropython": ("建置：`make -C mpy-cross && make -C ports/unix VARIANT=standard`（產生 ports/unix/build-standard/micropython）。"
                                "測試：`cd tests && MICROPY_MICROPYTHON=../ports/unix/build-standard/micropython ./run-tests.py <測試檔>`"
                                "（例如 `basics/list1.py`；測試的預期輸出由 CPython 跑同一個檔案產生）。"),
    "fmtlib/fmt": ("建置與測試用 CMake：`cmake -B build -S . && cmake --build build --parallel 8 --target <測試名稱> && "
                   "ctest --test-dir build -R <測試名稱>`（測試名稱例如 core-test，對應 test/core-test.cc；測試用 GoogleTest）。"),
    "nlohmann/json": ("建置與測試用 CMake：`cmake -S . -B build -DJSON_BuildTests=ON && cmake --build build --target test-<名稱>_cpp11 && "
                      "./build/tests/test-<名稱>_cpp11`（<名稱> 對應 tests/src/unit-<名稱>.cpp，例如 conversions；測試用 doctest）。"
                      "函式庫本體是 include/nlohmann/ 底下的標頭檔（single_include/ 是合併後的版本）。"),
}


def load(path=INSTANCES):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def by_id(path=INSTANCES):
    return {r["instance_id"]: r for r in load(path)}


def rules_text(inst):
    return ("# 這個專案的開發環境\n\n"
            f"- 專案：{inst['repo']}（{inst['lang']}）。工作區就是這個 git repo 的根目錄，版本停在 issue 回報時。\n"
            f"- 建置與測試：{HINTS[inst['repo']]}\n"
            "- 建置、測試、執行程式的指令會在專案的開發環境（Docker 容器）裡執行，路徑跟這裡一樣；環境已經裝好，"
            "不能連網路、不能安裝套件。\n")


def task_text(inst):
    return (f"請修正這個既有專案（{inst['repo']}，{inst['lang']}）的問題。下面是 GitHub issue 的原文：\n\n"
            f"<issue>\n{inst['problem_statement'].strip()}\n</issue>\n\n"
            "要求：\n"
            "- 修改專案的原始碼來解決這個問題；不要改變跟問題無關的行為，也不要為了讓測試通過而修改既有的測試。\n"
            "- 可以新增測試來確認修正，但評分會用另外準備的測試（你看不到）。\n"
            "- 建置與測試的方法見工作區的 .coding_agent.md；環境已經裝好，不能連網路、不能安裝套件。")
