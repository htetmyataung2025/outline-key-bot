"""Upstash KV REST client regression tests.

The old redis_set put the JSON value into the GET command path; urllib's
percent-encoding leaves '/' intact by default, so any state blob containing
a '/' (e.g. a Telegram file_id or caption) made Upstash reject the write
with "ERR syntax error" — silently losing the update while the /tmp file
copy succeeded. redis_set now POSTs the value as the request body.
"""

import json

from bot_app.storage import kv


class _FakeResp:
    status_code = 200


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append(("POST", url, data))
        return _FakeResp()

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        return _FakeResp()


def _configure_kv(monkeypatch):
    monkeypatch.setenv("KV_REST_API_URL", "https://example.upstash.io")
    monkeypatch.setenv("KV_REST_API_TOKEN", "test-token")
    fake = _FakeSession()
    monkeypatch.setattr(kv, "get_session", lambda: fake)
    return fake


def test_redis_set_posts_value_in_body_not_url(monkeypatch):
    fake = _configure_kv(monkeypatch)
    value = {"#257173": {"file_id": "AgAC/abc+def==", "cap": "x/y — dash"}}

    assert kv.redis_set("admin_slips_data", value) is True

    method, url, data = fake.calls[-1]
    assert method == "POST"
    assert url == "https://example.upstash.io/set/%22admin_slips_data%22"
    # The raw JSON (with its '/' characters) travels in the body, never the path
    assert json.loads(data) == value
    assert "/" not in url.split("/set/", 1)[1]


def test_redis_set_reports_failure(monkeypatch):
    fake = _configure_kv(monkeypatch)
    fake.calls.clear()

    class _BadResp:
        status_code = 400

    fake.post = lambda *a, **k: _BadResp()
    assert kv.redis_set("some_key", {"a": 1}) is False
