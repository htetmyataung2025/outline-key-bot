"""In-app notification inbox for the H&E VPN Android app.

Events that matter to a customer (top-up approved/rejected, purchase
completed) are appended to a small per-user list in Redis. The app reads
them via ``GET /api/app/notifications`` and also polls them with a
background worker that raises local notifications on the device.

Storage: ``app_notifs:<chat_id>`` -> list of dicts, newest first, capped.
All functions are best-effort: a notification failure must never break
the money flow that produced the event.
"""

import time
import uuid

from bot_app.storage.kv import redis_get, redis_set

_MAX_ITEMS = 30


def _key(chat_id) -> str:
    return f"app_notifs:{chat_id}"


def push_app_notification(chat_id, ntype: str, title: str, body: str) -> None:
    try:
        key = _key(chat_id)
        items = redis_get(key)
        if not isinstance(items, list):
            items = []
        items = [i for i in items if isinstance(i, dict)]
        items.insert(0, {
            "id": uuid.uuid4().hex[:12],
            "ts": int(time.time()),
            "type": ntype,
            "title": title,
            "body": body,
            "read": False,
        })
        redis_set(key, items[:_MAX_ITEMS])
    except Exception:
        pass


def list_app_notifications(chat_id):
    """(items, unread_count) for one user."""
    try:
        items = redis_get(_key(chat_id))
        if not isinstance(items, list):
            return [], 0
        items = [i for i in items if isinstance(i, dict)]
        unread = sum(1 for i in items if not i.get("read"))
        return items, unread
    except Exception:
        return [], 0


def mark_app_notifications_read(chat_id) -> None:
    try:
        key = _key(chat_id)
        items = redis_get(key)
        if not isinstance(items, list):
            return
        changed = False
        for item in items:
            if isinstance(item, dict) and not item.get("read"):
                item["read"] = True
                changed = True
        if changed:
            redis_set(key, items)
    except Exception:
        pass
