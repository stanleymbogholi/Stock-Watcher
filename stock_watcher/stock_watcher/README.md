# Stock Watcher

A prototype inventory agent for small and medium shops. It helps owners avoid
two common mistakes: buying more of something they already have, and
assuming something is in stock when it isn't. It also logs every sale so the
owner can see what actually sells and what just sits on the shelf.

## Project layout

```
stock_watcher/
├── data/
│   └── superstore_raw.csv     real transaction data (see "About the data" below)
├── backend/
│   ├── models.py               Product / Transaction data classes
│   ├── database.py             SQLite schema + all DB access
│   ├── extractor.py            loads the raw data into Stock Watcher's schema
│   ├── stock_engine.py         current stock, overstock guard, stockout guard
│   ├── analytics_engine.py     sales velocity, top sellers, dead stock
│   └── app.py                  Flask app: dashboard + JSON API
├── frontend/
│   ├── templates/index.html
│   └── static/{style.css,app.js}
└── requirements.txt
```

## Running it

```bash
cd stock_watcher
pip install -r requirements.txt
cd backend
python app.py
```

Then open in a browser. The database is created
and seeded automatically on first run (from `data/superstore_raw.csv`) into
`data/stock_watcher.db`. Delete that file (or run `python extractor.py`
directly) to reset and re-seed.

## What each engine does

- **stock_engine.py** — derives current stock for every product from the
  transaction log (never stored directly), and implements the two guards:
  - `check_purchase(product_id, qty)` — call this before placing a new
    order. It compares current stock to recent sales velocity and warns
    if the shop is already comfortably stocked.
  - `record_sale(product_id, qty)` — call this when a sale happens. It
    deducts stock and flags if the item just dropped to or below its
    reorder point.
- **analytics_engine.py** — `top_sellers()`, `dead_stock()`, and
  `sales_velocity()` for the sales log / reporting side of the agent.

## About the data

The seed data is a real, open, widely-used retail transaction dataset (the
"Sample Superstore" dataset — 9,994 real order lines, product names,
categories, quantities, and prices from 2014–2017), used here as a stand-in
for what a shop's own point-of-sale exports would look like. This copy is a
120-row sample of it (`data/superstore_raw.csv`) rather than the full file.

The dataset has no "current stock" column — no real sales log does either.
`extractor.py` invents one plausible, deterministic starting stock level per
product (seeded from the product ID, so re-running it gives the same
result) and records it as an opening "purchase" transaction, then replays
every historical order line as a "sale". This produces a realistic mix:
some products end up comfortably stocked, some run low or out, some barely
move at all — enough variety to exercise every part of the dashboard
(low-stock alerts, overstock alerts, top sellers, dead stock).

To point this at the full 9,994-row dataset or your own shop's export
instead, replace `data/superstore_raw.csv` with a CSV that has the same
columns (`Product ID`, `Product Name`, `Category`, `Sub-Category`,
`Order Date`, `Quantity`, `Sales`, `Order ID`) and re-run `extractor.py`.

## Where this goes next

This is a prototype of the core logic and a UI to demonstrate it, not a
production system. Natural next steps: real point-of-sale/spreadsheet
import instead of the seed script, user accounts per shop, a proper
production WSGI server instead of Flask's dev server, and turning the
guards into an actual conversational agent (natural-language "I want to
order 50 units of X" instead of a form).
