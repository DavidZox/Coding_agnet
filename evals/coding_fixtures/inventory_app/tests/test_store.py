import pytest

from inventory import Inventory


@pytest.fixture
def inv():
    i = Inventory()
    i.add("apple", 1.5, 4)
    i.add("pear", 2.0, 1)
    return i


def test_add_merges_quantity(inv):
    inv.add("apple", 9.9, 2)
    assert inv.items["apple"].qty == 6
    assert inv.items["apple"].price == 1.5


def test_add_rejects_non_positive():
    with pytest.raises(ValueError):
        Inventory().add("x", 1.0, 0)


def test_remove_to_zero_deletes(inv):
    inv.remove("pear")
    assert "pear" not in inv.items


def test_remove_unknown_raises(inv):
    with pytest.raises(KeyError):
        inv.remove("banana")


def test_total_value(inv):
    assert inv.total_value() == pytest.approx(8.0)


def test_report_sorted(inv):
    assert inv.report() == "apple: 4 x 1.50\npear: 1 x 2.00"
