"""Dynamic System Settings Service.

Allows Outline Servers, Payment Phones, Required Channel, OCR Key, and Plans
to be managed in real-time from the Admin Control Center, removing the need to
edit `.env` or redeploy on configuration changes.

Persistence backend (first available wins):
  1. Supabase `system_settings` table — used only when SUPABASE_URL/KEY are set
     (kept so existing Supabase deployments keep working unchanged).
  2. KV (Upstash Redis) `system_settings_data` key — the single-store default.
  3. In-memory fallback / env defaults — local dev and tests.
"""

import time
import requests
from bot_app.storage.kv import redis_get, redis_set
from bot_app.storage.supabase import is_supabase_configured, supabase_get, supabase_upsert
from bot_app.timeutil import myanmar_now

# In-memory settings cache and local fallback
_SETTINGS_CACHE: dict | None = None
_LAST_CACHE_TIME: float = 0.0
_CACHE_TTL_SECONDS: float = 45.0
_FALLBACK_SETTINGS: dict | None = None

# KV key holding the whole settings dict when running KV-only (no Supabase).
_KV_SETTINGS_KEY = "system_settings_data"


def _get_default_settings() -> dict:
    """Return fallback baseline settings derived from initial env/config or local edits."""
    if _FALLBACK_SETTINGS is not None:
        return dict(_FALLBACK_SETTINGS)

    from bot_app.config import (
        MY_PAYMENT_PHONES,
        OCR_API_KEY,
        OUTLINE_API_URL_1,
        OUTLINE_API_URL_2,
        OUTLINE_API_URL_3,
        PLANS,
        REQUIRED_CHANNEL,
    )

    # Only servers actually configured in the environment become part of the
    # baseline: an unset OUTLINE_API_URL_* must never surface as a phantom
    # server in the dashboard, the bot, or the Supabase seed.
    servers = [
        {"id": server_id, "name": name, "api_url": url}
        for server_id, name, url in (
            (1, "Server 1 (SG-1)", OUTLINE_API_URL_1),
            (2, "Server 2 (SG-2)", OUTLINE_API_URL_2),
            (3, "Server 3 (VIP)", OUTLINE_API_URL_3),
        )
        if url
    ]

    return {
        "servers": servers,
        "payment_phones": list(MY_PAYMENT_PHONES),
        "required_channel": REQUIRED_CHANNEL,
        "ocr_api_key": OCR_API_KEY,
        "plans": dict(PLANS),
    }


def invalidate_settings_cache(reset_fallback: bool = False):
    """Clear memory cache forcing next read to sync with Supabase or defaults."""
    global _SETTINGS_CACHE, _LAST_CACHE_TIME, _FALLBACK_SETTINGS
    _SETTINGS_CACHE = None
    _LAST_CACHE_TIME = 0.0
    if reset_fallback:
        _FALLBACK_SETTINGS = None


def get_system_settings(force_refresh: bool = False) -> dict:
    """Fetch all dynamic settings from Supabase (or memory cache/defaults)."""
    global _SETTINGS_CACHE, _LAST_CACHE_TIME

    now = time.time()
    if not force_refresh and _SETTINGS_CACHE and (now - _LAST_CACHE_TIME < _CACHE_TTL_SECONDS):
        return _SETTINGS_CACHE

    defaults = _get_default_settings()

    if not is_supabase_configured():
        # KV-only mode: settings persist in the same Redis store as everything
        # else. Missing keys fall back to env/in-memory defaults.
        kv_data = redis_get(_KV_SETTINGS_KEY)
        if isinstance(kv_data, dict) and kv_data:
            merged = {k: kv_data.get(k, defaults[k]) for k in defaults}
            _SETTINGS_CACHE = merged
            _LAST_CACHE_TIME = now
            return _SETTINGS_CACHE
        _SETTINGS_CACHE = defaults
        _LAST_CACHE_TIME = now
        return _SETTINGS_CACHE

    try:
        rows = supabase_get("system_settings", {"select": "*"})
        if rows and isinstance(rows, list):
            settings_map = {r["key"]: r["value"] for r in rows if "key" in r and "value" in r}
            merged = {
                "servers": settings_map.get("servers", defaults["servers"]),
                "payment_phones": settings_map.get("payment_phones", defaults["payment_phones"]),
                "required_channel": settings_map.get("required_channel", defaults["required_channel"]),
                "ocr_api_key": settings_map.get("ocr_api_key", defaults["ocr_api_key"]),
                "plans": settings_map.get("plans", defaults["plans"]),
            }
            _SETTINGS_CACHE = merged
            _LAST_CACHE_TIME = now
            return _SETTINGS_CACHE
        elif rows == []:
            # Seed initial defaults to Supabase so table is populated
            seed_rows = [
                {"key": k, "value": v, "description": f"Initial {k} config", "updated_by": "System"}
                for k, v in defaults.items()
            ]
            supabase_upsert("system_settings", seed_rows, on_conflict="key")
            _SETTINGS_CACHE = defaults
            _LAST_CACHE_TIME = now
            return _SETTINGS_CACHE
    except Exception:
        pass

    _SETTINGS_CACHE = defaults
    _LAST_CACHE_TIME = now
    return _SETTINGS_CACHE


