"""Flask webhook surface (Telegram delivery mocked, sync handlers)."""

USER = 4242424242


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


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_unknown_get_currently_returns_200(client):
    # TODO Phase 3: return 404 for unknown paths so scanners probing
    # /.env etc. don't get a 200. Locks CURRENT catch-all behavior.
    assert client.get("/.env").status_code == 200


def test_post_garbage_still_acks(client):
    resp = client.post("/", data="not-json{{{", content_type="application/json")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_start_reaches_welcome(client, mock_bot):
    resp = client.post("/", json=_message_update("/start"))
    assert resp.status_code == 200
    assert mock_bot.calls["reply_to"], "welcome message was not sent"
    chat_id, text = mock_bot.calls["reply_to"][0]
    assert chat_id == USER and "Test" in text


def test_verify_callback_opens_menu(client, mock_bot):
    resp = client.post("/", json=_callback_update("verify_subscription"))
    assert resp.status_code == 200
    assert mock_bot.calls["send_message"], "verify did not open the menu"
    chat_id, text = mock_bot.calls["send_message"][0]
    assert chat_id == USER


def test_verify_callback_answers_twice_when_not_subscribed(client, mock_bot):
    # TODO Phase 1: handler answers the callback TWICE on the fail path
    # (success toast first, then the "not joined" alert). Telegram rejects
    # the second answer, so the user sees a misleading success toast and
    # no guidance. Keep a single answer. Locks CURRENT behavior.
    mock_bot.member_status = "left"
    resp = client.post("/", json=_callback_update("verify_subscription"))
    assert resp.status_code == 200
    assert len(mock_bot.calls["answer_callback"]) == 2
    assert mock_bot.calls["send_message"] == []
