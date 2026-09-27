"""Shared fixtures.

Safety rules for the whole suite:
- Upstash/Redis is DISABLED (env vars removed) so storage falls back to files.
- All ``*_FILE`` state paths are redirected to a per-test tmp dir, so tests
  never touch real ``/tmp/*.json`` dev state.
- No test may touch the network: Telegram Bot API + Outline HTTP calls
  must be mocked (see ``mock_bot`` and per-test ``monkeypatch``).
- CI has no secrets: minimal env defaults are set BEFORE importing bot_app
  (its config module reads these at import time).
"""

import os
from types import SimpleNamespace

# --- Must run BEFORE importing bot_app (config reads these at import time) ---
for _var in ("KV_REST_API_URL", "KV_REST_API_TOKEN", "KV_URL", "KV_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.pop(_var, None)
os.environ.setdefault("ADMIN_CHAT_IDS", "111000111,222000222")
# Auth must verify with the SAME token the fixtures sign with; config's dummy
# default already covers this, but set it explicitly so the env-less CI runner
# and local .env setups behave identically.
os.environ.setdefault("TELEGRAM_TOKEN", "0000000000:AAADummyTokenForTestsOnly00000000000")
os.environ.setdefault("MY_PAYMENT_PHONES", "0999999999,9699999999")
os.environ.setdefault("REQUIRED_CHANNEL", "@test_channel")

import pytest  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def registered_app():
    """Import the app package once: registers Telegram handlers + Flask routes."""
    import bot_app

    for _var in ("KV_REST_API_URL", "KV_REST_API_TOKEN", "KV_URL", "KV_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"):
        os.environ.pop(_var, None)

    return bot_app


@pytest.fixture(autouse=True)
def disable_external_network(monkeypatch):
    """Ensure tests never attempt external network calls.

    Strip every KV / Redis / Supabase env var (including the KV_URL / KV_TOKEN
    / REDIS_URL aliases that ``bot_app.storage.kv._kv_config`` falls back to),
    so a populated local ``.env`` — e.g. real Upstash credentials added for
    manual inspection — can never make the suite read or WRITE production data.
    """
    for var in (
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "KV_REST_API_URL",
        "KV_REST_API_TOKEN",
        "KV_REST_API_READ_ONLY_TOKEN",
        "KV_URL",
        "KV_TOKEN",
        "REDIS_URL",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    """Redirect every ``*_FILE`` constant to an empty tmp dir.

    State constants live in ``bot_app.storage.paths`` and are imported by
    ``bot_app.services.*`` — patch every home so file I/O stays sandboxed.
    """
    import sys as _sys

    modules = [m for n, m in _sys.modules.items()
               if n == "index" or n.startswith(("bot_app.", "bot_app.handlers",
                                                "bot_app.services", "bot_app.storage"))]
    targets = {}
    for mod in modules:
        for name in [n for n in dir(mod) if n.endswith("_FILE")]:
            try:
                original = getattr(mod, name)
            except AttributeError:
                continue
            if not isinstance(original, str):
                continue
            targets.setdefault(name, str(tmp_path / os.path.basename(original)))
    for mod in modules:
        for name, target in targets.items():
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, target, raising=False)
    return tmp_path


class FakeMember:
    def __init__(self, status):
        self.status = status


class BotMock:
    """Replaces network-bound TeleBot methods with in-memory recorders."""

    def __init__(self, monkeypatch):
        self.calls = {"send_message": [], "reply_to": [], "answer_callback": [],
                      "delete_message": [], "menu_button": [], "get_chat_member": [],
                      "send_photo": [], "get_file": [], "edit_message_text": [],
                      "edit_message_caption": [], "get_chat": [],
                      "get_webhook_info": [], "set_webhook": []}
        self.member_status = "member"
        self.member_error = None
        self.webhook_url = ""  # tests may point this at a fake webhook URL

        from bot_app.extensions import bot as _bot
        for target in (_bot,):
            monkeypatch.setattr(target, "get_chat_member", self._get_chat_member)
            monkeypatch.setattr(target, "send_message", self._send_message)
            monkeypatch.setattr(target, "reply_to", self._reply_to)
            monkeypatch.setattr(target, "answer_callback_query", self._answer_callback)
            monkeypatch.setattr(target, "delete_message", self._delete_message)
            monkeypatch.setattr(target, "set_chat_menu_button", self._menu_button)
            monkeypatch.setattr(target, "send_photo", self._send_photo)
            monkeypatch.setattr(target, "get_file", self._get_file)
            monkeypatch.setattr(target, "edit_message_text", self._edit_message_text)
            monkeypatch.setattr(target, "edit_message_caption", self._edit_message_caption)
            monkeypatch.setattr(target, "get_chat", self._get_chat)
            monkeypatch.setattr(target, "get_webhook_info", self._get_webhook_info)
            monkeypatch.setattr(target, "set_webhook", self._set_webhook)

    def _get_chat_member(self, chat, user):
        self.calls["get_chat_member"].append((chat, user))
        if self.member_error is not None:
            raise self.member_error
        return FakeMember(self.member_status)

    def _get_webhook_info(self):
        self.calls["get_webhook_info"].append(True)
        return SimpleNamespace(url=self.webhook_url)

    def _set_webhook(self, url, **kwargs):
        self.calls["set_webhook"].append(url)
        self.webhook_url = url
        return True

    def _send_message(self, chat_id, text, *args, **kwargs):
        self.calls["send_message"].append((chat_id, text))
        return None

    def _reply_to(self, message, text, *args, **kwargs):
        self.calls["reply_to"].append((message.chat.id, text))
        return None

    def _answer_callback(self, *args, **kwargs):
        self.calls["answer_callback"].append((args, kwargs))
        return None

    def _delete_message(self, *args, **kwargs):
        self.calls["delete_message"].append((args, kwargs))
        return None

    def _menu_button(self, *args, **kwargs):
        self.calls["menu_button"].append((args, kwargs))
        return None

    def _send_photo(self, chat_id, photo, *args, **kwargs):
        self.calls["send_photo"].append((chat_id, photo))
        # Real TeleBot returns the sent Message; handlers may record its id.
        self._photo_seq = getattr(self, "_photo_seq", 0) + 1
        return SimpleNamespace(
            chat=SimpleNamespace(id=chat_id),
            message_id=900000 + self._photo_seq,
        )

    def _get_file(self, file_id):
        self.calls["get_file"].append(file_id)

        class _F:
            file_path = "photos/test.jpg"
        return _F()

    def _edit_message_text(self, *args, **kwargs):
        self.calls["edit_message_text"].append((args, kwargs))
        return None

    def _edit_message_caption(self, *args, **kwargs):
        self.calls["edit_message_caption"].append((args, kwargs))
        return None

    def _get_chat(self, chat_id):
        self.calls["get_chat"].append(chat_id)

        class _C:
            first_name = "Test"
            last_name = "User"
        return _C()


@pytest.fixture()
def mock_bot(monkeypatch):
    return BotMock(monkeypatch)


@pytest.fixture()
def client(isolated_state):
    from bot_app.extensions import flask_app
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.fixture()
def make_telegram_init_data():
    """Generate cryptographically valid or tampered Telegram initData strings."""
    import hashlib
    import hmac
    import json
    from urllib.parse import urlencode

    def _generator(user_id=111000111, username="admin_user", is_tampered=False, token=None,
                   auth_date=None):
        import time
        bot_token = token or os.environ.get("TELEGRAM_TOKEN", "0000000000:AAADummyTokenForTestsOnly00000000000")
        user_dict = {"id": user_id, "first_name": "Test", "username": username}
        params = {
            "auth_date": str(int(time.time()) if auth_date is None else auth_date),
            "query_id": "AAHdF6IQAAAAAN0XohD5p8Zb",
            "user": json.dumps(user_dict, separators=(",", ":")),
        }
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if is_tampered:
            computed_hash = "tampered_bad_hash_999999"

        params["hash"] = computed_hash
        return urlencode(params)

    return _generator


