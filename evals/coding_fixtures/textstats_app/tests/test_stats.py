from textstats.stats import average_word_length, top_words, word_count, words


def test_words_strip_punctuation():
    assert words("Hello, world! Hello.") == ["hello", "world", "hello"]


def test_word_count():
    assert word_count("One two, three.") == 3


def test_top_words():
    assert top_words("b a b c a b", 2) == [("b", 3), ("a", 2)]


def test_top_words_counts_punctuated_words_together():
    assert top_words("Cat. cat, CAT dog")[0] == ("cat", 3)


def test_average_word_length():
    assert average_word_length("ab, abcd!") == 3.0


def test_empty():
    assert word_count("") == 0
    assert average_word_length("...") == 0.0
