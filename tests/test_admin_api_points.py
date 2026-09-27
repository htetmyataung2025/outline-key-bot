"""Phase 4: admin dashboard points — list column, detail + ledger, manual adjust."""

from bot_app.config import POINTS_BALANCE_CAP
from bot_app.services.points import credit_points, get_points, try_claim

ADMIN_ID = 111000111
CUST_ID = 733222111


def _hdr(make_telegram_init_data):
    return {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}


def test_customer_list_includes_points(client, make_telegram_init_data, mock_bot):
    credit_points(CUST_ID, 1200, "topup")
    resp = client.get("/api/admin/customers", headers=_hdr(make_telegram_init_data))
    assert resp.status_code == 200
    found = [c for c in resp.json["customers"] if str(c["chat_id"]) == str(CUST_ID)]
    assert len(found) == 1 and found[0]["points"] == 1200


def test_customer_detail_includes_points_and_ledger(client, make_telegram_init_data, mock_bot):
    credit_points(CUST_ID, 800, "topup")      # POINTS_TOPUP ledger entry
    try_claim(CUST_ID)                          # POINTS_CLAIM ledger entry

    resp = client.get(f"/api/admin/customers/{CUST_ID}", headers=_hdr(make_telegram_init_data))
    assert resp.status_code == 200
    prof = resp.json["profile"]
    assert prof["points"] == get_points(CUST_ID)["points"]
    assert prof["points_has_topped_up"] is True
    actions = {e["action"] for e in resp.json["points_ledger"]}
    assert "POINTS_TOPUP" in actions and "POINTS_CLAIM" in actions


def test_admin_grant_points(client, make_telegram_init_data, mock_bot):
    resp = client.post(
        f"/api/admin/customers/{CUST_ID}/points",
        json={"adjustment_type": "GRANT", "amount": 500, "reason": "goodwill"},
        headers=_hdr(make_telegram_init_data),
    )
    assert resp.status_code == 200
    assert resp.json["new_balance"] == 500
    assert get_points(CUST_ID)["points"] == 500

    detail = client.get(f"/api/admin/customers/{CUST_ID}", headers=_hdr(make_telegram_init_data))
    ledger = detail.json["points_ledger"]
    assert any(e["action"] == "POINTS_ADMIN_GRANT" for e in ledger)
    # actor is the acting admin, not the customer
    grant = next(e for e in ledger if e["action"] == "POINTS_ADMIN_GRANT")
    assert str(grant["admin_id"]) == str(ADMIN_ID)


def test_admin_deduct_points(client, make_telegram_init_data, mock_bot):
    credit_points(CUST_ID, 1000, "topup")
    resp = client.post(
        f"/api/admin/customers/{CUST_ID}/points",
        json={"adjustment_type": "DEDUCT", "amount": 300},
        headers=_hdr(make_telegram_init_data),
    )
    assert resp.status_code == 200
    assert resp.json["new_balance"] == 700
    assert get_points(CUST_ID)["points"] == 700


def test_admin_deduct_overdraw_refused(client, make_telegram_init_data, mock_bot):
    credit_points(CUST_ID, 200, "topup")
    resp = client.post(
        f"/api/admin/customers/{CUST_ID}/points",
        json={"adjustment_type": "DEDUCT", "amount": 5000},
        headers=_hdr(make_telegram_init_data),
    )
    assert resp.status_code == 400
    assert "error" in resp.json
    assert get_points(CUST_ID)["points"] == 200   # untouched


def test_admin_grant_respects_cap(client, make_telegram_init_data, mock_bot):
    credit_points(CUST_ID, POINTS_BALANCE_CAP - 100, "topup")
    resp = client.post(
        f"/api/admin/customers/{CUST_ID}/points",
        json={"adjustment_type": "GRANT", "amount": 500},
        headers=_hdr(make_telegram_init_data),
    )
    assert resp.status_code == 200
    assert resp.json["new_balance"] == POINTS_BALANCE_CAP
    assert resp.json["discarded"] == 400
