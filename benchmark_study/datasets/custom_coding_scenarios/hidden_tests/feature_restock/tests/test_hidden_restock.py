import pytest
from inventory import Inventory


def make():
    inv = Inventory()
    inv.add("a", 1.0, 5)
    inv.add("b", 2.0, 1)
    inv.add("c", 3.0, 10)
    return inv


def test_hidden_restock_below():
    inv = make()
    assert inv.restock_below(5, 3) == ["b"]
    assert inv.items["b"].qty == 4 and inv.items["a"].qty == 5 and inv.items["c"].qty == 10


def test_hidden_restock_sorted():
    inv = Inventory()
    inv.add("z", 1.0, 1)
    inv.add("m", 1.0, 1)
    inv.add("a", 1.0, 9)
    assert inv.restock_below(2, 1) == ["m", "z"]


def test_hidden_remove_not_enough():
    inv = make()
    with pytest.raises(ValueError, match="not enough stock"):
        inv.remove("a", 9)
    assert inv.items["a"].qty == 5


def test_hidden_remove_exact_still_deletes():
    inv = make()
    inv.remove("a", 5)
    assert "a" not in inv.items
