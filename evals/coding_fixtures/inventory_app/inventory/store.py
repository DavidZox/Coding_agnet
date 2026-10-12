"""Inventory：記憶體裡的庫存，提供新增、移除、總價值與報表。"""
from .models import Item


class Inventory:
    def __init__(self):
        self.items = {}

    def add(self, name, price, qty=1):
        """新增品項；已存在時增加數量（單價以第一次為準）。"""
        if qty <= 0:
            raise ValueError("qty must be positive")
        if name in self.items:
            self.items[name].qty += qty
        else:
            self.items[name] = Item(name, price, qty)

    def remove(self, name, qty=1):
        """移除數量；數量歸零時刪掉品項。"""
        item = self.items.get(name)
        if item is None:
            raise KeyError(name)
        item.qty -= qty
        if item.qty <= 0:
            del self.items[name]

    def total_value(self):
        return sum(i.value() for i in self.items.values())

    def report(self):
        """每個品項一行：名稱: 數量 x 單價，依名稱排序。"""
        lines = []
        for name in sorted(self.items):
            i = self.items[name]
            lines.append(f"{name}: {i.qty} x {i.price:.2f}")
        return "\n".join(lines)
