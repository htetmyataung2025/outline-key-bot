"""Flask webhook surface (Telegram delivery mocked, sync handlers).

NOTE: on Vercel the WSGI app always sees PATH_INFO = "/api/index.py" (the
rewrite destination), so routes are path-agnostic: any POST is a Telegram
update. These tests cover both direct paths and the masked-path case.
"""

USER = 4242424242

WEBHOOK = "/webhook"


def _message_update(text="/start"):
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": USER, "is_bot": False, "first_name": "Test"},
            "chat": {"id": USER, "type": "private"},
            "date": 1700000000,
            "text": text,
        },
    }


def _callback_update(data="verify_subscription"):
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "chat_instance": "test-instance",
            "from": {"id": USER, "is_bot": False, "first_name": "Test"},
            "data": data,
            "message": {
                "message_id": 11,
                "chat": {"id": USER, "type": "private"},
                "date": 1700000000,
                "text": "join first",
            },
        },
    }


def test_root_get(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Bot is running perfectly!" in resp.data


def test_health_get_answers_200(client):
    # /health is served by the universal GET handler (path-agnostic on Vercel).
    resp = client.get("/health")
    assert resp.status_code == 200
    assert b"Bot is running perfectly!" in resp.data


def test_unknown_dotted_get_returns_404(client):
    # Scanners probing /.env* must not get a 200 when the real path is visible.
    assert client.get("/.env").status_code == 404
    assert client.get("/.env.prod").status_code == 404


def test_post_garbage_still_acks(client):
    resp = client.post(WEBHOOK, data="not-json{{{", content_type="application/json")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_post_garbage_on_root_still_acks(client):
    # Backward compat: webhook URLs pointing at the bare domain POST to "/".
    resp = client.post("/", data="not-json{{{", content_type="application/json")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_post_on_masked_vercel_path_acks(client):
    rep = client.post("/api/index.py", data="not-json{{{",
                      content_type="application/json")
    assert rep.status_code == 200
    assert rep.get_json() == {"status": "ok"}


def test_start_reaches_welcome(client, mock_bot):
    resp = client.post(WEBHOOK, json=_message_update("/start"))
    assert resp.status_code == 200
    assert mock_bot.calls["reply_to"], "welcome message was not sent"
    chat_id, text = mock_bot.calls["reply_to"][0]
    assert chat_id == USER and "Test" in text


def test_start_via_masked_path_reaches_welcome(client, mock_bot):
    # Real production case: Telegram POSTs to the domain, Vercel rewrites it,
    # Flask sees "/api/index.py".
    resp = client.post("/api/index.py", json=_message_update("/start"))
    assert resp.status_code == 200
    assert mock_bot.calls["reply_to"], "welcome message was not sent"


def test_verify_callback_opens_menu(client, mock_bot):
    resp = client.post(WEBHOOK, json=_callback_update("verify_subscription"))
    assert resp.status_code == 200
    assert mock_bot.calls["send_message"], "verify did not open the menu"
    chat_id, text = mock_bot.calls["send_message"][0]
    assert chat_id == USER


def test_verify_callback_answers_once_when_not_subscribed(client, mock_bot):
    # Fixed: single answer_callback_query on the fail path (no misleading toast).
    mock_bot.member_status = "left"
    resp = client.post(WEBHOOK, json=_callback_update("verify_subscription"))
    assert resp.status_code == 200
    assert len(mock_bot.calls["answer_callback"]) == 1
    assert mock_bot.calls["send_message"] == []


def test_cron_runs_for_vercel_cron_user_agent(client, mock_bot, monkeypatch):
    from bot_app.services import notifier

    class _Resp:
        status_code = 200

        def json(self):
            return {"accessKeys": []}

    monkeypatch.setattr(notifier.requests, "get", lambda url, **kw: _Resp())
    resp = client.get("/cron-check", headers={"User-Agent": "vercel-cron/1.0"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cron completed"


def test_plain_get_does_not_run_cron(client):
    resp = client.get("/cron-check")
    assert resp.status_code == 200
    assert b"Bot is running perfectly!" in resp.data


