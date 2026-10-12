"""把 Inventory 存成 JSON 檔、或從 JSON 檔讀回來。"""
import json
import os

from .store import Inventory


def save(inv, path):
    data = [{"name": i.name, "price": i.price, "qty": i.qty} for i in inv.items.values()]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load(path):
    inv = Inventory()
    if not os.path.exists(path):
        return inv
    with open(path, encoding="utf-8") as f:
        for row in json.load(f):
            inv.add(row["name"], row["price"], row["qty"])
    return inv
