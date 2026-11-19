"""Expiry cron: customer warnings are mirrored into the app inbox.

The Telegram DM behaviour is unchanged; beside it, the same warning is
pushed to the native app's notification inbox via push_app_notification
so app users (who may rarely open Telegram) get it as a phone
notification. Deletions do NOT produce an app-inbox copy.
"""

from bot_app.services import app_notify, notifier


_TEST_SERVERS = [
    {"id": 1, "name": "Server 1", "api_url": "https://srv1.example.com/api"},
    {"id": 2, "name": "Server 2", "api_url": "https://srv2.example.com/api"},
    {"id": 3, "name": "Server 3", "api_url": "https://srv3.example.com/api"},
]


class FakeSettings:
    def __call__(self, force_refresh=False):
        return {"servers": _TEST_SERVERS}


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _fake_outline(monkeypatch, keys, metrics=None):
    def fake_get(url, **kwargs):
        if url.endswith("/access-keys"):
            return FakeResp({"accessKeys": keys})
        if url.endswith("/metrics/transfer"):
            return FakeResp({"bytesTransferredByUserId": metrics or {}})
        return FakeResp({}, status=404)

    def fake_delete(url, **kwargs):
        return FakeResp({}, status=204)

    monkeypatch.setattr(notifier.requests, "get", fake_get)
    monkeypatch.setattr(notifier.requests, "delete", fake_delete)
    from bot_app.services import settings as settings_svc
    monkeypatch.setattr(settings_svc, "get_system_settings", FakeSettings())


def _record_pushes(monkeypatch):
    pushes = []

    def fake_push(chat_id, ntype, title, body):
        pushes.append({"chat_id": chat_id, "type": ntype, "title": title, "body": body})

    monkeypatch.setattr(app_notify, "push_app_notification", fake_push)
    return pushes


def test_expires_today_warning_mirrored_to_app(client, mock_bot, monkeypatch):
    from bot_app.timeutil import myanmar_now
    day = myanmar_now().strftime("%d.%m.%Y")
    keys = [{"id": "7", "name": f"Aung (555666777) {day}"}]
    _fake_outline(monkeypatch, keys)
    pushes = _record_pushes(monkeypatch)

    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})
    assert resp.status_code == 200

    # The mock key lives on all 3 fake servers, so one push per server scan;
    # in production a key lives on exactly one server -> exactly one push.
    assert len(pushes) == 3
    for push in pushes:
        assert str(push["chat_id"]) == "555666777"
        assert push["type"] == "expiry_warning"
        assert "သက်တမ်းကုန်ဆုံး" in push["body"]
    # The Telegram DM still went out as before (customer + admins per server).
    assert any(str(cid) == "555666777" for cid, _ in mock_bot.calls["send_message"])


def test_gb_full_warning_mirrored_to_app(client, mock_bot, monkeypatch):
    keys = [{
        "id": "9",
        "name": "Aung (555666777) 01.01.2099",
        "dataLimit": {"bytes": 1000},
    }]
    _fake_outline(monkeypatch, keys, metrics={"9": 1000})
    pushes = _record_pushes(monkeypatch)

    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})
    assert resp.status_code == 200

    assert len(pushes) == 3
    for push in pushes:
        assert str(push["chat_id"]) == "555666777"
        assert push["type"] == "expiry_warning"
        assert "Data GB ပြည့်သွား" in push["body"]


def test_deleted_key_gets_no_app_copy(client, mock_bot, monkeypatch):
    from datetime import timedelta
    from bot_app.timeutil import myanmar_now
    day = (myanmar_now() - timedelta(days=1)).strftime("%d.%m.%Y")
    keys = [{"id": "7", "name": f"Aung (555666777) {day}"}]
    _fake_outline(monkeypatch, keys)
    pushes = _record_pushes(monkeypatch)

    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 3
    assert pushes == []
