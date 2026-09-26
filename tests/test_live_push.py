"""Tests for the live-push channel (SSE) and version-change semantics.

Covers:
- The pub/sub bus: subscribers receive the bumped version.
- Registry sync is change-only: an identical re-sync must NOT bump the
  version (this was the root cause of the dashboard's refresh loop).
- One-time stream tickets: auth required to mint, single use, garbage and
  reuse rejected.
- The SSE stream: emits a baseline version frame and pushes a frame when
  shared state is written.
"""

import json

import pytest

from bot_app.helpers.sse import TICKET_TTL_SECONDS, consume_ticket, issue_ticket
from bot_app.storage import versioning
from bot_app.services.registry import sync_keys_to_persistent_registry

ADMIN_ID = 111000111


def _admin_headers(make_telegram_init_data):
    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    return {"X-Telegram-Init-Data": init_data}


def _first_frame(resp):
    return next(iter(resp.response))


def _parse_event(frame: bytes) -> dict:
    line = frame.decode().splitlines()[0]
    assert line.startswith("data: ")
    return json.loads(line[len("data: "):])


# ── In-process change bus ────────────────────────────────────────────────
def test_bump_notifies_subscribers(isolated_state):
    q = versioning.subscribe()
    try:
        before = versioning.get_data_version()
        new_version = versioning.bump_data_version()
        assert new_version == before + 1
        assert q.get_nowait() == new_version
    finally:
        versioning.unsubscribe(q)


def test_unsubscribed_queue_receives_nothing(isolated_state):
    q = versioning.subscribe()
    versioning.unsubscribe(q)
    versioning.bump_data_version()
    assert q.empty()


# ── Change-only registry sync (refresh-loop root cause) ──────────────────
def _sample_keys(name="user (12345) 01.10.2026"):
    return [{
        "id": "42",
        "name": name,
        "accessUrl": "ss://secret",
        "dataLimit": {"bytes": 1073741824},
    }]


def test_identical_resync_does_not_bump_version(isolated_state):
    sync_keys_to_persistent_registry("1", _sample_keys())
    after_first = versioning.get_data_version()

    # Read paths (GET /keys) re-run this sync constantly; without change
    # detection each one signalled "data changed" and retriggered every
    # connected dashboard — the flicker loop.
    sync_keys_to_persistent_registry("1", _sample_keys())
    assert versioning.get_data_version() == after_first


def test_real_change_bumps_version(isolated_state):
    sync_keys_to_persistent_registry("1", _sample_keys())
    after_first = versioning.get_data_version()

    sync_keys_to_persistent_registry("1", _sample_keys(name="user (12345) 08.10.2026"))
    assert versioning.get_data_version() == after_first + 1


def test_resync_preserves_registry_content(isolated_state):
    sync_keys_to_persistent_registry("1", _sample_keys())
    sync_keys_to_persistent_registry("1", _sample_keys())
    from bot_app.services.registry import load_persistent_keys
    registry = load_persistent_keys()
    assert registry["1_42"]["name"] == "user (12345) 01.10.2026"
    assert registry["1_42"]["chat_id"] == "12345"


# ── One-time stream tickets ──────────────────────────────────────────────
def test_ticket_issue_and_single_use():
    admin = {"id": "desktop_admin", "username": "Admin"}
    ticket = issue_ticket(admin)

    consumed = consume_ticket(ticket)
    assert consumed == admin
    # Burned on first use.
    assert consume_ticket(ticket) is None


def test_ticket_rejects_garbage_and_expiry():
    assert consume_ticket("") is None
    assert consume_ticket("bogus-ticket") is None

    admin = {"id": "desktop_admin"}
    ticket = issue_ticket(admin)
    # Simulate an expired ticket.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("bot_app.helpers.sse.TICKET_TTL_SECONDS", -1)
        assert consume_ticket(ticket) is None


# ── SSE endpoint ─────────────────────────────────────────────────────────
def test_sse_ticket_endpoint_requires_auth(client):
    resp = client.post("/api/admin/sse-ticket")
    assert resp.status_code == 401


def test_sse_stream_rejects_invalid_ticket(client):
    resp = client.get("/api/admin/events?ticket=not-a-ticket")
    assert resp.status_code == 401


def test_sse_stream_pushes_changes(client, make_telegram_init_data, isolated_state):
    headers = _admin_headers(make_telegram_init_data)

    resp = client.post("/api/admin/sse-ticket", headers=headers)
    assert resp.status_code == 200
    ticket = resp.json["ticket"]

    stream = client.get(f"/api/admin/events?ticket={ticket}")
    assert stream.status_code == 200
    assert stream.mimetype == "text/event-stream"

    # Baseline frame carries the current version.
    baseline = _parse_event(_first_frame(stream))
    assert baseline["version"] == versioning.get_data_version()

    # A write anywhere in the process is pushed instantly.
    bumped = versioning.bump_data_version()
    pushed = _parse_event(next(iter(stream.response)))
    assert pushed["version"] == bumped

    stream.close()


def test_sse_stream_ticket_is_single_use(client, make_telegram_init_data, isolated_state):
    headers = _admin_headers(make_telegram_init_data)
    ticket = client.post("/api/admin/sse-ticket", headers=headers).json["ticket"]

    stream = client.get(f"/api/admin/events?ticket={ticket}")
    _first_frame(stream)
    stream.close()

    replay = client.get(f"/api/admin/events?ticket={ticket}")
    assert replay.status_code == 401


def test_ticket_ttl_constant_is_short():
    # The whole point is a short exposure window in URLs/logs.
    assert 0 < TICKET_TTL_SECONDS <= 30
