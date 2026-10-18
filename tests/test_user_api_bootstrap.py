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


def test_user_api_bootstrap_existing_user_with_keys(client, make_telegram_init_data, isolated_state):
    user_id = 999333444
    init_data = make_telegram_init_data(user_id=user_id, username="active_user")

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
    assert len(data["keys"]) == 1

    key = data["keys"][0]
    assert key["id"] == "#ORD-VIP123"
    assert key["quota"] == 150.0
    assert "Server 1" in key["server"]
    assert key["status"] in ("active", "expiring")
    assert key["connected"] is True
    assert key["key"].startswith("ss://")
