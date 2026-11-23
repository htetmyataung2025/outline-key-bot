"""Tests for Bot Update #25: monthly per-server sales stock caps.

Servers whose VPS plan meters inbound + outbound transfer together
(Karvl-style "5 TB") get a monthly sold-quota cap (default 2,500 GB
for Servers 3 and 4). All three buy channels must refuse sales past
the cap with the shared stock-out message, and completed sales must
be recorded against the month's counter. Admins are exempt.
"""

import bot_app.routes_app as ra
import bot_app.services.stock as stock
from bot_app.services.billing import get_user_balance, update_user_balance

STARTER = {"name": "Starter Plan", "data": "25 GB", "bytes": 25 * 1000**3, "price": 1000}
ULTIMATE = {"name": "Ultimate VIP Plan", "data": "500 GB", "bytes": 500 * 1000**3, "price": 10000}


class _FakeCounter:
    """Dict-backed stand-in for the Redis INCRBY counter."""

    def __init__(self):
        self.values = {}

    def __call__(self, key, amount, ttl_seconds):
        self.values[key] = self.values.get(key, 0) + int(amount)
        return self.values[key]


def _use_fake_counter(monkeypatch):
    fake = _FakeCounter()
    monkeypatch.setattr(stock, "redis_incrby_with_expiry", fake)
    return fake


# ---------------------------------------------------------------------------
# plan_gb / caps
# ---------------------------------------------------------------------------

def test_plan_gb_from_bytes_and_data_string():
    assert stock.plan_gb(STARTER) == 25
    assert stock.plan_gb(ULTIMATE) == 500
    assert stock.plan_gb({"data": "75 GB"}) == 75
    assert stock.plan_gb({"name": "Mystery"}) == 0
    assert stock.plan_gb(None) == 0


def test_default_caps_cover_servers_3_and_4_only(monkeypatch):
    monkeypatch.setattr(
        "bot_app.services.settings.get_system_settings", lambda: {})
    assert stock.stock_cap_gb("3") == 2500
    assert stock.stock_cap_gb("4") == 2500
    assert stock.stock_cap_gb("1") is None
    assert stock.stock_cap_gb("2") is None


def test_settings_override_replaces_cap_table(monkeypatch):
    monkeypatch.setattr(
        "bot_app.services.settings.get_system_settings",
        lambda: {"server_stock_gb": {"3": 100}},
    )
    assert stock.stock_cap_gb("3") == 100
    assert stock.stock_cap_gb("4") is None


# ---------------------------------------------------------------------------
# availability + recording
# ---------------------------------------------------------------------------

def test_stock_available_boundary(monkeypatch):
    fake = _use_fake_counter(monkeypatch)
    key = stock._counter_key("3")
    fake.values[key] = 2000
    assert stock.stock_available("3", ULTIMATE) is True   # 2000 + 500 == cap
    fake.values[key] = 2001
    assert stock.stock_available("3", ULTIMATE) is False  # one GB over
    assert stock.stock_available("3", STARTER) is True    # smaller plan fits


def test_stock_available_uncapped_server_always_true(monkeypatch):
    _use_fake_counter(monkeypatch)
    assert stock.stock_available("1", ULTIMATE) is True
    assert stock.stock_available("2", ULTIMATE) is True


def test_record_stock_sale_counts_only_capped_servers(monkeypatch):
    fake = _use_fake_counter(monkeypatch)
    assert stock.record_stock_sale("3", STARTER) == 25
    assert stock.record_stock_sale("3", STARTER) == 50
    assert stock.record_stock_sale("1", STARTER) is None  # uncapped: no write
    assert stock.stock_used_gb("3") == 50
    assert stock.stock_used_gb("1") == 0


def test_stock_check_fails_open_when_redis_unreachable(monkeypatch):
    monkeypatch.setattr(stock, "redis_incrby_with_expiry", lambda *a: None)
    assert stock.stock_used_gb("3") == 0
    assert stock.stock_available("3", ULTIMATE) is True


def test_stock_out_message_names_the_server():
    message = stock.stock_out_message("3")
    assert "Stock ကုန်သွားပါပြီ" in message
    assert "Server 3" in message


# ---------------------------------------------------------------------------
# App buy channel integration
# ---------------------------------------------------------------------------

def _fake_create_key(*args, **kwargs):
    return (
        "ss://Y2hhY2hhMjA6bW9ja0tleUAxMjcuMC4wLjE6MTA4OQ==#User 25.11.2026",
        "User 25.11.2026",
        "25.11.2026",
    )


def test_app_buy_blocked_when_server_stock_out(client, isolated_state, mock_bot, monkeypatch):
    user_id = 555000333
    update_user_balance(user_id, 5000)
    monkeypatch.setattr(ra, "create_outline_key", _fake_create_key)
    monkeypatch.setattr(ra, "stock_available", lambda server, plan: False)

    token = ra._make_app_token(user_id)
    resp = client.post(
        "/api/app/buy",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_code": "starter", "server": "3",
              "idempotency_key": "stock-out-1"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "server_stock_out"
    assert "Stock ကုန်သွားပါပြီ" in data["message"]
    # No money moved and no key was minted.
    assert get_user_balance(user_id) == 5000


def test_app_buy_success_records_stock_sale(client, isolated_state, mock_bot, monkeypatch):
    user_id = 555000444
    update_user_balance(user_id, 5000)
    monkeypatch.setattr(ra, "create_outline_key", _fake_create_key)
    recorded = []
    monkeypatch.setattr(ra, "record_stock_sale",
                        lambda server, plan: recorded.append((server, plan["name"])))

    token = ra._make_app_token(user_id)
    resp = client.post(
        "/api/app/buy",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_code": "starter", "server": "3",
              "idempotency_key": "stock-record-1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert recorded == [("3", "Starter Plan")]


def test_app_buy_admin_is_never_stock_blocked(client, isolated_state, mock_bot, monkeypatch):
    admin_id = 111000111  # ADMIN_CHAT_IDS in conftest env
    monkeypatch.setattr(ra, "create_outline_key", _fake_create_key)
    monkeypatch.setattr(ra, "stock_available", lambda server, plan: False)
    recorded = []
    monkeypatch.setattr(ra, "record_stock_sale",
                        lambda server, plan: recorded.append(server))

    token = ra._make_app_token(admin_id)
    resp = client.post(
        "/api/app/buy",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_code": "starter", "server": "3",
              "idempotency_key": "stock-admin-1"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert recorded == []  # admin sales are not counted either
