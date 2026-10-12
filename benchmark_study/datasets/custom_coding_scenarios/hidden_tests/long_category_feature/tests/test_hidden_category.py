import json
import subprocess
import sys

from inventory import Inventory, Item, storage


def test_hidden_item_category_default():
    assert Item("a", 1.0, 1).category == "general"


def test_hidden_add_with_category_and_by_category():
    inv = Inventory()
    inv.add("pear", 2.0, 1, category="fruit")
    inv.add("apple", 1.5, 4, category="fruit")
    inv.add("hammer", 9.0, 1, category="tools")
    inv.add("misc", 1.0, 1)
    assert inv.by_category() == {"fruit": ["apple", "pear"], "general": ["misc"], "tools": ["hammer"]}


def test_hidden_storage_roundtrip_category(tmp_path):
    inv = Inventory()
    inv.add("apple", 1.5, 4, category="fruit")
    p = tmp_path / "inv.json"
    storage.save(inv, p)
    assert storage.load(p).items["apple"].category == "fruit"


def test_hidden_storage_loads_old_files_without_category(tmp_path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps([{"name": "apple", "price": 1.5, "qty": 4}]), encoding="utf-8")
    assert storage.load(p).items["apple"].category == "general"


def test_hidden_cli_category(tmp_path):
    f = tmp_path / "inv.json"

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "inventory.cli", "--file", str(f), *args], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout

    run("add", "apple", "1.5", "4", "--category", "fruit")
    run("add", "hammer", "9", "1", "--category", "tools")
    run("add", "misc", "1", "1")
    assert run("categories").strip().splitlines() == ["fruit: 1", "general: 1", "tools: 1"]
