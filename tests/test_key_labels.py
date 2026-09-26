"""Tests for key label cleaning + key-only users surfacing in Customers."""

from bot_app.services.registry import clean_key_label, save_persistent_key

ADMIN_ID = 111000111
KEY_ONLY_UID = 606060606


def test_clean_key_label_strips_id_and_date():
    assert clean_key_label("FAFAFA OFFICIAL 🧢 (7672856636) 26.10.2026") == "FAFAFA OFFICIAL 🧢"
    assert clean_key_label("VIP Customer (12345) 01.01.27") == "VIP Customer"
    # No embedded metadata → returned unchanged.
    assert clean_key_label("Just A Label") == "Just A Label"
    # Empty / packed-only names fall back gracefully.
    assert clean_key_label("") == ""
    assert clean_key_label("(999) 05.05.2025") == "(999) 05.05.2025"


def test_key_only_user_appears_in_customers(client, make_telegram_init_data):
    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}

    # User has an Outline key but no wallet and no profile.
    save_persistent_key("2", "k-606", f"KeyOnly User ({KEY_ONLY_UID}) 10.10.2026", "ss://x", chat_id=KEY_ONLY_UID)

    resp = client.get("/api/admin/customers", headers=headers)
    assert resp.status_code == 200
    found = [c for c in resp.json["customers"] if str(c["chat_id"]) == str(KEY_ONLY_UID)]
    assert len(found) == 1
    assert found[0]["keys_count"] == 1


def test_keys_endpoint_exposes_label(client, make_telegram_init_data):
    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}
    save_persistent_key("1", "k-label", "Labelled User (222) 09.09.2026", "ss://y", chat_id=222)

    resp = client.get("/api/admin/keys?sync=0", headers=headers)
    assert resp.status_code == 200
    item = next(k for k in resp.json["items"] if k["key_id"] == "k-label")
    assert item["label"] == "Labelled User"
    assert item["name"] == "Labelled User (222) 09.09.2026"  # raw name preserved
