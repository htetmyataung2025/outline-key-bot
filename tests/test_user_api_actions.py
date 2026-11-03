"""Tests for Customer TMA Actions (daily claim, slip upload, key replace, history, leaderboard)."""

import io
from bot_app.services.slips import load_all_slips, record_slip
from bot_app.services.orders import save_user_purchase_record


from bot_app import config
from bot_app.services import settings as settings_svc


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
    assert data1["cooldown_hours"] == 4
    assert "Points ရရှိပါသည်" in data1["message"]

    # 2. Second claim immediately fails due to cooldown
    resp2 = client.post(
        "/api/user/claim",  # Test /claim alias
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp2.status_code == 400
    data2 = resp2.get_json()
    assert data2["success"] is False
    assert data2["error"] == "cooldown"
    assert data2["next_in_s"] > 0
    assert data2["cooldown_hours"] == 4
    assert "နောက် Claim ရရှိရန်" in data2["message"]
    assert "နာရီ" in data2["message"] or "မိနစ်" in data2["message"]


def test_user_api_claim_dynamic_admin_cooldown_adjustment(client, make_telegram_init_data, isolated_state):
    """Admin increases or decreases claim_cooldown_h and it applies immediately."""
    settings_svc.invalidate_settings_cache(reset_fallback=True)

    # Admin sets cooldown to 2 hours
    pts_block = config.default_points_settings()
    pts_block["claim_cooldown_h"] = 2
    settings_svc.save_system_settings({"points": pts_block}, updated_by="Admin")

    user_id = 555666779
    init_data = make_telegram_init_data(user_id=user_id)

    # 1. Bootstrap shows 2 hours cooldown
    resp_boot = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_boot.status_code == 200
    boot_data = resp_boot.get_json()
    assert boot_data["wallet"]["cooldown_hours"] == 2
    assert boot_data["wallet"]["can_claim"] is True

    # 2. Claim succeeds with 2 hours next cooldown
    resp_claim = client.post(
        "/api/user/claim",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_claim.status_code == 200
    claim_data = resp_claim.get_json()
    assert claim_data["cooldown_hours"] == 2
    assert claim_data["next_in_s"] == 2 * 3600
    assert "2 နာရီ" in claim_data["message"]

    # 3. Admin increases cooldown to 6 hours
    pts_block["claim_cooldown_h"] = 6
    settings_svc.invalidate_settings_cache(reset_fallback=True)
    settings_svc.save_system_settings({"points": pts_block}, updated_by="Admin")

    # Immediate next check reflects 6 hours (remaining = 6h - elapsed)
    resp_cooldown = client.post(
        "/api/user/claim",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_cooldown.status_code == 400
    cooldown_data = resp_cooldown.get_json()
    assert cooldown_data["cooldown_hours"] == 6
    assert cooldown_data["next_in_s"] > 5 * 3600  # around ~6 hours remaining
    assert "နောက် Claim ရရှိရန်" in cooldown_data["message"]


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
    assert len(slip["admin_messages"]) > 0
    assert slip["file_id"] != ""

    # Verify Telegram notification was sent with photo and inline approve/reject buttons
    assert len(mock_bot.calls["send_photo"]) > 0
    reply_markup = mock_bot.last_send_photo_kwargs.get("reply_markup")
    assert reply_markup is not None
    # Verify buttons contain approve_topup and reject_topup
    button_callbacks = [b.callback_data for row in reply_markup.keyboard for b in row]
    assert any(cb.startswith(f"approve_topup_{user_id}_5000_{data['slip_id']}") for cb in button_callbacks)
    assert any(cb == f"reject_topup_{data['slip_id']}" for cb in button_callbacks)

    # Test Telegram-side Approve: Admin taps the Approve inline button
    from bot_app.handlers.topup import handle_approve_topup
    from types import SimpleNamespace
    admin_id = 111000111
    call = SimpleNamespace(
        id="cb-approve-test",
        data=f"approve_topup_{user_id}_5000_{data['slip_id']}",
        from_user=SimpleNamespace(id=admin_id, first_name="Admin"),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=admin_id),
            message_id=900001,
            caption="Test Caption"
        ),
    )
    handle_approve_topup(call)

    # Assert slip is now APPROVED in storage
    updated_slips = load_all_slips()
    assert updated_slips[data["slip_id"]]["status"] == "APPROVED"


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
    init_data = make_telegram_init_data(user_id=user_id, username="test_customer")

    # 1. Initial Empty State
    resp_hist = client.get(
        "/api/user/history",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_hist.status_code == 200
    hist_data = resp_hist.get_json()
    assert hist_data["purchases"] == []
    assert hist_data["slips"] == []

    # 2. Add real purchase record & slip
    save_user_purchase_record(
        chat_id=user_id,
        order_id="#ORD-HIST01",
        plan_name="VIP Plan",
        disp_gb="150 GB",
        months_count=1,
        price_str="5,000 Ks",
        server_num="1",
        expire_date="20.12.2026",
        vpn_key="ss://live-key-history"
    )
    record_slip(
        slip_id="SLP-998877",
        chat_id=user_id,
        amount=5000,
        username="TestCustomer",
        method="WAVE"
    )

    resp_hist2 = client.get(
        "/api/user/history",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_hist2.status_code == 200
    hist_data2 = resp_hist2.get_json()
    assert len(hist_data2["purchases"]) == 1
    p = hist_data2["purchases"][0]
    assert p["order_id"] == "#ORD-HIST01"
    assert p["plan_name"] == "VIP Plan"
    assert p["disp_gb"] == "150 GB"
    assert p["price"] == "5,000 Ks"
    assert p["status"] == "Active"
    assert "date" in p

    assert len(hist_data2["slips"]) == 1
    s = hist_data2["slips"][0]
    assert s["slip_id"] == "SLP-998877"
    assert s["amount"] == 5000
    assert s["method"] == "WAVE"
    assert s["status"] == "PENDING"
    assert "submitted_at" in s

    # 3. Leaderboard endpoint
    from bot_app.services.points import credit_points
    credit_points(user_id, 150, "test")

    resp_lb = client.get(
        "/api/user/leaderboard",
        headers={"X-Telegram-Init-Data": init_data}
    )
    assert resp_lb.status_code == 200
    lb_data = resp_lb.get_json()
    assert "rows" in lb_data
    assert len(lb_data["rows"]) >= 1
    top_user = lb_data["rows"][0]
    assert "rank" in top_user
    assert "name" in top_user
    assert "points" in top_user
    assert "is_you" in top_user
    assert top_user["points"] >= 150
    assert top_user["is_you"] is True

