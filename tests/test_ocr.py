"""OCR slip-parsing helpers (pure functions, no I/O)."""

from bot_app.config import MY_PAYMENT_PHONES
from bot_app.services import ocr
from bot_app.services.ocr import (
    clean_ocr_text_thoroughly,
    extract_order_id_and_tx,
    extract_transaction_last6,
    generate_order_id_from_slip,
)


def test_myanmar_digits_normalized():
    assert clean_ocr_text_thoroughly("၁၂၃၄၅၆၇၈၉၀") == "1234567890"


def test_empty_text_gives_none():
    assert extract_transaction_last6("") is None
    assert extract_transaction_last6(None) is None
    assert extract_transaction_last6("hello world") is None


def test_transaction_keyword_line():
    text = "KBPay\nTransaction ID: 123456789012\nAmount 5000"
    assert extract_transaction_last6(text) == "789012"


def test_transaction_id_on_next_line():
    text = "Transaction No\n987654321098\nThank you"
    assert extract_transaction_last6(text) == "321098"


def test_myanmar_digits_transaction():
    text = "လုပ်ဆောင်ချက်အမှတ် ၉၈၇၆၅၄၃၂၁၀၉၈"
    assert extract_transaction_last6(text) == "321098"


def test_kpay_reference_format():
    ref = "010" + "1234567890123"
    assert extract_transaction_last6(f"Ref: {ref}") == ref[-6:]


def test_own_payment_phones_are_ignored():
    # Fallback must not pick our own phone numbers as the transaction id.
    assert MY_PAYMENT_PHONES, "MY_PAYMENT_PHONES must be set in tests (see conftest)"
    text = f"Receiver {MY_PAYMENT_PHONES[0]} Transaction 112233445566"
    assert extract_transaction_last6(text) == "445566"


def test_fallback_skips_customer_phone_numbers():
    # Regression: a Wave Money slip where the recipient phone line was
    # mistaken for the transaction id (produced #912520-style ids).
    text = "Wave Money\nTo 9679912520\n1121631108\nThank you"
    assert extract_transaction_last6(text) == "631108"


def test_fallback_skips_dates():
    text = "29082026 13:12:22\n5566778899"
    assert extract_transaction_last6(text) == "778899"


def test_keyword_line_phone_before_label_is_skipped():
    # Digits must come AFTER the keyword on the line, not before it.
    text = "0979912520 Transaction 112233445566"
    assert extract_transaction_last6(text) == "445566"


def test_kpay_15_digit_statement_ref():
    # KBZPay statement refs can be 15 digits ("010" + 12).
    text = "KBZPay\n010042580200252\nAmount 500000"
    assert extract_transaction_last6(text) == "200252"


def test_extract_order_id_returns_tx_ref(monkeypatch):
    monkeypatch.setattr(ocr, "parse_slip_ocr", lambda fp: "Transaction ID: 123456789012")
    order_id, tx = extract_order_id_and_tx("photos/x.jpg")
    assert order_id == "#789012"
    assert tx == "789012"


def test_extract_order_id_random_when_ocr_fails(monkeypatch):
    monkeypatch.setattr(ocr, "parse_slip_ocr", lambda fp: "")
    order_id, tx = extract_order_id_and_tx("photos/x.jpg")
    assert order_id.startswith("#") and len(order_id) == 7
    assert tx == ""


def test_order_id_from_slip_falls_back_to_random():
    order_id = generate_order_id_from_slip()
    assert order_id.startswith("#") and len(order_id) == 7


# --- Bot Update #23: per-wallet receipt layouts (owner-supplied samples,
# 2026-11-23) + the "202608" date/time-fusion regression. ---


def test_kbz_burmese_receipt():
    text = (
        "KBZ BANK E-Receipt\n"
        "-2,000.00 Ks\n"
        "လုပ်ဆောင်သောအချိန် 12/11/2026 13:16:50\n"
        "လုပ်ဆောင်မှုအမှတ် 01004333081929153538\n"
        "လုပ်ဆောင်မှုအမျိုးအစား Transfer\n"
        "ငွေလွှဲမည် Htet Myat Aung (******0092)\n"
        "ငွေပမာဏ -2,000.00 Ks"
    )
    assert extract_transaction_last6(text) == "153538"


def test_kbz_english_receipt():
    text = (
        "KBZ BANK E-Receipt\n"
        "-5,000.00 Ks\n"
        "Transaction Time 13/11/2026 11:38:05\n"
        "Transaction No 01004334001975753480\n"
        "Transaction Type Transfer\n"
        "Transfer To Htet Myat Aung (******0092)\n"
        "Amount -5,000.00 Ks\n"
        "Notes Payment"
    )
    assert extract_transaction_last6(text) == "753480"


def test_kbz_datetime_beside_label_is_not_the_ref():
    # Regression (slip #202608, 2026-11-23): the extractor returned "202608"
    # — the year+hour of "23/11/2026 08:29" fused together — because the
    # date/time line sat next to the အမှတ် label, while the real ref
    # (…897249) was never reached. The real ref must win.
    text = (
        "KBZ Pay\n"
        "လုပ်ဆောင်မှုအမှတ်\n"
        "23/11/2026 08:29:05\n"
        "01004344090491 897249\n"
        "Htet Myat Aung (******0092)\n"
        "+1,000.00 Ks"
    )
    assert extract_transaction_last6(text) == "897249"


def test_datetime_alone_is_not_a_ref():
    # Same trap with no real reference present: must return None, never
    # the fused year+hour.
    text = "လုပ်ဆောင်မှုအမှတ်\n23/11/2026 08:29:05"
    assert extract_transaction_last6(text) is None


def test_uab_receipt():
    # UAB refs embed the date (12112026...) inside the number itself —
    # masking must not destroy the ref.
    text = (
        "uabpay Transfer\n"
        "MMK 2,000.00 Successful\n"
        "Htet Pyae Sone Aung uabpay 0942****703 From\n"
        "Htet Myat Aung uabpay 0969****092 To\n"
        "Transaction ID: 121120266442341\n"
        "Date & Time: 12 Nov 2026 09:44 PM\n"
        "Transaction Type: Transfer\n"
        "Total Amount: 2,000.00 MMK"
    )
    assert extract_transaction_last6(text) == "442341"


def test_aya_receipt():
    text = (
        "AYA PAY E-Receipt\n"
        "Transaction Type Transfer to Wallet\n"
        "Transaction ID 275771910725\n"
        "Sender Phone 09965407738\n"
        "Sender Name AUNG PHYO THANT\n"
        "Amount 1,000 MMK\n"
        "Receiver Phone 09699970092\n"
        "Receiver Name HTET MYAT AUNG\n"
        "Date and Time 26 September 2026, 7:18 PM\n"
        "Notes Vpn"
    )
    assert extract_transaction_last6(text) == "910725"


def test_wave_receipt():
    text = (
        "Successful\n"
        "5,000.00 Ks\n"
        "To Htet Myat Aung 09699970092\n"
        "Type Account\n"
        "Fees 0.00 Ks\n"
        "Amount 5,000.00 Ks\n"
        "Transaction ID 3040680460\n"
        "Date & Time 09 November 2026 • 9:17 AM\n"
        "Note shop"
    )
    assert extract_transaction_last6(text) == "680460"

