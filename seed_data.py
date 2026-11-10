"""
seed_data.py
------------
Populates the database with realistic retail products, 2 years of daily sales history,
offline suppliers, customer khata accounts, and shelf locations.

Run: python seed_data.py
"""

import random
import math
from datetime import date, timedelta, datetime
from database import get_connection, init_db


def ean13(first12):
    """Adds the EAN-13 check digit so real barcode scanners accept the code."""
    digits = [int(c) for c in first12]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits))
    return first12 + str((10 - total % 10) % 10)


# (name, category, price, cost_price, qty, reorder_level, expiry_offset_days, rack, unit)
PRODUCTS = [
    ("Wireless Optical Mouse", "Electronics", 499.0, 310.0, 45, 15, None, "Rack E-1", "pcs"),
    ("Bluetooth Speaker 10W", "Electronics", 1299.0, 850.0, 22, 10, None, "Rack E-2", "pcs"),
    ("Classmate Notebook A5 200pg", "Stationery", 60.0, 38.0, 150, 40, None, "Shelf S-1", "pcs"),
    ("Executive Office Desk Lamp", "Electronics", 899.0, 520.0, 18, 8, None, "Rack E-3", "pcs"),
    ("Whiteboard Marker Set (4 Colors)", "Stationery", 160.0, 95.0, 65, 20, 28, "Shelf S-2", "box"),   # Expiring soon
    ("USB-C Fast Charging Cable 1.5m", "Electronics", 299.0, 140.0, 80, 25, None, "Rack E-4", "pcs"),
    ("Dettol Hand Sanitizer 500ml", "Health & Hygiene", 199.0, 120.0, 50, 15, 12, "Rack M-1", "bottle"), # Expiring soon
    ("Maggi 2-Minute Noodles (Family Pack)", "Grocery & Food", 140.0, 105.0, 85, 30, -3, "Aisle G-1", "pack"),  # Already expired!
    ("Tata Salt 1kg", "Grocery & Food", 28.0, 21.0, 120, 40, 180, "Aisle G-2", "packet"),
    ("Fortune Sunlite Sunflower Oil 1L", "Grocery & Food", 165.0, 138.0, 35, 15, 90, "Aisle G-3", "pouch"),
    ("Britannia Good Day Biscuits Box", "Grocery & Food", 120.0, 88.0, 40, 12, 5, "Aisle G-1", "box"),    # Critical (5 days)
    ("Cadbury Dairy Milk Silk 150g", "Grocery & Food", 175.0, 130.0, 28, 10, 2, "Checkout Chiller", "bar"), # Critical (2 days)
    ("Himalaya Neem Face Wash 150ml", "Personal Care", 220.0, 155.0, 45, 12, 360, "Rack P-1", "tube"),
    ("Duracell AA Batteries (Pack of 4)", "Electronics", 180.0, 115.0, 90, 25, 720, "Counter Front", "pack"),
    ("Amul Taaza Milk 1L Tetra", "Dairy", 74.0, 62.0, 15, 20, 1, "Cold Storage", "packet"),             # Expires tomorrow!
]

SUPPLIERS = [
    ("Apex Metro Distributors", "9876543210", "orders@apexmetro.in", 4, 98.0),
    ("Shree Ganesh FMCG Wholesalers", "9123456780", "sales@ganeshfmcg.com", 3, 94.5),
    ("National Stationery & Paper Mart", "9988776655", "info@nationalpaper.in", 7, 91.0),
    ("Modern Tech Supplies Hub", "9765432109", "contact@moderntechhub.com", 5, 96.0),
]

CUSTOMERS = [
    ("Ramesh Sharma (Flat 302)", "9876501234", 1450.0, 5000.0, "Regular customer, pays on 1st of month"),
    ("Priya Patel (Greenwood Villa)", "9812345678", 680.0, 3000.0, "Prefers UPI payments"),
    ("Dr. S. K. Verma (Clinic)", "9899887766", 3250.0, 10000.0, "Bulk monthly stationery & refreshments"),
    ("Anand Kumar (Shop #4)", "9711223344", 0.0, 4000.0, "Immediate cash payer"),
    ("Sunita Devi (B-Block)", "9955443322", 890.0, 2500.0, "Sends maid for daily groceries"),
]


