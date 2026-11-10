"""
app.py
------
Smart Inventory Pro - Real-Life Offline Retail & Inventory Management System.
Features:
- Complete Inventory Management (Products, Batches, Barcodes, Shelves/Racks, Stock In/Out)
- Speed Point of Sale (POS) Billing with Thermal Receipt printing & WhatsApp share
- 4-Tier Expiry Tracker & Intimation Dashboard (FEFO logic)
- AI Zero-Waste Dynamic Markdown Engine (Near-expiry discount optimization)
- Machine Learning Demand Forecasting (Random Forest + Seasonality + Days of Cover)
- AI Ghost Stock & Shrinkage / Pilferage Anomaly Detector
- Smart Khata (Offline Store Credit / Udhaar Ledger & 1-Click WhatsApp Reminders)
- Suppliers & Automated AI Purchase Orders (PO generation & 1-click restock receipt)
- 100% Offline-First Architecture (SQLite, 1-Click Local Backups)
"""

import sys
import os
import json
import sqlite3
from datetime import date, datetime

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask import (Flask, render_template, request, redirect, url_for,
                   jsonify, flash, abort, send_file, session)

from database import (get_connection, init_db, get_setting, set_setting, DB_NAME,
                      get_saved_voice_commands, add_saved_voice_command,
                      delete_saved_voice_command, toggle_saved_voice_command,
                      get_saved_voice_profiles, get_active_voice_profiles,
                      add_saved_voice_profile, delete_saved_voice_profile,
                      toggle_saved_voice_profile)
from voice_biometrics import extract_voice_tone_from_wav_bytes, verify_speaker_voice_tone, compute_voice_tone_match_score
from ml_model import forecast_product_demand
from health_score import health_bp, compute_health_metrics
from expiry import expiry_info, parse_date, EXPIRY_WARNING_DAYS, get_fefo_warehouse_pick_list
from markdown_ai import get_markdown_opportunities, apply_markdown_discount, clear_markdown_discount
from anomaly_ai import detect_inventory_anomalies, record_stock_audit_adjustment
from khata import (get_all_customers, get_customer_by_id, add_or_update_customer,
                   record_customer_repayment, generate_whatsapp_reminder_link)
from pos import create_sale_bill, get_bill_details, get_recent_bills
from purchase import (get_all_suppliers, get_all_purchase_orders, get_po_details,
                      generate_ai_reorder_recommendations, create_purchase_order, receive_purchase_order)
from theft_protection import (get_theft_analytics, log_theft_incident,
                              verify_exit_receipt, update_all_theft_risk_scores)
from voice_inventory import process_voice_inventory_command

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "smart-inventory-pro-offline-secret-key-2026")
app.register_blueprint(health_bp)

# Ensure tables and migrations are ready
init_db(verbose=False)

import socket

def get_local_ip():
    """Find the best local Wi-Fi / LAN IP address for mobile devices to connect to."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@app.context_processor
def inject_mobile_info():
    ip = get_local_ip()
    port = int(os.environ.get("PORT", 5000))
    return {
        "mobile_url": f"http://{ip}:{port}",
        "local_ip": ip,
        "server_port": port
    }

@app.route("/manifest.json")
def pwa_manifest():
    return send_file(os.path.join(app.root_path, "static", "manifest.json"), mimetype="application/manifest+json")

@app.route("/sw.js")
def pwa_service_worker():
    response = send_file(os.path.join(app.root_path, "static", "sw.js"), mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

@app.route("/api/mobile-info")
def api_mobile_info():
    ip = get_local_ip()
    port = int(os.environ.get("PORT", 5000))
    mobile_url = f"http://{ip}:{port}"
    return jsonify({
        "local_ip": ip,
        "port": port,
        "mobile_url": mobile_url,
        "pwa_ready": True
    })



# ---------- helpers ----------

def to_product(row):
    """sqlite Row -> dict with expiry_status / expiry_days / expiry_label / profit_margin added."""
    if not row:
        return None
    p = dict(row)
    p.update(expiry_info(p.get("expiry_date")))
    cost = p.get("cost_price") or 0.0
    price = p.get("price") or 0.0
    margin = round(((price - cost) / price) * 100, 1) if price > 0 else 0.0
    p["margin_pct"] = margin
    return p


def get_all_products():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products ORDER BY name ASC").fetchall()
    conn.close()
    return [to_product(r) for r in rows]


def get_low_stock_products():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM products WHERE quantity <= reorder_level ORDER BY quantity ASC"
    ).fetchall()
    conn.close()
    return [to_product(r) for r in rows]


def get_expiry_alerts():
    """Expired + critical + soon products, most urgent first."""
    alerts = [p for p in get_all_products() if p["expiry_status"] in ("expired", "critical", "soon")]
    alerts.sort(key=lambda p: (p["expiry_days"] if p["expiry_days"] is not None else 999))
    return alerts


def get_product_by_id(product_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
    conn.close()
    return to_product(row) if row else None


# ---------- Global Context Processor for Templates ----------

@app.context_processor
def inject_global_settings():
    return {
        "shop_name": get_setting("shop_name", "Smart Kirana & Retail Pro"),
        "currency_symbol": get_setting("currency_symbol", "₹"),
        "upi_id": get_setting("upi_id", "smartshop@upi"),
        "assistant_name": get_setting("voice_assistant_name", "Gemini"),
        "voice_gender": get_setting("voice_gender", "girl"),
    }


@app.route("/api/health-ping")
def api_health_ping():
    """Heartbeat endpoint for frontend online/offline status detection."""
    return jsonify({
        "status": "online",
        "server_time": datetime.now().isoformat(),
        "database": "connected"
    })


@app.route("/api/sync/offline-bills", methods=["POST"])
def api_sync_offline_bills():
    """Syncs pending offline cash bills when connection is restored."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE bills SET sync_status = 'synced' WHERE sync_status = 'pending_sync'")
    updated_count = cur.rowcount
    conn.commit()
    conn.close()
    return jsonify({"success": True, "synced_count": updated_count, "message": f"Successfully synced {updated_count} offline bills."})


