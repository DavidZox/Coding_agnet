"""DevBench（open-compass/DevEval）實作任務的子集：Python 7 個、C++ 5 個 repo。

DevBench 的實作任務：給 PRD、UML 類別圖與循序圖、架構設計，依程式檔的相依順序（code_file_DAG）寫出整個專案的原始碼，
再用官方的單元測試與驗收測試計分（Python 用 pytest、C++ 用 GoogleTest 與驗收腳本）。
- 版本固定在 DevEval 的 COMMIT；tree 是那個 commit 底下 benchmark_data/<語言>/<repo> 的 git tree SHA（下載的檔案用 git blob SHA-1
  逐一驗證，內容跟這個版本一模一樣）。
- unit／acceptance：參考實作在這個環境跑出來的通過數（prepare.py --verify 會重跑確認），也就是計分的分母——
  跟 DevBench 論文表格列的測試數一致；lines 是那張表的程式碼行數（論文的平均依它加權）。
- C++ 的驗收測試是 acceptance_tests/test.sh：數輸出裡每個通過的標記（marker）；people_management 的驗收測試是 pytest。
沒有選的：Hybrid_Images（參考實作的單元測試在這個環境本身就有 8 個失敗）、ArXiv_digest（驗收測試要連 arXiv 網站）、
TextCNN（要 PyTorch 與實際訓練）；Java／JavaScript 不在這個 harness 的範圍（Python、C／C++）。
資料授權：DevBench 的資料是 CC BY 4.0（程式碼 Apache 2.0），引用見 README.md。
"""
COMMIT = "bb593c1f9c535ff0dde0c9f4807d58c9566c3a6c"   # DevEval main，2024-05-30
REPO_URL = "https://github.com/open-compass/DevEval"

REPOS = {
    # ---- Python
    "readtime": {"lang": "python", "lines": 284, "tree": "166b668e95cdb8fd320c9607cbce1a000e4ac6fd", "unit": 8, "acceptance": 4},
    "particle-swarm-optimization": {"lang": "python", "lines": 168, "tree": "141d900444888dcc94f577749ad0601716f1527d", "unit": 5, "acceptance": 1},
    "chakin": {"lang": "python", "lines": 162, "tree": "d30e0e42f680299c4be787ac278b66232b84a866", "unit": 1, "acceptance": 1},
    "stocktrends": {"lang": "python", "lines": 384, "tree": "0bf720eaff9446dd5e35dd85d382117f09743d4f", "unit": 7, "acceptance": 2},
    "geotext": {"lang": "python", "lines": 470, "tree": "a7aa87daed326d4e3a36327addf34dd849ef7817", "unit": 4, "acceptance": 5},
    "hone": {"lang": "python", "lines": 274, "tree": "4fd4c24bdd27e8a7865c8a941a09ef7b07b1ea7f", "unit": 7, "acceptance": 5},
    "lice": {"lang": "python", "lines": 376, "tree": "9535bcb8cd1175ece188168c3cd9d8a54aea87b7", "unit": 25, "acceptance": 6},
    # ---- C++
    "area_calculation": {"lang": "cpp", "lines": 162, "tree": "6b2d51005f288e44efbbac12a898b61a32133a6e", "unit": 3, "acceptance": 3,
                         "marker": r"^File \d+\.txt matches"},
    "graph-cpp": {"lang": "cpp", "lines": 667, "tree": "806c0861b22267be9be11c929003e8f0c710ba5a", "unit": 22, "acceptance": 5,
                  "marker": r"^Test passed"},
    "logistic_system": {"lang": "cpp", "lines": 630, "tree": "9527576d52c6b3115235beb5c5a0e582c4f7fdf1", "unit": 17, "acceptance": 7,
                        "marker": r"\[PASSED\]"},
    "people_management": {"lang": "cpp", "lines": 540, "tree": "7f64fe405c93ca7cfea094f469046aefa243979d", "unit": 9, "acceptance": 7,
                          "acceptance_pytest": "acceptance_tests/acceptance_testing.py"},
    "xlsx2csv": {"lang": "cpp", "lines": 476, "tree": "2e6b70a31753ce90db18b13699676a90eb1f5ea9", "unit": 8, "acceptance": 5,
                 "marker": r"\[PASSED\]"},
}

# Python repo 的測試需要的套件（docs/requirements.txt 的聯集）；版本固定成驗證過的組合
PYTHON_REQUIREMENTS = ["pytest==9.1.1", "beautifulsoup4==4.15.0", "pyquery==2.1.0", "markdown2==2.5.5", "lxml==6.1.3",
                       "pandas==3.0.6", "numpy==2.5.3", "matplotlib==3.11.2", "progressbar2==4.6.0"]

# DevEval README 的實作任務結果（Pass@ 驗收測試、Pass@ 單元測試，%）：全部 22 個 repo（Python、C／C++、Java、JavaScript），
# 依程式碼行數加權平均（lines 就是那張表的 #code lines）。我們只跑 12 個 Python／C++ repo、agent 也不一樣，只能當量級參考。
PAPER_IMPLEMENTATION = {"GPT-4-Turbo-0125": (7.1, 8.0), "GPT-4-Turbo-1106": (6.9, 6.8), "GPT-3.5-Turbo": (4.2, 4.3),
                        "DeepSeek-Coder-33B-Instruct": (4.4, 5.5), "CodeLlama-34B-Instruct": (0.6, 0.5)}
