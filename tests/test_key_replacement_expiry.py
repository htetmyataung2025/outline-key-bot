"""Regression tests: an expired key cannot be replaced via the ♻️ flow.

A replacement reissues the key with its *same* remaining validity, so letting
an already-expired key through would hand the customer a key that is dead on
arrival. Two choke points enforce the rule:

* ``menu.handle_all_messages`` (customer request side) — rejects before the
  admin is ever pinged.
* ``keys.handle_admin_replace_callback`` (admin approval side) — a defence in
  depth guard against a stale approve button.
"""

from datetime import datetime
from types import SimpleNamespace

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.handlers import keys as K
from bot_app.handlers import menu as M
from bot_app.services.states import set_replacement_state

ADMIN = str(ADMIN_CHAT_IDS[0])
CUST = 720000999


def _msg(text, chat_id=CUST):
    return SimpleNamespace(
        text=text,
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=chat_id, first_name="Htet", last_name="", username="htet"),
    )


def _stub_servers_and_fetch(monkeypatch, key_name):
    monkeypatch.setattr(M, "myanmar_now", lambda: datetime(2026, 10, 2))
    monkeypatch.setattr(M, "get_configured_servers",
                        lambda: [{"id": "1", "api_url": "https://s1.example.com/api"}])
    target_key = {"id": "k7", "name": key_name, "accessUrl": "ss://x",
                  "dataLimit": {"bytes": 500 * 1000 ** 3}}
    monkeypatch.setattr(M, "fetch_key_from_server",
                        lambda api_url, inp: (target_key, {}, "2"))


# ---------------------------------------------------------------------------
# Customer request side (menu.handle_all_messages)
# ---------------------------------------------------------------------------

def test_expired_key_request_is_rejected_without_pinging_admin(isolated_state, mock_bot, monkeypatch):
    _stub_servers_and_fetch(monkeypatch, "Htet (720000999) 01.09.2026")  # already lapsed
    set_replacement_state(CUST, True)

    M.handle_all_messages(_msg("Htet (720000999) 01.09.2026"))

    sent = mock_bot.calls["send_message"]
    assert any("သက်တမ်းကုန်ဆုံး" in text for _cid, text in sent), sent
    # No admin ever receives a KEY REPLACEMENT REQUEST.
    assert not any(str(cid) == ADMIN and "REPLACEMENT REQUEST" in text for cid, text in sent), sent


def test_still_valid_key_request_pings_admin(isolated_state, mock_bot, monkeypatch):
    _stub_servers_and_fetch(monkeypatch, "Htet (720000999) 30.11.2026")  # still valid
    set_replacement_state(CUST, True)

    M.handle_all_messages(_msg("Htet (720000999) 30.11.2026"))

    sent = mock_bot.calls["send_message"]
    assert any(str(cid) == ADMIN and "REPLACEMENT REQUEST" in text for cid, text in sent), sent
    assert not any("သက်တမ်းကုန်ဆုံး" in text for _cid, text in sent), sent


# ---------------------------------------------------------------------------
# Admin approval side (keys.handle_admin_replace_callback)
# ---------------------------------------------------------------------------

def _call(exp_date):
    data = f"replace_srv1_2_k7_{CUST}_10.0_{exp_date}"
    return SimpleNamespace(
        id="cb1", data=data,
        message=SimpleNamespace(chat=SimpleNamespace(id=int(ADMIN)), message_id=555, text="req"),
    )


def test_admin_approve_blocked_for_expired_key(isolated_state, mock_bot, monkeypatch):
    monkeypatch.setattr(K, "myanmar_now", lambda: datetime(2026, 10, 2))
    deleted, created = [], []
    monkeypatch.setattr(K.requests, "delete", lambda *a, **k: deleted.append(a))
    monkeypatch.setattr(K, "create_outline_key", lambda *a, **k: created.append(k) or ("ss://n", "n", "x"))

    K.handle_admin_replace_callback(_call("01.09.2026"))

    assert deleted == []       # old key never deleted
    assert created == []       # no new key issued
    # An alert fired telling the admin the key is expired.
    alerts = [
        args[1]
        for args, kw in mock_bot.calls["answer_callback"]
        if kw.get("show_alert") and len(args) > 1
    ]
    assert any("သက်တမ်းကုန်ဆုံး" in text for text in alerts), mock_bot.calls["answer_callback"]


def test_admin_approve_proceeds_for_valid_key(isolated_state, mock_bot, monkeypatch):
    monkeypatch.setattr(K, "myanmar_now", lambda: datetime(2026, 10, 2))
    created = {}
    monkeypatch.setattr(K.requests, "delete", lambda *a, **k: None)
    monkeypatch.setattr(K, "create_outline_key",
                        lambda *a, **k: created.update(k) or ("ss://new#n", "n", "30.11.2026"))

    K.handle_admin_replace_callback(_call("30.11.2026"))

    assert created.get("custom_expire_date") == "30.11.2026"
    assert any(str(cid) == str(CUST) for cid, _t in mock_bot.calls["send_message"])
