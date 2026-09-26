"""Tests for the Admin customer detail endpoint and enriched list."""

from bot_app.services.billing import update_user_balance
from bot_app.services.orders import save_redeem_codes
from bot_app.services.profiles import save_user_profile
from bot_app.services.registry import save_persistent_key
from bot_app.services.slips import record_audit_log, record_slip

ADMIN_ID = 111000111
CUST_ID = 424242424


def _headers(make_telegram_init_data):
    return {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}


def test_customer_list_includes_profile_fields(client, make_telegram_init_data):
    update_user_balance(CUST_ID, 3000)
    save_user_profile(CUST_ID, username="detailuser", first_name="Detail", last_name="User")

    resp = client.get("/api/admin/customers", headers=_headers(make_telegram_init_data))
    assert resp.status_code == 200
    found = [c for c in resp.json["customers"] if str(c["chat_id"]) == str(CUST_ID)]
    assert len(found) == 1
    row = found[0]
    assert row["username"] == "detailuser"
    assert row["full_name"] == "Detail User"
    assert "keys_count" in row and "last_seen" in row


def test_customer_detail_bundle(client, make_telegram_init_data):
    headers = _headers(make_telegram_init_data)

    update_user_balance(CUST_ID, 6000)
    save_user_profile(CUST_ID, username="detailuser", first_name="Detail", last_name="User")
    save_persistent_key("1", "k-900", "Detail User (424242424) 01.01.2027", "ss://url", chat_id=CUST_ID)
    record_slip("SLIP-D1", CUST_ID, 6000, username="Detail User")
    save_redeem_codes({
        "RD-SHARE1": {"amount": 1000, "mode": "shared", "validity_days": 30, "claimed_users": [str(CUST_ID)]},
        "RD-OTHER": {"amount": 500, "mode": "shared", "validity_days": 7, "claimed_users": ["999"]},
    })
    record_audit_log(ADMIN_ID, "BALANCE_TOPUP", "user", str(CUST_ID), {"amount": 6000})

    resp = client.get(f"/api/admin/customers/{CUST_ID}", headers=headers)
    assert resp.status_code == 200
    data = resp.json

    assert data["profile"]["chat_id"] == str(CUST_ID)
    assert data["profile"]["username"] == "detailuser"
    assert data["profile"]["wallet_balance"] == 6000

    assert any(k["key_id"] == "k-900" for k in data["keys"])
    assert any(s["id"] == "SLIP-D1" for s in data["slips"])

    codes = [r["code"] for r in data["redeems"]]
    assert "RD-SHARE1" in codes
    assert "RD-OTHER" not in codes  # claimed by a different user

    assert any(a["action"] == "BALANCE_TOPUP" for a in data["audit"])
