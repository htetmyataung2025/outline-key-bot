"""Regression tests: user-facing server lists must follow the Settings store.

Before this fix the plan-purchase flow rendered a hard-coded
Server 1 / Server 2 / Server 3 button row, so a server deleted in the
dashboard (Settings → Outline Servers) kept appearing in the bot, and the
monthly revenue report always printed the same three server rows.

Network-free: ``mock_bot`` stubs Telegram, billing/Outline lookups are
monkeypatched, ``isolated_state`` sandboxes file state.
"""

from types import SimpleNamespace

from bot_app.handlers import shop
from bot_app.services import outline, reports
from bot_app.timeutil import myanmar_now

UID = 720000999  # not an admin


_TWO_SERVERS = [
    {"id": 1, "name": "Server 1 (SG-1)", "api_url": "https://sg1.example.com/api"},
    {"id": 2, "name": "Server 2 (SG-2)", "api_url": "https://sg2.example.com/api"},
]

_FOUR_SERVERS = _TWO_SERVERS + [
    {"id": 3, "name": "Server 3 (VIP)", "api_url": "https://vip.example.com/api"},
    {"id": 4, "name": "Server 4 (IN)", "api_url": "https://in.example.com/api"},
]


def _settings_stub(monkeypatch, servers):
    from bot_app.services import settings as settings_svc

    monkeypatch.setattr(
        settings_svc, "get_system_settings",
        lambda force_refresh=False: {"servers": servers},
    )


def _call(data, chat_id=UID, message_id=555):
    return SimpleNamespace(
        id="cb1", data=data,
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=message_id),
    )


def _last_edit_markup(mock_bot):
    assert mock_bot.calls["edit_message_text"], "expected an edited plan panel"
    args, kwargs = mock_bot.calls["edit_message_text"][-1]
    return kwargs["reply_markup"]


def _callback_datas(markup):
    return [btn.callback_data for row in markup.keyboard for btn in row]


# ---------------------------------------------------------------------------
# get_server_display_name
# ---------------------------------------------------------------------------

def test_display_name_uses_settings_name(monkeypatch):
    _settings_stub(monkeypatch, _TWO_SERVERS)
    assert outline.get_server_display_name("2") == "Server 2 (SG-2)"
    assert outline.get_server_display_name(1) == "Server 1 (SG-1)"


def test_display_name_unknown_id_falls_back(monkeypatch):
    _settings_stub(monkeypatch, _TWO_SERVERS)
    assert outline.get_server_display_name("9") == "Server 9"


def test_display_name_strips_decoration_emojis(monkeypatch):
    servers = [{"id": 3, "name": "📡 Server 3 🇸🇬 ⚡", "api_url": "https://x.example.com"}]
    _settings_stub(monkeypatch, servers)
    assert outline.get_server_display_name("3") == "Server 3"


# ---------------------------------------------------------------------------
# shop plan-purchase buttons
# ---------------------------------------------------------------------------

def test_plan_buttons_follow_settings_no_ghost_server3(monkeypatch, mock_bot, isolated_state):
    """Settings has only Server 1 + 2 → exactly two buy buttons, no Server 3."""
    _settings_stub(monkeypatch, _TWO_SERVERS)
    monkeypatch.setattr(shop, "is_user_subscribed", lambda cid: True)
    monkeypatch.setattr(shop, "get_user_balance", lambda cid: 100000)
    monkeypatch.setattr(shop, "get_user_balance_breakdown", lambda cid: (100000, 0, 0))

    shop.handle_select_plan(_call("selectplan_starter"))

    datas = _callback_datas(_last_edit_markup(mock_bot))
    assert "buywallet_starter_1" in datas
    assert "buywallet_starter_2" in datas
    assert not any(d.startswith("buywallet_starter_3") for d in datas)


