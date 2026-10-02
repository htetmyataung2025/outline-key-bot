"""Admin Telemetry and KPI Metrics service."""

import time
import threading
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

from bot_app.timeutil import myanmar_now
from bot_app.services.orders import load_all_users, load_sales_history
from bot_app.services.registry import load_persistent_keys
from bot_app.services.slips import get_slips_list
from bot_app.utils import bytes_to_gb


# Live server probing is the slow part of the overview payload (each server does
# blocking HTTP calls). Cache the probed result and serve it stale-while-revalidate
# so the dashboard responds instantly after warm-up and a slow/offline VPN server
# can never make the whole overview time out. The cheap local KPIs stay fresh.
SERVER_TELEMETRY_TTL = 120  # seconds until a cached probe is considered stale
_server_cache = {"key": None, "data": None, "ts": 0.0}
_server_cache_lock = threading.Lock()
_refresh_lock = threading.Lock()
_refreshing = {"active": False}


def get_server_metrics(server_id: int, name: str, api_url: str) -> dict:
    """Fetch health and metrics for a specific Outline server."""
    if not api_url:
        return {
            "id": server_id,
            "name": name,
            "is_active": False,
            "total_keys": 0,
            "total_transferred_gb": 0.0,
            "latency_ms": 0,
            "error": "Not configured",
        }

    start_time = time.time()
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=3)
        latency_ms = int((time.time() - start_time) * 1000)

        if keys_resp.status_code != 200:
            return {
                "id": server_id,
                "name": name,
                "is_active": False,
                "total_keys": 0,
                "total_transferred_gb": 0.0,
                "latency_ms": latency_ms,
                "error": f"HTTP {keys_resp.status_code}",
            }

        keys_data = keys_resp.json().get("accessKeys", [])
        total_keys = len(keys_data)

        # Get data transfer metrics
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=3)
        total_bytes = 0
        if metrics_resp.status_code == 200:
            bytes_dict = metrics_resp.json().get("bytesTransferredByUserId", {})
            total_bytes = sum(bytes_dict.values())

        transferred_gb = round(bytes_to_gb(total_bytes), 2)

        return {
            "id": server_id,
            "name": name,
            "is_active": True,
            "total_keys": total_keys,
            "total_transferred_gb": transferred_gb,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return {
            "id": server_id,
            "name": name,
            "is_active": False,
            "total_keys": 0,
            "total_transferred_gb": 0.0,
            "latency_ms": latency_ms,
            "error": str(e),
        }


def _probe_all_servers(configured_servers: list) -> list:
    """Probe every configured server concurrently, preserving input order."""
    if not configured_servers:
        return []

    with ThreadPoolExecutor(max_workers=min(8, len(configured_servers))) as executor:
        futures = [
            executor.submit(
                get_server_metrics,
                srv.get("id", idx),
                srv.get("name", f"Server {idx}"),
                srv.get("api_url", ""),
            )
            for idx, srv in enumerate(configured_servers, 1)
        ]
        # Iterating the futures list keeps results in the original server order.
        return [f.result() for f in futures]


def _store_servers(cache_key, servers) -> None:
    with _server_cache_lock:
        _server_cache["key"] = cache_key
        _server_cache["data"] = servers
        _server_cache["ts"] = time.time()


def _refresh_in_background(configured_servers, cache_key) -> None:
    """Probe servers in a daemon thread (single-flight) and update the cache."""
    with _refresh_lock:
        if _refreshing["active"]:
            return
        _refreshing["active"] = True

    def worker():
        try:
            _store_servers(cache_key, _probe_all_servers(configured_servers))
        except Exception:
            pass
        finally:
            with _refresh_lock:
                _refreshing["active"] = False

    threading.Thread(target=worker, daemon=True).start()


def get_servers_telemetry(configured_servers: list, force_refresh: bool = False) -> list:
    """Return server telemetry using a stale-while-revalidate cache.

    - fresh cache  -> return immediately
    - stale cache  -> return stale immediately, refresh in the background
    - cold / forced -> probe synchronously (the only blocking path)
    """
    cache_key = tuple((s.get("id"), s.get("api_url", "")) for s in configured_servers)

    with _server_cache_lock:
        cached = _server_cache["data"] if _server_cache["key"] == cache_key else None
        age = time.time() - _server_cache["ts"]

    if force_refresh or cached is None:
        servers = _probe_all_servers(configured_servers)
        _store_servers(cache_key, servers)
        return servers

    if age >= SERVER_TELEMETRY_TTL:
        # Serve the stale copy now; refresh for the next caller in the background.
        _refresh_in_background(configured_servers, cache_key)

    return cached


def reset_telemetry_cache() -> None:
    """Clear the cached server telemetry (used by tests / after settings changes)."""
    with _server_cache_lock:
        _server_cache["key"] = None
        _server_cache["data"] = None
        _server_cache["ts"] = 0.0
    with _refresh_lock:
        _refreshing["active"] = False


def _reward_velocity() -> tuple[int, int]:
    """Config-derived tuning signal for the reward table.

    Returns ``(expected_value_per_claim, est_days_to_starter)`` computed purely
    from the CURRENT dynamic Points settings — no user data — so it re-answers
    "how many days of daily claiming earn one free Starter under this preset?"
    the moment the owner switches Conservative/Balanced/Generous. ``0`` days
    means the table is empty/invalid (guarded so the overview never raises).
    """
    from bot_app.config import points_settings

    cfg = points_settings()
    table = cfg.get("reward_table") or []
    total_weight = sum(int(w) for _, _, w in table)
    if total_weight <= 0:
        return 0, 0
    ev = sum(((int(lo) + int(hi)) / 2) * int(w) for lo, hi, w in table) / total_weight

    cooldown_h = int(cfg.get("claim_cooldown_h", 4)) or 4
    claims_per_day = max(1, 24 // cooldown_h)
    per_day = ev * claims_per_day
    starter_cost = int(cfg.get("starter_cost", 5000))
    days = math.ceil(starter_cost / per_day) if per_day > 0 else 0
    return round(ev), days


def get_admin_overview_telemetry(force_refresh: bool = False) -> dict:
    """Aggregate live telemetry, KPIs, and revenue metrics."""
    now = myanmar_now()
    today_str = now.strftime("%Y-%m-%d")
    current_year = now.year
    current_month = now.month

    # 1. Server telemetries — the single configured-server source of truth
    #    (Settings/Supabase values, falling back to .env-configured servers).
    #    Probed concurrently and cached for SERVER_TELEMETRY_TTL seconds.
    from bot_app.services.outline import get_configured_servers
    configured_servers = get_configured_servers()

    servers = get_servers_telemetry(configured_servers, force_refresh=force_refresh)

    # 2-4. Storage KPI reads are independent — fetch them concurrently
    #      (each is 1-2 KV round-trips; sequential they add up to seconds).
    from bot_app.services.points import load_all_points

    with ThreadPoolExecutor(max_workers=5) as executor:
        f_sales = executor.submit(load_sales_history)
        f_keys = executor.submit(load_persistent_keys)
        f_users = executor.submit(load_all_users)
        f_slips = executor.submit(get_slips_list, "PENDING")
        f_points = executor.submit(load_all_points)
        sales_history = f_sales.result()
        persistent_keys = f_keys.result()
        all_users = f_users.result()
        pending_slips_list = f_slips.result()
        points_data = f_points.result()

    today_revenue = 0
    month_revenue = 0

    for item in sales_history:
        price = int(item.get("price", 0))
        item_year = item.get("year")
        item_month = item.get("month")

        if item.get("date") == today_str:
            today_revenue += price

        if item_year == current_year and item_month == current_month:
            month_revenue += price

    # 3. Keys and customers count
    active_keys_count = sum(s["total_keys"] for s in servers if s["is_active"])
    if not active_keys_count and persistent_keys:
        active_keys_count = len(persistent_keys)

    total_customers = len(all_users)

    # 4. Pending slips count
    pending_slips = len(pending_slips_list)

    # 5. Traffic trends (last 3 points or based on servers)
    total_gb = sum(s["total_transferred_gb"] for s in servers)
    traffic_trend = [
        {"timestamp": now.strftime("%Y-%m-%dT%H:00:00Z"), "used_gb": total_gb}
    ]

    # 6. Loyalty-points KPIs (single cheap dict scan) + reward-tuning velocity.
    #    Circulation/holders/redeemed come from live user records; the velocity
    #    block ("how fast does a daily-active user reach a free Starter") is
    #    derived from the CURRENT reward table so it recomputes the instant the
    #    owner switches Conservative/Balanced — the signal for tuning §8.
    points_circulation = 0
    points_holders = 0
    points_starters_redeemed = 0
    points_total_claims = 0
    points_active_claimers = 0
    active_cutoff = now - timedelta(hours=48)
    for rec in points_data.values():
        if not isinstance(rec, dict):
            continue
        pts = int(rec.get("points", 0) or 0)
        points_circulation += pts
        if pts > 0:
            points_holders += 1
        points_starters_redeemed += int(rec.get("redeemed_count", 0) or 0)
        points_total_claims += int(rec.get("lifetime_claims", 0) or 0)
        last_claim = rec.get("last_claim_at")
        if last_claim:
            try:
                if datetime.strptime(last_claim, "%Y-%m-%d %H:%M:%S") >= active_cutoff:
                    points_active_claimers += 1
            except (ValueError, TypeError):
                pass

    points_avg_balance = points_circulation // points_holders if points_holders else 0
    points_reward_ev, points_est_days_to_starter = _reward_velocity()

    return {
        "servers": servers,
        "metrics": {
            "total_active_keys": active_keys_count,
            "total_customers": total_customers,
            "pending_slips": pending_slips,
            "today_revenue_ks": today_revenue,
            "month_revenue_ks": month_revenue,
            "points_circulation": points_circulation,
            "points_holders": points_holders,
            "points_starters_redeemed": points_starters_redeemed,
            "points_total_claims": points_total_claims,
            "points_active_claimers": points_active_claimers,
            "points_avg_balance": points_avg_balance,
            "points_reward_ev": points_reward_ev,
            "points_est_days_to_starter": points_est_days_to_starter,
        },
        "traffic_trend": traffic_trend,
    }
