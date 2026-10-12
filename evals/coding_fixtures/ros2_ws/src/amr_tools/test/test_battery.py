import pytest

from amr_tools.battery import percent


def test_percent_midpoint():
    assert percent(23.6) == pytest.approx(50.0)


def test_percent_is_clamped():
    assert percent(26.0) == 100.0
    assert percent(20.0) == 0.0


def test_percent_rejects_bad_range():
    with pytest.raises(ValueError):
        percent(24.0, empty=25.0, full=24.0)
