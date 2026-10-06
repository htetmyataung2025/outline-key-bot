"""Force-join gate: who is considered subscribed? (Bot API mocked)."""

from types import SimpleNamespace

from bot_app.utils import is_user_subscribed

USER = 123456789


def _admin_id():
    from bot_app.config import ADMIN_CHAT_IDS
    assert ADMIN_CHAT_IDS, "tests set ADMIN_CHAT_IDS via env; see conftest"
    return ADMIN_CHAT_IDS[0]


def test_admin_bypasses_check_without_api_call(mock_bot):
    assert is_user_subscribed(_admin_id()) is True
    assert mock_bot.calls["get_chat_member"] == []


def test_member_statuses_pass(mock_bot):
    for status in ("creator", "administrator", "member", "restricted"):
        mock_bot.member_status = status
        assert is_user_subscribed(USER) is True


def test_left_and_kicked_fail(mock_bot):
    for status in ("left", "kicked"):
        mock_bot.member_status = status
        assert is_user_subscribed(USER) is False


def test_api_error_fails_open(mock_bot):
    mock_bot.member_error = Exception("bot is not a member")
    assert is_user_subscribed(USER) is True


def test_empty_channel_disables_check_without_api_call(mock_bot, monkeypatch):
    """``REQUIRED_CHANNEL`` empty/None = force-join off (local dev bots):
    every user passes and the Telegram API is never touched."""
    import bot_app.config as config

    monkeypatch.setattr(config, "REQUIRED_CHANNEL", None)
    assert is_user_subscribed(USER) is True
    assert mock_bot.calls["get_chat_member"] == []


def test_blank_channel_env_disables_check(monkeypatch):
    """``REQUIRED_CHANNEL=`` (set-but-empty in .env) must parse to None, not
    an empty string — an empty chat id made get_chat_member fail with
    'Bad Request: chat_id is empty' on every message."""
    import importlib
    import os

    import bot_app.config as config

    original = os.environ.get("REQUIRED_CHANNEL")
    try:
        monkeypatch.setenv("REQUIRED_CHANNEL", "   ")
        importlib.reload(config)
        assert config.REQUIRED_CHANNEL is None
    finally:
        if original is None:
            monkeypatch.delenv("REQUIRED_CHANNEL", raising=False)
        else:
            monkeypatch.setenv("REQUIRED_CHANNEL", original)
        importlib.reload(config)


# ── Mini App entry points (zero-click admin auth) ──────────────────────────

def _start_message(chat_id):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=chat_id, first_name="Test", last_name="", username="tester"),
    )


def _last_menu_button(mock_bot):
    assert mock_bot.calls["menu_button"], "set_chat_menu_button was never called"
    args, _kwargs = mock_bot.calls["menu_button"][-1]
    return args[0], args[1]


def test_start_sets_dashboard_menu_button_for_admins(mock_bot, isolated_state):
    from bot_app.config import DASHBOARD_URL
    from bot_app.handlers import gate

    gate.send_welcome(_start_message(_admin_id()))

    chat_id, button = _last_menu_button(mock_bot)
    assert str(chat_id) == str(_admin_id())
    assert button.web_app.url == DASHBOARD_URL
    assert button.text == "🎛 Control"


def test_start_sets_default_menu_button_for_customers(mock_bot, isolated_state):
    """The public landing page is gone — customers must get Telegram's
    default menu button so the dead 'Main Website' pill is cleared."""
    from telebot.types import MenuButtonDefault

    from bot_app.handlers import gate

    gate.send_welcome(_start_message(USER))

    _chat_id, button = _last_menu_button(mock_bot)
    assert isinstance(button, MenuButtonDefault)
    assert button.type == "default"


def test_admin_main_menu_has_no_web_app_row():
    """The Control Center lives in the chat menu button only (gate.py) — a
    web_app row in the reply keyboard duplicated it and, on mobile, made the
    keyboard tall enough to swallow the message input."""
    from bot_app.keyboards import get_main_menu_keyboard

    rows = get_main_menu_keyboard(_admin_id()).keyboard
    assert all("web_app" not in btn for row in rows for btn in row)


def test_admin_main_menu_keeps_admin_tool_rows():
    from bot_app.keyboards import get_main_menu_keyboard

    rows = get_main_menu_keyboard(_admin_id()).keyboard
    labels = [btn["text"] for row in rows for btn in row]
    assert "📊 Total Data Usage" in labels
    assert "💸 ငွေနှုတ်ရန်" in labels
    assert "📢 Broadcast စာပို့ရန်" in labels


def test_customer_main_menu_has_no_web_app_button():
    from bot_app.keyboards import get_main_menu_keyboard

    rows = get_main_menu_keyboard(USER).keyboard
    assert all("web_app" not in btn for row in rows for btn in row)

