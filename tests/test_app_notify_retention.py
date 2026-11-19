"""Tests for Bot Update #10b: the app notification inbox auto-deletes
entries older than 3 days (keys and history are stored elsewhere and
are not touched — only the notification list is pruned)."""

import time

import bot_app.services.app_notify as an

DAY = 24 * 3600


def _store(monkeypatch):
    data = {}
    monkeypatch.setattr(an, "redis_get", lambda key: data.get(key))
    monkeypatch.setattr(an, "redis_set",
                        lambda key, value: data.__setitem__(key, value))
    return data


def _item(ts, read=False, title="t"):
    return {"id": f"id{ts}", "ts": ts, "type": "broadcast",
            "title": title, "body": "b", "read": read}


def test_list_drops_entries_older_than_three_days(monkeypatch):
    data = _store(monkeypatch)
    now = int(time.time())
    data["app_notifs:42"] = [
        _item(now - 4 * DAY, title="old"),
        _item(now - 2 * DAY, title="recent"),
        _item(now, title="now"),
    ]
    items, unread = an.list_app_notifications(42)
    assert [i["title"] for i in items] == ["recent", "now"]
    assert unread == 2
    # The stored list is self-cleaned too.
    assert [i["title"] for i in data["app_notifs:42"]] == ["recent", "now"]


def test_push_prunes_expired_entries(monkeypatch):
    data = _store(monkeypatch)
    now = int(time.time())
    data["app_notifs:7"] = [_item(now - 10 * DAY, title="ancient")]
    an.push_app_notification(7, "purchase", "new", "body")
    titles = [i["title"] for i in data["app_notifs:7"]]
    assert titles == ["new"]


def test_mark_read_also_prunes(monkeypatch):
    data = _store(monkeypatch)
    now = int(time.time())
    data["app_notifs:9"] = [
        _item(now - 5 * DAY, title="expired"),
        _item(now - 3600, title="fresh"),
    ]
    an.mark_app_notifications_read(9)
    stored = data["app_notifs:9"]
    assert [i["title"] for i in stored] == ["fresh"]
    assert stored[0]["read"] is True
