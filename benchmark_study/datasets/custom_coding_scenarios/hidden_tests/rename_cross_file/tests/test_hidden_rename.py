import subprocess
import sys

from inventory import Inventory, storage


def test_hidden_total_renamed():
    inv = Inventory()
    inv.add("a", 1.5, 4)
    assert inv.total() == 6.0
    assert not hasattr(inv, "total_value")


def test_hidden_cli_total(tmp_path):
    f = tmp_path / "inv.json"
    inv = Inventory()
    inv.add("a", 1.5, 4)
    inv.add("b", 2.0, 1)
    storage.save(inv, f)
    out = subprocess.run([sys.executable, "-m", "inventory.cli", "--file", str(f), "total"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "8.00"
