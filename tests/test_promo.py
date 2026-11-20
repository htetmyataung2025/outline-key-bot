"""Facebook promo keys (Bot Update #18): agent endpoint + claim rules.

Storage is an in-memory stand-in for the promo module's redis helpers;
``create_outline_key`` is monkeypatched so no Outline server is hit.
"""

import pytest

from bot_app.services import promo

CUSTOMER = 555000222
SECRET = {"X-Support-Agent-Secret": "test-secret"}
URL = "/api/app/support/agent/promo-key"


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
