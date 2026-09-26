"""Tests for Dynamic System Settings admin API."""

import pytest
from bot_app.services.settings import invalidate_settings_cache


@pytest.fixture(autouse=True)
def clean_settings():
    invalidate_settings_cache(reset_fallback=True)
    yield
    invalidate_settings_cache(reset_fallback=True)


def test_settings_api_unauthorized_without_token(client):
    resp = client.get("/api/admin/settings")
    assert resp.status_code == 401


def test_settings_api_get_success(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", "test-pin-123")
    resp = client.get(
        "/api/admin/settings",
        headers={"Authorization": "Bearer test-pin-123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "servers" in data
    assert "payment_phones" in data
    assert "required_channel" in data
    assert "plans" in data


def test_settings_api_update_success(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", "test-pin-123")

    update_payload = {
        "required_channel": "@new_vpn_channel",
        "payment_phones": ["09111222333", "09444555666"],
    }

    resp = client.post(
        "/api/admin/settings",
        json=update_payload,
        headers={"Authorization": "Bearer test-pin-123"},
    )
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data.get("success") is True
    assert res_data["settings"]["required_channel"] == "@new_vpn_channel"
    assert "09111222333" in res_data["settings"]["payment_phones"]


def test_settings_api_test_server(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", "test-pin-123")

    # Invalid URL
    resp_invalid = client.post(
        "/api/admin/settings/test-server",
        json={"api_url": "ftp://bad-url"},
        headers={"Authorization": "Bearer test-pin-123"},
    )
    assert resp_invalid.status_code == 200
    assert resp_invalid.get_json()["success"] is False

    # Mocked successful request
    class MockResponse:
        status_code = 200
        def json(self):
            return {"accessKeys": [{"id": "1"}, {"id": "2"}]}

    monkeypatch.setattr("requests.get", lambda url, **kwargs: MockResponse())

    resp_valid = client.post(
        "/api/admin/settings/test-server",
        json={"api_url": "https://sg1.example.com:443/secret"},
        headers={"Authorization": "Bearer test-pin-123"},
    )
    assert resp_valid.status_code == 200
    assert resp_valid.get_json()["success"] is True
    assert resp_valid.get_json()["keys_count"] == 2


# ---------------------------------------------------------------------------
# Server list derives strictly from configured servers (.env / Settings store)
# ---------------------------------------------------------------------------

def test_default_settings_only_include_env_configured_servers(monkeypatch):
    """An unset OUTLINE_API_URL_* must not become a phantom default server."""
    import bot_app.config as config
    from bot_app.services.settings import _get_default_settings

    monkeypatch.setattr(config, "OUTLINE_API_URL_1", "https://sg1.example.com/api")
    monkeypatch.setattr(config, "OUTLINE_API_URL_2", "https://sg2.example.com/api")
    monkeypatch.setattr(config, "OUTLINE_API_URL_3", "")

    servers = _get_default_settings()["servers"]
    assert [s["id"] for s in servers] == [1, 2]
    assert all(s["api_url"] for s in servers)


def test_default_settings_include_server_when_env_configured(monkeypatch):
    import bot_app.config as config
    from bot_app.services.settings import _get_default_settings

    monkeypatch.setattr(config, "OUTLINE_API_URL_1", "https://sg1.example.com/api")
    monkeypatch.setattr(config, "OUTLINE_API_URL_2", "https://sg2.example.com/api")
    monkeypatch.setattr(config, "OUTLINE_API_URL_3", "https://vip.example.com/api")
    servers = _get_default_settings()["servers"]
    assert [s["id"] for s in servers] == [1, 2, 3]


def test_get_configured_servers_filters_rows_without_api_url(monkeypatch):
    """Rows saved without an API URL (mid-edit / legacy) are never usable."""
    from bot_app.services import outline, settings as settings_svc

    monkeypatch.setattr(
        settings_svc,
        "get_system_settings",
        lambda force_refresh=False: {
            "servers": [
                {"id": 1, "name": "Server 1 (SG-1)", "api_url": "https://sg1.example.com/api"},
                {"id": 3, "name": "Server 3 (VIP)", "api_url": ""},
                {"id": 4, "name": "Server 4", "api_url": None},
            ]
        },
    )
    servers = outline.get_configured_servers()
    assert [s["id"] for s in servers] == [1]


def test_servers_endpoint_requires_auth(client):
    resp = client.get("/api/admin/servers")
    assert resp.status_code == 401


def test_servers_endpoint_lists_only_configured_servers(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", "test-pin-123")
    from bot_app.services import settings as settings_svc

    monkeypatch.setattr(
        settings_svc,
        "get_system_settings",
        lambda force_refresh=False: {
            "servers": [
                {"id": 1, "name": "Server 1 (SG-1)", "api_url": "https://sg1.example.com/api"},
                {"id": 2, "name": "Server 2 (SG-2)", "api_url": "https://sg2.example.com/api"},
                {"id": 3, "name": "Server 3 (VIP)", "api_url": ""},
            ]
        },
    )

    resp = client.get("/api/admin/servers", headers={"Authorization": "Bearer test-pin-123"})
    assert resp.status_code == 200
    servers = resp.get_json()["servers"]
    assert [s["id"] for s in servers] == [1, 2]
    assert [s["name"] for s in servers] == ["Server 1 (SG-1)", "Server 2 (SG-2)"]
    # The API URL (a secret) must not be exposed by this endpoint.
    assert all("api_url" not in s for s in servers)


# ---------------------------------------------------------------------------
# KV-only persistence (single-store mode, no Supabase)
# ---------------------------------------------------------------------------

def test_settings_persist_in_kv_without_supabase(monkeypatch):
    """With Supabase unconfigured, settings must save to and load from KV,
    surviving a cache + in-memory-fallback reset (i.e. a fresh process)."""
    from bot_app.services import settings as settings_svc

    store: dict = {}
    monkeypatch.setattr(settings_svc, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(settings_svc, "redis_set", lambda k, v: (store.__setitem__(k, v), True)[1])
    monkeypatch.setattr(settings_svc, "redis_get", lambda k: store.get(k))

    settings_svc.invalidate_settings_cache(reset_fallback=True)
    settings_svc.save_system_settings(
        {"required_channel": "@kv_only_channel", "payment_phones": ["0912345678"]},
        updated_by="Tester",
    )
    assert store.get("system_settings_data")  # written to KV

    # Wipe memory cache + fallback → next read can only come from KV.
    settings_svc.invalidate_settings_cache(reset_fallback=True)
    loaded = settings_svc.get_system_settings(force_refresh=True)
    assert loaded["required_channel"] == "@kv_only_channel"
    assert "0912345678" in loaded["payment_phones"]
