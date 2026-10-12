# SWE-bench 子集的來源與授權

| 檔案 | 來源 | 版本 | 授權 |
|---|---|---|---|
| `source/SWE-bench_Verified.json` | Hugging Face `SWE-bench/SWE-bench_Verified`（test split，500 題） | 資料集 revision `78f471bf655a3137b2e8a75af1501690ec009ec3`，2026-10-09 下載 | SWE-bench 專案為 MIT；題目內容（issue、程式碼）屬於各原始 repo 與其授權 |
| `source/SWE-bench_Multilingual.json` | Hugging Face `SWE-bench/SWE-bench_Multilingual`（test split，300 題） | revision `846e647b9f33c0b51b739d005d13d85493c9af09`，2026-10-09 下載 | MIT（資料集卡片標示）；題目內容屬於各原始 repo |
| `source/swe-bench-verified-mini.json` | Hugging Face `MariusHobbhahn/swe-bench-verified-mini`（50 題，只有 django 與 sphinx） | revision `b316c349947c29963fce3f4a65967c9807a4b673` | 參考用，這次沒有採用（見 README） |
| `instances.json`／`instances.md` | 由 `select_tasks.py` 從上面兩份抽出的 24 題（固定種子 20261009） | — | 同上 |

資料是透過 Hugging Face 的 datasets-server API（`https://datasets-server.huggingface.co/rows?dataset=…`）下載的 JSON，欄位跟原始資料集相同，
包括官方提供的 Docker 映像名稱（`image`）、評分腳本（`eval_script`）、log parser 名稱（`log_parser`）、評分用的測試（`FAIL_TO_PASS`、`PASS_TO_PASS`）、
參考解答（`patch`）與評分用的測試修改（`test_patch`）。agent 只看得到 `problem_statement`（issue 原文），其他欄位只用在計分。

執行環境：每一題官方的 Docker 映像（Docker Hub 的 `swebench/sweb.eval.x86_64.<題目>:latest`）；計分用官方的 `swebench` Python 套件 5.0.2
（裝在獨立的 venv：`~/swebench_venv`，`pip install swebench`）。映像的 digest 記在 `../../artifacts/docker_images.txt`。
