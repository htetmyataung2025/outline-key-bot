"""Admin action attribution: every audit entry must carry the acting admin's
real Telegram ID — dashboard (Bearer + X-Admin-ID) and Telegram-side handlers
alike. Covers the previously un-audited Telegram mutations."""

from types import SimpleNamespace

from bot_app.services.billing import get_user_balance, update_user_balance
from bot_app.services.orders import load_redeem_codes
from bot_app.services.slips import get_slip_by_id, load_audit_logs, record_slip, review_slip
from bot_app.services.states import (
    get_admin_reject_state, set_admin_deduct_state, set_broadcast_state,
)

ADMIN_ID = 111000111
CUSTOMER_ID = 555444333


def _admin_callback(data, message_id=7, caption=None):
    return SimpleNamespace(
        id=f"cb-{message_id}",
        data=data,
        from_user=SimpleNamespace(id=ADMIN_ID, first_name="Admin", username="admin"),
        message=SimpleNamespace(chat=SimpleNamespace(id=ADMIN_ID), message_id=message_id, caption=caption),
    )


def _admin_message(text):
    return SimpleNamespace(
        text=text,
        chat=SimpleNamespace(id=ADMIN_ID),
        from_user=SimpleNamespace(id=ADMIN_ID, first_name="Admin", username="admin"),
    )


def _last_audit(action):
    entries = [e for e in load_audit_logs() if e["action"] == action]
    assert entries, f"no audit entry for {action}: {load_audit_logs()}"
    return entries[-1]


# ── Dashboard: identity flows from the X-Admin-ID login header ────────────