# ---------- Dashboard ----------

@app.route("/")
def dashboard():
    products = get_all_products()
    low_stock = get_low_stock_products()
    expiry_alerts = get_expiry_alerts()
    expired_count = sum(1 for p in expiry_alerts if p["expiry_status"] == "expired")
    expiring_count = len(expiry_alerts) - expired_count
    total_stock_value = sum((p["price"] or 0) * (p["quantity"] or 0) for p in products)

    # Today's POS sales
    today_str = date.today().isoformat()
    conn = get_connection()
    today_sales_row = conn.execute(
        "SELECT COALESCE(SUM(grand_total), 0) as total, COUNT(*) as bills_count FROM bills WHERE created_at LIKE ?",
        (f"{today_str}%",)
    ).fetchone()

    # Total Khata outstanding receivables
    khata_row = conn.execute("SELECT COALESCE(SUM(balance), 0) as total_due FROM customers").fetchone()
    total_khata_due = round(khata_row["total_due"], 2) if khata_row else 0.0

    # Pending Purchase Orders
    po_count = conn.execute("SELECT COUNT(*) FROM purchase_orders WHERE status = 'Ordered'").fetchone()[0]
    conn.close()

    today_sales = round(today_sales_row["total"], 2) if today_sales_row else 0.0
    bills_count = today_sales_row["bills_count"] if today_sales_row else 0

    # Quick health metrics
    health = compute_health_metrics()

    return render_template(
        "dashboard.html",
        products=products,
        low_stock=low_stock,
        expiry_alerts=expiry_alerts,
        expired_count=expired_count,
        expiring_count=expiring_count,
        warning_days=EXPIRY_WARNING_DAYS,
        total_products=len(products),
        total_stock_value=round(total_stock_value, 2),
        today_sales=today_sales,
        today_bills_count=bills_count,
        total_khata_due=total_khata_due,
        pending_pos=po_count,
        health_score=health["overall_score"],
    )


# ---------- Products CRUD ----------

@app.route("/products")
def products_list():
    return render_template("products.html", products=get_all_products())


