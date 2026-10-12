| 題目 | 語言 | 難度 | harness：gemma4:26b | harness：DeepSeek-R1-32B 規劃＋Qwen2.5-Coder-32B worker | 不用 harness：gemma4:26b | 不用 harness：Qwen2.5-Coder-32B | harness：gemma4:26b（v4.1，C++ 掃描器 bug） | harness：gemma4:26b（v4.2） |
|---|---|---|---|---|---|---|---|---|
| astropy__astropy-8872 | Python | 15 min - 1 hour | ○ | ✅ | ✅ | ✅ | ○ | ○ |
| django__django-11141 | Python | 15 min - 1 hour | ○ | ∅ | ○ | ○ | — | ○ |
| django__django-11734 | Python | 15 min - 1 hour | ✗ | ✗ | ○ | ○ | — | ○ |
| django__django-12276 | Python | <15 min fix | ○ | ✅ | ∅ | ○ | — | ✅ |
| django__django-13410 | Python | <15 min fix | ✅ | ✅ | ✅ | ✅ | — | ○ |
| django__django-14089 | Python | <15 min fix | ✅ | ✗ | ∅ | ✗ | — | ✅ |
| django__django-15561 | Python | 15 min - 1 hour | ✗ | ✗ | ✗ | ✅ | — | ✗ |
| matplotlib__matplotlib-20488 | Python | 15 min - 1 hour | ✅ | ✗ | ✗ | ✗ | — | ✗ |
| pallets__flask-5014 | Python | <15 min fix | ✅ | ✅ | ∅ | ∅ | — | ∅ |
| pydata__xarray-3677 | Python | 15 min - 1 hour | ✗ | ✗ | ✅ | ✅ | — | ✅ |
| pytest-dev__pytest-10051 | Python | 15 min - 1 hour | ○ | ○ | ○ | ○ | — | ○ |
| scikit-learn__scikit-learn-14496 | Python | <15 min fix | ✅ | ∅ | ✅ | ∅ | — | ✅ |
| sphinx-doc__sphinx-10435 | Python | <15 min fix | ○ | ✗ | ✗ | ✗ | — | ○ |
| sphinx-doc__sphinx-8035 | Python | 15 min - 1 hour | ○ | ○ | ○ | ○ | — | ✅ |
| sympy__sympy-16597 | Python | 1-4 hours | ✗ | ○ | ✗ | ✗ | — | ○ |
| sympy__sympy-18199 | Python | 1-4 hours | ○ | ○ | ○ | ○ | — | ○ |
| jqlang__jq-2235 | C | — | ○ | ○ | ○ | ○ | — | ○ |
| micropython__micropython-13039 | C | — | ○ | ○ | ∅ | ✅ | — | ○ |
| redis__redis-12472 | C | — | ○ | ○ | ○ | ○ | ∅ | ○ |
| redis__redis-13115 | C | — | ✗ | ✗ | ∅ | ∅ | ∅ | ✗ |
| fmtlib__fmt-1683 | C++ | — | ○ | ✅ | ✅ | ✅ | ○ | ○ |
| fmtlib__fmt-2310 | C++ | — | ✅ | ✅ | ✗ | ○ | — | ✗ |
| fmtlib__fmt-3901 | C++ | — | ○ | ✅ | ✅ | ○ | — | ✅ |
| nlohmann__json-4237 | C++ | — | ✅ | ✅ | ∅ | ∅ | — | ✅ |

✅ 解決；○ 改到該改的檔案但沒有通過評分測試；✗ 改了別的檔案；∅ 沒有改任何東西
