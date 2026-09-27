"""Vercel Upstash Redis REST API client.

When KV env vars are absent (local dev / tests) both helpers degrade
gracefully: reads return None, writes return False, and callers fall
back to the /tmp JSON files.
"""

import json
import os
import urllib.parse

from bot_app.helpers.http_session import get_session


def _kv_config():
    url = os.environ.get("KV_REST_API_URL", "").rstrip("/")
    token = os.environ.get("KV_REST_API_TOKEN", "")
    # Vercel KV_* aliases (Upstash integration exposes KV_* names)
    if not url:
        url = os.environ.get("KV_URL", "").rstrip("/")
    if not token:
        token = os.environ.get("KV_REST_API_TOKEN", "") or os.environ.get("KV_TOKEN", "")
        if not token:
            raw = os.environ.get("KV_URL", "")
            if "://" in raw and "@" in raw:
                token = raw.split("://", 1)[1].split("@", 1)[0]
    return url, token


def redis_get(key):
    url, token = _kv_config()
    if not url or not token:
        return None
    try:
        encoded = urllib.parse.quote(json.dumps(key))
        res = get_session().get(
            f"{url}/get/{encoded}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if res.status_code == 200:
            val = res.json().get("result")
            return json.loads(val) if val else None
    except Exception:
        pass
    return None


def redis_set(key, value):
    # Every shared-state mutation bumps the dashboard data-version so the
    # admin UI can live-refresh (see bot_app/storage/versioning.py). Runs
    # even when Redis is unconfigured (dev/tests) — the version then lives
    # in a local JSON file. Guarded against recursion for the version key
    # itself, and never allowed to break the caller's write.
    if key != "admin_data_version":
        try:
            from bot_app.storage.versioning import bump_data_version

            bump_data_version()
        except Exception:
            pass

    url, token = _kv_config()
    if not url or not token:
        return False
    try:
        # Value goes in the POST body, not the URL: urllib's percent-encoding
        # leaves '/' intact by default, so any state blob whose content
        # contains '/' made Upstash reject the GET command path with
        # "ERR syntax error" and the write was silently lost.
        encoded_key = urllib.parse.quote(json.dumps(key), safe="")
        res = get_session().post(
            f"{url}/set/{encoded_key}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
            data=json.dumps(value),
            timeout=5,
        )
        return res.status_code == 200
    except Exception:
        return False


def redis_increment_with_expiry(key, ttl_seconds):
    """INCR ``key`` and keep a TTL on it (refreshed every call).

    Used by rate limiting: the window then measures "since the last attempt",
    and refreshing EXPIRE on every increment means a crash between the two
    commands can never leave a TTL-less key behind (a permanent lockout).
    Deliberately bypasses redis_set — counters must not bump the dashboard
    data-version or trigger SSE refresh storms.

    Returns the new count, or None when Redis is unconfigured/unreachable
    (the caller decides how to degrade).
    """
    url, token = _kv_config()
    if not url or not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        encoded_key = urllib.parse.quote(json.dumps(key), safe="")
        res = get_session().post(f"{url}/incr/{encoded_key}", headers=headers, timeout=5)
        if res.status_code != 200:
            return None
        count = int(res.json().get("result") or 0)
        get_session().post(
            f"{url}/expire/{encoded_key}/{int(ttl_seconds)}", headers=headers, timeout=5
        )
        return count
    except Exception:
        return None


def redis_delete(key):
    """DEL ``key``. True on success, False when unconfigured/unreachable."""
    url, token = _kv_config()
    if not url or not token:
        return False
    try:
        encoded_key = urllib.parse.quote(json.dumps(key), safe="")
        res = get_session().post(
            f"{url}/del/{encoded_key}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        return res.status_code == 200
    except Exception:
        return False


def redis_set_nx(key, ttl_seconds, value="1"):
    """Acquire a short-lived lock: ``SET key value NX EX ttl``.

    Used to guard non-idempotent flows (e.g. the points claim) against a
    double-tap in the serverless runtime. Deliberately bypasses ``redis_set``
    so a lock never bumps the dashboard data-version.

    Returns:
      * ``True``  — lock acquired (key did not exist).
      * ``False`` — key already held by a concurrent request.
      * ``None``  — KV unconfigured/unreachable; caller treats as best-effort
        (single-process dev/tests are safe without a lock).
    """
    url, token = _kv_config()
    if not url or not token:
        return None
    try:
        # Lock value is a fixed scalar with no '/', so path-argument form is
        # safe here (SET key value NX EX ttl).
        encoded_key = urllib.parse.quote(json.dumps(key), safe="")
        encoded_val = urllib.parse.quote(str(value), safe="")
        res = get_session().post(
            f"{url}/set/{encoded_key}/{encoded_val}/NX/EX/{int(ttl_seconds)}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if res.status_code == 200:
            # Upstash returns {"result":"OK"} on set, {"result":null} when NX fails.
            return res.json().get("result") == "OK"
        return False
    except Exception:
        return None