def test_dashboard_review_audits_logged_in_admin_id(client, mock_bot, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET_KEY", "super-secret-admin-pass-999")
    record_slip(slip_id="SLIP-AUD-1", chat_id=CUSTOMER_ID, amount=3000, username="buyer")

    resp = client.post(
        "/api/admin/slips/SLIP-AUD-1/review",
        json={"action": "APPROVE"},
        headers={"Authorization": "Bearer super-secret-admin-pass-999", "X-Admin-ID": str(ADMIN_ID)},
    )
    assert resp.status_code == 200

    entry = _last_audit("SLIP_APPROVE")
    assert entry["admin_id"] == str(ADMIN_ID)


# ── Telegram: legacy-slip approve fallback (money mutation, was un-audited) ──

def test_legacy_fallback_approve_leaves_audit_trail(mock_bot, isolated_state):
    from bot_app.handlers.topup import handle_approve_topup

    handle_approve_topup(_admin_callback("approve_topup_555444333_5000_LEGACY1", caption="slip"))

    assert get_user_balance(CUSTOMER_ID) == 5000
    entry = _last_audit("SLIP_APPROVE")
    assert entry["admin_id"] == str(ADMIN_ID)
    assert entry["target_id"] == "LEGACY1"
    assert entry["details"]["legacy"] is True
    assert entry["details"]["amount"] == 5000


# ── Telegram: redeem code generation ──────────────────────────────────────

def test_telegram_redeem_generation_audits_admin(mock_bot, isolated_state):
    from bot_app.handlers.admin import handle_admin_rd_generate

    handle_admin_rd_generate(_admin_callback("adm_rdcnt_1000_single_3_2"))

    codes = load_redeem_codes()
    assert len(codes) == 2
    entry = _last_audit("REDEEM_BATCH_CREATE")
    assert entry["admin_id"] == str(ADMIN_ID)
    assert entry["details"]["amount"] == 1000
    assert entry["details"]["count"] == 2
    assert entry["details"]["via"] == "telegram"


# ── Telegram: key deletion ────────────────────────────────────────────────

def test_telegram_key_delete_audits_admin(mock_bot, isolated_state, monkeypatch):
    from bot_app.handlers.admin import handle_admin_del_key

    class _Resp:
        status_code = 200

    monkeypatch.setattr("requests.delete", lambda *a, **k: _Resp())

    handle_admin_del_key(_admin_callback("delkey_confirm_1_999", message_id=9))

    entry = _last_audit("KEY_DELETE")
    assert entry["admin_id"] == str(ADMIN_ID)
    assert entry["target_id"] == "999"
    assert entry["details"]["server"] == "1"


# ── Telegram: /deduct command + dialog flow ───────────────────────────────

def test_deduct_command_audits_admin(mock_bot, isolated_state):
    from bot_app.handlers.wallet import handle_admin_deduct_command

    update_user_balance(CUSTOMER_ID, 5000)
    handle_admin_deduct_command(_admin_message(f"/deduct {CUSTOMER_ID} 2000"))

    entry = _last_audit("BALANCE_DEDUCT")
    assert entry["admin_id"] == str(ADMIN_ID)
    assert entry["target_id"] == str(CUSTOMER_ID)
    assert entry["details"]["amount"] == 2000
    assert entry["details"]["new_balance"] == 3000


def test_deduct_dialog_audits_admin(mock_bot, isolated_state):
    from bot_app.handlers.menu import handle_all_messages

    update_user_balance(CUSTOMER_ID, 5000)
    set_admin_deduct_state(ADMIN_ID, {"step": "ask_amount", "type": "all", "target_user_id": str(CUSTOMER_ID)})
    handle_all_messages(_admin_message("1500"))

    entry = _last_audit("BALANCE_DEDUCT")
    assert entry["admin_id"] == str(ADMIN_ID)
    assert entry["target_id"] == str(CUSTOMER_ID)
    assert entry["details"]["amount"] == 1500


# ── Telegram: broadcast ───────────────────────────────────────────────────

def test_text_broadcast_audits_admin(mock_bot, isolated_state, monkeypatch):
    from bot_app.handlers.menu import handle_all_messages

    # save_user_id/load_all_users need KV (disabled in tests) — stub the
    # recipient list the broadcast service reads.
    users = [str(CUSTOMER_ID), "555555555"]
    monkeypatch.setattr("bot_app.services.broadcast.load_all_users", lambda: users)
    set_broadcast_state(ADMIN_ID, True)

    handle_all_messages(_admin_message("📢 hello everyone"))

    entry = _last_audit("BROADCAST")
    assert entry["admin_id"] == str(ADMIN_ID)
    assert entry["details"]["message_type"] == "text"
    assert entry["details"]["recipients"] == 2
    assert entry["details"]["sent"] == 2
    # Only non-admin users receive the broadcast text (the admin gets only
    # the handler's status messages).
    user_received = [m[1] for m in mock_bot.calls["send_message"] if str(m[0]) == str(CUSTOMER_ID)]
    assert "📢 hello everyone" in user_received
    admin_received = [m[1] for m in mock_bot.calls["send_message"] if str(m[0]) == str(ADMIN_ID)]
    assert all("hello everyone" not in t for t in admin_received)


# ── Telegram slip rejection (parity with the dashboard) ───────────────────

def test_admin_notification_keyboard_has_reject_button(mock_bot, isolated_state, monkeypatch):
    from bot_app.handlers import topup

    monkeypatch.setattr(topup, "extract_order_id_and_tx", lambda file_path=None: ("#KKBTEST", "123456"))
    photo_message = SimpleNamespace(
        content_type="photo",
        chat=SimpleNamespace(id=CUSTOMER_ID),
        from_user=SimpleNamespace(id=CUSTOMER_ID, first_name="Buyer", last_name="", username="buyer"),
        photo=[SimpleNamespace(file_id="photo-file-id")],
        caption="receipt",
    )
    topup.handle_photo_messages(photo_message)

    assert mock_bot.calls["send_photo"], "admin notification was not sent"
    markup = mock_bot.last_send_photo_kwargs["reply_markup"]
    buttons = [btn for row in markup.keyboard for btn in row]
    assert any("Approve" in b.text for b in buttons)
    assert any(b.text == "❌ Reject" and b.callback_data.startswith("reject_topup_") for b in buttons)


def test_telegram_reject_flow_rejects_slip(mock_bot, isolated_state):
    from bot_app.handlers.menu import handle_all_messages
    from bot_app.handlers.topup import handle_reject_topup_start

    record_slip(slip_id="SLIP-REJ-1", chat_id=CUSTOMER_ID, amount=4000, username="buyer")

    # Step 1: pressing ❌ Reject parks the slip and asks for a reason.
    handle_reject_topup_start(_admin_callback("reject_topup_SLIP-REJ-1", message_id=11))
    assert get_admin_reject_state(ADMIN_ID) == {"slip_id": "SLIP-REJ-1"}

    # Step 2: the admin's next text is the rejection reason.
    handle_all_messages(_admin_message("ဘယ်သူ့မှ လွှဲထားတာ မတွေ့လို့ပါ"))

    slip = get_slip_by_id("SLIP-REJ-1")
    assert slip["status"] == "REJECTED"
    assert slip["reviewed_by"] == str(ADMIN_ID)
    assert get_user_balance(CUSTOMER_ID) == 0  # a reject must never credit
    entry = _last_audit("SLIP_REJECT")
    assert entry["admin_id"] == str(ADMIN_ID)
    assert get_admin_reject_state(ADMIN_ID) is None
    sent_to = [str(m[0]) for m in mock_bot.calls["send_message"]]
    assert str(CUSTOMER_ID) in sent_to  # customer was notified


def test_reject_start_on_reviewed_slip_shows_alert(mock_bot, isolated_state):
    from bot_app.handlers.topup import handle_reject_topup_start

    record_slip(slip_id="SLIP-REJ-2", chat_id=CUSTOMER_ID, amount=1000, username="buyer")
    review_slip("SLIP-REJ-2", "APPROVE", reviewed_by=ADMIN_ID)

    answers_before = len(mock_bot.calls["answer_callback"])
    handle_reject_topup_start(_admin_callback("reject_topup_SLIP-REJ-2", message_id=12))

    assert get_admin_reject_state(ADMIN_ID) is None
    answers = mock_bot.calls["answer_callback"][answers_before:]
    assert any("APPROVED" in str(a) for a in answers)


def test_cancel_reject_keeps_slip_pending(mock_bot, isolated_state):
    from bot_app.handlers.menu import handle_all_messages
    from bot_app.handlers.topup import handle_reject_topup_start

    record_slip(slip_id="SLIP-REJ-3", chat_id=CUSTOMER_ID, amount=2000, username="buyer")
    handle_reject_topup_start(_admin_callback("reject_topup_SLIP-REJ-3", message_id=13))

    handle_all_messages(_admin_message("/cancel_reject"))

    assert get_admin_reject_state(ADMIN_ID) is None
    assert get_slip_by_id("SLIP-REJ-3")["status"] == "PENDING"
