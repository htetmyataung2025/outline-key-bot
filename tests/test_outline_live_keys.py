"""Tests for get_live_key_ids_by_server / fetch_access_keys in services/outline.

These power the Mini App bootstrap's "hide keys deleted on the server"
filter. Zero network: requests.get is monkeypatched throughout.
"""

import pytest

from bot_app.services import outline


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setattr(outline, "_is_local_sandbox", lambda: False)
    monkeypatch.setattr(outline, "_live_keys_cache", {})
    yield


def _fake_servers(monkeypatch):
    monkeypatch.setattr(
        outline,
        "get_configured_servers",
        lambda: [
            {"id": "1", "name": "Server 1", "api_url": "https://s1.example/api"},
            {"id": "2", "name": "Server 2", "api_url": "https://s2.example/api"},
        ],
    )


def test_live_key_ids_success_and_failure(monkeypatch):
    _fake_servers(monkeypatch)

    def fake_get(url, verify=False, timeout=None):
        if url.startswith("https://s1.example"):
            return _Resp(200, {"accessKeys": [{"id": "11"}, {"id": 12}, {"name": "no-id"}]})
        raise ConnectionError("unreachable")

    monkeypatch.setattr(outline.requests, "get", fake_get)

    result = outline.get_live_key_ids_by_server()
    # Server 1 answered: ids normalised to str, id-less entries skipped.
    assert result["1"] == {"11", "12"}
    # Server 2 unreachable: omitted entirely (fail-open), NOT an empty set.
    assert "2" not in result


def test_live_key_ids_respects_server_filter(monkeypatch):
    _fake_servers(monkeypatch)
    seen = []

    def fake_get(url, verify=False, timeout=None):
        seen.append(url)
        return _Resp(200, {"accessKeys": [{"id": "7"}]})

    monkeypatch.setattr(outline.requests, "get", fake_get)

    result = outline.get_live_key_ids_by_server(server_ids={"2"})
    assert result == {"2": {"7"}}
    assert seen == ["https://s2.example/api/access-keys"]


def test_live_key_ids_empty_list_is_a_real_answer(monkeypatch):
    """A reachable server with zero keys returns an empty set — that DOES
    mean every key on it is gone (distinct from unreachable/omitted)."""
    _fake_servers(monkeypatch)
    monkeypatch.setattr(
        outline.requests,
        "get",
        lambda url, verify=False, timeout=None: _Resp(200, {"accessKeys": []}),
    )
    result = outline.get_live_key_ids_by_server(server_ids={"1"})
    assert result == {"1": set()}


def test_fetch_access_keys_non_200_returns_none(monkeypatch):
    monkeypatch.setattr(
        outline.requests,
        "get",
        lambda url, verify=False, timeout=None: _Resp(404, {}),
    )
    assert outline.fetch_access_keys("https://s1.example/api") is None


def test_live_keys_returns_raw_lists_and_omits_failures(monkeypatch):
    _fake_servers(monkeypatch)

    def fake_get(url, verify=False, timeout=None):
        if url.startswith("https://s1.example"):
            return _Resp(200, {"accessKeys": [{"id": "9", "accessUrl": "ss://eA@10.0.0.1:8388"}]})
        return _Resp(500, {})

    monkeypatch.setattr(outline.requests, "get", fake_get)

    result = outline.get_live_keys_by_server()
    assert result == {"1": [{"id": "9", "accessUrl": "ss://eA@10.0.0.1:8388"}]}
    # Server 2 answered 500: omitted (fail-open), not an empty list.
    assert "2" not in result
