"""Pure helpers shared across services/handlers (no I/O, no network)."""

import random
import re
import string


def bytes_to_gb(bytes_value):
    return round(bytes_value / (1000 ** 3), 2)


def clean_ss_url(url_str):
    if not url_str:
        return ""
    main_part = url_str.replace("ss://", "").split("#")[0].split("?")[0]
    return main_part.strip()


def generate_random_redeem_code():
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=10))


def extract_chat_id_from_key_name(key_name):
    if not key_name:
        return None
    match = re.search(r'\((\d{8,12})\)', key_name)
    if match:
        return match.group(1)
    return None


# Telegram-network helper lives here (single source of truth) so handlers
# and tests import one canonical implementation.
def is_user_subscribed(user_id):
    """Check force-join channel membership.

    Admins bypass the check. Unknown API errors fail-open (old behaviour:
    bot stays usable when Telegram API hiccups). ``restricted`` members
    (invite-link joins) count as subscribed so legit users are not locked
    out -- this was a Phase-1 TODO, now fixed. An empty/missing
    ``REQUIRED_CHANNEL`` disables the check entirely (local dev bots).
    """
    from bot_app.config import REQUIRED_CHANNEL, is_admin
    from bot_app.extensions import bot

    if not REQUIRED_CHANNEL:
        return True
    if is_admin(user_id):
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ('creator', 'administrator', 'member', 'restricted'):
            return True
    except Exception as e:
        print("Force Join Check Error:", e)
        return True
    return False

