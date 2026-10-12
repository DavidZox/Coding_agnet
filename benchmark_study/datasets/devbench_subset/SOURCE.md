# DevBench 子集（12 個 repo）

- 來源：open-compass/DevEval，commit `bb593c1f9c535ff0dde0c9f4807d58c9566c3a6c`（2024-05-30）。`evals/devbench/prepare.py` 下載時每個檔案都用 git blob SHA-1 驗證，跟這個 commit 的內容一模一樣。
- 授權：資料 **CC BY 4.0**（可以複製、散布、改作，要標示出處），程式 **Apache 2.0**（見 `LICENSE_DevEval_Apache-2.0`；原始 README 在 `../../references/devbench_source/`）。出處：Li et al., *DevBench: A Comprehensive Benchmark for Software Development*, arXiv:2403.08604。
- 內容：`python/` 7 個（readtime、particle-swarm-optimization、chakin、stocktrends、geotext、hone、lice）、`cpp/` 5 個（area_calculation、graph-cpp、logistic_system、people_management、xlsx2csv）。每個 repo 有規格文件（PRD、UML 類別圖與循序圖、架構設計）、參考實作、官方的單元測試與驗收測試、`repo_config.json`。
- `repos.json`：每個 repo 的語言、程式碼行數（論文依行數加權）、單元／驗收測試數（共 116／51）、驗收測試的計分方式。
- 沒選的：Hybrid_Images（參考實作的單元測試在這個環境本身就有 8 個失敗）、ArXiv_digest（驗收測試要連 arXiv 網站）、TextCNN（要 PyTorch 與實際訓練）；Java／JavaScript 的 repo 不在這個 harness 的範圍。
- 用法：評測時 agent 只拿到規格文件與 `required_files`（資料檔、第三方程式庫、C++ 的 `makefile_test`）；官方測試在 job 結束後才放進去計分（見 `evals/devbench/README.md`）。用參考實作驗證計分：`python3 evals/devbench/prepare.py --verify`（12 個全部通過：單元 116/116、驗收 51/51）。
