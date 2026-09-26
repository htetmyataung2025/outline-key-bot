"""Tests for live-refresh versioning + authenticated receipt-image proxy."""

from bot_app.services.slips import get_slip_by_id, record_slip
from bot_app.storage.versioning import get_data_version

ADMIN_ID = 111000111
CUSTOMER_ID = 555444333


def _headers(make_telegram_init_data):
    return {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}


# ── /api/admin/version ─────────────────────────────────────────────────────


def test_version_requires_auth(client):
    assert client.get("/api/admin/version").status_code == 401


def test_version_is_numeric(client, make_telegram_init_data):
    resp = client.get("/api/admin/version", headers=_headers(make_telegram_init_data))
    assert resp.status_code == 200
    assert isinstance(resp.json["version"], int)


def test_version_bumps_on_slip_record(client, make_telegram_init_data):
    headers = _headers(make_telegram_init_data)
    v0 = client.get("/api/admin/version", headers=headers).json["version"]
    record_slip(slip_id="VER-1", chat_id=CUSTOMER_ID, amount=1000)
    v1 = client.get("/api/admin/version", headers=headers).json["version"]
    assert v1 > v0


def test_version_bumps_on_dashboard_review(client, make_telegram_init_data, mock_bot):
    headers = _headers(make_telegram_init_data)
    record_slip(slip_id="VER-2", chat_id=CUSTOMER_ID, amount=1000)
    v0 = get_data_version()
    resp = client.post("/api/admin/slips/VER-2/review", json={"action": "APPROVE"}, headers=headers)
    assert resp.status_code == 200
    assert get_data_version() > v0


def test_version_bumps_on_wallet_change(client, make_telegram_init_data):
    from bot_app.services.billing import update_user_balance

    headers = _headers(make_telegram_init_data)
    v0 = client.get("/api/admin/version", headers=headers).json["version"]
    update_user_balance(CUSTOMER_ID, 500)
    v1 = client.get("/api/admin/version", headers=headers).json["version"]
    assert v1 > v0


# ── /api/admin/slips/<id>/image ────────────────────────────────────────────


def test_slip_image_requires_auth(client):
    assert client.get("/api/admin/slips/IMG-1/image").status_code == 401


def test_slip_image_streams_receipt(client, make_telegram_init_data, mock_bot, monkeypatch):
    headers = _headers(make_telegram_init_data)
    record_slip(slip_id="IMG-1", chat_id=CUSTOMER_ID, amount=2000, file_id="TG_FILE_123")

    class FakeResp:
        status_code = 200
        content = b"\xff\xd8fakejpegbytes"

    seen = {}

    def fake_get(url, *args, **kwargs):
        seen["url"] = url
        return FakeResp()

    import bot_app.routes_admin as routes_admin

    monkeypatch.setattr(routes_admin.requests, "get", fake_get)

    resp = client.get("/api/admin/slips/IMG-1/image", headers=headers)
    assert resp.status_code == 200
    assert resp.data == b"\xff\xd8fakejpegbytes"
    assert resp.mimetype == "image/jpeg"
    assert resp.headers["Cache-Control"] == "private, max-age=3600"
    # Resolved the file_id through the Bot API, then downloaded via the file URL.
    assert mock_bot.calls["get_file"] == ["TG_FILE_123"]
    assert seen["url"].startswith("https://api.telegram.org/file/bot")


def test_slip_image_missing_file_id(client, make_telegram_init_data):
    headers = _headers(make_telegram_init_data)
    record_slip(slip_id="IMG-2", chat_id=CUSTOMER_ID, amount=100)
    resp = client.get("/api/admin/slips/IMG-2/image", headers=headers)
    assert resp.status_code == 404


def test_slip_image_unknown_slip(client, make_telegram_init_data):
    resp = client.get("/api/admin/slips/nope/image", headers=_headers(make_telegram_init_data))
    assert resp.status_code == 404


def test_slip_image_telegram_failure_is_502(client, make_telegram_init_data, mock_bot, monkeypatch):
    headers = _headers(make_telegram_init_data)
    record_slip(slip_id="IMG-3", chat_id=CUSTOMER_ID, amount=100, file_id="TG_FILE_BAD")

    class FakeResp:
        status_code = 404
        content = b""

    import bot_app.routes_admin as routes_admin

    monkeypatch.setattr(routes_admin.requests, "get", lambda *a, **k: FakeResp())
    resp = client.get("/api/admin/slips/IMG-3/image", headers=headers)
    assert resp.status_code == 502


# ── extracted tx id persisted ──────────────────────────────────────────────


def test_record_slip_stores_extracted_tx_id(isolated_state):
    record_slip(slip_id="TX-1", chat_id=CUSTOMER_ID, amount=1000, extracted_tx_id="789012")
    assert get_slip_by_id("TX-1")["extracted_tx_id"] == "789012"
