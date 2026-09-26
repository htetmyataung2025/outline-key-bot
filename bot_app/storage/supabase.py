"""Supabase REST API client via PostgREST.

Requires no heavy external dependencies; utilizes standard `requests` for fast
cold starts on serverless platforms and reliable free-tier cloud persistence.
"""

import os
import requests


def get_supabase_config() -> tuple[str, str]:
    """Retrieve validated Supabase URL and API Key from environment."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "").strip()
    return url, key


def is_supabase_configured() -> bool:
    """True if both Supabase URL and API key are provided."""
    url, key = get_supabase_config()
    return bool(url and key and url.startswith("http"))


def _headers() -> dict:
    _, key = get_supabase_config()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def supabase_get(table: str, params: dict | None = None, timeout: int = 5) -> list | None:
    """Fetch rows from a Supabase table."""
    if not is_supabase_configured():
        return None
    url, _ = get_supabase_config()
    try:
        resp = requests.get(
            f"{url}/rest/v1/{table}",
            headers=_headers(),
            params=params or {},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        return None
    return None


def supabase_upsert(table: str, data: dict | list, on_conflict: str = "", timeout: int = 5) -> list | None:
    """Insert or update rows in a Supabase table."""
    if not is_supabase_configured():
        return None
    url, _ = get_supabase_config()
    headers = _headers()
    headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
    params = {}
    if on_conflict:
        params["on_conflict"] = on_conflict

    try:
        resp = requests.post(
            f"{url}/rest/v1/{table}",
            headers=headers,
            params=params,
            json=data,
            timeout=timeout,
        )
        if 200 <= resp.status_code < 300:
            return resp.json()
    except Exception:
        return None
    return None


def supabase_delete(table: str, params: dict, timeout: int = 5) -> bool:
    """Delete matching rows from a Supabase table."""
    if not is_supabase_configured() or not params:
        return False
    url, _ = get_supabase_config()
    try:
        resp = requests.delete(
            f"{url}/rest/v1/{table}",
            headers=_headers(),
            params=params,
            timeout=timeout,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        return False
