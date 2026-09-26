"""Monotonic data-version counter for live dashboard refresh.

Every shared-state mutation (slips, wallets, key registry, redeems,
settings…) funnels through ``redis_set``, which bumps this counter.
The admin dashboard polls ``GET /api/admin/version`` cheaply and only
re-fetches real data when the number changes — so an order arriving via
Telegram, an approval from either surface, or a settings save shows up
everywhere within one poll interval, without a manual refresh.

Redis is the source of truth in production; a local JSON file keeps the
mechanism working in dev/tests where Redis is intentionally disabled.
"""

import json
import os

from bot_app.storage.kv import redis_get, redis_set
from bot_app.storage.paths import DATA_VERSION_FILE

VERSION_KEY = "admin_data_version"


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
    return new_val
