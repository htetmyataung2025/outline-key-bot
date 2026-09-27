"""Tests for Admin Redeem Code Generation + Deletion endpoints."""

from bot_app.services.orders import is_code_expired, load_redeem_codes, save_redeem_codes
from bot_app.services.slips import load_audit_logs

ADMIN_ID = 111000111


def _admin_headers(make_telegram_init_data):
    return {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}


def test_batch_generate_redeem_codes(client, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    resp = client.post(
        "/api/admin/redeems/batch",
        json={"amount_ks": 3000, "mode": "single", "valid_days": 14, "count": 5},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json
    assert data["created_count"] == 5
    assert len(data["codes"]) == 5
    for c in data["codes"]:
        assert c.startswith("RD-")

    # Verify persisted in storage
    stored = load_redeem_codes()
    for c in data["codes"]:
        assert c in stored
        assert stored[c]["amount"] == 3000
        assert stored[c]["mode"] == "single"

    # List redeems
    list_resp = client.get("/api/admin/redeems", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json) >= 5


# --- Regression: dashboard batch codes must match the Telegram redeem schema --

def test_batch_codes_carry_redeem_flow_fields(client, make_telegram_init_data):
    """menu.py reads validity_days/remaining/claimed_users; codes generated
    here used to lack them (shared codes self-deleted, single codes got 1 day)."""
    headers = _admin_headers(make_telegram_init_data)
    resp = client.post(
        "/api/admin/redeems/batch",
        json={"amount_ks": 5000, "mode": "shared", "valid_days": 30, "count": 1},
        headers=headers,
    )
    assert resp.status_code == 201
    code = resp.json["codes"][0]
    rec = load_redeem_codes()[code]
    assert rec["remaining"] == 5000
    assert rec["claimed_users"] == []
    assert rec["validity_days"] == 30
    assert rec["expires_at"]  # dashboard display field kept


# --- DELETE /redeems/<code> ---------------------------------------------------

def test_delete_redeem_code_and_audit_snapshot(client, make_telegram_init_data):
    headers = _admin_headers(make_telegram_init_data)
    resp = client.post(
        "/api/admin/redeems/batch",
        json={"amount_ks": 2000, "mode": "single", "valid_days": 7, "count": 2},
        headers=headers,
    )
    codes = resp.json["codes"]

    del_resp = client.delete(f"/api/admin/redeems/{codes[0]}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json == {"success": True, "deleted": codes[0]}

    stored = load_redeem_codes()
    assert codes[0] not in stored
    assert codes[1] in stored  # only the targeted code was removed

    audit = [e for e in load_audit_logs() if e["action"] == "REDEEM_DELETE"]
    assert len(audit) == 1
    assert audit[0]["target_id"] == codes[0]
    assert audit[0]["details"]["amount"] == 2000
    assert audit[0]["details"]["mode"] == "single"


def test_delete_unknown_redeem_code_404(client, make_telegram_init_data):
    headers = _admin_headers(make_telegram_init_data)
    resp = client.delete("/api/admin/redeems/RD-NOPE123", headers=headers)
    assert resp.status_code == 404


# --- Bulk delete --------------------------------------------------------------

def test_bulk_delete_mixed_found_and_missing(client, make_telegram_init_data):
    headers = _admin_headers(make_telegram_init_data)
    resp = client.post(
        "/api/admin/redeems/batch",
        json={"amount_ks": 1000, "mode": "single", "valid_days": 7, "count": 2},
        headers=headers,
    )
    codes = resp.json["codes"]

    bulk = client.post(
        "/api/admin/redeems/delete",
        json={"codes": codes + ["GONE123456"]},
        headers=headers,
    )
    assert bulk.status_code == 200
    assert bulk.json["deleted"] == 2
    assert bulk.json["not_found"] == ["GONE123456"]
    assert load_redeem_codes() == {}

    # Empty list is rejected
    assert client.post("/api/admin/redeems/delete", json={"codes": []}, headers=headers).status_code == 400


# --- Derived list fields + expiry helper ---------------------------------------

def test_list_redeems_exposes_derived_fields(client, make_telegram_init_data):
    headers = _admin_headers(make_telegram_init_data)
    save_redeem_codes({
        "legacy-shared": {"amount": 10000, "mode": "shared", "remaining": 4000,
                          "validity_days": 3, "claimed_users": ["1", "2", "3"]},
        "legacy-single": {"amount": 1000, "mode": "single", "validity_days": 3},
    })
    items = {i["code"]: i for i in client.get("/api/admin/redeems", headers=headers).json}
    assert items["legacy-shared"]["remaining"] == 4000
    assert items["legacy-shared"]["claimed_count"] == 3
    assert items["legacy-shared"]["expired"] is False
    assert items["legacy-single"]["remaining"] == 1000  # defaults to full amount
    assert items["legacy-single"]["claimed_count"] == 0


def test_is_code_expired_never_past_future():
    assert is_code_expired({}) is False  # no expires_at = Never
    assert is_code_expired({"expires_at": "31/12/2099 11:59 PM"}) is False
    assert is_code_expired({"expires_at": "01/01/2020 12:00 AM"}) is True
    assert is_code_expired({"expires_at": "garbage"}) is False  # unparseable never locks out
