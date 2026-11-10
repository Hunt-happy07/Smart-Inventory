"""
anomaly_ai.py
--------------
Ghost Stock & Inventory Shrinkage Anomaly Detection (Unique AI Feature).
Detects pilferage, misplaced items, and phantom inventory for offline retail shops.

Algorithms:
1. Velocity Stagnation Anomaly (Ghost Stock):
   If an item with high historical demand suddenly has 0 sales for >7 days while
   the system reports positive stock, it is likely hidden behind racks or stolen.
2. High Shrinkage / Damage Anomaly:
   Flags items with disproportionately high write-offs compared to units sold.
3. Rapid 60-Second Cycle Count Generator:
   Selects the 5 highest-risk items for the shopkeeper to physically check today.
"""

from datetime import date, timedelta
from database import get_connection


def detect_inventory_anomalies():
    """
    Scans the inventory to identify discrepancies, ghost items, and shrinkage patterns.
    """
    conn = get_connection()
    products = conn.execute("""
        SELECT p.*,
               COALESCE((SELECT SUM(qty_sold) FROM sales_history sh 
                         WHERE sh.product_id = p.product_id 
                         AND sh.sale_date >= date('now', '-30 days')), 0) as sales_30d,
               COALESCE((SELECT SUM(qty_sold) FROM sales_history sh 
                         WHERE sh.product_id = p.product_id 
                         AND sh.sale_date >= date('now', '-7 days')), 0) as sales_7d,
               COALESCE((SELECT MAX(sale_date) FROM sales_history sh 
                         WHERE sh.product_id = p.product_id), NULL) as last_sale_date,
               COALESCE((SELECT SUM(ABS(qty_change)) FROM stock_adjustments sa 
                         WHERE sa.product_id = p.product_id 
                         AND sa.type IN ('damage_writeoff', 'audit_discrepancy')), 0) as total_shrinkage_units
        FROM products p
        ORDER BY p.name ASC
    """).fetchall()
    conn.close()

    anomalies = []
    cycle_count_candidates = []

    for p in products:
        pid = p["product_id"]
        name = p["name"]
        current_stock = p["quantity"]
        sales_30d = p["sales_30d"]
        sales_7d = p["sales_7d"]
        last_sale = p["last_sale_date"]
        shrinkage = p["total_shrinkage_units"]
        rack = p["rack_location"] or "A1"

        avg_daily = round(sales_30d / 30.0, 2)
        anomaly_detected = False
        anomaly_type = None
        severity = "info"
        reason = ""
        action = ""

        # Check 1: Ghost Stock Anomaly (Fast mover has stopped selling while stock > 0)
        if avg_daily >= 1.5 and sales_7d == 0 and current_stock > 5:
            anomaly_detected = True
            anomaly_type = "Ghost Stock / Shelf Disconnect"
            severity = "high"
            reason = f"Normal sales: {avg_daily}/day, but 0 sold in last 7 days despite {current_stock} recorded on shelf."
            action = f"Inspect rack {rack}. Product may be misplaced behind other items or stolen."
            cycle_count_candidates.append({"product_id": pid, "name": name, "rack": rack, "reason": reason, "priority": 1})

        # Check 2: High Shrinkage / Breakage Ratio
        elif shrinkage > 10 and (shrinkage / max(1, sales_30d)) > 0.25:
            anomaly_detected = True
            anomaly_type = "High Pilferage / Breakage Loss"
            severity = "warning"
            reason = f"{shrinkage} units lost to damage/discrepancies vs {sales_30d} sold this month."
            action = "Check storage handling and shelf security."
            cycle_count_candidates.append({"product_id": pid, "name": name, "rack": rack, "reason": reason, "priority": 2})

        # Check 3: Negative or Near-Zero Stock Discrepancy
        elif current_stock <= 0:
            anomaly_detected = True
            anomaly_type = "Stockout / Out-of-Stock Discrepancy"
            severity = "warning"
            reason = f"Current recorded stock is {current_stock}."
            action = "Restock immediately or adjust count if items are physically present."
            cycle_count_candidates.append({"product_id": pid, "name": name, "rack": rack, "reason": reason, "priority": 3})

        if anomaly_detected:
            anomalies.append({
                "product_id": pid,
                "name": name,
                "category": p["category"],
                "barcode": p["barcode"],
                "rack_location": rack,
                "quantity": current_stock,
                "avg_daily_sales": avg_daily,
                "last_sale_date": last_sale or "Never",
                "anomaly_type": anomaly_type,
                "severity": severity,
                "reason": reason,
                "action": action,
            })

    # Sort cycle count recommendations by priority
    cycle_count_candidates.sort(key=lambda x: x["priority"])
    quick_cycle_count = cycle_count_candidates[:5]

    return {
        "anomalies": anomalies,
        "total_anomalies": len(anomalies),
        "quick_cycle_count": quick_cycle_count,
    }


def record_stock_audit_adjustment(product_id, physical_qty, reason="Periodic Physical Audit"):
    """
    Reconciles physical count with system stock and logs the discrepancy into stock_adjustments.
    """
    conn = get_connection()
    row = conn.execute("SELECT quantity, name FROM products WHERE product_id = ?", (product_id,)).fetchone()
    if not row:
        conn.close()
        return False, "Product not found."

    old_qty = row["quantity"]
    diff = physical_qty - old_qty
    now_str = date.today().isoformat()

    conn.execute("UPDATE products SET quantity = ? WHERE product_id = ?", (physical_qty, product_id))
    conn.execute("""
        INSERT INTO stock_adjustments (product_id, type, qty_change, old_qty, new_qty, reason, created_at)
        VALUES (?, 'audit_discrepancy', ?, ?, ?, ?, ?)
    """, (product_id, diff, old_qty, physical_qty, reason, now_str))

    conn.commit()
    conn.close()
    return True, f"Stock updated for {row['name']} from {old_qty} to {physical_qty} (Discrepancy: {diff:+d})."
