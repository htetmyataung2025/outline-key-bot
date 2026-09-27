"""Flask webhook surface (Telegram delivery mocked, sync handlers).

NOTE: on Vercel the WSGI app always sees PATH_INFO = "/api/index.py" (the
rewrite destination), so routes are path-agnostic: any POST is a Telegram
update. These tests cover both direct paths and the masked-path case.
"""

USER = 4242424242

WEBHOOK = "/webhook"


def _message_update(text="/start", chat_id=USER, user_id=USER):
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
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


def test_myid_reports_admin_status_and_parsed_ids(client, mock_bot):
    # The admin may be locked by the channel gate; /myid must still answer and
    # must reveal what the *running deployment* parsed from ADMIN_CHAT_IDS.
    from bot_app.config import admin_chat_ids

    admin = int(admin_chat_ids()[0])
    resp = client.post(WEBHOOK, json=_message_update("/myid", chat_id=admin, user_id=admin))
    assert resp.status_code == 200
    assert mock_bot.calls["reply_to"], "/myid did not answer"
    chat_id, text = mock_bot.calls["reply_to"][0]
    assert chat_id == admin
    assert "✅" in text                     # recognised as admin
    assert str(admin) in text               # shows the parsed list
    assert "admin IDs" in text


def test_myid_tells_normal_users_their_id(client, mock_bot):
    resp = client.post(WEBHOOK, json=_message_update("/myid"))
    assert resp.status_code == 200
    assert mock_bot.calls["reply_to"], "/myid did not answer"
    _, text = mock_bot.calls["reply_to"][0]
    assert "❌" in text                     # not an admin
    assert str(USER) in text
    assert "ADMIN_CHAT_IDS" in text          # setup hint for the owner


def test_diag_rejects_missing_or_wrong_key(client):
    # No key / wrong key must look like any other anonymous GET (no info leak).
    for url in ("/diag", "/diag?key=wrong", f"/diag?key={'0' * 16}"):
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"Bot is running perfectly!" in resp.data


def test_diag_reports_config_status_for_the_owner(client, mock_bot, monkeypatch):
    from bot_app.config import admin_chat_ids
    from bot_app.routes import diag_key

    monkeypatch.setattr("bot_app.routes.outline_api_urls", lambda: [])
    resp = client.get(f"/diag?key={diag_key()}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["admins"] == len(admin_chat_ids())
    assert data["admin_env_sources"] == ["ADMIN_CHAT_IDS"]
    assert data["required_channel"]            # channel name is not a secret
    assert data["webhook_ok"] is None          # no Vercel domain in tests
    assert "token" not in resp.get_data(as_text=True).lower()




