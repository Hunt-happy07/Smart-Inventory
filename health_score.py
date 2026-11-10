"""
health_score.py
---------------
Inventory health score (0-100, higher = healthier) built from five checks:
dead stock, overstock, stockout risk, data accuracy and (new) expiry risk.

Fixed to use the real tables of this project (products / sales_history).
Registered in app.py as a Flask Blueprint.
"""

from datetime import date, timedelta
from flask import Blueprint, jsonify, render_template

from database import get_connection
from expiry import expiry_info

health_bp = Blueprint("health_score", __name__)

DEAD_STOCK_DAYS = 30        # no sales in this many days -> "dead"
LEAD_TIME_DAYS = 7          # assumed supplier lead time
OVERSTOCK_MULTIPLIER = 3    # qty > 3x (avg daily demand * lead time) -> overstock
STOCKOUT_WINDOW_DAYS = 7    # will it run out within this many days?


def compute_health_metrics():
    conn = get_connection()
    products = conn.execute(
        "SELECT product_id, name, quantity, expiry_date FROM products ORDER BY name"
    ).fetchall()

    today = date.today()
    cutoff_dead = (today - timedelta(days=DEAD_STOCK_DAYS)).isoformat()
    cutoff_30 = (today - timedelta(days=30)).isoformat()

    total = len(products) or 1
    dead = overstock = stockout = bad_data = expiry_risk = 0
    breakdown = []

    for p in products:
        pid, qty = p["product_id"], p["quantity"] or 0

        last_sale = conn.execute(
            "SELECT MAX(sale_date) AS d FROM sales_history WHERE product_id = ?", (pid,)
        ).fetchone()["d"]
        is_dead = last_sale is None or last_sale < cutoff_dead

        sold_30 = conn.execute(
            "SELECT COALESCE(SUM(qty_sold), 0) AS s FROM sales_history WHERE product_id = ? AND sale_date >= ?",
            (pid, cutoff_30),
        ).fetchone()["s"]
        avg_daily = sold_30 / 30.0

        is_over = avg_daily > 0 and qty > avg_daily * LEAD_TIME_DAYS * OVERSTOCK_MULTIPLIER
        cover = (qty / avg_daily) if avg_daily > 0 else float("inf")
        is_stockout = cover < STOCKOUT_WINDOW_DAYS
        is_bad = qty < 0

        ex = expiry_info(p["expiry_date"])
        is_expiry = ex["expiry_status"] in ("expired", "critical", "soon")

        dead += is_dead
        overstock += is_over
        stockout += is_stockout
        bad_data += is_bad
        expiry_risk += is_expiry

        breakdown.append({
            "product_id": pid,
            "name": p["name"],
            "current_qty": qty,
            "avg_daily_demand": round(avg_daily, 2),
            "days_of_cover": None if cover == float("inf") else round(cover, 1),
            "dead_stock": bool(is_dead),
            "overstock_risk": bool(is_over),
            "stockout_risk": bool(is_stockout),
            "expiry_status": ex["expiry_status"],
            "expiry_label": ex["expiry_label"],
        })
    conn.close()

    pct = lambda n: round(100 * n / total, 1)
    metrics = {
        "dead_stock_pct": pct(dead),
        "overstock_risk_pct": pct(overstock),
        "stockout_risk_pct": pct(stockout),
        "expiry_risk_pct": pct(expiry_risk),
        "inventory_accuracy_pct": round(100 - pct(bad_data), 1),
    }
    overall = round(sum([
        100 - metrics["dead_stock_pct"],
        100 - metrics["overstock_risk_pct"],
        100 - metrics["stockout_risk_pct"],
        100 - metrics["expiry_risk_pct"],
        metrics["inventory_accuracy_pct"],
    ]) / 5, 1)

    return {"overall_score": overall, "metrics": metrics, "breakdown": breakdown}


@health_bp.route("/api/health-score")
def api_health_score():
    return jsonify(compute_health_metrics())


@health_bp.route("/health-score")
def health_score_page():
    return render_template("health_score.html", data=compute_health_metrics())
