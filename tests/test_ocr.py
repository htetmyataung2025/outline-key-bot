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

