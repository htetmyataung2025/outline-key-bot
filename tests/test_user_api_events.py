import json
import pytest
from bot_app.storage import versioning


def test_user_events_ticket_flow(client, make_telegram_init_data, isolated_state):
    # 1. Missing header -> 401
    res = client.post("/api/user/events/ticket")
    assert res.status_code == 401

    # 2. Valid Telegram auth -> 200 with ticket
    init_data = make_telegram_init_data(user_id=12345678, username="testuser")
    res = client.post(
        "/api/user/events/ticket",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "ticket" in data
    ticket = data["ticket"]
    assert len(ticket) > 10

    # 3. Version endpoint
    res = client.get("/api/user/version", headers={"X-Telegram-Init-Data": init_data})
    assert res.status_code == 200
    assert "version" in res.get_json()


def test_user_events_stream_with_ticket(client, make_telegram_init_data, isolated_state):
    # Get ticket
    init_data = make_telegram_init_data(user_id=12345678, username="testuser")
    res = client.post(
        "/api/user/events/ticket",
        headers={"X-Telegram-Init-Data": init_data},
    )
    ticket = res.get_json()["ticket"]

    # Connect to SSE stream using ticket
    res = client.get(f"/api/user/events?ticket={ticket}")
    assert res.status_code == 200
    assert res.mimetype == "text/event-stream"
