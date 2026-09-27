"""Login brute-force protection for POST /api/admin/login.

Every login attempt increments a fixed-window counter keyed by the client
IP; once it exceeds ``LOGIN_RATE_LIMIT_MAX`` within ``LOGIN_RATE_LIMIT_WINDOW``
seconds the endpoint answers 429 before even comparing the submitted
password. A successful login clears the counter, so the limit effectively
measures *consecutive* failures — an admin who mistypes twice a day never
feels it.

Storage: Upstash Redis when configured (atomic INCR/EXPIRE, shared across
serverless instances); otherwise a per-process in-memory fallback for local
dev and tests. Storage failures degrade to the in-memory store, so the panel
never hard-locks because the counter store is down.
"""

import hashlib
import os
import threading
import time

from bot_app.storage.kv import redis_delete, redis_increment_with_expiry

_DEFAULT_MAX = 5
_DEFAULT_WINDOW = 600  # seconds

_memory_lock = threading.Lock()
_memory_store: dict[str, tuple[int, float]] = {}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def login_rate_limit_max() -> int:
    return _env_int("LOGIN_RATE_LIMIT_MAX", _DEFAULT_MAX)


def login_rate_limit_window() -> int:
    return _env_int("LOGIN_RATE_LIMIT_WINDOW", _DEFAULT_WINDOW)


def _bucket_key(identifier: str) -> str:
    # Hashed so raw client IPs never appear in the KV key namespace.
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:32]
    return f"login_rl:{digest}"


def client_ip_from_headers(headers) -> str:
    """Best-effort client IP for rate-limit keying.

    Vercel's ``X-Vercel-Forwarded-For`` carries the peer IP their edge saw.
    A plain ``X-Forwarded-For`` may carry client-supplied (spoofable) values
    first, so only its RIGHTMOST entry — the one the trusted edge appended —
    is used when the Vercel header is absent.
    """
    vercel_ip = (headers.get("X-Vercel-Forwarded-For") or "").strip()
    if vercel_ip:
        return vercel_ip.split(",")[0].strip()
    forwarded = (headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[-1].strip()
    real_ip = (headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip
    return "unknown"


def register_login_attempt(identifier: str) -> tuple[int, bool]:
    """Count one login attempt for ``identifier`` (usually the client IP).

    Returns ``(count, exceeded)`` where ``exceeded`` means the counter is
    strictly above the configured maximum and the request must be rejected.
    """
    max_attempts = login_rate_limit_max()
    window = login_rate_limit_window()
    key = _bucket_key(identifier)

    count = redis_increment_with_expiry(key, window)
    if count is None:
        # KV unconfigured or unreachable — per-process fallback.
        now = time.time()
        with _memory_lock:
            hits, expires_at = _memory_store.get(key, (0, 0.0))
            if now >= expires_at:
                hits, expires_at = 0, now + window
            hits += 1
            _memory_store[key] = (hits, expires_at)
        count = hits
    return count, count > max_attempts


def clear_login_attempts(identifier: str) -> None:
    """Successful login: forget this client's consecutive failures."""
    key = _bucket_key(identifier)
    redis_delete(key)
    with _memory_lock:
        _memory_store.pop(key, None)


def reset_memory_store() -> None:
    """Test hook: wipe the in-memory fallback between tests."""
    with _memory_lock:
        _memory_store.clear()
