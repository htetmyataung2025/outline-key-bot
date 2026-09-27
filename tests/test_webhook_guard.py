"""Self-healing webhook guard: drift detection + auto-repair.

Regression coverage for the twice-repeated outage where the production
webhook pointed at the site root (static index.html rejects POST → 405)
and every Telegram update queued up unheard.
"""

from bot_app.helpers.webhook_guard import ensure_webhook, expected_webhook_url

PROD = "https://outline-key-bot.vercel.app/webhook"
ROOT = "https://outline-key-bot.vercel.app/"


class FakeBot:
    def __init__(self, url="", error=None):
        self._url = url
        self._error = error
        self.set_calls = []

    def get_webhook_info(self):
        if self._error:
            raise self._error
        from types import SimpleNamespace
        return SimpleNamespace(url=self._url)

    def set_webhook(self, url, **kwargs):
        self.set_calls.append(url)
        self._url = url


# --- expected_webhook_url ---------------------------------------------------

def test_expected_url_empty_without_env(monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    assert expected_webhook_url() == ""


def test_expected_url_from_vercel_project_domain(monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "outline-key-bot.vercel.app")
    assert expected_webhook_url() == PROD


def test_expected_url_appends_webhook_suffix_to_root_override(monkeypatch):
    # A WEBHOOK_URL pointing at the root is the exact historical mistake.
    monkeypatch.setenv("WEBHOOK_URL", ROOT)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    assert expected_webhook_url() == PROD


def test_expected_url_keeps_explicit_webhook_path(monkeypatch):
    monkeypatch.setenv("WEBHOOK_URL", PROD)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    assert expected_webhook_url() == PROD


# --- ensure_webhook ----------------------------------------------------------

def test_healthy_webhook_is_left_alone():
    bot = FakeBot(PROD)
    result = ensure_webhook(bot, expected_url=PROD)
    assert result == {"checked": True, "url": PROD, "previous": PROD,
                      "fixed": False, "error": None}
    assert bot.set_calls == []


def test_drifted_root_webhook_is_repaired():
    bot = FakeBot(ROOT)
    result = ensure_webhook(bot, expected_url=PROD)
    assert result["fixed"] is True
    assert result["url"] == PROD
    assert result["previous"] == ROOT
    assert bot.set_calls == [PROD]


def test_no_expected_url_never_touches_bot():
    bot = FakeBot(ROOT)
    result = ensure_webhook(bot, expected_url="")
    assert result["checked"] is False
    assert bot.set_calls == []


def test_telegram_api_error_is_reported_not_raised():
    bot = FakeBot(error=RuntimeError("network down"))
    result = ensure_webhook(bot, expected_url=PROD)
    assert result["fixed"] is False
    assert "network down" in result["error"]


# --- cron route integration ---------------------------------------------------

def _mock_outline_empty(monkeypatch):
    from bot_app.services import notifier

    class _Resp:
        status_code = 200

        def json(self):
            return {"accessKeys": []}

    monkeypatch.setattr(notifier.requests, "get", lambda url, **kw: _Resp())


def test_cron_repairs_drifted_webhook_and_notifies_admins(client, mock_bot, monkeypatch):
    from bot_app.config import ADMIN_CHAT_IDS

    _mock_outline_empty(monkeypatch)
    mock_bot.webhook_url = ROOT
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "outline-key-bot.vercel.app")

    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["webhook_guard"]["fixed"] is True
    assert body["webhook_guard"]["url"] == PROD
    assert mock_bot.calls["set_webhook"] == [PROD]
    # every admin is told the delivery path was restored
    assert len(mock_bot.calls["send_message"]) == len(ADMIN_CHAT_IDS)


def test_cron_healthy_webhook_sends_no_repair_notice(client, mock_bot, monkeypatch):
    _mock_outline_empty(monkeypatch)
    mock_bot.webhook_url = PROD
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "outline-key-bot.vercel.app")

    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["webhook_guard"] == {"checked": True, "url": PROD, "previous": PROD,
                                     "fixed": False, "error": None}
    assert mock_bot.calls["set_webhook"] == []
    assert mock_bot.calls["send_message"] == []


def test_cron_without_expected_url_guard_is_noop(client, mock_bot, monkeypatch):
    _mock_outline_empty(monkeypatch)
    mock_bot.webhook_url = ROOT
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)

    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["webhook_guard"]["checked"] is False
    assert mock_bot.calls["set_webhook"] == []
    assert mock_bot.calls["send_message"] == []
