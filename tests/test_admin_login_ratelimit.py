"""Login brute-force protection: per-IP fixed-window rate limiting on
POST /api/admin/login.

KV is disabled across the suite, so these tests exercise the in-memory
fallback; conftest wipes the store around every test.
"""

import pytest

from bot_app.helpers.rate_limit import client_ip_from_headers

SECRET = "super-secret-admin-pass-999"
ADMIN_ID = "111000111"
NON_ADMIN_ID = "999888777"


@pytest.fixture(autouse=True)
def small_limit(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", SECRET)
    monkeypatch.setenv("LOGIN_RATE_LIMIT_MAX", "3")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_WINDOW", "600")


def _login(client, ip, password, admin_id=ADMIN_ID):
    return client.post(
        "/api/admin/login",
        json={"admin_id": admin_id, "password": password},
        headers={"X-Forwarded-For": ip},
    )


def test_blocks_after_max_attempts_even_with_correct_password(client):
    for _ in range(3):
        assert _login(client, "10.0.0.1", "wrong").status_code == 401

    resp = _login(client, "10.0.0.1", SECRET)
    assert resp.status_code == 429
    assert "Too many" in resp.json["error"]
    assert resp.headers.get("Retry-After") == "600"


def test_successful_login_resets_the_counter(client):
    assert _login(client, "10.0.0.2", "wrong").status_code == 401
    assert _login(client, "10.0.0.2", SECRET).status_code == 200

    # The consecutive-failure budget starts fresh after a success.
    for _ in range(3):
        assert _login(client, "10.0.0.2", "wrong").status_code == 401
    assert _login(client, "10.0.0.2", SECRET).status_code == 429


def test_client_ips_are_isolated(client):
    for _ in range(3):
        assert _login(client, "10.0.0.3", "wrong").status_code == 401
    assert _login(client, "10.0.0.3", SECRET).status_code == 429
    # A different IP has its own untouched budget.
    assert _login(client, "10.0.0.4", SECRET).status_code == 200


def test_missing_fields_do_not_count_as_attempts(client):
    for _ in range(4):
        resp = client.post(
            "/api/admin/login",
            json={"admin_id": ADMIN_ID},
            headers={"X-Forwarded-For": "10.0.0.5"},
        )
        assert resp.status_code == 400

    for _ in range(3):
        assert _login(client, "10.0.0.5", "wrong").status_code == 401
    assert _login(client, "10.0.0.5", SECRET).status_code == 429


def test_non_admin_id_attempts_count_too(client):
    for _ in range(3):
        assert _login(client, "10.0.0.6", SECRET, admin_id=NON_ADMIN_ID).status_code == 403
    assert _login(client, "10.0.0.6", SECRET).status_code == 429


def test_max_limit_is_env_tunable(client, monkeypatch):
    monkeypatch.setenv("LOGIN_RATE_LIMIT_MAX", "1")
    assert _login(client, "10.0.0.7", "wrong").status_code == 401
    assert _login(client, "10.0.0.7", SECRET).status_code == 429


def test_client_ip_prefers_trusted_sources():
    assert client_ip_from_headers({"X-Vercel-Forwarded-For": "10.0.0.10"}) == "10.0.0.10"
    # Spoofable leftmost XFF values must never be trusted.
    assert client_ip_from_headers({"X-Forwarded-For": "spoofed, 10.0.0.9"}) == "10.0.0.9"
    assert client_ip_from_headers({"X-Real-IP": "10.0.0.8"}) == "10.0.0.8"
    assert client_ip_from_headers({}) == "unknown"
