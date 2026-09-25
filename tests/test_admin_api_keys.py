"""Tests for Admin Key Management endpoints."""

import pytest
from bot_app.services.registry import load_persistent_keys, save_persistent_key

ADMIN_ID = 111000111


def test_list_and_filter_keys(client, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(
        server_num="1",
        key_id="1",
        name="vip_user_alice 20.10.2026",
        access_url="ss://conf1",
        chat_id="12345",
    )
    save_persistent_key(
        server_num="2",
        key_id="2",
        name="basic_user_bob 25.10.2026",
        access_url="ss://conf2",
        chat_id="67890",
    )

    # List all
    resp = client.get("/api/admin/keys", headers=headers)
    assert resp.status_code == 200
    assert resp.json["total"] >= 2

    # Filter by server
    resp_srv1 = client.get("/api/admin/keys?server_id=1", headers=headers)
    assert resp_srv1.status_code == 200
    assert all(k["server"] == "1" for k in resp_srv1.json["items"])

    # Search by username
    resp_search = client.get("/api/admin/keys?search=alice", headers=headers)
    assert resp_search.status_code == 200
    assert len(resp_search.json["items"]) == 1
    assert "alice" in resp_search.json["items"][0]["name"]


def test_extend_key_expiry(client, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(
        server_num="1",
        key_id="99",
        name="expiring_user 01.10.2026",
        access_url="ss://conf99",
    )

    resp = client.post(
        "/api/admin/keys/99/extend",
        json={"add_days": 30},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert data["new_expire_date"] == "31/10/2026"

    # Verify persisted in storage
    registry = load_persistent_keys()
    assert registry["1_99"]["expire_date"] == "31/10/2026"
