"""Tests for Admin Control Center cryptographic authentication.

Covers:
- Telegram Mini App HMAC-SHA256 signature verification
- Admin vs non-admin authorization enforcement (403 vs 200)
- Tampered or forged initData payload rejection (401)
- Missing authentication rejection (401)
- Desktop fallback Bearer token validation
- Admin ID + password login (POST /api/admin/login) and the
  ``X-Admin-ID`` binding on Bearer-authenticated requests
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

    # The secret alone is no longer enough: the acting admin ID is mandatory
    # so every audited action is attributable to a real admin.
    resp = auth_test_app.get(
        "/api/admin/test",
        headers={"Authorization": "Bearer super-secret-admin-pass-999"},
    )
    assert resp.status_code == 403
    assert "X-Admin-ID" in resp.json["error"]

    # Secret + registered admin ID binds that identity.
    resp_ok = auth_test_app.get(
        "/api/admin/test",
        headers={"Authorization": "Bearer super-secret-admin-pass-999", "X-Admin-ID": str(ADMIN_ID)},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json["success"] is True
    assert resp_ok.json["admin"]["id"] == str(ADMIN_ID)

    # Invalid secret still rejected regardless of the header.
    resp_invalid = auth_test_app.get(
        "/api/admin/test",
        headers={"Authorization": "Bearer wrong-password", "X-Admin-ID": str(ADMIN_ID)},
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


# ── initData auth_date freshness (opt-in via TMA_MAX_AGE_SECONDS) ──────────

def test_stale_init_data_accepted_when_window_disabled(auth_test_app, make_telegram_init_data, monkeypatch):
    """Default (unset/0) keeps long-open Mini App sessions working."""
    import time
    monkeypatch.delenv("TMA_MAX_AGE_SECONDS", raising=False)
    stale = make_telegram_init_data(user_id=ADMIN_ID, auth_date=int(time.time()) - 400 * 86400)
    resp = auth_test_app.get("/api/admin/test", headers={"X-Telegram-Init-Data": stale})
    assert resp.status_code == 200


def test_stale_init_data_rejected_when_window_configured(auth_test_app, make_telegram_init_data, monkeypatch):
    import time
    monkeypatch.setenv("TMA_MAX_AGE_SECONDS", "3600")

    stale = make_telegram_init_data(user_id=ADMIN_ID, auth_date=int(time.time()) - 7200)
    resp = auth_test_app.get("/api/admin/test", headers={"X-Telegram-Init-Data": stale})
    assert resp.status_code == 401

    fresh = make_telegram_init_data(user_id=ADMIN_ID, auth_date=int(time.time()) - 60)
    resp_ok = auth_test_app.get("/api/admin/test", headers={"X-Telegram-Init-Data": fresh})
    assert resp_ok.status_code == 200


# ── Admin ID + password login (dashboard login form, browser AND Mini App) ─

SECRET = "super-secret-admin-pass-999"


def test_admin_credentials_valid(monkeypatch):
    from bot_app.helpers.auth import check_admin_credentials
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    assert check_admin_credentials(str(ADMIN_ID), SECRET) is None


def test_admin_credentials_wrong_password(monkeypatch):
    from bot_app.helpers.auth import check_admin_credentials
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    status, error = check_admin_credentials(str(ADMIN_ID), "wrong-password")
    assert status == 401
    assert "password" in error.lower()


def test_admin_credentials_password_checked_before_id(monkeypatch):
    """A wrong password must not leak which Telegram IDs are admins."""
    from bot_app.helpers.auth import check_admin_credentials
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    status, _error = check_admin_credentials(str(NON_ADMIN_ID), "wrong-password")
    assert status == 401


def test_admin_credentials_reject_non_admin_id(monkeypatch):
    """Correct secret but an ID outside ADMIN_CHAT_IDS is refused."""
    from bot_app.helpers.auth import check_admin_credentials
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    status, error = check_admin_credentials(str(NON_ADMIN_ID), SECRET)
    assert status == 403
    assert "not authorized" in error.lower()


def test_admin_credentials_reject_non_numeric_id(monkeypatch):
    from bot_app.helpers.auth import check_admin_credentials
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    status, _error = check_admin_credentials("not-a-number", SECRET)
    assert status == 403


def test_admin_credentials_disabled_without_secret(monkeypatch):
    from bot_app.helpers.auth import check_admin_credentials
    monkeypatch.delenv("ADMIN_SECRET_KEY", raising=False)
    status, error = check_admin_credentials(str(ADMIN_ID), SECRET)
    assert status == 403
    assert "not enabled" in error.lower()


def test_login_endpoint_success(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    resp = client.post("/api/admin/login", json={"admin_id": str(ADMIN_ID), "password": SECRET})
    assert resp.status_code == 200
    assert resp.json["ok"] is True
    assert resp.json["admin"]["id"] == str(ADMIN_ID)


def test_login_endpoint_requires_both_fields(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    assert client.post("/api/admin/login", json={"admin_id": str(ADMIN_ID)}).status_code == 400
    assert client.post("/api/admin/login", json={"password": SECRET}).status_code == 400
    assert client.post("/api/admin/login", json={}).status_code == 400


def test_login_endpoint_wrong_password(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    resp = client.post("/api/admin/login", json={"admin_id": str(ADMIN_ID), "password": "nope"})
    assert resp.status_code == 401


def test_login_endpoint_non_admin_id(client, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    resp = client.post("/api/admin/login", json={"admin_id": str(NON_ADMIN_ID), "password": SECRET})
    assert resp.status_code == 403
    assert "not authorized" in resp.json["error"].lower()


def test_login_endpoint_disabled_without_secret(client, monkeypatch):
    monkeypatch.delenv("ADMIN_SECRET_KEY", raising=False)
    resp = client.post("/api/admin/login", json={"admin_id": str(ADMIN_ID), "password": SECRET})
    assert resp.status_code == 403
    assert "not enabled" in resp.json["error"].lower()


# ── Bearer + X-Admin-ID binding on protected routes ────────────────────────

def test_bearer_with_admin_id_header_binds_identity(auth_test_app, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    resp = auth_test_app.get(
        "/api/admin/test",
        headers={"Authorization": f"Bearer {SECRET}", "X-Admin-ID": str(ADMIN_ID)},
    )
    assert resp.status_code == 200
    assert resp.json["admin"]["id"] == str(ADMIN_ID)


def test_bearer_with_non_admin_id_header_rejected(auth_test_app, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    resp = auth_test_app.get(
        "/api/admin/test",
        headers={"Authorization": f"Bearer {SECRET}", "X-Admin-ID": str(NON_ADMIN_ID)},
    )
    assert resp.status_code == 403
    assert "not authorized" in resp.json["error"].lower()

