"""
khata.py
--------
Smart Khata (Customer Store Credit & Udhaar Ledger) for offline shops.
Provides digital ledger tracking, credit limits, transaction histories,
and 1-click WhatsApp payment reminder generation.
"""

import urllib.parse
from datetime import datetime
from database import get_connection, get_setting


def get_all_customers():
    conn = get_connection()
    customers = conn.execute("""
        SELECT c.*, 
               (SELECT MAX(created_at) FROM customer_transactions ct WHERE ct.customer_id = c.customer_id) as last_tx_date
        FROM customers c
        ORDER BY c.balance DESC, c.name ASC
    """).fetchall()
    conn.close()
    return [dict(c) for c in customers]


def get_customer_by_id(customer_id):
    conn = get_connection()
    cust = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    if not cust:
        conn.close()
        return None

    transactions = conn.execute("""
        SELECT * FROM customer_transactions 
        WHERE customer_id = ? 
        ORDER BY created_at DESC, tx_id DESC
    """, (customer_id,)).fetchall()
    conn.close()

    return {
        "customer": dict(cust),
        "transactions": [dict(t) for t in transactions],
    }


def add_or_update_customer(name, phone, credit_limit=5000.0, notes="", customer_id=None):
    conn = get_connection()
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if customer_id:
        conn.execute("""
            UPDATE customers SET name = ?, phone = ?, credit_limit = ?, notes = ?
            WHERE customer_id = ?
        """, (name.strip(), clean_phone, float(credit_limit), notes.strip(), customer_id))
    else:
        conn.execute("""
            INSERT INTO customers (name, phone, balance, credit_limit, notes, created_at)
            VALUES (?, ?, 0.0, ?, ?, ?)
        """, (name.strip(), clean_phone, float(credit_limit), notes.strip(), now))

    conn.commit()
    conn.close()
    return True


def record_customer_repayment(customer_id, amount, notes="Cash Payment"):
    """Records a repayment made by customer, reducing their credit balance."""
    amount = float(amount)
    if amount <= 0:
        return False, "Amount must be greater than zero."

    conn = get_connection()
    cust = conn.execute("SELECT balance, name FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    if not cust:
        conn.close()
        return False, "Customer not found."

    current_balance = cust["balance"]
    new_balance = round(current_balance - amount, 2)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute("UPDATE customers SET balance = ? WHERE customer_id = ?", (new_balance, customer_id))
    conn.execute("""
        INSERT INTO customer_transactions (customer_id, bill_id, type, amount, balance_after, notes, created_at)
        VALUES (?, NULL, 'payment_received', ?, ?, ?, ?)
    """, (customer_id, amount, new_balance, notes, now))

    conn.commit()
    conn.close()
    return True, f"Payment of ₹{amount} received from {cust['name']}. New balance: ₹{new_balance}."


def generate_whatsapp_reminder_link(customer_id):
    """
    Constructs a polite, personalized payment reminder message and returns a wa.me URL.
    """
    conn = get_connection()
    cust = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    conn.close()

    if not cust or cust["balance"] <= 0:
        return None

    shop_name = get_setting("shop_name", "Smart Kirana & Retail")
    shop_phone = get_setting("shop_phone", "")
    upi_id = get_setting("upi_id", "")
    currency = get_setting("currency_symbol", "₹")

    phone_clean = "".join(filter(str.isdigit, cust["phone"]))
    if len(phone_clean) == 10:
        phone_clean = "91" + phone_clean  # Default to India country code if 10 digits

    message = (
        f"Namaste {cust['name']} ji 🙏,\n\n"
        f"This is a gentle update from *{shop_name}* regarding your store credit (Khata) account.\n\n"
        f"Current Outstanding Due: *{currency}{cust['balance']:,.2f}*\n\n"
        f"You can clear this at our counter or pay directly via UPI to: *{upi_id}*\n\n"
        f"Thank you for your continued trust and patronage!\n"
        f"📞 Contact: {shop_phone}"
    )

    encoded = urllib.parse.quote(message)
    return f"https://wa.me/{phone_clean}?text={encoded}"
