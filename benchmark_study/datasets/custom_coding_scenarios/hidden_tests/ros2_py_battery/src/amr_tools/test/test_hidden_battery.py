import pytest

from amr_tools.battery import is_low, percent


def test_hidden_is_low():
    assert is_low(22.3) is True
    assert is_low(25.0) is False
    assert is_low(23.6, threshold=60.0) is True
    assert is_low(24.5, threshold=60.0) is False


def test_hidden_is_low_bad_threshold():
    with pytest.raises(ValueError, match="threshold must be between 0 and 100"):
        is_low(23.0, threshold=150)
    with pytest.raises(ValueError, match="threshold must be between 0 and 100"):
        is_low(23.0, threshold=-1)


def test_hidden_percent_unchanged():
    assert percent(23.6) == pytest.approx(50.0)
    assert percent(30.0) == 100.0
