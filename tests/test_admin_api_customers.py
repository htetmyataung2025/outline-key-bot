"""Tests for Admin Customers and Wallet Balance adjustment endpoints."""

from bot_app.services.billing import get_user_balance, update_user_balance

ADMIN_ID = 111000111
ADMIN_ID_2 = 222000222
CUST_ID = 777666555


def test_customer_list_and_balance_topup_and_deduct(client, make_telegram_init_data, mock_bot):
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
    assert resp_topup.json["notified"] is True
    assert get_user_balance(CUST_ID) == 7000

    # 3. Deduct customer balance
    resp_deduct = client.post(
        f"/api/admin/customers/{CUST_ID}/balance",
        json={"adjustment_type": "DEDUCT", "amount_ks": 3000, "reason": "Adjustment"},
        headers=headers,
    )
    assert resp_deduct.status_code == 200
    assert resp_deduct.json["new_balance"] == 4000
    assert resp_deduct.json["notified"] is True
    assert get_user_balance(CUST_ID) == 4000


def test_topup_sends_success_notification(client, make_telegram_init_data, mock_bot):
    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}

    resp = client.post(
        f"/api/admin/customers/{CUST_ID}/balance",
        json={"adjustment_type": "TOPUP", "amount_ks": 1000, "reason": "Loyalty reward"},
        headers=headers,
    )
    assert resp.status_code == 200

    sent = mock_bot.calls["send_message"]
    assert len(sent) == 1
    chat_id, text = sent[0]
    assert str(chat_id) == str(CUST_ID)
    assert "ငွေဖြည့်သွင်းမှု အောင်မြင်ပါသည်" in text
    assert "+1,000 MMK" in text
    assert "Loyalty reward" in text  # admin reason is echoed
    assert "Top-Up ID" not in text   # manual admin top-up carries no id


def test_deduct_sends_success_notification(client, make_telegram_init_data, mock_bot):
    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}
    update_user_balance(CUST_ID, 5000)

    resp = client.post(
        f"/api/admin/customers/{CUST_ID}/balance",
        json={"adjustment_type": "DEDUCT", "amount_ks": 2000, "reason": "Refund reversal"},
        headers=headers,
    )
    assert resp.status_code == 200

    sent = mock_bot.calls["send_message"]
    assert len(sent) == 1
    chat_id, text = sent[0]
    assert str(chat_id) == str(CUST_ID)
    assert "ငွေပြန်နုတ်ယူခြင်း အောင်မြင်ပါသည်" in text
    assert "-2,000 MMK" in text
    assert "Refund reversal" in text


def test_deduct_rejects_overdraw(client, make_telegram_init_data, mock_bot):
    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}
    update_user_balance(CUST_ID, 1500)

    resp = client.post(
        f"/api/admin/customers/{CUST_ID}/balance",
        json={"adjustment_type": "DEDUCT", "amount_ks": 5000},
        headers=headers,
    )
    # Overdraw is refused: no partial deduction, no notification.
    assert resp.status_code == 400
    assert "error" in resp.json
    assert get_user_balance(CUST_ID) == 1500
    assert mock_bot.calls["send_message"] == []


def test_adjustment_on_admin_target_skips_notification(client, make_telegram_init_data, mock_bot):
    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}

    resp = client.post(
        f"/api/admin/customers/{ADMIN_ID_2}/balance",
        json={"adjustment_type": "TOPUP", "amount_ks": 1000, "reason": "test"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json["notified"] is False
    assert mock_bot.calls["send_message"] == []
