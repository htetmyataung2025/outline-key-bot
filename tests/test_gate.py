"""Force-join gate: who is considered subscribed? (Bot API mocked)."""

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

