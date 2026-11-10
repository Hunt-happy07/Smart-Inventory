"""
expiry.py
---------
Small helper that turns an expiry date (YYYY-MM-DD text, or None) into a
status the UI can colour and animate.

Statuses:
    none      - product has no expiry date (e.g. a chair)
    expired   - date is in the past
    critical  - expires in 0-7 days
    soon      - expires in 8-EXPIRY_WARNING_DAYS days
    ok        - more than EXPIRY_WARNING_DAYS days left
"""

from datetime import date, datetime

EXPIRY_WARNING_DAYS = 30     # "expiring soon" window
EXPIRY_CRITICAL_DAYS = 7     # "act now" window


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def expiry_info(expiry_date, today=None):
    today = today or date.today()
    try:
        d = parse_date(expiry_date)
    except ValueError:
        d = None
    if d is None:
        return {"expiry_status": "none", "expiry_days": None, "expiry_label": "No expiry"}

    days = (d - today).days
    if days < 0:
        status, label = "expired", f"Expired {abs(days)} day{'s' if abs(days) != 1 else ''} ago"
    elif days == 0:
        status, label = "critical", "Expires today"
    elif days <= EXPIRY_CRITICAL_DAYS:
        status, label = "critical", f"Expires in {days} day{'s' if days != 1 else ''}"
    elif days <= EXPIRY_WARNING_DAYS:
        status, label = "soon", f"Expires in {days} days"
    else:
        status, label = "ok", f"{days} days left"
    return {"expiry_status": status, "expiry_days": days, "expiry_label": label}


def get_fefo_warehouse_pick_list(rack_filter=None):
    """
    FEFO (First-Expired, First-Out) Warehouse Picking Engine.
    Tells warehouse staff exactly which box/rack/shelf to pick first
    to prevent product spoilage and inventory waste.
    """
    from database import get_connection
    today = date.today()
    conn = get_connection()
    try:
        query = """
            SELECT product_id, name, category, price, cost_price, quantity,
                   barcode, expiry_date, rack_location, unit, discount_pct
            FROM products
            WHERE expiry_date IS NOT NULL AND expiry_date != '' AND quantity > 0
        """
        params = []
        if rack_filter and rack_filter != "ALL":
            query += " AND rack_location = ?"
            params.append(rack_filter)

        query += " ORDER BY expiry_date ASC, quantity DESC"
        rows = conn.execute(query, params).fetchall()

        pick_list = []
        for r in rows:
            p = dict(r)
            exp_info = expiry_info(p["expiry_date"], today)
            days = exp_info["expiry_days"]

            # Classify FEFO picking priority
            if days is not None and days < 0:
                priority = "EXPIRED_DISCARD"
                priority_label = "🚨 EXPIRED: Discard / Do Not Sell"
                action_instruction = f"Remove immediately from Rack {p.get('rack_location') or 'A1'}. Write off to avoid fines."
                badge_class = "badge-danger"
                pick_zone = "Zone 0 (Damaged/Expired Quarantine)"
                urgency_order = 0
            elif days is not None and days <= 7:
                priority = "PRIORITY_1_PICK"
                priority_label = "🔴 PICK FIRST: Expiring in <= 7 Days"
                action_instruction = f"PICK THIS BOX FIRST from Rack {p.get('rack_location') or 'A1'}. Move to Front Counter Clearance Shelf."
                badge_class = "badge-danger"
                pick_zone = "Zone 1 (Immediate Dispatch)"
                urgency_order = 1
            elif days is not None and days <= 30:
                priority = "PRIORITY_2_ROTATE"
                priority_label = "🟡 ACTIVE ROTATION: 8–30 Days"
                action_instruction = f"Pick from Rack {p.get('rack_location') or 'A1'}. Place in Front Display Row (Push newer boxes behind)."
                badge_class = "badge-warn"
                pick_zone = "Zone 2 (Active Stock Display)"
                urgency_order = 2
            else:
                priority = "PRIORITY_3_RESERVE"
                priority_label = f"🟢 FRESH RESERVE: {days} Days Left"
                action_instruction = f"Keep in Rack {p.get('rack_location') or 'A1'} Back-Row. Do not pick yet."
                badge_class = "badge-ok"
                pick_zone = "Zone 3 (Back-Row Reserve Storage)"
                urgency_order = 3

            p.update(exp_info)
            p["priority"] = priority
            p["priority_label"] = priority_label
            p["action_instruction"] = action_instruction
            p["badge_class"] = badge_class
            p["pick_zone"] = pick_zone
            p["urgency_order"] = urgency_order
            p["suggested_pick_qty"] = min(p["quantity"], 10 if days and days <= 7 else p["quantity"])

            pick_list.append(p)

        # Get all distinct rack locations for filtering
        racks_rows = conn.execute("""
            SELECT DISTINCT rack_location FROM products
            WHERE rack_location IS NOT NULL AND rack_location != ''
            ORDER BY rack_location ASC
        """).fetchall()
        all_racks = [r["rack_location"] for r in racks_rows]

        return {
            "pick_list": pick_list,
            "total_perishable_items": len(pick_list),
            "urgent_pick_count": sum(1 for p in pick_list if p["urgency_order"] <= 1),
            "all_racks": all_racks,
            "today_date": today.isoformat()
        }
    finally:
        conn.close()
