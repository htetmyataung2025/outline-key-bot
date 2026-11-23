"""Tests for the unified server label format (owner's format, 2026-11-24).

Every customer/admin surface must show a server as its Settings name
plus the correct country flag — "SG-1 🇸🇬", "JP 🇯🇵", "US 🇺🇸" —
never a hard-coded "Server N 🇸🇬" / "Singapore Server N" that would
mislabel the Japan and US servers added on 2026-11-23.
"""

from types import SimpleNamespace

from bot_app.handlers import shop
from bot_app.services import outline

_PROD_SERVERS = [
    {"id": 1, "name": "SG-1", "api_url": "https://sg1.example.com/api"},
    {"id": 2, "name": "SG-2", "api_url": "https://sg2.example.com/api"},
    {"id": 3, "name": "JP", "api_url": "https://jp.example.com/api"},
    {"id": 4, "name": "US", "api_url": "https://us.example.com/api"},
]


def _settings_stub(monkeypatch, servers):
    from bot_app.services import settings as settings_svc

    monkeypatch.setattr(
        settings_svc, "get_system_settings",
        lambda force_refresh=False: {"servers": servers},
    )


def test_server_label_matches_owner_format(monkeypatch):
    _settings_stub(monkeypatch, _PROD_SERVERS)
    assert outline.get_server_label("1") == "SG-1 🇸🇬"
    assert outline.get_server_label("2") == "SG-2 🇸🇬"
    assert outline.get_server_label("3") == "JP 🇯🇵"
    assert outline.get_server_label("4") == "US 🇺🇸"


def test_server_label_unknown_id_has_no_flag(monkeypatch):
    _settings_stub(monkeypatch, _PROD_SERVERS)
    assert outline.server_flag("9") == ""
    assert outline.get_server_label("9") == "Server 9"


def test_clean_label_strips_all_flags(monkeypatch):
    # A flag typed into the Settings name must not double up in labels.
    assert outline.clean_server_label("JP 🇯🇵") == "JP"
    assert outline.clean_server_label("US 🇺🇸") == "US"
    _settings_stub(monkeypatch, [
        {"id": 3, "name": "JP 🇯🇵", "api_url": "https://jp.example.com/api"},
    ])
    assert outline.get_server_label("3") == "JP 🇯🇵"


def _call(data, chat_id=720000999, message_id=555):
    return SimpleNamespace(
        id="cb1", data=data,
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=message_id),
    )


def test_shop_picker_buttons_carry_flags(monkeypatch, mock_bot, isolated_state):
    _settings_stub(monkeypatch, _PROD_SERVERS)
    monkeypatch.setattr(shop, "is_user_subscribed", lambda cid: True)
    monkeypatch.setattr(shop, "get_user_balance", lambda cid: 100000)
    monkeypatch.setattr(shop, "get_user_balance_breakdown", lambda cid: (100000, 0, 0))

    shop.handle_select_plan(_call("selectplan_starter"))

    args, kwargs = mock_bot.calls["edit_message_text"][-1]
    markup = kwargs["reply_markup"]
    texts = [btn.text for row in markup.keyboard for btn in row]
    assert any("SG-1 🇸🇬" in t and "ဖြင့် ဝယ်မည်" in t for t in texts)
    assert any("SG-2 🇸🇬" in t and "ဖြင့် ဝယ်မည်" in t for t in texts)
    assert any("JP 🇯🇵" in t and "ဖြင့် ဝယ်မည်" in t for t in texts)
    assert any("US 🇺🇸" in t and "ဖြင့် ဝယ်မည်" in t for t in texts)
    # No button may carry the wrong (Singapore) flag for JP / US.
    assert not any("JP 🇸🇬" in t or "US 🇸🇬" in t for t in texts)
