"""Expiry cron route with Outline HTTP + Telegram sends mocked."""

from datetime import timedelta

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.services import notifier


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _yesterday_myanmar():
    from bot_app.timeutil import myanmar_now
    return myanmar_now() - timedelta(days=1)


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
    return calls


def test_cron_with_no_keys(client, mock_bot, monkeypatch):
    calls = _fake_outline(monkeypatch, [])
    resp = client.get("/cron-check")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "cron completed", "notified": 0, "deleted": 0}
    assert calls["delete"] == []
    assert mock_bot.calls["send_message"] == []


def test_cron_deletes_yesterday_expired_key(client, mock_bot, monkeypatch):
    day = _yesterday_myanmar().strftime("%d.%m.%Y")
    keys = [{"id": "7", "name": f"Aung (555666777) {day}"}]
    calls = _fake_outline(monkeypatch, keys)

    resp = client.get("/cron-check")
    assert resp.status_code == 200
    body = resp.get_json()
    # 3 Outline servers are scanned; the expired key lives on each mock.
    assert body["deleted"] == 3
    assert len(calls["delete"]) == 3
    assert all(u.endswith("/access-keys/7") for u in calls["delete"])
    # Admins are notified about every deletion.
    assert len(mock_bot.calls["send_message"]) == 3 * len(ADMIN_CHAT_IDS)
    assert bot is not None  # same bot instance used across app

