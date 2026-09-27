"""
models.py
---------
Plain data classes for Stock Watcher.

A Product is the catalog entry (what the shop sells).
A Transaction is a single stock movement: a purchase (stock in),
a sale (stock out), or an adjustment (correction, damage, loss).

current_stock is deliberately NOT stored on Product. It is always
derived from the transaction log (see stock_engine.py), so the
log stays the single source of truth and can be replayed or audited.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Product:
    product_id: str
    name: str
    category: str
    sub_category: str
    cost_price: float
    sell_price: float
    reorder_threshold: int

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "sub_category": self.sub_category,
            "cost_price": round(self.cost_price, 2),
            "sell_price": round(self.sell_price, 2),
            "reorder_threshold": self.reorder_threshold,
        }


@dataclass
class Transaction:
    product_id: str
    type: str          # "purchase" | "sale" | "adjustment"
    quantity: int       # always a positive count of units moved
    timestamp: str      # ISO date string, e.g. "2016-11-08"
    note: str = ""

    VALID_TYPES = {"purchase", "sale", "adjustment"}

    def __post_init__(self):
        if self.type not in self.VALID_TYPES:
            raise ValueError(f"Invalid transaction type: {self.type}")
        if self.quantity <= 0:
            raise ValueError("Transaction quantity must be positive")
        # normalize to a plain date string if a datetime was passed in
        if isinstance(self.timestamp, datetime):
            self.timestamp = self.timestamp.strftime("%Y-%m-%d")

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "type": self.type,
            "quantity": self.quantity,
            "timestamp": self.timestamp,
            "note": self.note,
        }
