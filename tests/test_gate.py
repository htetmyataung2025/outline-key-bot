"""Force-join gate: who is considered subscribed? (Bot API mocked)."""

import index

USER = 123456789


def test_admin_bypasses_check_without_api_call(mock_bot):
    assert index.is_user_subscribed(index.ADMIN_CHAT_IDS[0]) is True
    assert mock_bot.calls["get_chat_member"] == []


def test_member_statuses_pass(mock_bot):
    for status in ("creator", "administrator", "member"):
        mock_bot.member_status = status
        assert index.is_user_subscribed(USER) is True


def test_left_and_kicked_fail(mock_bot):
    for status in ("left", "kicked"):
        mock_bot.member_status = status
        assert index.is_user_subscribed(USER) is False


def test_restricted_currently_fails(mock_bot):
    # TODO Phase 1: users joining via invite links show up as "restricted"
    # and should be accepted. This test locks CURRENT behavior so the fix
    # is a deliberate, reviewed change.
    mock_bot.member_status = "restricted"
    assert index.is_user_subscribed(USER) is False


def test_api_error_fails_open(mock_bot):
    mock_bot.member_error = Exception("bot is not a member")
    assert index.is_user_subscribed(USER) is True
