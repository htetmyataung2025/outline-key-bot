"""Shared handler helpers: force-join prompt + admin check."""

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.keyboards import get_force_join_keyboard
from bot_app.texts import force_join_text


def is_admin(chat_id) -> bool:
    return str(chat_id) in [str(a) for a in ADMIN_CHAT_IDS]


def send_force_join_message(chat_id) -> None:
    """Prompt a non-subscribed user to join the channel (with Verify button)."""
    bot.send_message(chat_id, force_join_text(), parse_mode="HTML",
                     reply_markup=get_force_join_keyboard())

