"""
app.py
------
Flask application: serves the dashboard and exposes the Stock Watcher
API. Run with `python app.py` from the backend/ folder.

Routes:
  GET  /                          dashboard page
  GET  /api/products              catalog + current stock + status
  GET  /api/alerts                low-stock and overstocked items
  GET  /api/top-sellers           best sellers (?days=&n=&by=)
  GET  /api/dead-stock            slow/no movers (?days=)
  POST /api/purchase-check        overstock guard  {product_id, quantity}
  POST /api/sale                  stockout guard   {product_id, quantity}
"""

from pathlib import Path

from flask import Flask, jsonify, request, render_template

import database
import extractor
from stock_engine import StockEngine
from analytics_engine import AnalyticsEngine

BASE_DIR = Path(__file__).resolve().parent.parent
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "frontend" / "templates"),
    static_folder=str(BASE_DIR / "frontend" / "static"),
)

stock_engine = StockEngine()
analytics_engine = AnalyticsEngine()


def ensure_seeded():
    if not database.is_seeded():
        extractor.run(reset=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/products")
def api_products():
    products = database.get_all_products()
    stock_by_product = stock_engine.all_current_stock()
    result = []
    for p in products:
        stock = stock_by_product.get(p["product_id"], 0)
        if stock <= 0:
            status = "out_of_stock"
        elif stock <= p["reorder_threshold"]:
            status = "low"
        else:
            status = "ok"
        result.append({**p, "current_stock": stock, "status": status})
    return jsonify(result)


@app.route("/api/alerts")
def api_alerts():
    return jsonify({
        "low_stock": stock_engine.low_stock_items(),
        "overstocked": stock_engine.overstocked_items(),
    })


@app.route("/api/top-sellers")
def api_top_sellers():
    n = request.args.get("n", default=10, type=int)
    days = request.args.get("days", default=None, type=int)
    by = request.args.get("by", default="quantity")
    return jsonify(analytics_engine.top_sellers(n=n, days=days, by=by))


@app.route("/api/dead-stock")
def api_dead_stock():
    days = request.args.get("days", default=60, type=int)
    return jsonify(analytics_engine.dead_stock(days=days))


@app.route("/api/purchase-check", methods=["POST"])
def api_purchase_check():
    data = request.get_json(force=True)
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 0))
    if not product_id or quantity <= 0:
        return jsonify({"error": "product_id and a positive quantity are required"}), 400
    return jsonify(stock_engine.check_purchase(product_id, quantity))


@app.route("/api/sale", methods=["POST"])
def api_sale():
    data = request.get_json(force=True)
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 0))
    if not product_id or quantity <= 0:
        return jsonify({"error": "product_id and a positive quantity are required"}), 400
    result = stock_engine.record_sale(product_id, quantity)
    status = 400 if "error" in result else 200
    return jsonify(result), status


if __name__ == "__main__":
    ensure_seeded()
    app.run(debug=True, port=5000)
