from inventory import Inventory, storage


def test_roundtrip(tmp_path):
    inv = Inventory()
    inv.add("apple", 1.5, 4)
    path = tmp_path / "inv.json"
    storage.save(inv, path)
    again = storage.load(path)
    assert again.report() == inv.report()


def test_load_missing_file_is_empty(tmp_path):
    assert storage.load(tmp_path / "nope.json").items == {}
