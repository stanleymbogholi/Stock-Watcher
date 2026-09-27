"""
stock_engine.py
----------------
The core inventory logic: turns the transaction log into current
stock levels, and answers the two questions Stock Watcher exists
for:

  1. "I want to buy more of X -- do I actually need it?"
       -> check_purchase()   (the overstock guard)
  2. "I just sold X -- am I now running low?"
       -> record_sale()       (the stockout guard)

Nothing here talks to Flask or the database schema directly except
through database.py, so this module can be unit tested on its own.
"""

from datetime import datetime, timedelta

import database
from models import Transaction
from analytics_engine import AnalyticsEngine


class StockEngine:
    def __init__(self):
        self.analytics = AnalyticsEngine()

    # ---- core stock level -------------------------------------------

    def current_stock(self, product_id: str) -> int:
        """Sum of all purchases/adjustments-in minus sales/adjustments-out."""
        transactions = database.get_transactions(product_id=product_id)
        stock = 0
        for t in transactions:
            if t["type"] in ("purchase",):
                stock += t["quantity"]
            elif t["type"] == "sale":
                stock -= t["quantity"]
            elif t["type"] == "adjustment":
                # note prefixed with '-' means a loss/damage/correction down
                if t["note"].startswith("-"):
                    stock -= t["quantity"]
                else:
                    stock += t["quantity"]
        return stock

    def all_current_stock(self) -> dict:
        """product_id -> current stock, computed in one pass over all
        transactions rather than one query per product."""
        transactions = database.get_transactions()
        stock = {}
        for t in transactions:
            pid = t["product_id"]
            stock.setdefault(pid, 0)
            if t["type"] == "purchase":
                stock[pid] += t["quantity"]
            elif t["type"] == "sale":
                stock[pid] -= t["quantity"]
            elif t["type"] == "adjustment":
                if t["note"].startswith("-"):
                    stock[pid] -= t["quantity"]
                else:
                    stock[pid] += t["quantity"]
        return stock

    # ---- overstock guard ----------------------------------------------

    def check_purchase(self, product_id: str, requested_qty: int, lookback_days: int = 90) -> dict:
        """
        Called before a new purchase order is placed. Warns the owner
        if they already hold comfortably more stock than their recent
        sales pace would use up before they'd naturally need to reorder.
        """
        product = database.get_product(product_id)
        if not product:
            return {"error": f"Unknown product_id: {product_id}"}

        stock = self.current_stock(product_id)
        velocity = self.analytics.sales_velocity(product_id, days=lookback_days)  # units/day
        days_of_stock = (stock / velocity) if velocity > 0 else None

        # "Comfortably stocked" = more than 30 days of stock at current pace,
        # or already above 3x the reorder threshold with no recent sales.
        overstocked = False
        if velocity > 0 and days_of_stock is not None and days_of_stock > 30:
            overstocked = True
        elif velocity == 0 and stock > product["reorder_threshold"] * 3:
            overstocked = True

        if overstocked and days_of_stock is not None:
            message = (
                f"You already have {stock} units of \"{product['name']}\" in stock -- "
                f"at the current sales pace that's about {round(days_of_stock)} days of "
                f"stock. You may not need to order {requested_qty} more yet."
            )
        elif overstocked:
            message = (
                f"You already have {stock} units of \"{product['name']}\" and it hasn't "
                f"sold recently. Ordering {requested_qty} more may not be necessary."
            )
        else:
            message = (
                f"Current stock is {stock} units. Ordering {requested_qty} looks reasonable."
            )

        return {
            "product_id": product_id,
            "product_name": product["name"],
            "current_stock": stock,
            "requested_qty": requested_qty,
            "sales_velocity_per_day": round(velocity, 2),
            "days_of_stock_remaining": round(days_of_stock, 1) if days_of_stock is not None else None,
            "overstocked": overstocked,
            "message": message,
        }

    # ---- stockout guard -------------------------------------------------

    def record_sale(self, product_id: str, quantity: int, timestamp: str = None) -> dict:
        """
        Records a sale and reports whether it pushed the product below
        its reorder threshold (or into a negative / blocked state).
        """
        product = database.get_product(product_id)
        if not product:
            return {"error": f"Unknown product_id: {product_id}"}

        stock_before = self.current_stock(product_id)
        if stock_before <= 0:
            return {
                "error": f"\"{product['name']}\" shows 0 units in stock. "
                         f"Sale was not recorded -- check stock before selling.",
                "current_stock": stock_before,
            }

        ts = timestamp or datetime.utcnow().strftime("%Y-%m-%d")
        database.insert_transaction(
            Transaction(product_id=product_id, type="sale", quantity=quantity, timestamp=ts, note="manual sale")
        )

        stock_after = stock_before - quantity
        low_stock = stock_after <= product["reorder_threshold"]

        return {
            "product_id": product_id,
            "product_name": product["name"],
            "stock_before": stock_before,
            "stock_after": stock_after,
            "reorder_threshold": product["reorder_threshold"],
            "low_stock": low_stock,
            "message": (
                f"Stock now at {stock_after} units, at or below the reorder "
                f"threshold of {product['reorder_threshold']}. Consider restocking."
                if low_stock else
                f"Stock now at {stock_after} units."
            ),
        }

    # ---- alerts --------------------------------------------------------

    def low_stock_items(self) -> list:
        products = database.get_all_products()
        stock_by_product = self.all_current_stock()
        low = []
        for p in products:
            stock = stock_by_product.get(p["product_id"], 0)
            if stock <= p["reorder_threshold"]:
                low.append({**p, "current_stock": stock})
        return sorted(low, key=lambda p: p["current_stock"])

    def overstocked_items(self, lookback_days: int = 90) -> list:
        products = database.get_all_products()
        stock_by_product = self.all_current_stock()
        overstocked = []
        for p in products:
            stock = stock_by_product.get(p["product_id"], 0)
            velocity = self.analytics.sales_velocity(p["product_id"], days=lookback_days)
            days_of_stock = (stock / velocity) if velocity > 0 else None
            if (velocity > 0 and days_of_stock and days_of_stock > 30) or (
                velocity == 0 and stock > p["reorder_threshold"] * 3
            ):
                overstocked.append({
                    **p,
                    "current_stock": stock,
                    "days_of_stock_remaining": round(days_of_stock, 1) if days_of_stock else None,
                })
        return sorted(overstocked, key=lambda p: -p["current_stock"])
