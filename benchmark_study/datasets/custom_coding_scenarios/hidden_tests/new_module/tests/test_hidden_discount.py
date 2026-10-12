import pytest

from inventory import Inventory
from inventory.discount import apply_discount, discounted_total


def test_hidden_apply_discount():
    assert apply_discount(100, 15) == 85.0
    assert apply_discount(19.99, 10) == 17.99
    assert apply_discount(5, 0) == 5.0


@pytest.mark.parametrize("bad", [-1, 101])
def test_hidden_apply_discount_range(bad):
    with pytest.raises(ValueError, match="percent must be between 0 and 100"):
        apply_discount(10, bad)


def test_hidden_discounted_total():
    inv = Inventory()
    inv.add("a", 1.5, 4)
    inv.add("b", 2.0, 1)
    assert discounted_total(inv, 50) == 4.0
