"""
Test Script: Verifies UPI QR generation, Online/Offline Payment Gating, and Sync Endpoint
"""
import sys
import os
import json

# Ensure inventory_ai is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import get_connection, init_db

def run_tests():
    print("[TEST] Initializing test suite...")
    init_db()
    client = app.test_client()

    # 1. Test Health Ping API
    print("\n--- Test 1: Health Ping API ---")
    res = client.get('/api/health-ping')
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.get_json()
    assert data.get('status') == 'online', f"Expected online, got {data}"
    print("[PASS] /api/health-ping returned status: online")

    from database import get_setting, set_setting
    if not get_setting("upi_id"):
        set_setting("upi_id", "smartshop@upi")

    # Fetch a valid product ID for cart testing
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT product_id, name, price, quantity FROM products WHERE quantity > 2 LIMIT 1")
    prod = cursor.fetchone()
    if not prod:
        cursor.execute("INSERT INTO products (name, barcode, category, cost_price, price, quantity) VALUES (?, ?, ?, ?, ?, ?)",
                       ("Test Biscuits", "8901234567890", "Snacks", 20.0, 30.0, 50))
        conn.commit()
        prod_id = cursor.lastrowid
        prod_price = 30.0
        prod_name = "Test Biscuits"
    else:
        prod_id = prod['product_id']
        prod_price = prod['price']
        prod_name = prod['name']
    conn.close()

    print(f"[INFO] Using test product: {prod_name} (ID: {prod_id}, Price: Rs. {prod_price})")

    # 2. Test Online Checkout with UPI Payment
    print("\n--- Test 2: Online UPI Checkout ---")
    online_payload = {
        'items': [
            {'product_id': prod_id, 'quantity': 1, 'unit_price': prod_price, 'discount_pct': 0}
        ],
        'customer_name': 'Ramesh Kumar',
        'customer_phone': '9876543210',
        'payment_mode': 'upi',
        'discount_amount': 0.0,
        'tax_rate': 0.0,
        'is_offline': 0
    }
    res = client.post('/api/pos/checkout', json=online_payload)
    assert res.status_code == 200, f"Checkout failed: {res.data}"
    resp_data = res.get_json()
    assert resp_data.get('success') is True, f"Checkout not successful: {resp_data}"
    bill_id = resp_data.get('bill_id')
    assert bill_id is not None
    print(f"[PASS] Online UPI Bill created: ID {bill_id}, Bill No: {resp_data.get('bill_number')}")

    # Verify Bill Details & UPI deep link
    res_bill = client.get(f'/api/pos/bill/{bill_id}')
    assert res_bill.status_code == 200
    bill_info = res_bill.get_json()
    assert bill_info.get('payment_mode') == 'upi'
    assert bill_info.get('is_offline') == 0
    assert 'upi://pay' in bill_info.get('upi_url', '')
    print(f"[PASS] Bill UPI Deep Link generated properly: {bill_info.get('upi_url')}")

    # 3. Test Offline Gating: Attempting non-cash (UPI) when is_offline=1 should FAIL or be rejected
    print("\n--- Test 3: Offline Non-Cash Gating ---")
    offline_upi_payload = {
        'items': [
            {'product_id': prod_id, 'quantity': 1, 'unit_price': prod_price, 'discount_pct': 0}
        ],
        'customer_name': 'Offline Guest',
        'customer_phone': '',
        'payment_mode': 'upi',
        'is_offline': 1
    }
    res_off_fail = client.post('/api/pos/checkout', json=offline_upi_payload)
    off_fail_data = res_off_fail.get_json()
    assert off_fail_data.get('success') is False or res_off_fail.status_code != 200, "Should reject UPI in offline mode"
    print(f"[PASS] Offline non-cash checkout blocked as expected: {off_fail_data.get('error')}")

    # 4. Test Offline Cash Checkout: Should SUCCEED and be flagged pending_sync
    print("\n--- Test 4: Offline Cash Checkout ---")
    offline_cash_payload = {
        'items': [
            {'product_id': prod_id, 'quantity': 1, 'unit_price': prod_price, 'discount_pct': 0}
        ],
        'customer_name': 'Offline Cash Buyer',
        'customer_phone': '9123456780',
        'payment_mode': 'cash',
        'cash_tendered': 100.0,
        'is_offline': 1
    }
    res_off_cash = client.post('/api/pos/checkout', json=offline_cash_payload)
    assert res_off_cash.status_code == 200, f"Offline cash checkout failed: {res_off_cash.data}"
    cash_data = res_off_cash.get_json()
    assert cash_data.get('success') is True
    off_bill_id = cash_data.get('bill_id')
    assert cash_data.get('is_offline') == 1
    assert cash_data.get('sync_status') == 'pending_sync'
    print(f"[PASS] Offline Cash Bill created successfully: ID {off_bill_id}, sync_status: {cash_data.get('sync_status')}")

    # 5. Test Offline Bills Sync Endpoint
    print("\n--- Test 5: Offline Bills Batch Sync API ---")
    sync_payload = {
        'bill_ids': [off_bill_id]
    }
    res_sync = client.post('/api/sync/offline-bills', json=sync_payload)
    assert res_sync.status_code == 200
    sync_res_data = res_sync.get_json()
    assert sync_res_data.get('success') is True
    assert sync_res_data.get('synced_count') == 1
    print(f"[PASS] Offline bill successfully synced to cloud server: {sync_res_data}")

    # Verify in DB that it is now marked 'synced'
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_offline, sync_status FROM bills WHERE bill_id = ?", (off_bill_id,))
    row = cursor.fetchone()
    conn.close()
    assert row['sync_status'] == 'synced', f"Expected synced, got {row['sync_status']}"
    print(f"[PASS] DB Record verified: sync_status is now '{row['sync_status']}'")

    print("\n==========================================")
    print("ALL 5 TESTS PASSED SUCCESSFULLY! (100% OK)")
    print("==========================================")

if __name__ == '__main__':
    run_tests()
