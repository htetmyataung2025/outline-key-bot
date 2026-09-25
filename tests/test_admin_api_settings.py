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
