"""Tests for Admin Customers and Wallet Balance adjustment endpoints."""

import pytest
from bot_app.services.billing import get_user_balance, update_user_balance

ADMIN_ID = 111000111
CUST_ID = 777666555


def test_customer_list_and_balance_topup_and_deduct(client, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    # Initial balance setup
    update_user_balance(CUST_ID, 2000)

    # 1. List customers
    resp = client.get("/api/admin/customers", headers=headers)
    assert resp.status_code == 200
    assert resp.json["total"] >= 1
    found = [c for c in resp.json["customers"] if str(c["chat_id"]) == str(CUST_ID)]
    assert len(found) == 1
    assert found[0]["wallet_balance"] == 2000

    # 2. Top-up customer balance
    resp_topup = client.post(
        f"/api/admin/customers/{CUST_ID}/balance",
        json={"adjustment_type": "TOPUP", "amount_ks": 5000, "reason": "VIP bonus"},
        headers=headers,
    )
    assert resp_topup.status_code == 200
    assert resp_topup.json["new_balance"] == 7000
    assert get_user_balance(CUST_ID) == 7000

    # 3. Deduct customer balance
    resp_deduct = client.post(
        f"/api/admin/customers/{CUST_ID}/balance",
        json={"adjustment_type": "DEDUCT", "amount_ks": 3000, "reason": "Adjustment"},
        headers=headers,
    )
    assert resp_deduct.status_code == 200
    assert resp_deduct.json["new_balance"] == 4000
    assert get_user_balance(CUST_ID) == 4000
