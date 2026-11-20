"""Bot Update #17: app version stats — record_seen / version_stats,
the /appstats admin command, and the bearer-auth recording hook."""

from types import SimpleNamespace

import pytest

import bot_app.routes_app as ra
import bot_app.services.app_stats as app_stats

ADMIN = 111000111
OTHER = 999000999
NOW = 1_700_000_000


@pytest.fixture()
def store(monkeypatch):
    data = {}
    monkeypatch.setattr(app_stats, "redis_get", lambda key: data.get(key))
    monkeypatch.setattr(
        app_stats, "redis_set", lambda key, value: data.__setitem__(key, value)
    )
    return data


def _msg(chat_id):
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=1)


def test_record_seen_and_version_stats(store):
    app_stats.record_seen(1001, "0.6.8", now=NOW)
    app_stats.record_seen(1002, "0.6.8", now=NOW - 2 * 24 * 3600)
    app_stats.record_seen(1003, "0.6.7", now=NOW - 20 * 24 * 3600)

    stats = app_stats.version_stats(now=NOW)
    assert stats["counts"] == {"0.6.8": 2, "0.6.7": 1}
    assert stats["total"] == 3
    assert stats["active_7d"] == 2
    assert stats["active_30d"] == 3


def test_record_seen_throttles_same_version_writes(store):
    app_stats.record_seen(1001, "0.6.8", now=NOW)
    app_stats.record_seen(1001, "0.6.8", now=NOW + 60)
    assert store["app_versions"]["1001"]["ts"] == NOW

    # An hour later the same version refreshes the timestamp...
    app_stats.record_seen(1001, "0.6.8", now=NOW + 3601)
    assert store["app_versions"]["1001"]["ts"] == NOW + 3601

    # ...and a version change always writes immediately.
    app_stats.record_seen(1001, "0.6.9", now=NOW + 3602)
    assert store["app_versions"]["1001"] == {"v": "0.6.9", "ts": NOW + 3602}


def test_record_seen_ignores_blank_version(store):
    app_stats.record_seen(1001, "", now=NOW)
    app_stats.record_seen(1001, None, now=NOW)
    app_stats.record_seen(None, "0.6.8", now=NOW)
    assert store == {}


def test_appstats_command_reports_counts(store, mock_bot, monkeypatch):
    import bot_app.handlers.admin as admin_handlers

    monkeypatch.setattr(admin_handlers, "ADMIN_CHAT_IDS", [ADMIN])
    app_stats.record_seen(1001, "0.6.8")
    app_stats.record_seen(1002, "0.6.8")
    admin_handlers.handle_appstats(_msg(ADMIN))

    sent = mock_bot.calls["send_message"]
    assert sent  # a reply was sent to the admin
    text = " ".join(str(c[1]) for c in sent if len(c) > 1)
    assert "0.6.8" in text
    assert "2 ယောက်" in text


def test_appstats_command_empty_and_non_admin(store, mock_bot, monkeypatch):
    import bot_app.handlers.admin as admin_handlers

    monkeypatch.setattr(admin_handlers, "ADMIN_CHAT_IDS", [ADMIN])
    admin_handlers.handle_appstats(_msg(ADMIN))
    texts = [
        str(call[1]) for call in mock_bot.calls["send_message"] if len(call) > 1
    ]
    assert any("မရှိသေးပါ" in t for t in texts)

    mock_bot.calls["send_message"].clear()
    admin_handlers.handle_appstats(_msg(OTHER))
    assert not mock_bot.calls["send_message"]


def test_bearer_hook_records_version_header(store, client):
    token = ra._make_app_token(424242)
    resp = client.get(
        "/api/app/notifications",
        headers={
            "Authorization": f"Bearer {token}",
            "X-App-Version": "0.6.8",
        },
    )
    assert resp.status_code == 200
    entry = store["app_versions"]["424242"]
    assert entry["v"] == "0.6.8"

    # Without the header (older builds) nothing is recorded.
    store.clear()
    token2 = ra._make_app_token(515151)
    resp = client.get(
        "/api/app/notifications",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200
    assert store == {}
