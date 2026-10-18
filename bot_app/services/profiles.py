"""User profile store: Telegram username / display name / activity timestamps.

The bot only ever stored a bare list of chat_ids (`all_users`); usernames and
display names lived scattered across slips and orders. This module gives the
Control Center a single place to read a customer's identity from.
"""

import json
import os
import time

from bot_app.storage.kv import redis_get, redis_set
from bot_app.storage.paths import USER_PROFILES_FILE
from bot_app.timeutil import myanmar_now


def load_all_profiles() -> dict:
    data = redis_get("user_profiles")
    local_data = {}
    if os.path.exists(USER_PROFILES_FILE):
        try:
            with open(USER_PROFILES_FILE, "r") as f:
                local_data = json.load(f)
        except Exception:
            pass

    if data is not None and isinstance(data, dict):
        if local_data:
            merged = False
            for k, v in local_data.items():
                if k not in data or (not data[k].get("full_name") and v.get("full_name")):
                    data[k] = {**v, **data.get(k, {})}
                    merged = True
            if merged:
                save_all_profiles(data)
        return data

    if local_data:
        save_all_profiles(local_data)
        return local_data

    return {}


def save_all_profiles(profiles: dict):
    redis_set("user_profiles", profiles)
    try:
        with open(USER_PROFILES_FILE, "w") as f:
            json.dump(profiles, f, indent=2)
    except Exception:
        pass


def _compose_name(first_name: str, last_name: str) -> str:
    return f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()


def save_user_profile(chat_id, username="", first_name="", last_name="", full_name=""):
    """Merge a profile update. Never blanks out a known field with an empty
    value, so a later interaction that lacks (e.g.) a username keeps the old one."""
    profiles = load_all_profiles()
    uid = str(chat_id)
    now = myanmar_now().strftime("%Y-%m-%d %H:%M:%S")
    existing = profiles.get(uid, {})

    name = (full_name or _compose_name(first_name, last_name)).strip()

    profile = {
        "chat_id": uid,
        "username": (username or "").strip() or existing.get("username", ""),
        "first_name": (first_name or "").strip() or existing.get("first_name", ""),
        "last_name": (last_name or "").strip() or existing.get("last_name", ""),
        "full_name": name or existing.get("full_name", ""),
        "first_seen": existing.get("first_seen") or now,
        "last_seen": now,
    }
    profiles[uid] = profile
    save_all_profiles(profiles)
    return profile


def get_user_profile(chat_id) -> dict:
    return load_all_profiles().get(str(chat_id), {})


def resolve_user_profile(chat_id, fetch_telegram: bool = True) -> dict:
    """Fetch user profile. If missing or lacking display name/username, and
    fetch_telegram is True, queries the Telegram Bot API (bot.get_chat) to resolve
    and persist the user's real name and username on the fly."""
    uid = str(chat_id or "").strip()
    if not uid or uid == "None":
        return {}

    profile = get_user_profile(uid)
    if profile and (profile.get("full_name") or profile.get("username")):
        return profile

    if fetch_telegram:
        try:
            from bot_app.extensions import bot
            chat = bot.get_chat(uid)
            if chat:
                first_name = (getattr(chat, "first_name", "") or "").strip()
                last_name = (getattr(chat, "last_name", "") or "").strip()
                username = (getattr(chat, "username", "") or "").strip()
                if first_name or username:
                    return save_user_profile(
                        chat_id=uid,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                    )
        except Exception:
            pass

    return profile or {}


_TOUCH_THROTTLE = {}


def touch_user(from_user):
    """Capture/refresh a profile from a Telegram message.from_user / call.from_user.
    Silent on any error — profile capture must never break a bot interaction."""
    if not from_user:
        return
    uid = str(getattr(from_user, "id", "") or "")
    if not uid:
        return
    now = time.time()
    last_touch = _TOUCH_THROTTLE.get(uid, 0.0)
    if now - last_touch < 300.0:
        return
    _TOUCH_THROTTLE[uid] = now
    try:
        save_user_profile(
            chat_id=uid,
            username=getattr(from_user, "username", "") or "",
            first_name=getattr(from_user, "first_name", "") or "",
            last_name=getattr(from_user, "last_name", "") or "",
        )
    except Exception:
        pass


def backfill_profiles_from_history() -> dict:
    """Fill display names from existing slips/orders for users whose profile has
    none yet, so pre-existing customers show a name immediately. Idempotent."""
    from bot_app.services.orders import load_orders
    from bot_app.services.slips import load_all_slips

    profiles = load_all_profiles()
    changed = False

    def _ensure(uid, name="", username=""):
        nonlocal changed
        uid = str(uid or "").strip()
        if not uid or uid == "None":
            return
        p = profiles.get(uid)
        if p is None:
            p = {
                "chat_id": uid,
                "username": "",
                "first_name": "",
                "last_name": "",
                "full_name": "",
                "first_seen": "",
                "last_seen": "",
            }
            profiles[uid] = p
            changed = True
        name = (name or "").strip()
        if name and name.lower() != "unknown" and not p.get("full_name"):
            p["full_name"] = name
            changed = True
        username = (username or "").strip()
        if username and not p.get("username"):
            p["username"] = username
            changed = True

    for slip in load_all_slips().values():
        _ensure(slip.get("chat_id"), name=slip.get("username", ""))

    for order in load_orders().values():
        _ensure(order.get("chat_id"), name=order.get("user_name", ""))

    if changed:
        save_all_profiles(profiles)
    return profiles
