"""Tests for Admin Slips Verification Queue endpoints."""

from bot_app.services.billing import get_user_balance
from bot_app.services.slips import record_slip

ADMIN_ID = 111000111
CUSTOMER_ID = 555444333


def test_list_and_get_slips(client, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    # Record 2 slips
    record_slip(slip_id="SLIP-TEST-1", chat_id=CUSTOMER_ID, amount=5000, username="buyer1")
    record_slip(slip_id="SLIP-TEST-2", chat_id=CUSTOMER_ID, amount=10000, username="buyer2")

    # List all pending slips
    resp = client.get("/api/admin/slips?status=PENDING", headers=headers)
    assert resp.status_code == 200
    items = resp.json
    assert len(items) == 2
    assert items[0]["id"] in ("SLIP-TEST-1", "SLIP-TEST-2")

    # Get single slip
    resp_single = client.get("/api/admin/slips/SLIP-TEST-1", headers=headers)
    assert resp_single.status_code == 200
    assert resp_single.json["id"] == "SLIP-TEST-1"
    assert resp_single.json["amount"] == 5000


def test_approve_slip_workflow(client, make_telegram_init_data, mock_bot):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    initial_bal = get_user_balance(CUSTOMER_ID)
    assert initial_bal == 0

    record_slip(slip_id="SLIP-APPR-1", chat_id=CUSTOMER_ID, amount=7000, username="good_buyer")

    # Review: Approve
    resp = client.post(
        "/api/admin/slips/SLIP-APPR-1/review",
        json={"action": "APPROVE", "reason": "Valid KBZPay receipt"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert data["action"] == "APPROVED"
    assert data["new_balance"] == 7000

    # User balance increased
    assert get_user_balance(CUSTOMER_ID) == 7000

    # Bot sent confirmation message to customer
    sent_msgs = [m for m in mock_bot.calls["send_message"] if str(m[0]) == str(CUSTOMER_ID)]
    assert len(sent_msgs) >= 1
    assert "ငွေဖြည့်သွင်းမှု အောင်မြင်ပါသည်" in sent_msgs[0][1]


def test_reject_slip_workflow(client, make_telegram_init_data, mock_bot):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    record_slip(slip_id="SLIP-REJ-1", chat_id=CUSTOMER_ID, amount=5000, username="bad_buyer")

    resp = client.post(
        "/api/admin/slips/SLIP-REJ-1/review",
        json={"action": "REJECT", "reason": "TxID already used"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json["action"] == "REJECTED"

    # User balance did not increase
    assert get_user_balance(CUSTOMER_ID) == 0

    # Rejection message was sent
    sent_msgs = [m for m in mock_bot.calls["send_message"] if str(m[0]) == str(CUSTOMER_ID)]
    assert len(sent_msgs) >= 1
    assert "ပယ်ချပါသည်" in sent_msgs[0][1]


def test_slip_review_idempotency(client, make_telegram_init_data, mock_bot):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    record_slip(slip_id="SLIP-DOUBLE-1", chat_id=CUSTOMER_ID, amount=3000)

    # First approve succeeds
    resp1 = client.post(
        "/api/admin/slips/SLIP-DOUBLE-1/review",
        json={"action": "APPROVE"},
        headers=headers,
    )
    assert resp1.status_code == 200

    # Second review attempt fails
    resp2 = client.post(
        "/api/admin/slips/SLIP-DOUBLE-1/review",
        json={"action": "APPROVE"},
        headers=headers,
    )
    assert resp2.status_code == 400
    assert "already APPROVED" in resp2.json["error"]
