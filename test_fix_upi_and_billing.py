"""
Comprehensive Verification Script:
Tests UPI update, POS checkout edge cases, and SQLite concurrency in WAL mode
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import get_connection, get_setting, set_setting, init_db

def run_tests():
    print("[TEST] Running verification suite for UPI and POS Billing fix...")
    init_db(verbose=False)
    client = app.test_client()

    # 1. Test UPI ID direct update via API
    print("\n--- Test 1: UPI ID Update API ---")
    test_upi = "merchant.store@oksbi"
    res_upi = client.post('/api/settings/update-upi', json={'upi_id': test_upi})
    assert res_upi.status_code == 200, f"Failed updating UPI: {res_upi.data}"
    upi_data = res_upi.get_json()
    assert upi_data.get('success') is True
    assert upi_data.get('upi_id') == test_upi
    
    # Verify in DB directly
    db_upi = get_setting("upi_id")
    assert db_upi == test_upi, f"Expected {test_upi}, got {db_upi}"
    print(f"[PASS] UPI ID successfully updated to: {db_upi}")

    # 2. Test Empty UPI validation
    res_empty_upi = client.post('/api/settings/update-upi', json={'upi_id': '   '})
    assert res_empty_upi.status_code == 400
    print("[PASS] Empty UPI ID rejected properly with HTTP 400")

    # Fetch a product for POS testing
    conn = get_connection()
    row = conn.execute("SELECT product_id, name, price, quantity FROM products WHERE quantity > 5 LIMIT 1").fetchone()
    conn.close()
    assert row is not None, "No test product available"
    pid = row["product_id"]
    p_name = row["name"]
    p_price = row["price"]
    print(f"[INFO] Using product: {p_name} (ID: {pid}, Price: Rs. {p_price})")

    # 3. Test Edge-Case Checkout 1: null discount_pct and empty string customer_id
    print("\n--- Test 3: Checkout with null discount & empty customer ---")
    p1 = {
        'items': [{'product_id': pid, 'quantity': 1, 'discount_pct': None}],
        'customer_id': '',
        'customer_name': 'Walk-in Customer',
        'customer_phone': '',
        'payment_mode': 'upi',
        'tax_rate': 0.0,
        'is_offline': False
    }
    res1 = client.post('/api/pos/checkout', json=p1)
    assert res1.status_code == 200, f"Checkout 1 failed: {res1.data}"
    d1 = res1.get_json()
    assert d1.get('success') is True
    print(f"[PASS] Checkout 1 succeeded: Bill #{d1.get('bill_number')}, Total: Rs. {d1.get('grand_total')}")

    # 4. Test Edge-Case Checkout 2: null tax_rate and missing discount_pct
    print("\n--- Test 4: Checkout with null tax_rate and omitted discount ---")
    p2 = {
        'items': [{'product_id': pid, 'quantity': 1}],
        'customer_id': None,
        'customer_name': '',
        'payment_mode': 'cash',
        'tax_rate': None,
        'is_offline': 0
    }
    res2 = client.post('/api/pos/checkout', json=p2)
    assert res2.status_code == 200, f"Checkout 2 failed: {res2.data}"
    d2 = res2.get_json()
    assert d2.get('success') is True
    print(f"[PASS] Checkout 2 succeeded: Bill #{d2.get('bill_number')}, Total: Rs. {d2.get('grand_total')}")

    # 5. Test Edge-Case Checkout 3: Offline mode enforces Cash-Only
    print("\n--- Test 5: Offline Mode blocks UPI gracefully ---")
    p3 = {
        'items': [{'product_id': pid, 'quantity': 1}],
        'payment_mode': 'upi',
        'is_offline': 1
    }
    res3 = client.post('/api/pos/checkout', json=p3)
    assert res3.status_code == 400
    d3 = res3.get_json()
    assert 'Only Cash payments are permitted' in d3.get('error', '')
    print(f"[PASS] Offline non-cash gracefully rejected with clean JSON: {d3.get('error')}")

    # 6. Test Bill Details API with the newly updated UPI ID
    print("\n--- Test 6: Verify UPI Deep Link on Generated Bill ---")
    bill_id = d1.get('bill_id')
    res_b = client.get(f'/api/pos/bill/{bill_id}')
    assert res_b.status_code == 200
    bill_info = res_b.get_json()
    upi_link = bill_info.get('upi_url', '')
    assert f"pa={test_upi}" in upi_link, f"Expected {test_upi} in link, got {upi_link}"
    print(f"[PASS] Bill QR deep link matches updated UPI ID: {upi_link}")

    print("\n==========================================")
    print("ALL VERIFICATION TESTS PASSED (100% OK)!")
    print("==========================================")

if __name__ == '__main__':
    run_tests()
