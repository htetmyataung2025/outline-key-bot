"""Tests for the user profile store (bot_app.services.profiles)."""

from bot_app.services import profiles


class _FakeUser:
    def __init__(self, uid, username="", first_name="", last_name=""):
        self.id = uid
        self.username = username
        self.first_name = first_name
        self.last_name = last_name


def test_save_and_get_profile(isolated_state):
    profiles.save_user_profile(123, username="alice", first_name="Alice", last_name="Wonder")
    p = profiles.get_user_profile(123)
    assert p["chat_id"] == "123"
    assert p["username"] == "alice"
    assert p["full_name"] == "Alice Wonder"
    assert p["first_seen"] and p["last_seen"]


def test_merge_never_blanks_known_fields(isolated_state):
    profiles.save_user_profile(555, username="bob", first_name="Bob")
    first_seen = profiles.get_user_profile(555)["first_seen"]

    # A later interaction without a username must keep the old one, and
    # must not reset first_seen.
    profiles.save_user_profile(555, first_name="Bob")
    p = profiles.get_user_profile(555)
    assert p["username"] == "bob"
    assert p["first_seen"] == first_seen


def test_touch_user_is_silent_and_persists(isolated_state):
    profiles.touch_user(_FakeUser(999, username="carol", first_name="Carol"))
    assert profiles.get_user_profile(999)["full_name"] == "Carol"
    # None must not raise.
    profiles.touch_user(None)


def test_backfill_from_slips_and_orders(isolated_state, monkeypatch):
    monkeypatch.setattr(profiles, "load_all_profiles", lambda: {})
    saved = {}
    monkeypatch.setattr(profiles, "save_all_profiles", lambda d: saved.update(d))
    monkeypatch.setattr(
        "bot_app.services.slips.load_all_slips",
        lambda: {"S1": {"chat_id": "1001", "username": "SlipName"}},
    )
    monkeypatch.setattr(
        "bot_app.services.orders.load_orders",
        lambda: {"O1": {"chat_id": "1002", "user_name": "OrderName"}},
    )

    result = profiles.backfill_profiles_from_history()
    assert result["1001"]["full_name"] == "SlipName"
    assert result["1002"]["full_name"] == "OrderName"
