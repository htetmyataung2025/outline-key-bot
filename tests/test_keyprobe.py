"""Tests for the /keyprobe admin diagnostic (bot update #7.2).

``diagnose_user_keys`` grades a user's purchase records against the live
Outline servers; the Telegram handler renders the report for admins only.
Zero network: the probe and live-key fetch are monkeypatched.
"""

from types import SimpleNamespace

from bot_app.services.orders import save_user_purchase_record
from bot_app import routes_user


def _seed_two_records(user_id):
    # Live key: no registry entry, but its (host, port) exists live.
    save_user_purchase_record(
        chat_id=user_id, order_id="#ORD-LIVE1", plan_name="Basic Plan",
        disp_gb="50 GB", months_count=1, price_str="2,000 Ks",
        server_num="1", expire_date="19.12.2026",
        vpn_key="ss://Y2hhY2hhMjA6cHc@10.9.9.9:8388#Basic Plan",
    )
    # Deleted key: its port exists nowhere on the live server.
    save_user_purchase_record(
        chat_id=user_id, order_id="#ORD-DEAD1", plan_name="Starter Plan",
        disp_gb="25 GB", months_count=1, price_str="1,000 Ks",
        server_num="1", expire_date="17.12.2026",
        vpn_key="ss://Y2hhY2hhMjA6cHc@10.9.9.9:9999#Starter Plan",
    )


def test_diagnose_grades_records_against_live_servers(isolated_state, monkeypatch):
    user_id = 999333444
    _seed_two_records(user_id)
    monkeypatch.setattr(
        routes_user, "probe_live_servers",
        lambda: {"1": {"ok": True, "count": 1, "error": None}},
    )
    monkeypatch.setattr(
        routes_user, "get_live_keys_by_server",
        lambda *a, **k: {"1": [{"id": "77", "accessUrl": "ss://eA@10.9.9.9:8388"}]},
    )

    report = routes_user.diagnose_user_keys(user_id)

    assert report["servers"] == [
        {"id": "1", "ok": True, "live_keys": 1, "error": None}]
    by_order = {r["order_id"]: r for r in report["records"]}
    assert by_order["#ORD-LIVE1"]["via"] == "port"
    assert by_order["#ORD-LIVE1"]["dropped"] is False
    assert by_order["#ORD-DEAD1"]["via"] == "none"
    assert by_order["#ORD-DEAD1"]["dropped"] is True
    assert by_order["#ORD-DEAD1"]["server_fetched"] is True


def test_diagnose_fails_open_when_server_unreachable(isolated_state, monkeypatch):
    user_id = 999333444
    _seed_two_records(user_id)
    monkeypatch.setattr(
        routes_user, "probe_live_servers",
        lambda: {"1": {"ok": False, "count": None, "error": "HTTP 500"}},
    )
    monkeypatch.setattr(routes_user, "get_live_keys_by_server", lambda *a, **k: {})

    report = routes_user.diagnose_user_keys(user_id)

    assert report["servers"][0]["ok"] is False
    assert all(r["dropped"] is False for r in report["records"])
    assert all(r["server_fetched"] is False for r in report["records"])


_CANNED_REPORT = {
    "servers": [
        {"id": "1", "ok": True, "live_keys": 5, "error": None},
        {"id": "2", "ok": False, "live_keys": None, "error": "HTTP 500"},
    ],
    "records": [
        {"order_id": "#ORD-A", "plan": "Basic Plan", "server": "1",
         "key_id": "3", "via": "id", "server_fetched": True, "dropped": False},
        {"order_id": "#ORD-B", "plan": "Starter Plan", "server": "1",
         "key_id": "", "via": "none", "server_fetched": True, "dropped": True},
        {"order_id": "#ORD-C", "plan": "Pro Plan", "server": "2",
         "key_id": "", "via": "none", "server_fetched": False, "dropped": False},
    ],
}


def test_keyprobe_handler_renders_report_for_admin(isolated_state, mock_bot, monkeypatch):
    from bot_app.handlers import admin as admin_handlers
    monkeypatch.setattr(routes_user, "diagnose_user_keys", lambda uid: _CANNED_REPORT)

    message = SimpleNamespace(chat=SimpleNamespace(id=111000111))
    admin_handlers.handle_keyprobe(message)

    assert len(mock_bot.calls["send_message"]) == 1
    text = mock_bot.calls["send_message"][0][1]
    assert "Live key 5 ခု" in text
    assert "HTTP 500" in text
    assert "ရှိနေသေးတယ်" in text          # alive record
    assert "ဖျောက်ပေးမယ်" in text          # dropped record
    assert "မဖျောက်ဘဲ ထားထားတယ်" in text  # unfetched server record


def test_keyprobe_handler_silent_for_non_admin(isolated_state, mock_bot, monkeypatch):
    from bot_app.handlers import admin as admin_handlers
    monkeypatch.setattr(routes_user, "diagnose_user_keys", lambda uid: _CANNED_REPORT)

    message = SimpleNamespace(chat=SimpleNamespace(id=424242))
    admin_handlers.handle_keyprobe(message)

    assert mock_bot.calls["send_message"] == []


def test_diagnose_flags_recycled_port(isolated_state, monkeypatch):
    """A record whose port is now held by a differently-named live key is
    graded dropped, with the port conflict surfaced for the report."""
    user_id = 999333445
    save_user_purchase_record(
        chat_id=user_id, order_id="#ORD-RECYC", plan_name="Basic Plan",
        disp_gb="50 GB", months_count=1, price_str="2,000 Ks",
        server_num="1", expire_date="19.12.2026",
        vpn_key="ss://cmVj@10.9.9.9:8388#Htet (999333445) 19.12.2026",
    )
    monkeypatch.setattr(
        routes_user, "probe_live_servers",
        lambda: {"1": {"ok": True, "count": 1, "error": None}},
    )
    monkeypatch.setattr(
        routes_user, "get_live_keys_by_server",
        lambda *a, **k: {"1": [{"id": "90", "accessUrl": "ss://eA@10.9.9.9:8388",
                                "name": "Other User (111) 01.01.2027"}]},
    )

    report = routes_user.diagnose_user_keys(user_id)

    assert len(report["records"]) == 1
    rec = report["records"][0]
    assert rec["plan"] == "Basic Plan"
    assert rec["dropped"] is True
    assert rec["port_conflict"] is True
    assert rec["live_name"] == "Other User (111) 01.01.2027"
