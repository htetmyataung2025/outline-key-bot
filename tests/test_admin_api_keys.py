"""Tests for Admin Key Management endpoints."""

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


def test_list_keys_joins_usage_bytes(client, make_telegram_init_data, monkeypatch):
    """GET /keys must join live per-key usage (bytes_used) from /metrics/transfer
    alongside the key's quota (limit_bytes)."""
    import bot_app.services.outline as ol
    ol._usage_cache.clear()

    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    monkeypatch.setattr(
        "bot_app.services.outline.get_configured_servers",
        lambda: [{"id": 1, "name": "S1", "api_url": "https://dummy.local:9000/secret"}],
    )

    class KeysResp:
        status_code = 200

        def json(self):
            return {
                "accessKeys": [
                    {
                        "id": "5001",
                        "name": "quota_user (999) 05.05.2027",
                        "accessUrl": "ss://live",
                        "dataLimit": {"bytes": 10 * 1000 ** 3},
                    }
                ]
            }

    class MetricsResp:
        status_code = 200

        def json(self):
            return {"bytesTransferredByUserId": {"5001": 4 * 1000 ** 3}}

    def fake_get(url, *a, **k):
        return MetricsResp() if "metrics/transfer" in url else KeysResp()

    monkeypatch.setattr("requests.get", fake_get)

    resp = client.get("/api/admin/keys?sync=force", headers=headers)
    assert resp.status_code == 200
    key = next(k for k in resp.json["items"] if k["key_id"] == "5001")
    assert key["limit_bytes"] == 10 * 1000 ** 3
    assert key["bytes_used"] == 4 * 1000 ** 3


def test_list_keys_usage_none_when_metrics_unavailable(client, make_telegram_init_data, monkeypatch):
    """An unreachable /metrics/transfer must not break the list: the key is still
    returned with bytes_used = None so the dashboard shows a dash."""
    import bot_app.services.outline as ol
    ol._usage_cache.clear()

    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    monkeypatch.setattr(
        "bot_app.services.outline.get_configured_servers",
        lambda: [{"id": 7, "name": "S7", "api_url": "https://dummy.local:9000/secret"}],
    )

    class KeysResp:
        status_code = 200

        def json(self):
            return {"accessKeys": [{"id": "6002", "name": "nolimit_user 05.05.2027", "accessUrl": "ss://live"}]}

    class MetricsDown:
        status_code = 500

        def json(self):
            return {}

    def fake_get(url, *a, **k):
        return MetricsDown() if "metrics/transfer" in url else KeysResp()

    monkeypatch.setattr("requests.get", fake_get)

    resp = client.get("/api/admin/keys?sync=force", headers=headers)
    assert resp.status_code == 200
    key = next(k for k in resp.json["items"] if k["key_id"] == "6002")
    assert key["bytes_used"] is None


def test_list_keys_skips_usage_when_sync_disabled(client, make_telegram_init_data, monkeypatch):
    """sync=0 keeps the read hermetic: no server probe for usage, bytes_used=None."""
    import bot_app.services.outline as ol
    ol._usage_cache.clear()

    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    def boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("usage must not be fetched when sync=0")

    monkeypatch.setattr("bot_app.services.outline.get_usage_by_server", boom)

    save_persistent_key(
        server_num="1",
        key_id="8001",
        name="hermetic_user 20.10.2026",
        access_url="ss://conf",
    )

    resp = client.get("/api/admin/keys?sync=0", headers=headers)
    assert resp.status_code == 200
    key = next(k for k in resp.json["items"] if k["key_id"] == "8001")
    assert key["bytes_used"] is None


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


def test_keys_live_sync_throttled_and_force_bypasses(client, make_telegram_init_data, monkeypatch):
    """Page visits within 30s must reuse the cached registry; ?sync=force
    always re-syncs (the probe costs 1-2s per visit otherwise)."""
    import bot_app.routes_admin as ra

    calls = {"n": 0}

    def fake_refresh():
        calls["n"] += 1

    monkeypatch.setattr("bot_app.services.outline.refresh_registry_from_servers", fake_refresh)
    # Usage join also probes servers; stub it so this test stays network-free
    # and only asserts the live-sync throttle behaviour.
    monkeypatch.setattr("bot_app.services.outline.get_usage_by_server", lambda *a, **k: {})
    monkeypatch.setattr(ra, "_last_live_sync", 0.0)

    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}

    assert client.get("/api/admin/keys", headers=headers).status_code == 200
    assert client.get("/api/admin/keys", headers=headers).status_code == 200
    assert calls["n"] == 1

    assert client.get("/api/admin/keys?sync=force", headers=headers).status_code == 200
    assert calls["n"] == 2

    assert client.get("/api/admin/keys?sync=0", headers=headers).status_code == 200
    assert calls["n"] == 2
