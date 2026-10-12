"""把文字統計排成報表。"""
from .stats import average_word_length, top_words, word_count


def format_report(text):
    lines = [f"words: {word_count(text)}", f"avg length: {average_word_length(text)}"]
    for w, c in top_words(text):
        lines.append(f"{w}: {c}")
    return "\n".join(lines)
