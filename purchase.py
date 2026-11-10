"""
purchase.py
-----------
Suppliers and Automated Purchase Order (PO) Management for Smart Inventory Pro.
Features:
- Supplier directory with lead times and reliability ratings
- AI-driven auto PO generation for low-stock & stockout-risk products
- 1-Click PO receipt that automatically replenishes physical stock
"""

import random
from datetime import datetime, date, timedelta
from database import get_connection
from ml_model import forecast_product_demand


def get_all_suppliers():
    conn = get_connection()
    suppliers = conn.execute("""
        SELECT s.*, p.name as primary_product_name,
               (SELECT COUNT(*) FROM purchase_orders po WHERE po.supplier_id = s.supplier_id) as total_pos
        FROM suppliers s
        LEFT JOIN products p ON s.product_id = p.product_id
        ORDER BY s.name ASC
    """).fetchall()
    conn.close()
    return [dict(s) for s in suppliers]


def get_all_purchase_orders():
    conn = get_connection()
    pos = conn.execute("""
        SELECT po.*, 
               (SELECT COUNT(*) FROM po_items poi WHERE poi.po_id = po.po_id) as total_items
        FROM purchase_orders po
        ORDER BY po.po_id DESC
    """).fetchall()
    conn.close()
    return [dict(p) for p in pos]


def get_po_details(po_id):
    conn = get_connection()
    po = conn.execute("SELECT * FROM purchase_orders WHERE po_id = ?", (po_id,)).fetchone()
    if not po:
        conn.close()
        return None

    items = conn.execute("SELECT * FROM po_items WHERE po_id = ?", (po_id,)).fetchall()
    supplier = conn.execute("SELECT * FROM suppliers WHERE supplier_id = ?", (po["supplier_id"],)).fetchone()
    conn.close()

    return {
        "po": dict(po),
        "items": [dict(i) for i in items],
        "supplier": dict(supplier) if supplier else None,
    }


def generate_ai_reorder_recommendations():
    """
    Scans entire inventory to find items needing restock based on current stock,
    reorder level, and AI demand forecasting.
    """
    conn = get_connection()
    products = conn.execute("SELECT product_id, name, category, quantity, reorder_level, cost_price, price FROM products ORDER BY name").fetchall()
    suppliers = conn.execute("SELECT supplier_id, name, lead_time_days, product_id FROM suppliers").fetchall()
    conn.close()

    # Map product to supplier
    supp_map = {}
    default_supp = suppliers[0] if suppliers else None
    for s in suppliers:
        if s["product_id"]:
            supp_map[s["product_id"]] = s

    recommendations = []
    for p in products:
        pid = p["product_id"]
        qty = p["quantity"]
        reorder_lvl = p["reorder_level"]

        # Run AI forecast
        fc = forecast_product_demand(pid, horizon_days=14)
        rec_qty = fc["recommended_reorder_qty"] if fc else max(0, reorder_lvl * 2 - qty)

        # Flag if below reorder level or forecast recommends restock
        if qty <= reorder_lvl or rec_qty > 0:
            supp = supp_map.get(pid, default_supp)
            cost_p = p["cost_price"] or (p["price"] * 0.75)
            order_qty = max(rec_qty, max(10, reorder_lvl - qty + 15))

            recommendations.append({
                "product_id": pid,
                "product_name": p["name"],
                "category": p["category"],
                "current_stock": qty,
                "reorder_level": reorder_lvl,
                "recommended_order_qty": order_qty,
                "cost_per_unit": round(cost_p, 2),
                "total_cost": round(order_qty * cost_p, 2),
                "supplier_id": supp["supplier_id"] if supp else 1,
                "supplier_name": supp["name"] if supp else "General Supplier",
                "reason": fc["stockout_risk"] if fc else "Below Reorder Level",
            })

    return recommendations


def create_purchase_order(supplier_id, items, expected_days=7):
    """
    Creates a new Purchase Order from a list of {product_id, quantity, unit_cost}.
    """
    conn = get_connection()
    cur = conn.cursor()

    supp = cur.execute("SELECT name FROM suppliers WHERE supplier_id = ?", (supplier_id,)).fetchone()
    supplier_name = supp["name"] if supp else "Supplier"

    today_str = datetime.now().strftime("%Y%m%d")
    rand_suffix = random.randint(100, 999)
    po_number = f"PO-{today_str}-{rand_suffix}"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expected_delivery = (date.today() + timedelta(days=expected_days)).isoformat()

    total_amount = sum(it["quantity"] * it["unit_cost"] for it in items)

    cur.execute("""
        INSERT INTO purchase_orders (po_number, supplier_id, supplier_name, status, total_amount, expected_delivery, created_at)
        VALUES (?, ?, ?, 'Ordered', ?, ?, ?)
    """, (po_number, supplier_id, supplier_name, total_amount, expected_delivery, now_str))
    po_id = cur.lastrowid

    for it in items:
        cur.execute("""
            INSERT INTO po_items (po_id, product_id, product_name, quantity, unit_cost, total_cost)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (po_id, it["product_id"], it["product_name"], it["quantity"], it["unit_cost"], it["quantity"] * it["unit_cost"]))

    conn.commit()
    conn.close()
    return po_id, po_number


def receive_purchase_order(po_id):
    """
    Marks a PO as received and automatically increments physical product inventory!
    """
    conn = get_connection()
    cur = conn.cursor()

    po = cur.execute("SELECT * FROM purchase_orders WHERE po_id = ?", (po_id,)).fetchone()
    if not po or po["status"] == "Received":
        conn.close()
        return False, "PO not found or already received."

    items = cur.execute("SELECT * FROM po_items WHERE po_id = ?", (po_id,)).fetchall()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for it in items:
        # Increment product stock
        cur.execute("UPDATE products SET quantity = quantity + ? WHERE product_id = ?", (it["quantity"], it["product_id"]))
        # Log adjustment
        cur.execute("""
            INSERT INTO stock_adjustments (product_id, type, qty_change, old_qty, new_qty, reason, created_at)
            VALUES (?, 'supplier_in', ?, (SELECT quantity - ? FROM products WHERE product_id = ?), 
                    (SELECT quantity FROM products WHERE product_id = ?), ?, ?)
        """, (it["product_id"], it["quantity"], it["quantity"], it["product_id"], it["product_id"], f"Received {po['po_number']}", now_str))

    cur.execute("UPDATE purchase_orders SET status = 'Received' WHERE po_id = ?", (po_id,))
    conn.commit()
    conn.close()
    return True, f"Purchase Order {po['po_number']} received. Stock updated successfully."
