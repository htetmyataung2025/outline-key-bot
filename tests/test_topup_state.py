"""Transient state must survive across separate Telegram updates.

With Redis disabled (as in tests / local polling), the top-up amount the
user picks in one update has to persist until the slip photo arrives in a
later update. A regression here silently defaulted every slip to 1,000 Ks.
"""

from bot_app.services.states import (
    get_custom_topup_state,
    get_topup_state,
    set_custom_topup_state,
    set_topup_state,
)


def test_topup_amount_persists_between_updates(isolated_state):
    chat_id = 55500123
    set_topup_state(chat_id, 5000)

    # Simulates a fresh handler invocation reading the earlier selection.
    assert get_topup_state(chat_id) == 5000


def test_topup_amount_defaults_when_unset(isolated_state):
    assert get_topup_state(99999999) is None
    # Mirrors the handler's `get_topup_state(chat_id) or 1000` guard.
    assert (get_topup_state(99999999) or 1000) == 1000


def test_topup_state_can_be_cleared(isolated_state):
    chat_id = 55500999
    set_topup_state(chat_id, 20000)
    assert get_topup_state(chat_id) == 20000
    set_topup_state(chat_id, None)
    assert get_topup_state(chat_id) is None


def test_custom_topup_flag_persists(isolated_state):
    chat_id = 55500777
    set_custom_topup_state(chat_id, True)
    assert get_custom_topup_state(chat_id) is True
    set_custom_topup_state(chat_id, False)
    assert get_custom_topup_state(chat_id) is False
