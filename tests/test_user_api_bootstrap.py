"""Tests for Customer TMA Bootstrap endpoint (GET /api/user/bootstrap)."""

from bot_app.services.billing import update_user_balance
from bot_app.services.orders import save_user_purchase_record


def test_user_api_bootstrap_new_user(client, make_telegram_init_data, isolated_state):
    init_data = make_telegram_init_data(user_id=888111222, username="newbie_user")

    resp = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp.status_code == 200
    data = resp.get_json()

    # User identity
    assert data["user"]["id"] == "888111222"
    assert data["user"]["username"] == "newbie_user"
    assert data["user"]["initials"] is not None

    # Wallet
    assert data["wallet"]["balance"] == 0
    assert data["wallet"]["points"] == 0
    assert data["wallet"]["claimed_today"] is False

    # Keys, Plans, Servers, Payment Methods
    assert isinstance(data["keys"], list)
    assert len(data["keys"]) == 0
    assert len(data["plans"]) >= 3
    assert len(data["servers"]) >= 1
    assert "kbz" in data["payment_methods"]
    assert "wave" in data["payment_methods"]


def test_user_api_bootstrap_existing_user_with_keys(client, make_telegram_init_data, isolated_state, monkeypatch):
    user_id = 999333444
    init_data = make_telegram_init_data(user_id=user_id, username="active_user")

    # Mock Outline usage metrics to ensure hermetic testing with zero network calls
    monkeypatch.setattr(
        "bot_app.routes_user.get_usage_by_server",
        lambda servers: {"1": {"k1": 14.5 * 1000**3}}
    )

    # Seed balance
    update_user_balance(user_id, 7500)

    # Seed purchase record
    save_user_purchase_record(
        chat_id=user_id,
        order_id="#ORD-VIP123",
        plan_name="VIP Plan",
        disp_gb="150 GB",
        months_count=1,
        price_str="5,000 Ks",
        server_num="1",
        expire_date="25.11.2026",
        vpn_key="ss://Y2hhY2hhMjA6ZHVtbXlLZXlAMTI3LjAuMC4xOjEwODk=#TestKey"
    )

    resp = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["wallet"]["balance"] == 7500
    assert "starter_cost" in data["wallet"]
    assert "has_topped_up" in data["wallet"]
    assert "can_redeem_points" in data["wallet"]
    assert len(data["keys"]) == 1

    key = data["keys"][0]
    assert key["id"] == "#ORD-VIP123"
    assert key["quota"] == 150.0
    assert "Server 1" in key["server"]
    assert key["status"] in ("active", "expiring")
    assert key["connected"] is True
    assert key["key"].startswith("ss://")


def test_user_api_bootstrap_keys_from_persistent_registry_and_usage(client, make_telegram_init_data, isolated_state, monkeypatch):
    """Ensure existing customers whose keys were restored into persistent_keys_registry
    (without an active order in sales_history) still see their keys and live usage in TMA."""
    user_id = 777888111
    init_data = make_telegram_init_data(user_id=user_id, username="old_outline_user")

    from bot_app.services.registry import save_persistent_key
    save_persistent_key(
        server_num="1",
        key_id="101",
        name="Old User (777888111) 25.12.2026",
        access_url="ss://cmVzdG9yZWRfa2V5QDEyNy4wLjAuMToxMDgw#OldKey",
        limit_bytes=50 * 1000**3,
        order_id="k_101",
        chat_id=user_id,
    )

    # Mock Outline server metrics: 12.3 GB used
    monkeypatch.setattr(
        "bot_app.routes_user.get_usage_by_server",
        lambda servers: {"1": {"101": 12.3 * 1000**3}}
    )

    resp = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp.status_code == 200
    data = resp.get_json()

    assert len(data["keys"]) == 1
    key = data["keys"][0]
    assert key["id"] == "k_101"
    assert key["plan"] == "Basic"
    assert key["quota"] == 50.0
    assert key["used"] == 12.3
    assert key["server"] == "Server 1"
    assert key["key"].startswith("ss://")


