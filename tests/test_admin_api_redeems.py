"""Tests for Admin Redeem Code Generation endpoints."""

from bot_app.services.orders import load_redeem_codes

ADMIN_ID = 111000111


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
