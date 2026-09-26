"""Monotonic data-version counter + in-process change bus for live updates.

Every shared-state mutation (slips, wallets, key registry, redeems,
settings…) funnels through ``redis_set``, which bumps this counter.

Two consumers exist:

1. The admin dashboard's SSE stream (``GET /api/admin/events``) subscribes
   to the in-process bus and receives the new version the moment it is
   bumped — true push, no polling, in the hybrid/polling single-process
   deployment.
2. ``GET /api/admin/version`` remains as a cheap fallback for serverless
   deployments (Vercel), where long-lived stream connections cannot be
   held and the dashboard falls back to asking "did the version move?".

Redis is the source of truth in production; a local JSON file keeps the
mechanism working in dev/tests where Redis is intentionally disabled.
"""

import json
import os
import queue
import threading

from bot_app.storage.kv import redis_get, redis_set
from bot_app.storage.paths import DATA_VERSION_FILE

VERSION_KEY = "admin_data_version"

# In-process change bus: each SSE client holds one bounded queue. Producers
# (bot thread, Flask worker threads) never block on a slow/stale consumer —
# if a queue is full the client has bigger problems and the next successful
# event carries the latest version anyway.
_subscribers: list[queue.Queue] = []
_bus_lock = threading.Lock()


def get_data_version() -> int:
    val = redis_get(VERSION_KEY)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val)
    try:
        if os.path.exists(DATA_VERSION_FILE):
            with open(DATA_VERSION_FILE, "r") as f:
                return int(json.load(f).get("version", 0))
    except Exception:
        pass
    return 0


def subscribe() -> queue.Queue:
    """Register a new change listener. Returns its event queue."""
    q: queue.Queue = queue.Queue(maxsize=32)
    with _bus_lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _bus_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def _notify_subscribers(version: int) -> None:
    with _bus_lock:
        targets = list(_subscribers)
    for q in targets:
        try:
            q.put_nowait(version)
        except queue.Full:
            continue


def bump_data_version() -> int:
    """Increment the version after a state write. Never raises."""
    try:
        current = get_data_version()
    except Exception:
        current = 0
    new_val = current + 1
    try:
        redis_set(VERSION_KEY, new_val)
    except Exception:
        pass
    try:
        with open(DATA_VERSION_FILE, "w") as f:
            json.dump({"version": new_val}, f)
    except Exception:
        pass
    try:
        _notify_subscribers(new_val)
    except Exception:
        pass
    return new_val
