"""Tests for Admin Control Center cryptographic authentication.

Covers:
- Telegram Mini App HMAC-SHA256 signature verification
- Admin vs non-admin authorization enforcement (403 vs 200)
- Tampered or forged initData payload rejection (401)
- Missing authentication rejection (401)
- Desktop fallback Bearer token validation
"""

import pytest
from flask import Flask, jsonify

from bot_app.helpers.auth import require_admin_api, verify_telegram_init_data

ADMIN_ID = 111000111        # Defined in conftest ADMIN_CHAT_IDS
NON_ADMIN_ID = 999888777    # Normal user, not in ADMIN_CHAT_IDS


@pytest.fixture
def auth_test_app():
    """Create a minimal Flask app to test the require_admin_api decorator."""
    test_app = Flask("auth_test_app")
    test_app.config["TESTING"] = True

    @test_app.route("/api/admin/test")
    @require_admin_api
    def protected_route():
        from flask import g
        return jsonify({"success": True, "admin": g.admin_user})

    return test_app.test_client()


def test_verify_valid_telegram_init_data(make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID, username="superadmin")
    verified = verify_telegram_init_data(init_data)
    assert verified is not None
    assert verified["user"]["id"] == ADMIN_ID
    assert verified["user"]["username"] == "superadmin"


def test_verify_tampered_telegram_init_data(make_telegram_init_data):
    tampered_data = make_telegram_init_data(user_id=ADMIN_ID, is_tampered=True)
    assert verify_telegram_init_data(tampered_data) is None


def test_verify_empty_or_malformed_init_data():
    assert verify_telegram_init_data("") is None
    assert verify_telegram_init_data("not_a_valid_query_string") is None
    assert verify_telegram_init_data("foo=bar&baz=qux") is None  # no hash


def test_admin_api_access_granted_for_admin_init_data(auth_test_app, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    resp = auth_test_app.get(
        "/api/admin/test",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert resp.status_code == 200
    assert resp.json["success"] is True
    assert resp.json["admin"]["id"] == ADMIN_ID


def test_admin_api_forbidden_for_non_admin_init_data(auth_test_app, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=NON_ADMIN_ID)
    resp = auth_test_app.get(
        "/api/admin/test",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert resp.status_code == 403
    assert "Forbidden" in resp.json["error"]


def test_admin_api_unauthorized_for_tampered_init_data(auth_test_app, make_telegram_init_data):
    tampered = make_telegram_init_data(user_id=ADMIN_ID, is_tampered=True)
    resp = auth_test_app.get(
        "/api/admin/test",
        headers={"X-Telegram-Init-Data": tampered},
    )
    assert resp.status_code == 401
    assert "tampered" in resp.json["error"]


def test_admin_api_unauthorized_when_no_auth_provided(auth_test_app):
    resp = auth_test_app.get("/api/admin/test")
    assert resp.status_code == 401
    assert "Unauthorized" in resp.json["error"]


def test_admin_api_bearer_token_authentication(auth_test_app, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", "super-secret-admin-pass-999")

    # Valid secret
    resp = auth_test_app.get(
        "/api/admin/test",
        headers={"Authorization": "Bearer super-secret-admin-pass-999"},
    )
    assert resp.status_code == 200
    assert resp.json["success"] is True
    assert resp.json["admin"]["id"] == "desktop_admin"

    # Invalid secret
    resp_invalid = auth_test_app.get(
        "/api/admin/test",
        headers={"Authorization": "Bearer wrong-password"},
    )
    assert resp_invalid.status_code == 401


def test_admin_api_bearer_disabled_when_secret_not_set(auth_test_app, monkeypatch):
    monkeypatch.delenv("ADMIN_SECRET_KEY", raising=False)
    resp = auth_test_app.get(
        "/api/admin/test",
        headers={"Authorization": "Bearer any_token_at_all"},
    )
    assert resp.status_code == 403
    assert "not enabled" in resp.json["error"]

