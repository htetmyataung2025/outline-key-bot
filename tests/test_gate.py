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
    assert "Control Center" in button.text


def test_start_sets_landing_menu_button_for_customers(mock_bot, isolated_state):
    from bot_app.config import LANDING_URL
    from bot_app.handlers import gate

    gate.send_welcome(_start_message(USER))

    _chat_id, button = _last_menu_button(mock_bot)
    assert button.web_app.url == LANDING_URL
    assert button.text == "Main Website"


def test_admin_main_menu_has_control_center_web_app_button():
    from bot_app.config import DASHBOARD_URL
    from bot_app.keyboards import get_main_menu_keyboard

    rows = get_main_menu_keyboard(_admin_id()).keyboard
    web_app_urls = [
        btn["web_app"]["url"]
        for row in rows for btn in row
        if "web_app" in btn
    ]
    assert web_app_urls == [DASHBOARD_URL]


def test_customer_main_menu_has_no_web_app_button():
    from bot_app.keyboards import get_main_menu_keyboard

    rows = get_main_menu_keyboard(USER).keyboard
    assert all("web_app" not in btn for row in rows for btn in row)

