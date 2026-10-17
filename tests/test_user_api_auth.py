"""Tests for Customer TMA authentication helper and user API security."""

from bot_app.services.profiles import get_user_profile


def test_user_api_auth_missing_header(client):
    resp = client.get("/api/user/bootstrap")
    assert resp.status_code == 401
    assert "Missing Telegram authentication" in resp.get_json().get("error", "")


def test_user_api_auth_tampered_header(client, make_telegram_init_data):
    tampered_data = make_telegram_init_data(user_id=78429105, is_tampered=True)

    resp = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": tampered_data}
    )
    assert resp.status_code == 401
    assert "Invalid or tampered" in resp.get_json().get("error", "")


def test_user_api_auth_valid_header(client, make_telegram_init_data, isolated_state):
    valid_data = make_telegram_init_data(user_id=78429105, username="heinthant")

    resp = client.get(
        "/api/user/bootstrap",
        headers={"X-Telegram-Init-Data": valid_data}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"]["id"] == "78429105"

    # Profile was touched and saved automatically
    profile = get_user_profile("78429105")
    assert profile.get("username") == "heinthant"
    assert profile.get("chat_id") == "78429105"
