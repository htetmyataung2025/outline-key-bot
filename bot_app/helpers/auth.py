"""Authentication and cryptographic security helpers for Admin Control Center.

Supports:
1. Telegram Mini App HMAC-SHA256 validation of WebApp ``initData`` (kept for
   API clients and diagnostics; the dashboard itself no longer auto-logs in
   with it).
2. Dashboard login via Admin ID + secret password (``POST /api/admin/login``),
   then ``Authorization: Bearer <ADMIN_SECRET_KEY>`` + ``X-Admin-ID`` on every
   request. The ID must belong to ``ADMIN_CHAT_IDS``.
3. Flask route protection decorator ``@require_admin_api``.
"""

from functools import wraps
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from flask import g, jsonify, request

from bot_app.config import is_admin

def _tma_max_age_seconds() -> int:
    """Max accepted age of initData ``auth_date``. 0 (default) disables the check.

    Telegram does not refresh ``initData`` while a Mini App stays open, so a
    strict expiry would lock out an admin who leaves the dashboard tab loaded
    past the window. Enable deliberately via ``TMA_MAX_AGE_SECONDS`` once the
    client re-mints initData on re-auth (e.g. through a session token).
    """
    raw = os.environ.get("TMA_MAX_AGE_SECONDS", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


def get_telegram_token() -> str:
    """Retrieve current Telegram bot token from environment or config."""
    return os.environ.get("TELEGRAM_TOKEN", "")


def get_admin_secret_key() -> str:
    """Retrieve desktop admin fallback secret key strictly from environment.

    Never fallback to a default password. If unset, desktop Bearer auth is disabled.
    """
    return os.environ.get("ADMIN_SECRET_KEY", "").strip()


def check_admin_credentials(admin_id: str, password: str) -> tuple[int, str] | None:
    """Validate an Admin ID + password pair for the dashboard login form.

    The password is the shared ``ADMIN_SECRET_KEY``; the ID must additionally
    belong to ``ADMIN_CHAT_IDS``, so a leaked secret alone cannot grant access.
    The password is checked first — only holders of the correct secret may
    probe which Telegram IDs are admins.

    Returns ``(http_status, error_message)`` on failure, ``None`` when valid.
    """
    secret = get_admin_secret_key()
    if not secret:
        return 403, "Admin login is not enabled. Set ADMIN_SECRET_KEY in .env"
    if not hmac.compare_digest(password, secret):
        return 401, "Invalid admin password"
    if not admin_id.isdigit() or not is_admin(admin_id):
        return 403, "Forbidden: This Admin ID is not authorized"
    return None


def verify_telegram_init_data(init_data_raw: str, bot_token: str | None = None) -> dict | None:
    """Validate raw Telegram WebApp initData query string.

    Returns the parsed data dictionary (with 'user' parsed as a dict) if the
    HMAC-SHA256 signature is valid, or None if invalid or tampered.
    """
    if not init_data_raw:
        return None

    token = bot_token or get_telegram_token()
    if not token:
        return None

    try:
        parsed_items = dict(parse_qsl(init_data_raw, keep_blank_values=True))
        hash_check = parsed_items.pop("hash", None)
        if not hash_check:
            return None

        # Sort alphabetically and format as key=value separated by newlines
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_items.items()))

        # Secret key is HMAC-SHA256 of bot token with key b"WebAppData"
        secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(computed_hash.lower(), hash_check.lower()):
            max_age = _tma_max_age_seconds()
            if max_age:
                try:
                    issued_at = int(parsed_items.get("auth_date", "0"))
                except ValueError:
                    issued_at = 0
                if time.time() - issued_at > max_age:
                    return None
            if "user" in parsed_items and isinstance(parsed_items["user"], str):
                try:
                    parsed_items["user"] = json.loads(parsed_items["user"])
                except Exception:
                    pass
            return parsed_items
    except Exception:
        return None

    return None


def require_admin_api(f):
    """Flask decorator protecting Admin REST API endpoints.

    Requires either:
    - ``X-Telegram-Init-Data`` header with valid signature and admin user ID.
    - ``Authorization: Bearer <ADMIN_SECRET_KEY>`` header.

    Attaches authenticated admin profile to ``flask.g.admin_user``.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check Telegram Mini App initData
        tma_init_data = request.headers.get("X-Telegram-Init-Data")
        if tma_init_data:
            verified_data = verify_telegram_init_data(tma_init_data)
            if not verified_data:
                return jsonify({"error": "Invalid or tampered Telegram session"}), 401

            user_obj = verified_data.get("user")
            user_id = user_obj.get("id") if isinstance(user_obj, dict) else None

            if not user_id or not is_admin(user_id):
                return jsonify({"error": "Forbidden: Admin privileges required"}), 403

            g.admin_user = user_obj
            return f(*args, **kwargs)

        # 2. Check Desktop Web Bearer token fallback (+ optional Admin ID binding)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            secret = get_admin_secret_key()
            if not secret:
                return jsonify({"error": "Desktop admin access is not enabled. Set ADMIN_SECRET_KEY in .env"}), 403
            if hmac.compare_digest(token, secret):
                admin_id = request.headers.get("X-Admin-ID", "").strip()
                if admin_id:
                    # The dashboard always identifies its logged-in admin; a
                    # correct secret paired with a non-admin ID is rejected.
                    if not admin_id.isdigit() or not is_admin(admin_id):
                        return jsonify({"error": "Forbidden: This Admin ID is not authorized"}), 403
                    g.admin_user = {"id": admin_id, "username": "Admin"}
                else:
                    g.admin_user = {"id": "desktop_admin", "username": "Admin"}
                return f(*args, **kwargs)
            return jsonify({"error": "Invalid admin token"}), 401

        # 3. Missing credentials
        return jsonify({"error": "Unauthorized: Missing authentication"}), 401

    return decorated_function

