"""Expiry cron route with Outline HTTP + Telegram sends mocked."""

from datetime import datetime, timedelta

import index


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _yesterday_myanmar():
    return (datetime.utcnow() + timedelta(hours=6, minutes=30) - timedelta(days=1))


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

    monkeypatch.setattr(index.requests, "get", fake_get)
    monkeypatch.setattr(index.requests, "delete", fake_delete)
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
    assert len(mock_bot.calls["send_message"]) == 3 * len(index.ADMIN_CHAT_IDS)
