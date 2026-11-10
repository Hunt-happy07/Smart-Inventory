"""
database.py
------------
Creates the SQLite database and all tables used by Smart Inventory Pro.
Features automatic migrations to upgrade older databases without losing data.
"""

import os
import sqlite3
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "inventory.db")


def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.row_factory = sqlite3.Row   # lets us access columns by name
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn


def _column_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r["name"] == column for r in cur.fetchall())


def migrate_db(cur):
    """Upgrade database in place without data loss."""
    # Ensure products table columns
    columns_to_add = [
        ("barcode", "TEXT"),
        ("expiry_date", "TEXT"),
        ("cost_price", "REAL DEFAULT 0"),
        ("rack_location", "TEXT DEFAULT 'A1'"),
        ("unit", "TEXT DEFAULT 'pcs'"),
        ("discount_pct", "REAL DEFAULT 0.0"),
        ("theft_risk_level", "TEXT DEFAULT 'Low'"),
        ("security_tag_required", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in columns_to_add:
        if not _column_exists(cur, "products", col_name):
            cur.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}")

    # Barcode unique index
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_barcode "
        "ON products(barcode) WHERE barcode IS NOT NULL"
    )

    # Ensure suppliers table columns
    if not _column_exists(cur, "suppliers", "lead_time_days"):
        cur.execute("ALTER TABLE suppliers ADD COLUMN lead_time_days INTEGER DEFAULT 7")
    if not _column_exists(cur, "suppliers", "reliability_score"):
        cur.execute("ALTER TABLE suppliers ADD COLUMN reliability_score REAL DEFAULT 95.0")
    if not _column_exists(cur, "suppliers", "email"):
        cur.execute("ALTER TABLE suppliers ADD COLUMN email TEXT")

    # Ensure bills table offline/sync & UPI columns
    bill_columns = [
        ("is_offline", "INTEGER DEFAULT 0"),
        ("sync_status", "TEXT DEFAULT 'synced'"),
        ("upi_ref", "TEXT"),
    ]
    for col_name, col_type in bill_columns:
        if not _column_exists(cur, "bills", col_name):
            cur.execute(f"ALTER TABLE bills ADD COLUMN {col_name} {col_type}")


