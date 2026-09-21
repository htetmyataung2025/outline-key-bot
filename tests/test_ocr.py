"""OCR slip-parsing helpers (pure functions, no I/O)."""

import index


def test_myanmar_digits_normalized():
    assert index.clean_ocr_text_thoroughly("၁၂၃၄၅၆၇၈၉၀") == "1234567890"


def test_empty_text_gives_none():
    assert index.extract_transaction_last6("") is None
    assert index.extract_transaction_last6(None) is None
    assert index.extract_transaction_last6("hello world") is None


def test_transaction_keyword_line():
    text = "KBPay\nTransaction ID: 123456789012\nAmount 5000"
    assert index.extract_transaction_last6(text) == "789012"


def test_transaction_id_on_next_line():
    text = "Transaction No\n987654321098\nThank you"
    assert index.extract_transaction_last6(text) == "321098"


def test_myanmar_digits_transaction():
    text = "လုပ်ဆောင်ချက်အမှတ် ၉၈၇၆၅၄၃၂၁၀၉၈"
    assert index.extract_transaction_last6(text) == "321098"


def test_kpay_reference_format():
    ref = "010" + "1234567890123"
    assert index.extract_transaction_last6(f"Ref: {ref}") == ref[-6:]


def test_own_payment_phones_are_ignored():
    # Fallback must not pick our own phone numbers as the transaction id.
    text = f"Receiver {index.MY_PAYMENT_PHONES[0]} Transaction 112233445566"
    assert index.extract_transaction_last6(text) == "445566"


def test_order_id_from_slip_falls_back_to_random():
    order_id = index.generate_order_id_from_slip()
    assert order_id.startswith("#") and len(order_id) == 7
