"""Broadcast engine: resumable chunked sends + app inbox fan-out.

Network-free: the service takes the bot as a parameter, so tests pass a
stub bot; Redis is replaced with an in-memory store patched into both
the broadcast service and the app-notify service (the same pattern as
test_admin_api_settings); sleeps are patched out and the admin id list
is pinned to a test value.
"""

import pytest

from bot_app.services import app_notify
from bot_app.services import broadcast as B
from bot_app.services.app_notify import list_app_notifications

ADMIN = "999"


class FakeTgError(Exception):
    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.error_code = code
        self.result_json = (
            {"parameters": {"retry_after": retry_after}} if retry_after is not None else {}
        )


class StubBot:
    """Records sends; ``fail`` maps uid -> exception (or list of them,
    raised on successive attempts)."""

    def __init__(self, fail=None):
        self.messages = []  # (uid, text)
        self.photos = []  # (uid, photo_id, caption)
        self.fail = {
            str(k): (list(v) if isinstance(v, list) else [v])
            for k, v in (fail or {}).items()
        }

    def _maybe_fail(self, uid):
        queue = self.fail.get(str(uid))
        if queue:
            raise queue.pop(0)

    def send_message(self, uid, text, **kwargs):
        self._maybe_fail(uid)
        self.messages.append((str(uid), text))

    def send_photo(self, uid, photo_id, caption=None, **kwargs):
        self._maybe_fail(uid)
        self.photos.append((str(uid), photo_id, caption))


@pytest.fixture(autouse=True)
def _fake_kv(monkeypatch):
    store = {}

    def _get(key):
        return store.get(key)

    def _set(key, value):
        store[key] = value
        return True

    monkeypatch.setattr(B, "redis_get", _get)
    monkeypatch.setattr(B, "redis_set", _set)
    monkeypatch.setattr(app_notify, "redis_get", _get)
    monkeypatch.setattr(app_notify, "redis_set", _set)
    monkeypatch.setattr(B, "_sleep", lambda s: None)
    monkeypatch.setattr(B, "ADMIN_CHAT_IDS", [ADMIN])
    return store


@pytest.fixture()
def start(monkeypatch):
    """Seed the user list and start a broadcast job."""

    def _start(ids, kind="text", text="<b>Hello</b> customers", **kwargs):
        monkeypatch.setattr(B, "load_all_users", lambda: list(ids))
        job, created = B.start_broadcast(ADMIN, kind, text, **kwargs)
        assert created
        return job

    return _start


def _customer_sends(bot):
    return [uid for uid, _ in bot.messages if uid != ADMIN]


# ── job creation ─────────────────────────────────────────────────────────────

def test_start_snapshots_recipients_without_admins_or_dupes(isolated_state, start):
    job = start([111, "222", 111, ADMIN, 333])
    assert job["recipients"] == ["111", "222", "333"]
    assert job["status"] == "running"
    assert B.remaining(job) == 3


def test_second_start_refused_while_running(isolated_state, start):
    job = start([1, 2])
    again, created = B.start_broadcast(ADMIN, "text", "second message")
    assert created is False
    assert again["id"] == job["id"]


# ── delivery ─────────────────────────────────────────────────────────────────

def test_advance_sends_all_and_pushes_app_inbox(isolated_state, start):
    start([111, 222])
    bot = StubBot()
    job = B.advance_broadcast(bot)

    assert job["status"] == "done"
    assert job["sent"] == 2 and job["app_sent"] == 2
    assert _customer_sends(bot) == ["111", "222"]

    items, unread = list_app_notifications(111)
    assert unread == 1 and len(items) == 1
    assert items[0]["type"] == "broadcast"
    assert items[0]["body"] == "Hello customers"  # HTML stripped for the app

    summaries = [t for uid, t in bot.messages if uid == ADMIN]
    assert len(summaries) == 1 and "Broadcast ပို့ပြီးပါပြီ" in summaries[0]


