"""Tests for Admin Key Management endpoints."""

import requests

from bot_app.services.registry import load_persistent_keys, save_persistent_key

ADMIN_ID = 111000111


def test_list_and_filter_keys(client, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(
        server_num="1",
        key_id="1",
        name="vip_user_alice 20.10.2026",
        access_url="ss://conf1",
        chat_id="12345",
    )
    save_persistent_key(
        server_num="2",
        key_id="2",
        name="basic_user_bob 25.10.2026",
        access_url="ss://conf2",
        chat_id="67890",
    )

    # List all (sync=0 keeps this hermetic — we only exercise registry filtering here)
    resp = client.get("/api/admin/keys?sync=0", headers=headers)
    assert resp.status_code == 200
    assert resp.json["total"] >= 2

    # Filter by server
    resp_srv1 = client.get("/api/admin/keys?sync=0&server_id=1", headers=headers)
    assert resp_srv1.status_code == 200
    assert all(k["server"] == "1" for k in resp_srv1.json["items"])

    # Search by username
    resp_search = client.get("/api/admin/keys?sync=0&search=alice", headers=headers)
    assert resp_search.status_code == 200
    assert len(resp_search.json["items"]) == 1
    assert "alice" in resp_search.json["items"][0]["name"]


def test_list_excludes_synthesized_history_rows(client, make_telegram_init_data):
    """sale_*/ord_* rows mirror sales/orders for customer search; they are not
    real Outline keys (no access URL, their 'expire_date' is the purchase date),
    so the key manager must not list them."""
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    import json

    from bot_app.storage.kv import redis_set
    from bot_app.storage.paths import PERSISTENT_KEYS_FILE

    registry = {
        "1_1": {"server": "1", "key_id": "1", "name": "real_key 20.10.2026",
                "access_url": "ss://real", "expire_date": "20.10.2026"},
        "1_sale_60": {"server": "1", "key_id": "sale_60", "name": "Basic Plan (555)",
                      "access_url": "N/A", "expire_date": "2026-10-01"},
        "1_ord_AB12": {"server": "1", "key_id": "ord_AB12", "name": "Starter Plan (777)",
                       "access_url": "N/A", "expire_date": "2026-09-21"},
    }
    redis_set("persistent_keys_registry", registry)
    with open(PERSISTENT_KEYS_FILE, "w") as f:
        json.dump(registry, f)

    resp = client.get("/api/admin/keys?sync=0", headers=headers)
    assert resp.status_code == 200
    ids = {k["key_id"] for k in resp.json["items"]}
    assert ids == {"1"}
    assert resp.json["total"] == 1


def test_extend_key_expiry(client, make_telegram_init_data, monkeypatch):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    # Keep hermetic: no live server, so extend just updates the local registry.
    monkeypatch.setattr("bot_app.services.outline.get_server_api_url", lambda sid: None)

    # Far-future expiry: the endpoint extends from the stored date only when it
    # is still ahead of "now", so a near-date here would make this test
    # time-bombed (base silently becomes today once the date passes).
    save_persistent_key(
        server_num="1",
        key_id="99",
        name="expiring_user 01.01.2030",
        access_url="ss://conf99",
    )

    resp = client.post(
        "/api/admin/keys/99/extend",
        json={"add_days": 30},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert data["new_expire_date"] == "31/01/2030"
    assert data["data_topup"] == {"applied": False, "add_gb": 0}

    # Verify persisted in storage
    registry = load_persistent_keys()
    assert registry["1_99"]["expire_date"] == "31/01/2030"


GB = 1000 ** 3


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_extend_key_with_data_topup(client, make_telegram_init_data, monkeypatch):
    """add_gb > 0 raises the Outline lifetime cap to (used + add_gb) — the same
    carry-over rule as the Ultimate renewal — and persists the new limit."""
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(
        server_num="1",
        key_id="77",
        name="capped_user 01.01.2030",
        access_url="ss://conf77",
    )

    monkeypatch.setattr(
        "bot_app.services.outline.get_server_api_url",
        lambda sid: "https://sg1.example.com/api",
    )

    puts = []

    def fake_get(url, *a, **k):
        if "/metrics/transfer" in url:
            return _Resp(200, {"bytesTransferredByUserId": {"77": 30 * GB}})
        if "/access-keys" in url:
            return _Resp(200, {"accessKeys": [
                {"id": "77", "name": "capped_user 01.01.2030", "accessUrl": "ss://conf77"},
            ]})
        return _Resp(404, {})

    def fake_put(url, *a, **k):
        puts.append((url, k))
        return _Resp(204)

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.put", fake_put)

    resp = client.post(
        "/api/admin/keys/77/extend",
        json={"add_days": 30, "add_gb": 50},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json
    assert body["success"] is True
    assert body["data_topup"]["applied"] is True
    assert body["data_topup"]["new_limit_bytes"] == 80 * GB   # 30 used + 50 fresh

    limit_puts = [(u, kw) for u, kw in puts if "/data-limit" in u]
    assert len(limit_puts) == 1
    assert limit_puts[0][1]["json"] == {"limit": {"bytes": 80 * GB}}

    registry = load_persistent_keys()
    assert registry["1_77"]["limit_bytes"] == 80 * GB
    assert registry["1_77"]["expire_date"] == "31/01/2030"


def test_extend_topup_1tb_bytes(client, make_telegram_init_data, monkeypatch):
    """1 TB chip = 1000 GB = 10**12 bytes on the wire; app uses decimal GB."""
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(
        server_num="1",
        key_id="55",
        name="tb_user 01.01.2030",
        access_url="ss://conf55",
    )

    monkeypatch.setattr(
        "bot_app.services.outline.get_server_api_url",
        lambda sid: "https://sg1.example.com/api",
    )

    puts = []

    def fake_get(url, *a, **k):
        if "/metrics/transfer" in url:
            return _Resp(200, {"bytesTransferredByUserId": {"55": 999 * GB}})
        if "/access-keys" in url:
            return _Resp(200, {"accessKeys": []})
        return _Resp(404, {})

    def fake_put(url, *a, **k):
        puts.append((url, k))
        return _Resp(204)

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.put", fake_put)

    resp = client.post(
        "/api/admin/keys/55/extend",
        json={"add_days": 30, "add_gb": 1000},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json["data_topup"]["new_limit_bytes"] == (999 + 1000) * GB

    limit_puts = [(u, kw) for u, kw in puts if "/data-limit" in u]
    assert limit_puts[0][1]["json"] == {"limit": {"bytes": (999 + 1000) * GB}}


def test_extend_topup_failure_still_extends_days(client, make_telegram_init_data, monkeypatch):
    """An unreachable Outline server must not block the day-extension: the
    response flags the failed top-up so the admin can retry just the data."""
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(
        server_num="1",
        key_id="88",
        name="offline_user 01.01.2030",
        access_url="ss://conf88",
    )

    monkeypatch.setattr(
        "bot_app.services.outline.get_server_api_url",
        lambda sid: "https://sg1.example.com/api",
    )

    def unreachable(url, *a, **k):
        raise requests.exceptions.ConnectionError("server down")

    monkeypatch.setattr("requests.get", unreachable)
    monkeypatch.setattr("requests.put", unreachable)

    resp = client.post(
        "/api/admin/keys/88/extend",
        json={"add_days": 30, "add_gb": 50},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json
    assert body["success"] is True
    assert body["new_expire_date"] == "31/01/2030"
    assert body["data_topup"]["applied"] is False
    assert body["data_topup"]["error"]

    registry = load_persistent_keys()
    assert registry["1_88"]["expire_date"] == "31/01/2030"


def test_list_keys_syncs_live_server_keys(client, make_telegram_init_data, monkeypatch):
    """GET /keys should pull keys that live on the Outline servers, not only
    registry-created ones."""
    import time as _time

    import bot_app.routes_admin as ra

    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    # Force the throttle window open regardless of its configured length
    # (monotonic can still be < LIVE_SYNC_MIN_INTERVAL on a fresh CI runner).
    monkeypatch.setattr(ra, "_last_live_sync", _time.monotonic() - 10_000)

    monkeypatch.setattr(
        "bot_app.services.outline.get_configured_servers",
        lambda: [{"id": 1, "name": "S1", "api_url": "https://dummy.local:9000/secret"}],
    )

    class FakeResp:
        status_code = 200

        def json(self):
            return {"accessKeys": [{"id": "5001", "name": "liveuser (999) 05.05.2027", "accessUrl": "ss://live"}]}

    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResp())

    resp = client.get("/api/admin/keys", headers=headers)
    assert resp.status_code == 200
    names = [k["name"] for k in resp.json["items"]]
    assert any("liveuser" in n for n in names)


def test_list_keys_joins_usage_bytes(client, make_telegram_init_data, monkeypatch):
    """GET /keys must join live per-key usage (bytes_used) from /metrics/transfer
    alongside the key's quota (limit_bytes)."""
    import bot_app.services.outline as ol
    ol._usage_cache.clear()

    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    monkeypatch.setattr(
        "bot_app.services.outline.get_configured_servers",
        lambda: [{"id": 1, "name": "S1", "api_url": "https://dummy.local:9000/secret"}],
    )

    class KeysResp:
        status_code = 200

        def json(self):
            return {
                "accessKeys": [
                    {
                        "id": "5001",
                        "name": "quota_user (999) 05.05.2027",
                        "accessUrl": "ss://live",
                        "dataLimit": {"bytes": 10 * 1000 ** 3},
                    }
                ]
            }

    class MetricsResp:
        status_code = 200

        def json(self):
            return {"bytesTransferredByUserId": {"5001": 4 * 1000 ** 3}}

    def fake_get(url, *a, **k):
        return MetricsResp() if "metrics/transfer" in url else KeysResp()

    monkeypatch.setattr("requests.get", fake_get)

    resp = client.get("/api/admin/keys?sync=force", headers=headers)
    assert resp.status_code == 200
    key = next(k for k in resp.json["items"] if k["key_id"] == "5001")
    assert key["limit_bytes"] == 10 * 1000 ** 3
    assert key["bytes_used"] == 4 * 1000 ** 3


def test_list_keys_usage_none_when_metrics_unavailable(client, make_telegram_init_data, monkeypatch):
    """An unreachable /metrics/transfer must not break the list: the key is still
    returned with bytes_used = None so the dashboard shows a dash."""
    import bot_app.services.outline as ol
    ol._usage_cache.clear()

    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    monkeypatch.setattr(
        "bot_app.services.outline.get_configured_servers",
        lambda: [{"id": 7, "name": "S7", "api_url": "https://dummy.local:9000/secret"}],
    )

    class KeysResp:
        status_code = 200

        def json(self):
            return {"accessKeys": [{"id": "6002", "name": "nolimit_user 05.05.2027", "accessUrl": "ss://live"}]}

    class MetricsDown:
        status_code = 500

        def json(self):
            return {}

    def fake_get(url, *a, **k):
        return MetricsDown() if "metrics/transfer" in url else KeysResp()

    monkeypatch.setattr("requests.get", fake_get)

    resp = client.get("/api/admin/keys?sync=force", headers=headers)
    assert resp.status_code == 200
    key = next(k for k in resp.json["items"] if k["key_id"] == "6002")
    assert key["bytes_used"] is None


def test_list_keys_skips_usage_when_sync_disabled(client, make_telegram_init_data, monkeypatch):
    """sync=0 keeps the read hermetic: no server probe for usage, bytes_used=None."""
    import bot_app.services.outline as ol
    ol._usage_cache.clear()

    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    def boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("usage must not be fetched when sync=0")

    monkeypatch.setattr("bot_app.services.outline.get_usage_by_server", boom)

    save_persistent_key(
        server_num="1",
        key_id="8001",
        name="hermetic_user 20.10.2026",
        access_url="ss://conf",
    )

    resp = client.get("/api/admin/keys?sync=0", headers=headers)
    assert resp.status_code == 200
    key = next(k for k in resp.json["items"] if k["key_id"] == "8001")
    assert key["bytes_used"] is None


def test_delete_key(client, make_telegram_init_data, monkeypatch):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(
        server_num="1",
        key_id="777",
        name="deleteme 01.01.2027",
        access_url="ss://confdel",
    )

    monkeypatch.setattr(
        "bot_app.services.outline.get_server_api_url",
        lambda sid: "https://dummy.local:9000/secret",
    )

    class FakeResp:
        status_code = 204

    monkeypatch.setattr("requests.delete", lambda *a, **k: FakeResp())

    resp = client.delete("/api/admin/keys/1/777", headers=headers)
    assert resp.status_code == 200
    assert resp.json["success"] is True

    registry = load_persistent_keys()
    assert "1_777" not in registry


def test_delete_key_unconfigured_server(client, make_telegram_init_data, monkeypatch):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    monkeypatch.setattr("bot_app.services.outline.get_server_api_url", lambda sid: None)

    resp = client.delete("/api/admin/keys/9/123", headers=headers)
    assert resp.status_code == 400
    assert "error" in resp.json


def test_keys_live_sync_throttled_and_force_bypasses(client, make_telegram_init_data, monkeypatch):
    """Page visits within the throttle window must reuse the cached registry;
    ?sync=force always re-syncs (the probe costs 1-2s per visit otherwise)."""
    import time as _time

    import bot_app.routes_admin as ra

    calls = {"n": 0}

    def fake_refresh():
        calls["n"] += 1

    monkeypatch.setattr("bot_app.services.outline.refresh_registry_from_servers", fake_refresh)
    # Usage join also probes servers; stub it so this test stays network-free
    # and only asserts the live-sync throttle behaviour.
    monkeypatch.setattr("bot_app.services.outline.get_usage_by_server", lambda *a, **k: {})
    # Start stale relative to the monotonic base (not 0.0) so the first visit
    # re-syncs even on a fresh CI runner where time.monotonic() is still small.
    monkeypatch.setattr(ra, "_last_live_sync", _time.monotonic() - 10_000)

    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}

    assert client.get("/api/admin/keys", headers=headers).status_code == 200
    assert client.get("/api/admin/keys", headers=headers).status_code == 200
    assert calls["n"] == 1

    assert client.get("/api/admin/keys?sync=force", headers=headers).status_code == 200
    assert calls["n"] == 2

    assert client.get("/api/admin/keys?sync=0", headers=headers).status_code == 200
    assert calls["n"] == 2


def _fmt(days_delta):
    from datetime import datetime, timedelta

    return (datetime.now() + timedelta(days=days_delta)).strftime("%d.%m.%Y")


def test_delete_expired_keys_sweep(client, make_telegram_init_data, monkeypatch):
    """The sweep permanently removes expired keys (server + registry) and
    leaves everything else: active keys, unparseable dates, VIP/manual keys,
    synthesized history rows, and keys on unreachable servers."""
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    headers = {"X-Telegram-Init-Data": init_data}

    save_persistent_key(server_num="1", key_id="101", name=f"old_user {_fmt(-40)}",
                        access_url="ss://old1")
    save_persistent_key(server_num="1", key_id="102", name=f"fresh_user {_fmt(30)}",
                        access_url="ss://fresh")
    save_persistent_key(server_num="2", key_id="201", name=f"gone_user {_fmt(-10)}",
                        access_url="ss://gone")
    save_persistent_key(server_num="1", key_id="103", name=f"stuck_user {_fmt(-5)}",
                        access_url="ss://stuck")
    save_persistent_key(server_num="1", key_id="104", name="nodate_user",
                        access_url="ss://nodate")
    save_persistent_key(server_num="VIP", key_id="custom_1", name=f"vip_user {_fmt(-90)}",
                        access_url="ss://vip")
    save_persistent_key(server_num="1", key_id="sale_9", name=f"Basic Plan {_fmt(-90)}",
                        access_url="N/A")

    monkeypatch.setattr(
        "bot_app.services.outline.refresh_registry_from_servers", lambda: None)
    monkeypatch.setattr(
        "bot_app.services.outline.resolve_server_api_url",
        lambda sid: "https://dummy.local:9000/secret",
    )

    class FakeResp:
        def __init__(self, status_code):
            self.status_code = status_code

    def fake_delete(url, **kwargs):
        if url.endswith("/103"):
            raise ConnectionError("unreachable")
        if url.endswith("/201"):
            return FakeResp(404)  # already gone from the server
        return FakeResp(204)

    monkeypatch.setattr("requests.delete", fake_delete)

    resp = client.post("/api/admin/keys/delete-expired", headers=headers)
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert data["expired_found"] == 3
    assert data["deleted"] == 2
    assert [f["key_id"] for f in data["failed"]] == ["103"]
    assert data["skipped_unknown_date"] >= 1
    assert data["skipped_vip"] == 1

    registry = load_persistent_keys()
    assert "1_101" not in registry       # expired, deleted
    assert "2_201" not in registry       # expired, 404 on server, still cleaned
    assert "1_102" in registry           # active, untouched
    assert "1_103" in registry           # unreachable server, kept
    assert "1_104" in registry           # unknown expiry, kept
    assert "VIP_custom_1" in registry    # VIP/manual, skipped
    assert "1_sale_9" in registry        # synthesized history row, excluded


def test_delete_expired_keys_requires_admin(client, make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=999888777, username="not_admin")
    resp = client.post(
        "/api/admin/keys/delete-expired",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert resp.status_code in (401, 403)
