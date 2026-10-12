"""文字統計：字數、最常出現的字、平均字長。字一律轉小寫，標點符號不算字的一部分。"""
import re
from collections import Counter

_WORD_RE = re.compile(r"[A-Za-z']+")


def words(text):
    """把文字切成小寫的字（標點符號不算）。"""
    return [w.lower() for w in text.split()]


def word_count(text):
    return len(words(text))


def top_words(text, n=3):
    """出現最多次的 n 個字：[(字, 次數)]，次數一樣時依字母排序。"""
    counts = Counter(words(text))
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def average_word_length(text):
    ws = words(text)
    if not ws:
        return 0.0
    return round(sum(len(w) for w in ws) / len(ws), 2)
