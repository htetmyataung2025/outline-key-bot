"""Facebook promo keys (Bot Update #18): agent endpoint + claim rules.

Storage is an in-memory stand-in for the promo module's redis helpers;
``create_outline_key`` is monkeypatched so no Outline server is hit.
Bot Update #22 raised the cap to 100 and moved code delivery into the
Telegram bot (``/start promo``).
"""

import pytest

from bot_app.services import promo

CUSTOMER = 555000222
SECRET = {"X-Support-Agent-Secret": "test-secret"}
URL = "/api/app/support/agent/promo-key"


class BotStub:
    def __init__(self):
        self.sent = []  # (chat_id, text, kwargs)

    def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))


@pytest.fixture()
def store(monkeypatch):
    data = {}

    def _set_nx(key, ttl, value="1"):
        if key in data:
            return False
        data[key] = value
        return True

    monkeypatch.setattr(promo, "redis_get", lambda key: data.get(key))
    monkeypatch.setattr(promo, "redis_set",
                        lambda key, value: data.__setitem__(key, value))
    monkeypatch.setattr(promo, "redis_delete",
                        lambda key: data.pop(key, None))
    monkeypatch.setattr(promo, "redis_set_nx", _set_nx)
    monkeypatch.setattr(promo, "push_app_notification", lambda *a, **k: None)
    monkeypatch.setattr(promo, "save_user_purchase_record", lambda **k: None)
    monkeypatch.setattr(promo, "save_key_mapping", lambda *a, **k: None)
    monkeypatch.setattr(promo, "get_user_profile",
                        lambda cid: {"full_name": "Aung Khant"})
    monkeypatch.setattr(promo, "bot", BotStub())
    monkeypatch.setattr(promo, "get_key_delivery_markup", lambda k: None)
    monkeypatch.setattr(promo, "load_persistent_keys", lambda: {})
    monkeypatch.setattr(promo, "load_all_user_history", lambda: {})
    monkeypatch.setattr(promo, "is_admin", lambda cid: False)
    return data


@pytest.fixture()
def created(monkeypatch):
    calls = []

    def _fake(server_num, user_name, **kwargs):
        calls.append({"server": server_num, "name": user_name, **kwargs})
        return ("ss://fake-key#k", "Aung Khant [GW] 25.11.2026", "25.11.2026")

    monkeypatch.setattr(promo, "create_outline_key", _fake)
    return calls


