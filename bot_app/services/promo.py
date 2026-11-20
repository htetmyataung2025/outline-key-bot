"""Facebook promo keys (Bot Update #18).

The owner posts a promo code on Facebook; a customer who sends that
code in the in-app Support Chat gets one free trial key from the
support agent: 10 GB / 5 days on Server 2, named after the customer.
``create_outline_key`` ends the key name with the expiry date, so the
nightly expiry cron deletes the key automatically when the 5 days
are up, and ``save_persistent_key`` inside it lands the key in the
customer's My Keys like any purchased key.

One claim per Telegram account and a hard cap on total claims, both
recorded in KV under ``promo_claims:<code-lower>`` as
``{chat_id: {"ts", "key_name", "expire_date"}}``.
"""

import random
import string
import time

from bot_app.services.app_notify import push_app_notification
from bot_app.services.orders import save_key_mapping, save_user_purchase_record
from bot_app.services.outline import create_outline_key
from bot_app.services.profiles import get_user_profile
from bot_app.storage.kv import redis_delete, redis_get, redis_set, redis_set_nx

PROMO_CODE = "HEFREEFORYOU"
PROMO_SERVER = "2"
PROMO_GB = 10
PROMO_DAYS = 5
PROMO_CAP = 50

_CLAIMS_KEY = f"promo_claims:{PROMO_CODE.lower()}"
_LOCK_KEY = f"{_CLAIMS_KEY}:lock"
_LOCK_TTL_S = 20


def _load_claims() -> dict:
    data = redis_get(_CLAIMS_KEY)
    return data if isinstance(data, dict) else {}


def promo_status() -> dict:
    claims = _load_claims()
    return {
        "claimed": len(claims),
        "cap": PROMO_CAP,
        "remaining": max(0, PROMO_CAP - len(claims)),
    }


def claim_promo_key(chat_id, fallback_name: str = "") -> dict:
    """Issue the promo key for ``chat_id`` (one per account, capped).

    Returns ``{"ok": True, "vpn_key", "key_name", "expire_date", ...}``
    or ``{"ok": False, "error": <already_claimed|cap_reached|busy|
    key_creation_failed|bad_chat_id>}``. A failed creation is NOT
    recorded, so the customer can simply send the code again.
    """
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return {"ok": False, "error": "bad_chat_id"}

    lock = redis_set_nx(_LOCK_KEY, _LOCK_TTL_S)
    if lock is False:
        return {"ok": False, "error": "busy"}
    try:
        claims = _load_claims()
        prior = claims.get(chat_id)
        if prior:
            return {
                "ok": False,
                "error": "already_claimed",
                "expire_date": prior.get("expire_date", ""),
            }
        if len(claims) >= PROMO_CAP:
            return {"ok": False, "error": "cap_reached"}

        try:
            profile = get_user_profile(chat_id) or {}
        except Exception:
            profile = {}
        user_name = (
            profile.get("full_name") or fallback_name or "Customer"
        ).strip() or "Customer"

        order_id = "PROMO-" + "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
        try:
            vpn_key, key_name, expire_date = create_outline_key(
                PROMO_SERVER,
                user_name,
                custom_gb=PROMO_GB,
                target_chat_id=chat_id,
                custom_days=PROMO_DAYS,
                is_giveaway=True,
                order_id=order_id,
            )
        except Exception:
            vpn_key = key_name = expire_date = None
        if not vpn_key:
            return {"ok": False, "error": "key_creation_failed"}

        claims[chat_id] = {
            "ts": int(time.time()),
            "key_name": key_name,
            "expire_date": expire_date,
        }
        redis_set(_CLAIMS_KEY, claims)

        try:
            save_user_purchase_record(
                chat_id=chat_id,
                order_id=order_id,
                plan_name="Free Promo (Facebook)",
                disp_gb=f"{PROMO_GB} GB",
                months_count=1,
                price_str="0 Ks (Promo)",
                server_num=PROMO_SERVER,
                expire_date=expire_date,
                vpn_key=vpn_key,
            )
            save_key_mapping(user_name.strip().lower(), chat_id)
        except Exception:
            pass
        try:
            push_app_notification(
                chat_id,
                "promo",
                "အခမဲ့ Promo Key ရပါပြီ 🎉",
                f"{PROMO_GB} GB · {PROMO_DAYS} Days · Server {PROMO_SERVER}"
                f" · Expire {expire_date}",
            )
        except Exception:
            pass

        return {
            "ok": True,
            "vpn_key": vpn_key,
            "key_name": key_name,
            "expire_date": expire_date,
            "gb": PROMO_GB,
            "days": PROMO_DAYS,
            "server": PROMO_SERVER,
            "claimed_count": len(claims),
        }
    finally:
        if lock is True:
            try:
                redis_delete(_LOCK_KEY)
            except Exception:
                pass
