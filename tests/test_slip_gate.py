"""Bot Update #21: the slip-photo gate.

A photo with NO sign of a payment slip (no transaction reference, no
amount, no receiver, no wallet brand in its OCR text) is bounced at
intake on all three channels: the customer is told right away and the
photo never reaches the admin review queue. Every channel keeps an
escape hatch — the customer can vouch "this IS a real slip", and the
photo is then recorded flagged ``unverified_photo`` for a human check.
"""

import io
from types import SimpleNamespace

import bot_app.routes_app as ra
import bot_app.routes_user as ru
from bot_app.services.ocr import slip_photo_is_probable
from bot_app.services.slips import get_slip_by_id, load_all_slips

CUSTOMER_ID = 555000777

KBZ_RECEIPT = (
    "KBZ Pay\n"
    "E-Receipt\n"
    "Receiver: Htet Myat Aung (******0092)\n"
    "Amount: 4,000.00 Ks\n"
    "Transaction ID: 01004342000400157230\n"
)

APP_SCREENSHOT_TEXT = (
    "H&E VPN\n"
    "Connected\n"
    "Singapore Server\n"
    "Install\n"
    "Version 0.6.8\n"
)


# --- the gate verdict itself -------------------------------------------------

def test_real_receipts_pass_the_gate():
    assert slip_photo_is_probable(KBZ_RECEIPT) is True


def test_app_screenshot_is_bounced():
    assert slip_photo_is_probable(APP_SCREENSHOT_TEXT) is False


def test_empty_text_is_bounced():
    assert slip_photo_is_probable("") is False
    assert slip_photo_is_probable(None) is False


def test_brand_alone_passes():
    assert slip_photo_is_probable("KBZ Pay") is True
    assert slip_photo_is_probable("Wave Money") is True


def test_receiver_name_alone_passes():
    assert slip_photo_is_probable("Transfer to Htet Myat Aung\nSuccessful") is True


def test_amount_alone_passes():
    assert slip_photo_is_probable("You sent 5,000 Ks\nThank you") is True


# --- Telegram bot flow --------------------------------------------------------

def _photo_message(chat_id=CUSTOMER_ID):
    return SimpleNamespace(
        content_type="photo",
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=chat_id, first_name="Test", last_name="", username="tester"),
        photo=[SimpleNamespace(file_id="fid_small"), SimpleNamespace(file_id="fid_big")],
        caption=None,
    )


def test_bot_bounces_non_slip_photo(mock_bot, isolated_state, monkeypatch):
    from bot_app.handlers import topup
    from bot_app.services.states import get_slip_gate_state, set_topup_state

    monkeypatch.setattr(topup, "extract_slip_facts",
                        lambda file_path=None: ("#RAND42", "", None, False))
    set_topup_state(CUSTOMER_ID, 2000)

    topup.handle_photo_messages(_photo_message())

    # Nothing recorded, no admin alert — but the photo is parked and the
    # customer got the notice.
    assert load_all_slips() == {}
    assert mock_bot.calls["send_photo"] == []
    assert len(mock_bot.calls["reply_to"]) == 1
    assert "ငွေလွှဲပြေစာ မဟုတ်ပါဘူး" in mock_bot.calls["reply_to"][0][1]
    state = get_slip_gate_state(CUSTOMER_ID)
    assert state is not None
    assert state["file_id"] == "fid_big"
    assert state["selected_amt"] == 2000


def test_bot_escape_hatch_records_unverified_slip(mock_bot, isolated_state, monkeypatch):
    from bot_app.handlers import topup
    from bot_app.services.states import get_slip_gate_state, set_slip_gate_state

    set_slip_gate_state(CUSTOMER_ID, {
        "file_id": "fid_big",
        "topup_id": "#RAND42",
        "tx_ref": "",
        "selected_amt": 2000,
        "user_name": "Test",
        "username": "@tester",
    })
    call = SimpleNamespace(
        id="cb1",
        data="slip_gate_send",
        message=SimpleNamespace(chat=SimpleNamespace(id=CUSTOMER_ID), message_id=42),
        from_user=SimpleNamespace(id=CUSTOMER_ID),
    )
    topup.handle_slip_gate_send(call)

    slip = get_slip_by_id("#RAND42")
    assert slip is not None
    assert slip["amount"] == 2000
    assert slip["unverified_photo"] is True
    assert mock_bot.calls["send_photo"], "admin alert was not sent"
    assert get_slip_gate_state(CUSTOMER_ID) is None


def test_bot_escape_hatch_without_state_is_a_noop(mock_bot, isolated_state):
    from bot_app.handlers import topup

    call = SimpleNamespace(
        id="cb2",
        data="slip_gate_send",
        message=SimpleNamespace(chat=SimpleNamespace(id=CUSTOMER_ID), message_id=43),
        from_user=SimpleNamespace(id=CUSTOMER_ID),
    )
    topup.handle_slip_gate_send(call)
    assert load_all_slips() == {}


# --- Native app flow -----------------------------------------------------------

_PNG_1PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="


def _app_post(client, user_id, extra=None):
    token = ra._make_app_token(user_id)
    body = {"amount": 2000, "method": "KBZ", "image_base64": _PNG_1PX}
    if extra:
        body.update(extra)
    return client.post(
        "/api/app/topup",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


def test_app_bounces_non_slip_photo(client, isolated_state, mock_bot, monkeypatch):
    monkeypatch.setattr(ra, "extract_amount_and_tx_from_bytes", lambda b: ("", None, False))
    resp = _app_post(client, 555000778)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"] == "not_a_slip"
    assert "ငွေလွှဲပြေစာ မဟုတ်ပါဘူး" in data["message"]
    assert load_all_slips() == {}
    assert mock_bot.calls["send_photo"] == []


def test_app_force_slip_records_unverified(client, isolated_state, mock_bot, monkeypatch):
    monkeypatch.setattr(ra, "extract_amount_and_tx_from_bytes", lambda b: ("", None, False))
    resp = _app_post(client, 555000779, {"force_slip": True})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["unverified"] is True
    slip = next(iter(load_all_slips().values()))
    assert slip["unverified_photo"] is True


# --- Mini App flow -------------------------------------------------------------

def _mini_post(client, make_telegram_init_data, user_id, extra_form=None):
    init_data = make_telegram_init_data(user_id=user_id)
    form = {"amount": "2000", "method": "KBZ",
            "file": (io.BytesIO(b"\x89PNG fake"), "photo.png")}
    if extra_form:
        form.update(extra_form)
    return client.post(
        "/api/user/topup-slip",
        headers={"X-Telegram-Init-Data": init_data},
        data=form,
        content_type="multipart/form-data",
    )


def test_miniapp_bounces_non_slip_photo(client, isolated_state, mock_bot, monkeypatch, make_telegram_init_data):
    monkeypatch.setattr(ru, "extract_amount_and_tx_from_bytes", lambda b: ("", None, False))
    resp = _mini_post(client, make_telegram_init_data, 555000780)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"] == "not_a_slip"
    assert load_all_slips() == {}


def test_miniapp_force_slip_records_unverified(client, isolated_state, mock_bot, monkeypatch, make_telegram_init_data):
    monkeypatch.setattr(ru, "extract_amount_and_tx_from_bytes", lambda b: ("", None, False))
    resp = _mini_post(client, make_telegram_init_data, 555000781, {"force_slip": "true"})
    assert resp.status_code == 200
    slip = next(iter(load_all_slips().values()))
    assert slip["unverified_photo"] is True
