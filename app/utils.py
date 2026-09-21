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
