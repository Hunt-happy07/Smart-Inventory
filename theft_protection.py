"""
theft_protection.py
--------------------
Store Theft Protection & Loss Prevention System.
Features:
- High-Theft Risk Scoring & EAS Tagging recommendations
- Shoplifting & Internal Pilferage Incident Logging
- Rack / Aisle Blindspot Heatmap (CCTV alignment recommendations)
- Exit Gate Receipt Verification Scanner (Anti-shoplifting bag check tool)
- Automated stock decrement & theft loss write-off
"""

from datetime import datetime, date
from database import get_connection


# High-theft category heuristics in retail (compact, high-resale or pocketable goods)
HIGH_THEFT_CATEGORIES = {"Electronics", "Personal Care", "Health & Hygiene", "Dairy", "Grocery & Food"}
HIGH_THEFT_KEYWORDS = {"battery", "batteries", "cable", "mouse", "chocolate", "silk", "face wash", "sanitizer", "razor", "blade"}


def evaluate_product_theft_risk(name, category, price):
    """
    Evaluates theft risk based on product value density, compact footprint,
    and historical retail shoplifting data.
    """
    name_lower = name.lower()
    is_keyword_match = any(kw in name_lower for kw in HIGH_THEFT_KEYWORDS)

    if (category in HIGH_THEFT_CATEGORIES and is_keyword_match) or price >= 400.0:
        return "High", 1  # High risk, Security Tag recommended
    elif category in HIGH_THEFT_CATEGORIES or price >= 150.0:
        return "Medium", 0
    else:
        return "Low", 0


def update_all_theft_risk_scores():
    """Batch-updates theft risk levels for all existing products."""
    conn = get_connection()
    products = conn.execute("SELECT product_id, name, category, price FROM products").fetchall()
    for p in products:
        risk, tag_req = evaluate_product_theft_risk(p["name"], p["category"], p["price"])
        conn.execute("""
            UPDATE products SET theft_risk_level = ?, security_tag_required = ?
            WHERE product_id = ?
        """, (risk, tag_req, p["product_id"]))
    conn.commit()
    conn.close()


def log_theft_incident(product_id, units_stolen, theft_type, cctv_timestamp="", notes=""):
    """
    Logs a theft/shoplifting incident, automatically records a stock adjustment,
    and decrements physical stock.
    theft_type: 'customer_shoplifting' | 'internal_pilferage' | 'under_ringing' | 'unaccounted_variance'
    """
    units_stolen = int(units_stolen)
    if units_stolen <= 0:
        return False, "Units stolen must be at least 1."

    conn = get_connection()
    cur = conn.cursor()

    prod = cur.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
    if not prod:
        conn.close()
        return False, "Product not found."

    cost_price = prod["cost_price"] or (prod["price"] * 0.75)
    estimated_loss = round(units_stolen * cost_price, 2)
    today_str = date.today().isoformat()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rack = prod["rack_location"] or "A1"
    old_qty = prod["quantity"]
    new_qty = max(0, old_qty - units_stolen)

    # 1. Insert into theft_incidents
    cur.execute("""
        INSERT INTO theft_incidents (
            incident_date, product_id, product_name, units_stolen,
            estimated_loss, rack_location, theft_type, cctv_timestamp,
            notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today_str, product_id, prod["name"], units_stolen,
        estimated_loss, rack, theft_type, cctv_timestamp.strip(),
        notes.strip(), now_str
    ))
    incident_id = cur.lastrowid

    # 2. Adjust product physical stock
    cur.execute("UPDATE products SET quantity = ? WHERE product_id = ?", (new_qty, product_id))

    # 3. Log stock adjustment audit
    cur.execute("""
        INSERT INTO stock_adjustments (product_id, type, qty_change, old_qty, new_qty, reason, created_at)
        VALUES (?, 'damage_writeoff', ?, ?, ?, ?, ?)
    """, (product_id, -units_stolen, old_qty, new_qty, f"Theft write-off: {theft_type} (Incident #{incident_id})", now_str))

    conn.commit()
    conn.close()

    return True, {
        "incident_id": incident_id,
        "product_name": prod["name"],
        "units_stolen": units_stolen,
        "estimated_loss": estimated_loss,
        "new_stock": new_qty,
    }


def get_theft_analytics():
    """
    Returns analytics summary: total losses, theft incidents list,
    rack blindspots, and high-theft products needing security tags.
    """
    conn = get_connection()
    
    # Total loss stats
    stats_row = conn.execute("""
        SELECT 
            COALESCE(SUM(estimated_loss), 0) as total_loss_amount,
            COALESCE(SUM(units_stolen), 0) as total_units_stolen,
            COUNT(*) as total_incidents
        FROM theft_incidents
    """).fetchone()

    total_loss = round(stats_row["total_loss_amount"], 2)
    total_units = stats_row["total_units_stolen"]
    total_incidents = stats_row["total_incidents"]

    # Incidents list
    incidents = conn.execute("""
        SELECT ti.*, p.barcode
        FROM theft_incidents ti
        LEFT JOIN products p ON ti.product_id = p.product_id
        ORDER BY ti.incident_id DESC LIMIT 50
    """).fetchall()

    # Rack / Aisle Blindspot Heatmap
    rack_hotspots = conn.execute("""
        SELECT rack_location, 
               COUNT(*) as incident_count, 
               SUM(units_stolen) as units_lost,
               SUM(estimated_loss) as total_loss
        FROM theft_incidents
        GROUP BY rack_location
        ORDER BY total_loss DESC LIMIT 10
    """).fetchall()

    # High Theft Risk Products
    high_theft_products = conn.execute("""
        SELECT * FROM products 
        WHERE theft_risk_level = 'High' OR security_tag_required = 1
        ORDER BY price DESC
    """).fetchall()

    conn.close()

    return {
        "total_loss": total_loss,
        "total_units": total_units,
        "total_incidents": total_incidents,
        "incidents": [dict(i) for i in incidents],
        "rack_hotspots": [dict(r) for r in rack_hotspots],
        "high_theft_products": [dict(p) for p in high_theft_products],
    }


def verify_exit_receipt(bill_number):
    """
    Exit Gate Audit tool: Security guard scans receipt barcode to verify paid items.
    """
    conn = get_connection()
    bill = conn.execute("SELECT * FROM bills WHERE bill_number = ?", (bill_number.strip(),)).fetchone()
    if not bill:
        conn.close()
        return None, "Invalid Receipt Number: No matching bill found in system."

    items = conn.execute("""
        SELECT bi.*, p.security_tag_required, p.theft_risk_level, p.category, p.rack_location
        FROM bill_items bi
        LEFT JOIN products p ON bi.product_id = p.product_id
        WHERE bi.bill_id = ?
    """, (bill["bill_id"],)).fetchall()
    conn.close()

    items_list = [dict(i) for i in items]
    security_tag_count = sum(1 for i in items_list if i.get("security_tag_required") == 1)

    return {
        "bill": dict(bill),
        "items": items_list,
        "total_items_count": sum(i["quantity"] for i in items_list),
        "security_tag_count": security_tag_count,
    }, "Verified"
