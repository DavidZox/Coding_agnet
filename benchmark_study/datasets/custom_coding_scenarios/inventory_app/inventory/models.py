"""庫存品項的資料結構。"""
from dataclasses import dataclass


@dataclass
class Item:
    name: str
    price: float
    qty: int = 0

    def value(self):
        """這個品項的總價值（單價 × 數量）。"""
        return self.price * self.qty
