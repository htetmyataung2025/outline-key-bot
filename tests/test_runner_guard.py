"""Local runner guard: polling must not silently kill production delivery."""

from types import SimpleNamespace

from bot_app.helpers.webhook_guard import polling_conflict


class FakeBot:
    def __init__(self, url="", error=None):
        self._url = url
        self._error = error

    def get_webhook_info(self):
        if self._error:
            raise self._error
        return SimpleNamespace(url=self._url)


def test_polling_allowed_when_no_webhook():
    allowed, url = polling_conflict(FakeBot(""))
    assert allowed is True and url == ""


def test_polling_refused_when_webhook_active():
    # The exact case that took production down: local polling would delete it.
    allowed, url = polling_conflict(FakeBot("https://outline-key-bot.vercel.app/webhook"))
    assert allowed is False
    assert url == "https://outline-key-bot.vercel.app/webhook"


def test_polling_allowed_with_explicit_flag():
    allowed, url = polling_conflict(FakeBot("https://example.test/hook"), allow_remove=True)
    assert allowed is True and url == "https://example.test/hook"


def test_network_error_does_not_block_polling():
    allowed, url = polling_conflict(FakeBot(error=RuntimeError("no network")))
    assert allowed is True and url == ""
