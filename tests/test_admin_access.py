"""Admin access: forgiving env parsing + live re-read of ADMIN_CHAT_IDS.

Guards against the production symptom "admin မပါလာဘူး": an env var that the
running build could not turn into an admin list (empty, renamed, or formatted
as ``'["123"]'`` / ``id:123;456``), and against a stale import-time snapshot.
"""

import pytest

from bot_app.config import (
    ADMIN_CHAT_IDS,
    admin_chat_ids,
    admin_env_sources,
    admin_ids_masked,
    is_admin,
)
from bot_app.keyboards import get_main_menu_keyboard

ADMIN = 111000111          # conftest sets ADMIN_CHAT_IDS=111000111,222000222
SECOND_ADMIN = 222000222
RANDOM_USER = 987654321


def _button_texts(keyboard):
    """Reply-keyboard row texts (works with KeyboardButton or plain dicts)."""
    return [getattr(b, "text", None) or b["text"] for row in keyboard.keyboard for b in row]


@pytest.fixture()
def clean_admin_env(monkeypatch):
    """Remove every admin env var so a test controls the whole list."""
    for name in ("ADMIN_CHAT_IDS", "ADMIN_IDS", "ADMINS",
                 "ADMIN_CHAT_ID", "ADMIN_USER_IDS", "ADMIN_ID"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_conftest_admin_env_is_read():
    assert admin_chat_ids() == [str(ADMIN), str(SECOND_ADMIN)]
    assert is_admin(ADMIN) is True
    assert is_admin(str(ADMIN)) is True
    assert is_admin(RANDOM_USER) is False
    assert is_admin(None) is False


@pytest.mark.parametrize("raw", [
    "333333333,444444444",                 # plain
    "333333333, 444444444",                # spaced
    '["333333333", "444444444"]',          # JSON-ish paste
    "'333333333','444444444'",             # single quoted
    "333333333;444444444",                 # semicolon
    "333333333|444444444",                 # pipe
    "333333333\n444444444",                # newlines
    "id:333333333 id:444444444",           # labelled
    "admin=333333333, admin=444444444",    # key=value
    "ADMIN_CHAT_IDS=333333333 444444444",  # whole assignment pasted
])
def test_messy_env_values_are_parsed(clean_admin_env, raw):
    clean_admin_env.setenv("ADMIN_CHAT_IDS", raw)
    assert admin_chat_ids() == ["333333333", "444444444"]


def test_dedupes_and_ignores_junk_tokens(clean_admin_env):
    clean_admin_env.setenv("ADMIN_CHAT_IDS", "555555555,555555555,none,abc,12,vip.example.com:33300")
    # 5-15 digit tokens only; a URL/hostname must never become an admin.
    assert admin_chat_ids() == ["555555555"]


def test_alias_env_names_are_accepted(clean_admin_env):
    clean_admin_env.setenv("ADMIN_IDS", "666666666")
    assert admin_chat_ids() == ["666666666"]
    assert admin_env_sources() == ["ADMIN_IDS"]


def test_all_alias_values_are_combined(clean_admin_env):
    clean_admin_env.setenv("ADMIN_CHAT_IDS", "111000111")
    clean_admin_env.setenv("ADMIN_ID", "222000222")
    assert admin_chat_ids() == ["111000111", "222000222"]


def test_values_are_reread_without_reimport(clean_admin_env):
    """Env changes apply at call time — no stale import-time snapshot."""
    clean_admin_env.setenv("ADMIN_CHAT_IDS", "111111111")
    assert is_admin(111111111) is True

    clean_admin_env.setenv("ADMIN_CHAT_IDS", "999999999")
    assert is_admin(111111111) is False
    assert is_admin(999999999) is True
    assert ADMIN_CHAT_IDS[0] == "999999999"
    assert len(ADMIN_CHAT_IDS) == 1
    assert list(ADMIN_CHAT_IDS) == ["999999999"]
    assert 999999999 in ADMIN_CHAT_IDS
    assert ADMIN_CHAT_IDS == ["999999999"]


def test_masked_ids_do_not_leak_full_numbers(clean_admin_env):
    clean_admin_env.setenv("ADMIN_CHAT_IDS", "111000111")
    assert admin_ids_masked() == "…0111"


def test_admin_keyboard_has_admin_rows_and_users_do_not(clean_admin_env):
    clean_admin_env.setenv("ADMIN_CHAT_IDS", str(ADMIN))
    admin_buttons = _button_texts(get_main_menu_keyboard(ADMIN))
    user_buttons = _button_texts(get_main_menu_keyboard(RANDOM_USER))

    assert "📊 Total Data Usage" in admin_buttons
    assert "🎟️ Gen RD Code" in admin_buttons
    assert "📢 Broadcast စာပို့ရန်" in admin_buttons
    assert "📊 Total Data Usage" not in user_buttons
    assert len(admin_buttons) > len(user_buttons)


def test_admin_keyboard_reacts_to_env_change(clean_admin_env):
    clean_admin_env.setenv("ADMIN_CHAT_IDS", "")
    assert "🎟️ Gen RD Code" not in _button_texts(get_main_menu_keyboard(RANDOM_USER))

    clean_admin_env.setenv("ADMIN_CHAT_IDS", str(RANDOM_USER))
    assert "🎟️ Gen RD Code" in _button_texts(get_main_menu_keyboard(RANDOM_USER))


def test_admin_bypasses_force_join_even_with_messy_env(clean_admin_env, mock_bot):
    from bot_app.utils import is_user_subscribed

    clean_admin_env.setenv("ADMIN_CHAT_IDS", '"111000111"')
    assert is_user_subscribed(111000111) is True
    assert mock_bot.calls["get_chat_member"] == []
