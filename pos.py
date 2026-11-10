"""
pos.py
------
Point of Sale (POS) Billing Engine for offline retail shops.
Features:
- Instant barcode lookup and item additions
- Automatic stock deduction
- Real-time ML sales history logging
- Integration with Smart Khata (Credit Ledger)
- Thermal receipt generator format (58mm/80mm) and invoice view
"""

import random
from datetime import datetime, date
from database import get_connection, get_setting


def generate_bill_number():
    """Generates an offline invoice number like INV-20261014-4821."""
    today_str = datetime.now().strftime("%Y%m%d")
    rand_suffix = random.randint(1000, 9999)
    return f"INV-{today_str}-{rand_suffix}"


def create_sale_bill(data):
    """
    Creates a new sale bill, decrements stock, updates sales_history for ML,
    and updates customer khata if paid on credit.
    data format:
    {
        "customer_id": int or None,
        "customer_name": str,
        "customer_phone": str,
        "payment_mode": "cash" | "upi" | "card" | "credit",
        "tax_rate": float (e.g. 5.0),
        "items": [
            {"product_id": int, "quantity": int, "discount_pct": float}
        ]
    }
    """
    items_data = data.get("items", [])
    if not items_data:
        return False, "Cart is empty. Add at least one product."

    conn = get_connection()
    try:
        cur = conn.cursor()

        # Verify all items and check stock
        verified_items = []
        subtotal = 0.0
        discount_total = 0.0

        for item in items_data:
            try:
                pid = int(item.get("product_id", 0))
            except (ValueError, TypeError):
                continue

            try:
                qty = int(item.get("quantity", 1))
            except (ValueError, TypeError):
                qty = 1

            if qty <= 0:
                continue

            prod = cur.execute("SELECT * FROM products WHERE product_id = ?", (pid,)).fetchone()
            if not prod:
                return False, f"Product ID {pid} not found."

            if prod["quantity"] < qty:
                return False, f"Insufficient stock for '{prod['name']}'. In stock: {prod['quantity']}, requested: {qty}."

            unit_price = float(prod["price"] or 0.0)

            # Safely parse discount_pct
            raw_discount = item.get("discount_pct")
            if raw_discount is None or raw_discount == "":
                discount_pct = float(prod["discount_pct"] or 0.0)
            else:
                try:
                    discount_pct = float(raw_discount)
                except (ValueError, TypeError):
                    discount_pct = 0.0

            item_gross = unit_price * qty
            item_discount = round(item_gross * (discount_pct / 100.0), 2)
            item_total = round(item_gross - item_discount, 2)

            subtotal += item_gross
            discount_total += item_discount

            verified_items.append({
                "product_id": pid,
                "product_name": prod["name"],
                "unit_price": unit_price,
                "quantity": qty,
                "discount_pct": discount_pct,
                "total_price": item_total,
                "current_stock": prod["quantity"],
            })

        if not verified_items:
            return False, "No valid items to bill."

        # Safely parse tax_rate
        raw_tax = data.get("tax_rate")
        try:
            tax_rate = float(raw_tax) if raw_tax is not None and raw_tax != "" else 0.0
        except (ValueError, TypeError):
            tax_rate = 0.0

        taxable_amount = subtotal - discount_total
        tax_amount = round(taxable_amount * (tax_rate / 100.0), 2) if tax_rate > 0 else 0.0
        grand_total = round(taxable_amount + tax_amount, 2)

        bill_number = generate_bill_number()

        # Safely parse customer_id
        raw_cust_id = data.get("customer_id")
        try:
            customer_id = int(raw_cust_id) if raw_cust_id not in (None, "", "null") else None
        except (ValueError, TypeError):
            customer_id = None

        customer_name = (data.get("customer_name") or "Walk-in Customer").strip() or "Walk-in Customer"
        customer_phone = (data.get("customer_phone") or "").strip()
        payment_mode = (data.get("payment_mode") or "cash").strip().lower()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_str = date.today().isoformat()

        raw_offline = data.get("is_offline")
        is_offline = 1 if raw_offline in (True, 1, "true", "1") else 0
        sync_status = "pending_sync" if is_offline else "synced"
        upi_ref = (data.get("upi_ref") or "").strip()

        # In offline mode, ONLY Cash payment mode is permitted
        if is_offline and payment_mode != "cash":
            return False, "Offline Mode Active: Internet/Server is offline. Only Cash payments are permitted."

        # 1. Insert into bills table
        cur.execute("""
            INSERT INTO bills (
                bill_number, customer_id, customer_name, customer_phone,
                subtotal, discount_total, tax_rate, tax_amount, grand_total,
                payment_mode, payment_status, created_at, is_offline, sync_status, upi_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            bill_number, customer_id, customer_name, customer_phone,
            subtotal, discount_total, tax_rate, tax_amount, grand_total,
            payment_mode, "Paid" if payment_mode != "credit" else "Credit Due", now_str,
            is_offline, sync_status, upi_ref
        ))
        bill_id = cur.lastrowid

        # 2. Insert bill items and decrement stock
        for it in verified_items:
            cur.execute("""
                INSERT INTO bill_items (bill_id, product_id, product_name, quantity, unit_price, discount_pct, total_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (bill_id, it["product_id"], it["product_name"], it["quantity"], it["unit_price"], it["discount_pct"], it["total_price"]))

            # Decrement stock
            cur.execute("UPDATE products SET quantity = quantity - ? WHERE product_id = ?", (it["quantity"], it["product_id"]))

            # Feed sales_history for ML model
            existing_sale = cur.execute(
                "SELECT sale_id FROM sales_history WHERE product_id = ? AND sale_date = ?",
                (it["product_id"], today_str)
            ).fetchone()

            if existing_sale:
                cur.execute("UPDATE sales_history SET qty_sold = qty_sold + ? WHERE sale_id = ?",
                            (it["quantity"], existing_sale["sale_id"]))
            else:
                cur.execute("INSERT INTO sales_history (product_id, sale_date, qty_sold) VALUES (?, ?, ?)",
                            (it["product_id"], today_str, it["quantity"]))

        # 3. If paid on credit (Khata), update customer ledger
        if payment_mode == "credit" and customer_id:
            cust = cur.execute("SELECT balance, name FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
            if cust:
                new_balance = round(cust["balance"] + grand_total, 2)
                cur.execute("UPDATE customers SET balance = ? WHERE customer_id = ?", (new_balance, customer_id))
                cur.execute("""
                    INSERT INTO customer_transactions (customer_id, bill_id, type, amount, balance_after, notes, created_at)
                    VALUES (?, ?, 'credit_added', ?, ?, ?, ?)
                """, (customer_id, bill_id, grand_total, new_balance, f"POS Bill #{bill_number}", now_str))

        conn.commit()

        return True, {
            "success": True,
            "bill_id": bill_id,
            "bill_number": bill_number,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "subtotal": subtotal,
            "discount_total": discount_total,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "grand_total": grand_total,
            "payment_mode": payment_mode,
            "is_offline": is_offline,
            "sync_status": sync_status,
            "created_at": now_str,
            "items": verified_items,
        }
    except Exception as e:
        conn.rollback()
        return False, f"Transaction error: {str(e)}"
    finally:
        conn.close()


def get_bill_details(bill_id):
    """Retrieve full bill and item details for receipt printing."""
    conn = get_connection()
    bill = conn.execute("SELECT * FROM bills WHERE bill_id = ?", (bill_id,)).fetchone()
    if not bill:
        conn.close()
        return None

    items = conn.execute("SELECT * FROM bill_items WHERE bill_id = ?", (bill_id,)).fetchall()
    conn.close()

    import urllib.parse
    upi_id = get_setting("upi_id", "")
    shop_name = get_setting("shop_name", "Smart Kirana & Retail")
    grand_total = float(bill["grand_total"] or 0)
    bill_number = bill["bill_number"]
    encoded_name = urllib.parse.quote(shop_name)
    upi_url = f"upi://pay?pa={upi_id}&pn={encoded_name}&am={grand_total:.2f}&tn=Bill_{bill_number}&cu=INR" if upi_id else ""

    return {
        "bill": dict(bill),
        "items": [dict(i) for i in items],
        "upi_url": upi_url,
        "is_offline": bool(bill["is_offline"]),
        "shop": {
            "name": shop_name,
            "tagline": get_setting("shop_tagline", "Smart Inventory & Billing"),
            "phone": get_setting("shop_phone", ""),
            "address": get_setting("shop_address", ""),
            "currency": get_setting("currency_symbol", "₹"),
            "upi_id": upi_id,
            "footer": get_setting("receipt_footer", "Thank you for shopping with us!"),
        }
    }


def get_recent_bills(limit=30):
    conn = get_connection()
    bills = conn.execute("SELECT * FROM bills ORDER BY bill_id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(b) for b in bills]
