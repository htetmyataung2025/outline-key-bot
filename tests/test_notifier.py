"""Expiry cron route with Outline HTTP + Telegram sends mocked."""

from datetime import timedelta

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.services import notifier


# Servers the cron is expected to scan. Pinned (rather than read from .env,
# which loads prod URLs during test runs) so the count is deterministic.
_TEST_SERVERS = [
    {"id": 1, "name": "Server 1", "api_url": "https://srv1.example.com/api"},
    {"id": 2, "name": "Server 2", "api_url": "https://srv2.example.com/api"},
    {"id": 3, "name": "Server 3", "api_url": "https://srv3.example.com/api"},
]


class FakeSettings:
    """Lightweight stand-in for bot_app.services.settings.get_system_settings."""

    def __call__(self, force_refresh=False):
        return {"servers": _TEST_SERVERS}


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _days_ago_myanmar(n):
    from bot_app.timeutil import myanmar_now
    return myanmar_now() - timedelta(days=n)


def _fake_outline(monkeypatch, keys):
    calls = {"get": [], "delete": []}

    def fake_get(url, **kwargs):
        calls["get"].append(url)
        if url.endswith("/access-keys"):
            return FakeResp({"accessKeys": keys})
        if url.endswith("/metrics/transfer"):
            return FakeResp({"bytesTransferredByUserId": {}})
        return FakeResp({}, status=404)

    def fake_delete(url, **kwargs):
        calls["delete"].append(url)
        return FakeResp({}, status=204)

    monkeypatch.setattr(notifier.requests, "get", fake_get)
    monkeypatch.setattr(notifier.requests, "delete", fake_delete)
    # Pin the server list so the cron scans exactly the 3 mock servers,
    # independent of whatever .env happens to load during the test run.
    from bot_app.services import settings as settings_svc
    monkeypatch.setattr(settings_svc, "get_system_settings", FakeSettings())
    return calls


def test_cron_with_no_keys(client, mock_bot, monkeypatch):
    calls = _fake_outline(monkeypatch, [])
    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})
    assert resp.status_code == 200
    assert resp.get_json() == {
        "status": "cron completed",
        "webhook_guard": {"checked": False, "url": "", "previous": "",
                          "fixed": False, "error": None},
        "notified": 0,
        "deleted": 0,
    }
    assert calls["delete"] == []
    assert mock_bot.calls["send_message"] == []


def test_cron_keeps_key_expiring_today(client, mock_bot, monkeypatch):
    """A key whose expiry is *today* is not deleted yet — the customer still has
    the day; it is only flagged/notified."""
    from bot_app.timeutil import myanmar_now
    day = myanmar_now().strftime("%d.%m.%Y")
    keys = [{"id": "7", "name": f"Aung (555666777) {day}"}]
    calls = _fake_outline(monkeypatch, keys)

    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 0
    assert calls["delete"] == []


def test_cron_deletes_key_expired_yesterday(client, mock_bot, monkeypatch):
    """Default grace is 0: a key is purged on the first run after it lapses
    (the day after expiry) — the original behaviour, restored."""
    day = _days_ago_myanmar(1).strftime("%d.%m.%Y")
    keys = [{"id": "7", "name": f"Aung (555666777) {day}"}]
    calls = _fake_outline(monkeypatch, keys)

    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})
    assert resp.status_code == 200
    body = resp.get_json()
    # 3 Outline servers are scanned; the expired key lives on each mock.
    assert body["deleted"] == 3
    assert len(calls["delete"]) == 3
    assert all(u.endswith("/access-keys/7") for u in calls["delete"])
    # Admins are notified about every deletion.
    assert len(mock_bot.calls["send_message"]) == 3 * len(ADMIN_CHAT_IDS)
    assert bot is not None  # same bot instance used across app

