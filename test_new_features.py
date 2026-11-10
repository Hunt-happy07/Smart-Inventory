"""
Test suite for:
1. Exit Gate Receipt Barcode verification
2. FEFO Warehouse Picking Engine
3. Voice Control Inventory Engine
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import get_connection

def run_tests():
    print("[TEST] Running test suite for Anti-Theft Exit Gate, FEFO Warehouse, and Voice Control...")
    client = app.test_client()

    # 1. Anti-Theft Exit Gate Receipt Verification
    print("\n--- Test 1: Anti-Theft Exit Gate Verification API ---")
    conn = get_connection()
    last_bill = conn.execute("SELECT bill_number FROM bills ORDER BY bill_id DESC LIMIT 1").fetchone()
    conn.close()
    assert last_bill is not None, "No bills in DB"
    bill_no = last_bill["bill_number"]

    res_gate = client.get(f'/api/theft/verify-receipt?bill_number={bill_no}')
    assert res_gate.status_code == 200, f"Gate verify failed: {res_gate.data}"
    gate_data = res_gate.get_json()
    assert gate_data.get('bill', {}).get('bill_number') == bill_no
    assert 'items' in gate_data
    assert 'security_tag_count' in gate_data
    print(f"[PASS] Exit gate verified receipt #{bill_no}: {gate_data['total_items_count']} items, {gate_data['security_tag_count']} security tag(s)")

    # 2. FEFO Warehouse Picking Engine
    print("\n--- Test 2: FEFO Warehouse Picking Engine ---")
    res_fefo = client.get('/api/fefo/pick-list')
    assert res_fefo.status_code == 200, f"FEFO pick-list failed: {res_fefo.data}"
    fefo_data = res_fefo.get_json()
    assert 'pick_list' in fefo_data
    assert 'all_racks' in fefo_data
    assert 'urgent_pick_count' in fefo_data
    print(f"[PASS] FEFO Warehouse returned {len(fefo_data['pick_list'])} perishable lines. Urgent picks: {fefo_data['urgent_pick_count']}.")
    if fefo_data['pick_list']:
        first_item = fefo_data['pick_list'][0]
        print(f"[INFO] Oldest stock to pick first: {first_item['name']} (Rack: {first_item['rack_location']}, Expiry: {first_item['expiry_date']}, Days: {first_item['expiry_days']})")

    # 3. Voice Control: Check Stock
    print("\n--- Test 3: Voice Control - Check Stock ---")
    res_v1 = client.post('/api/voice/command', json={'transcript': 'Check stock of wireless mouse'})
    assert res_v1.status_code == 200
    d_v1 = res_v1.get_json()
    assert d_v1.get('action') == 'stock_check'
    assert 'Wireless Optical Mouse' in d_v1.get('voice_response', '')
    print(f"[PASS] Voice check reply: \"{d_v1.get('voice_response')}\"")

    # 4. Voice Control: Add Stock
    print("\n--- Test 4: Voice Control - Add Stock ---")
    res_v2 = client.post('/api/voice/command', json={'transcript': 'Add 5 units of wireless mouse'})
    assert res_v2.status_code == 200
    d_v2 = res_v2.get_json()
    assert d_v2.get('action') == 'stock_added'
    assert d_v2.get('qty_changed') == 5
    print(f"[PASS] Voice add reply: \"{d_v2.get('voice_response')}\"")

    # 5. Voice Control: Deduct/Sell Stock
    print("\n--- Test 5: Voice Control - Deduct Stock ---")
    res_v3 = client.post('/api/voice/command', json={'transcript': 'Remove 2 wireless mouse'})
    assert res_v3.status_code == 200
    d_v3 = res_v3.get_json()
    assert d_v3.get('action') == 'stock_removed'
    assert d_v3.get('qty_changed') == -2
    print(f"[PASS] Voice deduct reply: \"{d_v3.get('voice_response')}\"")

    # 6. Voice Control: Navigation
    print("\n--- Test 6: Voice Control - Fast Navigation ---")
    res_v4 = client.post('/api/voice/command', json={'transcript': 'Open POS billing'})
    assert res_v4.status_code == 200
    d_v4 = res_v4.get_json()
    assert d_v4.get('action') == 'navigate'
    assert d_v4.get('url') == '/pos'
    print(f"[PASS] Voice navigation reply: \"{d_v4.get('voice_response')}\" -> {d_v4.get('url')}")

    # 7. Hey Jessi: Wake-Word Detection & Persona Greeting
    print("\n--- Test 7: Hey Jessi - Wake Greeting ---")
    res_v5 = client.post('/api/voice/command', json={'transcript': 'Hey Jessi'})
    assert res_v5.status_code == 200
    d_v5 = res_v5.get_json()
    assert d_v5.get('action') == 'wake_greeting'
    assert 'Jessi' in d_v5.get('voice_response', '')
    print(f"[PASS] 'Hey Jessi' greeting reply: \"{d_v5.get('voice_response')}\"")

    # 8. Hey Jessi: Identity Question
    print("\n--- Test 8: Hey Jessi - Assistant Identity ---")
    res_v6 = client.post('/api/voice/command', json={'transcript': 'Hey Jessie, who are you?'})
    assert res_v6.status_code == 200
    d_v6 = res_v6.get_json()
    assert d_v6.get('action') == 'identity'
    assert 'Jessi' in d_v6.get('voice_response', '')
    print(f"[PASS] Identity question reply: \"{d_v6.get('voice_response')}\"")

    # 9. Hey Jessi: Single-Sentence Wake Word + Command Execution
    print("\n--- Test 9: Hey Jessi - Single-Sentence Voice Command ---")
    res_v7 = client.post('/api/voice/command', json={'transcript': 'Hey Jessi, check stock of wireless mouse'})
    assert res_v7.status_code == 200
    d_v7 = res_v7.get_json()
    assert d_v7.get('action') == 'stock_check'
    assert 'Wireless Optical Mouse' in d_v7.get('voice_response', '')
    print(f"[PASS] 'Hey Jessi check stock...' reply: \"{d_v7.get('voice_response')}\"")

    # 10. Hey Jessi: Wake Word + Warehouse Navigation
    print("\n--- Test 10: Hey Jessi - Wake Word Navigation to Warehouse ---")
    res_v8 = client.post('/api/voice/command', json={'transcript': 'Hey Jessi open warehouse'})
    assert res_v8.status_code == 200
    d_v8 = res_v8.get_json()
    assert d_v8.get('action') == 'navigate'
    assert d_v8.get('url') == '/fefo-picking'
    print(f"[PASS] 'Hey Jessi open warehouse' reply: \"{d_v8.get('voice_response')}\" -> {d_v8.get('url')}")

    print("\n=======================================================")
    print("ALL 10 ANTI-THEFT, FEFO, AND 'HEY JESSI' TESTS PASSED (100%)")
    print("=======================================================")

if __name__ == '__main__':
    run_tests()