def test_chunk_cap_and_resume_without_duplicates(isolated_state, start):
    start([1, 2, 3, 4, 5])
    bot = StubBot()

    job = B.advance_broadcast(bot, cap=2)
    assert job["status"] == "running" and job["cursor"] == 2
    job = B.advance_broadcast(bot, cap=2)
    assert job["cursor"] == 4
    job = B.advance_broadcast(bot, cap=2)
    assert job["status"] == "done" and job["sent"] == 5
    assert _customer_sends(bot) == ["1", "2", "3", "4", "5"]

    # Advancing a finished job is a no-op; the summary is sent once.
    B.advance_broadcast(bot)
    summaries = [t for uid, t in bot.messages if uid == ADMIN]
    assert len(summaries) == 1


def test_blocked_and_failed_counted_app_still_pushed(isolated_state, start):
    start([1, 2, 3])
    bot = StubBot(fail={
        2: FakeTgError(403, "Forbidden: bot was blocked by the user"),
        3: FakeTgError(500, "Internal error"),
    })
    job = B.advance_broadcast(bot)

    assert job["status"] == "done"
    assert job["sent"] == 1 and job["blocked"] == 1 and job["failed"] == 1
    # The app inbox push happens for every recipient, blocked or not.
    assert job["app_sent"] == 3
    items, _ = list_app_notifications(2)
    assert len(items) == 1


def test_flood_429_retried_once_then_succeeds(isolated_state, start):
    start([1])
    bot = StubBot(fail={1: [FakeTgError(429, "Too Many Requests", retry_after=1)]})
    job = B.advance_broadcast(bot)
    assert job["sent"] == 1 and job["failed"] == 0


def test_photo_broadcast_uses_photo_and_fallback_app_body(isolated_state, start):
    start([7], kind="photo", text="", photo_id="PHOTO1")
    bot = StubBot()
    job = B.advance_broadcast(bot)

    assert job["sent"] == 1
    assert bot.photos == [("7", "PHOTO1", "")]
    items, _ = list_app_notifications(7)
    assert len(items) == 1 and "Bot တွင် ကြည့်ပါ" in items[0]["body"]


def test_photo_caption_becomes_app_body(isolated_state, start):
    start([8], kind="photo", text="<b>Promo</b> today", photo_id="PHOTO2")
    bot = StubBot()
    B.advance_broadcast(bot)
    items, _ = list_app_notifications(8)
    assert items[0]["body"] == "Promo today"


# ── continue-button handler ──────────────────────────────────────────────────

def _continue_call(message_id=42):
    from types import SimpleNamespace

    return SimpleNamespace(
        id="cb-1",
        data="broadcast_continue",
        message=SimpleNamespace(
            chat=SimpleNamespace(id=int(ADMIN)), message_id=message_id
        ),
    )


def test_continue_button_completes_and_edits_message(isolated_state, start, mock_bot, monkeypatch):
    import bot_app.handlers.admin as admin_handlers

    monkeypatch.setattr(admin_handlers, "ADMIN_CHAT_IDS", [ADMIN])
    start([111, 222])

    admin_handlers.handle_broadcast_continue(_continue_call())

    # The callback is answered and customers got the message via the
    # global (mocked) bot; the tapped progress message is edited to done.
    assert mock_bot.calls["answer_callback"]
    sent_to = [str(m[0]) for m in mock_bot.calls["send_message"]]
    assert "111" in sent_to and "222" in sent_to
    edits = mock_bot.calls["edit_message_text"]
    assert edits and "ပို့ပြီးပါပြီ" in edits[0][0][0]
    assert B.get_active_job() is None


def test_continue_button_edits_progress_when_more_remain(isolated_state, start, mock_bot, monkeypatch):
    import bot_app.handlers.admin as admin_handlers

    monkeypatch.setattr(admin_handlers, "ADMIN_CHAT_IDS", [ADMIN])
    start(list(range(1000, 1100)))  # 100 users; the tap cap is 80

    admin_handlers.handle_broadcast_continue(_continue_call())

    job = B.get_active_job()
    assert job is not None and job["cursor"] == 80
    edits = mock_bot.calls["edit_message_text"]
    assert edits and "ကျန်: <b>20</b>" in edits[0][0][0]
