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
# Inbox entries older than 3 days are dropped automatically (the user
# asked for a self-cleaning inbox; keys/history live elsewhere and are
# unaffected — only the notification list is pruned).
_MAX_AGE_SECONDS = 3 * 24 * 60 * 60


def _fresh(items):
    """Keep only dict items whose ts is within the retention window."""
    cutoff = int(time.time()) - _MAX_AGE_SECONDS
    kept = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ts = item.get("ts")
        if isinstance(ts, (int, float)) and ts < cutoff:
            continue
        kept.append(item)
    return kept


def _key(chat_id) -> str:
    return f"app_notifs:{chat_id}"


def push_app_notification(chat_id, ntype: str, title: str, body: str) -> None:
    try:
        key = _key(chat_id)
        items = redis_get(key)
        if not isinstance(items, list):
            items = []
        items = _fresh(items)
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
        fresh = _fresh(items)
        if len(fresh) != len(items):
            try:
                redis_set(_key(chat_id), fresh)  # self-clean expired entries
            except Exception:
                pass
        items = fresh
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
        raw_count = len(items)
        items = _fresh(items)
        changed = len(items) != raw_count
        for item in items:
            if isinstance(item, dict) and not item.get("read"):
                item["read"] = True
                changed = True
        if changed:
            redis_set(key, items)
    except Exception:
        pass
