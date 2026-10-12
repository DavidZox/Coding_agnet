# DevBench 子集（同第一次研究）

這次的 DevBench 實驗（E8）用的是第一次研究的同一份資料：12 個 repo（Python 7、C++ 5）的規格文件、參考實作、官方的單元與驗收測試。
資料與授權說明在 [`../../../benchmark_study/datasets/devbench_subset/`](../../../benchmark_study/datasets/devbench_subset/SOURCE.md)，這裡不重複存一份。

評測程式：`evals/devbench/run.py`（harness）、`evals/devbench/bare.py`（不用 harness），計分方式與第一次研究相同。
