# textstats_app

文字統計的小工具（coding harness 的評測 fixture，`textstats/stats.py` 裡故意留了 bug）。

- `textstats/stats.py`：`word_count`、`top_words`、`average_word_length`
- `textstats/report.py`：`format_report(text)` 把統計排成報表
- 測試：`python3 -m pytest -q`
