"""Tests for the Admin unified Purchases History endpoint."""

from datetime import timedelta

from bot_app.services.orders import (
    save_sale_transaction,
    save_user_purchase_record,
)

ADMIN_ID = 111000111


def _admin_headers(make_telegram_init_data):
    return {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}


def test_purchases_requires_auth(client):
    resp = client.get("/api/admin/purchases")
    assert resp.status_code == 401


def test_purchase_merged_across_stores(client, make_telegram_init_data):
    """One wallet purchase written to BOTH stores must show as one item with
    the numeric price from sales_history and the key details from history."""
    headers = _admin_headers(make_telegram_init_data)
    save_sale_transaction("1", "555", "starter", "Starter Plan", 1, 5000, order_id="#AAAAAA")
    save_user_purchase_record(
        chat_id="555", order_id="#AAAAAA", plan_name="Starter Plan", disp_gb="25 GB",
        months_count=1, price_str="5,000 Ks", server_num="1",
        expire_date="02.11.2026", vpn_key="ss://merged",
    )

    data = client.get("/api/admin/purchases", headers=headers).json
    items = [i for i in data["items"] if i["order_id"] == "#AAAAAA"]
    assert len(items) == 1
    item = items[0]
    assert item["source"] == "both"
    assert item["price"] == 5000
    assert item["disp_gb"] == "25 GB"
    assert item["vpn_key"] == "ss://merged"
    assert item["expire_date"] == "02.11.2026"
    assert item["chat_id"] == "555"
    assert item["kind"] == "paid"


def test_points_record_kept_but_not_in_revenue(client, make_telegram_init_data):
    """Points redemptions exist only in user_purchases_data: they must appear
    (kind=points) but never count toward revenue."""
    headers = _admin_headers(make_telegram_init_data)
    save_user_purchase_record(
        chat_id="777", order_id="#POINTS1", plan_name="Starter Plan (Points Reward)",
        disp_gb="25 GB", months_count=1, price_str="0 Ks (Points)", server_num="1",
        expire_date="02.11.2026", vpn_key="ss://free",
    )

    data = client.get("/api/admin/purchases", headers=headers).json
    item = next(i for i in data["items"] if i["order_id"] == "#POINTS1")
    assert item["kind"] == "points"
    assert data["summary"]["today_count"] >= 1
    # Revenue for today must not include the points record's 0 — and since it
    # is the only record, revenue stays 0 while count >= 1.
    assert data["summary"]["today_revenue_ks"] == 0


def test_vip_sale_and_filters(client, make_telegram_init_data):
    headers = _admin_headers(make_telegram_init_data)
    save_sale_transaction("VIP", "1001", "vip5", "5 Device VIP", 1, 20000, order_id="#VIP001")
    save_sale_transaction("2", "1002", "basic", "Basic Plan", 1, 3000, order_id="#SRV002")

    data = client.get("/api/admin/purchases", headers=headers).json
    assert {i["order_id"] for i in data["items"]} >= {"#VIP001", "#SRV002"}
    vip_item = next(i for i in data["items"] if i["order_id"] == "#VIP001")
    assert vip_item["server_name"] == "VIP"

    # server filter (exact string, "VIP" included)
    resp = client.get("/api/admin/purchases?server=VIP", headers=headers).json
    assert [i["order_id"] for i in resp["items"]] == ["#VIP001"]

    # search matches chat_id
    resp = client.get("/api/admin/purchases?q=1002", headers=headers).json
    assert [i["order_id"] for i in resp["items"]] == ["#SRV002"]


def test_days_window_and_newest_first(client, make_telegram_init_data, monkeypatch):
    headers = _admin_headers(make_telegram_init_data)
    # Old sale: 30 days back (outside a 7-day window).
    import bot_app.services.orders as orders_mod
    import bot_app.timeutil as timeutil

    real_now = timeutil.myanmar_now
    monkeypatch.setattr(orders_mod, "myanmar_now", lambda: real_now() - timedelta(days=30))
    save_sale_transaction("1", "2001", "starter", "Starter Plan", 1, 5000, order_id="#OLD0001")
    monkeypatch.setattr(orders_mod, "myanmar_now", real_now)
    save_sale_transaction("1", "2002", "starter", "Starter Plan", 1, 5000, order_id="#NEW0002")

    data = client.get("/api/admin/purchases", headers=headers).json
    ids = [i["order_id"] for i in data["items"]]
    assert ids == ["#NEW0002", "#OLD0001"]  # newest first

    windowed = client.get("/api/admin/purchases?days=7", headers=headers).json
    assert [i["order_id"] for i in windowed["items"]] == ["#NEW0002"]
    # Summary is computed before the days window: the old sale sits in the
    # previous month (30 days back), so only the fresh purchase counts in the
    # current-month counters.
    assert windowed["summary"]["month_count"] == 1
    assert windowed["summary"]["today_count"] == 1