def test_promo_endpoint_needs_secret(client, store, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    assert client.post(URL, json={"chat_id": CUSTOMER,
                                  "code": promo.PROMO_CODE}).status_code == 401
    bad = {"X-Support-Agent-Secret": "wrong"}
    assert client.post(URL, headers=bad,
                       json={"chat_id": CUSTOMER,
                             "code": promo.PROMO_CODE}).status_code == 401


def test_promo_bad_code_rejected(client, store, created, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    resp = client.post(URL, headers=SECRET,
                       json={"chat_id": CUSTOMER, "code": "WRONGCODE"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_code"
    assert created == []


def test_promo_claim_success(client, store, created, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    # The code match is case-insensitive (customers type it by hand).
    resp = client.post(URL, headers=SECRET,
                       json={"chat_id": CUSTOMER, "code": "hefreeforyou"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["vpn_key"].startswith("ss://")
    assert body["expire_date"] == "25.11.2026"
    assert len(created) == 1
    call = created[0]
    assert call["server"] == "2"
    assert call["name"] == "Aung Khant"
    assert call["custom_gb"] == 10
    assert call["custom_days"] == 5
    assert call["is_giveaway"] is True
    assert call["target_chat_id"] == str(CUSTOMER)


def test_promo_one_claim_per_user(client, store, created, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    first = client.post(URL, headers=SECRET,
                        json={"chat_id": CUSTOMER, "code": promo.PROMO_CODE})
    assert first.status_code == 200
    second = client.post(URL, headers=SECRET,
                         json={"chat_id": CUSTOMER, "code": promo.PROMO_CODE})
    assert second.status_code == 409
    assert second.get_json()["error"] == "already_claimed"
    assert len(created) == 1


def test_promo_cap_reached(client, store, created, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    store[promo._CLAIMS_KEY] = {
        str(900000000 + i): {"ts": 1, "key_name": "k", "expire_date": "x"}
        for i in range(promo.PROMO_CAP)
    }
    resp = client.post(URL, headers=SECRET,
                       json={"chat_id": CUSTOMER, "code": promo.PROMO_CODE})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "cap_reached"
    assert created == []


def test_promo_failed_creation_can_retry(client, store, created, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    monkeypatch.setattr(promo, "create_outline_key",
                        lambda *a, **k: (None, None, None))
    resp = client.post(URL, headers=SECRET,
                       json={"chat_id": CUSTOMER, "code": promo.PROMO_CODE})
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "key_creation_failed"
    # The failed attempt must not burn the customer's one claim.
    assert promo._load_claims() == {}


def test_promo_claim_sends_telegram_dm(client, store, created, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    resp = client.post(URL, headers=SECRET,
                       json={"chat_id": CUSTOMER, "code": promo.PROMO_CODE})
    assert resp.status_code == 200
    # Support Chat text cannot be copied in the app, so the key is also
    # delivered by Telegram DM in a tap-to-copy <code> block.
    assert len(promo.bot.sent) == 1
    chat_id, text, _kwargs = promo.bot.sent[0]
    assert str(chat_id) == str(CUSTOMER)
    assert "ss://fake-key#k" in text


def test_promo_admin_unlimited_claims(client, store, created, monkeypatch):
    # The owner (admin) can claim repeatedly for testing, and admin
    # claims never consume the 100-customer cap.
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    monkeypatch.setattr(promo, "is_admin", lambda cid: True)
    for _ in range(2):
        resp = client.post(URL, headers=SECRET,
                           json={"chat_id": CUSTOMER,
                                 "code": promo.PROMO_CODE})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
    assert len(created) == 2
    assert promo._load_claims() == {}


def test_promo_reclaim_redelivers_and_repairs(client, store, created,
                                              monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    store[promo._CLAIMS_KEY] = {
        str(CUSTOMER): {
            "ts": 1,
            "key_name": "Aung Khant [GW] 25.11.2026",
            "expire_date": "25.11.2026",
            "order_id": "PROMO-ABC123",
        }
    }
    monkeypatch.setattr(promo, "load_persistent_keys", lambda: {
        "2_99": {
            "name": "Aung Khant [GW] 25.11.2026",
            "access_url": "ss://reg-key#x",
            "server": "2",
            "order_id": "PROMO-ABC123",
            "expire_date": "25.11.2026",
        }
    })
    written = []
    monkeypatch.setattr(promo, "save_user_purchase_record",
                        lambda **k: written.append(k))
    # History has no record for the claim -> the repair must write one.
    monkeypatch.setattr(promo, "load_all_user_history", lambda: {})

    resp = client.post(URL, headers=SECRET,
                       json={"chat_id": CUSTOMER, "code": promo.PROMO_CODE})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "already_claimed"
    assert body["vpn_key"] == "ss://reg-key#x"
    assert created == []  # never creates a second key
    assert len(written) == 1
    assert written[0]["order_id"] == "PROMO-ABC123"
    assert written[0]["vpn_key"] == "ss://reg-key#x"
    assert len(promo.bot.sent) == 1  # key DM'd again
    assert "ss://reg-key#x" in promo.bot.sent[0][1]


# --- Bot Update #22: cap 100 + bot-side code delivery -------------------------

def test_promo_cap_is_100(store):
    assert promo.PROMO_CAP == 100
    status = promo.promo_status()
    assert status["cap"] == 100
    assert status["remaining"] == 100


def test_promo_bot_message_has_code_cap_and_linking_steps():
    text = promo.promo_bot_message()
    assert promo.PROMO_CODE in text
    assert "100" in text
    # The claim happens in Support Chat, which needs a linked app — the
    # message must walk the customer through linking first.
    assert "ချိတ်ပါ" in text
    assert "Support Chat" in text
