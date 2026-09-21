"""Small pure helpers."""

import re

import index


def test_bytes_to_gb():
    assert index.bytes_to_gb(25 * 1000 ** 3) == 25.0
    assert index.bytes_to_gb(0) == 0


def test_clean_ss_url_strips_fragment_and_query():
    url = "ss://abc123@host:8388#My Key (123)?plugin=x"
    cleaned = index.clean_ss_url(url)
    assert "#" not in cleaned and "?" not in cleaned
    assert "abc123@host:8388" in cleaned
    assert index.clean_ss_url("") == ""


def test_random_order_id_format():
    assert re.fullmatch(r"#[A-Z0-9]{6}", index.generate_order_id_from_slip())


def test_payment_phones_configured():
    assert len(index.MY_PAYMENT_PHONES) >= 1
