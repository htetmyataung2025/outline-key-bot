"""Regression tests for multi-server routing.

Background: before this fix, every key-issuance + server-lookup path resolved
the Outline API URL via a hard-coded ternary that clamped *any* server id other
than 1/2 to Server 3's URL. So once "Server 4" was added via the Settings page,
issuing from Server 4 actually hit Server 3's host. These tests pin the fix.
"""

import pytest

from bot_app.services import outline, settings as settings_svc


# A Settings-page layout with Server 4 (the id that used to fall through).
_SERVERS = [
    {"id": 1, "name": "Server 1 (SG-1)", "api_url": "https://sg1.example.com/api"},
    {"id": 2, "name": "Server 2 (SG-2)", "api_url": "https://sg2.example.com/api"},
    {"id": 3, "name": "Server 3 (VIP)", "api_url": "https://vip.example.com/api"},
    {"id": 4, "name": "Server 4 (IN)", "api_url": "https://in.example.com/api"},
]


@pytest.fixture
def settings_stub(monkeypatch):
    """Pin the dynamic settings store so tests are deterministic (no .env bleed)."""
    monkeypatch.setattr(
        settings_svc, "get_system_settings",
        lambda force_refresh=False: {"servers": _SERVERS},
    )
    monkeypatch.setattr(settings_svc, "invalidate_settings_cache", lambda reset_fallback=False: None)
    # Drop the env fallbacks so resolve_server_api_url is decided solely by settings.
    import bot_app.config as cfg
    monkeypatch.setattr(cfg, "OUTLINE_API_URL_1", "")
    monkeypatch.setattr(cfg, "OUTLINE_API_URL_2", "")
    monkeypatch.setattr(cfg, "OUTLINE_API_URL_3", "")


class FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


# ---------------------------------------------------------------------------
# resolve_server_api_url / server_num_for_api_url
# ---------------------------------------------------------------------------

def test_resolve_url_picks_server_4_from_settings(settings_stub):
    assert outline.resolve_server_api_url("4") == "https://in.example.com/api"
    assert outline.resolve_server_api_url(4) == "https://in.example.com/api"


def test_resolve_url_unknown_server_returns_empty(settings_stub):
    assert outline.resolve_server_api_url("99") == ""


def test_server_num_for_api_url_round_trips_all_servers(settings_stub):
    for srv in _SERVERS:
        assert outline.server_num_for_api_url(srv["api_url"]) == str(srv["id"])


# ---------------------------------------------------------------------------
# create_outline_key: must POST to the Server-4 host, not Server 3.
# ---------------------------------------------------------------------------

def test_create_key_on_server_4_hits_server_4(settings_stub, monkeypatch, isolated_state):
    posted = []

    def fake_post(url, **kw):
        posted.append(url)
        return FakeResp({"id": "k-xyz", "accessUrl": "ss://created"})

    def fake_put(url, **kw):
        return FakeResp({})

    monkeypatch.setattr(outline.requests, "post", fake_post)
    monkeypatch.setattr(outline.requests, "put", fake_put)

    key, name, exp = outline.create_outline_key(
        "4", "TestUser", plan_info={"bytes": 500}, target_chat_id="7654321",
        custom_days=30, is_giveaway=False,
    )
    assert key is not None
    assert len(posted) == 1
    assert posted[0].startswith("https://in.example.com/api/access-keys"), posted
    # persisted registry records the right server id
    from bot_app.services.registry import load_persistent_keys
    reg = load_persistent_keys()
    assert "4_k-xyz" in reg
    assert reg["4_k-xyz"]["server"] == "4"


def test_create_key_on_server_3_still_routes_to_server_3(settings_stub, monkeypatch, isolated_state):
    posted = []

    def fake_post(url, **kw):
        posted.append(url)
        return FakeResp({"id": "k-3", "accessUrl": "ss://created"})

    monkeypatch.setattr(outline.requests, "post", fake_post)
    monkeypatch.setattr(outline.requests, "put", lambda *a, **k: FakeResp({}))

    outline.create_outline_key("3", "TestUser", custom_days=7)
    assert posted[0].startswith("https://vip.example.com/api/access-keys"), posted


def test_create_key_on_unconfigured_server_no_op(settings_stub, monkeypatch, isolated_state):
    """A server id with no URL must NOT silently fall back to Server 3."""
    posted = []

    def fake_post(url, **kw):
        posted.append(url)
        return FakeResp({"id": "k-x", "accessUrl": "ss://created"})

    monkeypatch.setattr(outline.requests, "post", fake_post)
    monkeypatch.setattr(outline.requests, "put", lambda *a, **k: FakeResp({}))

    key, name, exp = outline.create_outline_key("999", "TestUser", custom_days=7)
    assert key is None
    assert posted == []  # never attempted an Outline call


# ---------------------------------------------------------------------------
# iter_configured_server_urls: dynamic servers are visible, env fallback gone
# ---------------------------------------------------------------------------

def test_iter_urls_yields_server_4(settings_stub):
    urls = list(outline.iter_configured_server_urls())
    assert "https://in.example.com/api" in urls
    assert len(urls) == 4


def test_iter_urls_env_fallback_only_when_no_settings(monkeypatch):
    """When Settings has no servers, the legacy env slots 1-3 are used."""
    import bot_app.config as cfg
    monkeypatch.setattr(settings_svc, "get_system_settings",
                        lambda force_refresh=False: {"servers": []})
    monkeypatch.setattr(cfg, "OUTLINE_API_URL_1", "https://env1.example.com/api")
    monkeypatch.setattr(cfg, "OUTLINE_API_URL_2", "https://env2.example.com/api")
    monkeypatch.setattr(cfg, "OUTLINE_API_URL_3", "")
    urls = list(outline.iter_configured_server_urls())
    assert urls == ["https://env1.example.com/api", "https://env2.example.com/api"]