def test_plan_buttons_include_added_server4(monkeypatch, mock_bot, isolated_state):
    _settings_stub(monkeypatch, _FOUR_SERVERS)
    monkeypatch.setattr(shop, "is_user_subscribed", lambda cid: True)
    monkeypatch.setattr(shop, "get_user_balance", lambda cid: 100000)
    monkeypatch.setattr(shop, "get_user_balance_breakdown", lambda cid: (100000, 0, 0))

    shop.handle_select_plan(_call("selectplan_starter"))

    datas = _callback_datas(_last_edit_markup(mock_bot))
    for sid in ("1", "2", "3", "4"):
        assert f"buywallet_starter_{sid}" in datas


def test_plan_buttons_use_settings_names(monkeypatch, mock_bot, isolated_state):
    _settings_stub(monkeypatch, _TWO_SERVERS)
    monkeypatch.setattr(shop, "is_user_subscribed", lambda cid: True)
    monkeypatch.setattr(shop, "get_user_balance", lambda cid: 100000)
    monkeypatch.setattr(shop, "get_user_balance_breakdown", lambda cid: (100000, 0, 0))

    shop.handle_select_plan(_call("selectplan_starter"))

    markup = _last_edit_markup(mock_bot)
    texts = [btn.text for row in markup.keyboard for btn in row]
    assert any("Server 1 (SG-1)" in t and "ဝယ်မည်" in t for t in texts)


def test_ultimate_stays_on_server1(monkeypatch, mock_bot, isolated_state):
    """Business rule: Ultimate VIP (and redeem-credit) keys are minted on
    Server 1 only — that binding is intentional and must survive the
    dynamic-button change."""
    _settings_stub(monkeypatch, _FOUR_SERVERS)
    monkeypatch.setattr(shop, "is_user_subscribed", lambda cid: True)
    monkeypatch.setattr(shop, "get_user_balance", lambda cid: 100000)
    monkeypatch.setattr(shop, "get_user_balance_breakdown", lambda cid: (100000, 0, 0))
    monkeypatch.setattr(shop, "get_user_ultimate_keys", lambda cid, srv: [])

    shop.handle_select_plan(_call("selectplan_ultimate"))

    datas = _callback_datas(_last_edit_markup(mock_bot))
    assert "buywallet_ultimate_1" in datas
    assert not any(d.startswith("buywallet_ultimate_2") for d in datas)


# ---------------------------------------------------------------------------
# monthly revenue report
# ---------------------------------------------------------------------------

def _sales_entry(server, price, months=1, today=True):
    now = myanmar_now()
    return {
        "year": now.year, "month": now.month,
        "date": now.strftime("%Y-%m-%d") if today else "01.01.2000",
        "server": server, "price": price,
        "plan_name": "Starter Plan", "months": months,
    }


def test_revenue_report_rows_follow_settings(monkeypatch, isolated_state):
    """Server 3 removed from Settings → no hard-coded S3 row; its legacy sales
    still surface once via the history fallback; VIP row intact."""
    _settings_stub(monkeypatch, _TWO_SERVERS)
    monkeypatch.setattr(reports, "load_sales_history", lambda: [
        _sales_entry("1", 1000),
        _sales_entry("2", 2000),
        _sales_entry("3", 500),    # sold before the server was removed
        _sales_entry("VIP", 700),
    ])

    text = reports.get_monthly_revenue_report()

    assert "Server 1 (SG-1)" in text and "1,000 Ks" in text
    assert "Server 2 (SG-2)" in text and "2,000 Ks" in text
    assert "Server 3" in text and "500 Ks" in text      # historical, not phantom
    assert "VIP (စိတ်ကြိုက်သုံး)" in text and "700 Ks" in text
    assert "4,200 MMK" in text


def test_revenue_report_server4_no_longer_lumped_into_vip(monkeypatch, isolated_state):
    """Sales recorded on Settings-added Server 4 get their own row (the old
    hard-coded report folded every id > 3 into VIP)."""
    _settings_stub(monkeypatch, _FOUR_SERVERS)
    monkeypatch.setattr(reports, "load_sales_history", lambda: [
        _sales_entry("4", 3000),
        _sales_entry("VIP", 700),
    ])

    text = reports.get_monthly_revenue_report()

    assert "Server 4 (IN)" in text and "3,000 Ks" in text
    assert "700 Ks" in text
    assert "3,700 MMK" in text
