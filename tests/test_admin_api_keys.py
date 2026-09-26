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

    # List all (sync=0 keeps this hermetic — we only exercise registry filtering here)
    resp = client.get("/api/admin/keys?sync=0", headers=headers)
    assert resp.status_code == 200
    assert resp.json["total"] >= 2

    # Filter by server
    resp_srv1 = client.get("/api/admin/keys?sync=0&server_id=1", headers=headers)
    assert resp_srv1.status_code == 200
    assert all(k["server"] == "1" for k in resp_srv1.json["items"])

    # Search by username
    resp_search = client.get("/api/admin/keys?sync=0&search=alice", headers=headers)
    assert resp_search.status_code == 200
    assert len(resp_search.json["items"]) == 1
    assert "alice" in resp_search.json["items"][0]["name"]


def test_extend_key_expiry(client, make_telegram_init_data, monkeypatch):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    # Keep hermetic: no live server, so extend just updates the local registry.
    monkeypatch.setattr("bot_app.services.outline.get_server_api_url", lambda sid: None)

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


def test_list_keys_syncs_live_server_keys(client, make_telegram_init_data, monkeypatch):
    """GET /keys should pull keys that live on the Outline servers, not only
    registry-created ones."""
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    monkeypatch.setattr(
        "bot_app.services.outline.get_configured_servers",
        lambda: [{"id": 1, "name": "S1", "api_url": "https://dummy.local:9000/secret"}],
    )

    class FakeResp:
        status_code = 200

        def json(self):
            return {"accessKeys": [{"id": "5001", "name": "liveuser (999) 05.05.2027", "accessUrl": "ss://live"}]}

    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResp())

    resp = client.get("/api/admin/keys", headers=headers)
    assert resp.status_code == 200
    names = [k["name"] for k in resp.json["items"]]
    assert any("liveuser" in n for n in names)


def test_delete_key(client, make_telegram_init_data, monkeypatch):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(
        server_num="1",
        key_id="777",
        name="deleteme 01.01.2027",
        access_url="ss://confdel",
    )

    monkeypatch.setattr(
        "bot_app.services.outline.get_server_api_url",
        lambda sid: "https://dummy.local:9000/secret",
    )

    class FakeResp:
        status_code = 204

    monkeypatch.setattr("requests.delete", lambda *a, **k: FakeResp())

    resp = client.delete("/api/admin/keys/1/777", headers=headers)
    assert resp.status_code == 200
    assert resp.json["success"] is True

    registry = load_persistent_keys()
    assert "1_777" not in registry


def test_delete_key_unconfigured_server(client, make_telegram_init_data, monkeypatch):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    monkeypatch.setattr("bot_app.services.outline.get_server_api_url", lambda sid: None)

    resp = client.delete("/api/admin/keys/9/123", headers=headers)
    assert resp.status_code == 400
    assert "error" in resp.json
