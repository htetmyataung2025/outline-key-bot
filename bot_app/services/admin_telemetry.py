"""Admin Telemetry and KPI Metrics service."""

import time
import requests

from bot_app.timeutil import myanmar_now
from bot_app.config import OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3
from bot_app.services.orders import load_all_users, load_sales_history
from bot_app.services.registry import load_persistent_keys
from bot_app.services.slips import get_slips_list
from bot_app.utils import bytes_to_gb


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
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
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
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=4)
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


def get_admin_overview_telemetry() -> dict:
    """Aggregate live telemetry, KPIs, and revenue metrics."""
    now = myanmar_now()
    today_str = now.strftime("%Y-%m-%d")
    current_year = now.year
    current_month = now.month

    # 1. Server telemetries
    server_configs = [
        (1, "Server 1 (SG-1)", OUTLINE_API_URL_1),
        (2, "Server 2 (SG-2)", OUTLINE_API_URL_2),
        (3, "Server 3 (VIP)", OUTLINE_API_URL_3),
    ]

    servers = [
        get_server_metrics(srv_id, name, url)
        for srv_id, name, url in server_configs
    ]

    # 2. Sales and revenue calculation
    sales_history = load_sales_history()
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
    persistent_keys = load_persistent_keys()
    active_keys_count = sum(s["total_keys"] for s in servers if s["is_active"])
    if not active_keys_count and persistent_keys:
        active_keys_count = len(persistent_keys)

    all_users = load_all_users()
    total_customers = len(all_users)

    # 4. Pending slips count
    pending_slips = len(get_slips_list("PENDING"))

    # 5. Traffic trends (last 3 points or based on servers)
    total_gb = sum(s["total_transferred_gb"] for s in servers)
    traffic_trend = [
        {"timestamp": now.strftime("%Y-%m-%dT%H:00:00Z"), "used_gb": total_gb}
    ]

    return {
        "servers": servers,
        "metrics": {
            "total_active_keys": active_keys_count,
            "total_customers": total_customers,
            "pending_slips": pending_slips,
            "today_revenue_ks": today_revenue,
            "month_revenue_ks": month_revenue,
        },
        "traffic_trend": traffic_trend,
    }
