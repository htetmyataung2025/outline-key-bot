"""Tests for Customer TMA Actions (daily claim, slip upload, key replace, history, leaderboard)."""

import io
from bot_app.services.points import get_points
from bot_app.services.slips import load_all_slips
from bot_app.services.orders import save_user_purchase_record


def test_user_api_daily_claim_success_and_cooldown(client, make_telegram_init_data, isolated_state):
    user_id = 555666777
    init_data = make_telegram_init_data(user_id=user_id)

    # 1. First claim succeeds
    resp1 = client.post(
        "/api/user/claim-daily",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1["success"] is True
    assert data1["awarded"] > 0
    assert data1["new_balance"] == data1["awarded"]

    # 2. Second claim immediately fails due to cooldown
    resp2 = client.post(
        "/api/user/claim-daily",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp2.status_code == 400
    data2 = resp2.get_json()
    assert data2["success"] is False
    assert data2["error"] == "cooldown"


def test_user_api_topup_slip_upload(client, make_telegram_init_data, isolated_state, mock_bot):
    user_id = 555666888
    init_data = make_telegram_init_data(user_id=user_id, username="slip_uploader")

    # Reject if amount < 500
    resp_invalid = client.post(
        "/api/user/topup-slip",
        headers={"X-Telegram-Init-Data": init_data},
        data={"amount": "200"}
    )
    assert resp_invalid.status_code == 400

    # Valid upload with fake receipt image
    fake_img = (io.BytesIO(b"fake image bytes"), "receipt.jpg")
    resp_valid = client.post(
        "/api/user/topup-slip",
        headers={"X-Telegram-Init-Data": init_data},
        data={"amount": "5,000", "method": "kbz", "file": fake_img},
        content_type="multipart/form-data"
    )
    assert resp_valid.status_code == 200
    data = resp_valid.get_json()
    assert data["success"] is True
    assert data["status"] == "PENDING"
    assert data["amount"] == 5000

    # Check slip was recorded in storage
    slips = load_all_slips()
    assert data["slip_id"] in slips
    slip = slips[data["slip_id"]]
    assert slip["amount"] == 5000
    assert str(slip["chat_id"]) == str(user_id)
    assert slip["status"] == "PENDING"


def test_user_api_key_replace(client, make_telegram_init_data, isolated_state, mock_bot):
    user_id = 555666999
    init_data = make_telegram_init_data(user_id=user_id)

    # Key not found
    resp_404 = client.post(
        "/api/user/keys/non_existent_key/replace",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_404.status_code == 404

    # Seed active key
    save_user_purchase_record(
        chat_id=user_id,
        order_id="#ORD-REPL99",
        plan_name="VIP Plan",
        disp_gb="150 GB",
        months_count=1,
        price_str="5,000 Ks",
        server_num="1",
        expire_date="20.12.2026",
        vpn_key="ss://dummy-vpn-key-to-replace"
    )

    from urllib.parse import quote
    resp_valid = client.post(
        f"/api/user/keys/{quote('#ORD-REPL99', safe='')}/replace",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_valid.status_code == 200
    assert resp_valid.get_json()["success"] is True



def test_user_api_history_and_leaderboard(client, make_telegram_init_data, isolated_state):
    user_id = 555666000
    init_data = make_telegram_init_data(user_id=user_id)

    # History endpoint
    resp_hist = client.get(
        "/api/user/history",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_hist.status_code == 200
    hist_data = resp_hist.get_json()
    assert "purchases" in hist_data
    assert "slips" in hist_data

    # Leaderboard endpoint
    resp_lb = client.get(
        "/api/user/leaderboard",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_lb.status_code == 200
    lb_data = resp_lb.get_json()
    assert "rows" in lb_data
