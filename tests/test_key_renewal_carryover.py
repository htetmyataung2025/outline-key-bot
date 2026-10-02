"""Regression tests for renewal expiry carry-over.

Background: the Telegram-bot renewal flow (``renew_specific_unlimited_key`` /
``renew_or_create_unlimited_key``) used to compute the new expiry as
``today + term``, ignoring the key's current expiry. A customer who renewed
early therefore *lost* the days they had already paid for. The renewal must
instead add the new term on top of the current expiry (carry-over), falling
back to today only when the key has already lapsed — the same rule
``routes_admin.extend_key_endpoint`` applies.
"""

from datetime import datetime

import pytest

from bot_app.services import outline, settings as settings_svc


_SERVERS = [
    {"id": 1, "name": "Server 1 (SG-1)", "api_url": "https://sg1.example.com/api"},
]


@pytest.fixture
def settings_stub(monkeypatch):
    monkeypatch.setattr(
        settings_svc, "get_system_settings",
        lambda force_refresh=False: {"servers": _SERVERS},
    )
    monkeypatch.setattr(settings_svc, "invalidate_settings_cache", lambda reset_fallback=False: None)
    import bot_app.config as cfg
    monkeypatch.setattr(cfg, "OUTLINE_API_URL_1", "")


class FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_parse_expiry_reads_trailing_date():
    assert outline._parse_expiry_from_name("Htet (12345) 30.10.2026") == datetime(2026, 10, 30)
    assert outline._parse_expiry_from_name("Htet (12345) 5.9.26") == datetime(2026, 9, 5)
    assert outline._parse_expiry_from_name("Htet no date here") is None


def test_carry_over_adds_term_onto_future_expiry():
    today = datetime(2026, 10, 2)
    # 28 days still remaining -> +1 month lands on the OLD expiry + 1 month.
    assert outline._carry_over_expiry("H (1) 30.10.2026", today, months_count=1) == "30.11.2026"


def test_carry_over_starts_from_today_when_lapsed():
    today = datetime(2026, 10, 2)
    assert outline._carry_over_expiry("H (1) 01.09.2026", today, months_count=1) == "02.11.2026"


def test_carry_over_starts_from_today_when_no_date():
    today = datetime(2026, 10, 2)
    assert outline._carry_over_expiry("H (1) no-date", today, custom_days=30) == "01.11.2026"


# ---------------------------------------------------------------------------
# renew_specific_unlimited_key: early renewal keeps the unused days + data.
# ---------------------------------------------------------------------------

def test_renew_specific_carries_over_remaining_days(settings_stub, monkeypatch, isolated_state):
    monkeypatch.setattr(outline, "myanmar_now", lambda: datetime(2026, 10, 2))

    used_bytes = 100 * 1000 ** 3  # 100 GB already used
    puts = {}

    def fake_get(url, **kw):
        if url.endswith("/access-keys"):
            return FakeResp({"accessKeys": [
                {"id": "k1", "name": "Htet (12345) 30.10.2026", "accessUrl": "ss://old"},
            ]})
        if url.endswith("/metrics/transfer"):
            return FakeResp({"bytesTransferredByUserId": {"k1": used_bytes}})
        return FakeResp({})

    def fake_put(url, **kw):
        if url.endswith("/name"):
            puts["name"] = kw.get("data", {}).get("name")
        elif url.endswith("/data-limit"):
            puts["limit"] = kw.get("json", {}).get("limit", {}).get("bytes")
        return FakeResp({})

    monkeypatch.setattr(outline.requests, "get", fake_get)
    monkeypatch.setattr(outline.requests, "put", fake_put)

    final_key, updated_name, new_expire = outline.renew_specific_unlimited_key("1", "k1", months_count=1)

    # Expiry carried over from 30.10.2026, NOT reset to 02.11.2026.
    assert new_expire == "30.11.2026"
    assert updated_name == "Htet (12345) 30.11.2026"
    assert final_key == "ss://old#Htet (12345) 30.11.2026"
    # Data limit = used + 500 GB (carry-over on the lifetime cap).
    assert puts["limit"] == used_bytes + 500 * 1000 ** 3


def test_renew_or_create_carries_over_for_existing_user(settings_stub, monkeypatch, isolated_state):
    monkeypatch.setattr(outline, "myanmar_now", lambda: datetime(2026, 10, 2))

    def fake_get(url, **kw):
        if url.endswith("/access-keys"):
            return FakeResp({"accessKeys": [
                {"id": "k9", "name": "Aung (999) 20.10.2026", "accessUrl": "ss://u"},
            ]})
        if url.endswith("/metrics/transfer"):
            return FakeResp({"bytesTransferredByUserId": {}})
        return FakeResp({})

    captured = {}

    def fake_put(url, **kw):
        if url.endswith("/name"):
            captured["name"] = kw.get("data", {}).get("name")
        return FakeResp({})

    monkeypatch.setattr(outline.requests, "get", fake_get)
    monkeypatch.setattr(outline.requests, "put", fake_put)

    final_key, updated_name, new_expire, renewed = outline.renew_or_create_unlimited_key(
        "1", "Aung", "999", months_count=1,
    )

    assert renewed is True
    assert new_expire == "20.11.2026"
    assert captured["name"] == "Aung (999) 20.11.2026"
