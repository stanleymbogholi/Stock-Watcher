"""
analytics_engine.py
--------------------
Turns the transaction log into the sales insights a shop owner
actually wants: what's moving, what isn't, and how fast stock is
being used up.

Note on "now": the seed data is historical (2014-2017), so "the last
90 days" would be meaningless measured against today's real date.
Every method here measures relative to the most recent transaction
timestamp in the log instead -- which also means it behaves correctly
once real, live sales (dated today) start being recorded on top of
the seed data.
"""

from datetime import datetime, timedelta

import database


class AnalyticsEngine:
    def _reference_date(self) -> datetime:
        latest = database.latest_transaction_date()
        if latest:
            return datetime.strptime(latest, "%Y-%m-%d")
        return datetime.utcnow()

    # ---- velocity --------------------------------------------------------

    def sales_velocity(self, product_id: str, days: int = 90) -> float:
        """Average units sold per day over the trailing window."""
        ref = self._reference_date()
        since = (ref - timedelta(days=days)).strftime("%Y-%m-%d")
        sales = database.get_transactions(product_id=product_id, since=since, tx_type="sale")
        total = sum(t["quantity"] for t in sales)
        return total / days if days > 0 else 0.0

    def days_of_stock_remaining(self, product_id: str, current_stock: int, days: int = 90) -> float | None:
        velocity = self.sales_velocity(product_id, days=days)
        return (current_stock / velocity) if velocity > 0 else None

    # ---- top / bottom sellers ---------------------------------------------

    def top_sellers(self, n: int = 10, days: int = None, by: str = "quantity") -> list:
        """by: 'quantity' or 'revenue'."""
        since = None
        if days:
            since = (self._reference_date() - timedelta(days=days)).strftime("%Y-%m-%d")

        sales = database.get_transactions(since=since, tx_type="sale")
        products = {p["product_id"]: p for p in database.get_all_products()}

        agg = {}
        for t in sales:
            pid = t["product_id"]
            product = products.get(pid)
            if not product:
                continue
            entry = agg.setdefault(pid, {"product": product, "quantity": 0, "revenue": 0.0})
            entry["quantity"] += t["quantity"]
            entry["revenue"] += t["quantity"] * product["sell_price"]

        rows = [
            {
                "product_id": pid,
                "name": e["product"]["name"],
                "category": e["product"]["category"],
                "quantity_sold": e["quantity"],
                "revenue": round(e["revenue"], 2),
            }
            for pid, e in agg.items()
        ]
        key = "quantity_sold" if by == "quantity" else "revenue"
        rows.sort(key=lambda r: r[key], reverse=True)
        return rows[:n]

    def dead_stock(self, days: int = 60) -> list:
        """Products with zero sales in the trailing window -- candidates
        to stop reordering or to discount / clear out."""
        # local import: avoids a circular import with stock_engine, which
        # imports this module for velocity calculations.
        from stock_engine import StockEngine

        since = (self._reference_date() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent_sales = database.get_transactions(since=since, tx_type="sale")
        sold_recently = {t["product_id"] for t in recent_sales}

        stock_engine = StockEngine()
        stock_by_product = stock_engine.all_current_stock()

        dead = []
        for p in database.get_all_products():
            if p["product_id"] in sold_recently:
                continue
            stock = stock_by_product.get(p["product_id"], 0)
            if stock <= 0:
                continue  # nothing left to clear, not a "dead stock" concern
            dead.append({**p, "current_stock": stock})

        return sorted(dead, key=lambda p: -p["current_stock"])