def init_db(verbose=True):
    conn = get_connection()
    cur = conn.cursor()

    # 1. PRODUCTS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            cost_price REAL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 0,
            reorder_level INTEGER NOT NULL DEFAULT 10,
            barcode TEXT,
            expiry_date TEXT,
            rack_location TEXT DEFAULT 'A1',
            unit TEXT DEFAULT 'pcs',
            discount_pct REAL DEFAULT 0.0
        )
    """)

    # 2. SALES HISTORY (Daily aggregation used for Machine Learning forecasting)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_history (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            sale_date TEXT NOT NULL,
            qty_sold INTEGER NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (product_id)
        )
    """)

    # 3. SUPPLIERS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            email TEXT,
            product_id INTEGER,
            lead_time_days INTEGER DEFAULT 7,
            reliability_score REAL DEFAULT 95.0,
            FOREIGN KEY (product_id) REFERENCES products (product_id)
        )
    """)

    # 4. CUSTOMERS & KHATA (Store Credit Ledger for Offline Shops)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            balance REAL NOT NULL DEFAULT 0.0,
            credit_limit REAL NOT NULL DEFAULT 5000.0,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # 5. CUSTOMER KHATA TRANSACTIONS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customer_transactions (
            tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            bill_id INTEGER,
            type TEXT NOT NULL, -- 'credit_added' or 'payment_received'
            amount REAL NOT NULL,
            balance_after REAL NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
        )
    """)

    # 6. BILLS / POS INVOICES
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number TEXT NOT NULL UNIQUE,
            customer_id INTEGER,
            customer_name TEXT DEFAULT 'Walk-in Customer',
            customer_phone TEXT,
            subtotal REAL NOT NULL,
            discount_total REAL NOT NULL DEFAULT 0.0,
            tax_rate REAL NOT NULL DEFAULT 0.0,
            tax_amount REAL NOT NULL DEFAULT 0.0,
            grand_total REAL NOT NULL,
            payment_mode TEXT NOT NULL, -- 'cash', 'upi', 'card', 'credit'
            payment_status TEXT NOT NULL DEFAULT 'Paid',
            created_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
        )
    """)

    # 7. BILL ITEMS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bill_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            discount_pct REAL DEFAULT 0.0,
            total_price REAL NOT NULL,
            FOREIGN KEY (bill_id) REFERENCES bills (bill_id),
            FOREIGN KEY (product_id) REFERENCES products (product_id)
        )
    """)

    # 8. PURCHASE ORDERS (Automated reordering)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT NOT NULL UNIQUE,
            supplier_id INTEGER NOT NULL,
            supplier_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Draft', -- 'Draft', 'Ordered', 'Received', 'Cancelled'
            total_amount REAL NOT NULL DEFAULT 0.0,
            expected_delivery TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id)
        )
    """)

    # 9. PURCHASE ORDER ITEMS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS po_items (
            po_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_cost REAL NOT NULL,
            total_cost REAL NOT NULL,
            FOREIGN KEY (po_id) REFERENCES purchase_orders (po_id),
            FOREIGN KEY (product_id) REFERENCES products (product_id)
        )
    """)

    # 10. STOCK ADJUSTMENTS & SHRINKAGE AUDIT LOGS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_adjustments (
            adj_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            type TEXT NOT NULL, -- 'audit_discrepancy', 'damage_writeoff', 'supplier_in', 'expiry_discard'
            qty_change INTEGER NOT NULL,
            old_qty INTEGER NOT NULL,
            new_qty INTEGER NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (product_id)
        )
    """)

    # 11. SHOP SETTINGS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shop_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # 12. STORE THEFT & PILFERAGE INCIDENT LOG
    cur.execute("""
        CREATE TABLE IF NOT EXISTS theft_incidents (
            incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_date TEXT NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            units_stolen INTEGER NOT NULL,
            estimated_loss REAL NOT NULL,
            rack_location TEXT,
            theft_type TEXT NOT NULL, -- 'customer_shoplifting', 'internal_pilferage', 'under_ringing', 'unaccounted_variance'
            cctv_timestamp TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (product_id)
        )
    """)

    # 13. SAVED VOICE COMMANDS (STRICT WHITELIST ENGINE)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_voice_commands (
            command_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_phrase TEXT NOT NULL UNIQUE,
            action_type TEXT NOT NULL, -- 'stock_check', 'stock_add', 'stock_remove', 'stock_discard', 'navigate', 'identity', 'courtesy'
            target_url TEXT,
            description TEXT,
            is_enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    # 14. SAVED VOICE PROFILES (VOICE TONE & SPEAKER BIOMETRICS)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_voice_profiles (
            profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
            speaker_name TEXT NOT NULL,
            f0_pitch_hz REAL DEFAULT 0.0,
            spectral_centroid REAL DEFAULT 0.0,
            zero_crossing_rate REAL DEFAULT 0.0,
            voiceprint_vector TEXT NOT NULL,
            audio_sample_base64 TEXT,
            tone_label TEXT,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    # Apply in-place migrations
    migrate_db(cur)

    # Insert default shop settings if missing
    default_settings = [
        ("shop_name", "Smart Kirana & Retail Pro"),
        ("shop_tagline", "Smart Inventory & Offline Billing"),
        ("shop_phone", "+91 98765 43210"),
        ("shop_address", "Main Market Road, Near Gandhi Square"),
        ("currency_symbol", "₹"),
        ("default_tax_rate", "5.0"),
        ("upi_id", "smartshop@upi"),
        ("receipt_footer", "Thank you for your visit! Goods once sold can be returned within 2 days with bill."),
        ("voice_assistant_name", "Gemini"),
        ("settings_pin", "1234"),
        ("voice_strict_whitelist", "0"),
        ("voice_tone_security_enabled", "0"),
        ("voice_match_threshold", "60.0"),
    ]
    for key, val in default_settings:
        cur.execute("INSERT OR IGNORE INTO shop_settings (key, value) VALUES (?, ?)", (key, val))

    # Seed default authorized voice commands (English & தமிழ்)
    default_voice_cmds = [
        ("check stock", "stock_check", None, "Check inventory quantity and rack location"),
        ("what is the stock of", "stock_check", None, "Inquire about product inventory"),
        ("add stock", "stock_add", None, "Restock / add received goods"),
        ("remove stock", "stock_remove", None, "Deduct sold counter units"),
        ("discard damaged", "stock_discard", None, "Discard or write-off expired/damaged goods"),
        ("open pos", "navigate", "/pos", "Open Speed POS Billing Counter"),
        ("open billing", "navigate", "/pos", "Open Speed POS Billing Counter"),
        ("open warehouse", "navigate", "/fefo-picking", "Open FEFO Warehouse Picking List"),
        ("open theft guard", "navigate", "/theft-protection", "Open Anti-Theft Exit Gate Scanner"),
        ("open khata", "navigate", "/khata", "Open Customer Credit Ledger"),
        ("open forecast", "navigate", "/forecast", "Open AI Demand Forecasting"),
        ("open markdowns", "navigate", "/markdowns", "Open Dynamic Markdowns Engine"),
        ("open products", "navigate", "/products", "Open Products Catalog"),
        ("who are you", "identity", None, "Assistant identity check"),
        ("thank you", "courtesy", None, "Courtesy acknowledgment"),
        # Application Live Telemetry & Business Reports (வணிக அறிக்கைகள்)
        ("today sales", "sales_summary", None, "Today's POS billing and sales report"),
        ("low stock", "low_stock_report", None, "Low stock & out-of-stock items alert"),
        ("which products are low on stock", "low_stock_report", None, "Low stock & out-of-stock items alert"),
        ("expiry alerts", "expiry_report", None, "Near-expiry and expired products report"),
        ("inventory value", "inventory_valuation", None, "Total catalog inventory valuation"),
        ("khata balance", "khata_summary", None, "Smart Khata outstanding customer credit receivables"),
        ("health score", "health_summary", None, "Store operations & inventory health score"),
        ("theft report", "theft_summary", None, "Loss prevention and theft incidents report"),
        ("top selling", "top_products", None, "Top selling products by sales volume"),
        ("store summary", "store_summary", None, "Comprehensive daily store briefing"),
        # Feature Guides & Knowledge Base (பயன்பாட்டு வழிகாட்டிகள்)
        ("how to bill", "help_pos", None, "POS Billing counter guide and instructions"),
        ("how to create a bill in pos", "help_pos", None, "POS Billing counter guide and instructions"),
        ("what is fefo", "help_fefo", None, "FEFO Warehouse picking guide"),
        ("what is fefo warehouse", "help_fefo", None, "FEFO Warehouse picking guide"),
        ("what is theft protection", "help_theft", None, "Anti-theft exit gate scanner guide"),
        ("how does theft protection work", "help_theft", None, "Anti-theft exit gate scanner guide"),
        ("what is ghost stock", "help_ghost_stock", None, "Ghost stock & anomaly audit guide"),
        ("what is khata", "help_khata", None, "Smart Khata credit ledger guide"),
        ("what is smart khata", "help_khata", None, "Smart Khata credit ledger guide"),
        ("what is forecast", "help_forecast", None, "AI Demand Forecasting guide"),
        ("what is ai forecast", "help_forecast", None, "AI Demand Forecasting guide"),
        ("what are markdowns", "help_markdowns", None, "Dynamic expiry markdowns guide"),
        ("what are dynamic markdowns", "help_markdowns", None, "Dynamic expiry markdowns guide"),
        ("how does upi work", "help_upi", None, "UPI QR payment and offline mode guide"),
        ("how does upi qr work", "help_upi", None, "UPI QR payment and offline mode guide"),
        ("help", "help_assistant", None, "Assistant capabilities and available voice commands"),
        ("what can you do", "help_assistant", None, "Assistant capabilities and available voice commands"),
        ("shop info", "shop_info", None, "Shop name, address, phone and UPI ID"),
        ("what is the shop upi id", "shop_info", None, "Shop UPI ID inquiry"),
        ("total inventory valuation", "inventory_valuation", None, "Total catalog inventory valuation"),
        ("how much customer credit is pending in khata", "khata_summary", None, "Smart Khata customer credit receivables"),
        ("what is our store health score", "health_summary", None, "Store operations & inventory health score"),
        ("what are top selling products", "top_products", None, "Top selling products by sales volume"),
        ("daily store summary", "store_summary", None, "Comprehensive daily store briefing"),
        # Tamil Core Authorized Commands (தமிழ் கட்டளைகள்)
        ("பால் இருப்பு எவ்வளவு", "stock_check", None, "Check inventory in Tamil"),
        ("சரக்கு இருப்பு பார்", "stock_check", None, "Check inventory in Tamil"),
        ("சரக்கு சேர்", "stock_add", None, "Restock inventory in Tamil"),
        ("சரக்கு விற்பனை கழி", "stock_remove", None, "Deduct counter sale in Tamil"),
        ("சேதமடைந்த பொருட்கள் நீக்கு", "stock_discard", None, "Discard damaged goods in Tamil"),
        ("பில்லிங் திற", "navigate", "/pos", "Open Billing Counter in Tamil"),
        ("கிடங்கு திற", "navigate", "/fefo-picking", "Open Warehouse in Tamil"),
        ("திருட்டு பாதுகாப்பு திற", "navigate", "/theft-protection", "Open Theft Guard in Tamil"),
        ("யார் நீ", "identity", None, "Assistant identity check in Tamil"),
        ("நன்றி", "courtesy", None, "Courtesy thanks in Tamil"),
        ("இன்றைய விற்பனை", "sales_summary", None, "Today's sales report in Tamil"),
        ("இன்றைய விற்பனை என்ன", "sales_summary", None, "Today's sales report in Tamil"),
        ("குறைந்த இருப்பு", "low_stock_report", None, "Low stock alert in Tamil"),
        ("குறைந்த இருப்பு பொருட்கள் என்ன", "low_stock_report", None, "Low stock alert in Tamil"),
        ("காலாவதி எச்சரிக்கை", "expiry_report", None, "Expiry alert report in Tamil"),
        ("காலாவதியாகும் பொருட்கள் என்ன", "expiry_report", None, "Expiry alert report in Tamil"),
        ("மொத்த சரக்கு மதிப்பு", "inventory_valuation", None, "Inventory valuation in Tamil"),
        ("மொத்த சரக்கு மதிப்பு என்ன", "inventory_valuation", None, "Inventory valuation in Tamil"),
        ("கடன் பாக்கி", "khata_summary", None, "Khata customer debt report in Tamil"),
        ("கடன் பாக்கி எவ்வளவு", "khata_summary", None, "Khata customer debt report in Tamil"),
        ("கடை ஆரோக்கியம்", "health_summary", None, "Store health score in Tamil"),
        ("கடை ஆரோக்கியம் என்ன", "health_summary", None, "Store health score in Tamil"),
        ("திருட்டு அறிக்கை", "theft_summary", None, "Theft and security report in Tamil"),
        ("அதிகம் விற்கும் பொருட்கள்", "top_products", None, "Top selling products in Tamil"),
        ("அதிகம் விற்கும் பொருட்கள் எவை", "top_products", None, "Top selling products in Tamil"),
        ("கடை சுருக்கம்", "store_summary", None, "Store daily briefing in Tamil"),
        ("கடை சுருக்கம் சொல்", "store_summary", None, "Store daily briefing in Tamil"),
        ("பில்லிங் எப்படி போடுவது", "help_pos", None, "POS billing guide in Tamil"),
        ("FEFO என்றால் என்ன", "help_fefo", None, "FEFO warehouse guide in Tamil"),
        ("திருட்டு பாதுகாப்பு எப்படி", "help_theft", None, "Theft protection guide in Tamil"),
        ("திருட்டு பாதுகாப்பு எப்படி வேலை செய்கிறது", "help_theft", None, "Theft protection guide in Tamil"),
        ("கோஸ்ட் ஸ்டாக் என்றால் என்ன", "help_ghost_stock", None, "Ghost stock guide in Tamil"),
        ("உதவி", "help_assistant", None, "Assistant help and commands in Tamil"),
        ("கடை முகவரி என்ன", "shop_info", None, "Shop address in Tamil"),
    ]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for phrase, act, url, desc in default_voice_cmds:
        cur.execute("""
            INSERT OR IGNORE INTO saved_voice_commands (trigger_phrase, action_type, target_url, description, is_enabled, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (phrase, act, url, desc, now_str))

    # Populate cost_price for existing products if 0
    cur.execute("UPDATE products SET cost_price = ROUND(price * 0.75, 2) WHERE cost_price IS NULL OR cost_price = 0")

    conn.commit()
    conn.close()
    if verbose:
        print("Database ready ->", DB_NAME)


