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


# ── Rate-limit primitives: INCR/EXPIRE/DEL (no data-version bump) ─────────

def test_redis_increment_with_expiry_incrs_and_refreshes_ttl(monkeypatch):
    fake = _configure_kv(monkeypatch)
    urls = []

    class _IncrResp:
        status_code = 200

        @staticmethod
        def json():
            return {"result": 2}

    class _OkResp:
        status_code = 200

    def post(url, headers=None, data=None, timeout=None):
        urls.append(url)
        return _IncrResp() if "/incr/" in url else _OkResp()

    fake.post = post

    assert kv.redis_increment_with_expiry("login_rl:abc", 600) == 2
    assert urls[0].startswith("https://example.upstash.io/incr/")
    # EXPIRE is re-issued on every increment so a crashed pair of calls can
    # never leave a TTL-less key (permanent lockout) behind.
    assert urls[1] == "https://example.upstash.io/expire/%22login_rl%3Aabc%22/600"


def test_redis_increment_reports_unreachable_as_none(monkeypatch):
    fake = _configure_kv(monkeypatch)

    class _BadResp:
        status_code = 500

    fake.post = lambda *a, **k: _BadResp()
    assert kv.redis_increment_with_expiry("login_rl:abc", 600) is None


def test_redis_increment_and_delete_when_unconfigured(monkeypatch):
    monkeypatch.delenv("KV_REST_API_URL", raising=False)
    monkeypatch.delenv("KV_REST_API_TOKEN", raising=False)
    monkeypatch.delenv("KV_URL", raising=False)
    assert kv.redis_increment_with_expiry("login_rl:abc", 600) is None
    assert kv.redis_delete("login_rl:abc") is False


def test_redis_delete_posts_del_command(monkeypatch):
    fake = _configure_kv(monkeypatch)

    assert kv.redis_delete("login_rl:abc") is True

    method, url, _data = fake.calls[-1]
    assert method == "POST"
    assert url.startswith("https://example.upstash.io/del/")