def test_user_api_local_sandbox_mode_offline(client, make_telegram_init_data, isolated_state, monkeypatch):
    """Verify LOCAL_SANDBOX=1 works completely offline without remote DB or Outline servers."""
    monkeypatch.setenv("LOCAL_SANDBOX", "1")
    user_id = 777000999
    init_data = make_telegram_init_data(user_id=user_id, username="sandbox_user")

    update_user_balance(user_id, 10000)

    # 1. Purchase a plan in LOCAL_SANDBOX mode without mocking Outline API
    resp_buy = client.post(
        "/api/user/purchase",
        headers={"X-Telegram-Init-Data": init_data},
        json={"plan_code": "basic", "server_id": "1"},
    )
    assert resp_buy.status_code == 200
    buy_data = resp_buy.get_json()
    assert buy_data["success"] is True
    assert buy_data["vpn_key"].startswith("ss://")
    assert buy_data["remaining_balance"] == 8000

    # 2. Bootstrap in LOCAL_SANDBOX mode returns sandbox servers & newly minted key
    resp_boot = client.get(
        "/api/user/bootstrap?refresh=1",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert resp_boot.status_code == 200
    boot_data = resp_boot.get_json()
    assert boot_data["wallet"]["balance"] == 8000
    assert len(boot_data["servers"]) == 2
    assert len(boot_data["keys"]) == 1
    assert boot_data["keys"][0]["key"].startswith("ss://")


def test_user_api_bootstrap_dynamic_payment_phones(client, make_telegram_init_data, isolated_state):
    """Verify Admin Settings payment_phones dynamically sync into Mini App bootstrap."""
    from bot_app.services import settings as settings_svc

    settings_svc.invalidate_settings_cache(reset_fallback=True)
    settings_svc.save_system_settings(
        {"payment_phones": ["09777111222", "09999333444"]},
        updated_by="Admin",
    )

    init_data = make_telegram_init_data(user_id=888222333, username="phone_sync_user")
    resp = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["payment_methods"]["kbz"]["phone"] == "09777111222"
    assert data["payment_methods"]["wave"]["phone"] == "09999333444"


def test_user_api_bootstrap_server_locations_follow_settings_not_hardcoded_ids(
    client, make_telegram_init_data, isolated_state, monkeypatch
):
    """Server 2/4 must derive location/country from real Settings server names, not hardcoded IDs."""
    from bot_app.services import settings as settings_svc

    settings_svc.invalidate_settings_cache(reset_fallback=True)
    settings_svc.save_system_settings(
        {
            "servers": [
                {"id": 2, "name": "Server 2 (SG-2)", "api_url": "https://s2.example.com/key"},
                {"id": 4, "name": "Server 4 (Tokyo)", "api_url": "https://s4.example.com/key"},
            ]
        },
        updated_by="Admin",
    )

    monkeypatch.setattr("bot_app.routes_user.get_usage_by_server", lambda servers: {})

    user_id = 888444555
    save_user_purchase_record(
        chat_id=user_id,
        order_id="#ORD-SG2",
        plan_name="Basic Plan",
        disp_gb="50 GB",
        months_count=1,
        price_str="2,000 Ks",
        server_num="2",
        expire_date="25.12.2026",
        vpn_key="ss://Y2hhY2hhMjA6c2cyQDEyNy4wLjAuMToxMDgw#SG2",
    )
    save_user_purchase_record(
        chat_id=user_id,
        order_id="#ORD-JP4",
        plan_name="VIP Plan",
        disp_gb="150 GB",
        months_count=1,
        price_str="5,000 Ks",
        server_num="4",
        expire_date="25.12.2026",
        vpn_key="ss://Y2hhY2hhMjA6anA0QDEyNy4wLjAuMToxMDgw#JP4",
    )

    init_data = make_telegram_init_data(user_id=user_id, username="real_srv_user")
    resp = client.get("/api/user/bootstrap", headers={"X-Telegram-Init-Data": init_data})
    assert resp.status_code == 200
    data = resp.get_json()

    servers_by_id = {s["id"]: s for s in data["servers"]}
    assert servers_by_id["2"]["name"] == "Server 2 (SG-2)"
    assert servers_by_id["2"]["location"] == "Singapore"
    assert servers_by_id["2"]["country"] == "SG"
    assert servers_by_id["2"]["flag"] == "🇸🇬"

    assert servers_by_id["4"]["name"] == "Server 4 (Tokyo)"
    assert servers_by_id["4"]["location"] == "Tokyo"
    assert servers_by_id["4"]["country"] == "JP"
    assert servers_by_id["4"]["flag"] == "🇯🇵"

    keys_by_id = {k["id"]: k for k in data["keys"]}
    assert keys_by_id["#ORD-SG2"]["server"] == "Server 2"
    assert keys_by_id["#ORD-SG2"]["location"] == "Singapore"
    assert keys_by_id["#ORD-SG2"]["country"] == "SG"

    assert keys_by_id["#ORD-JP4"]["server"] == "Server 4"
    assert keys_by_id["#ORD-JP4"]["location"] == "Tokyo"
    assert keys_by_id["#ORD-JP4"]["country"] == "JP"



