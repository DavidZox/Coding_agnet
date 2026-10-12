from textstats.report import format_report


def test_format_report():
    text = "the cat and the hat"
    assert format_report(text) == "words: 5\navg length: 3.0\nthe: 2\nand: 1\ncat: 1"
