"""Phase 3: Daily Reward bot UX — panel, claim, redeem (with refund on failure).

Network-free: ``mock_bot`` stubs Telegram (incl. subscription check + get_chat),
``create_outline_key`` is monkeypatched, ``isolated_state`` sandboxes files.
"""

from types import SimpleNamespace

from telebot.apihelper import ApiTelegramException

from bot_app.config import POINTS_STARTER_COST
from bot_app.handlers import points as H
from bot_app.services import points as P

UID = 720000555


def _call(data, chat_id=UID, message_id=555):
    return SimpleNamespace(
        id="cb1", data=data,
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=message_id),
    )


def _api_error(description):
    return ApiTelegramException(
        "editMessageText", "resp",
        {"error_code": 400, "description": description},
    )


def test_refresh_not_modified_does_not_duplicate(isolated_state, mock_bot, monkeypatch):
    """Tapping Refresh twice in the same minute yields identical content;
    Telegram raises 'message is not modified' — that must be a no-op, never a
    second (duplicate) reward panel."""
    def _raise(*a, **k):
        raise _api_error("Bad Request: message is not modified")
    monkeypatch.setattr(H.bot, "edit_message_text", _raise)

    H.handle_points_view(_call("points_view"))

    assert mock_bot.calls["send_message"] == []   # no duplicate panel


def test_refresh_falls_back_when_message_gone(isolated_state, mock_bot, monkeypatch):
    """A genuinely un-editable message (deleted / too old) still falls back to
    a fresh send so the user is not left without a panel."""
    def _raise(*a, **k):
        raise _api_error("Bad Request: message to edit not found")
    monkeypatch.setattr(H.bot, "edit_message_text", _raise)

    H.handle_points_view(_call("points_view"))

    assert len(mock_bot.calls["send_message"]) == 1


def test_reward_view_ready_for_fresh_user(isolated_state):
    text, markup = H.build_reward_view(UID)
    assert "Claim လုပ်နိုင်" in text
    datas = [b.callback_data for row in markup.keyboard for b in row]
    assert "points_claim" in datas
    assert "points_redeem" not in datas   # not topped up + no points


def test_reward_view_shows_redeem_when_eligible(isolated_state):
    P.credit_points(UID, POINTS_STARTER_COST, "topup")
    _text, markup = H.build_reward_view(UID)
    datas = [b.callback_data for row in markup.keyboard for b in row]
    assert "points_redeem" in datas


def test_claim_callback_awards_points(isolated_state, mock_bot):
    H.handle_points_claim(_call("points_claim"))
    rec = P.get_points(UID)
    assert rec["points"] > 0 and rec["lifetime_claims"] == 1
    assert mock_bot.calls["answer_callback"]        # popup shown


def test_redeem_do_provisions_key_and_deducts(isolated_state, mock_bot, monkeypatch):
    P.credit_points(UID, POINTS_STARTER_COST + 100, "topup")
    monkeypatch.setattr(
        H, "create_outline_key",
        lambda *a, **k: ("ss://fake-key#Starter", "Starter (720000555)", "27.10.2026"),
    )
    H.handle_points_redeem_do(_call("points_redeem_do", message_id=1001))

    assert P.get_points(UID)["points"] == 100        # 5,000 spent
    assert P.get_points(UID)["redeemed_count"] == 1
    # success message carries the provisioned key
    sent = " ".join(str(a) for a, _ in mock_bot.calls["edit_message_text"])
    assert "ss://fake-key" in sent


def test_redeem_do_refunds_on_provision_failure(isolated_state, mock_bot, monkeypatch):
    P.credit_points(UID, POINTS_STARTER_COST, "topup")
    monkeypatch.setattr(H, "create_outline_key", lambda *a, **k: (None, None, None))
    H.handle_points_redeem_do(_call("points_redeem_do", message_id=1002))

    rec = P.get_points(UID)
    assert rec["points"] == POINTS_STARTER_COST      # points returned
    assert rec["redeemed_count"] == 0                # redemption rolled back


def test_redeem_do_blocks_without_topup(isolated_state, mock_bot):
    P.credit_points(UID, POINTS_STARTER_COST, "claim")   # points but never topped up
    H.handle_points_redeem_do(_call("points_redeem_do", message_id=1003))
    assert P.get_points(UID)["points"] == POINTS_STARTER_COST   # untouched