@app.route("/products/add", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            price = float(request.form.get("price", 0))
            cost_price = float(request.form.get("cost_price", 0) or (price * 0.75))
            quantity = int(request.form.get("quantity", 0))
            reorder_level = int(request.form.get("reorder_level", 10))
            barcode = request.form.get("barcode", "").strip() or None
            expiry_date = request.form.get("expiry_date", "").strip() or None
            rack_location = request.form.get("rack_location", "A1").strip()
            unit = request.form.get("unit", "pcs").strip()

            if not name or not category:
                raise ValueError("Product Name and Category are required.")

            conn = get_connection()
            conn.execute("""
                INSERT INTO products (name, category, price, cost_price, quantity, reorder_level, barcode, expiry_date, rack_location, unit, discount_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0)
            """, (name, category, price, cost_price, quantity, reorder_level, barcode, expiry_date, rack_location, unit))
            conn.commit()
            conn.close()

            flash(f'Product "{name}" added successfully.', "success")
            return redirect(url_for("products_list"))
        except ValueError as e:
            flash(str(e), "error")
        except sqlite3.IntegrityError:
            flash("Another product already uses this barcode.", "error")

    return render_template("add_product.html", editing=False, values={"barcode": request.args.get("barcode", "")})


@app.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    product = get_product_by_id(product_id)
    if not product:
        abort(404)

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            price = float(request.form.get("price", 0))
            cost_price = float(request.form.get("cost_price", 0))
            quantity = int(request.form.get("quantity", 0))
            reorder_level = int(request.form.get("reorder_level", 10))
            barcode = request.form.get("barcode", "").strip() or None
            expiry_date = request.form.get("expiry_date", "").strip() or None
            rack_location = request.form.get("rack_location", "A1").strip()
            unit = request.form.get("unit", "pcs").strip()
            discount_pct = float(request.form.get("discount_pct", 0.0))

            conn = get_connection()
            conn.execute("""
                UPDATE products SET name=?, category=?, price=?, cost_price=?, quantity=?,
                       reorder_level=?, barcode=?, expiry_date=?, rack_location=?, unit=?, discount_pct=?
                WHERE product_id=?
            """, (name, category, price, cost_price, quantity, reorder_level, barcode, expiry_date, rack_location, unit, discount_pct, product_id))
            conn.commit()
            conn.close()

            flash(f'Product "{name}" updated.', "success")
            return redirect(url_for("products_list"))
        except ValueError as e:
            flash(str(e), "error")
        except sqlite3.IntegrityError:
            flash("Another product already uses that barcode.", "error")

    return render_template("add_product.html", editing=True, product_id=product_id, values=product)


@app.route("/products/delete/<int:product_id>", methods=["POST"])
def delete_product(product_id):
    conn = get_connection()
    conn.execute("DELETE FROM sales_history WHERE product_id = ?", (product_id,))
    conn.execute("DELETE FROM suppliers WHERE product_id = ?", (product_id,))
    conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
    conn.commit()
    conn.close()
    flash("Product deleted.", "success")
    return redirect(url_for("products_list"))


# ---------- Point of Sale (POS) & Billing ----------

@app.route("/pos")
def pos_page():
    customers = get_all_customers()
    products = get_all_products()
    tax_rate = float(get_setting("default_tax_rate", "5.0"))
    return render_template("pos.html", customers=customers, products=products, tax_rate=tax_rate)


@app.route("/api/pos/search")
def api_pos_search():
    q = request.args.get("q", "").strip()
    conn = get_connection()
    if q:
        rows = conn.execute("""
            SELECT * FROM products 
            WHERE name LIKE ? OR barcode LIKE ? OR category LIKE ?
            ORDER BY name ASC LIMIT 20
        """, (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = conn.execute("SELECT * FROM products ORDER BY name ASC LIMIT 20").fetchall()
    conn.close()
    return jsonify([to_product(r) for r in rows])


@app.route("/api/pos/checkout", methods=["POST"])
def api_pos_checkout():
    try:
        data = request.get_json(silent=True) or {}
        success, res = create_sale_bill(data)
        if not success:
            return jsonify({"error": res}), 400
        return jsonify(res)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal error processing checkout: {str(e)}"}), 500


@app.route("/api/settings/update-upi", methods=["POST"])
def api_update_upi():
    try:
        data = request.get_json(silent=True) or {}
        new_upi = (data.get("upi_id") or "").strip()
        if not new_upi:
            return jsonify({"error": "UPI ID cannot be blank."}), 400
        set_setting("upi_id", new_upi)
        return jsonify({"success": True, "upi_id": new_upi, "message": f"UPI ID updated successfully to {new_upi}"})
    except Exception as e:
        return jsonify({"error": f"Failed to save UPI ID: {str(e)}"}), 500


@app.route("/pos/bill/<int:bill_id>")
def pos_bill_view(bill_id):
    bill_data = get_bill_details(bill_id)
    if not bill_data:
        abort(404)
    return render_template("bill_receipt.html", **bill_data)


@app.route("/api/pos/bill/<int:bill_id>")
def api_pos_bill(bill_id):
    bill_data = get_bill_details(bill_id)
    if not bill_data:
        return jsonify({"error": "Bill not found"}), 404
    resp = dict(bill_data["bill"])
    resp["items"] = bill_data["items"]
    resp["upi_url"] = bill_data.get("upi_url")
    resp["shop"] = bill_data.get("shop")
    return jsonify(resp)


@app.route("/pos/history")
def pos_history():
    bills = get_recent_bills(50)
    return render_template("pos_history.html", bills=bills)


# ---------- AI Zero-Waste Dynamic Markdown Engine ----------

@app.route("/markdowns")
def markdowns_page():
    opportunities = get_markdown_opportunities()
    return render_template("markdowns.html", opportunities=opportunities)


@app.route("/api/markdown/apply", methods=["POST"])
def api_markdown_apply():
    data = request.get_json(silent=True) or {}
    product_id = int(data.get("product_id"))
    discount_pct = float(data.get("discount_pct", 20.0))
    apply_markdown_discount(product_id, discount_pct)
    return jsonify({"success": True, "message": f"Applied {discount_pct}% markdown discount!"})


@app.route("/api/markdown/clear", methods=["POST"])
def api_markdown_clear():
    data = request.get_json(silent=True) or {}
    product_id = int(data.get("product_id"))
    clear_markdown_discount(product_id)
    return jsonify({"success": True, "message": "Cleared discount. Restored full price."})


# ---------- FEFO Warehouse Picking Assistant ----------

@app.route("/fefo-picking")
def fefo_picking_page():
    rack_filter = request.args.get("rack", "ALL")
    fefo_data = get_fefo_warehouse_pick_list(rack_filter)
    return render_template("fefo_picking.html", **fefo_data, selected_rack=rack_filter)


@app.route("/api/fefo/pick-list")
def api_fefo_pick_list():
    rack_filter = request.args.get("rack", "ALL")
    return jsonify(get_fefo_warehouse_pick_list(rack_filter))


# ---------- Voice Control Inventory Assistant ----------

@app.route("/api/voice/command", methods=["POST"])
def api_voice_command():
    data = request.get_json(silent=True) or {}
    transcript = (data.get("transcript") or "").strip()
    voice_audio = data.get("audio_wav") or data.get("voice_audio")
    voice_features = data.get("voice_features")
    if not transcript:
        return jsonify({"error": "No speech transcript received."}), 400
    res = process_voice_inventory_command(transcript, voice_audio=voice_audio, voice_features=voice_features)
    return jsonify(res)


@app.route("/api/voice/set-gender", methods=["POST"])
@app.route("/api/voice/gender", methods=["GET", "POST"])
def api_voice_gender():
    """Sets or retrieves AI Voice gender persona ('girl' or 'boy')."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        g = (data.get("gender") or "girl").strip().lower()
        gender = "boy" if g in ["boy", "male"] else "girl"
        set_setting("voice_gender", gender)
        return jsonify({"success": True, "gender": gender})
    return jsonify({"success": True, "gender": get_setting("voice_gender", "girl")})


# ---------- AI Ghost Stock & Inventory Anomalies ----------

@app.route("/anomalies")
def anomalies_page():
    report = detect_inventory_anomalies()
    return render_template("anomalies.html", **report)


@app.route("/api/audit/adjust", methods=["POST"])
def api_audit_adjust():
    data = request.get_json(silent=True) or {}
    product_id = int(data.get("product_id"))
    physical_qty = int(data.get("physical_qty"))
    reason = data.get("reason", "Physical Cycle Count Audit")
    success, msg = record_stock_audit_adjustment(product_id, physical_qty, reason)
    if not success:
        return jsonify({"error": msg}), 400
    return jsonify({"success": True, "message": msg})


# ---------- Smart Khata (Customer Credit & WhatsApp) ----------

@app.route("/khata")
def khata_page():
    customers = get_all_customers()
    total_receivable = sum(c["balance"] for c in customers)
    return render_template("khata.html", customers=customers, total_receivable=round(total_receivable, 2))


@app.route("/khata/customer/<int:customer_id>")
def khata_customer_detail(customer_id):
    data = get_customer_by_id(customer_id)
    if not data:
        abort(404)
    wa_link = generate_whatsapp_reminder_link(customer_id)
    return render_template("khata_detail.html", **data, wa_link=wa_link)


@app.route("/khata/add", methods=["POST"])
def khata_add_customer():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    credit_limit = float(request.form.get("credit_limit", 5000.0))
    notes = request.form.get("notes", "").strip()
    if not name or not phone:
        flash("Name and phone number are required.", "error")
        return redirect(url_for("khata_page"))

    try:
        add_or_update_customer(name, phone, credit_limit, notes)
        flash(f'Customer "{name}" added to Khata ledger.', "success")
    except sqlite3.IntegrityError:
        flash("A customer with this phone number already exists.", "error")

    return redirect(url_for("khata_page"))


@app.route("/khata/repay", methods=["POST"])
def khata_repay():
    customer_id = int(request.form.get("customer_id"))
    amount = float(request.form.get("amount", 0))
    notes = request.form.get("notes", "Cash Repayment")
    success, msg = record_customer_repayment(customer_id, amount, notes)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")
    return redirect(url_for("khata_customer_detail", customer_id=customer_id))


@app.route("/api/khata/whatsapp/<int:customer_id>")
def api_khata_whatsapp(customer_id):
    link = generate_whatsapp_reminder_link(customer_id)
    if not link:
        return jsonify({"error": "No outstanding balance or invalid phone."}), 400
    return jsonify({"whatsapp_url": link})


# ---------- Suppliers & Smart Purchase Orders ----------

@app.route("/suppliers")
def suppliers_page():
    suppliers = get_all_suppliers()
    return render_template("suppliers.html", suppliers=suppliers)


@app.route("/purchase-orders")
def purchase_orders_page():
    pos = get_all_purchase_orders()
    ai_reorders = generate_ai_reorder_recommendations()
    suppliers = get_all_suppliers()
    return render_template("purchase_orders.html", pos=pos, ai_reorders=ai_reorders, suppliers=suppliers)


@app.route("/purchase-orders/create-auto", methods=["POST"])
def create_auto_po():
    supplier_id = int(request.form.get("supplier_id"))
    ai_reorders = generate_ai_reorder_recommendations()
    # Filter items for this supplier
    items = []
    for r in ai_reorders:
        if r["supplier_id"] == supplier_id or not items:
            items.append({
                "product_id": r["product_id"],
                "product_name": r["product_name"],
                "quantity": r["recommended_order_qty"],
                "unit_cost": r["cost_per_unit"],
            })

    if not items:
        flash("No restock items found for this supplier.", "warning")
        return redirect(url_for("purchase_orders_page"))

    po_id, po_num = create_purchase_order(supplier_id, items)
    flash(f"Purchase Order {po_num} created successfully!", "success")
    return redirect(url_for("purchase_orders_page"))


@app.route("/purchase-orders/receive/<int:po_id>", methods=["POST"])
def po_receive(po_id):
    success, msg = receive_purchase_order(po_id)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")
    return redirect(url_for("purchase_orders_page"))


# ---------- Barcode Scanning & Physical Labels ----------

@app.route("/scan")
def scan_page():
    return render_template("scan.html")


@app.route("/barcodes")
def barcodes_page():
    return render_template("barcodes.html", products=[p for p in get_all_products() if p.get("barcode")])


@app.route("/api/product/lookup")
def api_lookup():
    code = request.args.get("barcode", "").strip()
    if not code:
        return jsonify({"error": "No barcode given."}), 400
    conn = get_connection()
    row = conn.execute("SELECT * FROM products WHERE barcode = ?", (code,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "No product with this barcode.", "barcode": code}), 404
    return jsonify(to_product(row))


@app.route("/api/stock/adjust", methods=["POST"])
def api_adjust_stock():
    data = request.get_json(silent=True) or {}
    try:
        product_id = int(data.get("product_id"))
        qty = int(data.get("qty", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid product or quantity."}), 400

    action = data.get("action")
    if action not in ("in", "out", "discard") or qty < 1:
        return jsonify({"error": "Invalid action or quantity."}), 400

    conn = get_connection()
    row = conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "Product not found."}), 404

    if action != "in" and qty > row["quantity"]:
        conn.close()
        return jsonify({"error": f"Only {row['quantity']} in stock."}), 400

    new_qty = row["quantity"] + qty if action == "in" else row["quantity"] - qty
    conn.execute("UPDATE products SET quantity = ? WHERE product_id = ?", (new_qty, product_id))

    today = date.today().isoformat()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action == "out":
        existing = conn.execute(
            "SELECT sale_id FROM sales_history WHERE product_id = ? AND sale_date = ?",
            (product_id, today),
        ).fetchone()
        if existing:
            conn.execute("UPDATE sales_history SET qty_sold = qty_sold + ? WHERE sale_id = ?",
                         (qty, existing["sale_id"]))
        else:
            conn.execute("INSERT INTO sales_history (product_id, sale_date, qty_sold) VALUES (?, ?, ?)",
                         (product_id, today, qty))
    elif action == "discard":
        conn.execute("""
            INSERT INTO stock_adjustments (product_id, type, qty_change, old_qty, new_qty, reason, created_at)
            VALUES (?, 'expiry_discard', ?, ?, ?, 'Discarded/Damaged via Scanner', ?)
        """, (product_id, -qty, row["quantity"], new_qty, now_str))

    conn.commit()
    updated = conn.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
    conn.close()

    product = to_product(updated)
    verb = {"in": "received", "out": "sold", "discard": "discarded"}[action]
    return jsonify({"message": f"{qty} x {product['name']} {verb}.", "product": product})


# ---------- Demand Forecasting API & UI ----------

@app.route("/forecast")
def forecast_page():
    return render_template("forecast.html", products=get_all_products())


@app.route("/api/forecast/<int:product_id>")
def api_forecast(product_id):
    horizon = int(request.args.get("horizon", 14))
    result = forecast_product_demand(product_id, horizon_days=horizon)
    if result is None:
        return jsonify({"error": "Product not found."}), 404
    return jsonify(result)


# ---------- Shopkeeper Guide (Problems Faced & Built-in Solutions) ----------

@app.route("/shopkeeper-guide")
def shopkeeper_guide():
    return render_template("shopkeeper_guide.html")


# ---------- Store Theft Protection & Loss Prevention ----------

@app.route("/theft-protection")
def theft_protection_page():
    analytics = get_theft_analytics()
    products = get_all_products()
    return render_template("theft_protection.html", **analytics, products=products)


@app.route("/api/theft/report", methods=["POST"])
def api_theft_report():
    data = request.get_json(silent=True) or {}
    try:
        product_id = int(data.get("product_id"))
        units_stolen = int(data.get("units_stolen", 1))
        theft_type = data.get("theft_type", "customer_shoplifting")
        cctv_timestamp = data.get("cctv_timestamp", "")
        notes = data.get("notes", "")

        success, res = log_theft_incident(product_id, units_stolen, theft_type, cctv_timestamp, notes)
        if not success:
            return jsonify({"error": res}), 400
        return jsonify({"success": True, "data": res, "message": f"Logged theft of {units_stolen}x {res['product_name']}. Loss: ₹{res['estimated_loss']}."})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/theft/verify-receipt")
def api_theft_verify_receipt():
    bill_number = request.args.get("bill_number", "").strip()
    if not bill_number:
        return jsonify({"error": "No bill number provided."}), 400
    res, msg = verify_exit_receipt(bill_number)
    if not res:
        return jsonify({"error": msg}), 404
    return jsonify(res)


# ---------- Privacy Password Protected Settings & Whitelist Management ----------

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    # Privacy Password Gatekeeper
    if not session.get("settings_unlocked"):
        return render_template("settings_unlock.html")

    if request.method == "POST":
        set_setting("shop_name", request.form.get("shop_name", "Smart Retail Pro"))
        set_setting("shop_tagline", request.form.get("shop_tagline", ""))
        set_setting("shop_phone", request.form.get("shop_phone", ""))
        set_setting("shop_address", request.form.get("shop_address", ""))
        set_setting("currency_symbol", request.form.get("currency_symbol", "₹"))
        set_setting("default_tax_rate", request.form.get("default_tax_rate", "5.0"))
        set_setting("upi_id", request.form.get("upi_id", ""))
        set_setting("receipt_footer", request.form.get("receipt_footer", ""))
        set_setting("voice_assistant_name", request.form.get("voice_assistant_name", "Gemini").strip() or "Gemini")
        set_setting("voice_gender", "boy" if request.form.get("voice_gender") in ["boy", "male"] else "girl")
        set_setting("voice_strict_whitelist", "1" if request.form.get("voice_strict_whitelist") else "0")
        set_setting("voice_tone_security_enabled", "1" if request.form.get("voice_tone_security_enabled") else "0")
        set_setting("voice_match_threshold", request.form.get("voice_match_threshold", "68.0"))
        flash("Shop settings, privacy lock, and voice tone biometrics updated successfully.", "success")
        return redirect(url_for("settings_page"))

    settings = {
        "shop_name": get_setting("shop_name"),
        "shop_tagline": get_setting("shop_tagline"),
        "shop_phone": get_setting("shop_phone"),
        "shop_address": get_setting("shop_address"),
        "currency_symbol": get_setting("currency_symbol", "₹"),
        "default_tax_rate": get_setting("default_tax_rate", "5.0"),
        "upi_id": get_setting("upi_id"),
        "receipt_footer": get_setting("receipt_footer"),
        "voice_assistant_name": get_setting("voice_assistant_name", "Gemini"),
        "voice_gender": get_setting("voice_gender", "girl"),
        "voice_strict_whitelist": get_setting("voice_strict_whitelist", "0"),
        "voice_tone_security_enabled": get_setting("voice_tone_security_enabled", "0"),
        "voice_match_threshold": get_setting("voice_match_threshold", "68.0"),
    }
    saved_commands = get_saved_voice_commands()
    saved_profiles = get_saved_voice_profiles()
    return render_template("settings.html", settings=settings, saved_commands=saved_commands, saved_profiles=saved_profiles)


@app.route("/settings/unlock", methods=["POST"])
def settings_unlock():
    entered_pin = request.form.get("pin", "").strip()
    saved_pin = get_setting("settings_pin", "1234").strip()
    if entered_pin == saved_pin:
        session["settings_unlocked"] = True
        flash("Settings unlocked successfully.", "success")
    else:
        flash("Incorrect Privacy Password! Access to settings denied.", "danger")
    return redirect(url_for("settings_page"))


@app.route("/settings/lock", methods=["POST", "GET"])
def settings_lock():
    session.pop("settings_unlocked", None)
    flash("Settings locked securely.", "info")
    return redirect(url_for("settings_page"))


@app.route("/settings/change-password", methods=["POST"])
def settings_change_password():
    if not session.get("settings_unlocked"):
        return redirect(url_for("settings_page"))

    current_pin = request.form.get("current_pin", "").strip()
    new_pin = request.form.get("new_pin", "").strip()
    confirm_pin = request.form.get("confirm_pin", "").strip()
    saved_pin = get_setting("settings_pin", "1234").strip()

    if current_pin != saved_pin:
        flash("Current Privacy Password is incorrect.", "danger")
        return redirect(url_for("settings_page"))

    if not new_pin or len(new_pin) < 4:
        flash("New Privacy Password must be at least 4 characters.", "danger")
        return redirect(url_for("settings_page"))

    if new_pin != confirm_pin:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("settings_page"))

    set_setting("settings_pin", new_pin)
    flash("Privacy Password successfully updated!", "success")
    return redirect(url_for("settings_page"))


@app.route("/api/settings/voice-commands/add", methods=["POST"])
def api_add_voice_command():
    if not session.get("settings_unlocked"):
        if request.is_json:
            return jsonify({"error": "Unauthorized"}), 403
        flash("Settings locked. Please enter your Privacy Password to continue.", "danger")
        return redirect(url_for("settings_page"))

    phrase = request.form.get("trigger_phrase") or (request.json.get("trigger_phrase", "") if request.is_json else "")
    action = request.form.get("action_type") or (request.json.get("action_type", "stock_check") if request.is_json else "stock_check")
    target_url = request.form.get("target_url") or (request.json.get("target_url", "") if request.is_json else "")
    desc = request.form.get("description") or (request.json.get("description", "") if request.is_json else "")

    ok, msg = add_saved_voice_command(phrase, action, target_url, desc)
    if not ok:
        flash(msg, "danger")
    else:
        flash(msg, "success")
    if request.is_json:
        return jsonify({"success": ok, "message": msg})
    return redirect(url_for("settings_page"))


@app.route("/api/settings/voice-commands/<int:cmd_id>/delete", methods=["POST"])
def api_delete_voice_command(cmd_id):
    if not session.get("settings_unlocked"):
        if request.is_json:
            return jsonify({"error": "Unauthorized"}), 403
        flash("Settings locked. Please enter your Privacy Password to continue.", "danger")
        return redirect(url_for("settings_page"))

    delete_saved_voice_command(cmd_id)
    flash("Voice command deleted from authorized whitelist.", "info")
    if request.is_json:
        return jsonify({"success": True})
    return redirect(url_for("settings_page"))


@app.route("/api/settings/voice-commands/<int:cmd_id>/toggle", methods=["POST"])
def api_toggle_voice_command(cmd_id):
    if not session.get("settings_unlocked"):
        return jsonify({"error": "Unauthorized"}), 403

    enabled = request.json.get("enabled", True) if request.is_json else (request.form.get("enabled") == "1")
    toggle_saved_voice_command(cmd_id, enabled)
    return jsonify({"success": True, "command_id": cmd_id, "is_enabled": 1 if enabled else 0})


# ---------- Voice Tone Biometric Enrollment & Speaker Management ----------

@app.route("/api/settings/voice-profiles/enroll", methods=["POST"])
def api_enroll_voice_profile():
    if not session.get("settings_unlocked"):
        return jsonify({"error": "Unauthorized. Please unlock settings first."}), 403

    data = request.get_json(silent=True) or {}
    speaker_name = (data.get("speaker_name") or "Store Owner").strip()
    audio_wav = data.get("audio_wav") or data.get("voice_audio")
    voice_features = data.get("voice_features")
    desc = data.get("description", f"Authorized Voice Profile for {speaker_name}")

    if audio_wav:
        feat = extract_voice_tone_from_wav_bytes(audio_wav)
    elif voice_features:
        feat = voice_features
    else:
        return jsonify({"error": "No voice audio sample or acoustic features received."}), 400

    if not feat:
        return jsonify({"error": "Could not analyze voice tone. Please speak clearly into the microphone."}), 400

    pitch_hz = feat.get("pitch_hz", 125.0)
    centroid = feat.get("spectral_centroid", 1000.0)
    zcr = feat.get("zcr", 0.05)
    tone_label = feat.get("tone_label", "Standard Tone")

    ok, msg, profile_id = add_saved_voice_profile(
        speaker_name=speaker_name,
        f0_pitch_hz=pitch_hz,
        spectral_centroid=centroid,
        zcr=zcr,
        voiceprint_dict=feat,
        tone_label=tone_label,
        description=desc,
        audio_sample=audio_wav if (audio_wav and len(str(audio_wav)) < 60000) else ""
    )

    if not ok:
        return jsonify({"error": msg}), 500

    return jsonify({
        "success": True,
        "message": f"Voice tone profile for '{speaker_name}' successfully enrolled!",
        "profile_id": profile_id,
        "tone_label": tone_label,
        "pitch_hz": pitch_hz
    })


@app.route("/api/settings/voice-profiles/<int:profile_id>/delete", methods=["POST"])
def api_delete_voice_profile(profile_id):
    if not session.get("settings_unlocked"):
        if request.is_json:
            return jsonify({"error": "Unauthorized"}), 403
        flash("Settings locked. Please enter your Privacy Password to continue.", "danger")
        return redirect(url_for("settings_page"))

    delete_saved_voice_profile(profile_id)
    flash("Voice tone profile deleted. System will no longer obey this voice.", "info")
    if request.is_json:
        return jsonify({"success": True})
    return redirect(url_for("settings_page"))


@app.route("/api/settings/voice-profiles/<int:profile_id>/toggle", methods=["POST"])
def api_toggle_voice_profile(profile_id):
    if not session.get("settings_unlocked"):
        return jsonify({"error": "Unauthorized"}), 403

    enabled = request.json.get("enabled", True) if request.is_json else (request.form.get("enabled") == "1")
    toggle_saved_voice_profile(profile_id, enabled)
    return jsonify({"success": True, "profile_id": profile_id, "is_active": 1 if enabled else 0})


@app.route("/api/settings/voice-profiles/test", methods=["POST"])
def api_test_voice_profile():
    data = request.get_json(silent=True) or {}
    audio_wav = data.get("audio_wav") or data.get("voice_audio")
    voice_features = data.get("voice_features")

    audio_or_feat = audio_wav if audio_wav else voice_features
    if not audio_or_feat:
        return jsonify({"error": "No voice audio received for tone test."}), 400

    enrolled = get_active_voice_profiles()
    threshold = float(get_setting("voice_match_threshold", "68.0"))
    result = verify_speaker_voice_tone(audio_or_feat, enrolled, threshold=threshold)
    return jsonify({"success": True, "result": result})


@app.route("/backup/download")
def backup_download():
    """Download the complete SQLite database file for 100% offline security."""
    return send_file(DB_NAME, as_attachment=True, download_name=f"inventory_backup_{date.today().isoformat()}.db")


@app.route("/backup/export-json")
def backup_export_json():
    """Export products and sales history as JSON."""
    conn = get_connection()
    products = [dict(r) for r in conn.execute("SELECT * FROM products").fetchall()]
    customers = [dict(r) for r in conn.execute("SELECT * FROM customers").fetchall()]
    suppliers = [dict(r) for r in conn.execute("SELECT * FROM suppliers").fetchall()]
    conn.close()

    export_data = {
        "backup_date": datetime.now().isoformat(),
        "products": products,
        "customers": customers,
        "suppliers": suppliers,
    }
    json_path = os.path.join(os.path.dirname(DB_NAME), "inventory_export.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2)

    return send_file(json_path, as_attachment=True, download_name=f"inventory_export_{date.today().isoformat()}.json")


if __name__ == "__main__":
    ssl = "adhoc" if os.environ.get("HTTPS") == "1" else None
    print("[SERVER] Smart Inventory Pro running on http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000, ssl_context=ssl)
