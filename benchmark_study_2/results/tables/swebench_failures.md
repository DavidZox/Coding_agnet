| 條件 | 解決 | 沒有改任何東西 | patch 套不上 | 改錯地方（沒改到該改的檔案） | 改對檔案但沒修好 | 修好了但弄壞既有測試 |
|---|---|---|---|---|---|---|
| harness：gemma4:26b | 7 | 0 | 0 | 4 | 9 | 4 |
| harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker | 8 | 2 | 0 | 7 | 6 | 1 |
| 不用 harness：gemma4:26b | 6 | 6 | 0 | 5 | 6 | 1 |
| 不用 harness：Qwen2.5-Coder-32B | 6 | 4 | 0 | 4 | 8 | 2 |
| harness：gemma4:26b（v4.1，C++ 掃描器 bug） | 0 | 2 | 0 | 0 | 1 | 1 |
| harness：gemma4:26b（v4.2） | 7 | 1 | 0 | 4 | 9 | 3 |
