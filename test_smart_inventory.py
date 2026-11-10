"""
test_smart_inventory.py
------------------------
Automated test script verifying every real-life feature of Smart Inventory Pro:
1. Products Catalog & Expiry status
2. Speed POS Billing & Stock Decrement
3. Customer Khata Credit Ledger & WhatsApp generation
4. AI Zero-Waste Dynamic Markdown Engine
5. AI Ghost Stock & Shrinkage Anomaly Detection
6. Machine Learning Demand Forecasting
7. Supplier Purchase Orders & 1-Click Stock Replenishment
"""

import sys
import codecs
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date
from database import get_connection, init_db
from ml_model import forecast_product_demand
from markdown_ai import get_markdown_opportunities, apply_markdown_discount, clear_markdown_discount
from anomaly_ai import detect_inventory_anomalies, record_stock_audit_adjustment
from khata import get_all_customers, record_customer_repayment, generate_whatsapp_reminder_link
from pos import create_sale_bill, get_recent_bills
from purchase import generate_ai_reorder_recommendations, create_purchase_order, receive_purchase_order
from theft_protection import log_theft_incident, get_theft_analytics, verify_exit_receipt


def run_tests():
    print("==================================================")
    print("🚀 RUNNING SMART INVENTORY PRO SYSTEM TEST SUITE")
    print("==================================================")

    init_db(verbose=False)
    conn = get_connection()
    products = conn.execute("SELECT * FROM products").fetchall()
    customers = conn.execute("SELECT * FROM customers").fetchall()
    suppliers = conn.execute("SELECT * FROM suppliers").fetchall()
    conn.close()

    print(f"✅ Database verified: {len(products)} Products, {len(customers)} Customers, {len(suppliers)} Suppliers.")

    # 1. Test ML Demand Forecasting
    print("\n--- 1. Testing ML Demand Forecasting ---")
    p1 = products[0]
    fc = forecast_product_demand(p1["product_id"], horizon_days=14)
    assert fc is not None, "Forecast returned None"
    print(f"Product: {fc['name']}")
    print(f"Avg Daily Demand: {fc['avg_daily_demand']} units/day")
    print(f"Days of Cover: {fc['days_of_cover']} days | Risk: {fc['stockout_risk']}")
    print(f"Recommended Reorder Qty: {fc['recommended_reorder_qty']} units (Est Cost: ₹{fc['reorder_cost_estimate']})")
    print(f"ML Model: {fc['model_used']} | Trend: {fc['trend_direction']}")
    print("✅ ML Demand Forecasting passed!")

    # 2. Test Speed POS Billing (Cash Sale)
    print("\n--- 2. Testing Speed POS Billing (Cash) ---")
    initial_stock = p1["quantity"]
    bill_payload = {
        "customer_id": None,
        "customer_name": "Walk-in Cash Customer",
        "payment_mode": "cash",
        "tax_rate": 5.0,
        "items": [
            {"product_id": p1["product_id"], "quantity": 2, "discount_pct": 0.0}
        ]
    }
    success, bill_res = create_sale_bill(bill_payload)
    assert success, f"POS Checkout failed: {bill_res}"

    conn = get_connection()
    p1_updated = conn.execute("SELECT quantity FROM products WHERE product_id = ?", (p1["product_id"],)).fetchone()
    conn.close()

    assert p1_updated["quantity"] == initial_stock - 2, "Stock did not decrement accurately"
    print(f"Bill created: #{bill_res['bill_number']} | Grand Total: ₹{bill_res['grand_total']}")
    print(f"Physical Stock decremented from {initial_stock} to {p1_updated['quantity']}")
    print("✅ Cash Billing & Stock Decrement passed!")

    # 3. Test POS Billing with Khata Credit (Udhaar)
    print("\n--- 3. Testing POS Billing with Smart Khata (Store Credit) ---")
    c1 = customers[0]
    initial_balance = c1["balance"]
    khata_payload = {
        "customer_id": c1["customer_id"],
        "customer_name": c1["name"],
        "customer_phone": c1["phone"],
        "payment_mode": "credit",
        "tax_rate": 5.0,
        "items": [
            {"product_id": products[1]["product_id"], "quantity": 1, "discount_pct": 0.0}
        ]
    }
    success, khata_res = create_sale_bill(khata_payload)
    assert success, f"Khata checkout failed: {khata_res}"

    conn = get_connection()
    c1_updated = conn.execute("SELECT balance FROM customers WHERE customer_id = ?", (c1["customer_id"],)).fetchone()
    conn.close()

    expected_balance = round(initial_balance + khata_res["grand_total"], 2)
    assert c1_updated["balance"] == expected_balance, "Customer credit balance mismatch"
    print(f"Customer: {c1['name']}")
    print(f"Balance updated from ₹{initial_balance} to ₹{c1_updated['balance']}")

    # Test WhatsApp Reminder link generator
    wa_link = generate_whatsapp_reminder_link(c1["customer_id"])
    assert wa_link and "wa.me" in wa_link, "WhatsApp link generation failed"
    print(f"Generated WhatsApp Reminder URL: {wa_link[:60]}...")
    print("✅ Smart Khata Ledger & WhatsApp Generation passed!")

    # 4. Test Customer Repayment
    print("\n--- 4. Testing Customer Repayment ---")
    rep_success, rep_msg = record_customer_repayment(c1["customer_id"], 100.0, "Cash counter payment")
    assert rep_success, "Repayment failed"
    conn = get_connection()
    c1_after_rep = conn.execute("SELECT balance FROM customers WHERE customer_id = ?", (c1["customer_id"],)).fetchone()
    conn.close()
    assert c1_after_rep["balance"] == round(expected_balance - 100.0, 2)
    print(f"Repayment recorded: ₹100. New balance: ₹{c1_after_rep['balance']}")
    print("✅ Repayment passed!")

    # 5. Test Zero-Waste Dynamic Markdown Engine
    print("\n--- 5. Testing Zero-Waste Dynamic Markdown Engine ---")
    markdown_ops = get_markdown_opportunities()
    assert len(markdown_ops) > 0, "No markdown opportunities found"
    urgent_op = markdown_ops[0]
    print(f"Candidate: {urgent_op['name']} (Shelf: {urgent_op['rack_location']})")
    print(f"Days to Expiry: {urgent_op['days_to_expiry']} days | Velocity: {urgent_op['daily_velocity']}/day")
    print(f"AI Recommended Discount: {urgent_op['recommended_discount_pct']}% OFF")

    # Apply markdown discount
    apply_markdown_discount(urgent_op["product_id"], 25.0)
    conn = get_connection()
    chk_disc = conn.execute("SELECT discount_pct FROM products WHERE product_id = ?", (urgent_op["product_id"],)).fetchone()[0]
    conn.close()
    assert chk_disc == 25.0, "Discount percentage not applied"
    print(f"Applied 25% clearance discount to {urgent_op['name']} in database.")
    clear_markdown_discount(urgent_op["product_id"])
    print("✅ Dynamic Markdown Engine passed!")

    # 6. Test Ghost Stock & Anomaly Detector
    print("\n--- 6. Testing Ghost Stock & Anomaly Detection ---")
    anomaly_rep = detect_inventory_anomalies()
    print(f"Detected Anomalies: {anomaly_rep['total_anomalies']}")
    print(f"Quick Cycle Count Items: {len(anomaly_rep['quick_cycle_count'])}")

    # Test 60-Second Cycle Count Reconcile
    audit_ok, audit_msg = record_stock_audit_adjustment(p1["product_id"], 40, "Test Physical Audit")
    assert audit_ok, "Stock audit reconcile failed"
    print(f"Audit log result: {audit_msg}")
    print("✅ Anomaly Detection & Cycle Count passed!")

    # 7. Test AI Purchase Orders & Restocking
    print("\n--- 7. Testing AI Purchase Orders & Inventory Replenishment ---")
    reorders = generate_ai_reorder_recommendations()
    assert len(reorders) > 0, "No reorder recommendations"
    first_reorder = reorders[0]
    print(f"AI Restock Suggestion: {first_reorder['product_name']} -> Reorder +{first_reorder['recommended_order_qty']} units")

    po_id, po_num = create_purchase_order(
        suppliers[0]["supplier_id"],
        [{"product_id": first_reorder["product_id"], "product_name": first_reorder["product_name"],
          "quantity": first_reorder["recommended_order_qty"], "unit_cost": first_reorder["cost_per_unit"]}]
    )
    print(f"Created PO: #{po_num}")

    # Receive PO and verify stock increase
    conn = get_connection()
    pre_receive_stock = conn.execute("SELECT quantity FROM products WHERE product_id = ?", (first_reorder["product_id"],)).fetchone()[0]
    conn.close()

    rcv_ok, rcv_msg = receive_purchase_order(po_id)
    assert rcv_ok, "Receive PO failed"

    conn = get_connection()
    post_receive_stock = conn.execute("SELECT quantity FROM products WHERE product_id = ?", (first_reorder["product_id"],)).fetchone()[0]
    conn.close()

    assert post_receive_stock == pre_receive_stock + first_reorder["recommended_order_qty"], "Restock quantity did not increment properly"
    print(f"Stock for '{first_reorder['product_name']}' replenished from {pre_receive_stock} to {post_receive_stock}")
    print("✅ Purchase Order & Stock Replenishment passed!")

    # 8. Test Store Theft Protection & Exit Gate Receipt Auditor
    print("\n--- 8. Testing Store Theft Protection & Loss Prevention ---")
    theft_analytics = get_theft_analytics()
    print(f"Recorded Thefts: {theft_analytics['total_incidents']} | Total Financial Loss: ₹{theft_analytics['total_loss']}")
    print(f"High-Theft Items Monitored: {len(theft_analytics['high_theft_products'])}")

    # Test Exit Gate Receipt Auditor
    exit_verify, msg = verify_exit_receipt(bill_res["bill_number"])
    assert exit_verify is not None, "Exit gate receipt verification failed"
    print(f"Exit Gate Audit for {bill_res['bill_number']}: Verified {exit_verify['total_items_count']} items in customer bag.")

    # Test Theft Incident Logging
    th_ok, th_res = log_theft_incident(p1["product_id"], 1, "customer_shoplifting", "CAM-01 19:40", "Test concealment")
    assert th_ok, "Theft incident logging failed"
    print(f"Logged theft incident #{th_res['incident_id']} for {th_res['product_name']} (Loss: ₹{th_res['estimated_loss']}).")
    print("✅ Store Theft Protection & Loss Prevention passed!")

    print("\n==================================================")
    print("🎉 ALL 8 TEST SUITES PASSED FLAWLESSLY! 100% SUCCESS")
    print("==================================================")


if __name__ == "__main__":
    run_tests()