def get_setting(key, default=""):
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM shop_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO shop_settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
    finally:
        conn.close()


def get_saved_voice_commands():
    """Returns all saved voice commands from the whitelist table."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM saved_voice_commands ORDER BY command_id ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_saved_voice_command(trigger_phrase, action_type, target_url="", description=""):
    """Adds a new authorized voice command to the whitelist."""
    phrase_clean = trigger_phrase.strip().lower()
    if not phrase_clean:
        return False, "Command phrase cannot be empty."
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO saved_voice_commands (trigger_phrase, action_type, target_url, description, is_enabled, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (phrase_clean, action_type, target_url or None, description or phrase_clean.title(), now_str))
        conn.commit()
        return True, f"Voice command '{phrase_clean}' successfully saved."
    except sqlite3.IntegrityError:
        return False, f"Command phrase '{phrase_clean}' already exists."
    finally:
        conn.close()


def delete_saved_voice_command(command_id):
    """Deletes an authorized voice command from the whitelist."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM saved_voice_commands WHERE command_id = ?", (command_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def toggle_saved_voice_command(command_id, is_enabled):
    """Toggles active/disabled status for an authorized voice command."""
    conn = get_connection()
    try:
        conn.execute("UPDATE saved_voice_commands SET is_enabled = ? WHERE command_id = ?", (1 if is_enabled else 0, command_id))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- Voice Tone Biometric Profiles (Speaker Verification) ----------

def get_saved_voice_profiles():
    """Returns all saved speaker voice tone profiles with deserialized voiceprints."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM saved_voice_profiles ORDER BY profile_id ASC").fetchall()
        profiles = []
        for r in rows:
            p = dict(r)
            try:
                p["voiceprint_dict"] = json.loads(p.get("voiceprint_vector") or "{}")
            except Exception:
                p["voiceprint_dict"] = {}
            profiles.append(p)
        return profiles
    finally:
        conn.close()


def get_active_voice_profiles():
    """Returns only enabled speaker voice tone profiles."""
    all_profiles = get_saved_voice_profiles()
    return [p for p in all_profiles if p.get("is_active", 1)]


def add_saved_voice_profile(speaker_name, f0_pitch_hz, spectral_centroid, zcr, voiceprint_dict, tone_label="", description="", audio_sample=""):
    """Adds a new enrolled speaker voice tone profile."""
    name_clean = (speaker_name or "Store Owner").strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vector_json = json.dumps(voiceprint_dict) if isinstance(voiceprint_dict, dict) else str(voiceprint_dict)
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO saved_voice_profiles 
            (speaker_name, f0_pitch_hz, spectral_centroid, zero_crossing_rate, voiceprint_vector, audio_sample_base64, tone_label, description, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (name_clean, float(f0_pitch_hz or 0.0), float(spectral_centroid or 0.0), float(zcr or 0.0), vector_json, audio_sample or "", tone_label or "Standard Tone", description or f"Enrolled Voice for {name_clean}", now_str))
        conn.commit()
        return True, f"Voice tone profile for '{name_clean}' enrolled successfully.", cur.lastrowid
    except Exception as e:
        return False, str(e), None
    finally:
        conn.close()


def delete_saved_voice_profile(profile_id):
    """Deletes an enrolled voice tone profile."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM saved_voice_profiles WHERE profile_id = ?", (profile_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def toggle_saved_voice_profile(profile_id, is_active):
    """Toggles active status of an enrolled voice tone profile."""
    conn = get_connection()
    try:
        conn.execute("UPDATE saved_voice_profiles SET is_active = ? WHERE profile_id = ?", (1 if is_active else 0, profile_id))
        conn.commit()
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
