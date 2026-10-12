import csv
import subprocess
import sys

from inventory import Inventory, storage


def test_hidden_export_csv(tmp_path):
    inv = Inventory()
    inv.add("pear", 2.0, 1)
    inv.add("apple", 1.5, 4)
    p = tmp_path / "out.csv"
    storage.export_csv(inv, p)
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["name", "price", "qty"]
    assert rows[1:] == [["apple", "1.50", "4"], ["pear", "2.00", "1"]]


def test_hidden_cli_export(tmp_path):
    f = tmp_path / "inv.json"
    out = tmp_path / "x.csv"
    inv = Inventory()
    inv.add("apple", 1.5, 4)
    storage.save(inv, f)
    r = subprocess.run([sys.executable, "-m", "inventory.cli", "--file", str(f), "export", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.read_text(encoding="utf-8").splitlines()[:2] == ["name,price,qty", "apple,1.50,4"]
