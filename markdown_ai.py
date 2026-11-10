"""
markdown_ai.py
---------------
Zero-Waste Dynamic Markdown Engine (Unique AI Feature).
Designed specifically to prevent 100% dead-loss from expired stock in offline retail.

Algorithm:
1. Calculates remaining shelf life (days to expiry).
2. Calculates current sales velocity (avg daily units sold).
3. Forecasts if current stock will sell out before expiry at normal speed:
   Days_To_Sell = Current_Stock / Daily_Velocity
4. If Days_To_Sell > Days_To_Expiry, an expiry dead-loss is guaranteed.
5. Dynamically determines optimal markdown discount % to accelerate sales velocity,
   recovering cost and margin before the product turns into a complete write-off.
"""

from datetime import date, datetime, timedelta
from database import get_connection
from expiry import parse_date


def get_markdown_opportunities():
    """
    Evaluates all inventory products and identifies products at risk of expiring before selling out.
    Returns categorized markdown recommendations.
    """
    conn = get_connection()
    products = conn.execute("""
        SELECT p.*, 
               COALESCE((SELECT SUM(qty_sold) FROM sales_history sh 
                         WHERE sh.product_id = p.product_id 
                         AND sh.sale_date >= date('now', '-30 days')), 0) as sales_30d
        FROM products p
        WHERE p.expiry_date IS NOT NULL AND p.quantity > 0
        ORDER BY p.expiry_date ASC
    """).fetchall()
    conn.close()

    today = date.today()
    opportunities = []

    for p in products:
        exp_date = parse_date(p["expiry_date"])
        if not exp_date:
            continue

        days_to_expiry = (exp_date - today).days
        current_stock = p["quantity"]
        selling_price = p["price"]
        cost_price = p["cost_price"] or (selling_price * 0.75)
        current_discount = p["discount_pct"] or 0.0

        sales_30d = p["sales_30d"] or 0
        daily_velocity = round(sales_30d / 30.0, 2)
        if daily_velocity == 0:
            daily_velocity = 0.2  # Assume baseline trickle velocity

        days_to_sell = round(current_stock / daily_velocity, 1)

        # Analysis & Recommendation
        if days_to_expiry < 0:
            status = "expired"
            urgency = "Immediate Disposal"
            rec_discount = 0
            badge_class = "danger"
            action_text = "Expired: Write off stock immediately"
            at_risk_units = current_stock
            projected_loss = round(current_stock * cost_price, 2)
            estimated_recovery = 0.0
        elif days_to_expiry == 0:
            status = "critical"
            urgency = "Expires Today"
            rec_discount = 70.0
            badge_class = "danger"
            action_text = "Final clearance flash sale (70% OFF)"
            at_risk_units = current_stock
            projected_loss = round(current_stock * cost_price, 2)
            estimated_recovery = round(current_stock * selling_price * 0.30, 2)
        elif days_to_expiry <= 3:
            status = "critical"
            urgency = "Critical (< 3 days)"
            rec_discount = 50.0
            badge_class = "danger"
            action_text = "Apply 50% Flash Sale Markdown"
            at_risk_units = max(0, int(current_stock - (days_to_expiry * daily_velocity)))
            projected_loss = round(at_risk_units * cost_price, 2)
            estimated_recovery = round(current_stock * selling_price * 0.50, 2)
        elif days_to_expiry <= 7:
            status = "urgent"
            urgency = "Urgent (< 7 days)"
            rec_discount = 35.0
            badge_class = "warning"
            action_text = "Apply 35% Near-Expiry Markdown"
            at_risk_units = max(0, int(current_stock - (days_to_expiry * daily_velocity)))
            projected_loss = round(at_risk_units * cost_price, 2)
            estimated_recovery = round(current_stock * selling_price * 0.65, 2)
        elif days_to_expiry <= 15:
            status = "soon"
            urgency = "Expiring in 2 Weeks"
            rec_discount = 20.0
            badge_class = "warning"
            action_text = "Apply 20% Fast-Mover Markdown"
            at_risk_units = max(0, int(current_stock - (days_to_expiry * daily_velocity)))
            projected_loss = round(at_risk_units * cost_price, 2)
            estimated_recovery = round(current_stock * selling_price * 0.80, 2)
        elif days_to_expiry <= 30 and days_to_sell > days_to_expiry:
            status = "warning"
            urgency = "Slow Velocity vs Expiry"
            rec_discount = 10.0
            badge_class = "info"
            action_text = "Promotional 10% Discount to Boost Velocity"
            at_risk_units = max(0, int(current_stock - (days_to_expiry * daily_velocity)))
            projected_loss = round(at_risk_units * cost_price, 2)
            estimated_recovery = round(current_stock * selling_price * 0.90, 2)
        else:
            status = "safe"
            urgency = "Safe Pace"
            rec_discount = 0.0
            badge_class = "success"
            action_text = "Selling on track at normal price"
            at_risk_units = 0
            projected_loss = 0.0
            estimated_recovery = round(current_stock * selling_price, 2)

        discounted_price = round(selling_price * (1 - (rec_discount / 100.0)), 2)

        opportunities.append({
            "product_id": p["product_id"],
            "name": p["name"],
            "category": p["category"],
            "barcode": p["barcode"],
            "rack_location": p["rack_location"] or "A1",
            "quantity": current_stock,
            "expiry_date": p["expiry_date"],
            "days_to_expiry": days_to_expiry,
            "selling_price": selling_price,
            "cost_price": cost_price,
            "daily_velocity": daily_velocity,
            "days_to_sell": days_to_sell,
            "at_risk_units": at_risk_units,
            "projected_loss": projected_loss,
            "recommended_discount_pct": rec_discount,
            "discounted_price": discounted_price,
            "estimated_recovery": estimated_recovery,
            "current_applied_discount": current_discount,
            "status": status,
            "urgency": urgency,
            "badge_class": badge_class,
            "action_text": action_text,
        })

    # Sort so most urgent loss-prevention items appear at the top
    opportunities.sort(key=lambda x: (x["days_to_expiry"] if x["days_to_expiry"] >= 0 else -9999, -x["projected_loss"]))
    return opportunities


def apply_markdown_discount(product_id, discount_pct):
    """Applies a dynamic discount % to a product so POS rings it up at reduced price."""
    conn = get_connection()
    conn.execute(
        "UPDATE products SET discount_pct = ? WHERE product_id = ?",
        (float(discount_pct), product_id),
    )
    conn.commit()
    conn.close()
    return True


def clear_markdown_discount(product_id):
    """Restores full price."""
    conn = get_connection()
    conn.execute("UPDATE products SET discount_pct = 0.0 WHERE product_id = ?", (product_id,))
    conn.commit()
    conn.close()
    return True
