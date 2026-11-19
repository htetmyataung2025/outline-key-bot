"""Tests for Bot Update #10a: native-app purchases (POST /api/app/buy)
must send the admins the same Telegram sale alert the bot and Mini App
channels already send."""

import bot_app.routes_app as ra
from bot_app.services.billing import update_user_balance

ADMIN_IDS = {"111000111", "222000222"}


def _fake_create_key(*args, **kwargs):
    return (
        "ss://Y2hhY2hhMjA6bW9ja0tleUAxMjcuMC4wLjE6MTA4OQ==#User 25.11.2026",
        "User 25.11.2026",
        "25.11.2026",
    )


def _admin_texts(mock_bot):
    return [text for chat_id, text in mock_bot.calls["send_message"]
            if str(chat_id) in ADMIN_IDS]


def test_app_buy_sends_admin_sale_alert(client, isolated_state, mock_bot, monkeypatch):
    user_id = 555000111
    update_user_balance(user_id, 5000)
    monkeypatch.setattr(ra, "create_outline_key", _fake_create_key)

    token = ra._make_app_token(user_id)
    resp = client.post(
        "/api/app/buy",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_code": "starter", "server": "1",
              "idempotency_key": "alert-test-1"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"

    # The customer still receives the key by Telegram DM.
    customer_texts = [text for chat_id, text in mock_bot.calls["send_message"]
                      if str(chat_id) == str(user_id)]
    assert any("ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ" in t for t in customer_texts)

    # Every admin receives the sale alert naming the app channel.
    alerts = _admin_texts(mock_bot)
    assert len(alerts) == 2
    for text in alerts:
        assert "H&E VPN App မှ ကီးဝယ်ယူမှု" in text
        assert data["order_id"] in text
        assert "Starter" in text
        assert "1,000 MMK" in text


def test_app_buy_failed_purchase_sends_no_admin_alert(client, isolated_state,
                                                      mock_bot, monkeypatch):
    user_id = 555000222  # balance 0 -> purchase is rejected
    monkeypatch.setattr(ra, "create_outline_key", _fake_create_key)

    token = ra._make_app_token(user_id)
    resp = client.post(
        "/api/app/buy",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_code": "starter", "server": "1",
              "idempotency_key": "alert-test-2"},
    )
    assert resp.status_code == 402
    assert _admin_texts(mock_bot) == []
