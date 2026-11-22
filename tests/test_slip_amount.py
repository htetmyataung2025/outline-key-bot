"""Bot Update #20: slip amount auto-fill from OCR.

Customers select the top-up amount before uploading the slip and often
select the wrong one. At intake the slip photo's OCR text is mined for
the transfer amount; when one is confidently read it replaces the
selected amount on the recorded slip.
"""

import io

import bot_app.routes_app as ra
import bot_app.routes_user as ru
from bot_app.services import ocr
from bot_app.services.ocr import extract_slip_amount, resolve_slip_amount
from bot_app.services.slips import load_all_slips

KBZ_RECEIPT = (
    "KBZ Pay\n"
    "E-Receipt\n"
    "Receiver: Htet Myat Aung (******0092)\n"
    "Amount: 4,000.00 Ks\n"
    "Transaction ID: 01004342000400157230\n"
    "Date: 21/11/2026 12:19:10\n"
)

WAVE_RECEIPT = (
    "Wave Money\n"
    "Transfer Successful\n"
    "To: 09699970092\n"
    "Amount: 5,000 Ks\n"
    "Transaction ID: 3261197032\n"
)


# --- extract_slip_amount: pure parsing ------------------------------------

def test_kbz_receipt_amount():
    assert extract_slip_amount(KBZ_RECEIPT) == 4000


def test_wave_receipt_amount():
    assert extract_slip_amount(WAVE_RECEIPT) == 5000


def test_label_amount_beats_balance_line():
    text = "KBZ Pay\nAvailable Balance: 150,000 Ks\nTransfer Amount: 5,000 Ks\n"
    assert extract_slip_amount(text) == 5000


def test_total_balance_line_is_not_the_amount():
    text = "Total Balance 150,000 Ks\nAmount 5,000 Ks\n"
    assert extract_slip_amount(text) == 5000


def test_currency_anchored_without_label():
    assert extract_slip_amount("Payment Successful\n5,000 Ks\nThank you\n") == 5000


def test_fee_zero_is_ignored():
    assert extract_slip_amount("Wave Money\nAmount 10,000 Ks\nFee 0 Ks\n") == 10000


def test_myanmar_digits_amount():
    assert extract_slip_amount("ပမာဏ ၅,၀၀၀ ကျပ်") == 5000


def test_non_slip_image_text_gives_none():
    text = "H&E VPN\nInstall\nOpen the app to continue\nVersion 0.6.8\n"
    assert extract_slip_amount(text) is None


def test_phone_date_time_only_gives_none():
    assert extract_slip_amount("09699970092\n21/11/2026 12:19:10\n") is None


def test_empty_text_gives_none():
    assert extract_slip_amount("") is None
    assert extract_slip_amount(None) is None


# --- resolve_slip_amount: which amount gets recorded -----------------------

def test_resolve_prefers_ocr_when_different():
    assert resolve_slip_amount(1000, 5000) == (5000, "ocr")


def test_resolve_ocr_matching_selection():
    assert resolve_slip_amount(5000, 5000) == (5000, "ocr")


def test_resolve_falls_back_when_ocr_reads_nothing():
    assert resolve_slip_amount(1000, None) == (1000, "selected")


def test_resolve_distrusts_tiny_ocr_read():
    # A detected amount under the 500 Ks minimum top-up is treated as a
    # misread: the customer's selection stands and the slip is flagged.
    assert resolve_slip_amount(5000, 300) == (5000, "selected")


# --- extract_slip_facts: one OCR pass yields id + tx + amount --------------

def test_extract_slip_facts_single_ocr_pass(monkeypatch):
    calls = []

    def fake_ocr(file_path):
        calls.append(file_path)
        return KBZ_RECEIPT

    monkeypatch.setattr(ocr, "parse_slip_ocr", fake_ocr)
    order_id, tx, amount, probable = ocr.extract_slip_facts("photos/slip.jpg")
    assert calls == ["photos/slip.jpg"]
    assert tx == "157230"  # last 6 of the receipt's transaction reference
    assert order_id == "#157230"
    assert amount == 4000
    assert probable is True


# --- App intake: POST /api/app/topup ----------------------------------------

_PNG_1PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="


def _app_topup(client, user_id, amount, monkeypatch, ocr_result):
    monkeypatch.setattr(ra, "extract_amount_and_tx_from_bytes", lambda b: ocr_result)
    token = ra._make_app_token(user_id)
    return client.post(
        "/api/app/topup",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount": amount, "method": "KBZ", "image_base64": _PNG_1PX},
    )


def test_app_topup_autofills_amount_from_slip(client, isolated_state, mock_bot, monkeypatch):
    resp = _app_topup(client, 555000222, 1000, monkeypatch, ("001572", 5000, True))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["amount"] == 5000
    assert data["amount_corrected"] is True
    assert data["ocr_amount"] == 5000
    # Bot Update #20.1: the Top-Up ID comes from the slip's transaction
    # reference, like the Telegram-bot flow — not a random string.
    assert data["slip_id"] == "#001572"

    slips = load_all_slips()
    assert len(slips) == 1
    slip = next(iter(slips.values()))
    assert slip["amount"] == 5000
    assert slip["ocr_amount"] == 5000
    assert slip["selected_amount"] == 1000
    assert slip["extracted_tx_id"] == "001572"


def test_app_topup_id_collision_falls_back_to_random(client, isolated_state, mock_bot, monkeypatch):
    from bot_app.services.slips import record_slip

    record_slip(slip_id="#001572", chat_id=999, amount=5000)
    resp = _app_topup(client, 555000555, 5000, monkeypatch, ("001572", 5000, True))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["slip_id"] != "#001572"
    assert len(data["slip_id"]) == 8
    # Both records survive — the new slip never overwrites the old one.
    assert len(load_all_slips()) == 2


def test_app_topup_keeps_selection_when_ocr_reads_nothing(client, isolated_state, mock_bot, monkeypatch):
    # Probable slip (another signal matched) but no amount/tx read: the
    # customer's selection stands. A photo with NO signal at all is
    # bounced by the Bot Update #21 gate — see tests/test_slip_gate.py.
    resp = _app_topup(client, 555000333, 2000, monkeypatch, ("", None, True))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["amount"] == 2000
    assert data["amount_corrected"] is False

    slip = next(iter(load_all_slips().values()))
    assert slip["amount"] == 2000
    assert slip["ocr_amount"] is None
    assert slip["selected_amount"] == 2000


# --- Mini App intake: POST /api/user/topup-slip ------------------------------

def test_miniapp_topup_autofills_amount_from_slip(client, isolated_state, mock_bot, monkeypatch, make_telegram_init_data):
    monkeypatch.setattr(ru, "extract_amount_and_tx_from_bytes", lambda b: ("778899", 5000, True))
    user_id = 555000444
    init_data = make_telegram_init_data(user_id=user_id)
    resp = client.post(
        "/api/user/topup-slip",
        headers={"X-Telegram-Init-Data": init_data},
        data={"amount": "1000", "method": "KBZ",
              "file": (io.BytesIO(b"\x89PNG fake"), "slip.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["amount"] == 5000
    assert data["slip_id"] == "#778899"

    slip = next(iter(load_all_slips().values()))
    assert slip["amount"] == 5000
    assert slip["ocr_amount"] == 5000
    assert slip["selected_amount"] == 1000
    assert slip["extracted_tx_id"] == "778899"
