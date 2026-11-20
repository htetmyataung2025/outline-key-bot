"""App version + activity stats for the H&E VPN Android app.

Every authenticated ``/api/app/*`` request carries an ``X-App-Version``
header (added by the app in bot update #17). The bearer-auth helper in
``routes_app`` records the caller's version here, so the owner can see
how many customers run each app version and how many were active
recently (Telegram command ``/appstats``).

Storage: ``app_versions`` -> {chat_id: {"v": version, "ts": last_seen}}.
Writes are throttled to one per user per hour unless the version
changed — the record is best-effort telemetry and must never slow down
or break a real request.
"""

import time

from bot_app.storage.kv import redis_get, redis_set

_KEY = "app_versions"
_WRITE_THROTTLE_S = 3600
_DAY_S = 24 * 3600


def _load() -> dict:
    data = redis_get(_KEY)
    return data if isinstance(data, dict) else {}


def record_seen(chat_id, version, now=None) -> None:
    """Remember that ``chat_id`` last used app ``version`` at ``now``."""
    version = str(version or "").strip()[:20]
    if not version or chat_id is None:
        return
    now = int(now if now is not None else time.time())
    data = _load()
    key = str(chat_id)
    entry = data.get(key)
    if (
        isinstance(entry, dict)
        and entry.get("v") == version
        and now - int(entry.get("ts") or 0) < _WRITE_THROTTLE_S
    ):
        return
    data[key] = {"v": version, "ts": now}
    redis_set(_KEY, data)


def version_stats(now=None) -> dict:
    """Aggregate counts: per version, plus 7/30-day activity."""
    now = int(now if now is not None else time.time())
    counts: dict = {}
    active_7d = 0
    active_30d = 0
    for entry in _load().values():
        if not isinstance(entry, dict):
            continue
        version = str(entry.get("v") or "").strip()
        if not version:
            continue
        counts[version] = counts.get(version, 0) + 1
        age = now - int(entry.get("ts") or 0)
        if age <= 7 * _DAY_S:
            active_7d += 1
        if age <= 30 * _DAY_S:
            active_30d += 1
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "active_7d": active_7d,
        "active_30d": active_30d,
    }
