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


# --- Regression: '#' in slip ids must survive URL encoding on Vercel ---------
# Browsers encode '#082412' as '%23082412'; Vercel hands the encoded segment
# to Flask undecoded, so every slip lookup 404'd on production (image, detail,
# review) even though the queue list worked.

def test_hash_prefixed_slip_id_reached_encoded(client, make_telegram_init_data, mock_bot, monkeypatch):
    from bot_app.routes_admin import requests as admin_requests

    class _Resp:
        status_code = 200
        content = b"JPEGBYTES"

    monkeypatch.setattr(admin_requests, "get", lambda url, **kw: _Resp())
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    record_slip(slip_id="#082412", chat_id=CUSTOMER_ID, amount=2000,
                username="@Ko_Nyein_Maung", file_id="AgACTESTFILEID")

    resp = client.get("/api/admin/slips/%23082412", headers=headers)
    assert resp.status_code == 200
    assert resp.json["id"] == "#082412"

    resp_img = client.get("/api/admin/slips/%23082412/image", headers=headers)
    assert resp_img.status_code == 200
    assert resp_img.data == b"JPEGBYTES"

    resp_review = client.post(
        "/api/admin/slips/%23082412/review",
        json={"action": "APPROVE", "reason": "ok"},
        headers=headers,
    )
    assert resp_review.status_code == 200
    assert resp_review.json["action"] == "APPROVED"


def test_vercel_middleware_decodes_encoded_forwarded_path():
    from bot_app.routes import VercelPathFixMiddleware

    captured = {}

    def fake_app(environ, start_response):
        captured["path"] = environ["PATH_INFO"]
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    wsgi = VercelPathFixMiddleware(fake_app)

    # Vercel rewrite destination + raw (still-encoded) forwarded URI
    environ = {"PATH_INFO": "/api/index.py",
               "HTTP_X_MATCHED_PATH": "/api/admin/slips/%23082412/image"}
    wsgi(environ, lambda *a: None)
    assert captured["path"] == "/api/admin/slips/#082412/image"

    # Already-decoded path must pass through untouched (no double decode)
    environ2 = {"PATH_INFO": "/api/index.py",
                "HTTP_X_MATCHED_PATH": "/api/admin/slips/#082412/image"}
    wsgi(environ2, lambda *a: None)
    assert captured["path"] == "/api/admin/slips/#082412/image"

    # Non-rewrite paths are left alone
    environ3 = {"PATH_INFO": "/api/admin/slips/%23082412/image"}
    wsgi(environ3, lambda *a: None)
    assert captured["path"] == "/api/admin/slips/%23082412/image"
