"""Phase 0 shared fixtures.

Safety rules for the whole suite:
- Upstash/Redis is DISABLED (env vars removed) so storage falls back to files.
- All ``*_FILE`` state paths inside ``index`` are redirected to a per-test
  tmp dir, so tests never touch real ``/tmp/*.json`` dev state.
- No test may touch the network: Telegram Bot API + Outline HTTP calls
  must be mocked (see ``mock_bot`` and per-test ``monkeypatch``).
"""

import os

# --- Must run BEFORE importing index (it reads these at import time) ---
for _var in ("KV_REST_API_URL", "KV_REST_API_TOKEN"):
    os.environ.pop(_var, None)

import pytest  # noqa: E402

import index  # noqa: E402


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    """Redirect every ``*_FILE`` constant to an empty tmp dir.

    State constants now live in ``app.storage.paths`` but are re-exported
    through ``index`` and used inside ``app.services.*`` — patch all homes.
    """
    import sys as _sys

    modules = [m for n, m in _sys.modules.items()
               if n == "index" or n.startswith(("app.services", "app.storage"))]
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
                      "delete_message": [], "menu_button": [], "get_chat_member": []}
        self.member_status = "member"
        self.member_error = None

        monkeypatch.setattr(index.bot, "get_chat_member", self._get_chat_member)
        monkeypatch.setattr(index.bot, "send_message", self._send_message)
        monkeypatch.setattr(index.bot, "reply_to", self._reply_to)
        monkeypatch.setattr(index.bot, "answer_callback_query", self._answer_callback)
        monkeypatch.setattr(index.bot, "delete_message", self._delete_message)
        monkeypatch.setattr(index.bot, "set_chat_menu_button", self._menu_button)

    def _get_chat_member(self, chat, user):
        self.calls["get_chat_member"].append((chat, user))
        if self.member_error is not None:
            raise self.member_error
        return FakeMember(self.member_status)

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


@pytest.fixture()
def mock_bot(monkeypatch):
    return BotMock(monkeypatch)


@pytest.fixture()
def client(isolated_state):
    index.app.config["TESTING"] = True
    return index.app.test_client()
