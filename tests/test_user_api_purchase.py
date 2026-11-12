"""Tests for Customer TMA 1-Click Purchase endpoint (POST /api/user/purchase)."""

from bot_app.services.billing import get_user_balance, update_user_balance
from bot_app.services.orders import get_user_combined_purchase_records


def test_user_api_purchase_insufficient_balance(client, make_telegram_init_data, isolated_state):
    user_id = 12345001
    init_data = make_telegram_init_data(user_id=user_id)

    # User balance is 0, trying to buy Basic (2,000 Ks)
    resp = client.post(
        "/api/user/purchase",
        headers={"X-Telegram-Init-Data": init_data},
        json={"plan_code": "basic", "server_id": "1"}
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"] == "insufficient_balance"


def test_user_api_purchase_invalid_plan(client, make_telegram_init_data, isolated_state):
    user_id = 12345002
    init_data = make_telegram_init_data(user_id=user_id)
    update_user_balance(user_id, 10000)

    resp = client.post(
        "/api/user/purchase",
        headers={"X-Telegram-Init-Data": init_data},
        json={"plan_code": "non_existent_plan_xyz", "server_id": "1"}
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid plan selected"


def test_user_api_purchase_success(client, make_telegram_init_data, isolated_state, monkeypatch):
    user_id = 12345003
    init_data = make_telegram_init_data(user_id=user_id, username="happy_customer")
    update_user_balance(user_id, 5000)

    # Mock Outline key creation
    def fake_create_key(*args, **kwargs):
        return ("ss://Y2hhY2hhMjA6bW9ja0tleUAxMjcuMC4wLjE6MTA4OQ==#User (12345003) 25.11.2026",
                "User (12345003) 25.11.2026",
                "25.11.2026")

    import bot_app.routes_user as ru
    monkeypatch.setattr(ru, "create_outline_key", fake_create_key)

    # Buy Starter Plan (1,000 Ks)
    resp = client.post(
        "/api/user/purchase",
        headers={"X-Telegram-Init-Data": init_data},
        json={"plan_code": "starter", "server_id": "1"}
    )
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["success"] is True
    assert data["order_id"].startswith("#")
    assert data["vpn_key"].startswith("ss://")
    assert data["new_balance"] == 4000  # 5000 - 1000 = 4000
    assert data["remaining_balance"] == 4000
    assert data["key_details"] is not None
    assert data["key_details"]["id"] == data["order_id"]
    assert data["key_details"]["plan"] == "Starter"

    # Verify wallet in service
    assert get_user_balance(user_id) == 4000

    # Verify purchase record was saved
    records = get_user_combined_purchase_records(user_id)
    assert len(records) == 1
    assert records[0]["order_id"] == data["order_id"]


def test_user_api_purchase_manual_plan(client, make_telegram_init_data, isolated_state, mock_bot):
    """5-Device Custom Plan (manual) requires admin delivery."""
    user_id = 12345005
    init_data = make_telegram_init_data(user_id=user_id, username="custom_customer")
    update_user_balance(user_id, 25000)

    resp = client.post(
        "/api/user/purchase",
        headers={"X-Telegram-Init-Data": init_data},
        json={"plan_code": "custom_1m", "server_id": "1"}
    )
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["success"] is True
    assert data["manual"] is True
    assert data["vpn_key"] == ""
    assert data["key_details"] is None
    assert data["remaining_balance"] == 5000  # 25000 - 20000 = 5000
    assert "စိတ်ကြိုက်သုံး 5 Device Plan" in data["message"]

    # Verify purchase record saved
    records = get_user_combined_purchase_records(user_id)
    assert len(records) == 1
    assert records[0]["order_id"] == data["order_id"]
    assert records[0]["vpn_key"] == "N/A"

    # Verify admin alert was sent
    admin_calls = [msg for chat_id, msg in mock_bot.calls["send_message"] if "5 Device Plan" in msg]
    assert len(admin_calls) >= 1


def test_user_api_purchase_with_redeem_bonus_forces_server_1(client, make_telegram_init_data, isolated_state, monkeypatch):
    """If user has bonus balance, server must be forced to Server 1."""
    from bot_app.services.billing import add_expiring_bonus_to_wallet
    user_id = 12345006
    init_data = make_telegram_init_data(user_id=user_id, username="bonus_user")
    add_expiring_bonus_to_wallet(user_id, 2000, 3)

    captured_server = []

    def fake_create_key(server_num, *args, **kwargs):
        captured_server.append(str(server_num))
        return ("ss://mockServer1Key#Bonus", "BonusKey", "25.11.2026")

    import bot_app.routes_user as ru
    monkeypatch.setattr(ru, "create_outline_key", fake_create_key)

    # User attempts to request server_id="2"
    resp = client.post(
        "/api/user/purchase",
        headers={"X-Telegram-Init-Data": init_data},
        json={"plan_code": "starter", "server_id": "2"}
    )
    assert resp.status_code == 200
    assert captured_server == ["1"]  # Forced to server 1!


def test_user_api_purchase_server_failure_refunds_balance(client, make_telegram_init_data, isolated_state, monkeypatch):
    user_id = 12345004
    init_data = make_telegram_init_data(user_id=user_id)
    update_user_balance(user_id, 5000)

    # Mock Outline key creation failure
    def fake_failing_key(*args, **kwargs):
        return (None, None, None)

    import bot_app.routes_user as ru
    monkeypatch.setattr(ru, "create_outline_key", fake_failing_key)

    resp = client.post(
        "/api/user/purchase",
        headers={"X-Telegram-Init-Data": init_data},
        json={"plan_code": "basic", "server_id": "1"}
    )
    assert resp.status_code == 502
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"] == "server_unavailable"

    # Crucial assertion: Balance was refunded back to 5000!
    assert get_user_balance(user_id) == 5000
