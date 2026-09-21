"""Tests for scripts/set_webhook.py (HTTP mocked, no network)."""

import importlib.util
import os

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "set_webhook.py")


def load_script():
    spec = importlib.util.spec_from_file_location("set_webhook", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def sw():
    return load_script()


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _mock_api(monkeypatch, sw, handler):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params or {}))
        return FakeResp(handler(url, params or {}))

    monkeypatch.setattr(sw.requests, "get", fake_get)
    return calls


def test_check_passes_with_full_updates(sw, monkeypatch):
    info = {"url": "https://x.example/", "pending_update_count": 0}
    _mock_api(monkeypatch, sw, lambda url, p: {"ok": True, "result": info})
    assert sw.main(["check", "--token", "1:abc", "--url", "https://x.example/"]) == 0


def test_check_fails_when_callback_query_filtered(sw, monkeypatch, capsys):
    info = {"url": "https://x.example/",
            "allowed_updates": ["message", "edited_message"],
            "pending_update_count": 0}
    _mock_api(monkeypatch, sw, lambda url, p: {"ok": True, "result": info})
    assert sw.main(["check", "--token", "1:abc", "--url", "https://x.example/"]) == 1
    assert "callback_query" in capsys.readouterr().out


def test_check_fails_on_url_mismatch(sw, monkeypatch):
    info = {"url": "https://evil.example/", "pending_update_count": 0}
    _mock_api(monkeypatch, sw, lambda url, p: {"ok": True, "result": info})
    assert sw.main(["check", "--token", "1:abc", "--url", "https://x.example/"]) == 1


def test_set_requests_full_updates_then_verifies(sw, monkeypatch):
    def handler(url, params):
        if url.endswith("/setWebhook"):
            assert params.get("allowed_updates") == "[]"
            return {"ok": True, "result": True}
        return {"ok": True, "result": {"url": "https://x.example/",
                                       "pending_update_count": 0}}

    calls = _mock_api(monkeypatch, sw, handler)
    assert sw.main(["set", "--token", "1:abc", "--url", "https://x.example/"]) == 0
    assert any(u.endswith("/setWebhook") for u, _ in calls)


def test_missing_token_is_usage_error(sw):
    assert sw.main(["check", "--token", "", "--url", "https://x.example/"]) == 2
