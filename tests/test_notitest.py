"""Bot Update #15: /notitest — admin self-test for app notifications."""

from types import SimpleNamespace

import pytest

import bot_app.services.app_notify as an

ADMIN = 111000111
OTHER = 999000999


@pytest.fixture()
def inbox(monkeypatch):
    data = {}
    monkeypatch.setattr(an, "redis_get", lambda key: data.get(key))
    monkeypatch.setattr(an, "redis_set",
                        lambda key, value: data.__setitem__(key, value))
    return data


def _msg(chat_id):
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=1)


def test_notitest_pushes_to_own_inbox(inbox, mock_bot, monkeypatch):
    import bot_app.handlers.admin as admin_handlers

    monkeypatch.setattr(admin_handlers, "ADMIN_CHAT_IDS", [ADMIN])
    admin_handlers.handle_notitest(_msg(ADMIN))

    items, unread = an.list_app_notifications(ADMIN)
    assert items and items[0]["type"] == "test"
    assert "စမ်းသပ်" in items[0]["title"]
    assert unread == 1
    sent = [str(m[0]) for m in mock_bot.calls["send_message"]]
    assert str(ADMIN) in sent


def test_notitest_ignores_non_admins(inbox, mock_bot, monkeypatch):
    import bot_app.handlers.admin as admin_handlers

    monkeypatch.setattr(admin_handlers, "ADMIN_CHAT_IDS", [ADMIN])
    admin_handlers.handle_notitest(_msg(OTHER))

    items, _ = an.list_app_notifications(OTHER)
    assert items == []
    assert not mock_bot.calls["send_message"]