def save_system_settings(new_settings: dict, updated_by: str = "Admin") -> dict:
    """Save updated configurations to Supabase and invalidate cache."""
    now_str = myanmar_now().strftime("%Y-%m-%d %H:%M:%S")
    current = get_system_settings()

    # Merge incoming keys
    servers = new_settings.get("servers", current.get("servers"))
    payment_phones = new_settings.get("payment_phones", current.get("payment_phones"))
    required_channel = new_settings.get("required_channel", current.get("required_channel"))
    ocr_api_key = new_settings.get("ocr_api_key", current.get("ocr_api_key"))
    plans = new_settings.get("plans", current.get("plans"))

    payload_rows = [
        {"key": "servers", "value": servers, "updated_at": now_str, "updated_by": str(updated_by)},
        {"key": "payment_phones", "value": payment_phones, "updated_at": now_str, "updated_by": str(updated_by)},
        {"key": "required_channel", "value": required_channel, "updated_at": now_str, "updated_by": str(updated_by)},
        {"key": "ocr_api_key", "value": ocr_api_key, "updated_at": now_str, "updated_by": str(updated_by)},
        {"key": "plans", "value": plans, "updated_at": now_str, "updated_by": str(updated_by)},
    ]

    global _FALLBACK_SETTINGS
    _FALLBACK_SETTINGS = {
        "servers": servers,
        "payment_phones": payment_phones,
        "required_channel": required_channel,
        "ocr_api_key": ocr_api_key,
        "plans": plans,
    }

    if is_supabase_configured():
        supabase_upsert("system_settings", payload_rows, on_conflict="key")
        # Supabase writes skip redis_set, so bump the live-refresh version here.
        from bot_app.storage.versioning import bump_data_version
        bump_data_version()
    else:
        # KV-only mode: persist the whole settings dict. redis_set bumps the
        # live-refresh data version itself (no separate bump needed).
        redis_set(_KV_SETTINGS_KEY, _FALLBACK_SETTINGS)

    invalidate_settings_cache()
    return get_system_settings(force_refresh=True)


def test_outline_server(api_url: str) -> dict:
    """Test reachability and latency of an Outline API URL before saving."""
    if not api_url or not api_url.startswith("http"):
        return {"success": False, "error": "Invalid URL. Must start with http:// or https://"}

    start_time = time.time()
    try:
        resp = requests.get(f"{api_url.rstrip('/')}/access-keys", verify=False, timeout=4)
        latency_ms = int((time.time() - start_time) * 1000)
        if resp.status_code == 200:
            keys_count = len(resp.json().get("accessKeys", []))
            return {
                "success": True,
                "latency_ms": latency_ms,
                "keys_count": keys_count,
            }
        return {
            "success": False,
            "latency_ms": latency_ms,
            "error": f"Server responded with HTTP {resp.status_code}",
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "latency_ms": latency_ms,
            "error": str(e),
        }
