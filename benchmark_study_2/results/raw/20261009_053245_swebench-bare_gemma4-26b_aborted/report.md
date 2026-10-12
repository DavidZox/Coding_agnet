# SWE-bench 子集：不用 harness（BM25 檢索＋一次寫出修改），模型 gemma4:26b

- 時間：2026-10-09 05:34；3 題已計分；**不用 harness**：關鍵字檢索找出相關檔案、模型一次寫出修改（SEARCH/REPLACE）。
- **resolved 0/3**（0.0%）
  - Python：0/3

| 題目 | 語言 | 難度 | resolved | patch 套用 | F2P | P2P | job 狀態 | 改的檔案 | 分鐘 | 模型呼叫 |
|---|---|---|---|---|---|---|---|---|---|---|
| django__django-12276 | Python | <15 min fix | ❌ | 空的 | — | — | — | 0 | 0.2 | 1 |
| sympy__sympy-16597 | Python | 1-4 hours | ❌ | 是 | 0/3 | 74/74 | — | 1 | 0.0 | 1 |
| sphinx-doc__sphinx-10435 | Python | <15 min fix | ❌ | 是 | 0/1 | 74/74 | — | 1 | 0.6 | 1 |

## 每一題

### django__django-12276：❌
- patch：（空的）（+0／-0）

### sympy__sympy-16597：❌
- patch：sympy/assumptions/sathandlers.py（+2／-2）

### sphinx-doc__sphinx-10435：❌
- patch：tox.ini（+1／-1）