def seed_database():
    init_db(verbose=False)
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM products")
    cur.execute("DELETE FROM suppliers")
    cur.execute("DELETE FROM sales_history")
    cur.execute("DELETE FROM customers")
    cur.execute("DELETE FROM customer_transactions")
    cur.execute("DELETE FROM bills")
    cur.execute("DELETE FROM bill_items")
    cur.execute("DELETE FROM purchase_orders")
    cur.execute("DELETE FROM po_items")
    cur.execute("DELETE FROM stock_adjustments")
    cur.execute("DELETE FROM theft_incidents")

    product_ids = []
    today = date.today()

    # 1. Seed Products
    for i, (name, cat, price, cost_price, qty, reorder, exp_offset, rack, unit) in enumerate(PRODUCTS, start=1):
        barcode = ean13(f"890123400{i:03d}")
        expiry = (today + timedelta(days=exp_offset)).isoformat() if exp_offset is not None else None
        
        # Initial dynamic markdown for items very close to expiry
        discount_pct = 0.0
        if exp_offset is not None:
            if exp_offset <= 2:
                discount_pct = 50.0
            elif exp_offset <= 5:
                discount_pct = 30.0

        # Evaluate theft risk
        name_lower = name.lower()
        theft_risk = "High" if (price >= 400 or "battery" in name_lower or "silk" in name_lower or "face wash" in name_lower) else ("Medium" if price >= 150 else "Low")
        tag_req = 1 if theft_risk == "High" else 0

        cur.execute("""
            INSERT INTO products (name, category, price, cost_price, quantity, reorder_level, barcode, expiry_date, rack_location, unit, discount_pct, theft_risk_level, security_tag_required)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, cat, price, cost_price, qty, reorder, barcode, expiry, rack, unit, discount_pct, theft_risk, tag_req))
        product_ids.append(cur.lastrowid)

    # 2. Seed Suppliers
    supplier_ids = []
    for i, (sname, contact, email, lead_time, rel_score) in enumerate(SUPPLIERS):
        pid = product_ids[i % len(product_ids)]
        cur.execute("""
            INSERT INTO suppliers (name, contact, email, product_id, lead_time_days, reliability_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sname, contact, email, pid, lead_time, rel_score))
        supplier_ids.append(cur.lastrowid)

    # 3. Seed Customers & Initial Khata Balances
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for name, phone, balance, credit_limit, notes in CUSTOMERS:
        cur.execute("""
            INSERT INTO customers (name, phone, balance, credit_limit, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, phone, balance, credit_limit, notes, now_str))
        cid = cur.lastrowid
        if balance > 0:
            cur.execute("""
                INSERT INTO customer_transactions (customer_id, bill_id, type, amount, balance_after, notes, created_at)
                VALUES (?, NULL, 'credit_added', ?, ?, 'Opening Balance / Previous Store Credit', ?)
            """, (cid, balance, balance, now_str))

    # 4. Generate 2 Years of Sales History for ML
    days = 730
    start_date = today - timedelta(days=days)
    for idx, pid in enumerate(product_ids):
        base_demand = random.uniform(4, 14)
        trend = random.uniform(-0.001, 0.008)
        weekly_amp = random.uniform(0.8, 2.5)
        yearly_amp = random.uniform(1.2, 3.5)

        rows = []
        for d in range(days):
            current_day = start_date + timedelta(days=d)
            dow = current_day.weekday()
            day_of_year = current_day.timetuple().tm_yday

            # Demand model with weekend and holiday boosts
            weekend_boost = weekly_amp if dow in (5, 6) else 0.0
            seasonal_boost = yearly_amp * math.sin(2 * math.pi * day_of_year / 365)
            noise = random.gauss(0, 1.2)

            qty = max(0, int(round(base_demand + (trend * d) + weekend_boost + seasonal_boost + noise)))
            rows.append((pid, current_day.isoformat(), qty))

        cur.executemany("INSERT INTO sales_history (product_id, sale_date, qty_sold) VALUES (?, ?, ?)", rows)

    # 5. Seed a couple of initial bills
    cur.execute("""
        INSERT INTO bills (bill_number, customer_id, customer_name, customer_phone, subtotal, discount_total, tax_rate, tax_amount, grand_total, payment_mode, payment_status, created_at)
        VALUES ('INV-20261014-1001', 1, 'Ramesh Sharma (Flat 302)', '9876501234', 599.0, 50.0, 5.0, 27.45, 576.45, 'credit', 'Credit Due', ?)
    """, (now_str,))
    sample_bill_id = cur.lastrowid
    cur.execute("""
        INSERT INTO bill_items (bill_id, product_id, product_name, quantity, unit_price, discount_pct, total_price)
        VALUES (?, 1, 'Wireless Optical Mouse', 1, 499.0, 0.0, 499.0)
    """, (sample_bill_id,))

    # 6. Seed Sample Theft / Loss Incidents
    cur.execute("""
        INSERT INTO theft_incidents (incident_date, product_id, product_name, units_stolen, estimated_loss, rack_location, theft_type, cctv_timestamp, notes, created_at)
        VALUES (?, ?, 'Duracell AA Batteries (Pack of 4)', 2, 230.0, 'Counter Front', 'customer_shoplifting', 'CAM-02 18:42:15', 'Pocketed by customer during peak rush', ?)
    """, (today.isoformat(), product_ids[13], now_str))

    cur.execute("""
        INSERT INTO theft_incidents (incident_date, product_id, product_name, units_stolen, estimated_loss, rack_location, theft_type, cctv_timestamp, notes, created_at)
        VALUES (?, ?, 'Cadbury Dairy Milk Silk 150g', 1, 130.0, 'Checkout Chiller', 'customer_shoplifting', 'CAM-01 19:15:00', 'Concealed in jacket pocket near chiller blindspot', ?)
    """, (today.isoformat(), product_ids[11], now_str))

    conn.commit()
    conn.close()
    print("Database successfully seeded with realistic offline shop inventory, ML history, suppliers, and khata records!")


if __name__ == "__main__":
    seed_database()
