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
    assert key["go_url"].startswith("/go/")

    from bot_app.helpers.deeplink import verify_go_token
    assert verify_go_token(key["go_url"].removeprefix("/go/")) == ("1", "101")


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


def test_local_state_dir_overrides_paths_module(tmp_path, monkeypatch):
    """Setting LOCAL_STATE_DIR redirects all JSON state files away from /tmp."""
    import importlib
    from bot_app.storage import paths

    custom_dir = tmp_path / "sandbox_store"
    monkeypatch.setenv("LOCAL_STATE_DIR", str(custom_dir))
    reloaded = importlib.reload(paths)
    try:
        assert custom_dir.is_dir()
        assert reloaded.STATE_DIR == str(custom_dir)
        assert reloaded.WALLET_FILE == str(custom_dir / "user_wallets.json")
        assert reloaded.USER_HISTORY_FILE == str(custom_dir / "user_purchases.json")
        assert reloaded.PERSISTENT_KEYS_FILE == str(custom_dir / "persistent_keys.json")
    finally:
        monkeypatch.delenv("LOCAL_STATE_DIR", raising=False)
        importlib.reload(paths)


def test_user_api_bootstrap_all_five_payment_methods_and_ocr_suffix_dedup(
    client, make_telegram_init_data, isolated_state
):
    """Bootstrap exposes kbz/wave/aya/uab/cb and ignores OCR suffix duplicates like 9699970092."""
    from bot_app.services import settings as settings_svc

    settings_svc.invalidate_settings_cache(reset_fallback=True)
    settings_svc.save_system_settings(
        {"payment_phones": ["09699970092", "9699970092", "699970092"]},
        updated_by="Admin",
    )

    init_data = make_telegram_init_data(user_id=888333444, username="pay5_user")
    resp = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert resp.status_code == 200
    pm = resp.get_json()["payment_methods"]
    for key in ("kbz", "wave", "aya", "uab", "cb"):
        assert key in pm
        assert pm[key]["phone"] == "09699970092"
        assert pm[key]["account_name"] == "Htet Myat Aung"


def test_format_user_key_handles_ultimate_and_unlimited():
    """Ultimate VIP Plan must not be mislabeled VIP, and Unlimited Data must have quota 0."""
    from bot_app.routes_user import _format_user_key

    ult = _format_user_key({
        "order_id": "#ULT1",
        "plan_name": "Ultimate VIP Plan",
        "disp_gb": "500 GB",
        "server": "1",
        "expire_date": "25.12.2026",
        "vpn_key": "ss://test#ult",
    })
    assert ult["plan"] == "Ultimate"
    assert ult["quota"] == 500.0

    unlim = _format_user_key({
        "order_id": "#UNL1",
        "plan_name": "၁ လ စိတ်ကြိုက်သုံး (5 Device)",
        "disp_gb": "Unlimited Data",
        "server": "VIP",
        "expire_date": "25.12.2026",
        "vpn_key": "ss://test#unl",
    })
    assert unlim["quota"] == 0.0


def test_user_api_bootstrap_returns_exact_seven_default_plans(client, make_telegram_init_data, isolated_state):
    """Default Mini App plans must match the exact 7 production plans in order."""
    from bot_app.services.settings import invalidate_settings_cache

    invalidate_settings_cache(reset_fallback=True)
    init_data = make_telegram_init_data(user_id=888111223, username="plan_order_user")
    resp = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert resp.status_code == 200
    plans = resp.get_json()["plans"]
    assert [p["code"] for p in plans] == [
        "starter",
        "basic",
        "standard",
        "premium",
        "vip",
        "pro",
        "ultimate",
    ]
    assert [p["price"] for p in plans] == [1000, 2000, 3000, 4000, 5000, 7000, 10000]
    assert [p["quota"] for p in plans] == ["25 GB", "50 GB", "75 GB", "100 GB", "150 GB", "200 GB", "500 GB"]


def test_admin_settings_plan_updates_sync_to_miniapp_and_bot_keyboard(client, make_telegram_init_data, isolated_state):
    """Editing plans in Admin Settings must immediately update Mini App bootstrap and Telegram Bot keyboard."""
    from bot_app.config import default_plans
    from bot_app.keyboards import get_plan_keyboard
    from bot_app.services.settings import invalidate_settings_cache, save_system_settings

    init_data = make_telegram_init_data(user_id=888111224, username="sync_check_user")
    invalidate_settings_cache(reset_fallback=True)
    try:
        custom_plans = {
            **default_plans(),
            "starter": {
                **default_plans()["starter"],
                "price": 1500,
            },
            "flash": {
                "name": "Flash Deal",
                "price": 12000,
                "months": 2,
                "bytes": 600 * (1000**3),
                "data": "600 GB",
            },
        }
        del custom_plans["pro"]
        save_system_settings({"plans": custom_plans}, updated_by="Admin")

        resp = client.get(
            "/api/user/bootstrap?refresh=1",
            headers={"X-Telegram-Init-Data": init_data},
        )
        assert resp.status_code == 200
        plans = {p["code"]: p for p in resp.get_json()["plans"]}
        assert plans["starter"]["price"] == 1500
        assert "pro" not in plans
        assert plans["flash"]["quota"] == "600 GB"
        assert plans["flash"]["price"] == 12000

        kb = get_plan_keyboard()
        callback_data = [btn.callback_data for row in kb.keyboard for btn in row]
        texts = [btn.text for row in kb.keyboard for btn in row]
        assert "selectplan_starter" in callback_data
        assert "selectplan_pro" not in callback_data
        assert "selectplan_flash" in callback_data
        assert any("Starter (25 GB) - 1,500 Ks" in t for t in texts)
        assert any("Flash Deal (600 GB) - 12,000 Ks" in t for t in texts)
    finally:
        invalidate_settings_cache(reset_fallback=True)


def test_user_api_leaderboard_returns_up_to_fifty_rows_and_total_players(client, make_telegram_init_data, isolated_state):
    """Leaderboard API must return up to 50 ranked players plus total_players for modal browsing."""
    from bot_app.services.points import _leaderboard_epoch, current_week_start, save_all_points
    from bot_app.timeutil import myanmar_now

    now = myanmar_now()
    week_start = current_week_start(now, _leaderboard_epoch())
    all_pts = {}
    for i in range(1, 31):
        uid = str(990000 + i)
        all_pts[uid] = {
            "points": i * 10,
            "lifetime_earned": i * 10,
            "week_start": week_start,
            "week_earned": i * 10,
        }
    save_all_points(all_pts)

    caller_id = 990005  # rank 26 out of 30
    init_data = make_telegram_init_data(user_id=caller_id, username="mid_rank_user")
    resp = client.get(
        "/api/user/leaderboard",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total_players"] == 30
    assert len(body["rows"]) == 30
    assert body["rows"][0]["rank"] == 1
    assert body["rows"][0]["points"] == 300
    you_rows = [r for r in body["rows"] if r["is_you"]]
    assert len(you_rows) == 1
    assert you_rows[0]["rank"] == 26





