"""
database.py
-----------
Thin SQLite wrapper for Stock Watcher.

Two tables:
  products      -- the catalog (one row per item the shop sells)
  transactions  -- the append-only movement log (purchases, sales,
                   adjustments). current stock is always derived
                   from this table, never stored directly.

Every other module (extractor, stock_engine, analytics_engine, app)
goes through this module to touch the database, so the schema only
lives in one place.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "stock_watcher.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    product_id        TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    category          TEXT NOT NULL,
    sub_category      TEXT NOT NULL,
    cost_price        REAL NOT NULL,
    sell_price        REAL NOT NULL,
    reorder_threshold INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     TEXT NOT NULL,
    type           TEXT NOT NULL CHECK (type IN ('purchase', 'sale', 'adjustment')),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    timestamp      TEXT NOT NULL,
    note           TEXT DEFAULT '',
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE INDEX IF NOT EXISTS idx_tx_product ON transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_tx_timestamp ON transactions(timestamp);
"""


def get_connection():
    """Every caller gets its own connection; SQLite handles the locking."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = False):
    """Create the schema. If reset=True, wipe existing data first."""
    conn = get_connection()
    if reset:
        conn.executescript("DROP TABLE IF EXISTS transactions; DROP TABLE IF EXISTS products;")
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def is_seeded() -> bool:
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()
        return row["n"] > 0
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


# ---- products --------------------------------------------------------

def upsert_product(product):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO products (product_id, name, category, sub_category, cost_price, sell_price, reorder_threshold)
        VALUES (:product_id, :name, :category, :sub_category, :cost_price, :sell_price, :reorder_threshold)
        ON CONFLICT(product_id) DO UPDATE SET
            name=excluded.name,
            category=excluded.category,
            sub_category=excluded.sub_category,
            cost_price=excluded.cost_price,
            sell_price=excluded.sell_price,
            reorder_threshold=excluded.reorder_threshold
        """,
        product.to_dict(),
    )
    conn.commit()
    conn.close()


def get_all_products():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products ORDER BY category, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product(product_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ---- transactions ------------------------------------------------------

def insert_transaction(transaction):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO transactions (product_id, type, quantity, timestamp, note)
        VALUES (:product_id, :type, :quantity, :timestamp, :note)
        """,
        transaction.to_dict(),
    )
    conn.commit()
    conn.close()


def bulk_insert_transactions(transactions):
    conn = get_connection()
    conn.executemany(
        """
        INSERT INTO transactions (product_id, type, quantity, timestamp, note)
        VALUES (:product_id, :type, :quantity, :timestamp, :note)
        """,
        [t.to_dict() for t in transactions],
    )
    conn.commit()
    conn.close()


def get_transactions(product_id=None, since=None, tx_type=None):
    conn = get_connection()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if product_id:
        query += " AND product_id = ?"
        params.append(product_id)
    if since:
        query += " AND timestamp >= ?"
        params.append(since)
    if tx_type:
        query += " AND type = ?"
        params.append(tx_type)
    query += " ORDER BY timestamp"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def latest_transaction_date():
    conn = get_connection()
    row = conn.execute("SELECT MAX(timestamp) AS latest FROM transactions").fetchone()
    conn.close()
    return row["latest"] if row and row["latest"] else None
