"""
extractor.py
------------
Turns the raw, real-world "Sample Superstore" transaction data
(data/superstore_raw.csv) into Stock Watcher's own schema and loads it
into the database.

Why this dataset: it's real retail order data (product, category,
quantity, date, price per line item) -- the same shape of data a
small shop's point-of-sale system would produce. It has no
"current stock" column, because no real sales log does either: that
is exactly the number Stock Watcher's engines are meant to derive.

What this module does with it:
  1. Reads every order line.
  2. Groups lines by product to build the catalog (name, category,
     price, a sensible reorder threshold).
  3. Invents one plausible starting stock level per product (seeded
     deterministically from the product id, so re-running the
     extractor is reproducible) and records it as an opening
     "purchase" transaction just before the product's first sale.
  4. Replays every historical order line as a "sale" transaction,
     in date order.

The result is a realistic, messy transaction log: some products will
look permanently overstocked, some will run out partway through the
period, some will barely sell at all -- exactly the mix Stock
Watcher's guards and analytics are meant to catch.
"""

import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from models import Product, Transaction
import database

RAW_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "superstore_raw.csv"


def _parse_date(raw: str) -> str:
    """'11/8/2016' -> '2016-11-08'"""
    return datetime.strptime(raw.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")


def _seed_factor(product_id: str) -> float:
    """
    Deterministic pseudo-random number in [0.7, 3.5] derived from the
    product id. Used to pick a starting stock level relative to how
    much of that product sold historically. Deterministic so the same
    product always gets the same demo starting stock. The range is
    biased above 1.0 so most products start comfortably stocked, with
    a genuine (not universal) minority running low or out -- enough
    variety to exercise both guards without every item being an alert.
    """
    digest = hashlib.sha256(product_id.encode()).hexdigest()
    n = int(digest[:8], 16) / 0xFFFFFFFF  # -> [0, 1]
    return 0.7 + n * 2.8  # -> [0.7, 3.5]


def read_raw_rows():
    with open(RAW_CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_products(rows):
    """One Product per distinct Product ID, priced from the average
    observed unit price, with a reorder threshold sized to roughly
    two typical orders' worth of stock."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["Product ID"]].append(row)

    products = {}
    for product_id, lines in grouped.items():
        first = lines[0]
        quantities = [int(r["Quantity"]) for r in lines]
        unit_prices = [float(r["Sales"]) / int(r["Quantity"]) for r in lines]
        avg_unit_price = sum(unit_prices) / len(unit_prices)
        avg_order_qty = sum(quantities) / len(quantities)

        products[product_id] = Product(
            product_id=product_id,
            name=first["Product Name"],
            category=first["Category"],
            sub_category=first["Sub-Category"],
            sell_price=avg_unit_price,
            cost_price=avg_unit_price * 0.65,     # assume ~35% margin
            reorder_threshold=max(3, round(avg_order_qty * 0.75)),
        )
    return products


def build_transactions(rows, products):
    """Opening 'purchase' per product + one 'sale' per order line."""
    by_product = defaultdict(list)
    for row in rows:
        by_product[row["Product ID"]].append(row)

    transactions = []
    for product_id, lines in by_product.items():
        lines_sorted = sorted(lines, key=lambda r: _parse_date(r["Order Date"]))
        total_sold = sum(int(r["Quantity"]) for r in lines_sorted)

        opening_stock = max(5, round(total_sold * _seed_factor(product_id)))
        opening_date = (
            datetime.strptime(_parse_date(lines_sorted[0]["Order Date"]), "%Y-%m-%d")
            - timedelta(days=7)
        ).strftime("%Y-%m-%d")

        transactions.append(
            Transaction(
                product_id=product_id,
                type="purchase",
                quantity=opening_stock,
                timestamp=opening_date,
                note="Initial stock load (seed data)",
            )
        )

        for row in lines_sorted:
            transactions.append(
                Transaction(
                    product_id=product_id,
                    type="sale",
                    quantity=int(row["Quantity"]),
                    timestamp=_parse_date(row["Order Date"]),
                    note=row["Order ID"],
                )
            )

    transactions.sort(key=lambda t: t.timestamp)
    return transactions


def run(reset: bool = True):
    print("Initializing database...")
    database.init_db(reset=reset)

    print(f"Reading raw data from {RAW_CSV_PATH.name}...")
    rows = read_raw_rows()
    print(f"  {len(rows)} order lines read")

    print("Building product catalog...")
    products = build_products(rows)
    for product in products.values():
        database.upsert_product(product)
    print(f"  {len(products)} distinct products")

    print("Building transaction log (opening stock + historical sales)...")
    transactions = build_transactions(rows, products)
    database.bulk_insert_transactions(transactions)
    print(f"  {len(transactions)} transactions inserted")

    print("Done.")


if __name__ == "__main__":
    run(reset=True)
